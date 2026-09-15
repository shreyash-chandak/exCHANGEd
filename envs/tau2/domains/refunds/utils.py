"""Paths for the refunds domain's data files. Lives in our repo, not the
tau2 vendor package's own data directory (session-2 guide phase 4a
preamble: "Our domain lives in our repo ... No vendor edits.")."""

from __future__ import annotations

from pathlib import Path

REFUNDS_DATA_DIR = Path(__file__).parent / "data"
REFUNDS_DB_PATH = REFUNDS_DATA_DIR / "db.json"
REFUNDS_POLICY_PATH = REFUNDS_DATA_DIR / "policy.md"
REFUNDS_POLICY_D3_PATH = REFUNDS_DATA_DIR / "policy_d3.md"
REFUNDS_TASK_SET_PATH = REFUNDS_DATA_DIR / "tasks.json"
REFUNDS_TASK_SET_D3_PATH = REFUNDS_DATA_DIR / "tasks_d3.json"
