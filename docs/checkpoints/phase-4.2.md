# Phase 4.2 checkpoint (session-2 guide, no-memory baseline gate) — RESOLVED

`scripts/baseline.py --domain refunds --n 50` and `--domain retail --n 50`, empty
memory, no gates, `max_steps=20`, against Ollama/qwen3.5:4b. Both gates originally
failed, for two different, clearly diagnosed reasons — this was the guide's own
explicit STOP point 3 ("owner confirms the gate").

**Resolution** (owner-authorized remediation run to completion for both domains):
retail's `max_steps` swept 20→40→80 (accepted 80, diminishing returns beyond);
refunds ran the guide's full three-step 4.2.2 ladder, then had a real grading gap
fixed (R1/R10 were never actually checked) and was re-baselined clean. **Both
domains' violation gates now pass; both still fail on derail rate specifically**,
for two different, orthogonal, diagnosed behavioral reasons (not grading bugs) —
see "Final status" below. Owner's call: proceed to phase 4c anyway, since it only
needs a measurable drift signal, not a passing derail rate.

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

## Remediation results (owner-authorized, run to completion)

### Retail: `max_steps` sweep

| max_steps | n  | violation_rate | gate (< 0.30) | task_success | derail_rate | gate (< 0.15) | mean_turns | mean_s/ep |
|---|---:|---:|---|---:|---:|---|---:|---:|
| 20 (original) | 50 | 0.000 | pass (trivial) | 0.000 | 0.920 | **FAIL** | 9.98  | 40.0 |
| 40            | 50 | 0.020 | pass           | 0.120 | 0.600 | **FAIL** | 14.84 | 36.5 |
| 80            | 50 | 0.020 | pass           | 0.120 | 0.500 | **FAIL** | 18.58 | 45.9 |

Clear diminishing returns: derail drops 32 points (92→60) on the first doubling,
then only 10 more points (60→50) on the second, while wall time per episode grows.
At `max_steps=80`, turns still show some clustering near the new ceiling but also
a substantial tail of much shorter derailed episodes — confirms budget exhaustion
is a real contributor but not the whole story, and further doubling has a
worsening cost/benefit ratio. **Owner's call: stop at `max_steps=80`, accept 50%
derail as a documented finding rather than chase this further.**

### Refunds: the guide's 4.2.2 ladder, run cumulatively (each step keeps the prior ones)

| variant | n  | violation_rate | gate (< 0.20) | task_success | derail_rate | gate (< 0.15) | violations_by_rule |
|---|---:|---:|---|---:|---:|---|---|
| original                              | 50 | 0.200 | FAIL | 0.120 | 0.600 | FAIL | R3:2, R4:3, R5:1, R6:3, R7:1 |
| step 1: shortened policy.md           | 50 | 0.260 | FAIL (worse) | 0.220 | 0.500 | FAIL | R3:4, R4:3, R5:5, R7:1 |
| step 2: + drop R8/R10 from grading    | 50 | 0.260 | FAIL (no change) | 0.220 | 0.500 | FAIL | R3:4, R4:3, R5:5, R7:1 |
| step 3: + neutral stance only         | 42\* | 0.262 | FAIL | 0.238 | 0.381 | FAIL (improved) | R3:6, R4:2, R5:1, R7:2, R8:2 |

\* only 42 of 120 refunds tasks have `[STANCE=neutral]`; `--stance neutral` took
all of them rather than padding to 50.

