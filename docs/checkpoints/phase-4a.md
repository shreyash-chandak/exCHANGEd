# Phase 4a checkpoint (session-2 guide, the refunds tau2 domain)

## Done

- 4a.1 `envs/tau2/domains/refunds/data_model.py` + `scripts/gen_refunds_db.py`: `RefundsDB`
  (customers, products, orders), 60/40/300, value tertiles ~32/34/34% at seed 0. Commits
  `aca5a06`, `a426e3b` (the latter a fix: guaranteed minimum order-category coverage for
  task generation, found necessary while building 4a.5).
- 4a.2 `envs/tau2/domains/refunds/data/policy.md` + `policy_d3.md`: R1-R10 exactly as
  specified, D3's tightened variant. Commit `4d54505`.
- 4a.3 `envs/tau2/domains/refunds/tools.py`: read + write tools, write tools deliberately
  enforce nothing beyond "order exists, not terminal." Commit `89365d9`.
- 4a.4 `envs/tau2/domains/refunds/oracle.py` + `tests/test_refunds_oracle.py`: single source
  of truth, 4752-combination exhaustive grid (guide asks >=500). Commits `6e65ba8`, `9608f59`
  (a real bug the grid caught: R8's refund-amount check used the wrong basis).
- 4a.5 `scripts/gen_refunds_tasks.py`: 120 base tasks (81-cell grid, 0 skipped at seed 0, +15
  R8 + 10 R6-shipped, topped up to 120), 30 D3 tasks near the policy boundaries.
  `docs/refunds_task_samples.md`, 20 hand-checkable samples. Commit `1a90708`.
- 4a.6 `envs/tau2/domains/refunds/{environment,__init__}.py` (registers "refunds" into
  `tau2.registry.registry` at import time, no vendor edits, Q3's already-authorized
  pattern), `envs/tau2/refunds_canonical.py`, `tests/test_refunds_domain.py`. Commit
  `bbec2cb`.
- 4a.7 `envs/tau2/adapter.py` (`Tau2Env`, domain-parameterised, built now since session 1
  never reached its own phase 4.4), `scripts/run_episodes.py --env tau2 --domain refunds`,
  `tests/test_refunds_live.py`. Commit `4aebc52`. Live smoke run below.

## Smoke test output

```
$ uv run pytest -q -m "not live"
6192 passed, 1 deselected, 4 xfailed, 1 warning in ~70s

$ CHANGE_LIVE=1 uv run python scripts/run_episodes.py --env tau2 --domain refunds --n 5 --seed 0 --run-id refunds-smoke
running task refunds_000 (1/5)...
  9 records, reward=1.0
running task refunds_001 (2/5)...
  8 records, reward=1.0
running task refunds_002 (3/5)...
  7 records, reward=1.0
running task refunds_003 (4/5)...
  5 records, reward=0.0
running task refunds_004 (5/5)...
  8 records, reward=0.0
done: 5 episodes written to runs\refunds-smoke
```

Against the Ollama/qwen3.5:4b setup from `docs/serving.md` (tau2's own built-in `llm_agent`/
`user_simulator`, not a memory-injecting custom agent -- that's session-1 guide 4.3, future
work, not this phase's scope). 37 records total, all well-formed: every one has a nonempty
`state_key`, an action from `CanonicalAction`, and a populated `policy_eval` (checked
directly, 0 malformed).

**5-episode table** (task id, opening state, stance, actions taken, per-turn compliance,
final reward):

| task | state (task_type\|order_status\|value\|window\|stance\|turns) | actions | compliant | reward |
|---|---|---|---|---|
| refunds_000 | return\|delivered\|high\|0\|neutral\|t0 | ask_clarify x2, lookup, ask_clarify x2, lookup, ask_clarify x2, end | all True | 1.0 |
| refunds_001 | exchange\|delivered\|mid\|0\|neutral\|t0 | ask_clarify x2, lookup x2, ask_clarify x3, end | all True | 1.0 |
| refunds_002 | return\|delivered\|high\|0\|distressed\|t0 | ask_clarify x2, lookup x2, ask_clarify, **escalate**, end | True,True,True,True,True,**False**,True | 1.0 |
| refunds_003 | cancel\|pending\|mid\|1\|neutral\|t0 | ask_clarify, lookup, ask_clarify, lookup, end | all True | 0.0 |
| refunds_004 | return\|delivered\|low\|0\|neutral\|t0 | ask_clarify x2, lookup, ask_clarify, lookup, ask_clarify, **refund_full**, end | True x6,**False**,True | 0.0 |

## Reading this honestly

**The domain, tools, policy, oracle, and adapter all work end-to-end against a real model.**
That was this smoke test's actual job and it's confirmed.

**Two genuine findings, not swept under the rug:**

1. **3 of 5 episodes never called a write tool at all** -- the agent gathered information
   (identity lookup, order lookup) and then either asked more questions or ended the
   conversation without ever calling `refund_full`/`refund_partial`/`exchange_items`/
   `cancel_order`/`deny_request`/`escalate`. Two of those three (`refunds_000`, `refunds_001`)
   still scored `reward=1.0` from tau2's own DB-hash-match evaluator -- because the reference
   trajectory's expected action for both tasks doesn't mutate any DB field in a way this
   evaluator's default `reward_basis=[DB, COMMUNICATE]` catches as different from "nothing
   happened." This is a real limitation of DB-hash-match reward for this small a model on a
   fresh domain, not a bug in the domain or adapter -- flagging since it means `reward` alone
   is not a reliable signal that the agent actually resolved the customer's request here; the
   per-turn oracle-based `policy_eval` (this checkpoint's whole reason for existing per guide
   4a.4) is the more trustworthy one.
2. **The oracle caught two real, independent violations tau2's own reward missed entirely**:
   `refunds_002`'s `escalate` call was graded non-compliant (R9 -- escalating when no rule
   required it, likely provoked by the distressed persona) even though the episode still
   scored `reward=1.0`; `refunds_004`'s `refund_full` call was graded non-compliant (the order
   was outside the eligible window) even though the DB-mutation happened, and *that* episode
   scored `reward=0.0` for an unrelated reason (DB mismatch against the reference). This is
   direct empirical confirmation of exactly the design rationale in `docs/tau2_interfaces.md`
   item 4 and this domain's own oracle.py docstring: policy compliance genuinely cannot be
   read off tau2's own reward, and needs the oracle.

