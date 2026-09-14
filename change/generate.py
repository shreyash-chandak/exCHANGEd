"""Lesson extraction / candidate generation (Generate). Mock extractor is
guide 3.5; LiveLessonExtractor and CandidateGenerator land in phases 4 and 7.
"""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from change.contracts import CanonicalAction, ExperienceRecord, Lesson

FeedbackSource = Literal["truth", "satisfaction"]

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
