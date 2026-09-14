"""Settings and numeric constants (guide section 2.4). Do not change the
default values without asking — they are pinned by CHANGE_poc_agent_guide.md.
All are overridable via environment variables prefixed CHANGE_ (e.g.
CHANGE_SIM_TRAJECTORIES=300 for a faster test run).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHANGE_", env_file=".env", extra="ignore")

    # ---- section 2.5: environment / run configuration ----
    agent_model: str | None = None
    user_model: str | None = None
    extractor_model: str | None = None
    live: bool = False
    runs_dir: str = "runs"

    # ---- section 2.4: numeric constants ----
    window_episodes: int = 50
    min_cell_count: int = 20
    dirichlet_alpha: float = 1.0
    drift_bootstrap_n: int = 200
    drift_alert_jsd: float = 0.05
    envelope_violation_max: float = 0.10
    envelope_success_drop_max: float = 0.05
    envelope_cost_ratio_max: float = 1.3
    sim_trajectories: int = 2000
    sim_horizon: int = 2000
    sim_rolling_window: int = 100
    trend_min_snapshots: int = 3
    trend_logit_clip: float = 6.0
    forecast_horizons: list[int] = [250, 500, 1000]
    lead_time_trigger: int = 300
    sandbox_heldout_fraction: float = 0.20
    canary_fraction_of_heldout: float = 0.50
    sandbox_tasks_per_candidate: int = 25
    sandbox_trials: int = 1
    max_candidates: int = 3
    risk_low_quantile: float = 0.90
    supervisor_success_tol: float = 0.02
    boundary_expand_after: int = 3
    distill_trigger_windows: int = 2
    memory_top_k: int = 3
    memory_cap: int = 200
    utility_lambda_cost: float = 0.5
    utility_mu_latency: float = 0.1
    seeds: list[int] = [0, 1]


settings = Settings()

# Module-level aliases so other modules can `from change.config import X`
# without threading a Settings instance through every call site.
WINDOW_EPISODES = settings.window_episodes
MIN_CELL_COUNT = settings.min_cell_count
DIRICHLET_ALPHA = settings.dirichlet_alpha
DRIFT_BOOTSTRAP_N = settings.drift_bootstrap_n
DRIFT_ALERT_JSD = settings.drift_alert_jsd
ENVELOPE_VIOLATION_MAX = settings.envelope_violation_max
ENVELOPE_SUCCESS_DROP_MAX = settings.envelope_success_drop_max
ENVELOPE_COST_RATIO_MAX = settings.envelope_cost_ratio_max
SIM_TRAJECTORIES = settings.sim_trajectories
SIM_HORIZON = settings.sim_horizon
SIM_ROLLING_WINDOW = settings.sim_rolling_window
TREND_MIN_SNAPSHOTS = settings.trend_min_snapshots
TREND_LOGIT_CLIP = settings.trend_logit_clip
FORECAST_HORIZONS = settings.forecast_horizons
LEAD_TIME_TRIGGER = settings.lead_time_trigger
SANDBOX_HELDOUT_FRACTION = settings.sandbox_heldout_fraction
CANARY_FRACTION_OF_HELDOUT = settings.canary_fraction_of_heldout
SANDBOX_TASKS_PER_CANDIDATE = settings.sandbox_tasks_per_candidate
SANDBOX_TRIALS = settings.sandbox_trials
MAX_CANDIDATES = settings.max_candidates
RISK_LOW_QUANTILE = settings.risk_low_quantile
SUPERVISOR_SUCCESS_TOL = settings.supervisor_success_tol
BOUNDARY_EXPAND_AFTER = settings.boundary_expand_after
DISTILL_TRIGGER_WINDOWS = settings.distill_trigger_windows
MEMORY_TOP_K = settings.memory_top_k
MEMORY_CAP = settings.memory_cap
UTILITY_LAMBDA_COST = settings.utility_lambda_cost
UTILITY_MU_LATENCY = settings.utility_mu_latency
SEEDS = settings.seeds
