"""Episode runner: drives buyer/seller turns through AgenticPay with optional OCL control."""

from __future__ import annotations

from contextlib import suppress
import re
from typing import Any

from aimai_ocl.adapters import (
    EnvAdapter,
    enforce_single_product,
    passthrough_executable,
    raw_action_from_text,
)
from aimai_ocl.control import (
    AuditPolicy,
    ControlConfig,
    apply_control,
    resolve_escalation,
)
from aimai_ocl.coordinator import Coordinator
from aimai_ocl.schemas import ActionRole, AuditEvent, AuditEventType, EpisodeTrace
from aimai_ocl.schemas import (
    ConstraintCheck,
    ConstraintSeverity,
    ControlDecision,
    ExecutableAction,
    ViolationType,
)

# Terminal metrics keys extracted from AgenticPay final_info.
_METRIC_KEYS = (
    "round", "status", "termination_reason", "agreed_price",
    "buyer_price", "seller_price", "buyer_reward", "seller_reward",
    "global_score", "buyer_score", "seller_score",
)


def run_episode(
    *,
    env_id: str,
    buyer_agent: Any,
    seller_agent: Any,
    reset_kwargs: dict[str, Any],
    env_kwargs: dict[str, Any] | None = None,
    trace_metadata: dict[str, Any] | None = None,
    # OCL components (all optional — omit for baseline)
    ocl: bool = False,
    control_config: ControlConfig | None = None,
    coordinator: Coordinator | None = None,
    audit_policy: AuditPolicy | None = None,
    enable_replan: bool = True,
    baseline_mode: str | None = None,
) -> tuple[EpisodeTrace, dict[str, Any]]:
    """Run one negotiation episode.

    Args:
        ocl: If True, seller actions go through the control pipeline.
             If False, seller actions pass through directly (baseline).
    """
    normalized_reset = enforce_single_product(reset_kwargs)
    env_config = dict(env_kwargs or {})
    env_config["buyer_agent"] = buyer_agent
    env_config["seller_agent"] = seller_agent

    adapter = EnvAdapter(env_id=env_id, env_kwargs=env_config)
    observation, _ = adapter.reset(**normalized_reset)
    trace = adapter.new_trace(scenario=normalized_reset, metadata=trace_metadata)

    coord = coordinator or Coordinator()
    policy = audit_policy
    ctrl_cfg = control_config
    ctrl_state = {
        "buyer_max_price": env_config.get("buyer_max_price"),
        "seller_min_price": env_config.get("seller_min_price"),
        "max_rounds": env_config.get("max_rounds"),
    }
    product_info = normalized_reset.get("product_info")
    if isinstance(product_info, dict):
        ctrl_state["product_name"] = product_info.get("name")
        ctrl_state["product_price"] = product_info.get("price")

    done = False
    final_info: dict[str, Any] = {}

    while not done:
        round_id = int(observation.get("current_round", 0))

        # --- Buyer turn (always passthrough) ---
        buyer_action = buyer_agent.respond(
            conversation_history=observation["conversation_history"],
            current_state=observation,
        )
        buyer_text = _normalize(buyer_action if isinstance(buyer_action, str) else None)

        # --- Seller turn ---
        seller_history = observation["conversation_history"].copy()
        if buyer_text is not None:
            seller_history.append({"role": "buyer", "content": buyer_text, "round": round_id})

        seller_actor_id = getattr(seller_agent, "name", "seller")

        if ocl:
            # Coordination: who owns this round?
            plan = coord.plan_turn(
                round_id=round_id, buyer_text=buyer_text,
                seller_actor_id=seller_actor_id,
                max_rounds=ctrl_state.get("max_rounds"),
            )
            _add_event(trace, coord.build_audit_event(plan), policy)

            seller_state = {**observation, **{k: v for k, v in ctrl_state.items() if v is not None}}
            seller_state["coordination_plan"] = {
                "decision_role": plan.decision_role.value,
                "reason": plan.reason,
            }
            seller_action = seller_agent.respond(
                conversation_history=seller_history, current_state=seller_state,
            )
            seller_text = _apply_ocl(
                trace=trace, text=seller_action,
                actor_id=seller_actor_id, round_id=round_id,
                state={**seller_state}, config=ctrl_cfg,
                audit_policy=policy, enable_replan=enable_replan,
            )
        else:
            seller_action = seller_agent.respond(
                conversation_history=seller_history, current_state=observation,
            )
            if baseline_mode == "price_floor_guard":
                seller_text = _apply_price_floor_guard(
                    trace=trace, text=seller_action,
                    actor_id=seller_actor_id, round_id=round_id,
                    state={**observation, **{k: v for k, v in ctrl_state.items() if v is not None}},
                    audit_policy=policy,
                )
            elif baseline_mode == "reference_monitor":
                seller_text = _apply_reference_monitor(
                    trace=trace, text=seller_action,
                    actor_id=seller_actor_id, round_id=round_id,
                    state={**observation, **{k: v for k, v in ctrl_state.items() if v is not None}},
                    config=ctrl_cfg,
                    audit_policy=policy,
                )
            else:
                # Baseline: passthrough with minimal audit
                seller_text = _apply_passthrough(
                    trace=trace, text=seller_action,
                    actor_id=seller_actor_id, round_id=round_id,
                    audit_policy=policy,
                )

        if seller_text is not None:
            trace.metadata.setdefault("executed_seller_actions", []).append(
                {
                    "round_id": round_id,
                    "actor_id": seller_actor_id,
                    "text": seller_text,
                }
            )

        observation, _, terminated, truncated, final_info = adapter.step(
            buyer_action=buyer_text, seller_action=seller_text,
        )
        done = terminated or truncated

    trace.final_status = str(final_info.get("status"))
    trace.final_metrics = {k: final_info.get(k) for k in _METRIC_KEYS}
    _add_event(trace, AuditEvent(
        event_type=AuditEventType.EPISODE_FINISHED,
        summary=f"Episode finished: status={trace.final_status}",
        metadata=trace.final_metrics,
    ), policy)

    with suppress(Exception):
        adapter.close()

    return trace, final_info


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_ocl(
    *,
    trace: EpisodeTrace,
    text: str | None,
    actor_id: str,
    round_id: int,
    state: dict[str, Any],
    config: ControlConfig | None,
    audit_policy: AuditPolicy | None,
    enable_replan: bool,
) -> str | None:
    """Run seller text through OCL control + escalation."""
    if text is None:
        return None

    raw = raw_action_from_text(actor_id, ActionRole.SELLER, text)
    result = apply_control(raw, state=state, round_id=round_id, config=config)
    for ev in result.audit_events:
        _add_event(trace, ev, audit_policy)

    final_text, esc_events = resolve_escalation(
        raw=raw, executable=result.executable,
        state=state, round_id=round_id, enable_replan=enable_replan,
    )
    for ev in esc_events:
        _add_event(trace, ev, audit_policy)

    if final_text is not None and final_text != text:
        # Replanned text — re-validate through control
        raw2 = raw_action_from_text(actor_id, ActionRole.SELLER, final_text)
        result2 = apply_control(raw2, state=state, round_id=round_id, config=config)
        for ev in result2.audit_events:
            _add_event(trace, ev, audit_policy)
        if result2.executable.approved:
            return result2.executable.final_text.strip() or None
        return None

    return final_text


