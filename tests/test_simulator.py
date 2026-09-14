import time

import numpy as np

from change.anticipate.simulator import simulate
from change.anticipate.trend import LastValueModel
from change.config import SIM_HORIZON, SIM_TRAJECTORIES
from change.contracts import BehavioralSnapshot

OUTSIDE_WINDOW_RETURN_STATE = "return|delivered|high|0|neutral|t0"


def _snapshot(
    state_key: str, p_action: dict[str, float], p_compliant: dict[str, float]
) -> BehavioralSnapshot:
    all_actions = list(p_action.keys())
    n_total = 200
    n_action = {a: round(p * n_total) for a, p in p_action.items()}
    p_outcome = {
        a: {"compliant": p_compliant[a], "success": p_compliant[a], "satisfied": p_compliant[a]}
        for a in all_actions
    }
    violation_rate = sum(p_action[a] * (1 - p_compliant[a]) for a in all_actions)
    return BehavioralSnapshot(
        snapshot_id="s0",
        parent_id=None,
        run_id="r1",
        agent_id="alice",
        agent_version=1,
        memory_version=0,
        window_start_t=0,
        window_end_t=0,
        n_records=n_total,
        p_action={state_key: p_action},
        n_action={state_key: n_action},
        p_outcome={state_key: p_outcome},
        p_transition={},
        p_initial={state_key: 1.0},
        violation_rate=violation_rate,
        success_rate=1 - violation_rate,
        satisfaction_rate=1 - violation_rate,
        mean_cost=10.0,
        mean_latency_ms=800.0,
        coverage=[state_key],
    )


def test_stationary_model_matches_snapshot_violation_rate_at_horizon():
    state_key = "s1"
    snapshot = _snapshot(
        state_key, {"refund_full": 0.3, "deny": 0.7}, {"refund_full": 0.0, "deny": 1.0}
    )
    model = LastValueModel().fit([snapshot])
    rng = np.random.default_rng(0)
    sim = simulate(model, snapshot, n_traj=2000, horizon=500, rng=rng)
    assert abs(sim.violation.mean() - snapshot.violation_rate) < 0.02


def test_patching_refund_full_to_zero_drops_violation():
    snapshot = _snapshot(
        OUTSIDE_WINDOW_RETURN_STATE,
        {"refund_full": 0.5, "deny": 0.5},
        {"refund_full": 0.0, "deny": 1.0},
    )
    model = LastValueModel().fit([snapshot])
    rng = np.random.default_rng(0)
    unpatched = simulate(model, snapshot, n_traj=2000, horizon=300, rng=rng)

    patches = {OUTSIDE_WINDOW_RETURN_STATE: {"refund_full": 0.0, "deny": 1.0}}
    rng2 = np.random.default_rng(0)
    patched = simulate(model, snapshot, n_traj=2000, horizon=300, rng=rng2, patches=patches)

    assert patched.violation.mean() < unpatched.violation.mean() - 0.1


def test_runtime_under_30_seconds():
    snapshot = _snapshot("s1", {"refund_full": 0.3, "deny": 0.7}, {"refund_full": 0.0, "deny": 1.0})
    model = LastValueModel().fit([snapshot])
    rng = np.random.default_rng(0)
    start = time.perf_counter()
    simulate(model, snapshot, n_traj=SIM_TRAJECTORIES, horizon=SIM_HORIZON, rng=rng)
    elapsed = time.perf_counter() - start
    assert elapsed < 30
