# ShoppingBench A-OCL Adapter Plan

## Status

The minimal product compatibility probe is implemented. It imports an external
ShoppingBench checkout and exercises the upstream prompt, message parser, tool
dispatcher, and LLM loop against a three-product fixture. It has been exercised
against upstream commit `2f4d132500d4962d7ee3143e103b93499c82aca0`.

The A-OCL runtime interception adapter remains planned. No benchmark code,
dataset, search index, or evaluation logic is vendored here.

## Intended boundary

ShoppingBench is primarily a search-and-recommendation environment rather than
an adversarial negotiation environment. The main controlled action is the final
recommendation:

```text
find_product / view_product_information / web_search
  -> observable evidence

recommend_product
  -> ProposedAction
  -> shared A-OCL decision
  -> native recommendation or blocked/revised result
```

`python_execute`, if enabled, needs a separate code-execution security policy;
it must not be treated as an ordinary shopping recommendation. `terminate` is
normally scheduling rather than an economic commitment.

## Host-owned checks

Candidate deterministic checks include total budget, required item count,
voucher eligibility, same-shop requirements, mandatory attributes, and product
identifier existence. Soft constraints may capture contextual errors such as
excluding shipping from the effective total, optimizing items independently
while violating a bundle constraint, or trusting title keywords over product
specifications.

## Research role

ShoppingBench is a secondary cross-task generalization study, not the primary
evidence for negotiation governance. The main risk is confounding governance
with ordinary recommendation improvement. Experiments must therefore separate:

- hard intent/transaction violations;
- learned defensive constraint activation;
- ordinary search or reasoning accuracy.

Implementation starts only after `aocl_core` and the CoffeeBench adapter have a
stable action/outcome contract. It should add only native mapping, validators,
and a runner; it must reuse the core library, retrieval, evaluator, audit, and
offline learning pipeline.

## First runnable slice

`shoppingbench_ocl.product_probe` answers one deliberately narrow question:
can this repository drive a real ShoppingBench product episode before the
large product corpus is installed? It replaces `find_product` and
`view_product_information` with deterministic fixture data and records
`recommend_product` and `terminate`. Everything that defines the dialogue loop
remains upstream-owned.

This is a compatibility and wiring test, not an A-OCL effectiveness experiment.
The next slice will intercept `recommend_product` immediately before upstream
tool execution, translate it to a shared `ProposedAction`, and return the A-OCL
decision through ShoppingBench's native observation channel.
