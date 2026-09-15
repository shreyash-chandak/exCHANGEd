# exCHANGEd

A prototype implementation of predictive, anticipatory governance for a self-evolving agent, built on top of tau2-bench's retail domain. It instruments a lesson-memory agent that drifts as it self-evolves, models its behavior as versioned probabilistic snapshots (Contextualize), forecasts when it will leave its behavioral envelope and ranks candidate adaptations before they are deployed (Anticipate), replays candidates offline (Sandbox), and decides whether to accept, escalate, reject, or defer each adaptation (Negotiate/Evolve). Everything runs offline against a mock environment by default; real tau2/LLM runs are gated behind `CHANGE_LIVE=1`.

See `context/CHANGE_poc_agent_guide.md` for the full build spec, `context/status.md` for current progress and open questions, and `docs/checkpoints/phase-*.md` for a per-phase record of what was built and every deviation from the guide.

## Install

```bash
uv sync
git submodule update --init --recursive   # pulls vendor/tau2-bench
cp .env.example .env                        # fill in model names before any --live work
```

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/); it will use the pinned Python 3.12 automatically (`.python-version`).

## Run the mock experiment grid in one command

```bash
uv run python scripts/run_grid.py \
  --env mock --systems A0,A1,A2,A3,A4,FULL --conditions d1,d2,d3 --seeds 0,1 \
  --n-episodes 1000 --out runs/grid-mock

uv run python scripts/make_figures.py --grid runs/grid-mock
```

This runs entirely offline against the mock retail environment — zero LLM spend. `run_grid.py` is resumable: a cell whose run dir already has a `DONE` marker is skipped and its cached metrics are reused, so a killed/interrupted grid can just be re-run. Results land under `runs/<out>/<system>_<condition>_seed<seed>/` (one dir per grid cell — `ExperienceRecord.jsonl`, `BehavioralSnapshot.jsonl`, `Prediction.jsonl`, `AdaptationDecision.jsonl`, `SandboxResult.jsonl`, `AgentVersion.jsonl`, `task_split.json`, `metrics.csv.json`), with `runs/<out>/summary.csv` (one row per cell, every metric) and, after `make_figures.py`, three PNGs plus `table1_summary.md` in the grid's top-level directory.

Smaller pieces can also be run individually — see `scripts/run_episodes.py` (Contextualize/mock-env only), `scripts/run_anticipate.py` (Anticipate forecast vs. realized), and `scripts/run_loop.py` (single system/condition governance loop with a per-cycle printout).

## Live gating

Everything above is offline (`--env mock`). Real tau2-bench runs and any LLM call are gated behind `CHANGE_LIVE=1` and are not implemented in this PoC yet (blocked on the open questions in `context/status.md` — tau2 retail's real tools don't map cleanly onto the guide's original `CanonicalAction` taxonomy). `make test-live` runs the `live`-marked test suite once that phase lands; until then it has nothing to run. Never run a `--live` script without `CHANGE_LIVE=1` set explicitly and, per `context/CHANGE_poc_agent_guide.md` section 0.2, the owner's sign-off on that phase's budget.

## Development

- `make install` — sync dependencies with uv
- `make test` — run the offline test suite (`tests/test_loop.py` is slow — ~75s — and usually run separately: `uv run pytest -q tests/test_loop.py`)
- `make test-live` — run tests marked `live` (requires `CHANGE_LIVE=1` and API keys)
- `make lint` — ruff check + format check
- `make fmt` — ruff format + autofix
