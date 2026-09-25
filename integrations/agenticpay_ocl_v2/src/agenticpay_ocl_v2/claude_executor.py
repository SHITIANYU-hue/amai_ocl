"""Minimal Claude HTTP adapter for AgenticPay executor roles."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional


class ClaudeLLM:
    """Expose the generate(...) interface expected by AgenticPay."""

    def __init__(
        self,
        model: str = "claude-sonnet-5",
        api_key: Optional[str] = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError(
                "Anthropic API key is required. "
                "Set ANTHROPIC_API_KEY or pass api_key."
            )

        self.endpoint = "https://api.anthropic.com/v1/messages"

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        # temperature is intentionally ignored for compatibility
        # with current Claude models.
        payload = {
            "model": self.model,
            "max_tokens": max_tokens or 1024,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }

        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Claude API HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Claude API connection error: {exc}"
            ) from exc

        parts = [
            block.get("text", "")
            for block in result.get("content", [])
            if block.get("type") == "text"
        ]

        text = "\n".join(parts).strip()

        if not text:
            raise RuntimeError(
                f"Claude API returned no text content: {result}"
            )

        return text

    def __repr__(self) -> str:
        return f"ClaudeLLM(model={self.model})"
