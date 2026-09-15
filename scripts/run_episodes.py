"""Run episodes against the mock env (guide 3.6) or, LIVE-gated, a tau2
domain (session-2 guide 4a.7), writing ExperienceRecord/Lesson jsonl and
printing a per-50-episode violation rate table (mock only)."""

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


def _run_tau2(domain: str, n: int, seed: int, run_id: str, runs_dir: str) -> None:
    if not LIVE:
        raise typer.BadParameter("--env tau2 requires CHANGE_LIVE=1 (see .env.example)")

    import envs.tau2.domains.refunds  # noqa: F401 -- registers at import time
    from envs.tau2.adapter import Tau2Env

    env_obj = Tau2Env(domain=domain, run_id=run_id)
    task_ids = env_obj.task_ids()[:n]
    store = JsonlStore(Path(runs_dir) / run_id)

    for i, task_id in enumerate(task_ids):
        typer.echo(f"running task {task_id} ({i + 1}/{len(task_ids)})...")
        result = env_obj.run_episode(task_id, agent=None, seed=seed)
        for record in result.records:
            store.append(record)
        typer.echo(f"  {len(result.records)} records, reward={result.reward}")

    typer.echo(f"done: {len(task_ids)} episodes written to {Path(runs_dir) / run_id}")


@app.command()
def main(
    env: str = typer.Option("mock", help="'mock' or 'tau2' (tau2 requires CHANGE_LIVE=1)."),
    domain: str = typer.Option("refunds", help="tau2 domain name (only used when --env tau2)."),
    feedback: str = typer.Option("truth", help="'truth' (D1) or 'satisfaction' (D2). Mock only."),
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
        _run_tau2(domain, n, seed, run_id, runs_dir)
    else:
        raise typer.BadParameter("--env must be 'mock' or 'tau2'")


if __name__ == "__main__":
    app()
