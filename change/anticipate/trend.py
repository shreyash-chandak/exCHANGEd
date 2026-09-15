"""T1 nonstationary trend model and the naive last-value baseline (guide 6.1)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from change.config import TREND_LOGIT_CLIP, TREND_MIN_SNAPSHOTS
from change.contracts import BehavioralSnapshot, CanonicalAction

ALL_ACTIONS = [a.value for a in CanonicalAction]


def _logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))


@dataclass
class _Cell:
    slope: float
    intercept: float
    residual_std: float


def _weighted_least_squares(
    t: np.ndarray, y: np.ndarray, w: np.ndarray
) -> tuple[float, float, float]:
    sum_w = w.sum()
    mean_t = (w * t).sum() / sum_w
    mean_y = (w * y).sum() / sum_w
    var_t = (w * (t - mean_t) ** 2).sum()
    if var_t <= 0:
        return 0.0, mean_y, 0.0
    slope = (w * (t - mean_t) * (y - mean_y)).sum() / var_t
    intercept = mean_y - slope * mean_t
    residuals = y - (intercept + slope * t)
    residual_var = (w * residuals**2).sum() / sum_w
    return slope, intercept, math.sqrt(max(residual_var, 0.0))


class TrendModel:
    """Per-(state, action) cell: weighted least squares of logit(p) on window
    midpoint t, weights = n_action count. Cells with fewer than
    TREND_MIN_SNAPSHOTS observations fall back to slope 0, intercept =
    logit(last observed p)."""

    def __init__(self):
        self._cells: dict[tuple[str, str], _Cell] = {}
        self._states: list[str] = []
        # Vectorized mirrors of _cells (state x action), built in fit(),
        # used by _logits so predict/predict_sample don't pay per-scalar
        # Python + numpy call overhead in the simulator's hot inner loop.
        self._slopes: np.ndarray = np.zeros((0, len(ALL_ACTIONS)))
        self._intercepts: np.ndarray = np.zeros((0, len(ALL_ACTIONS)))
        self._residual_stds: np.ndarray = np.zeros((0, len(ALL_ACTIONS)))

    def fit(self, snapshots: list[BehavioralSnapshot]) -> TrendModel:
        if not snapshots:
            raise ValueError("TrendModel.fit requires at least one snapshot")
        last = snapshots[-1]
        self._states = sorted(last.p_action.keys())

        # (state, action) -> list of (t_mid, logit_p, weight)
        points: dict[tuple[str, str], list[tuple[float, float, float]]] = {}
        for snapshot in snapshots:
            t_mid = (snapshot.window_start_t + snapshot.window_end_t) / 2.0
            for state, action_probs in snapshot.p_action.items():
                counts = snapshot.n_action.get(state, {})
                for action, p in action_probs.items():
                    weight = counts.get(action, 0)
                    key = (state, action)
                    points.setdefault(key, []).append((t_mid, _logit(p), weight))

        for state in self._states:
            for action in ALL_ACTIONS:
                key = (state, action)
                obs = points.get(key, [])
                n_snapshots_with_state = sum(
                    1
                    for snapshot in snapshots
                    if state in snapshot.n_action and sum(snapshot.n_action[state].values()) > 0
                )
                last_p = last.p_action.get(state, {}).get(action, 1.0 / len(ALL_ACTIONS))

                if n_snapshots_with_state < TREND_MIN_SNAPSHOTS or not obs:
                    self._cells[key] = _Cell(slope=0.0, intercept=_logit(last_p), residual_std=0.0)
                    continue

                t = np.array([o[0] for o in obs])
                y = np.array([o[1] for o in obs])
                w = np.array([o[2] for o in obs], dtype=float)
                if w.sum() <= 0:
                    self._cells[key] = _Cell(slope=0.0, intercept=_logit(last_p), residual_std=0.0)
                    continue
                slope, intercept, residual_std = _weighted_least_squares(t, y, w)
                self._cells[key] = _Cell(
                    slope=slope, intercept=intercept, residual_std=residual_std
                )

        k = len(self._states)
        n_actions = len(ALL_ACTIONS)
        self._slopes = np.zeros((k, n_actions))
        self._intercepts = np.zeros((k, n_actions))
        self._residual_stds = np.zeros((k, n_actions))
        for si, state in enumerate(self._states):
            for ai, action in enumerate(ALL_ACTIONS):
                cell = self._cells[(state, action)]
                self._slopes[si, ai] = cell.slope
                self._intercepts[si, ai] = cell.intercept
                self._residual_stds[si, ai] = cell.residual_std
        return self

    def _logits(self, t: int, noise_rng: np.random.Generator | None) -> np.ndarray:
        """Vectorized (n_states, n_actions) logit matrix -- a single clip
        call over the whole grid rather than one per (state, action)."""
        logits = self._intercepts + self._slopes * t
        if noise_rng is not None:
            nonzero = self._residual_stds > 0
            if nonzero.any():
                logits = logits.copy()
                logits[nonzero] += noise_rng.normal(0.0, self._residual_stds[nonzero])
        return np.clip(logits, -TREND_LOGIT_CLIP, TREND_LOGIT_CLIP)

    def _predict_from_logits(self, logits: np.ndarray) -> dict[str, dict[str, float]]:
        shifted = logits - logits.max(axis=1, keepdims=True)
        exp = np.exp(shifted)
        probs = exp / exp.sum(axis=1, keepdims=True)
        return {state: dict(zip(ALL_ACTIONS, probs[i])) for i, state in enumerate(self._states)}

    def predict(self, t: int) -> dict[str, dict[str, float]]:
        return self._predict_from_logits(self._logits(t, noise_rng=None))

    def predict_sample(self, t: int, rng: np.random.Generator) -> dict[str, dict[str, float]]:
        return self._predict_from_logits(self._logits(t, noise_rng=rng))


class LastValueModel:
    """Naive baseline: always returns the last snapshot's p_action, ignoring t."""

    def __init__(self):
        self._p_action: dict[str, dict[str, float]] = {}

    def fit(self, snapshots: list[BehavioralSnapshot]) -> LastValueModel:
        if not snapshots:
            raise ValueError("LastValueModel.fit requires at least one snapshot")
        self._p_action = snapshots[-1].p_action
        return self

    def predict(self, t: int) -> dict[str, dict[str, float]]:
        return self._p_action

    def predict_sample(self, t: int, rng: np.random.Generator) -> dict[str, dict[str, float]]:
        return self._p_action
