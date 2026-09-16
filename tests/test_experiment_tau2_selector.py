"""Offline tests for change/experiment.py's env/domain selector (session-2
guide 4d). Only exercises env='mock' construction plus the tau2 branch's
CHANGE_LIVE gate and object types -- never actually runs a tau2 episode
(that needs a live model)."""

from __future__ import annotations

import pytest

from change.experiment import CONDITIONS, _build_env_and_agent_factory, default_agent_factory
from envs.mock.mock_env import MockRetailEnv


def test_mock_selector_returns_mock_env_and_default_factory():
    env, factory = _build_env_and_agent_factory(
        "mock", "refunds", "run1", seed=0, n_tasks=50, cond=CONDITIONS["d1"]
    )
    assert isinstance(env, MockRetailEnv)
    assert factory is default_agent_factory


def test_tau2_selector_rejects_without_change_live(monkeypatch):
    monkeypatch.setattr("change.config.LIVE", False)
    with pytest.raises(RuntimeError, match="CHANGE_LIVE"):
        _build_env_and_agent_factory(
            "tau2", "refunds", "run1", seed=0, n_tasks=50, cond=CONDITIONS["d1"]
        )


def test_tau2_selector_builds_tau2_env_and_handle_factory(monkeypatch):
    monkeypatch.setattr("change.config.LIVE", True)
    from envs.tau2.adapter import Tau2Env, tau2_agent_factory

    env, factory = _build_env_and_agent_factory(
        "tau2", "refunds", "run-tau2-selector", seed=0, n_tasks=50, cond=CONDITIONS["d1"]
    )
    assert isinstance(env, Tau2Env)
    assert env.domain == "refunds"
    assert factory is tau2_agent_factory


def test_tau2_selector_threads_policy_update_at_episode_for_d3(monkeypatch):
    monkeypatch.setattr("change.config.LIVE", True)
    env, _factory = _build_env_and_agent_factory(
        "tau2", "refunds", "run-d3", seed=0, n_tasks=50, cond=CONDITIONS["d3"]
    )
    assert env.policy_update_at_episode == CONDITIONS["d3"]["policy_update_at_episode"]


def test_unknown_env_raises():
    with pytest.raises(ValueError, match="mock.*tau2"):
        _build_env_and_agent_factory(
            "bogus", "refunds", "run1", seed=0, n_tasks=50, cond=CONDITIONS["d1"]
        )
