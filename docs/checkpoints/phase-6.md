# Phase 6 checkpoint

## Done
- 6.1 `change/anticipate/trend.py`: `TrendModel` (per-(state,action) weighted least squares of logit(p) on window midpoint t, weight = n_action count, `TREND_MIN_SNAPSHOTS`/zero-weight fallback to slope 0 + last-value intercept, `predict`/`predict_sample` with clip + softmax renormalization), `LastValueModel` baseline — `e59c167`
- 6.2 `change/anticipate/simulator.py`: vectorized discrete-time Markov chain (`simulate`), `SimOutput`. One `predict_sample` call per time step (shared across all trajectories, matching the guide's literal phrasing), fully vectorized action/outcome sampling via a precomputed `(states x actions)` lookup built once per snapshot, transition sampling grouped by the small number of distinct `(state, action)` pairs actually realized at each step (not per-trajectory) — `c412033`
- 6.3 `change/anticipate/envelope.py`: `Envelope` (rolling violation/success/cost via an expanding-then-fixed-window mean, `first_exit`, `margin`), `make_prediction` — `39c0946`
- 6.4 `change/anticipate/counterfactual.py`: `patch_from_sandbox`, `rank` — `f5204f4`
- 6.5 Tests — `f6270d2`
- 6.6 `scripts/run_anticipate.py` — `4bcb92a`

## Smoke test output
```
$ uv run pytest -q -m "not live"
1402 passed, 3 xfailed, 1 warning in 12.78s

$ uv run python scripts/run_episodes.py --env mock --feedback satisfaction --n 1000 --seed 0 --run-id mock-d2-1k
[... 20 blocks, violation rate trending from ~0.14 up to ~0.20-0.26 ...]
done: 1000 episodes written to runs\mock-d2-1k

$ uv run python scripts/run_anticipate.py --run-id mock-d2-1k --at-t 400
cutoff snapshot: mock-d2-1k-snap-361 (window_end_t=361)
realized exit t (from actual records): 364

model: LastValue
  predicted exit t: q10=99 q50=149 q90=383 (metric=success)
  top contributing cells:
    modify|processed|high|1|neutral|t0 | refund_full: +0.0000
    modify|processed|high|1|neutral|t0 | refund_partial: +0.0000
    modify|processed|high|1|neutral|t0 | exchange: +0.0000

model: T1 (trend)
  predicted exit t: q10=99 q50=151 q90=394 (metric=success)
  top contributing cells:
    lookup|delivered|mid|1|neutral|t4plus | lookup: +0.6694
    modify|pending|low|1|neutral|t0 | modify: +0.5885
    return|processed|low|1|neutral|t0 | refund_full: +0.5514
```

## Forecast vs. realized (guide's requested comparison for this checkpoint)
- **Realized**: the actual records after the cutoff (t=361) crossed the envelope at t=364 — almost immediately.
- **Both models' q50 (~149-151) badly underestimate** how soon the crossing actually happened; **both q90 (~383-394) are much closer** to the realized 364. Both models forecast the breach coming via the **success** metric first, not violation — a side effect of using the cutoff window's own success_rate (a single ~60-episode-window estimate, so somewhat noisy) as the Envelope baseline; not a bug, but a real limitation of a single-window baseline that a future iteration could stabilize (e.g. average success rate over the first few windows).
- T1 and LastValue give nearly identical q10/q50 here (99 vs 99, 149 vs 151) and only mildly diverge at q90 (383 vs 394) — consistent with `test_anticipate_mock_d2.py`'s finding (T1 beats LastValue by only ~0.0004 absolute error at seed 0): this early in a run (cutoff at only 7 snapshots), most trend cells are still in the `TREND_MIN_SNAPSHOTS` fallback regime, so T1 and LastValue mostly agree. This is expected to sharpen once the D2 mechanism itself produces a stronger, more separable signal — see the phase-3/5 open question.

## Deviations from the guide
None requiring owner sign-off. Implementation choices made within normal engineering discretion (documented for transparency):
- **Cost sampling**: `BehavioralSnapshot` has no per-(state,action) cost breakdown (only a window-level `mean_cost`), so the simulator applies `snapshot.mean_cost` uniformly per simulated step regardless of state/action, rather than a state/action-conditioned cost. Sufficient for the PoC's cost-ratio envelope check; a future iteration could add a per-cell cost table to the snapshot contract if finer cost forecasting is needed.
- **Ramp-up guard in `first_exit`**: added a rule ignoring the first `SIM_ROLLING_WINDOW - 1` steps when searching for an envelope breach, since the expanding-window rolling estimate is unstable on very few samples (an early unlucky single violation could otherwise trigger a spurious immediate "exit" at t=0). Not specified either way by the guide; a defensible general-purpose robustness fix, verified against the guide's own `test_envelope.py` step-change scenario (crossing detected at t=742, within the required [700, 800] range).
- **Envelope baseline source**: `scripts/run_anticipate.py` sources `baseline_success`/`baseline_cost` from the cutoff snapshot itself (single window, ~50-90 records) since the guide doesn't specify a source. As seen above, this makes the baseline somewhat noisy in the 1k-episode smoke test, which is why "success" (not "violation") is the metric that trips first. Worth revisiting once Phase 7's loop has a settled convention for what "baseline" means across a full governance run.

## Open questions for owner
None new. Same as phases 3/5 (D2/D3 mechanism tuning) — expected to improve this phase's forecast quality once resolved, not required to unblock further phases.

## Next
Phase 7: Generate (CandidateGenerator), Sandbox, Negotiate, Evolve, and the governance loop tying A0-FULL together. Also not blocked by the phase-1 tau2 questions (mock env only) or the phase-3/5 D2 tuning question, though the loop's qualitative story (does governance actually reduce violations vs. A0) will be more convincing once that's resolved.

## Revision (owner-authorized, this session)

**Envelope baseline is now the mean over the first 3 windows of a run, fixed thereafter** — not just the cutoff/first window's own (noisy) values, addressing the "Envelope baseline source" limitation noted above. Implemented in `change/loop.py::GovernanceLoop._update_envelope`. This is a real improvement (a 3-window mean is materially less noisy than a 1-window estimate) but also, downstream in phase 7's Evolve gate, exposed a new dynamic once the phase-3 population fix made drift genuinely stronger: a baseline frozen *before* drift sets in can end up meaningfully higher than what's achievable *during* drift, even after a correct partial fix — see `docs/checkpoints/phase-7.md` "Revision" for the resulting finding in `test_full_reduces_cumulative_violations_vs_a0_on_d2`.
