# RetailBench OCL Adapter Design

This document records the proposed experiment design for integrating AiMai OCL
with RetailBench.

The RetailBench paper inspected for this design is `arXiv:2603.16453v3`
(`RetailBench: Evaluating Long-Horizon Autonomous Decision-Making and Strategy
Stability of LLM Agents in Realistic Retail Environments`, revised 2026-07-08).
Code and simulator data are now public at
`https://github.com/Ice-Moon-28/RetailBench`. RetailBench remains an external
benchmark and is not vendored into this repository.

Current project status: the execution boundary and V2 runtime are active. The
integration wraps the public `RetailEnvironment.exec_tools` dispatcher, has a
real one-SKU smoke test, and can run RetailBench's upstream LLM loop on a small
three-SKU environment with a fixed Constraint Bank. It also implements a
minimal end-to-end Bank update experiment: derive a candidate from a real
failure, validate Current Bank against Trial Bank on paired risky and benign
scenarios, promote the candidate when safety improves without regression, and
evaluate the resulting Bank on held-out SKUs. Broader long-horizon and
multi-policy experiments remain later phases.

The organizational constraints evaluated here are an explicit
**RetailBench-OCL extension**, not rules supplied by RetailBench. RetailBench
continues to define the economy and native action validity. The extension fixes
a visible policy profile before an experiment and records its identity and
parameters in every run report.

This integration should live under `integrations/` to keep ownership explicit:
RetailBench remains the simulator and benchmark; this package is the OCL
attachment, control, and measurement layer.

## 1. OCL Boundary

AgenticPay tested OCL at a narrow transaction boundary:

```text
LLM proposes economic speech/action.
OCL checks whether price or commitment violates visible constraints.
```

RetailBench extends the same idea to a long-horizon organizational boundary:

```text
LLM proposes long-horizon economic tool action.
OCL checks whether the focal business action violates visible organizational
constraints.
```

RetailBench is the cleanest next step because its simulator already separates
read tools, analysis or memory tools, and state-changing action tools:

```text
LLM proposes a store-management tool action.
OCL audits evidence, validates operational feasibility, maintains store memory,
and optionally blocks or routes unsafe actions before RetailBench executes them.
```

OCL must not rewrite RetailBench's economy:

- do not change demand generation, deliveries, returns, reviews, expiration,
  news effects, rent, cash-flow rules, or hidden simulator fields
- do not expose latent demand, raw supplier quality, hidden news impact, or any
  privileged oracle state to the agent
- do not choose the optimal price, supplier, assortment, or reorder policy in
  validation arms
- only change the focal store agent's tool interface, memory surface, and
  pre-execution checks

## 2. Controlled Operational Surface

RetailBench exposes three tool groups:

```text
read    observable business records
other   memory, constrained analysis, execute_code
act     state-changing retail operations
```

OCL-controlled action tools:

```text
modify_sku_price          pricing commitment
place_order               procurement and inventory commitment
add_note                  cross-day operational memory
```

`end_today` is audited by RetailBench but is temporarily left outside blocking
control because the upstream LLM loop advances its own phase whenever that tool
name is attempted, even if a wrapper returns a blocked result. Controlling the
day transition therefore requires an adapter-owned loop rather than a thin
`exec_tools` proxy.

Tools intentionally left outside blocking control:

```text
view_current_orders
view_sku_sales_history
view_current_date_supplier_prices
view_supplier_price_history
view_inventory
view_funds_and_date
view_sku_prices
view_notes
view_sku_reviews
view_sku_avg_ratings
view_return_rates
view_today_news
view_news_detail
view_news_history
```

These names match the 2026-07-08 public release. That release does not expose
the earlier proposed shelf-assortment or `execute_code` tools. Read-only tools
are observable evidence; warning/blocking targets state-changing actions.

## 3. OCL Runtime

The runtime should attach at the RetailBench tool dispatcher for one focal store
agent.

Minimal runtime responsibilities:

- passive audit of all focal tool calls with day, step, tool name, input, result
  status, and visible state summary
- lifecycle reconstruction across price changes, orders, deliveries, shelf
  updates, stockouts, returns, expirations, reviews, news, and cash events
- read-only OCL memory tools:
  `view_ocl_store_ledger`, `view_ocl_attention_queue`,
  `view_ocl_open_risks`
- warning-mode or blocking-mode validation around action tools
- optional policy-interface tools that replace raw action tools with structured
  operations:
  `draft_retail_plan`, `validate_retail_plan`, `submit_price_changes`,
  `submit_replenishment_plan`, `submit_shelf_plan`, `close_trading_day`

The policy-interface arm should hide:

```text
modify_product_price
place_order
update_shelf_assortment
end_today
```

`write_note` may remain exposed because RetailBench already treats it as a
state-changing cross-day memory action. OCL should still audit it and may limit
note size or reject malformed note payloads.

## 4. Validation Semantics

Validation is limited to visible organizational constraints. It checks whether a
proposed action is well-formed, feasible under visible state, or missing
action-critical evidence. It does not optimize strategy.

The implemented minimal profile (`data/policies/minimal_v1.json`) currently
checks cash reserve, inventory capacity, visible procurement cost, large price
changes, and action-specific evidence. These values are experiment controls,
not claims that RetailBench natively defines the same policy.

Examples of hard errors:

- malformed or non-positive product id, supplier id, quantity, or price
- price update for an unknown product
- order for an unknown product or supplier
- order quantity that exceeds visible cash or remaining inventory capacity
- shelf update that exceeds shelf capacity or includes unknown products
- end-of-day call while required daily operational checks are absent in strict
  interface arms
- duplicate action payloads that conflict within the same day, such as repeated
  shelf replacements with incompatible product sets

Examples of warnings:

