# Phase 5 checkpoint

## Done
- 5.1 `change/contextualize.py`: `build_snapshot` (Dirichlet-smoothed `p_action` over all 10 canonical actions, `p_outcome`/`p_transition` only for observed cells, `p_initial` from `turn_idx==0`), `weighted_jsd` (base-2 JSD weighted by parent state frequency), `drift_score` (episode-level bootstrap CI, top-3 cell attribution weighted by state frequency, lesson-id over-representation at a 1.5x ratio threshold, capped at 5), `Snapshotter` (dual trigger: `WINDOW_EPISODES` episodes OR memory_version delta >= 10, persists to store), `__main__` entry printing the snapshot table — `461387f`
- 5.2 `tests/test_contextualize.py` — `feb0e5f`

## Smoke test output
```
$ uv run pytest -q -m "not live"
1389 passed, 3 xfailed, 1 warning in 8.35s

$ uv run python -m change.contextualize --run-id mock-d2-smoke
id                      window               n  violation     jsd  top_cell
mock-d2-smoke-snap0     0-26                27      0.185   0.000
mock-d2-smoke-snap1     27-37               11      0.000   0.000
...
mock-d2-smoke-snap31    557-583             27      0.148   0.022  return|delivered|low|1|neutral|t0|refund_full (-0.091)
```
(32 snapshots for 500 episodes — see deviation below on why this is far more than the ~10 the guide's 5.2 test text assumes.)

## Deviations from the guide

### Snapshotter's memory-version trigger fires far more often than the guide's phase-5.2 test assumes, given how MockLessonExtractor actually behaves
`Snapshotter` (as specified: emit every `WINDOW_EPISODES` (50) episodes **or** whenever `memory_version` has changed by 10+, whichever first) is implemented exactly as written and is correct. The problem is empirical, not implementational: under D2 (`feedback=satisfaction`), `MockLessonExtractor` emits a lesson roughly every 2 episodes (positive feedback is common — any generous action always satisfies the user per guide 3.2 bullet 5, and non-generous actions still satisfy 30% of the time), so `memory_version` reaches +10 roughly every ~20-25 episodes — far faster than the intended 50-episode cadence. Running the smoke test's 500 D2 episodes through `Snapshotter` therefore produces **32 snapshots, not ~10**, each covering only ~15-27 records. This is not a bug in `Snapshotter`'s trigger logic (verified independently by `test_snapshotter_emits_on_window_and_on_memory_version_jump`, which passes cleanly on synthetic data) — it's an emergent interaction between two guide-specified mechanisms (the "10" memory-version threshold is guide-5.1 prose, not a protected section-2.4 constant; the extractor's emission rate is guide-3.5 prose).

**Consequence for guide 5.2's drift test**: `test_contextualize.py` does **not** run the D2 scenario through `Snapshotter` for the monotonicity/attribution assertion — it builds 10 fixed 50-episode windows directly via `build_snapshot`, matching the guide's literal "500 episodes / window 50 -> 9 consecutive pairs" arithmetic as closely as possible. Even with this fairer windowing, the assertion is still `xfail`: see below.

### D2 monotonicity + last-snapshot attribution assertion is `xfail(strict)` — same root cause as phase 3
`test_d2_violation_rate_trends_up_and_last_snapshot_attributes_it` is `xfail`. With 10 windows of ~50 episodes each, only 4-5 of 9 consecutive pairs are nondecreasing (measured, seed 0), short of the guide's "at least 7 of 9," and the very last window's top-3 drifted cells don't reliably include an out-of-window `refund_full` cell. This is **the same root cause already documented in `docs/checkpoints/phase-3.md`**: the generosity mechanism's `sigmoid`-clip ceiling bounds the achievable D2 drift to roughly +0.08 over 500 episodes (vs. the guide's +0.10 threshold), and that weak signal, spread over only 10 windows, is dominated by per-window sampling noise (each window is only ~50-90 records). This is not a new/independent problem — it is expected to resolve automatically once the owner's phase-3 D2 fix (whichever option they pick) is applied, so I did not spend further effort tuning Contextualize-side thresholds independently.

**D1 flatness passes cleanly**: across the same 10-window scheme, all 9 windows had `jsd_weighted` below `DRIFT_ALERT_JSD` (0.05) — well within "except at most 1."

## Open questions for owner
Same as phase 3 — the D2/D3 mechanism-tuning decision (`docs/checkpoints/phase-3.md`) now also resolves this phase's one open `xfail`. No new questions from this phase.

## Next
Phase 6: Anticipate (`change/anticipate/{trend,simulator,envelope,counterfactual}.py`). Works on `BehavioralSnapshot` sequences built by this phase; does not depend on the phase-1 tau2 mapping questions and is not expected to depend further on the D2 magnitude question either (T1 trend-fitting and the Markov simulator should work correctly regardless of how strong the underlying drift signal is — weak drift just means a longer/less certain time-to-exit forecast, which is itself a valid and reportable outcome).

## Revision (owner-authorized, this session)

**`Snapshotter` simplified to window-count only** — the memory-version-delta-10 trigger documented above (deviation 1) is removed entirely, matching what `change/loop.py` was already doing by bypassing it (`docs/checkpoints/phase-7.md` deviation 1). `change/loop.py` now uses `Snapshotter` directly again instead of its own hand-rolled window loop, since the two mechanisms are identical once the dual trigger is gone. `test_snapshotter_emits_on_window_and_on_memory_version_jump` renamed to `test_snapshotter_emits_every_window_episodes` and rewritten to assert a memory-version jump does *not* cause early emission.

The phase-3 population fix (see `docs/checkpoints/phase-3.md` "Revision") raised D2's ceiling well past the guide's threshold but also made the underlying drift saturate within ~10-25 episodes rather than ramping across 500 — so `test_d2_violation_rate_trends_up_and_last_snapshot_attributes_it` remains `xfail(strict)`, now because 50-episode windows are already at the noisy plateau by the first window, not because the signal is too weak to detect at all. See the test's updated `xfail` reason and `docs/checkpoints/phase-3.md`.
