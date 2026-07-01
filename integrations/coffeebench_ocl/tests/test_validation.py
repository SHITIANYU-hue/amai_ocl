"""Validation tests for CoffeeBench operational actions."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from coffeebench_ocl.contracts import ValidationStatus
from coffeebench_ocl.validation import validate_operational_action


@dataclass
class Listing:
    id: str
    seller_id: str
    item_id: str
    qty: int
    status: str = "open"


class FakeMarketplace:
    def __init__(self) -> None:
        self.listings = [Listing("lst_self", "roaster_A", "green_coffee_kg", 10)]
        self.offers = [
            SimpleNamespace(id="off_other", buyer_id="retailer_A", seller_id="roaster_A", status="pending"),
            SimpleNamespace(id="off_done", buyer_id="roaster_A", seller_id="farmer_A", status="accepted"),
        ]
        self.deals = []
        self.business_apps = {}

    def get_item(self, item_id: str):
        return SimpleNamespace(id=item_id) if item_id else None


class FakeBusinessApp:
    agent_id = "roaster_A"
    role = "roaster"
    cash = 100.0
    inventory = {"roasted_coffee_kg": 5, "green_coffee_kg": 2}
    accounts_payable = []
    accounts_receivable = []

    def __init__(self) -> None:
        self.marketplace = FakeMarketplace()

    def _today(self) -> int:
        return 1

    def _total_inventory_kg(self) -> int:
        return sum(self.inventory.values())

    def _pending_inbound_kg(self) -> int:
        return 0

    def _inventory_cap_kg(self) -> int:
        return 120


def test_validation_blocks_self_offer() -> None:
    result = validate_operational_action(
        FakeBusinessApp(),
        "make_offer",
        {"listing_id": "lst_self", "offered_price": 3.0, "qty": 1, "payment_terms_days": 30},
    )

    assert result.status is ValidationStatus.FAIL
    assert any("own listing" in error for error in result.errors)


def test_validation_blocks_listing_more_than_inventory() -> None:
    result = validate_operational_action(
        FakeBusinessApp(),
        "post_listing",
        {"item_id": "roasted_coffee_kg", "qty": 10, "asking_price": 12.0, "payment_terms_days": 30},
    )

    assert result.status is ValidationStatus.FAIL
    assert any("on-hand inventory" in error for error in result.errors)


def test_validation_blocks_roast_without_green_inventory() -> None:
    result = validate_operational_action(
        FakeBusinessApp(),
        "roast",
        {"green_item_id": "green_coffee_kg", "qty_kg": 20},
    )

    assert result.status is ValidationStatus.FAIL
    assert any("Insufficient green inventory" in error for error in result.errors)


def test_validation_blocks_withdrawal_by_wrong_buyer() -> None:
    result = validate_operational_action(
        FakeBusinessApp(),
        "withdraw_offer",
        {"offer_id": "off_other"},
    )

    assert result.status is ValidationStatus.FAIL
    assert any("Only the buyer" in error for error in result.errors)
