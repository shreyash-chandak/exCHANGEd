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
from envs.tau2.refunds_canonical import canonical_action, canonical_state
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
from tau2.data_model.simulation import SimulationRun, TextRunConfig
from tau2.domains.retail.data_model import RetailDB
from tau2.domains.retail.utils import RETAIL_DB_PATH
from tau2.evaluator.evaluator import EvaluationType
from tau2.run import get_tasks, run_single_task

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

    def _canonicalize_refunds(self, task, sim: SimulationRun, agent: Agent) -> list[ExperienceRecord]:
        write_action = task.evaluation_criteria.actions[1]
        order_id = write_action.arguments["order_id"]
        order = self._db.orders[order_id]
        customer = self._db.customers[order.customer_id]
        request_type = task.description.purpose.split(",")[0].split()[0]
        persona = task.user_scenario.persona

        reward = 0.0
        if sim.reward_info is not None:
            reward = sim.reward_info.reward

        records: list[ExperienceRecord] = []
        prior_turns_bucket: PriorTurnsBucket = "t0"
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
                # the order's state as of episode start (matches R10's
                # one-write-per-order assumption -- the compliance
                # question is "was this the right call given how things
                # stood when the conversation started", not a moving
                # target as tau2's own internal DB mutates mid-episode).
                request = RefundRequest(
                    request_type=request_type,
                    order_id=order_id,
                    item_ids=taken[1].get("item_ids", []),
                    new_product_ids=taken[1].get("new_product_ids", []),
                )
                policy_eval_result = check(
                    order, request, customer, self._db.products, taken, self.policy_version
                )
                policy_eval = PolicyEval(
                    compliant=policy_eval_result.compliant,
                    violated_rule_ids=policy_eval_result.violated_rule_ids,
                )
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
            )
            records.append(record)
            self._t_global += 1
            prior_turns_bucket = _advance_prior_turns(prior_turns_bucket)

        return records

    def _canonicalize_retail(self, task, sim: SimulationRun, agent: Agent) -> list[ExperienceRecord]:
        # The reference trajectory's actions are ordered lookups-then-write
        # (e.g. find_user_id -> get_order_details -> get_product_details x2
        # -> exchange_delivered_order_items) -- taking the *first* action
        # bearing an order_id (a real bug, found live: every one of the
        # retail 5-episode smoke test's episodes came back task_type
        # "other" because that first action is always a read tool, which
        # task_type_from_tool has no mapping for) silently picks the wrong
        # order for grading whenever a write does occur. Look for the
        # write action specifically; only fall back to "any order_id" for
        # tasks with no write action in their reference (pure lookup /
        # COMMUNICATE-only tasks).
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
        order = self._db.orders[order_id] if order_id is not None else next(iter(self._db.orders.values()))

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
            )
            records.append(record)
            self._t_global += 1
            prior_turns_bucket = _advance_prior_turns(prior_turns_bucket)

        return records
