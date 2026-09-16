"""Thin pre-execution control layer around RetailBench's tool dispatcher."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Mapping

from aocl_core.contracts import (
    CheckLevel,
    CheckResult,
    ControlDecision,
    DecisionType,
    ObservableContext,
    ObservedOutcome,
    ProposedAction,
)
from aocl_core.json_utils import jsonable
from aocl_core.learning import LearningTrace, VisibleActionStep
from aocl_core.policies import ControlMode
from aocl_core.runtime import IntegrationOCLRuntime

from .policy import RetailGovernancePolicy


CONTROLLED_TOOLS = frozenset(("place_order", "modify_sku_price", "add_note"))

MAX_OBSERVATION_CHARS = 12_000


@dataclass(frozen=True, slots=True)
class RetailBenchOCLResult:
    action_id: str | None
    decision: ControlDecision | None
    executed: bool
    host_result: Mapping[str, Any]
    action: ProposedAction | None = None
    context: ObservableContext | None = None


@dataclass(slots=True)
class RetailBenchOCL:
    """Proxy an existing ``RetailEnvironment`` without modifying upstream code.

    Read calls execute normally and become same-day evidence. Controlled write
    calls are evaluated by ``aocl_core`` before the original dispatcher runs.
    """

    environment: Any
    episode_id: str = "retailbench-smoke"
    actor_id: str = "store-agent"
    runtime: IntegrationOCLRuntime = field(
        default_factory=lambda: IntegrationOCLRuntime(mode=ControlMode.BLOCKING)
    )
    policy: RetailGovernancePolicy = field(default_factory=RetailGovernancePolicy)
    _sequence: int = field(default=0, init=False, repr=False)
    _evidence_by_day: dict[str, set[str]] = field(default_factory=dict, init=False, repr=False)
    _observations_by_day: dict[str, dict[str, Any]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _results: list[RetailBenchOCLResult] = field(default_factory=list, init=False, repr=False)
    last_result: RetailBenchOCLResult | None = field(default=None, init=False)

    def get_tools(self) -> Mapping[str, Mapping[str, Any]]:
        return self.environment.get_tools()

    def exec_tools(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """Keep RetailBench's native ``exec_tools`` call and response shape."""
        if tool_name not in CONTROLLED_TOOLS:
            result = self.environment.exec_tools(tool_name, **kwargs)
            if not _contains_error(result):
                self._evidence_for_today().add(tool_name)
                self._observations_for_today()[tool_name] = _compact_observation(result)
            self._save_result(RetailBenchOCLResult(
                action_id=None,
                decision=None,
                executed=True,
                host_result=result,
            ))
            return result

        self._sequence += 1
        action_id = f"{self.episode_id}:{self._sequence}:{tool_name}"
        evidence = self._evidence_for_today()
        missing = tuple(
            item for item in self.policy.required_evidence(tool_name) if item not in evidence
        )
        action = ProposedAction(
            action_id=action_id,
            actor_id=self.actor_id,
            action_type=f"retailbench.{tool_name}",
            payload=jsonable(kwargs),
            metadata={"host": "retailbench", "day": self._current_day()},
        )
        context = ObservableContext(
            episode_id=self.episode_id,
            step_id=self._sequence,
            actor_id=self.actor_id,
            visible_state={
                "day": self._current_day(),
                "evidence_tools_called": sorted(evidence),
                "observations": dict(self._observations_for_today()),
                "environment_limits": self._visible_environment_limits(),
                "organizational_policy": self.policy.to_dict(),
            },
            metadata={"host": "retailbench"},
        )
        decision = self.runtime.evaluate(
            action=action,
            context=context,
            host_checks=(_evidence_check(tool_name, missing),),
        )
        execute = decision.decision in {DecisionType.APPROVE, DecisionType.WARN}

        if execute:
            result = self.environment.exec_tools(tool_name, **kwargs)
            status = "host_error" if _contains_error(result) else "executed"
        else:
            result = _blocked_result(tool_name, decision, missing)
            status = "blocked"

        self.runtime.observe(
            ObservedOutcome(
                action_id=action_id,
                executed=execute,
                status=status,
                visible_result=jsonable(result),
                metadata={"host": "retailbench"},
            )
        )
        if execute and status == "executed":
            self._invalidate_after(tool_name)
        result = dict(result)
        result["ocl"] = {
            "action_id": action_id,
            "decision": decision.decision.value,
            "missing_evidence": list(missing),
        }
        self._save_result(RetailBenchOCLResult(
            action_id=action_id,
            decision=decision,
            executed=execute,
            host_result=result,
            action=action,
            context=context,
        ))
        return result

    @property
    def controlled_results(self) -> tuple[RetailBenchOCLResult, ...]:
        return tuple(item for item in self._results if item.action_id is not None)

    @property
    def decision_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.controlled_results:
            if item.decision is None:
                continue
            key = item.decision.decision.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def learning_trace(
        self,
        *,
        scenario_id: str,
        split: str,
        visible_outcome: Mapping[str, Any],
    ) -> LearningTrace:
        """Export controlled RetailBench actions in the shared V2 trace schema."""
        steps = []
        for item in self.controlled_results:
            if item.action is None or item.context is None:
                continue
            steps.append(
                VisibleActionStep(
                    step_id=item.context.step_id,
                    action_type=item.action.action_type,
                    observable_context=jsonable(item.context.visible_state),
                    proposed_action={
                        "payload": jsonable(item.action.payload),
                        "visible_text": item.action.visible_text,
                    },
                    executed=item.executed,
                    visible_result=jsonable(item.host_result),
                )
            )
        return LearningTrace(
            episode_id=self.episode_id,
            scenario_id=scenario_id,
            split=split,
            steps=tuple(steps),
            visible_outcome=jsonable(visible_outcome),
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.environment, name)

    def _current_day(self) -> str:
        return str(getattr(self.environment, "current_date", "unknown"))

    def _evidence_for_today(self) -> set[str]:
        return self._evidence_by_day.setdefault(self._current_day(), set())

    def _observations_for_today(self) -> dict[str, Any]:
        return self._observations_by_day.setdefault(self._current_day(), {})

    def _save_result(self, result: RetailBenchOCLResult) -> None:
        self.last_result = result
        self._results.append(result)

    def _visible_environment_limits(self) -> dict[str, Any]:
        inventory = getattr(self.environment, "inventory", None)
        return {
            "daily_rent": getattr(self.environment, "rent", None),
            "inventory_capacity": getattr(inventory, "capacity", None),
        }

    def _invalidate_after(self, tool_name: str) -> None:
        """Discard same-day observations made stale by a successful write."""
        observations = self._observations_for_today()
        evidence = self._evidence_for_today()
        stale_by_action = {
            "place_order": (
                "view_current_orders",
                "view_inventory",
                "view_funds_and_date",
            ),
            "modify_sku_price": ("view_sku_prices",),
        }
        for stale in stale_by_action.get(tool_name, ()):
            observations.pop(stale, None)
            evidence.discard(stale)


