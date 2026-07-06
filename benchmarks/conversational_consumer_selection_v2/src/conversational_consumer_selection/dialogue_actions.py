"""Dual-channel dialogue actions for the transaction benchmark.

LLM agents emit one buyer/seller-facing message plus one hidden ENV_ACTION tag.
The visible message is shown to the other agent; the parsed action is only for
the benchmark environment, metrics, and future control layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import re
from typing import Any, Mapping

from conversational_consumer_selection.schemas import (
    CLARIFICATION_BUDGET_MAX,
    CLARIFICATION_MUST_HAVE_PREFIX,
    CLARIFICATION_PREFERENCE_PREFIX,
    normalize_clarification_slot,
    SelectionTask,
)


ENV_ACTION_PATTERN = re.compile(r"###\s*ENV_ACTION\s*(\{.*?\})\s*###", re.DOTALL)


class DialogueActor(str, Enum):
    """Agents that can produce transaction dialogue actions."""

    BUYER = "buyer"
    SELLER = "seller"


class BuyerDialogueActionType(str, Enum):
    """Buyer-side hidden action labels."""

    ASK_MORE = "ask_more"
    REVEAL_NEED = "reveal_need"
    REJECT = "reject"
    ACCEPT = "accept"
    WAIT = "wait"


class SellerDialogueActionType(str, Enum):
    """Seller/clerk-side hidden action labels."""

    ASK_CLARIFICATION = "ask_clarification"
    RECOMMEND = "recommend"
    COMMIT = "commit"
    ESCALATE = "escalate"
    WAIT = "wait"


@dataclass(frozen=True)
class EnvDialogueAction:
    """One hidden environment-facing action parsed from an LLM response."""

    actor: DialogueActor
    action_type: str
    slot: str | None = None
    product_id: str | None = None
    reason: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate actor/action compatibility and copy the raw payload.

        Inputs are fields parsed from the hidden JSON tag. The method raises
        `ValueError` for unknown buyer/seller action types and returns nothing.
        """

        action_type = str(self.action_type)
        if self.actor is DialogueActor.BUYER:
            BuyerDialogueActionType(action_type)
        else:
            SellerDialogueActionType(action_type)
        object.__setattr__(self, "action_type", action_type)
        object.__setattr__(self, "payload", dict(self.payload))


@dataclass(frozen=True)
class ParsedDialogueOutput:
    """Dual-channel output after stripping the hidden action tag."""

    actor: DialogueActor
    raw_output: str
    visible_message: str
    env_action: EnvDialogueAction


def parse_dual_channel_output(
    raw_output: str,
    *,
    expected_actor: DialogueActor | str,
) -> ParsedDialogueOutput:
    """Parse and strip one hidden ENV_ACTION tag from an LLM response.

    `raw_output` is the full LLM message containing visible text plus exactly
    one `### ENV_ACTION {...} ###` tag. `expected_actor` guards against the
    wrong side emitting an action. The return value contains both the stripped
    visible message and the parsed environment-only action.
    """

    actor = DialogueActor(expected_actor)
    matches = list(ENV_ACTION_PATTERN.finditer(raw_output))
    if not matches:
        raise ValueError("missing ENV_ACTION tag")
    if len(matches) > 1:
        raise ValueError("expected exactly one ENV_ACTION tag")

    match = matches[0]
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid ENV_ACTION JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("ENV_ACTION payload must be a JSON object")

    payload_actor = DialogueActor(payload.get("actor"))
    if payload_actor is not actor:
        raise ValueError(f"ENV_ACTION actor {payload_actor.value!r} does not match {actor.value!r}")

    action = EnvDialogueAction(
        actor=payload_actor,
        action_type=str(payload["type"]),
        slot=str(payload["slot"]) if payload.get("slot") is not None else None,
        product_id=(
            str(payload["product_id"]) if payload.get("product_id") is not None else None
        ),
        reason=str(payload.get("reason", "")),
        payload=payload,
    )
    visible_message = ENV_ACTION_PATTERN.sub("", raw_output).strip()
    return ParsedDialogueOutput(
        actor=actor,
        raw_output=raw_output,
        visible_message=visible_message,
        env_action=action,
    )


def validate_dialogue_action(
    action: EnvDialogueAction,
    *,
    task: SelectionTask,
    last_recommended_product_id: str | None = None,
    last_committed_product_id: str | None = None,
) -> tuple[str, ...]:
    """Return validation errors for a hidden dialogue action.

    These checks are factual/protocol checks only. They do not decide buyer
    utility or acceptance strategy.
    """

    errors: list[str] = []
    product_ids = {offer.offer_id for offer in task.offers}
    action_type = action.action_type

    if action.product_id is not None and action.product_id not in product_ids:
        errors.append(f"unknown product_id: {action.product_id}")

    if action.actor is DialogueActor.SELLER:
        if action_type == SellerDialogueActionType.ASK_CLARIFICATION.value:
            if action.slot is None:
                errors.append("ask_clarification requires slot")
            else:
                normalized_slot = normalize_clarification_slot(action.slot)
                if normalized_slot not in task.available_clarification_slots:
                    errors.append(f"unknown clarification slot: {action.slot}")
        elif action_type in {
            SellerDialogueActionType.RECOMMEND.value,
            SellerDialogueActionType.COMMIT.value,
        }:
            if action.product_id is None:
                errors.append(f"{action_type} requires product_id")
            if action_type == SellerDialogueActionType.COMMIT.value:
                if action.product_id != last_recommended_product_id:
                    errors.append("commit requires prior recommend for the same product")
        return tuple(errors)

    if action_type == BuyerDialogueActionType.REVEAL_NEED.value:
        if action.slot is None:
            errors.append("reveal_need requires slot")
        elif not _is_valid_buyer_slot(action.slot, task):
            errors.append(f"unknown buyer need slot: {action.slot}")
    elif action_type in {
        BuyerDialogueActionType.REJECT.value,
        BuyerDialogueActionType.ACCEPT.value,
    }:
        if action.product_id is None:
            errors.append(f"{action_type} requires product_id")
        if action_type == BuyerDialogueActionType.ACCEPT.value:
            if action.product_id != last_committed_product_id:
                errors.append("accept requires prior seller commit for the same product")
    return tuple(errors)


def _is_valid_buyer_slot(slot: str, task: SelectionTask) -> bool:
    """Return whether a buyer reveal slot exists in the task schema."""

    normalized_slot = normalize_clarification_slot(slot)
    if normalized_slot == CLARIFICATION_BUDGET_MAX:
        return True
    if normalized_slot.startswith(CLARIFICATION_MUST_HAVE_PREFIX):
        key = normalized_slot[len(CLARIFICATION_MUST_HAVE_PREFIX) :]
        return key in task.category_schema.constraint_slots
    if normalized_slot.startswith(CLARIFICATION_PREFERENCE_PREFIX):
        key = normalized_slot[len(CLARIFICATION_PREFERENCE_PREFIX) :]
        return key in task.category_schema.preference_slots
    return False
