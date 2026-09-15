# Phase 7 checkpoint

## Done
- 7.1 `change/generate.py`: `CandidateGenerator.propose` (G1 add_lesson, G2 remove_lessons, G3 approval_gate, do_nothing), `apply_candidate_to_memory_and_gates` (shared by Sandbox and Evolve). Also `CanonicalState.from_state_key` and `MockAgent` gate enforcement — `ddb29ce`
- 7.2 `change/sandbox.py`: `TaskSplit` (deterministic train/canary/sandbox), `Sandbox.run` — `74a6d13`
- 7.3 `change/negotiate.py`: `risk_tier`, `utility`, `feasible`, `supervisor_oracle`, `decide` (steps 1-7 of approach1.md 5.7), boundary expansion after `BOUNDARY_EXPAND_AFTER` consecutive escalated approvals — `b7f7c96`
- 7.4 `change/evolve.py`: `apply`, `canary`, `check_and_rollback`, `distill`, `should_distill`, `maybe_distill` — `05f6a86`, signature fix in `21c67d2` (see deviations)
- 7.5 `change/loop.py`: `GovernanceLoop` for systems A0-FULL — committed bundled with `21c67d2` (see deviations), perf fix in `1345d31`, override fix in `02f41f1`
- 7.6 `scripts/run_loop.py` — `f1f1fbd`
- 7.7 Tests — `ab777be` (sandbox, negotiate), `aeee33a` (evolve), `d0629e1` (loop)

## Smoke test output
```
$ uv run pytest -q -m "not live"
1413 passed, 3 xfailed (plus test_loop.py: 1 passed, 1 xfailed, run separately — see below)

$ uv run python scripts/run_loop.py --env mock --system A0 --condition d2 --n-episodes 1000 --seed 0 --run-id mock-a0-d2
cycle      t  violation      jsd  pred_exit   decision        candidate  version
    0     61      0.113    0.000         99     ACCEPT    approval_gate        2
    1    122      0.082    0.011         99     ACCEPT       do_nothing        2
    2    183      0.082    0.017         99     ACCEPT       do_nothing        2
    3    238      0.091    0.018         99     ACCEPT       do_nothing        2
    4    302      0.078    0.005         99     ACCEPT       do_nothing        2
    5    360      0.086    0.014         99     ACCEPT       do_nothing        2
    6    420      0.067    0.006         99     ACCEPT       do_nothing        2
    7    479      0.068    0.003         99     ACCEPT       do_nothing        2
    8    543      0.062    0.006        180     ACCEPT       do_nothing        2
    9    598      0.127    0.010         99     ACCEPT    approval_gate        3
   10    655      0.123    0.014         99     ACCEPT    approval_gate        4
   11    716      0.082    0.010         99     ACCEPT       do_nothing        4
   12    772      0.071    0.011         99     ACCEPT       do_nothing        4
   13    834      0.097    0.006         99     ACCEPT       do_nothing        4
   14    899      0.015    0.011        165     ACCEPT       do_nothing        4
   15    959      0.117    0.007         99     ACCEPT    approval_gate        5
   16   1015      0.036    0.007        315     ACCEPT       do_nothing        5
   17   1081      0.152    0.011         99     ACCEPT    approval_gate        6
   18   1139      0.138    0.019         99     ACCEPT    approval_gate        7
   19   1198      0.119    0.006         99     ACCEPT    approval_gate        8

$ uv run python scripts/run_loop.py --env mock --system FULL --condition d2 --n-episodes 1000 --seed 0 --run-id mock-full-d2
cycle      t  violation      jsd  pred_exit   decision        candidate  version
    0     61      0.113    0.000         99      DEFER       do_nothing        1
    1    152      0.082    0.011         99      DEFER       do_nothing        1
    2    303      0.033    0.017        192     ACCEPT       add_lesson        2
    3    508      0.055    0.020         99   ESCALATE       add_lesson        2
    4    668      0.031    0.005        115   ESCALATE       add_lesson        2
    5    825      0.052    0.014         99   ESCALATE       add_lesson        2
    6    972      0.050    0.006        174     ACCEPT       add_lesson        3
    7   1169      0.051    0.003         99   ESCALATE       add_lesson        3
    8   1323      0.031    0.006        766     ACCEPT       add_lesson        4
    9   1526      0.125    0.010         99      DEFER       do_nothing        4
   10   1670      0.123    0.014         99      DEFER       do_nothing        4
   11   1833      0.082    0.010         99   ESCALATE       add_lesson        5
   12   2000      0.071    0.013         99   ESCALATE       add_lesson        5
   13   2152      0.097    0.008        101   ESCALATE       add_lesson        6
   14   2355      0.031    0.011        496     ACCEPT       add_lesson        7
   15   2562      0.117    0.007         99      DEFER       do_nothing        7
   16   2717      0.036    0.007       None     ACCEPT       do_nothing        7
   17   2783      0.152    0.011         99      DEFER       do_nothing        7
   18   2931      0.138    0.019         99      DEFER       do_nothing        7
   19   3078      0.133    0.006         99      DEFER       do_nothing        7
```
Note cycles 3-5 (ESCALATE, ESCALATE, ESCALATE, all against the same `context:medium` key) followed by cycle 6's ACCEPT at `version 3` — visible evidence of `BOUNDARY_EXPAND_AFTER=3` boundary expansion working as designed ("trust expands with demonstrated reliability").

