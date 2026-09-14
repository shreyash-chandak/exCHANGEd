# CHANGE Extension: Predictive Behavioral Governance

## 1. Necessary Context

The position paper **“CHANGE: A Framework for Continuous Governance of Evolving Agentic Systems”** proposes governance capabilities for agentic systems that evolve over time. For the CAIN 2027 extension, the goal is to move beyond a conceptual framework and demonstrate a concrete implementation of selected CHANGE capabilities, with empirical evaluation and ablations.

The proposed implementation focuses on a closed-loop mechanism for **observing, modeling, anticipating, evaluating, and authorizing agent evolution**. Generation of candidate changes (G) and physical application of approved changes (E) are treated as outside the scope of the core prototype.

The central research idea is:

> Instead of only detecting that an agent's behavior has already drifted, construct a probabilistic behavioral model from runtime experience and use it to predict future behavior and evaluate the consequences of possible adaptations before they are deployed.

This turns CHANGE from a primarily reactive governance framework into a **predictive adaptation loop**.

---

# 2. Core Architecture

The proposed workflow is:

```text
Agent Runtime
     │
     ▼
Instrumentation / Experience Extraction
     │
     ▼
Experience Store
     │
     ▼
CONTEXTUALIZE
     │
     ├── Experiential Context
     │
     └── Behavioral Snapshot
              │
              ▼
         ANTICIPATE
              │
              ├── Behavioral Model
              ├── Scenario Generator
              ├── Trajectory Simulator
              └── Forecaster
              │
              ▼
          SANDBOX
              │
              ▼
          NEGOTIATE
              ▲
              │
          HARMONIZE
              │
              ▼
      Adaptation Decision
       ┌────────┴────────┐
       ▼                 ▼
  INTRA-TEST         INTER-TEST
       │                 │
       └────────┬────────┘
                ▼
        G / E (out of scope)
```

The implementation should explicitly distinguish two questions:

### WHEN should the agent evolve?

1. **Intra-test-time evolution** — adaptation while the current test/deployment is ongoing.
2. **Inter-test-time evolution** — adaptation between test/deployment cycles using accumulated evidence.

### WHAT should evolve?

Candidate changes can target four layers:

1. **Model** — underlying model or normative policy/specification.
2. **Context** — memory, lessons, examples, prompts/context assembly.
3. **Tools** — available tools, tool permissions, tool constraints, verification gates.
4. **Architecture** — routing, verification, escalation, topology, human-in-the-loop structure.

A useful taxonomy distinction is:

- **Policy** = normative source of truth / constraint.
- **Lesson** = empirically derived behavioral guidance extracted from experience.
- **Memory** = episodic information retained from previous interactions.
- **Examples** = exemplars used to shape behavior.
- **Prompt/context** = mechanism that assembles information presented to the agent.

A lesson is therefore a form of **context adaptation**, not model-weight training. For example:

```text
Repeated experience:
High-value damaged orders are frequently mishandled.

Extracted lesson:
"Before issuing a high-value refund, verify eligibility
against the refund policy."

Candidate:
Add lesson to the agent's experiential context.

Sandbox:
Does the lesson reduce policy violations without
unacceptably reducing task success or increasing latency?

Negotiate:
Should the lesson be accepted?
```

---

# 3. Running Example: Alice and Bob

Use a small multi-agent testbed to make the architecture concrete.

### Alice

A customer-support/refund agent.

It receives cases such as:

- order value
- delay severity
- product condition
- customer sentiment
- policy sensitivity

It chooses actions such as:

- partial refund
- full refund
- deny
- escalate to human

### Bob

A logistics agent responsible for downstream fulfillment/logistics decisions.

The important point is not the specific domains. They provide a setting in which agents have **observable states, actions, outcomes, policies, and interactions**.

---

# 4. Contextualize: From Logs to Behavioral Distributions

The first important implementation question is:

> How do raw runtime logs become a representation that Anticipate can simulate?

## 4.1 Raw Experience Records

Every relevant agent execution should be converted into a structured experience record.

Conceptually:

```text
ExperienceRecord {
    agent_id
    agent_version
    timestamp

    state
    context

    action
    tools_used

    outcome
    feedback

    policy_evaluation

    latency
    cost
}
```

The state should be **canonicalized** rather than simply storing raw text.

For Alice, a state might be:

```text
{
    task_type: "refund",
    order_value_bucket: "high",
    delay_severity: "severe",
    customer_sentiment: "negative",
    policy_sensitive: true,
    tool_available: true
}
```

