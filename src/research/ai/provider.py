"""LLM Provider Abstraction.

No core research component imports a specific LLM SDK.
All providers implement the same interface.

The AI must fail closed — provider errors are never swallowed.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResponse:
    """Structured response from an LLM provider."""
    content: str
    model: str = ""
    model_version: str = ""
    provider: str = ""
    tokens_used: int = 0
    finish_reason: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract LLM provider interface.

    Implementations: MockLLMProvider, AnthropicProvider, OpenAIProvider.
    Core research never imports provider SDKs directly.
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            prompt: User/research prompt.
            system_prompt: System instructions.
            temperature: Sampling temperature.
            max_tokens: Max response tokens.

        Returns:
            LLMResponse with content.

        Raises:
            Exception on provider failure (never swallowed).
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is configured and reachable."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g., 'anthropic', 'openai', 'mock')."""
        ...


class MockLLMProvider(LLMProvider):
    """Mock provider for testing. Returns deterministic structured proposals.

    Never makes real API calls. Used when AI is disabled or in tests.
    """

    def __init__(self, responses: Optional[list[str]] = None) -> None:
        """Initialize with optional predefined responses.

        Args:
            responses: List of response strings to return in order.
                      If exhausted, returns a default valid proposal.
        """
        self._responses = list(responses) if responses else []
        self._call_count = 0
        self._calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def calls(self) -> list[dict[str, Any]]:
        """Record of all calls made."""
        return list(self._calls)

    @property
    def provider_name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        self._call_count += 1
        self._calls.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })

        if self._responses:
            content = self._responses.pop(0)
        else:
            # Default: return a valid structured proposal
            content = json.dumps({
                "market_type": "CORNERS_TOTAL",
                "feature_ids": ["dangerous_attacks_home"],
                "conditions": [{"feature_id": "dangerous_attacks_home", "operator": ">", "threshold": 35.0}],
                "direction": "OVER",
                "operator_type": "THRESHOLD_GT",
                "model_type": "historical_frequency",
                "model_parameters": {},
                "rationale": "Mock AI proposal for testing",
                "confidence": 0.6,
            })

        return LLMResponse(
            content=content,
            model="mock-model",
            model_version="1.0",
            provider="mock",
            tokens_used=len(content),
        )


class DisabledProvider(LLMProvider):
    """Provider that always indicates AI is unavailable."""

    @property
    def provider_name(self) -> str:
        return "disabled"

    def is_available(self) -> bool:
        return False

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        raise RuntimeError("AI is disabled. No LLM provider configured.")
