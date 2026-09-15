# Phase 8b checkpoint (session-2 guide 4.0.7)

Full 6-system x 3-condition x 2-seed grid (`A0,A1,A2,A3,A4,FULL` x `d1,d2,d3` x `0,1`),
1000 episodes/cell, superseding the earlier 9-cell and 18-cell (`A0,A2,FULL` only)
partial grids in `docs/checkpoints/phase-8.md`. This is the first time A1/A3/A4 have
been run through the full grid at all.

## Deviation: 1000x1000, not 2000x2000

Guide 4.0.7 says try 2000x2000 first. Two separate attempts at 2000x2000 were killed
by real system-wide memory pressure (confirmed via `Get-Process`: Memory Compression,
Discord, browser processes, VS Code, and this session's own Claude process were the
top memory consumers both times -- no Python process was ever near the top, so this is
not a leak or regression in the grid code). Per 4.0.7's instruction ("if any cell is
killed, restart the whole grid at 1000x1000, do not mix"), the partial 2000x2000 run
was discarded in full and restarted uniformly at 1000x1000. That run **also** got
killed once (8/36 cells, same non-code cause), discarded again, and the third attempt
(uniform 1000x1000 throughout) completed cleanly: 36/36 cells, confirmed uniform
`sim_trajectories=sim_horizon=1000` in every row of `summary.csv` (checked directly,
not assumed). Recorded here as an explicit, owner-visible deviation from the guide's
preferred-first setting, not a silent downgrade.

## Table 1 (means over 2 seeds)

| system | condition | n_seeds | cumulative_violations | final_success_rate | adaptations_count | rollbacks | boundary_expansions |
|---|---|---|---|---|---|---|---|
| A0 | d1 | 2 | 51.0 | 0.743 | 1.0 | 0.0 | 0.0 |
| A0 | d2 | 2 | 122.5 | 0.619 | 11.0 | 0.0 | 0.0 |
| A0 | d3 | 2 | 139.5 | 0.625 | 13.5 | 0.0 | 0.0 |
| A1 | d1 | 2 | 54.5 | 0.866 | 0.0 | 0.0 | 0.0 |
| A1 | d2 | 2 | 204.5 | 0.620 | 0.0 | 0.0 | 0.0 |
| A1 | d3 | 2 | 216.5 | 0.711 | 0.0 | 0.0 | 0.0 |
| A2 | d1 | 2 | 50.0 | 0.743 | 19.0 | 0.0 | 0.0 |
| A2 | d2 | 2 | 122.5 | 0.619 | 18.5 | 0.0 | 0.0 |
| A2 | d3 | 2 | 139.5 | 0.625 | 19.5 | 0.0 | 0.0 |
| A3 | d1 | 2 | 54.5 | 0.866 | 14.0 | 0.0 | 0.0 |
| A3 | d2 | 2 | 149.0 | 0.657 | 17.0 | 0.0 | 0.0 |
| A3 | d3 | 2 | 209.0 | 0.705 | 17.0 | 0.0 | 0.0 |
| A4 | d1 | 2 | 54.5 | 0.866 | 9.5 | 0.0 | 0.0 |
| A4 | d2 | 2 | 200.0 | 0.620 | 1.5 | 0.0 | 0.0 |
| A4 | d3 | 2 | 258.5 | 0.639 | 1.0 | 0.0 | 0.0 |
| FULL | d1 | 2 | 54.5 | 0.866 | 9.0 | 0.0 | 0.0 |
| FULL | d2 | 2 | 204.5 | 0.620 | 1.0 | 0.5 | 0.0 |
| FULL | d3 | 2 | 268.5 | 0.577 | 1.5 | 0.5 | 0.0 |

Figures (`figure1_violation_over_t.png`, `figure2_forecast_error.png`,
`figure3_cumulative_violations.png`) written to `runs/grid-mock-v2/` alongside this
table (not committed, `runs/` is gitignored).

## Reading this plainly

**D1 (control) is correctly a near-wash**: 50-55 cumulative violations and comparable
success rates across all six systems -- no system is meaningfully triggering on flat,
non-drifting behavior (except A2, see below), which is the expected/correct result for
a control condition.

