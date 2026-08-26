"""Bedrock Configuration — clean, typed configuration for AWS Bedrock.

Supports environment-based configuration and safe defaults.
Never stores credentials — relies on standard AWS credential resolution.

Configuration hierarchy:
    1. Explicit constructor arguments
    2. Environment variables
    3. Safe defaults
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional


# Default model: Claude Sonnet via Bedrock (configurable, not hardcoded)
_DEFAULT_MODEL_ID = "anthropic.claude-sonnet-4-20250514-v1:0"
_DEFAULT_REGION = "us-east-1"
_DEFAULT_MAX_TOKENS = 2000
_DEFAULT_TEMPERATURE = 0.2  # Low temperature for structured research hypotheses
_DEFAULT_TIMEOUT_SECONDS = 60.0
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_MAX_AI_CALLS_PER_RUN = 20
_DEFAULT_MAX_TOTAL_INPUT_TOKENS = 100_000
_DEFAULT_MAX_TOTAL_OUTPUT_TOKENS = 50_000


@dataclass(frozen=True)
class BedrockConfig:
    """Configuration for AWS Bedrock LLM provider.

    All fields are immutable after creation.
    No credentials stored — uses standard AWS credential chain.

    Attributes:
        model_id: Bedrock model identifier (e.g., anthropic.claude-sonnet-4-20250514-v1:0).
        region: AWS region for Bedrock endpoint.
        max_tokens: Maximum tokens per response.
        temperature: Sampling temperature (low = more deterministic).
        timeout_seconds: Request timeout.
        max_retries: Maximum retry attempts for transient failures.
        max_ai_calls_per_run: Hard limit on AI calls in a single research run.
        max_total_input_tokens: Cumulative input token budget per run.
        max_total_output_tokens: Cumulative output token budget per run.
    """

    model_id: str = ""
    region: str = ""
    max_tokens: int = _DEFAULT_MAX_TOKENS
    temperature: float = _DEFAULT_TEMPERATURE
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    max_retries: int = _DEFAULT_MAX_RETRIES
    max_ai_calls_per_run: int = _DEFAULT_MAX_AI_CALLS_PER_RUN
    max_total_input_tokens: int = _DEFAULT_MAX_TOTAL_INPUT_TOKENS
    max_total_output_tokens: int = _DEFAULT_MAX_TOTAL_OUTPUT_TOKENS

    def __post_init__(self) -> None:
        """Resolve defaults from environment if not provided."""
        # Use object.__setattr__ because frozen=True
        if not self.model_id:
            object.__setattr__(
                self, "model_id",
                os.environ.get("BEDROCK_MODEL_ID", _DEFAULT_MODEL_ID),
            )
        if not self.region:
            object.__setattr__(
                self, "region",
                os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", _DEFAULT_REGION)),
            )

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize configuration without any credential information.

        Safe for logging, persistence, and inclusion in research metadata.
        """
        return {
            "model_id": self.model_id,
            "region": self.region,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "max_ai_calls_per_run": self.max_ai_calls_per_run,
            "max_total_input_tokens": self.max_total_input_tokens,
            "max_total_output_tokens": self.max_total_output_tokens,
        }

    @staticmethod
    def from_env() -> "BedrockConfig":
        """Create config purely from environment variables.

        Environment variables:
            BEDROCK_MODEL_ID: Model identifier
            AWS_REGION: AWS region
            BEDROCK_MAX_TOKENS: Max tokens per response
            BEDROCK_TEMPERATURE: Sampling temperature
            BEDROCK_TIMEOUT_SECONDS: Request timeout
            BEDROCK_MAX_RETRIES: Max retry attempts
            BEDROCK_MAX_AI_CALLS: Max AI calls per run
        """
        return BedrockConfig(
            model_id=os.environ.get("BEDROCK_MODEL_ID", _DEFAULT_MODEL_ID),
            region=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", _DEFAULT_REGION)),
            max_tokens=int(os.environ.get("BEDROCK_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS))),
            temperature=float(os.environ.get("BEDROCK_TEMPERATURE", str(_DEFAULT_TEMPERATURE))),
            timeout_seconds=float(os.environ.get("BEDROCK_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS))),
            max_retries=int(os.environ.get("BEDROCK_MAX_RETRIES", str(_DEFAULT_MAX_RETRIES))),
            max_ai_calls_per_run=int(os.environ.get("BEDROCK_MAX_AI_CALLS", str(_DEFAULT_MAX_AI_CALLS_PER_RUN))),
            max_total_input_tokens=int(os.environ.get("BEDROCK_MAX_INPUT_TOKENS", str(_DEFAULT_MAX_TOTAL_INPUT_TOKENS))),
            max_total_output_tokens=int(os.environ.get("BEDROCK_MAX_OUTPUT_TOKENS", str(_DEFAULT_MAX_TOTAL_OUTPUT_TOKENS))),
        )

    def validate(self) -> list[str]:
        """Validate configuration. Returns list of errors (empty = valid)."""
        errors: list[str] = []
        if not self.model_id:
            errors.append("model_id is required")
        if not self.region:
            errors.append("region is required")
        if self.max_tokens < 100:
            errors.append(f"max_tokens too low: {self.max_tokens}")
        if self.max_tokens > 8192:
            errors.append(f"max_tokens too high: {self.max_tokens}")
        if not (0.0 <= self.temperature <= 1.0):
            errors.append(f"temperature must be 0.0-1.0, got {self.temperature}")
        if self.timeout_seconds < 5.0:
            errors.append(f"timeout_seconds too low: {self.timeout_seconds}")
        if self.max_retries < 0 or self.max_retries > 10:
            errors.append(f"max_retries must be 0-10, got {self.max_retries}")
        if self.max_ai_calls_per_run < 1:
            errors.append(f"max_ai_calls_per_run must be >= 1, got {self.max_ai_calls_per_run}")
        return errors
