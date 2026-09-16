"""Run episodes against the mock env (guide 3.6) or, LIVE-gated, a tau2
domain through a memory-injecting LessonAgent (session-2 guide 4c),
writing ExperienceRecord/Lesson jsonl and printing a per-50-episode
violation rate table."""

from __future__ import annotations

import random
from pathlib import Path

import typer

from change.config import LIVE, MEMORY_CAP, settings
from change.generate import MockLessonExtractor
from change.memory import LessonMemory
from change.store import JsonlStore
from envs.mock.mock_agent import MockAgent
from envs.mock.mock_env import MockRetailEnv

app = typer.Typer(add_completion=False)


def _run_mock(
    feedback: str,
    n: int,
    seed: int,
    run_id: str,
    n_tasks: int,
    policy_update_at_episode: int | None,
    runs_dir: str,
) -> None:
    memory = LessonMemory(cap=MEMORY_CAP)
    agent = MockAgent(memory=memory, rng=random.Random(seed))
    mock_env = MockRetailEnv(
        n_tasks=n_tasks,
        seed=seed,
        run_id=run_id,
        policy_update_at_episode=policy_update_at_episode,
    )
    extractor = MockLessonExtractor(feedback=feedback)
    store = JsonlStore(Path(runs_dir) / run_id)

    task_ids = mock_env.task_ids()
    violation_flags: list[bool] = []

    for i in range(n):
        task_id = task_ids[i % len(task_ids)]
        episode_seed = seed * 1_000_003 + i
        result = mock_env.run_episode(task_id, agent, episode_seed)

        for record in result.records:
            store.append(record)
        violation_flags.append(not all(r.policy_eval.compliant for r in result.records))

        for lesson in extractor.extract(
            result.records, episode_id=result.records[-1].episode_id, t_global=mock_env.t_global
        ):
            memory.add(lesson)
            store.append(lesson)

        if (i + 1) % 50 == 0:
            block = violation_flags[i + 1 - 50 : i + 1]
            rate = sum(block) / len(block)
            typer.echo(f"episodes {i + 1 - 49:>4}-{i + 1:<4}: violation_rate={rate:.3f}")

    typer.echo(f"done: {n} episodes written to {Path(runs_dir) / run_id}")


def _run_tau2(domain: str, feedback: str, n: int, seed: int, run_id: str, runs_dir: str) -> None:
    """Memory-injecting path (session-2 guide 4c): drives episodes
    through LessonAgent + a live LessonMemory + LiveLessonExtractor,
    mirroring _run_mock's loop shape. This is what guide 4c.3's D2 gate
    command (`--feedback satisfaction --n 300`) needs -- tasks cycle
    when `n` exceeds the domain's task count, same as _run_mock.

    Supersedes the phase-4a/4b no-memory smoke path that used to live
    here (docs/checkpoints/phase-4a.md, phase-4b.md's exact commands) --
    those checkpoints' own text already flagged the memory-injecting
    agent as "future work, not this phase's scope", and phase 4c is that
    future work. `scripts/baseline.py` is the one still-current
    no-memory path (phase 4.2's "empty memory, no gates" baseline gate
    needs memory to never exist at all, not just start empty)."""
    import envs.tau2.domains.refunds  # noqa: F401 -- registers at import time
    from change.generate import LiveLessonExtractor
    from envs.tau2.adapter import Tau2Env

    memory = LessonMemory(cap=MEMORY_CAP)
    gates: dict = {}
    extractor = LiveLessonExtractor(feedback=feedback)
    env_obj = Tau2Env(domain=domain, run_id=run_id)
    task_ids = env_obj.task_ids()
    store = JsonlStore(Path(runs_dir) / run_id)

    violation_flags: list[bool] = []
    for i in range(n):
        task_id = task_ids[i % len(task_ids)]
        episode_seed = seed * 1_000_003 + i
        typer.echo(f"[{i + 1}/{n}] {task_id} (memory_version={memory.version}) ...")
        result = env_obj.run_live_episode(task_id, memory, gates, seed=episode_seed)

        for record in result.records:
            store.append(record)
        violation_flags.append(not all(r.policy_eval.compliant for r in result.records))

        lessons = extractor.extract(
            result.records, episode_id=result.records[-1].episode_id, t_global=env_obj.t_global
        )
        for lesson in lessons:
            memory.add(lesson)
            store.append(lesson)

        typer.echo(
            f"  {len(result.records)} records, reward={result.reward}, "
            f"violation={violation_flags[-1]}, lessons_added={len(lessons)}"
        )
        if (i + 1) % 50 == 0:
            block = violation_flags[i + 1 - 50 : i + 1]
            rate = sum(block) / len(block)
            typer.echo(f"episodes {i + 1 - 49:>4}-{i + 1:<4}: violation_rate={rate:.3f}")

    if extractor.n_parse_failures:
        typer.echo(f"lesson extractor parse failures: {extractor.n_parse_failures}")
    typer.echo(f"done: {n} episodes written to {Path(runs_dir) / run_id}")


@app.command()
def main(
    env: str = typer.Option("mock", help="'mock' or 'tau2' (tau2 requires CHANGE_LIVE=1)."),
    domain: str = typer.Option("refunds", help="tau2 domain name (only used when --env tau2)."),
    feedback: str = typer.Option("truth", help="'truth' (D1) or 'satisfaction' (D2)."),
    n: int = typer.Option(500, help="Number of episodes to run."),
    seed: int = typer.Option(0),
    run_id: str = typer.Option(..., "--run-id"),
    n_tasks: int = typer.Option(400, help="Mock only."),
    policy_update_at_episode: int | None = typer.Option(
        None, help="D3: episode count at which the mock policy tightens. Mock only."
    ),
    runs_dir: str = typer.Option(settings.runs_dir),
) -> None:
    if env == "mock":
        _run_mock(feedback, n, seed, run_id, n_tasks, policy_update_at_episode, runs_dir)
    elif env == "tau2":
        if not LIVE:
            raise typer.BadParameter("--env tau2 requires CHANGE_LIVE=1 (see .env.example)")
        _run_tau2(domain, feedback, n, seed, run_id, runs_dir)
    else:
        raise typer.BadParameter("--env must be 'mock' or 'tau2'")


if __name__ == "__main__":
    app()
