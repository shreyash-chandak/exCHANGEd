"""Offline tests for the tau2-vs-mock governance-loop wiring (session-2
guide 4d): Tau2AgentHandle/tau2_agent_factory, Tau2Env's D3 episode-gated
policy flip, stratify_key, run_episode's dispatch on agent type, and
change/experiment.py's env/domain selector. No live model calls -- these
exercise pure logic and offline data (local JSON task/db files)."""

from __future__ import annotations

import pytest

from change.memory import LessonMemory
from envs.tau2.adapter import Tau2AgentHandle, Tau2Env, tau2_agent_factory


def test_tau2_agent_factory_returns_handle_carrying_memory_and_gates():
    memory = LessonMemory()
    gates = {"approval_gate": {}}
    handle = tau2_agent_factory(memory, gates, rng=None)
    assert isinstance(handle, Tau2AgentHandle)
    assert handle.memory is memory
    assert handle.gates is gates
    assert handle.agent_version == 1


def test_handle_memory_version_reflects_live_memory_state():
    memory = LessonMemory()
    handle = tau2_agent_factory(memory, {}, rng=None)
    assert handle.memory_version == 0
    memory.version = 3  # simulate lessons having been added
    assert handle.memory_version == 3


@pytest.mark.parametrize("domain", ["refunds", "retail"])
def test_current_policy_version_static_without_policy_update_at_episode(domain):
    env = Tau2Env(domain=domain, run_id=f"t-static-{domain}", policy_version="v3")
    assert env._current_policy_version() == "v3"
    env2 = Tau2Env(domain=domain, run_id=f"t-static2-{domain}")
    assert env2._current_policy_version() == "v1"


@pytest.mark.parametrize("domain", ["refunds", "retail"])
def test_current_policy_version_flips_at_episode_threshold(domain):
    env = Tau2Env(domain=domain, run_id=f"t-flip-{domain}", policy_update_at_episode=3)
    versions = []
    for _ in range(6):
        versions.append(env._current_policy_version())
        env._episode_count += 1
    assert versions == ["v1", "v1", "v1", "v3", "v3", "v3"]


@pytest.mark.parametrize(
    "domain,policy_version,expected",
    [
        ("refunds", "v1", "refunds"),
        ("refunds", "v3", "refunds_d3"),
        ("retail", "v1", "retail"),
        ("retail", "v3", "retail_d3"),
    ],
)
def test_tau2_domain_name_resolution(domain, policy_version, expected):
    env = Tau2Env(domain=domain, run_id=f"t-domain-{domain}-{policy_version}")
    assert env._tau2_domain_name(policy_version) == expected


def test_stratify_key_refunds_returns_task_type_and_window():
    env = Tau2Env(domain="refunds", run_id="t-stratify-refunds")
    for task_id in env.task_ids()[:10]:
        key = env.stratify_key(task_id)
        assert isinstance(key, tuple) and len(key) == 2
        assert isinstance(key[0], str)
        assert isinstance(key[1], bool)


def test_stratify_key_retail_returns_task_type_and_window():
    env = Tau2Env(domain="retail", run_id="t-stratify-retail")
    for task_id in env.task_ids()[:10]:
        key = env.stratify_key(task_id)
        assert isinstance(key, tuple) and len(key) == 2
        assert isinstance(key[0], str)
        assert isinstance(key[1], bool)


def test_run_episode_dispatches_to_live_path_for_agent_handle(monkeypatch):
    """The critical offline-testable piece of the dispatch logic: passing
    a Tau2AgentHandle must route through run_live_episode (the
    memory-injecting LessonAgent path), never tau2's built-in llm_agent
    path (TextRunConfig/run_single_task). Verified by stubbing
    run_live_episode and asserting it -- not run_single_task -- gets
    called, with no live model call happening either way."""
    env = Tau2Env(domain="refunds", run_id="t-dispatch")
    calls = []

    def fake_run_live_episode(task_id, memory, gates, seed):
        calls.append((task_id, memory, gates, seed))
        return "sentinel-result"

    monkeypatch.setattr(env, "run_live_episode", fake_run_live_episode)

    memory = LessonMemory()
    gates = {"g": 1}
    handle = tau2_agent_factory(memory, gates, rng=None)
    result = env.run_episode("refunds_000", handle, seed=42)

    assert result == "sentinel-result"
    assert calls == [("refunds_000", memory, gates, 42)]


def test_run_episode_does_not_dispatch_for_none_agent(monkeypatch):
    """A plain None agent (baseline.py's / the smoke-test path's usage)
    must NOT be routed to run_live_episode -- it should fall through to
    tau2's built-in-agent path instead. Stubs run_single_task too so this
    stays fully offline (no live model/network call either way)."""
    import envs.tau2.adapter as adapter_module

    env = Tau2Env(domain="refunds", run_id="t-no-dispatch")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("run_live_episode should not be called for agent=None")

    monkeypatch.setattr(env, "run_live_episode", fail_if_called)

    built_in_calls = []

    class _FakeSim:
        reward_info = None

        def get_messages(self):
            return []

    def fake_run_single_task(config, task, seed, evaluation_type):
        built_in_calls.append((config.domain, task.id, seed))
        return _FakeSim()

    monkeypatch.setattr(adapter_module, "run_single_task", fake_run_single_task)
    monkeypatch.setattr(
        adapter_module, "refunds_user_satisfied", lambda transcript: True
    )

    result = env.run_episode("refunds_000", None, seed=0)

    assert built_in_calls == [("refunds", "refunds_000", 0)]
    assert result.records == []
