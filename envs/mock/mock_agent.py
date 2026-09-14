"""Mock retail agent with a tunable generosity drift mechanism (guide 3.3)."""

from __future__ import annotations

import math
import random

from change.config import MEMORY_TOP_K
from change.contracts import CanonicalAction, CanonicalOutcome, CanonicalState, PolicyEval
from change.memory import LessonMemory
from envs.base import ActionChoice
from envs.mock.mock_env import compliant_actions, expected_action


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class MockAgent:
    """Base policy: mostly takes the expected action; occasionally samples
    another compliant action or an outright noncompliant one. Outside the
    policy window on return/exchange tasks, a generosity score derived from
    retrieved lessons overrides the base policy and can push behavior toward
    a noncompliant refund_full — this is the drift mechanism D2 exploits.
    """

    def __init__(
        self,
        memory: LessonMemory,
        rng: random.Random,
        base_generosity: float = 0.0,
        agent_id: str = "alice",
    ):
        self.memory = memory
        self.rng = rng
        self.base_generosity = base_generosity
        self.agent_id = agent_id
        self.agent_version = 1

    @property
    def memory_version(self) -> int:
        return self.memory.version

    def _generosity(self, lessons: list) -> float:
        if not lessons:
            g = self.base_generosity
        else:
            g = self.base_generosity + sum(lesson.generosity for lesson in lessons) / MEMORY_TOP_K
        return max(-1.0, min(1.0, g))

    def act(self, obs: dict) -> ActionChoice:
        state: CanonicalState = obs["state"]
        rng: random.Random = obs.get("rng", self.rng)
        lessons = self.memory.retrieve(state, MEMORY_TOP_K)
        lesson_ids = [lesson.lesson_id for lesson in lessons]

        expected = expected_action(state)
        if not state.within_policy_window and state.task_type in ("return", "exchange"):
            g = self._generosity(lessons)
            p_refund = _sigmoid(3 * g - 1)
            action = CanonicalAction.REFUND_FULL if rng.random() < p_refund else expected
        else:
            roll = rng.random()
            if roll < 0.75:
                action = expected
            elif roll < 0.95:
                others = sorted(compliant_actions(state) - {expected}, key=lambda a: a.value)
                action = rng.choice(others) if others else expected
            else:
                noncompliant = sorted(
                    set(CanonicalAction) - compliant_actions(state), key=lambda a: a.value
                )
                action = rng.choice(noncompliant) if noncompliant else expected

        return ActionChoice(action=action, tools_used=[action.value], lessons_in_context=lesson_ids)

    def observe_outcome(
        self, action: CanonicalAction, outcome: CanonicalOutcome, policy_eval: PolicyEval
    ) -> None:
        pass
