"""Experiment grid runner: one run dir per (system, condition, seed) cell,
resumable via a DONE marker, writing summary.csv (guide 8.2)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from change.loop import GovernanceLoop
from change.metrics import compute_metrics

CONDITIONS = {
    "d1": {"feedback": "truth", "policy_update_at_episode": None},
    "d2": {"feedback": "satisfaction", "policy_update_at_episode": None},
    # Owner-authorized revision (docs/checkpoints/phase-3.md): D3 now learns
    # from `satisfaction` feedback (not `truth`) so the memory it accumulates
    # before the policy tightens is reliably generosity-biased -- under
    # `truth` feedback most positive-feedback lessons came from non-generous
    # compliant actions, so the intended "stale memory causes violations
    # after the policy update" story didn't reproduce. Gated on episode
    # count (see MockRetailEnv/Tau2Env's policy_update_at_episode), not
    # t_global.
    "d3": {"feedback": "satisfaction", "policy_update_at_episode": 200},
}


def default_agent_factory(memory, gates, rng):
    from envs.mock.mock_agent import MockAgent

    return MockAgent(memory=memory, rng=rng, gates=gates)


def _build_env_and_agent_factory(
    env: str, domain: str, run_id: str, seed: int, n_tasks: int, cond: dict
):
    """Session-2 guide 4d: the live-tau2 counterpart to mock's
    MockRetailEnv + default_agent_factory. Tau2Env + Tau2AgentHandle's
    tau2_agent_factory is a drop-in Env+Agent pair for GovernanceLoop
    (see envs/tau2/adapter.py::Tau2AgentHandle's docstring for why zero
    changes were needed to change/loop.py, change/sandbox.py,
    change/evolve.py to support this)."""
    if env == "mock":
        from envs.mock.mock_env import MockRetailEnv

        return (
            MockRetailEnv(
                n_tasks=n_tasks,
                seed=seed,
                run_id=run_id,
                policy_update_at_episode=cond["policy_update_at_episode"],
            ),
            default_agent_factory,
        )
    if env == "tau2":
        from change.config import LIVE
        from envs.tau2.adapter import Tau2Env, tau2_agent_factory

        if not LIVE:
            raise RuntimeError("--env tau2 requires CHANGE_LIVE=1 (see .env.example)")
        return (
            Tau2Env(
                domain=domain,
                run_id=run_id,
                policy_update_at_episode=cond["policy_update_at_episode"],
            ),
            tau2_agent_factory,
        )
    raise ValueError(f"--env must be 'mock' or 'tau2', got {env!r}")


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
    agent_factory=None,
    sim_trajectories: int | None = None,
    sim_horizon: int | None = None,
    env: str = "mock",
    domain: str = "refunds",
) -> dict:
    """Runs one grid cell unless already DONE; returns its flat metrics row
    either way (freshly computed, or reloaded from a previous run).
    `env`/`domain` select mock (default) or a live tau2 domain (session-2
    guide 4d) -- `agent_factory` left as None picks the matching default
    for whichever `env` was selected; pass explicitly to override."""
    run_id = _cell_run_id(system, condition, seed)
    run_dir = Path(out_dir) / run_id
    done_marker = run_dir / "DONE"
    metrics_path = run_dir / "metrics.csv.json"

    if done_marker.exists() and metrics_path.exists():
        metrics = json.loads(metrics_path.read_text())
    else:
        cond = CONDITIONS[condition]
        built_env, default_factory = _build_env_and_agent_factory(
            env, domain, run_id, seed, n_tasks, cond
        )
        loop = GovernanceLoop(
            built_env,
            agent_factory if agent_factory is not None else default_factory,
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
        # Owner-authorized addition (Q7, docs/checkpoints/phase-8.md
        # "Revision" section): record the *effective* (post-None-fallback)
        # simulation scale actually used for this cell, so summary.csv can
        # be audited for a uniform sim_trajectories/sim_horizon setting
        # across every cell of a grid run.
        metrics["sim_trajectories"] = loop.sim_trajectories
        metrics["sim_horizon"] = loop.sim_horizon

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
    agent_factory=None,
    sim_trajectories: int | None = None,
    sim_horizon: int | None = None,
    env: str = "mock",
    domain: str = "refunds",
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
                        env,
                        domain,
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
