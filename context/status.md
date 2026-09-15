# CHANGE PoC — status

Last updated: 2026-09-15 (session 2, Claude Sonnet 5). **PoC complete per the guide's
own definition of done** (guide section 4), modulo the items in "What's not done"
below — all of which are the owner's call, not further coding work. This session
implemented the owner's answers to the open questions from session 1 (Q3, Q5 and
its three sub-decisions, Q6, Q7) and found/fixed three real bugs those answers
exposed along the way.

## What this is

Implementation of the CHANGE governance-loop PoC per `context/CHANGE_poc_agent_guide.md`
(the literal build spec) and `context/approach1.md` (the research plan it implements).
Repo root doubles as `change-poc` — built directly here rather than a separate nested
repo, since `context/` already held the planning docs. Branch `shreyash` (not merged to
`main` — see "What's not done").

## Where things stand

**Phases 0, 1, 2, 3, 5, 6, 7, 8 done and tagged.** Phase 4 (tau2 adapter) still not
started — still blocked on owner decisions (one of four questions from phase 1 is now
answered, see below); `docs/checkpoints/phase-4.md` documents why. Phase 9 (Harmonize,
optional) not started per the guide's own "only start if the owner says so."

`make test` (`uv run pytest -q -m "not live"`) is green: **1421 passed, 4 xfailed**
(all tests now run in one `pytest` invocation, including `test_loop.py` — no longer
needs a separate run; full suite takes ~30s).

- **Phases 0–2**: unchanged from session 1 — see prior status or `docs/checkpoints/phase-{0,1,2}.md`.
- **Phase 3** (mock environment): population revised this session (see below). `docs/checkpoints/phase-3.md`.
- **Phase 5** (Contextualize): `Snapshotter` simplified this session (see below). `docs/checkpoints/phase-5.md`.
- **Phase 6** (Anticipate): envelope baseline revised this session (see below). `docs/checkpoints/phase-6.md`.
- **Phase 7** (Generate/Sandbox/Negotiate/Evolve/loop): two real bugs found and fixed
  this session, one genuine finding documented. `docs/checkpoints/phase-7.md`.
- **Phase 8** (experiment grid + metrics): grid re-run this session at a uniform,
  publication-scale simulation setting. `docs/checkpoints/phase-8.md`.

## This session's work (owner answered Q3/Q5/Q6/Q7 from the consolidated list; implemented exactly as specified)

1. **D2/D3 mock population fix** (Q5 main, exact spec given): reweighted `_TASK_TYPES`
   to `{return:.30, exchange:.30, cancel:.15, modify:.15, lookup:.10}`, dropped
   `_WITHIN_WINDOW_PROB` to `.55`, switched D3 to `satisfaction` feedback gated on
   episode count (not turn count). Eligible-state fraction rose from 0.14 to 0.27 as
   calculated. **New finding**: the fix raised the achievable ceiling well past the
   guide's threshold, but also made the drift saturate within ~10-25 episodes instead
   of ramping across 500 — so the D2/D3 "first-vs-last-window" magnitude tests remain
   `xfail`, now for this new, correctly-diagnosed reason (not the old ceiling issue).
   Reported back; window redefinition is a modeling decision, not made unilaterally.
   `docs/checkpoints/phase-3.md`.
