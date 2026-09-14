from tau2.domains.retail.environment import get_environment, get_tasks

RETAIL_BASE_SPLIT_TASK_COUNT = 114


def test_tau2_retail_domain_loads_offline():
    env = get_environment()
    policy = env.get_policy()
    assert isinstance(policy, str)
    assert len(policy.strip()) > 0

    tasks = get_tasks(task_split_name="base")
    assert len(tasks) == RETAIL_BASE_SPLIT_TASK_COUNT
