"""Generic tau2 Env adapter (session-2 guide 4a.7 -- builds what session-1
guide 4.4 specified as `Tau2RetailEnv`, made domain-parameterised per
4a.7's explicit instruction: "Wire Tau2Env(domain='refunds') through the
adapter ... build it now, domain parameterised").

tau2's own orchestrator drives the whole multi-turn conversation
internally (agent LLM + user-simulator LLM), unlike MockRetailEnv's
per-turn `agent.act(obs)` callback model -- see docs/tau2_interfaces.md
item 1. `run_episode`'s `agent` parameter is accepted for `Env` protocol
conformance but not used to drive turns; which tau2 agent implementation
actually runs is `agent_name` (a registry name, default tau2's own
built-in "llm_agent"). Wiring in a memory-injecting custom agent
(LessonAgent, session-1 guide 4.3) is future work, not in this phase's
scope -- this adapter's job here is the 4a.7 smoke test: drive the
refunds domain through tau2's real orchestrator against a real model and
confirm the domain itself works end-to-end.

Both the refunds domain (built from scratch, phase 4a) and tau2's own
shipped retail domain (external control, phase 4b) are wired up, each
through its own canonicalization module -- their compliance models are
different enough (an oracle with expected_action vs. two/three native
rule checks on top of tau2's own tool-level enforcement) that a shared
per-turn grading path isn't a good fit; `Tau2Env` dispatches to
`_canonicalize_refunds` or `_canonicalize_retail` by `self.domain`.
"""

from __future__ import annotations

from change.config import LLM_MODEL
from change.contracts import (
    CanonicalAction,
    CanonicalOutcome,
    ExperienceRecord,
    PolicyEval,
    PriorTurnsBucket,
)
from envs.base import Agent, EpisodeResult
from envs.tau2.domains.refunds.data_model import RefundsDB
from envs.tau2.domains.refunds.oracle import RefundRequest, check
from envs.tau2.domains.refunds.utils import REFUNDS_DB_PATH
from envs.tau2.refunds_canonical import canonical_action, canonical_state, grade_r1_r10
from envs.tau2.refunds_canonical import user_satisfied as refunds_user_satisfied
from envs.tau2.retail_canonical import (
    canonical_action as retail_canonical_action,
)
from envs.tau2.retail_canonical import (
    canonical_state as retail_canonical_state,
)
from envs.tau2.retail_canonical import (
    grade_write_action as retail_grade_write_action,
)
from envs.tau2.retail_canonical import task_type_from_tool as retail_task_type_from_tool
from envs.tau2.retail_canonical import user_satisfied as retail_user_satisfied
from envs.tau2.lesson_agent import LessonAgent
from change.memory import LessonMemory
from tau2.data_model.simulation import SimulationRun, TextRunConfig
from tau2.domains.retail.data_model import RetailDB
from tau2.domains.retail.utils import RETAIL_DB_PATH
from tau2.evaluator.evaluator import EvaluationType
from tau2.orchestrator.orchestrator import Orchestrator
from tau2.run import get_tasks, run_single_task
from tau2.runner.build import build_environment, build_user
from tau2.runner.simulation import run_simulation

_RETAIL_WRITE_TOOLS = {
    "cancel_pending_order",
    "return_delivered_order_items",
    "exchange_delivered_order_items",
    "modify_pending_order_address",
    "modify_pending_order_items",
    "modify_pending_order_payment",
    "modify_user_address",
    "transfer_to_human_agents",
}

