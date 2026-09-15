# Phase 4.1 checkpoint (session-2 guide, local model serving)

## Done

- 4.1.1 Model provenance researched and recorded (`docs/serving.md`): llama.cpp build
  `b10985` CUDA 13.4 assets identified, `unsloth/Qwen3.5-4B-GGUF` Q4_K_M identified. Download
  attempted, abandoned on measured ~8-10 KB/s sustained throughput (not a code issue --
  connectivity itself was fine, only large-file transfer was constrained). Commit `10eb7cd`.
- 4.1.2 `scripts/serve.sh`/`serve.ps1` written and syntax-verified. Serve **Ollama**, not
  llama-server, per the owner's own fallback instruction once llama.cpp's download proved
  impractical in this environment -- `OLLAMA_NUM_PARALLEL=6 OLLAMA_KV_CACHE_TYPE=q8_0 ollama
  serve` (guide's own documented Ollama fallback settings, 4.1.4). Commit `10eb7cd`.
- 4.1.3 `change/llm.py::chat()` -- single litellm entrypoint, thinking disabled. Required two
  iterations: the guide-suggested `chat_template_kwargs.enable_thinking=False` alone did not
  actually disable thinking through Ollama (measured: empty `content`, reasoning leaked into
  a separate `reasoning_content` field, consuming the whole token budget) -- litellm's
  `ollama_chat/` provider's own `think=False` kwarg was what worked. Both are now passed
  together (verified harmless combination), and the leak check covers both the `<think>`-tag
  and separate-reasoning-field cases. Commits `e905ff6`, `d3120f9`.
- 4.1.4 `.env.example` matches the guide's exact llama.cpp-oriented spec unchanged (for
  anyone running the primary path on unconstrained bandwidth); this session's actual `.env`
  (gitignored) uses Ollama-adjusted values, documented in `docs/serving.md`.
  `change/config.py` gains `llm_base_url`/`llm_model`/`llm_concurrency`. Commit `561bf0d`.
- 4.1.5 `scripts/bench_serving.py` -- single-stream vs. aggregate tok/s and p50 latency. Run
  live, see benchmark table below. Commit `734dd39`.
- 4.1.6 `change/runner.py::run_concurrent_episodes`/`write_episode_records` -- bounded
  ThreadPoolExecutor, completion-order yielding, t_global assigned sequentially at write
  time. Not wired into `scripts/run_episodes.py`'s mock path (`MockRetailEnv` mutates shared
  per-instance counters inside `run_episode`, never designed for concurrent calls on one
  instance, and doesn't need concurrency anyway -- it's fast and synchronous). Infrastructure
  for phase 4a/4b's live env; unit-tested against a fake env (3 tests, all passing) since no
  live env exists yet to exercise it end-to-end. `ExperienceRecord` gains `task_id`/
  `episode_seed` fields (guide-authorized, 4.1.6's own text). Commit `f33e9c7`.

## Smoke test output

```
$ uv run pytest -q -m "not live"
1425 passed, 4 xfailed, 1 warning in ~70s

$ curl http://127.0.0.1:11434/api/version
{"version":"0.30.7"}

$ CHANGE_LIVE=1 uv run python -c "from change.llm import chat; print(chat([{'role':'user','content':'Say OK'}]))"
... choices[0].message.content == "OK", no reasoning_content, no <think> block

$ CHANGE_LIVE=1 uv run python scripts/bench_serving.py --slots 6 --max-tokens 100
=== single-stream (N=1) ===
tokens=56 wall=4.05s tok/s=13.84 p50_latency=4.05s

=== aggregate (N=6) ===
tokens=336 wall=6.73s tok/s=49.90 p50_latency=4.06s

aggregate / single-stream ratio: 3.61x
```

**3.61x aggregate speedup at 6 parallel slots** -- clears the guide's >=3x target, no
step-down to fewer slots needed.

## Deviations from the guide

### llama.cpp (the stated primary serving path) was attempted and abandoned for Ollama
Full detail in `docs/serving.md`. Summary: this environment's download throughput to
GitHub/Hugging Face was measured at ~8-10 KB/s sustained, confirmed across multiple tools
(`curl`, `curl --retry --retry-all-errors`, PowerShell `Invoke-WebRequest`) and multiple
attempts -- not a transient blip. The ~3.3GB needed (llama-server binaries + CUDA runtime +
GGUF) would have taken many hours at that rate. Owner's own instruction covered this exact
contingency ("llama.cpp first ... if not, go with ollama"), so the switch was made rather
than continuing to wait. Ollama was already installed with `qwen3.5:4b` already pulled, so
the fallback needed no download at all. Everything needed to retry llama.cpp on
unconstrained bandwidth (exact release build, exact asset names, exact GGUF repo/file) is
recorded in `docs/serving.md` "If picking this back up."

### Thinking-disable mechanism differs from the guide's suggested one
Guide 4.1.3 explicitly says to find whichever mechanism works, trying `chat_template_kwargs`
or a `/no_think` marker. Neither of those was what worked for Ollama -- `think=False` via
litellm's `ollama_chat/` provider (mapping to Ollama's native `/api/chat` `think` field) was
the one that actually disabled reasoning, measured directly (see table in `docs/serving.md`).
`change/llm.py::chat()` now sends both mechanisms together so the same call works whichever
provider `CHANGE_LLM_MODEL` resolves to.

### `change/runner.py`'s concurrency is unwired from the mock path
Not a deviation from what the guide asked for necessarily, but a design choice about scope:
the guide's 4.1.6 targets `scripts/run_episodes.py` and `change/experiment.py`. Since the
mock env is fast, synchronous, and not thread-safe across concurrent `run_episode` calls on
one instance, wiring concurrency into the mock path would be pure regression risk for zero
benefit. The primitive is built, tested, and ready for phase 4a/4b to wire into a live env
where episodes are actually slow enough to benefit.

## Open questions for owner
None new from this phase's own logic beyond what's already open (session-1
phase-1 questions 1/2/4, D2/D3 window definition, Negotiate/Evolve design, A1/A2 trigger
miscalibration -- see `context/status.md`).

## Next
Phase 4a: the `refunds` tau2-compatible domain (data model, policy, tools, oracle, tasks,
registration, canonicalization) -- the actual synthetic dataset generation work. Guide
mandates a **STOP** after 4a for the owner to read `docs/refunds_task_samples.md` and the
5-episode live smoke table before proceeding further.
