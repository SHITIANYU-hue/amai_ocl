# ShoppingBench A-OCL Adapter

This directory now contains a minimal product compatibility probe. The probe
runs a real LLM episode through ShoppingBench's own prompt, message parser,
tool dispatcher, and ReAct loop. Product search is replaced with three small
in-memory records, so this first check does **not** require the full product
dataset, Pyserini index, or local search server.

ShoppingBench remains an external dependency: its source and data are not
copied into this repository. The A-OCL interception adapter itself is still the
next step; see [`DESIGN.md`](DESIGN.md) for that boundary.

## Minimal setup

Fetch only the upstream files needed by the probe:

```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/yjwjy/ShoppingBench.git /path/to/ShoppingBench
git -C /path/to/ShoppingBench sparse-checkout set src/agent config
```

Install the shared core and this integration:

```bash
python -m pip install -e integrations/aocl_core \
  -e integrations/shoppingbench_ocl
```

Check that the selected upstream revision still exposes the expected product
tools, without calling an LLM:

```bash
aimai-shoppingbench-product-probe \
  --shoppingbench-root /path/to/ShoppingBench \
  --check-only
```

Then run one real product dialogue (requires `OPENAI_API_KEY`):

```bash
aimai-shoppingbench-product-probe \
  --shoppingbench-root /path/to/ShoppingBench \
  --model gpt-4o-mini
```

The live probe succeeds only when the official loop recommends
`red-runner-001`, the sole fixture item satisfying all query requirements. It
writes the upstream commit, dialogue trajectory, tool calls, and compact report
under `outputs/shoppingbench_ocl/product_probe/`.