# tau2's built-in agent/user-simulator call litellm directly (their own
# tau2/utils/llm_utils.py::generate), not through change/llm.py::chat() --
# so that function's thinking-disable fix doesn't reach them. Found live:
# without this, Ollama's qwen3.5:4b left content empty (reasoning went to
# a separate field tau2 doesn't look at), and tau2's own orchestrator
# crashed on the user simulator's empty UserMessage
# ("UserMessage must have either content or tool_calls"). TextRunConfig's
# llm_args_agent/llm_args_user are forwarded as **kwargs straight through
# to litellm.completion (tau2/utils/llm_utils.py::generate), so the same
# two mechanisms change/llm.py uses work here too.
_THINKING_DISABLED_LLM_ARGS = {
    "temperature": 0.0,
    "think": False,
    "chat_template_kwargs": {"enable_thinking": False},
}

_WRITE_TOOLS = {
    "refund_full",
    "refund_partial",
    "exchange_items",
    "cancel_order",
    "deny_request",
    "escalate",
}


def _advance_prior_turns(bucket: PriorTurnsBucket) -> PriorTurnsBucket:
    if bucket == "t0":
        return "t1to3"
    return "t4plus"


def _render_transcript(messages: list) -> str:
    """Flattens tau2's message-history objects into "Agent: ..." /
    "Customer: ..." lines for the end-of-episode satisfaction question
    (envs/tau2/satisfaction.py) -- deliberately not tau2's own message
    schema, see that module's docstring for why."""
    lines: list[str] = []
    for message in messages:
        role = getattr(message, "role", None)
        if role == "assistant":
            speaker = "Agent"
        elif role == "user":
            speaker = "Customer"
        else:
            continue  # system/tool messages aren't part of the customer's own view
        content = getattr(message, "content", None)
        if content:
            lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def _lessons_for_turn(lessons_by_turn: list[list[str]] | None, turn_idx: int) -> list[str]:
    """`lessons_by_turn` (LessonAgent.lessons_in_context_by_turn) has one
    entry per `generate_next_message` call -- but tau2's orchestrator
    always injects a hardcoded scripted opener as the conversation's
    first assistant message (`Orchestrator.DEFAULT_FIRST_AGENT_MESSAGE`,
    non-solo mode) *without* calling the agent at all, so `turn_idx=0`
    (that opener) has no corresponding entry and every later turn_idx is
    shifted by one. Found live: an unguarded `lessons_by_turn[turn_idx]`
    raised IndexError on the very first live memory-loop smoke test."""
    if not lessons_by_turn or turn_idx == 0:
        return []
    return lessons_by_turn[turn_idx - 1]


def _refunds_episode_context(task, db):
    """Shared by `run_episode` (post-hoc canonicalization) and
    `run_live_episode` (needs the same context up front to build the
    LessonAgent's per-turn state closure) -- one source of truth for
    "which order/customer/request is this episode about"."""
    write_action = task.evaluation_criteria.actions[1]
    order_id = write_action.arguments["order_id"]
    order = db.orders[order_id]
    customer = db.customers[order.customer_id]
    request_type = task.description.purpose.split(",")[0].split()[0]
    persona = task.user_scenario.persona
    return order, customer, request_type, persona, order_id


def _retail_episode_context(task, db):
    """Same sharing rationale as `_refunds_episode_context`. See
    `_canonicalize_retail`'s comment for why the write action (not just
    "any action bearing an order_id") must be found specifically."""
    order_id = None
    task_type = "other"
    actions = task.evaluation_criteria.actions or []
    for ref_action in actions:
        if ref_action.name in _RETAIL_WRITE_TOOLS and ref_action.arguments.get("order_id"):
            order_id = ref_action.arguments["order_id"]
            task_type = retail_task_type_from_tool(ref_action.name)
            break
    if order_id is None:
        for ref_action in actions:
            candidate_order_id = ref_action.arguments.get("order_id")
            if candidate_order_id is not None:
                order_id = candidate_order_id
                break
    order = db.orders[order_id] if order_id is not None else next(iter(db.orders.values()))
    return order, task_type, order_id


