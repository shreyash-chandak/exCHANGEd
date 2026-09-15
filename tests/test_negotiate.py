from change.contracts import (
    AdaptationDecision,
    BehavioralSnapshot,
    Candidate,
    Prediction,
    SandboxResult,
)
from change.negotiate import decide

SNAPSHOT = BehavioralSnapshot(
    snapshot_id="s1",
    parent_id=None,
    run_id="r1",
    agent_id="alice",
    agent_version=1,
    memory_version=0,
    window_start_t=0,
    window_end_t=50,
    n_records=50,
    violation_rate=0.1,
    success_rate=0.8,
    satisfaction_rate=0.8,
    mean_cost=10.0,
    mean_latency_ms=800.0,
)


def _candidate(cid: str, kind: str = "add_lesson", layer: str = "context") -> Candidate:
    return Candidate(candidate_id=cid, kind=kind, layer=layer, payload={})


def _prediction(
    cid: str, margin: float, q90_inside: bool, q50_inside: bool, success_q50: float = 0.9
) -> Prediction:
    return Prediction(
        prediction_id=f"p-{cid}",
        snapshot_id="s1",
        candidate_id=cid,
        twin_model="trend_t1",
        horizon=100,
        violation_curve_q10=[0.01],
        violation_curve_q50=[0.01] if q50_inside else [0.5],
        violation_curve_q90=[0.01] if q90_inside else [0.5],
        success_q50=success_q50,
        cost_ratio_q50=1.0,
        envelope_margin_q50=margin,
    )


def _sandbox(cid: str, violation_rate: float = 0.02, task_success: float = 0.9) -> SandboxResult:
    return SandboxResult(
        sandbox_id=f"sb-{cid}",
        candidate_id=cid,
        case_set_id="sandbox",
        n_trials=1,
        task_success=task_success,
        violation_rate=violation_rate,
        satisfaction_rate=0.9,
        mean_latency_ms=800.0,
        mean_cost=10.0,
    )


COMMON_KWARGS = {
    "live_violation": 0.1,
    "live_success": 0.8,
    "baseline_success": 0.9,
    "baseline_cost": 10.0,
    "baseline_latency": 800.0,
}


def test_in_boundary_low_risk_gives_accept():
    candidate = _candidate("c1", layer="context")
    candidates = {"c1": candidate}
    predictions = {"c1": _prediction("c1", margin=0.05, q90_inside=True, q50_inside=True)}
    sandboxes = {"c1": _sandbox("c1")}

    decision, _boundary = decide(
        cycle_idx=0,
        snapshot=SNAPSHOT,
        candidates=candidates,
        predictions=predictions,
        sandboxes=sandboxes,
        boundary={"context:low"},
        history=[],
        **COMMON_KWARGS,
    )

    assert decision.decision == "ACCEPT"
    assert decision.in_boundary is True
    assert decision.risk_tier == "low"


def test_out_of_boundary_gives_escalate_with_oracle_consulted():
    candidate = _candidate("c1", layer="architecture")  # forced at least medium tier
    candidates = {"c1": candidate}
    predictions = {"c1": _prediction("c1", margin=0.05, q90_inside=True, q50_inside=True)}
    sandboxes = {
        "c1": _sandbox("c1", violation_rate=0.02, task_success=0.9)
    }  # oracle should approve

    decision, _boundary = decide(
        cycle_idx=0,
        snapshot=SNAPSHOT,
        candidates=candidates,
        predictions=predictions,
        sandboxes=sandboxes,
        boundary=set(),  # nothing in boundary
        history=[],
        **COMMON_KWARGS,
    )

    assert decision.decision == "ESCALATE"
    assert decision.supervisor_verdict in ("approved", "rejected")
    assert decision.in_boundary is False


def test_no_feasible_candidates_gives_defer():
    candidates = {
        "do_nothing": _candidate("do_nothing", kind="do_nothing"),
        "c1": _candidate("c1"),
    }
    predictions = {
        "do_nothing": _prediction("do_nothing", margin=-0.1, q90_inside=False, q50_inside=False),
        "c1": _prediction("c1", margin=-0.05, q90_inside=False, q50_inside=False),
    }
    sandboxes = {"do_nothing": _sandbox("do_nothing"), "c1": _sandbox("c1")}

    decision, _boundary = decide(
        cycle_idx=0,
        snapshot=SNAPSHOT,
        candidates=candidates,
        predictions=predictions,
        sandboxes=sandboxes,
        boundary={"context:low"},
        history=[],
        **COMMON_KWARGS,
    )

    assert decision.decision == "DEFER"
    assert decision.candidate_id == "do_nothing"


def test_three_consecutive_escalated_approvals_expand_boundary():
    candidate = _candidate("c1", layer="context")
    candidates = {"c1": candidate}
    # medium risk tier (q50 inside, q90 not) so it stays out of the initial
    # boundary ({"context:low"}) and needs escalation every time
    predictions = {"c1": _prediction("c1", margin=0.05, q90_inside=False, q50_inside=True)}
    sandboxes = {"c1": _sandbox("c1", violation_rate=0.02, task_success=0.9)}  # always approved

    boundary = {"context:low"}
    history: list[AdaptationDecision] = []
    for _ in range(3):
        decision, boundary = decide(
            cycle_idx=len(history),
            snapshot=SNAPSHOT,
            candidates=candidates,
            predictions=predictions,
            sandboxes=sandboxes,
            boundary=boundary,
            history=history,
            **COMMON_KWARGS,
        )
        assert decision.decision == "ESCALATE"
        assert decision.supervisor_verdict == "approved"
        history.append(decision)

    assert "context:medium" in boundary
