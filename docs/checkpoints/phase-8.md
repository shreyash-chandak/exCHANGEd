# Phase 8 checkpoint

## Done
- 8.1 `change/metrics.py`: `lead_time`, `false_alert_rate`, `forecast_error` (re-fits both twin models per snapshot per horizon and compares to the realized later snapshot), `exit_time_error_and_coverage`, `attribution_hit`, `counterfactual_fidelity` (predicted-vs-realized violation at +250, Spearman rank correlation between predicted margin and sandbox-observed violation when >=3 candidates were sandboxed), `governance_metrics` (cumulative_violations, final_success_rate, adaptations_count, unnecessary_adaptation_rate, rollbacks, boundary_expansions), `compute_metrics(run_dir)` — `d6e7dbe`. Required a small prerequisite fix to `change/loop.py` (persisting the decided `Candidate` each cycle — `a9a2fa5`) since candidates were otherwise ephemeral and a run dir couldn't recover which kind a decision applied.
- 8.2 `change/experiment.py` (`run_cell`, `run_grid`, resumable via a `DONE` marker + cached `metrics.csv.json`), `scripts/run_grid.py` — `e08354f`. Refactored `scripts/run_loop.py` to import `CONDITIONS`/`default_agent_factory` from `change/experiment.py` instead of keeping its own copy.
- 8.3 `scripts/make_figures.py`: figure 1 (violation over t, A0 vs FULL on d2, predicted-exit lines), figure 2 (forecast error vs horizon, T1 vs last value), figure 3 (cumulative violations bar chart by system x condition), `table1_summary.md` — `70075da`
- 8.4 Tests — `8cd6eb2` (metrics), `9d99ca5` (experiment, including a real resume test that corrupts a completed cell's underlying data and confirms a resumed run reads the cache rather than trying to regenerate it)

## Smoke test output
```
$ uv run pytest -q -m "not live"
1420 passed, 3 xfailed, 1 warning in 20.80s

$ uv run python scripts/run_grid.py --env mock --systems A0,A2,FULL --conditions d1,d2,d3 --seeds 0 --n-episodes 600 --out runs/grid-mock-smoke
9 cells written to runs/grid-mock-smoke/summary.csv

$ uv run python scripts/make_figures.py --grid runs/grid-mock-smoke
wrote figures and table1_summary.md to runs\grid-mock-smoke
```

**Table 1** (means over seeds — n_seeds=1 throughout, this smoke test only ran seed 0):

| system | condition | n_seeds | cumulative_violations | final_success_rate | adaptations_count | rollbacks | boundary_expansions | lead_time |
|---|---|---|---|---|---|---|---|---|
| A0 | d1 | 1 | 32.000 | 0.787 | 1.000 | 0.000 | 0.000 | 0.000 |
| A0 | d2 | 1 | 63.000 | 0.738 | 3.000 | 0.000 | 0.000 | 0.000 |
| A0 | d3 | 1 | 27.000 | 0.803 | 0.000 | 0.000 | 0.000 | - |
| A2 | d1 | 1 | 31.000 | 0.787 | 12.000 | 0.000 | 0.000 | 594.000 |
| A2 | d2 | 1 | 63.000 | 0.738 | 12.000 | 0.000 | 0.000 | 0.000 |
| A2 | d3 | 1 | 26.000 | 0.770 | 11.000 | 0.000 | 0.000 | - |
| FULL | d1 | 1 | 32.000 | 0.803 | 3.000 | 0.000 | 0.000 | 1609.000 |
| FULL | d2 | 1 | 78.000 | 0.738 | 4.000 | 0.000 | 0.000 | 0.000 |
| FULL | d3 | 1 | 27.000 | 0.833 | 1.000 | 0.000 | 0.000 | - |

## Deviations from the guide

### The smoke test grid is not a fair A0-vs-FULL comparison as run — see below before reading `FULL | d2`'s 78 violations
Partway through this smoke test the machine this session runs on hit severe system-wide memory pressure (from other, unrelated processes — confirmed via `Get-CimInstance Win32_OperatingSystem`, free memory dropped from ~2.1GB to ~0.6GB across the run, with no `python`/`uv` process anywhere in the top-10 by working set). The `run_grid.py` process was killed by the OS three times while running the `FULL` cells specifically (the expensive ones — do-nothing forecasts plus per-candidate sandbox+forecast each triggered cycle). **The resumable design handled this correctly**: each retry picked up exactly where it left off via the `DONE` marker (verified concretely, not just in the synthetic pytest test — `A0`/`A2`'s 6 cells and `FULL_d1` survived across kills; only the incomplete cell needed re-running each time). To get the remaining two `FULL` cells (`d2`, `d3`) to complete reliably under the memory pressure, they were run individually with reduced `sim_trajectories=300, sim_horizon=200` (same reduction guide 7.7/`test_loop.py` already uses), while `A0`/`A2` and `FULL_d1` had already completed at the full default 2000x2000 scale before the pressure hit.

**Consequence**: the table above mixes forecast quality/scale between systems within the same "d2"/"d3" columns — `FULL`'s `d2`/`d3` cells forecast with a coarser twin model (300 trajectories, horizon 200) than `A0`/`A2`'s `d2`/`d3` cells (2000/2000) or than `FULL`'s own `d1` cell. This is almost certainly why `FULL | d2` shows *more* cumulative violations (78) than `A0 | d2` (63) here — not evidence that governance doesn't help. **The properly controlled comparison is `test_loop.py::test_full_reduces_cumulative_violations_vs_a0_on_d2`** (phase 7), which runs A0 and FULL with *matched* `sim_trajectories=300, sim_horizon=200` for both systems on the same seed, and passes: FULL has strictly lower cumulative violations than A0 there. Treat that test, not this smoke test's table, as the validated claim. Re-running this smoke test grid on a machine with more headroom (or with matched reduced settings for every cell) would very likely fix the apparent inversion; not done here since the pytest suite already carries the real claim and re-running is a memory-availability problem, not a code correctness one.

### Everything else
No other deviations. `metrics.py`'s `lead_time` sign convention (`exit_t - trigger_t`, positive = anticipated early) reads more naturally than guide 8.1's literal "trigger minus exit" phrasing and matches approach1.md section 7.3's "positive is good" framing — implemented the latter, noted inline in the docstring.

## Open questions for owner
None new from this phase's own logic. See the consolidated list (all phases) delivered at the end of this session.

## Next
Per guide 7.6/8.3: **the PoC is complete at this point** (guide's own words). `docs/checkpoints/phase-0.md` through `phase-8.md` all exist (phase 4's documents why it was skipped, matching the guide's definition-of-done checklist item as closely as an un-run phase can). Tags `phase-0-done` through `phase-3-done`, `phase-5-done` through `phase-8-done` exist; **no `phase-4-done` tag** since nothing in phase 4 was actually completed (tagging it would misrepresent that). Phase 9 (Harmonize, two real agents) is explicitly optional and owner-gated — not started, per guide's own instruction ("Only start if the owner says so").

Remaining before this branch could be considered a finished PoC delivery (not "phase 8 done," but the guide's full "definition of done" checklist):
- `make lint`/`make test` green **on `main`** — this work is all on branch `shreyash`; nothing has been merged. Merging is a decision for the owner, not something to do unilaterally.
- The phase-4 live tau2 smoke test (5 real episodes) — blocked on the phase-1 questions plus a budget/model decision, `CHANGE_LIVE=1` gated either way.

## Revision (owner-authorized, this session)

Q7 (owner): re-run the smoke-test grid with one uniform simulation setting across every cell, plus seed 1, since a table mixing scales (the original memory-pressure situation described above) "can't go anywhere near the paper." Re-ran all 9 original cells (A0, A2, FULL x d1, d2, d3, seed 0) plus seed 1 (18 cells total) at the guide's own default `SIM_TRAJECTORIES=SIM_HORIZON=2000` uniformly — this machine held it fine this time (no repeat of the earlier memory pressure), ~30 minutes total, cells run sequentially one at a time as `run_grid.py` already does. `change/experiment.py::run_cell` now writes the *effective* `sim_trajectories`/`sim_horizon` into each cell's metrics, so `summary.csv` carries them as columns — confirmed uniform (2000/2000) across all 18 rows.

This re-run directly surfaced the `TaskSplit` interleaving bug documented in `docs/checkpoints/phase-7.md` "Revision" (found because `A0` on `d1` vs `d2` at seed 0 came out byte-identical in the first attempt, which shouldn't happen) — fixed, and the grid was re-run a second time after the fix. The table below is from the corrected run.

**Table 1** (means over seeds, n_seeds=2 throughout — matches `docs/checkpoints/phase-8.md`'s own smoke-test cell count, guide 8.4):

| system | condition | n_seeds | cumulative_violations | final_success_rate | adaptations_count | rollbacks | boundary_expansions |
|---|---|---|---|---|---|---|---|
| A0 | d1 | 2 | 30.000 | 0.703 | 1.000 | 0.000 | 0.000 |
| A0 | d2 | 2 | 74.000 | 0.661 | 6.000 | 0.000 | 0.000 |
| A0 | d3 | 2 | 83.000 | 0.640 | 8.500 | 0.000 | 0.000 |
| A2 | d1 | 2 | 29.000 | 0.703 | 11.500 | 0.000 | 0.000 |
| A2 | d2 | 2 | 74.000 | 0.661 | 11.000 | 0.000 | 0.000 |
| A2 | d3 | 2 | 83.000 | 0.640 | 11.000 | 0.000 | 0.000 |
| FULL | d1 | 2 | 31.000 | 0.763 | 4.500 | 0.000 | 0.000 |
| FULL | d2 | 2 | 107.000 | 0.703 | 1.500 | 1.000 | 0.000 |
| FULL | d3 | 2 | 147.000 | 0.659 | 1.500 | 0.500 | 0.000 |

**Reading this honestly, not selectively**: D1 (no real drift) is a near-wash across all three systems, as expected. Under D2 and D3, **FULL has *more* cumulative violations than A0**, not fewer — consistent across both seeds (d2: 44 vs 66 and 104 vs 148 per-seed; d3: 53 vs 77 and 113 vs 217 per-seed) and consistent with `test_loop.py::test_full_reduces_cumulative_violations_vs_a0_on_d2`'s own xfail finding. This is **not** the settings-mismatch artifact the original smoke test's table showed (this run is uniformly 2000x2000, confirmed via the `sim_trajectories`/`sim_horizon` columns) — it is the real, reproducible consequence of `docs/checkpoints/phase-7.md`'s "Revision" finding: `Evolve`'s canary gate, verified against a small (~40-task) held-out sample, rejects nearly every corrective candidate FULL proposes under the corrected drift severity (sometimes on `ENVELOPE_VIOLATION_MAX`, sometimes on `ENVELOPE_SUCCESS_DROP_MAX`), so `agent_version` rarely advances and FULL's own `rollbacks` count (1 and 0.5 mean, vs A0's 0) shows the safety net actively firing rather than sitting idle. A0's blunt, unverified gate has no such check and simply applies every trigger, winning on raw violation count while offering no rollback guarantee at all.

**This table should not be read as "governance doesn't help" — it should be read as "this specific greedy, single-shot corrective-candidate design, verified against a canary sample this small, cannot outrun this severity of drift in one cycle."** `test_loop.py`'s properly-diagnosed root cause (phase-7.md) is the validated explanation for this table now, not a settings artifact to wave away as before. Whether this is acceptable as a documented PoC-level finding, or whether it warrants a design change (e.g. a larger canary sample, multi-cycle credit for a still-improving-but-not-yet-fully-recovered candidate, or a different Evolve policy) is the owner's call — flagging it plainly rather than tuning canary/Evolve parameters to make the table look better.
