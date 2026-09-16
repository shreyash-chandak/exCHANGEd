"""No-memory baseline gate (session-2 guide 4.2): how well does the
configured model follow policy with empty memory and no gates? Calls
Tau2Env.run_episode (tau2's own built-in llm_agent), not run_live_episode
(the memory-injecting LessonAgent, phase 4c) -- "empty memory, no gates"
means memory never exists at all here, not just starts empty.

Reports: violation rate, task success rate, derail rate (episodes ending
without any write action at all -- not even deny/escalate), mean turns,
mean seconds/episode, and violations broken down by rule id.
"""

from __future__ import annotations

import time
from pathlib import Path

import typer

from change.config import LIVE, settings
from change.store import JsonlStore

app = typer.Typer(add_completion=False)

_WRITE_TOOLS_BY_DOMAIN = {
    "refunds": {
        "refund_full",
        "refund_partial",
        "exchange_items",
        "cancel_order",
        "deny_request",
        "escalate",
    },
    # retail's tools that actually mutate the DB or hand off to a human --
    # matches envs/tau2/adapter.py's _RETAIL_WRITE_TOOLS plus the escalate
    # equivalent (transfer_to_human_agents).
    "retail": {
        "cancel_pending_order",
        "return_delivered_order_items",
        "exchange_delivered_order_items",
        "modify_pending_order_address",
        "modify_pending_order_items",
        "modify_pending_order_payment",
        "modify_user_address",
        "transfer_to_human_agents",
    },
}


