# exCHANGEd

A prototype implementation of predictive, anticipatory governance for a self-evolving agent, built on top of tau2-bench's retail domain. It instruments a lesson-memory agent that drifts as it self-evolves, models its behavior as versioned probabilistic snapshots (Contextualize), forecasts when it will leave its behavioral envelope and ranks candidate adaptations before they are deployed (Anticipate), replays candidates offline (Sandbox), and decides whether to accept, escalate, reject, or defer each adaptation (Negotiate/Evolve). Everything runs offline against a mock environment by default; real tau2/LLM runs are gated behind `CHANGE_LIVE=1`.

## Development

- `make install` — sync dependencies with uv
- `make test` — run the offline test suite
- `make test-live` — run tests marked `live` (requires `CHANGE_LIVE=1` and API keys)
- `make lint` — ruff check + format check
- `make fmt` — ruff format + autofix
