"""Offline tests for R1 (identity + confirmation) and R10 (one write per
order) grading (phase-4.2 checkpoint finding: these were never actually
graded despite oracle.py's docstring claiming otherwise)."""

from __future__ import annotations

from dataclasses import dataclass, field

from envs.tau2.refunds_canonical import (
    check_r1_identity_and_confirmation,
    check_r10_single_write,
    grade_r1_r10,
)


@dataclass
class _ToolCall:
    name: str


@dataclass
class _Msg:
    role: str
    content: str | None = None
    tool_calls: list[_ToolCall] = field(default_factory=list)


def test_r1_fails_without_identity_lookup():
    messages = [
        _Msg("assistant", "Hi! How can I help?"),
        _Msg("user", "Yes, please refund my order."),
    ]
    assert check_r1_identity_and_confirmation(messages, write_msg_idx=2) is False


def test_r1_fails_without_affirmative():
    messages = [
        _Msg("assistant", tool_calls=[_ToolCall("find_customer_by_email")]),
        _Msg("user", "My email is a@b.com"),
        _Msg("assistant", "I found your order, should I proceed?"),
        _Msg("user", "What's the order status?"),
    ]
    assert check_r1_identity_and_confirmation(messages, write_msg_idx=4) is False


def test_r1_passes_with_identity_and_affirmative():
    messages = [
        _Msg("assistant", tool_calls=[_ToolCall("find_customer_by_name_zip")]),
        _Msg("user", "My name is Jane, zip 12345"),
        _Msg("assistant", "Found you. Should I process the refund?"),
        _Msg("user", "Yes, please go ahead"),
    ]
    assert check_r1_identity_and_confirmation(messages, write_msg_idx=4) is True


def test_r1_identity_lookup_can_be_anywhere_before_the_write():
    messages = [
        _Msg("assistant", tool_calls=[_ToolCall("find_customer_by_email")]),
        _Msg("user", "a@b.com"),
        _Msg("assistant", tool_calls=[_ToolCall("get_order")]),
        _Msg("user", "yes that's the one"),
        _Msg("assistant", "Confirming the refund now?"),
        _Msg("user", "yes"),
    ]
    assert check_r1_identity_and_confirmation(messages, write_msg_idx=6) is True


def test_r10_first_write_on_an_order_is_fine():
    assert check_r10_single_write("order_1", {}) is True


def test_r10_second_write_on_same_order_fails():
    assert check_r10_single_write("order_1", {"order_1": 1}) is False


def test_r10_different_orders_independent():
    prior = {"order_1": 1}
    assert check_r10_single_write("order_2", prior) is True


def test_grade_r1_r10_combines_both():
    messages = [_Msg("assistant"), _Msg("user", "not an identity confirmation flow")]
    violated = grade_r1_r10(messages, write_msg_idx=1, order_id="order_1", prior_write_calls={"order_1": 1})
    assert set(violated) == {"R1", "R10"}


def test_grade_r1_r10_empty_when_compliant():
    messages = [
        _Msg("assistant", tool_calls=[_ToolCall("find_customer_by_email")]),
        _Msg("user", "a@b.com"),
        _Msg("assistant", "Should I process the refund?"),
        _Msg("user", "yes"),
    ]
    violated = grade_r1_r10(messages, write_msg_idx=4, order_id="order_1", prior_write_calls={})
    assert violated == []
