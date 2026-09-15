"""Serving throughput benchmark (session-2 guide 4.1.5): single-stream vs.
aggregate tok/s and p50 latency at N=1 and N=slots concurrent requests,
each with a ~4k token prompt and a 300 token completion."""

from __future__ import annotations

import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import typer

from change.llm import chat

app = typer.Typer(add_completion=False)

# ~4000 tokens of filler (roughly 4 chars/token for English prose).
_FILLER_SENTENCE = (
    "The quick brown fox jumps over the lazy dog near the riverbank at dusk. "
)
_PROMPT = _FILLER_SENTENCE * 250  # ~4000 tokens


def _one_request(max_tokens: int) -> tuple[float, int]:
    """Returns (elapsed_seconds, completion_tokens)."""
    messages = [
        {
            "role": "user",
            "content": (
                f"Summarize the following text in one sentence:\n\n{_PROMPT}"
            ),
        }
    ]
    start = time.monotonic()
    response = chat(messages, temperature=0.0, max_tokens=max_tokens)
    elapsed = time.monotonic() - start
    completion_tokens = response.get("usage", {}).get("completion_tokens", max_tokens)
    return elapsed, completion_tokens


def _run_batch(n: int, max_tokens: int) -> dict:
    with ThreadPoolExecutor(max_workers=n) as pool:
        start = time.monotonic()
        results = list(pool.map(lambda _: _one_request(max_tokens), range(n)))
        wall = time.monotonic() - start

    latencies = [r[0] for r in results]
    total_tokens = sum(r[1] for r in results)
    return {
        "n": n,
        "wall_seconds": wall,
        "total_tokens": total_tokens,
        "aggregate_tok_s": total_tokens / wall if wall > 0 else 0.0,
        "p50_latency_s": statistics.median(latencies),
    }


@app.command()
def main(
    slots: int = typer.Option(6, help="concurrent request count for the aggregate run"),
    max_tokens: int = typer.Option(300, "--max-tokens"),
) -> None:
    typer.echo(f"prompt length: ~{len(_PROMPT.split())} words (~4k tokens target)")

    typer.echo("\n=== single-stream (N=1) ===")
    single = _run_batch(1, max_tokens)
    single_tok_s = single["total_tokens"] / single["wall_seconds"]
    typer.echo(
        f"tokens={single['total_tokens']} wall={single['wall_seconds']:.2f}s "
        f"tok/s={single_tok_s:.2f} p50_latency={single['p50_latency_s']:.2f}s"
    )

    typer.echo(f"\n=== aggregate (N={slots}) ===")
    agg = _run_batch(slots, max_tokens)
    typer.echo(
        f"tokens={agg['total_tokens']} wall={agg['wall_seconds']:.2f}s "
        f"tok/s={agg['aggregate_tok_s']:.2f} p50_latency={agg['p50_latency_s']:.2f}s"
    )

    ratio = agg["aggregate_tok_s"] / single_tok_s if single_tok_s > 0 else 0.0
    typer.echo(f"\naggregate / single-stream ratio: {ratio:.2f}x (target >= 3x, floor 2x)")
    if ratio < 2.0:
        typer.echo(
            "ratio below 2x -- guide 4.1.5 says try -np one lower and re-run once "
            "(restart scripts/serve.sh with a smaller slot count)"
        )


if __name__ == "__main__":
    app()
