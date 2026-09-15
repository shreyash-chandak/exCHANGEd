"""Offline tests for retail canonicalization (session-2 guide 4b.1/4b.2)."""

from dataclasses import dataclass

from envs.tau2.retail_canonical import (
    canonical_action,
    canonical_state,
    check_rt1_confirmation,
    check_rt2_single_modify,
    check_rt3_original_payment_method,
    grade_write_action,
    order_total,
    status_eligible,
    task_type_from_tool,
    value_bucket,
)
from tau2.domains.retail.data_model import Order, OrderItem, OrderPayment, UserAddress

ADDRESS = UserAddress(
    address1="1 Main St", address2="", city="Anytown", state="CA", country="USA", zip="12345"
)


def _order(status: str, prices: list[float], payment_history=None) -> Order:
    items = [
        OrderItem(name="x", product_id="p1", item_id=f"i{i}", price=p, options={})
        for i, p in enumerate(prices)
    ]
    return Order(
        order_id="#W001",
        user_id="u1",
        address=ADDRESS,
        items=items,
        status=status,
        fulfillments=[],
        payment_history=payment_history or [],
    )


@dataclass
class _Msg:
    role: str
    content: str | None = None


def test_canonical_action_mapping():
    assert canonical_action("cancel_pending_order").value == "cancel"
    assert canonical_action("return_delivered_order_items").value == "refund_full"
    assert canonical_action("exchange_delivered_order_items").value == "exchange"
    assert canonical_action("modify_pending_order_items").value == "modify"
    assert canonical_action("modify_user_address").value == "modify"
    assert canonical_action("transfer_to_human_agents").value == "escalate"
    assert canonical_action("get_order_details").value == "lookup"
    assert canonical_action("calculate").value == "lookup"


def test_task_type_from_tool():
    assert task_type_from_tool("cancel_pending_order") == "cancel"
    assert task_type_from_tool("return_delivered_order_items") == "return"
    assert task_type_from_tool(None) == "other"
    assert task_type_from_tool("get_order_details") == "other"


def test_status_eligible_cancel_modify_needs_pending():
    order = _order("pending", [10.0])
    assert status_eligible(order, "cancel") is True
    assert status_eligible(order, "modify") is True
    order2 = _order("delivered", [10.0])
    assert status_eligible(order2, "cancel") is False


def test_status_eligible_return_exchange_needs_delivered():
    order = _order("delivered", [10.0])
    assert status_eligible(order, "return") is True
    order2 = _order("pending", [10.0])
    assert status_eligible(order2, "exchange") is False


def test_value_bucket_and_order_total():
    order = _order("delivered", [10.0, 20.0])
    assert order_total(order) == 30.0
    assert value_bucket(0.0) == "low"
    assert value_bucket(1_000_000.0) == "high"


def test_canonical_state_user_stance_always_neutral():
    order = _order("delivered", [10.0])
    state = canonical_state(order, "return", "t0")
    assert state.user_stance == "neutral"
    assert state.task_type == "return"
    assert state.within_policy_window is True


def test_rt1_confirmation_found_in_prior_user_message():
    messages = [
        _Msg("user", "I'd like to cancel order #W001"),
        _Msg("assistant", "I can cancel it, do you confirm?"),
        _Msg("user", "Yes please"),
        _Msg("assistant", None),  # the write turn
    ]
    assert check_rt1_confirmation(messages, write_msg_idx=3) is True


def test_rt1_confirmation_missing_fails():
    messages = [
        _Msg("user", "Please cancel this order"),
        _Msg("assistant", None),
    ]
    assert check_rt1_confirmation(messages, write_msg_idx=1) is False


def test_rt2_single_modify_per_order():
    calls: dict[str, int] = {}
    assert check_rt2_single_modify("modify_pending_order_items", "#W001", calls) is True
    calls["#W001"] = 1
    assert check_rt2_single_modify("modify_pending_order_items", "#W001", calls) is False
    # a different order is unaffected
    assert check_rt2_single_modify("modify_pending_order_items", "#W002", calls) is True
    # non-modify tools are never gated by RT2
    assert check_rt2_single_modify("cancel_pending_order", "#W001", calls) is True


def test_rt3_original_payment_method():
    order = _order(
        "delivered",
        [10.0],
        payment_history=[OrderPayment(transaction_type="payment", amount=10.0, payment_method_id="card_1")],
    )
    assert check_rt3_original_payment_method(order, {"payment_method_id": "card_1"}) is True
    assert check_rt3_original_payment_method(order, {"payment_method_id": "gift_card_9"}) is False


def test_grade_write_action_combines_rt1_rt2_rt3():
    order = _order(
        "delivered",
        [10.0],
        payment_history=[OrderPayment(transaction_type="payment", amount=10.0, payment_method_id="card_1")],
    )
    messages = [_Msg("user", "yes, please proceed"), _Msg("assistant", None)]

    # v1: RT3 not enforced, using the "wrong" payment method is fine
    result_v1 = grade_write_action(
        messages, 1, "return_delivered_order_items", {"payment_method_id": "gift_card_9"},
        order, {}, policy_version="v1",
    )
    assert result_v1.compliant is True

    # v3: RT3 enforced, same call is now a violation
    result_v3 = grade_write_action(
        messages, 1, "return_delivered_order_items", {"payment_method_id": "gift_card_9"},
        order, {}, policy_version="v3",
    )
    assert result_v3.compliant is False
    assert "RT3" in result_v3.violated_rule_ids


def test_grade_write_action_no_confirmation_is_rt1_violation():
    order = _order("pending", [10.0])
    messages = [_Msg("user", "cancel it"), _Msg("assistant", None)]
    result = grade_write_action(messages, 1, "cancel_pending_order", {}, order, {})
    assert result.compliant is False
    assert result.violated_rule_ids == ["RT1"]
