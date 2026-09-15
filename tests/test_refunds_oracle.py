"""Exhaustive oracle tests over a state grid (session-2 guide 4a.4: "at
least 500 combinations"). Every state's expected_action() must itself be
graded compliant by check() -- the oracle can't disagree with itself."""

from itertools import product as iproduct

import pytest

from envs.tau2.domains.refunds.data_model import (
    Customer,
    Order,
    OrderItem,
    PaymentMethod,
    Product,
)
from envs.tau2.domains.refunds.oracle import RefundRequest, check, expected_action

PRODUCTS = {
    "p_electronics": Product(product_id="p_electronics", name="e", category="electronics", price=100.0),
    "p_electronics_2": Product(product_id="p_electronics_2", name="e2", category="electronics", price=120.0),
    "p_apparel": Product(product_id="p_apparel", name="a", category="apparel", price=40.0),
}

CUSTOMER_CARD = Customer(
    customer_id="c1",
    name="Test Customer",
    email="t@example.com",
    zip="12345",
    payment_methods=[PaymentMethod(id="pm_card", type="card")],
)
CUSTOMER_GIFT = Customer(
    customer_id="c2",
    name="Gift Customer",
    email="g@example.com",
    zip="54321",
    payment_methods=[PaymentMethod(id="pm_gift", type="gift_card")],
)


def _order(
    status: str,
    days_since_delivery: float | None,
    total: float,
    damage_reported: bool,
    prior_refunds_12m: int,
    payment_method_id: str,
) -> Order:
    delivered_at = None
    if days_since_delivery is not None:
        from datetime import timedelta

        from envs.tau2.domains.refunds.oracle import _now

        delivered_at = (_now() - timedelta(days=days_since_delivery)).isoformat()

    return Order(
        order_id="o1",
        customer_id="c1",
        items=[
            OrderItem(item_id="i1", product_id="p_electronics", price=100.0, qty=1),
        ],
        total=total,
        status=status,
        created_at="2026-01-01T00:00:00",
        delivered_at=delivered_at,
        payment_method_id=payment_method_id,
        damage_reported=damage_reported,
        prior_refunds_12m=prior_refunds_12m,
    )


# ---- grid for return/exchange requests on delivered orders ----
_DAYS = [5, 15, 25, 35, 40, 50, 55, 65, 80]
_TOTALS = [30.0, 100.0, 149.0, 151.0, 200.0, 249.0, 251.0, 300.0]
_DAMAGE = [True, False]
_PRIOR_REFUNDS = [0, 1, 2, 3]
_PAYMENT = ["pm_card", "pm_gift"]
_POLICY_VERSIONS = ["v1", "v3"]
_REQUEST_TYPES = ["return", "exchange"]

DELIVERED_GRID = list(
    iproduct(
        _REQUEST_TYPES,
        _DAYS,
        _TOTALS,
        _DAMAGE,
        _PRIOR_REFUNDS,
        _PAYMENT,
        _POLICY_VERSIONS,
    )
)


@pytest.mark.parametrize(
    "request_type,days,total,damage,prior_refunds,payment_method_id,policy_version", DELIVERED_GRID
)
def test_expected_action_is_always_compliant_delivered(
    request_type, days, total, damage, prior_refunds, payment_method_id, policy_version
):
    customer = CUSTOMER_CARD if payment_method_id == "pm_card" else CUSTOMER_GIFT
    order = _order("delivered", days, total, damage, prior_refunds, payment_method_id)
    request = RefundRequest(
        request_type=request_type,
        order_id="o1",
        item_ids=["i1"],
        new_product_ids=["p_electronics_2"] if request_type == "exchange" else [],
    )
    taken = expected_action(order, request, customer, PRODUCTS, policy_version)
    result = check(order, request, customer, PRODUCTS, taken, policy_version)
    assert result.compliant, (
        f"oracle disagrees with itself: {taken} not compliant for "
        f"request={request_type} days={days} total={total} damage={damage} "
        f"prior_refunds={prior_refunds} payment={payment_method_id} policy={policy_version}"
    )


# ---- grid for non-delivered statuses (cancel requests, and return/exchange
# attempts that should be denied outright) ----
_NON_DELIVERED_STATUSES = ["pending", "processed", "shipped", "cancelled", "refunded", "exchanged"]
_NON_DELIVERED_REQUEST_TYPES = ["cancel", "return", "exchange"]

NON_DELIVERED_GRID = list(
    iproduct(_NON_DELIVERED_STATUSES, _NON_DELIVERED_REQUEST_TYPES, _PRIOR_REFUNDS, _POLICY_VERSIONS)
)


@pytest.mark.parametrize(
    "status,request_type,prior_refunds,policy_version", NON_DELIVERED_GRID
)
def test_expected_action_is_always_compliant_non_delivered(
    status, request_type, prior_refunds, policy_version
):
    order = _order(status, None, 100.0, False, prior_refunds, "pm_card")
    request = RefundRequest(
        request_type=request_type,
        order_id="o1",
        item_ids=["i1"],
        new_product_ids=["p_electronics_2"] if request_type == "exchange" else [],
    )
    taken = expected_action(order, request, CUSTOMER_CARD, PRODUCTS, policy_version)
    result = check(order, request, CUSTOMER_CARD, PRODUCTS, taken, policy_version)
    assert result.compliant


def test_wants_human_always_escalates_and_is_compliant():
    order = _order("delivered", 5, 100.0, False, 0, "pm_card")
    request = RefundRequest(request_type="return", order_id="o1", wants_human=True)
    taken = expected_action(order, request, CUSTOMER_CARD, PRODUCTS)
    assert taken[0] == "escalate"
    result = check(order, request, CUSTOMER_CARD, PRODUCTS, taken)
    assert result.compliant


def test_grid_size_at_least_500():
    assert len(DELIVERED_GRID) + len(NON_DELIVERED_GRID) >= 500


def test_check_flags_wrong_action_noncompliant():
    order = _order("delivered", 5, 100.0, False, 0, "pm_card")
    request = RefundRequest(request_type="return", order_id="o1")
    wrong_taken = ("deny_request", {"order_id": "o1", "reason": "made_up"})
    result = check(order, request, CUSTOMER_CARD, PRODUCTS, wrong_taken)
    assert not result.compliant
    assert result.violated_rule_ids
