"""Offline domain registration + canonicalization tests (session-2 guide
4a.6)."""

import envs.tau2.domains.refunds  # noqa: F401 -- registers at import time
from envs.tau2.domains.refunds.data_model import RefundsDB
from envs.tau2.domains.refunds.oracle import RefundRequest, check
from envs.tau2.domains.refunds.utils import REFUNDS_DB_PATH
from envs.tau2.refunds_canonical import (
    canonical_action,
    canonical_outcome,
    canonical_state,
    parse_user_stance,
)
from tau2.registry import registry


def test_domain_registered():
    assert "refunds" in registry.get_domains()
    assert "refunds" in registry.get_task_sets()


def test_environment_loads():
    env = registry.get_env_constructor("refunds")()
    assert env.domain_name == "refunds"
    assert len(env.policy) > 0


def test_120_base_tasks():
    tasks = registry.get_tasks_loader("refunds")()
    assert len(tasks) == 120
    assert len({t.id for t in tasks}) == 120


def test_30_d3_tasks():
    tasks = registry.get_tasks_loader("refunds")("d3")
    assert len(tasks) == 30


def test_policy_nonempty():
    env = registry.get_env_constructor("refunds")()
    assert "R1" in env.policy
    assert "R10" in env.policy


def test_every_task_expected_action_passes_oracle_check():
    db = RefundsDB.load(REFUNDS_DB_PATH)
    tasks = registry.get_tasks_loader("refunds")()
    for task in tasks:
        write_action = task.evaluation_criteria.actions[1]
        order_id = write_action.arguments["order_id"]
        order = db.orders[order_id]
        customer = db.customers[order.customer_id]
        request_type = task.description.purpose.split(",")[0].split()[0]
        item_ids = write_action.arguments.get("item_ids") or [i.item_id for i in order.items]
        new_product_ids = write_action.arguments.get("new_product_ids", [])
        policy_version = "v3" if "v3" in task.description.purpose else "v1"
        request = RefundRequest(
            request_type=request_type,
            order_id=order_id,
            item_ids=item_ids,
            new_product_ids=new_product_ids,
        )
        taken = (write_action.name, write_action.arguments)
        result = check(order, request, customer, db.products, taken, policy_version)
        assert result.compliant, f"{task.id}: {taken} not compliant"


# ---- canonicalization ----


def test_canonical_state_within_window_return():
    db = RefundsDB.load(REFUNDS_DB_PATH)
    order = next(o for o in db.orders.values() if o.status == "delivered")
    state = canonical_state(order, "return", "[STANCE=pushy] x", "t0")
    assert state.task_type == "return"
    assert state.user_stance == "pushy"


def test_canonical_state_cancel_uses_pending_status():
    db = RefundsDB.load(REFUNDS_DB_PATH)
    pending = next(o for o in db.orders.values() if o.status == "pending")
    non_pending = next(o for o in db.orders.values() if o.status != "pending")
    assert canonical_state(pending, "cancel", None, "t0").within_policy_window is True
    assert canonical_state(non_pending, "cancel", None, "t0").within_policy_window is False


def test_canonical_state_order_status_collapses_onto_five_values():
    db = RefundsDB.load(REFUNDS_DB_PATH)
    shipped = next(o for o in db.orders.values() if o.status == "shipped")
    state = canonical_state(shipped, "cancel", None, "t0")
    assert state.order_status == "processed"


def test_parse_user_stance_defaults_to_neutral():
    assert parse_user_stance(None) == "neutral"
    assert parse_user_stance("no tag here") == "neutral"
    assert parse_user_stance("[STANCE=distressed] hardship text") == "distressed"


def test_canonical_action_mapping():
    assert canonical_action("refund_full").value == "refund_full"
    assert canonical_action("cancel_order").value == "cancel"
    assert canonical_action("get_order").value == "lookup"


def test_canonical_outcome_uses_oracle_for_compliance():
    db = RefundsDB.load(REFUNDS_DB_PATH)
    order = next(o for o in db.orders.values() if o.status == "pending")
    customer = db.customers[order.customer_id]
    request = RefundRequest(request_type="cancel", order_id=order.order_id)
    compliant_taken = ("cancel_order", {"order_id": order.order_id})
    outcome = canonical_outcome(
        order, request, customer, db.products, compliant_taken, task_success=True, user_satisfied=True
    )
    assert outcome.policy_compliant is True

    noncompliant_taken = ("deny_request", {"order_id": order.order_id, "reason": "no"})
    outcome2 = canonical_outcome(
        order, request, customer, db.products, noncompliant_taken, task_success=False, user_satisfied=False
    )
    assert outcome2.policy_compliant is False
