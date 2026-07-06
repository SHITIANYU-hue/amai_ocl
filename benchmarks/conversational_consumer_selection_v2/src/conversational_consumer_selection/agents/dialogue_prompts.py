"""AgenticPay-style prompts for V2 transaction dialogue agents."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence


def build_buyer_dialogue_prompt(
    *,
    buyer_name: str,
    selection_model: Mapping[str, Any],
    conversation_history: Sequence[Mapping[str, Any]],
    buyer_profile: str = "",
) -> str:
    """Build a buyer prompt with private selection context and hidden action tags.

    Inputs are the buyer identity, private selection model, visible conversation
    history, and optional profile text. The returned prompt asks the buyer LLM
    to emit visible dialogue plus one environment-only action tag.
    """

    return f"""You are {buyer_name}, a buyer shopping for a product through an online clerk.

Context Information:
- private_selection_model:
{_format_json(selection_model)}
- buyer_profile: {buyer_profile or "No additional profile."}

Conversation History:
{_format_history(conversation_history)}

Please respond naturally as {buyer_name} would. Be realistic, consistent with your private selection model, and do not reveal confidential internal details unless you choose to disclose them in normal conversation.

IMPORTANT:
- Your budget, must-have constraints, preferences, patience, and acceptance rule are private buyer information.
- Use the selection model to decide whether to ask follow-up questions, reject a recommendation, or accept a transaction.
- You may reveal some needs naturally, but do not dump the full selection model unless the conversation calls for it.
- If the seller recommends or commits a product that violates your hard constraints, reject it.
- If the product is acceptable under your selection model and you are ready to buy, you may accept.

HIDDEN ACTION FORMAT:
- In each turn, include exactly one hidden action tag at the end of your response:
  ### ENV_ACTION {{"actor":"buyer","type":"...", ...}} ###
- This tag is private to the benchmark environment and will be removed before the seller sees your message.
- Do not refer to the hidden tag in your visible message.
- Valid buyer action types are: ask_more, reveal_need, reject, accept, wait.
- Use reveal_need with slot when you reveal a preference, budget constraint, or must-have.
- Use reject or accept with product_id when responding to a concrete product.
- If you accept the transaction, also include the exact phrase MAKE_DEAL in your visible message.

Examples:
I mostly need these for commuting, so portability matters, but I still need them to be comfortable.
### ENV_ACTION {{"actor":"buyer","type":"reveal_need","slot":"preference.portability","reason":"commuting use case"}} ###

That works for me. It fits what I need, so I am ready to finalize. MAKE_DEAL
### ENV_ACTION {{"actor":"buyer","type":"accept","product_id":"offer_budget","reason":"acceptable under my selection model"}} ###

Now, respond as {buyer_name}:
"""


def build_seller_dialogue_prompt(
    *,
    seller_name: str,
    product_catalog: Sequence[Mapping[str, Any]],
    platform_rules: Mapping[str, Any],
    conversation_history: Sequence[Mapping[str, Any]],
    seller_profile: str = "",
) -> str:
    """Build a seller/clerk prompt with catalog context and hidden action tags.

    Inputs are the seller identity, product catalog, platform rules, visible
    conversation history, and optional profile text. The returned prompt asks
    the seller LLM to emit visible dialogue plus one environment-only action tag.
    """

    return f"""You are {seller_name}, a store clerk helping a buyer choose and purchase a product.

Context Information:
- product_catalog:
{_format_json(list(product_catalog))}
- platform_rules:
{_format_json(platform_rules)}
- seller_profile: {seller_profile or "No additional profile."}

Conversation History:
{_format_history(conversation_history)}

Please respond naturally as {seller_name} would. Be helpful, concise, and guide the buyer from needs clarification to recommendation and, when appropriate, transaction commitment.

IMPORTANT:
- You know product IDs, prices, attributes, stock, and descriptions.
- You do not know the buyer's full private selection model.
- Infer the buyer's needs only from the visible conversation.
- Ask clarifying questions when important buyer constraints are missing.
- Recommend a product only when you have enough information to justify it.
- Commit a transaction only after recommending the same product and after the buyer appears ready.
- Never invent product IDs, prices, attributes, or stock.
- If no product is suitable, say so and escalate/refuse instead of forcing a transaction.

HIDDEN ACTION FORMAT:
- In each turn, include exactly one hidden action tag at the end of your response:
  ### ENV_ACTION {{"actor":"seller","type":"...", ...}} ###
- This tag is private to the benchmark environment and will be removed before the buyer sees your message.
- Do not refer to the hidden tag in your visible message.
- Valid seller action types are: ask_clarification, recommend, commit, escalate, wait.
- Use ask_clarification with slot for missing buyer needs, e.g. budget.max, must_have.noise_cancellation, preference.comfort.
- Use recommend or commit with product_id for a concrete product from the catalog.

Examples:
What matters more for you: battery life or comfort for long sessions?
### ENV_ACTION {{"actor":"seller","type":"ask_clarification","slot":"preference.comfort","reason":"comfort may determine the best product"}} ###

I recommend StudioLite ANC because it stays within your budget and covers the commuting use case well.
### ENV_ACTION {{"actor":"seller","type":"recommend","product_id":"offer_budget","reason":"best fit from the visible needs"}} ###

Now, respond as {seller_name}:
"""


def _format_history(history: Sequence[Mapping[str, Any]]) -> str:
    """Render visible history messages into prompt text."""

    if not history:
        return "No conversation history yet."
    lines = []
    for message in history:
        role = str(message.get("role", "unknown")).upper()
        content = str(message.get("content", ""))
        round_index = message.get("round", "?")
        lines.append(f"[Round {round_index}] {role}: {content}")
    return "\n".join(lines)


def _format_json(value: Any) -> str:
    """Render structured prompt context as deterministic JSON."""

    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
