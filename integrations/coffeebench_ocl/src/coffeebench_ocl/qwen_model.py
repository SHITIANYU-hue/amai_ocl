"""DashScope/Qwen provider for CoffeeBench's tool-use model interface."""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from coffeebench.models._retry import call_with_retry
from coffeebench.models.types import ModelResponse, ToolCall, ToolSpec

load_dotenv()


DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def is_qwen_model_id(model: str) -> bool:
    """Return whether a CoffeeBench model id should use DashScope/Qwen."""

    normalized = model.removeprefix("dashscope/").removeprefix("qwen/")
    return normalized.startswith(("qwen", "qwq"))


def build_qwen_model(model: str) -> "DashScopeQwenModel":
    """Build a DashScope model from a CoffeeBench model id.

    Supported ids include `qwen-plus`, `qwen-plus-no-thinking`,
    `qwen/qwen-plus`, and `dashscope/qwen-plus`.
    """

    model_id = model.removeprefix("dashscope/").removeprefix("qwen/")
    enable_thinking = False
    if model_id.endswith("-no-thinking"):
        model_id = model_id[: -len("-no-thinking")]
    elif model_id.endswith("-thinking"):
        model_id = model_id[: -len("-thinking")]
        enable_thinking = True
    return DashScopeQwenModel(model=model_id, enable_thinking=enable_thinking)


def install_qwen_provider() -> None:
    """Patch CoffeeBench's model registry to recognize DashScope/Qwen ids."""

    import coffeebench.main as coffee_main  # noqa: PLC0415
    import coffeebench.models as coffee_models  # noqa: PLC0415

    original_get_model = getattr(
        coffee_models,
        "_ocl_original_get_model",
        coffee_models.get_model,
    )
    coffee_models._ocl_original_get_model = original_get_model

    def get_model_with_qwen(model: str):
        if is_qwen_model_id(model):
            return build_qwen_model(model)
        return original_get_model(model)

    coffee_models.get_model = get_model_with_qwen
    coffee_main.get_model = get_model_with_qwen


