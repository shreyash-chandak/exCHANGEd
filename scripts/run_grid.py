"""Run the full experiment grid (systems x conditions x seeds), resumable,
writing summary.csv (guide 8.2)."""

from __future__ import annotations

import typer

from change.experiment import run_grid

app = typer.Typer(add_completion=False)


@app.command()
def main(
    env: str = typer.Option("mock"),
    systems: str = typer.Option(..., help="comma-separated: A0,A1,A2,A3,A4,FULL"),
    conditions: str = typer.Option(..., help="comma-separated: d1,d2,d3"),
    seeds: str = typer.Option(..., help="comma-separated seeds: 0,1"),
    n_episodes: int = typer.Option(1000, "--n-episodes"),
    out: str = typer.Option(..., help="output directory, e.g. runs/grid-mock"),
    n_tasks: int = typer.Option(400),
    sim_trajectories: int = typer.Option(
        None, "--sim-trajectories", help="overrides SIM_TRAJECTORIES uniformly for every cell"
    ),
    sim_horizon: int = typer.Option(
        None, "--sim-horizon", help="overrides SIM_HORIZON uniformly for every cell"
    ),
) -> None:
    if env != "mock":
        raise typer.BadParameter("only --env mock is implemented")

    system_list = systems.split(",")
    condition_list = conditions.split(",")
    seed_list = [int(s) for s in seeds.split(",")]

    rows = run_grid(
        systems=system_list,
        conditions=condition_list,
        seeds=seed_list,
        n_episodes=n_episodes,
        out_dir=out,
        n_tasks=n_tasks,
        sim_trajectories=sim_trajectories,
        sim_horizon=sim_horizon,
    )

    typer.echo(f"{len(rows)} cells written to {out}/summary.csv")


if __name__ == "__main__":
    app()
