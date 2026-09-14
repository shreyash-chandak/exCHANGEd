"""Run episodes against the mock env, writing ExperienceRecord/Lesson jsonl
and printing a per-50-episode violation rate table (guide 3.6)."""

from __future__ import annotations

import random
from pathlib import Path

import typer

from change.config import MEMORY_CAP, settings
from change.generate import MockLessonExtractor
from change.memory import LessonMemory
from change.store import JsonlStore
from envs.mock.mock_agent import MockAgent
from envs.mock.mock_env import MockRetailEnv

app = typer.Typer(add_completion=False)


@app.command()
def main(
    env: str = typer.Option("mock", help="Only 'mock' is implemented before phase 4."),
    feedback: str = typer.Option("truth", help="'truth' (D1) or 'satisfaction' (D2)."),
    n: int = typer.Option(500, help="Number of episodes to run."),
    seed: int = typer.Option(0),
    run_id: str = typer.Option(..., "--run-id"),
    n_tasks: int = typer.Option(400),
    policy_update_at_t: int | None = typer.Option(
        None, help="D3: t_global at which the mock policy tightens."
    ),
    runs_dir: str = typer.Option(settings.runs_dir),
) -> None:
    if env != "mock":
        raise typer.BadParameter("only --env mock is implemented before phase 4")

    memory = LessonMemory(cap=MEMORY_CAP)
    agent = MockAgent(memory=memory, rng=random.Random(seed))
    mock_env = MockRetailEnv(
        n_tasks=n_tasks, seed=seed, run_id=run_id, policy_update_at_t=policy_update_at_t
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


if __name__ == "__main__":
    app()