class Tau2Env:
    """`Env` protocol implementation driving a real tau2 domain through a
    real LLM. Requires `CHANGE_LIVE=1` at the caller's discretion -- this
    class itself doesn't gate on it (callers, e.g. scripts/run_episodes.py,
    are responsible for the live-call gate)."""

    def __init__(
        self,
        domain: str,
        run_id: str,
        agent_name: str = "llm_agent",
        policy_version: str = "v1",
        max_steps: int = 20,
    ):
        if domain not in ("refunds", "retail"):
            raise NotImplementedError(f"only refunds/retail are wired up, got {domain!r}")
        self.domain = domain
        self.run_id = run_id
        self.agent_name = agent_name
        self.policy_version = policy_version
        self.max_steps = max_steps
        if domain == "refunds":
            self._db = RefundsDB.load(REFUNDS_DB_PATH)
            self._tasks = {t.id: t for t in get_tasks(task_set_name=domain, task_split_name=None)}
        else:
            import envs.tau2.domains.retail_d3  # noqa: F401 -- registers "retail_d3" at import

            self._db = RetailDB.load(RETAIL_DB_PATH)
            self._tasks = {t.id: t for t in get_tasks(task_set_name=domain, task_split_name="base")}
        self._t_global = 0

    def task_ids(self) -> list[str]:
        return list(self._tasks.keys())

    def task(self, task_id: str):
        return self._tasks[task_id]

    @property
    def t_global(self) -> int:
        return self._t_global

    def set_t_global(self, value: int) -> None:
        """Lets a resuming caller (scripts/run_episodes.py's --resume,
        guide 4d.2) continue t_global from where a prior, interrupted run
        of the same run_id left off, instead of restarting the count at 0
        and colliding with already-written records' t_global values."""
        self._t_global = value

    def run_episode(self, task_id: str, agent: Agent, seed: int) -> EpisodeResult:
        task = self._tasks[task_id]
        # retail's D3 policy is a separate registered domain variant
        # (envs/tau2/domains/retail_d3.py) -- same db/tools/tasks, swapped
        # policy text, per guide 4b.3 ("no policy text change needed for
        # [grading]... the agent's policy text is swapped").
        tau2_domain = "retail_d3" if self.domain == "retail" and self.policy_version == "v3" else self.domain
        config = TextRunConfig(
            domain=tau2_domain,
            agent=self.agent_name,
            user="user_simulator",
            llm_agent=LLM_MODEL,
            llm_args_agent=dict(_THINKING_DISABLED_LLM_ARGS),
            llm_user=LLM_MODEL,
            llm_args_user=dict(_THINKING_DISABLED_LLM_ARGS),
            max_steps=self.max_steps,
        )
        # Pin evaluation_type off tau2's default (EvaluationType.ALL):
        # ALL runs NL_ASSERTIONS whenever a task's reward_basis includes
        # it, and NL_ASSERTIONS is graded by a *hardcoded* model
        # (tau2.config.DEFAULT_LLM_NL_ASSERTIONS = "gpt-4.1-2025-04-14",
        # ignoring our own CHANGE_LLM_MODEL entirely) -- found live, some
        # retail tasks do have NL_ASSERTIONS in their reward_basis (docs/
        # tau2_interfaces.md item 4's "retail's reward_basis = [DB,
        # COMMUNICATE]" isn't universal), which would otherwise attempt a
        # real OpenAI call with no key configured. ALL_IGNORE_BASIS
        # evaluates ENV/COMMUNICATE/ACTION only, never NL_ASSERTIONS --
        # matches the guide's "no API spend" constraint and this repo's
        # own compliance signal (the oracle/RT-checks), which never used
        # NL_ASSERTIONS anyway.
        sim = run_single_task(
            config, task, seed=seed, evaluation_type=EvaluationType.ALL_IGNORE_BASIS
        )
        if self.domain == "refunds":
            records = self._canonicalize_refunds(task, sim, agent)
        else:
            records = self._canonicalize_retail(task, sim, agent)
        return EpisodeResult(records=records, reward=records[-1].reward if records else 0.0)

    def run_live_episode(
        self, task_id: str, memory: LessonMemory, gates: dict, seed: int
    ) -> EpisodeResult:
        """Like `run_episode`, but drives the episode through a
        memory-injecting `LessonAgent` (session-1 guide 4.3, wired live in
        session-2 guide 4c.2) instead of tau2's own built-in `llm_agent`.

        tau2's `build_agent`/`run_single_task` only construct agents by a
        registry-looked-up string name with a fixed kwarg set (tools,
        domain_policy, llm, llm_args, task) -- no room for our own
        `LessonMemory`/gates objects. So this builds the environment,
        agent, user, and orchestrator directly instead of going through
        `TextRunConfig`/`run_single_task`, the same low-level path
        `tau2.runner.simulation.run_simulation`'s own docstring
        demonstrates (docs/tau2_interfaces.md item 2, option (b))."""
        task = self._tasks[task_id]
        tau2_domain = "retail_d3" if self.domain == "retail" and self.policy_version == "v3" else self.domain
        environment = build_environment(tau2_domain)

        if self.domain == "refunds":
            order, customer, request_type, persona, order_id = _refunds_episode_context(
                task, self._db
            )
            state_fn = lambda ptb: canonical_state(order, request_type, persona, ptb)  # noqa: E731
            escalate_tool = "escalate"
            escalate_args_fn = lambda: {  # noqa: E731
                "order_id": order_id,
                "reason": "policy gate: high-value request outside eligibility window",
            }
        else:
            order, task_type, order_id = _retail_episode_context(task, self._db)
            state_fn = lambda ptb: retail_canonical_state(order, task_type, ptb)  # noqa: E731
            escalate_tool = "transfer_to_human_agents"
            escalate_args_fn = lambda: {  # noqa: E731
                "summary": f"Escalating order {order_id} per policy gate (high-value, outside eligibility)."
            }

        agent = LessonAgent(
            tools=environment.get_tools(),
            domain_policy=environment.get_policy(),
            llm=LLM_MODEL,
            llm_args=dict(_THINKING_DISABLED_LLM_ARGS),
            memory=memory,
            gates=gates,
            state_fn=state_fn,
            escalate_tool=escalate_tool,
            escalate_args_fn=escalate_args_fn,
        )
        # `_canonicalize_*` read agent_id/agent_version/memory_version via
        # getattr(..., default) since tau2's built-in llm_agent (the
        # run_episode path) has none of these -- LessonAgent gets a real
        # memory_version here so records reflect the actual evolving
        # memory rather than the fallback default of 0.
        agent.memory_version = memory.version
        user = build_user(
            "user_simulator",
            environment,
            task,
            llm=LLM_MODEL,
            llm_args=dict(_THINKING_DISABLED_LLM_ARGS),
        )
        orchestrator = Orchestrator(
            domain=tau2_domain,
            agent=agent,
            user=user,
            environment=environment,
            task=task,
            max_steps=self.max_steps,
            seed=seed,
        )
        sim = run_simulation(orchestrator, evaluation_type=EvaluationType.ALL_IGNORE_BASIS)

        if self.domain == "refunds":
            records = self._canonicalize_refunds(
                task, sim, agent, lessons_by_turn=agent.lessons_in_context_by_turn
            )
        else:
            records = self._canonicalize_retail(
                task, sim, agent, lessons_by_turn=agent.lessons_in_context_by_turn
            )
        return EpisodeResult(records=records, reward=records[-1].reward if records else 0.0)

    def _canonicalize_refunds(
        self,
        task,
        sim: SimulationRun,
        agent: Agent,
        lessons_by_turn: list[list[str]] | None = None,
    ) -> list[ExperienceRecord]:
        order, customer, request_type, persona, order_id = _refunds_episode_context(task, self._db)

        reward = 0.0
        if sim.reward_info is not None:
            reward = sim.reward_info.reward

        records: list[ExperienceRecord] = []
        prior_turns_bucket: PriorTurnsBucket = "t0"
        prior_write_calls: dict[str, int] = {}
        messages = sim.get_messages()
        assistant_indices = [i for i, m in enumerate(messages) if m.role == "assistant"]
        # One extra live call per episode (guide 4a.6): a real satisfaction
        # signal distinct from `reward`/task_success, which matters for D2
        # ("feedback=satisfaction") to be a meaningfully different signal
        # from D1 ("feedback=truth") at all.
        satisfied = refunds_user_satisfied(_render_transcript(messages))

        for turn_idx, msg_idx in enumerate(assistant_indices):
            message = messages[msg_idx]
            is_last = msg_idx == assistant_indices[-1]

            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                tool_call = tool_calls[0]
                try:
                    action = canonical_action(tool_call.name)
                except ValueError:
                    action = CanonicalAction.LOOKUP  # unknown/read tool, treat as informational
                taken = (tool_call.name, tool_call.arguments)
            elif is_last:
                action = CanonicalAction.END
                taken = None
            else:
                action = CanonicalAction.ASK_CLARIFY
                taken = None

            state = canonical_state(order, request_type, persona, prior_turns_bucket)

            if taken is not None and taken[0] in _WRITE_TOOLS:
                # A real write action: grade it against the oracle, using
                # the order's state as of episode start (the compliance
                # question is "was this the right call given how things
                # stood when the conversation started", not a moving
                # target as tau2's own internal DB mutates mid-episode),
                # plus R1 (identity+confirmation) and R10 (one write per
                # order) -- conversation-level properties the oracle's
                # pure (order, request) functions can't see, same
                # treatment as retail's RT1/RT2.
                request = RefundRequest(
                    request_type=request_type,
                    order_id=order_id,
                    item_ids=taken[1].get("item_ids", []),
                    new_product_ids=taken[1].get("new_product_ids", []),
                )
                policy_eval_result = check(
                    order, request, customer, self._db.products, taken, self.policy_version
                )
                r1_r10_violations = grade_r1_r10(messages, msg_idx, order_id, prior_write_calls)
                violated_rule_ids = list(policy_eval_result.violated_rule_ids) + r1_r10_violations
                policy_eval = PolicyEval(
                    compliant=not violated_rule_ids,
                    violated_rule_ids=violated_rule_ids,
                )
                prior_write_calls[order_id] = prior_write_calls.get(order_id, 0) + 1
            else:
                # Read/lookup/ask_clarify/end turns carry no policy
                # decision of their own -- the oracle only grades write
                # actions, so these are trivially compliant rather than
                # run through check() against a write action they aren't.
                request = RefundRequest(request_type=request_type, order_id=order_id)
                policy_eval = PolicyEval(compliant=True, violated_rule_ids=[])

            # Built directly (not via canonical_outcome, which re-derives
            # policy_compliant from the oracle -- for a non-write turn
            # that would wrongly grade it against a write action it never
            # took) using the policy_eval.compliant already computed above.
            outcome = CanonicalOutcome(
                policy_compliant=policy_eval.compliant,
                task_success=reward >= 1.0,
                user_satisfied=satisfied,
            )

            record = ExperienceRecord(
                run_id=self.run_id,
                agent_id=getattr(agent, "agent_id", "tau2-agent"),
                agent_version=getattr(agent, "agent_version", 1),
                memory_version=getattr(agent, "memory_version", 0),
                episode_id=str(sim.id),
                task_id=task.id,
                episode_seed=sim.seed or 0,
                turn_idx=turn_idx,
                t_global=self._t_global,
                state=state,
                action=action,
                tools_used=[tool_calls[0].name] if tool_calls else [],
                outcome=outcome,
                policy_eval=policy_eval,
                reward=reward,
                latency_ms=(message.generation_time_seconds or 0.0) * 1000.0,
                tokens_in=(message.usage or {}).get("prompt_tokens", 0) if message.usage else 0,
                tokens_out=(message.usage or {}).get("completion_tokens", 0) if message.usage else 0,
                cost_usd=message.cost or 0.0,
                lessons_in_context=_lessons_for_turn(lessons_by_turn, turn_idx),
            )
            records.append(record)
            self._t_global += 1
            prior_turns_bucket = _advance_prior_turns(prior_turns_bucket)

        return records

    def _canonicalize_retail(
        self,
        task,
        sim: SimulationRun,
        agent: Agent,
        lessons_by_turn: list[list[str]] | None = None,
    ) -> list[ExperienceRecord]:
        order, task_type, order_id = _retail_episode_context(task, self._db)

        reward = 0.0
        if sim.reward_info is not None:
            reward = sim.reward_info.reward

        records: list[ExperienceRecord] = []
        prior_turns_bucket: PriorTurnsBucket = "t0"
        prior_modify_calls: dict[str, int] = {}
        messages = sim.get_messages()
        assistant_indices = [i for i, m in enumerate(messages) if m.role == "assistant"]
        satisfied = retail_user_satisfied(_render_transcript(messages))

        for turn_idx, msg_idx in enumerate(assistant_indices):
            message = messages[msg_idx]
            is_last = msg_idx == assistant_indices[-1]

            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                tool_call = tool_calls[0]
                try:
                    action = retail_canonical_action(tool_call.name)
                except ValueError:
                    action = CanonicalAction.LOOKUP
                taken = (tool_call.name, tool_call.arguments)
            elif is_last:
                action = CanonicalAction.END
                taken = None
            else:
                action = CanonicalAction.ASK_CLARIFY
                taken = None

            state = retail_canonical_state(order, task_type, prior_turns_bucket)

            if taken is not None and taken[0] in _RETAIL_WRITE_TOOLS:
                policy_eval_result = retail_grade_write_action(
                    messages,
                    msg_idx,
                    taken[0],
                    taken[1],
                    order,
                    prior_modify_calls,
                    self.policy_version,
                )
                policy_eval = PolicyEval(
                    compliant=policy_eval_result.compliant,
                    violated_rule_ids=policy_eval_result.violated_rule_ids,
                )
                if taken[0] in (
                    "modify_pending_order_address",
                    "modify_pending_order_items",
                    "modify_pending_order_payment",
                ):
                    prior_modify_calls[order.order_id] = prior_modify_calls.get(order.order_id, 0) + 1
            else:
                policy_eval = PolicyEval(compliant=True, violated_rule_ids=[])

            outcome = CanonicalOutcome(
                policy_compliant=policy_eval.compliant,
                task_success=reward >= 1.0,
                user_satisfied=satisfied,
            )

            record = ExperienceRecord(
                run_id=self.run_id,
                agent_id=getattr(agent, "agent_id", "tau2-agent"),
                agent_version=getattr(agent, "agent_version", 1),
                memory_version=getattr(agent, "memory_version", 0),
                episode_id=str(sim.id),
                task_id=task.id,
                episode_seed=sim.seed or 0,
                turn_idx=turn_idx,
                t_global=self._t_global,
                state=state,
                action=action,
                tools_used=[tool_calls[0].name] if tool_calls else [],
                outcome=outcome,
                policy_eval=policy_eval,
                reward=reward,
                latency_ms=(message.generation_time_seconds or 0.0) * 1000.0,
                tokens_in=(message.usage or {}).get("prompt_tokens", 0) if message.usage else 0,
                tokens_out=(message.usage or {}).get("completion_tokens", 0) if message.usage else 0,
                cost_usd=message.cost or 0.0,
                lessons_in_context=_lessons_for_turn(lessons_by_turn, turn_idx),
            )
            records.append(record)
            self._t_global += 1
            prior_turns_bucket = _advance_prior_turns(prior_turns_bucket)

        return records
