from change.contracts import Candidate
from change.memory import LessonMemory
from change.sandbox import Sandbox, TaskSplit
from envs.mock.mock_agent import MockAgent
from envs.mock.mock_env import MockRetailEnv


def _agent_factory(memory, gates, rng):
    return MockAgent(memory=memory, rng=rng, gates=gates)


def test_split_is_deterministic():
    env = MockRetailEnv(n_tasks=400, seed=0, run_id="r")
    split1 = TaskSplit(env, seed=0)
    split2 = TaskSplit(env, seed=0)
    assert split1.train == split2.train
    assert split1.canary == split2.canary
    assert split1.sandbox == split2.sandbox


def test_split_is_disjoint_and_covers_all_tasks():
    env = MockRetailEnv(n_tasks=400, seed=0, run_id="r")
    split = TaskSplit(env, seed=0)
    all_ids = set(split.train) | set(split.canary) | set(split.sandbox)
    assert all_ids == set(env.task_ids())
    assert not (set(split.train) & set(split.canary))
    assert not (set(split.train) & set(split.sandbox))
    assert not (set(split.canary) & set(split.sandbox))


def test_split_save_and_load_round_trip(tmp_path):
    env = MockRetailEnv(n_tasks=400, seed=0, run_id="r")
    split = TaskSplit(env, seed=0)
    split.save(tmp_path)
    loaded = TaskSplit.load(tmp_path)
    assert loaded.train == split.train
    assert loaded.canary == split.canary
    assert loaded.sandbox == split.sandbox


def test_sandbox_records_never_appear_in_main_store(tmp_path):
    env = MockRetailEnv(n_tasks=400, seed=0, run_id="sbtest")
    split = TaskSplit(env, seed=0)
    memory = LessonMemory()
    candidate = Candidate(candidate_id="do_nothing", kind="do_nothing", layer="context", payload={})

    sandbox = Sandbox("sbtest", runs_dir=str(tmp_path))
    result = sandbox.run(
        candidate, _agent_factory, env, split.sandbox, memory, {}, n_trials=1, cycle_idx=0, seed=0
    )

    assert result.n_trials == 1
    sandbox_file = tmp_path / "sbtest" / "sandbox" / "ExperienceRecord.jsonl"
    assert sandbox_file.exists()
    main_file = tmp_path / "sbtest" / "ExperienceRecord.jsonl"
    assert not main_file.exists()
