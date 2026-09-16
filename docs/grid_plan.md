# Live grid sizing (session-2 guide 4d.1)

**No live grid is run for this document — sizing only, per the guide's explicit
instruction.** All numbers below are computed from measured throughput and the
guide's own reduced-grid definition (section 4d.1).

## Measured throughput (this session, sequential — no concurrency wired into
## episode-level execution yet, see "Concurrency" below)

| path | domain | condition | n | mean s/episode | source |
|---|---|---|---:|---:|---|
| `scripts/baseline.py` (no memory) | refunds | -- | 50 | 32.4 | phase-4.2, original baseline |
| `scripts/baseline.py` (no memory) | refunds | -- | 50 | 14.9-17.8 | phase-4.2, remediation variants |
| `scripts/baseline.py` (no memory, `max_steps=80`) | retail | -- | 50 | 45.9 | phase-4.2, accepted retail setting |
| `scripts/run_episodes.py --env tau2` (LessonAgent + LiveLessonExtractor + satisfaction question) | refunds | d2 | 56 (partial, killed by system memory pressure before completing 300) | 19.8 | phase 4c D2 gate, first segment (19:20:24-19:38:51) |

The live grid's actual per-episode cost is closest to the last row (the full
memory-injecting loop, not the no-memory baseline) since that is what
`GovernanceLoop`/`Sandbox`/`evolve.canary` all drive via `Tau2AgentHandle` +
`tau2_agent_factory` (session-2 guide 4d wiring, this session). Used below:
**refunds ~20 s/episode, retail ~46 s/episode** (retail's own D2-gate-loop
throughput hasn't been measured live yet — using the accepted `max_steps=80`
no-memory figure as the closest available proxy, likely an underestimate since
retail's live grid would also carry the LessonAgent/satisfaction-question
overhead refunds' 19.8s figure already includes).

### Concurrency

`change/runner.py::run_concurrent_episodes` (phase 4.1.6) exists and is
unit-tested, but is **not wired into `GovernanceLoop`/`Sandbox`/`evolve`** --
every live episode in this session's testing, including the tau2 governance-loop
wiring built for phase 4d, ran strictly sequentially. The serving benchmark's
3.61x aggregate speedup at 6 parallel slots (phase 4.1) is therefore *not*
reflected in the numbers above or below. Wiring concurrency into the grid runner
is out of scope for this sizing pass -- flagged as the single highest-leverage
follow-up if the total below needs to come down further than the cuts here
already bring it.

## Guide's reduced grid definition (4d.1)

- **refunds**: A0,A1,A2,A3,A4,FULL on d2 and d3, seeds 0 and 1, 800 episodes
  each. A0, A2, FULL on d1, seeds 0 and 1.
- **retail**: A0, A2, FULL on d2 and d3, seeds 0 and 1, 600 episodes each. A0
  on d1.
- Sandbox per plan 7.4 reductions: 3 candidates, 25 tasks, 1 trial, at most 5
  governance cycles per run get the full Sandbox/Negotiate treatment. These are
  already `change/config.py`'s live defaults (`MAX_CANDIDATES=3`,
  `SANDBOX_TASKS_PER_CANDIDATE=25`, `SANDBOX_TRIALS=1`) -- no further reduction
  needed to match the guide's own numbers.

## Episode count

### Base episodes (every cell, before Sandbox/canary overhead)

| domain | cells | episodes/cell | base episodes |
|---|---:|---:|---:|
| refunds d2+d3 (6 systems x 2 conditions x 2 seeds) | 24 | 800 | 19,200 |
| refunds d1 (3 systems x 1 condition x 2 seeds) | 6 | 800 | 4,800 |
| retail d2+d3 (3 systems x 2 conditions x 2 seeds) | 12 | 600 | 7,200 |
| retail d1 (1 system x 1 condition x 2 seeds) | 2 | 600 | 1,200 |
| **base total** | | | **32,400** |

### Sandbox/canary overhead (A3/A4/FULL cells only, upper bound)

