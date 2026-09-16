# A-OCL Core Design

## Purpose

A-OCL is a host-independent governance layer at the action execution boundary.
It is not an agent, dialogue loop, benchmark runner, or general-purpose RAG
system. A benchmark owns its agents, state transitions, rewards, and execution.
A-OCL observes a normalized proposal and returns a control decision.

## Two levels

Level 1 hard constraints are deterministic host-owned checks such as schema,
authority, inventory, cash, price, or disclosure rules. Level 2 soft
constraints are reviewed defensive heuristics distilled from failed episodes.
Hard checks provide the safety boundary; soft constraints improve semantic and
contextual handling over time.

## Stable host contract

```text
host proposal
  -> ProposedAction + ObservableContext + optional host pre-checks
  -> hard validators
  -> retrieve approved soft constraints
  -> evaluate constraint activation
  -> APPROVE / WARN / REVISE / BLOCK / ESCALATE
  -> host decides whether to execute
  -> host reports ObservedOutcome
```

The runtime never calls a host tool. Adapters must exclude oracle labels,
future outcomes, hidden benchmark answers, and reward signals from online
context.

## Adaptive Constraint Bank

Level 2 has one experience representation, not separate detection and repair
skill types. Each approved `SoftConstraint` is a defensive skill with:

- `trigger_pattern` as its `when_to_apply` condition;
- `instruction` as its reusable defensive principle;
- `response` as its control action;
- optional `metadata.revision_guidance` when that action is `REVISE`;
- `metadata.scope` (`general` or `task_specific`) for analysis and optional
  hierarchical retrieval.

Hard validators remain code and never enter the bank. A learned constraint may
both detect a prohibited proposal and tell the host how to revise it, so a
second Repair SkillBank is unnecessary. `FrozenConstraintLibrary` remains the
backward-compatible implementation name; `FrozenConstraintBank` is its
research-facing alias.

## Frozen experience versions

Learning is asynchronous and split-safe:

```text
derivation failure -> diagnosis -> candidate -> paired fresh host rollouts
                   -> fixed promotion rule -> new immutable library version
```

An active bank is frozen for an evaluation run. Failed evaluation episodes
never feed back into that run. Each promoted version records provenance,
validation metrics, parent digest, and its own digest.

This gives A-OCL a closed self-improving governance loop. Let `H` be the
immutable Hard Safety Envelope and `X_k` the frozen Constraint Bank at update
step `k`. A host episode generated under `(H, X_k)` produces trajectory and
outcome feedback. A fixed model may turn a diagnosed failure into a Candidate,
but only host-supplied verification evidence and the configured update rule can
create `X_{k+1}`:

```text
(H, X_k) -> governed trajectory -> diagnosed feedback -> Candidate
         -> Parent/Trial evidence -> update decision -> (H, X_{k+1})
```

No model parameters change. Self-improvement means that accumulated experience
changes future governance decisions through `X_k` while `H` remains invariant.

The core defines step-grounded paired outcomes and the promotion contract but
never runs a benchmark. It has no concept of an "attack" or "benign" episode.
A host adapter labels each proposal as policy-violating or safe, records whether
it executed, and attributes candidate activations by action ID. The core then
requires no executed Trial violations, an increase in blocked violating steps,
no increase in blocked safe steps, an observed candidate-attributed intercept,
and no loss of task successes. An LLM may supply a fixed semantic label where
structured state is insufficient, but it cannot approve its own constraint.

Those requirements describe the conservative `strict` promotion baseline, not
a necessary definition of A-OCL. Verification produces measurements; promotion
policy decides how those measurements control Bank growth. The core policy also
supports marginal safety improvement subject to explicit executed-violation,
false-block, and valid-success budgets. AgenticPay records a frozen `strict` or
`marginal` preset before test evaluation and with each promoted Bank version.

## Capacity and verified retirement

The default Bank has no active-constraint limit. This keeps the main learning
experiment focused on whether validated experience improves governance rather
than on a storage budget. A host may later configure
`ConstraintBankMaintenancePolicy.max_active_constraints` to study bounded
long-term operation.

Reaching the configured limit triggers a cleanup audit; it never directly
deletes a constraint. The host first shortlists rules with evidence of
duplication, supersession, persistent false blocking, or no confirmed marginal
contribution. It then compares fresh paired rollouts under the current Bank and
the Bank with one rule removed. A rule can leave the active snapshot only when
removal does not increase executed violations or reduce task/valid success, and
either reduces false blocking or confirms an explicitly redundant rule. If no
rule passes, the incoming Candidate is rejected or deferred. Hard constraints
never participate in cleanup, and prior immutable Bank versions retain the full
history for audit and rollback.

## Adapter responsibility

Each adapter owns native action mapping, visible-state mapping, host-specific
hard checks, execution/block semantics, and outcome mapping. It must not copy
the core library, retrieval, evaluator, learning, or versioning code.

Current adapters:

- AgenticPay: seller response before `env.step()`.
- CoffeeBench: focal `BusinessApp` operational tool before invocation.
- ShoppingBench: planned; final `recommend_product` is the primary controlled
  boundary while search and inspection tools are normally observable context.
