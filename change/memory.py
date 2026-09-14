"""Lesson memory with deterministic retrieval (guide 3.4)."""

from __future__ import annotations

from change.config import MEMORY_CAP
from change.contracts import CanonicalState, Lesson


class LessonMemory:
    def __init__(self, cap: int = MEMORY_CAP):
        self.cap = cap
        self._lessons: dict[str, Lesson] = {}
        self.version = 0

    def add(self, lesson: Lesson) -> None:
        self._lessons[lesson.lesson_id] = lesson
        while len(self._lessons) > self.cap:
            oldest_id = next(iter(self._lessons))
            del self._lessons[oldest_id]
        self.version += 1

    def remove(self, ids: list[str]) -> None:
        removed_any = False
        for lesson_id in ids:
            if lesson_id in self._lessons:
                del self._lessons[lesson_id]
                removed_any = True
        if removed_any:
            self.version += 1

    def snapshot_ids(self) -> list[str]:
        return list(self._lessons.keys())

    def retrieve(self, state: CanonicalState, k: int) -> list[Lesson]:
        """Exact state_key match first, then (task_type, within_policy_window)
        match, then most recent. Deterministic ordering throughout."""
        exact: list[Lesson] = []
        partial: list[Lesson] = []
        rest: list[Lesson] = []
        for lesson in self._lessons.values():
            key = lesson.condition_state_key
            if key == state.state_key:
                exact.append(lesson)
            elif key is not None:
                parts = key.split("|")
                if (
                    parts[0] == state.task_type
                    and bool(int(parts[3])) == state.within_policy_window
                ):
                    partial.append(lesson)
                else:
                    rest.append(lesson)
            else:
                rest.append(lesson)

        exact.sort(key=lambda lesson: lesson.created_t, reverse=True)
        partial.sort(key=lambda lesson: lesson.created_t, reverse=True)
        rest.sort(key=lambda lesson: lesson.created_t, reverse=True)
        return (exact + partial + rest)[:k]
