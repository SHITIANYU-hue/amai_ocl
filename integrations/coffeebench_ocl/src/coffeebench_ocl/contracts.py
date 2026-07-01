"""OCL contract skeleton for CoffeeBench transactions.

The schema mirrors CoffeeBench's native objects without replacing them:
Listing, Offer, Deal, and Invoice stay owned by CoffeeBench. OCL contracts
store the cross-object lifecycle and audit metadata for the focal agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ContractStatus(str, Enum):
    DRAFTED = "drafted"
    VALIDATED = "validated"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    INVOICED = "invoiced"
    PAID = "paid"
    CLOSED = "closed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    RETURNED = "returned"
    DISPUTED = "disputed"
    DEFAULTED = "defaulted"
    INVALID = "invalid"
    SHIPMENT_DELAYED = "shipment_delayed"
    SHIPMENT_LOST = "shipment_lost"


class ValidationStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    NOT_RUN = "not_run"


TERMINAL_STATUSES: frozenset[ContractStatus] = frozenset(
    {
        ContractStatus.CLOSED,
        ContractStatus.REJECTED,
        ContractStatus.EXPIRED,
        ContractStatus.CANCELLED,
        ContractStatus.RETURNED,
        ContractStatus.DEFAULTED,
        ContractStatus.INVALID,
        ContractStatus.SHIPMENT_LOST,
    }
)


@dataclass(slots=True, frozen=True)
class ValidationResult:
    """Result of an OCL feasibility/risk check."""

    status: ValidationStatus = ValidationStatus.NOT_RUN
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ContractAuditEvent:
    """One lifecycle event linked to a CoffeeBench object or tool call."""

    event_type: str
    day: int | None = None
    actor_id: str | None = None
    status_before: ContractStatus | None = None
    status_after: ContractStatus | None = None
    coffee_event_type: str | None = None
    coffee_action_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OCLContract:
    """OCL-side lifecycle record for one CoffeeBench transaction."""

    contract_id: str
    focal_agent_id: str
    source: str = "coffeebench"
    status: ContractStatus = ContractStatus.DRAFTED

    buyer_id: str | None = None
    seller_id: str | None = None
    item_id: str | None = None
    quantity: int | None = None
    unit_price: float | None = None
    total_price: float | None = None
    payment_terms_days: int | None = None

    created_day: int | None = None
    delivery_day: int | None = None
    due_day: int | None = None

    listing_id: str | None = None
    offer_id: str | None = None
    deal_id: str | None = None
    invoice_id: str | None = None

    validation: ValidationResult = field(default_factory=ValidationResult)
    audit_events: list[ContractAuditEvent] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def append_event(self, event: ContractAuditEvent) -> None:
        self.audit_events.append(event)
        if event.status_after is not None:
            self.status = event.status_after
