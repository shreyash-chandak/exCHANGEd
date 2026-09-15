# Phase 4.0 checkpoint (session-2 guide, section 1)

Session-2 guide (`context/CHANGE_poc_agent_guide-2.md`) section 1 restates and extends
this session's earlier Q5/Q7 work with an exact spec. Where the earlier work already
matched, this checkpoint records the reconciliation; where it didn't (test naming, the
shared envelope-baseline helper, `--serial`, the T1-vs-LastValue STOP check, and the
grid's exact scope), this session did the additional work to match section 1 exactly.

## Done

- 4.0.1 Mock env population (`{return:.30, exchange:.30, cancel:.15, modify:.15, lookup:.10}`,
  `within_policy_window` True prob `.55`) — already matched the earlier Q5 implementation,
  commit `3fbb4d8`.
- 4.0.2 D3 `policy_update_at_episode`, `feedback=satisfaction` — already matched, commit `3fbb4d8`.
- 4.0.3 Three `xfail` markers: **do not now pass** — see "Measured numbers" below. Per
  4.0.3's own instruction ("if any still fails ... stop and report the measured numbers,
  do not tune anything else"), they remain `xfail(strict)` with the exact numbers below
  in each test's reason. Not tuned further.
- 4.0.4 Snapshotter window-count only — already matched, commit `f820115`.
- 4.0.5 `test_a0_on_d1_produces_at_most_one_adaptation` — renamed to the guide's exact
  name this session (was `..._at_most_one_spurious_adaptation`), commit `d862a3f`.
- 4.0.6 Envelope baseline from first 3 windows, implemented once and reused — the
  `change/loop.py` implementation already matched; extracted into
  `change.anticipate.envelope.baseline_from_first_windows` and wired into
  `scripts/run_anticipate.py` this session (previously used only the cutoff window's own
  noisy values). `change/metrics.py` needed no change: it only reads persisted
  `Prediction` records (already produced with the correct baseline by `change/loop.py`)
  rather than computing its own. Commit `d862a3f`.
- 4.0.7 `--sim-trajectories`/`--sim-horizon`/`--serial` flags on `scripts/run_grid.py`,
  `summary.csv` gains `sim_trajectories`/`sim_horizon` columns — commits `bdc379d`,
  `d862a3f`. Grid rerun: see below.

## Measured numbers (4.0.3)

All three, seed 0, measured directly (not estimated) after 4.0.1/4.0.2:

| test | measured | threshold | passes? |
|---|---|---|---|
| `test_d2_satisfaction_feedback_drifts_violation_rate_up` | first_100=0.230, last_100=0.280, delta=+0.050 | delta >= 0.10 | **no** |
| `test_d3_policy_update_raises_violation_rate` | block_100_200=0.240, block_200_300=0.210, delta=-0.030 | delta >= 0.05 | **no** |
| `test_d2_violation_rate_trends_up_and_last_snapshot_attributes_it` | 4/9 nondecreasing window-pairs (rates: 0.226, 0.186, 0.180, 0.250, 0.169, 0.176, 0.246, 0.170, 0.346, 0.159) | >= 7/9 | **no** |

This is not the same failure as before 4.0.1/4.0.2. The population fix worked as
designed: the achievable *ceiling* is now well past every threshold above (the D2
violation rate alone reaches 0.346 in one window, more than 3x the pre-fix ceiling).
The problem now is *timing*, not magnitude: with the eligible-state fraction raised to
0.27, even one matching retrieved lesson meaningfully moves `MEMORY_TOP_K`-averaged
generosity, so the drift mechanism saturates within roughly 10-25 episodes instead of
ramping gradually across the full window. By the time any of these tests take their
"first vs last" or "pairwise monotonic" measurement, the signal is already at its noisy
saturated plateau, not still rising — so a comparison designed to detect a *rise* no
longer measures one. Full detail and the exact reasoning in each test's `xfail` reason;
root-caused in `docs/checkpoints/phase-3.md` and `phase-5.md` "Revision" sections. A
window-definition decision (not a further population or formula change) would be needed
to make these pass; not made unilaterally, per 4.0.3's own instruction not to tune
further.

## T1 vs LastValue (STOP point 1, section 9)

`test_t1_forecast_beats_last_value_baseline_on_mock_d2`: T1 error 0.2082, LastValue
error 0.2233, **margin 0.0151** (target_actual=0.2778, t1_pred=0.0696, lv_pred=0.0545).
This is clear of the guide's 0.005 STOP threshold (up from the pre-population-fix
margin of ~0.0004) — **not stopping**, proceeding with the rest of phase 4.0 and beyond.
Both models still substantially underestimate the realized rate at this horizon (the
D2 mechanism's saturation-then-noisy-plateau dynamic, same root cause as above, makes
the true trajectory harder to forecast than a steadily-ramping one would be) but T1's
relative edge over LastValue is now real and reproducible, not noise-level.

## Grid rerun (4.0.7)

In progress at the time of writing this checkpoint: `A0,A1,A2,A3,A4,FULL` x `d1,d2,d3`
x seeds `0,1`, 1000 episodes, uniform `SIM_TRAJECTORIES=SIM_HORIZON=2000` (tried first
per the guide; this machine has historically hit memory pressure at similarly low free
memory before, per `docs/checkpoints/phase-8.md`, so if this run is killed it will be
restarted in full at 1000x1000 rather than mixed, per 4.0.7's instruction). 36 cells
expected in `runs/grid-mock-v2/summary.csv`. Table and figures to follow once complete;
`phase-4.0-done` will be tagged once this is confirmed.
