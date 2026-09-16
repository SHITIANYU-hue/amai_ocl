"""External organizational policy added by the RetailBench OCL integration.

RetailBench defines the retail economy.  This module deliberately keeps the
experiment's governance policy separate so results never present an OCL rule as
an upstream benchmark invariant.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_ORDER_EVIDENCE = (
    "view_current_date_supplier_prices",
    "view_inventory",
    "view_funds_and_date",
    "view_sku_sales_history",
    "view_current_orders",
)
DEFAULT_PRICE_EVIDENCE = (
    "view_sku_prices",
    "view_inventory",
    "view_sku_sales_history",
    "view_current_date_supplier_prices",
)


@dataclass(frozen=True, slots=True)
class RetailGovernancePolicy:
    """A declared policy profile layered on top of RetailBench.

    The numerical values are experimental organizational choices, not native
    RetailBench rules and not claims about an economically optimal strategy.
    """

    policy_id: str = "retailbench_ocl_minimal_v1"
    reserve_rent_days: float = 3.0
    enforce_inventory_capacity: bool = True
    minimum_markup_fraction: float = 0.0
    large_price_change_fraction: float = 0.5
    order_required_evidence: tuple[str, ...] = DEFAULT_ORDER_EVIDENCE
    price_required_evidence: tuple[str, ...] = DEFAULT_PRICE_EVIDENCE

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must be a non-empty string")
        if self.reserve_rent_days < 0:
            raise ValueError("reserve_rent_days must be non-negative")
        if self.minimum_markup_fraction < 0:
            raise ValueError("minimum_markup_fraction must be non-negative")
        if self.large_price_change_fraction <= 0:
            raise ValueError("large_price_change_fraction must be greater than zero")
        for name, values in (
            ("order_required_evidence", self.order_required_evidence),
            ("price_required_evidence", self.price_required_evidence),
        ):
            if not values or any(not isinstance(item, str) or not item.strip() for item in values):
                raise ValueError(f"{name} must contain non-empty tool names")

    def required_evidence(self, tool_name: str) -> tuple[str, ...]:
        if tool_name == "place_order":
            return self.order_required_evidence
        if tool_name == "modify_sku_price":
            return self.price_required_evidence
        return ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_origin": "retailbench_ocl_extension",
            "reserve_rent_days": self.reserve_rent_days,
            "enforce_inventory_capacity": self.enforce_inventory_capacity,
            "minimum_markup_fraction": self.minimum_markup_fraction,
            "large_price_change_fraction": self.large_price_change_fraction,
            "required_evidence": {
                "place_order": list(self.order_required_evidence),
                "modify_sku_price": list(self.price_required_evidence),
            },
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RetailGovernancePolicy":
        evidence = payload.get("required_evidence", {})
        if not isinstance(evidence, Mapping):
            raise ValueError("required_evidence must be an object")
        return cls(
            policy_id=str(payload.get("policy_id", "retailbench_ocl_minimal_v1")),
            reserve_rent_days=float(payload.get("reserve_rent_days", 3.0)),
            enforce_inventory_capacity=bool(
                payload.get("enforce_inventory_capacity", True)
            ),
            minimum_markup_fraction=float(payload.get("minimum_markup_fraction", 0.0)),
            large_price_change_fraction=float(
                payload.get("large_price_change_fraction", 0.5)
            ),
            order_required_evidence=tuple(
                evidence.get("place_order", DEFAULT_ORDER_EVIDENCE)
            ),
            price_required_evidence=tuple(
                evidence.get("modify_sku_price", DEFAULT_PRICE_EVIDENCE)
            ),
        )


def load_retail_governance_policy(
    path: str | Path | None,
) -> RetailGovernancePolicy:
    """Load an OCL policy profile; no path selects the documented default."""
    if path is None:
        return RetailGovernancePolicy()
    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("retail governance policy must be a JSON object")
    return RetailGovernancePolicy.from_dict(payload)
