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

## Not fixed further

Per this session's established pattern (and the owner's own prior instruction to
document rather than keep tuning), none of A1's non-triggering, A2's over-triggering,
or Negotiate/Evolve's near-total suppression under D2/D3 were adjusted to make this
table look better. `ENVELOPE_VIOLATION_MAX`, `DRIFT_ALERT_JSD`, `LEAD_TIME_TRIGGER`,
and `supervisor_oracle`'s comparison are all guide-specified and left as-is. Whether
any of these thresholds should be revisited given the corrected (stronger) drift
population is an open question for the owner, not a unilateral fix.

## Tag

`phase-4.0-done` tagged after this checkpoint, per session-2 guide section 1's
instruction ("Tag `phase-4.0-done`. Checkpoint must include...").
