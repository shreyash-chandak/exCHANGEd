"""Offline tests for LessonAgent's pure logic (gate matching, lesson
injection into the system prompt) -- no tau2 orchestrator/live model
call needed for these, since `_gate_applies` and `_system_prompt` don't
touch either."""

from __future__ import annotations

from change.contracts import CanonicalState, Lesson
from change.memory import LessonMemory
from envs.tau2.lesson_agent import LESSONS_HEADER, LessonAgent

STATE_HIGH_OUTSIDE = CanonicalState("return", "delivered", "high", False, "neutral", "t0")
STATE_LOW_OUTSIDE = CanonicalState("return", "delivered", "low", False, "neutral", "t0")
STATE_HIGH_INSIDE = CanonicalState("return", "delivered", "high", True, "neutral", "t0")


def _make_agent(memory=None, gates=None, state=STATE_HIGH_OUTSIDE):
    return LessonAgent(
        tools=[],
        domain_policy="policy text",
        llm="fake-model",
        llm_args={},
        memory=memory or LessonMemory(),
        gates=gates or {},
        state_fn=lambda ptb: state,
        escalate_tool="escalate",
        escalate_args_fn=lambda: {"order_id": "o1", "reason": "gate"},
    )


def test_gate_applies_matches_value_bucket_and_window():
    gates = {"approval_gate": {"value_bucket": "high", "require_escalate_when_outside_window": True}}
    agent = _make_agent(gates=gates, state=STATE_HIGH_OUTSIDE)
    assert agent._gate_applies(STATE_HIGH_OUTSIDE) is True


def test_gate_does_not_apply_when_within_window():
    gates = {"approval_gate": {"value_bucket": "high", "require_escalate_when_outside_window": True}}
    agent = _make_agent(gates=gates)
    assert agent._gate_applies(STATE_HIGH_INSIDE) is False


def test_gate_does_not_apply_for_different_value_bucket():
    gates = {"approval_gate": {"value_bucket": "high", "require_escalate_when_outside_window": True}}
    agent = _make_agent(gates=gates)
    assert agent._gate_applies(STATE_LOW_OUTSIDE) is False


def test_no_gate_configured_never_applies():
    agent = _make_agent(gates={})
    assert agent._gate_applies(STATE_HIGH_OUTSIDE) is False


def test_system_prompt_includes_lessons_header_only_when_lessons_present():
    agent = _make_agent()
    assert LESSONS_HEADER not in agent._system_prompt("")
    prompt = agent._system_prompt("- do the thing")
    assert LESSONS_HEADER in prompt
    assert "- do the thing" in prompt


def test_generate_next_message_forces_escalate_without_model_call(monkeypatch):
    import envs.tau2.lesson_agent as lesson_agent_module

    def fail_generate(*args, **kwargs):
        raise AssertionError("generate() should not be called when the gate applies")

    monkeypatch.setattr(lesson_agent_module, "generate", fail_generate)

    gates = {"approval_gate": {"value_bucket": "high", "require_escalate_when_outside_window": True}}
    agent = _make_agent(gates=gates, state=STATE_HIGH_OUTSIDE)
    state = agent.get_init_state()

    from tau2.data_model.message import UserMessage

    assistant_message, _ = agent.generate_next_message(
        UserMessage(role="user", content="please refund"), state
    )
    assert assistant_message.tool_calls[0].name == "escalate"
    assert assistant_message.tool_calls[0].arguments == {"order_id": "o1", "reason": "gate"}
    assert agent.lessons_in_context_by_turn == [[]]


def test_generate_next_message_tracks_retrieved_lesson_ids(monkeypatch):
    import envs.tau2.lesson_agent as lesson_agent_module
    from tau2.data_model.message import AssistantMessage, UserMessage

    memory = LessonMemory()
    lesson = Lesson(
        lesson_id="l1",
        text="Be careful.",
        created_t=0,
        source_episode_id="e1",
        condition_state_key=STATE_HIGH_OUTSIDE.state_key,
        prescribed_action="deny",
        generosity=0.0,
    )
    memory.add(lesson)

    captured_messages = {}

    def fake_generate(model, tools, messages, call_name, **kwargs):
        captured_messages["messages"] = messages
        return AssistantMessage(role="assistant", content="ok")

    monkeypatch.setattr(lesson_agent_module, "generate", fake_generate)

    agent = _make_agent(memory=memory, gates={}, state=STATE_HIGH_OUTSIDE)
    state = agent.get_init_state()
    agent.generate_next_message(UserMessage(role="user", content="hi"), state)

    assert agent.lessons_in_context_by_turn == [["l1"]]
    system_content = captured_messages["messages"][0].content
    assert "Be careful." in system_content
