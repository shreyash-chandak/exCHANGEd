"""Behavioral envelope, time-to-exit, and Prediction assembly (guide 6.3)."""

from __future__ import annotations

from collections import Counter
from uuid import uuid4

import numpy as np

from change.anticipate.simulator import ALL_ACTIONS, SimOutput
from change.config import (
    ENVELOPE_COST_RATIO_MAX,
    ENVELOPE_SUCCESS_DROP_MAX,
    ENVELOPE_VIOLATION_MAX,
    SIM_ROLLING_WINDOW,
)
from change.contracts import BehavioralSnapshot, CellAttribution, Prediction


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """Expanding mean for t < window, fixed trailing window mean after."""
    cumsum = np.cumsum(arr, axis=1)
    _, horizon = arr.shape
    out = np.empty_like(arr, dtype=float)
    t_idx = np.arange(horizon)
    expanding = cumsum / (t_idx + 1)
    windowed = np.empty_like(arr, dtype=float)
    windowed[:, :window] = expanding[:, :window]
    if horizon > window:
        windowed[:, window:] = (cumsum[:, window:] - cumsum[:, : horizon - window]) / window
    out[:] = windowed
    return out


class Envelope:
    def __init__(self, baseline_success: float, baseline_cost: float):
        self.baseline_success = baseline_success
        self.baseline_cost = baseline_cost if baseline_cost > 0 else 1e-9
        self.violation_max = ENVELOPE_VIOLATION_MAX
        self.success_drop_max = ENVELOPE_SUCCESS_DROP_MAX
        self.cost_ratio_max = ENVELOPE_COST_RATIO_MAX

    def _rolling(self, sim: SimOutput) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rolling_violation = _rolling_mean(sim.violation, SIM_ROLLING_WINDOW)
        rolling_success = _rolling_mean(sim.success, SIM_ROLLING_WINDOW)
        rolling_cost = _rolling_mean(sim.cost, SIM_ROLLING_WINDOW) / self.baseline_cost
        return rolling_violation, rolling_success, rolling_cost

    def first_exit(self, sim: SimOutput) -> tuple[int | None, int | None, int | None, str | None]:
        rolling_violation, rolling_success, rolling_cost = self._rolling(sim)
        n_traj, _ = sim.violation.shape

        breach_violation = rolling_violation > self.violation_max
        breach_success = (self.baseline_success - rolling_success) > self.success_drop_max
        breach_cost = rolling_cost > self.cost_ratio_max
        # Ignore the ramp-up period before the rolling window has enough
        # samples to be a stable estimate (avoids spurious early exits from
        # a single unlucky sample averaged over very few points).
        breach_violation[:, : SIM_ROLLING_WINDOW - 1] = False
        breach_success[:, : SIM_ROLLING_WINDOW - 1] = False
        breach_cost[:, : SIM_ROLLING_WINDOW - 1] = False

        exit_times: list[int] = []
        exit_metrics: list[str] = []
        for i in range(n_traj):
            t_v = np.argmax(breach_violation[i]) if breach_violation[i].any() else None
            t_s = np.argmax(breach_success[i]) if breach_success[i].any() else None
            t_c = np.argmax(breach_cost[i]) if breach_cost[i].any() else None
            candidates = [
                (t, metric)
                for t, metric in [(t_v, "violation"), (t_s, "success"), (t_c, "cost")]
                if t is not None
            ]
            if not candidates:
                continue
            t_exit, metric = min(candidates, key=lambda c: c[0])
            exit_times.append(int(t_exit))
            exit_metrics.append(metric)

        if len(exit_times) < 0.5 * n_traj:
            return None, None, None, None

        exit_arr = np.array(exit_times)
        t_q10 = int(np.percentile(exit_arr, 10))
        t_q50 = int(np.percentile(exit_arr, 50))
        t_q90 = int(np.percentile(exit_arr, 90))
        exit_metric = Counter(exit_metrics).most_common(1)[0][0]
        return t_q10, t_q50, t_q90, exit_metric

    def margin(self, sim: SimOutput) -> float:
        rolling_violation, _, _ = self._rolling(sim)
        median_final_violation = float(np.median(rolling_violation[:, -1]))
        return self.violation_max - median_final_violation


def _contributing_cells(
    model, t_end: int, horizon: int, max_cells: int = 3
) -> list[CellAttribution]:
    p_start = model.predict(t_end)
    p_end = model.predict(t_end + horizon)
    candidates: list[tuple[float, str, str]] = []
    for state in set(p_start) & set(p_end):
        for action in ALL_ACTIONS:
            delta = p_end[state].get(action, 0.0) - p_start[state].get(action, 0.0)
            candidates.append((delta, state, action))
    candidates.sort(key=lambda c: abs(c[0]), reverse=True)
    return [
        CellAttribution(state_key=state, action=action, delta_p=delta, lesson_ids=[])
        for delta, state, action in candidates[:max_cells]
    ]


def make_prediction(
    snapshot: BehavioralSnapshot,
    candidate_id: str,
    model,
    sim: SimOutput,
    envelope: Envelope,
    twin_model: str,
) -> Prediction:
    rolling_violation, rolling_success, rolling_cost = envelope._rolling(sim)
    n_blocks = sim.violation.shape[1] // SIM_ROLLING_WINDOW
    q10, q50, q90 = [], [], []
    for b in range(n_blocks):
        idx = (b + 1) * SIM_ROLLING_WINDOW - 1
        col = rolling_violation[:, idx]
        q10.append(float(np.percentile(col, 10)))
        q50.append(float(np.percentile(col, 50)))
        q90.append(float(np.percentile(col, 90)))

    t_q10, t_q50, t_q90, exit_metric = envelope.first_exit(sim)
    margin = envelope.margin(sim)

    return Prediction(
        prediction_id=str(uuid4()),
        snapshot_id=snapshot.snapshot_id,
        candidate_id=candidate_id,
        twin_model=twin_model,
        horizon=sim.violation.shape[1],
        violation_curve_q10=q10,
        violation_curve_q50=q50,
        violation_curve_q90=q90,
        success_q50=float(np.median(rolling_success[:, -1])),
        cost_ratio_q50=float(np.median(rolling_cost[:, -1])),
        first_exit_t_q10=t_q10,
        first_exit_t_q50=t_q50,
        first_exit_t_q90=t_q90,
        exit_metric=exit_metric,
        contributing_cells=_contributing_cells(
            model, snapshot.window_end_t, sim.violation.shape[1]
        ),
        envelope_margin_q50=margin,
    )
