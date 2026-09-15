"""Guide 6.5's D2 forecast comparison. Per the guide: if T1 does not beat
LastValue, report both errors rather than tuning. At seed 0, post the
session-2 population revision (docs/checkpoints/phase-3.md "Revision"),
T1 beats LastValue by 0.0151 absolute error (t1_error=0.2082,
lv_error=0.2233, target=0.2778) -- clear of session-2 guide 4.0's 0.005
STOP threshold, up from the pre-revision margin of ~0.0004. See
docs/checkpoints/phase-6.md for the full numbers."""

import random

from change.anticipate.trend import LastValueModel, TrendModel
from change.contextualize import _state_weights, build_snapshot
from change.contracts import BehavioralSnapshot, ExperienceRecord
from change.generate import MockLessonExtractor
from change.memory import LessonMemory
from envs.mock.mock_agent import MockAgent
from envs.mock.mock_env import MockRetailEnv


def _run_windowed(
    feedback: str, seed: int = 0, n: int = 1000, window: int = 50
) -> list[BehavioralSnapshot]:
    memory = LessonMemory()
    agent = MockAgent(memory=memory, rng=random.Random(seed))
    env = MockRetailEnv(n_tasks=400, seed=seed, run_id="d2fc")
    extractor = MockLessonExtractor(feedback=feedback)
    task_ids = env.task_ids()

    by_episode: dict[str, list[ExperienceRecord]] = {}
    episode_order: list[str] = []
    for i in range(n):
        task_id = task_ids[i % len(task_ids)]
        result = env.run_episode(task_id, agent, seed=seed * 1_000_003 + i)
        episode_id = result.records[0].episode_id
        by_episode[episode_id] = result.records
        episode_order.append(episode_id)
        for lesson in extractor.extract(
            result.records, episode_id=episode_id, t_global=env.t_global
        ):
            memory.add(lesson)

    snapshots = []
    parent = None
    parent_records = None
    for start in range(0, len(episode_order), window):
        chunk_ids = episode_order[start : start + window]
        chunk_records = [r for eid in chunk_ids for r in by_episode[eid]]
        if not chunk_records:
            continue
        snapshot = build_snapshot(
            chunk_records, parent=parent, run_id="d2fc", parent_records=parent_records
        )
        snapshots.append(snapshot)
        parent = snapshot
        parent_records = chunk_records
    return snapshots


def _predicted_violation_rate(
    p_action_dict: dict[str, dict[str, float]],
    outcome_snapshot: BehavioralSnapshot,
    weights: dict[str, float],
) -> float | None:
    total_w = 0.0
    acc = 0.0
    for state, dist in p_action_dict.items():
        w = weights.get(state, 0.0)
        if w <= 0:
            continue
        outcomes = outcome_snapshot.p_outcome.get(state)
        if not outcomes:
            continue
        violation = sum(dist.get(a, 0.0) * (1 - outcomes[a]["compliant"]) for a in outcomes)
        acc += w * violation
        total_w += w
    return acc / total_w if total_w > 0 else None


def test_t1_forecast_beats_last_value_baseline_on_mock_d2():
    snapshots = _run_windowed("satisfaction", seed=0, n=1000, window=50)

    cutoff_idx = min(range(len(snapshots)), key=lambda i: abs(snapshots[i].window_end_t - 400))
    target_idx = min(range(len(snapshots)), key=lambda i: abs(snapshots[i].window_end_t - 900))
    fit_snapshots = snapshots[: cutoff_idx + 1]
    cutoff = snapshots[cutoff_idx]
    weights = _state_weights(cutoff.n_action)

    t1 = TrendModel().fit(fit_snapshots)
    last_value = LastValueModel().fit(fit_snapshots)

    target_actual = snapshots[target_idx].violation_rate
    t1_pred = _predicted_violation_rate(t1.predict(900), cutoff, weights)
    lv_pred = _predicted_violation_rate(last_value.predict(900), cutoff, weights)

    t1_error = abs(t1_pred - target_actual)
    lv_error = abs(lv_pred - target_actual)

    assert t1_error < lv_error, (
        f"T1 error {t1_error:.4f} not below LastValue error {lv_error:.4f} "
        f"(target={target_actual:.4f}, T1 pred={t1_pred:.4f}, LV pred={lv_pred:.4f}) "
        "-- see docs/checkpoints/phase-6.md"
    )
