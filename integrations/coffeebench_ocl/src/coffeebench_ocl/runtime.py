"""Runtime attachment for CoffeeBench OCL capability arms."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from functools import wraps
import inspect
from pathlib import Path
from types import MethodType
from typing import Any, Callable
from uuid import uuid4

from .audit import PassiveOCLAuditLogger
from .contracts import ContractAuditEvent, ContractStatus, OCLContract
from .json_utils import jsonable
from .tooling import (
    FOCAL_AGENT_ID,
    OCL_CONTRACT_TOOLS,
    OCL_LEDGER_TOOLS,
    OPERATIONAL_CONTROL_TOOLS,
    RAW_TRADE_TOOLS,
)
from .validation import ValidationMode, ValidationPolicy, validate_operational_action


def attach_ocl_runtime(
    env: Any,
    *,
    events_path: str | Path,
    focal_agent_id: str = FOCAL_AGENT_ID,
    validation_mode: ValidationMode = ValidationMode.AUDIT,
    expose_ledger_tools: bool = False,
    expose_contract_tools: bool = False,
    hide_raw_trade_tools: bool = False,
) -> "CoffeeBenchOCLRuntime":
    runtime = CoffeeBenchOCLRuntime(
        env=env,
        events_path=events_path,
        focal_agent_id=focal_agent_id,
        validation_policy=ValidationPolicy(mode=validation_mode),
        expose_ledger_tools=expose_ledger_tools,
        expose_contract_tools=expose_contract_tools,
        hide_raw_trade_tools=hide_raw_trade_tools,
    )
    runtime.attach()
    return runtime


class CoffeeBenchOCLRuntime:
    """Organization-side OCL boundary for one CoffeeBench focal agent."""

    def __init__(
        self,
        *,
        env: Any,
        events_path: str | Path,
        focal_agent_id: str,
        validation_policy: ValidationPolicy,
        expose_ledger_tools: bool,
        expose_contract_tools: bool,
        hide_raw_trade_tools: bool,
    ) -> None:
        self.env = env
        self.focal_agent_id = focal_agent_id
        self.validation_policy = validation_policy
        self.expose_ledger_tools = expose_ledger_tools
        self.expose_contract_tools = expose_contract_tools
        self.hide_raw_trade_tools = hide_raw_trade_tools
        self.logger = PassiveOCLAuditLogger(events_path=events_path, focal_agent_id=focal_agent_id)
        self.business_app = env.business_apps[focal_agent_id]
        self.agent = env.agents[focal_agent_id]
        self.original_tools: dict[str, Callable[..., dict]] = {}

    def attach(self) -> None:
        self._attach_emit_hook()
        self._capture_original_tools()
        self._wrap_operational_tools()
        if self.expose_ledger_tools:
            self._add_tools([self.view_ocl_ledger, self.view_ocl_obligations])
        if self.expose_contract_tools:
            self._add_tools(
                [
                    self.draft_purchase_contract,
                    self.validate_contract,
                    self.submit_contract_offer,
                    self.withdraw_contract_offer,
                    self.accept_contract_offer,
                    self.settle_due_contract,
                    self.return_contract_shipment,
                ]
            )
        if self.hide_raw_trade_tools:
            self._remove_tools(RAW_TRADE_TOOLS)
        self._refresh_agent_tools()
        self.logger.emit(
            "ocl_runtime_attached",
            focal_agent_id=self.focal_agent_id,
            validation_mode=self.validation_policy.mode.value,
            wrapped_tools=OPERATIONAL_CONTROL_TOOLS,
            ledger_tools=OCL_LEDGER_TOOLS if self.expose_ledger_tools else (),
            contract_tools=OCL_CONTRACT_TOOLS if self.expose_contract_tools else (),
            hidden_tools=RAW_TRADE_TOOLS if self.hide_raw_trade_tools else (),
        )

    def close(self) -> None:
        self.logger.close()

    def save_outputs(self) -> dict[str, Any]:
        return self.logger.save_outputs()

    def view_ocl_ledger(self) -> dict:
        """View OCL's read-only contract ledger for the focal business."""

        records = self.logger.lifecycle.to_records()
        return {
            "status": "success",
            "summary": self.logger.lifecycle.metrics(),
            "contracts": records,
            "open_contracts": [r for r in records if not r.get("is_terminal")],
        }

    def view_ocl_obligations(self) -> dict:
        """View current payment, delivery, and exposure obligations."""

        ba = self.business_app
        today = ba._today()
        payables = [_invoice_row(inv, today) for inv in ba.accounts_payable if _open_invoice(inv)]
        receivables = [_invoice_row(inv, today) for inv in ba.accounts_receivable if _open_invoice(inv)]
        pending_inbound = []
        pending_outbound = []
        env = getattr(ba.marketplace, "_env", None)
        if env is not None:
            for deal in getattr(env, "_pending_shipments", []):
                row = _dataclass_dict(deal)
                if getattr(deal, "buyer_id", None) == ba.agent_id:
                    pending_inbound.append(row)
                if getattr(deal, "seller_id", None) == ba.agent_id:
                    pending_outbound.append(row)
        return {
            "status": "success",
            "day": today,
            "cash": round(float(ba.cash), 2),
            "inventory_kg": ba._total_inventory_kg(),
            "pending_inbound_kg": ba._pending_inbound_kg(),
            "inventory_cap_kg": ba._inventory_cap_kg(),
            "open_payables": payables,
            "open_receivables": receivables,
            "overdue_payables": [p for p in payables if p["overdue"]],
            "due_soon_payables": [p for p in payables if 0 <= p["days_to_due"] <= 3],
            "pending_inbound_deliveries": pending_inbound,
            "pending_outbound_deliveries": pending_outbound,
            "note": "Read-only operational memory; no supplier, price, or production recommendation is provided.",
        }

    def draft_purchase_contract(
        self,
        seller_id: str,
        item_id: str,
        quantity: int,
        unit_price: float,
        payment_terms_days: int = 30,
        listing_id: str = "",
        rationale: str = "",
    ) -> dict:
        """Draft a purchase contract without executing a CoffeeBench action."""

        contract_id = "ocl_draft_" + str(uuid4())[:8]
        contract = OCLContract(
            contract_id=contract_id,
            focal_agent_id=self.focal_agent_id,
            buyer_id=self.focal_agent_id,
            seller_id=seller_id,
            item_id=item_id,
            quantity=int(quantity),
            unit_price=float(unit_price),
            total_price=round(int(quantity) * float(unit_price), 2),
            payment_terms_days=int(payment_terms_days),
            listing_id=listing_id or None,
            created_day=self.business_app._today(),
        )
        self.logger.lifecycle.contracts[contract_id] = contract
        event = ContractAuditEvent(
            event_type="purchase_contract_drafted",
            day=self.business_app._today(),
            actor_id=self.focal_agent_id,
            status_before=ContractStatus.DRAFTED,
            status_after=ContractStatus.DRAFTED,
            metadata={"rationale": rationale},
        )
        contract.append_event(event)
        self.logger.emit("ocl_contract_event", **jsonable(event))
        validation = self._validate(
            "make_offer",
            {
                "listing_id": listing_id,
                "offered_price": unit_price,
                "qty": quantity,
                "payment_terms_days": payment_terms_days,
            },
        )
        return {
            "status": "success",
            "contract_id": contract_id,
            "validation": jsonable(validation),
        }

    def validate_contract(
        self,
        listing_id: str,
        offered_price: float,
        qty: int,
        payment_terms_days: int = 30,
    ) -> dict:
        """Validate a proposed purchase contract without submitting an offer."""

        validation = self._validate(
            "make_offer",
            {
                "listing_id": listing_id,
                "offered_price": offered_price,
                "qty": qty,
                "payment_terms_days": payment_terms_days,
            },
        )
        return {"status": "success", "validation": jsonable(validation)}

    def submit_contract_offer(
        self,
        listing_id: str,
        offered_price: float,
        qty: int,
        payment_terms_days: int = 30,
        message: str = "",
    ) -> dict:
        """Submit a validated purchase offer through CoffeeBench."""

        return self._execute_original(
            "make_offer",
            {
                "listing_id": listing_id,
                "offered_price": offered_price,
                "qty": qty,
                "payment_terms_days": payment_terms_days,
                "message": message,
            },
        )

    def accept_contract_offer(self, offer_id: str) -> dict:
        """Accept an incoming offer through the OCL execution boundary."""

        return self._execute_original("accept_offer", {"offer_id": offer_id})

    def withdraw_contract_offer(self, offer_id: str) -> dict:
        """Withdraw an outgoing pending offer through the OCL execution boundary."""

        return self._execute_original("withdraw_offer", {"offer_id": offer_id})

    def settle_due_contract(self, invoice_id: str) -> dict:
        """Settle an open payable invoice through the OCL execution boundary."""

        return self._execute_original("pay_invoice", {"invoice_id": invoice_id})

    def return_contract_shipment(
        self,
        invoice_id: str,
        quantity_kg: int,
        reason: str = "",
    ) -> dict:
        """Return delivered goods through the OCL execution boundary."""

        return self._execute_original(
            "return_shipment",
            {"invoice_id": invoice_id, "quantity_kg": quantity_kg, "reason": reason},
        )

    def _attach_emit_hook(self) -> None:
        original_emit = self.env._emit

        def logged_emit(event_type: str, **data: Any) -> None:
            original_emit(event_type, **data)
            self.logger.record_coffee_event(event_type, data)

        self.env._emit = MethodType(lambda _self, event_type, **data: logged_emit(event_type, **data), self.env)

    def _capture_original_tools(self) -> None:
        for action_name in OPERATIONAL_CONTROL_TOOLS:
            tool = getattr(self.business_app, action_name, None)
            if callable(tool):
                self.original_tools[action_name] = tool

    def _wrap_operational_tools(self) -> None:
        for action_name, original_tool in self.original_tools.items():
            wrapped = self._make_wrapped_tool(action_name, original_tool)
            setattr(self.business_app, action_name, wrapped)
            self._replace_tool(action_name, wrapped)

    def _make_wrapped_tool(
        self,
        action_name: str,
        original_tool: Callable[..., dict],
    ) -> Callable[..., dict]:
        @wraps(original_tool)
        def wrapped(*args: Any, **kwargs: Any) -> dict:
            action_input = _call_input_from_bound_method(original_tool, args, kwargs)
            return self._execute_tool(action_name, original_tool, action_input)

        return wrapped

    def _execute_original(self, action_name: str, action_input: dict[str, Any]) -> dict:
        original_tool = self.original_tools[action_name]
        return self._execute_tool(action_name, original_tool, action_input)

    def _execute_tool(
        self,
        action_name: str,
        original_tool: Callable[..., dict],
        action_input: dict[str, Any],
    ) -> dict:
        context = _snapshot_context(self.business_app, action_name, action_input)
        validation = self._validate(action_name, action_input)
        if self.validation_policy.validates:
            self.logger.emit(
                "ocl_validation",
                agent_id=self.focal_agent_id,
                action=action_name,
                action_input=action_input,
                validation=validation,
            )
        if self.validation_policy.blocks and validation.status.value == "fail":
            blocked = {
                "status": "error",
                "message": "Blocked by OCL validation before CoffeeBench execution.",
                "ocl_decision": "block",
                "ocl_validation": jsonable(validation),
            }
            self.logger.record_tool_call(
                action_name=action_name,
                action_input=action_input,
                result=blocked,
                context=context,
            )
            return blocked
        try:
            result = original_tool(**action_input)
        except BaseException as exc:
            self.logger.record_tool_exception(
                action_name=action_name,
                action_input=action_input,
                exception=exc,
                context=context,
            )
            raise
        self.logger.record_tool_call(
            action_name=action_name,
            action_input=action_input,
            result=result,
            context=context,
        )
        if self.validation_policy.validates and isinstance(result, dict):
            result = dict(result)
            result["ocl_validation"] = jsonable(validation)
        return result

    def _validate(self, action_name: str, action_input: dict[str, Any]):
        if not self.validation_policy.validates and action_name != "make_offer":
            from .contracts import ValidationResult, ValidationStatus

            return ValidationResult(status=ValidationStatus.NOT_RUN)
        return validate_operational_action(self.business_app, action_name, action_input)

    def _replace_tool(self, name: str, tool: Callable[..., dict]) -> None:
        replaced = False
        new_tools = []
        for existing in self.agent.tools:
            if getattr(existing, "__name__", "") == name:
                new_tools.append(tool)
                replaced = True
            else:
                new_tools.append(existing)
        if not replaced:
            new_tools.append(tool)
        self.agent.tools = new_tools

    def _add_tools(self, tools: list[Callable[..., dict]]) -> None:
        existing_names = {getattr(t, "__name__", "") for t in self.agent.tools}
        for tool in tools:
            if getattr(tool, "__name__", "") not in existing_names:
                self.agent.tools.append(tool)

    def _remove_tools(self, names: tuple[str, ...]) -> None:
        hidden = set(names)
        self.agent.tools = [tool for tool in self.agent.tools if getattr(tool, "__name__", "") not in hidden]

    def _refresh_agent_tools(self) -> None:
        from coffeebench.models.types import ToolSpec  # noqa: PLC0415

        self.agent.tools_by_name = {tool.__name__: tool for tool in self.agent.tools}
        self.agent.tool_specs = [ToolSpec.from_function(tool) for tool in self.agent.tools]


