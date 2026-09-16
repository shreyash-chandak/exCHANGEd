# Phase 4d checkpoint (session-2 guide, grid sizing + live governance-loop wiring)

## Done

Guide 4d.1/4d.2 as literally specified, plus additional scope the owner asked
for beyond the guide's own text: wiring the full governance loop (Contextualize/
Anticipate/Generate/Sandbox/Negotiate/Evolve) against a live tau2 domain, not
just sizing the eventual grid. Rationale (owner, 2026-09-16): batch all
remaining live compute into one final session rather than have more design
decisions interrupt an unsupervised run later.

- **`envs/tau2/domains/refunds_d3.py`**: registers a genuine `refunds_d3` tau2
  domain (mirrors `retail_d3.py`). Found live while starting this work: D3's
  `policy_version="v3"` previously only reached the oracle's grading -- the
  agent's own system prompt always showed the base policy text, since neither
  `run_episode`'s `TextRunConfig` path nor `run_live_episode`'s
  `build_environment(domain)` path had a way to pass `policy_version` through.
  Commit `d3c9292`.
- **`Tau2AgentHandle` / `tau2_agent_factory`** (`envs/tau2/adapter.py`): an
  `Agent`-protocol stand-in carrying `memory`/`gates`. Every call site in
  `change/loop.py`, `change/sandbox.py`, `change/evolve.py` already shares the
  identical pattern `agent = agent_factory(memory, gates, rng); env.run_episode
  (task_id, agent, seed)`, written once generically for `MockAgent` -- supplying
  `Tau2Env` + `tau2_agent_factory` instead of `MockRetailEnv` +
  `default_agent_factory` makes the entire existing governance loop work
  against a live tau2 domain with **zero changes** to any of those three
  modules. `Tau2Env.run_episode` dispatches to the live memory-injecting path
  (`run_live_episode`) when given a `Tau2AgentHandle`, tau2's built-in
  `llm_agent` otherwise. Commit `d3c9292`.
- **D3 episode-gated policy flip + `stratify_key`** (`Tau2Env`): mirrors
  `MockRetailEnv`'s own `policy_update_at_episode` mechanism (same task pool
  throughout, policy silently tightens mid-run) and `stratify_key` (lets
  `TaskSplit` stratify train/canary/sandbox instead of a plain shuffle, same
  rationale as the mock env's own documented bug). Commit `8dca5f9`.
- **`change/experiment.py`**: `run_cell`/`run_grid` gain `env`/`domain`
  selectors via a new `_build_env_and_agent_factory` helper, gated on
  `CHANGE_LIVE=1` for the tau2 path. Commit `b6c92d0`.
- **`scripts/run_grid.py`**: `--env tau2 --domain refunds|retail` now works
  (was a hard `raise` before). Commit `b1a5e7f`.
- **19 offline tests** (`tests/test_tau2_governance_wiring.py`,
  `tests/test_experiment_tau2_selector.py`): dispatch logic, D3 flip, domain
  name resolution, `stratify_key`, and the experiment selector, all verified
  without live model calls via stubbing. Commit `f326fb3`.
- **`docs/grid_plan.md`** (guide 4d.1): sizing only, no live grid run. ~39,750
  episodes, ~294 hours at measured sequential throughput -- exceeds the guide's
  120h threshold by ~2.45x, cut list proposed (recommended: seeds 2->1 + halve
  episodes/cell brings it to ~74h without dropping any guide-specified
  system/condition/domain). Commit `afc9a3b`.
- **Resume-under-kill verified live** (guide 4d.2's explicit ask): a real
  kill-and-resume test on `scripts/run_episodes.py --env tau2 --resume`
  (6-episode run, killed after 1 completed, resumed, confirmed 6 distinct
  episodes / 46 records / monotonic unique `t_global`, no duplicates). Done
  earlier this session as part of building `--resume` support (commit
  `e9768f4`), reused here rather than repeated.
- **Offline construction sanity check**: `GovernanceLoop` + `Tau2Env` +
  `tau2_agent_factory` construct cleanly with no live calls (`__init__` never
  runs an episode) -- `TaskSplit` produces a sensible 95/13/12
  train/canary/sandbox split for refunds using the new `stratify_key`.

## Deviations from the guide

### Scope expanded beyond guide 4d's literal text, at owner's explicit request
The guide's own 4d.2 only asks for a `--domain` flag and a resume-verification
test on `run_grid.py`. It does not anticipate that `GovernanceLoop`/`Sandbox`/
`evolve` were built exclusively against the mock env's per-turn `agent.act(obs)`
callback model, fundamentally different from tau2's whole-episode orchestration
(flagged as a real architectural gap back in phase 4a's own checkpoint). Wiring
that gap shut was a larger undertaking than the guide's two-bullet text implies
-- done here because the owner wants everything ready to run in one batched
session rather than hit this gap mid-run later.

### The live smoke test (a genuine full governance cycle against tau2) was deferred
Offline construction is verified (no crashes, sensible splits), but no live
episode has actually been run through `GovernanceLoop`+`Tau2Env` yet -- doing so
meaningfully (enough cycles to exercise Sandbox/Negotiate/Evolve, not just
Contextualize/Anticipate which run every cycle regardless of trigger) needs
~150 real episodes, ~30-60 minutes. Owner's explicit call (2026-09-16): defer
this to the final "run everything" session rather than spend more time now.
**This means the tau2 governance-loop wiring is unverified end-to-end against a
real model** -- offline tests cover the dispatch/selection logic, but not
whether e.g. `Sandbox.run`'s candidate replay, `evolve.canary`, or
`evolve.distill` actually produce sane results against live tau2 data. Given
this session already found 3+ real integration bugs on first live contact with
simpler pieces of this same codebase (retail_d3 registration, order-extraction,
the NL_ASSERTIONS paid-model path), **treat the first live run of this wiring
as likely to surface at least one more bug**, not a formality.

## Open questions for owner

1. Retail's live-grid-loop throughput (LessonAgent + satisfaction question) is
   unmeasured -- `docs/grid_plan.md`'s 46s/episode figure is a proxy from the
   no-memory baseline, likely an underestimate.
2. Which cut (if any) from `docs/grid_plan.md`'s list to apply before running
   the real grid, given the ~294h estimate exceeds 120h by ~2.45x.
3. Whether to wire `change/runner.py`'s concurrency primitive into the live
   grid path before the final run -- not attempted this session, flagged as
   the highest-leverage lever to reduce wall time without cutting scope.

## Next

Per owner's stated plan: batch the remaining live work (phase 4c's D2 gate
resume to completion, the live governance-loop smoke test, sizing confirmation,
and the real grid itself, possibly cut per `docs/grid_plan.md`) into one
session when the owner can dedicate the time. All code is built, tested
offline, and committed -- nothing further to build without running something
live first.
