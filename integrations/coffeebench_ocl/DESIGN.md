# CoffeeBench OCL Adapter Design

This document records the current experiment design for integrating AiMai OCL
with the official CoffeeBench benchmark.

The upstream CoffeeBench code inspected for this design was
`SakanaAI/CoffeeBench` at commit `71442fb`. CoffeeBench is treated as an
external benchmark, not vendored into this repository.

This integration lives under `integrations/` to make the ownership boundary
explicit: CoffeeBench remains the benchmark; this package is the OCL attachment
and measurement layer.

## 1. OCL Boundary

AgenticPay used OCL at a narrow transaction boundary:

```text
LLM proposes economic speech/action.
OCL checks whether price or commitment violates visible constraints.
```

CoffeeBench extends the same idea to organizational operations:

```text
LLM proposes long-horizon economic tool action.
OCL checks whether procurement, sales, settlement, or production violates
visible organizational constraints.
```

OCL is not modeled as a wall between sellers and buyers. It is an
organization-side control layer for one focal business. For this benchmark the
default focal business is `roaster_A`.

The adapter must not rewrite CoffeeBench's economy:

- do not change demand, spoilage, delivery loss/delay, invoice issue, late
  fees, returns, bankruptcy, or truth-ledger mechanics
- do not change background agents
- do not recommend supplier, price, production, or inventory strategy
- only change the focal agent's tool interface and pre-execution checks

## 2. Controlled Operational Surface

CoffeeBench exposes a `BusinessApp` tool layer. OCL attaches there.

OCL-controlled operational actions:

```text
post_listing      sales commitment
make_offer        procurement commitment
withdraw_offer    procurement commitment cancellation
accept_offer      sales acceptance / binding deal
pay_invoice       settlement
return_shipment   settlement reversal / goods return
roast             production
```

Tools intentionally left outside OCL control:

```text
view_listings
view_offers
view_deals
view_messages
view_payables
view_receivables
view_trial_balance
view_market_aggregate
send_message
read_message
wait_for_next_day
```

Read-only views and messages are observable context, not controlled economic
execution. `wait_for_next_day` is a benchmark scheduling tool, not an
organizational commitment.

## 3. Implemented Runtime

The current runtime supports:

- passive audit of focal CoffeeBench tool calls and selected native events
- lifecycle reconstruction across offer, deal, delivery, invoice, payment,
  return, shipment delay, and shipment loss
- read-only OCL memory tools:
  `view_ocl_ledger`, `view_ocl_obligations`
- warning-mode or blocking-mode validation around operational tools
- contract-interface tools:
  `draft_purchase_contract`, `validate_contract`,
  `submit_contract_offer`, `withdraw_contract_offer`, `accept_contract_offer`,
  `settle_due_contract`, `return_contract_shipment`
- hiding raw focal trade tools in the contract-interface arm
- DashScope/Qwen model ids through an adapter-local provider, without patching
  the installed CoffeeBench package

The contract-interface arm hides:

```text
make_offer
withdraw_offer
accept_offer
pay_invoice
return_shipment
```

`post_listing` and `roast` keep their CoffeeBench names because there is not yet
a separate sale-side or production-planning contract interface. They are still
wrapped by OCL validation.

## 4. Model Providers

CoffeeBench's upstream model registry does not natively recognize Alibaba Qwen
model ids. This adapter installs a small runtime registry patch before
`build_run()`, so model ids such as `qwen-plus`, `qwen3-max`,
`qwen/qwen-plus`, and `dashscope/qwen-plus` use DashScope's
OpenAI-compatible Chat Completions API.

Required environment:

```text
DASHSCOPE_API_KEY=...
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

`DASHSCOPE_BASE_URL` is intentionally configurable because Aliyun keys may be
bound to a China-region, international-region, or workspace-specific endpoint.
Token counts are tracked. USD cost is reported as zero unless these optional
rates are set:

```text
DASHSCOPE_INPUT_USD_PER_MTOK
DASHSCOPE_CACHED_INPUT_USD_PER_MTOK
DASHSCOPE_OUTPUT_USD_PER_MTOK
```

## 5. Validation Semantics

Validation is limited to visible organizational constraints. It checks whether a
proposed action is feasible or violates an obvious operating constraint. It does
not choose the best supplier, price, listing strategy, production schedule, or
inventory policy.

Examples of checks:

- malformed or non-positive quantity, price, or payment terms
- self-dealing against the focal agent's own listing
- withdrawing an offer the focal agent does not own or that is no longer pending
- listing more goods than on-hand inventory
- accepting an offer without enough inventory
- paying an invoice that is missing, already paid, returned, or unaffordable
- returning more than the remaining returnable quantity
- returning outside CoffeeBench's return window
- roasting without green inventory, cash for labor, valid recipe, or daily
  roasting capacity
- adding inbound commitments beyond inventory cap
- warning when open payables are overdue

Modes:

```text
audit      no validation shown to the agent; audit/lifecycle only
warning    validation is recorded and attached, but CoffeeBench still executes
blocking   validation failures are blocked before CoffeeBench execution
```

## 6. Scientific Arms

The experiment design is the B0-B5 capability ladder:

```text
B0 CoffeeBench baseline
   Original CoffeeBench focal roaster setup.

B1 OCL-Audit
   Passive audit and lifecycle reconstruction only.

B2 OCL-Memory
   B1 plus read-only ledger and obligation tools.

B3 OCL-Warning
   B2 plus warning-mode validation around operational actions.

B4 OCL-Blocking
   B3 with conservative blocking for clearly infeasible actions.

B5 OCL-Contract Interface
   B4 plus OCL contract tools replacing raw focal trade tools.
```

This ladder is the paper-facing ablation surface. Numeric phases in the code are
implementation milestones and compatibility names only.

## 7. Metrics

CoffeeBench-native metrics:

- focal net income, revenue, cash, inventory value, AP, and AR
- bad debt, returns, late fees, and bankruptcy/early termination
- tool calls, model calls, tokens, and API cost
- marketplace deals, listings, offers, and messages

OCL lifecycle metrics:

- contracts created, offered, accepted, delivered, invoiced, paid, closed
- contracts returned, delayed, lost, defaulted, invalid, or cancelled
- offer/deal/invoice link counts

OCL control metrics:

- validation counts by status: pass, warning, fail, not_run
- blocked action count
- controlled tool-call counts
- invalid action rate
- warning and blocking reasons
- audit trace completeness

Settlement metrics:

- unpaid invoice count
- overdue invoice count
- average days late
- settlement latency
- late fees paid/accrued
- bad debt amount

## 8. Run Ladder

Do not start with 90-day real-model ablations.

Recommended ladder:

1. `passive`, 3-5 days, one seed.
2. `heuristic_roaster`, 3-5 days, one seed.
3. B1-B5, `heuristic_roaster`, 3-5 days, one seed.
4. B1-B5, `heuristic_roaster`, 30 days, one seed.
5. one cheap LLM, B1-B3, 3-5 days, one seed.
6. selected LLM arms, 30 days, one seed.
7. selected LLM arms, 90 days, fixed seed set.
8. full B0-B5 only after short-run traces are inspected.

## 9. Known Limits

- B5 replaces raw focal trade tools for offer, withdrawal, acceptance,
  settlement, and return, but `post_listing` and `roast` are still native-name
  tools wrapped by validation.
- DashScope/Qwen cost accounting needs explicit local per-token rate
  environment variables; otherwise token counts are tracked but cost is `0`.
- Validation is conservative and rule-based; it is not yet calibrated on many
  invalid LLM traces.
- The default no-cost `heuristic_roaster` may produce few trade events in short
  runs, so validation behavior is covered by unit tests and must be stress
  tested with LLM traces.
- Contract IDs are reconciled from CoffeeBench offer/deal/invoice IDs because
  CoffeeBench issues invoices after delivery.
- This adapter currently controls one focal business at a time.
