"""Buyer/seller agent wrappers for transaction-dialogue runs.

This module intentionally keeps buyer and seller models separate. A benchmark
run may configure both sides to use the same provider/model name, but the API
does not assume that. Each side owns its own model object, role prompt, private
context, and generation call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from conversational_consumer_selection.agents.dialogue_prompts import (
    build_buyer_dialogue_prompt,
    build_seller_dialogue_prompt,
)
from conversational_consumer_selection.dialogue_actions import DialogueActor
from conversational_consumer_selection.schemas import Offer, SelectionTask
from conversational_consumer_selection.transaction_env import TransactionDialogueEnv


class TransactionDialogueModel(Protocol):
    """Minimal text-generation interface for one dialogue participant."""

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return one raw dialogue message including its hidden ENV_ACTION tag."""


@dataclass
class BuyerDialogueAgent:
    """LLM-backed buyer participant with private selection-model context."""

    model: TransactionDialogueModel
    buyer_name: str = "Buyer"
    buyer_profile: str = ""
    selection_model: Mapping[str, Any] | None = None

    def act(
        self,
        *,
        task: SelectionTask,
        conversation_history: Sequence[Mapping[str, Any]],
    ) -> str:
        """Generate one raw buyer message for the transaction environment.

        Inputs are the benchmark task and visible conversation history. The
        output is raw model text containing visible buyer dialogue plus exactly
        one hidden buyer `ENV_ACTION` tag.
        """

        user_prompt = build_buyer_dialogue_prompt(
            buyer_name=self.buyer_name,
            selection_model=dict(self.selection_model or _default_selection_model(task)),
            conversation_history=conversation_history,
            buyer_profile=self.buyer_profile,
        )
        return self.model.generate(
            system_prompt=(
                "You are the buyer-side model in a two-agent transaction-dialogue "
                "benchmark. Follow the buyer prompt and emit exactly one hidden "
                "buyer ENV_ACTION tag."
            ),
            user_prompt=user_prompt,
        )


@dataclass
class SellerDialogueAgent:
    """LLM-backed seller/clerk participant with catalog and rule context."""

    model: TransactionDialogueModel
    seller_name: str = "Clerk"
    seller_profile: str = ""
    product_catalog: Sequence[Mapping[str, Any]] | None = None
    platform_rules: Mapping[str, Any] | None = None

    def act(
        self,
        *,
        task: SelectionTask,
        conversation_history: Sequence[Mapping[str, Any]],
    ) -> str:
        """Generate one raw seller message for the transaction environment.

        Inputs are the benchmark task and visible conversation history. The
        output is raw model text containing visible seller dialogue plus exactly
        one hidden seller `ENV_ACTION` tag.
        """

        user_prompt = build_seller_dialogue_prompt(
            seller_name=self.seller_name,
            product_catalog=list(self.product_catalog or _default_product_catalog(task.offers)),
            platform_rules=dict(self.platform_rules or _default_platform_rules(task)),
            conversation_history=conversation_history,
            seller_profile=self.seller_profile,
        )
        return self.model.generate(
            system_prompt=(
                "You are the seller-side model in a two-agent transaction-dialogue "
                "benchmark. Follow the seller prompt and emit exactly one hidden "
                "seller ENV_ACTION tag."
            ),
            user_prompt=user_prompt,
        )


def run_transaction_dialogue(
    *,
    task: SelectionTask,
    buyer_agent: BuyerDialogueAgent,
    seller_agent: SellerDialogueAgent,
    first_actor: DialogueActor | str = DialogueActor.BUYER,
) -> dict[str, Any]:
    """Run buyer and seller agents until success, escalation, or timeout.

    Inputs are one task plus independently configured buyer and seller agents.
    The returned dictionary is `TransactionDialogueEnv.summary()` after the
    dialogue terminates or reaches the task turn budget.
    """

    env = TransactionDialogueEnv(task=task)
    current_actor = DialogueActor(first_actor)
    while not env.state.terminated:
        history = tuple(env.state.visible_history)
        if current_actor is DialogueActor.BUYER:
            raw_output = buyer_agent.act(task=task, conversation_history=history)
        else:
            raw_output = seller_agent.act(task=task, conversation_history=history)
        env.process_turn(actor=current_actor, raw_output=raw_output)
        current_actor = (
            DialogueActor.SELLER
            if current_actor is DialogueActor.BUYER
            else DialogueActor.BUYER
        )
    return env.summary()


def _default_selection_model(task: SelectionTask) -> dict[str, Any]:
    """Build the buyer-private selection model from a benchmark task."""

    return {
        "category": task.user_goal.category,
        "budget_max": task.user_goal.budget_max,
        "must_have": dict(task.user_goal.must_have),
        "preference_weights": dict(task.preference_weights),
        "price_sensitivity": task.price_sensitivity,
        "outside_option_threshold": task.outside_option_threshold,
        "turn_penalty": task.turn_penalty,
    }


def _default_product_catalog(offers: Sequence[Offer]) -> list[dict[str, Any]]:
    """Serialize task offers into seller-visible product catalog entries."""

    return [
        {
            "offer_id": offer.offer_id,
            "title": offer.title,
            "category": offer.category,
            "price": offer.price,
            "features": dict(offer.features),
            "attribute_values": dict(offer.attribute_values),
        }
        for offer in offers
    ]


def _default_platform_rules(task: SelectionTask) -> dict[str, Any]:
    """Build seller-visible protocol rules for the transaction dialogue."""

    return {
        "valid_product_ids": [offer.offer_id for offer in task.offers],
        "valid_clarification_slots": list(task.available_clarification_slots),
        "commit_requires_prior_recommend": True,
        "buyer_acceptance_required_for_success": True,
    }
