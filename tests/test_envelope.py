import numpy as np

from change.anticipate.envelope import Envelope
from change.anticipate.simulator import SimOutput


def _step_violation_sim(
    n_traj: int, horizon: int, step_t: int, low: float, high: float
) -> SimOutput:
    period = 20
    low_count = round(low * period)
    high_count = round(high * period)
    violation = np.zeros((n_traj, horizon))
    for t in range(horizon):
        if t < step_t:
            violation[:, t] = 1.0 if (t % period) < low_count else 0.0
        else:
            violation[:, t] = 1.0 if (t % period) < high_count else 0.0
    success = np.ones((n_traj, horizon))
    cost = np.full((n_traj, horizon), 10.0)
    return SimOutput(violation=violation, success=success, cost=cost)


def test_first_exit_detects_step_change_near_the_step():
    sim = _step_violation_sim(n_traj=10, horizon=900, step_t=700, low=0.05, high=0.15)
    envelope = Envelope(baseline_success=0.9, baseline_cost=10.0)
    _t_q10, t_q50, _t_q90, exit_metric = envelope.first_exit(sim)
    assert t_q50 is not None
    assert 700 <= t_q50 <= 800
    assert exit_metric == "violation"


def test_first_exit_none_when_fewer_than_half_exit():
    exiting = _step_violation_sim(n_traj=4, horizon=900, step_t=700, low=0.05, high=0.15)
    never_exits = np.zeros((6, 900))
    violation = np.concatenate([exiting.violation, never_exits], axis=0)
    success = np.ones_like(violation)
    cost = np.full_like(violation, 10.0)
    sim = SimOutput(violation=violation, success=success, cost=cost)

    envelope = Envelope(baseline_success=0.9, baseline_cost=10.0)
    result = envelope.first_exit(sim)
    assert result == (None, None, None, None)


def test_margin_is_violation_max_minus_median_final_rolling_violation():
    sim = _step_violation_sim(n_traj=10, horizon=900, step_t=700, low=0.05, high=0.15)
    envelope = Envelope(baseline_success=0.9, baseline_cost=10.0)
    margin = envelope.margin(sim)
    assert abs(margin - (envelope.violation_max - 0.15)) < 0.02
