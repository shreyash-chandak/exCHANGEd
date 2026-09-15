"""Deterministic task split and candidate replay (guide 7.2)."""

from __future__ import annotations

import copy
import json
import random
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from change.config import (
    CANARY_FRACTION_OF_HELDOUT,
    SANDBOX_HELDOUT_FRACTION,
    SANDBOX_TASKS_PER_CANDIDATE,
)
from change.contracts import Candidate, SandboxResult
from change.generate import apply_candidate_to_memory_and_gates
from change.memory import LessonMemory
from change.store import JsonlStore


class TaskSplit:
    """train / canary / sandbox, deterministic given (env, seed).

    Stratified by `env.stratify_key(task_id)` when the env provides one
    (owner-authorized, docs/checkpoints/phase-7.md "Revision" section): a
    plain shuffle of a small heldout pool (40/40 canary/sandbox out of 400
    tasks) has enough sampling noise in composition to bias Sandbox.run's
    violation_rate away from the live window's, independent of candidate
    quality -- see MockRetailEnv.stratify_key's docstring. Falls back to a
    plain shuffle (the original behavior) for any env without one.
    """

    def __init__(self, env, seed: int):
        rng = random.Random(seed)
        stratify_key = getattr(env, "stratify_key", None)

        strata: dict[object, list[str]] = defaultdict(list)
        if stratify_key is None:
            strata[None] = list(env.task_ids())
        else:
            for task_id in env.task_ids():
                strata[stratify_key(task_id)].append(task_id)

        self.train: list[str] = []
        self.canary: list[str] = []
        self.sandbox: list[str] = []
        for key in sorted(strata, key=repr):
            group = strata[key][:]
            rng.shuffle(group)

            n_heldout = round(len(group) * SANDBOX_HELDOUT_FRACTION)
            heldout = group[:n_heldout]
            self.train.extend(group[n_heldout:])

            n_canary = round(len(heldout) * CANARY_FRACTION_OF_HELDOUT)
            self.canary.extend(heldout[:n_canary])
            self.sandbox.extend(heldout[n_canary:])

        # Bug fix: extending per-stratum in a fixed (sorted-key) order left
        # each list as contiguous blocks by stratum (e.g. every "cancel"
        # task, then every "exchange" task, ...) instead of interleaved.
        # GovernanceLoop cycles through `train` by index
        # (`split.train[episode_counter % len(split.train)]`) and Sandbox.run
        # /canary do the same for `sandbox`/`canary` -- both implicitly rely
        # on a well-mixed order, not just correct proportions. Blocky order
        # meant, e.g., ~50 straight episodes of one task_type before any
        # eligible (return/exchange, out-of-window) task appeared at all,
        # breaking the drift mechanism's intended episode-by-episode mixing.
        # A final shuffle restores interleaving while keeping the
        # stratified, proportionally-representative composition.
        rng.shuffle(self.train)
        rng.shuffle(self.canary)
        rng.shuffle(self.sandbox)

    def save(self, run_dir: Path) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "task_split.json"
        path.write_text(
            json.dumps(
                {"train": self.train, "canary": self.canary, "sandbox": self.sandbox}, indent=2
            )
        )

    @classmethod
    def load(cls, run_dir: Path) -> TaskSplit:
        data = json.loads((run_dir / "task_split.json").read_text())
        split = cls.__new__(cls)
        split.train = data["train"]
        split.canary = data["canary"]
        split.sandbox = data["sandbox"]
        return split


class Sandbox:
    """Replays a candidate on held-out tasks. Records are stored under
    runs/<run_id>/sandbox/ and are never fed to Contextualize."""

    def __init__(self, run_id: str, runs_dir: str = "runs"):
        self.run_id = run_id
        self.store = JsonlStore(Path(runs_dir) / run_id / "sandbox")

    def run(
        self,
        candidate: Candidate,
        agent_factory,
        env,
        task_ids: list[str],
        base_memory: LessonMemory,
        base_gates: dict,
        n_trials: int,
        cycle_idx: int = 0,
        seed: int = 0,
    ) -> SandboxResult:
        if not task_ids:
            raise ValueError("Sandbox.run requires a non-empty sandbox task split")

        memory = copy.deepcopy(base_memory)
        gates = copy.deepcopy(base_gates)
        apply_candidate_to_memory_and_gates(candidate, memory, gates)

        agent = agent_factory(memory, gates, random.Random(seed))

        n_tasks = min(SANDBOX_TASKS_PER_CANDIDATE, len(task_ids))
        selected = [task_ids[(cycle_idx * n_tasks + i) % len(task_ids)] for i in range(n_tasks)]

        n_total = violations = successes = satisfied = 0
        cost_sum = latency_sum = 0.0
        state_action_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for trial in range(n_trials):
            for task_idx, task_id in enumerate(selected):
                episode_seed = seed * 1_000_003 + cycle_idx * 10_000 + trial * 1_000 + task_idx
                result = env.run_episode(task_id, agent, episode_seed)
                for record in result.records:
                    self.store.append(record)
                    n_total += 1
                    if not record.policy_eval.compliant:
                        violations += 1
                    if record.outcome.task_success:
                        successes += 1
                    if record.outcome.user_satisfied:
                        satisfied += 1
                    cost_sum += record.outcome.cost_delta
                    latency_sum += record.latency_ms
                    state_action_counts[record.state.state_key][record.action.value] += 1

        p_action: dict[str, dict[str, float]] = {}
        for state, counts in state_action_counts.items():
            total = sum(counts.values())
            p_action[state] = {a: c / total for a, c in counts.items()}

        return SandboxResult(
            sandbox_id=str(uuid4()),
            candidate_id=candidate.candidate_id,
            case_set_id="sandbox",
            n_trials=n_trials,
            task_success=successes / n_total if n_total else 0.0,
            violation_rate=violations / n_total if n_total else 0.0,
            satisfaction_rate=satisfied / n_total if n_total else 0.0,
            mean_latency_ms=latency_sum / n_total if n_total else 0.0,
            mean_cost=cost_sum / n_total if n_total else 0.0,
            p_action=p_action,
            coverage=list(state_action_counts.keys()),
        )
