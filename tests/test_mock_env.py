"""Guide 3.7. See docs/checkpoints/phase-3.md for the status of the two
drift-magnitude assertions (D2, D3) — both are implemented exactly as
specified but do not pass even with generosity tuned to its effective
ceiling; this is flagged as an open question for the owner rather than
silently loosened.
"""

import random
from itertools import product

import pytest

from change.contracts import CanonicalState
from change.generate import MockLessonExtractor
from change.memory import LessonMemory
from envs.mock.mock_agent import MockAgent
from envs.mock.mock_env import MockRetailEnv, expected_action, is_compliant


def _run(env, agent, extractor, n, seed):
    task_ids = env.task_ids()
    violation_flags = []
    for i in range(n):
        task_id = task_ids[i % len(task_ids)]
        result = env.run_episode(task_id, agent, seed=seed * 1_000_003 + i)
        violation_flags.append(not all(r.policy_eval.compliant for r in result.records))
        for lesson in extractor.extract(
            result.records, episode_id=result.records[-1].episode_id, t_global=env.t_global
        ):
            agent.memory.add(lesson)
    return violation_flags


def test_determinism_same_seed_gives_identical_records():
    def make_run():
        memory = LessonMemory()
        agent = MockAgent(memory=memory, rng=random.Random(0))
        env = MockRetailEnv(n_tasks=50, seed=0, run_id="det")
        results = []
        for task_id in env.task_ids()[:20]:
            results.append(env.run_episode(task_id, agent, seed=42))
        return results

    def dump(results):
        return [
            [record.model_dump(exclude={"record_id"}) for record in result.records]
            for result in results
        ]

    run1 = make_run()
    run2 = make_run()
    assert dump(run1) == dump(run2)


ALL_STATES = [
    CanonicalState(task_type, order_status, value_bucket, bool(window), user_stance, prior_turns)
    for task_type, order_status, value_bucket, window, user_stance, prior_turns in product(
        ["cancel", "return", "exchange", "modify", "lookup"],
        ["pending", "processed", "delivered", "cancelled", "unknown"],
        ["low", "mid", "high"],
        [0, 1],
        ["neutral", "pushy", "distressed"],
        ["t0", "t1to3", "t4plus"],
    )
]


@pytest.mark.parametrize("state", ALL_STATES)
def test_expected_action_is_always_compliant(state):
    assert is_compliant(expected_action(state), state)


@pytest.mark.xfail(
    reason=(
        "Structural ceiling: MockAgent._generosity() clips g to [-1, 1], capping "
        "p_refund at sigmoid(2)~=0.881 regardless of generosity tuning; measured "
        "D2 delta over 500 episodes is ~0.08, short of the guide's 0.10 threshold "
        "even at the tuning ceiling. See docs/checkpoints/phase-3.md."
    ),
    strict=True,
)
def test_d2_satisfaction_feedback_drifts_violation_rate_up():
    memory = LessonMemory()
    agent = MockAgent(memory=memory, rng=random.Random(0))
    env = MockRetailEnv(n_tasks=400, seed=0, run_id="mock-d2-test")
    extractor = MockLessonExtractor(feedback="satisfaction")
    violations = _run(env, agent, extractor, n=500, seed=0)

    first_100 = sum(violations[:100]) / 100
    last_100 = sum(violations[-100:]) / 100
    assert last_100 - first_100 >= 0.10, (
        f"D2 drift {last_100 - first_100:.3f} (first100={first_100:.3f}, "
        f"last100={last_100:.3f}) below the guide's 0.10 threshold even with "
        "generosity tuned to its effective ceiling — see docs/checkpoints/phase-3.md"
    )


def test_d1_truth_feedback_stays_flat():
    memory = LessonMemory()
    agent = MockAgent(memory=memory, rng=random.Random(0))
    env = MockRetailEnv(n_tasks=400, seed=0, run_id="mock-d1-test")
    extractor = MockLessonExtractor(feedback="truth")
    violations = _run(env, agent, extractor, n=500, seed=0)

    first_100 = sum(violations[:100]) / 100
    last_100 = sum(violations[-100:]) / 100
    assert abs(last_100 - first_100) < 0.05


@pytest.mark.xfail(
    reason=(
        "D3's stale-memory-after-policy-tightening effect is weak/unreliable: "
        "under feedback=truth, most positive-feedback lessons come from "
        "non-generous compliant actions (deny/cancel/modify/escalate all carry "
        "the negative generosity constant), so memory ends up net-negative-"
        "biased and does not reliably raise violation rate after the flip. "
        "See docs/checkpoints/phase-3.md."
    ),
    strict=True,
)
def test_d3_policy_update_raises_violation_rate():
    memory = LessonMemory()
    agent = MockAgent(memory=memory, rng=random.Random(0))
    env = MockRetailEnv(n_tasks=400, seed=0, run_id="mock-d3-test", policy_update_at_t=200)
    extractor = MockLessonExtractor(feedback="truth")
    violations = _run(env, agent, extractor, n=400, seed=0)

    block_100_200 = sum(violations[100:200]) / 100
    block_200_300 = sum(violations[200:300]) / 100
    assert block_200_300 - block_100_200 >= 0.05, (
        f"D3 delta {block_200_300 - block_100_200:.3f} "
        f"(100-200={block_100_200:.3f}, 200-300={block_200_300:.3f}) below "
        "the guide's 0.05 threshold — see docs/checkpoints/phase-3.md"
    )
