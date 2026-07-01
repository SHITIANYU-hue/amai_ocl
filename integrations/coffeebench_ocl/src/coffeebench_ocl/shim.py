"""CoffeeBench integration probe.

This module deliberately avoids importing CoffeeBench at package import time.
The upstream benchmark is an optional external dependency and should remain
owned by its official repository.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib
from typing import Any

from .phases import OCL_CAPABILITY_ARMS, PHASES
from .tooling import (
    COMMON_COFFEEBENCH_TOOLS,
    FOCAL_AGENT_ID,
    FOCAL_ROLE,
    RAW_TRADE_TOOLS,
    ROLE_TOOLS,
    build_tool_exposure_plan,
)


@dataclass(frozen=True, slots=True)
class CoffeeBenchProbeResult:
    available: bool
    module_prefix: str
    version: str | None = None
    common_tools_present: tuple[str, ...] = ()
    common_tools_missing: tuple[str, ...] = ()
    role_tools_present: tuple[str, ...] = ()
    role_tools_missing: tuple[str, ...] = ()
    error: str | None = None

    @property
    def integration_ready(self) -> bool:
        return self.available and not self.common_tools_missing and not self.role_tools_missing

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["integration_ready"] = self.integration_ready
        return data


def probe_coffeebench(module_prefix: str = "coffeebench") -> CoffeeBenchProbeResult:
    """Inspect the installed CoffeeBench package without running a simulation."""

    try:
        package = importlib.import_module(module_prefix)
        main = importlib.import_module(f"{module_prefix}.main")
    except Exception as exc:  # pragma: no cover - exact import error varies
        return CoffeeBenchProbeResult(
            available=False,
            module_prefix=module_prefix,
            error=f"{type(exc).__name__}: {exc}",
        )

    native_common = tuple(getattr(main, "COMMON_TOOL_NAMES", ()))
    native_role_map = dict(getattr(main, "ROLE_TOOL_NAMES", {}))
    native_role = tuple(native_role_map.get(FOCAL_ROLE, ()))

    common_present = tuple(t for t in COMMON_COFFEEBENCH_TOOLS if t in native_common)
    common_missing = tuple(t for t in COMMON_COFFEEBENCH_TOOLS if t not in native_common)
    expected_role_tools = ROLE_TOOLS[FOCAL_ROLE]
    role_present = tuple(t for t in expected_role_tools if t in native_role)
    role_missing = tuple(t for t in expected_role_tools if t not in native_role)

    return CoffeeBenchProbeResult(
        available=True,
        module_prefix=module_prefix,
        version=getattr(package, "__version__", None),
        common_tools_present=common_present,
        common_tools_missing=common_missing,
        role_tools_present=role_present,
        role_tools_missing=role_missing,
    )


def build_phase0_report(module_prefix: str = "coffeebench") -> dict[str, Any]:
    """Build a JSON-serializable feasibility report for the scaffold."""

    probe = probe_coffeebench(module_prefix=module_prefix)
    return {
        "integration": "coffeebench_ocl",
        "upstream_benchmark": "CoffeeBench",
        "focal_agent_id": FOCAL_AGENT_ID,
        "focal_role": FOCAL_ROLE,
        "coffee_probe": probe.to_dict(),
        "raw_trade_tools_to_wrap": RAW_TRADE_TOOLS,
        "phase0_tool_plan": build_tool_exposure_plan(0).exposed_tools,
        "phase_count": len(PHASES),
        "capability_arm_count": len(OCL_CAPABILITY_ARMS),
        "next_required_step": (
            "Install or place CoffeeBench on PYTHONPATH, then run a short-horizon "
            "passive or heuristic_roaster smoke simulation with this adapter."
        ),
    }
