"""Canonicalization for tau2's shipped retail domain (session-2 guide
4b.1-4b.3): external control, collapsed taxonomy, native violations.

Unlike the refunds domain (built from scratch with tools that
deliberately enforce nothing, guide 4a.3), retail's own tools already
enforce most eligibility rules themselves (raising ValueError for e.g. a
non-pending cancel) -- confirmed in phase 1 (docs/tau2_interfaces.md item
8). So there is no oracle.expected_action equivalent here: "compliance"
is tau2's own per-action correctness (a write call either succeeds,
meaning it was valid, or fails and nothing changes) plus exactly two
extra rule checks this module implements on top, since they're
conversational-flow properties the tools can't enforce themselves:

- RT1: explicit user confirmation (an affirmative) in the turn
  immediately before a write action.
- RT2: at most one modify_pending_order_* call per order per
  conversation (modify_user_address is a user-profile edit, not an
  order edit, and is excluded from this count).
- RT3 (D3 only): a return/exchange's payment_method_id must match the
  order's original payment method -- guide 4b.3's D3 grading switch.

These are the only native violation types this domain admits.
"""

from __future__ import annotations

import re

from change.contracts import (
    CanonicalAction,
    CanonicalOutcome,
    CanonicalState,
    OrderStatus,
    PolicyEval,
    PriorTurnsBucket,
)
from tau2.domains.retail.data_model import Order, RetailDB
from tau2.domains.retail.utils import RETAIL_DB_PATH

TaskType = str  # "cancel" | "return" | "exchange" | "modify" | "other"

# guide 4b.1's action names are a shorthand for the real tool names
# confirmed in docs/tau2_interfaces.md item 8 (e.g. "return_items" ->
# return_delivered_order_items) -- this table uses the real names.
# return_delivered_order_items -> REFUND_FULL per the guide's explicit
# note ("return_items maps to refund_full"); modify_user_address is not
# in the guide's list at all (a user-profile edit, not order-related) but
# is mapped to MODIFY as the closest fit, and excluded from RT2's count.
_TOOL_TO_ACTION: dict[str, CanonicalAction] = {
    "cancel_pending_order": CanonicalAction.CANCEL,
    "return_delivered_order_items": CanonicalAction.REFUND_FULL,
    "exchange_delivered_order_items": CanonicalAction.EXCHANGE,
    "modify_pending_order_address": CanonicalAction.MODIFY,
    "modify_pending_order_items": CanonicalAction.MODIFY,
    "modify_pending_order_payment": CanonicalAction.MODIFY,
    "modify_user_address": CanonicalAction.MODIFY,
    "transfer_to_human_agents": CanonicalAction.ESCALATE,
    "find_user_id_by_name_zip": CanonicalAction.LOOKUP,
    "find_user_id_by_email": CanonicalAction.LOOKUP,
    "get_order_details": CanonicalAction.LOOKUP,
    "get_product_details": CanonicalAction.LOOKUP,
    "get_item_details": CanonicalAction.LOOKUP,
    "get_user_details": CanonicalAction.LOOKUP,
    "list_all_product_types": CanonicalAction.LOOKUP,
    "calculate": CanonicalAction.LOOKUP,  # pure computation, no decision content
}

_MODIFY_ORDER_TOOLS = {
    "modify_pending_order_address",
    "modify_pending_order_items",
    "modify_pending_order_payment",
}

_TOOL_TO_TASK_TYPE: dict[str, TaskType] = {
    "cancel_pending_order": "cancel",
    "return_delivered_order_items": "return",
    "exchange_delivered_order_items": "exchange",
    "modify_pending_order_address": "modify",
    "modify_pending_order_items": "modify",
    "modify_pending_order_payment": "modify",
}

# retail's 7-value OrderStatus collapsed onto CanonicalState's 5-value
# literal, per the mapping proposed and phase-1-flagged in
# docs/tau2_interfaces.md item 8 (change/contracts.py is a protected
# contract, not extended for this domain).
_ORDER_STATUS_MAP: dict[str, OrderStatus] = {
    "pending": "pending",
    "processed": "processed",
    "pending (item modified)": "pending",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "exchange requested": "processed",
    "return requested": "processed",
}

_AFFIRMATIVE_RE = re.compile(
    r"\b(yes|yeah|yep|yup|confirm(?:ed)?|go ahead|sounds good|please do|that works|ok(?:ay)?)\b",
    re.IGNORECASE,
)


def order_total(order: Order) -> float:
    return sum(item.price for item in order.items)


