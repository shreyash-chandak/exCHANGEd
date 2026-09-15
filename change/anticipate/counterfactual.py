"""Counterfactual patching and candidate ranking (guide 6.4)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from change.contracts import Candidate, Prediction, SandboxResult


def _generalization_key(candidate: Candidate, state_key: str) -> tuple | None:
    """The category `state_key` falls into under `candidate`'s own live
    generalization mechanism, or None if this candidate kind has no
    generalization beyond its exact sandboxed states. Mirrors the actual
    mechanism used when the candidate is applied live, not an arbitrary
    grouping:
    - add_lesson/remove_lessons generalize via LessonMemory.retrieve's
      partial-match tier (change/memory.py), keyed on (task_type,
      within_policy_window).
    - approval_gate generalizes via its own match condition
      (MockAgent.act's gate check), keyed on (value_bucket,
      within_policy_window == False)."""
    if candidate.kind not in ("add_lesson", "remove_lessons", "approval_gate"):
        return None
    parts = state_key.split("|")
    if len(parts) < 4:
        return None
    task_type, _order_status, value_bucket, window = parts[0], parts[1], parts[2], parts[3]
    within_policy_window = window == "1"
    if candidate.kind == "approval_gate":
        return ("gate_category", value_bucket, within_policy_window)
    return ("lesson_category", task_type, within_policy_window)


def patch_from_sandbox(
    sandbox: SandboxResult,
    candidate: Candidate,
    snapshot_states: Iterable[str] = (),
) -> dict[str, dict[str, float]]:
    """Patch p_action for every state the sandbox actually exercised, then
    (owner-authorized, docs/checkpoints/phase-8b.md "digging in" discussion)
    generalize that patch to every other state in `snapshot_states` sharing
    the category `candidate`'s own live mechanism would generalize across.

    Without this, a small (~SANDBOX_TASKS_PER_CANDIDATE-task) sandbox
    sample only directly observes a fraction of a drift-relevant state
    category (measured: as few as 4 of 13 relevant states covered in one
    traced cycle), so the counterfactual forecast kept predicting
    unpatched, still-drifting behavior for the rest even though live
    deployment -- via the same generalization mechanism the candidate
    actually uses -- would correct them too. This made genuinely-improving
    candidates look infeasible (`envelope_margin_q50 <= 0`,
    `change/negotiate.py::feasible`) far more often than the candidate's
    true live effect warrants. States not in `sandbox.coverage` and not
    sharing a category the sandbox has any observations for keep the
    model's own (unpatched) forecast, exactly as before."""
    exact_patches = {
        state: sandbox.p_action[state] for state in sandbox.coverage if state in sandbox.p_action
    }

    category_dists: dict[tuple, list[dict[str, float]]] = defaultdict(list)
    for state in sandbox.coverage:
        dist = sandbox.p_action.get(state)
        if not dist:
            continue
        key = _generalization_key(candidate, state)
        if key is not None:
            category_dists[key].append(dist)

    category_avg: dict[tuple, dict[str, float]] = {}
    for key, dists in category_dists.items():
        actions: set[str] = set()
        for dist in dists:
            actions.update(dist)
        category_avg[key] = {a: sum(d.get(a, 0.0) for d in dists) / len(dists) for a in actions}

    patches = dict(exact_patches)
    for state in snapshot_states:
        if state in patches:
            continue
        key = _generalization_key(candidate, state)
        if key is not None and key in category_avg:
            patches[state] = category_avg[key]
    return patches


def rank(predictions: list[Prediction]) -> list[Prediction]:
    """Descending by envelope_margin_q50, ties broken by success_q50."""
    return sorted(predictions, key=lambda p: (p.envelope_margin_q50, p.success_q50), reverse=True)