This is important because behavioral distributions must be conditioned on comparable situations.

---

# 5. The Probability Distributions

The key output of Contextualize is not one global distribution over everything Alice does.

It should produce distributions **conditioned on behavioral state**.

## 5.1 Behavioral / Action Distribution

The primary behavioral distribution is:

\[
P(A \mid S)
\]

Meaning:

> Given that the agent encounters behavioral state \(S\), what actions does it tend to take?

Example:

```text
State:
high-value + severe-delay + negative sentiment

P(action | state):

partial_refund    0.72
full_refund       0.08
escalate          0.15
deny              0.05
```

This is an empirical behavioral tendency.

It does **not** mean that Alice is 72% confident in a partial refund. It means that, among comparable observed executions, approximately 72% resulted in that action.

---

## 5.2 Outcome Distribution

A second distribution captures consequences:

\[
P(O \mid S,A)
\]

For example:

```text
State:
high-value + severe-delay

Action:
partial_refund

Outcome:

customer_satisfied       0.71
customer_dissatisfied    0.20
policy_complaint         0.09
```

This connects behavior to consequences.

---

## 5.3 State-Transition Distribution

Anticipate also needs to model how one behavioral state leads to another:

\[
P(S_{t+1} \mid S_t,A_t,O_t)
\]

For example:

```text
high-value + severe-delay
          │
          │ partial_refund
          ▼
customer satisfied       0.71 ──► normal follow-up
customer dissatisfied    0.20 ──► escalation
policy complaint         0.09 ──► human review
```

These three distributions together form the basis of a probabilistic behavioral model.

---

# 6. Behavioral Snapshots

Contextualize should aggregate experience into **versioned Behavioral Snapshots**.

Example:

```text
BehavioralSnapshot v7
────────────────────────────────

Agent: Alice
Agent version: 12
Time window: Sept 1–7

State:
high-value + severe-delay

Action distribution:
    partial_refund = 0.72
    escalate       = 0.15
    deny            = 0.13

Outcome distribution:
    satisfaction:
        high   = 0.71
        medium = 0.20
        low    = 0.09

    policy:
        compliant = 0.91
        violation = 0.09

Transition distribution:
    satisfied → normal-case = 0.71
    dissatisfied → escalation = 0.20
    complaint → human-review = 0.09

Samples: 1,842
Confidence / uncertainty: ...
```

Snapshots should be versioned so that they can be compared.

For example:

```text
Snapshot v6:
partial_refund = 0.31
escalate       = 0.42
deny           = 0.27

Snapshot v7:
partial_refund = 0.72
escalate       = 0.15
deny           = 0.13
```

This represents a material behavioral shift even if conventional infrastructure metrics such as latency and error rate remain normal.

A divergence measure such as Jensen-Shannon divergence can quantify the shift, while sample counts and uncertainty should prevent overreacting to small-sample fluctuations.

---

# 7. Anticipate: What It Actually Does

Once Contextualize has produced these distributions, Anticipate becomes a **probabilistic behavioral forecasting and counterfactual evaluation engine**.

Its fundamental question is:

> If the agent continues behaving according to the current behavioral model, what is likely to happen over the next N interactions?

And its second question is:

> What is likely to happen if we introduce candidate adaptation X instead?

---

# 8. Building the Behavioral Model

The distributions can be represented as a behavioral graph or stochastic Petri net.

A simplified representation is:

```text
[Order Received]
       │
       ▼
[Assess Case]
       │
   ┌───┼────────┐
   ▼   ▼        ▼
Refund Escalate Deny
```

Instead of deterministic transitions, transitions carry empirical probabilities:

```text
Assess Case
    ├── partial_refund   0.72
    ├── escalate         0.15
    └── deny             0.13
```

The existing Petri-net machinery can therefore serve as the behavioral digital twin, provided it represents **observable agent behavior and state transitions**, rather than attempting to model the internal LLM reasoning process.

The model should contain at least:

\[
P(A\mid S)
\]

\[
P(O\mid S,A)
\]

