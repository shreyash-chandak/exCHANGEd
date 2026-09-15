"""Governance loop tying Generate/Sandbox/Negotiate/Evolve together across
systems A0-FULL (guide 7.5)."""

from __future__ import annotations

import copy
import random
from pathlib import Path
from uuid import uuid4

import numpy as np

from change.anticipate.counterfactual import patch_from_sandbox, rank
from change.anticipate.envelope import Envelope, make_prediction
from change.anticipate.simulator import simulate
from change.anticipate.trend import LastValueModel, TrendModel
from change.config import (
    DRIFT_ALERT_JSD,
    ENVELOPE_VIOLATION_MAX,
    LEAD_TIME_TRIGGER,
    SANDBOX_TRIALS,
    SIM_HORIZON,
    SIM_TRAJECTORIES,
    WINDOW_EPISODES,
)
from change.contextualize import build_snapshot
from change.contracts import (
    AdaptationDecision,
    AgentVersion,
    BehavioralSnapshot,
    Candidate,
    DriftScore,
    Prediction,
)
from change.evolve import apply, canary, check_and_rollback, distill, should_distill
from change.generate import CandidateGenerator, MockLessonExtractor
from change.memory import LessonMemory
from change.negotiate import DEFAULT_BOUNDARY, Boundary
from change.negotiate import decide as negotiate_decide
from change.negotiate import risk_tier as negotiate_risk_tier
from change.sandbox import Sandbox, TaskSplit
from change.store import JsonlStore

SYSTEMS = ("A0", "A1", "A2", "A3", "A4", "FULL")


def _seeded_rng(seed: int, cycle_idx: int, tag: str) -> np.random.Generator:
    return np.random.default_rng([seed, cycle_idx, abs(hash(tag)) % (2**31 - 1)])


def _do_nothing_candidate() -> Candidate:
    return Candidate(candidate_id=str(uuid4()), kind="do_nothing", layer="context", payload={})


def _g3_gate_candidate() -> Candidate:
    return Candidate(
        candidate_id=str(uuid4()),
        kind="approval_gate",
        layer="architecture",
        payload={"value_bucket": "high", "require_escalate_when_outside_window": True},
    )


