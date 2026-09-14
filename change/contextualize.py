"""Contextualize: versioned behavioral snapshots, drift, attribution (guide 5.1)."""

from __future__ import annotations

import random
from collections import defaultdict
from itertools import pairwise

import numpy as np

from change.config import DIRICHLET_ALPHA, DRIFT_BOOTSTRAP_N, MIN_CELL_COUNT, WINDOW_EPISODES
from change.contracts import (
    BehavioralSnapshot,
    CanonicalAction,
    CellAttribution,
    DriftScore,
    ExperienceRecord,
)
from change.store import JsonlStore

ALL_ACTIONS = [a.value for a in CanonicalAction]


def _jsd(p: dict[str, float], q: dict[str, float]) -> float:
    """Jensen-Shannon divergence, base 2, over the union of keys."""
    keys = sorted(set(p) | set(q))
    if not keys:
        return 0.0
    parr = np.array([p.get(k, 0.0) for k in keys], dtype=float)
    qarr = np.array([q.get(k, 0.0) for k in keys], dtype=float)
    p_sum, q_sum = parr.sum(), qarr.sum()
    if p_sum > 0:
        parr = parr / p_sum
    if q_sum > 0:
        qarr = qarr / q_sum
    m = 0.5 * (parr + qarr)

    def _kl(a: np.ndarray, b: np.ndarray) -> float:
        mask = a > 0
        return float(np.sum(a[mask] * np.log2(a[mask] / b[mask])))

    return 0.5 * _kl(parr, m) + 0.5 * _kl(qarr, m)


def weighted_jsd(
    p_a: dict[str, dict[str, float]],
    p_b: dict[str, dict[str, float]],
    weights: dict[str, float],
) -> tuple[float, dict[str, float]]:
    """Weighted-average per-state JSD over states covered in both p_a and p_b."""
    common = set(p_a) & set(p_b)
    per_state_jsd = {state: _jsd(p_a[state], p_b[state]) for state in common}
    total_weight = sum(weights.get(state, 0.0) for state in common)
    if total_weight <= 0:
        return 0.0, per_state_jsd
    jsd_weighted = (
        sum(weights.get(state, 0.0) * per_state_jsd[state] for state in common) / total_weight
    )
    return jsd_weighted, per_state_jsd


def _state_weights(n_action: dict[str, dict[str, int]]) -> dict[str, float]:
    totals = {state: sum(counts.values()) for state, counts in n_action.items()}
    grand_total = sum(totals.values())
    if grand_total <= 0:
        return dict.fromkeys(totals, 0.0)
    return {state: total / grand_total for state, total in totals.items()}