def _apply_passthrough(
    *,
    trace: EpisodeTrace,
    text: str | None,
    actor_id: str,
    round_id: int,
    audit_policy: AuditPolicy | None,
) -> str | None:
    """Record passthrough seller action with minimal audit."""
    if text is None:
        return None
    raw = raw_action_from_text(actor_id, ActionRole.SELLER, text)
    exe = passthrough_executable(raw)
    _add_event(trace, AuditEvent(
        event_type=AuditEventType.ACTION_EXECUTED,
        round_id=round_id, actor_id=actor_id,
        summary=f"Passthrough action for {actor_id}",
        raw_action=raw, executable_action=exe,
    ), audit_policy)
    return exe.final_text


def _apply_price_floor_guard(
    *,
    trace: EpisodeTrace,
    text: str | None,
    actor_id: str,
    round_id: int,
    state: dict[str, Any],
    audit_policy: AuditPolicy | None,
) -> str | None:
    """Apply a narrow price-only guardrail baseline.

    This baseline deliberately ignores role, privacy, and high-risk checks. It
    only clamps explicit seller prices into the configured buyer/seller bounds.
    """
    if text is None:
        return None

    raw = raw_action_from_text(actor_id, ActionRole.SELLER, text)
    price = raw.proposed_price
    buyer_max = _as_float(state.get("buyer_max_price"))
    seller_min = _as_float(state.get("seller_min_price"))
    final_text = text
    final_price = price
    checks: list[ConstraintCheck] = []

    if price is None:
        checks.append(ConstraintCheck(
            constraint_id="price_floor_guard_format",
            passed=True,
            reason="No explicit seller price found; price guard does not apply.",
        ))
        decision = ControlDecision.APPROVE
    else:
        lower_bound = seller_min
        upper_bound = buyer_max
        clamped = price
        if lower_bound is not None:
            clamped = max(lower_bound, clamped)
        if upper_bound is not None:
            clamped = min(upper_bound, clamped)

        passed = clamped == price
        if lower_bound is not None and price < lower_bound:
            checks.append(ConstraintCheck(
                constraint_id="price_floor_guard_seller_floor",
                passed=False,
                severity=ConstraintSeverity.ERROR,
                violation_type=ViolationType.SELLER_FLOOR_BREACH,
                reason=f"Price {price:.2f} below seller floor {lower_bound:.2f}.",
                metadata={"original_price": price, "clamped_price": clamped},
            ))
        else:
            checks.append(ConstraintCheck(constraint_id="price_floor_guard_seller_floor", passed=True))

        if upper_bound is not None and price > upper_bound:
            checks.append(ConstraintCheck(
                constraint_id="price_floor_guard_budget_cap",
                passed=False,
                severity=ConstraintSeverity.ERROR,
                violation_type=ViolationType.BUDGET_EXCEEDED,
                reason=f"Price {price:.2f} exceeds buyer max {upper_bound:.2f}.",
                metadata={"original_price": price, "clamped_price": clamped},
            ))
        else:
            checks.append(ConstraintCheck(constraint_id="price_floor_guard_budget_cap", passed=True))

        if not passed:
            final_text = _replace_last_dollar_price(text, clamped)
            final_price = clamped
        decision = ControlDecision.APPROVE if passed else ControlDecision.REWRITE

    executable = ExecutableAction(
        actor_id=raw.actor_id,
        actor_role=raw.actor_role,
        approved=True,
        decision=decision,
        final_text=final_text,
        intent=raw.intent,
        final_price=final_price,
        metadata={"baseline_mode": "price_floor_guard"},
    )
    _add_event(trace, AuditEvent(
        event_type=AuditEventType.CONSTRAINT_EVALUATED,
        round_id=round_id,
        actor_id=actor_id,
        summary="Price-floor guard evaluated seller action.",
        raw_action=raw,
        executable_action=executable,
        constraint_checks=checks,
    ), audit_policy)
    _add_event(trace, AuditEvent(
        event_type=AuditEventType.ACTION_EXECUTED,
        round_id=round_id,
        actor_id=actor_id,
        summary=f"Price-floor guard decision: {decision.value}",
        raw_action=raw,
        executable_action=executable,
    ), audit_policy)
    return executable.final_text.strip() or None


