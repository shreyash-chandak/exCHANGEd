from change.contracts import CanonicalState, Lesson
from change.memory import LessonMemory

STATE = CanonicalState("return", "delivered", "high", False, "neutral", "t0")


def make_lesson(lesson_id: str, created_t: int, condition_state_key: str | None) -> Lesson:
    return Lesson(
        lesson_id=lesson_id,
        text="t",
        created_t=created_t,
        source_episode_id="e1",
        condition_state_key=condition_state_key,
        prescribed_action="deny",
        generosity=0.0,
    )


def test_add_and_remove_bump_version():
    memory = LessonMemory(cap=10)
    assert memory.version == 0
    memory.add(make_lesson("l1", 0, None))
    assert memory.version == 1
    memory.remove(["l1"])
    assert memory.version == 2
    memory.remove(["does-not-exist"])
    assert memory.version == 2  # no-op removal does not bump version


def test_cap_evicts_oldest_inserted():
    memory = LessonMemory(cap=2)
    memory.add(make_lesson("l1", 0, None))
    memory.add(make_lesson("l2", 1, None))
    memory.add(make_lesson("l3", 2, None))
    assert memory.snapshot_ids() == ["l2", "l3"]


def test_retrieve_prioritizes_exact_then_partial_then_recent():
    memory = LessonMemory(cap=10)
    exact = make_lesson("exact", 0, STATE.state_key)
    partial = make_lesson("partial", 5, "return|processed|low|0|pushy|t0")
    other_type = make_lesson("other", 10, "cancel|pending|low|0|neutral|t0")
    memory.add(other_type)
    memory.add(partial)
    memory.add(exact)

    retrieved = memory.retrieve(STATE, k=3)
    assert [lesson.lesson_id for lesson in retrieved] == ["exact", "partial", "other"]

    top1 = memory.retrieve(STATE, k=1)
    assert [lesson.lesson_id for lesson in top1] == ["exact"]


def test_retrieve_recency_within_same_tier():
    memory = LessonMemory(cap=10)
    memory.add(make_lesson("old", 0, None))
    memory.add(make_lesson("new", 5, None))
    retrieved = memory.retrieve(STATE, k=2)
    assert [lesson.lesson_id for lesson in retrieved] == ["new", "old"]
