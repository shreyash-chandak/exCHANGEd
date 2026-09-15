"""Run-level metrics computed from a run dir (guide 8.1)."""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

from scipy.stats import spearmanr

from change.anticipate.trend import LastValueModel, TrendModel
from change.config import ENVELOPE_VIOLATION_MAX, FORECAST_HORIZONS, SIM_ROLLING_WINDOW
from change.contextualize import _state_weights, weighted_jsd
from change.contracts import (
    AdaptationDecision,
    BehavioralSnapshot,
    Candidate,
    CanonicalState,
    ExperienceRecord,
    Prediction,
    SandboxResult,
)
from change.store import JsonlStore

_COUNTERFACTUAL_HORIZON = 250


def _is_triggered(decision: AdaptationDecision) -> bool:
    """Absent "triggered" key means the decision came from the
    triggered-candidate-evaluation branch (A3+); explicit False/True covers
    everything else. See docs/checkpoints/phase-8.md."""
    return bool(decision.rationale.get("triggered", True))


def _is_applied(decision: AdaptationDecision) -> bool:
    return decision.decision == "ACCEPT" or (
        decision.decision == "ESCALATE" and decision.supervisor_verdict == "approved"
    )


def _predicted_violation_rate(
    p_action: dict[str, dict[str, float]],
    outcome_snapshot: BehavioralSnapshot,
    weights: dict[str, float],
) -> float | None:
    total_w = 0.0
    acc = 0.0
    for state, dist in p_action.items():
        w = weights.get(state, 0.0)
        outcomes = outcome_snapshot.p_outcome.get(state)
        if w <= 0 or not outcomes:
            continue
        violation = sum(dist.get(a, 0.0) * (1 - outcomes[a]["compliant"]) for a in outcomes)
        acc += w * violation
        total_w += w
    return acc / total_w if total_w > 0 else None


def _first_realized_exit_t(snapshots: list[BehavioralSnapshot]) -> int | None:
    for snapshot in sorted(snapshots, key=lambda s: s.window_end_t):
        if snapshot.violation_rate > ENVELOPE_VIOLATION_MAX:
            return snapshot.window_end_t
    return None


def _first_trigger_t(
    snapshots: list[BehavioralSnapshot], decisions: list[AdaptationDecision]
) -> int | None:
    snapshot_by_id = {s.snapshot_id: s for s in snapshots}
    for decision in sorted(decisions, key=lambda d: d.cycle_idx):
        if _is_triggered(decision):
            snapshot = snapshot_by_id.get(decision.snapshot_id)
            if snapshot is not None:
                return snapshot.window_end_t
    return None


def lead_time(
    snapshots: list[BehavioralSnapshot], decisions: list[AdaptationDecision]
) -> float | None:
    """Positive = the governance trigger preceded the realized envelope
    exit (anticipatory, good). None if no realized exit occurred."""
    exit_t = _first_realized_exit_t(snapshots)
    trigger_t = _first_trigger_t(snapshots, decisions)
    if exit_t is None or trigger_t is None:
        return None
    return exit_t - trigger_t


def false_alert_rate(decisions: list[AdaptationDecision]) -> float:
    """Fraction of cycles that triggered. Meaningful on D1 (no real drift)."""
    if not decisions:
        return 0.0
    return sum(1 for d in decisions if _is_triggered(d)) / len(decisions)


