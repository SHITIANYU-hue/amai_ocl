"""Deterministic checks for RetailBench actions and the added OCL policy."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

from aocl_core.contracts import (
    CheckLevel,
    CheckResult,
    DecisionType,
    ObservableContext,
    ProposedAction,
)

from .policy import RetailGovernancePolicy


@dataclass(frozen=True, slots=True)
class RetailActionHardValidator:
    """Reject malformed state-changing actions before RetailBench executes them."""

    def validate(
        self,
        action: ProposedAction,
        context: ObservableContext,
    ) -> Sequence[CheckResult]:
        del context
        tool_name = action.action_type.removeprefix("retailbench.")
        error = self._error(tool_name, dict(action.payload))
        return (
            CheckResult(
                check_id=f"retailbench.hard.{tool_name}",
                passed=error is None,
                level=CheckLevel.ERROR if error else CheckLevel.INFO,
                reason=error or "",
                source="retailbench_hard_constraints",
                recommended_decision=DecisionType.BLOCK if error else None,
            ),
        )

    @staticmethod
    def _error(tool_name: str, payload: dict[str, Any]) -> str | None:
        if tool_name == "place_order":
            supplier_id = payload.get("supplier_id")
            if not isinstance(supplier_id, str) or not supplier_id.strip():
                return "place_order requires a non-empty supplier_id"
            items = payload.get("items")
            if not isinstance(items, list) or not items:
                return "place_order requires at least one order item"
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    return f"place_order item {index} must be an object"
                sku_id = item.get("sku_id")
                quantity = item.get("quantity")
                if not isinstance(sku_id, str) or not sku_id.strip():
                    return f"place_order item {index} requires a non-empty sku_id"
                if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
                    return f"place_order item {index} quantity must be a positive integer"
            return None

        if tool_name == "modify_sku_price":
            sku_id = payload.get("sku_id")
            price = payload.get("new_price")
            if not isinstance(sku_id, str) or not sku_id.strip():
                return "modify_sku_price requires a non-empty sku_id"
            if (
                isinstance(price, bool)
                or not isinstance(price, (int, float))
                or not math.isfinite(float(price))
                or float(price) <= 0
            ):
                return "modify_sku_price new_price must be a finite positive number"
            return None

        if tool_name == "add_note":
            content = payload.get("content")
            if not isinstance(content, str) or not content.strip():
                return "add_note requires non-empty content"
            return None

        if tool_name == "end_today":
            return None

        return None


@dataclass(frozen=True, slots=True)
class RetailOrganizationalPolicyValidator:
    """Enforce the declared OCL policy using only visible RetailBench state."""

    policy: RetailGovernancePolicy = RetailGovernancePolicy()

    def validate(
        self,
        action: ProposedAction,
        context: ObservableContext,
    ) -> Sequence[CheckResult]:
        tool_name = action.action_type.removeprefix("retailbench.")
        if tool_name == "place_order":
            return self._validate_order(action.payload, context.visible_state)
        if tool_name == "modify_sku_price":
            return self._validate_price(action.payload, context.visible_state)
        return ()

    def _validate_order(
        self,
        payload: Mapping[str, Any],
        visible_state: Mapping[str, Any],
    ) -> tuple[CheckResult, ...]:
        observations = _mapping(visible_state.get("observations"))
        limits = _mapping(visible_state.get("environment_limits"))
        items = payload.get("items")
        supplier_id = payload.get("supplier_id")
        if not isinstance(items, list) or not isinstance(supplier_id, str):
            return ()

        quantity = 0
        total_cost = 0.0
        quotes = _mapping(observations.get("view_current_date_supplier_prices"))
        for item in items:
            if not isinstance(item, Mapping):
                return ()
            sku_id = item.get("sku_id")
            item_quantity = item.get("quantity")
            if not isinstance(sku_id, str) or isinstance(item_quantity, bool) or not isinstance(item_quantity, int) or item_quantity <= 0:
                return ()
            price = _supplier_price(quotes, sku_id, supplier_id)
            if price is None:
                return ()
            quantity += item_quantity
            total_cost += price * item_quantity

        checks: list[CheckResult] = []
        funds_payload = _mapping(observations.get("view_funds_and_date"))
        funds = _number(funds_payload.get("funds"))
        daily_rent = _number(limits.get("daily_rent"))
        if funds is not None and daily_rent is not None:
            required_reserve = daily_rent * self.policy.reserve_rent_days
            funds_after = funds - total_cost
            passed = funds_after >= required_reserve
            checks.append(
                _policy_check(
                    "retailbench.policy.cash_reserve",
                    passed,
                    (
                        "Order would leave insufficient cash reserve: "
                        f"{funds_after:.2f} < {required_reserve:.2f}"
                        if not passed
                        else ""
                    ),
                    metadata={
                        "funds": funds,
                        "order_cost": total_cost,
                        "funds_after": funds_after,
                        "required_reserve": required_reserve,
                    },
                )
            )

        if self.policy.enforce_inventory_capacity:
            inventory = _mapping(observations.get("view_inventory"))
            used = _number(inventory.get("total_items"))
            waiting = _number(inventory.get("waiting_items"))
            capacity = _number(limits.get("inventory_capacity"))
            if used is not None and waiting is not None and capacity is not None:
                projected = used + waiting + quantity
                passed = projected <= capacity
                checks.append(
                    _policy_check(
                        "retailbench.policy.inventory_capacity",
                        passed,
                        (
                            "Order would exceed declared inventory capacity: "
                            f"{projected:.0f} > {capacity:.0f}"
                            if not passed
                            else ""
                        ),
                        metadata={
                            "inventory_used": used,
                            "waiting_items": waiting,
                            "order_quantity": quantity,
                            "projected_inventory": projected,
                            "inventory_capacity": capacity,
                        },
                    )
                )
        return tuple(checks)

    def _validate_price(
        self,
        payload: Mapping[str, Any],
        visible_state: Mapping[str, Any],
    ) -> tuple[CheckResult, ...]:
        sku_id = payload.get("sku_id")
        new_price = _number(payload.get("new_price"))
        if not isinstance(sku_id, str) or new_price is None or new_price <= 0:
            return ()
        observations = _mapping(visible_state.get("observations"))
        checks: list[CheckResult] = []

        quotes = _mapping(observations.get("view_current_date_supplier_prices"))
        costs = _sku_prices(quotes, sku_id)
        if costs:
            visible_cost = min(costs)
            floor = visible_cost * (1.0 + self.policy.minimum_markup_fraction)
            passed = new_price >= floor
            checks.append(
                _policy_check(
                    "retailbench.policy.price_floor",
                    passed,
                    (
                        "Proposed selling price is below the visible procurement floor: "
                        f"{new_price:.2f} < {floor:.2f}"
                        if not passed
                        else ""
                    ),
                    metadata={
                        "new_price": new_price,
                        "visible_procurement_cost": visible_cost,
                        "required_price_floor": floor,
                    },
                )
            )

        current_prices = _mapping(observations.get("view_sku_prices"))
        current_price = _number(current_prices.get(sku_id))
        if current_price is not None and current_price > 0:
            change = abs(new_price - current_price) / current_price
            passed = change <= self.policy.large_price_change_fraction
            checks.append(
                CheckResult(
                    check_id="retailbench.policy.large_price_change",
                    passed=passed,
                    level=CheckLevel.WARNING if not passed else CheckLevel.INFO,
                    reason=(
                        "Proposed price change exceeds the declared review threshold: "
                        f"{change:.3f} > {self.policy.large_price_change_fraction:.3f}"
                        if not passed
                        else ""
                    ),
                    source="retailbench_organizational_policy",
                    recommended_decision=DecisionType.WARN if not passed else None,
                    metadata={
                        "current_price": current_price,
                        "new_price": new_price,
                        "change_fraction": change,
                        "threshold": self.policy.large_price_change_fraction,
                    },
                )
            )
        return tuple(checks)


def _policy_check(
    check_id: str,
    passed: bool,
    reason: str,
    *,
    metadata: Mapping[str, Any],
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        passed=passed,
        level=CheckLevel.ERROR if not passed else CheckLevel.INFO,
        reason=reason,
        source="retailbench_organizational_policy",
        recommended_decision=DecisionType.BLOCK if not passed else None,
        metadata=metadata,
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _sku_prices(quotes: Mapping[str, Any], sku_id: str) -> tuple[float, ...]:
    entries = quotes.get(sku_id)
    if not isinstance(entries, list):
        return ()
    prices = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        price = _number(entry.get("price"))
        if price is not None:
            prices.append(price)
    return tuple(prices)


def _supplier_price(
    quotes: Mapping[str, Any],
    sku_id: str,
    supplier_id: str,
) -> float | None:
    entries = quotes.get(sku_id)
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, Mapping) and entry.get("supplier_id") == supplier_id:
            return _number(entry.get("price"))
    return None
