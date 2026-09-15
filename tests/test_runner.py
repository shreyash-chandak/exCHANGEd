import time

from change.contracts import (
    CanonicalAction,
    CanonicalOutcome,
    CanonicalState,
    ExperienceRecord,
    PolicyEval,
)
from change.runner import run_concurrent_episodes, write_episode_records
from change.store import JsonlStore
from envs.base import ActionChoice, EpisodeResult

STATE = CanonicalState("return", "delivered", "high", True, "neutral", "t0")


class _FakeAgent:
    agent_id = "alice"
    agent_version = 1
    memory_version = 0

    def act(self, obs: dict) -> ActionChoice:
        return ActionChoice(action=CanonicalAction.REFUND_FULL)

    def observe_outcome(self, action, outcome, policy_eval) -> None:
        pass


class _FakeSlowEnv:
    """run_episode sleeps proportionally to `seed` so *lower*-seed tasks
    (submitted first) finish *last* -- completion order is the reverse of
    submission order, forcing a real test of out-of-order handling."""

    def task_ids(self) -> list[str]:
        return ["t0", "t1", "t2"]

    def run_episode(self, task_id: str, agent, seed: int) -> EpisodeResult:
        time.sleep((3 - seed) * 0.05)
        record = ExperienceRecord(
            run_id="r1",
            agent_id=agent.agent_id,
            agent_version=agent.agent_version,
            memory_version=agent.memory_version,
            episode_id=f"ep-{task_id}",
            task_id=task_id,
            episode_seed=seed,
            turn_idx=0,
            t_global=-1,  # deliberately wrong -- write_episode_records must override this
            state=STATE,
            action=CanonicalAction.REFUND_FULL,
            outcome=CanonicalOutcome(True, True, True, 10.0),
            policy_eval=PolicyEval(compliant=True, violated_rule_ids=[]),
            latency_ms=100.0,
            tokens_in=10,
            tokens_out=5,
            cost_usd=0.01,
        )
        return EpisodeResult(records=[record], reward=1.0)


def test_run_concurrent_episodes_yields_in_completion_not_submission_order():
    env = _FakeSlowEnv()
    agent = _FakeAgent()
    pairs = [("t0", 1), ("t1", 2), ("t2", 3)]  # seed=1 sleeps longest, seed=3 shortest

    completed = [
        (task_id, seed) for task_id, seed, _ in run_concurrent_episodes(env, agent, pairs, 3)
    ]

    # seed=3 (shortest sleep) finishes first, seed=1 (longest) finishes last --
    # the reverse of submission order.
    assert completed == [("t2", 3), ("t1", 2), ("t0", 1)]


def test_run_concurrent_episodes_respects_max_concurrency(tmp_path):
    env = _FakeSlowEnv()
    agent = _FakeAgent()
    pairs = [("t0", 1), ("t1", 2), ("t2", 3)]

    start = time.monotonic()
    list(run_concurrent_episodes(env, agent, pairs, max_concurrency=1))
    serial_elapsed = time.monotonic() - start

    start = time.monotonic()
    list(run_concurrent_episodes(env, agent, pairs, max_concurrency=3))
    parallel_elapsed = time.monotonic() - start

    assert parallel_elapsed < serial_elapsed


def test_write_episode_records_assigns_t_global_at_write_time_sequentially(tmp_path):
    store = JsonlStore(tmp_path / "run")
    env = _FakeSlowEnv()
    agent = _FakeAgent()
    pairs = [("t0", 1), ("t1", 2), ("t2", 3)]

    next_t = 0
    write_order = []
    for task_id, seed, result in run_concurrent_episodes(env, agent, pairs, max_concurrency=3):
        write_order.append(task_id)
        next_t = write_episode_records(store, result.records, next_t)

    written = list(store.iter(ExperienceRecord))
    assert [r.t_global for r in written] == list(range(len(written)))
    # t_global order matches completion (write) order, not submission order
    assert [r.task_id for r in written] == write_order