Step 1 made violation_rate measurably *worse* (shorter prose apparently removed
context the model was using correctly, e.g. R5 violations went 1→5) — a real,
counterintuitive finding worth keeping, not just a null result. Step 2 had
**zero effect**, consistent with the earlier finding that R8/R10 weren't
contributing measurable violations in this sample to begin with (R10, it turns
out, isn't graded at all currently — see below). Step 3 (neutral stance) did
meaningfully cut derail (50%→38%) — pushy/distressed personas apparently
correlate with more derailed conversations — but nowhere near the 15% gate, and
violation_rate stayed flat throughout the whole ladder regardless of which lever
was pulled.

**Per the guide's own instruction ("stop after the third if still failing") — the
remediation ladder is now exhausted. Owner's call: accept both domains' baseline
numbers as documented findings and proceed to phase 4c anyway**, since 4c's D2
gate only needs the drift signal (later window minus earlier window) to be
measurable, not a passing absolute baseline.

### New finding surfaced during remediation: R1/R10 aren't actually graded

`envs/tau2/domains/refunds/oracle.py`'s own docstring claims "R1/R10 are checked
in envs/tau2/refunds_canonical.py" — they are not. Neither R1 (identity +
explicit confirmation) nor R10 (one write action per order per conversation) has
any implementation anywhere in the refunds grading pipeline (confirmed by
grepping for "confirm"/"affirmative"/"R1"/"R10" across
`envs/tau2/refunds_canonical.py` and `envs/tau2/adapter.py` — nothing). This means
**every refunds violation_rate reported this session, including phase 4a's
original 5-episode smoke and this checkpoint's numbers, has always undercounted**
— any R1/R10 violations that occurred were silently never flagged. Not fixed as
part of this remediation (fixing it would only make violation_rate *worse*,
confounding interpretation of the ladder's three isolated steps, and guide 4.2.2
didn't authorize adding a new grading dimension mid-ladder) — flagging for a
separate decision: implement R1/R10 grading (retail already has the equivalent
RT1/RT2) and re-baseline, or accept the gap as a documented scope limit.

## R1/R10 fix + corrected re-baseline (owner-authorized)

`envs/tau2/refunds_canonical.py::check_r1_identity_and_confirmation`/
`check_r10_single_write` implemented (same pattern as retail's RT1/RT2), wired
into `_canonicalize_refunds`'s write-action branch. `policy.md` also reverted to
its original (unshortened) prose -- the ladder's step 1 had made things worse, no
reason to keep it. Re-ran the refunds baseline clean against this corrected
pipeline:

| variant | n | violation_rate | gate (< 0.20) | derail_rate | gate (< 0.15) | violations_by_rule |
|---|---:|---:|---|---:|---|---|
| original (R1/R10 never graded) | 50 | 0.200 | FAIL | 0.600 | FAIL | R3:2, R4:3, R5:1, R6:3, R7:1 |
| **corrected (R1/R10 graded, original policy)** | 50 | **0.140** | **PASS** | 0.580 | FAIL | R1:2, R3:1, R4:1, R5:2, R6:2, R7:1 |

**The corrected violation gate actually passes** (0.140 < 0.20) -- R1 catches 2
real violations that were previously invisible, R10 catches zero (0 second-write
attempts in this sample). Note this is a fresh 50-episode sample, not a replay of
the exact same episodes (tau2's own documented provider-side nondeterminism, docs/
tau2_interfaces.md item 12, means even seed=0 + temperature=0 reruns aren't
bit-identical), so the drop from 0.200 to 0.140 isn't purely attributable to the
grading fix -- but R1's 2 genuine violations are real regardless.

**Derail (0.580) is still the one gate that doesn't pass for refunds** -- consistent
with the diagnosis above (text-only denial instead of `deny_request`), which the
R1/R10 fix doesn't touch since it's an orthogonal issue (whether a write happens
at all, not whether a write that did happen was compliant).

## Final status, both domains

- **Retail**: violation gate passes (accepted at `max_steps=80`); derail gate
  fails (50%, down from 92% at the default 20, diminishing returns beyond this).
- **Refunds**: violation gate passes with corrected R1/R10 grading (14%); derail
  gate fails (58%, essentially unchanged across every remediation attempt).

**Both domains now fail on exactly one axis each: derail rate**, for two
different, orthogonal, diagnosed behavioral reasons (retail: budget-limited task
complexity; refunds: text-only denial instead of tool use). Neither is a grading
bug -- both are genuine properties of how a small local model handles these
domains, worth reporting as PoC-level findings rather than continuing to chase.

## Open questions for owner

1. ~~Raise `max_steps` for retail?~~ **Answered**: swept 20/40/80, accepted 80.
2. ~~Run the guide's 4.2.2 remediation steps for refunds?~~ **Answered**: ladder
   exhausted, still failing on derail specifically.
3. ~~Implement R1/R10 grading?~~ **Answered and done**: both domains' violation
   gates now pass; derail is the sole remaining failure for each, for different
   reasons neither gate's guide-specified remediation addresses.
4. Does phase 4c's 300-episode D2 gate proceed now?

## Next

Per owner authorization: proceeding to phase 4c's D2 gate.
