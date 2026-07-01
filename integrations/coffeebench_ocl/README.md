# CoffeeBench OCL Adapter

`coffeebench_ocl` is an adapter layer for testing AiMai's organization control
layer on the official CoffeeBench benchmark. It is not a CoffeeBench fork and
does not reimplement the benchmark.

CoffeeBench stays an external dependency owned by its upstream repository. This
package attaches to the focal agent's CoffeeBench `BusinessApp` tool boundary;
it does not rewrite CoffeeBench's marketplace, accounting, delivery, demand, or
truth-ledger mechanics.

## Principle

AgenticPay tested OCL at the transaction boundary:

```text
LLM proposes economic speech/action.
OCL checks whether price or commitment violates visible constraints.
```

CoffeeBench tests the extension to the operational boundary:

```text
LLM proposes long-horizon economic tool action.
OCL checks whether procurement, sales, settlement, or production violates
visible organizational constraints.
```

OCL is not a wall between buyer and seller. It is an organization-side
execution boundary for the focal business (`roaster_A` by default).

## Current Scope

- focal agent: `roaster_A`
- focal role: `roaster`
- OCL-controlled operational tools:
  `post_listing`, `make_offer`, `withdraw_offer`, `accept_offer`, `pay_invoice`,
  `return_shipment`, `roast`
- native tools left outside OCL control:
  `view_*`, `send_message`, `read_message`, `wait_for_next_day`

The contract-interface arm hides the raw focal trade tools
`make_offer`, `withdraw_offer`, `accept_offer`, `pay_invoice`, and
`return_shipment`.
`post_listing` and `roast` keep their CoffeeBench names but are still checked by
OCL validation.

## Experiment Arms

The scientific comparison surface is B0-B5:

```text
B0 CoffeeBench baseline
   Original CoffeeBench focal roaster setup.

B1 OCL-Audit
   Passive audit and lifecycle reconstruction.

B2 OCL-Memory
   B1 plus read-only OCL ledger and obligation tools.

B3 OCL-Warning
   B2 plus warning-mode validation around operational actions.

B4 OCL-Blocking
   B3 with conservative blocking for clearly infeasible actions.

B5 OCL-Contract Interface
   B4 plus OCL contract tools replacing raw focal trade tools.
```

Numeric phases in the code are implementation milestones retained for
backwards compatibility. They are not the experiment taxonomy.

## Run

Check that CoffeeBench is importable and exposes the expected focal tools:

```bash
PYTHONPATH=integrations/coffeebench_ocl/src python -m coffeebench_ocl.phase0_probe
```

Smoke run with no paid model calls:

```bash
PYTHONPATH=integrations/coffeebench_ocl/src python -m coffeebench_ocl.phase1 \
  --arm B3 \
  --model passive \
  --models roaster_A:heuristic_roaster \
  --max-days 3 \
  --output-dir outputs/coffeebench_ocl/b3_smoke
```

The runner suppresses CoffeeBench's verbose native stdout by default and prints
a compact JSON summary. Add `--verbose` when debugging upstream CoffeeBench
events or provider calls.

DashScope/Qwen smoke run, using a China-region OpenAI-compatible endpoint:

```bash
PYTHONPATH=integrations/coffeebench_ocl/src python -m coffeebench_ocl.phase1 \
  --arm B3 \
  --model passive \
  --models roaster_A:qwen-plus \
  --max-days 1 \
  --output-dir outputs/coffeebench_ocl/qwen_cn_quick
```

Required local environment:

```text
DASHSCOPE_API_KEY=...
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

If your Aliyun key is bound to a specific workspace or region, use the exact
compatible-mode endpoint shown in that console. The adapter also accepts
`qwen/qwen-plus`, `dashscope/qwen-plus`, and `qwen-plus-no-thinking`.

Outputs:

- `run.json`
- `run.events.jsonl`
- `run.ocl.jsonl`
- `run.ocl.contracts.json`
- `run.ocl.summary.json`
- `run_report.json`
- `phase1_report.json` compatibility copy

## Files

- [`DESIGN.md`](DESIGN.md)
  experiment design and integration protocol
- [`src/coffeebench_ocl/runtime.py`](src/coffeebench_ocl/runtime.py)
  runtime attachment for B0-B5 capability arms
- [`src/coffeebench_ocl/validation.py`](src/coffeebench_ocl/validation.py)
  organizational feasibility checks
- [`src/coffeebench_ocl/audit.py`](src/coffeebench_ocl/audit.py)
  append-only OCL audit logger
- [`src/coffeebench_ocl/lifecycle.py`](src/coffeebench_ocl/lifecycle.py)
  lifecycle reconstruction from CoffeeBench events and tool calls
- [`src/coffeebench_ocl/phases.py`](src/coffeebench_ocl/phases.py)
  B0-B5 capability arms and legacy implementation milestones
- [`src/coffeebench_ocl/qwen_model.py`](src/coffeebench_ocl/qwen_model.py)
  DashScope/Qwen OpenAI-compatible provider
- [`src/coffeebench_ocl/tooling.py`](src/coffeebench_ocl/tooling.py)
  focal tool exposure plan

## Testing

From the repository root:

```bash
PYTHONPATH=integrations/coffeebench_ocl/src pytest -q integrations/coffeebench_ocl/tests
```