**Under real drift (D2/D3), raw cumulative violations get *worse*, close to
monotonically, as governance sophistication increases**: A0 ~= A2 (best) < A3 < A4 ~=
FULL (worst). FULL posts the single worst d3 number of any system (268.5, vs A0's
139.5) despite having the most safety machinery in the pipeline. This confirms and
generalizes the finding from the smaller grids in `docs/checkpoints/phase-8.md` and
`phase-7.md` -- it isn't specific to FULL, it's a pattern across the whole A3-A4-FULL
lineage.

**Two additional, previously-undiagnosed findings from A1 and A2, now visible with the
full system set in the grid for the first time:**

1. **A1 (drift-triggered, JSD-gated) never adapts -- 0 adaptations in all 6 cells**,
   including under D2/D3 where real drift is present and other systems detect and
   react to it. A1's trigger is `drift.jsd_weighted > DRIFT_ALERT_JSD`
   (`change/loop.py::_run_simple_system`); this never fires under the corrected
   population. A1 behaves as pure do-nothing and posts the second-worst D2/D3 numbers
   of any system (204.5, 216.5) as a direct consequence -- worse than A0's blunt
   violation-threshold trigger, worse than A3, on par with A4/FULL despite doing
   nothing at all to reach that outcome. Not root-caused further this session; noted
   as a finding, same "report rather than guess" pattern as elsewhere in this project.
2. **A2 (forecast-lead-time-triggered) over-triggers massively -- 18-20 of ~20 cycles
   in every single condition, including D1** (no real drift) -- yet produces
   *cumulative violations and success rates identical to A0's, seed for seed* (e.g.
   A2/A0 d2 seed0: both 95 violations, 0.6154 success; d2 seed1: both 150, 0.6226).
   Not a bug: A2 applies the same fixed `approval_gate` candidate A0 does
   (`_g3_gate_candidate`), and once applied it stays applied -- redundant re-triggers
   are behaviorally inert, just noisy in the decision log. Distinct miscalibration
   from A1's "never fires": A2's `first_exit_t_q50 - window_end_t <= LEAD_TIME_TRIGGER`
   condition is apparently satisfied almost every cycle regardless of actual drift.

**Refining the phase-7 "Revision" root cause**: that checkpoint attributed FULL's
under-performance to Evolve's canary gate specifically. This grid shows the dominant
suppression happens one layer earlier, in **Negotiate**, which A4 also uses (FULL =
A4 + Evolve): A3 (candidate generation + simple ranking, no Negotiate) applies 14-19
of ~20 attempts; A4 (adds `negotiate_decide`'s boundary controller + supervisor
oracle) collapses to 0-10, nearly identical to FULL's 0-9 in every matching cell.
Evolve (FULL-only) adds `rollbacks` (0.5 mean on d2/d3, vs A4's 0) but barely changes
the adaptation *count* Negotiate already suppressed. So: **Negotiate's
`supervisor_oracle` (`sandbox.violation_rate < live_violation`, guide 7.3, literal and
unchanged) is the primary bottleneck**, not specifically Evolve's canary check --
Evolve adds an additional, mostly-redundant safety layer on top of an already-heavily-
filtered candidate stream. Both draw on the same small (~40-task) held-out sample
noise problem documented in `phase-7.md`.

## Not fixed further (at the time of tagging `phase-4.0-done`)

Per this session's established pattern (and the owner's own prior instruction to
document rather than keep tuning), none of A1's non-triggering, A2's over-triggering,
or Negotiate/Evolve's near-total suppression under D2/D3 were adjusted to make this
table look better at the time this checkpoint's grid was tagged. `ENVELOPE_VIOLATION_MAX`,
`DRIFT_ALERT_JSD`, `LEAD_TIME_TRIGGER`, and `supervisor_oracle`'s comparison were all
guide-specified and left as-is pending owner input. See "Verification-gate
recalibration" below for what changed after the owner reviewed this table.

## Tag

