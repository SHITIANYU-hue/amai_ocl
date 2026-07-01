"""Phase-0 scaffold tests for CoffeeBench OCL."""

from __future__ import annotations

from coffeebench_ocl.contracts import ContractAuditEvent, ContractStatus, OCLContract
from coffeebench_ocl.phases import OCL_CAPABILITY_ARMS, PHASES
from coffeebench_ocl.shim import probe_coffeebench
from coffeebench_ocl.tooling import OPERATIONAL_CONTROL_TOOLS, RAW_TRADE_TOOLS, build_tool_exposure_plan


def test_phase_ids_are_unique_and_ordered() -> None:
    phase_ids = [phase.phase_id for phase in PHASES]

    assert phase_ids == sorted(phase_ids)
    assert len(phase_ids) == len(set(phase_ids))
    assert phase_ids[0] == 0


def test_capability_arms_are_scientific_ablation_surface() -> None:
    names = [arm.name for arm in OCL_CAPABILITY_ARMS]

    assert names == ["B0", "B1", "B2", "B3", "B4", "B5"]
    assert OCL_CAPABILITY_ARMS[-1].hides_raw_trade_tools


def test_phase0_keeps_native_trade_tools_visible() -> None:
    plan = build_tool_exposure_plan(0)

    for tool_name in RAW_TRADE_TOOLS:
        assert plan.exposes(tool_name)
    assert not plan.hidden_tools
    assert not plan.wrapped_tools


def test_operational_scope_covers_sales_procurement_settlement_and_production() -> None:
    assert set(OPERATIONAL_CONTROL_TOOLS) == {
        "post_listing",
        "make_offer",
        "withdraw_offer",
        "accept_offer",
        "pay_invoice",
        "return_shipment",
        "roast",
    }


def test_phase4_hides_raw_trade_tools_but_keeps_post_listing() -> None:
    plan = build_tool_exposure_plan(4)

    for tool_name in RAW_TRADE_TOOLS:
        assert not plan.exposes(tool_name)
        assert tool_name in plan.hidden_tools
    assert plan.exposes("post_listing")
    assert "post_listing" in plan.wrapped_tools
    assert "roast" in plan.wrapped_tools
    assert plan.exposes("draft_purchase_contract")
    assert plan.exposes("view_ocl_ledger")


def test_contract_updates_status_from_audit_event() -> None:
    contract = OCLContract(contract_id="ocl_1", focal_agent_id="roaster_A")

    contract.append_event(
        ContractAuditEvent(
            event_type="contract_validated",
            status_before=ContractStatus.DRAFTED,
            status_after=ContractStatus.VALIDATED,
        )
    )

    assert contract.status is ContractStatus.VALIDATED
    assert not contract.is_terminal


def test_probe_reports_missing_nonexistent_module_cleanly() -> None:
    result = probe_coffeebench("definitely_missing_coffeebench_module")

    assert not result.available
    assert not result.integration_ready
    assert result.error
