"""Env/Agent protocol shared by the mock and tau2 environments (guide 3.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from change.contracts import CanonicalAction, CanonicalOutcome, ExperienceRecord, PolicyEval


@dataclass
class ActionChoice:
    action: CanonicalAction
    tools_used: list[str] = field(default_factory=list)
    lessons_in_context: list[str] = field(default_factory=list)


@dataclass
class EpisodeResult:
    records: list[ExperienceRecord]
    reward: float


@runtime_checkable
class Agent(Protocol):
    """An agent under governance. Implementations own their own memory."""

    agent_id: str
    agent_version: int
    memory_version: int

    def act(self, obs: dict) -> ActionChoice:
        """obs contains at least: state (CanonicalState), turn_idx (int)."""
        ...

    def observe_outcome(
        self, action: CanonicalAction, outcome: CanonicalOutcome, policy_eval: PolicyEval
    ) -> None: ...


@runtime_checkable
class Env(Protocol):
    def task_ids(self) -> list[str]: ...

    def run_episode(self, task_id: str, agent: Agent, seed: int) -> EpisodeResult: ...
