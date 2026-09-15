"""Boundary controller and supervisor oracle (guide 7.3 / approach1.md 5.7)."""

from __future__ import annotations

import math
from uuid import uuid4

from change.config import (
    BOUNDARY_EXPAND_AFTER,
    ENVELOPE_VIOLATION_MAX,
    SANDBOX_TASKS_PER_CANDIDATE,
    SUPERVISOR_SUCCESS_TOL,
    UTILITY_LAMBDA_COST,
    UTILITY_MU_LATENCY,
    WINDOW_EPISODES,
)
from change.contracts import (
    AdaptationDecision,
    BehavioralSnapshot,
    Candidate,
    HarmonizationConstraint,
    Prediction,
    RiskTier,
    SandboxResult,
)

Boundary = set[str]

DEFAULT_BOUNDARY: Boundary = {"context:low"}


def risk_tier(prediction: Prediction, candidate: Candidate, baseline_success: float) -> RiskTier:
    """Low if violation stays inside the envelope at the 90% quantile for the
    whole horizon and success drop < SUPERVISOR_SUCCESS_TOL; medium if inside
    at the median only; high otherwise. approval_gate candidates are at
    least medium."""
    success_drop = baseline_success - prediction.success_q50
    q90_inside = all(v < ENVELOPE_VIOLATION_MAX for v in prediction.violation_curve_q90)
    q50_inside = all(v < ENVELOPE_VIOLATION_MAX for v in prediction.violation_curve_q50)

    if q90_inside and success_drop < SUPERVISOR_SUCCESS_TOL:
        tier: RiskTier = "low"
    elif q50_inside:
        tier = "medium"
    else:
        tier = "high"

    if candidate.kind == "approval_gate" and tier == "low":
        tier = "medium"
    return tier


def utility(
    prediction: Prediction, sandbox: SandboxResult, baseline_cost: float, baseline_latency: float
) -> float:
    cost_term = (
        UTILITY_LAMBDA_COST * (sandbox.mean_cost / baseline_cost - 1) if baseline_cost > 0 else 0.0
    )
    latency_term = (
        UTILITY_MU_LATENCY * (sandbox.mean_latency_ms / baseline_latency - 1)
        if baseline_latency > 0
        else 0.0
    )
    return prediction.envelope_margin_q50 - cost_term - latency_term


def feasible(
    prediction: Prediction, sandbox: SandboxResult, constraints: list[HarmonizationConstraint]
) -> bool:
    if prediction.envelope_margin_q50 <= 0:
        return False
    for constraint in constraints:
        if constraint.consensus_action == "veto":
            return False
    return True


def one_sided_margin(p: float, n: int, z: float = 1.0) -> float:
    """Normal-approximation standard error for a proportion estimated from
    n samples, scaled by z (default one sigma, ~84% one-sided confidence).
    Used to give small-sample point estimates a statistically-motivated
    tolerance band instead of treating them as exact -- see
    supervisor_oracle's docstring."""
    p = min(max(p, 0.0), 1.0)
    return z * math.sqrt(p * (1 - p) / max(n, 1))


def supervisor_oracle(sandbox: SandboxResult, live_violation: float, live_success: float) -> bool:
    """Scripted, deterministic supervisor -- a stated limitation of the PoC.

    Owner-authorized recalibration (docs/checkpoints/phase-8b.md "what's
    next" discussion): guide 7.3's literal formula (`sandbox.violation_rate
    < live_violation and sandbox.task_success >= live_success -
    SUPERVISOR_SUCCESS_TOL`) is a strict point-estimate comparison between
    two small, independently noisy samples -- sandbox is
    ~SANDBOX_TASKS_PER_CANDIDATE tasks, live is ~WINDOW_EPISODES episodes.
    The full 36-cell grid (phase-8b.md) showed this measurably rejecting
    candidates that would have helped about as often as it caught ones that
    wouldn't, because sampling noise on samples this small is comparable in
    size to the threshold gaps being tested. Each side now gets a one-sigma
    tolerance band for its own sampling noise (`one_sided_margin`) added to
    the comparison, rather than the raw point estimates being treated as
    exact. `ENVELOPE_VIOLATION_MAX` and `SUPERVISOR_SUCCESS_TOL` themselves
    are untouched (guide-protected constants) -- only the noise-blindness of
    the comparison is fixed."""
    violation_margin = one_sided_margin(
        sandbox.violation_rate, SANDBOX_TASKS_PER_CANDIDATE
    ) + one_sided_margin(live_violation, WINDOW_EPISODES)
    success_margin = one_sided_margin(
        sandbox.task_success, SANDBOX_TASKS_PER_CANDIDATE
    ) + one_sided_margin(live_success, WINDOW_EPISODES)
    return (
        sandbox.violation_rate < live_violation + violation_margin
        and sandbox.task_success >= live_success - SUPERVISOR_SUCCESS_TOL - success_margin
    )


