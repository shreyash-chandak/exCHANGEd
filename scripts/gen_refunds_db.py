"""Generate the refunds domain's synthetic database (session-2 guide 4a.1).

Deterministic given --seed. 60 customers, 40 products across 5 categories,
300 orders with created_at spread over the 120 days before CURRENT_TIME
and status consistent with age. Value tertiles target low<60, mid 60-250,
high>250 approximately.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import typer

from envs.tau2.domains.refunds.data_model import (
    CURRENT_TIME,
    Customer,
    Order,
    OrderItem,
    PaymentMethod,
    Product,
    RefundsDB,
)
from envs.tau2.domains.refunds.utils import REFUNDS_DB_PATH

app = typer.Typer(add_completion=False)

_N_CUSTOMERS = 60
_N_PRODUCTS = 40
_N_ORDERS = 300
_CATEGORIES = ["electronics", "apparel", "home", "sporting_goods", "books"]
_FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Avery",
    "Quinn", "Drew", "Reese", "Sam", "Rowan", "Skyler", "Emerson", "Finley",
    "Harper", "Kendall", "Logan", "Parker",
]
_LAST_NAMES = [
    "Nguyen", "Garcia", "Smith", "Kim", "Patel", "Johnson", "Brown", "Lee",
    "Martinez", "Davis", "Lopez", "Wilson", "Anderson", "Thomas", "Moore",
    "Jackson", "White", "Harris", "Clark", "Young",
]


def _current_time() -> datetime:
    return datetime.fromisoformat(CURRENT_TIME)


def _gen_customers(rng: random.Random) -> dict[str, Customer]:
    customers: dict[str, Customer] = {}
    for i in range(_N_CUSTOMERS):
        customer_id = f"cust_{i:03d}"
        first = rng.choice(_FIRST_NAMES)
        last = rng.choice(_LAST_NAMES)
        payment_methods = [PaymentMethod(id=f"{customer_id}_card", type="card")]
        if rng.random() < 0.4:
            payment_methods.append(PaymentMethod(id=f"{customer_id}_giftcard", type="gift_card"))
        customers[customer_id] = Customer(
            customer_id=customer_id,
            name=f"{first} {last}",
            email=f"{first.lower()}.{last.lower()}{i}@example.com",
            zip=f"{rng.randint(10000, 99999)}",
            payment_methods=payment_methods,
        )
    return customers


# Price ranges per category chosen so that, combined with qty in gen_orders,
# order totals spread roughly evenly across the low(<60)/mid(60-250)/high(>250)
# tertiles -- verified empirically below, not just assumed. Deliberately
# polarized (cheap categories stay cheap, expensive stay expensive) rather
# than each spanning low-to-high, since multi-item orders mixing a cheap and
# an expensive item otherwise regress everything toward the mid tertile.
_PRICE_RANGES = {
    "electronics": (80.0, 450.0),
    "apparel": (8.0, 55.0),
    "home": (10.0, 300.0),
    "sporting_goods": (10.0, 70.0),
    "books": (5.0, 25.0),
}


def _gen_products(rng: random.Random) -> dict[str, Product]:
    products: dict[str, Product] = {}
    per_category = _N_PRODUCTS // len(_CATEGORIES)
    idx = 0
    for category in _CATEGORIES:
        lo, hi = _PRICE_RANGES[category]
        for _ in range(per_category):
            product_id = f"prod_{idx:03d}"
            price = round(rng.uniform(lo, hi), 2)
            products[product_id] = Product(
                product_id=product_id,
                name=f"{category}_item_{idx:03d}",
                category=category,
                price=price,
            )
            idx += 1
    return products


def _status_for_age(rng: random.Random, days_old: int) -> str:
    """Status consistent with age: very recent orders haven't shipped yet,
    older orders are almost always delivered (needed for return/exchange
    window coverage across 0-30/31-60/60+ days), a few end up in a
    terminal refunded/cancelled/exchanged state.

    Widened from a <2-day to a <7-day "recent" bucket: at <2 days, only
    ~4 of 300 orders landed as pending (measured), nowhere near enough
    for scripts/gen_refunds_tasks.py's cancel-request grid (3 value x 3
    stance cells, each needing its own pending order) to find a match --
    23 of 81 grid cells came back empty. ~7 days gives enough pending
    volume across all three value tertiles without changing the
    delivered-order population the return/exchange window grid relies on
    (delivered orders still dominate from day 5 onward, unchanged)."""
    if days_old < 7:
        return rng.choices(["pending", "processed"], weights=[0.55, 0.45])[0]
    if days_old < 10:
        return rng.choices(["processed", "shipped", "delivered"], weights=[0.3, 0.4, 0.3])[0]
    # Older orders: mostly delivered, a handful terminal for realism/coverage.
    return rng.choices(
        ["delivered", "cancelled", "refunded", "exchanged"],
        weights=[0.88, 0.04, 0.05, 0.03],
    )[0]


def _value_bucket(total: float) -> str:
    if total < 60:
        return "low"
    if total < 250:
        return "mid"
    return "high"


def _pick_items(rng: random.Random, products: dict[str, Product], order_id: str) -> list[OrderItem]:
    product_ids = list(products.keys())
    n_items = rng.choices([1, 2, 3], weights=[0.55, 0.3, 0.15])[0]
    items = []
    for item_idx in range(n_items):
        pid = rng.choice(product_ids)
        price = products[pid].price
        qty = rng.choices([1, 2], weights=[0.8, 0.2])[0]
        items.append(OrderItem(item_id=f"{order_id}_item_{item_idx}", product_id=pid, price=price, qty=qty))
    return items


def _pick_items_in_bucket(
    rng: random.Random, products: dict[str, Product], order_id: str, bucket: str, max_tries: int = 50
) -> list[OrderItem]:
    """Retries random item selection until the resulting total lands in the
    requested value bucket -- used to guarantee task-generation coverage
    for grid cells a purely random population wouldn't reliably fill
    (see _reserve_orders_for_task_coverage)."""
    best = None
    best_gap = float("inf")
    for _ in range(max_tries):
        items = _pick_items(rng, products, order_id)
        total = round(sum(i.price * i.qty for i in items), 2)
        if _value_bucket(total) == bucket:
            return items
        gap = 0.0 if bucket == "mid" else abs(total - (60.0 if bucket == "low" else 250.0))
        if gap < best_gap:
            best, best_gap = items, gap
    return best


def _reserve_orders_for_task_coverage(
    rng: random.Random, customers: dict[str, Customer], products: dict[str, Product]
) -> list[Order]:
    """gen_refunds_tasks.py's grid needs categories a purely random
    population doesn't reliably produce enough of: pending orders spread
    across all three value tiers (for the cancel-request grid), shipped
    orders (R6-on-shipped cases), and delivered orders whose customer has
    prior_refunds_12m>=2 within the refund window (R8 cases). Measured
    directly: even after widening the "recent" age bucket
    (_status_for_age), a from-scratch run still left some grid cells
    (e.g. cancel x high-value) with zero matching orders. Rather than keep
    tuning random weights and hoping, reserve a small number of orders
    with these properties forced explicitly."""
    now = _current_time()
    customer_ids = list(customers.keys())
    reserved: list[Order] = []
    idx = 0

    def _next_id() -> str:
        nonlocal idx
        order_id = f"order_r{idx:03d}"
        idx += 1
        return order_id

    # 27 pending orders, 9 per value bucket -- gen_refunds_tasks.py's grid
    # treats "window" as a real (if functionally inert for cancel-type
    # requests) axis, so a single (value, stance) pair is drawn against by
    # 3 separate grid cells (one per window label) each needing their own
    # order once used. 9 = 3 windows x 3 stances per value bucket,
    # guaranteeing every cancel x value x stance x window cell can be
    # filled without reuse. Spread across customers with varying
    # prior_refunds_12m (irrelevant to R6/cancel but keeps variety).
    for bucket in ("low", "mid", "high"):
        for _ in range(9):
            order_id = _next_id()
            customer_id = rng.choice(customer_ids)
            customer = customers[customer_id]
            items = _pick_items_in_bucket(rng, products, order_id, bucket)
            days_old = rng.randint(0, 4)
            created_at = now - timedelta(days=days_old, hours=rng.randint(0, 23))
            reserved.append(
                Order(
                    order_id=order_id,
                    customer_id=customer_id,
                    items=items,
                    total=round(sum(i.price * i.qty for i in items), 2),
                    status="pending",
                    created_at=created_at.isoformat(),
                    delivered_at=None,
                    payment_method_id=rng.choice(customer.payment_methods).id,
                    damage_reported=False,
                    prior_refunds_12m=rng.choices([0, 1, 2, 3], weights=[0.55, 0.25, 0.13, 0.07])[0],
                )
            )

    # 15 shipped orders (guide needs >=10 for the R6 cases).
    for _ in range(15):
        order_id = _next_id()
        customer_id = rng.choice(customer_ids)
        customer = customers[customer_id]
        items = _pick_items(rng, products, order_id)
        days_old = rng.randint(3, 6)
        created_at = now - timedelta(days=days_old, hours=rng.randint(0, 23))
        reserved.append(
            Order(
                order_id=order_id,
                customer_id=customer_id,
                items=items,
                total=round(sum(i.price * i.qty for i in items), 2),
                status="shipped",
                created_at=created_at.isoformat(),
                delivered_at=None,
                payment_method_id=rng.choice(customer.payment_methods).id,
                damage_reported=False,
                prior_refunds_12m=rng.choices([0, 1, 2, 3], weights=[0.55, 0.25, 0.13, 0.07])[0],
            )
        )

    # 20 delivered, within-60-days, total>100, frequent-refunder orders
    # (guide needs >=15 R8 cases).
    for _ in range(20):
        order_id = _next_id()
        customer_id = rng.choice(customer_ids)
        customer = customers[customer_id]
        items = _pick_items_in_bucket(rng, products, order_id, rng.choice(["mid", "high"]))
        days_old = rng.randint(10, 55)
        created_at = now - timedelta(days=days_old, hours=rng.randint(0, 23))
        delivery_lag = rng.randint(2, 6)
        delivered_at = created_at + timedelta(days=delivery_lag)
        reserved.append(
            Order(
                order_id=order_id,
                customer_id=customer_id,
                items=items,
                total=round(sum(i.price * i.qty for i in items), 2),
                status="delivered",
                created_at=created_at.isoformat(),
                delivered_at=delivered_at.isoformat(),
                payment_method_id=rng.choice(customer.payment_methods).id,
                damage_reported=rng.random() < 0.12,
                prior_refunds_12m=rng.choices([2, 3], weights=[0.6, 0.4])[0],
            )
        )

    return reserved


def _gen_orders(
    rng: random.Random, customers: dict[str, Customer], products: dict[str, Product]
) -> dict[str, Order]:
    now = _current_time()
    customer_ids = list(customers.keys())
    product_ids = list(products.keys())

    # prior_refunds_12m is a per-customer count (guide 4a.1 puts the field
    # on Order, but R8 reads it as a customer-level fact) -- assign once per
    # customer, replicate across that customer's orders for consistency.
    # Skewed toward 0-1 with a deliberate minority at 2+ so R8 is reachable.
    prior_refunds_by_customer = {
        cid: rng.choices([0, 1, 2, 3], weights=[0.55, 0.25, 0.13, 0.07])[0]
        for cid in customer_ids
    }

    orders: dict[str, Order] = {}
    n_random = _N_ORDERS - 62  # 62 reserved for guaranteed task-coverage categories
    for i in range(n_random):
        order_id = f"order_{i:04d}"
        customer_id = rng.choice(customer_ids)
        customer = customers[customer_id]
        days_old = rng.randint(0, 120)
        created_at = now - timedelta(days=days_old, hours=rng.randint(0, 23))

        items = _pick_items(rng, products, order_id)
        total = round(sum(i.price * i.qty for i in items), 2)

        status = _status_for_age(rng, days_old)
        delivered_at = None
        if status in ("delivered", "refunded", "exchanged"):
            delivery_lag = rng.randint(2, 6)
            delivered_at = (created_at + timedelta(days=delivery_lag)).isoformat()

        damage_reported = False
        if status == "delivered":
            damage_reported = rng.random() < 0.12

        payment_method_id = rng.choice(customer.payment_methods).id

        orders[order_id] = Order(
            order_id=order_id,
            customer_id=customer_id,
            items=items,
            total=total,
            status=status,
            created_at=created_at.isoformat(),
            delivered_at=delivered_at,
            payment_method_id=payment_method_id,
            damage_reported=damage_reported,
            prior_refunds_12m=prior_refunds_by_customer[customer_id],
        )

    for order in _reserve_orders_for_task_coverage(rng, customers, products):
        orders[order.order_id] = order

    return orders


def _report_value_tertiles(orders: dict[str, Order]) -> None:
    totals = sorted(o.total for o in orders.values())
    low = sum(1 for t in totals if t < 60)
    mid = sum(1 for t in totals if 60 <= t < 250)
    high = sum(1 for t in totals if t >= 250)
    n = len(totals)
    typer.echo(
        f"value tertiles: low(<60)={low} ({low / n:.1%}) "
        f"mid(60-250)={mid} ({mid / n:.1%}) high(>=250)={high} ({high / n:.1%})"
    )


@app.command()
def main(seed: int = typer.Option(0), out: str = typer.Option(str(REFUNDS_DB_PATH))) -> None:
    rng = random.Random(seed)
    customers = _gen_customers(rng)
    products = _gen_products(rng)
    orders = _gen_orders(rng, customers, products)

    db = RefundsDB(customers=customers, products=products, orders=orders)
    db.dump(out)

    _report_value_tertiles(orders)
    typer.echo(
        f"wrote {len(customers)} customers, {len(products)} products, "
        f"{len(orders)} orders to {out}"
    )


if __name__ == "__main__":
    app()
