"""OCL audit logging for CoffeeBench runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import threading
from typing import Any

from .contracts import ContractAuditEvent
from .json_utils import jsonable
from .lifecycle import ContractLifecycle
from .tooling import FOCAL_AGENT_ID, RAW_TRADE_TOOLS


RELEVANT_COFFEE_EVENTS: frozenset[str] = frozenset(
    {
        "agent_step",
        "deal_delivered",
        "shipment_delayed",
        "shipment_lost",
        "deliveries_processed",
        "day_end",
        "run_start",
        "run_end",
    }
)


@dataclass(frozen=True, slots=True)
class AuditPaths:
    events_path: Path
    contracts_path: Path
    summary_path: Path


class PassiveOCLAuditLogger:
    """Append-only CoffeeBench OCL logger.

    It observes focal tool calls and selected CoffeeBench events, updates the
    reconstructed lifecycle, and writes OCL JSONL records. Audit and warning
    arms must not affect CoffeeBench tool results or environment transitions.
    """

    def __init__(
        self,
        *,
        events_path: str | Path,
        focal_agent_id: str = FOCAL_AGENT_ID,
    ) -> None:
        self.focal_agent_id = focal_agent_id
        self.events_path = Path(events_path)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.contracts_path = self.events_path.with_suffix(".contracts.json")
        self.summary_path = self.events_path.with_suffix(".summary.json")
        self.lifecycle = ContractLifecycle(focal_agent_id=focal_agent_id)
        self.validation_counts: dict[str, int] = {
            "pass": 0,
            "warning": 0,
            "fail": 0,
            "not_run": 0,
        }
        self.tool_call_counts: dict[str, int] = {}
        self.blocked_action_count = 0
        self._fh = self.events_path.open("w", encoding="utf-8", buffering=1)
        self._lock = threading.Lock()
        self._seq = 0

    @property
    def paths(self) -> AuditPaths:
        return AuditPaths(
            events_path=self.events_path,
            contracts_path=self.contracts_path,
            summary_path=self.summary_path,
        )

    def record_tool_call(
        self,
        *,
        action_name: str,
        action_input: dict[str, Any],
        result: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> None:
        context = context or {}
        self.tool_call_counts[action_name] = self.tool_call_counts.get(action_name, 0) + 1
        if result.get("ocl_decision") == "block":
            self.blocked_action_count += 1
        transitions = self.lifecycle.process_tool_call(
            action_name=action_name,
            action_input=action_input,
            result=result,
            context=context,
        )
        self.emit(
            "ocl_tool_call",
            agent_id=self.focal_agent_id,
            day=context.get("day"),
            action=action_name,
            action_input=action_input,
            result=result,
            context=context,
            transition_count=len(transitions),
        )
        self._emit_transitions(transitions)

    def record_tool_exception(
        self,
        *,
        action_name: str,
        action_input: dict[str, Any],
        exception: BaseException,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.emit(
            "ocl_tool_exception",
            agent_id=self.focal_agent_id,
            day=(context or {}).get("day"),
            action=action_name,
            action_input=action_input,
            error=f"{type(exception).__name__}: {exception}",
            context=context or {},
        )

    def record_coffee_event(self, event_type: str, data: dict[str, Any]) -> None:
        if event_type == "agent_step":
            transitions = self._process_agent_step(data)
            if not transitions:
                return
        elif event_type not in RELEVANT_COFFEE_EVENTS:
            return
        else:
            transitions = self.lifecycle.process_coffee_event(event_type=event_type, data=data)
        self.emit(
            "ocl_coffee_event",
            coffee_event_type=event_type,
            data=data,
            transition_count=len(transitions),
        )
        self._emit_transitions(transitions)

    def _process_agent_step(self, data: dict[str, Any]) -> list[ContractAuditEvent]:
        """Process useful native CoffeeBench `agent_step` records.

        Focal tool calls are already captured by wrappers in live Phase-1 runs,
        so this only uses non-focal actions that complete a focal transaction,
        such as a farmer accepting `roaster_A`'s outgoing offer.
        """

        actor_id = str(data.get("agent_id") or "")
        action = data.get("action")
        if action not in RAW_TRADE_TOOLS:
            return []
        if actor_id == self.focal_agent_id:
            return []

        action_input = data.get("action_input") or {}
        result = data.get("observation") or {}
        if not isinstance(action_input, dict) or not isinstance(result, dict):
            return []
        if result.get("status") != "success":
            return []

        if action == "accept_offer" and result.get("buyer_id") == self.focal_agent_id:
            return self.lifecycle.process_tool_call(
                action_name=action,
                action_input=action_input,
                result=result,
                context={
                    "agent_id": actor_id,
                    "day": data.get("day"),
                    "source": "coffee_agent_step",
                },
            )
        return []

    def save_outputs(self) -> dict[str, Any]:
        contracts = self.lifecycle.to_records()
        summary = self.lifecycle.metrics()
        summary.update(
            {
                "validation_counts": dict(self.validation_counts),
                "tool_call_counts": dict(sorted(self.tool_call_counts.items())),
                "blocked_action_count": self.blocked_action_count,
            }
        )
        self.contracts_path.write_text(
            json.dumps(contracts, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        self.summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        return {
            "events_path": str(self.events_path),
            "contracts_path": str(self.contracts_path),
            "summary_path": str(self.summary_path),
            "summary": summary,
        }

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def emit(self, record_type: str, **data: Any) -> None:
        with self._lock:
            if record_type == "ocl_validation":
                self._record_validation_count(data.get("validation"))
            self._seq += 1
            record = {
                "seq": self._seq,
                "type": record_type,
                "time": datetime.now().isoformat(timespec="seconds"),
                **jsonable(data),
            }
            self._fh.write(json.dumps(record, default=str, sort_keys=True) + "\n")

    def _emit_transitions(self, transitions: list[ContractAuditEvent]) -> None:
        for event in transitions:
            self.emit("ocl_contract_event", **jsonable(event))

    def _record_validation_count(self, validation: Any) -> None:
        status = getattr(validation, "status", None)
        value = getattr(status, "value", status)
        if value is None and isinstance(validation, dict):
            value = validation.get("status")
        value = str(value or "not_run")
        if value not in self.validation_counts:
            self.validation_counts[value] = 0
        self.validation_counts[value] += 1
