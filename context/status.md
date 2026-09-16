# CHANGE PoC — status

Last updated: 2026-09-16 (session 2 continued, Claude Sonnet 5). **Phase 4b (retail
adapter) is complete and tagged `phase-4b-done`.** Phase 4.2 (no-memory baseline gate)
ran for both domains but **both gates fail** — see `docs/checkpoints/phase-4.2.md`.
This is the guide's own explicit STOP point 3 ("owner confirms the gate"), currently
**awaiting owner input** before phase 4c (live D2 gate) proceeds. Summary:

- **Three real bugs found and fixed** getting a trustworthy retail result: the
  `retail_d3` domain variant was never actually registered (nothing imported the
  module); `_canonicalize_retail` graded write actions against the wrong order
  (picked the first reference action bearing an order_id, which is always a read
  tool, not the write action); tau2's default `evaluation_type` would have hit an
  unconfigured OpenAI call for NL_ASSERTIONS on some retail tasks (pinned to
  `ALL_IGNORE_BASIS`). All three caught live, not guessed at.
- **Baseline gate fails for both domains, for two different diagnosed reasons** (read
  from actual transcripts, not assumed): retail's 92% derail rate clusters at ~11
  turns, consistent with `max_steps=20` budget exhaustion on inherently multi-lookup
  tasks (identity auth + order lookup + product-variant checks). Refunds' 60% derail
  is the model resolving denials in plain natural language instead of calling the
  `deny_request` tool that exists specifically to make denial a gradable action —
  not a budget problem. Neither matches the guide's own 4.2.2/4.2.3 remediation menu
  (written assuming a user-simulator-side fix, which isn't the cause for either).
- Phase 4c's `LessonAgent` (memory injection, gate-forcing) and `LiveLessonExtractor`
  are built, tested (offline + a live 2-episode smoke run), and wired into
  `scripts/run_episodes.py --env tau2` as the new default path (with `--resume`
  support, verified live via an actual kill-and-resume test). Not yet run at the
  guide's full 300-episode D2 gate scale — waiting on the baseline-gate STOP above.

## History (session 2, through phase 4.1)

Session-1 PoC was complete per the original guide's definition of done. This session first implemented the owner's
answers to session 1's open questions (Q3, Q5 + sub-decisions, Q6, Q7), then the owner
supplied `context/CHANGE_poc_agent_guide-2.md` (session-2 guide, wins on conflicts with
session 1) which restated those decisions with an exact spec and added phase 4.0-4d.
**Phase 4.0 of the session-2 guide is now complete and tagged `phase-4.0-done`.**

**Post-tag verification-gate recalibration** (owner asked to dig into the grid's
FULL-underperforms-A0 finding before moving on): two real small-sample measurement
bugs found and fixed in `negotiate.py`/`evolve.py`/`counterfactual.py` (statistical
tolerance margins on point-estimate comparisons; generalized counterfactual patch
coverage). Both verified real but second-order — `test_full_reduces_cumulative_violations_vs_a0_on_d2`'s
numbers didn't change, because the deeper cause turned out to be that a single-cycle
G1 candidate genuinely isn't strong enough against this drift's engineered severity,
which Negotiate/Evolve correctly decline to accept rather than a bug. Full writeup in
`docs/checkpoints/phase-8b.md` "Verification-gate recalibration". Owner's call after
seeing this was to proceed to phase 4.1 rather than pursue further (multi-cycle
credit / stronger candidates) for now.

**Phase 4.1 (local model serving) is now also complete and tagged `phase-4.1-done`.**
llama.cpp (the guide's stated primary serving path) was attempted per the owner's
explicit instruction, then abandoned after measuring ~8-10 KB/s sustained download
throughput in this environment (not a code issue, confirmed across multiple tools and
attempts) — the ~3.3GB of binaries+model would have taken many hours. Fell back to
Ollama per the owner's own contingency instruction; it was already installed with
`qwen3.5:4b` already pulled, no download needed. `change/llm.py::chat()` works
end-to-end with thinking genuinely disabled (required `think=False` via litellm's
`ollama_chat/` provider — the guide-suggested `chat_template_kwargs` mechanism alone
did not work for Ollama, measured directly). Benchmark: 3.61x aggregate speedup at 6
parallel slots, clears the guide's >=3x target. `change/runner.py`'s bounded-
concurrency episode runner is built and unit-tested but not yet wired into a live env
(none exists until phase 4a). Full writeup in `docs/checkpoints/phase-4.1.md` and
`docs/serving.md` (includes exact llama.cpp asset names/repos to retry on
unconstrained bandwidth).

**Phase 4a (the `refunds` tau2 domain) is now also complete and tagged `phase-4a-done`.**
Built from scratch: `envs/tau2/domains/refunds/` (data model, 300-order synthetic DB,
R1-R10 policy + D3's tightened variant, tools that deliberately don't enforce policy,
an oracle verified against a 4752-combination exhaustive grid, 120 base + 30 D3 tasks),
registered into `tau2.registry.registry` at import time (Q3's pattern), plus
`envs/tau2/refunds_canonical.py` and `envs/tau2/adapter.py` (`Tau2Env`, the adapter
session 1 never got to). Two real bugs found and fixed along the way (R8's
refund-amount check used the wrong basis; task-generation coverage gaps in the random
DB population) — both caught by the exhaustive grid/coverage checks themselves, not
guessed at. **Live smoke test (5 episodes against Ollama/qwen3.5:4b) ran clean** — found
and fixed a third real issue immediately (tau2's own built-in agent/user-simulator don't
route through `change/llm.py::chat()`, so its thinking-disable fix didn't reach them;
fixed by forwarding the same mechanism through `TextRunConfig`'s `llm_args_agent`/
`llm_args_user`). The smoke run itself surfaced two genuine, worth-keeping findings (not
bugs): 3 of 5 episodes never called a write tool, two of those still scored
`reward=1.0` from tau2's DB-hash-match evaluator since the reference action doesn't
mutate the DB in a way it catches; and the oracle independently caught two real policy
violations tau2's own reward missed in both directions. Full writeup in
`docs/checkpoints/phase-4a.md` and `docs/refunds_task_samples.md`.

**STOP per the guide's own section 9** — this is a mandatory stop point. Owner reviews
`docs/refunds_task_samples.md` and the 5-episode table in `docs/checkpoints/phase-4a.md`
before phase 4.2 (no-memory baseline gate, LIVE, 50 episodes) proceeds.

## What this is

Implementation of the CHANGE governance-loop PoC per `context/CHANGE_poc_agent_guide.md`
(session-1 literal build spec), `context/CHANGE_poc_agent_guide-2.md` (session-2 guide,
adds decisions + phases 4.0-4d, wins on conflicts), and `context/approach1.md` (the
research plan both implement). Repo root doubles as `change-poc`. Branch `shreyash`
(not merged to `main`).

## Where things stand

**Session-1 phases 0, 1, 2, 3, 5, 6, 7, 8 done and tagged. Session-2 phases 4.0, 4.1,
4a, 4b done and tagged.** Phase 4.2's baseline gate ran for both domains but both
gates fail (see the summary at the top and `docs/checkpoints/phase-4.2.md`) — **STOP,
awaiting owner input** before phase 4c's 300-episode D2 gate runs at full scale.
Phase 4c's code (LessonAgent, LiveLessonExtractor, the live memory loop, `--resume`)
is built and verified live at small scale, just not run at the guide's full scale yet.

`make test` (`uv run pytest -q -m "not live"`) is green: **6220 passed, 4 xfailed**,
~30-60s for the whole suite in one invocation (2 live tests deselected: refunds and
retail 2-episode smoke).

- **Session-1 phases 0–2**: unchanged — see `docs/checkpoints/phase-{0,1,2}.md`.
- **Phase 3** (mock environment): population revised. `docs/checkpoints/phase-3.md`.
- **Phase 5** (Contextualize): `Snapshotter` simplified. `docs/checkpoints/phase-5.md`.
- **Phase 6** (Anticipate): envelope baseline revised, extracted into a shared helper.
  `docs/checkpoints/phase-6.md`.
- **Phase 7** (Generate/Sandbox/Negotiate/Evolve/loop): three real bugs found and fixed
  (two in `TaskSplit`, one in `_seeded_rng`), root cause refined further in phase 8b.
  `docs/checkpoints/phase-7.md`.
- **Phase 8 / 8b** (experiment grid + metrics): grid re-run three times this session at
  increasing scope/rigor — 18 cells (A0,A2,FULL) at 2000x2000, then the full 36-cell
  grid (all six systems) at 1000x1000 after 2000x2000 was killed twice by real
  system-wide memory pressure. `docs/checkpoints/phase-8.md`, `phase-8b.md`.
- **Phase 4.0** (session-2 guide section 1): reconciled all of session 1's Q5/Q7 work
  against the session-2 guide's exact spec (test naming, shared envelope-baseline
  helper, `--serial` flag), verified the T1-vs-LastValue STOP gate clears, ran the full
  36-cell grid. `docs/checkpoints/phase-4.0.md`, `phase-8b.md`.
- **Phase 4.1** (local model serving): Ollama fallback (llama.cpp abandoned on this
  environment's ~8-10 KB/s download throughput), `change/llm.py::chat()`, 3.61x
  concurrency speedup. `docs/checkpoints/phase-4.1.md`, `docs/serving.md`.
- **Phase 4a** (`refunds` tau2 domain): built from scratch, live smoke clean.
  `docs/checkpoints/phase-4a.md`, `docs/refunds_task_samples.md`.
- **Phase 4b** (retail adapter): collapsed canonicalization, RT1-RT3 native compliance
  rules, D3 grading switch. Three real bugs found and fixed (see summary at top).
  `docs/checkpoints/phase-4b.md`.
- **Phase 4.2** (no-memory baseline gate, both domains): both gates fail, two
  different diagnosed causes. `docs/checkpoints/phase-4.2.md`. **Current STOP.**

## Key findings this session (all reported, none silently tuned away)

1. **D2/D3 population fix works past the guide's threshold, but the drift now
   saturates in ~10-25 episodes instead of ramping across 500** — so the three
   "first-vs-last-window" magnitude tests remain `xfail`, correctly diagnosed but not
   yet resolved (needs a window-definition decision). `phase-3.md`, `phase-4.0.md`.
2. **Three real bugs found and fixed**, none guide-protected-constant issues:
   `TaskSplit`'s plain shuffle biased canary/sandbox composition (fixed: stratify by
   `(task_type, within_policy_window)`); that fix then left splits as contiguous
   per-stratum blocks instead of interleaved (fixed: shuffle each list after
   stratifying); `_seeded_rng` used Python's per-process-randomized `hash()`, breaking
   cross-run reproducibility (fixed: `zlib.crc32`). `phase-7.md`.
3. **Full 36-cell grid (`phase-8b.md`) shows governance sophistication correlating
   with *worse* raw cumulative violations under real drift**: A0 ~= A2 (best) < A3 <
   A4 ~= FULL (worst) on D2/D3. Root cause refined from the earlier (18-cell) finding:
   it's **Negotiate's `supervisor_oracle`** (present starting at A4) that's the primary
   suppressor of adaptation rate, not specifically Evolve's canary gate as previously
   attributed — A4 (Negotiate, no Evolve) already collapses adaptations to near-FULL's
   levels; Evolve mainly adds the rollback mechanism on top.
4. **Two new, previously-undiagnosed miscalibrations, visible now that A1/A2 are in
   the grid for the first time**: A1 (JSD-drift-triggered) never adapts in any of its
   6 cells — its threshold apparently never fires under the corrected population. A2
   (forecast-lead-time-triggered) over-triggers on 18-20 of ~20 cycles in every
   condition including the no-drift control, but is behaviorally inert once its fixed
   gate first applies — produces cumulative violations identical to A0's, seed for
   seed. `phase-8b.md`.
5. **The 2000x2000 grid setting got killed by real system memory pressure twice**
   (confirmed: Discord/browser/VS Code/memory-compression, never a Python process) —
   both times the whole grid was discarded and restarted at 1000x1000 per the guide's
   "do not mix" instruction, rather than resuming a partial run at a different scale.
   Final grid is uniform 1000x1000, confirmed directly in `summary.csv`.

## What's not done (owner decisions, not further coding work)

1. **Phase 4.1 (local model serving) not started** — next per the session-2 guide's
   ordering. Prerequisites checked and look favorable: GPU confirmed present (RTX
   5060 Laptop, 8GB, matches the guide's assumption), and Ollama is already installed
   with `qwen3.5:4b`/`9b`/`2b` already pulled — the guide's documented Ollama fallback
   path could be used immediately with no download, as an alternative to the
   llama.cpp/GGUF primary path.
2. **Phase 4a (refunds domain + synthetic dataset), 4.2, 4b, 4c, 4d not started** —
   all come after 4.1 in the guide's ordering, with explicit stop points along the way
   that need the owner's reply before proceeding past them (session-2 guide section 9).
3. **Not merged to `main`.**
4. **Phase 9 (Harmonize) not started** — explicitly optional, owner-gated.
5. **D2/D3/Contextualize-D2 magnitude tests remain `xfail`** (see finding 1 above) —
   session-2 guide 4.0.3 explicitly said not to tune further if still failing after the
   population fix, so left as a reported, unresolved finding.
6. **The A0-A2-vs-A3-A4-FULL cumulative-violations pattern** (finding 3 above): two
   real small-sample measurement bugs in `supervisor_oracle`/Evolve's canary check and
   counterfactual patch coverage were found and fixed (`phase-8b.md` "Verification-gate
   recalibration"), verified real, but second-order — the pattern persists because a
   single-cycle G1 candidate genuinely isn't strong enough against this drift's
   engineered severity, which Negotiate/Evolve correctly decline to accept. Not a bug
   at this point; whether to give multi-cycle credit or strengthen the candidate is a
   real design decision, not made unilaterally.
7. **A1/A2's threshold miscalibrations** (finding 4 above) are still documented but not
   fixed — `DRIFT_ALERT_JSD` and `LEAD_TIME_TRIGGER` are guide-specified and left as-is
   pending owner input.

## Consolidated open questions for the owner

**From session-1 phase 1 (blocks phase 4a/4b's tau2 canonicalization) — Q3 answered,
three remain:**
1. How to adjust `CanonicalAction`/`CanonicalState` for retail's real tools? (Mostly
   superseded by the session-2 guide's own decision to build a custom `refunds` domain
   instead of forcing retail into the original schema — retail now only needs the
   simpler "collapsed taxonomy, external control" treatment of guide phase 4b.)
2. Budget and model choice for the agent/user-simulator LLMs, beyond what session-2
   guide 4.1 already specifies (Qwen3.5 4B local)?
3. ~~OK to register a custom `LessonAgent`/domain factory into `tau2.registry.registry`?~~
   **Answered**: yes, at import time, no vendor edits — confirmed this session that
   tau2's own registry uses exactly this decorator-at-import pattern already.

**From this session's grid findings, needing a decision before phase 8's table is
paper-ready:**
4. Window definition for the D2/D3/Contextualize-D2 magnitude tests (finding 1)?
5. Now that the A0/A2-beats-A3/A4/FULL pattern is understood to be a genuine
   "single-cycle candidate too weak" limitation rather than a measurement bug (finding
   6/`phase-8b.md`) — is that an acceptable PoC-level result, or does it warrant giving
   Negotiate/Evolve multi-cycle credit for improving-but-not-yet-sufficient candidates,
   or strengthening G1's corrective candidate design?
6. Should A1's `DRIFT_ALERT_JSD` trigger or A2's `LEAD_TIME_TRIGGER` be revisited given
   they're now measurably miscalibrated (never-fires / always-fires) under the
   corrected population (finding 4)?

**Still open, process-level:**
7. Merge `shreyash` to `main`?
8. Proceed into phase 4.1 (local model serving) as the session-2 guide specifies next?

## Environment notes for next session

- Native Windows toolchain (Git Bash + `uv`), not WSL.
- GPU: NVIDIA RTX 5060 Laptop, 8GB. Ollama already installed (v0.30.7) with
  `qwen3.5:4b`/`9b`/`2b` pulled. `llama-server` not installed.
- `runs/` is gitignored; grid re-runs should use a fresh/cleared output directory
  (`rm -rf runs/<name>` first) to avoid the resumable `DONE`-marker mechanism silently
  reusing stale pre-fix data.
- This machine has hit real system-wide memory pressure during long grid runs twice
  this session (not a code issue — other running applications). If a long run risks
  memory pressure again, consider asking the owner to free memory first rather than
  immediately dropping simulation scale below what the guide specifies.
- `TaskSplit` (`change/sandbox.py`) stratifies by `env.stratify_key(task_id)` when the
  env provides one, then shuffles each resulting list — both matter, removing either
  reintroduces a documented bug (`phase-7.md`).
- `change.anticipate.envelope.baseline_from_first_windows` is the single shared
  implementation of the "mean over first 3 windows" envelope baseline — used by
  `change/loop.py` and `scripts/run_anticipate.py`; extend rather than reimplement.

## Next step

**Currently stopped at phase 4.2's baseline-gate STOP** (`docs/checkpoints/
phase-4.2.md`) — both domains' no-memory baseline gate fail, for two different
diagnosed reasons (retail: `max_steps=20` budget exhaustion on multi-lookup tasks;
refunds: the model resolves denials in text instead of calling `deny_request`).
Three questions need an answer before phase 4c's 300-episode D2 gate runs at full
scale (see `phase-4.2.md`'s "Open questions for owner" for the full context):

1. Raise `max_steps` for retail and re-run the baseline?
2. Run the guide's 4.2.2 remediation steps for refunds' violation rate despite
   derail being the bigger problem there, or accept the text-only-denial pattern
   as a documented limitation?
3. Proceed to phase 4c anyway (to see if the D2 drift signal is measurable
   regardless), or resolve this stop first?

The older phases-1-through-4.1 open questions below (Q1/Q2/Q4, window definition,
Negotiate/Evolve design, A1/A2 trigger miscalibration) are all still open too, but
are lower priority than the above right now.
