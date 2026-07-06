# Conversational Consumer Selection V2

`conversational_consumer_selection_v2` is a benchmark module for platform-side
guided selection over a small candidate set.

Within this repository, it serves as a cleaner benchmark for studying
platform-side control when user intent is only partially observable and
decisions unfold over multiple turns. For the overall project context, see the
root [`README.md`](../../README.md).

## Purpose

This benchmark is designed for settings where:

- user intent is incomplete at the beginning of the interaction
- the platform must act over multiple turns
- success depends on both language behavior and decision quality

It is intended as a controlled testbed for studying guided selection under
different intent-visibility regimes rather than as a replacement for real
marketplace logs or online A/B testing.

## Core Contract

The benchmark keeps the platform interface intentionally small:

- input: `Observation`
- output: `SelectionAction`

`Observation` includes:

- `revealed_context`
- `available_clarification_slots`
- `offers`
- `history`
- `turn_index`
- `max_turns`
- `remaining_turns`

`SelectionAction` supports:

- `ask_clarification(slot)`
- `compare_options(offer_id, comparison_offer_id)`
- `recommend_option(offer_id)`
- `commit_selection(offer_id)`
- `escalate()`

Anything richer than that, such as belief state or parser traces, is agent
internal rather than part of the benchmark contract.

## Transaction Dialogue

V2 also supports a dual-agent transaction dialogue layer. In this setting, the
buyer and seller/clerk both produce natural-language messages, but each raw LLM
response also includes one hidden environment action:

```text
Visible message for the other agent.
### ENV_ACTION {"actor":"seller","type":"recommend","product_id":"offer_budget"} ###
```

The environment strips the `ENV_ACTION` tag before adding the message to the
other agent's visible conversation history. The hidden action is recorded only
in the environment event log for validation, metrics, and future control-layer
integration.

The transaction dialogue layer keeps two histories:

- `visible_history`
  buyer/seller-facing natural-language conversation only
- `event_log`
  visible message plus parsed hidden action and validation results

Convergence is detected from actions, not inferred from free text. The minimal
success condition is a seller `commit` for a product followed by a buyer
`accept` for the same product before `max_turns`.

OCL is not instantiated inside the benchmark core. OCL, prompt-policy,
LLM-judge review, and audit/warning/blocking/memory ablations should be
implemented in a separate integration layer that wraps parsed `ENV_ACTION`
events and the benchmark event log.

## Modes

- `v0_structured`
  no dialogue in the contract; the platform acts on structured observations
- `v2_direct_intent`
  dialogue is present and the platform also receives full structured intent
- `v2_partial_intent`
  dialogue is present and the platform receives only partial structured intent
- `v2_hidden_intent`
  dialogue is primary and the environment judges against latent structured
  consumer preferences

## Task Structure

Each task separates:

- `CategorySchema`
  available constraints and preferences for the category
- `UserProfile`
  how the interaction starts
- `LatentConsumerModel`
  the hidden consumer model used by the simulator and the judge

The default examples use a `headphones` category with multiple offers at
different prices and attribute profiles.

## Quick Start

Run the structured demo:

```bash
cd benchmarks/conversational_consumer_selection_v2
PYTHONPATH=src python -m conversational_consumer_selection.clerk_agent_demo --backend demo
```

Run the dialogue demo with a model backend:

```bash
cd benchmarks/conversational_consumer_selection_v2
PYTHONPATH=src python -m conversational_consumer_selection.dialogue_demo \
  --backend openai \
  --model gpt-5.4-mini \
  --reasoning-effort none \
  --mode v2_partial_intent
```

Add `--debug-actions` if you want to inspect the structured control actions.

## Important Files

- [`src/conversational_consumer_selection/schemas.py`](src/conversational_consumer_selection/schemas.py)
  benchmark I/O contract and task structure
- [`src/conversational_consumer_selection/tasks.py`](src/conversational_consumer_selection/tasks.py)
  example task builders
- [`src/conversational_consumer_selection/env.py`](src/conversational_consumer_selection/env.py)
  environment transition and judgment logic
- [`src/conversational_consumer_selection/transaction_env.py`](src/conversational_consumer_selection/transaction_env.py)
  dual-agent transaction dialogue state machine
- [`src/conversational_consumer_selection/dialogue_actions.py`](src/conversational_consumer_selection/dialogue_actions.py)
  hidden `ENV_ACTION` parser and protocol validation
- [`src/conversational_consumer_selection/simulator.py`](src/conversational_consumer_selection/simulator.py)
  rule-based user simulator
- [`src/conversational_consumer_selection/agents/dialogue_prompts.py`](src/conversational_consumer_selection/agents/dialogue_prompts.py)
  AgenticPay-style buyer and seller prompt builders
- [`src/conversational_consumer_selection/agents/clerk_agent.py`](src/conversational_consumer_selection/agents/clerk_agent.py)
  minimal clerk agent
- [`src/conversational_consumer_selection/clerk_agent_demo.py`](src/conversational_consumer_selection/clerk_agent_demo.py)
  `v0_structured` demo entry point
- [`src/conversational_consumer_selection/dialogue_demo.py`](src/conversational_consumer_selection/dialogue_demo.py)
  dialogue demo entry point

## Testing

From the repository root:

```bash
pytest benchmarks/conversational_consumer_selection_v2/tests/test_benchmark.py
```
