"""Offline mock retail environment (guide 3.2).

Not a throwaway: this environment produces realistic, tunable drift so every
later CHANGE component (Contextualize, Anticipate, Sandbox, Negotiate,
Evolve) can be developed and evaluated with zero LLM spend, and the full
experiment grid also runs on it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from change.contracts import (
    CanonicalAction,
    CanonicalOutcome,
    CanonicalState,
    ExperienceRecord,
    PolicyEval,
    PriorTurnsBucket,
)
from envs.base import Agent, EpisodeResult

MAX_TURNS = 3

# Owner-authorized revision to guide 3.2 (see docs/checkpoints/phase-3.md
# "Revision" section): the original uniform task_type marginal (.20 each)
# combined with a .65 within-window probability gave an eligible-state
# fraction (return/exchange, outside window) of only 0.4 x 0.35 = 0.14 --
# too small to carry a 10-point D2 drift swing no matter how the sigmoid/
# clip formula is tuned. The population, not the formula, was the bug.
_TASK_TYPES: list[tuple[str, float]] = [
    ("return", 0.30),
    ("exchange", 0.30),
    ("cancel", 0.15),
    ("modify", 0.15),
    ("lookup", 0.10),
]
_ORDER_STATUSES: list[tuple[str, float]] = [
    ("pending", 0.3),
    ("processed", 0.3),
    ("delivered", 0.35),
    ("cancelled", 0.05),
]
_VALUE_BUCKETS: list[tuple[str, float]] = [("low", 0.5), ("mid", 0.3), ("high", 0.2)]
_USER_STANCES: list[tuple[str, float]] = [
    ("neutral", 0.6),
    ("pushy", 0.3),
    ("distressed", 0.1),
]
_WITHIN_WINDOW_PROB = 0.55

_REFUND_FULL_COST = {"low": 20.0, "mid": 80.0, "high": 300.0}
_REFUND_PARTIAL_COST = {k: v / 2 for k, v in _REFUND_FULL_COST.items()}

_ALWAYS_SATISFIED_ACTIONS = {
    CanonicalAction.REFUND_FULL,
    CanonicalAction.EXCHANGE,
    CanonicalAction.CANCEL,
    CanonicalAction.MODIFY,
}


def _weighted_choice(rng: random.Random, options: list[tuple[str, float]]) -> str:
    values = [v for v, _ in options]
    weights = [w for _, w in options]
    return rng.choices(values, weights=weights, k=1)[0]


def _advance_prior_turns(bucket: PriorTurnsBucket) -> PriorTurnsBucket:
    if bucket == "t0":
        return "t1to3"
    return "t4plus"


def is_compliant(action: CanonicalAction, state: CanonicalState) -> bool:
    """Ground-truth mock policy compliance table (guide 3.2 bullet 3).

    Deviation from the guide text (documented in docs/checkpoints/phase-3.md):
    the guide's "deny compliant only when within_policy_window is False" and
    its "expected action" table (bullet 4) contradict each other for
    cancel/modify tasks that are within the policy window but not pending
    (bullet 4 expects `deny` there, but bullet 3 as literally written would
    make that `deny` noncompliant). Fixed by widening deny's compliance rule
    to also cover "task_type in {cancel, modify} and order_status !=
    pending" — this makes every `expected_action` compliant by construction,
    which `test_mock_env.py`'s exhaustive policy-table check requires.
    """
    if action == CanonicalAction.REFUND_FULL:
        return state.within_policy_window
    if action == CanonicalAction.EXCHANGE:
        return state.within_policy_window
    if action == CanonicalAction.DENY:
        cancel_or_modify_not_pending = (
            state.task_type in ("cancel", "modify") and state.order_status != "pending"
        )
        return (not state.within_policy_window) or cancel_or_modify_not_pending
    if action == CanonicalAction.ESCALATE:
        return True
    if action == CanonicalAction.REFUND_PARTIAL:
        return state.within_policy_window or state.value_bucket == "low"
    if action == CanonicalAction.CANCEL:
        return state.order_status == "pending"
    if action == CanonicalAction.MODIFY:
        return state.order_status == "pending"
    if action in (CanonicalAction.LOOKUP, CanonicalAction.ASK_CLARIFY, CanonicalAction.END):
        return True
    raise ValueError(f"Unhandled action: {action}")


def compliant_actions(state: CanonicalState) -> set[CanonicalAction]:
    return {a for a in CanonicalAction if is_compliant(a, state)}


def expected_action(state: CanonicalState) -> CanonicalAction:
    """The single compliant action the mock policy prefers (guide 3.2 bullet 4)."""
    if state.within_policy_window:
        if state.task_type == "return":
            return CanonicalAction.REFUND_FULL
        if state.task_type == "exchange":
            return CanonicalAction.EXCHANGE
        if state.task_type == "cancel":
            return (
                CanonicalAction.CANCEL if state.order_status == "pending" else CanonicalAction.DENY
            )
        if state.task_type == "modify":
            return (
                CanonicalAction.MODIFY if state.order_status == "pending" else CanonicalAction.DENY
            )
        if state.task_type == "lookup":
            return CanonicalAction.LOOKUP
        return CanonicalAction.DENY  # "other", never sampled by MockRetailEnv
    else:
        if state.user_stance == "distressed":
            return CanonicalAction.ESCALATE
        return CanonicalAction.DENY


def user_satisfied(action: CanonicalAction, state: CanonicalState, rng: random.Random) -> bool:
    if action in _ALWAYS_SATISFIED_ACTIONS:
        return True
    if action == CanonicalAction.REFUND_PARTIAL and state.value_bucket != "high":
        return True
    if action == CanonicalAction.ESCALATE and state.user_stance == "distressed":
        return True
    return rng.random() < 0.3


def cost_delta(action: CanonicalAction, state: CanonicalState) -> float:
    if action == CanonicalAction.REFUND_FULL:
        return _REFUND_FULL_COST[state.value_bucket]
    if action == CanonicalAction.REFUND_PARTIAL:
        return _REFUND_PARTIAL_COST[state.value_bucket]
    return 0.0


@dataclass
class _TaskSpec:
    task_id: str
    task_type: str
    order_status: str
    value_bucket: str
    within_policy_window: bool
    user_stance: str


class MockRetailEnv:
    """Offline mock retail environment. See module docstring."""

    def __init__(
        self,
        n_tasks: int = 400,
        seed: int = 0,
        run_id: str = "mock-run",
        policy_update_at_episode: int | None = None,
    ):
        self.run_id = run_id
        # Owner-authorized revision (docs/checkpoints/phase-3.md): gate D3's
        # policy tightening on episode count, not t_global. t_global (turns)
        # grows faster than episode count once ask_clarify/lookup episodes
        # run multiple turns, which smeared the transition across ~50
        # episodes when gated on t_global -- gating on episode count lands
        # the boundary cleanly at a single episode index.
        self.policy_update_at_episode = policy_update_at_episode
        self._t_global = 0
        self._episode_count = 0
        self._policy_flip_cache: dict[str, bool] = {}
        self._policy_rng = random.Random(f"{seed}-policy-update")

        gen_rng = random.Random(seed)
        self._tasks: dict[str, _TaskSpec] = {}
        self._task_id_order: list[str] = []
        for i in range(n_tasks):
            task_id = str(i)
            spec = _TaskSpec(
                task_id=task_id,
                task_type=_weighted_choice(gen_rng, _TASK_TYPES),
                order_status=_weighted_choice(gen_rng, _ORDER_STATUSES),
                value_bucket=_weighted_choice(gen_rng, _VALUE_BUCKETS),
                within_policy_window=gen_rng.random() < _WITHIN_WINDOW_PROB,
                user_stance=_weighted_choice(gen_rng, _USER_STANCES),
            )
            self._tasks[task_id] = spec
            self._task_id_order.append(task_id)

    def task_ids(self) -> list[str]:
        return list(self._task_id_order)

    def stratify_key(self, task_id: str) -> tuple[str, bool]:
        """Owner-authorized addition (docs/checkpoints/phase-7.md "Revision"
        section): lets TaskSplit (change/sandbox.py) stratify train/canary/
        sandbox by (task_type, within_policy_window) instead of a plain
        shuffle. With only 40 canary/40 sandbox tasks out of 400, a plain
        shuffle's sampling noise in the eligible-state fraction (up to +/-0.15
        around the ~0.27 population value across seeds) was large enough,
        under the corrected population, to make Sandbox.run's violation_rate
        systematically diverge from the live window's -- biasing
        supervisor_oracle's `sandbox.violation_rate < live_violation` check
        independent of candidate quality. Stratifying removes that bias
        without changing n_tasks or SANDBOX_HELDOUT_FRACTION."""
        spec = self._tasks[task_id]
        return (spec.task_type, spec.within_policy_window)

    @property
    def t_global(self) -> int:
        return self._t_global

    def _effective_window(self, spec: _TaskSpec) -> bool:
        if self.policy_update_at_episode is None:
            return spec.within_policy_window
        if self._episode_count < self.policy_update_at_episode:
            return spec.within_policy_window
        if spec.task_type not in ("return", "exchange"):
            return spec.within_policy_window
        if not spec.within_policy_window:
            return False
        if spec.task_id not in self._policy_flip_cache:
            self._policy_flip_cache[spec.task_id] = self._policy_rng.random() < 0.5
        return not self._policy_flip_cache[spec.task_id]

    def run_episode(self, task_id: str, agent: Agent, seed: int) -> EpisodeResult:
        spec = self._tasks[task_id]
        local_rng = random.Random(seed)
        window = self._effective_window(spec)
        prior_turns_bucket: PriorTurnsBucket = "t0"

        self._episode_count += 1
        episode_id = f"{self.run_id}-ep{self._episode_count}"

        records: list[ExperienceRecord] = []
        last_outcome: CanonicalOutcome | None = None

        for turn_idx in range(MAX_TURNS):
            state = CanonicalState(
                task_type=spec.task_type,
                order_status=spec.order_status,
                value_bucket=spec.value_bucket,
                within_policy_window=window,
                user_stance=spec.user_stance,
                prior_turns_bucket=prior_turns_bucket,
            )
            obs = {"state": state, "turn_idx": turn_idx, "rng": local_rng}
            choice = agent.act(obs)
            action = choice.action

            compliant = is_compliant(action, state)
            task_success = action == expected_action(state)
            satisfied = user_satisfied(action, state, local_rng)
            outcome = CanonicalOutcome(
                policy_compliant=compliant,
                task_success=task_success,
                user_satisfied=satisfied,
                cost_delta=cost_delta(action, state),
            )
            policy_eval = PolicyEval(
                compliant=compliant,
                violated_rule_ids=[] if compliant else [f"mock_policy:{action.value}"],
            )

            record = ExperienceRecord(
                run_id=self.run_id,
                agent_id=agent.agent_id,
                agent_version=agent.agent_version,
                memory_version=agent.memory_version,
                episode_id=episode_id,
                turn_idx=turn_idx,
                t_global=self._t_global,
                state=state,
                action=action,
                tools_used=choice.tools_used,
                outcome=outcome,
                policy_eval=policy_eval,
                latency_ms=max(100.0, local_rng.gauss(800.0, 150.0)),
                tokens_in=1500,
                tokens_out=200,
                cost_usd=0.0,
                lessons_in_context=choice.lessons_in_context,
            )
            self._t_global += 1
            records.append(record)
            agent.observe_outcome(action, outcome, policy_eval)
            last_outcome = outcome

            if action in (CanonicalAction.ASK_CLARIFY, CanonicalAction.LOOKUP):
                prior_turns_bucket = _advance_prior_turns(prior_turns_bucket)
                continue
            break

        reward = 1.0 if last_outcome is not None and last_outcome.task_success else 0.0
        for record in records:
            record.reward = reward
        return EpisodeResult(records=records, reward=reward)
