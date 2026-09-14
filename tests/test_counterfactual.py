from change.anticipate.counterfactual import patch_from_sandbox, rank
from change.contracts import Prediction, SandboxResult


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


def test_patch_from_sandbox_only_covers_sandboxed_states():
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

    patches = patch_from_sandbox(sandbox)

    assert patches == {"return|delivered|high|0|neutral|t0": {"deny": 1.0}}
