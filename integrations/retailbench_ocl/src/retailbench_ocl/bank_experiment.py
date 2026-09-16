"""Minimal real-LLM failure -> Candidate -> L001 RetailBench experiment."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import timedelta
import json
from pathlib import Path
from typing import Any

from aocl_core.audit import JsonlAuditSink
from aocl_core.json_utils import jsonable
from aocl_core.learning import (
    CandidateDiagnosis,
    PairedRolloutReport,
    PromptedConstraintDiagnoser,
    RolloutMetrics,
    promote_candidate_from_rollouts,
)
from aocl_core.library import FrozenConstraintLibrary
from aocl_core.policies import ControlMode
from aocl_core.versioning import LibraryVersion, VersionedLibraryStore

from .adapter import RetailBenchOCL
from .bank_scenarios import (
    PreparedRetailScenario,
    RetailBankScenario,
    pilot_scenarios,
    prepare_scenario,
)
from .configuration import (
    RetailBenchV2Config,
    build_retailbench_v2_runtime,
    load_constraint_bank,
)
from .duplicate_order_verifier import (
    DuplicateOrderVerification,
    DuplicateOrderVerifier,
)
from .loader import load_small_environment
from .openai_compatible import OpenAICompatibleJsonGenerator
from .policy import RetailGovernancePolicy, load_retail_governance_policy
from .promotion import retailbench_promotion_policy
from .run_v2 import _connection, _run_directory, _upstream_runner


@dataclass(frozen=True, slots=True)
class EpisodeArtifact:
    directory: Path
    trace: Any
    verification: DuplicateOrderVerification
    report: dict[str, Any]


def _synchronize_governance_state(
    controlled: RetailBenchOCL,
    scenario: RetailBankScenario,
) -> None:
    """Populate OCL's visible ledger before comparing Current and Trial Banks."""
    current_date = controlled.environment.current_date
    start_date = (current_date - timedelta(days=7)).isoformat()
    end_date = current_date.isoformat()
    controlled.exec_tools(
        "view_current_date_supplier_prices", sku_ids=[scenario.sku_id]
    )
    controlled.exec_tools("view_inventory")
    controlled.exec_tools("view_funds_and_date")
    controlled.exec_tools(
        "view_sku_sales_history",
        sku_ids=[scenario.sku_id],
        start_date=start_date,
        end_date=end_date,
    )
    controlled.exec_tools("view_current_orders")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(jsonable(value), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _trial_bank(
    directory: Path,
    parent: FrozenConstraintLibrary,
    diagnosis: CandidateDiagnosis,
) -> Path:
    trial = FrozenConstraintLibrary(
        parent.constraints
        + (diagnosis.constraint.approved_copy(metadata={"validation_only": True}),)
    )
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "constraints.jsonl").write_text(trial.to_jsonl(), encoding="utf-8")
    _write_json(
        directory / "manifest.json",
        {
            "kind": "unpromoted_trial_bank",
            "parent_digest": parent.digest,
            "library_digest": trial.digest,
            "candidate_id": diagnosis.constraint.constraint_id,
        },
    )
    return directory


