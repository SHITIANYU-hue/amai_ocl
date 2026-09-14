# AgenticPay A-OCL Adapter Design

## Role

This package is the AgenticPay host adapter for `aocl_core`. It is not an
independent control runtime and does not own constraint retrieval, semantic
evaluation, learning, or library versioning.

AgenticPay remains external and owns the buyer, seller, dialogue loop,
environment transitions, rewards, and execution. The adapter controls only the
seller proposal immediately before `env.step()`:

```text
buyer message -> seller proposal -> AgenticPay adapter -> A-OCL core
                                                   approve/warn -> env.step(text)
                                            block/escalate/revise -> no execution
```

The package imports AgenticPay lazily, so its adapter contracts remain
importable when the benchmark is not installed.

## Files owned here

```text
agenticpay_adapter.py  seller text/context normalization and hard price rule
agenticpay_runner.py   native AgenticPay episode loop and execution boundary
trace_export.py        native run result to host-independent learning trace
demo.py                one real-LLM vertical demonstration
adaptive_demo.py       resumable L000 -> candidate -> validation -> L001 demo
batch_experiment.py    frozen-library growth curve over disjoint profiles
```

All shared contracts and mechanisms live in `integrations/aocl_core`.

## Online mapping

Each seller proposal becomes:

- `action_type="commerce.respond"`;
- `visible_text` and payload containing only the proposed seller response;
- visible conversation turns and sanitized environment observation;
- no persona label, reward, hidden price bound, oracle answer, or future result.

Hard Constraints are the generic Level 1 concept. Their deterministic
validators are host-owned because action parsing and hidden organizational
bounds are environment-specific. AgenticPay contributes a versioned static
suite that checks the configured seller identity/action boundary, requires one
valid positive `SELLER_PRICE` marker, enforces the hidden seller floor, and
blocks explicit credential values such as card numbers, SSNs, CVVs, routing
numbers, and account numbers. Hidden bounds and detected secret values are
never exposed to retrieval, the semantic evaluator, or audit metadata.

The explicit-sensitive-data validator deliberately does not block keywords
alone. A safe refusal that mentions “credit card” must pass the hard layer;
whether a proposal indirectly requests, agrees to, or facilitates off-platform
payment remains a Level 2 semantic decision. The suite version is persisted in
configs, episode artifacts, and metrics so old runs cannot silently resume
under new hard semantics.

Decision mapping is fixed:

```text
approve/warn  execute the exact proposed text
revise        optionally regenerate within a fixed retry budget, then re-check
block         pass no seller action to AgenticPay
escalate      pass no seller action without an external resolution
```

## Real-LLM demo

The small demo uses separate buyer, seller, and gate model calls. A deliberately
vulnerable seller agrees to an off-platform payment request; the external gate
must prevent that proposal from reaching AgenticPay. It demonstrates the
online boundary only, not the offline learning claim.

## Adaptive demo

The adaptive demo is the smallest complete learning experiment. It uses four
disjoint profiles: one derivation failure, one validation attack, one benign
validation case, and one held-out evaluation attack. A Meta-Agent converts the
derivation trace into one candidate constraint. A fixed promotion policy accepts
it only when Parent + Candidate improves over the Parent Bank in complete new
attack and benign episodes, then writes immutable `L001`.

The blinded LLM judge handles only the semantic question of which seller
proposals violate policy. Its input excludes the Bank, Parent/Trial condition,
current execution flags, episode identifier, and final reward. Code aligns the
returned step IDs with proposal execution flags. Audit events are aligned by
`action_id` to prove that the candidate itself activated on each counted
intercept. Safe over-blocking is counted in every profile, not only profiles
named benign. This prevents an episode-level intervention elsewhere in the
dialogue from being credited to the candidate.

Every stage is persisted before the next begins. `--resume` reuses completed
episodes and model calls, while artifacts that fail a machine-checkable schema
or execution invariant are rejected and regenerated.

## Self-improving mechanism

