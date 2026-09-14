import math

import numpy as np

from change.anticipate.trend import ALL_ACTIONS, LastValueModel, TrendModel
from change.config import TREND_MIN_SNAPSHOTS
from change.contracts import BehavioralSnapshot


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _make_snapshot(
    snapshot_id: str, t_mid: int, p_refund_full: float, n_total: int = 200
) -> BehavioralSnapshot:
    remainder = (1.0 - p_refund_full) / (len(ALL_ACTIONS) - 1)
    p_action = {a: remainder for a in ALL_ACTIONS}
    p_action["refund_full"] = p_refund_full
    n_action = {a: round(p * n_total) for a, p in p_action.items()}
    return BehavioralSnapshot(
        snapshot_id=snapshot_id,
        parent_id=None,
        run_id="r1",
        agent_id="alice",
        agent_version=1,
        memory_version=0,
        window_start_t=t_mid,
        window_end_t=t_mid,
        n_records=n_total,
        p_action={"s1": p_action},
        n_action={"s1": n_action},
        p_outcome={},
        p_transition={},
        p_initial={"s1": 1.0},
        violation_rate=0.1,
        success_rate=0.8,
        satisfaction_rate=0.8,
        mean_cost=10.0,
        mean_latency_ms=800.0,
        coverage=["s1"],
    )


def test_trend_recovers_known_slope_within_20_percent():
    true_intercept, true_slope = -1.0, 0.01
    ts = list(range(0, 500, 50))
    snapshots = [
        _make_snapshot(f"s{i}", t, _sigmoid(true_intercept + true_slope * t))
        for i, t in enumerate(ts)
    ]
    model = TrendModel().fit(snapshots)
    cell = model._cells[("s1", "refund_full")]
    assert abs(cell.slope - true_slope) < 0.2 * abs(true_slope)


def test_fewer_than_min_snapshots_falls_back_to_last_value():
    snapshots = [_make_snapshot(f"s{i}", t, 0.3 + 0.01 * t) for i, t in enumerate([0, 50])]
    assert len(snapshots) < TREND_MIN_SNAPSHOTS
    model = TrendModel().fit(snapshots)
    cell = model._cells[("s1", "refund_full")]
    assert cell.slope == 0.0
    last_p = snapshots[-1].p_action["s1"]["refund_full"]
    assert cell.intercept == _logit(last_p)


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def test_predictions_sum_to_one_per_state():
    ts = list(range(0, 500, 50))
    snapshots = [_make_snapshot(f"s{i}", t, _sigmoid(-1.0 + 0.01 * t)) for i, t in enumerate(ts)]
    model = TrendModel().fit(snapshots)
    prediction = model.predict(1000)
    assert abs(sum(prediction["s1"].values()) - 1.0) < 1e-9

    rng = np.random.default_rng(0)
    sampled = model.predict_sample(1000, rng)
    assert abs(sum(sampled["s1"].values()) - 1.0) < 1e-9


def test_last_value_model_ignores_t():
    ts = list(range(0, 500, 50))
    snapshots = [_make_snapshot(f"s{i}", t, _sigmoid(-1.0 + 0.01 * t)) for i, t in enumerate(ts)]
    model = LastValueModel().fit(snapshots)
    assert model.predict(0) == model.predict(10_000) == snapshots[-1].p_action
