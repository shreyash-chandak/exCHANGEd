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

Only the refunds domain's canonicalization is wired up (retail_canonical
was never built -- phase 4b, not started).
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
from tau2.data_model.simulation import SimulationRun, TextRunConfig
from tau2.run import get_tasks, run_single_task

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
        if domain != "refunds":
            raise NotImplementedError(f"only the refunds domain is wired up, got {domain!r}")
        self.domain = domain
        self.run_id = run_id
        self.agent_name = agent_name
        self.policy_version = policy_version
        self.max_steps = max_steps
        self._db = RefundsDB.load(REFUNDS_DB_PATH)
        self._tasks = {t.id: t for t in get_tasks(task_set_name=domain, task_split_name=None)}
        self._t_global = 0

    def task_ids(self) -> list[str]:
        return list(self._tasks.keys())

    def run_episode(self, task_id: str, agent: Agent, seed: int) -> EpisodeResult:
        task = self._tasks[task_id]
        config = TextRunConfig(
            domain=self.domain,
            agent=self.agent_name,
            user="user_simulator",
            llm_agent=LLM_MODEL,
            llm_args_agent=dict(_THINKING_DISABLED_LLM_ARGS),
            llm_user=LLM_MODEL,
            llm_args_user=dict(_THINKING_DISABLED_LLM_ARGS),
            max_steps=self.max_steps,
        )
        sim = run_single_task(config, task, seed=seed)
        records = self._canonicalize(task, sim, agent)
        return EpisodeResult(records=records, reward=records[-1].reward if records else 0.0)

    def _canonicalize(self, task, sim: SimulationRun, agent: Agent) -> list[ExperienceRecord]:
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
                user_satisfied=reward >= 1.0,
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
