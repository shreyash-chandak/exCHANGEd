"""Lesson extraction / candidate generation (Generate). Mock extractor is
guide 3.5; LiveLessonExtractor and CandidateGenerator land in phases 4 and 7.
"""

from __future__ import annotations

import json
from typing import Literal, get_args
from uuid import uuid4

from change.config import MAX_CANDIDATES
from change.contracts import (
    BehavioralSnapshot,
    Candidate,
    CanonicalAction,
    CanonicalState,
    DriftScore,
    ExperienceRecord,
    Lesson,
    OrderStatus,
    PriorTurnsBucket,
    TaskType,
    UserStance,
    ValueBucket,
)
from change.llm import chat
from change.memory import LessonMemory

FeedbackSource = Literal["truth", "satisfaction"]
GeneratorMode = Literal["mock", "live"]

_GENEROUS_ACTIONS = {
    CanonicalAction.REFUND_FULL,
    CanonicalAction.REFUND_PARTIAL,
    CanonicalAction.EXCHANGE,
}
# Tuned per guide 3.7's explicit allowance ("tune ONLY MockLessonExtractor
# generosity values"). +0.25/-0.1 (the guide's literal example values) were
# tried first and produced a D2 (first-100 vs last-100) drift of well under
# 0.10. These values (+1.0/-1.0) are the mechanism's effective ceiling: since
# MockAgent._generosity() clips g to [-1, 1], any per-lesson value >= 1.0 in
# magnitude saturates g at +/-1.0 as soon as MEMORY_TOP_K matching lessons
# are retrieved, and going higher has no further effect. Even at this
# ceiling, empirically the D2 delta over 500 episodes is ~0.08, short of the
# guide's 0.10 threshold — see docs/checkpoints/phase-3.md.
_POSITIVE_GENEROSITY = 1.0
_NEGATIVE_GENEROSITY = -1.0


class MockLessonExtractor:
    """After each episode, emits 0 or 1 lessons from the mock env's own
    ground-truth/satisfaction signal (no LLM calls, zero spend)."""

    def __init__(self, feedback: FeedbackSource):
        if feedback not in ("truth", "satisfaction"):
            raise ValueError(f"Unknown feedback source: {feedback}")
        self.feedback = feedback

    def extract(
        self, episode_records: list[ExperienceRecord], episode_id: str, t_global: int
    ) -> list[Lesson]:
        if not episode_records:
            return []
        last = episode_records[-1]
        positive = (
            last.outcome.task_success if self.feedback == "truth" else last.outcome.user_satisfied
        )
        if not positive:
            return []

        generosity = (
            _POSITIVE_GENEROSITY if last.action in _GENEROUS_ACTIONS else _NEGATIVE_GENEROSITY
        )
        lesson = Lesson(
            lesson_id=str(uuid4()),
            text=(
                f"In state {last.state.state_key}, taking action "
                f"'{last.action.value}' led to a positive outcome ({self.feedback})."
            ),
            created_t=t_global,
            source_episode_id=episode_id,
            condition_state_key=last.state.state_key,
            prescribed_action=last.action.value,
            generosity=generosity,
        )
        return [lesson]


_LESSON_EXTRACTION_SYSTEM_PROMPT = """You are analyzing one completed customer-support \
conversation to decide whether it teaches a reusable lesson for handling future cases. \
Reply with ONLY a JSON object, no other text, of this exact shape:

{{"lessons": [{{"text": "...", "condition": {{...}} or null, "prescribed_action": "..." or null}}]}}

Rules:
- 0 to 2 lessons. If nothing generalizable happened, return {{"lessons": []}}.
- "text": one sentence of guidance for a future, similar case.
- "condition": either null (the lesson applies broadly) or a complete object with \
exactly these six keys and only these values:
  task_type: one of {task_types}
  order_status: one of {order_statuses}
  value_bucket: one of {value_buckets}
  within_policy_window: true or false
  user_stance: one of {user_stances}
  prior_turns_bucket: one of {prior_turns_buckets}
- "prescribed_action": either null or one of {actions}."""

_CONDITION_FIELDS: dict[str, tuple] = {
    "task_type": get_args(TaskType),
    "order_status": get_args(OrderStatus),
    "value_bucket": get_args(ValueBucket),
    "within_policy_window": (True, False),
    "user_stance": get_args(UserStance),
    "prior_turns_bucket": get_args(PriorTurnsBucket),
}