def forecast_error(snapshots: list[BehavioralSnapshot]) -> dict:
    """For each snapshot with a later realized snapshot near t+h, JSD
    between predicted and realized p_action plus abs violation-rate error,
    for both twin models, at each horizon in FORECAST_HORIZONS."""
    ordered = sorted(snapshots, key=lambda s: s.window_end_t)
    per_horizon: dict[int, dict[str, list[dict]]] = {
        h: {"trend_t1": [], "last_value": []} for h in FORECAST_HORIZONS
    }

    for i, snapshot in enumerate(ordered):
        history = ordered[: i + 1]
        weights = _state_weights(snapshot.n_action)
        for horizon in FORECAST_HORIZONS:
            target_t = snapshot.window_end_t + horizon
            later = [s for s in ordered[i + 1 :] if s.window_end_t <= target_t + horizon]
            if not later:
                continue
            realized = min(later, key=lambda s: abs(s.window_end_t - target_t))

            for model_cls, name in [(TrendModel, "trend_t1"), (LastValueModel, "last_value")]:
                model = model_cls().fit(history)
                predicted_p_action = model.predict(realized.window_end_t)
                jsd, _ = weighted_jsd(predicted_p_action, realized.p_action, weights)
                predicted_violation = _predicted_violation_rate(
                    predicted_p_action, snapshot, weights
                )
                violation_abs_error = (
                    abs(predicted_violation - realized.violation_rate)
                    if predicted_violation is not None
                    else None
                )
                per_horizon[horizon][name].append(
                    {"jsd": jsd, "violation_abs_error": violation_abs_error}
                )

    summary: dict[str, dict] = {}
    for horizon, by_model in per_horizon.items():
        summary[str(horizon)] = {}
        for name, entries in by_model.items():
            if not entries:
                summary[str(horizon)][name] = None
                continue
            errs = [
                e["violation_abs_error"] for e in entries if e["violation_abs_error"] is not None
            ]
            summary[str(horizon)][name] = {
                "jsd_mean": sum(e["jsd"] for e in entries) / len(entries),
                "violation_abs_error_mean": (sum(errs) / len(errs)) if errs else None,
                "n": len(entries),
            }
    return summary


def exit_time_error_and_coverage(
    snapshots: list[BehavioralSnapshot], predictions: list[Prediction]
) -> dict:
    """Mean abs error of trend_t1 do_nothing's first_exit_t_q50 against the
    realized exit, and the fraction of cases where the realized exit falls
    within [q10, q90] (calibration)."""
    realized_exit_t = _first_realized_exit_t(snapshots)
    trend_do_nothing = [
        p for p in predictions if p.candidate_id == "do_nothing" and p.twin_model == "trend_t1"
    ]

    errors: list[float] = []
    covered = total = 0
    for prediction in trend_do_nothing:
        if prediction.first_exit_t_q50 is None or realized_exit_t is None:
            continue
        total += 1
        errors.append(abs(prediction.first_exit_t_q50 - realized_exit_t))
        if (
            prediction.first_exit_t_q10 is not None
            and prediction.first_exit_t_q90 is not None
            and prediction.first_exit_t_q10 <= realized_exit_t <= prediction.first_exit_t_q90
        ):
            covered += 1

    return {
        "exit_time_error_mean": (sum(errors) / len(errors)) if errors else None,
        "interval_coverage": (covered / total) if total else None,
    }


def attribution_hit(
    snapshots: list[BehavioralSnapshot],
    predictions: list[Prediction],
    decisions: list[AdaptationDecision],
) -> bool | None:
    """D3: does the top contributing cell at the first triggering cycle
    match the changed policy rule (return/exchange, outside window)?"""
    first_triggered = next(
        (d for d in sorted(decisions, key=lambda d: d.cycle_idx) if _is_triggered(d)), None
    )
    if first_triggered is None:
        return None
    trend_preds = [
        p
        for p in predictions
        if p.snapshot_id == first_triggered.snapshot_id
        and p.candidate_id == "do_nothing"
        and p.twin_model == "trend_t1"
    ]
    if not trend_preds or not trend_preds[0].contributing_cells:
        return None
    top = trend_preds[0].contributing_cells[0]
    state = CanonicalState.from_state_key(top.state_key)
    return state.task_type in ("return", "exchange") and not state.within_policy_window


