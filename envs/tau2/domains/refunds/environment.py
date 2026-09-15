"""get_environment/get_tasks for the refunds domain, mirroring tau2's own
domain module structure (session-2 guide phase 4a preamble: "Mirror the
mock domain's structure exactly")."""

from __future__ import annotations

import json
from typing import Optional

from tau2.data_model.tasks import Task
from tau2.environment.environment import Environment

from envs.tau2.domains.refunds.data_model import RefundsDB
from envs.tau2.domains.refunds.tools import RefundsTools
from envs.tau2.domains.refunds.utils import (
    REFUNDS_DB_PATH,
    REFUNDS_POLICY_D3_PATH,
    REFUNDS_POLICY_PATH,
    REFUNDS_TASK_SET_D3_PATH,
    REFUNDS_TASK_SET_PATH,
)


def get_environment(
    db: Optional[RefundsDB] = None,
    solo_mode: bool = False,
    policy_version: str = "v1",
) -> Environment:
    if solo_mode:
        raise ValueError("refunds domain does not support solo mode")
    if db is None:
        db = RefundsDB.load(REFUNDS_DB_PATH)
    tools = RefundsTools(db)
    policy_path = REFUNDS_POLICY_PATH if policy_version == "v1" else REFUNDS_POLICY_D3_PATH
    with open(policy_path, "r", encoding="utf-8") as fp:
        policy = fp.read()
    return Environment(
        domain_name="refunds",
        policy=policy,
        tools=tools,
    )


def get_tasks(task_split_name: Optional[str] = None) -> list[Task]:
    """`task_split_name="d3"` loads tasks_d3.json; anything else (including
    None) loads the base 120-task set."""
    path = REFUNDS_TASK_SET_D3_PATH if task_split_name == "d3" else REFUNDS_TASK_SET_PATH
    with open(path, "r", encoding="utf-8") as fp:
        raw_tasks = json.load(fp)
    return [Task.model_validate(t) for t in raw_tasks]