def _snapshot_context(business_app: Any, action_name: str, action_input: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {
        "day": business_app._today(),
        "agent_id": business_app.agent_id,
    }
    marketplace = business_app.marketplace
    if action_name == "make_offer":
        listing_id = str(action_input.get("listing_id") or "")
        context["listing"] = _dataclass_dict(_find_by_id(marketplace.listings, listing_id))
    elif action_name == "withdraw_offer":
        offer_id = str(action_input.get("offer_id") or "")
        context["offer"] = _dataclass_dict(_find_by_id(marketplace.offers, offer_id))
    elif action_name == "accept_offer":
        offer_id = str(action_input.get("offer_id") or "")
        offer = _find_by_id(marketplace.offers, offer_id)
        context["offer"] = _dataclass_dict(offer)
        context["offer_id"] = offer_id
        context["listing"] = _dataclass_dict(_find_by_id(marketplace.listings, getattr(offer, "listing_id", "")))
    elif action_name in {"pay_invoice", "return_shipment"}:
        invoice_id = str(action_input.get("invoice_id") or "")
        invoice = _find_by_id(business_app.accounts_payable, invoice_id)
        context["invoice"] = _dataclass_dict(invoice)
        context["deal"] = _dataclass_dict(_find_by_id(marketplace.deals, getattr(invoice, "reference", "")))
    return jsonable(context)


def _call_input_from_bound_method(tool: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    signature = inspect.signature(tool)
    bound = signature.bind_partial(*args, **kwargs)
    return dict(bound.arguments)


def _find_by_id(rows: list[Any], object_id: str) -> Any | None:
    for row in rows:
        if getattr(row, "id", None) == object_id:
            return row
    return None


def _dataclass_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return {}


def _open_invoice(invoice: Any) -> bool:
    return (
        not getattr(invoice, "paid", False)
        and not getattr(invoice, "returned", False)
        and not getattr(invoice, "bad_debt", False)
        and float(getattr(invoice, "net_outstanding", 0.0) or 0.0) > 0
    )


def _invoice_row(invoice: Any, today: int) -> dict[str, Any]:
    due_day = int(getattr(invoice, "due_date", today) or today)
    return {
        "id": getattr(invoice, "id", ""),
        "issuer": getattr(invoice, "issuer", ""),
        "payer": getattr(invoice, "payer", ""),
        "amount": round(float(getattr(invoice, "amount", 0.0) or 0.0), 2),
        "outstanding": round(float(getattr(invoice, "net_outstanding", 0.0) or 0.0), 2),
        "due_day": due_day,
        "days_to_due": due_day - today,
        "overdue": due_day < today,
        "reference": getattr(invoice, "reference", None),
    }
