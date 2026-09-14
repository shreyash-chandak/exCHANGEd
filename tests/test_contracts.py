import json
from pathlib import Path

import pytest

from change.contracts import (
    EXPORTED_MODELS,
    AdaptationDecision,
    AgentVersion,
    BehavioralSnapshot,
    Candidate,
    CanonicalAction,
    CanonicalOutcome,
    CanonicalState,
    CellAttribution,
    DriftScore,
    ExperienceRecord,
    HarmonizationConstraint,
    Lesson,
    PolicyEval,
    Prediction,
    SandboxResult,
)

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

STATE = CanonicalState("return", "delivered", "high", True, "neutral", "t0")
OUTCOME = CanonicalOutcome(True, True, True, 10.0)
CELL = CellAttribution(
    state_key=STATE.state_key, action="refund_full", delta_p=0.1, lesson_ids=["l1"]
)
DRIFT = DriftScore(
    jsd_weighted=0.1,
    jsd_ci_low=0.05,
    jsd_ci_high=0.15,
    per_state_jsd={STATE.state_key: 0.1},
    top_cells=[CELL],
)
SANDBOX = SandboxResult(
    sandbox_id="sb1",
    candidate_id="c1",
    case_set_id="cs1",
    n_trials=1,
    task_success=0.8,
    violation_rate=0.1,
    satisfaction_rate=0.9,
    mean_latency_ms=800.0,
    mean_cost=10.0,
    p_action={STATE.state_key: {"refund_full": 1.0}},
    coverage=[STATE.state_key],
)

SAMPLES: dict[str, object] = {
    "ExperienceRecord": ExperienceRecord(
        run_id="r1",
        agent_id="alice",
        agent_version=1,
        memory_version=0,
        episode_id="e1",
        turn_idx=0,
        t_global=0,
        state=STATE,
        action=CanonicalAction.REFUND_FULL,
        tools_used=["refund_full"],
        outcome=OUTCOME,
        policy_eval=PolicyEval(compliant=True, violated_rule_ids=[]),
        reward=1.0,
        latency_ms=800.0,
        tokens_in=1500,
        tokens_out=200,
        cost_usd=0.0,
        lessons_in_context=["l1"],
    ),
    "PolicyEval": PolicyEval(compliant=False, violated_rule_ids=["rule_1"]),
    "BehavioralSnapshot": BehavioralSnapshot(
        snapshot_id="s1",
        parent_id=None,
        run_id="r1",
        agent_id="alice",
        agent_version=1,
        memory_version=0,
        window_start_t=0,
        window_end_t=50,
        n_records=50,
        p_action={STATE.state_key: {"refund_full": 1.0}},
        n_action={STATE.state_key: {"refund_full": 50}},
        p_outcome={STATE.state_key: {"refund_full": {"compliant": 1.0}}},
        p_transition={STATE.state_key: {"refund_full": {STATE.state_key: 1.0}}},
        p_initial={STATE.state_key: 1.0},
        violation_rate=0.1,
        success_rate=0.9,
        satisfaction_rate=0.9,
        mean_cost=10.0,
        mean_latency_ms=800.0,
        drift_vs_parent=DRIFT,
        coverage=[STATE.state_key],
    ),
    "DriftScore": DRIFT,
    "CellAttribution": CELL,
    "Lesson": Lesson(
        lesson_id="l1",
        text="verify eligibility before refund",
        created_t=0,
        source_episode_id="e1",
        condition_state_key=STATE.state_key,
        prescribed_action="refund_full",
        generosity=0.2,
    ),
    "Candidate": Candidate(
        candidate_id="c1", kind="add_lesson", layer="context", payload={"lesson_id": "l1"}
    ),
    "Prediction": Prediction(
        prediction_id="p1",
        snapshot_id="s1",
        candidate_id="c1",
        twin_model="trend_t1",
        horizon=2000,
        violation_curve_q10=[0.1],
        violation_curve_q50=[0.12],
        violation_curve_q90=[0.15],
        success_q50=0.8,
        cost_ratio_q50=1.1,
        first_exit_t_q10=100,
        first_exit_t_q50=200,
        first_exit_t_q90=300,
        exit_metric="violation",
        contributing_cells=[CELL],
        envelope_margin_q50=0.02,
    ),
    "SandboxResult": SANDBOX,
    "HarmonizationConstraint": HarmonizationConstraint(
        constraint_id="h1",
        detector_id="H1",
        agents=["alice", "bob"],
        shared_state_key=STATE.state_key,
        evidence={"jsd": 0.2},
        consensus_action="veto",
    ),
    "AdaptationDecision": AdaptationDecision(
        decision_id="d1",
        cycle_idx=0,
        snapshot_id="s1",
        candidate_id="c1",
        risk_tier="low",
        in_boundary=True,
        decision="ACCEPT",
        supervisor_verdict="not_consulted",
        utility=0.1,
        rationale={"reason": "inside envelope"},
        boundary_after=["context:low"],
    ),
    "AgentVersion": AgentVersion(
        agent_id="alice",
        agent_version=1,
        memory_version=0,
        parent_version=None,
        gates={},
        lesson_ids=["l1"],
        canary_result=SANDBOX,
        alignment_drift_vs_v1=0.0,
        created_t=0,
    ),
}


@pytest.mark.parametrize("model_cls", EXPORTED_MODELS, ids=lambda m: m.__name__)
def test_round_trip(model_cls):
    instance = SAMPLES[model_cls.__name__]
    js = instance.model_dump_json()
    restored = model_cls.model_validate_json(js)
    assert restored == instance


@pytest.mark.parametrize("model_cls", EXPORTED_MODELS, ids=lambda m: m.__name__)
def test_schema_parity(model_cls):
    schema_path = SCHEMAS_DIR / f"{model_cls.__name__}.json"
    on_disk = json.loads(schema_path.read_text())
    assert on_disk == model_cls.model_json_schema()


def test_experience_record_state_key():
    assert STATE.state_key == "return|delivered|high|1|neutral|t0"
