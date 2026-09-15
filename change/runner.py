"""Bounded-concurrency episode runner (session-2 guide 4.1.6).

Meant for a live env (phase 4a/4b), where each episode is a slow network
call to the local model server and running several in flight at once
matters. Not wired into the mock path: `MockRetailEnv` mutates shared,
per-instance counters (`_episode_count`, `_t_global`, a policy-flip cache)
inside `run_episode` and was never designed to be called concurrently from
multiple threads on the same instance -- doing so would race those
counters. The mock env is fast enough sequentially that it doesn't need
this anyway. Unit-tested here against a fake env instead.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed

from change.contracts import ExperienceRecord
from change.store import JsonlStore
from envs.base import Agent, EpisodeResult, Env


def run_concurrent_episodes(
    env: Env,
    agent: Agent,
    task_seed_pairs: list[tuple[str, int]],
    max_concurrency: int,
) -> Iterator[tuple[str, int, EpisodeResult]]:
    """Runs `env.run_episode(task_id, agent, episode_seed)` for every
    (task_id, episode_seed) pair, at most `max_concurrency` in flight at
    once, yielding (task_id, episode_seed, EpisodeResult) tuples in
    COMPLETION order -- concurrent episodes don't finish in submission
    order, so callers assign t_global at write time from this order
    (`write_episode_records` below) rather than trusting whatever the env
    itself set."""
    with ThreadPoolExecutor(max_workers=max_concurrency) as pool:
        futures = {
            pool.submit(env.run_episode, task_id, agent, episode_seed): (
                task_id,
                episode_seed,
            )
            for task_id, episode_seed in task_seed_pairs
        }
        for future in as_completed(futures):
            task_id, episode_seed = futures[future]
            yield task_id, episode_seed, future.result()


def write_episode_records(
    store: JsonlStore, records: list[ExperienceRecord], next_t_global: int
) -> int:
    """Writes one episode's records to `store`, reassigning t_global
    sequentially starting at `next_t_global` (guide 4.1.6: t_global is
    assigned at write time, not by the env, since concurrent episodes
    complete out of submission order). Returns the next free t_global."""
    t = next_t_global
    for record in records:
        record.t_global = t
        store.append(record)
        t += 1
    return t
