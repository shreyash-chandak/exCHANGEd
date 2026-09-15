"""Experiment grid runner: one run dir per (system, condition, seed) cell,
resumable via a DONE marker, writing summary.csv (guide 8.2)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from change.loop import GovernanceLoop
from change.metrics import compute_metrics

CONDITIONS = {
    "d1": {"feedback": "truth", "policy_update_at_t": None},
    "d2": {"feedback": "satisfaction", "policy_update_at_t": None},
    "d3": {"feedback": "truth", "policy_update_at_t": 300},
}


def default_agent_factory(memory, gates, rng):
    from envs.mock.mock_agent import MockAgent

    return MockAgent(memory=memory, rng=rng, gates=gates)


def _cell_run_id(system: str, condition: str, seed: int) -> str:
    return f"{system}_{condition}_seed{seed}"


def _flatten(d: dict, prefix: str = "") -> dict:
    out: dict = {}
    for key, value in d.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, full_key))
        else:
            out[full_key] = value
    return out


def run_cell(
    system: str,
    condition: str,
    seed: int,
    n_episodes: int,
    out_dir: Path,
    n_tasks: int = 400,
    agent_factory=default_agent_factory,
    sim_trajectories: int | None = None,
    sim_horizon: int | None = None,
) -> dict:
    """Runs one grid cell unless already DONE; returns its flat metrics row
    either way (freshly computed, or reloaded from a previous run)."""
    from envs.mock.mock_env import MockRetailEnv

    run_id = _cell_run_id(system, condition, seed)
    run_dir = Path(out_dir) / run_id
    done_marker = run_dir / "DONE"
    metrics_path = run_dir / "metrics.csv.json"

    if done_marker.exists() and metrics_path.exists():
        metrics = json.loads(metrics_path.read_text())
    else:
        cond = CONDITIONS[condition]
        env = MockRetailEnv(
            n_tasks=n_tasks, seed=seed, run_id=run_id, policy_update_at_t=cond["policy_update_at_t"]
        )
        loop = GovernanceLoop(
            env,
            agent_factory,
            system=system,
            drift_condition={"feedback": cond["feedback"]},
            seed=seed,
            run_id=run_id,
            runs_dir=str(out_dir),
            sim_trajectories=sim_trajectories,
            sim_horizon=sim_horizon,
        )
        loop.run(n_episodes)

        metrics = compute_metrics(run_dir)

        run_dir.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(metrics, default=str, indent=2))
        done_marker.write_text("done")

    row = {"system": system, "condition": condition, "seed": seed}
    row.update(_flatten(metrics))
    return row


def run_grid(
    systems: list[str],
    conditions: list[str],
    seeds: list[int],
    n_episodes: int,
    out_dir: Path,
    n_tasks: int = 400,
    agent_factory=default_agent_factory,
    sim_trajectories: int | None = None,
    sim_horizon: int | None = None,
) -> list[dict]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for system in systems:
        for condition in conditions:
            for seed in seeds:
                rows.append(
                    run_cell(
                        system,
                        condition,
                        seed,
                        n_episodes,
                        out_dir,
                        n_tasks,
                        agent_factory,
                        sim_trajectories,
                        sim_horizon,
                    )
                )

    _write_summary_csv(rows, out_dir / "summary.csv")
    return rows


def _write_summary_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text("")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
