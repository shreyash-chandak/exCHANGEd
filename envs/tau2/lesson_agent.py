"""Memory-injecting tau2 agent (session-1 guide 4.3, wired live in
session-2 guide 4c.2). Constructed directly (not via
`tau2.registry.registry`'s string-keyed agent factories) and passed
straight into a manually-built `Orchestrator` -- `build_agent`'s factory
signature only forwards a fixed kwarg set (tools, domain_policy, llm,
llm_args, task, ...), with no room for our own `LessonMemory`/gates
objects, so this follows the alternative tau2_interfaces.md item 2
flagged as option (b): construct the orchestrator's pieces directly
(same pattern `tau2.runner.simulation.run_simulation`'s own docstring
demonstrates), never touching the registry at all.

Per turn: build the caller-supplied `CanonicalState`, retrieve
MEMORY_TOP_K lessons from `memory`, inject them into the system prompt
under a fixed "## Lessons from experience" header, call the model, and
record which lesson_ids were shown (`lessons_in_context_by_turn`, read
by the caller after the episode to populate `ExperienceRecord.
lessons_in_context`). If `gates["approval_gate"]` is set and the
current state matches its criteria, the turn is forced to the caller's
escalate tool without a model call at all.
"""

from __future__ import annotations

from typing import Callable, Optional

from tau2.agent.base.llm_config import LLMConfigMixin
from tau2.agent.base_agent import (
    HalfDuplexAgent,
    ValidAgentInputMessage,
    is_valid_agent_history_message,
)
from tau2.agent.llm_agent import AGENT_INSTRUCTION, SYSTEM_PROMPT, LLMAgentState
from tau2.data_model.message import (
    AssistantMessage,
    Message,
    MultiToolMessage,
    SystemMessage,
    ToolCall,
)
from tau2.environment.tool import Tool
from tau2.utils.llm_utils import generate

from change.config import MEMORY_TOP_K
from change.contracts import CanonicalState, PriorTurnsBucket
from change.memory import LessonMemory

LESSONS_HEADER = "## Lessons from experience"


def _advance_prior_turns(bucket: PriorTurnsBucket) -> PriorTurnsBucket:
    """Same rule as envs/tau2/adapter.py's helper -- kept as a tiny local
    copy rather than importing from adapter.py, which would create a
    circular import (adapter.py constructs LessonAgent instances)."""
    if bucket == "t0":
        return "t1to3"
    return "t4plus"


class LessonAgent(LLMConfigMixin, HalfDuplexAgent[LLMAgentState]):
    def __init__(
        self,
        tools: list[Tool],
        domain_policy: str,
        llm: str,
        llm_args: Optional[dict],
        memory: LessonMemory,
        gates: dict,
        state_fn: Callable[[PriorTurnsBucket], CanonicalState],
        escalate_tool: str,
        escalate_args_fn: Callable[[], dict],
        top_k: int = MEMORY_TOP_K,
    ):
        super().__init__(tools=tools, domain_policy=domain_policy, llm=llm, llm_args=llm_args)
        self.memory = memory
        self.gates = gates
        self.state_fn = state_fn
        self.escalate_tool = escalate_tool
        self.escalate_args_fn = escalate_args_fn
        self.top_k = top_k
        self.prior_turns_bucket: PriorTurnsBucket = "t0"
        # Parallel to the eventual per-turn ExperienceRecord list (one
        # entry per assistant turn, in generation order) -- the caller
        # zips this against `sim.get_messages()`'s assistant turns after
        # the episode, same indexing as `states_by_turn`.
        self.lessons_in_context_by_turn: list[list[str]] = []
        self.states_by_turn: list[CanonicalState] = []

    def _system_prompt(self, lessons_text: str) -> str:
        base = SYSTEM_PROMPT.format(
            domain_policy=self.domain_policy, agent_instruction=AGENT_INSTRUCTION
        )
        if not lessons_text:
            return base
        return f"{base}\n\n{LESSONS_HEADER}\n{lessons_text}"

    def get_init_state(self, message_history: Optional[list[Message]] = None) -> LLMAgentState:
        if message_history is None:
            message_history = []
        assert all(is_valid_agent_history_message(m) for m in message_history), (
            "Message history must contain only AssistantMessage, UserMessage, or "
            "ToolMessage to Agent."
        )
        # Placeholder -- generate_next_message rebuilds system_messages
        # fresh every turn with that turn's retrieved lessons.
        return LLMAgentState(
            system_messages=[SystemMessage(role="system", content=self._system_prompt(""))],
            messages=message_history,
        )

    def _gate_applies(self, state: CanonicalState) -> bool:
        gate = self.gates.get("approval_gate")
        if not gate:
            return False
        if "value_bucket" in gate and state.value_bucket != gate["value_bucket"]:
            return False
        if gate.get("require_escalate_when_outside_window") and state.within_policy_window:
            return False
        return True

    def generate_next_message(
        self, message: ValidAgentInputMessage, state: LLMAgentState
    ) -> tuple[AssistantMessage, LLMAgentState]:
        canonical_state = self.state_fn(self.prior_turns_bucket)
        lessons = self.memory.retrieve(canonical_state, self.top_k)
        lessons_text = "\n".join(f"- {lesson.text}" for lesson in lessons)
        state.system_messages = [
            SystemMessage(role="system", content=self._system_prompt(lessons_text))
        ]

        if isinstance(message, MultiToolMessage):
            state.messages.extend(message.tool_messages)
        else:
            state.messages.append(message)

        if self._gate_applies(canonical_state):
            assistant_message = AssistantMessage(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        id=f"gate-{len(self.lessons_in_context_by_turn)}",
                        name=self.escalate_tool,
                        arguments=self.escalate_args_fn(),
                    )
                ],
            )
        else:
            messages = state.system_messages + state.messages
            assistant_message = generate(
                model=self.llm,
                tools=self.tools,
                messages=messages,
                call_name="lesson_agent_response",
                **self.llm_args,
            )

        state.messages.append(assistant_message)
        self.lessons_in_context_by_turn.append([lesson.lesson_id for lesson in lessons])
        self.states_by_turn.append(canonical_state)
        self.prior_turns_bucket = _advance_prior_turns(self.prior_turns_bucket)
        return assistant_message, state
