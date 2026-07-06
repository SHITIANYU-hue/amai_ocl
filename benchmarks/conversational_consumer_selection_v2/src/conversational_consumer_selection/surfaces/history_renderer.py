"""Dialogue-first renderers for structured interaction history."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import Mapping, Sequence

from conversational_consumer_selection.schemas import (
    CLARIFICATION_BUDGET_MAX,
    CLARIFICATION_MUST_HAVE_PREFIX,
    CLARIFICATION_PREFERENCE_PREFIX,
    HistoryEntry,
    normalize_clarification_slot,
    Offer,
    SelectionAction,
)
from conversational_consumer_selection.surfaces.buyer_surface import render_buyer_response


def render_platform_action_surface(
    action: SelectionAction,
    *,
    offers: Sequence[Offer] | Mapping[str, Offer] | None = None,
    include_signal_tag: bool = False,
    annotate_entities: bool = False,
) -> str:
    """Render one platform-side utterance from a structured action.

    Inputs are a structured platform action, optional offer metadata, and debug
    rendering flags. The output is natural-language text for the clerk side of
    the transcript.
    """

    offer_lookup = _offer_lookup(offers)

    if action.action_type.value == "ask_clarification":
        message = _clarification_prompt(
            action.slot or "unknown",
            annotate_entities=annotate_entities,
        )
    elif action.action_type.value == "compare_options":
        left = _offer_reference(
            offer_lookup.get(action.offer_id or ""),
            action.offer_id or "unknown",
            annotate_entities=annotate_entities,
        )
        right = _offer_reference(
            offer_lookup.get(action.comparison_offer_id or ""),
            action.comparison_offer_id or "unknown",
            annotate_entities=annotate_entities,
        )
        message = f"Let me compare {left} against {right} directly."
    elif action.action_type.value == "recommend_option":
        offer = offer_lookup.get(action.offer_id or "")
        message = (
            "Based on what I know so far, I would recommend "
            f"{_offer_reference(offer, action.offer_id or 'unknown', annotate_entities=annotate_entities)}."
        )
    elif action.action_type.value == "commit_selection":
        offer = offer_lookup.get(action.offer_id or "")
        message = (
            "If you are ready, I can finalize "
            f"{_offer_reference(offer, action.offer_id or 'unknown', annotate_entities=annotate_entities)} now."
        )
    else:
        message = "I do not see a safe next step, so I am escalating this case."

    if not include_signal_tag:
        return message
    return f"{message} {render_platform_action_signal_tag(action)}"


def render_platform_action_signal_tag(action: SelectionAction) -> str:
    """Render a compact debug-only platform action tag.

    Input is a `SelectionAction`; output is a human-readable marker used in
    demos, not a hidden action consumed by the environment.
    """

    if action.action_type.value == "ask_clarification":
        return f"### ASK_CLARIFICATION(slot={action.slot}) ###"
    if action.action_type.value == "compare_options":
        return (
            "### COMPARE_OPTIONS("
            f"offer_id={action.offer_id}, comparison_offer_id={action.comparison_offer_id}"
            ") ###"
        )
    if action.action_type.value == "recommend_option":
        return f"### RECOMMEND_OPTION(offer_id={action.offer_id}) ###"
    if action.action_type.value == "commit_selection":
        return f"### COMMIT_SELECTION(offer_id={action.offer_id}) ###"
    return "### ESCALATE() ###"


def render_history_transcript(
    history: Sequence[HistoryEntry],
    *,
    include_signal_tags: bool = False,
    offers: Sequence[Offer] | Mapping[str, Offer] | None = None,
    annotate_entities: bool = False,
) -> str:
    """Render a structured history as a readable transcript.

    Inputs are prior `HistoryEntry` objects plus optional offer metadata and
    debug flags. The output is a multi-line transcript alternating platform and
    buyer messages.
    """

    if not history:
        return "(no prior turns)"

    lines: list[str] = []
    for entry in history:
        lines.append(f"Turn {entry.turn_index}")
        lines.append(
            "Platform: "
            + render_platform_action_surface(
                entry.action,
                offers=offers,
                include_signal_tag=include_signal_tags,
                annotate_entities=annotate_entities,
            )
        )
        lines.append(
            "Buyer: "
            + render_buyer_response(
                entry.action,
                entry.response,
                offers=_offer_lookup(offers).values(),
                include_signal_tag=include_signal_tags,
                annotate_entities=annotate_entities,
            )
        )
    return "\n".join(lines)


def _offer_lookup(offers: Sequence[Offer] | Mapping[str, Offer] | None) -> dict[str, Offer]:
    """Normalize optional offer metadata into an offer-id lookup."""

    if offers is None:
        return {}
    if isinstance(offers, MappingABC):
        return dict(offers)
    return {offer.offer_id: offer for offer in offers}


def _offer_reference(
    offer: Offer | None,
    fallback_offer_id: str,
    *,
    annotate_entities: bool,
) -> str:
    """Render one offer reference with title/price or a debug anchor."""

    if annotate_entities:
        return _offer_anchor(offer, fallback_offer_id)
    if offer is None:
        return fallback_offer_id
    if offer.title:
        return f"{offer.title} at ${offer.price:.0f}"
    return f"{offer.offer_id} at ${offer.price:.0f}"


def _offer_anchor(offer: Offer | None, fallback_offer_id: str) -> str:
    """Return an annotated product/price token for transcript debugging."""

    if offer is None:
        return f"[[PRODUCT:{fallback_offer_id}]]"
    if offer.title:
        return (
            f"[[PRODUCT:{offer.offer_id}|{offer.title}]] "
            f"at [[PRICE:${offer.price:.0f}]]"
        )
    return f"[[PRODUCT:{offer.offer_id}]] at [[PRICE:${offer.price:.0f}]]"


def _slot_reference(slot: str, *, annotate_entities: bool) -> str:
    """Render one slot name as readable text or a debug slot anchor."""

    if annotate_entities:
        return _slot_anchor(slot)
    return slot.replace("_", " ")


def _slot_anchor(slot: str) -> str:
    """Return the debug annotation token for a slot."""

    return f"[[SLOT:{slot}]]"


def _clarification_prompt(slot: str, *, annotate_entities: bool) -> str:
    """Render the clerk's clarification question for one slot."""

    normalized = normalize_clarification_slot(slot)
    if normalized == CLARIFICATION_BUDGET_MAX:
        return "I can narrow this down quickly, but I need to know your budget ceiling first."
    if normalized.startswith(CLARIFICATION_MUST_HAVE_PREFIX):
        key = normalized[len(CLARIFICATION_MUST_HAVE_PREFIX) :]
        readable_key = _slot_reference(key, annotate_entities=annotate_entities)
        return f"I should confirm one hard requirement first: do you definitely need {readable_key}?"
    if normalized.startswith(CLARIFICATION_PREFERENCE_PREFIX):
        key = normalized[len(CLARIFICATION_PREFERENCE_PREFIX) :]
        readable_key = _slot_reference(key, annotate_entities=annotate_entities)
        return (
            "I can narrow this down quickly, but I need to know how important "
            f"{readable_key} is for you."
        )
    return (
        "I can narrow this down quickly, but I need to know more about "
        f"{_slot_reference(normalized, annotate_entities=annotate_entities)}."
    )