\[
P(S'\mid S,A,O)
\]

---

# 9. Why the Environment Model Matters

Anticipate cannot simply extrapolate:

```text
state → action
```

because that only predicts isolated decisions.

It needs:

```text
state
  ↓
action
  ↓
outcome
  ↓
next state
  ↓
next action
  ↓
...
```

The environment/state-transition probabilities can initially be learned empirically from runtime traces.

This allows Anticipate to model behavioral trajectories rather than isolated predictions.

---

# 10. Trajectory Simulation

Given a current behavioral model, Anticipate samples future trajectories.

Conceptually:

```python
for trajectory in range(NUM_TRAJECTORIES):

    state = sample_initial_state()

    for t in range(HORIZON):

        action = sample(P_action[state])

        outcome = sample(P_outcome[state, action])

        next_state = sample(
            P_transition[state, action, outcome]
        )

        record(state, action, outcome)

        state = next_state
```

The implementation can use the stochastic Petri-net simulator instead of literal state sampling.

The important point is that the simulator generates **many possible future trajectories**.

For example:

```text
10,000 trajectories
×
5,000 future interactions
```

The result is a distribution over possible futures.

---

# 11. Forecasting the Future Behavioral Envelope

Suppose Alice's current observed behavior is:

```text
Partial refund:       58%
Escalation:           14%
Denial:               28%

Policy violation:      4%
Customer satisfaction: 81%
```

Anticipate might forecast:

```text
After 5,000 interactions:

Partial refund:       76%
Escalation:             8%
Denial:                16%

Policy violation:      19%
Customer satisfaction: 74%
Average cost:          +31%
```

The useful output is therefore not merely:

> “Behavior is drifting.”

It is:

> “Under current behavior, policy violation is predicted to rise from 4% to approximately 19% over the next 5,000 interactions.”

---

# 12. Threshold Crossing / Time-to-Failure

Define an acceptable behavioral envelope.

For example:

```text
policy violation < 10%
customer satisfaction > 75%
average refund cost < threshold
```

Anticipate can examine simulated trajectories:

```text
Future interactions     Predicted violation

0                         4%
500                       6%
1000                      8%
1500                     10%
2000                     13%
2500                     15%
3000                     17%
```

It can therefore report:

```text
Predicted threshold crossing:
~1,450 interactions

Confidence:
87%

Primary contributing behavior:
increasing partial-refund probability
for high-value/severe-delay cases
```

This is the main distinction between **reactive monitoring** and **anticipatory governance**.

A reactive monitor says:

> The violation threshold has been exceeded.

Anticipate says:

> The current trajectory is likely to exceed the threshold soon.

---

# 13. Anticipate Should Also Support Counterfactuals

Prediction alone is not enough for a governance loop.

Suppose candidate adaptations are:

### Candidate A: Context/lesson adaptation

Add:

```text
"Before issuing a high-value refund,
verify eligibility against the refund policy."
```

### Candidate B: Tool adaptation

Require a policy-check tool before refund authorization.

### Candidate C: Architecture adaptation

Require human approval for refunds above ₹3,000.

These candidates can be evaluated against the behavioral model.

Conceptually:

```text
Current Configuration
        │
        ▼
Current Behavioral Model
        │
        ├──────────────► simulate "do nothing"
        │
        ├── Candidate A ─► simulate
        │
        ├── Candidate B ─► simulate
        │
        └── Candidate C ─► simulate
```

This produces predicted outcomes for each possible future.

---

# 14. Where Counterfactual Probabilities Come From

The simulator should not simply invent the effects of an intervention.

The strongest initial implementation is **empirical replay / sandbox execution**.

For example:

```text
Historical cases
      │
      ▼
Candidate configuration
      │
      ▼
Sandbox execution
      │
      ▼
Candidate experience records
      │
      ▼
Contextualize
      │
      ▼
Candidate behavioral distributions
```

These candidate distributions can then be used to calibrate the behavioral simulator.

This creates a useful combination:

### Empirical evidence

Historical replay / sandbox tests establish what the candidate actually does on observed cases.

### Simulation

The behavioral twin extrapolates those effects to longer horizons and alternative environmental trajectories.

This avoids requiring the digital twin to magically know how an arbitrary prompt/tool/architecture change will behave.

---

# 15. Sandbox

Sandbox is therefore an explicit component rather than a generic testing step.

Input:

```text
CandidateConfiguration
TestCases
CurrentBehavioralModel
GovernanceConstraints
```

Output:

```text
SandboxResult {
    task_success
    policy_compliance
    safety
    satisfaction
    latency
    cost
    behavioral_distribution
}
```

It can combine:

1. Historical replay.
2. Synthetic test cases.
3. Behavioral-model simulation.
4. Controlled candidate execution.

---

# 16. Negotiate

Negotiate converts predictions and sandbox evidence into a governance decision.

Inputs:

```text
Current behavioral state
Anticipate predictions
Sandbox results
Governance constraints
Harmonize constraints
Adaptation timing
```

Candidate selection should not be a simple:

```text
if risk > threshold:
    adapt
```

Instead, formulate adaptation as constrained decision-making.

For example:

\[
\max_I U(I)
\]

subject to:

\[
Risk(I) < R_{max}
\]

\[
Violation(I) < V_{max}
\]

\[
Success(I) > S_{min}
\]

\[
Latency(I) < L_{max}
\]

and any autonomy/governance constraints.

Example candidate comparison:

| Candidate | Violation | Satisfaction | Cost | Latency |
|---|---:|---:|---:|---:|
| No change | 19% | 74% | +31% | baseline |
| Prompt/lesson | 12% | 76% | +20% | +2% |
| Policy tool | 7% | 79% | +12% | +12% |
| Hard constraint | 2% | 67% | +5% | +4% |
| Human approval > ₹3k | 6% | 77% | +8% | +18% |

Negotiate selects the candidate that provides the best acceptable trade-off under the governance constraints.

---

# 17. Harmonize

Harmonize is particularly important once Alice and Bob are both present.

The initial implementation does not need a sophisticated LLM consensus protocol.

Instead, use a **shared behavioral ontology**.

For example:

```text
task
state
action
policy
risk
resource
outcome
responsibility
```

Each agent's experience is canonicalized into this ontology.

Then Harmonize can compare agents operating in semantically equivalent states.

For example:

```text
Alice:
high-value + policy-sensitive
    → refund

Bob:
high-value + policy-sensitive
    → approve shipment
```

If the agents share a policy boundary or responsibility, Harmonize can detect disagreement.

It can produce constraints such as:

```text
HarmonizationConstraint {
    agents: [Alice, Bob]
    shared_state: high_value + policy_sensitive
    conflict: inconsistent_policy_interpretation
    required_property:
        both agents must respect policy P
}
```

These constraints feed back into Negotiate.

Thus:

```text
Alice's candidate adaptation
          │
          ▼
      Harmonize
          │
          ▼
"Does this create conflict with Bob?"
          │
          ▼
constraints
          │
          ▼
      Negotiate
```

---

# 18. Adaptation Timing

The final decision should include when the adaptation should occur.

```text
AdaptationDecision {
    candidate_id

    timing:
        INTRA_TEST
        or
        INTER_TEST

    decision:
        ACCEPT
        REJECT
        DEFER

    rationale
    constraints_satisfied
}
```

### Intra-test

Appropriate for changes that are:

- low risk
- reversible
- narrowly scoped
- supported by strong evidence

Examples:

- adding a lesson
- changing contextual examples
- tightening a tool gate

### Inter-test

More appropriate for:

- model replacement
- major policy changes
- architectural restructuring
- changes requiring broad regression testing

---

# 19. G and E Are Outside the Core Prototype

The architecture deliberately separates:

### G — Generate

Creates candidate adaptations.

Examples:

- propose a new lesson
- propose a prompt change
- propose a tool gate
- propose an architectural modification

### CHANGE prototype

Evaluates and governs those candidates.

### E — Evolve

Actually applies the approved change.

This means the prototype can accept candidate configurations from a simple rule-based or manually specified generator without needing to make automated code/model generation the central research contribution.

---

# 20. Complete End-to-End Example

The complete lifecycle becomes:

```text
1. Alice executes normally.

2. Instrumentation records:
   state, action, outcome, tools, policy result, etc.

3. Experience Extractor creates structured records.

4. Contextualize aggregates records.

5. Behavioral Snapshot v7 is produced.

6. Snapshot v7 is compared against v6.

7. A significant shift in P(action | state) is detected.

8. Anticipate constructs/updates the behavioral twin.

9. Anticipate simulates future behavior.

10. Forecast shows policy violation will likely
    exceed the acceptable envelope.

11. Candidate adaptations are supplied by G
    (outside the prototype).

12. Anticipate evaluates counterfactual candidates.

13. Sandbox empirically tests candidates.

14. Harmonize checks effects on Bob and
    shared policy/responsibility constraints.

15. Negotiate selects the best admissible candidate.

16. Negotiate determines:
    INTRA_TEST vs INTER_TEST.

17. AdaptationDecision is produced.

18. E applies the approved change
    (outside the prototype).

19. The new agent version executes.

20. Contextualize measures the resulting behavior.

21. The loop repeats.
```

The resulting control loop is:

```text
             ┌───────────────────────┐
             │                       │
             ▼                       │
         Experience                  │
             │                       │
             ▼                       │
       Contextualize                │
             │                       │
             ▼                       │
      Behavioral Snapshot           │
             │                       │
             ▼                       │
         Anticipate                 │
             │                       │
       ┌─────┴─────┐                │
       ▼           ▼                │
   Forecast    Counterfactuals      │
       │           │                │
       └─────┬─────┘                │
             ▼                      │
          Sandbox                   │
             │                      │
             ▼                      │
         Harmonize                  │
             │                      │
             ▼                      │
         Negotiate                  │
             │                      │
             ▼                      │
    Adaptation Decision             │
             │                      │
             ▼                      │
          Evolve                    │
             │                      │
             └──────────────────────┘
```

---

# 22. Proposed Data Contracts

A concrete prototype can use the following artifacts.

## Experience

```text
Experience {
    agent_id
    agent_version
    timestamp
    state
    context
    action
    tools
    outcome
    feedback
    policy_evaluation
    latency
    cost
}
```

## BehavioralSnapshot

```text
BehavioralSnapshot {
    agent_id
    agent_version
    snapshot_id
    time_window

    state_distributions
    action_distributions
    outcome_distributions
    transition_distributions

    policy_compliance
    performance_metrics

    sample_counts
    confidence
}
```

## BehavioralModel

```text
BehavioralModel {
    snapshot_id

    states
    actions
    outcomes
    transitions

    P_action
    P_outcome
    P_transition

    environment_model
}
```

## Prediction

```text
Prediction {
    candidate_id
    horizon

    expected_behavior
    expected_outcomes
    risk_trajectory

    threshold_crossing_time
    uncertainty
}
```

## SandboxResult

```text
SandboxResult {
    candidate_id

    task_success
    policy_compliance
    safety
    satisfaction

    latency
    cost

    behavioral_distribution
}
```

## HarmonizationConstraint

```text
HarmonizationConstraint {
    agents
    shared_state
    conflict
    required_property
}
```

## AdaptationDecision

```text
AdaptationDecision {
    candidate_id

    timing
    decision

    rationale
    constraints_satisfied
}
```

---

# 23. Evaluation Plan

The strongest experimental comparison is a progression from reactive to predictive governance.

### A0 — Reactive baseline

```text
Agent + monitoring
```

The system only reacts after undesirable behavior has occurred.

### A1 — + Contextualize

```text
Agent + behavioral state estimation
```

Measure whether behavioral drift is detected more meaningfully than raw infrastructure metrics.

### A2 — + Anticipate

```text
A1 + behavioral forecasting
```

Measure:

- future action-distribution prediction accuracy
- outcome prediction accuracy
- threshold-crossing prediction
- lead time before actual violation
- uncertainty/calibration

### A3 — + Sandbox / counterfactual evaluation

Measure:

- candidate outcome prediction accuracy
- correlation between simulated and actual candidate behavior
- ability to reject unsafe adaptations

### A4 — + Negotiate

Measure:

- constraint satisfaction
- utility of selected adaptation
- quality of trade-offs
- unnecessary adaptation rate

### A5 — + Harmonize

Measure:

- cross-agent policy conflicts detected
- responsibility conflicts detected
- violations avoided through coordination

A smaller study can focus on A0, A1, A2, and the full loop.

---

# 24. The Central Scientific Claim

The strongest version of the paper should not be:

> “We implemented six components of CHANGE.”

That risks becoming a checklist implementation.

The stronger claim is:

> **A continuously governed agent can be represented through empirical behavioral distributions, transformed into a probabilistic behavioral model, and simulated forward to anticipate undesirable future behavior and evaluate candidate adaptations before deployment.**

CHANGE then provides the governance loop around that predictive model:

```text
Observe
  ↓
Contextualize
  ↓
Model behavior
  ↓
Anticipate future trajectories
  ↓
Evaluate counterfactual adaptations
  ↓
Harmonize with other agents
  ↓
Negotiate under governance constraints
  ↓
Authorize evolution
  ↓
Observe the resulting behavior
```

The key empirical distinction is therefore:

**Reactive governance:**  
“Has the agent already violated its behavioral envelope?”

versus

**Predictive governance:**  
“Given the agent's current behavioral trajectory, is it likely to violate its behavioral envelope, when will that happen, and which admissible adaptation is most likely to prevent it?”

That distinction gives Anticipate a concrete purpose and gives the overall CHANGE implementation a measurable research contribution.