## Deviations from the guide

### 1. `GovernanceLoop` bypasses `Snapshotter`; uses a fixed 50-episode window directly via `build_snapshot`
Same root cause as `docs/checkpoints/phase-5.md`: `Snapshotter`'s memory-version trigger fires far more often than every 50 episodes once a lesson extractor is attached (regardless of `truth` or `satisfaction` feedback — both emit lessons often), producing noisy ~15-20-record windows. Verified this concretely breaks a *specific, load-bearing* guide requirement here: "A0 on d1 produces zero adaptations" failed at Snapshotter-driven window sizes because small-sample noise crossed `ENVELOPE_VIOLATION_MAX` under flat D1 behavior. Switched `GovernanceLoop._run_episodes_until_snapshot` to always run exactly `WINDOW_EPISODES` full episodes and build one snapshot directly (same fix already applied in `test_contextualize.py`). `Snapshotter` itself is untouched and still correctly implements its own spec (verified by its own unit test in phase 5).

### 2. `check_and_rollback` signature changed to perform the restoration itself
Originally returned only `(failed, boundary)` and pushed "restore parent memory and gates" onto the caller. Changed to take `current_memory`/`current_gates`/`parent_memory`/`parent_gates` and return `(failed, memory, gates, boundary)` — matches the guide's literal phrasing ("restore parent memory and gates") and makes the restoration directly unit-testable (`test_rollback_restores_exact_lesson_ids_and_gates`). `change/loop.py` updated to match.

### 3. `sim_trajectories`/`sim_horizon` are explicit `GovernanceLoop` constructor overrides, not read from `CHANGE_SIM_TRAJECTORIES` at test time
Guide 7.7 says to "set CHANGE_SIM_TRAJECTORIES=300 in the test." This doesn't reliably work: `change/config.py`'s constants are bound once, at first import, into every module that does `from change.config import SIM_TRAJECTORIES` (including `change/loop.py`) — and by the time a test body sets the env var, pytest's collection has typically already imported `change.loop` with the default baked in. Constructor parameters sidestep the ordering problem entirely.

### 4. `SIM_TRAJECTORIES` alone was not enough to hit the 90s budget — `SIM_HORIZON` also needed reducing, and `TrendModel` needed a real perf fix
Profiling one FULL cycle (`cProfile`) showed `TrendModel._logits` — which called `np.clip` on a Python scalar inside a nested `for state: for action:` loop — was the dominant cost (2.7s of a 4.1s cycle at horizon=200), not `simulate()`'s own trajectory loop. This meant reducing `n_traj` alone barely helped: the per-time-step Python/numpy call overhead doesn't shrink with fewer trajectories, so a large `SIM_HORIZON` dominated regardless. Fixed by precomputing `(state x action)` slope/intercept/residual_std arrays in `fit()` and doing one vectorized clip per `predict`/`predict_sample` call instead of one per cell (~2x speedup measured at full 2000x2000 scale: 11.6s -> 5.7s). `test_loop.py` also reduces `sim_horizon` to 200 (guide only mentioned trajectories). With both fixes, `test_loop.py` runs in ~73s, under the 90s budget.

