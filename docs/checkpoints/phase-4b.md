# Phase 4b checkpoint (session-2 guide, retail adapter)

## Done

- 4b.1 `envs/tau2/retail_canonical.py`: collapsed taxonomy (7 retail tool names to
  `CanonicalAction`), `status_eligible` as `within_policy_window` (retail has no
  order dates, only status gates -- confirmed in phase 1), value tertiles computed
  once over the retail db. Commit `46a0d0a`.
- 4b.2 `grade_write_action`: RT1 (explicit confirmation, regex matcher on the prior
  user turn) and RT2 (at most one `modify_pending_order_*` call per order).
  Commits `46a0d0a`, `02ea61d` (tests).
- 4b.3 D3 grading switch (RT3, original-payment-method-only), plus
  `envs/tau2/domains/retail_d3.py` registering a `retail_d3` tau2 domain variant
  (same db/tools/tasks, swapped policy text) -- same pattern tau2 itself uses for
  `telecom`/`telecom-workflow`. Commit `e3f054e`.
- `envs/tau2/adapter.py`: `Tau2Env` dispatches to `_canonicalize_retail` for
  `domain="retail"`, selecting `retail_d3` internally when `policy_version="v3"`.
  Commit `1855ef0`.
- 4b.4 Live smoke (5 episodes) and the phase 4.2 baseline gate (50 episodes) --
  both below, run after three real bugs found live were fixed (see Deviations).

## Smoke test output

```
$ uv run pytest -q -m "not live"
6220 passed, 2 deselected, 4 xfailed, 1 warning

$ CHANGE_LIVE=1 uv run python scripts/run_episodes.py --env tau2 --domain retail --n 5 --seed 0 --run-id retail-smoke
[1/5] 0 ... 11 records, reward=0.0
[2/5] 1 ... 11 records, reward=0.0
[3/5] 2 ... 11 records, reward=0.0
[4/5] 3 ...  9 records, reward=0.0
[5/5] 4 ... 11 records, reward=0.0
done: 5 episodes written to runs\retail-smoke
```

**5-episode table** (task, opening state, turn count, per-turn compliance, reward):

| task | state (task_type/order_status/value/window) | n turns | all compliant | reward |
|---|---|---:|---|---:|
| 0 | exchange/delivered/high/eligible | 11 | True | 0.0 |
| 1 | exchange/delivered/high/eligible | 11 | True | 0.0 |
| 2 | return/delivered/high/eligible | 11 | True | 0.0 |
| 3 | modify/pending/high/eligible | 9 | True | 0.0 |
| 4 | modify/pending/low/eligible | 11 | True | 0.0 |

**Retail baseline gate** (50 episodes, empty memory, no gates, `max_steps=20`):
see `docs/checkpoints/phase-4.2.md` (run together with refunds' baseline as the
same STOP point).

## Reading this honestly

**0 of 5 smoke episodes ever called a write tool.** All five stayed in
`ask_clarify`/`lookup`/`end` for their entire budget. These are tau2's own
well-known base retail tasks (0-4, the "Yusuf Rossi" exchange/return/modify
scenarios), which require several rounds of identity auth, order lookup, and (for
exchanges) 2+ product-variant lookups before a write is even possible -- a smaller
local model spends most of a 20-step budget gathering that context and, in this
sample, never got to the write call. Not tuned around -- reported as-is, same
spirit as phase 4a's own smoke findings. The baseline gate's larger n=50 sample
(`phase-4.2.md`) diagnoses this pattern further and finds a second, more specific
cause on the refunds side.

## Deviations from the guide

### Three real bugs found and fixed before these results were trustworthy
1. **`retail_d3` domain was never actually registered.** `envs/tau2/domains/
   retail_d3.py`'s module-level `registry.register_domain(...)` call only runs if
   the module is imported, and nothing imported it -- any D3 retail episode would
   have failed at task lookup. Fixed: `Tau2Env.__init__` imports it when
   `domain == "retail"`. Commit `6f5ef31`.
2. **`_canonicalize_retail` graded write actions against the wrong order.** It
   took `order_id` from the *first* reference action bearing one, but the
   reference trajectory is ordered lookups-then-write, so that first action is
   always a read tool -- `task_type_from_tool` has no mapping for those, so every
   episode's `task_type` silently came back `"other"`, and had a write occurred
   it would have been graded against an arbitrary fallback order. Fixed to find
   the *write* action specifically. Commit `fb0f808`. Verified offline against
   retail tasks 0-4: order/task_type now resolve correctly instead of "other" x5.
3. **An unconfigured paid-model call was one task away from firing.** tau2's
   default `evaluation_type=EvaluationType.ALL` runs its NL_ASSERTIONS evaluator
   whenever a task's `reward_basis` includes it, and that evaluator is hardcoded
   to `gpt-4.1-2025-04-14` (`tau2.config.DEFAULT_LLM_NL_ASSERTIONS`), ignoring
   `CHANGE_LLM_MODEL` entirely. Some retail tasks *do* have `NL_ASSERTION` in
   their reward_basis (docs/tau2_interfaces.md item 4's "retail's reward_basis =
   [DB, COMMUNICATE]" isn't universal) -- hit this live on retail task index 3 of
   the first 5-episode attempt, which crashed with "Missing credentials" since no
   OpenAI key is configured (by design, per the guide's no-API-spend rule).
   Pinned to `EvaluationType.ALL_IGNORE_BASIS` (never runs NL_ASSERTIONS).
   Commit `441498b`.

None of these were guessed at -- each was caught by a crash or a suspicious
"task_type=other" result on the very first live run, then verified against the
real task data before fixing.

### `user_satisfied` now asks a real question instead of `reward >= 1.0`
Unrelated to retail specifically, but touched the same code path: `envs/tau2/
refunds_canonical.py::user_satisfied()` (guide 4a.6's end-of-episode satisfaction
question) existed but was never called -- the adapter used `reward >= 1.0` as a
stand-in for both `task_success` and `user_satisfied`, which would have made D2's
`feedback=satisfaction` behaviorally identical to D1's `feedback=truth` once
phase 4c's live lesson extractor needed to tell them apart. Wired the real
question through for both domains (`envs/tau2/satisfaction.py`, shared).
Commit `6f5ef31`.

## Open questions for owner

None new beyond what phase 4.2's checkpoint raises (same STOP point).

## Next

Per session-2 guide section 9's stop-point list: phase 4.2's baseline gate
(`docs/checkpoints/phase-4.2.md`) is the actual STOP -- read that checkpoint for
the gate results and open questions before phase 4c proceeds.
