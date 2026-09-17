"""Small OpenAI-compatible JSON generator for the RetailBench semantic gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class OpenAICompatibleJsonGenerator:
    client: Any
    model: str
    max_tokens: int = 1200

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Return only the strict JSON object requested by the user.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=self.max_tokens,
        )
        content = response.choices[0].message.content
        if isinstance(content, list):
            content = "".join(str(item) for item in content)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("semantic gate returned empty content")
        value = content.strip()
        if value.startswith("```json") and value.endswith("```"):
            value = value[7:-3].strip()
        elif value.startswith("```") and value.endswith("```"):
            value = value[3:-3].strip()
        return value

