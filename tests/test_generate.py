"""Offline tests for LiveLessonExtractor (session-2 guide 4c.1: "Add a
unit test with a canned model response fixture (offline)"). Monkeypatches
change.generate.chat so no live call happens."""

from __future__ import annotations

import json

import pytest

import change.generate as generate_module
from change.contracts import (
    CanonicalAction,
    CanonicalOutcome,
    CanonicalState,
    ExperienceRecord,
    PolicyEval,
)
from change.generate import LiveLessonExtractor

STATE = CanonicalState("return", "delivered", "high", False, "neutral", "t0")


def _record(compliant: bool = True, task_success: bool = True, user_satisfied: bool = True) -> ExperienceRecord:
    return ExperienceRecord(
        run_id="r1",
        agent_id="a1",
        agent_version=1,
        memory_version=0,
        episode_id="e1",
        turn_idx=0,
        t_global=0,
        state=STATE,
        action=CanonicalAction.REFUND_FULL,
        outcome=CanonicalOutcome(
            policy_compliant=compliant, task_success=task_success, user_satisfied=user_satisfied
        ),
        policy_eval=PolicyEval(compliant=compliant, violated_rule_ids=[] if compliant else ["R1"]),
        reward=1.0 if task_success else 0.0,
        latency_ms=0.0,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
    )


def _fake_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _patch_chat(monkeypatch, content: str):
    calls = []

    def fake_chat(messages, **kwargs):
        calls.append(messages)
        return _fake_response(content)

    monkeypatch.setattr(generate_module, "chat", fake_chat)
    return calls


def test_unknown_feedback_rejected():
    with pytest.raises(ValueError):
        LiveLessonExtractor(feedback="bogus")


def test_empty_episode_records_returns_empty_without_calling_chat(monkeypatch):
    def fail_chat(*args, **kwargs):
        raise AssertionError("chat() should not be called for an empty episode")

    monkeypatch.setattr(generate_module, "chat", fail_chat)
    extractor = LiveLessonExtractor(feedback="truth")
    assert extractor.extract([], episode_id="e1", t_global=0) == []


def test_valid_lesson_with_full_condition_and_prescribed_action(monkeypatch):
    content = json.dumps(
        {
            "lessons": [
                {
                    "text": "Verify eligibility before a high-value refund.",
                    "condition": {
                        "task_type": "return",
                        "order_status": "delivered",
                        "value_bucket": "high",
                        "within_policy_window": False,
                        "user_stance": "neutral",
                        "prior_turns_bucket": "t0",
                    },
                    "prescribed_action": "deny",
                }
            ]
        }
    )
    _patch_chat(monkeypatch, content)
    extractor = LiveLessonExtractor(feedback="truth")
    lessons = extractor.extract([_record()], episode_id="e1", t_global=5)

    assert len(lessons) == 1
    lesson = lessons[0]
    assert lesson.text == "Verify eligibility before a high-value refund."
    assert lesson.condition_state_key == STATE.state_key
    assert lesson.prescribed_action == "deny"
    assert lesson.generosity == 0.0
    assert lesson.created_t == 5
    assert lesson.source_episode_id == "e1"
    assert extractor.n_parse_failures == 0


def test_null_condition_and_prescribed_action(monkeypatch):
    content = json.dumps({"lessons": [{"text": "General advice.", "condition": None, "prescribed_action": None}]})
    _patch_chat(monkeypatch, content)
    extractor = LiveLessonExtractor(feedback="satisfaction")
    lessons = extractor.extract([_record()], episode_id="e1", t_global=0)

    assert len(lessons) == 1
    assert lessons[0].condition_state_key is None
    assert lessons[0].prescribed_action is None
    assert extractor.n_parse_failures == 0


def test_malformed_json_dropped_and_counted(monkeypatch):
    _patch_chat(monkeypatch, "not json at all")
    extractor = LiveLessonExtractor(feedback="truth")
    lessons = extractor.extract([_record()], episode_id="e1", t_global=0)

    assert lessons == []
    assert extractor.n_parse_failures == 1


def test_one_bad_lesson_in_a_list_is_dropped_the_rest_kept(monkeypatch):
    content = json.dumps(
        {
            "lessons": [
                {"text": "Fine lesson.", "condition": None, "prescribed_action": None},
                {
                    "text": "Bad lesson.",
                    "condition": {"task_type": "return"},  # missing keys -- malformed
                    "prescribed_action": None,
                },
            ]
        }
    )
    _patch_chat(monkeypatch, content)
    extractor = LiveLessonExtractor(feedback="truth")
    lessons = extractor.extract([_record()], episode_id="e1", t_global=0)

    assert len(lessons) == 1
    assert lessons[0].text == "Fine lesson."
    assert extractor.n_parse_failures == 1


def test_bad_prescribed_action_drops_that_lesson(monkeypatch):
    content = json.dumps(
        {"lessons": [{"text": "x", "condition": None, "prescribed_action": "not_a_real_action"}]}
    )
    _patch_chat(monkeypatch, content)
    extractor = LiveLessonExtractor(feedback="truth")
    lessons = extractor.extract([_record()], episode_id="e1", t_global=0)

    assert lessons == []
    assert extractor.n_parse_failures == 1


def test_more_than_two_lessons_truncated_to_two(monkeypatch):
    raw = [{"text": f"lesson {i}", "condition": None, "prescribed_action": None} for i in range(5)]
    _patch_chat(monkeypatch, json.dumps({"lessons": raw}))
    extractor = LiveLessonExtractor(feedback="truth")
    lessons = extractor.extract([_record()], episode_id="e1", t_global=0)

    assert len(lessons) == 2


def test_feedback_source_selects_truth_vs_satisfaction_signal(monkeypatch):
    calls = _patch_chat(monkeypatch, json.dumps({"lessons": []}))

    truth_extractor = LiveLessonExtractor(feedback="truth")
    truth_extractor.extract(
        [_record(task_success=False, user_satisfied=True)], episode_id="e1", t_global=0
    )
    assert "negative" in calls[-1][1]["content"]

    satisfaction_extractor = LiveLessonExtractor(feedback="satisfaction")
    satisfaction_extractor.extract(
        [_record(task_success=False, user_satisfied=True)], episode_id="e1", t_global=0
    )
    assert "positive" in calls[-1][1]["content"]
