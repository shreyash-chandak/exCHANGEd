"""Apply, canary, rollback, successor distillation (guide 7.4)."""

from __future__ import annotations

import random
from uuid import uuid4

from change.anticipate.envelope import Envelope
from change.config import (
    DISTILL_TRIGGER_WINDOWS,
    ENVELOPE_SUCCESS_DROP_MAX,
    ENVELOPE_VIOLATION_MAX,
)
from change.contracts import (
    AdaptationDecision,
    AgentVersion,
    BehavioralSnapshot,
    Candidate,
    SandboxResult,
)
from change.generate import apply_candidate_to_memory_and_gates
from change.memory import LessonMemory
from change.negotiate import Boundary, contract_boundary, one_sided_margin
from change.store import JsonlStore


def apply(candidate: Candidate, memory: LessonMemory, gates: dict) -> tuple[LessonMemory, dict]:
    """Mutates the live memory/gates in place. memory.version bumps
    automatically via LessonMemory.add/remove."""
    apply_candidate_to_memory_and_gates(candidate, memory, gates)
    return memory, gates


def canary(
    agent_factory,
    env,
    canary_ids: list[str],
    memory: LessonMemory,
    gates: dict,
    store: JsonlStore | None = None,
    seed: int = 0,
) -> SandboxResult:
    """Evaluate the current (already-applied) agent on the canary split."""
    if not canary_ids:
        raise ValueError("canary requires a non-empty canary task split")

    agent = agent_factory(memory, gates, random.Random(seed))

    n_total = violations = successes = satisfied = 0
    cost_sum = latency_sum = 0.0
    states_seen: set[str] = set()

    for i, task_id in enumerate(canary_ids):
        result = env.run_episode(task_id, agent, seed * 1_000_003 + i)
        for record in result.records:
            if store is not None:
                store.append(record)
            n_total += 1
            if not record.policy_eval.compliant:
                violations += 1
            if record.outcome.task_success:
                successes += 1
            if record.outcome.user_satisfied:
                satisfied += 1
            cost_sum += record.outcome.cost_delta
            latency_sum += record.latency_ms
            states_seen.add(record.state.state_key)

    return SandboxResult(
        sandbox_id=str(uuid4()),
        candidate_id="canary",
        case_set_id="canary",
        n_trials=1,
        task_success=successes / n_total if n_total else 0.0,
        violation_rate=violations / n_total if n_total else 0.0,
        satisfaction_rate=satisfied / n_total if n_total else 0.0,
        mean_latency_ms=latency_sum / n_total if n_total else 0.0,
        mean_cost=cost_sum / n_total if n_total else 0.0,
        p_action={},
        coverage=sorted(states_seen),
    )


def check_and_rollback(
    version: AgentVersion,
    canary_result: SandboxResult,
    envelope: Envelope,
    boundary: Boundary,
    applied_key: str | None,
    current_memory: LessonMemory,
    current_gates: dict,
    parent_memory: LessonMemory,
    parent_gates: dict,
    canary_n: int,
) -> tuple[bool, LessonMemory, dict, Boundary]:
    """Returns (failed, memory, gates, boundary_after). On failure, restores
    (and returns) the parent memory/gates exactly and contracts the
    boundary; on success, passes `current_memory`/`current_gates` through
    unchanged.

    Owner-authorized recalibration (docs/checkpoints/phase-8b.md "what's
    next" discussion), same reasoning as `negotiate.supervisor_oracle`:
    `canary_result.violation_rate`/`task_success` are point estimates from a
    single, small (`canary_n`-task) canary pass, but were being compared
    against `ENVELOPE_VIOLATION_MAX`/`ENVELOPE_SUCCESS_DROP_MAX` as if exact
    -- the full grid showed this rejecting genuinely-improving candidates
    almost as often as bad ones. `baseline_success` itself is already a
    3-window mean (phase-6.md "Revision", ~3x WINDOW_EPISODES of data) so
    only the noisier canary side gets a tolerance margin here, not the
    baseline. `ENVELOPE_VIOLATION_MAX`/`ENVELOPE_SUCCESS_DROP_MAX` themselves
    are untouched."""
    violation_margin = one_sided_margin(canary_result.violation_rate, canary_n)
    success_margin = one_sided_margin(canary_result.task_success, canary_n)
    success_drop = envelope.baseline_success - canary_result.task_success
    failed = (
        canary_result.violation_rate > ENVELOPE_VIOLATION_MAX + violation_margin
        or success_drop > ENVELOPE_SUCCESS_DROP_MAX + success_margin
    )

    version.canary_result = canary_result
    new_boundary = set(boundary)
    if not failed:
        return False, current_memory, current_gates, new_boundary

    if applied_key is not None:
        new_boundary = contract_boundary(new_boundary, applied_key)
    return True, parent_memory, parent_gates, new_boundary


