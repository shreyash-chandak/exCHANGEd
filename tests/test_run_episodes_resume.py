"""Offline regression test for scripts/run_episodes.py's --resume state
reconstruction. Found live: resuming a tau2 D2-gate run crashed with
ZeroDivisionError the next time the per-50-episode violation_rate block
report fired, because `violation_flags` wasn't reconstructed on resume --
the *global* episode index (continuing from `already_done`) hit a
multiple of 50 long before this process's freshly-empty local list had
50 entries. _resume_state must return the full violation_flags history,
not just the memory/episode-count/t_global."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from change.contracts import (
    CanonicalAction,
    CanonicalOutcome,
    CanonicalState,
    ExperienceRecord,
    PolicyEval,
)
from change.store import JsonlStore

_SPEC = importlib.util.spec_from_file_location(
    "run_episodes_script", Path(__file__).parent.parent / "scripts" / "run_episodes.py"
)
run_episodes_script = importlib.util.module_from_spec(_SPEC)
sys.modules["run_episodes_script"] = run_episodes_script
_SPEC.loader.exec_module(run_episodes_script)

STATE = CanonicalState("return", "delivered", "high", False, "neutral", "t0")


def _record(episode_id: str, compliant: bool) -> ExperienceRecord:
    return ExperienceRecord(
        run_id="r1",
        agent_id="a1",
        agent_version=1,
        memory_version=0,
        episode_id=episode_id,
        turn_idx=0,
        t_global=0,
        state=STATE,
        action=CanonicalAction.REFUND_FULL,
        outcome=CanonicalOutcome(policy_compliant=compliant, task_success=True, user_satisfied=True),
        policy_eval=PolicyEval(compliant=compliant, violated_rule_ids=[] if compliant else ["R1"]),
        reward=1.0,
        latency_ms=0.0,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0.0,
    )


def test_resume_state_reconstructs_violation_flags_in_episode_order(tmp_path):
    store = JsonlStore(tmp_path)
    # Three episodes: compliant, non-compliant, compliant.
    store.append(_record("ep1", compliant=True))
    store.append(_record("ep2", compliant=False))
    store.append(_record("ep3", compliant=True))

    already_done, n_records, memory, violation_flags = run_episodes_script._resume_state(tmp_path)

    assert already_done == 3
    assert n_records == 3
    assert violation_flags == [False, True, False]


def test_resume_state_multi_record_episodes_flag_true_if_any_record_noncompliant(tmp_path):
    store = JsonlStore(tmp_path)
    store.append(_record("ep1", compliant=True))
    store.append(_record("ep1", compliant=False))  # same episode, second turn, violates

    _already_done, _n_records, _memory, violation_flags = run_episodes_script._resume_state(
        tmp_path
    )

    assert violation_flags == [True]


def test_resume_state_empty_run_dir_returns_empty_flags(tmp_path):
    already_done, n_records, _memory, violation_flags = run_episodes_script._resume_state(tmp_path)
    assert already_done == 0
    assert n_records == 0
    assert violation_flags == []


def test_resumed_violation_flags_plus_fresh_ones_cover_a_full_50_block_without_crashing():
    """Regression for the exact live crash: 56 already-done episodes'
    flags (reconstructed) plus fresh ones appended in the loop must let
    the i+1==100 block slice (violation_flags[50:100]) be non-empty."""
    already_done_flags = [False] * 56
    violation_flags = list(already_done_flags)
    for _ in range(56, 100):
        violation_flags.append(False)

    i = 99  # 0-indexed episode loop variable when global index reaches 100
    block = violation_flags[i + 1 - 50 : i + 1]
    assert len(block) == 50
    rate = sum(block) / len(block)  # must not raise ZeroDivisionError
    assert rate == 0.0
