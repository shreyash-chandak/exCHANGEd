# CHANGE extension for CAIN 2027: implementation plan

Deadline Fri 30 Oct 2026 (AoE). Full paper 10+2 pages IEEE, double anonymous, design contributions must be evaluated. Agentic software is an explicit focus topic this year. Plan written 14 Sep, so 6.5 weeks.

## 0. What changed from approach1 and why

approach1 is already most of a paper. These are the things I fixed or tightened. Read this section even if you skip the rest.

1. The forecast in approach1 is internally inconsistent. Section 7 says "if the agent continues behaving according to the current behavioral model" and section 11 then forecasts violation rising 4% to 19%. A stationary P(A|S) cannot produce a rising violation rate. Anticipate needs an explicit nonstationary drift model over the snapshot sequence. This is now the core technical contribution, see 5.3.
2. Negotiate in approach1 is candidate selection under constraints. In the CHANGE paper Negotiate is about adaptation boundaries and autonomy requests reviewed by a supervisor. I kept the constrained selection but made it the evidence step inside a boundary controller, so it is faithful to the paper. See 5.7.
3. approach1 puts G and E out of scope. G partially in: the lesson proposer that makes the agent self evolve IS Generate, and it is what causes the drift we govern. Tool generation stays out. E partially in: version application, canary alignment check, rollback, and successor distillation as curated memory transfer. See 5.5 and 5.8.
4. None of the seven repos are datasets. They are environments. Drift has to be induced. The cleanest and most defensible drift source is experience driven self evolution (ReasoningBank / AWM style lesson memory), which recent work shows degrades safety on its own. So the system under governance is a self evolving agent, and CHANGE governs the evolution. See section 3.
5. tau2-bench is the primary testbed. It has the three things we need: a written policy, gradable action level correctness, and a user simulator. Retail plus airline give Alice and Bob domains without inventing a testbed from scratch. llm_coordination (Overcooked) is the optional secondary testbed for Harmonize only.
6. Petri net is justified only where there is concurrency and shared resources (Alice and Bob contending for the human review queue, latency and cost). For a single agent path it collapses to a Markov chain. The paper should say this plainly instead of claiming Petri nets are necessary.
7. approach1 cites the paper title as "CHANGE: A Framework for Continuous Governance of Evolving Agentic Systems". The real title is "Architecting AgentOps Needs CHANGE". Also double anonymous, so the extension has to refer to it in third person.

## 1. Scope and the one claim

Claim: an evolving agent can be represented by empirical behavioural distributions conditioned on canonical state, those distributions can be modelled as a nonstationary behavioural twin, and the twin can (a) forecast when the agent will leave its behavioural envelope before it does and (b) rank candidate adaptations before they are deployed, with the whole thing wrapped in a CHANGE governance loop.

What is in scope for the prototype

- Contextualize: full
- Anticipate: full, this is the main contribution
- Negotiate: full, as a boundary controller with a scripted supervisor
- Harmonize: lightweight, shared ontology plus conflict detection plus shared lesson store, evaluated on a two agent tau2 wrapper
- Generate: lesson proposer only (context layer changes). No tool synthesis
- Evolve: version application, canary alignment eval, rollback, successor distillation of lessons. No weight distillation

What is explicitly out

- Tool or code generation by agents
- Model weight updates of any kind
- Real humans in the loop (supervisor is a scripted oracle, stated as a limitation)
- Architecture layer adaptations beyond toggling a human approval gate

## 2. Testbed decision

| Repo | Verdict | Why |
|---|---|---|
| tau2-bench (sierra) | Primary | Policy doc per domain, tools, tasks with expected actions and reward, user simulator, gym interface, LiteLLM so any model works. Domains retail, airline, telecom, banking_knowledge. Python 3.12+ and uv. Pin a version and record it, v1.0.1 changed grading |
| llm_coordination (UCSB) | Secondary, Harmonize only, optional | Overcooked and Hanabi two agent pure coordination. Clean setting for two agents with divergent lesson memories. Python 3.9 and needs vLLM, environment setup cost is real. Only do this if week 4 is on schedule |
| BattleAgentBench (THUDM) | Skip | Game server plus pygame, competition framing, far from the AgentOps narrative. Nothing it gives that Overcooked does not |
| agentic-fleet (Qredence) | Reference only | Production style runtime with OTel, Langfuse, DSPy self optimisation. Do not run it. Use its tracing schema and its "self optimising" claim as the motivating example of an AgentOps platform with no C/A/N capabilities in the gap analysis section |
| autogen-ui | Skip | Hello world UI, nothing to evaluate |
| ai-doc-gen (divar) | Skip | No policy, no ground truth, no drift. Five parallel analysers is not the kind of multi agent we need |
| Controllable-RAG-Agent | Skip | Deterministic single graph, no evolution. Could matter for HarmonE-RAG later, not here |

