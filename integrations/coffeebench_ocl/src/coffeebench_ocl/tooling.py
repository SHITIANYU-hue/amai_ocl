"""Tool exposure plan for focal CoffeeBench OCL integration."""

from __future__ import annotations

from dataclasses import dataclass


FOCAL_AGENT_ID = "roaster_A"
FOCAL_ROLE = "roaster"

COMMON_COFFEEBENCH_TOOLS: tuple[str, ...] = (
    "post_listing",
    "view_listings",
    "make_offer",
    "withdraw_offer",
    "accept_offer",
    "view_offers",
    "view_deals",
    "send_message",
    "view_messages",
    "read_message",
    "view_payables",
    "view_receivables",
    "pay_invoice",
    "return_shipment",
    "view_trial_balance",
    "view_market_aggregate",
    "wait_for_next_day",
)

ROLE_TOOLS: dict[str, tuple[str, ...]] = {
    "farmer": ("produce_item",),
    "roaster": ("roast",),
    "retailer": ("set_retail_price", "view_consumer_sales"),
}

PROCUREMENT_TOOLS: tuple[str, ...] = (
    "make_offer",
    "withdraw_offer",
)

SALES_TOOLS: tuple[str, ...] = (
    "post_listing",
    "accept_offer",
)

SETTLEMENT_TOOLS: tuple[str, ...] = (
    "pay_invoice",
    "return_shipment",
)

PRODUCTION_TOOLS: tuple[str, ...] = ("roast",)

RAW_TRADE_TOOLS: tuple[str, ...] = (
    "make_offer",
    "withdraw_offer",
    "accept_offer",
    "pay_invoice",
    "return_shipment",
)

OPERATIONAL_CONTROL_TOOLS: tuple[str, ...] = (
    *PROCUREMENT_TOOLS,
    *SALES_TOOLS,
    *SETTLEMENT_TOOLS,
    *PRODUCTION_TOOLS,
)

OCL_LEDGER_TOOLS: tuple[str, ...] = (
    "view_ocl_ledger",
    "view_ocl_obligations",
)

OCL_CONTRACT_TOOLS: tuple[str, ...] = (
    "draft_purchase_contract",
    "validate_contract",
    "submit_contract_offer",
    "withdraw_contract_offer",
    "accept_contract_offer",
    "settle_due_contract",
    "return_contract_shipment",
)


@dataclass(frozen=True, slots=True)
class ToolExposurePlan:
    phase_id: int
    focal_agent_id: str
    role: str
    exposed_tools: tuple[str, ...]
    wrapped_tools: tuple[str, ...] = ()
    hidden_tools: tuple[str, ...] = ()
    added_tools: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def exposes(self, tool_name: str) -> bool:
        return tool_name in self.exposed_tools


def native_tools_for_role(role: str) -> tuple[str, ...]:
    return COMMON_COFFEEBENCH_TOOLS + ROLE_TOOLS.get(role, ())


def build_tool_exposure_plan(
    phase_id: int,
    *,
    focal_agent_id: str = FOCAL_AGENT_ID,
    role: str = FOCAL_ROLE,
) -> ToolExposurePlan:
    """Return the intended focal-agent tool surface for a phase.

    The numeric phases are implementation milestones. Scientific comparisons
    should use the capability arms in `phases.py`. OCL covers procurement,
    sales, settlement, and production actions, while read/message/wait tools
    remain native.
    """

    native = native_tools_for_role(role)

    if phase_id <= 0:
        return ToolExposurePlan(
            phase_id=phase_id,
            focal_agent_id=focal_agent_id,
            role=role,
            exposed_tools=native,
            notes=("No wrapper is installed in Phase 0.",),
        )
    if phase_id == 1:
        return ToolExposurePlan(
            phase_id=phase_id,
            focal_agent_id=focal_agent_id,
            role=role,
            exposed_tools=native,
            wrapped_tools=OPERATIONAL_CONTROL_TOOLS,
            notes=("Wrappers log operational actions but return native CoffeeBench results.",),
        )
    if phase_id == 2:
        added = OCL_LEDGER_TOOLS
        return ToolExposurePlan(
            phase_id=phase_id,
            focal_agent_id=focal_agent_id,
            role=role,
            exposed_tools=native + added,
            wrapped_tools=OPERATIONAL_CONTROL_TOOLS,
            added_tools=added,
            notes=("Ledger tools are read-only and must not provide strategy recommendations.",),
        )
    if phase_id == 3:
        added = OCL_LEDGER_TOOLS
        return ToolExposurePlan(
            phase_id=phase_id,
            focal_agent_id=focal_agent_id,
            role=role,
            exposed_tools=native + added,
            wrapped_tools=OPERATIONAL_CONTROL_TOOLS,
            added_tools=added,
            notes=("Validation runs in warning mode; CoffeeBench calls still execute.",),
        )

    hidden = RAW_TRADE_TOOLS
    added = OCL_LEDGER_TOOLS + OCL_CONTRACT_TOOLS
    exposed = tuple(t for t in native if t not in hidden) + added
    wrapped = tuple(t for t in OPERATIONAL_CONTROL_TOOLS if t not in hidden)
    return ToolExposurePlan(
        phase_id=phase_id,
        focal_agent_id=focal_agent_id,
        role=role,
        exposed_tools=exposed,
        wrapped_tools=wrapped,
        hidden_tools=hidden,
        added_tools=added,
        notes=(
            "Raw focal trade tools are hidden behind OCL contract tools.",
            "post_listing and roast keep native names but remain under OCL validation.",
        ),
    )
