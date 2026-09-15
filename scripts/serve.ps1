# Start local Qwen3.5 4B serving (session-2 guide 4.1.2/4.1.4).
#
# Primary path (llama.cpp) was attempted this session and abandoned: this
# environment's download throughput to GitHub/Hugging Face was measured at
# ~8-10 KB/s sustained -- the ~570MB of llama-server binaries plus the
# ~2.7GB GGUF would have taken many hours. See docs\serving.md. Using the
# guide's own documented Ollama fallback instead.
#
# Usage: powershell -File scripts\serve.ps1
$ErrorActionPreference = "Stop"

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Error "ollama not found on PATH -- see docs\serving.md"
    exit 1
}

$env:OLLAMA_NUM_PARALLEL = "6"
$env:OLLAMA_KV_CACHE_TYPE = "q8_0"
Write-Host "starting ollama serve (OLLAMA_NUM_PARALLEL=6, OLLAMA_KV_CACHE_TYPE=q8_0) ..."
& ollama serve