def _boundary_key(candidate: Candidate, tier: RiskTier) -> str:
    return f"{candidate.layer}:{tier}"


def decide(
    cycle_idx: int,
    snapshot: BehavioralSnapshot,
    candidates: dict[str, Candidate],
    predictions: dict[str, Prediction],
    sandboxes: dict[str, SandboxResult],
    boundary: Boundary,
    history: list[AdaptationDecision],
    live_violation: float,
    live_success: float,
    baseline_success: float,
    baseline_cost: float,
    baseline_latency: float,
    constraints: list[HarmonizationConstraint] | None = None,
) -> tuple[AdaptationDecision, Boundary]:
    constraints = constraints or []

    do_nothing_id = next(
        (cid for cid, c in candidates.items() if c.kind == "do_nothing"), next(iter(candidates))
    )

    # 1. feasible set
    feasible_ids = [
        cid for cid in predictions if feasible(predictions[cid], sandboxes[cid], constraints)
    ]

    # 2. empty -> DEFER
    if not feasible_ids:
        decision = AdaptationDecision(
            decision_id=str(uuid4()),
            cycle_idx=cycle_idx,
            snapshot_id=snapshot.snapshot_id,
            candidate_id=do_nothing_id,
            risk_tier="high",
            in_boundary=False,
            decision="DEFER",
            supervisor_verdict="not_consulted",
            utility=0.0,
            rationale={"reason": "no feasible candidates"},
            boundary_after=sorted(boundary),
        )
        return decision, set(boundary)

    # 3. argmax utility
    utilities = {
        cid: utility(predictions[cid], sandboxes[cid], baseline_cost, baseline_latency)
        for cid in feasible_ids
    }
    best_id = max(utilities, key=lambda cid: utilities[cid])
    best_candidate = candidates[best_id]
    best_prediction = predictions[best_id]
    tier = risk_tier(best_prediction, best_candidate, baseline_success)
    key = _boundary_key(best_candidate, tier)
    in_boundary = key in boundary

    # 4/5/6
    if in_boundary:
        decision_val, supervisor_verdict = "ACCEPT", "not_consulted"
        new_boundary = set(boundary)
    else:
        approved = supervisor_oracle(sandboxes[best_id], live_violation, live_success)
        decision_val = "ESCALATE"
        supervisor_verdict = "approved" if approved else "rejected"
        new_boundary = _maybe_expand_boundary(boundary, key, approved, history)

    decision = AdaptationDecision(
        decision_id=str(uuid4()),
        cycle_idx=cycle_idx,
        snapshot_id=snapshot.snapshot_id,
        candidate_id=best_id,
        risk_tier=tier,
        in_boundary=in_boundary,
        decision=decision_val,
        supervisor_verdict=supervisor_verdict,
        utility=utilities[best_id],
        rationale={"key": key, "utility_by_candidate": utilities},
        boundary_after=sorted(new_boundary),
    )
    return decision, new_boundary


def _maybe_expand_boundary(
    boundary: Boundary, key: str, approved: bool, history: list[AdaptationDecision]
) -> Boundary:
    """After BOUNDARY_EXPAND_AFTER consecutive escalated approvals for the
    same (layer:tier) key, that key enters the boundary."""
    new_boundary = set(boundary)
    past_escalations = [
        d.supervisor_verdict == "approved"
        for d in history
        if d.decision == "ESCALATE" and d.rationale.get("key") == key
    ]
    streak = [*past_escalations, approved]
    if len(streak) >= BOUNDARY_EXPAND_AFTER and all(streak[-BOUNDARY_EXPAND_AFTER:]):
        new_boundary.add(key)
    return new_boundary


def contract_boundary(boundary: Boundary, key: str) -> Boundary:
    """Called from Evolve on a post-hoc canary failure."""
    new_boundary = set(boundary)
    new_boundary.discard(key)
    return new_boundary
