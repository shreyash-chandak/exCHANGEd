# Local model serving (session-2 guide phase 4.1)

## Decision: Ollama, not llama.cpp

Guide 4.1's primary path is llama.cpp (download a GGUF, install/build `llama-server` with
CUDA, custom launch scripts), with Ollama documented as a fallback. The owner's explicit
instruction this session was "llama.cpp first ... if not, go with ollama."

**llama.cpp was attempted and abandoned.** Concrete steps taken:
- Located a current prebuilt release: `ggml-org/llama.cpp` build `b10985` (2026-09-15),
  `llama-b10985-bin-win-cuda-13.4-x64.zip` (~150MB, matches this machine's driver-reported
  CUDA 13.3 UMD) plus its companion `cudart-llama-bin-win-cuda-13.4-x64.zip` (~423MB, CUDA
  runtime DLLs).
- Located the GGUF: `unsloth/Qwen3.5-4B-GGUF` on Hugging Face (916k downloads, well-established
  quantizer), `Qwen3.5-4B-Q4_K_M.gguf` (~2.74GB) -- Q4_K_M per the guide's stated preference.
- Started all three downloads. **Measured sustained throughput: ~8-10 KB/s**, confirmed
  across multiple methods (`curl`, `curl --retry`, PowerShell `Invoke-WebRequest`) and
  multiple attempts -- not a one-off blip. At that rate the ~3.3GB combined would have taken
  many hours. Basic connectivity itself was fine (`curl -I` to both github.com and
  huggingface.co returned instant `200 OK`); the constraint is specifically on sustained
  large-file transfer throughput in this sandboxed environment.
- Stopped the downloads, deleted the partial files, switched to Ollama per the owner's own
  fallback instruction.

**Ollama was already installed** (v0.30.7) with `qwen3.5:4b` (and `9b`/`2b`) already pulled
locally -- no download needed at all for the fallback path.

## Serving setup (what's actually running)

```
scripts/serve.sh   # bash scripts/serve.sh
scripts/serve.ps1  # powershell -File scripts\serve.ps1
```

Both just set `OLLAMA_NUM_PARALLEL=6` and `OLLAMA_KV_CACHE_TYPE=q8_0` (the guide's own
documented Ollama fallback settings, guide 4.1.4) and run `ollama serve`. Endpoint:
`http://127.0.0.1:11434` (native API) / `http://127.0.0.1:11434/v1` (OpenAI-compatible).

`.env` (gitignored, not `.env.example` -- see below):
```
CHANGE_LLM_BASE_URL=http://127.0.0.1:11434
CHANGE_LLM_MODEL=ollama_chat/qwen3.5:4b
CHANGE_AGENT_MODEL=ollama_chat/qwen3.5:4b
CHANGE_USER_MODEL=ollama_chat/qwen3.5:4b
CHANGE_EXTRACTOR_MODEL=ollama_chat/qwen3.5:4b
CHANGE_LIVE=0
CHANGE_LLM_CONCURRENCY=6
```
`.env.example` in the repo root still matches the guide's literal llama.cpp-oriented spec
(`CHANGE_LLM_MODEL=openai/qwen3.5-4b`, base url `:8080/v1`) unchanged, since that's the
intended primary setup for anyone running this on a machine/network without this session's
bandwidth constraint. This session's actual `.env` uses the Ollama values above instead.

## Thinking-disable mechanism -- measured, not assumed

Guide 4.1.3 says to find whichever mechanism actually works. Tested directly against the
running Ollama server (`qwen3.5:4b`, a hybrid-thinking model):

| mechanism | endpoint | result |
|---|---|---|
| `extra_body.chat_template_kwargs.enable_thinking=false` via litellm `openai/` provider | `/v1/chat/completions` | **did not work** -- `content` came back empty, reasoning appeared in a separate `reasoning_content` field, `max_tokens` consumed entirely by hidden reasoning |
| top-level `"think": false` in the request body | `/v1/chat/completions` (OpenAI-compat) | **did not work** -- same empty-content/reasoning-field behavior |
| top-level `"think": false` | `/api/chat` (Ollama native) | **worked** -- clean `"content": "OK"`, no reasoning field |
| `think=False` kwarg via litellm's `ollama_chat/<model>` provider | (litellm maps to Ollama's native API) | **worked** -- same clean result, confirmed through `change/llm.py::chat()` directly |

`change/llm.py::chat()` passes **both** `think=False` and the `chat_template_kwargs`
form together (harmless combination, verified) so the same call works regardless of which
provider `CHANGE_LLM_MODEL` ultimately resolves to (`openai/...` for llama-server,
`ollama_chat/...` for Ollama). It also checks the response for either a literal `<think>`
block in `content` *or* a non-empty `reasoning_content`/`reasoning` field and raises
`ThinkingLeakError` if either is present, rather than silently accepting leaked reasoning.

## Benchmark (guide 4.1.5)

`CHANGE_LIVE=1 uv run python scripts/bench_serving.py --slots 6 --max-tokens 100`, against
the Ollama setup above (`OLLAMA_NUM_PARALLEL=6`), ~4k-token prompt, up to 100-token
completions:

```
=== single-stream (N=1) ===
tokens=56 wall=4.05s tok/s=13.84 p50_latency=4.05s

=== aggregate (N=6) ===
tokens=336 wall=6.73s tok/s=49.90 p50_latency=4.06s

aggregate / single-stream ratio: 3.61x
```

**3.61x aggregate speedup, above the guide's >=3x target** -- no step-down needed.
(Single-stream token count came in under the 100-token cap because the model's completion
finished naturally, `finish_reason=stop`, not because it was truncated.)

## Ollama fallback reference (guide 4.1.4, for anyone reproducing this)

```
OLLAMA_NUM_PARALLEL=6 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve
```
Base url `http://127.0.0.1:11434/v1` (OpenAI-compatible) or `http://127.0.0.1:11434` (native,
what `ollama_chat/` uses). Model `qwen3.5:4b` (already pulled: `ollama list`).

## If picking this back up on a machine with normal bandwidth

The llama.cpp path is fully identified and ready to retry, nothing about it was found to be
broken -- only slow in this specific environment:
- `https://github.com/ggml-org/llama.cpp/releases/tag/b10985` (or a later `bNNNNN` tag --
  these are frequent CI builds, not the sparse `vX.Y.Z` tags which lack platform binaries),
  assets `llama-bNNNNN-bin-win-cuda-13.4-x64.zip` + `cudart-llama-bin-win-cuda-13.4-x64.zip`
  (match the driver's reported CUDA UMD version; this machine's driver reports 13.3, so the
  13.4 build was the closest available and should be forward-compatible).
- `https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf`
  (sha256 not recorded -- download did not complete far enough to hash; re-verify against
  the repo's own listed checksum, if any, once re-downloaded).