2. **Snapshotter simplified** to window-count-only (Q5 downstream #1): the
   memory-version-delta-10 trigger is gone; `change/loop.py` uses `Snapshotter`
   directly again instead of its old bypass. `docs/checkpoints/phase-5.md`.
3. **A0 threshold test loosened** (Q5 downstream #2): tolerates at most 1 spurious
   trigger per 20 cycles instead of demanding exactly 0 — a property of A0's
   deliberately un-debounced blunt check, not a bug. Now genuinely passes (`xfail`
   removed). `docs/checkpoints/phase-7.md`.
4. **Envelope baseline fixed to a 3-window mean** (Q5 downstream #3): fixed at the
   run's first 3 windows, not just the first window's noisy values.
   `docs/checkpoints/phase-6.md`.
5. **Two real bugs found while investigating why FULL started losing to A0** after
   the population fix (found by measuring, not assuming — `docs/checkpoints/phase-7.md`):
   - `TaskSplit`'s plain shuffle under-sampled a 40-task canary/sandbox pool, biasing
     its composition against `train`'s under the new, more sensitive population — fixed
     by stratifying on `(task_type, within_policy_window)`.
   - That stratification fix then left `train`/`canary`/`sandbox` as contiguous
     per-stratum blocks instead of interleaved (found via a byte-identical-behavior
     anomaly in the Q7 grid re-run) — fixed with a final shuffle per list.
   - `_seeded_rng` used Python's per-process-randomized `hash()`, silently breaking
     reproducibility of the loop's decision layer across runs of the same seed — fixed
     with `zlib.crc32`.
6. **Remaining FULL-vs-A0 gap under D2/D3 is a genuine, documented finding, not a bug**:
   `Evolve`'s canary gate — verified against a small (~40-task) held-out sample —
   rejects nearly every corrective candidate under the now-correctly-strong drift, on
   either `ENVELOPE_VIOLATION_MAX` or `ENVELOPE_SUCCESS_DROP_MAX` depending on the
   specific noisy canary draw, so `agent_version` rarely advances. A0's blunt,
   unverified gate has no such check and wins on raw violation count while offering no
   rollback guarantee. `test_loop.py`'s test for this is `xfail(strict)` with the full
   root cause in its reason. Owner-authorized as a documented finding.
7. **Q3 (tau2 registry) decision recorded**: register `LessonAgent` into
   `tau2.registry.registry` at import time, no vendor edits — not yet actionable,
   phase 4 still blocked on the other three phase-1 questions. `docs/checkpoints/phase-4.md`.
8. **Q7 grid re-run**: all 9 original smoke cells plus seed 1 (18 cells), one uniform
   `SIM_TRAJECTORIES=SIM_HORIZON=2000` setting (the guide's own default — this
   machine held it fine this time), sequential cell-at-a-time as before.
   `change/experiment.py` now records the effective `sim_trajectories`/`sim_horizon`
   per cell as `summary.csv` columns, confirmed uniform across all 18 rows. The
   corrected table (after the interleaving-bug fix) shows FULL with *more* cumulative
   violations than A0 under D2/D3, consistently across both seeds — this is the real,
   reproducible consequence of finding 6 above, not a settings artifact.
   `docs/checkpoints/phase-8.md`.

All of the above implemented from the owner's own specific technical instructions
(exact reweighted population values, exact D3 mechanism swap, exact test tolerances,
exact baseline-window count, exact grid scale) — nothing here was a unilateral design
choice except the two follow-on bug fixes (TaskSplit interleaving, `_seeded_rng`),
which were genuine bugs with no guide-protected constant involved.

## What's not done (owner decisions, not further coding work)

1. **Phase 4 (tau2 adapter) still not started** — Q3 (tau2 registry) is answered, but
   three of the four phase-1 questions remain open (action/state taxonomy for real
   retail tools, D3 retargeting for a status-gate policy, LLM budget/model choice).
2. **Not merged to `main`** — everything is on branch `shreyash`.
3. **Phase 9 (Harmonize) not started** — explicitly optional, owner-gated.
4. **D2/D3/Contextualize-D2 magnitude tests remain `xfail`** — not because the
   population fix failed (it worked, past the guide's own threshold), but because the
   fix's stronger drift saturates faster than a "first-window-vs-last-window"
   comparison can measure. A window-definition decision is needed if a clean pass is
   wanted here; the mock env's job (letting phases 5-8 be built and tested at zero
   cost) is otherwise unaffected.
5. **The FULL-vs-A0 comparison under D2/D3 (`test_loop.py`, phase-8 grid table) now
   shows FULL losing on raw cumulative violations**, for a well-understood, genuine
   reason (`Evolve`'s canary gate can't confirm recovery against a small sample fast
   enough under this drift severity), not a bug or settings artifact. Whether this is
   an acceptable PoC-level finding or warrants an Evolve/canary design change (larger
   canary sample, multi-cycle credit, different rollback policy) is the owner's call.

## Consolidated open questions for the owner

**From phase 1 (blocks phase 4) — Q3 now answered, three remain:**
1. How to adjust `CanonicalAction`/`CanonicalState` for retail's real tools?
2. If retargeting D3 to a status-gating policy change: what should the specific policy
   edit be?
3. ~~OK to register a custom `LessonAgent` factory into `tau2.registry.registry`?~~
   **Answered**: yes, at import time, no vendor edits.
4. Budget and model choice for the agent/user-simulator LLMs?

**From this session's new findings:**
5. Which window definition for the D2/D3/Contextualize-D2 magnitude tests, now that
   the drift saturates within ~10-25 episodes rather than ramping across 500?
   (`docs/checkpoints/phase-3.md`, `phase-5.md`.)
6. Is FULL losing to A0 on raw cumulative violations under D2/D3 (well-diagnosed:
   `Evolve`'s canary gate can't confirm recovery fast enough against a small sample)
   an acceptable PoC-level finding, or does it warrant a design change to Evolve's
   canary policy? (`docs/checkpoints/phase-7.md`, `phase-8.md`.)

**Still open, process-level:**
7. Merge `shreyash` to `main`?
8. Start phase 9 (Harmonize)?

## Environment notes for next session

- Native Windows toolchain (Git Bash + `uv`), not WSL.
- `pytest` runs the full suite (including `test_loop.py`) in one invocation now,
  ~30s — no longer needs to be run separately for timing reasons.
- `runs/` is gitignored; grid re-runs should use a fresh/cleared output directory
  (`rm -rf runs/<name>` first) to avoid the resumable `DONE`-marker mechanism silently
  reusing stale pre-fix data.
- If re-running the grid at 2000x2000: budget ~85s/cell for A0/A2, ~105s/cell for
  FULL (measured this session) — an 18-cell grid takes ~30 minutes.
- `TaskSplit` (`change/sandbox.py`) now stratifies by `env.stratify_key(task_id)` when
  the env provides one, then shuffles each resulting list — both the stratification
  *and* the final shuffle matter; removing either reintroduces a bug (composition bias
  or blocky ordering respectively) documented in `docs/checkpoints/phase-7.md`.

## Next step

Nothing is technically blocking further *mock-env* work. The meaningful next steps all
need the owner's input — see "Consolidated open questions" above, especially #5 and #6
which are new this session.
