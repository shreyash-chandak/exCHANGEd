import csv
import json

from change.experiment import run_grid

FAST_KWARGS = {"sim_trajectories": 50, "sim_horizon": 50}


def test_grid_writes_summary_csv_with_expected_shape(tmp_path):
    rows = run_grid(
        systems=["A0"],
        conditions=["d1", "d2"],
        seeds=[0],
        n_episodes=100,
        out_dir=tmp_path,
        n_tasks=100,
        **FAST_KWARGS,
    )

    assert len(rows) == 2
    assert {r["condition"] for r in rows} == {"d1", "d2"}
    assert all(r["system"] == "A0" and r["seed"] == 0 for r in rows)

    summary_path = tmp_path / "summary.csv"
    assert summary_path.exists()
    with open(summary_path, newline="") as f:
        reader = csv.DictReader(f)
        csv_rows = list(reader)
    assert len(csv_rows) == 2
    assert "cumulative_violations" in reader.fieldnames


def test_grid_resume_skips_completed_cells(tmp_path):
    run_grid(
        systems=["A0"],
        conditions=["d1", "d2"],
        seeds=[0],
        n_episodes=100,
        out_dir=tmp_path,
        n_tasks=100,
        **FAST_KWARGS,
    )

    for run_id in ("A0_d1_seed0", "A0_d2_seed0"):
        assert (tmp_path / run_id / "DONE").exists()
        metrics_path = tmp_path / run_id / "metrics.csv.json"
        assert metrics_path.exists()
        cached = json.loads(metrics_path.read_text())

        # Corrupt the underlying run data; a resumed cell must NOT try to
        # regenerate it (which would crash on this corrupted store), proving
        # it read the cached metrics instead.
        (tmp_path / run_id / "ExperienceRecord.jsonl").write_text("not valid jsonl\n")
        metrics_path.write_text(json.dumps({**cached, "_from_cache": True}))

    rows = run_grid(
        systems=["A0"],
        conditions=["d1", "d2"],
        seeds=[0],
        n_episodes=100,
        out_dir=tmp_path,
        n_tasks=100,
        **FAST_KWARGS,
    )

    assert all(r["_from_cache"] is True for r in rows)
