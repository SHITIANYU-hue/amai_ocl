# AiMai OCL

`aimai_ocl` is a research codebase for studying Organizational Control Layers
(OCLs) in multi-agent economic systems.

The repository explores how an explicit control layer can improve reliability,
constraint satisfaction, and decision quality in language-agent workflows. The
current setting uses AgenticPay as an external negotiation substrate and adds a
control plane for role decomposition, risk gating, auditability, escalation,
and attribution.

## Overview

This repository focuses on three questions:

- How should raw language actions be mapped into executable economic actions?
- When should a system approve, rewrite, block, or escalate an agent action?
- How can platform-side control be evaluated under partial observability and
  multi-turn interaction?

The current public codebase includes:

- an OCL implementation in [`aimai_ocl`](aimai_ocl)
- experiment scripts in [`scripts`](scripts)
- a local benchmark module in
  [`benchmarks/conversational_consumer_selection_v2`](benchmarks/conversational_consumer_selection_v2)
- tests in [`tests`](tests)

## Main Components

- `Role decomposition`
  separates planning, execution, and escalation responsibilities
- `Risk gating`
  scores candidate actions and chooses approve, rewrite, block, or escalate
- `Audit traces`
  records structured control decisions for later analysis
- `Escalation and replanning`
  handles infeasible or high-risk actions
- `Attribution`
  supports post-hoc contribution analysis across algorithmic components

## Research Setting

The repository currently uses two benchmark layers:

- `AgenticPay`
  is treated as an external negotiation/runtime substrate
- `Conversational Consumer Selection V2`
  is a local benchmark for controlled guided selection and dual-agent
  transaction dialogue under incomplete buyer intent

The benchmark module is documented in
[`benchmarks/conversational_consumer_selection_v2/README.md`](benchmarks/conversational_consumer_selection_v2/README.md).
It preserves the original guided-selection interface:

- input: `Observation`
- output: `SelectionAction`

and also adds a transaction dialogue layer where buyer and seller/clerk LLMs
exchange visible messages while hidden `ENV_ACTION` tags are stripped before
the other agent sees them and recorded in an environment event log.

The benchmark core does not instantiate OCL. OCL, prompt-policy, judge-review,
and ablation arms belong in an integration layer that wraps the benchmark's
parsed actions and event log.

The benchmark supports four visibility regimes:

- `v0_structured`
- `v2_direct_intent`
- `v2_partial_intent`
- `v2_hidden_intent`

## Repository Layout

```text
aimai_ocl/
  controllers/    role, gate, audit, escalation, control surface
  runners/        clerk-agent and OCL execution paths
  adapters/       AgenticPay integration
  schemas/        action, audit, and constraint schemas
scripts/
  run_demo.py
  run_batch_eval.py
  run_ablation_matrix.py
  run_tau_sweep.py
benchmarks/conversational_consumer_selection_v2/
  src/conversational_consumer_selection/
  tests/
tests/
```

## Installation

Create a Python environment and install the project:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Install AgenticPay separately as an external dependency:

```bash
pip install "git+https://github.com/SafeRL-Lab/AgenticPay.git"
```

If you want to run the guided-selection benchmark as a package, also install:

```bash
pip install -e benchmarks/conversational_consumer_selection_v2
```

For OpenAI-backed runs, set:

```bash
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-5.4-mini
```

## Quick Start

Run one negotiation episode:

```bash
python scripts/run_demo.py --arm ocl_full --model gpt-5.4-mini --seed 42
```

Run a paired batch evaluation:

```bash
python scripts/run_batch_eval.py \
  --arms single,ocl_full \
  --episodes-per-arm 20 \
  --seed-base 42 \
  --output-dir outputs/main_result_v2
```

Run a `tau` sweep over control strength:

```bash
python scripts/run_tau_sweep.py \
  --tau-values 0.0,0.25,0.5,0.75,1.0 \
  --episodes-per-arm 20 \
  --seed-base 42 \
  --output-root outputs/tau_sweep_v2
```

Run the guided-selection benchmark demo:

```bash
cd benchmarks/conversational_consumer_selection_v2
PYTHONPATH=src python -m conversational_consumer_selection.clerk_agent_demo --backend demo
```

## Key Files

- [`aimai_ocl/controllers/ocl_controller.py`](aimai_ocl/controllers/ocl_controller.py)
  main OCL control path
- [`aimai_ocl/controllers/risk_gate.py`](aimai_ocl/controllers/risk_gate.py)
  risk-gating algorithms including the `tau`-controlled family
- [`aimai_ocl/controllers/coordinator.py`](aimai_ocl/controllers/coordinator.py)
  role-decomposition logic
- [`aimai_ocl/evaluation_metrics.py`](aimai_ocl/evaluation_metrics.py)
  experiment metrics and summary fields
- [`aimai_ocl/plugin_registry.py`](aimai_ocl/plugin_registry.py)
  algorithm registries and experiment composition
- [`benchmarks/conversational_consumer_selection_v2/src/conversational_consumer_selection/env.py`](benchmarks/conversational_consumer_selection_v2/src/conversational_consumer_selection/env.py)
  guided-selection environment
- [`benchmarks/conversational_consumer_selection_v2/src/conversational_consumer_selection/transaction_env.py`](benchmarks/conversational_consumer_selection_v2/src/conversational_consumer_selection/transaction_env.py)
  dual-agent transaction dialogue environment
- [`benchmarks/conversational_consumer_selection_v2/src/conversational_consumer_selection/dialogue_actions.py`](benchmarks/conversational_consumer_selection_v2/src/conversational_consumer_selection/dialogue_actions.py)
  hidden `ENV_ACTION` parser and protocol checks
- [`benchmarks/conversational_consumer_selection_v2/src/conversational_consumer_selection/schemas.py`](benchmarks/conversational_consumer_selection_v2/src/conversational_consumer_selection/schemas.py)
  benchmark I/O contract

## Testing

Run the main test suite:

```bash
pytest
```

Run the benchmark-specific tests:

```bash
pytest benchmarks/conversational_consumer_selection_v2/tests/test_benchmark.py
```

## Status

This is an active research repository. Interfaces and experiment settings may
still evolve as the paper implementation is refined.

## Citation

If you find this work useful, please consider citing:

```bibtex
@misc{shi2026organizationalcontrol,
  title        = {Organizational Control Layer: Governance Infrastructure at the Execution Boundary of LLM Agent Systems},
  author       = {Shi, Tianyu and Mo, Yang and Liu, Yiou and Hao, Zhuonan and Wang, Yin and Hu, Wenzhuo and Yu, Nan and Zhou, Meng and Yu, Jiangbo},
  year         = {2026},
  eprint       = {2606.04306},
  archivePrefix = {arXiv},
  primaryClass = {cs.MA},
  url          = {https://arxiv.org/abs/2606.04306}
}
```
