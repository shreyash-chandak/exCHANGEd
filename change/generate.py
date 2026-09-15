"""Lesson extraction / candidate generation (Generate). Mock extractor is
guide 3.5; LiveLessonExtractor and CandidateGenerator land in phases 4 and 7.
"""

from __future__ import annotations

from typing import Literal
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
)
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


class LiveLessonExtractor:
    """Implemented in phase 4 — calls a real LLM to propose lessons."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("LiveLessonExtractor is implemented in phase 4")


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
