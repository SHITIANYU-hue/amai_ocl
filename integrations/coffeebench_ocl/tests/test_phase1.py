"""Phase-1 passive lifecycle and audit tests."""

from __future__ import annotations

import json

from coffeebench_ocl.audit import PassiveOCLAuditLogger
from coffeebench_ocl.contracts import ContractStatus, ValidationResult, ValidationStatus
from coffeebench_ocl.lifecycle import ContractLifecycle


def test_lifecycle_links_outgoing_offer_accept_delivery_and_payment() -> None:
    lifecycle = ContractLifecycle(focal_agent_id="roaster_A")

    lifecycle.process_tool_call(
        action_name="make_offer",
        action_input={
            "listing_id": "lst_1",
            "offered_price": 3.25,
            "qty": 10,
            "payment_terms_days": 30,
        },
        result={"status": "success", "offer_id": "off_1", "seller_id": "farmer_A"},
        context={
            "agent_id": "roaster_A",
            "day": 1,
            "listing": {"id": "lst_1", "seller_id": "farmer_A", "item_id": "green_coffee_kg"},
        },
    )
    lifecycle.process_tool_call(
        action_name="accept_offer",
        action_input={"offer_id": "off_1"},
        result={
            "status": "success",
            "deal_id": "dl_1",
            "buyer_id": "roaster_A",
            "item_id": "green_coffee_kg",
            "qty": 10,
            "unit_price": 3.25,
            "total_price": 32.5,
            "payment_terms_days": 30,
            "delivery_day": 2,
        },
        context={"agent_id": "farmer_A", "day": 1, "source": "coffee_agent_step"},
    )
    lifecycle.process_coffee_event(
        event_type="deal_delivered",
        data={
            "day": 2,
            "deal_id": "dl_1",
            "seller": "farmer_A",
            "buyer": "roaster_A",
            "item_id": "green_coffee_kg",
            "qty": 10,
            "unit_price": 3.25,
            "total_price": 32.5,
            "invoice_id": "inv_1",
        },
    )
    lifecycle.process_tool_call(
        action_name="pay_invoice",
        action_input={"invoice_id": "inv_1"},
        result={"status": "success", "paid_amount": 32.5},
        context={
            "agent_id": "roaster_A",
            "day": 32,
            "invoice": {
                "id": "inv_1",
                "issuer": "farmer_A",
                "payer": "roaster_A",
                "amount": 32.5,
                "due_date": 32,
                "reference": "dl_1",
            },
        },
    )

    assert len(lifecycle.contracts) == 1
    contract = next(iter(lifecycle.contracts.values()))
    assert contract.offer_id == "off_1"
    assert contract.deal_id == "dl_1"
    assert contract.invoice_id == "inv_1"
    assert contract.status is ContractStatus.CLOSED
    assert lifecycle.metrics()["link_counts"] == {"offer": 1, "deal": 1, "invoice": 1}


def test_lifecycle_ignores_unrelated_delivery() -> None:
    lifecycle = ContractLifecycle(focal_agent_id="roaster_A")

    transitions = lifecycle.process_coffee_event(
        event_type="deal_delivered",
        data={
            "day": 2,
            "deal_id": "dl_other",
            "seller": "farmer_A",
            "buyer": "retailer_A",
            "item_id": "green_coffee_kg",
            "qty": 10,
        },
    )

    assert transitions == []
    assert lifecycle.contracts == {}


def test_lifecycle_marks_withdrawn_offer_cancelled() -> None:
    lifecycle = ContractLifecycle(focal_agent_id="roaster_A")

    lifecycle.process_tool_call(
        action_name="make_offer",
        action_input={
            "listing_id": "lst_1",
            "offered_price": 3.25,
            "qty": 10,
            "payment_terms_days": 30,
        },
        result={"status": "success", "offer_id": "off_1", "seller_id": "farmer_A"},
        context={
            "agent_id": "roaster_A",
            "day": 1,
            "listing": {"id": "lst_1", "seller_id": "farmer_A", "item_id": "green_coffee_kg"},
        },
    )
    lifecycle.process_tool_call(
        action_name="withdraw_offer",
        action_input={"offer_id": "off_1"},
        result={"status": "success", "message": "Offer withdrawn."},
        context={
            "agent_id": "roaster_A",
            "day": 2,
            "offer": {
                "id": "off_1",
                "listing_id": "lst_1",
                "buyer_id": "roaster_A",
                "seller_id": "farmer_A",
                "offered_price": 3.25,
                "qty": 10,
                "payment_terms_days": 30,
            },
        },
    )

    contract = lifecycle.contracts["ocl_offer_off_1"]
    assert contract.status is ContractStatus.CANCELLED
    assert contract.is_terminal


def test_audit_logger_processes_non_focal_accept_of_focal_offer(tmp_path) -> None:
    logger = PassiveOCLAuditLogger(events_path=tmp_path / "run.ocl.jsonl")
    try:
        logger.record_coffee_event(
            "agent_step",
            {
                "agent_id": "farmer_A",
                "day": 1,
                "action": "accept_offer",
                "action_input": {"offer_id": "off_1"},
                "observation": {
                    "status": "success",
                    "deal_id": "dl_1",
                    "buyer_id": "roaster_A",
                    "item_id": "green_coffee_kg",
                    "qty": 10,
                    "unit_price": 3.25,
                    "total_price": 32.5,
                    "payment_terms_days": 30,
                    "delivery_day": 2,
                },
            },
        )
        outputs = logger.save_outputs()
    finally:
        logger.close()

    assert outputs["summary"]["contract_count"] == 1
    records = (tmp_path / "run.ocl.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line)["type"] == "ocl_contract_event" for line in records)


def test_audit_summary_counts_validation_and_blocks(tmp_path) -> None:
    logger = PassiveOCLAuditLogger(events_path=tmp_path / "run.ocl.jsonl")
    try:
        logger.emit(
            "ocl_validation",
            action="post_listing",
            validation=ValidationResult(status=ValidationStatus.FAIL),
        )
        logger.record_tool_call(
            action_name="post_listing",
            action_input={"item_id": "roasted_coffee_kg", "qty": 999, "asking_price": 8.0},
            result={"status": "error", "ocl_decision": "block"},
            context={"day": 0},
        )
        outputs = logger.save_outputs()
    finally:
        logger.close()

    summary = outputs["summary"]
    assert summary["validation_counts"]["fail"] == 1
    assert summary["blocked_action_count"] == 1
    assert summary["tool_call_counts"]["post_listing"] == 1
