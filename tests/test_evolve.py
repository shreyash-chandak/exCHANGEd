import copy

from change.anticipate.envelope import Envelope
from change.contracts import AgentVersion, Lesson, SandboxResult
from change.evolve import _evaluate_on_canary, check_and_rollback, distill
from change.memory import LessonMemory
from envs.mock.mock_agent import MockAgent
from envs.mock.mock_env import MockRetailEnv


def _lesson(lesson_id: str, created_t: int, generosity: float = 0.0) -> Lesson:
    return Lesson(
        lesson_id=lesson_id,
        text="t",
        created_t=created_t,
        source_episode_id="e",
        condition_state_key=None,
        prescribed_action=None,
        generosity=generosity,
    )


def _sandbox_result(violation_rate: float, task_success: float) -> SandboxResult:
    return SandboxResult(
        sandbox_id="sb",
        candidate_id="c1",
        case_set_id="canary",
        n_trials=1,
        task_success=task_success,
        violation_rate=violation_rate,
        satisfaction_rate=0.9,
        mean_latency_ms=800.0,
        mean_cost=10.0,
    )


def test_rollback_restores_exact_lesson_ids_and_gates():
    parent_memory = LessonMemory()
    parent_memory.add(_lesson("l1", 0))
    parent_memory.add(_lesson("l2", 1))
    parent_gates = {"approval_gate": {"value_bucket": "high"}}

    current_memory = copy.deepcopy(parent_memory)
    current_memory.add(_lesson("l3", 2))  # simulates a candidate having been applied
    current_gates = {}  # simulates a gate having been cleared/changed

    envelope = Envelope(baseline_success=0.9, baseline_cost=10.0)
    version = AgentVersion(
        agent_id="alice",
        agent_version=2,
        memory_version=3,
        parent_version=1,
        gates={},
        lesson_ids=[],
        canary_result=None,
        alignment_drift_vs_v1=None,
        created_t=100,
    )
    failing_canary = _sandbox_result(violation_rate=0.5, task_success=0.5)  # breaches envelope

    failed, restored_memory, restored_gates, boundary = check_and_rollback(
        version,
        failing_canary,
        envelope,
        boundary={"context:low"},
        applied_key="context:low",
        current_memory=current_memory,
        current_gates=current_gates,
        parent_memory=parent_memory,
        parent_gates=parent_gates,
    )

    assert failed is True
    assert sorted(restored_memory.snapshot_ids()) == ["l1", "l2"]
    assert restored_gates == parent_gates
    assert "context:low" not in boundary


def test_no_rollback_when_canary_passes():
    parent_memory = LessonMemory()
    current_memory = copy.deepcopy(parent_memory)
    current_memory.add(_lesson("l1", 0))

    envelope = Envelope(baseline_success=0.9, baseline_cost=10.0)
    version = AgentVersion(
        agent_id="alice",
        agent_version=2,
        memory_version=1,
        parent_version=1,
        gates={},
        lesson_ids=[],
        canary_result=None,
        alignment_drift_vs_v1=None,
        created_t=100,
    )
    passing_canary = _sandbox_result(violation_rate=0.01, task_success=0.9)

    failed, restored_memory, _restored_gates, boundary = check_and_rollback(
        version,
        passing_canary,
        envelope,
        boundary={"context:low"},
        applied_key="context:low",
        current_memory=current_memory,
        current_gates={},
        parent_memory=parent_memory,
        parent_gates={},
    )

    assert failed is False
    assert restored_memory.snapshot_ids() == ["l1"]
    assert "context:low" in boundary


def _agent_factory(memory, gates, rng):
    return MockAgent(memory=memory, rng=rng, gates=gates)


def test_distill_never_returns_more_lessons_than_input_and_never_worse_than_empty():
    env = MockRetailEnv(n_tasks=400, seed=0, run_id="distill-test")
    canary_ids = env.task_ids()[:10]

    memory = LessonMemory()
    # a mix of helpful (corrective, negative generosity) and harmful
    # (generous, positive generosity) lessons
    for i in range(6):
        generosity = 0.3 if i % 2 == 0 else -0.3
        memory.add(_lesson(f"l{i}", created_t=i, generosity=generosity))

    empty_violation, empty_success = _evaluate_on_canary(
        LessonMemory(), _agent_factory, env, canary_ids, seed=0
    )

    distilled = distill(memory, _agent_factory, env, canary_ids, seed=0)

    assert len(distilled.snapshot_ids()) <= len(memory.snapshot_ids())

    distilled_violation, distilled_success = _evaluate_on_canary(
        distilled, _agent_factory, env, canary_ids, seed=0
    )
    assert distilled_violation <= empty_violation
    assert distilled_success >= empty_success
