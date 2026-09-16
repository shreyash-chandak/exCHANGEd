"""Live smoke test for the retail domain (session-2 guide 4b.4). Runs 2
real episodes through Ollama/Qwen3.5 and asserts every record has a
nonempty state_key, an action from the CanonicalAction set, and a
populated policy_eval -- CHANGE_LIVE=1 required (deselected by default,
`pytest -m "not live"`)."""

import pytest

from change.contracts import CanonicalAction

pytestmark = pytest.mark.live


def test_two_retail_episodes_produce_well_formed_records(tmp_path):
    from envs.tau2.adapter import Tau2Env

    env = Tau2Env(domain="retail", run_id="retail-live-test", max_steps=15)
    task_ids = env.task_ids()[:2]
    assert len(task_ids) == 2

    for task_id in task_ids:
        result = env.run_episode(task_id, agent=None, seed=0)
        assert result.records, f"{task_id} produced no records"
        for record in result.records:
            assert record.state.state_key, "empty state_key"
            assert record.action in CanonicalAction
            assert record.policy_eval is not None
