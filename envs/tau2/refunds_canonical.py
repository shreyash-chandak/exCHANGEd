"""Canonicalization for the refunds domain (session-2 guide 4a.6): maps
refunds-domain concepts (Order, RefundsTools calls, persona stance) onto
the shared CanonicalState/CanonicalAction/CanonicalOutcome contracts
(change/contracts.py) that Contextualize/Anticipate/etc. already work
with, generically, for any environment.
"""

from __future__ import annotations

import re

from change.contracts import (
    CanonicalAction,
    CanonicalOutcome,
    CanonicalState,
    OrderStatus,
    PriorTurnsBucket,
    UserStance,
)
from change.llm import chat
from envs.tau2.domains.refunds.data_model import CURRENT_TIME, Order
from envs.tau2.domains.refunds.oracle import PolicyVersion, RefundRequest, TakenAction, check

_STANCE_RE = re.compile(r"\[STANCE=(neutral|pushy|distressed)\]")

# refunds' 7-state OrderStatus collapses onto CanonicalState's existing
# 5-value literal (change/contracts.py, a protected contract -- not
# extended for this domain). shipped is mid-fulfillment like processed;
# refunded/exchanged are terminal/resolved like cancelled.
_ORDER_STATUS_MAP: dict[str, OrderStatus] = {
    "pending": "pending",
    "processed": "processed",
    "shipped": "processed",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "refunded": "cancelled",
    "exchanged": "cancelled",
}

_TOOL_TO_ACTION: dict[str, CanonicalAction] = {
    "refund_full": CanonicalAction.REFUND_FULL,
    "refund_partial": CanonicalAction.REFUND_PARTIAL,
    "exchange_items": CanonicalAction.EXCHANGE,
    "cancel_order": CanonicalAction.CANCEL,
    "deny_request": CanonicalAction.DENY,
    "escalate": CanonicalAction.ESCALATE,
    "transfer_to_human": CanonicalAction.ESCALATE,
    "find_customer_by_email": CanonicalAction.LOOKUP,
    "find_customer_by_name_zip": CanonicalAction.LOOKUP,
    "get_order": CanonicalAction.LOOKUP,
    "list_orders": CanonicalAction.LOOKUP,
    "get_product": CanonicalAction.LOOKUP,
}


def parse_user_stance(persona: str | None) -> UserStance:
    """Reads user_stance structurally from the `[STANCE=...]` tag
    scripts/gen_refunds_tasks.py writes into the persona field, per guide
    4a.5's "stance is written into the persona field so user_stance is
    read structurally" -- not inferred from free text."""
    if persona is None:
        return "neutral"
    match = _STANCE_RE.search(persona)
    return match.group(1) if match else "neutral"  # type: ignore[return-value]


def _days_since_delivery(order: Order) -> float | None:
    from datetime import datetime

    if order.delivered_at is None:
        return None
    delivered = datetime.fromisoformat(order.delivered_at)
    now = datetime.fromisoformat(CURRENT_TIME)
    return (now - delivered).total_seconds() / 86400.0


def canonical_state(
    order: Order,
    request_type: str,
    persona: str | None,
    prior_turns_bucket: PriorTurnsBucket,
) -> CanonicalState:
    """`within_policy_window` = within 30 days of delivery for return/
    exchange requests, or `status == "pending"` for cancel requests --
    per guide 4a.6's exact wording. Uses the base policy's literal 30-day
    figure regardless of which policy_version is actually in force
    (guide 4a.6 doesn't parameterize this by D3), matching the same
    canonical concept ("is this request inside the fast-track window")
    across conditions rather than a moving threshold."""
    value_bucket = "low" if order.total < 60 else "mid" if order.total < 250 else "high"

    if request_type == "cancel":
        within_policy_window = order.status == "pending"
    else:
        days = _days_since_delivery(order)
        within_policy_window = days is not None and days <= 30

    return CanonicalState(
        task_type=request_type,
        order_status=_ORDER_STATUS_MAP.get(order.status, "unknown"),
        value_bucket=value_bucket,
        within_policy_window=within_policy_window,
        user_stance=parse_user_stance(persona),
        prior_turns_bucket=prior_turns_bucket,
    )


def canonical_action(tool_name: str) -> CanonicalAction:
    """One-to-one mapping from a refunds tool call (or a plain text turn,
    for which the caller should use CanonicalAction.ASK_CLARIFY / END
    directly -- there's no tool call to map)."""
    if tool_name not in _TOOL_TO_ACTION:
        raise ValueError(f"Unknown refunds tool: {tool_name}")
    return _TOOL_TO_ACTION[tool_name]


def canonical_outcome(
    order: Order,
    request: RefundRequest,
    customer,
    products: dict,
    taken: TakenAction,
    task_success: bool,
    user_satisfied: bool,
    policy_version: PolicyVersion = "v1",
) -> CanonicalOutcome:
    """policy_compliant comes from the oracle (the single source of truth,
    per 4a.4); task_success is whatever tau2's own reward computation
    says for this episode (supplied by the caller, not recomputed here)."""
    policy_eval = check(order, request, customer, products, taken, policy_version)
    return CanonicalOutcome(
        policy_compliant=policy_eval.compliant,
        task_success=task_success,
        user_satisfied=user_satisfied,
    )


_SATISFACTION_QUESTION = (
    "On a scale of 1 to 5 (1 = very dissatisfied, 5 = very satisfied), how satisfied "
    "are you with how the agent just handled your request? Reply with only the number."
)


def user_satisfied(transcript: list[dict]) -> bool:
    """Asks the user-simulator model one question at episode end (guide
    4a.6), 1-5, satisfied iff the answer is 4 or more. LIVE only -- calls
    change.llm.chat, so this is exercised by the live smoke test (4a.7),
    not the offline test suite."""
    messages = [*transcript, {"role": "user", "content": _SATISFACTION_QUESTION}]
    response = chat(messages, temperature=0.0, max_tokens=10)
    content = response["choices"][0]["message"]["content"].strip()
    match = re.search(r"[1-5]", content)
    if not match:
        raise ValueError(f"user satisfaction response not parseable as 1-5: {content!r}")
    return int(match.group(0)) >= 4


__all__ = [
    "canonical_action",
    "canonical_outcome",
    "canonical_state",
    "parse_user_stance",
    "user_satisfied",
]
