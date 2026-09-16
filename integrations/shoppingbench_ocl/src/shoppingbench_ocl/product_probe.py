"""Exercise ShoppingBench's real product-agent loop with a tiny local fixture.

The probe deliberately keeps ShoppingBench external. It imports the upstream
``run_rollout`` module, replaces only its product I/O tools with deterministic
fixture implementations, and leaves the upstream prompt, message parser, tool
dispatcher, and LLM loop untouched.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Sequence
from uuid import uuid4


REQUIRED_TOOLS = (
    "find_product",
    "view_product_information",
    "recommend_product",
    "terminate",
)

QUERY = (
    "I need one red running shoe for daily road running, under $100. "
    "Recommend exactly one product that satisfies all requirements."
)

PRODUCTS = (
    {
        "product_id": "red-runner-001",
        "shop_id": "shop-a",
        "title": "Red Lightweight Running Shoes",
        "price": 79.0,
        "service": "freeShipping",
        "sold_count": 120,
    },
    {
        "product_id": "blue-runner-002",
        "shop_id": "shop-b",
        "title": "Blue Road Running Shoes",
        "price": 69.0,
        "service": "freeShipping",
        "sold_count": 95,
    },
    {
        "product_id": "red-hiker-003",
        "shop_id": "shop-c",
        "title": "Red Hiking Boots",
        "price": 89.0,
        "service": "COD",
        "sold_count": 50,
    },
)


@dataclass(frozen=True)
class ProbeCompatibility:
    shoppingbench_root: str
    upstream_commit: str | None
    run_rollout: str
    system_prompt: str
    required_tools: tuple[str, ...]
    compatible: bool


def _resolved_root(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    required = (
        root / "src" / "agent" / "run_rollout.py",
        root / "src" / "agent" / "prompt" / "rollout.md",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "ShoppingBench root is missing required files: " + ", ".join(missing)
        )
    return root


def _upstream_commit(root: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _load_upstream(root: Path) -> Any:
    agent_dir = root / "src" / "agent"
    agent_path = str(agent_dir)
    if agent_path not in sys.path:
        sys.path.insert(0, agent_path)

    existing = sys.modules.get("run_rollout")
    if existing is not None:
        loaded_from = Path(existing.__file__).resolve()
        expected = (agent_dir / "run_rollout.py").resolve()
        if loaded_from != expected:
            raise RuntimeError(
                f"run_rollout is already imported from {loaded_from}, expected {expected}"
            )
        module = existing
    else:
        module = importlib.import_module("run_rollout")

    missing_tools = [name for name in REQUIRED_TOOLS if name not in module.toolmap]
    if missing_tools:
        raise RuntimeError(
            "ShoppingBench toolmap is missing required tools: "
            + ", ".join(missing_tools)
        )
    return module


def inspect_upstream(shoppingbench_root: str | Path) -> ProbeCompatibility:
    root = _resolved_root(shoppingbench_root)
    module = _load_upstream(root)
    return ProbeCompatibility(
        shoppingbench_root=str(root),
        upstream_commit=_upstream_commit(root),
        run_rollout=str(Path(module.__file__).resolve()),
        system_prompt=str((root / "src" / "agent" / "prompt" / "rollout.md")),
        required_tools=REQUIRED_TOOLS,
        compatible=True,
    )


def _install_fixture_tools(
    module: Any, calls: list[dict[str, Any]]
) -> dict[type, Callable[..., Any]]:
    def fake_find(_self: Any, **kwargs: Any) -> list[dict[str, Any]]:
        calls.append({"name": "find_product", "parameters": dict(kwargs)})
        return [dict(product) for product in PRODUCTS]

    def fake_view(_self: Any, **kwargs: Any) -> list[dict[str, Any]]:
        calls.append(
            {"name": "view_product_information", "parameters": dict(kwargs)}
        )
        requested = {
            item.strip()
            for item in str(kwargs.get("product_ids", "")).split(",")
            if item.strip()
        }
        details = []
        for product in PRODUCTS:
            if product["product_id"] not in requested:
                continue
            details.append(
                {
                    **product,
                    "description": "Breathable daily running shoe.",
                    "sku & attrs": {
                        "color": (
                            "blue"
                            if product["product_id"] == "blue-runner-002"
                            else "red"
                        ),
                        "category": (
                            "hiking boots"
                            if product["product_id"] == "red-hiker-003"
                            else "running shoes"
                        ),
                    },
                }
            )
        return details

    def recording_recommend(_self: Any, **kwargs: Any) -> str:
        calls.append({"name": "recommend_product", "parameters": dict(kwargs)})
        return (
            "Having recommended the products to the user: "
            f"{kwargs.get('product_ids', '')}."
        )

    def recording_terminate(_self: Any, **kwargs: Any) -> str:
        calls.append({"name": "terminate", "parameters": dict(kwargs)})
        return (
            "The interaction has been completed with status: "
            f"{kwargs.get('status', '')}."
        )

    replacements = {
        "find_product": fake_find,
        "view_product_information": fake_view,
        "recommend_product": recording_recommend,
        "terminate": recording_terminate,
    }
    originals: dict[type, Callable[..., Any]] = {}
    for name, replacement in replacements.items():
        tool_class = type(module.toolmap[name])
        originals[tool_class] = tool_class.execute
        tool_class.execute = replacement
    return originals


def _restore_tools(originals: dict[type, Callable[..., Any]]) -> None:
    for tool_class, execute in originals.items():
        tool_class.execute = execute


def _new_output_dir(base: Path | None) -> Path:
    if base is not None:
        output = base.expanduser().resolve()
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = (
            Path.cwd()
            / "outputs"
            / "shoppingbench_ocl"
            / "product_probe"
            / f"{run_id}-{uuid4().hex[:8]}"
        )
    output.mkdir(parents=True, exist_ok=False)
    return output


def _tool_calls(trajectory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        call
        for step in trajectory
        for call in step["completion"]["message"].get("tool_call", [])
    ]


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    compatibility = inspect_upstream(args.shoppingbench_root)
    if args.check_only:
        return {"mode": "check-only", **asdict(compatibility)}

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    if not os.getenv("OPENAI_API_KEY") and not args.api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured; use --check-only for an offline check"
        )

    module = _load_upstream(Path(compatibility.shoppingbench_root))
    output_dir = _new_output_dir(args.output_dir)
    rollout_path = output_dir / "rollout.jsonl"
    fixture_calls: list[dict[str, Any]] = []
    originals = _install_fixture_tools(module, fixture_calls)
    old_max_steps = module.MAX_STEPS
    module.MAX_STEPS = args.max_steps
    try:
        config = {
            "task": "product",
            "system_prompt_file": compatibility.system_prompt,
            "rollout_file": str(rollout_path),
            "exclude_tools": ["web_search"],
            "model_config": {
                "model": args.model,
                "temperature": 0,
                "max_tokens": args.max_tokens,
            },
        }
        if args.base_url:
            config["base_url"] = args.base_url
        if args.api_key:
            config["api_key"] = args.api_key
        module.react_loop(QUERY, config)
    finally:
        module.MAX_STEPS = old_max_steps
        _restore_tools(originals)

    trajectory = json.loads(rollout_path.read_text(encoding="utf-8").splitlines()[-1])
    calls = _tool_calls(trajectory)
    recommendations = [
        call["parameters"].get("product_ids")
        for call in calls
        if call["name"] == "recommend_product"
    ]
    succeeded = bool(recommendations) and recommendations[-1] == "red-runner-001"
    report = {
        "mode": "live",
        "shoppingbench_root": compatibility.shoppingbench_root,
        "upstream_commit": compatibility.upstream_commit,
        "model": args.model,
        "query": QUERY,
        "steps": len(trajectory),
        "tool_names": [call["name"] for call in calls],
        "recommendations": recommendations,
        "fixture_calls": fixture_calls,
        "rollout_file": str(rollout_path),
        "succeeded": succeeded,
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a minimal product episode through official ShoppingBench code."
    )
    parser.add_argument(
        "--shoppingbench-root",
        required=True,
        help="Path to an external checkout of yjwjy/ShoppingBench.",
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=1000)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_probe(args)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("succeeded", report.get("compatible", False)) else 2


if __name__ == "__main__":
    raise SystemExit(main())