class DashScopeQwenModel:
    """Qwen via DashScope's OpenAI-compatible Chat Completions API."""

    DEFAULT_MAX_INPUT_TOKENS = 128_000

    def __init__(self, model: str = "qwen-plus", enable_thinking: bool = False) -> None:
        self.provider_model = model
        # CoffeeBench Agent.init routes slash-style models through a system
        # message, which matches the OpenAI-compatible Chat Completions path.
        self.model = f"qwen/{model}"
        self.cost = 0.0
        self.n_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.last_input_tokens = 0
        self.max_input_tokens = self.DEFAULT_MAX_INPUT_TOKENS
        self.max_tokens = int(os.getenv("DASHSCOPE_MAX_TOKENS", "4096"))
        self.temperature = float(os.getenv("DASHSCOPE_TEMPERATURE", "0"))
        self._skip_temperature = False
        self._sent_cost_notice = False
        self.enable_thinking = enable_thinking
        api_key = _clean_env_value(os.getenv("DASHSCOPE_API_KEY"))
        if not api_key:
            raise ValueError("DASHSCOPE_API_KEY is not set.")
        self.client = OpenAI(
            api_key=api_key,
            base_url=_clean_env_value(os.getenv("DASHSCOPE_BASE_URL"))
            or DEFAULT_DASHSCOPE_BASE_URL,
            timeout=300.0,
        )

    @staticmethod
    def _tools_to_chatcompletions(tools: list[ToolSpec] | None) -> list[dict] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]

    def _to_chat_messages(self, messages: list[dict]) -> list[dict]:
        out: list[dict] = []
        for message in messages:
            role = message.get("role")
            if role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": message["tool_call_id"],
                        "content": message.get("content", ""),
                    }
                )
                continue
            if role == "assistant":
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": message.get("content") or None,
                }
                tool_calls = message.get("tool_calls") or []
                if tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": call.id if isinstance(call, ToolCall) else call["id"],
                            "type": "function",
                            "function": {
                                "name": call.name if isinstance(call, ToolCall) else call["name"],
                                "arguments": json.dumps(
                                    call.input if isinstance(call, ToolCall) else call["input"]
                                ),
                            },
                        }
                        for call in tool_calls
                    ]
                out.append(assistant_msg)
                continue
            out.append({"role": role, "content": message.get("content", "")})
        return out

    def query(
        self,
        messages: list[dict],
        tools: list[ToolSpec] | None = None,
        tool_choice: str | dict | None = None,
    ) -> ModelResponse:
        kwargs = self._base_kwargs(messages)
        chat_tools = self._tools_to_chatcompletions(tools)
        if chat_tools:
            kwargs["tools"] = chat_tools
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice
            kwargs["parallel_tool_calls"] = False

        response = call_with_retry(
            lambda: self._create_chat_completion(kwargs),
            label=f"dashscope:{self.provider_model}",
        )
        cost = self._record_usage(response)
        choice = response.choices[0]
        msg = choice.message
        tool_calls: list[ToolCall] = []
        for tool_call in msg.tool_calls or []:
            try:
                args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
            except (TypeError, ValueError):
                args = {}
            tool_calls.append(ToolCall(id=tool_call.id, name=tool_call.function.name, input=args))
        return ModelResponse(
            content=msg.content or "",
            thinking="",
            tool_calls=tool_calls,
            stop_reason=getattr(choice, "finish_reason", "") or "",
            cost=cost,
            raw=None,
        )

    def summarize(self, instructions: str, content: str, max_tokens: int = 8192) -> str:
        kwargs = {
            "model": self.provider_model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": content},
            ],
            "max_tokens": int(max_tokens),
        }
        if not self._skip_temperature:
            kwargs["temperature"] = self.temperature
        response = call_with_retry(
            lambda: self._create_chat_completion(kwargs),
            label=f"dashscope:{self.provider_model}:summarize",
        )
        self._record_usage(response)
        return response.choices[0].message.content or ""

    def get_usage_stats(self) -> dict:
        return {
            "n_model_calls": self.n_calls,
            "model_cost": self.cost,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "last_input_tokens": self.last_input_tokens,
        }

    def _base_kwargs(self, messages: list[dict]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.provider_model,
            "messages": self._to_chat_messages(messages),
            "max_tokens": self.max_tokens,
        }
        if not self._skip_temperature:
            kwargs["temperature"] = self.temperature
        return kwargs

    def _create_chat_completion(self, kwargs: dict[str, Any]):
        try:
            return self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            msg = str(exc).lower()
            if "temperature" in msg and "temperature" in kwargs:
                self._skip_temperature = True
                kwargs.pop("temperature", None)
                return self.client.chat.completions.create(**kwargs)
            if "parallel_tool_calls" in msg and "parallel_tool_calls" in kwargs:
                kwargs.pop("parallel_tool_calls", None)
                return self.client.chat.completions.create(**kwargs)
            raise

    def _record_usage(self, response: Any) -> float:
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        if details is not None:
            cached = int(getattr(details, "cached_tokens", 0) or 0)
        non_cached = max(0, prompt_tokens - cached)
        cost = self._completion_cost(non_cached, cached, completion_tokens)
        self.n_calls += 1
        self.cost += cost
        self.last_input_tokens = prompt_tokens
        self.total_input_tokens += prompt_tokens
        self.total_output_tokens += completion_tokens
        print(
            f"[dashscope:{self.provider_model}] in={prompt_tokens} "
            f"cached={cached} out={completion_tokens}"
        )
        return cost

    def _completion_cost(self, non_cached: int, cached: int, output: int) -> float:
        input_rate = float(os.getenv("DASHSCOPE_INPUT_USD_PER_MTOK", "0") or 0)
        cached_rate = float(os.getenv("DASHSCOPE_CACHED_INPUT_USD_PER_MTOK", "0") or 0)
        output_rate = float(os.getenv("DASHSCOPE_OUTPUT_USD_PER_MTOK", "0") or 0)
        if input_rate == cached_rate == output_rate == 0 and not self._sent_cost_notice:
            print(
                "[dashscope] token usage is tracked, but USD cost is 0 because "
                "DASHSCOPE_*_USD_PER_MTOK rates are unset."
            )
            self._sent_cost_notice = True
        return (
            non_cached * input_rate
            + cached * cached_rate
            + output * output_rate
        ) / 1_000_000


def _clean_env_value(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().strip("\"'“”‘’")