Per the guide's own reduced-plan arithmetic (7.4: "3 candidates, 25 tasks, 1
trial... cycles to 5. That is 375 per run"), each A3/A4/FULL cell adds up to
`3 x 25 x 1 x 5 = 375` sandbox episodes. FULL cells additionally run a canary
pass (~12 tasks, guide's `CANARY_FRACTION_OF_HELDOUT x SANDBOX_HELDOUT_FRACTION`
split -- measured directly off a dry `TaskSplit` construction this session:
refunds' 120 tasks split 95 train / 13 canary / 12 sandbox) per applied
candidate, bounded the same way at 5: `12 x 5 = 60`. Successor distillation
(FULL only, rare trigger condition) is not bounded here -- flagged as an
unquantified additional cost if it fires.

| domain | A3/A4/FULL cells | sandbox overhead | FULL-only canary overhead | subtotal |
|---|---:|---:|---:|---:|
| refunds (A3:4, A4:4, FULL:6) | 14 | 14 x 375 = 5,250 | 6 x 60 = 360 | 5,610 |
| retail (FULL:4) | 4 | 4 x 375 = 1,500 | 4 x 60 = 240 | 1,740 |
| **overhead total** | | | | **7,350** |

### Grand total

**~39,750 episodes** (32,400 base + 7,350 overhead), upper-bound (assumes every
A3/A4/FULL cell hits the full 5-cycle sandbox budget and applies a candidate
every triggered cycle -- actual live trigger rates for tau2 are unmeasured, this
session's mock-grid findings showed A1/A2 triggering far less than a worst-case
assumption, so the real number is plausibly lower).

## Wall time at measured throughput

| domain | episodes | s/episode | hours |
|---|---:|---:|---:|
| refunds (29,610 = 24,000 base + 5,610 overhead) | 29,610 | 20 | 164.5 |
| retail (10,140 = 8,400 base + 1,740 overhead) | 10,140 | 46 | 129.5 |
| **total** | **39,750** | | **~294** |

## Cut list (294h exceeds the guide's 120h threshold by ~2.45x)

None of these are applied here -- sizing only. In order of least to most
scientifically costly, per this session's own judgment (not guide-specified,
since the guide only says "report... the cut list if hours exceed 120"):

1. **Seeds 2 -> 1** (halves everything): ~147h. Still over.
2. **Also halve episodes/cell** (refunds 800->400, retail 600->300): ~74h.
   Under 120h. Matches approach1.md's own 7.4 fallback reasoning ("cut
   candidates/trials/tasks/cycles" already applied; episode count is the next
   lever) -- loses some statistical power on the later-window drift measurement
   but the D2/D3 sanity gates (phase 4c) already showed drift signal well
   before 400 episodes in the mock grid.
3. **Drop D1 entirely** (it's the no-drift control, cheapest per-cell but least
   informative for the headline claim): D1 base episodes = 4,800 (refunds) +
   1,200 (retail) = 6,000 of 32,400 base (~18.5%), plus refunds d1's 2 FULL
   cells' ~750 sandbox/canary overhead -- dropping D1 saves ~6,750 episodes
   total (~17% of the grand total), not the dominant cost on its own. Combine
   with #1+#2 if still needed after those.
4. **Minimum viable** (approach1.md section 7.2's own fallback): A0, A1, A2,
   FULL on D2 and D3 only, single agent (refunds only, skip retail's live grid
   entirely) -- this alone removes retail's ~130h, leaving only refunds' ~165h
   (still needs #1+#2 combined to clear 120h: ~1 seed x 400 episodes/cell would
   put refunds alone around ~41h).

**Recommended combination if the full grid doesn't fit in the available
session**: #1 + #2 (seeds=1, episodes/cell halved) brings the total to ~74h,
comfortably under 120h, without dropping any system/condition/domain the guide
asks for. Owner's call at grid-run time, informed by how the actual throughput
compares to these estimates once concurrency (if wired) or real measured D2/D3
retail-domain live-loop timing is available.

## Open items this sizing surfaces

- Retail's live-grid-loop throughput (LessonAgent + satisfaction question, not
  just the no-memory baseline) is unmeasured -- the 46s/episode figure is a
  proxy from the no-memory baseline at the accepted `max_steps=80`, likely an
  underestimate.
- Sandbox/canary overhead is an upper bound assuming worst-case trigger
  frequency; this session's mock-grid findings (docs/checkpoints/phase-8b.md)
  showed real trigger rates vary widely by system (A1 never triggers, A2
  over-triggers but is behaviorally inert) -- the live tau2 grid's actual
  overhead could be meaningfully lower once the first few cells are observed.
- Concurrency (`change/runner.py`) is unwired -- the single highest-leverage
  lever to reduce wall time further without cutting scientific scope, not
  attempted in this sizing pass.
