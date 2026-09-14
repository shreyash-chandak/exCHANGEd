"""Counterfactual patching and candidate ranking (guide 6.4)."""

from __future__ import annotations

from change.contracts import Prediction, SandboxResult


def patch_from_sandbox(sandbox: SandboxResult) -> dict[str, dict[str, float]]:
    """Patch p_action for every state the sandbox actually exercised.
    States not in sandbox.coverage keep the forecast (not patched)."""
    return {
        state: sandbox.p_action[state] for state in sandbox.coverage if state in sandbox.p_action
    }


def rank(predictions: list[Prediction]) -> list[Prediction]:
    """Descending by envelope_margin_q50, ties broken by success_q50."""
    return sorted(predictions, key=lambda p: (p.envelope_margin_q50, p.success_q50), reverse=True)
