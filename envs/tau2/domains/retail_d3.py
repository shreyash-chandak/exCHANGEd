"""Registers a "retail_d3" domain variant into tau2's registry at import
time (session-2 guide 4b.3), reusing retail's own real DB/tools/tasks but
swapping in the tightened D3 policy text (retail_d3_policy.md). Same
pattern tau2 itself uses for policy variants of one domain (registry.py
registers both "telecom" and "telecom-workflow" against the same
underlying telecom domain with different policies). No vendor edits --
retail's own DB/tools/tasks are imported and reused, not modified.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tau2.domains.retail.data_model import RetailDB
from tau2.domains.retail.tools import RetailTools
from tau2.domains.retail.utils import RETAIL_DB_PATH
from tau2.environment.environment import Environment
from tau2.registry import registry

_D3_POLICY_PATH = Path(__file__).parent / "retail_d3_policy.md"


def get_environment(db: Optional[RetailDB] = None, solo_mode: bool = False) -> Environment:
    if solo_mode:
        raise ValueError("retail_d3 does not support solo mode")
    if db is None:
        db = RetailDB.load(RETAIL_DB_PATH)
    tools = RetailTools(db)
    with open(_D3_POLICY_PATH, "r", encoding="utf-8") as fp:
        policy = fp.read()
    return Environment(domain_name="retail_d3", policy=policy, tools=tools)


if "retail_d3" not in registry.get_domains():
    registry.register_domain(get_environment, "retail_d3")
if "retail_d3" not in registry.get_task_sets():
    # Same tasks as base retail -- only the policy text differs.
    registry.register_tasks(registry.get_tasks_loader("retail"), "retail_d3")
