# Phase 2 checkpoint

## Done
- 2.1 `change/contracts.py`: `CanonicalState` (frozen dataclass, hashable, `state_key` property), `CanonicalAction` (str enum, 10 members per guide 2.2, kept exactly as specified even though phase 1 flagged that `refund_full`/`refund_partial` don't map cleanly onto real tau2 retail tools — the mock env and phases 2/3 use this taxonomy as originally specified; only the phase-4 tau2 adapter needs the owner's decision from the phase-1 checkpoint), `CanonicalOutcome`, and all 12 exported pydantic models (`ExperienceRecord`, `PolicyEval`, `BehavioralSnapshot`, `DriftScore`, `CellAttribution`, `Lesson`, `Candidate`, `Prediction`, `SandboxResult`, `HarmonizationConstraint`, `AdaptationDecision`, `AgentVersion`) — `f6729e6`. Also added `change/config.py` (Settings + numeric constants from guide 2.4, env-overridable via `CHANGE_` prefix so e.g. `test_loop.py` in phase 7 can shrink `SIM_TRAJECTORIES` for test speed) and `.env.example`, since contracts and everything downstream needs them.
- 2.2 `scripts/export_schemas.py` writes one JSON schema per exported model to `schemas/`; run and committed — `2c2fcd4` (+ `b2b937f` fix: the script itself was left out of that commit)
- 2.3 `change/store.py`: `JsonlStore(path)` with `append`/`iter`/`read_all`, one file per model type (`<ModelName>.jsonl`) under the run directory, orjson, single `write()` call per record for atomicity — `45ba0e1`
- 2.4 `tests/test_contracts.py` (round-trips all 12 exported models through `model_dump_json`/`model_validate_json`, and checks each `schemas/<Name>.json` matches a fresh `model_json_schema()`) and `tests/test_store.py` (appends 100 `ExperienceRecord`s, reads them back in order and byte-for-byte equal) — `f480a44`

## Smoke test output
```
$ uv run pytest -q -m "not live"      # `make` is not installed in this shell; ran the underlying command directly
.............................                                            [100%]
29 passed, 1 warning in 5.53s

$ ls schemas | wc -l
12
```

## Deviations from the guide
- `make` is not available in the Git Bash shell used for this session (Windows, no `make` on PATH). Ran the `Makefile` targets' underlying `uv run ...` commands directly instead; `Makefile` itself is unchanged and correct if `make` is installed. Flagging so future checkpoints don't imply `make test` was literally invoked.
- `CanonicalOutcome` is a plain frozen dataclass (guide only explicitly says "frozen dataclass" for `CanonicalState`; `CanonicalOutcome`'s section 2.3 doesn't specify a type). Chose a frozen dataclass for symmetry with `CanonicalState` and because it round-trips through pydantic v2 identically. Not a contract change — same fields, same names.

## Open questions for owner
Still the three from `docs/checkpoints/phase-1.md` (refund action taxonomy vs. real tau2 tools, `within_policy_window` having no date source in retail, `user_stance` having no signal in retail) — unaffected by phase 2 since `CanonicalAction`/`CanonicalState` are used here exactly as guide-specified, and phase 4 is where a decision is actually needed.

## Next
Phase 3: mock environment (`envs/base.py`, `envs/mock/mock_env.py`, `envs/mock/mock_agent.py`, `change/memory.py`, `change/generate.py` `MockLessonExtractor`, `scripts/run_episodes.py`). Does not depend on tau2, can proceed now per guide's explicit note in phase 1.
