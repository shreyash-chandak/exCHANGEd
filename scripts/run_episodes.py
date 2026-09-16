"""Run episodes against the mock env (guide 3.6) or, LIVE-gated, a tau2
domain through a memory-injecting LessonAgent (session-2 guide 4c),
writing ExperienceRecord/Lesson jsonl and printing a per-50-episode
violation rate table."""

from __future__ import annotations

import random
from pathlib import Path

import typer

from change.config import LIVE, MEMORY_CAP, settings
from change.contracts import ExperienceRecord, Lesson
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


def _resume_state(run_dir: Path) -> tuple[int, int, LessonMemory, list[bool]]:
    """Reconstructs (episodes_already_done, next_t_global, memory,
    violation_flags) from an existing run dir's JsonlStore contents
    (session-2 guide 4d.2's resumability): every completed episode wrote
    exactly one distinct episode_id worth of ExperienceRecords, so that
    count is the loop iteration to resume from; the total record count is
    where t_global must continue from (t_global is a 0-based count of
    decision records in the run, guide 2.1); replaying Lesson.jsonl's
    lessons back into a fresh LessonMemory in the same (append) order
    reconstructs its exact prior state, cap-eviction included.
    `violation_flags` (one bool per already-done episode, in episode
    order) is needed too -- found live: without it, resuming partway
    through a run crashed with ZeroDivisionError the next time the
    per-50-episode block report fired, since the *global* episode index
    (continuing from `already_done`) hit a multiple of 50 long before
    this process's own, freshly-empty `violation_flags` list had 50
    entries in it. No separate marker file needed -- the append-only
    store already has everything required."""
    store = JsonlStore(run_dir)
    memory = LessonMemory(cap=MEMORY_CAP)
    for lesson in store.iter(Lesson):
        memory.add(lesson)

    episode_order: list[str] = []
    episode_records: dict[str, list[ExperienceRecord]] = {}
    n_records = 0
    for record in store.iter(ExperienceRecord):
        if record.episode_id not in episode_records:
            episode_order.append(record.episode_id)
            episode_records[record.episode_id] = []
        episode_records[record.episode_id].append(record)
        n_records += 1

    violation_flags = [
        not all(r.policy_eval.compliant for r in episode_records[episode_id])
        for episode_id in episode_order
    ]
    return len(episode_order), n_records, memory, violation_flags


def _run_tau2(
    domain: str, feedback: str, n: int, seed: int, run_id: str, runs_dir: str, resume: bool
) -> None:
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

    run_dir = Path(runs_dir) / run_id
    already_done = 0
    memory = LessonMemory(cap=MEMORY_CAP)
    violation_flags: list[bool] = []
    env_obj = Tau2Env(domain=domain, run_id=run_id)
    if resume:
        already_done, next_t_global, memory, violation_flags = _resume_state(run_dir)
        if already_done:
            typer.echo(f"resuming: {already_done} episode(s) already recorded in {run_dir}")
            env_obj.set_t_global(next_t_global)

    gates: dict = {}
    extractor = LiveLessonExtractor(feedback=feedback)
    task_ids = env_obj.task_ids()
    store = JsonlStore(run_dir)

    for i in range(already_done, n):
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
    resume: bool = typer.Option(
        False, "--resume", help="tau2 only: skip episodes already recorded under --run-id."
    ),
) -> None:
    if env == "mock":
        _run_mock(feedback, n, seed, run_id, n_tasks, policy_update_at_episode, runs_dir)
    elif env == "tau2":
        if not LIVE:
            raise typer.BadParameter("--env tau2 requires CHANGE_LIVE=1 (see .env.example)")
        _run_tau2(domain, feedback, n, seed, run_id, runs_dir, resume)
    else:
        raise typer.BadParameter("--env must be 'mock' or 'tau2'")


if __name__ == "__main__":
    app()