Reason tau2 beats a custom Alice and Bob testbed: reviewers can reproduce, the policy compliance signal is not something we invented, and the retail domain literally is refunds and exchanges. We lose nothing from the running example.

## 3. System under governance: self evolving Alice and Bob on tau2

### 3.1 Agents

- Alice = tau2 retail agent. Refunds, exchanges, cancellations, order lookup. The running example maps directly
- Bob = second role inside the same tau2 episode. Two options, pick one in week 1
  - Option A (preferred, cheaper): split retail tools into two roles behind one tau2 Agent class. Alice owns customer facing decisions (cancel, return, exchange, refund). Bob owns fulfilment state changes (modify pending order, address and shipping changes). A small router decides who handles each turn. tau2 sees one agent, so grading is untouched
  - Option B: Bob = airline agent, separate episodes, and Harmonize compares them on the shared ontology only (no real interaction). Weaker story, only if A fails

### 3.2 The evolution mechanism (this is Generate)

After each episode, a lesson extractor (ReasoningBank style) reads the trajectory plus reward and writes 0 to 2 lessons into the agent's experience memory. At inference the top k lessons by similarity to the current case are injected into the prompt. Memory grows, behaviour drifts. That drift is natural, documented in the literature, and not something we engineered to look bad.

Config knobs

- lesson_extractor_model, k retrieved lessons, memory cap
- feedback_source: ground truth reward, user satisfaction proxy from the simulator, or biased (see 7.1)

### 3.3 Drift induction conditions

We need drift that (i) actually happens and (ii) is measurable against policy. Four conditions, run separately

- D1 natural: lessons extracted from true reward. Expected mild drift, possibly beneficial. This is the control
- D2 biased feedback: lesson extractor is rewarded on a user satisfaction proxy instead of policy compliance. Expected: generosity drift, more refunds outside policy. This is the Alice story
- D3 policy update: at interaction t0 the retail policy doc changes (e.g. exchange window shortened). Old lessons become violations. Tests whether Anticipate sees the envelope crossing coming
- D4 model swap: agent LLM swapped mid stream. Tests robustness of the twin to a distribution shift that is not memory driven. Optional, drop first if short on time

Sanity gate for week 1: run D2 for 300 to 500 episodes with no governance and confirm policy violation rate rises measurably. If it does not, nothing else matters. Fix by raising k, lowering memory cap, or strengthening the satisfaction proxy before touching any CHANGE component.

## 4. Architecture

```
tau2 episodes (Alice, Bob, user sim, policy grader)
        |
  Instrumentation -> ExperienceRecord stream
        |
  CONTEXTUALIZE  -> versioned BehavioralSnapshot (per agent, per window)
        |
  ANTICIPATE     -> nonstationary twin -> forecast, time to envelope exit
        |                 \-> counterfactual ranking of candidates
  GENERATE       -> candidate lessons (and gate toggles) from experience
        |
  SANDBOX        -> replay candidates on held out cases -> candidate snapshots
        |
  HARMONIZE      -> cross agent conflicts on shared states -> constraints
        |
  NEGOTIATE      -> boundary controller: accept / escalate / reject / defer
        |
  EVOLVE         -> apply version, canary eval, rollback, successor distillation
        |
        +--------------------------------> back to episodes
```

Two adaptation timings, kept from approach1 but renamed to match the paper's language: intra deployment (agent self applies within its boundary) and inter deployment (supervisor approves between cycles).

Adaptation layers, kept: model, context, tools, architecture. The prototype only generates context layer candidates plus one architecture candidate (human approval gate above value X). Say this in the paper as a deliberate reduction.

## 5. Component specifications

### 5.1 Instrumentation and canonicalization

ExperienceRecord per agent turn that ends in a decision (not per LLM call)

