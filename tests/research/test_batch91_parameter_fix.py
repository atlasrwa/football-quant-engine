"""Batch 9.1 — Regression tests for sentinel-value removal.

Verifies that explicit parameter values (including the former sentinel values
0.7 and 2000) are preserved exactly, and that None correctly falls through
to provider/config defaults.

Test matrix:
- Omitted temperature → config/provider default
- Explicit temperature=0.7 → exactly 0.7
- Explicit temperature=0.0 → exactly 0.0
- Explicit temperature=0.2 → exactly 0.2
- Omitted max_tokens → config/provider default
- Explicit max_tokens=2000 → exactly 2000
- Explicit max_tokens=100 → exactly 100
- Explicit max_tokens=1 → exactly 1 (preserved)
- Configuration defaults propagate correctly
- BedrockLLMProvider resolves None → config values
- BedrockLLMProvider preserves explicit values including former sentinels
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.research.ai.bedrock import BedrockLLMProvider
from src.research.ai.bedrock_config import BedrockConfig
from src.research.ai.provider import LLMProvider, LLMResponse, MockLLMProvider


# ═══════════════════════════════════════════════════════════════════
# MOCK PROVIDER TESTS
# ═══════════════════════════════════════════════════════════════════


class TestMockProviderParameterSemantics:
    """Verify MockLLMProvider correctly handles None vs explicit values."""

    def test_omitted_temperature_uses_default(self):
        """temperature=None → provider default (0.7)."""
        provider = MockLLMProvider()
        provider.generate(prompt="test")
        assert provider.calls[0]["temperature"] == 0.7

    def test_explicit_temperature_0_7_preserved(self):
        """temperature=0.7 → exactly 0.7 (NOT replaced by any sentinel logic)."""
        provider = MockLLMProvider()
        provider.generate(prompt="test", temperature=0.7)
        assert provider.calls[0]["temperature"] == 0.7

    def test_explicit_temperature_0_0_preserved(self):
        """temperature=0.0 → exactly 0.0."""
        provider = MockLLMProvider()
        provider.generate(prompt="test", temperature=0.0)
        assert provider.calls[0]["temperature"] == 0.0

    def test_explicit_temperature_0_2_preserved(self):
        """temperature=0.2 → exactly 0.2."""
        provider = MockLLMProvider()
        provider.generate(prompt="test", temperature=0.2)
        assert provider.calls[0]["temperature"] == 0.2

    def test_explicit_temperature_1_0_preserved(self):
        """temperature=1.0 → exactly 1.0."""
        provider = MockLLMProvider()
        provider.generate(prompt="test", temperature=1.0)
        assert provider.calls[0]["temperature"] == 1.0

    def test_omitted_max_tokens_uses_default(self):
        """max_tokens=None → provider default (2000)."""
        provider = MockLLMProvider()
        provider.generate(prompt="test")
        assert provider.calls[0]["max_tokens"] == 2000

    def test_explicit_max_tokens_2000_preserved(self):
        """max_tokens=2000 → exactly 2000 (NOT replaced by any sentinel logic)."""
        provider = MockLLMProvider()
        provider.generate(prompt="test", max_tokens=2000)
        assert provider.calls[0]["max_tokens"] == 2000

    def test_explicit_max_tokens_100_preserved(self):
        """max_tokens=100 → exactly 100."""
        provider = MockLLMProvider()
        provider.generate(prompt="test", max_tokens=100)
        assert provider.calls[0]["max_tokens"] == 100

    def test_explicit_max_tokens_1_preserved(self):
        """max_tokens=1 → exactly 1 (edge case, preserved)."""
        provider = MockLLMProvider()
        provider.generate(prompt="test", max_tokens=1)
        assert provider.calls[0]["max_tokens"] == 1

    def test_both_none_uses_both_defaults(self):
        """Both omitted → both defaults."""
        provider = MockLLMProvider()
        provider.generate(prompt="test", temperature=None, max_tokens=None)
        assert provider.calls[0]["temperature"] == 0.7
        assert provider.calls[0]["max_tokens"] == 2000

    def test_both_explicit_preserved(self):
        """Both explicit → both preserved exactly."""
        provider = MockLLMProvider()
        provider.generate(prompt="test", temperature=0.5, max_tokens=1500)
        assert provider.calls[0]["temperature"] == 0.5
        assert provider.calls[0]["max_tokens"] == 1500


# ═══════════════════════════════════════════════════════════════════
# BEDROCK PROVIDER TESTS
# ═══════════════════════════════════════════════════════════════════


def _make_bedrock_response(content: str = "test") -> dict:
    return {
        "content": [{"type": "text", "text": content}],
        "model": "anthropic.claude-sonnet-4-20250514-v1:0",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


def _mock_boto3_client(response_body: dict):
    mock_client = MagicMock()
    body_bytes = json.dumps(response_body).encode()
    mock_client.invoke_model.return_value = {"body": BytesIO(body_bytes)}
    return mock_client


class TestBedrockProviderParameterSemantics:
    """Verify BedrockLLMProvider resolves None → config, preserves explicit."""

    @pytest.fixture
    def config(self):
        return BedrockConfig(
            model_id="anthropic.claude-sonnet-4-20250514-v1:0",
            region="us-east-1",
            max_tokens=2000,
            temperature=0.2,  # Config default is 0.2
            timeout_seconds=30.0,
            max_retries=1,
        )

    @patch("src.research.ai.bedrock.BedrockLLMProvider._get_client")
    def test_none_temperature_uses_config_default(self, mock_get_client, config):
        """temperature=None → config.temperature (0.2)."""
        response_body = _make_bedrock_response()
        mock_client = _mock_boto3_client(response_body)
        mock_get_client.return_value = mock_client

        provider = BedrockLLMProvider(config=config)
        provider._available = True

        provider.generate(prompt="test", temperature=None)

        call_body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        assert call_body["temperature"] == 0.2

    @patch("src.research.ai.bedrock.BedrockLLMProvider._get_client")
    def test_explicit_temperature_0_7_preserved(self, mock_get_client, config):
        """temperature=0.7 → exactly 0.7 (NOT replaced by config default 0.2)."""
        response_body = _make_bedrock_response()
        mock_client = _mock_boto3_client(response_body)
        mock_get_client.return_value = mock_client

        provider = BedrockLLMProvider(config=config)
        provider._available = True

        provider.generate(prompt="test", temperature=0.7)

        call_body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        assert call_body["temperature"] == 0.7

    @patch("src.research.ai.bedrock.BedrockLLMProvider._get_client")
    def test_explicit_temperature_0_0_preserved(self, mock_get_client, config):
        """temperature=0.0 → exactly 0.0."""
        response_body = _make_bedrock_response()
        mock_client = _mock_boto3_client(response_body)
        mock_get_client.return_value = mock_client

        provider = BedrockLLMProvider(config=config)
        provider._available = True

        provider.generate(prompt="test", temperature=0.0)

        call_body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        assert call_body["temperature"] == 0.0

    @patch("src.research.ai.bedrock.BedrockLLMProvider._get_client")
    def test_none_max_tokens_uses_config_default(self, mock_get_client, config):
        """max_tokens=None → config.max_tokens (2000)."""
        response_body = _make_bedrock_response()
        mock_client = _mock_boto3_client(response_body)
        mock_get_client.return_value = mock_client

        provider = BedrockLLMProvider(config=config)
        provider._available = True

        provider.generate(prompt="test", max_tokens=None)

        call_body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        assert call_body["max_tokens"] == 2000

    @patch("src.research.ai.bedrock.BedrockLLMProvider._get_client")
    def test_explicit_max_tokens_2000_preserved(self, mock_get_client, config):
        """max_tokens=2000 → exactly 2000 (same as config, but explicitly set)."""
        response_body = _make_bedrock_response()
        mock_client = _mock_boto3_client(response_body)
        mock_get_client.return_value = mock_client

        provider = BedrockLLMProvider(config=config)
        provider._available = True

        provider.generate(prompt="test", max_tokens=2000)

        call_body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        assert call_body["max_tokens"] == 2000

    @patch("src.research.ai.bedrock.BedrockLLMProvider._get_client")
    def test_explicit_max_tokens_500_preserved(self, mock_get_client, config):
        """max_tokens=500 → exactly 500."""
        response_body = _make_bedrock_response()
        mock_client = _mock_boto3_client(response_body)
        mock_get_client.return_value = mock_client

        provider = BedrockLLMProvider(config=config)
        provider._available = True

        provider.generate(prompt="test", max_tokens=500)

        call_body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        assert call_body["max_tokens"] == 500

    @patch("src.research.ai.bedrock.BedrockLLMProvider._get_client")
    def test_config_override_with_different_defaults(self, mock_get_client):
        """Different config values propagate when None passed."""
        custom_config = BedrockConfig(
            model_id="anthropic.claude-sonnet-4-20250514-v1:0",
            region="us-east-1",
            max_tokens=4096,
            temperature=0.5,
            timeout_seconds=30.0,
            max_retries=1,
        )
        response_body = _make_bedrock_response()
        mock_client = _mock_boto3_client(response_body)
        mock_get_client.return_value = mock_client

        provider = BedrockLLMProvider(config=custom_config)
        provider._available = True

        # Pass None → should get config values
        provider.generate(prompt="test", temperature=None, max_tokens=None)

        call_body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        assert call_body["temperature"] == 0.5
        assert call_body["max_tokens"] == 4096

    @patch("src.research.ai.bedrock.BedrockLLMProvider._get_client")
    def test_explicit_overrides_config(self, mock_get_client):
        """Explicit values override config regardless of config values."""
        custom_config = BedrockConfig(
            model_id="anthropic.claude-sonnet-4-20250514-v1:0",
            region="us-east-1",
            max_tokens=4096,
            temperature=0.5,
            timeout_seconds=30.0,
            max_retries=1,
        )
        response_body = _make_bedrock_response()
        mock_client = _mock_boto3_client(response_body)
        mock_get_client.return_value = mock_client

        provider = BedrockLLMProvider(config=custom_config)
        provider._available = True

        # Pass explicit values different from config
        provider.generate(prompt="test", temperature=0.9, max_tokens=100)

        call_body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        assert call_body["temperature"] == 0.9
        assert call_body["max_tokens"] == 100


# ═══════════════════════════════════════════════════════════════════
# INTERFACE CONTRACT TEST
# ═══════════════════════════════════════════════════════════════════


class TestLLMProviderInterface:
    """Verify the LLMProvider ABC signature uses Optional[None] semantics."""

    def test_generate_accepts_none_temperature(self):
        """The interface must accept None for temperature."""
        provider = MockLLMProvider()
        # This must not raise TypeError
        response = provider.generate(prompt="test", temperature=None)
        assert response.content != ""

    def test_generate_accepts_none_max_tokens(self):
        """The interface must accept None for max_tokens."""
        provider = MockLLMProvider()
        # This must not raise TypeError
        response = provider.generate(prompt="test", max_tokens=None)
        assert response.content != ""

    def test_generate_default_omission(self):
        """Calling without temperature/max_tokens must work (defaults to None)."""
        provider = MockLLMProvider()
        response = provider.generate(prompt="test")
        assert response.content != ""
