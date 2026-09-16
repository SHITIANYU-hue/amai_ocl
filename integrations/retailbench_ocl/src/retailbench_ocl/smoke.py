"""Real RetailBench -> OCL -> RetailBench minimal smoke test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .adapter import RetailBenchOCL
from .configuration import RetailBenchV2Config, build_retailbench_v2_runtime
from .loader import MINIMAL_SKU, load_minimal_environment
from .policy import RetailGovernancePolicy


def run_smoke(retailbench_root: str | Path) -> dict[str, Any]:
    with load_minimal_environment(retailbench_root) as environment:
        policy = RetailGovernancePolicy()
        runtime = build_retailbench_v2_runtime(
            RetailBenchV2Config(
                evaluator_mode="lexical",
                organizational_policy=policy,
            )
        )
        controlled = RetailBenchOCL(environment, runtime=runtime, policy=policy)

        quotes = controlled.exec_tools(
            "view_current_date_supplier_prices", sku_ids=[MINIMAL_SKU]
        )
        entries = quotes.get("result", {}).get(MINIMAL_SKU, [])
        if not entries:
            raise RuntimeError(f"RetailBench returned no supplier quote for {MINIMAL_SKU}")
        supplier_id = entries[0]["supplier_id"]
        order = {
            "items": [{"sku_id": MINIMAL_SKU, "quantity": 1}],
            "supplier_id": supplier_id,
        }

        blocked = controlled.exec_tools("place_order", **order)
        if blocked.get("ocl", {}).get("decision") != "block":
            raise AssertionError("OCL should block an order missing required evidence")

        controlled.exec_tools("view_inventory")
        controlled.exec_tools("view_funds_and_date")
        current_day = str(environment.current_date)
        controlled.exec_tools(
            "view_sku_sales_history",
            sku_ids=[MINIMAL_SKU],
            start_date=current_day,
            end_date=current_day,
        )
        controlled.exec_tools("view_current_orders")

        capacity = environment.inventory.capacity
        capacity_blocked = controlled.exec_tools(
            "place_order",
            items=[{"sku_id": MINIMAL_SKU, "quantity": capacity + 1}],
            supplier_id=supplier_id,
        )
        capacity_checks = {
            check.check_id
            for check in controlled.last_result.decision.checks
            if not check.passed
        }
        if "retailbench.policy.inventory_capacity" not in capacity_checks:
            raise AssertionError("OCL should enforce the added inventory-capacity policy")

        controlled.exec_tools("view_sku_prices", sku_ids=[MINIMAL_SKU])
        price_blocked = controlled.exec_tools(
            "modify_sku_price",
            sku_id=MINIMAL_SKU,
            new_price=float(entries[0]["price"]) / 2,
        )
        price_checks = {
            check.check_id
            for check in controlled.last_result.decision.checks
            if not check.passed
        }
        if "retailbench.policy.price_floor" not in price_checks:
            raise AssertionError("OCL should enforce the added procurement-price floor")

        approved = controlled.exec_tools("place_order", **order)
        if approved.get("ocl", {}).get("decision") != "approve":
            raise AssertionError("OCL should approve the order after evidence collection")
        if "order_id" not in approved.get("result", {}):
            raise AssertionError("Approved call did not execute RetailBench place_order")

        return {
            "status": "passed",
            "retailbench_tools": len(controlled.get_tools()),
            "sku_id": MINIMAL_SKU,
            "supplier_id": supplier_id,
            "blocked": {
                "decision": blocked["ocl"]["decision"],
                "missing_evidence": blocked["ocl"]["missing_evidence"],
            },
            "policy_blocks": {
                "inventory_capacity": capacity_blocked["ocl"]["decision"],
                "price_floor": price_blocked["ocl"]["decision"],
            },
            "approved": {
                "decision": approved["ocl"]["decision"],
                "order_id": approved["result"]["order_id"],
                "funds_after": approved["result"]["funds_after"],
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a real one-SKU RetailBench/OCL smoke test"
    )
    parser.add_argument(
        "--retailbench-root",
        required=True,
        help="Path to an external Ice-Moon-28/RetailBench checkout",
    )
    args = parser.parse_args()
    print(json.dumps(run_smoke(args.retailbench_root), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
