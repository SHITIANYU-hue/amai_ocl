"""OCL validation for CoffeeBench operational actions.

Validation is intentionally limited to organizational constraints visible at
execution time: object existence, ownership, capacity, settlement state, and
cash/inventory feasibility. It does not recommend suppliers, prices, or
production strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .contracts import ValidationResult, ValidationStatus


class ValidationMode(str, Enum):
    AUDIT = "audit"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class ValidationPolicy:
    mode: ValidationMode = ValidationMode.AUDIT

    @property
    def validates(self) -> bool:
        return self.mode in {ValidationMode.WARNING, ValidationMode.BLOCKING}

    @property
    def blocks(self) -> bool:
        return self.mode is ValidationMode.BLOCKING


def validate_operational_action(
    business_app: Any,
    action_name: str,
    action_input: dict[str, Any],
) -> ValidationResult:
    """Validate one focal CoffeeBench tool call before execution."""

    errors: list[str] = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {"action_name": action_name}

    if action_name == "post_listing":
        _validate_post_listing(business_app, action_input, errors, warnings)
    elif action_name == "make_offer":
        _validate_make_offer(business_app, action_input, errors, warnings)
    elif action_name == "withdraw_offer":
        _validate_withdraw_offer(business_app, action_input, errors, warnings)
    elif action_name == "accept_offer":
        _validate_accept_offer(business_app, action_input, errors, warnings)
    elif action_name == "pay_invoice":
        _validate_pay_invoice(business_app, action_input, errors, warnings)
    elif action_name == "return_shipment":
        _validate_return_shipment(business_app, action_input, errors, warnings)
    elif action_name == "roast":
        _validate_roast(business_app, action_input, errors, warnings)

    _warn_if_overdue_payables(business_app, warnings)

    if errors:
        status = ValidationStatus.FAIL
    elif warnings:
        status = ValidationStatus.WARNING
    else:
        status = ValidationStatus.PASS
    return ValidationResult(
        status=status,
        errors=tuple(errors),
        warnings=tuple(warnings),
        metadata=metadata,
    )


def _validate_post_listing(
    business_app: Any,
    action_input: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    item_id = str(action_input.get("item_id") or "")
    qty = _positive_int(action_input.get("qty"))
    price = _positive_float(action_input.get("asking_price"))
    terms = _positive_int(action_input.get("payment_terms_days", 30))
    if not item_id:
        errors.append("post_listing requires item_id.")
    if qty is None:
        errors.append("post_listing requires qty > 0.")
    elif business_app.inventory.get(item_id, 0) < qty:
        errors.append(f"Cannot list {qty} units of {item_id}; on-hand inventory is {business_app.inventory.get(item_id, 0)}.")
    if price is None:
        errors.append("post_listing requires asking_price > 0.")
    if terms is None:
        errors.append("post_listing requires positive payment_terms_days.")
    if item_id and business_app.marketplace.get_item(item_id) is None:
        errors.append(f"Unknown item_id '{item_id}'.")


def _validate_make_offer(
    business_app: Any,
    action_input: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    listing_id = str(action_input.get("listing_id") or "")
    qty = _positive_int(action_input.get("qty"))
    price = _positive_float(action_input.get("offered_price"))
    terms = _positive_int(action_input.get("payment_terms_days", 30))
    listing = _find_by_id(business_app.marketplace.listings, listing_id)
    if listing is None:
        errors.append(f"Listing '{listing_id}' does not exist.")
        return
    if getattr(listing, "status", None) != "open":
        errors.append(f"Listing '{listing_id}' is not open.")
    if getattr(listing, "seller_id", None) == business_app.agent_id:
        errors.append("Cannot make an offer on the focal agent's own listing.")
    if qty is None:
        errors.append("make_offer requires qty > 0.")
    elif qty > int(getattr(listing, "qty", 0)):
        errors.append(f"Offer qty {qty} exceeds listing qty {getattr(listing, 'qty', 0)}.")
    if price is None:
        errors.append("make_offer requires offered_price > 0.")
    if terms is None:
        errors.append("make_offer requires positive payment_terms_days.")
    _check_inbound_inventory_cap(business_app, qty or 0, errors)
    duplicate = [
        offer.id
        for offer in business_app.marketplace.offers
        if getattr(offer, "buyer_id", None) == business_app.agent_id
        and getattr(offer, "listing_id", None) == listing_id
        and getattr(offer, "status", None) == "pending"
    ]
    if duplicate:
        warnings.append(f"Existing pending offer(s) on the same listing: {duplicate}.")


def _validate_accept_offer(
    business_app: Any,
    action_input: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    offer_id = str(action_input.get("offer_id") or "")
    offer = _find_by_id(business_app.marketplace.offers, offer_id)
    if offer is None:
        errors.append(f"Offer '{offer_id}' does not exist.")
        return
    if getattr(offer, "seller_id", None) != business_app.agent_id:
        errors.append("Only the seller may accept this offer.")
    if getattr(offer, "status", None) != "pending":
        errors.append(f"Offer '{offer_id}' is not pending.")
    listing = _find_by_id(business_app.marketplace.listings, getattr(offer, "listing_id", ""))
    if listing is None or getattr(listing, "status", None) != "open":
        errors.append("Linked listing is missing or not open.")
        return
    item_id = getattr(listing, "item_id", "")
    qty = int(getattr(offer, "qty", 0) or 0)
    if business_app.inventory.get(item_id, 0) < qty:
        errors.append(f"Insufficient inventory to accept offer: need {qty} {item_id}.")
    buyer = business_app.marketplace.business_apps.get(getattr(offer, "buyer_id", ""))
    if buyer is not None:
        _check_inbound_inventory_cap(buyer, qty, errors, subject=f"Buyer {buyer.agent_id}")
    if warnings is not None and float(getattr(offer, "offered_price", 0.0) or 0.0) <= 0:
        errors.append("Offer price must be positive.")


def _validate_withdraw_offer(
    business_app: Any,
    action_input: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    offer_id = str(action_input.get("offer_id") or "")
    offer = _find_by_id(business_app.marketplace.offers, offer_id)
    if offer is None:
        errors.append(f"Offer '{offer_id}' does not exist.")
        return
    if getattr(offer, "buyer_id", None) != business_app.agent_id:
        errors.append("Only the buyer may withdraw this offer.")
    if getattr(offer, "status", None) != "pending":
        errors.append(f"Offer '{offer_id}' is not pending.")


def _validate_pay_invoice(
    business_app: Any,
    action_input: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    invoice_id = str(action_input.get("invoice_id") or "")
    invoice = _find_by_id(business_app.accounts_payable, invoice_id)
    if invoice is None:
        errors.append(f"Open AP invoice '{invoice_id}' is not visible to the focal agent.")
        return
    if getattr(invoice, "paid", False):
        errors.append(f"Invoice '{invoice_id}' is already paid.")
    if getattr(invoice, "returned", False):
        errors.append(f"Invoice '{invoice_id}' is already returned/credited.")
    amount_due = float(getattr(invoice, "net_outstanding", 0.0) or 0.0)
    if business_app.cash < amount_due:
        errors.append(f"Insufficient cash to pay invoice '{invoice_id}' (${business_app.cash:.2f} < ${amount_due:.2f}).")
    today = business_app._today()
    if int(getattr(invoice, "due_date", today) or today) < today:
        warnings.append(f"Invoice '{invoice_id}' is overdue.")


def _validate_return_shipment(
    business_app: Any,
    action_input: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    invoice_id = str(action_input.get("invoice_id") or "")
    qty = _positive_int(action_input.get("quantity_kg"))
    invoice = _find_by_id(business_app.accounts_payable, invoice_id)
    if invoice is None:
        errors.append(f"AP invoice '{invoice_id}' is not visible to the focal agent.")
        return
    if qty is None:
        errors.append("return_shipment requires quantity_kg > 0.")
        return
    deal = _find_by_id(business_app.marketplace.deals, getattr(invoice, "reference", ""))
    if deal is None:
        errors.append("Linked deal is missing; return cannot be reconciled.")
        return
    if getattr(deal, "buyer_id", None) != business_app.agent_id:
        errors.append("Only the original buyer can return this shipment.")
    remaining = int(getattr(deal, "qty", 0) or 0) - int(getattr(deal, "returned_qty", 0) or 0)
    if qty > remaining:
        errors.append(f"Return quantity {qty} exceeds remaining returnable quantity {remaining}.")
    item_id = getattr(deal, "item_id", "")
    if business_app.inventory.get(item_id, 0) < qty:
        errors.append(f"Insufficient {item_id} inventory for return.")
    try:
        from coffeebench.environment import RETURN_WINDOW_DAYS  # noqa: PLC0415
    except Exception:
        RETURN_WINDOW_DAYS = 14
    if business_app._today() - int(getattr(invoice, "issue_date", 0) or 0) > RETURN_WINDOW_DAYS:
        errors.append(f"Return window of {RETURN_WINDOW_DAYS} days has closed.")


def _validate_roast(
    business_app: Any,
    action_input: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    if business_app.role != "roaster":
        errors.append("roast is roaster-only.")
        return
    green_item_id = str(action_input.get("green_item_id") or "")
    qty = _positive_int(action_input.get("qty_kg"))
    if qty is None:
        errors.append("roast requires qty_kg > 0.")
        return
    try:
        from coffeebench.environment import ROAST_DAILY_CAP_GREEN_KG, ROAST_RECIPES  # noqa: PLC0415
    except Exception:
        errors.append("CoffeeBench roast recipe metadata is unavailable.")
        return
    recipe = ROAST_RECIPES.get(green_item_id)
    if recipe is None:
        errors.append(f"Unknown green item '{green_item_id}'.")
        return
    held = business_app.inventory.get(green_item_id, 0)
    if held < qty:
        errors.append(f"Insufficient green inventory: {held} kg held, {qty} kg requested.")
    env = getattr(business_app.marketplace, "_env", None)
    used = getattr(env, "_roast_used_today", {}).get(business_app.agent_id, 0) if env is not None else 0
    remaining = ROAST_DAILY_CAP_GREEN_KG - used
    if qty > remaining:
        errors.append(f"Roast request exceeds remaining shared roasting capacity ({remaining} kg).")
    labor_cost = qty * float(recipe.get("labor_cost_per_kg", 0.0) or 0.0)
    if business_app.cash < labor_cost:
        errors.append(f"Insufficient cash for roast labor (${business_app.cash:.2f} < ${labor_cost:.2f}).")
    output_qty = max(0, int(round(qty * float(recipe.get("yield", 0.0) or 0.0))))
    post_call_hold = business_app._total_inventory_kg() - qty + business_app._pending_inbound_kg() + output_qty
    if post_call_hold > business_app._inventory_cap_kg():
        errors.append("Roast would exceed committed inventory cap.")


def _warn_if_overdue_payables(business_app: Any, warnings: list[str]) -> None:
    today = business_app._today()
    overdue = [
        inv.id
        for inv in business_app.accounts_payable
        if not getattr(inv, "paid", False)
        and not getattr(inv, "returned", False)
        and float(getattr(inv, "net_outstanding", 0.0) or 0.0) > 0
        and int(getattr(inv, "due_date", today) or today) < today
    ]
    if overdue:
        warnings.append(f"Open overdue payable invoice(s): {overdue}.")


def _check_inbound_inventory_cap(
    business_app: Any,
    added_qty: int,
    errors: list[str],
    *,
    subject: str = "Focal agent",
) -> None:
    if added_qty <= 0:
        return
    effective = business_app._total_inventory_kg() + business_app._pending_inbound_kg()
    cap = business_app._inventory_cap_kg()
    if effective + added_qty > cap:
        errors.append(f"{subject} would exceed inventory cap {cap} kg with this commitment.")


def _find_by_id(rows: list[Any], object_id: str) -> Any | None:
    for row in rows:
        if getattr(row, "id", None) == object_id:
            return row
    return None


def _positive_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _positive_int(value: Any) -> int | None:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None