def _evaluate_on_canary(
    memory: LessonMemory, agent_factory, env, canary_ids: list[str], seed: int
) -> tuple[float, float]:
    """(violation_rate, task_success) of `memory` (with empty gates) on the
    canary split. Cheap on the mock env; live mode would need to cap this."""
    agent = agent_factory(memory, {}, random.Random(seed))
    n_total = violations = successes = 0
    for i, task_id in enumerate(canary_ids):
        result = env.run_episode(task_id, agent, seed * 1_000_003 + i)
        for record in result.records:
            n_total += 1
            if not record.policy_eval.compliant:
                violations += 1
            if record.outcome.task_success:
                successes += 1
    if n_total == 0:
        return 0.0, 0.0
    return violations / n_total, successes / n_total


def distill(
    memory: LessonMemory, agent_factory, env, canary_ids: list[str], seed: int = 0
) -> LessonMemory:
    """Greedy forward selection: start from an empty memory, add lessons
    (ordered by created_t) one at a time, keeping each only if canary
    violation does not rise and success does not fall. Never returns more
    lessons than the input, never worse than the empty-memory baseline."""
    lessons_sorted = sorted(memory._lessons.values(), key=lambda lesson: lesson.created_t)

    selected = LessonMemory(cap=memory.cap)
    best_violation, best_success = _evaluate_on_canary(
        selected, agent_factory, env, canary_ids, seed
    )

    for lesson in lessons_sorted:
        trial = LessonMemory(cap=memory.cap)
        for existing_id in selected.snapshot_ids():
            trial.add(selected._lessons[existing_id])
        trial.add(lesson)
        trial_violation, trial_success = _evaluate_on_canary(
            trial, agent_factory, env, canary_ids, seed
        )
        if trial_violation <= best_violation and trial_success >= best_success:
            selected.add(lesson)
            best_violation, best_success = trial_violation, trial_success

    return selected


def should_distill(
    recent_snapshots: list[BehavioralSnapshot],
    last_decision: AdaptationDecision | None,
    envelope: Envelope,
) -> bool:
    if len(recent_snapshots) < DISTILL_TRIGGER_WINDOWS:
        return False
    windows = recent_snapshots[-DISTILL_TRIGGER_WINDOWS:]
    all_outside = all(
        snapshot.violation_rate > ENVELOPE_VIOLATION_MAX
        or (envelope.baseline_success - snapshot.success_rate) > ENVELOPE_SUCCESS_DROP_MAX
        for snapshot in windows
    )
    return all_outside and last_decision is not None and last_decision.decision == "DEFER"


def maybe_distill(
    snapshot_history: list[BehavioralSnapshot],
    decision_history: list[AdaptationDecision],
    memory: LessonMemory,
    envelope: Envelope,
    agent_factory,
    env,
    canary_ids: list[str],
    agent_id: str,
    agent_version: int,
    memory_version: int,
    seed: int = 0,
) -> AgentVersion | None:
    last_decision = decision_history[-1] if decision_history else None
    if not should_distill(snapshot_history, last_decision, envelope):
        return None

    distilled = distill(memory, agent_factory, env, canary_ids, seed)
    return AgentVersion(
        agent_id=agent_id,
        agent_version=agent_version + 1,
        memory_version=memory_version + 1,
        parent_version=agent_version,
        gates={},
        lesson_ids=distilled.snapshot_ids(),
        canary_result=None,
        alignment_drift_vs_v1=None,
        created_t=snapshot_history[-1].window_end_t,
    )
