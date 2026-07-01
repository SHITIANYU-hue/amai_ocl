"""Milestone and capability-arm definitions for CoffeeBench OCL experiments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExperimentPhase:
    phase_id: int
    name: str
    objective: str
    behavior_change: str
    coffee_patch_required: bool
    acceptance_criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OCLCapabilityArm:
    """Scientific comparison arm.

    These arms are the experiment design. `PHASES` below are implementation
    milestones and should not be treated as the ablation taxonomy.
    """

    name: str
    label: str
    description: str
    validation_mode: str = "audit"
    exposes_ledger_tools: bool = False
    exposes_contract_tools: bool = False
    hides_raw_trade_tools: bool = False


PHASES: tuple[ExperimentPhase, ...] = (
    ExperimentPhase(
        phase_id=0,
        name="Feasibility shim",
        objective=(
            "Create a standalone benchmark package and verify that CoffeeBench "
            "can be integrated through focal-agent tool wrapping."
        ),
        behavior_change="None. No CoffeeBench run behavior should change.",
        coffee_patch_required=False,
        acceptance_criteria=(
            "CoffeeBench is treated as an optional external dependency.",
            "The focal roaster tool exposure plan is explicit and testable.",
            "The later experiment phases are documented before implementation.",
        ),
    ),
    ExperimentPhase(
        phase_id=1,
        name="OCL-Log",
        objective=(
            "Convert CoffeeBench native events and focal tool calls into an "
            "OCL lifecycle audit stream without changing any tool result."
        ),
        behavior_change="No semantic behavior change; passive logging only.",
        coffee_patch_required=True,
        acceptance_criteria=(
            "A baseline run and OCL-log run produce equivalent CoffeeBench outcomes.",
            "Offer, deal, delivery, invoice, payment, loss, and delay events are linkable.",
        ),
    ),
    ExperimentPhase(
        phase_id=2,
        name="OCL-Ledger",
        objective=(
            "Expose structured operational memory through view_ocl_ledger and "
            "view_ocl_obligations for roaster_A."
        ),
        behavior_change="Adds read-only tools for the focal agent.",
        coffee_patch_required=True,
        acceptance_criteria=(
            "Ledger views agree with CoffeeBench AP, AR, offers, deals, and pending shipments.",
            "The tools provide no direct recommendation of price, supplier, or strategy.",
        ),
    ),
    ExperimentPhase(
        phase_id=3,
        name="OCL-Validation Warning",
        objective=(
            "Run feasibility and risk validation around focal operational actions, "
            "recording warnings while still forwarding the original CoffeeBench call."
        ),
        behavior_change="Warnings are visible/audited, but actions still execute.",
        coffee_patch_required=True,
        acceptance_criteria=(
            "Invalid or risky actions are detected before CoffeeBench returns its native result.",
            "Warning mode preserves CoffeeBench execution semantics.",
        ),
    ),
    ExperimentPhase(
        phase_id=4,
        name="OCL-Contract Interface",
        objective=(
            "Hide focal raw trade tools and route purchase, withdrawal, accept, "
            "settle, and return flows through OCL contract tools while validating "
            "sale listings and production through native CoffeeBench tool names."
        ),
        behavior_change="Focal trade interface changes; CoffeeBench environment logic does not.",
        coffee_patch_required=True,
        acceptance_criteria=(
            "roaster_A can buy, accept offers, settle AP, and return shipments via OCL tools.",
            "post_listing and roast remain callable but are checked by OCL validation.",
        ),
    ),
    ExperimentPhase(
        phase_id=5,
        name="OCL-Blocking",
        objective=(
            "Enable blocking for clearly infeasible or high-risk focal actions "
            "after warning-mode validation has been calibrated."
        ),
        behavior_change="Some focal actions are blocked before reaching CoffeeBench.",
        coffee_patch_required=True,
        acceptance_criteria=(
            "Blocked cases are explainable and reproducible.",
            "Blocking reduces invalid/risky action rate without breaking routine commerce.",
        ),
    ),
    ExperimentPhase(
        phase_id=6,
        name="Full ablation",
        objective="Run the B0-B5 comparison on fixed seeds and fixed CoffeeBench configs.",
        behavior_change="Depends on selected arm.",
        coffee_patch_required=True,
        acceptance_criteria=(
            "Short-horizon smoke runs pass before any 90-day LLM run.",
            "Metrics include CoffeeBench native outcomes and OCL reliability/audit outcomes.",
        ),
    ),
)


OCL_CAPABILITY_ARMS: tuple[OCLCapabilityArm, ...] = (
    OCLCapabilityArm(
        name="B0",
        label="CoffeeBench baseline",
        description="Original CoffeeBench focal roaster setup.",
    ),
    OCLCapabilityArm(
        name="B1",
        label="OCL-Audit",
        description="Passive audit and lifecycle reconstruction only.",
    ),
    OCLCapabilityArm(
        name="B2",
        label="OCL-Memory",
        description="Passive audit plus read-only ledger and obligation tools.",
        exposes_ledger_tools=True,
    ),
    OCLCapabilityArm(
        name="B3",
        label="OCL-Warning",
        description="Warning-mode validation for operational actions.",
        validation_mode="warning",
        exposes_ledger_tools=True,
    ),
    OCLCapabilityArm(
        name="B4",
        label="OCL-Blocking",
        description="Blocking validation for clearly infeasible operational actions.",
        validation_mode="blocking",
        exposes_ledger_tools=True,
    ),
    OCLCapabilityArm(
        name="B5",
        label="OCL-Contract Interface",
        description="Contract tools replace raw trade tools for focal trade execution.",
        validation_mode="blocking",
        exposes_ledger_tools=True,
        exposes_contract_tools=True,
        hides_raw_trade_tools=True,
    ),
)


def resolve_capability_arm(name: str) -> OCLCapabilityArm:
    for arm in OCL_CAPABILITY_ARMS:
        if arm.name == name:
            return arm
    available = ", ".join(arm.name for arm in OCL_CAPABILITY_ARMS)
    raise ValueError(f"Unknown CoffeeBench OCL arm '{name}'. Available: {available}")
