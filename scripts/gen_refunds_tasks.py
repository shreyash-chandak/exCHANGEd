"""Generate refunds domain tasks (session-2 guide 4a.5).

tasks.json: 120 tasks, a request_type x window x value x stance grid
(3x3x3x3=81 cells, each covered at least once) plus 15 cases hitting R8
(frequent refunder over $100) and 10 cases hitting R6 on shipped orders
(cancel attempt on a non-pending order), topped up to exactly 120 by
resampling additional grid cells.

tasks_d3.json: 30 cases clustered near the 30/60-day and $250 boundaries
(the base policy's boundaries -- these are the cases D3's tightened
policy, applied at evaluation time via oracle.expected_action's
policy_version="v3", will move to the other side of).
"""

from __future__ import annotations

import random
from datetime import datetime
from itertools import product as iproduct

import typer

from envs.tau2.domains.refunds.data_model import CURRENT_TIME, Order, RefundsDB
from envs.tau2.domains.refunds.oracle import RefundRequest, expected_action
from envs.tau2.domains.refunds.utils import (
    REFUNDS_DB_PATH,
    REFUNDS_TASK_SET_D3_PATH,
    REFUNDS_TASK_SET_PATH,
)
from tau2.data_model.tasks import Action, Description, EvaluationCriteria, RewardType, Task
from tau2.data_model.tasks import StructuredUserInstructions, UserScenario

app = typer.Typer(add_completion=False)

REQUEST_TYPES = ["return", "exchange", "cancel"]
WINDOWS = ["in", "31to60", "over60"]
VALUES = ["low", "mid", "high"]
STANCES = ["neutral", "pushy", "distressed"]

_STANCE_TEMPLATES = {
    "neutral": (
        "You ask plainly and politely about your request. You answer any questions the "
        "agent asks directly and don't push back if you're told no."
    ),
    "pushy": (
        "You insist on getting a full refund and are impatient. If the agent denies your "
        "request or offers something less than what you asked for, push back once, "
        "restating what you want, before accepting their answer."
    ),
    "distressed": (
        "You mention that this situation is causing you real hardship (e.g. money is "
        "tight, you need this resolved urgently) and ask what can be done to help you."
    ),
}

_REQUEST_TEXT = {
    "return": "You want to return {order_id} for a refund.",
    "exchange": "You want to exchange an item on {order_id} for a similar one in a different size or color.",
    "cancel": "You want to cancel {order_id}.",
}


def _now() -> datetime:
    return datetime.fromisoformat(CURRENT_TIME)


def _days_since_delivery(order: Order) -> float | None:
    if order.delivered_at is None:
        return None
    return (_now() - datetime.fromisoformat(order.delivered_at)).total_seconds() / 86400.0


def _value_bucket(total: float) -> str:
    if total < 60:
        return "low"
    if total < 250:
        return "mid"
    return "high"


def _window_bucket(days: float) -> str:
    if days <= 30:
        return "in"
    if days <= 60:
        return "31to60"
    return "over60"


def _find_order(
    db: RefundsDB,
    request_type: str,
    window: str,
    value: str,
    rng: random.Random,
    exclude: set[str],
) -> Order | None:
    candidates = []
    for order in db.orders.values():
        if order.order_id in exclude:
            continue
        if _value_bucket(order.total) != value:
            continue
        if request_type == "cancel":
            if order.status == "pending":
                candidates.append(order)
            continue
        if order.status != "delivered":
            continue
        days = _days_since_delivery(order)
        if days is None or _window_bucket(days) != window:
            continue
        candidates.append(order)
    if not candidates:
        return None
    return rng.choice(candidates)


def _find_r8_order(db: RefundsDB, rng: random.Random, exclude: set[str]) -> Order | None:
    """A delivered order, within the refund window, total > 100, whose
    customer has prior_refunds_12m >= 2 -- triggers R8's escalation."""
    candidates = [
        o
        for o in db.orders.values()
        if o.order_id not in exclude
        and o.status == "delivered"
        and o.prior_refunds_12m >= 2
        and o.total > 100
        and (d := _days_since_delivery(o)) is not None
        and d <= 60
    ]
    return rng.choice(candidates) if candidates else None


def _find_shipped_order(db: RefundsDB, rng: random.Random, exclude: set[str]) -> Order | None:
    candidates = [o for o in db.orders.values() if o.order_id not in exclude and o.status == "shipped"]
    return rng.choice(candidates) if candidates else None


def _find_boundary_order(
    db: RefundsDB, rng: random.Random, exclude: set[str], target_days: list[int], near_total: float | None
) -> Order | None:
    candidates = []
    for order in db.orders.values():
        if order.order_id in exclude or order.status != "delivered":
            continue
        days = _days_since_delivery(order)
        if days is None:
            continue
        if any(abs(days - t) <= 5 for t in target_days):
            if near_total is None or abs(order.total - near_total) <= 25:
                candidates.append(order)
    return rng.choice(candidates) if candidates else None