def _run_episode(
    *,
    directory: Path,
    upstream: Any,
    client: Any,
    model: str,
    gate_model: str,
    retailbench_root: str | Path,
    scenario: RetailBankScenario,
    bank_path: str | Path,
    policy: RetailGovernancePolicy,
    max_turns_per_day: int,
    max_input_tokens: int,
    candidate_id: str | None = None,
) -> EpisodeArtifact:
    directory.mkdir(parents=True, exist_ok=False)
    gate_generator = OpenAICompatibleJsonGenerator(client=client, model=gate_model)
    runtime = build_retailbench_v2_runtime(
        RetailBenchV2Config(
            constraint_bank=bank_path,
            control_mode=ControlMode.BLOCKING,
            evaluator_mode="semantic",
            retrieval_top_k=3,
            organizational_policy=policy,
        ),
        semantic_generator=gate_generator,
        audit_sink=JsonlAuditSink(directory / "ocl_events.jsonl"),
    )
    episode_id = f"{directory.name}-{scenario.scenario_id}"
    with load_small_environment(
        retailbench_root,
        sku_ids=(scenario.sku_id,),
        random_seed=scenario.random_seed,
    ) as environment:
        prepared: PreparedRetailScenario = prepare_scenario(environment, scenario)
        initial_date = str(environment.current_date)
        controlled = RetailBenchOCL(
            environment,
            episode_id=episode_id,
            runtime=runtime,
            policy=policy,
        )
        _synchronize_governance_state(controlled, scenario)
        upstream.run_react_loop(
            goal=upstream.DEFAULT_GOAL,
            env=controlled,
            model=model,
            max_turns=max_turns_per_day,
            log_path=directory / "retailbench_messages.json",
            max_input_tokens=max_input_tokens,
            checkpoint_dir=directory / "checkpoints",
            checkpoint_interval=max_turns_per_day,
            log_dir=directory / "turns",
            max_days=1,
            max_execution_turns_per_day=max_turns_per_day,
            fixed_strategy=prepared.strategy,
            client=client,
        )
        final_date = str(environment.current_date)
        final_funds = float(environment.funds)
        task_success = final_date != initial_date and final_funds >= 0
        if not controlled.controlled_results:
            raise RuntimeError(
                f"scenario {scenario.scenario_id} produced no controlled proposal"
            )
        trace = controlled.learning_trace(
            scenario_id=scenario.scenario_id,
            split=scenario.split,
            visible_outcome={
                "initial_date": initial_date,
                "final_date": final_date,
                "final_funds": final_funds,
                "task_success": task_success,
                "setup_order_id": prepared.setup_order_id,
            },
        )
        verification = DuplicateOrderVerifier().verify(
            episode_id=episode_id,
            case_id=scenario.scenario_id,
            results=controlled.controlled_results,
            task_success=task_success,
            candidate_id=candidate_id,
            reference_pending_by_sku=(
                {scenario.sku_id: scenario.pending_quantity}
                if scenario.has_pending_order
                else {}
            ),
        )
        report = {
            "scenario": jsonable(scenario),
            "setup": {
                "supplier_id": prepared.supplier_id,
                "unit_cost": prepared.unit_cost,
                "setup_order_id": prepared.setup_order_id,
            },
            "bank_digest": runtime.constraint_library.digest,
            "bank_size": len(runtime.constraint_library.approved),
            "decision_counts": controlled.decision_counts,
            "initial_date": initial_date,
            "final_date": final_date,
            "final_funds": final_funds,
            "task_success": task_success,
            "verification": jsonable(verification),
        }
    _write_json(directory / "learning_trace.json", trace)
    _write_json(directory / "verification.json", verification)
    _write_json(directory / "report.json", report)
    return EpisodeArtifact(directory, trace, verification, report)


def _validate_candidate_shape(diagnosis: CandidateDiagnosis) -> None:
    candidate = diagnosis.constraint
    if "retailbench.place_order" not in candidate.action_types:
        raise RuntimeError("candidate does not govern retailbench.place_order")
    if candidate.response.value == "warn":
        raise RuntimeError("candidate only warns and cannot prevent duplicate execution")


def _paired_validation(
    *,
    root: Path,
    upstream: Any,
    client: Any,
    args: argparse.Namespace,
    policy: RetailGovernancePolicy,
    parent: LibraryVersion,
    trial_bank_path: Path,
    diagnosis: CandidateDiagnosis,
    scenarios: tuple[RetailBankScenario, ...],
) -> PairedRolloutReport:
    parent_cases = []
    trial_cases = []
    for scenario in scenarios:
        parent_artifact = _run_episode(
            directory=root / "parent" / scenario.scenario_id,
            upstream=upstream,
            client=client,
            model=args.model,
            gate_model=args.gate_model or args.model,
            retailbench_root=args.retailbench_root,
            scenario=scenario,
            bank_path=parent.path,
            policy=policy,
            max_turns_per_day=args.max_turns_per_day,
            max_input_tokens=args.max_input_tokens,
        )
        trial_artifact = _run_episode(
            directory=root / "trial" / scenario.scenario_id,
            upstream=upstream,
            client=client,
            model=args.model,
            gate_model=args.gate_model or args.model,
            retailbench_root=args.retailbench_root,
            scenario=scenario,
            bank_path=trial_bank_path,
            policy=policy,
            max_turns_per_day=args.max_turns_per_day,
            max_input_tokens=args.max_input_tokens,
            candidate_id=diagnosis.constraint.constraint_id,
        )
        parent_cases.append(parent_artifact.verification.rollout)
        trial_cases.append(trial_artifact.verification.rollout)
    return PairedRolloutReport.from_cases(
        candidate_id=diagnosis.constraint.constraint_id,
        parent_cases=parent_cases,
        trial_cases=trial_cases,
    )


