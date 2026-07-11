"""Provider configuration tests for OpenAI-compatible backends."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import aimai_ocl.adapters as adapters_mod
from aimai_ocl.adapters import DEFAULT_DASHSCOPE_BASE_URL, build_model_client
from aimai_ocl.config import load_config


class ProviderConfigTests(unittest.TestCase):
    """Check that Qwen/DashScope can use its own env without network calls."""

    def test_qwen_baseline_config_selects_dashscope_provider(self) -> None:
        """Input: Qwen benchmark YAML. Output: dashscope provider config."""
        with patch.dict(os.environ, {}, clear=True):
            config = load_config("configs/benchmark_baselines_qwen.yaml")

        self.assertEqual("dashscope", config.provider)
        self.assertEqual("qwen-plus", config.model)
        self.assertEqual("DASHSCOPE_API_KEY", config.api_key_env)

    def test_dashscope_provider_uses_dashscope_key_and_default_base_url(self) -> None:
        """Input: dashscope provider with DASHSCOPE_API_KEY only.

        Expected output: OpenAI-compatible client uses DashScope key/base URL.
        """
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "dash-key"}, clear=True):
            with patch.object(adapters_mod, "load_env_file", lambda: None):
                client = build_model_client(
                    provider="dashscope",
                    model="qwen-plus",
                    api_sleep_sec=0,
                )

        self.assertEqual("dash-key", client._client.api_key)
        self.assertEqual(DEFAULT_DASHSCOPE_BASE_URL, client._client.base_url)

    def test_dashscope_provider_honors_dashscope_base_url_env(self) -> None:
        """Input: DASHSCOPE_BASE_URL override. Output: client uses override."""
        custom_base_url = "https://example.test/compatible-mode/v1"
        with patch.dict(
            os.environ,
            {
                "DASHSCOPE_API_KEY": "dash-key",
                "DASHSCOPE_BASE_URL": custom_base_url,
            },
            clear=True,
        ):
            with patch.object(adapters_mod, "load_env_file", lambda: None):
                client = build_model_client(
                    provider="dashscope",
                    model="qwen-plus",
                    api_sleep_sec=0,
                )

        self.assertEqual(custom_base_url, client._client.base_url)

    def test_dashscope_provider_strips_smart_quotes_from_env(self) -> None:
        """Input: smart-quoted DashScope env values. Output: clean client config."""
        with patch.dict(
            os.environ,
            {
                "DASHSCOPE_API_KEY": "\u201cdash-key\u201d",
                "DASHSCOPE_BASE_URL": "\u201chttps://example.test/v1\u201d",
            },
            clear=True,
        ):
            with patch.object(adapters_mod, "load_env_file", lambda: None):
                client = build_model_client(
                    provider="dashscope",
                    model="qwen-plus",
                    api_sleep_sec=0,
                )

        self.assertEqual("dash-key", client._client.api_key)
        self.assertEqual("https://example.test/v1", client._client.base_url)


if __name__ == "__main__":
    unittest.main()
