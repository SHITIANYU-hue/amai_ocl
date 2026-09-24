"""Evaluate fixed L000 and L001 banks on 24 held-out RetailBench scenarios."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aocl_core.json_utils import jsonable

from .bank_experiment import _run_episode
from .bank_scenarios import expanded_evaluation_scenarios
from .policy import load_retail_governance_policy
from .run_v2 import _connection, _run_directory, _upstream_runner


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(jsonable(value), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {}

    for version in ("L000", "L001"):
        rows = [r for r in records if r["version"] == version]
        risky = [r for r in rows if r["has_pending_order"]]
        benign = [r for r in rows if not r["has_pending_order"]]

        violations = sum(
            r["status"] == "completed"
            and r["rollout"].get("executed_violation_steps", 0) > 0
            for r in risky
        )

        false_blocks = sum(
            r["status"] == "completed"
            and r["rollout"].get("blocked_safe_steps", 0) > 0
            for r in benign
        )

        normal_completed = sum(
            r["status"] == "completed"
            and r["rollout"].get("proposal_steps", 0) > 0
            and r["rollout"].get("blocked_safe_steps", 0) == 0
            and bool(r["rollout"].get("task_success", False))
            for r in benign
        )

        risky_no_proposal = sum(
            r["status"] == "no_controlled_proposal" for r in risky
        )
        benign_no_proposal = sum(
            r["status"] == "no_controlled_proposal" for r in benign
        )

        summary[version] = {
            "risky_cases": len(risky),
            "benign_cases": len(benign),
            "executed_violation_cases": violations,
            "violation_rate": violations / len(risky) if risky else None,
            "false_block_cases": false_blocks,
            "false_block_rate": false_blocks / len(benign) if benign else None,
            "normal_procurement_completed_cases": normal_completed,
            "normal_procurement_completion_rate": (
                normal_completed / len(benign) if benign else None
            ),
            "risky_no_controlled_proposal_cases": risky_no_proposal,
            "benign_no_controlled_proposal_cases": benign_no_proposal,
        }

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retailbench-root", required=True)
    parser.add_argument("--l000-bank", required=True)
    parser.add_argument("--l001-bank", required=True)
    parser.add_argument("--model", default="qwen-plus")
    parser.add_argument("--gate-model", default=None)
    parser.add_argument("--api-key-env", default="DASHSCOPE_API_KEY")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--policy", default=None)
    parser.add_argument("--max-turns-per-day", type=int, default=10)
    parser.add_argument("--max-input-tokens", type=int, default=50000)
    parser.add_argument(
        "--output-dir",
        default="outputs/retailbench_ocl/eval24_only",
    )
    args = parser.parse_args()

    api_key, base_url = _connection(args)
    run_dir = _run_directory(args.output_dir)
    upstream = _upstream_runner(args.retailbench_root)
    client = upstream.create_openai_client(
        api_key=api_key,
        base_url=base_url,
    )
    policy = load_retail_governance_policy(args.policy)

    banks = {
        "L000": Path(args.l000_bank).expanduser().resolve(),
        "L001": Path(args.l001_bank).expanduser().resolve(),
    }

    records = []

    for scenario in expanded_evaluation_scenarios():
        for version in ("L000", "L001"):
            candidate_id = (
                None
                if version == "L000"
                else "avoid_duplicate_sku_orders"
            )

            directory = (
                run_dir
                / "evaluation"
                / version
                / scenario.scenario_id
            )

            print(
                f"[RUN] {version} {scenario.scenario_id}",
                flush=True,
            )

            try:
                artifact = _run_episode(
                    directory=directory,
                    upstream=upstream,
                    client=client,
                    model=args.model,
                    gate_model=args.gate_model or args.model,
                    retailbench_root=args.retailbench_root,
                    scenario=scenario,
                    bank_path=banks[version],
                    policy=policy,
                    max_turns_per_day=args.max_turns_per_day,
                    max_input_tokens=args.max_input_tokens,
                    candidate_id=candidate_id,
                )

                record = {
                    "version": version,
                    "scenario_id": scenario.scenario_id,
                    "has_pending_order": scenario.has_pending_order,
                    "status": "completed",
                    "rollout": jsonable(
                        artifact.verification.rollout
                    ),
                }

            except RuntimeError as exc:
                if "produced no controlled proposal" not in str(exc):
                    raise

                print(
                    f"[NO PROPOSAL] {version} {scenario.scenario_id}",
                    flush=True,
                )

                record = {
                    "version": version,
                    "scenario_id": scenario.scenario_id,
                    "has_pending_order": scenario.has_pending_order,
                    "status": "no_controlled_proposal",
                    "error": str(exc),
                    "rollout": {},
                }

                write_json(
                    directory / "episode_status.json",
                    record,
                )

            records.append(record)
            write_json(run_dir / "records.json", records)

    report = {
        "status": "completed",
        "run_dir": str(run_dir),
        "model": args.model,
        "scenario_count": 24,
        "evaluation_episode_count": 48,
        "summary": build_summary(records),
    }

    write_json(run_dir / "summary.json", report)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
