"""Fit T1/LastValue on a run up to --at-t, forecast forward, and print the
predicted exit vs. whatever the actual records show happened (guide 6.6)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import typer

from change.anticipate.envelope import Envelope, baseline_from_first_windows, make_prediction
from change.anticipate.simulator import simulate
from change.anticipate.trend import LastValueModel, TrendModel
from change.config import ENVELOPE_VIOLATION_MAX, SIM_HORIZON, SIM_ROLLING_WINDOW, SIM_TRAJECTORIES
from change.contextualize import build_snapshot
from change.contracts import ExperienceRecord
from change.store import JsonlStore

app = typer.Typer(add_completion=False)


def _windowed_snapshots(records: list[ExperienceRecord], run_id: str, window: int = 50):
    by_episode: dict[str, list[ExperienceRecord]] = {}
    order: list[str] = []
    for record in records:
        if record.episode_id not in by_episode:
            order.append(record.episode_id)
        by_episode.setdefault(record.episode_id, []).append(record)

    snapshots = []
    parent = None
    parent_records = None
    for start in range(0, len(order), window):
        chunk_ids = order[start : start + window]
        chunk_records = [r for eid in chunk_ids for r in by_episode[eid]]
        if not chunk_records:
            continue
        snapshot = build_snapshot(
            chunk_records, parent=parent, run_id=run_id, parent_records=parent_records
        )
        snapshots.append(snapshot)
        parent = snapshot
        parent_records = chunk_records
    return snapshots


def _realized_exit_t(records: list[ExperienceRecord], after_t: int) -> int | None:
    future = sorted([r for r in records if r.t_global > after_t], key=lambda r: r.t_global)
    if not future:
        return None
    violations = [0 if r.policy_eval.compliant else 1 for r in future]
    for i in range(len(violations)):
        window = violations[max(0, i - SIM_ROLLING_WINDOW + 1) : i + 1]
        rate = sum(window) / len(window)
        if rate > ENVELOPE_VIOLATION_MAX:
            return future[i].t_global
    return None


@app.command()
def main(
    run_id: str = typer.Option(..., "--run-id"),
    at_t: int = typer.Option(..., "--at-t"),
    runs_dir: str = typer.Option("runs"),
    seed: int = typer.Option(0),
) -> None:
    store = JsonlStore(Path(runs_dir) / run_id)
    records = store.read_all(ExperienceRecord)
    if not records:
        typer.echo(f"no records found for run {run_id!r} under {runs_dir}")
        raise typer.Exit(1)

    snapshots = _windowed_snapshots(records, run_id)
    fit_snapshots = [s for s in snapshots if s.window_end_t <= at_t]
    if not fit_snapshots:
        typer.echo(f"no snapshot window ends at or before t={at_t}")
        raise typer.Exit(1)
    cutoff = fit_snapshots[-1]

    # Session-2 guide 4.0.6: baseline is the mean over the run's first 3
    # windows (not just the cutoff window's own noisy values), same
    # implementation change/loop.py uses.
    baseline_success, baseline_cost, _baseline_latency = baseline_from_first_windows(snapshots)
    envelope = Envelope(baseline_success=baseline_success, baseline_cost=baseline_cost)
    realized_exit_t = _realized_exit_t(records, after_t=cutoff.window_end_t)

    typer.echo(f"cutoff snapshot: {cutoff.snapshot_id} (window_end_t={cutoff.window_end_t})")
    typer.echo(
        f"realized exit t (from actual records): "
        f"{realized_exit_t if realized_exit_t is not None else 'not observed in available data'}"
    )
    typer.echo("")

    for name, model_cls, twin_model in [
        ("LastValue", LastValueModel, "last_value"),
        ("T1 (trend)", TrendModel, "trend_t1"),
    ]:
        model = model_cls().fit(fit_snapshots)
        rng = np.random.default_rng(seed)
        sim = simulate(model, cutoff, n_traj=SIM_TRAJECTORIES, horizon=SIM_HORIZON, rng=rng)
        prediction = make_prediction(cutoff, "do_nothing", model, sim, envelope, twin_model)

        typer.echo(f"model: {name}")
        typer.echo(
            f"  predicted exit t: q10={prediction.first_exit_t_q10} "
            f"q50={prediction.first_exit_t_q50} q90={prediction.first_exit_t_q90} "
            f"(metric={prediction.exit_metric})"
        )
        typer.echo("  top contributing cells:")
        for cell in prediction.contributing_cells:
            typer.echo(f"    {cell.state_key} | {cell.action}: {cell.delta_p:+.4f}")
        typer.echo("")


if __name__ == "__main__":
    app()