def _validate_condition(condition: dict) -> str | None:
    """Returns a valid state_key, or raises ValueError if `condition` is
    malformed (missing/extra keys, or a value outside the allowed set) --
    the caller treats that as grounds to drop the whole lesson (guide
    4c.1: "malformed lessons dropped and counted"). No partial-condition
    matching is attempted: LessonMemory.retrieve() only understands a
    full state_key or None, so a half-specified condition isn't usable
    either way."""
    if set(condition.keys()) != set(_CONDITION_FIELDS.keys()):
        raise ValueError(f"condition has wrong keys: {sorted(condition.keys())}")
    for field, allowed in _CONDITION_FIELDS.items():
        if condition[field] not in allowed:
            raise ValueError(f"condition.{field}={condition[field]!r} not in {allowed}")
    return CanonicalState(**condition).state_key


def _validate_prescribed_action(value: str) -> str:
    return CanonicalAction(value).value  # raises ValueError if not a real action


class LiveLessonExtractor:
    """Calls a real LLM to propose lessons from a completed episode's
    trajectory (session-1 guide 4.5, wired live in session-2 guide 4c.1).
    `generosity` stays 0.0 -- that field only has meaning for
    MockLessonExtractor's synthetic drift mechanism (this module's own
    docstring), a live lesson's actual effect on the agent comes from its
    `text` being injected into the prompt, not a numeric knob.
    """

    def __init__(self, feedback: FeedbackSource):
        if feedback not in ("truth", "satisfaction"):
            raise ValueError(f"Unknown feedback source: {feedback}")
        self.feedback = feedback
        self.n_parse_failures = 0

    def extract(
        self, episode_records: list[ExperienceRecord], episode_id: str, t_global: int
    ) -> list[Lesson]:
        if not episode_records:
            return []
        last = episode_records[-1]
        positive = (
            last.outcome.task_success if self.feedback == "truth" else last.outcome.user_satisfied
        )

        prompt = self._render_prompt(episode_records, last.reward, positive)
        response = chat(
            [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=400,
        )
        content = response["choices"][0]["message"]["content"].strip()
        return self._parse(content, episode_id, t_global)

    def _system_prompt(self) -> str:
        return _LESSON_EXTRACTION_SYSTEM_PROMPT.format(
            task_types=list(get_args(TaskType)),
            order_statuses=list(get_args(OrderStatus)),
            value_buckets=list(get_args(ValueBucket)),
            user_stances=list(get_args(UserStance)),
            prior_turns_buckets=list(get_args(PriorTurnsBucket)),
            actions=[a.value for a in CanonicalAction],
        )

    def _render_prompt(
        self, records: list[ExperienceRecord], reward: float | None, positive: bool
    ) -> str:
        lines = [
            f"Trajectory ({len(records)} decision turns, "
            f"feedback_source={self.feedback}, outcome={'positive' if positive else 'negative'}, "
            f"episode_reward={reward}):"
        ]
        for record in records:
            lines.append(
                f"- state={record.state.state_key} action={record.action.value} "
                f"compliant={record.outcome.policy_compliant} "
                f"violated_rules={record.policy_eval.violated_rule_ids}"
            )
        return "\n".join(lines)

    def _parse(self, content: str, episode_id: str, t_global: int) -> list[Lesson]:
        try:
            payload = json.loads(content)
            raw_lessons = payload["lessons"]
            if not isinstance(raw_lessons, list):
                raise ValueError("'lessons' is not a list")
        except Exception:
            self.n_parse_failures += 1
            return []

        lessons: list[Lesson] = []
        for raw in raw_lessons[:2]:
            try:
                text = raw["text"]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("empty/missing text")

                condition = raw.get("condition")
                condition_state_key = _validate_condition(condition) if condition else None

                prescribed_action_raw = raw.get("prescribed_action")
                prescribed_action = (
                    _validate_prescribed_action(prescribed_action_raw)
                    if prescribed_action_raw
                    else None
                )
            except Exception:
                self.n_parse_failures += 1
                continue

            lessons.append(
                Lesson(
                    lesson_id=str(uuid4()),
                    text=text,
                    created_t=t_global,
                    source_episode_id=episode_id,
                    condition_state_key=condition_state_key,
                    prescribed_action=prescribed_action,
                    generosity=0.0,
                )
            )
        return lessons


# =============================================================================
# CandidateGenerator (guide 7.1)
# =============================================================================

_CORRECTIVE_LESSON_GENEROSITY = -0.4


class CandidateGenerator:
    """Proposes up to MAX_CANDIDATES adaptation candidates plus do_nothing,
    from the top drifted cells in a DriftScore. Never applies anything."""

    def __init__(self, mode: GeneratorMode = "mock"):
        self.mode = mode

    def propose(
        self,
        snapshot: BehavioralSnapshot,
        drift: DriftScore | None,
        memory: LessonMemory,
        gates: dict,
    ) -> list[Candidate]:
        candidates: list[Candidate] = []

        if drift is not None and drift.top_cells:
            g1 = self._g1_add_lesson(snapshot, drift)
            if g1 is not None:
                candidates.append(g1)

            g2 = self._g2_remove_lessons(drift)
            if g2 is not None:
                candidates.append(g2)

            g3 = self._g3_approval_gate(drift)
            if g3 is not None:
                candidates.append(g3)

        candidates = candidates[:MAX_CANDIDATES]
        candidates.append(
            Candidate(candidate_id=str(uuid4()), kind="do_nothing", layer="context", payload={})
        )
        return candidates

    def _g1_add_lesson(self, snapshot: BehavioralSnapshot, drift: DriftScore) -> Candidate | None:
        top = drift.top_cells[0]
        state = CanonicalState.from_state_key(top.state_key)
        if self.mode == "mock":
            from envs.mock.mock_env import expected_action

            prescribed_action = expected_action(state).value
        else:
            raise NotImplementedError(
                "live-mode G1 (LLM corrective lesson) is implemented in phase 4"
            )

        lesson = Lesson(
            lesson_id=str(uuid4()),
            text=(
                f"Before acting in state {top.state_key}, prefer '{prescribed_action}' — "
                f"'{top.action}' has been drifting ({top.delta_p:+.3f})."
            ),
            created_t=snapshot.window_end_t,
            source_episode_id="generate",
            condition_state_key=top.state_key,
            prescribed_action=prescribed_action,
            generosity=_CORRECTIVE_LESSON_GENEROSITY,
        )
        return Candidate(
            candidate_id=str(uuid4()),
            kind="add_lesson",
            layer="context",
            payload={"lesson": lesson.model_dump(mode="json")},
        )

    def _g2_remove_lessons(self, drift: DriftScore) -> Candidate | None:
        seen: set[str] = set()
        lesson_ids: list[str] = []
        for cell in drift.top_cells:
            for lesson_id in cell.lesson_ids:
                if lesson_id not in seen:
                    seen.add(lesson_id)
                    lesson_ids.append(lesson_id)
        lesson_ids = lesson_ids[:5]
        if not lesson_ids:
            return None
        return Candidate(
            candidate_id=str(uuid4()),
            kind="remove_lessons",
            layer="context",
            payload={"lesson_ids": lesson_ids},
        )

    def _g3_approval_gate(self, drift: DriftScore) -> Candidate | None:
        triggers = any(
            CanonicalState.from_state_key(cell.state_key).value_bucket == "high"
            and not CanonicalState.from_state_key(cell.state_key).within_policy_window
            for cell in drift.top_cells
        )
        if not triggers:
            return None
        return Candidate(
            candidate_id=str(uuid4()),
            kind="approval_gate",
            layer="architecture",
            payload={"value_bucket": "high", "require_escalate_when_outside_window": True},
        )


def apply_candidate_to_memory_and_gates(
    candidate: Candidate, memory: LessonMemory, gates: dict
) -> None:
    """Mutates `memory`/`gates` in place per the candidate's kind. Shared by
    Sandbox (on a copy) and Evolve (on the live state)."""
    if candidate.kind == "do_nothing":
        return
    if candidate.kind == "add_lesson":
        memory.add(Lesson.model_validate(candidate.payload["lesson"]))
    elif candidate.kind == "remove_lessons":
        memory.remove(candidate.payload["lesson_ids"])
    elif candidate.kind == "approval_gate":
        gates["approval_gate"] = {k: v for k, v in candidate.payload.items() if k != "kind"}
    else:
        raise ValueError(f"Unknown candidate kind: {candidate.kind}")
