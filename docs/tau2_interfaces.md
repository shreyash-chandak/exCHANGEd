# tau2-bench interface discovery

Submodule: `vendor/tau2-bench`, pinned to tag `v1.0.1`, commit `fc0055dc4e0a316c3f83133267fbd6faaa770992` (2026-07-16, "chore: prepare release v1.0.1 — banking_knowledge grading fixes (#408)"). This is the newest tagged release at or above the `v1.0.1` floor (next tag `voice-user-sim-v1.0` points at the same commit as `v1.0.0`, i.e. older).

Package name on import is `tau2` (installed editable as `tau2==1.0.1` from `vendor/tau2-bench`, dependency name `tau2` in `pyproject.toml` via `[tool.uv.sources]`).

**READ THIS BEFORE STARTING PHASE 4.** Section "Deviations that affect the data contracts" below lists three places where the actual retail domain differs materially from what `CHANGE_poc_agent_guide.md` section 2 assumed. Per section 0.2 of the guide, differences that change a data contract are a stop-and-ask trigger — this is that stop.

---

## 1. Instantiate and run a single task programmatically (no CLI)

Three layers, all under `tau2.runner`, re-exported from `tau2.run`:

```python
from tau2.run import get_tasks, run_single_task
from tau2.data_model.simulation import TextRunConfig

config = TextRunConfig(
    domain="retail",
    agent="llm_agent",          # default
    user="user_simulator",      # default
    llm_agent="gpt-4.1-2025-04-14",     # any litellm model string
    llm_args_agent={"temperature": 0.0},
    llm_user="gpt-4.1-2025-04-14",
    llm_args_user={"temperature": 0.0},
    max_steps=200,               # DEFAULT_MAX_STEPS
    max_errors=10,
    seed=300,                    # DEFAULT_SEED; per-trial seed passed separately below
)

tasks = get_tasks(task_set_name="retail", task_split_name="base", task_ids=["0"])
sim: SimulationRun = run_single_task(config, tasks[0], seed=42)
```

- `run_single_task(config, task, *, seed=None, evaluation_type=EvaluationType.ALL, save_dir=None, ...) -> SimulationRun` — `tau2/runner/batch.py:341`. Builds an orchestrator (Layer 2, `build_orchestrator` in `tau2/runner/build.py`) and runs it (Layer 1, `run_simulation` in `tau2/runner/simulation.py`). No CLI, no disk I/O unless `save_dir` is given.
- Lower level, if we ever need it: `tau2.run.build_orchestrator(config, task, seed=...)` then `tau2.run.run_simulation(orchestrator, evaluation_type=..., env_kwargs=...)`.
- Batch: `tau2.runner.batch.run_tasks(config, tasks, save_path=None, save_dir=None, console_display=False)` — handles concurrency, retries, checkpointing; per-trial seeds are derived by `random.seed(config.seed); seeds=[random.randint(0,1_000_000) for _ in range(num_trials)]` (`tau2/runner/batch.py:517-518`), i.e. **not simply `config.seed`** — one trial's actual seed is `seeds[trial]`, not `config.seed + trial`.
- For our per-episode loop (phase 4.4 `Tau2RetailEnv.run_episode(task_id, agent, seed)`), call `get_tasks` once, then `run_single_task(config, task, seed=seed)` per episode — matches the `Env` protocol from `envs/base.py` directly, no batch runner needed.

## 2. Agent base class / protocol

- Two protocols: `HalfDuplexAgent` (turn-based, what we use — text mode) and `FullDuplexAgent` (voice, irrelevant to us).
- `HalfDuplexAgent[StateType]` (`src/tau2/agent/base_agent.py`), constructor contract shared with `FullDuplexAgent`: `__init__(self, tools: list[Tool], domain_policy: str)`. LLM-backed agents additionally mix in `LLMConfigMixin` (`src/tau2/agent/base/llm_config.py`) which adds `llm: str`, `llm_args: dict`, and `set_seed(seed)` (writes `llm_args["seed"] = seed`, with a warning if already set — see item 10 below).
- Methods to implement:
  - `get_init_state(message_history: Optional[list[Message]] = None) -> StateType`
  - `generate_next_message(message: UserMessage | ToolMessage | MultiToolMessage, state: StateType) -> tuple[AssistantMessage, StateType]`
