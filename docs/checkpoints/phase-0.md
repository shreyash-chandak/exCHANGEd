# Phase 0 checkpoint

## Done
- 0.1 Repo layout created (`change/`, `envs/`, `scripts/`, `tests/`, `docs/`, `schemas/`, `vendor/`), `.gitignore` added, `context/` docs committed — `6f5c7f5`
- 0.2 `pyproject.toml` (uv, python 3.12 pinned, deps per guide), `uv sync` run, `uv.lock` committed — `d500d6d`
- 0.3 `Makefile` (install/test/test-live/lint/fmt), `tests/conftest.py` registers the `live` marker and skips it unless `CHANGE_LIVE=1` — `5ebd2dc`
- 0.4 `tests/test_smoke.py` (imports `change`), README with dev paragraph and make targets — `adac896`
- fix `ruff` was formatting/linting `context/*.md`; excluded `context/`, `docs/`, `vendor/` — `fb9b992`

## Smoke test output
```
$ make lint
All checks passed!
8 files already formatted

$ make test
.                                                                        [100%]
1 passed in 0.24s
```

## Deviations from the guide
- Built directly in the existing `CHANGE` git repo (branch `shreyash`) rather than initializing a separate fresh `change-poc` repo, since this repo already held the planning docs under `context/` and `git init` had already happened. Layout, module names, and paths otherwise match section 1 of the guide exactly.
- Native Windows toolchain (Git Bash + uv) used instead of WSL for phase 0; WSL (Ubuntu-26.04) is available as a fallback if a later dependency (e.g. tau2-bench) needs a POSIX environment. System Python is 3.14 (too new for the `>=3.12,<3.14` constraint); `uv python pin 3.12` resolved this using an already-installed 3.12.10 interpreter.
- Added `extend-exclude = ["context/", "docs/", "vendor/"]` to `[tool.ruff]` (not specified in the guide) because ruff's format/lint was reaching into the planning markdown docs.

## Open questions for owner
(none)

## Next
Phase 1: tau2 discovery (STOP at end — requires owner review of `docs/tau2_interfaces.md` item 8 and the `escalate` representation before Phase 4 can start).
