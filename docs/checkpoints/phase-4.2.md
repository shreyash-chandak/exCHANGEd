# Phase 4.2 checkpoint (session-2 guide, no-memory baseline gate) — STOP

`scripts/baseline.py --domain refunds --n 50` and `--domain retail --n 50`, empty
memory, no gates, `max_steps=20`, against Ollama/qwen3.5:4b. Both gates fail, for
two different, clearly diagnosed reasons. **This is the guide's own explicit STOP
point 3 ("owner confirms the gate") — reporting honestly rather than proceeding.**

## Results

| domain  | n  | violation_rate | gate (< 0.20/0.30) | task_success | derail_rate | gate (< 0.15) | mean_turns | mean_s/ep |
|---|---:|---:|---|---:|---:|---|---:|---:|
| refunds | 50 | 0.200 | **FAIL** | 0.120 | 0.600 | **FAIL** | 7.46 | 32.4 |
| retail  | 50 | 0.000 | pass (trivially) | 0.000 | 0.920 | **FAIL** | 9.98 | 40.0 |

Refunds violations by rule: `{'R3': 2, 'R4': 3, 'R5': 1, 'R6': 3, 'R7': 1}` (spread
across five different rules, not one dominant failure mode). Retail: none
(nothing to violate — see below).

## Diagnosis (not guessed at — read from the actual records and raw transcripts)

**Retail's "0.000 violation_rate" is not a good result — it's a symptom of the
derail rate.** 46 of 50 episodes never called a write tool at all, so there was
almost nothing for the compliance checks to grade. Turn counts cluster hard at
exactly 11 assistant turns for 36 of those 46 (`[4,5,5,7,7,7,8,8,8,8,9,9,9,10,10,
11×26,...]`) — consistent with `max_steps=20` (an orchestrator-step budget, not an
assistant-turn budget — roughly 2 orchestrator steps per assistant turn once tool
calls are counted) being hit mid-conversation on tasks that inherently need many
lookups (identity auth, order details, 1-2 product-variant lookups per item)
before a write is even possible. This reads as **budget exhaustion**, not a
capability failure the guide's derail remediation (4.2.3, "switch the user
simulator") addresses — the user simulator isn't the bottleneck here.

**Refunds' derail is a different mechanism: the model resolves in text instead of
calling `deny_request`.** Read the raw transcript for one derailed episode
(`refunds_000`, task refund request outside the 60-day window, no damage
reported): the agent correctly looks up identity and order, correctly reasons
through the policy ("Since this was delivered more than 60 days ago... according
to policy R4... an order is not eligible for any refund"), and is about to
explain the denial in plain text — never calling the `deny_request(order_id,
reason)` tool that exists specifically so a denial is a recorded, gradable
action. Turn counts for refunds' derailed episodes are much lower and more varied
(`[2,2,4,4,4,4,5,5,5,...11,11]`, mean 6.7) than retail's, and don't cluster at a
step ceiling — this is a genuine behavioral pattern (small local model treats
"explaining why I can't help" as conversation, not tool use), not exhaustion.
28 of 30 refunds-derailed episodes end this way (`end` as the last action); the
other 2 end mid-`lookup`.

Both are real findings, not measurement bugs. Neither is fixed by guide 4.2.3's
specific remediation (switching the user simulator) since we're already on the
guide's own documented Ollama fallback and neither cause is a user-simulator
problem.

## What guide 4.2.2/4.2.3 authorize vs. what's actually needed

- 4.2.2 (violation-gate remediation: shorten policy.md prose, drop R8/R10 from
  grading, reduce stance to neutral-only) targets *why the agent violates policy
  when it does act* — refunds' violations are spread across 5 different rules
  with no dominant cause, so it's unclear any of these three steps would move the
  number much, and none of them touch the derail rate at all (the larger
  problem, 0.600 vs. the 0.200 violation number).
- 4.2.3 (derail-gate remediation: switch the user simulator) doesn't match
  either diagnosed cause above.
- The one concrete, undiagnosed-by-the-guide lever that plausibly addresses
  **retail's** derail specifically is raising `max_steps` past 20 — not
  something section 2.4 protects (it's a per-call parameter, not a listed
  constant) and not one of the guide's own remediation steps, so not applied
  without asking first.
- **Refunds'** derail (text-only denial) isn't a budget problem, so more steps
  wouldn't fix it — it needs either a prompt-level nudge to always use
  `deny_request` for denials, or accepting this as a real property of a small
  local model's behavior for the paper to report as a limitation.

## Open questions for owner

1. Raise `max_steps` for retail (e.g. 30-40) and re-run the baseline, given the
   clustering-at-11-turns evidence points at budget exhaustion specifically?
2. For refunds: run the guide's three 4.2.2 remediation steps one at a time
   despite the violation number being the *smaller* problem here (0.200 vs.
   0.600 derail), or treat the text-only-denial pattern as a documented model
   limitation and proceed?
3. Given neither gate cleanly passes for either domain, does phase 4c (D2 gate,
   also refunds-only per the guide) proceed anyway to see whether the drift
   signal is still measurable against this baseline, or does resolving this
   stop take priority?

## Next

Per session-2 guide section 9: **STOP.** Waiting on the above before phase 4c
(or before re-running phase 4.2 with any adjustment).
