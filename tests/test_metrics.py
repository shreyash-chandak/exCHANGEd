from change.contracts import (
    AdaptationDecision,
    BehavioralSnapshot,
    Candidate,
    CanonicalAction,
    CanonicalOutcome,
    CanonicalState,
    ExperienceRecord,
    PolicyEval,
)
from change.metrics import compute_metrics, false_alert_rate, governance_metrics, lead_time
from change.store import JsonlStore

STATE = CanonicalState("return", "delivered", "high", False, "neutral", "t0")


def _record(i: int, compliant: bool) -> ExperienceRecord:
    return ExperienceRecord(
        run_id="r1",
        agent_id="alice",
        agent_version=1,
        memory_version=0,
        episode_id=f"e{i}",
        turn_idx=0,
        t_global=i,
        state=STATE,
        action=CanonicalAction.REFUND_FULL,
        outcome=CanonicalOutcome(compliant, True, True, 0.0),
        policy_eval=PolicyEval(compliant=compliant, violated_rule_ids=[] if compliant else ["x"]),
        latency_ms=1.0,
        tokens_in=1,
        tokens_out=1,
        cost_usd=0.0,
    )


def _snapshot(
    snapshot_id: str, parent_id: str | None, window_end_t: int, violation_rate: float
) -> BehavioralSnapshot:
    return BehavioralSnapshot(
        snapshot_id=snapshot_id,
        parent_id=parent_id,
        run_id="r1",
        agent_id="alice",
        agent_version=1,
        memory_version=0,
        window_start_t=max(0, window_end_t - 50),
        window_end_t=window_end_t,
        n_records=50,
        violation_rate=violation_rate,
        success_rate=1 - violation_rate,
        satisfaction_rate=1 - violation_rate,
        mean_cost=10.0,
        mean_latency_ms=800.0,
    )


def _decision(
    cycle_idx: int,
    snapshot_id: str,
    candidate_id: str,
    triggered: bool,
    decision: str = "ACCEPT",
    supervisor_verdict: str = "not_consulted",
    boundary_after: list[str] | None = None,
) -> AdaptationDecision:
    return AdaptationDecision(
        decision_id=f"d{cycle_idx}",
        cycle_idx=cycle_idx,
        snapshot_id=snapshot_id,
        candidate_id=candidate_id,
        risk_tier="low",
        in_boundary=True,
        decision=decision,
        supervisor_verdict=supervisor_verdict,
        utility=0.0,
        rationale={"triggered": triggered},
        boundary_after=boundary_after or ["context:low"],
    )


def test_governance_metrics_counts_violations_and_adaptations():
    records = [_record(i, compliant=(i % 5 != 0)) for i in range(20)]  # 4 violations
    snapshots = [_snapshot("s1", None, 20, violation_rate=0.2)]
    do_nothing = Candidate(candidate_id="dn", kind="do_nothing", layer="context", payload={})
    add_lesson = Candidate(candidate_id="c1", kind="add_lesson", layer="context", payload={})
    decisions = [
        _decision(0, "s1", "dn", triggered=False),
        _decision(1, "s1", "c1", triggered=True, boundary_after=["context:low", "context:medium"]),
    ]
    candidate_by_id = {"dn": do_nothing, "c1": add_lesson}

    metrics = governance_metrics(
        records, snapshots, decisions, sandboxes=[], candidate_by_id=candidate_by_id
    )

    assert metrics["cumulative_violations"] == 4
    assert metrics["adaptations_count"] == 1
    assert metrics["unnecessary_adaptation_rate"] == 0.5
    assert metrics["boundary_expansions"] == 1


def test_lead_time_positive_when_trigger_precedes_exit():
    snapshots = [
        _snapshot("s0", None, 50, violation_rate=0.05),
        _snapshot("s1", "s0", 100, violation_rate=0.08),
        _snapshot("s2", "s1", 150, violation_rate=0.15),  # first realized exit
    ]
    decisions = [
        _decision(0, "s0", "dn", triggered=False),
        _decision(1, "s1", "dn", triggered=True),  # trigger fires before the exit
        _decision(2, "s2", "dn", triggered=True),
    ]
    result = lead_time(snapshots, decisions)
    assert result == 150 - 100  # exit_t - trigger_t, positive = anticipated early


def test_lead_time_none_without_realized_exit():
    snapshots = [_snapshot("s0", None, 50, violation_rate=0.02)]
    decisions = [_decision(0, "s0", "dn", triggered=False)]
    assert lead_time(snapshots, decisions) is None


def test_false_alert_rate():
    decisions = [
        _decision(0, "s0", "dn", triggered=False),
        _decision(1, "s0", "dn", triggered=False),
        _decision(2, "s0", "dn", triggered=True),
    ]
    assert false_alert_rate(decisions) == 1 / 3


def test_compute_metrics_runs_on_tiny_synthetic_run_dir(tmp_path):
    store = JsonlStore(tmp_path)
    for i in range(20):
        store.append(_record(i, compliant=(i % 4 != 0)))

    snap0 = _snapshot("s0", None, 20, violation_rate=0.25)
    store.append(snap0)

    do_nothing = Candidate(candidate_id="dn", kind="do_nothing", layer="context", payload={})
    store.append(do_nothing)
    store.append(_decision(0, "s0", "dn", triggered=False))

    metrics = compute_metrics(tmp_path)

    expected_keys = {
        "lead_time",
        "false_alert_rate",
        "forecast_error",
        "attribution_hit",
        "exit_time_error_mean",
        "interval_coverage",
        "counterfactual_fidelity",
        "cumulative_violations",
        "final_success_rate",
        "adaptations_count",
        "unnecessary_adaptation_rate",
        "rollbacks",
        "boundary_expansions",
    }
    assert expected_keys.issubset(metrics.keys())
    assert metrics["cumulative_violations"] == 5
    assert metrics["adaptations_count"] == 0