- price set below visible procurement cost or to an extreme jump from current
  price
- replenishment without same-day inventory, sales, supplier quote, and quality
  proxy evidence
- price change without same-day current price, cost, inventory, and recent
  sales/profit evidence
- order from the cheapest supplier when visible return/review proxies indicate
  quality risk
- end_today while high-demand stockouts, expiring inventory, or negative cash
  risk are visible and unaddressed
- repeated focus on a narrow product subset while recent stockouts or top-sales
  products have not been revisited

Modes:

```text
audit      no validation shown to the agent; audit/lifecycle only
memory     audit plus read-only OCL memory tools
warning    validation is recorded and attached, but RetailBench still executes
blocking   conservative validation failures are blocked before execution
interface  raw action tools are replaced by structured OCL policy tools
```

## 5. Evidence Control

RetailBench's paper identifies incomplete evidence acquisition as a primary
failure mode. OCL should measure this directly and can expose it as a control
surface.

For each state-changing action, record same-day evidence gathered before the
action:

```text
price action:
  current price, cost/procurement proxy, inventory, recent sales/profit

order action:
  inventory, recent sales, supplier quotes, supplier quality proxy

shelf action:
  inventory, recent sales, stockout history, category coverage

end_today:
  funds, inventory, shelf status, recent sales, pending orders, visible risks
```

In `warning` mode, missing evidence should be attached as warnings. In
`blocking` mode, only block when the missing evidence makes the action obviously
unsafe or malformed. In `interface` mode, structured policy tools can require
the evidence fields explicitly.

## 6. Scientific Arms

The recommended paper-facing ablation ladder is R0-R6:

```text
R0 RetailBench baseline
   Original RetailBench agent setup.

R1 OCL-Audit
   Passive audit and lifecycle reconstruction only.

R2 OCL-Memory
   R1 plus read-only store ledger, attention queue, and open-risk tools.

R3 OCL-Evidence Warning
   R2 plus evidence-completeness warnings before action execution.

R4 OCL-Feasibility Blocking
   R3 with conservative blocking for clearly infeasible actions.

R5 OCL-Policy Interface
   R4 plus structured plan/submit tools replacing raw retail action tools.

R6 OCL-Strategy Rhythm
   R5 plus explicit weekly strategy review and daily execution checklist.
```

R6 is the most scientifically interesting RetailBench-specific arm. It should
not use hidden state or an oracle policy. Its purpose is to test whether OCL can
stabilize long-horizon policy maintenance by forcing a separate cadence for
strategic review, daily evidence collection, execution, and follow-up.

## 7. Metrics

RetailBench-native metrics:

- final net worth and survival days
- final total sales, daily sold products, and return ratio
- stockout days and expired ratio
- direct tool calls per day, total tool calls per day, and tokens per day

OCL control metrics:

- validation counts by status: pass, warning, fail, not_run
- blocked action count and block reason distribution
- controlled action counts by tool
- missing-evidence rate before price, order, shelf, and end-day actions
- warning-to-fix rate: whether the agent repairs an action after a warning
- audit trace completeness

OCL lifecycle and policy metrics:

- product attention coverage and action concentration
- high-demand product follow-up within three and seven days
- unresolved-event rate for stockout, return, expiration, and cash-risk events
- order lifecycle counts: placed, pending, delivered, expired, returned-impact
- shelf churn and category coverage
- weekly strategy revisions and drift from the current strategy memo

## 8. Implementation Plan

Recommended implementation order:

1. Feasibility probe
   Create `retailbench_ocl` as an optional integration package and inspect the
   installed RetailBench module without importing it at repository import time.

2. Passive runtime
   Attach to the RetailBench tool dispatcher and log focal tool calls plus
   simulator day events without changing any result.

3. Store ledger
   Reconstruct visible lifecycle records and expose read-only memory tools for
   funds, inventory, pending orders, shelf, action history, and open risks.

4. Evidence diagnostics
   Compute RetailBench-aligned evidence coverage per action and reproduce the
   paper's stage-level diagnostics from trace logs.

5. Warning validation
   Add warnings for malformed, unsupported, risky, or evidence-thin actions
   while preserving RetailBench execution semantics.

6. Blocking validation
   Block only obviously infeasible actions after warning-mode traces are
   inspected.

7. Policy interface
   Hide raw action tools and expose structured OCL tools that batch price,
   replenishment, shelf, and day-close decisions through explicit evidence
   fields.

8. Full ablation
   Run R0-R6 on fixed RetailBench seeds and compare against the paper's baseline
   agent frameworks and oracle reference where available.

## 9. Run Ladder

Do not start with 180-day paid LLM ablations.

Recommended ladder:

1. `passive`, 3-5 days, one seed.
2. deterministic oracle or heuristic policy, 3-5 days, one seed.
3. R1-R5 with deterministic policy, 10-30 days, one seed.
4. one cheap LLM, R1-R3, 3-5 days, one seed.
5. one cheap LLM, R1-R4, 30 days, one seed.
6. selected LLM arms, 60 days, fixed seed set.
7. selected LLM arms, 180 days, fixed seed set.
8. R0-R6 full comparison only after short-run traces are inspected.

## 10. Known Limits

- The current AiMai core schemas are negotiation-oriented. RetailBench should
  use adapter-local schemas for retail actions rather than forcing everything
  into `proposed_price`.
- Evidence warnings can change agent behavior even when actions are not blocked,
  so R1/R2 should be used to separate audit and memory effects from validation
  effects.
- OCL memory may increase tool-use and token costs; this must be reported
  alongside business metrics.
- Blocking can improve feasibility while hurting exploration or sales volume.
  Block rules should remain conservative and explainable.
- Any strategy-rhythm arm must avoid privileged state; it should enforce
  process discipline, not oracle-like recommendations.
