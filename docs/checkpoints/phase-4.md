# Phase 4 checkpoint

## Done
Nothing. Phase 4 (tau2 adapter, live instrumentation) was not started this session.

## Smoke test output
N/A — not started.

## Deviations from the guide
None — this is a deliberate skip, not a deviation. Phase 1's STOP (`docs/checkpoints/phase-1.md`) explicitly required owner sign-off before phase 4 could start, and per guide section 0.2 the coding agent "does not guess through" a stop-and-ask trigger. The trigger fired for real: three genuine mismatches between the guide's `CanonicalAction`/`CanonicalState` contracts and tau2 retail's actual tools/data were found in phase 1 (no `refund_full`/`refund_partial` tools exist; there are no order dates anywhere in retail's data so `within_policy_window` cannot be computed as specified; retail tasks carry no `user_stance` signal). Building `envs/tau2/{retail_canonical,lesson_agent,adapter}.py` and `LiveLessonExtractor` against contracts that don't match the real tool surface would mean guessing at a fix the owner hasn't approved, or silently reducing scope — both explicitly forbidden by guide section 0.2.

Phases 5-8 were built and fully validated against the mock environment in the meantime (guide's own note at the end of phase 1: "Phases 2 and 3 do not depend on tau2 and may proceed while waiting" — extended here to phases 5-8, none of which touch tau2 either).

## Open questions for owner
See the consolidated list at the end of this session's summary (also `context/status.md`). Specifically for phase 4:
1. How to adjust `CanonicalAction`/`CanonicalState` for retail's real tools (collapse refund actions, redefine `within_policy_window` as a status gate, keep `user_stance` constant) — or pick a different tau2 domain instead.
2. If retargeting D3 to a status-gating change: what should the specific policy edit be?
3. OK to register a custom `LessonAgent` factory into `tau2.registry.registry` at import time (no vendor file edits)?
4. Budget and model choice for the agent/user-simulator LLMs (plan section 7.4/11) — needed before any `CHANGE_LIVE=1` script can run at all.

## Next
Once the owner answers the above: `envs/tau2/retail_canonical.py` (canonicalization functions using the confirmed tool mapping), `envs/tau2/lesson_agent.py` (memory injection + gate support), `envs/tau2/adapter.py` (`Tau2RetailEnv`), `change/generate.py`'s `LiveLessonExtractor`, then the LIVE smoke test (5 retail episodes, `CHANGE_LIVE=1`, owner inspects). Everything downstream of phase 4 (a real `envs.tau2` `Env` implementation) is otherwise a drop-in replacement for `MockRetailEnv` in `GovernanceLoop`/`scripts/run_loop.py`/`scripts/run_grid.py` — no other phase's code should need to change.

## Revision (owner-authorized, this session)

Question 3 above is answered: **register the `LessonAgent` factory into `tau2.registry.registry` at import time from `envs/tau2/lesson_agent.py`, no vendor file edits.** Recorded here for when phase 4 actually starts — not yet actionable, since questions 1/2/4 above remain open and phase 4 is still blocked on them.