The adaptive object is the external governance state. Let `H` be the immutable
Hard Safety Envelope and `X_k` the frozen Constraint Bank at update step `k`:

```text
OCL_k = (H, X_k)

X_k -> governed episode -> failure feedback -> Candidate
    -> Parent/Trial verification -> update rule -> X_{k+1}
```

The buyer, seller, Meta-Agent, semantic gate, and Judge may all be implemented
with pretrained models, but this loop does not update their parameters. The
Meta-Agent proposes a discrete textual change; verification measures its effect
on complete host episodes; deterministic code decides whether the proposed
change becomes part of a new immutable Bank version. Later episodes retrieve
from that version, close the feedback loop, and may expose the next residual
failure.

The mechanism therefore contains three separate components:

- Candidate generation transforms experience into a proposed governance change;
- verification estimates the behavioral effect of that change;
- the update rule controls whether accumulated experience changes the active Bank.

Constraint retrieval and semantic activation are the online use of learned
experience. Candidate generation and Bank version updates occur between
episodes. Evaluation episodes never update the Bank being evaluated.

The batch experiment applies the same loop repeatedly. Each derivation episode
runs against the latest frozen version. Episodes with no observed failure do not
create a new version; artifacts distinguish intrinsically safe handling from a
constraint-library intervention. Tactic checkpoint versions are evaluated on
the same held-out attack and benign profiles, producing the library-size growth
curve without learning from evaluation outcomes.

## One learned object

AgenticPay V2 treats each Level 2 constraint as one defensive skill in an
Adaptive Constraint Bank. Detection and correction are not separate skills.
The same record defines when it applies, what principle the proposal must obey,
the control response, and optional revision guidance. The existing hard price
validator stays outside the bank.

The growth experiment learns in ordered tactic checkpoints:

```text
L000 -> privacy phishing -> role hijacking -> time wasting -> final bank
```

Each tactic has disjoint derivation and attack-validation profiles, while all
candidates must also pass benign validation. Evaluation is performed on the
fixed held-out pool at L000 and at the end of each tactic checkpoint, rather
than after every promoted record. Per-tactic metrics expose whether a learned
constraint transfers, remains local, or creates negative transfer.

The batch uses multi-round episodes because time-wasting is a temporal failure.
For every candidate it reruns the same profiles twice: once with the frozen
Parent Bank and once with Parent + Candidate. The fixed promotion rule requires
zero executed Trial violations, more blocked violating proposal steps, at least
one candidate-attributed intercept, no increase in blocked safe proposal steps,
and no decrease in task successes. `REVISE` constraints receive one bounded
regeneration attempt by default; the unsafe original proposal is never
executed.

This conjunction remains available as `--promotion-policy strict`. It is
intentionally conservative but can reject a useful specialized Candidate merely
because a fresh Trial episode contains a different residual violation. It can
also make promotion sensitive to stochastic differences between separately
generated Parent and Trial conversations.

The default `--promotion-policy marginal` instead requires a
Candidate-attributed intercept and positive observed safety gain while enforcing
zero budgets for increases in executed violations, blocked-safe steps, and loss
of valid successes. It does not require the Trial to remove every residual
violation and does not protect unsafe raw task completion. The selected mode,
policy version, and complete parameter set are frozen in `config.json`; the
policy is also recorded when a new Bank version is promoted. This makes the
strict-versus-marginal comparison an explicit update-rule experiment.

The formal batch also reports four arms: no OCL, hard OCL, hard OCL with all
generated constraints added without validation, and hard OCL with only promoted
constraints. The complete AgenticPay Hard Constraint suite is active in all
hard-OCL arms and remains outside the Bank.

## Experiment role

AgenticPay is the short-horizon adversarial negotiation environment. It should
remain a small reference integration for price, privacy, role, and bounded
multi-round interaction attacks.
Long-horizon library growth belongs primarily in CoffeeBench. Evaluation uses
frozen library versions and disjoint derivation, validation, and evaluation
splits as specified by `aocl_core`.
