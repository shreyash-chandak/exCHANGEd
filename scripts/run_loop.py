"""Run the governance loop for one system/condition and print a per-cycle
table (guide 7.6)."""

from __future__ import annotations

import typer

from change.experiment import CONDITIONS, default_agent_factory
from change.loop import GovernanceLoop
from envs.mock.mock_env import MockRetailEnv

app = typer.Typer(add_completion=False)


@app.command()
def main(
    env: str = typer.Option("mock"),
    system: str = typer.Option(..., help="A0, A1, A2, A3, A4, or FULL"),
    condition: str = typer.Option(..., help="d1, d2, or d3"),
    n_episodes: int = typer.Option(1000, "--n-episodes"),
    seed: int = typer.Option(0),
    run_id: str = typer.Option(..., "--run-id"),
    n_tasks: int = typer.Option(400),
    runs_dir: str = typer.Option("runs"),
) -> None:
    if env != "mock":
        raise typer.BadParameter("only --env mock is implemented")
    if condition not in CONDITIONS:
        raise typer.BadParameter(f"condition must be one of {list(CONDITIONS)}")

    cond = CONDITIONS[condition]
    mock_env = MockRetailEnv(
        n_tasks=n_tasks,
        seed=seed,
        run_id=run_id,
        policy_update_at_episode=cond["policy_update_at_episode"],
    )
    loop = GovernanceLoop(
        mock_env,
        default_agent_factory,
        system=system,
        drift_condition={"feedback": cond["feedback"]},
        seed=seed,
        run_id=run_id,
        runs_dir=runs_dir,
    )

    header = f"{'cycle':>5} {'t':>6} {'violation':>10} {'jsd':>8} {'pred_exit':>10} {'decision':>10} {'candidate':>16} {'version':>8}"
    typer.echo(header)
    while loop._episode_counter < n_episodes:
        r = loop.run_cycle()
        typer.echo(
            f"{r['cycle']:>5} {r['t']:>6} {r['violation']:>10.3f} {r['jsd']:>8.3f} "
            f"{r['predicted_exit']!s:>10} {r['decision']:>10} {r['candidate_kind']:>16} "
            f"{r['version']:>8}"
        )


if __name__ == "__main__":
    app()