```
ExperienceRecord
  agent_id, agent_version, memory_version, episode_id, turn_idx, t_global
  state: CanonicalState
  action: CanonicalAction
  tools_used: [str]
  outcome: CanonicalOutcome
  policy_eval: {compliant: bool, violated_rule_ids: [str]}
  reward: float (episode level, backfilled)
  latency_ms, tokens_in, tokens_out, cost_usd
  lessons_in_context: [lesson_id]
```

CanonicalState for retail (start with these, add only if needed)

- task_type: cancel | return | exchange | modify | lookup | other
- order_status: pending | processed | delivered | cancelled
- value_bucket: low | mid | high (thresholds from order value quantiles)
- within_policy_window: bool (derived from policy doc and order dates)
- user_stance: neutral | pushy | distressed (from simulator instruction tags, not inferred from text)
- prior_turns_bucket: 0 | 1to3 | 4plus

CanonicalAction: the tau2 tool call name plus a coarse argument class (e.g. refund_full, refund_partial, exchange, deny, escalate, ask_clarify, end). Escalate is added as an explicit tool so Negotiate has something to observe.

CanonicalOutcome: policy_compliant, task_success (tau2 reward), user_satisfied (simulator signal), cost delta.

Canonicalization must be a deterministic function of structured fields already present in the tau2 task and db state. Do not use an LLM labeller for state. If a field cannot be derived deterministically, drop the field. This is what makes P(A|S) comparable across snapshots and is worth a paragraph in the paper.

### 5.2 Contextualize

Produces BehavioralSnapshot v_n over a window of W episodes (start W = 50) or every m memory writes, whichever first.