### 5. `test_a0_on_d1_produces_zero_adaptations` is `xfail(strict)`
Deterministic (seed 0) statistical near-miss, not a bug: `WINDOW_EPISODES=50`-episode windows are only ~55-90 records; combined with `MockAgent`'s own ~5% baseline noncompliance rate (the "totally noncompliant" branch of its base policy, guide 3.3), binomial sampling noise occasionally pushes a window's `violation_rate` just over `ENVELOPE_VIOLATION_MAX=0.10` even under flat D1 behavior with zero real drift. At seed 0 this happens once in 20 cycles (cycle 0 above: `violation=0.113`, the very first window). All the constants involved (`WINDOW_EPISODES`, `ENVELOPE_VIOLATION_MAX`, `MockAgent`'s 5% rate) are guide-protected, so there is no tuning lever available — this is the same *family* of finding as the phase-3/5 xfails (small-sample noise against a fixed threshold) though a distinct instance of it, not literally the same root cause.

### 6. Commit discipline slip
`change/loop.py` (step 7.5) was committed bundled together with the `check_and_rollback` signature fix (deviation 2) in commit `21c67d2`, instead of getting its own `feat(loop): governance loop for systems A0 to FULL` commit. Content is correct and complete; only the commit boundary is off. Flagging per the checkpoint's own honesty requirement rather than rewriting session-local history to hide it.

## Open questions for owner
Same as phases 3/5 (D2/D3 mechanism tuning, `docs/checkpoints/phase-3.md`) — unaffected by phase 7's own findings, which are new instances of the same general "guide-protected constants + finite sample sizes -> occasional threshold false positives" pattern rather than new open decisions. No new questions requiring owner input from this phase.

## Next
Guide 7.6 mandates a **STOP** here: "Owner decides whether to run the live D2 sanity gate (plan section 3.3) now. Budget for that gate: 300 episodes with `run_episodes.py --env tau2 --feedback satisfaction`. Do not run it without approval." This also remains blocked on the phase-1 open questions (retail's real tool/action taxonomy) since a live tau2 run needs `envs/tau2/lesson_agent.py` (phase 4), not yet built.

Phase 8 (experiment grid and metrics) is next and, like phase 7, only needs the mock env — not blocked by phase 1 or the D2/D3 tuning question, though (as before) the grid's headline numbers will look more convincing once D2/D3 is resolved.

## Revision (owner-authorized, this session)

**Deviation 1 above (bypassing `Snapshotter`) is superseded**: `Snapshotter`'s dual trigger was simplified to window-count-only (`docs/checkpoints/phase-5.md` "Revision"), so `GovernanceLoop` now uses `Snapshotter` directly again — the reason to bypass it no longer exists.

**`test_a0_on_d1_produces_zero_adaptations` renamed to `test_a0_on_d1_produces_at_most_one_spurious_adaptation`**, tolerating up to 1 trigger instead of demanding exactly 0, and its `xfail` marker removed (now genuinely passes). A single-window false alert on a ~5% baseline noncompliance rate is an inherent property of A0's blunt single-window threshold check — deliberately *not* debounced, since debouncing A0 specifically would bias the A0-vs-FULL comparison in FULL's favor. `false_alert_rate` (`change/metrics.py`) is the metric that actually reports this rate.

**Two real, independent bugs found and fixed while investigating why the phase-3 population fix made `test_full_reduces_cumulative_violations_vs_a0_on_d2` fail outright** (FULL: 92 violations vs. A0: 58 — FULL *worse*):

1. **`TaskSplit` (`change/sandbox.py`) sampling bias.** Each `task_id` has a *fixed* spec (task_type, within_policy_window, etc.) assigned once at `MockRetailEnv` construction — task content doesn't vary episode to episode. `TaskSplit`'s plain shuffle-and-slice into train(320)/canary(40)/sandbox(40) has real sampling noise in a pool this small: measured eligible-state fraction (`task_type in {return,exchange} and not within_policy_window`) swings +/-0.10-0.15 around the ~0.27 population value across seeds (e.g. seed 0: train 0.209, sandbox 0.375). Under the old, weaker population this bias was invisible (small absolute effect); under the corrected population it was large enough that `Sandbox.run`'s `violation_rate` — measured on a systematically harder-than-live 40-task sample — ran above `live_violation` almost every cycle, so `supervisor_oracle`'s guide-literal `sandbox.violation_rate < live_violation` check (guide 7.3, unchanged) rejected nearly every `ESCALATE`, regardless of candidate quality. **Fixed by stratifying `TaskSplit` on `env.stratify_key(task_id)`** (new method on `MockRetailEnv`, `(task_type, within_policy_window)`) so train/canary/sandbox each get proportional representation — same `n_tasks=400`/`SANDBOX_HELDOUT_FRACTION=0.20` (both guide-protected, untouched), just no longer subject to shuffle luck. Verified: post-fix eligible fractions match within ~1-2 points across train/canary/sandbox at every seed tested (were up to 15 points apart before).
2. **`_seeded_rng` (`change/loop.py`) used Python's built-in `hash()`** on string tags (including a candidate's `candidate_id`, itself a fresh unseeded `uuid4()`) to derive part of `simulate()`'s forecasting RNG seed. `hash()` on `str` is randomized per-process (PEP 456) unless `PYTHONHASHSEED` is pinned, which it isn't anywhere in this repo/environment — confirmed directly (`hash('trend_t1')` returned three different values across three separate `python -c` invocations). This silently broke reproducibility of the loop's decision-making layer across process runs even with the same explicit `seed`, while every other seeded component (episode seeding, `TaskSplit`) stayed correctly deterministic. **Fixed** by replacing `hash(tag)` with `zlib.crc32(tag.encode())`, a stable, process-independent hash.

**With both fixed**, the same test went from 92-vs-58 (FULL worse) to a **31-vs-31 tie**, stable and reproducible across repeated runs (confirmed the crc32 fix directly: same 31/31 result on 3 separate invocations).

**Remaining tie has a third, distinct and genuine cause — documented as a finding, not fixed further** (owner-authorized): `Evolve`'s canary gate (`change/evolve.py::check_and_rollback`) rejects essentially every FULL candidate under corrected D2, not on `ENVELOPE_VIOLATION_MAX` (canary violation rate is comfortably inside it, e.g. 0.095 < 0.10) but on `ENVELOPE_SUCCESS_DROP_MAX=0.05`: canary `task_success` (~0.786, measured post-drift) falls short of `baseline_success` (~0.849, frozen at the run's first 3 windows — the phase-6 "Revision" baseline fix, pre-drift) by more than the 0.05 tolerance, so the candidate is rolled back and memory never compounds a fix. This repeats near-identically cycle after cycle (canary numbers were exactly 0.095/0.786 at cycles 3, 4, and 9 in one traced run — because each rollback restores the same pre-attempt memory, so the next cycle proposes essentially the same corrective lesson against the same starting point). **A0 has no such check at all** (`_run_simple_system` applies unconditionally, no canary/rollback) — so this is not an apples-to-apples candidate-quality comparison: under the corrected drift's severity, FULL is held to a stricter, safety-verified full-recovery bar that a single adaptation cycle genuinely can't clear, while A0's blunt gate faces no such bar and simply wins on raw violation count. `ENVELOPE_SUCCESS_DROP_MAX` and the baseline-freeze policy are left unchanged; `test_full_reduces_cumulative_violations_vs_a0_on_d2` is `xfail(strict)` with this root cause documented in its reason. This is arguably a paper-relevant nuance in its own right (safety-verified adaptation trades raw reactivity for a recovery guarantee it can't always meet in one cycle under severe drift) rather than a defect to engineer away.
