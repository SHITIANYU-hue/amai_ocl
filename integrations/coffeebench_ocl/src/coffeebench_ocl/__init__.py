"""OCL adapter for the official CoffeeBench benchmark.

This package is intentionally a thin integration layer. It does not vendor,
fork, or rewrite CoffeeBench; it records the OCL-side contract, tool exposure
plan, and capability-arm definitions needed to attach OCL to the upstream
benchmark.
"""

from .contracts import (
    ContractAuditEvent,
    ContractStatus,
    OCLContract,
    ValidationResult,
    ValidationStatus,
)
from .audit import AuditPaths, PassiveOCLAuditLogger
from .lifecycle import ContractLifecycle
from .phases import (
    OCL_CAPABILITY_ARMS,
    PHASES,
    ExperimentPhase,
    OCLCapabilityArm,
    resolve_capability_arm,
)
from .qwen_model import DashScopeQwenModel, install_qwen_provider, is_qwen_model_id
from .runtime import CoffeeBenchOCLRuntime, attach_ocl_runtime
from .shim import CoffeeBenchProbeResult, build_phase0_report, probe_coffeebench
from .tooling import ToolExposurePlan, build_tool_exposure_plan
from .validation import ValidationMode, ValidationPolicy, validate_operational_action

__all__ = [
    "AuditPaths",
    "CoffeeBenchOCLRuntime",
    "ContractLifecycle",
    "ContractAuditEvent",
    "ContractStatus",
    "CoffeeBenchProbeResult",
    "DashScopeQwenModel",
    "ExperimentPhase",
    "OCLCapabilityArm",
    "OCL_CAPABILITY_ARMS",
    "OCLContract",
    "PHASES",
    "PassiveOCLAuditLogger",
    "ToolExposurePlan",
    "ValidationResult",
    "ValidationStatus",
    "ValidationMode",
    "ValidationPolicy",
    "attach_ocl_runtime",
    "build_phase0_report",
    "build_tool_exposure_plan",
    "install_qwen_provider",
    "is_qwen_model_id",
    "probe_coffeebench",
    "resolve_capability_arm",
    "validate_operational_action",
]