def build_snapshot(
    records: list[ExperienceRecord],
    parent: BehavioralSnapshot | None,
    run_id: str,
    snapshot_id: str | None = None,
    parent_records: list[ExperienceRecord] | None = None,
) -> BehavioralSnapshot:
    if not records:
        raise ValueError("build_snapshot requires at least one record")

    agent_id = records[0].agent_id
    last = records[-1]
    snapshot_id = snapshot_id or f"{run_id}-snap-{last.t_global}"

    n_action: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    outcome_sums: dict[str, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: {"compliant": 0.0, "success": 0.0, "satisfied": 0.0, "n": 0.0})
    )
    initial_counts: dict[str, int] = defaultdict(int)
    transition_counts: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )

    violations = successes = satisfied_n = 0
    cost_sum = latency_sum = 0.0

    by_episode: dict[str, list[ExperienceRecord]] = defaultdict(list)
    for record in records:
        by_episode[record.episode_id].append(record)

        state_key = record.state.state_key
        action = record.action.value
        n_action[state_key][action] += 1

        cell = outcome_sums[state_key][action]
        cell["compliant"] += float(record.outcome.policy_compliant)
        cell["success"] += float(record.outcome.task_success)
        cell["satisfied"] += float(record.outcome.user_satisfied)
        cell["n"] += 1

        if record.turn_idx == 0:
            initial_counts[state_key] += 1

        if record.outcome.policy_compliant is False:
            violations += 1
        if record.outcome.task_success:
            successes += 1
        if record.outcome.user_satisfied:
            satisfied_n += 1
        cost_sum += record.outcome.cost_delta
        latency_sum += record.latency_ms

    for episode_records in by_episode.values():
        ordered = sorted(episode_records, key=lambda r: r.turn_idx)
        for cur, nxt in pairwise(ordered):
            transition_counts[cur.state.state_key][cur.action.value][nxt.state.state_key] += 1

    p_action: dict[str, dict[str, float]] = {}
    for state_key, counts in n_action.items():
        total = sum(counts.values())
        denom = total + DIRICHLET_ALPHA * len(ALL_ACTIONS)
        p_action[state_key] = {
            action: (counts.get(action, 0) + DIRICHLET_ALPHA) / denom for action in ALL_ACTIONS
        }

    p_outcome: dict[str, dict[str, dict[str, float]]] = {}
    for state_key, actions in outcome_sums.items():
        p_outcome[state_key] = {}
        for action, sums in actions.items():
            n = sums["n"]
            if n <= 0:
                continue
            p_outcome[state_key][action] = {
                "compliant": sums["compliant"] / n,
                "success": sums["success"] / n,
                "satisfied": sums["satisfied"] / n,
            }

    p_transition: dict[str, dict[str, dict[str, float]]] = {}
    for state_key, actions in transition_counts.items():
        p_transition[state_key] = {}
        for action, next_counts in actions.items():
            total = sum(next_counts.values())
            if total <= 0:
                continue
            p_transition[state_key][action] = {s: c / total for s, c in next_counts.items()}

    initial_total = sum(initial_counts.values())
    p_initial = (
        {state: count / initial_total for state, count in initial_counts.items()}
        if initial_total > 0
        else {}
    )

    n_records = len(records)
    coverage = [
        state for state, counts in n_action.items() if sum(counts.values()) >= MIN_CELL_COUNT
    ]

    snapshot = BehavioralSnapshot(
        snapshot_id=snapshot_id,
        parent_id=parent.snapshot_id if parent else None,
        run_id=run_id,
        agent_id=agent_id,
        agent_version=last.agent_version,
        memory_version=last.memory_version,
        window_start_t=min(r.t_global for r in records),
        window_end_t=max(r.t_global for r in records),
        n_records=n_records,
        p_action=p_action,
        n_action={state: dict(counts) for state, counts in n_action.items()},
        p_outcome=p_outcome,
        p_transition=p_transition,
        p_initial=p_initial,
        violation_rate=violations / n_records,
        success_rate=successes / n_records,
        satisfaction_rate=satisfied_n / n_records,
        mean_cost=cost_sum / n_records,
        mean_latency_ms=latency_sum / n_records,
        drift_vs_parent=None,
        coverage=coverage,
    )

    if parent is not None and parent_records:
        snapshot.drift_vs_parent = drift_score(snapshot, parent, records, parent_records)

    return snapshot


def _lesson_ids_for_cell(
    records: list[ExperienceRecord], state_key: str, action: str, max_ids: int = 5
) -> list[str]:
    cell_records = [
        r for r in records if r.state.state_key == state_key and r.action.value == action
    ]
    if not cell_records:
        return []

    cell_counts: dict[str, int] = defaultdict(int)
    for record in cell_records:
        for lesson_id in record.lessons_in_context:
            cell_counts[lesson_id] += 1
    overall_counts: dict[str, int] = defaultdict(int)
    for record in records:
        for lesson_id in record.lessons_in_context:
            overall_counts[lesson_id] += 1

    n_cell = len(cell_records)
    n_overall = len(records)
    ratios: list[tuple[float, str]] = []
    for lesson_id, count in cell_counts.items():
        cell_freq = count / n_cell
        overall_freq = overall_counts[lesson_id] / n_overall
        if overall_freq > 0 and cell_freq > 1.5 * overall_freq:
            ratios.append((cell_freq / overall_freq, lesson_id))
    ratios.sort(key=lambda x: x[0], reverse=True)
    return [lesson_id for _, lesson_id in ratios[:max_ids]]


def drift_score(
    current: BehavioralSnapshot,
    parent: BehavioralSnapshot,
    records_current: list[ExperienceRecord],
    records_parent: list[ExperienceRecord],
) -> DriftScore:
    weights = _state_weights(parent.n_action)
    jsd_weighted, per_state_jsd = weighted_jsd(current.p_action, parent.p_action, weights)

    common_states = set(current.p_action) & set(parent.p_action)
    candidates: list[tuple[float, str, str, float]] = []
    for state in common_states:
        actions = set(current.p_action[state]) | set(parent.p_action[state])
        for action in actions:
            p_cur = current.p_action[state].get(action, 0.0)
            p_par = parent.p_action[state].get(action, 0.0)
            delta = p_cur - p_par
            score = abs(delta) * weights.get(state, 0.0)
            candidates.append((score, state, action, delta))
    candidates.sort(key=lambda c: c[0], reverse=True)
    top_cells = [
        CellAttribution(
            state_key=state,
            action=action,
            delta_p=delta,
            lesson_ids=_lesson_ids_for_cell(records_current, state, action),
        )
        for _, state, action, delta in candidates[:3]
    ]

    ci_low, ci_high = _bootstrap_ci(records_current, parent.p_action, weights)

    return DriftScore(
        jsd_weighted=jsd_weighted,
        jsd_ci_low=ci_low,
        jsd_ci_high=ci_high,
        per_state_jsd=per_state_jsd,
        top_cells=top_cells,
    )