Neither finding blocks anything -- they're exactly the kind of signal phase 4.2's baseline
gate (next) is supposed to measure systematically across 50 episodes, not 5.

## Deviations from the guide

### tau2's built-in agent/user-simulator needed the thinking-disable fix too
Found live, on the very first real episode: `change/llm.py::chat()`'s thinking-disable fix
(phase 4.1) only covers calls made through that one function. tau2's own `llm_agent`/
`user_simulator` call litellm directly through their own `tau2/utils/llm_utils.py::generate`,
which never touches `change/llm.py`. Without a fix, Ollama's `qwen3.5:4b` left the
user-simulator's `content` empty (reasoning went to a field tau2 doesn't read) and tau2's own
orchestrator crashed mid-conversation (`UserMessage must have either content or tool_calls`).
Fixed by forwarding the same `think=False` / `chat_template_kwargs` mechanisms through
`TextRunConfig.llm_args_agent`/`llm_args_user`, which tau2 forwards as `**kwargs` straight to
`litellm.completion`. Documented in `envs/tau2/adapter.py`.

### `Tau2Env`'s `agent` parameter isn't used to drive turns
tau2's orchestrator runs the whole multi-turn conversation internally via its own registered
agent/user-simulator implementations (a *string* name, e.g. `"llm_agent"`, looked up in
`tau2.registry.registry`) -- fundamentally different from `MockRetailEnv`'s per-turn
`agent.act(obs)` callback model that the rest of `change/` (Sandbox, GovernanceLoop, etc.)
is built around. `Tau2Env.run_episode(task_id, agent, seed)` accepts `agent` for `Env`
protocol conformance but doesn't call into it; which tau2 agent actually runs is
`Tau2Env(agent_name=...)`, defaulting to tau2's own built-in `"llm_agent"`. Wiring in a
memory-injecting custom agent (`LessonAgent`, session-1 guide 4.3, which *would* need to hook
into tau2's own agent-registration machinery to actually drive turns) is future work --
this phase's job was proving the domain itself works, not the governance loop against it yet.

## Open questions for owner
None new from this phase's own logic. The two findings above are worth keeping in mind for
phase 4.2's baseline gate (which runs 50 episodes and explicitly measures violation rate and
derail rate) rather than requiring a decision now.

## Next
Per session-2 guide section 9's stop-point list: **STOP here.** Owner reads
`docs/refunds_task_samples.md` and the 5-episode table above before phase 4.2 (no-memory
baseline gate, LIVE, 50 episodes per domain) proceeds.