class GovernanceLoop:
    def __init__(
        self,
        env,
        agent_factory,
        system: str,
        drift_condition: dict,
        seed: int,
        run_id: str,
        runs_dir: str = "runs",
    ):
        if system not in SYSTEMS:
            raise ValueError(f"unknown system {system!r}, expected one of {SYSTEMS}")
        self.env = env
        self.agent_factory = agent_factory
        self.system = system
        self.seed = seed
        self.run_id = run_id
        self.feedback = drift_condition.get("feedback", "truth")

        self.memory = LessonMemory()
        self.gates: dict = {}
        self.agent = agent_factory(self.memory, self.gates, random.Random(seed))

        run_dir = Path(runs_dir) / run_id
        self.store = JsonlStore(run_dir)
        self.extractor = MockLessonExtractor(feedback=self.feedback)
        self.generator = CandidateGenerator(mode="mock")
        self.sandbox = Sandbox(run_id, runs_dir)

        self.split = TaskSplit(env, seed)
        self.split.save(run_dir)

        self.boundary: Boundary = set(DEFAULT_BOUNDARY)
        self.snapshot_history: list[BehavioralSnapshot] = []
        self.decision_history: list[AdaptationDecision] = []
        self.envelope: Envelope | None = None
        self.baseline_latency = 0.0
        self.agent_version = 1
        self._episode_counter = 0
        self.cycle_idx = 0
        self._parent_snapshot: BehavioralSnapshot | None = None
        self._parent_records: list = []

        self.store.append(
            AgentVersion(
                agent_id=self.agent.agent_id,
                agent_version=1,
                memory_version=0,
                parent_version=None,
                gates={},
                lesson_ids=[],
                canary_result=None,
                alignment_drift_vs_v1=None,
                created_t=0,
            )
        )

    # ------------------------------------------------------------------
    # driving the loop
    # ------------------------------------------------------------------

    def run(self, n_episodes: int) -> list[dict]:
        results = []
        while self._episode_counter < n_episodes:
            results.append(self.run_cycle())
        return results

    def run_cycle(self) -> dict:
        snapshot = self._run_episodes_until_snapshot()
        drift = snapshot.drift_vs_parent
        self.snapshot_history.append(snapshot)

        if self.envelope is None:
            self.envelope = Envelope(
                baseline_success=snapshot.success_rate, baseline_cost=snapshot.mean_cost
            )
            self.baseline_latency = snapshot.mean_latency_ms

        do_nothing_predictions = self._predict_do_nothing(snapshot)
        trend_pred = do_nothing_predictions["trend_t1"]

        result = {
            "cycle": self.cycle_idx,
            "t": snapshot.window_end_t,
            "violation": snapshot.violation_rate,
            "jsd": drift.jsd_weighted if drift else 0.0,
            "predicted_exit": trend_pred.first_exit_t_q50,
            "decision": None,
            "candidate_kind": None,
            "version": self.agent_version,
        }

        if self.system in ("A0", "A1", "A2"):
            self._run_simple_system(snapshot, drift, trend_pred, result)
        else:
            self._run_full_system(snapshot, drift, trend_pred, result)

        result["version"] = self.agent_version
        self.cycle_idx += 1
        return result

    def _run_episodes_until_snapshot(self) -> BehavioralSnapshot:
        """Runs exactly WINDOW_EPISODES full episodes and builds one snapshot
        from all of their records directly via build_snapshot.

        Deviation from a literal reading of "feeding records to Snapshotter":
        Snapshotter's own dual trigger (window OR memory_version delta >= 10)
        emits far more often than every 50 episodes once a lesson extractor
        is attached, the same finding already documented in
        docs/checkpoints/phase-5.md. Windows of ~15-20 records are noisy
        enough that even flat (D1) behavior spuriously crosses
        ENVELOPE_VIOLATION_MAX by chance sometimes, which would break "A0 on
        d1 produces zero adaptations" (guide 7.7) for reasons unrelated to
        A0's own logic. Using a fixed 50-episode window here (same fix
        already applied in test_contextualize.py) keeps "a cycle is one
        snapshot window" true while giving stable-enough estimates. See
        docs/checkpoints/phase-7.md.
        """
        episode_ids: list[str] = []
        by_episode: dict[str, list] = {}

        for _ in range(WINDOW_EPISODES):
            task_id = self.split.train[self._episode_counter % len(self.split.train)]
            episode_seed = self.seed * 1_000_003 + self._episode_counter
            result = self.env.run_episode(task_id, self.agent, episode_seed)
            self._episode_counter += 1

            episode_id = result.records[0].episode_id
            episode_ids.append(episode_id)
            by_episode[episode_id] = result.records
            for record in result.records:
                self.store.append(record)

            for lesson in self.extractor.extract(
                result.records, episode_id=episode_id, t_global=self.env.t_global
            ):
                self.memory.add(lesson)

        all_records = [r for eid in episode_ids for r in by_episode[eid]]
        snapshot = build_snapshot(
            all_records,
            parent=self._parent_snapshot,
            run_id=self.run_id,
            snapshot_id=f"{self.run_id}-cycle{self.cycle_idx}",
            parent_records=self._parent_records,
        )
        self.store.append(snapshot)
        self._parent_snapshot = snapshot
        self._parent_records = all_records
        return snapshot

    def _predict_do_nothing(self, snapshot: BehavioralSnapshot) -> dict[str, Prediction]:
        predictions = {}
        for model_cls, twin_model in [(LastValueModel, "last_value"), (TrendModel, "trend_t1")]:
            model = model_cls().fit(self.snapshot_history)
            rng = _seeded_rng(self.seed, self.cycle_idx, twin_model)
            sim = simulate(model, snapshot, n_traj=SIM_TRAJECTORIES, horizon=SIM_HORIZON, rng=rng)
            prediction = make_prediction(
                snapshot, "do_nothing", model, sim, self.envelope, twin_model
            )
            self.store.append(prediction)
            predictions[twin_model] = prediction
        return predictions

    # ------------------------------------------------------------------
    # A0 / A1 / A2: blunt threshold trigger, fixed G3 gate, no sandbox
    # ------------------------------------------------------------------

    def _run_simple_system(
        self,
        snapshot: BehavioralSnapshot,
        drift: DriftScore | None,
        trend_pred: Prediction,
        result: dict,
    ) -> None:
        if self.system == "A0":
            triggered = snapshot.violation_rate > ENVELOPE_VIOLATION_MAX
        elif self.system == "A1":
            triggered = drift is not None and drift.jsd_weighted > DRIFT_ALERT_JSD
        else:  # A2
            triggered = (
                trend_pred.first_exit_t_q50 is not None
                and (trend_pred.first_exit_t_q50 - snapshot.window_end_t) <= LEAD_TIME_TRIGGER
            )

        if triggered:
            candidate = _g3_gate_candidate()
            apply(candidate, self.memory, self.gates)
            self.agent_version += 1
            self._record_version(snapshot)
        else:
            candidate = _do_nothing_candidate()

        decision = AdaptationDecision(
            decision_id=str(uuid4()),
            cycle_idx=self.cycle_idx,
            snapshot_id=snapshot.snapshot_id,
            candidate_id=candidate.candidate_id,
            risk_tier="high" if triggered else "low",
            in_boundary=False,
            decision="ACCEPT",
            supervisor_verdict="not_consulted",
            utility=0.0,
            rationale={"system": self.system, "triggered": triggered},
            boundary_after=sorted(self.boundary),
        )
        self._finish_decision(decision, candidate, result)

    # ------------------------------------------------------------------
    # A3 / A4 / FULL: Generate -> Sandbox -> counterfactual Predict -> pick
    # ------------------------------------------------------------------

    def _run_full_system(
        self,
        snapshot: BehavioralSnapshot,
        drift: DriftScore | None,
        trend_pred: Prediction,
        result: dict,
    ) -> None:
        triggered = (
            trend_pred.first_exit_t_q50 is not None
            and (trend_pred.first_exit_t_q50 - snapshot.window_end_t) <= LEAD_TIME_TRIGGER
        )

        if not triggered:
            candidate = _do_nothing_candidate()
            decision = AdaptationDecision(
                decision_id=str(uuid4()),
                cycle_idx=self.cycle_idx,
                snapshot_id=snapshot.snapshot_id,
                candidate_id=candidate.candidate_id,
                risk_tier="low",
                in_boundary=True,
                decision="ACCEPT",
                supervisor_verdict="not_consulted",
                utility=0.0,
                rationale={"system": self.system, "triggered": False},
                boundary_after=sorted(self.boundary),
            )
            self._finish_decision(decision, candidate, result)
            return

        candidates, predictions, sandboxes = self._evaluate_candidates(snapshot, drift)
        applied_flag = False
        memory_backup = gates_backup = None

        if self.system == "A3":
            ranked = rank(list(predictions.values()))
            top = ranked[0]
            candidate = candidates[top.candidate_id]
            if candidate.kind != "do_nothing":
                memory_backup, gates_backup = copy.deepcopy(self.memory), copy.deepcopy(self.gates)
                apply(candidate, self.memory, self.gates)
                self.agent_version += 1
                applied_flag = True
            decision = AdaptationDecision(
                decision_id=str(uuid4()),
                cycle_idx=self.cycle_idx,
                snapshot_id=snapshot.snapshot_id,
                candidate_id=candidate.candidate_id,
                risk_tier=negotiate_risk_tier(top, candidate, self.envelope.baseline_success),
                in_boundary=False,
                decision="ACCEPT",
                supervisor_verdict="not_consulted",
                utility=top.envelope_margin_q50,
                rationale={"system": self.system, "ranked_by": "envelope_margin_q50"},
                boundary_after=sorted(self.boundary),
            )
        else:  # A4 or FULL
            decision, new_boundary = negotiate_decide(
                self.cycle_idx,
                snapshot,
                candidates,
                predictions,
                sandboxes,
                self.boundary,
                self.decision_history,
                live_violation=snapshot.violation_rate,
                live_success=snapshot.success_rate,
                baseline_success=self.envelope.baseline_success,
                baseline_cost=self.envelope.baseline_cost,
                baseline_latency=self.baseline_latency,
            )
            self.boundary = new_boundary
            candidate = candidates[decision.candidate_id]
            should_apply = decision.decision == "ACCEPT" or (
                decision.decision == "ESCALATE" and decision.supervisor_verdict == "approved"
            )
            if should_apply and candidate.kind != "do_nothing":
                memory_backup, gates_backup = copy.deepcopy(self.memory), copy.deepcopy(self.gates)
                apply(candidate, self.memory, self.gates)
                self.agent_version += 1
                applied_flag = True

        self._finish_decision(decision, candidate, result)

        if applied_flag:
            self._record_version(snapshot)

        if self.system == "FULL" and applied_flag:
            self._run_evolve(snapshot, decision, memory_backup, gates_backup)

    def _evaluate_candidates(self, snapshot: BehavioralSnapshot, drift: DriftScore | None):
        candidates_list = self.generator.propose(snapshot, drift, self.memory, self.gates)
        candidates = {c.candidate_id: c for c in candidates_list}
        predictions: dict[str, Prediction] = {}
        sandboxes: dict = {}
        model = TrendModel().fit(self.snapshot_history)

        for cid, candidate in candidates.items():
            sandbox_result = self.sandbox.run(
                candidate,
                self.agent_factory,
                self.env,
                self.split.sandbox,
                self.memory,
                self.gates,
                n_trials=SANDBOX_TRIALS,
                cycle_idx=self.cycle_idx,
                seed=self.seed,
            )
            self.store.append(sandbox_result)
            patches = patch_from_sandbox(sandbox_result)
            rng = _seeded_rng(self.seed, self.cycle_idx, cid)
            sim = simulate(
                model,
                snapshot,
                n_traj=SIM_TRAJECTORIES,
                horizon=SIM_HORIZON,
                rng=rng,
                patches=patches,
            )
            prediction = make_prediction(snapshot, cid, model, sim, self.envelope, "trend_t1")
            self.store.append(prediction)
            predictions[cid] = prediction
            sandboxes[cid] = sandbox_result

        return candidates, predictions, sandboxes

    def _run_evolve(self, snapshot, decision, memory_backup, gates_backup) -> None:
        canary_result = canary(
            self.agent_factory, self.env, self.split.canary, self.memory, self.gates, seed=self.seed
        )
        self.store.append(canary_result)

        applied_key = decision.rationale.get("key")
        version = AgentVersion(
            agent_id=self.agent.agent_id,
            agent_version=self.agent_version,
            memory_version=self.memory.version,
            parent_version=self.agent_version - 1,
            gates=dict(self.gates),
            lesson_ids=self.memory.snapshot_ids(),
            canary_result=None,
            alignment_drift_vs_v1=None,
            created_t=snapshot.window_end_t,
        )
        failed, restored_memory, restored_gates, new_boundary = check_and_rollback(
            version,
            canary_result,
            self.envelope,
            self.boundary,
            applied_key,
            current_memory=self.memory,
            current_gates=self.gates,
            parent_memory=memory_backup,
            parent_gates=gates_backup,
        )
        self.boundary = new_boundary
        if failed:
            self.memory = restored_memory
            self.gates = restored_gates
            self.agent.memory = self.memory
            self.agent.gates = self.gates
            self.agent_version -= 1
        self.store.append(version)

        last_decision = self.decision_history[-1] if self.decision_history else None
        if should_distill(self.snapshot_history, last_decision, self.envelope):
            distilled = distill(
                self.memory, self.agent_factory, self.env, self.split.canary, seed=self.seed
            )
            self.memory = distilled
            self.agent.memory = self.memory
            self.agent_version += 1
            self._record_version(snapshot)

    # ------------------------------------------------------------------
    # bookkeeping
    # ------------------------------------------------------------------

    def _finish_decision(
        self, decision: AdaptationDecision, candidate: Candidate, result: dict
    ) -> None:
        self.store.append(decision)
        self.decision_history.append(decision)
        result["decision"] = decision.decision
        result["candidate_kind"] = candidate.kind

    def _record_version(self, snapshot: BehavioralSnapshot) -> None:
        version = AgentVersion(
            agent_id=self.agent.agent_id,
            agent_version=self.agent_version,
            memory_version=self.memory.version,
            parent_version=self.agent_version - 1,
            gates=dict(self.gates),
            lesson_ids=self.memory.snapshot_ids(),
            canary_result=None,
            alignment_drift_vs_v1=None,
            created_t=snapshot.window_end_t,
        )
        self.store.append(version)