- P_n(A | S) with Dirichlet smoothing, alpha = 1, plus sample count per S
- P_n(O | S, A)
- P_n(S' | S, A, O) inside an episode, plus P_n(S_0) initial state distribution
- drift score vs v_{n-1}: JSD per state weighted by state frequency, plus a bootstrap CI so tiny cells do not fire
- attribution: top 3 (S, A) cells by contribution to JSD, and which lesson_ids are over represented in those cells (this is the "why" that the paper's Contextualize promises)

Snapshots are stored as versioned artifacts with a diff API. Nothing clever needed, JSON files plus a git style parent pointer is enough.

### 5.3 Anticipate

Two questions: how will the current snapshot sequence continue, and what happens under candidate X.

5.3.1 Nonstationary behavioural twin

Given snapshots v_1..v_n, model the trajectory of P_t(A|S) not just its current value. Three options in increasing complexity. Implement the first, evaluate the second, mention the third as future work.

- T1 trend extrapolation: per (S, A) cell fit a logit linear trend against t (interaction index) or against memory size m, with bootstrap uncertainty. Forecast P_{t+h}(A|S) by extrapolating h steps. Cheap, interpretable, and enough to produce a time to envelope exit
- T2 memory conditioned: model P(A | S, memory_features) where memory_features summarise the retrieved lessons (count, mean generosity score, fraction post policy update). Forecast by forecasting memory growth, which is near deterministic since we control the extractor. Better mechanism, more work
- T3 mechanistic: run the lesson extractor itself inside the twin. Requires LLM calls inside simulation, too expensive for now

5.3.2 Simulation engine

Reuse the existing Petri net simulator from the cost estimation work. Mapping

- places = canonical states, plus resource places: human_review_queue, bob_queue
- transitions = (S, A) pairs with firing weights from P_t(A|S), outcome transitions weighted by P_t(O|S,A), timed transitions with latency from the experience log
- tokens = active cases, initial marking from P(S_0)
- time varying weights: update weights every step from the T1/T2 forecast

Output per candidate: N trajectories (start N = 2000, horizon H = 2000 interactions) giving predicted violation rate curve, satisfaction curve, cost curve, queue lengths, with quantiles.

Be honest in the paper: with one agent and no shared resource this is a Markov chain and the Petri net adds nothing. The Petri net earns its place once Alice and Bob share the human review queue and we want latency and queue growth in the forecast.

5.3.3 Envelope and time to exit

Envelope E = {violation < 10%, task_success > baseline minus 5 pts, cost per case < 1.3x baseline, review queue < Q}. Report predicted first exit time with an 80% interval, the metric that crossed, and the top contributing (S, A) cells. This output is the headline figure of the paper.

5.3.4 Counterfactuals

For each candidate from Generate, Sandbox produces a candidate snapshot on held out cases. Anticipate replaces the corresponding P(A|S) cells (only the ones the sandbox actually exercised, others keep the current forecast) and re simulates. Rank candidates by predicted envelope margin at horizon H.

### 5.4 Sandbox

Input: candidate config, held out case set (a fixed 20% of tau2 tasks never used for lesson extraction), current twin, envelope.
Run: replay the candidate on the held out set, 2 trials per task, canonicalize, build a candidate snapshot.
Output: SandboxResult with task_success, violation, satisfaction, latency, cost, candidate P(A|S), and coverage (which states were exercised, so Anticipate knows what to trust).

Budget the sandbox explicitly. It is the expensive part. See 7.4.

### 5.5 Generate (context layer only)

Three candidate types

- G1 corrective lesson: the extractor is pointed at the attribution cells from 5.2 and asked for a lesson that would reduce violations there. Same extractor, different objective
- G2 lesson removal: drop the lesson_ids over represented in violating cells
- G3 architecture gate: require escalate for value_bucket = high and within_policy_window = false

Generate always emits 2 to 4 candidates plus do nothing. It never applies anything.

### 5.6 Harmonize

Shared behavioural ontology = the CanonicalState fields that both Alice and Bob can be in. For option A these are task_type, order_status, value_bucket, within_policy_window.

Conflict detectors, all run on snapshots, no LLM

- H1 divergent policy interpretation: JSD between P_Alice(A|S) and P_Bob(A|S) on shared states above tau, restricted to the action subset both can take (e.g. escalate vs proceed)
- H2 contradictory lessons: lessons in the two memories that fire on the same shared state and prescribe incompatible actions. Detect by embedding similarity of the lesson condition plus mismatch of prescribed action class
- H3 handoff degradation: P(O | S) for cases that pass Alice to Bob worsens relative to single owner cases

Output: HarmonizationConstraint list that Negotiate must respect, and a consensus action: promote a lesson to the shared common knowledge store (both agents retrieve from it) or veto a candidate that would widen H1.

Evaluation: inject known contradictory lessons (ground truth) and measure precision and recall of H2, measure H1 on D3 where only Alice's memory is updated after the policy change.

### 5.7 Negotiate (boundary controller)

Adaptation boundary B_agent = set of (layer, risk_tier) the agent may self apply intra deployment. Starts at {(context, low)}.

Risk tier of a candidate comes from Anticipate: low if predicted violation stays inside envelope at 90% quantile and predicted task_success drop < 2 pts, medium if inside at median only, high otherwise or if it is an architecture change.

Decision procedure for each governance cycle

1. Feasible set = candidates satisfying envelope constraints under the forecast and all Harmonize constraints
2. If empty: DEFER and shorten the next window
3. Pick argmax utility U = predicted envelope margin minus lambda times cost delta minus mu times latency delta
4. If (layer, tier) of the pick is in B_agent: ACCEPT intra deployment, agent applies it
5. Else: ESCALATE to supervisor with the evidence bundle (forecast, sandbox result, constraints)
6. Supervisor oracle: approves iff the candidate's sandbox violation is below the current live violation AND task_success is not worse by more than 2 pts. Scripted, deterministic, stated as a limitation
7. Boundary update: after 3 consecutive ESCALATEd approvals in a tier, that tier enters B_agent. After 1 post hoc canary failure, it leaves. This is the "trust expands with demonstrated reliability" mechanism from the paper

Log every decision as AdaptationDecision with rationale fields populated from the evidence bundle so the paper can show traceability.

### 5.8 Evolve

- Apply: accepted candidate becomes memory_version+1 or agent_version+1 (gate change). Immutable versions, parent pointers
- Canary: after each apply, run the canary set (a fixed 10% of held out tasks) and compare against envelope. Fail means automatic rollback to parent and a boundary contraction in Negotiate
- Successor distillation: triggered when live violation has exceeded envelope for two consecutive windows and no candidate in the last cycle was feasible. Create agent v+1 with base prompt and current policy, then select the subset of lessons to carry over by greedy forward selection on the canary set (add lesson if canary violation does not rise and success does not fall). This is "distillation" in the sense of curated experience transfer. Do not cite Hinton for it
- Alignment eval per version = canary result plus drift score vs v_1 baseline, both recorded on the version

## 6. Data contracts

Keep approach1 section 22 but add these fields

- ExperienceRecord: memory_version, lessons_in_context, t_global
- BehavioralSnapshot: attribution (top cells, lesson ids), drift_ci, coverage (states with n >= 20)
- Prediction: horizon, per metric quantile curves, first_exit_time with interval, exit_metric, contributing_cells, twin_model_id (T1 or T2)
- SandboxResult: coverage, n_trials, case_set_id
- HarmonizationConstraint: detector_id (H1, H2, H3), evidence, consensus_action
- AdaptationDecision: risk_tier, in_boundary (bool), supervisor_verdict, boundary_after
- AgentVersion: parent, memory_version, gates, canary_result, alignment_score

All as JSON schema files in the repo, validated on write.

## 7. Experimental design

### 7.1 Conditions

Drift conditions D1, D2, D3 (D4 optional). Retail domain for everything. Airline only if Option B is chosen for Bob.

### 7.2 Systems compared

- A0 reactive: no governance, threshold monitor on live violation, when exceeded apply G3 gate (this is what a sensible engineer does today)
- A1 + Contextualize: same as A0 but the monitor is JSD drift on snapshots. Tests whether behavioural drift is visible before violation
- A2 + Anticipate: forecast triggers governance at predicted exit minus lead L instead of at actual exit
- A3 + Sandbox and counterfactuals: candidates ranked by twin instead of applying G3 blindly
- A4 + Negotiate: boundary controller with supervisor oracle
- A5 + Harmonize: two agent setting only
- Full CHANGE = A5 plus Evolve
- External baselines to include if time: ABA style behavioural anchoring (inject baseline exemplars scaled by drift) as an adaptation baseline, and ASI style drift monitor from the Agent Drift paper as a detection baseline. Both are cheap to implement from the papers

Minimum viable paper if things go badly: A0, A1, A2, Full on D2 and D3, single agent. That alone supports the claim.

### 7.3 Metrics

Detection and forecasting (Contextualize, Anticipate)

- lead time: interactions between first alert and actual envelope exit, positive is good
- false alert rate on D1
- forecast error: JSD between forecast P_{t+h}(A|S) and realized, at h = 250, 500, 1000
- time to exit error: predicted vs actual, plus interval coverage
- attribution accuracy on D3: does the top contributing cell match the changed policy rule

Counterfactual fidelity (Sandbox and Anticipate)

- per candidate predicted vs realized violation and success when the candidate is actually deployed for a window
- Spearman rank correlation between predicted and realized candidate ranking

Governance outcomes (Negotiate, Evolve)

- cumulative violations over the run
- task success retained
- cost and latency overhead of governance (LLM calls spent in sandbox per accepted change)
- unnecessary adaptation rate on D1
- boundary expansion correctness: fraction of self applied changes that later passed canary
- rollbacks triggered

Harmonize

- precision and recall of H2 against injected contradictions
- H1 divergence over time on D3 with and without the shared store

### 7.4 Budget

Rough per episode: 8 to 15 agent calls plus user sim calls, 10k to 25k tokens. Assume 20k.

- Drift runs: 3 conditions x 500 episodes x 2 seeds = 3000 episodes
- Governance runs: 4 systems x 2 conditions x 500 episodes x 2 seeds = 8000 episodes
- Sandbox: per cycle 4 candidates x 40 held out tasks x 2 trials = 320 episodes, maybe 8 cycles per run, 20 runs = about 50k episodes. This is the problem

Sandbox dominates. Fixes, in order: cut candidates to 3, trials to 1, held out tasks to 25, cycles to 5. That is 375 per run, 7.5k total. Total then roughly 20k episodes at 20k tokens = 400M tokens. At a cheap model this is tens to low hundreds of USD. At a frontier model it is not affordable. Use the cheap subject models already in use for the cost estimation work for both agent and user sim, and state the model in the paper. Local 7B to 8B on the RTX 5060 is possible for the user simulator but will be slow, treat it as a fallback not the plan.

Decide the budget with Karthik in week 1, before building anything that depends on it.

### 7.5 Reproducibility

Pin tau2-bench version, pin model names and dates, fix seeds, store every ExperienceRecord and snapshot, anonymous repo via anonymous.4open.science for submission, Zenodo on acceptance. CAIN says sharing is the default.

## 8. Timeline

Week 1, 15 to 21 Sep: tau2 up, cheap model wired through LiteLLM, lesson memory (Generate G0) working, instrumentation and canonicalization done, D2 sanity gate passed. Budget decided. Bob option chosen.

Week 2, 22 to 28 Sep: Contextualize complete with drift score and attribution. Anticipate T1 with Petri net simulation reused from the estimator. Envelope and time to exit output. First figure: forecast vs realized on D2.

Week 3, 29 Sep to 5 Oct: Sandbox, Generate G1 to G3, counterfactual ranking, Negotiate boundary controller and supervisor oracle, Evolve apply and canary and rollback. Single agent full loop runs end to end on D2.

Week 4, 6 to 12 Oct: Bob router, Harmonize H1 to H3, shared store, successor distillation. Anticipate T2 if T1 results are weak. Start writing sections 1 to 4 in parallel.

Week 5, 13 to 19 Oct: all experiments. Freeze code on 19 Oct. Anything not running by then is cut and mentioned as future work.

Week 6, 20 to 26 Oct: writing, figures, related work, threats to validity. Internal review by Shaunak and Karthik.

Week 7, 27 to 30 Oct: polish, anonymize, submit. No new experiments.

Cut order if behind: D4, llm_coordination, T2, external baselines, H3, successor distillation, Harmonize entirely (then it is a 5 capability paper and that is still fine).

## 9. Risks

- Drift does not materialize under D2. Mitigation: week 1 gate, stronger satisfaction proxy, higher k. If it truly does not drift, D3 alone still gives the paper
- Forecast is no better than a naive last value baseline. Mitigation: report it honestly, the counterfactual ranking result can carry the paper. Always include the naive baseline in the table
- Sandbox cost blows up. Mitigation: 7.4 reductions, decided up front
- tau2 user simulator noise swamps behavioural signal. Mitigation: Dirichlet smoothing, bigger windows, report CIs, 2 seeds minimum
- Reviewers say it is HarmonE with a new managed element. Mitigation: the twin is the novelty, HarmonE has no forecasting and no counterfactual ranking. Say it once in related work and move on
- Reviewers say the supervisor oracle is unrealistic. Mitigation: it is a limitation, and the boundary expansion logic is the contribution, not the oracle

## 10. Related work to position against

Read these before writing section 2. All 2026 unless noted.

- Agent Drift and the Agent Stability Index (arXiv 2601.04170): quantifies degradation over 200+ interactions, proposes Adaptive Behavioral Anchoring. We forecast rather than measure, and we govern candidate adaptations rather than always anchoring. Use ASI as a detection baseline
- Agent Behavioral Contracts (arXiv 2602.22302): preconditions, invariants, governance, recovery enforced at runtime, with a drift bounds argument. Reactive enforcement at action level. We are anticipatory and work at the distribution level
- Runtime Governance for AI Agents: Policies on Paths (arXiv 2603.16586): policy engine over execution paths. Reactive
- MI9 (arXiv 2508.03858): goal conditioned drift indicator that separates intentional adaptation from suspicious change. Closest to Contextualize plus drift score. No forecasting, no counterfactuals
- Governor / sequence level behavioural analysis (arXiv 2606.15579): production deployment study of sequence pathologies. Useful for motivation and for the "before and after" evaluation style
- On Safety Risks in Experience Driven Self Evolving Agents (arXiv 2604.16968) and Rethinking Experience Utilization (arXiv 2605.07164): show memory based self evolution (ReasoningBank, AWM) creates safety regressions. This is our justification for the drift source
- Self evolving agents survey (TMLR 2026, "what, when, how, where to evolve"): their what and when axes are our layers and timings, cite it for the taxonomy
- EvoMemBench (arXiv 2605.18421) and LifelongAgentBench: benchmarks for evolution itself, not for governing it. Position as complementary
- Always On Agents survey (arXiv 2606.30306): calls governance the missing half of the lifecycle, good framing quote target
- Original CHANGE (arXiv 2601.06456), HarmonE (ECSA 2025), AgentOps (Dong et al. 2024), all in third person

## 11. Decisions I need from you before week 1 ends

1. Budget and model for agent and user simulator
2. Bob option A or B
3. Is Shaunak building any of this or is it all you plus a coding agent
4. Full paper with the minimum viable scope, or short paper as a fallback. My view: aim full, decide on 19 Oct