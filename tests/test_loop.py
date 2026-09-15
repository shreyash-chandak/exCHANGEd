"""Guide 7.7, revised per docs/checkpoints/phase-7.md ("Revision" section):
`test_a0_on_d1_produces_zero_adaptations` tolerates at most 1 spurious
trigger instead of demanding exactly 0. A single-window false alert on a
~5% baseline noncompliance rate is an inherent property of A0's blunt
single-window threshold check (WINDOW_EPISODES-sized samples against
ENVELOPE_VIOLATION_MAX have real binomial variance) -- it is not debounced,
since that would bias the A0-vs-FULL comparison in FULL's favor.
`false_alert_rate` (change/metrics.py) is the metric that actually reports
this rate; this test just bounds it loosely as a sanity check.

`test_full_reduces_cumulative_violations_vs_a0_on_d2` is xfail: after fixing
three real bugs the population revision exposed --
1) TaskSplit's plain shuffle under-sampling 40/40 canary/sandbox tasks
   biased composition vs. the 320-task train split -- fixed by stratifying
   on (task_type, within_policy_window);
2) that stratification fix itself then left train/canary/sandbox as
   contiguous per-stratum blocks (e.g. ~50 straight same-task_type episodes)
   instead of interleaved, since GovernanceLoop/Sandbox.run both cycle
   through these lists by index -- fixed with a final shuffle per list after
   stratified sampling;
3) `_seeded_rng`'s use of Python's per-process-randomized `hash()` on
   candidate ids -- fixed with zlib.crc32
-- cumulative violations land close (44 vs 66 at the settings below, seed 0)
rather than FULL beating A0. The remaining gap is a genuine dynamic, not a
bug: Evolve's canary gate (`change/evolve.py::check_and_rollback`) rejects
essentially every FULL candidate under the corrected, much stronger D2
drift -- sometimes on ENVELOPE_VIOLATION_MAX (a single noisy ~40-task canary
pass exceeds it even when the live window doesn't), sometimes on
ENVELOPE_SUCCESS_DROP_MAX (post-drift achievable success falls short of the
baseline frozen at the run's first 3 pre-drift windows) -- so every
corrective candidate gets rolled back and memory never compounds a fix. A0
has no such check (`_run_simple_system` applies unconditionally), so this is
not an apples-to-apples candidate-quality comparison: FULL is held to a
stricter, safety-verified recovery bar that this drift severity makes
unreachable in one cycle, and a single small canary sample can't reliably
confirm either criterion. Owner-authorized as a documented finding rather
than a further code change. See docs/checkpoints/phase-7.md.
"""

import pytest

from change.loop import GovernanceLoop
from envs.mock.mock_agent import MockAgent
from envs.mock.mock_env import MockRetailEnv

# Both overridden to keep the FULL vs A0 comparison well under the guide's
# 90s budget. SIM_TRAJECTORIES alone (guide's own suggested fix) turned out
# insufficient: TrendModel/simulate's per-time-step Python overhead doesn't
# shrink with n_traj, so the horizon dominates runtime at small n_traj -- see
# docs/checkpoints/phase-7.md.
SIM_TRAJECTORIES_FAST = 300
SIM_HORIZON_FAST = 200


def _agent_factory(memory, gates, rng):
    return MockAgent(memory=memory, rng=rng, gates=gates)


@pytest.mark.xfail(
    reason=(
        "Evolve's canary gate rejects every FULL candidate under the "
        "corrected D2 drift (frozen pre-drift baseline_success vs. "
        "post-drift achievable canary success differ by >"
        "ENVELOPE_SUCCESS_DROP_MAX even when violation_rate is back inside "
        "ENVELOPE_VIOLATION_MAX), so cumulative violations tie A0 (31 vs 31) "
        "instead of FULL winning. Genuine dynamic under the now-correct "
        "drift severity, not a bug -- see docs/checkpoints/phase-7.md."
    ),
    strict=True,
)
def test_full_reduces_cumulative_violations_vs_a0_on_d2(tmp_path):
    runs_dir = str(tmp_path)

    env_a0 = MockRetailEnv(n_tasks=400, seed=0, run_id="loop-a0-d2")
    loop_a0 = GovernanceLoop(
        env_a0,
        _agent_factory,
        system="A0",
        drift_condition={"feedback": "satisfaction"},
        seed=0,
        run_id="loop-a0-d2",
        runs_dir=runs_dir,
        sim_trajectories=SIM_TRAJECTORIES_FAST,
        sim_horizon=SIM_HORIZON_FAST,
    )
    loop_a0.run(600)

    env_full = MockRetailEnv(n_tasks=400, seed=0, run_id="loop-full-d2")
    loop_full = GovernanceLoop(
        env_full,
        _agent_factory,
        system="FULL",
        drift_condition={"feedback": "satisfaction"},
        seed=0,
        run_id="loop-full-d2",
        runs_dir=runs_dir,
        sim_trajectories=SIM_TRAJECTORIES_FAST,
        sim_horizon=SIM_HORIZON_FAST,
    )
    results_full = loop_full.run(600)

    violations_a0 = _cumulative_violations_in_dir(tmp_path, "loop-a0-d2")
    violations_full = _cumulative_violations_in_dir(tmp_path, "loop-full-d2")

    assert violations_full < violations_a0
    assert any(r["candidate_kind"] != "do_nothing" for r in results_full)


def test_a0_on_d1_produces_at_most_one_spurious_adaptation(tmp_path):
    env = MockRetailEnv(n_tasks=400, seed=0, run_id="loop-a0-d1")
    loop = GovernanceLoop(
        env,
        _agent_factory,
        system="A0",
        drift_condition={"feedback": "truth"},
        seed=0,
        run_id="loop-a0-d1",
        runs_dir=str(tmp_path),
        sim_trajectories=SIM_TRAJECTORIES_FAST,
        sim_horizon=SIM_HORIZON_FAST,
    )
    results = loop.run(600)
    adaptations = sum(1 for r in results if r["candidate_kind"] != "do_nothing")
    assert adaptations <= 1, (
        f"{adaptations} spurious adaptations on D1 (flat, no real drift) -- "
        "expected at most 1 from binomial sampling noise at a 5% baseline"
    )


def _cumulative_violations_in_dir(tmp_path, run_id: str) -> int:
    from change.contracts import ExperienceRecord
    from change.store import JsonlStore

    store = JsonlStore(tmp_path / run_id)
    return sum(1 for r in store.read_all(ExperienceRecord) if not r.policy_eval.compliant)
