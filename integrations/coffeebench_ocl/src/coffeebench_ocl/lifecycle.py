"""Passive reconstruction of CoffeeBench transaction lifecycles."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from .contracts import ContractAuditEvent, ContractStatus, OCLContract
from .json_utils import jsonable
from .tooling import FOCAL_AGENT_ID, RAW_TRADE_TOOLS


def _asdict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return {}


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


class ContractLifecycle:
    """Maintains OCL contracts reconstructed from passive CoffeeBench signals."""

    def __init__(self, *, focal_agent_id: str = FOCAL_AGENT_ID) -> None:
        self.focal_agent_id = focal_agent_id
        self.contracts: dict[str, OCLContract] = {}
        self.by_offer_id: dict[str, str] = {}
        self.by_deal_id: dict[str, str] = {}
        self.by_invoice_id: dict[str, str] = {}

    def process_tool_call(
        self,
        *,
        action_name: str,
        action_input: dict[str, Any],
        result: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> list[ContractAuditEvent]:
        """Update lifecycle state from one focal raw trade tool result."""

        if action_name not in RAW_TRADE_TOOLS:
            return []
        if result.get("status") != "success":
            return []

        context = context or {}
        if action_name == "make_offer":
            return self._from_make_offer(action_input, result, context)
        if action_name == "withdraw_offer":
            return self._from_withdraw_offer(action_input, result, context)
        if action_name == "accept_offer":
            return self._from_accept_offer(action_input, result, context)
        if action_name == "pay_invoice":
            return self._from_pay_invoice(action_input, result, context)
        if action_name == "return_shipment":
            return self._from_return_shipment(action_input, result, context)
        return []

    def process_coffee_event(
        self,
        *,
        event_type: str,
        data: dict[str, Any],
    ) -> list[ContractAuditEvent]:
        """Update lifecycle state from a native CoffeeBench event."""

        if event_type == "deal_delivered":
            return self._from_deal_delivered(data)
        if event_type == "shipment_delayed":
            return self._from_shipment_delayed(data)
        if event_type == "shipment_lost":
            return self._from_shipment_lost(data)
        return []

    def to_records(self) -> list[dict[str, Any]]:
        records = []
        for contract in self.contracts.values():
            row = jsonable(contract)
            row["is_terminal"] = contract.is_terminal
            records.append(row)
        return records

    def metrics(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        for contract in self.contracts.values():
            status_counts[contract.status.value] = status_counts.get(contract.status.value, 0) + 1
        return {
            "focal_agent_id": self.focal_agent_id,
            "contract_count": len(self.contracts),
            "status_counts": status_counts,
            "link_counts": {
                "offer": len(self.by_offer_id),
                "deal": len(self.by_deal_id),
                "invoice": len(self.by_invoice_id),
            },
        }

    def _from_make_offer(
        self,
        action_input: dict[str, Any],
        result: dict[str, Any],
        context: dict[str, Any],
    ) -> list[ContractAuditEvent]:
        offer_id = str(result.get("offer_id") or "")
        if not offer_id:
            return []

        listing = _asdict(context.get("listing"))
        qty = _positive_int(action_input.get("qty"))
        unit_price = _positive_float(action_input.get("offered_price"))
        contract = self._get_or_create(
            key=f"offer:{offer_id}",
            contract_id=f"ocl_offer_{offer_id}",
            offer_id=offer_id,
        )
        actor_id = str(context.get("agent_id") or self.focal_agent_id)
        contract.buyer_id = actor_id
        contract.seller_id = str(result.get("seller_id") or listing.get("seller_id") or "") or None
        contract.item_id = str(listing.get("item_id") or "") or None
        contract.quantity = qty
        contract.unit_price = unit_price
        contract.total_price = round(qty * unit_price, 2) if qty and unit_price else None
        contract.payment_terms_days = _positive_int(action_input.get("payment_terms_days"))
        contract.listing_id = str(action_input.get("listing_id") or listing.get("id") or "") or None
        contract.offer_id = offer_id
        contract.created_day = context.get("day")
        self._index(contract)
        return [
            self._transition(
                contract,
                event_type="offer_submitted",
                status_after=ContractStatus.OFFERED,
                action_name="make_offer",
                day=context.get("day"),
                metadata={"result": result, "action_input": action_input},
            )
        ]

    def _from_accept_offer(
        self,
        action_input: dict[str, Any],
        result: dict[str, Any],
        context: dict[str, Any],
    ) -> list[ContractAuditEvent]:
        offer_id = str(action_input.get("offer_id") or context.get("offer_id") or "")
        deal_id = str(result.get("deal_id") or "")
        if offer_id and offer_id in self.by_offer_id:
            contract = self.contracts[self.by_offer_id[offer_id]]
        else:
            key = f"deal:{deal_id}" if deal_id else f"accepted_offer:{offer_id}"
            contract = self._get_or_create(
                key=key,
                contract_id=f"ocl_deal_{deal_id}" if deal_id else f"ocl_offer_{offer_id}",
                offer_id=offer_id or None,
                deal_id=deal_id or None,
            )

        actor_id = str(context.get("agent_id") or self.focal_agent_id)
        contract.seller_id = actor_id
        contract.buyer_id = str(result.get("buyer_id") or "") or None
        contract.item_id = str(result.get("item_id") or "") or None
        contract.quantity = _positive_int(result.get("qty"))
        contract.unit_price = _positive_float(result.get("unit_price"))
        contract.total_price = _positive_float(result.get("total_price"))
        contract.payment_terms_days = _positive_int(result.get("payment_terms_days"))
        contract.delivery_day = _positive_int(result.get("delivery_day"))
        contract.offer_id = offer_id or contract.offer_id
        contract.deal_id = deal_id or contract.deal_id
        invoice_id = str(result.get("invoice_id") or "")
        contract.invoice_id = invoice_id or contract.invoice_id
        self._index(contract)
        return [
            self._transition(
                contract,
                event_type="offer_accepted",
                status_after=ContractStatus.ACCEPTED,
                action_name="accept_offer",
                day=context.get("day"),
                metadata={"result": result, "action_input": action_input},
            )
        ]

    def _from_withdraw_offer(
        self,
        action_input: dict[str, Any],
        result: dict[str, Any],
        context: dict[str, Any],
    ) -> list[ContractAuditEvent]:
        offer_id = str(action_input.get("offer_id") or "")
        if not offer_id:
            return []
        if offer_id in self.by_offer_id:
            contract = self.contracts[self.by_offer_id[offer_id]]
        else:
            contract = self._get_or_create(
                key=f"offer:{offer_id}",
                contract_id=f"ocl_offer_{offer_id}",
                offer_id=offer_id,
            )
        offer = _asdict(context.get("offer"))
        contract.offer_id = offer_id
        contract.buyer_id = str(offer.get("buyer_id") or contract.buyer_id or self.focal_agent_id) or None
        contract.seller_id = str(offer.get("seller_id") or contract.seller_id or "") or None
        contract.listing_id = str(offer.get("listing_id") or contract.listing_id or "") or None
        contract.quantity = _positive_int(offer.get("qty")) or contract.quantity
        contract.unit_price = _positive_float(offer.get("offered_price")) or contract.unit_price
        contract.payment_terms_days = _positive_int(offer.get("payment_terms_days")) or contract.payment_terms_days
        if contract.quantity and contract.unit_price:
            contract.total_price = round(contract.quantity * contract.unit_price, 2)
        self._index(contract)
        return [
            self._transition(
                contract,
                event_type="offer_withdrawn",
                status_after=ContractStatus.CANCELLED,
                action_name="withdraw_offer",
                day=context.get("day"),
                metadata={"result": result, "action_input": action_input},
            )
        ]

    def _from_pay_invoice(
        self,
        action_input: dict[str, Any],
        result: dict[str, Any],
        context: dict[str, Any],
    ) -> list[ContractAuditEvent]:
        invoice_id = str(action_input.get("invoice_id") or "")
        contract = self._find_by_invoice_or_context(invoice_id, context)
        if contract is None:
            contract = self._get_or_create(
                key=f"invoice:{invoice_id}",
                contract_id=f"ocl_invoice_{invoice_id}",
                invoice_id=invoice_id,
            )
        contract.invoice_id = invoice_id or contract.invoice_id
        self._hydrate_from_invoice_context(contract, context)
        self._index(contract)
        return [
            self._transition(
                contract,
                event_type="invoice_paid",
                status_after=ContractStatus.PAID,
                action_name="pay_invoice",
                day=context.get("day"),
                metadata={"result": result, "action_input": action_input},
            ),
            self._transition(
                contract,
                event_type="contract_closed",
                status_after=ContractStatus.CLOSED,
                action_name="pay_invoice",
                day=context.get("day"),
                metadata={"reason": "invoice settled"},
            ),
        ]

    def _from_return_shipment(
        self,
        action_input: dict[str, Any],
        result: dict[str, Any],
        context: dict[str, Any],
    ) -> list[ContractAuditEvent]:
        invoice_id = str(result.get("invoice_id") or action_input.get("invoice_id") or "")
        contract = self._find_by_invoice_or_context(invoice_id, context)
        if contract is None:
            contract = self._get_or_create(
                key=f"invoice:{invoice_id}",
                contract_id=f"ocl_invoice_{invoice_id}",
                invoice_id=invoice_id,
            )
        contract.deal_id = str(result.get("deal_id") or contract.deal_id or "") or None
        contract.invoice_id = invoice_id or contract.invoice_id
        self._hydrate_from_invoice_context(contract, context)
        self._index(contract)
        return [
            self._transition(
                contract,
                event_type="shipment_returned",
                status_after=ContractStatus.RETURNED,
                action_name="return_shipment",
                day=context.get("day"),
                metadata={"result": result, "action_input": action_input},
            )
        ]

    def _from_deal_delivered(self, data: dict[str, Any]) -> list[ContractAuditEvent]:
        deal_id = str(data.get("deal_id") or "")
        if not self._data_involves_focal(data):
            return []
        contract = self._find_by_deal(deal_id)
        if contract is None:
            contract = self._get_or_create(
                key=f"deal:{deal_id}",
                contract_id=f"ocl_deal_{deal_id}",
                deal_id=deal_id,
            )
        contract.seller_id = str(data.get("seller") or contract.seller_id or "") or None
        contract.buyer_id = str(data.get("buyer") or contract.buyer_id or "") or None
        contract.item_id = str(data.get("item_id") or contract.item_id or "") or None
        contract.quantity = _positive_int(data.get("qty")) or contract.quantity
        contract.unit_price = _positive_float(data.get("unit_price")) or contract.unit_price
        contract.total_price = _positive_float(data.get("total_price")) or contract.total_price
        contract.invoice_id = str(data.get("invoice_id") or contract.invoice_id or "") or None
        contract.delivery_day = _positive_int(data.get("day")) or contract.delivery_day
        self._index(contract)
        day = _positive_int(data.get("day"))
        return [
            self._transition(
                contract,
                event_type="shipment_delivered",
                status_after=ContractStatus.DELIVERED,
                coffee_event_type="deal_delivered",
                day=day,
                metadata=data,
            ),
            self._transition(
                contract,
                event_type="invoice_issued",
                status_after=ContractStatus.INVOICED,
                coffee_event_type="deal_delivered",
                day=day,
                metadata={"invoice_id": contract.invoice_id},
            ),
        ]

    def _from_shipment_delayed(self, data: dict[str, Any]) -> list[ContractAuditEvent]:
        contract = self._find_by_deal(str(data.get("deal_id") or ""))
        if contract is None:
            return []
        return [
            self._transition(
                contract,
                event_type="shipment_delayed",
                status_after=ContractStatus.SHIPMENT_DELAYED,
                coffee_event_type="shipment_delayed",
                day=_positive_int(data.get("day")),
                metadata=data,
            )
        ]

    def _from_shipment_lost(self, data: dict[str, Any]) -> list[ContractAuditEvent]:
        deal_id = str(data.get("deal_id") or "")
        if not self._data_involves_focal(data):
            return []
        contract = self._find_by_deal(deal_id)
        if contract is None:
            contract = self._get_or_create(
                key=f"deal:{deal_id}",
                contract_id=f"ocl_deal_{deal_id}",
                deal_id=deal_id,
            )
        contract.seller_id = str(data.get("seller") or contract.seller_id or "") or None
        contract.buyer_id = str(data.get("buyer") or contract.buyer_id or "") or None
        contract.item_id = str(data.get("item_id") or contract.item_id or "") or None
        self._index(contract)
        return [
            self._transition(
                contract,
                event_type="shipment_lost",
                status_after=ContractStatus.SHIPMENT_LOST,
                coffee_event_type="shipment_lost",
                day=_positive_int(data.get("day")),
                metadata=data,
            )
        ]

    def _find_by_deal(self, deal_id: str) -> OCLContract | None:
        contract_id = self.by_deal_id.get(deal_id)
        return self.contracts.get(contract_id) if contract_id else None

    def _data_involves_focal(self, data: dict[str, Any]) -> bool:
        return self.focal_agent_id in {
            str(data.get("seller") or ""),
            str(data.get("seller_id") or ""),
            str(data.get("buyer") or ""),
            str(data.get("buyer_id") or ""),
            str(data.get("issuer") or ""),
            str(data.get("payer") or ""),
        }

    def _find_by_invoice_or_context(
        self,
        invoice_id: str,
        context: dict[str, Any],
    ) -> OCLContract | None:
        contract_id = self.by_invoice_id.get(invoice_id)
        if contract_id:
            return self.contracts.get(contract_id)
        invoice = _asdict(context.get("invoice"))
        reference = str(invoice.get("reference") or "")
        if reference and reference in self.by_deal_id:
            return self.contracts[self.by_deal_id[reference]]
        return None

    def _hydrate_from_invoice_context(self, contract: OCLContract, context: dict[str, Any]) -> None:
        invoice = _asdict(context.get("invoice"))
        if not invoice:
            return
        contract.invoice_id = str(invoice.get("id") or contract.invoice_id or "") or None
        contract.deal_id = str(invoice.get("reference") or contract.deal_id or "") or None
        contract.buyer_id = str(invoice.get("payer") or contract.buyer_id or "") or None
        contract.seller_id = str(invoice.get("issuer") or contract.seller_id or "") or None
        contract.total_price = _positive_float(invoice.get("amount")) or contract.total_price
        contract.due_day = _positive_int(invoice.get("due_date")) or contract.due_day

    def _get_or_create(
        self,
        *,
        key: str,
        contract_id: str,
        offer_id: str | None = None,
        deal_id: str | None = None,
        invoice_id: str | None = None,
    ) -> OCLContract:
        existing_id = None
        if key.startswith("offer:") and offer_id:
            existing_id = self.by_offer_id.get(offer_id)
        elif key.startswith("deal:") and deal_id:
            existing_id = self.by_deal_id.get(deal_id)
        elif key.startswith("invoice:") and invoice_id:
            existing_id = self.by_invoice_id.get(invoice_id)
        if existing_id and existing_id in self.contracts:
            return self.contracts[existing_id]

        contract = OCLContract(contract_id=contract_id, focal_agent_id=self.focal_agent_id)
        contract.offer_id = offer_id
        contract.deal_id = deal_id
        contract.invoice_id = invoice_id
        self.contracts[contract.contract_id] = contract
        self._index(contract)
        return contract

    def _index(self, contract: OCLContract) -> None:
        if contract.offer_id:
            self.by_offer_id[contract.offer_id] = contract.contract_id
        if contract.deal_id:
            self.by_deal_id[contract.deal_id] = contract.contract_id
        if contract.invoice_id:
            self.by_invoice_id[contract.invoice_id] = contract.contract_id

    def _transition(
        self,
        contract: OCLContract,
        *,
        event_type: str,
        status_after: ContractStatus,
        action_name: str | None = None,
        coffee_event_type: str | None = None,
        day: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContractAuditEvent:
        before = contract.status
        event = ContractAuditEvent(
            event_type=event_type,
            day=day,
            actor_id=self.focal_agent_id,
            status_before=before,
            status_after=status_after,
            coffee_event_type=coffee_event_type,
            coffee_action_name=action_name,
            metadata=jsonable(metadata or {}),
        )
        contract.append_event(event)
        return event
