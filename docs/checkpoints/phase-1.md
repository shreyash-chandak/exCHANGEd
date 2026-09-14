# Phase 1 checkpoint

## Done
- 1.1 Added `vendor/tau2-bench` as a git submodule, pinned to tag `v1.0.1` (commit `fc0055d`), installed editable via `uv add --editable ./vendor/tau2-bench` — succeeded on the first attempt, no fallback needed — `03f5161`
- 1.2 Read, in order: `README.md`, `docs/getting-started.md`, `docs/evaluation.md`, `src/tau2/agent/README.md`, `src/tau2/domains/README.md`, `src/tau2/gym/README.md`, `docs/cli-reference.md`, plus source for `run.py`, `runner/batch.py`, `runner/helpers.py`, `data_model/tasks.py`, `data_model/simulation.py`, `user/user_simulator.py`, `config.py`, `domains/retail/{data_model,tools,environment}.py`, `policy.md`, and inspected `tasks.json`/`db.json`/`split_tasks.json` directly
- 1.3 Wrote `docs/tau2_interfaces.md` answering all 12 discovery items — `4ea8f6b`
- 1.4 `tests/test_tau2_import.py` (offline, not `live`): loads the retail domain, asserts task count == 114, asserts policy string nonempty. Also scoped `testpaths = ["tests"]` in `pyproject.toml` — without it, pytest collected `vendor/tau2-bench`'s own test suite and errored on missing extras (voice/gym/knowledge) — `1d2eb24`

## Smoke test output
```
$ make test
..                                                                       [100%]
2 passed, 1 warning in 5.45s

$ uv run python -c "import tau2; print(tau2.__file__)"
...
C:\Users\shrey\Desktop\CHANGE\vendor\tau2-bench\src\tau2\__init__.py
```

## Deviations from the guide
Three findings materially affect the `CanonicalState`/`CanonicalAction` data contracts in `CHANGE_poc_agent_guide.md` section 2, all written up in full in `docs/tau2_interfaces.md`'s final section ("Deviations that affect the data contracts"). Summary:

1. **No `refund_full`/`refund_partial` tools exist in retail.** The refund-generosity drift story (D2) was written around an Alice abstraction that doesn't match tau2 retail's actual toolkit (`cancel_pending_order`, `return_delivered_order_items`, `exchange_delivered_order_items` — none of which is a two-way full/partial refund switch). Proposed fix in the doc: collapse `CanonicalAction` to match retail's real write tools.
2. **`within_policy_window` cannot be computed — retail has no order dates anywhere** (confirmed by reading the full `RetailDB`/`Order` pydantic schema and a sample order; confirmed by reading `policy.md` in full — eligibility is gated purely by `order_status`, never by time). This breaks D3 ("policy update... exchange window shortened") as literally specified. Proposed fix: retarget D3 to a status-gating policy change instead of a date-window change, and rename the field to something like `status_eligible`.
3. **`user_stance` has no source signal** — all 114 retail tasks have `persona=None` and no structured stance tag. Proposed fix: keep it as a constant `"neutral"` per guide 4.1's documented fallback, but note in the paper that this dimension carries zero information for retail as shipped (not worth an LLM-based stance classifier, which the guide forbids anyway).

Also flagged, smaller: `OrderStatus` has 7 values vs. `CanonicalState.order_status`'s 5 (proposed collapse given in the doc); and custom-agent registration for phase 4's `LessonAgent` needs one decision (register a factory via `registry.register_agent_factory` from our own module at import time — recommended, doesn't touch vendored files — vs. bypassing `build_orchestrator` and constructing `Orchestrator` directly).

## Open questions for owner
1. Accept the proposed `CanonicalAction`/`CanonicalState` adjustments in `docs/tau2_interfaces.md` (collapse refund actions to retail's real tools, rename/redefine `within_policy_window` as a status gate, keep `user_stance` constant), or pick a different tau2 domain (airline/telecom — not investigated), or proceed with retail as originally specified some other way?
2. If retargeting D3 to a status-gating change: what specific policy edit should the paper use (e.g. "processed-but-not-delivered orders can no longer be cancelled" vs. some other status-gate tightening)?
3. OK with registering the custom `LessonAgent` factory into `tau2.registry.registry` at import time from our own module (no vendor file edits), for phase 4?

## Next
Per the guide, phases 2 and 3 (data contracts, store, mock environment) do not depend on tau2 and may proceed while these are pending. Phase 4 (tau2 adapter, live instrumentation) is blocked on the three answers above.