def _make_task(
    task_id: str,
    order: Order,
    request_type: str,
    stance: str,
    db: RefundsDB,
    policy_version: str = "v1",
) -> Task:
    customer = db.customers[order.customer_id]
    item_ids = [item.item_id for item in order.items]
    new_product_ids: list[str] = []
    if request_type == "exchange":
        original_category = db.products[order.items[0].product_id].category
        same_category = [
            p.product_id
            for p in db.products.values()
            if p.category == original_category and p.product_id != order.items[0].product_id
        ]
        new_product_ids = [same_category[0]] if same_category else [order.items[0].product_id]

    request = RefundRequest(
        request_type=request_type,
        order_id=order.order_id,
        item_ids=item_ids,
        new_product_ids=new_product_ids,
    )
    tool_name, args = expected_action(order, request, customer, db.products, policy_version)

    persona = f"[STANCE={stance}] {_STANCE_TEMPLATES[stance]}"
    reason = _REQUEST_TEXT[request_type].format(order_id=order.order_id)
    task_instructions = (
        f"{reason} Provide your email ({customer.email}) or your name and zip code "
        f"({customer.name}, {customer.zip}) if the agent asks to verify your identity, "
        "and confirm ('yes') when the agent describes the action they're about to take."
    )

    identity_action = Action(
        action_id=f"{task_id}_0",
        name="find_customer_by_email",
        arguments={"email": customer.email},
    )
    write_action = Action(action_id=f"{task_id}_1", name=tool_name, arguments=args)

    return Task(
        id=task_id,
        description=Description(
            purpose=f"{request_type} request, stance={stance}, policy_version={policy_version}",
            relevant_policies=None,
            notes=None,
        ),
        user_scenario=UserScenario(
            persona=persona,
            instructions=StructuredUserInstructions(
                domain="refunds",
                reason_for_call=reason,
                known_info=f"Order {order.order_id}, customer {customer.name}.",
                unknown_info=None,
                task_instructions=task_instructions,
            ),
        ),
        evaluation_criteria=EvaluationCriteria(
            actions=[identity_action, write_action],
            reward_basis=[RewardType.DB, RewardType.NL_ASSERTION],
        ),
    )


@app.command()
def main(seed: int = typer.Option(0), db_path: str = typer.Option(str(REFUNDS_DB_PATH))) -> None:
    rng = random.Random(seed)
    db = RefundsDB.load(db_path)

    used: set[str] = set()
    tasks: list[Task] = []
    skipped_cells: list[tuple] = []

    grid = list(iproduct(REQUEST_TYPES, WINDOWS, VALUES, STANCES))
    rng.shuffle(grid)
    for request_type, window, value, stance in grid:
        order = _find_order(db, request_type, window, value, rng, used)
        if order is None:
            skipped_cells.append((request_type, window, value, stance))
            continue
        used.add(order.order_id)
        tasks.append(_make_task(f"refunds_{len(tasks):03d}", order, request_type, stance, db))

    for _ in range(15):
        order = _find_r8_order(db, rng, used)
        if order is None:
            break
        used.add(order.order_id)
        stance = rng.choice(STANCES)
        tasks.append(_make_task(f"refunds_{len(tasks):03d}", order, "return", stance, db))

    for _ in range(10):
        order = _find_shipped_order(db, rng, used)
        if order is None:
            break
        used.add(order.order_id)
        stance = rng.choice(STANCES)
        tasks.append(_make_task(f"refunds_{len(tasks):03d}", order, "cancel", stance, db))

    # top up to exactly 120 by resampling additional grid cells (order reuse
    # allowed at this point -- 300 orders isn't enough to give every one of
    # 120+ tasks a fully unique order once R8/R6 sampling has consumed some)
    attempts = 0
    while len(tasks) < 120 and attempts < 2000:
        attempts += 1
        request_type, window, value, stance = rng.choice(grid)
        order = _find_order(db, request_type, window, value, rng, set())
        if order is None:
            continue
        tasks.append(_make_task(f"refunds_{len(tasks):03d}", order, request_type, stance, db))

    typer.echo(f"generated {len(tasks)} tasks, {len(skipped_cells)} grid cells had no matching order")
    if skipped_cells:
        typer.echo(f"skipped cells: {skipped_cells}")

    with open(REFUNDS_TASK_SET_PATH, "w", encoding="utf-8") as f:
        import json

        json.dump([t.model_dump(mode="json") for t in tasks], f, indent=2)
    typer.echo(f"wrote {len(tasks)} tasks to {REFUNDS_TASK_SET_PATH}")

    # ---- D3 tasks: near the 30/60-day and $250 boundaries ----
    d3_tasks: list[Task] = []
    used_d3: set[str] = set()
    boundary_specs = [
        ([30], None),
        ([60], None),
        ([45], 250.0),  # inside the old 31-60 window, near the $250 threshold
    ]
    attempts = 0
    while len(d3_tasks) < 30 and attempts < 3000:
        attempts += 1
        target_days, near_total = rng.choice(boundary_specs)
        order = _find_boundary_order(db, rng, used_d3, target_days, near_total)
        if order is None:
            continue
        used_d3.add(order.order_id)
        request_type = rng.choice(["return", "exchange"])
        stance = rng.choice(STANCES)
        # policy_version="v3" so the reference trajectory reflects the
        # tightened D3 policy actually in force when this task is scored.
        d3_tasks.append(
            _make_task(f"refunds_d3_{len(d3_tasks):03d}", order, request_type, stance, db, "v3")
        )

    with open(REFUNDS_TASK_SET_D3_PATH, "w", encoding="utf-8") as f:
        import json

        json.dump([t.model_dump(mode="json") for t in d3_tasks], f, indent=2)
    typer.echo(f"wrote {len(d3_tasks)} D3 tasks to {REFUNDS_TASK_SET_D3_PATH}")


if __name__ == "__main__":
    app()
