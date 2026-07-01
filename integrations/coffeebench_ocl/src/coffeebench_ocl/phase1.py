"""CoffeeBench OCL runner.

The module name is kept for compatibility with the first passive-logging
implementation. The CLI runs the scientific B0-B5 capability arms.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .json_utils import jsonable
from .phases import OCL_CAPABILITY_ARMS, resolve_capability_arm
from .qwen_model import install_qwen_provider
from .runtime import attach_ocl_runtime
from .tooling import FOCAL_AGENT_ID
from .validation import ValidationMode


def attach_phase1_logger(
    env: Any,
    *,
    events_path: str | Path,
    focal_agent_id: str = FOCAL_AGENT_ID,
) -> PassiveOCLAuditLogger:
    """Attach passive logging to a built CoffeeBench environment.

    Compatibility wrapper for earlier Phase-1 code. New callers should use
    `attach_ocl_runtime`.
    """

    return attach_ocl_runtime(
        env,
        events_path=events_path,
        focal_agent_id=focal_agent_id,
        validation_mode=ValidationMode.AUDIT,
    ).logger


def build_coffeebench_args(args: argparse.Namespace, output_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        config=args.config,
        model=args.model,
        models=args.models,
        max_days=args.max_days,
        seed=args.seed,
        main_agent=args.main_agent,
        output=output_path,
    )


def run_coffeebench_ocl(args: argparse.Namespace) -> dict[str, Any]:
    """Run a CoffeeBench simulation with one OCL capability arm attached."""

    install_qwen_provider()
    from coffeebench.main import build_run  # noqa: PLC0415

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    trajectory_path = output_dir / "run.json"
    ocl_events_path = output_dir / "run.ocl.jsonl"

    arm = resolve_capability_arm(args.arm)
    with _maybe_quiet(args.quiet) as captured:
        try:
            coffee_args = build_coffeebench_args(args, str(trajectory_path))
            env, output_path, coffee_events_path = build_run(coffee_args)
            runtime = None
            if arm.name != "B0":
                runtime = attach_ocl_runtime(
                    env,
                    events_path=ocl_events_path,
                    focal_agent_id=args.focal_agent_id,
                    validation_mode=ValidationMode(arm.validation_mode),
                    expose_ledger_tools=arm.exposes_ledger_tools,
                    expose_contract_tools=arm.exposes_contract_tools,
                    hide_raw_trade_tools=arm.hides_raw_trade_tools,
                )

            try:
                result = asyncio.run(env.run())
                env.save_trajectory(output_path)
                ocl_outputs = runtime.save_outputs() if runtime is not None else None
            finally:
                if runtime is not None:
                    runtime.close()
        except BaseException:
            if captured is not None:
                _print_captured_tail(captured)
            raise

    report_path = output_dir / "run_report.json"
    legacy_report_path = output_dir / "phase1_report.json"
    report = {
        "arm": arm.name,
        "label": arm.label,
        "report_path": str(report_path),
        "trajectory_path": output_path,
        "coffee_events_path": coffee_events_path,
        "ocl": ocl_outputs,
        "result": result,
    }
    report_json = json.dumps(jsonable(report), indent=2, sort_keys=True)
    report_path.write_text(report_json, encoding="utf-8")
    legacy_report_path.write_text(report_json, encoding="utf-8")
    return report


class _maybe_quiet:
    def __init__(self, quiet: bool) -> None:
        self.quiet = quiet
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self._stdout_cm = None
        self._stderr_cm = None

    def __enter__(self) -> tuple[io.StringIO, io.StringIO] | None:
        if not self.quiet:
            return None
        self._stdout_cm = redirect_stdout(self.stdout)
        self._stderr_cm = redirect_stderr(self.stderr)
        self._stdout_cm.__enter__()
        self._stderr_cm.__enter__()
        return self.stdout, self.stderr

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if not self.quiet:
            return False
        assert self._stderr_cm is not None
        assert self._stdout_cm is not None
        self._stderr_cm.__exit__(exc_type, exc, traceback)
        self._stdout_cm.__exit__(exc_type, exc, traceback)
        return False


def _print_captured_tail(captured: tuple[io.StringIO, io.StringIO], *, lines: int = 80) -> None:
    stdout, stderr = captured
    chunks = []
    for name, buffer in (("stdout", stdout), ("stderr", stderr)):
        text = buffer.getvalue().strip()
        if text:
            tail = "\n".join(text.splitlines()[-lines:])
            chunks.append(f"--- captured {name} tail ---\n{tail}")
    if chunks:
        print("\n".join(chunks))


def report_brief(report: dict[str, Any]) -> dict[str, Any]:
    result = report.get("result") or {}
    agents = result.get("agents") or {}
    main_agent = result.get("main_agent")
    main = agents.get(main_agent, {}) if isinstance(agents, dict) else {}
    usage = main.get("usage") or {}
    audit = main.get("audit") or {}
    balance = audit.get("balance_sheet") or {}
    return {
        "arm": report.get("arm"),
        "label": report.get("label"),
        "main_agent": main_agent,
        "actual_final_day": result.get("actual_final_day"),
        "terminated_early": result.get("terminated_early"),
        "marketplace": result.get("marketplace_summary"),
        "ocl_summary": (report.get("ocl") or {}).get("summary"),
        "main_agent_result": {
            "model": usage.get("model"),
            "calls": usage.get("n_calls"),
            "cost": usage.get("cost"),
            "net_income": main.get("net_income"),
            "cash": balance.get("true_cash"),
            "equity": balance.get("true_equity"),
        },
        "paths": {
            "report": report.get("report_path"),
            "trajectory": report.get("trajectory_path"),
            "ocl_events": (report.get("ocl") or {}).get("events_path"),
            "ocl_summary": (report.get("ocl") or {}).get("summary_path"),
        },
    }


def run_phase1(args: argparse.Namespace) -> dict[str, Any]:
    """Compatibility wrapper for the original Phase-1 runner name."""

    return run_coffeebench_ocl(args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CoffeeBench with an OCL capability arm.")
    parser.add_argument(
        "--arm",
        default="B1",
        choices=[arm.name for arm in OCL_CAPABILITY_ARMS],
        help="CoffeeBench OCL capability arm.",
    )
    parser.add_argument("--config", default=None, help="Optional CoffeeBench TOML config.")
    parser.add_argument("--model", default="passive", help="Default CoffeeBench model id.")
    parser.add_argument(
        "--models",
        default="roaster_A:heuristic_roaster",
        help="Per-agent model overrides, e.g. 'roaster_A:heuristic_roaster'.",
    )
    parser.add_argument("--max-days", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--main-agent", default=FOCAL_AGENT_ID)
    parser.add_argument("--focal-agent-id", default=FOCAL_AGENT_ID)
    parser.add_argument("--output-dir", default="outputs/coffeebench_ocl/phase1_smoke")
    parser.add_argument(
        "--verbose",
        action="store_false",
        dest="quiet",
        help="Show CoffeeBench's native per-agent/event stdout.",
    )
    parser.set_defaults(quiet=True)
    args = parser.parse_args()
    report = run_coffeebench_ocl(args)
    print(json.dumps(jsonable(report_brief(report)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