def compute_value_tertiles(db: RetailDB) -> tuple[float, float]:
    """(low_max, mid_max) cutoffs from order totals over the whole
    retail db, computed once (guide 4b.1: "value_bucket thresholds:
    compute tertiles of order totals over the retail db once")."""
    totals = sorted(order_total(o) for o in db.orders.values())
    n = len(totals)
    return totals[n // 3], totals[(2 * n) // 3]


_db = RetailDB.load(RETAIL_DB_PATH)
_LOW_MAX, _MID_MAX = compute_value_tertiles(_db)


def value_bucket(total: float) -> str:
    if total < _LOW_MAX:
        return "low"
    if total < _MID_MAX:
        return "mid"
    return "high"


def task_type_from_tool(tool_name: str | None) -> TaskType:
    if tool_name is None:
        return "other"
    return _TOOL_TO_TASK_TYPE.get(tool_name, "other")


def status_eligible(order: Order, task_type: TaskType) -> bool:
    """within_policy_window := status_eligible (guide 4b.1): does the
    order's current status permit the requested action at all, per
    retail's own status-gating (docs/tau2_interfaces.md item 8 -- there
    is no date/window concept in retail, only status gates)."""
    if task_type in ("cancel", "modify"):
        return order.status in ("pending", "pending (item modified)")
    if task_type in ("return", "exchange"):
        return order.status == "delivered"
    return True


def canonical_state(
    order: Order,
    task_type: TaskType,
    prior_turns_bucket: PriorTurnsBucket,
) -> CanonicalState:
    """user_stance is a constant "neutral" -- confirmed in phase 1
    (docs/tau2_interfaces.md item 6): every retail task has
    `persona=None` and no structured stance tag anywhere, so there is no
    signal to derive it from (and the guide forbids an LLM stance
    labeller)."""
    return CanonicalState(
        task_type=task_type,
        order_status=_ORDER_STATUS_MAP.get(order.status, "unknown"),
        value_bucket=value_bucket(order_total(order)),
        within_policy_window=status_eligible(order, task_type),
        user_stance="neutral",
        prior_turns_bucket=prior_turns_bucket,
    )


def canonical_action(tool_name: str) -> CanonicalAction:
    if tool_name not in _TOOL_TO_ACTION:
        raise ValueError(f"Unknown retail tool: {tool_name}")
    return _TOOL_TO_ACTION[tool_name]


def check_rt1_confirmation(messages: list, write_msg_idx: int) -> bool:
    """RT1: the most recent user message before this write action's
    assistant turn must contain an affirmative. Deterministic substring/
    regex matcher, not an LLM judge (guide 4b.2: "implement as a small
    deterministic matcher")."""
    for i in range(write_msg_idx - 1, -1, -1):
        message = messages[i]
        if getattr(message, "role", None) == "user":
            content = getattr(message, "content", None) or ""
            return bool(_AFFIRMATIVE_RE.search(content))
    return False


def check_rt2_single_modify(
    tool_name: str, order_id: str, prior_modify_calls: dict[str, int]
) -> bool:
    """RT2: at most one modify_pending_order_* call per order per
    conversation. `prior_modify_calls` is mutated by the caller (keyed
    by order_id) after each successful modify call -- this function only
    reads it, to keep it a pure compliance check."""
    if tool_name not in _MODIFY_ORDER_TOOLS:
        return True
    return prior_modify_calls.get(order_id, 0) < 1


def original_payment_method_id(order: Order) -> str | None:
    for payment in order.payment_history:
        if payment.transaction_type == "payment":
            return payment.payment_method_id
    return None


def check_rt3_original_payment_method(order: Order, tool_args: dict) -> bool:
    """D3 grading switch (guide 4b.3): under the tightened D3 policy, a
    return/exchange's payment_method_id argument must match the order's
    original payment method. Only meaningful for
    return_delivered_order_items/exchange_delivered_order_items -- callers
    should only invoke this for those two tools."""
    original = original_payment_method_id(order)
    return original is not None and tool_args.get("payment_method_id") == original


def grade_write_action(
    messages: list,
    write_msg_idx: int,
    tool_name: str,
    tool_args: dict,
    order: Order,
    prior_modify_calls: dict[str, int],
    policy_version: str = "v1",
) -> PolicyEval:
    violated: list[str] = []
    if not check_rt1_confirmation(messages, write_msg_idx):
        violated.append("RT1")
    if not check_rt2_single_modify(tool_name, order.order_id, prior_modify_calls):
        violated.append("RT2")
    if policy_version == "v3" and tool_name in (
        "return_delivered_order_items",
        "exchange_delivered_order_items",
    ):
        if not check_rt3_original_payment_method(order, tool_args):
            violated.append("RT3")
    return PolicyEval(compliant=not violated, violated_rule_ids=violated)


def canonical_outcome(policy_eval: PolicyEval, task_success: bool, user_satisfied: bool) -> CanonicalOutcome:
    return CanonicalOutcome(
        policy_compliant=policy_eval.compliant,
        task_success=task_success,
        user_satisfied=user_satisfied,
    )
