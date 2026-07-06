"""Transaction dialogue environment for dual-agent shopping conversations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from conversational_consumer_selection.dialogue_actions import (
    BuyerDialogueActionType,
    DialogueActor,
    EnvDialogueAction,
    parse_dual_channel_output,
    ParsedDialogueOutput,
    SellerDialogueActionType,
    validate_dialogue_action,
)
from conversational_consumer_selection.schemas import SelectionTask


@dataclass(frozen=True)
class DialogueEvent:
    """One environment-visible dialogue event."""

    turn_index: int
    actor: DialogueActor
    visible_message: str
    env_action: EnvDialogueAction
    validation_errors: tuple[str, ...] = ()


@dataclass
class TransactionDialogueState:
    """Mutable transaction dialogue state."""

    task: SelectionTask
    visible_history: list[dict[str, Any]] = field(default_factory=list)
    event_log: list[DialogueEvent] = field(default_factory=list)
    turn_index: int = 0
    last_recommended_product_id: str | None = None
    last_committed_product_id: str | None = None
    accepted_product_id: str | None = None
    rejected_product_ids: list[str] = field(default_factory=list)
    escalated: bool = False
    terminated: bool = False
    truncated: bool = False
    termination_reason: str | None = None
    invalid_action_count: int = 0
    protocol_violation_count: int = 0


class TransactionDialogueEnv:
    """Minimal environment that routes visible text and records hidden actions."""

    def __init__(self, task: SelectionTask) -> None:
        """Create a transaction dialogue environment for one selection task.

        Input is the task defining products, slots, and max turns. The method
        initializes empty visible history and hidden event logs, and returns
        nothing.
        """

        self._state = TransactionDialogueState(task=task)

    @property
    def state(self) -> TransactionDialogueState:
        """Return the mutable transaction dialogue state."""

        return self._state

    def process_turn(
        self,
        *,
        actor: DialogueActor | str,
        raw_output: str,
    ) -> tuple[ParsedDialogueOutput, dict[str, Any]]:
        """Parse one raw LLM output, hide its action tag, and update state."""

        state = self.state
        if state.terminated:
            raise RuntimeError("transaction dialogue is already terminated")

        parsed = parse_dual_channel_output(raw_output, expected_actor=actor)
        errors = validate_dialogue_action(
            parsed.env_action,
            task=state.task,
            last_recommended_product_id=state.last_recommended_product_id,
            last_committed_product_id=state.last_committed_product_id,
        )
        if errors:
            state.invalid_action_count += 1
            state.protocol_violation_count += 1

        state.turn_index += 1
        event = DialogueEvent(
            turn_index=state.turn_index,
            actor=parsed.actor,
            visible_message=parsed.visible_message,
            env_action=parsed.env_action,
            validation_errors=errors,
        )
        state.event_log.append(event)
        state.visible_history.append(
            {
                "role": parsed.actor.value,
                "content": parsed.visible_message,
                "round": state.turn_index,
            }
        )
        self._apply_valid_action(parsed.env_action, errors)
        self._update_timeout()
        return parsed, self.summary()

    def summary(self) -> dict[str, Any]:
        """Return current transaction metrics and state.

        The output includes the visible transcript, hidden-action counters, last
        recommend/commit/accept product IDs, and termination status.
        """

        state = self.state
        return {
            "task_id": state.task.task_id,
            "turn_index": state.turn_index,
            "visible_history": list(state.visible_history),
            "event_count": len(state.event_log),
            "last_recommended_product_id": state.last_recommended_product_id,
            "last_committed_product_id": state.last_committed_product_id,
            "accepted_product_id": state.accepted_product_id,
            "transaction_success": state.accepted_product_id is not None,
            "invalid_action_count": state.invalid_action_count,
            "protocol_violation_count": state.protocol_violation_count,
            "escalated": state.escalated,
            "terminated": state.terminated,
            "truncated": state.truncated,
            "termination_reason": state.termination_reason,
        }

    def _apply_valid_action(
        self,
        action: EnvDialogueAction,
        errors: tuple[str, ...],
    ) -> None:
        """Apply a parsed hidden action after protocol validation.

        Inputs are the parsed action and its validation errors. Invalid actions
        are ignored for state transitions; valid recommend/commit/accept actions
        update transaction progress.
        """

        if errors:
            return
        state = self.state
        if action.actor is DialogueActor.SELLER:
            if action.action_type == SellerDialogueActionType.RECOMMEND.value:
                state.last_recommended_product_id = action.product_id
            elif action.action_type == SellerDialogueActionType.COMMIT.value:
                state.last_committed_product_id = action.product_id
            elif action.action_type == SellerDialogueActionType.ESCALATE.value:
                state.escalated = True
                state.terminated = True
                state.termination_reason = "escalated"
            return

        if action.action_type == BuyerDialogueActionType.REJECT.value:
            if action.product_id is not None:
                state.rejected_product_ids.append(action.product_id)
        elif action.action_type == BuyerDialogueActionType.ACCEPT.value:
            state.accepted_product_id = action.product_id
            state.terminated = True
            state.termination_reason = "buyer_accepted"

    def _update_timeout(self) -> None:
        """Terminate the dialogue when message turns exceed the task budget."""

        state = self.state
        if state.terminated:
            return
        max_message_turns = state.task.max_turns * 2
        if state.turn_index >= max_message_turns:
            state.terminated = True
            state.truncated = True
            state.termination_reason = "timeout"
