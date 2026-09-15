from change.anticipate.counterfactual import patch_from_sandbox, rank
from change.contracts import Candidate, Prediction, SandboxResult


def _prediction(candidate_id: str, margin: float, success: float) -> Prediction:
    return Prediction(
        prediction_id=f"p-{candidate_id}",
        snapshot_id="s1",
        candidate_id=candidate_id,
        twin_model="trend_t1",
        horizon=100,
        success_q50=success,
        cost_ratio_q50=1.0,
        envelope_margin_q50=margin,
    )


def test_rank_orders_by_margin_then_success():
    low = _prediction("low", margin=0.01, success=0.9)
    high = _prediction("high", margin=0.05, success=0.9)
    tie_better_success = _prediction("tie_better", margin=0.01, success=0.95)

    ranked = rank([low, high, tie_better_success])

    assert [p.candidate_id for p in ranked] == ["high", "tie_better", "low"]


def test_patch_from_sandbox_only_covers_sandboxed_states_for_do_nothing():
    sandbox = SandboxResult(
        sandbox_id="sb1",
        candidate_id="c1",
        case_set_id="cs1",
        n_trials=1,
        task_success=0.8,
        violation_rate=0.05,
        satisfaction_rate=0.9,
        mean_latency_ms=800.0,
        mean_cost=10.0,
        p_action={
            "return|delivered|high|0|neutral|t0": {"deny": 1.0},
            "uncovered_state": {"deny": 1.0},
        },
        coverage=["return|delivered|high|0|neutral|t0"],
    )
    do_nothing = Candidate(candidate_id="c1", kind="do_nothing", layer="context", payload={})

    patches = patch_from_sandbox(sandbox, do_nothing, snapshot_states=[])

    assert patches == {"return|delivered|high|0|neutral|t0": {"deny": 1.0}}


def test_patch_from_sandbox_generalizes_add_lesson_across_matching_category():
    # sandbox only directly visits one "return, outside window" state, but
    # a lesson-based candidate generalizes to every state sharing
    # (task_type, within_policy_window) per LessonMemory.retrieve's
    # partial-match tier -- so a sibling state (different order_status)
    # should pick up the same observed distribution, and a state in a
    # different category should stay unpatched.
    sandbox = SandboxResult(
        sandbox_id="sb1",
        candidate_id="c1",
        case_set_id="cs1",
        n_trials=1,
        task_success=0.8,
        violation_rate=0.05,
        satisfaction_rate=0.9,
        mean_latency_ms=800.0,
        mean_cost=10.0,
        p_action={"return|delivered|high|0|neutral|t0": {"deny": 1.0}},
        coverage=["return|delivered|high|0|neutral|t0"],
    )
    add_lesson = Candidate(
        candidate_id="c1", kind="add_lesson", layer="context", payload={"lesson": {}}
    )
    snapshot_states = [
        "return|delivered|high|0|neutral|t0",  # exact sandboxed state
        "return|processed|low|0|pushy|t0",  # same category (return, outside window)
        "return|delivered|high|1|neutral|t0",  # same task_type, but within window
        "lookup|delivered|high|0|neutral|t0",  # different task_type entirely
    ]

    patches = patch_from_sandbox(sandbox, add_lesson, snapshot_states)

    assert patches["return|delivered|high|0|neutral|t0"] == {"deny": 1.0}
    assert patches["return|processed|low|0|pushy|t0"] == {"deny": 1.0}
    assert "return|delivered|high|1|neutral|t0" not in patches
    assert "lookup|delivered|high|0|neutral|t0" not in patches
