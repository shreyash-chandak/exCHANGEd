# CHANGE PoC — status

Last updated: 2026-09-14 (session 1, Claude Sonnet 5).

## What this is

Implementation of the CHANGE governance-loop PoC per `context/CHANGE_poc_agent_guide.md`
(the literal build spec) and `context/approach1.md` (the research plan it implements).
Repo root doubles as `change-poc` — built directly here rather than a separate nested
repo, since `context/` already held the planning docs. Branch `shreyash`.

## Where things stand

**Phases 0, 1, 2, 3, 5, 6 done and tagged** (`phase-0-done` .. `phase-3-done`,
`phase-5-done`, `phase-6-done`; phase 4 skipped for now, see below). `make test`
(`uv run pytest -q -m "not live"`) is green: 1402 passed, 3 xfailed.

- **Phase 0** (bootstrap): repo layout, `uv` + Python 3.12 pinned, Makefile, ruff, smoke test.
- **Phase 1** (tau2 discovery, STOP): `vendor/tau2-bench` submodule pinned to `v1.0.1`.
  `docs/tau2_interfaces.md` answers all 12 discovery items. **Found three real
  mismatches between the guide's data contracts and tau2 retail's actual tools/data**
  (no refund_full/refund_partial tools, no order dates anywhere so
  `within_policy_window` can't be computed as specified, no user-stance signal in
  retail tasks) — full writeup + proposed fixes in `docs/tau2_interfaces.md`'s
  "Deviations" section and `docs/checkpoints/phase-1.md`. **Blocks phase 4.**
- **Phase 2** (data contracts + store): `change/contracts.py` (12 exported pydantic
  models + `CanonicalState`/`CanonicalAction`/`CanonicalOutcome`), `change/config.py`
  (Settings + all guide 2.4 numeric constants, env-overridable via `CHANGE_` prefix),
  `change/store.py` (JsonlStore). Fully tested, schemas exported to `schemas/`.
- **Phase 3** (mock environment): `envs/mock/{mock_env,mock_agent}.py`,
  `change/memory.py` (LessonMemory), `change/generate.py` (MockLessonExtractor),
  `scripts/run_episodes.py`. **Found two structural issues** in the guide's own
  mock-env drift design (D2's generosity mechanism has a hard mathematical ceiling
  ~8.5 points short of the required +10 point drift threshold; D3's policy-update
  test is unreliable given how `truth`-feedback lessons get generosity-tagged) —
  both proven with real measurements, not just modeling, and documented in
  `docs/checkpoints/phase-3.md` with 5 concrete options. The two blocked assertions
  are marked `xfail(strict=True)` so the suite stays green but the gap stays loud.
- **Phase 5** (Contextualize): `change/contextualize.py` (`build_snapshot`,
  `weighted_jsd`, `drift_score` with episode-level bootstrap CI and lesson
  attribution, `Snapshotter`). Fixed a genuine contradiction between guide 3.2's
  ground-truth compliance rule and its expected-action table (see phase-3 checkpoint
  item 1). One D2 assertion is `xfail` — same root cause as phase 3's D2 finding,
  now also shown to degrade Contextualize's own monotonicity test via noisy small
  windows. D1 passes cleanly. `docs/checkpoints/phase-5.md`.
- **Phase 6** (Anticipate): `change/anticipate/{trend,simulator,envelope,counterfactual}.py`
  (T1 weighted-least-squares trend model + LastValue baseline, vectorized Markov
  simulator, envelope/time-to-exit, counterfactual patching/ranking),
  `scripts/run_anticipate.py`. All tests pass (T1 beats LastValue on the D2 forecast
  test, but only marginally — same weak-signal root cause). No new open questions.
  `docs/checkpoints/phase-6.md` has the full forecast-vs-realized numbers.

## Open questions blocking further progress (owner decisions needed)

From `docs/checkpoints/phase-1.md` (blocks **phase 4**, tau2 adapter):
1. How to adjust `CanonicalAction`/`CanonicalState` for retail's real tools —
   collapse the refund actions to match retail's actual write tools, rename
   `within_policy_window` to a status-gate concept (no dates exist in retail data at
   all), keep `user_stance` as a constant `"neutral"` — or pick a different tau2
   domain (airline/telecom, not investigated) instead.
2. If retargeting D3 to a status-gating policy change (since there's no date window
   in retail): what should the specific policy edit be?
3. OK to register a custom `LessonAgent` factory into `tau2.registry.registry` at
   import time (no vendor file edits) for phase 4?

From `docs/checkpoints/phase-3.md` (does **not** block further mock-env-only work,
but the D2/D3 sanity-gate story in the paper depends on it, and now also affects
phase 5's monotonicity test and phase 6's forecast-quality numbers):
4. Which fix for the D2/D3 drift thresholds — loosen thresholds, change the sigmoid
   formula/clip bound, raise the eligible-state fraction, switch D3 to
   `satisfaction` feedback, or accept as documented limitations of the mock (real
   tau2 D2 gate in phase 4 would be the actual empirical validation)?

None of these block **phase 7** (Generate/Sandbox/Negotiate/Evolve/loop) mechanically
— it only needs the mock env, already built — but the loop's headline comparison
(does governance reduce violations vs. A0) will read a lot more convincingly once
question 4 is resolved, since the underlying drift signal it's governing is
currently weak. Recommend settling questions 1-4 before or alongside phase 7.

## Environment notes for next session

- Native Windows toolchain (Git Bash + `uv`) used throughout, not WSL — worked fine
  so far including the tau2-bench editable install. WSL (Ubuntu-26.04) available as
  fallback if something needs a POSIX environment.
- System Python is 3.14 (too new for the project's `>=3.12,<3.14` pin); `uv python
  pin 3.12` resolved it with an already-installed 3.12.10 interpreter — no action
  needed, `.python-version` is committed.
- `make` is not installed in this shell; use the `uv run ...` commands directly
  (same ones the Makefile targets wrap) — see `Makefile` for the exact commands.
- `pytest` is scoped to `testpaths = ["tests"]` in `pyproject.toml` — without this it
  collects `vendor/tau2-bench`'s own test suite and errors on missing extras
  (voice/gym/knowledge). Don't remove this.
- Zero LLM spend so far — everything through phase 6 runs offline against the mock
  env. Phase 4 is the first LIVE-gated phase (needs `CHANGE_LIVE=1` + explicit
  budget approval per `CHANGE_poc_agent_guide.md` section 0.2/4).
- The 2000x2000 simulator timing test (`test_simulator.py::test_runtime_under_30_seconds`)
  runs in ~11-12s on this machine — comfortably under the guide's 30s hard limit but
  over its "under 10s" soft target. Not worth optimizing further unless it becomes
  a bottleneck in phase 8's experiment grid.

## Next step

Two parallel options, not mutually exclusive:
1. Get owner answers to the 4 open questions above (phase 1 + phase 3/5 findings).
2. Continue unblocked implementation: **Phase 7** (`change/generate.py`'s
   `CandidateGenerator`, `change/sandbox.py`, `change/negotiate.py`,
   `change/evolve.py`, `change/loop.py`, `scripts/run_loop.py`) — the biggest
   remaining phase, ties Generate/Sandbox/Negotiate/Evolve into the A0-FULL
   governance loop comparison. Still entirely mock-env-based, no LLM spend.