`phase-4.0-done` tagged after this checkpoint, per session-2 guide section 1's
instruction ("Tag `phase-4.0-done`. Checkpoint must include...").

## Verification-gate recalibration (owner-authorized, same session)

After reviewing this table the owner asked to dig into whether Negotiate/Evolve's
suppression of A3-FULL's adaptation rate was itself a fixable calibration bug before
moving on to phase 4.1. Two real, distinct measurement bugs were found and fixed:

1. **`negotiate.supervisor_oracle` and `evolve.check_and_rollback` compared small-
   sample point estimates as if exact.** `sandbox.violation_rate < live_violation`
   (guide 7.3's literal formula) and the canary check against
   `ENVELOPE_VIOLATION_MAX`/`ENVELOPE_SUCCESS_DROP_MAX` both treat a single noisy
   measurement (sandbox: ~`SANDBOX_TASKS_PER_CANDIDATE` tasks; canary: similar) as
   ground truth. Fixed with `negotiate.one_sided_margin` -- a one-sigma
   normal-approximation tolerance band added to both sides of each comparison,
   computed from the known sample sizes, not an arbitrary threshold loosening.
   `ENVELOPE_VIOLATION_MAX`, `ENVELOPE_SUCCESS_DROP_MAX`, and `SUPERVISOR_SUCCESS_TOL`
   themselves are untouched.
2. **`counterfactual.patch_from_sandbox` only patched the exact states the sandbox
   sample happened to visit.** Traced directly: in one cycle, the live snapshot had
   13 drift-relevant ("eligible") states but the ~25-task sandbox sample covered only
   4 of them -- the other 9 kept the forecast model's un-patched, still-drifting
   prediction, even though a lesson-based candidate's real live mechanism
   (`LessonMemory.retrieve`'s partial-match tier) generalizes across every state
   sharing `(task_type, within_policy_window)`. Fixed by generalizing the sandbox's
   observed distribution to every snapshot state sharing the category the candidate's
   own live mechanism would actually reach (`add_lesson`/`remove_lessons` by
   `(task_type, within_policy_window)`; `approval_gate` by `(value_bucket,
   within_policy_window)`) -- mirroring the real generalization rule, not an
   arbitrary broadening.

**Both fixes are real, individually verified** (traced specific cycles where a
decision or margin measurably changed -- e.g. one candidate that previously rolled
back now sticks at `agent_version=2` for the rest of the run; margins shifted from
-0.08 to -0.05 and from 0.00 to +0.01 in traced cycles), and neither touches a
guide-protected constant.

**But their aggregate effect on `test_full_reduces_cumulative_violations_vs_a0_on_d2`
is second-order**: cumulative violations at the test's settings are unchanged, 66
(FULL) vs 44 (A0), before and after both fixes. Digging into why: even with full
category-generalized patching, `envelope_margin_q50` for the D2 corrective candidate
remains meaningfully negative in most cycles (e.g. -0.05, -0.02) -- meaning the
forecast is *correctly* predicting that a single G1 corrective lesson
(`_CORRECTIVE_LESSON_GENEROSITY=-0.4`, diluted against accumulated +1.0-generosity
lessons via `MEMORY_TOP_K` averaging) genuinely is not strong enough to pull the
trajectory back under `ENVELOPE_VIOLATION_MAX` within one forecast horizon, given how
strong D2's drift was deliberately engineered to be (`docs/checkpoints/phase-3.md`).

**Reframed conclusion**: two genuine measurement-noise bugs existed and are now
fixed, but the dominant remaining cause of A3-FULL's under-performance is not
measurement noise -- it's that a single-cycle candidate of this design genuinely
can't outrun this drift severity, and Negotiate/Evolve are correctly declining to
claim an insufficient fix as successful. A0 only wins because it faces no such
verification bar at all, not because its fix is actually better. Going further
(giving multi-cycle credit for a candidate that's improving but not yet fully
recovered, or strengthening G1's corrective magnitude) would be a real design change,
not a bug fix -- left for the owner to decide; not made unilaterally. The owner's
decision after this investigation was to proceed to phase 4.1 rather than pursue this
further for now.