- Built-in reference implementation: `LLMAgent` (`src/tau2/agent/llm_agent.py`), state = `LLMAgentState(system_messages, messages)`. `envs/tau2/lesson_agent.py` (phase 4.3) should subclass `HalfDuplexAgent` (mix in `LLMConfigMixin`) the same way, injecting the lesson block into the system prompt inside `get_init_state`, and emitting an `ExperienceRecord` via callback at the end of `generate_next_message` once a tool call (or end-of-turn) is observed.
- Registration: new agents register a factory in `src/tau2/registry.py` via `registry.register_agent_factory(create_fn, "name")`. We do **not** need to register `LessonAgent` in the vendored registry (never modify `vendor/tau2-bench`, section 0.3) — we construct it directly in `envs/tau2/adapter.py` and pass it to `run_single_task`'s underlying `build_orchestrator`, or more simply, construct the orchestrator manually with our agent instance rather than going through the `--agent <name>` CLI/registry path. `run_single_task`/`build_orchestrator` take `config.agent` as a **string** looked up in the registry, so for a *custom* agent class not in the registry we need `tau2.runner.build.build_orchestrator`'s lower-level pieces, or bypass by constructing `Orchestrator` directly with `agent=LessonAgent(...)`. **Needs confirmation from owner in phase 4**: whether to (a) monkey-register our factory into `tau2.registry.registry` at import time from our own module (not editing vendor files, just calling the registry's public `register_agent_factory` from `envs/tau2/lesson_agent.py`), or (b) construct the `Orchestrator` directly bypassing `build_orchestrator`. Option (a) is simplest and doesn't touch vendored files — recommended, but flagging since the guide didn't anticipate this decision point.

## 3. Retail policy location

- `data/tau2/domains/retail/policy.md`, plain markdown, loaded by `envs/tau2/environment.py::get_environment()` (`RETAIL_POLICY_PATH`, resolved in `src/tau2/domains/retail/utils.py`) and passed to `Environment(domain_name="retail", policy=policy, tools=tools)`. The agent receives it as `domain_policy` in its constructor (`HalfDuplexAgent.__init__`), and `LLMAgent` renders it into the system prompt.

## 4. Task schema, expected actions, reward basis

- `Task` (`src/tau2/data_model/tasks.py:560`): `id`, `description`, `user_scenario` (`UserScenario{persona, instructions}`), `initial_state`, `evaluation_criteria`, `issues`.
- **`evaluation_criteria.actions` is NOT a required trajectory.** It is one reference path replayed on a fresh environment to derive a target DB hash; the agent may take any path that produces an equivalent DB end state. Retail's default `reward_basis = [DB, COMMUNICATE]` — `RewardType.ACTION` is never used in retail/airline/telecom (only ~9 `banking_knowledge` tasks). This is extensively documented in `docs/evaluation.md` (read in full) and matters a lot for us: **`policy_eval.compliant` (2.3 CanonicalOutcome) cannot be derived from "did the agent's tool calls match `evaluation_criteria.actions`."** It has to come from a rule check against the retail policy (order status, action taken) written by us — which is what guide section 4.1 item 3 already anticipated ("If neither is possible, stop and ask" — it is possible, via a rule check, see section 8 below).
- Reward computed by `EnvironmentEvaluator` (DB hash match) × `CommunicateEvaluator` (substring match of `communicate_info`). `tau2 evaluate-trajs` / `EvaluationType.ALL_WITH_NL_ASSERTIONS` (CLI default) also populates `action_checks` / `partial_action_reward` **diagnostically** even when `ACTION` is not in `reward_basis` — useful as an extra signal but not the compliance signal itself.
- 114 base-split retail tasks total (`data/tau2/domains/retail/tasks.json`), with `split_tasks.json` giving `{"train": 74, "test": 40, "base": 114}`. **Note**: `test` and `train` together (114) equal `base`, i.e. `base` is the full set, `train`/`test` partition it — useful directly for our own held-out split (5.7.2 `SANDBOX_HELDOUT_FRACTION`) without having to invent our own partition, though we may still want our own deterministic re-split for the canary/sandbox/train-proper three-way split the PoC guide specifies.

## 5. Trajectory / simulation output schema

- `SimulationRun` (`src/tau2/data_model/simulation.py:1247`): `id`, `task_id`, `timestamp`, `start_time`/`end_time`/`duration`, `termination_reason` (`TerminationReason` enum: `user_stop`, `agent_stop`, `max_steps`, `timeout`, `too_many_errors`, `agent_error`, `user_error`, `infrastructure_error`, `context_window_exceeded`, `unexpected_error`), `agent_cost`, `user_cost`, `reward_info: RewardInfo`, `messages: list[Message]` (half-duplex — this is what we use), `ticks` (full-duplex only, N/A), `trial`, `seed`.
- `sim.get_messages()` returns the flat list (already populated for text/half-duplex runs).
- Message types (`src/tau2/data_model/message.py`): `SystemMessage`, `UserMessage`, `AssistantMessage` (has `.tool_calls: Optional[list[ToolCall]]`, `.content`), `ToolMessage` (`.content` = tool result, tied to a `ToolCall.id`), `MultiToolMessage`. `ToolCall{id, name, arguments: dict, requestor}`.
- `RewardInfo` (`simulation.py:1053`): `reward: float`, `db_check: DBCheck{db_match, db_reward}`, `env_assertions`, `action_checks: list[ActionCheck]{action, action_match, action_reward, tool_type}` (diagnostic, see item 4), `communicate_checks`, `reward_basis`, `reward_breakdown: dict[RewardType, float]`.
- For our `ExperienceRecord` per decision turn (guide 5.1): iterate `sim.get_messages()`, group by assistant turn; each `AssistantMessage` with `tool_calls` (or none, for pure-text turns) is one decision. `sim.reward_info.reward` and `.db_check.db_match` back-fill the episode-level `reward`/`policy_eval` fields once the episode ends (matches guide's "policy_eval ... from a rule check you write", since DB-hash-match is an end-state signal, not a per-turn one — see section 8).

## 6. User simulator configuration / `user_stance` source

- `UserSimulator` (`src/tau2/user/user_simulator.py:99`), LLM-backed, system prompt = global guidelines (`data/tau2/user_simulator/simulation_guidelines*.md`) + task's `user_scenario` (persona + instructions) rendered via `UserScenario.__str__`.
- `Task.user_scenario.persona: Optional[str]` — **inspected all 114 retail tasks: `persona` is `null` on every one** (confirmed by spot-checking task `"0"`; the field exists in the schema but retail doesn't populate it). `Task.user_scenario.instructions` is either a free-text string or a `StructuredUserInstructions{domain, reason_for_call, known_info, unknown_info, task_instructions}` — retail tasks use the structured form. None of these fields carry a machine-readable stance/persona tag (no `pushy`/`distressed`/`neutral` enum anywhere in the task JSON).
- Runtime persona knobs exist (`PersonaConfig{verbosity, interrupt_tendency}`, `src/tau2/data_model/persona.py`) but are a **run-level** override applied uniformly to every task in a batch (see `runner/batch.py:539` — only built for voice mode in the current code path), not a per-task property we can read.
- **Conclusion for `user_stance` (guide 4.1 / 2.1)**: there is no structured signal to derive it from. Per guide section 4.1 ("from simulator instruction tags, not inferred from text... If a field cannot be derived deterministically, drop the field"), `user_stance` cannot be derived deterministically for the retail domain as specified and **should default to the constant `"neutral"` for every record**, which we document in `retail_canonical.py`'s docstring per guide 4.1. This still satisfies the `CanonicalState` schema (2.1) since the field stays present, just constant — flagging because it makes `user_stance` a no-op dimension for the base retail split (all three drift conditions D1-D3 will show zero variance on it), which the paper should note as a limitation of the chosen testbed rather than something to fabricate a proxy for.

## 7. Retail DB schema (orders/products/users)

- `RetailDB(DB)` (`src/tau2/domains/retail/data_model.py:208`): `products: dict[str, Product]`, `users: dict[str, User]`, `orders: dict[str, Order]`.
- `Order`/`BaseOrder`: `order_id`, `user_id`, `address`, `items: list[OrderItem]{name, product_id, item_id, price, options}`, `status: OrderStatus`, `fulfillments`, `payment_history: list[OrderPayment]{transaction_type: "payment"|"refund", amount, payment_method_id}`, `cancel_reason`, `exchange_items`/`exchange_new_items`/`exchange_payment_method_id`/`exchange_price_difference`, `return_items`/`return_payment_method_id`.
- `OrderStatus = Literal["processed", "pending", "pending (item modified)", "delivered", "cancelled", "exchange requested", "return requested"]` — this maps directly onto `CanonicalState.order_status` (2.1), but that enum only has `{pending, processed, delivered, cancelled, unknown}` — **`"pending (item modified)"`, `"exchange requested"`, `"return requested"` have no slot**. Proposed mapping (needs owner sign-off): `"pending (item modified)" -> pending`, `"exchange requested" -> processed`, `"return requested" -> processed`. Alternative: extend the enum. Flagged below.
- **No date/timestamp field exists anywhere on `Order`, `OrderItem`, or the DB** (confirmed by inspecting a sample order and the full pydantic schema — there is no `created_at`, `order_date`, `delivered_at`, nothing). `value_bucket` (2.1) *is* still derivable — from `sum(item.price for item in order.items)`, tertiles computed once over `db.json` at import time as guide 4.1 already specifies. **`within_policy_window` (2.1) is NOT derivable from dates because there are none** — see the deviations section below, this is the most important finding of phase 1.

## 8. Retail tool names → canonical actions (2.2) — MAJOR DEVIATION, see below

Full retail toolkit (`src/tau2/domains/retail/tools.py`, `RetailTools(ToolKitBase)`), 13 tools:

| Tool | Type | Effect | Proposed canonical action |
|---|---|---|---|
| `calculate` | GENERIC | pure math, no DB | *(not a decision action — filter out of ExperienceRecord, or map to a new `other` bucket)* |
| `cancel_pending_order(order_id, reason)` | WRITE | pending → cancelled, refund | `cancel` |
| `exchange_delivered_order_items(order_id, item_ids, new_item_ids, payment_method_id)` | WRITE | delivered → "exchange requested" | `exchange` |
| `find_user_id_by_name_zip` | READ | auth | `lookup` |
| `find_user_id_by_email` | READ | auth | `lookup` |
| `get_order_details` | READ | — | `lookup` |
| `get_product_details` | READ | — | `lookup` |
| `get_item_details` | READ | — | `lookup` |
| `get_user_details` | READ | — | `lookup` |
| `list_all_product_types` | READ | — | `lookup` |
| `modify_pending_order_address` | WRITE | pending, address only | `modify` |
| `modify_pending_order_items` | WRITE | pending → "pending (item modified)" | `modify` |
| `modify_pending_order_payment` | WRITE | pending, payment only | `modify` |
| `return_delivered_order_items(order_id, item_ids, payment_method_id)` | WRITE | delivered → "return requested" | **no clean slot — see below** |
| `transfer_to_human_agents(summary)` | GENERIC | no DB effect | `escalate` |

**`ask_clarify` and `end`**, as anticipated by the guide: no tool exists for either. Represented as: `ask_clarify` = an `AssistantMessage` turn with `content` set and `tool_calls` empty/`None` (a pure-text turn that is a question, heuristically — or more simply, *any* non-tool-call assistant turn that isn't the last one); `end` = the final assistant turn of the episode (`sim.termination_reason in {agent_stop, user_stop}` and no further turns). This matches the guide's expectation exactly.

**`refund_full` and `refund_partial` (2.2) have NO tau2 tool at all, and neither does a generic "refund."** The closest retail actions are:
- `cancel_pending_order` — refunds the *entire* order (gift card immediately, else 5-7 business days) as a side effect of cancelling a pending order. This is a full refund, but it's gated on order status `pending`, not on a "return" decision for a delivered order.
- `return_delivered_order_items` — for a **delivered** order, marks specific items for return; the actual refund is asynchronous (order status becomes `"return requested"`, user gets an email, no direct payment record is written by this tool call itself). Full vs. partial is determined by whether `item_ids` covers all items in the order or a subset — not by two distinct tools.
- `exchange_delivered_order_items` — item-for-item exchange, with a computed price difference (can itself be positive or negative, i.e. a partial refund or an additional charge) posted immediately as a same-call side effect (unlike return).

**None of `deny` is a tool either** — same as `ask_clarify`/`end`, it is implicit: a pure-text assistant turn that refuses the request per policy (e.g. "I'm sorry, I can't process that because...").

## 9. Task count

114 tasks in `data/tau2/domains/retail/tasks.json` (`base` split = all 114; `split_tasks.json` also defines `train` (74) and `test` (40), which partition `base`).

## 10. LiteLLM model string, temperature, seed

- `llm_agent`/`llm_user` are arbitrary LiteLLM model strings (any provider LiteLLM supports), passed straight through — no tau2-specific validation.
- Temperature: `TextRunConfig.llm_args_agent` / `llm_args_user`, defaulting to `{"temperature": 0.0}` (`DEFAULT_LLM_ARGS_AGENT`/`DEFAULT_LLM_ARGS_USER`, `src/tau2/config.py:19-22`) — i.e. **greedy decoding by default already**, we don't need to set it ourselves unless overriding.
- Seed: **not set by default.** `LLMConfigMixin.set_seed(seed)` (item 2 above) writes `llm_args["seed"] = seed`, and the orchestrator calls `agent.set_seed(self.seed)` / `user.set_seed(self.seed)` automatically whenever `Orchestrator(seed=...)` is non-`None` (`src/tau2/orchestrator/orchestrator.py:526-528`), which happens whenever we pass `seed=` into `run_single_task`/`build_orchestrator`. The seed then flows into `litellm.completion(..., seed=...)` inside `generate()` (`src/tau2/utils/llm_utils.py:355`) as a plain passthrough kwarg — support for actually honoring it is provider-dependent (OpenAI documents `seed` as best-effort, not a determinism guarantee).

## 11. Replay determinism

- Passing the same `seed` to `run_single_task(config, task, seed=N)` reproduces the same orchestrator/agent/user seeding, and with `temperature=0` + `seed=N` on both agent and user LLM calls, trajectories are **close to deterministic but not guaranteed** — provider-side nondeterminism (item 12) means two runs with identical `(task, seed, model, temperature)` can occasionally diverge, especially past a few turns (small logit differences compound). No tau2-internal source of extra randomness was found for text-mode retail beyond the two LLM calls themselves (no dice rolls in `RetailTools`, no randomized DB state at task-load time).
- Batch-level note (item 1): if we ever go through `run_tasks`/`run_domain` instead of calling `run_single_task` ourselves per episode, the *effective* per-trial seed is `seeds[trial]` from `random.seed(config.seed); seeds=[random.randint(...) for _ in range(num_trials)]`, not `config.seed` directly — irrelevant to our design since guide 3.6/4.4 call `run_single_task` once per episode with our own seed.

## 12. Uncontrollable nondeterminism

- LLM provider-side sampling nondeterminism even at `temperature=0` + fixed `seed` (documented OpenAI/Anthropic behavior — logits can differ run-to-run due to batching/hardware effects on the provider side). This is the only source found; there is no local randomness in the retail tools, DB, or orchestrator once seeds are fixed. Practically: expect episode-level determinism to be high but not exact; for `D4` (optional, model swap) and any "replay" analysis, treat two same-seed runs as approximately, not exactly, comparable.

---

## Deviations that affect the data contracts (STOP — needs owner sign-off before phase 4)

Three findings from this phase materially change what `CHANGE_poc_agent_guide.md` section 2 (`CanonicalState`/`CanonicalAction`) assumed, because they were written from `approach1.md`'s illustrative Alice/Bob refund agent rather than tau2 retail's actual tools:

1. **No `refund_full` / `refund_partial` distinction exists in retail.** The closest real actions are `cancel_pending_order` (full refund, but only for *pending* orders), `return_delivered_order_items` (delivered orders, refund is downstream/async, full-vs-partial is an argument to one tool not two tools), and `exchange_delivered_order_items` (item swap with a priced delta, immediate). Recommendation: collapse `CanonicalAction` (2.2) to match tau2 retail's actual write tools — e.g. `{cancel, return, exchange, modify_address, modify_items, modify_payment, escalate, ask_clarify, lookup, end}` — dropping `refund_full`/`refund_partial`/`deny` as tool-backed actions (`deny` stays as the "no tool call, refusal" bucket, same treatment as `ask_clarify`/`end`). This is a bigger change than a rename: it removes the refund-generosity axis that `approach1.md`'s drift story (D2, "generosity drift, more refunds outside policy") was built around.
2. **`within_policy_window` cannot be computed — retail has no order dates anywhere in the DB or task data.** Eligibility for cancel/modify is gated purely by `order_status == "pending"`; eligibility for return/exchange purely by `order_status == "delivered"`. There is no time-window concept in the retail policy at all (confirmed by reading `policy.md` in full — it describes status-gating only). This breaks D3 (guide 3.3: "policy update... exchange window shortened") as originally conceived for retail, since there is no window to shorten. Recommendation: **retarget D3** to a status-gating policy change instead (e.g. "returns of `'processed'`-but-not-yet-`'delivered'` orders newly disallowed" or a change to which `order_status` values permit which action) — mechanically the same kind of drift-inducing policy edit, just keyed on `order_status` instead of a date window. `within_policy_window` as a `CanonicalState` field name should probably be renamed to reflect a status-gate check (e.g. `status_eligible: bool`) rather than implying a temporal window.
3. **`user_stance` has no source signal** (item 6) — every retail task has `persona=None` and no structured stance tag in `instructions`. Recommend it stays in `CanonicalState` as a constant `"neutral"` (matches guide 4.1's documented fallback) but the paper/checkpoint should note this dimension carries zero information for the retail domain as shipped, rather than us inventing an LLM-based stance classifier (which the guide explicitly forbids: "Do not use an LLM labeller for state").

None of these block Phase 2/3 (contracts, mock env — the mock env is our own invention and unaffected). They **do** block Phase 4 (`envs/tau2/retail_canonical.py`, `lesson_agent.py`) until the owner picks: (a) adjust `CanonicalAction`/`CanonicalState` per the recommendations above, (b) pick a different tau2 domain (airline/telecom) if either has the refund-generosity + time-window structure the plan wants more natively (not investigated — out of scope for this phase per guide 1.3 "Do not read further than needed"), or (c) accept the retail domain as-is and have the coding agent proceed with the recommended mappings above without further changes.

Also flagged inline above, smaller and non-blocking:
- `OrderStatus` has 7 values, `CanonicalState.order_status` (2.1) has 5 — proposed collapse in item 8's table.
- Custom (non-registry) agent construction for `LessonAgent` (item 2) — recommended approach: call `registry.register_agent_factory` from our own module at import time (no vendor edits), needs a one-line owner nod since the guide didn't anticipate this.