def counterfactual_fidelity(
    records: list[ExperienceRecord],
    snapshots: list[BehavioralSnapshot],
    predictions: list[Prediction],
    sandboxes: list[SandboxResult],
    decisions: list[AdaptationDecision],
    candidate_by_id: dict[str, Candidate],
) -> dict:
    snapshot_by_id = {s.snapshot_id: s for s in snapshots}
    candidate_preds: dict[str, list[Prediction]] = defaultdict(list)
    for p in predictions:
        if p.candidate_id != "do_nothing":
            candidate_preds[p.snapshot_id].append(p)
    sandbox_by_id = {sb.candidate_id: sb for sb in sandboxes if sb.case_set_id == "sandbox"}

    block_idx = _COUNTERFACTUAL_HORIZON // SIM_ROLLING_WINDOW - 1
    applied_errors: list[float] = []
    rank_correlations: list[float] = []

    for decision in decisions:
        snapshot = snapshot_by_id.get(decision.snapshot_id)
        cycle_preds = candidate_preds.get(decision.snapshot_id, [])

        if _is_applied(decision):
            candidate = candidate_by_id.get(decision.candidate_id)
            if candidate is not None and candidate.kind != "do_nothing" and snapshot is not None:
                pred = next(
                    (p for p in cycle_preds if p.candidate_id == decision.candidate_id), None
                )
                if pred is not None and 0 <= block_idx < len(pred.violation_curve_q50):
                    predicted_v = pred.violation_curve_q50[block_idx]
                    window = [
                        r
                        for r in records
                        if snapshot.window_end_t
                        < r.t_global
                        <= snapshot.window_end_t + _COUNTERFACTUAL_HORIZON
                    ]
                    if window:
                        realized_v = sum(1 for r in window if not r.policy_eval.compliant) / len(
                            window
                        )
                        applied_errors.append(abs(predicted_v - realized_v))

        eligible = [p for p in cycle_preds if p.candidate_id in sandbox_by_id]
        if len(eligible) >= 3:
            predicted_order = [p.candidate_id for p in eligible]
            predicted_scores = [p.envelope_margin_q50 for p in eligible]
            sandbox_scores = [-sandbox_by_id[cid].violation_rate for cid in predicted_order]
            if len(set(predicted_scores)) > 1 and len(set(sandbox_scores)) > 1:
                corr, _ = spearmanr(predicted_scores, sandbox_scores)
                if corr is not None and not math.isnan(corr):
                    rank_correlations.append(corr)

    return {
        "predicted_vs_realized_violation_abs_error_mean": (
            sum(applied_errors) / len(applied_errors) if applied_errors else None
        ),
        "n_applied_candidates": len(applied_errors),
        "rank_spearman_mean": (
            sum(rank_correlations) / len(rank_correlations) if rank_correlations else None
        ),
        "n_ranked_cycles": len(rank_correlations),
    }


def governance_metrics(
    records: list[ExperienceRecord],
    snapshots: list[BehavioralSnapshot],
    decisions: list[AdaptationDecision],
    sandboxes: list[SandboxResult],
    candidate_by_id: dict[str, Candidate],
) -> dict:
    ordered_snapshots = sorted(snapshots, key=lambda s: s.window_end_t)
    applied = []
    for decision in decisions:
        if not _is_applied(decision):
            continue
        candidate = candidate_by_id.get(decision.candidate_id)
        if candidate is not None and candidate.kind != "do_nothing":
            applied.append(decision)

    rollbacks = sum(
        1
        for sb in sandboxes
        if sb.case_set_id == "canary" and sb.violation_rate > ENVELOPE_VIOLATION_MAX
    )

    boundary_expansions = 0
    prev_boundary: set[str] | None = None
    for decision in sorted(decisions, key=lambda d: d.cycle_idx):
        current = set(decision.boundary_after)
        if prev_boundary is not None:
            boundary_expansions += len(current - prev_boundary)
        prev_boundary = current

    return {
        "cumulative_violations": sum(1 for r in records if not r.policy_eval.compliant),
        "final_success_rate": ordered_snapshots[-1].success_rate if ordered_snapshots else None,
        "adaptations_count": len(applied),
        "unnecessary_adaptation_rate": (len(applied) / len(decisions)) if decisions else 0.0,
        "rollbacks": rollbacks,
        "boundary_expansions": boundary_expansions,
    }


def compute_metrics(run_dir: Path | str) -> dict:
    run_dir = Path(run_dir)
    store = JsonlStore(run_dir)

    records = store.read_all(ExperienceRecord)
    snapshots = store.read_all(BehavioralSnapshot)
    predictions = store.read_all(Prediction)
    decisions = store.read_all(AdaptationDecision)
    sandboxes = store.read_all(SandboxResult)
    candidates = store.read_all(Candidate)
    candidate_by_id = {c.candidate_id: c for c in candidates}

    metrics: dict = {
        "lead_time": lead_time(snapshots, decisions),
        "false_alert_rate": false_alert_rate(decisions),
        "forecast_error": forecast_error(snapshots),
        "attribution_hit": attribution_hit(snapshots, predictions, decisions),
    }
    metrics.update(exit_time_error_and_coverage(snapshots, predictions))
    metrics["counterfactual_fidelity"] = counterfactual_fidelity(
        records, snapshots, predictions, sandboxes, decisions, candidate_by_id
    )
    metrics.update(governance_metrics(records, snapshots, decisions, sandboxes, candidate_by_id))
    return metrics
