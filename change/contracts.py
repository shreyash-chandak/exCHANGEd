"""Data contracts for the CHANGE governance loop (guide section 2 and 2.1-2.4).

Field names are contracts: add nothing, remove nothing without asking
(CHANGE_poc_agent_guide.md section 0.3). CanonicalState/CanonicalOutcome are
plain frozen dataclasses (not top-level exported schemas — they are nested
inside ExperienceRecord); every other model here is a pydantic BaseModel and
is exported to schemas/ by scripts/export_schemas.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

# =============================================================================
# Canonical state / action / outcome (guide section 2.1-2.3)
# =============================================================================

TaskType = Literal["cancel", "return", "exchange", "modify", "lookup", "other"]
OrderStatus = Literal["pending", "processed", "delivered", "cancelled", "unknown"]
ValueBucket = Literal["low", "mid", "high"]
UserStance = Literal["neutral", "pushy", "distressed"]
PriorTurnsBucket = Literal["t0", "t1to3", "t4plus"]


@dataclass(frozen=True)
class CanonicalState:
    """Canonical retail state (guide section 2.1). Frozen and hashable so it
    can be used directly as a dict key in addition to via `state_key`.
    """

    task_type: TaskType
    order_status: OrderStatus
    value_bucket: ValueBucket
    within_policy_window: bool
    user_stance: UserStance
    prior_turns_bucket: PriorTurnsBucket

    @property
    def state_key(self) -> str:
        return (
            f"{self.task_type}|{self.order_status}|{self.value_bucket}|"
            f"{int(self.within_policy_window)}|{self.user_stance}|{self.prior_turns_bucket}"
        )


class CanonicalAction(str, Enum):
    """Canonical retail action (guide section 2.2)."""

    REFUND_FULL = "refund_full"
    REFUND_PARTIAL = "refund_partial"
    EXCHANGE = "exchange"
    CANCEL = "cancel"
    MODIFY = "modify"
    DENY = "deny"
    ESCALATE = "escalate"
    ASK_CLARIFY = "ask_clarify"
    LOOKUP = "lookup"
    END = "end"


@dataclass(frozen=True)
class CanonicalOutcome:
    """Canonical retail outcome (guide section 2.3)."""

    policy_compliant: bool
    task_success: bool
    user_satisfied: bool
    cost_delta: float = 0.0


# =============================================================================
# Experience (guide sections 2.1 "Instrumentation" and 22/2.1 data contracts)
# =============================================================================


class PolicyEval(BaseModel):
    compliant: bool
    violated_rule_ids: list[str] = Field(default_factory=list)


class ExperienceRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    agent_id: str
    agent_version: int
    memory_version: int
    episode_id: str
    turn_idx: int
    t_global: int
    state: CanonicalState
    action: CanonicalAction
    tools_used: list[str] = Field(default_factory=list)
    outcome: CanonicalOutcome
    policy_eval: PolicyEval
    reward: float | None = None
    latency_ms: float
    tokens_in: int
    tokens_out: int
    cost_usd: float
    lessons_in_context: list[str] = Field(default_factory=list)


# =============================================================================
# Behavioral snapshot / drift
# =============================================================================


class CellAttribution(BaseModel):
    state_key: str
    action: str
    delta_p: float
    lesson_ids: list[str] = Field(default_factory=list)


class DriftScore(BaseModel):
    jsd_weighted: float
    jsd_ci_low: float
    jsd_ci_high: float
    per_state_jsd: dict[str, float] = Field(default_factory=dict)
    top_cells: list[CellAttribution] = Field(default_factory=list)


class BehavioralSnapshot(BaseModel):
    snapshot_id: str
    parent_id: str | None = None
    run_id: str
    agent_id: str
    agent_version: int
    memory_version: int
    window_start_t: int
    window_end_t: int
    n_records: int
    p_action: dict[str, dict[str, float]] = Field(default_factory=dict)
    n_action: dict[str, dict[str, int]] = Field(default_factory=dict)
    p_outcome: dict[str, dict[str, dict[str, float]]] = Field(default_factory=dict)
    p_transition: dict[str, dict[str, dict[str, float]]] = Field(default_factory=dict)
    p_initial: dict[str, float] = Field(default_factory=dict)
    violation_rate: float
    success_rate: float
    satisfaction_rate: float
    mean_cost: float
    mean_latency_ms: float
    drift_vs_parent: DriftScore | None = None
    coverage: list[str] = Field(default_factory=list)


# =============================================================================
# Lessons and candidates (Generate)
# =============================================================================


class Lesson(BaseModel):
    lesson_id: str
    text: str
    created_t: int
    source_episode_id: str
    condition_state_key: str | None = None
    prescribed_action: str | None = None
    generosity: float = 0.0


CandidateKind = Literal["do_nothing", "add_lesson", "remove_lessons", "approval_gate"]
CandidateLayer = Literal["context", "architecture"]


class Candidate(BaseModel):
    candidate_id: str
    kind: CandidateKind
    layer: CandidateLayer
    payload: dict = Field(default_factory=dict)


# =============================================================================
# Anticipate (Prediction)
# =============================================================================

TwinModel = Literal["last_value", "trend_t1"]


class Prediction(BaseModel):
    prediction_id: str
    snapshot_id: str
    candidate_id: str
    twin_model: TwinModel
    horizon: int
    violation_curve_q10: list[float] = Field(default_factory=list)
    violation_curve_q50: list[float] = Field(default_factory=list)
    violation_curve_q90: list[float] = Field(default_factory=list)
    success_q50: float
    cost_ratio_q50: float
    first_exit_t_q10: int | None = None
    first_exit_t_q50: int | None = None
    first_exit_t_q90: int | None = None
    exit_metric: str | None = None
    contributing_cells: list[CellAttribution] = Field(default_factory=list)
    envelope_margin_q50: float


# =============================================================================
# Sandbox
# =============================================================================


class SandboxResult(BaseModel):
    sandbox_id: str
    candidate_id: str
    case_set_id: str
    n_trials: int
    task_success: float
    violation_rate: float
    satisfaction_rate: float
    mean_latency_ms: float
    mean_cost: float
    p_action: dict[str, dict[str, float]] = Field(default_factory=dict)
    coverage: list[str] = Field(default_factory=list)


# =============================================================================
# Harmonize
# =============================================================================


class HarmonizationConstraint(BaseModel):
    constraint_id: str
    detector_id: str
    agents: list[str]
    shared_state_key: str
    evidence: dict = Field(default_factory=dict)
    consensus_action: str


# =============================================================================
# Negotiate / Evolve
# =============================================================================

RiskTier = Literal["low", "medium", "high"]
Decision = Literal["ACCEPT", "ESCALATE", "REJECT", "DEFER"]
SupervisorVerdict = Literal["approved", "rejected", "not_consulted"]


class AdaptationDecision(BaseModel):
    decision_id: str
    cycle_idx: int
    snapshot_id: str
    candidate_id: str
    risk_tier: RiskTier
    in_boundary: bool
    decision: Decision
    supervisor_verdict: SupervisorVerdict
    utility: float
    rationale: dict = Field(default_factory=dict)
    boundary_after: list[str] = Field(default_factory=list)


class AgentVersion(BaseModel):
    agent_id: str
    agent_version: int
    memory_version: int
    parent_version: int | None = None
    gates: dict = Field(default_factory=dict)
    lesson_ids: list[str] = Field(default_factory=list)
    canary_result: SandboxResult | None = None
    alignment_drift_vs_v1: float | None = None
    created_t: int


# Models exported as JSON schemas by scripts/export_schemas.py (12 total).
EXPORTED_MODELS: list[type[BaseModel]] = [
    ExperienceRecord,
    PolicyEval,
    BehavioralSnapshot,
    DriftScore,
    CellAttribution,
    Lesson,
    Candidate,
    Prediction,
    SandboxResult,
    HarmonizationConstraint,
    AdaptationDecision,
    AgentVersion,
]
