"""Figures and summary table from a grid run dir (guide 8.3)."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import typer

from change.config import FORECAST_HORIZONS
from change.contracts import BehavioralSnapshot, Prediction
from change.store import JsonlStore

app = typer.Typer(add_completion=False)


def _read_summary(grid_dir: Path) -> list[dict]:
    with open(grid_dir / "summary.csv", newline="") as f:
        return list(csv.DictReader(f))


def _load_snapshots(grid_dir: Path, run_id: str) -> list[BehavioralSnapshot]:
    store = JsonlStore(grid_dir / run_id)
    return sorted(store.read_all(BehavioralSnapshot), key=lambda s: s.window_end_t)


def _load_predictions(grid_dir: Path, run_id: str) -> list[Prediction]:
    store = JsonlStore(grid_dir / run_id)
    return store.read_all(Prediction)


def _first_predicted_exit(predictions: list[Prediction]) -> int | None:
    do_nothing_trend = [
        p for p in predictions if p.candidate_id == "do_nothing" and p.twin_model == "trend_t1"
    ]
    for p in do_nothing_trend:
        if p.first_exit_t_q50 is not None:
            return p.first_exit_t_q50
    return None


def figure_1_violation_over_t(grid_dir: Path, out_path: Path, condition: str = "d2") -> None:
    """Violation rate over t for A0 vs FULL on `condition`, first seed
    found, with each system's earliest predicted exit marked."""
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {"A0": "#d62728", "FULL": "#1f77b4"}

    for system in ("A0", "FULL"):
        run_id = next(
            (p.name for p in sorted(grid_dir.glob(f"{system}_{condition}_seed*")) if p.is_dir()),
            None,
        )
        if run_id is None:
            continue
        snapshots = _load_snapshots(grid_dir, run_id)
        if not snapshots:
            continue
        ts = [s.window_end_t for s in snapshots]
        violations = [s.violation_rate for s in snapshots]
        ax.plot(ts, violations, label=system, color=colors[system], marker="o", markersize=3)

        predictions = _load_predictions(grid_dir, run_id)
        exit_t = _first_predicted_exit(predictions)
        if exit_t is not None:
            ax.axvline(exit_t, color=colors[system], linestyle="--", alpha=0.6)
            ax.text(
                exit_t,
                ax.get_ylim()[1] * 0.95,
                f"{system} predicted exit",
                color=colors[system],
                fontsize=8,
                rotation=90,
                va="top",
            )

    ax.set_xlabel("t (interactions)")
    ax.set_ylabel("violation rate")
    ax.set_title(f"Violation rate over time: A0 vs FULL ({condition})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def figure_2_forecast_error_vs_horizon(rows: list[dict], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    for model_name, color in [("trend_t1", "#1f77b4"), ("last_value", "#7f7f7f")]:
        xs, ys = [], []
        for h in FORECAST_HORIZONS:
            key = f"forecast_error.{h}.{model_name}.jsd_mean"
            values = [float(r[key]) for r in rows if r.get(key) not in (None, "", "None")]
            if values:
                xs.append(h)
                ys.append(sum(values) / len(values))
        ax.plot(xs, ys, marker="o", label=model_name, color=color)
    ax.set_xlabel("forecast horizon h")
    ax.set_ylabel("mean JSD(predicted, realized)")
    ax.set_title("Forecast error vs horizon: T1 vs last value")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def figure_3_cumulative_violations_bar(rows: list[dict], out_path: Path) -> None:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        key = (r["system"], r["condition"])
        if r.get("cumulative_violations") not in (None, "", "None"):
            grouped[key].append(float(r["cumulative_violations"]))

    systems = sorted({k[0] for k in grouped})
    conditions = sorted({k[1] for k in grouped})
    fig, ax = plt.subplots(figsize=(9, 5))
    width = 0.8 / max(len(conditions), 1)
    x = range(len(systems))
    for i, condition in enumerate(conditions):
        heights = [
            (sum(grouped[(s, condition)]) / len(grouped[(s, condition)]))
            if grouped.get((s, condition))
            else 0
            for s in systems
        ]
        offsets = [xi + i * width for xi in x]
        ax.bar(offsets, heights, width=width, label=condition)

    ax.set_xticks([xi + width * (len(conditions) - 1) / 2 for xi in x])
    ax.set_xticklabels(systems)
    ax.set_xlabel("system")
    ax.set_ylabel("mean cumulative violations")
    ax.set_title("Cumulative violations by system and condition")
    ax.legend(title="condition")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def table_1_summary_means(rows: list[dict]) -> str:
    metric_cols = [
        "cumulative_violations",
        "final_success_rate",
        "adaptations_count",
        "rollbacks",
        "boundary_expansions",
        "lead_time",
    ]
    grouped: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        key = (r["system"], r["condition"])
        for col in metric_cols:
            value = r.get(col)
            if value not in (None, "", "None"):
                grouped[key][col].append(float(value))

    header = ["system", "condition", "n_seeds", *metric_cols]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for system, condition in sorted(grouped):
        cols = grouped[(system, condition)]
        n_seeds = max((len(v) for v in cols.values()), default=0)
        row_cells = [system, condition, str(n_seeds)]
        for col in metric_cols:
            values = cols.get(col, [])
            row_cells.append(f"{sum(values) / len(values):.3f}" if values else "-")
        lines.append("| " + " | ".join(row_cells) + " |")
    return "\n".join(lines)


@app.command()
def main(grid: str = typer.Option(..., help="grid output dir, e.g. runs/grid-mock")) -> None:
    grid_dir = Path(grid)
    rows = _read_summary(grid_dir)

    figure_1_violation_over_t(grid_dir, grid_dir / "figure1_violation_over_t.png")
    figure_2_forecast_error_vs_horizon(rows, grid_dir / "figure2_forecast_error.png")
    figure_3_cumulative_violations_bar(rows, grid_dir / "figure3_cumulative_violations.png")

    table_md = table_1_summary_means(rows)
    (grid_dir / "table1_summary.md").write_text(table_md + "\n")

    typer.echo(f"wrote figures and table1_summary.md to {grid_dir}")
    typer.echo(table_md)


if __name__ == "__main__":
    app()