def _bootstrap_ci(
    records_current: list[ExperienceRecord],
    parent_p_action: dict[str, dict[str, float]],
    weights: dict[str, float],
    n_resamples: int = DRIFT_BOOTSTRAP_N,
    seed: int = 0,
) -> tuple[float, float]:
    by_episode: dict[str, list[ExperienceRecord]] = defaultdict(list)
    for record in records_current:
        by_episode[record.episode_id].append(record)
    episode_ids = list(by_episode.keys())
    if not episode_ids:
        return 0.0, 0.0

    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(n_resamples):
        sampled_ids = [rng.choice(episode_ids) for _ in episode_ids]
        sampled_records = [r for eid in sampled_ids for r in by_episode[eid]]
        p_action = _p_action_only(sampled_records)
        jsd_w, _ = weighted_jsd(p_action, parent_p_action, weights)
        values.append(jsd_w)

    values.sort()
    lo_idx = max(0, int(0.05 * len(values)))
    hi_idx = min(len(values) - 1, int(0.95 * len(values)))
    return values[lo_idx], values[hi_idx]


def _p_action_only(records: list[ExperienceRecord]) -> dict[str, dict[str, float]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in records:
        counts[record.state.state_key][record.action.value] += 1
    p_action: dict[str, dict[str, float]] = {}
    for state_key, action_counts in counts.items():
        total = sum(action_counts.values())
        denom = total + DIRICHLET_ALPHA * len(ALL_ACTIONS)
        p_action[state_key] = {
            action: (action_counts.get(action, 0) + DIRICHLET_ALPHA) / denom
            for action in ALL_ACTIONS
        }
    return p_action


class Snapshotter:
    """Consumes records one at a time, emits a BehavioralSnapshot every
    `window` episodes or whenever memory_version has changed by 10+ since
    the last snapshot, whichever comes first. Persists to `store`.
    """

    def __init__(self, store: JsonlStore, window: int = WINDOW_EPISODES):
        self.store = store
        self.window = window
        self._buffer: list[ExperienceRecord] = []
        self._episode_ids_seen: set[str] = set()
        self._last_memory_version = 0
        self._parent: BehavioralSnapshot | None = None
        self._parent_records: list[ExperienceRecord] = []
        self._snapshot_count = 0

    def consume(self, record: ExperienceRecord) -> BehavioralSnapshot | None:
        self._buffer.append(record)
        self._episode_ids_seen.add(record.episode_id)

        should_emit = (
            len(self._episode_ids_seen) >= self.window
            or (record.memory_version - self._last_memory_version) >= 10
        )
        if not should_emit:
            return None

        snapshot = build_snapshot(
            self._buffer,
            parent=self._parent,
            run_id=record.run_id,
            snapshot_id=f"{record.run_id}-snap{self._snapshot_count}",
            parent_records=self._parent_records,
        )
        self.store.append(snapshot)

        self._parent = snapshot
        self._parent_records = list(self._buffer)
        self._snapshot_count += 1
        self._last_memory_version = record.memory_version
        self._buffer = []
        self._episode_ids_seen = set()
        return snapshot


def _print_snapshot_table(run_id: str, runs_dir: str = "runs") -> None:
    from pathlib import Path

    store = JsonlStore(Path(runs_dir) / run_id)
    snapshotter = Snapshotter(store)
    header = f"{'id':<24}{'window':<16}{'n':>6}{'violation':>11}{'jsd':>8}  top_cell"
    print(header)
    for record in store.iter(ExperienceRecord):
        snapshot = snapshotter.consume(record)
        if snapshot is None:
            continue
        jsd = snapshot.drift_vs_parent.jsd_weighted if snapshot.drift_vs_parent else 0.0
        top_cell = ""
        if snapshot.drift_vs_parent and snapshot.drift_vs_parent.top_cells:
            top = snapshot.drift_vs_parent.top_cells[0]
            top_cell = f"{top.state_key}|{top.action} ({top.delta_p:+.3f})"
        window = f"{snapshot.window_start_t}-{snapshot.window_end_t}"
        print(
            f"{snapshot.snapshot_id:<24}{window:<16}{snapshot.n_records:>6}"
            f"{snapshot.violation_rate:>11.3f}{jsd:>8.3f}  {top_cell}"
        )


if __name__ == "__main__":
    import typer

    def _main(
        run_id: str = typer.Option(..., "--run-id"), runs_dir: str = typer.Option("runs")
    ) -> None:
        _print_snapshot_table(run_id, runs_dir)

    typer.run(_main)
