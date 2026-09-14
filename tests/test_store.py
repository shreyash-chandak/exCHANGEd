from change.contracts import (
    CanonicalAction,
    CanonicalOutcome,
    CanonicalState,
    ExperienceRecord,
    PolicyEval,
)
from change.store import JsonlStore

STATE = CanonicalState("return", "delivered", "high", True, "neutral", "t0")


def make_record(i: int) -> ExperienceRecord:
    return ExperienceRecord(
        run_id="r1",
        agent_id="alice",
        agent_version=1,
        memory_version=0,
        episode_id=f"e{i}",
        turn_idx=0,
        t_global=i,
        state=STATE,
        action=CanonicalAction.REFUND_FULL,
        outcome=CanonicalOutcome(True, True, True, 10.0),
        policy_eval=PolicyEval(compliant=True, violated_rule_ids=[]),
        latency_ms=100.0,
        tokens_in=10,
        tokens_out=5,
        cost_usd=0.01,
    )


def test_append_and_read_all_preserves_order(tmp_path):
    store = JsonlStore(tmp_path / "run-1")
    records = [make_record(i) for i in range(100)]
    for record in records:
        store.append(record)

    read_back = store.read_all(ExperienceRecord)

    assert len(read_back) == 100
    assert [r.t_global for r in read_back] == list(range(100))
    assert read_back == records


def test_read_all_missing_file_returns_empty(tmp_path):
    store = JsonlStore(tmp_path / "run-2")
    assert store.read_all(ExperienceRecord) == []
