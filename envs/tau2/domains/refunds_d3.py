"""Registers a "refunds_d3" domain variant into tau2's registry at import
time (mirrors envs/tau2/domains/retail_d3.py's exact pattern), reusing
refunds' own real DB/tools/tasks but with the tightened D3 policy text
(policy_d3.md) swapped in.

Found live while wiring the governance loop against tau2 (session-2 guide
4d): refunds' D3 condition previously had `policy_version="v3"` reach
only the oracle's grading (envs/tau2/adapter.py passes it explicitly per
write action) -- the agent's own system prompt always showed the base
policy.md text regardless, since neither `run_episode` (TextRunConfig/
registry path) nor `run_live_episode` (build_environment(domain) path)
had any way to pass `policy_version` through to
envs/tau2/domains/refunds/environment.py::get_environment's
`policy_version` kwarg. That made D3 ungradeable fairly: the agent was
being judged against rules it was never shown. Retail's D3 already
avoided this by registering a genuinely separate domain name
("retail_d3") with its own environment constructor -- this module does
the same for refunds.

Uses the same 120-task base pool as "refunds" (not tasks_d3.json, which
is a fixed 30-task set for the oracle's own boundary-condition testing,
guide 4a.5 -- a different purpose). The live D3 condition needs "same
population of requests, policy silently got stricter partway through",
matching envs/mock/mock_env.py's MockRetailEnv.policy_update_at_episode
design, not a separate boundary-focused task set.
"""

from __future__ import annotations

from typing import Optional

from tau2.environment.environment import Environment
from tau2.registry import registry

import envs.tau2.domains.refunds  # noqa: F401 -- must register "refunds" first, get_tasks_loader below needs it
from envs.tau2.domains.refunds.data_model import RefundsDB
from envs.tau2.domains.refunds.tools import RefundsTools
from envs.tau2.domains.refunds.utils import REFUNDS_DB_PATH, REFUNDS_POLICY_D3_PATH


def get_environment(db: Optional[RefundsDB] = None, solo_mode: bool = False) -> Environment:
    if solo_mode:
        raise ValueError("refunds_d3 does not support solo mode")
    if db is None:
        db = RefundsDB.load(REFUNDS_DB_PATH)
    tools = RefundsTools(db)
    with open(REFUNDS_POLICY_D3_PATH, "r", encoding="utf-8") as fp:
        policy = fp.read()
    return Environment(domain_name="refunds_d3", policy=policy, tools=tools)


if "refunds_d3" not in registry.get_domains():
    registry.register_domain(get_environment, "refunds_d3")
if "refunds_d3" not in registry.get_task_sets():
    # Same tasks as base refunds -- only the policy text differs.
    registry.register_tasks(registry.get_tasks_loader("refunds"), "refunds_d3")