def run_bank_experiment(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    api_key, base_url = _connection(args)
    run_dir = _run_directory(args.output_dir)
    upstream = _upstream_runner(args.retailbench_root)
    client = upstream.create_openai_client(api_key=api_key, base_url=base_url)
    generator = OpenAICompatibleJsonGenerator(
        client=client,
        model=args.gate_model or args.model,
    )
    policy = load_retail_governance_policy(args.policy)
    scenarios = pilot_scenarios()

    store = VersionedLibraryStore(run_dir / "banks")
    initial_library = load_constraint_bank(args.initial_bank)
    l000 = store.create_initial(initial_library, version_id="L000")

    derivation = _run_episode(
        directory=run_dir / "derivation" / scenarios["derivation_risky"].scenario_id,
        upstream=upstream,
        client=client,
        model=args.model,
        gate_model=args.gate_model or args.model,
        retailbench_root=args.retailbench_root,
        scenario=scenarios["derivation_risky"],
        bank_path=l000.path,
        policy=policy,
        max_turns_per_day=args.max_turns_per_day,
        max_input_tokens=args.max_input_tokens,
    )
    if not derivation.verification.label.policy_failure:
        raise RuntimeError(
            "derivation episode produced no executed duplicate-order failure; "
            f"inspect {derivation.directory}"
        )
    diagnosis = PromptedConstraintDiagnoser(generator).diagnose(
        derivation.trace,
        derivation.verification.label,
    )
    _validate_candidate_shape(diagnosis)
    _write_json(run_dir / "candidate.json", diagnosis)
    trial_bank_path = _trial_bank(run_dir / "trial_bank", l000.library, diagnosis)

    paired = _paired_validation(
        root=run_dir / "validation",
        upstream=upstream,
        client=client,
        args=args,
        policy=policy,
        parent=l000,
        trial_bank_path=trial_bank_path,
        diagnosis=diagnosis,
        scenarios=(
            scenarios["validation_risky"],
            scenarios["validation_benign"],
        ),
    )
    _write_json(run_dir / "paired_validation.json", paired)
    promotion_policy = retailbench_promotion_policy(args.promotion_policy)
    promotion = promote_candidate_from_rollouts(
        diagnosis.constraint,
        paired,
        promotion_policy,
    )
    _write_json(run_dir / "promotion.json", promotion)

    report: dict[str, Any] = {
        "status": "candidate_rejected",
        "run_dir": str(run_dir),
        "model": args.model,
        "gate_model": args.gate_model or args.model,
        "candidate": diagnosis.constraint.to_dict(),
        "promotion": jsonable(promotion),
        "bank_capacity": None,
        "organizational_policy": policy.to_dict(),
    }
    if not promotion.approved:
        _write_json(run_dir / "report.json", report)
        return run_dir, report

    l001 = store.promote(
        parent=l000,
        result=promotion,
        policy=promotion_policy,
        version_id="L001",
    )
    evaluation_cases: dict[str, list[Any]] = {"L000": [], "L001": []}
    for scenario in (
        scenarios["evaluation_risky"],
        scenarios["evaluation_benign"],
    ):
        for version, bank, candidate_id in (
            ("L000", l000, None),
            ("L001", l001, diagnosis.constraint.constraint_id),
        ):
            artifact = _run_episode(
                directory=run_dir / "evaluation" / version / scenario.scenario_id,
                upstream=upstream,
                client=client,
                model=args.model,
                gate_model=args.gate_model or args.model,
                retailbench_root=args.retailbench_root,
                scenario=scenario,
                bank_path=bank.path,
                policy=policy,
                max_turns_per_day=args.max_turns_per_day,
                max_input_tokens=args.max_input_tokens,
                candidate_id=candidate_id,
            )
            evaluation_cases[version].append(artifact.verification.rollout)

    evaluation_metrics = {
        version: jsonable(RolloutMetrics.from_cases(cases))
        for version, cases in evaluation_cases.items()
    }
    report.update(
        {
            "status": "completed",
            "promoted_version": l001.version_id,
            "promoted_bank_digest": l001.library.digest,
            "evaluation_metrics": evaluation_metrics,
        }
    )
    _write_json(run_dir / "report.json", report)
    return run_dir, report


def inspect_bank_experiment(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.retailbench_root).expanduser().resolve()
    scenarios = pilot_scenarios()
    return {
        "status": (
            "ready"
            if (root / "agents/run_exec_strategy_env.py").is_file()
            else "missing_upstream_runner"
        ),
        "retailbench_root": str(root),
        "model": args.model,
        "bank_capacity": None,
        "episodes_if_promoted": 9,
        "scenarios": {key: jsonable(value) for key, value in scenarios.items()},
        "organizational_policy": load_retail_governance_policy(args.policy).to_dict(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the minimal RetailBench Constraint Bank learning experiment"
    )
    parser.add_argument("--retailbench-root", required=True)
    parser.add_argument("--model", default="qwen-plus")
    parser.add_argument("--gate-model", default=None)
    parser.add_argument("--api-key-env", default="DASHSCOPE_API_KEY")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--initial-bank", default=None)
    parser.add_argument("--policy", default=None)
    parser.add_argument("--promotion-policy", choices=("marginal", "strict"), default="marginal")
    parser.add_argument("--max-turns-per-day", type=int, default=10)
    parser.add_argument("--max-input-tokens", type=int, default=50_000)
    parser.add_argument("--output-dir", default="outputs/retailbench_ocl/bank_experiment")
    parser.add_argument("--check-only", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.check_only:
        print(json.dumps(inspect_bank_experiment(args), ensure_ascii=False, indent=2))
        return
    run_dir, report = run_bank_experiment(args)
    print(json.dumps({"run_dir": str(run_dir), **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