def _evidence_check(action_name: str, missing: tuple[str, ...]) -> CheckResult:
    return CheckResult(
        check_id=f"retailbench.evidence.{action_name}",
        passed=not missing,
        level=CheckLevel.ERROR if missing else CheckLevel.INFO,
        reason=(
            f"Missing same-day evidence before {action_name}: {', '.join(missing)}"
            if missing
            else ""
        ),
        source="retailbench_evidence_policy",
        recommended_decision=DecisionType.BLOCK if missing else None,
        metadata={"missing_evidence": missing},
    )


def _blocked_result(
    tool_name: str,
    decision: ControlDecision,
    missing: tuple[str, ...],
) -> dict[str, Any]:
    reason = decision.message or f"OCL blocked {tool_name}"
    return {
        "result": {
            "error": reason,
            "blocked_by": "retailbench_ocl",
            "missing_evidence": list(missing),
        },
        "formatted": f"OCL blocked {tool_name}: {reason}",
    }


def _contains_error(result: Mapping[str, Any]) -> bool:
    payload = result.get("result")
    return isinstance(payload, Mapping) and "error" in payload


def _compact_observation(result: Mapping[str, Any]) -> Any:
    payload = jsonable(result.get("result", result))
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(encoded) <= MAX_OBSERVATION_CHARS:
        return payload
    return {
        "truncated": True,
        "preview": encoded[:MAX_OBSERVATION_CHARS],
        "original_characters": len(encoded),
    }
