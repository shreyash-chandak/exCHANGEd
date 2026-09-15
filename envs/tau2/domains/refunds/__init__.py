"""Registers the refunds domain into tau2's global registry at import
time. No vendor edits (owner-authorized, Q3 in context/status.md) -- same
pattern tau2's own registry.py uses for its built-in domains."""

from tau2.registry import registry

from envs.tau2.domains.refunds.environment import get_environment, get_tasks

if "refunds" not in registry.get_domains():
    registry.register_domain(get_environment, "refunds")
if "refunds" not in registry.get_task_sets():
    registry.register_tasks(get_tasks, "refunds")
