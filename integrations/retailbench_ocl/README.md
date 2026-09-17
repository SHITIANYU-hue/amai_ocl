# RetailBench OCL

This integration wraps RetailBench's real `RetailEnvironment.exec_tools`
boundary. RetailBench remains an external checkout; this repository contains
the OCL adapter, V2 runtime configuration, and short-run experiment entry point.

## What is added to RetailBench

RetailBench supplies the economy, tools, and native feasibility checks. This
integration adds a separate organizational policy profile; its rules are not
presented as native RetailBench constraints. The default profile is
`data/policies/minimal_v1.json` and currently declares:

- evidence required before procurement and pricing actions
- a three-day rent reserve after procurement
- an inventory-capacity limit that also counts pending stock
- a selling-price floor based on visible current procurement quotes
- a warning threshold for price changes larger than 50 percent

The values are fixed experiment settings, not an optimal retail strategy. Use
`--policy` to select the exact profile and retain it with every result.

## Minimal run

RetailBench currently requires Python 3.10 or newer and contains Git LFS files
under `paper_data/`. The simulator data used here is stored in ordinary Git.
If Git LFS is unavailable, clone while skipping only LFS material:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/Ice-Moon-28/RetailBench.git /tmp/RetailBench
git -C /tmp/RetailBench sparse-checkout set --no-cone \
  /retail_environment.py /requirements.txt /model/ /module/ /util/ \
  /data/dynamic/customer_number/15/data.json \
  /data/dynamic/simulate_data/15/sku_model_parameter.json \
  /data/dynamic/simulate_data/15/upc.json \
  /data/dynamic/simulate_data/15/Bathroom_Tissues/3828111129_suppliers.json
```

Install the shared core and this adapter:

```bash
python -m pip install -r /tmp/RetailBench/requirements.txt
python -m pip install -e integrations/aocl_core \
  -e integrations/retailbench_ocl
```

Run the real one-SKU smoke test:

```bash
PYTHONPATH=integrations/aocl_core/src:integrations/retailbench_ocl/src \
python -m retailbench_ocl.smoke --retailbench-root /tmp/RetailBench
```

Success means the same proposed order is first blocked for missing observable
evidence, then executed by RetailBench after the adapter observes inventory,
funds, sales, and supplier-price evidence. The command performs no LLM call and
no long-horizon simulation; it validates only the host integration boundary.

## Short real-LLM V2 run

The V2 runner uses RetailBench's upstream `run_exec_strategy_env` agent loop.
It restricts the simulator to three public SKUs, freezes one Constraint Bank
snapshot for the run, and routes every state-changing tool call through:

```text
RetailBench LLM -> Hard Constraints -> Constraint Bank -> OCL decision
                -> RetailBench exec_tools -> audit trace
```

Check paths and Bank loading without making an LLM call:

```bash
PYTHONPATH=integrations/aocl_core/src:integrations/retailbench_ocl/src \
python -m retailbench_ocl.run_v2 \
  --retailbench-root /tmp/RetailBench \
  --constraint-bank integrations/retailbench_ocl/data/constraint_banks/L000 \
  --policy integrations/retailbench_ocl/data/policies/minimal_v1.json \
  --check-only
```

Run ten days with Qwen through DashScope:

```bash
export DASHSCOPE_API_KEY=...

PYTHONPATH=integrations/aocl_core/src:integrations/retailbench_ocl/src \
python -m retailbench_ocl.run_v2 \
  --retailbench-root /tmp/RetailBench \
  --model qwen-plus \
  --constraint-bank integrations/retailbench_ocl/data/constraint_banks/L000 \
  --policy integrations/retailbench_ocl/data/policies/minimal_v1.json \
  --max-days 10 \
  --sku-count 3
```

Omit `--constraint-bank` to start with an empty Bank. Use
`--evaluator lexical` only for deterministic debugging; the default semantic
mode makes a separate LLM call when a retrieved constraint must be evaluated.
The run writes RetailBench messages, OCL audit events, checkpoints, a shared-V2
`learning_trace.json`, and a compact `report.json` under
`outputs/retailbench_ocl/v2_short/`. It also writes `policy_feedback.json`,
whose reference labels come only from reproducible hard, evidence, and declared
organizational-policy checks. Constraint Bank activations do not label their
own correctness. Use `--split derivation`, `validation`, or `evaluation` to
label the trace for the later learning protocol.

The Bank is not rewritten during a run. Candidate derivation and paired
Current-Bank/Trial-Bank validation happen between runs, using
`retailbench_promotion_policy("marginal")` or the stricter ablation policy.

## Minimal Constraint Bank learning experiment

The bank experiment runs the complete update path with a real RetailBench
environment and a real LLM. It starts from an empty Bank, derives a candidate
from a duplicate-purchase failure, compares the current and trial Banks on one
risky and one benign validation scenario, and evaluates an approved Bank on
held-out SKUs. The primary experiment has no Bank-size limit.

```bash
export DASHSCOPE_API_KEY=...

PYTHONUNBUFFERED=1 \
PYTHONPATH=integrations/aocl_core/src:integrations/retailbench_ocl/src \
python -m retailbench_ocl.bank_experiment \
  --retailbench-root /tmp/RetailBench \
  --policy integrations/retailbench_ocl/data/policies/minimal_v1.json \
  --model qwen-plus \
  --max-turns-per-day 8
```

Each run writes the candidate, paired-validation report, promotion decision,
immutable Bank snapshots, episode traces, and final evaluation report under
`outputs/retailbench_ocl/bank_experiment/`.

In the 2026-09-16 pilot, the LLM derived a rule against ordering a SKU that
already had an undelivered order. Paired validation approved the candidate:
executed violations fell from 1 to 0, valid successes rose from 1/2 to 2/2,
and benign false blocks remained 0. The same result held on two held-out SKU
scenarios. This is a mechanism check on a deliberately small sample, not a
statistical benchmark result.

## Attach to an existing runner

```python
from retailbench_ocl import RetailBenchOCL

env = RetailEnvironment(config)
env = RetailBenchOCL(env, episode_id="experiment-001")

# Existing agent code remains unchanged:
result = env.exec_tools(tool_name, **tool_args)
```

The default policy requires same-day supplier-price, inventory, funds, and
sales evidence before `place_order`, and current-price, inventory, sales, and
supplier-price evidence before `modify_sku_price`. Read tools are never blocked.
Deterministic Hard Constraints also reject malformed orders, non-positive
prices, and empty notes before RetailBench sees them.

## Experiment protocol

Keep RetailBench's simulator and native metrics unchanged, and compare:

1. upstream RetailBench with no OCL control
2. declared Hard Constraints and evidence policy only
3. the same policy plus a fixed Constraint Bank
4. the same policy plus a Bank learned on derivation runs and selected on
   separate validation runs

Only the fourth arm updates the Bank. Freeze the selected Bank snapshot before
evaluation. Report RetailBench outcomes together with executed policy
violations, blocked policy violations, and interventions without a reference
policy violation. This separates economic performance from governance quality.

The primary experiment leaves Bank capacity unlimited. A separate maintenance
experiment may set a finite `max_active_constraints` and compare verified
retirement or replacement. Reaching the limit starts paired removal validation;
it does not authorize FIFO, least-recently-used, or unverified deletion.

The upstream execution loop treats any attempted `end_today` call as a completed
day without checking the returned tool result. Until that upstream lifecycle
assumption is replaced by an adapter-owned loop, `end_today` remains a native
RetailBench call rather than a blocking OCL action.
