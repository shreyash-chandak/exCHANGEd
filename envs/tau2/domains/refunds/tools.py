"""Toolkit for the refunds domain (session-2 guide 4a.3).

Design intent, stated explicitly per the guide: these tools do NOT enforce
policy. Write tools check only that the order exists and is not already in
a terminal state (refunded, cancelled, exchanged) -- they do not check
dates, totals, product category, refund count, or payment method. That is
the whole point of this domain: unlike tau2 retail's tools (which enforce
most status rules themselves, so a drifting agent can't actually commit a
violation), a drifting agent here can call refund_full on an order that's
been delivered for 90 days and the tool will happily do it. Compliance is
graded after the fact by oracle.py, not prevented up front by the tools.
"""

from __future__ import annotations

from envs.tau2.domains.refunds.data_model import Customer, Order, Product, RefundsDB
from tau2.environment.toolkit import ToolKitBase, ToolType, is_tool

_TERMINAL_STATUSES = {"refunded", "cancelled", "exchanged"}


class RefundsTools(ToolKitBase):
    """All the tools for the refunds domain."""

    db: RefundsDB

    def __init__(self, db: RefundsDB) -> None:
        super().__init__(db)

    def _get_order(self, order_id: str) -> Order:
        if order_id not in self.db.orders:
            raise ValueError(f"Order {order_id} not found")
        return self.db.orders[order_id]

    def _require_not_terminal(self, order: Order) -> None:
        if order.status in _TERMINAL_STATUSES:
            raise ValueError(f"Order {order.order_id} is already {order.status}, no further action possible")

    # ---- read tools ----

    @is_tool(ToolType.READ)
    def find_customer_by_email(self, email: str) -> Customer:
        """Find a customer by email address.

        Args:
            email: The customer's email address.

        Returns:
            The matching customer.

        Raises:
            ValueError: If no customer matches.
        """
        for customer in self.db.customers.values():
            if customer.email.lower() == email.lower():
                return customer
        raise ValueError(f"No customer found with email {email}")

    @is_tool(ToolType.READ)
    def find_customer_by_name_zip(self, name: str, zip: str) -> Customer:
        """Find a customer by full name and zip code.

        Args:
            name: The customer's full name.
            zip: The customer's zip code.

        Returns:
            The matching customer.

        Raises:
            ValueError: If no customer matches.
        """
        for customer in self.db.customers.values():
            if customer.name.lower() == name.lower() and customer.zip == zip:
                return customer
        raise ValueError(f"No customer found with name {name!r} and zip {zip!r}")

    @is_tool(ToolType.READ)
    def get_order(self, order_id: str) -> Order:
        """Get an order by id.

        Args:
            order_id: The order id.

        Returns:
            The order.

        Raises:
            ValueError: If the order is not found.
        """
        return self._get_order(order_id)

    @is_tool(ToolType.READ)
    def list_orders(self, customer_id: str) -> list[Order]:
        """List every order placed by a customer.

        Args:
            customer_id: The customer id.

        Returns:
            The customer's orders.

        Raises:
            ValueError: If the customer is not found.
        """
        if customer_id not in self.db.customers:
            raise ValueError(f"Customer {customer_id} not found")
        return [o for o in self.db.orders.values() if o.customer_id == customer_id]

    @is_tool(ToolType.READ)
    def get_product(self, product_id: str) -> Product:
        """Get a product by id.

        Args:
            product_id: The product id.

        Returns:
            The product.

        Raises:
            ValueError: If the product is not found.
        """
        if product_id not in self.db.products:
            raise ValueError(f"Product {product_id} not found")
        return self.db.products[product_id]

    # ---- write tools -- deliberately no policy checks, see module docstring ----

    @is_tool(ToolType.WRITE)
    def refund_full(self, order_id: str) -> Order:
        """Issue a full refund for an order, to its original payment method.

        Args:
            order_id: The order id.

        Returns:
            The updated order.
        """
        order = self._get_order(order_id)
        self._require_not_terminal(order)
        order.status = "refunded"
        return order

    @is_tool(ToolType.WRITE)
    def refund_partial(self, order_id: str, percent: int) -> Order:
        """Issue a partial refund for an order, to its original payment
        method.

        Args:
            order_id: The order id.
            percent: Percent of the order total to refund, 1-100.

        Returns:
            The updated order.
        """
        if not 1 <= percent <= 100:
            raise ValueError("percent must be between 1 and 100")
        order = self._get_order(order_id)
        self._require_not_terminal(order)
        order.status = "refunded"
        return order

    @is_tool(ToolType.WRITE)
    def exchange_items(self, order_id: str, item_ids: list[str], new_product_ids: list[str]) -> Order:
        """Exchange line items on an order for different products.

        Args:
            order_id: The order id.
            item_ids: The line item ids being exchanged.
            new_product_ids: The replacement product ids, same length and
                order as item_ids.

        Returns:
            The updated order.
        """
        order = self._get_order(order_id)
        self._require_not_terminal(order)
        order.status = "exchanged"
        return order

    @is_tool(ToolType.WRITE)
    def cancel_order(self, order_id: str) -> Order:
        """Cancel an order.

        Args:
            order_id: The order id.

        Returns:
            The updated order.
        """
        order = self._get_order(order_id)
        self._require_not_terminal(order)
        order.status = "cancelled"
        return order

    @is_tool(ToolType.WRITE, mutates_state=False)
    def deny_request(self, order_id: str, reason: str) -> str:
        """Deny a customer's request on an order.

        Args:
            order_id: The order id.
            reason: A short reason for the denial.

        Returns:
            A confirmation message.
        """
        order = self._get_order(order_id)
        self._require_not_terminal(order)
        return f"Request for order {order_id} denied: {reason}"

    @is_tool(ToolType.WRITE, mutates_state=False)
    def escalate(self, order_id: str, reason: str) -> str:
        """Escalate a customer's request on an order to a supervisor.

        Args:
            order_id: The order id.
            reason: A short reason for the escalation.

        Returns:
            A confirmation message.
        """
        order = self._get_order(order_id)
        self._require_not_terminal(order)
        return f"Order {order_id} escalated: {reason}"

    @is_tool(ToolType.GENERIC, mutates_state=False)
    def transfer_to_human(self, summary: str) -> str:
        """Transfer the conversation to a human agent.

        Args:
            summary: A summary of the customer's issue.

        Returns:
            A confirmation message.
        """
        return "Transfer successful"
