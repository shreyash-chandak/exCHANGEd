#!/usr/bin/env bash
# Start local Qwen3.5 4B serving (session-2 guide 4.1.2/4.1.4).
#
# Primary path (llama.cpp) was attempted this session and abandoned: this
# environment's download throughput to GitHub/Hugging Face was measured at
# ~8-10 KB/s sustained (multiple methods, multiple retries) -- the ~570MB of
# llama-server binaries plus the ~2.7GB GGUF would have taken many hours.
# See docs/serving.md. Using the guide's own documented Ollama fallback
# instead: OLLAMA_NUM_PARALLEL=6, OLLAMA_KV_CACHE_TYPE=q8_0, already-pulled
# qwen3.5:4b, served on Ollama's OpenAI-compatible endpoint at :11434/v1.
#
# Usage: bash scripts/serve.sh
set -euo pipefail

if ! command -v ollama >/dev/null 2>&1; then
    echo "ollama not found on PATH -- see docs/serving.md" >&2
    exit 1
fi

export OLLAMA_NUM_PARALLEL=6
export OLLAMA_KV_CACHE_TYPE=q8_0
echo "starting ollama serve (OLLAMA_NUM_PARALLEL=6, OLLAMA_KV_CACHE_TYPE=q8_0) ..."
exec ollama serve