@app.command()
def main(
    domain: str = typer.Option(..., help="'refunds' or 'retail'."),
    n: int = typer.Option(50, help="Number of tasks to run."),
    seed: int = typer.Option(0),
    run_id: str = typer.Option(None, "--run-id", help="Defaults to '<domain>-baseline'."),
    runs_dir: str = typer.Option(settings.runs_dir),
    max_steps: int = typer.Option(
        20,
        "--max-steps",
        help=(
            "tau2 orchestrator step budget per episode (Tau2Env's own default is 20). "
            "Owner-authorized override (phase-4.2 baseline gate STOP, docs/checkpoints/"
            "phase-4.2.md): retail's derail rate clustered at ~11 turns, consistent "
            "with 20 being exhausted mid-conversation on multi-lookup tasks."
        ),
    ),
    drop_rules: str = typer.Option(
        "",
        "--drop-rules",
        help=(
            "comma-separated rule ids to exclude from this run's violation_rate/gate "
            "calculation only (guide 4.2.2 step 2: 'drop R8 and R10 from grading, keep "
            "in policy') -- policy.md is untouched, oracle.py/grade_write_action still "
            "detect these rules, and every record's own policy_eval.violated_rule_ids "
            "is written to disk unfiltered. Only this script's PASS/FAIL summary drops "
            "them, e.g. --drop-rules R8,R10."
        ),
    ),
    stance: str = typer.Option(
        "",
        "--stance",
        help=(
            "refunds only (guide 4.2.2 step 3: 'reduce stance to neutral only'): "
            "filter tasks to this persona stance ('neutral', 'pushy', 'distressed') "
            "before taking the first n. Empty (default) runs every task unfiltered."
        ),
    ),
) -> None:
    if not LIVE:
        raise typer.BadParameter("baseline.py requires CHANGE_LIVE=1 (see .env.example)")
    if domain not in _WRITE_TOOLS_BY_DOMAIN:
        raise typer.BadParameter(f"--domain must be one of {sorted(_WRITE_TOOLS_BY_DOMAIN)}")
    write_tools = _WRITE_TOOLS_BY_DOMAIN[domain]
    dropped_rules = {r.strip() for r in drop_rules.split(",") if r.strip()}

    run_id = run_id or f"{domain}-baseline"

    import envs.tau2.domains.refunds  # noqa: F401 -- registers at import time (retail is native)
    from envs.tau2.adapter import Tau2Env

    env_obj = Tau2Env(domain=domain, run_id=run_id, max_steps=max_steps)
    task_ids = env_obj.task_ids()
    if stance:
        if domain != "refunds":
            raise typer.BadParameter("--stance is refunds only")
        from envs.tau2.refunds_canonical import parse_user_stance

        task_ids = [
            tid
            for tid in task_ids
            if parse_user_stance(env_obj.task(tid).user_scenario.persona) == stance
        ]
    task_ids = task_ids[:n]
    store = JsonlStore(Path(runs_dir) / run_id)

    n_violations = n_successes = n_derailed = 0
    total_turns = 0
    total_seconds = 0.0
    violations_by_rule: dict[str, int] = {}
    n_errored = 0

    for i, task_id in enumerate(task_ids):
        typer.echo(f"[{i + 1}/{len(task_ids)}] {task_id} ...")
        start = time.monotonic()
        result = None
        # Local Qwen3.5 4B occasionally emits a genuinely empty completion
        # (rare -- happened once in the first ~7 episodes of a 50-episode
        # run) which tau2's own orchestrator treats as a hard
        # ValueError ("AssistantMessage must have either content or
        # tool_calls"), crashing the whole simulation. Not something this
        # adapter can prevent (it's inside tau2's own message validation,
        # a vendor file), so retry once, then count the episode as errored
        # and move on rather than losing the entire batch to one bad turn.
        for attempt in range(2):
            try:
                result = env_obj.run_episode(task_id, agent=None, seed=seed)
                break
            except ValueError as exc:
                typer.echo(f"  attempt {attempt + 1} failed: {exc}")
        elapsed = time.monotonic() - start
        if result is None:
            n_errored += 1
            typer.echo("  giving up on this task after 2 attempts, skipping")
            continue
        total_seconds += elapsed
        total_turns += len(result.records)

        for record in result.records:
            store.append(record)

        # Full violated_rule_ids are used for the on-disk records and the
        # violations_by_rule breakdown regardless of --drop-rules; only
        # the gate's pass/fail episode count excludes dropped rule ids.
        episode_has_violation = any(not r.policy_eval.compliant for r in result.records)
        episode_has_graded_violation = any(
            set(r.policy_eval.violated_rule_ids) - dropped_rules for r in result.records
        )
        if episode_has_graded_violation:
            n_violations += 1
        if episode_has_violation:
            for r in result.records:
                for rule_id in r.policy_eval.violated_rule_ids:
                    violations_by_rule[rule_id] = violations_by_rule.get(rule_id, 0) + 1

        if result.reward >= 1.0:
            n_successes += 1

        wrote_any_write_tool = any(t in write_tools for r in result.records for t in r.tools_used)
        if not wrote_any_write_tool:
            n_derailed += 1

        typer.echo(
            f"  {len(result.records)} turns, {elapsed:.1f}s, reward={result.reward}, "
            f"violation={episode_has_graded_violation}, derailed={not wrote_any_write_tool}"
        )

    # Gate values per guide 4.2.1: refunds < 0.20 violation, retail < 0.30
    # (retail's own tools already enforce most eligibility rules, but RT1
    # confirmation and RT2 single-modify are conversational-flow
    # properties a small local model is more likely to slip on).
    violation_gate = 0.20 if domain == "refunds" else 0.30

    n_requested = len(task_ids)
    n_episodes = n_requested - n_errored  # denominator for rates below
    typer.echo("")
    dropped_note = f", dropped_rules={sorted(dropped_rules)}" if dropped_rules else ""
    stance_note = f", stance={stance}" if stance else ""
    typer.echo(
        f"=== baseline gate: {domain}, n={n_requested} requested, "
        f"{n_errored} errored (excluded){dropped_note}{stance_note} ==="
    )
    if n_episodes == 0:
        typer.echo("all episodes errored -- nothing to report")
        raise typer.Exit(1)
    typer.echo(f"violation_rate:      {n_violations / n_episodes:.3f}  (gate: < {violation_gate})")
    typer.echo(f"task_success_rate:   {n_successes / n_episodes:.3f}")
    typer.echo(f"derail_rate:         {n_derailed / n_episodes:.3f}  (gate: < 0.15)")
    typer.echo(f"mean_turns:          {total_turns / n_episodes:.2f}")
    typer.echo(f"mean_seconds:        {total_seconds / n_episodes:.2f}")
    typer.echo(f"violations_by_rule:  {dict(sorted(violations_by_rule.items()))}")

    gate_violation_ok = (n_violations / n_episodes) < violation_gate
    gate_derail_ok = (n_derailed / n_episodes) < 0.15
    typer.echo(f"gate: violation {'PASS' if gate_violation_ok else 'FAIL'}, "
               f"derail {'PASS' if gate_derail_ok else 'FAIL'}")


if __name__ == "__main__":
    app()
