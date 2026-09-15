"""Data model for the refunds tau2 domain (session-2 guide 4a.1).

Tools built on this DB do not enforce policy (see tools.py's module
docstring) -- compliance is graded separately, after the fact, by
oracle.py. This is the domain's whole point: a generosity surface a
drifting agent can actually violate, unlike tau2 retail's tools (which
enforce most status rules themselves).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from tau2.environment.db import DB
from tau2.utils.pydantic_utils import BaseModelNoExtra

CURRENT_TIME = "2026-06-01T12:00:00"

PaymentMethodType = Literal["card", "gift_card"]
OrderStatus = Literal[
    "pending", "processed", "shipped", "delivered", "cancelled", "refunded", "exchanged"
]


class PaymentMethod(BaseModelNoExtra):
    id: str = Field(description="Unique identifier for the payment method.")
    type: PaymentMethodType = Field(description="'card' or 'gift_card'.")


class Customer(BaseModelNoExtra):
    customer_id: str = Field(description="Unique identifier for the customer.")
    name: str = Field(description="Customer's full name.")
    email: str = Field(description="Customer's email address.")
    zip: str = Field(description="Customer's zip code.")
    payment_methods: list[PaymentMethod] = Field(
        description="Payment methods on file for this customer."
    )


class Product(BaseModelNoExtra):
    product_id: str = Field(description="Unique identifier for the product.")
    name: str = Field(description="Product name.")
    category: str = Field(description="Product category.")
    price: float = Field(description="Unit price in USD.")


class OrderItem(BaseModelNoExtra):
    item_id: str = Field(description="Unique identifier for this line item.")
    product_id: str = Field(description="The product this line item is for.")
    price: float = Field(description="Unit price at time of order.")
    qty: int = Field(description="Quantity ordered.")


class Order(BaseModelNoExtra):
    order_id: str = Field(description="Unique identifier for the order.")
    customer_id: str = Field(description="The customer who placed this order.")
    items: list[OrderItem] = Field(description="Line items in this order.")
    total: float = Field(description="Order total in USD.")
    status: OrderStatus = Field(description="Current order status.")
    created_at: str = Field(description="ISO 8601 timestamp the order was placed.")
    delivered_at: str | None = Field(
        default=None, description="ISO 8601 timestamp of delivery, null unless delivered."
    )
    payment_method_id: str = Field(description="Payment method used for this order.")
    damage_reported: bool = Field(
        default=False, description="Whether the customer reported item damage."
    )
    prior_refunds_12m: int = Field(
        default=0,
        description="Number of refunds this customer received in the trailing 12 months.",
    )


class RefundsDB(DB):
    """The refunds domain database: customers, products, orders."""

    customers: dict[str, Customer] = Field(description="Customers indexed by customer_id.")
    products: dict[str, Product] = Field(description="Products indexed by product_id.")
    orders: dict[str, Order] = Field(description="Orders indexed by order_id.")
