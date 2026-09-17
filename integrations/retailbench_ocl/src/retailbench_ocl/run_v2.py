"""Run RetailBench's real LLM loop through the shared OCL V2 runtime."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from aocl_core.audit import JsonlAuditSink
from aocl_core.json_utils import jsonable
from aocl_core.policies import ControlMode

from .adapter import RetailBenchOCL
from .configuration import (
    RetailBenchV2Config,
    build_retailbench_v2_runtime,
    load_constraint_bank,
)
from .loader import SMALL_SKUS, load_small_environment
from .openai_compatible import OpenAICompatibleJsonGenerator
from .feedback import summarize_policy_feedback
from .policy import load_retail_governance_policy


DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().strip("\"'“”‘’").strip()
    return cleaned or None


def _upstream_runner(retailbench_root: str | Path) -> Any:
    root = Path(retailbench_root).expanduser().resolve()
    runner = root / "agents/run_exec_strategy_env.py"
    if not runner.is_file():
        raise FileNotFoundError(f"RetailBench execution runner not found: {runner}")
    os.environ.setdefault("MPLCONFIGDIR", tempfile.gettempdir())
    os.environ.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())
    for path in (root, root / "module"):
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)
    module_name = "retailbench_upstream_run_exec_strategy_env"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, runner)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load RetailBench execution runner: {runner}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _connection(args: argparse.Namespace) -> tuple[str, str | None]:
    api_key = _clean(os.getenv(args.api_key_env))
    if api_key is None:
        raise ValueError(f"{args.api_key_env} is not set")
    base_url = _clean(args.base_url) or _clean(os.getenv("OPENAI_BASE_URL"))
    if base_url is None and args.api_key_env == "DASHSCOPE_API_KEY":
        base_url = _clean(os.getenv("DASHSCOPE_BASE_URL")) or DEFAULT_DASHSCOPE_BASE_URL
    return api_key, base_url


def _run_directory(root: str | Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    directory = Path(root).expanduser().resolve() / timestamp
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def inspect_configuration(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.retailbench_root).expanduser().resolve()
    runner = root / "agents/run_exec_strategy_env.py"
    bank = load_constraint_bank(args.constraint_bank)
    policy = load_retail_governance_policy(args.policy)
    return {
        "status": "ready" if runner.is_file() else "missing_upstream_runner",
        "retailbench_root": str(root),
        "runner": str(runner),
        "sku_ids": list(SMALL_SKUS[: args.sku_count]),
        "constraint_bank_size": len(bank.approved),
        "constraint_bank_digest": bank.digest,
        "evaluator": args.evaluator,
        "retrieval_top_k": args.retrieval_top_k,
        "max_days": args.max_days,
        "organizational_policy": policy.to_dict(),
    }


def run_short_v2(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    api_key, base_url = _connection(args)
    run_dir = _run_directory(args.output_dir)
    audit_path = run_dir / "ocl_events.jsonl"
    upstream = _upstream_runner(args.retailbench_root)
    client = upstream.create_openai_client(api_key=api_key, base_url=base_url)
    gate_generator = OpenAICompatibleJsonGenerator(
        client=client,
        model=args.gate_model or args.model,
    )
    policy = load_retail_governance_policy(args.policy)
    runtime = build_retailbench_v2_runtime(
        RetailBenchV2Config(
            constraint_bank=args.constraint_bank,
            control_mode=ControlMode(args.ocl_mode),
            evaluator_mode=args.evaluator,
            retrieval_top_k=args.retrieval_top_k,
            organizational_policy=policy,
        ),
        semantic_generator=gate_generator if args.evaluator == "semantic" else None,
        audit_sink=JsonlAuditSink(audit_path),
    )

    sku_ids = SMALL_SKUS[: args.sku_count]
    with load_small_environment(args.retailbench_root, sku_ids=sku_ids) as environment:
        controlled = RetailBenchOCL(
            environment,
            episode_id=run_dir.name,
            runtime=runtime,
            policy=policy,
        )
        if args.strategy_file:
            strategy = upstream.load_strategy_from_file(args.strategy_file)
        else:
            strategy_module = importlib.import_module("module.strategy_manager")
            strategy = strategy_module.create_initial_strategy()

        upstream.run_react_loop(
            goal=upstream.DEFAULT_GOAL,
            env=controlled,
            model=args.model,
            max_turns=args.max_days * args.max_turns_per_day,
            log_path=run_dir / "retailbench_messages.json",
            max_input_tokens=args.max_input_tokens,
            checkpoint_dir=run_dir / "checkpoints",
            checkpoint_interval=max(1, args.max_turns_per_day),
            log_dir=run_dir / "turns",
            max_days=args.max_days,
            max_execution_turns_per_day=args.max_turns_per_day,
            fixed_strategy=strategy,
            client=client,
        )
        report = {
            "status": "completed",
            "run_dir": str(run_dir),
            "model": args.model,
            "gate_model": args.gate_model or args.model,
            "max_days": args.max_days,
            "sku_ids": list(sku_ids),
            "final_date": str(getattr(environment, "current_date", "unknown")),
            "final_funds": getattr(environment, "funds", None),
            "constraint_bank_size": len(runtime.constraint_library.approved),
            "constraint_bank_digest": runtime.constraint_library.digest,
            "decision_counts": controlled.decision_counts,
            "controlled_actions": len(controlled.controlled_results),
            "audit_path": str(audit_path),
            "organizational_policy": policy.to_dict(),
        }
        feedback = summarize_policy_feedback(controlled.controlled_results)
        feedback_path = run_dir / "policy_feedback.json"
        feedback_path.write_text(
            json.dumps(feedback, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        report["policy_feedback"] = {
            key: value for key, value in feedback.items() if key != "records"
        }
        report["policy_feedback_path"] = str(feedback_path)
        trace_path = None
        if controlled.controlled_results:
            trace_path = run_dir / "learning_trace.json"
            trace = controlled.learning_trace(
                scenario_id=f"retailbench-small-{len(sku_ids)}sku",
                split=args.split,
                visible_outcome={
                    "final_date": report["final_date"],
                    "final_funds": report["final_funds"],
                    "decision_counts": report["decision_counts"],
                },
            )
            trace_path.write_text(
                json.dumps(jsonable(trace), ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
        report["learning_trace_path"] = str(trace_path) if trace_path else None

    (run_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return run_dir, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a short real-LLM RetailBench episode through OCL V2"
    )
    parser.add_argument("--retailbench-root", required=True)
    parser.add_argument("--model", default="qwen-plus")
    parser.add_argument("--gate-model", default=None)
    parser.add_argument("--api-key-env", default="DASHSCOPE_API_KEY")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--constraint-bank", default=None)
    parser.add_argument(
        "--policy",
        default=None,
        help=(
            "JSON policy added by retailbench_ocl; omitted uses the documented "
            "minimal_v1 defaults"
        ),
    )
    parser.add_argument("--evaluator", choices=("semantic", "lexical"), default="semantic")
    parser.add_argument("--retrieval-top-k", type=int, default=3)
    parser.add_argument(
        "--ocl-mode",
        choices=tuple(item.value for item in ControlMode),
        default=ControlMode.BLOCKING.value,
    )
    parser.add_argument("--sku-count", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--max-days", type=int, default=10)
    parser.add_argument("--max-turns-per-day", type=int, default=12)
    parser.add_argument("--max-input-tokens", type=int, default=50_000)
    parser.add_argument("--strategy-file", default=None)
    parser.add_argument(
        "--split",
        choices=("derivation", "validation", "evaluation", "benign"),
        default="evaluation",
    )
    parser.add_argument("--output-dir", default="outputs/retailbench_ocl/v2_short")
    parser.add_argument("--check-only", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.check_only:
        print(json.dumps(inspect_configuration(args), ensure_ascii=False, indent=2))
        return
    run_dir, report = run_short_v2(args)
    print(json.dumps({"run_dir": str(run_dir), **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