def _apply_reference_monitor(
    *,
    trace: EpisodeTrace,
    text: str | None,
    actor_id: str,
    round_id: int,
    state: dict[str, Any],
    config: ControlConfig | None,
    audit_policy: AuditPolicy | None,
) -> str | None:
    """Apply a policy-only reference monitor baseline.

    It reuses the same checks as OCL but does not coordinate, escalate, or
    replan. Rejected actions are simply not executed.
    """
    if text is None:
        return None

    raw = raw_action_from_text(actor_id, ActionRole.SELLER, text)
    result = apply_control(raw, state=state, round_id=round_id, config=config)
    for ev in result.audit_events:
        ev.metadata["baseline_mode"] = "reference_monitor"
        _add_event(trace, ev, audit_policy)

    if not result.executable.approved:
        return None
    return result.executable.final_text.strip() or None


def _add_event(trace: EpisodeTrace, event: AuditEvent, policy: AuditPolicy | None) -> None:
    if policy is None or policy.should_record(event.event_type):
        trace.add_event(event)


def _normalize(text: str | None) -> str | None:
    if text is None:
        return None
    s = text.strip()
    return s or None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _replace_last_dollar_price(text: str, price: float) -> str:
    matches = list(re.finditer(r"\$[\d,]+(?:\.\d+)?", text))
    if not matches:
        return f"{text.strip()} ${price:.2f}".strip()
    last = matches[-1]
    return f"{text[:last.start()]}${price:.2f}{text[last.end():]}"
