"""AWS Bedrock LLM Provider — production Claude Sonnet integration.

Architecture:
    ResearchAgent
        -> LLMProvider (interface)
            -> BedrockLLMProvider
                -> AWS Bedrock Runtime (boto3)
                    -> Claude Sonnet

Security:
    - No credentials stored in provider state
    - No credentials in prompts, logs, exceptions, or hashes
    - Uses standard AWS credential resolution (IAM role, env, profile)
    - Responses are NEVER executed as code
    - Responses are parsed as structured JSON only

Retry Policy:
    - Transient failures (throttling, timeout, 5xx): retry with backoff
    - Authentication/permission failures (403, AccessDenied): fail immediately
    - Malformed response: no retry (not transient)
    - Bounded retry count (max_retries from config)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from src.research.ai.bedrock_config import BedrockConfig
from src.research.ai.provider import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class BedrockError(Exception):
    """Base exception for Bedrock provider errors."""

    def __init__(self, message: str, retryable: bool = False, error_code: str = "") -> None:
        # Never include credentials in error messages
        super().__init__(message)
        self.retryable = retryable
        self.error_code = error_code


class BedrockAuthenticationError(BedrockError):
    """Authentication/permission failure — not retryable."""

    def __init__(self, message: str = "AWS authentication or permission error") -> None:
        super().__init__(message, retryable=False, error_code="AUTH_ERROR")


class BedrockThrottlingError(BedrockError):
    """Rate limiting — retryable after backoff."""

    def __init__(self, message: str = "Bedrock request throttled") -> None:
        super().__init__(message, retryable=True, error_code="THROTTLED")


class BedrockTimeoutError(BedrockError):
    """Request timeout — retryable."""

    def __init__(self, message: str = "Bedrock request timed out") -> None:
        super().__init__(message, retryable=True, error_code="TIMEOUT")


class BedrockServiceError(BedrockError):
    """Bedrock service error (5xx) — retryable."""

    def __init__(self, message: str = "Bedrock service error") -> None:
        super().__init__(message, retryable=True, error_code="SERVICE_ERROR")


class BedrockUnavailableError(BedrockError):
    """Bedrock not available (missing boto3, bad config)."""

    def __init__(self, message: str = "Bedrock is not available") -> None:
        super().__init__(message, retryable=False, error_code="UNAVAILABLE")


# Non-retryable error codes from AWS
_AUTH_ERROR_CODES = frozenset({
    "AccessDeniedException",
    "UnrecognizedClientException",
    "InvalidIdentityToken",
    "ExpiredTokenException",
})

# Retryable error codes
_THROTTLE_ERROR_CODES = frozenset({
    "ThrottlingException",
    "TooManyRequestsException",
    "ServiceQuotaExceededException",
})

_SERVICE_ERROR_CODES = frozenset({
    "InternalServerException",
    "ServiceUnavailableException",
    "ModelTimeoutException",
})


class BedrockLLMProvider(LLMProvider):
    """AWS Bedrock LLM provider implementing the LLMProvider interface.

    Uses boto3 Bedrock Runtime client to call Claude Sonnet.
    Handles retry logic, error classification, and structured output parsing.

    Never stores or logs AWS credentials.
    Never executes returned content as code.
    """

    def __init__(self, config: Optional[BedrockConfig] = None) -> None:
        """Initialize with optional configuration.

        Args:
            config: BedrockConfig instance. If None, creates from environment.

        Raises:
            BedrockUnavailableError: If boto3 is not installed.
        """
        self._config = config or BedrockConfig.from_env()
        self._client: Any = None
        self._available: Optional[bool] = None

        # Usage tracking (safe metadata only — no credentials)
        self._request_count: int = 0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._total_latency_ms: float = 0.0
        self._failure_count: int = 0

        # Validate configuration
        errors = self._config.validate()
        if errors:
            logger.warning("Bedrock config validation errors: %s", errors)
            self._available = False

    @property
    def provider_name(self) -> str:
        return "bedrock"

    @property
    def config(self) -> BedrockConfig:
        """Read-only access to configuration (safe, no credentials)."""
        return self._config

    @property
    def usage_stats(self) -> dict[str, Any]:
        """Safe usage statistics — no credentials or secrets."""
        return {
            "provider": "bedrock",
            "model_id": self._config.model_id,
            "region": self._config.region,
            "request_count": self._request_count,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_latency_ms": round(self._total_latency_ms, 1),
            "failure_count": self._failure_count,
            "avg_latency_ms": round(
                self._total_latency_ms / max(1, self._request_count), 1
            ),
        }

    def is_available(self) -> bool:
        """Check if Bedrock is configured and reachable.

        Checks:
        1. boto3 is importable
        2. Configuration is valid
        3. Client can be created (credentials resolvable)

        Does NOT make an API call on every check — caches result.
        """
        if self._available is not None:
            return self._available

        # Check boto3 availability
        try:
            import boto3  # noqa: F401
            import botocore  # noqa: F401
        except ImportError:
            logger.info("boto3 not installed — Bedrock unavailable")
            self._available = False
            return False

        # Validate config
        errors = self._config.validate()
        if errors:
            logger.info("Bedrock config invalid: %s", errors)
            self._available = False
            return False

        # Try to create client (validates credentials can be resolved)
        try:
            self._get_client()
            self._available = True
        except Exception as e:
            # Never log credential details
            logger.info("Bedrock client creation failed: %s", type(e).__name__)
            self._available = False

        return self._available

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a response from Claude via Bedrock.

        Args:
            prompt: User/research prompt (never contains credentials).
            system_prompt: System instructions.
            temperature: Sampling temperature. None = use config default.
            max_tokens: Max response tokens. None = use config default.

        Returns:
            LLMResponse with structured content.

        Raises:
            BedrockAuthenticationError: On auth/permission failure.
            BedrockThrottlingError: After all retries exhausted on throttling.
            BedrockTimeoutError: After all retries exhausted on timeout.
            BedrockServiceError: After all retries exhausted on service errors.
            BedrockError: On other non-retryable failures.
        """
        import botocore.exceptions

        client = self._get_client()

        # Resolve None to config defaults; explicit values always preserved
        effective_temperature = temperature if temperature is not None else self._config.temperature
        effective_max_tokens = max_tokens if max_tokens is not None else self._config.max_tokens

        # Build request body for Claude Messages API via Bedrock
        request_body = self._build_request_body(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=effective_temperature,
            max_tokens=effective_max_tokens,
        )

        # Retry loop with exponential backoff
        last_error: Optional[Exception] = None
        for attempt in range(self._config.max_retries + 1):
            if attempt > 0:
                backoff = min(2 ** attempt, 30)  # Cap at 30 seconds
                logger.info("Bedrock retry %d/%d after %ds backoff", attempt, self._config.max_retries, backoff)
                time.sleep(backoff)

            start_time = time.time()
            try:
                response = client.invoke_model(
                    modelId=self._config.model_id,
                    body=json.dumps(request_body),
                    contentType="application/json",
                    accept="application/json",
                )
                elapsed_ms = (time.time() - start_time) * 1000

                # Parse response
                response_body = json.loads(response["body"].read())
                llm_response = self._parse_bedrock_response(response_body, elapsed_ms)

                # Update usage stats
                self._request_count += 1
                self._total_latency_ms += elapsed_ms
                self._total_input_tokens += llm_response.raw_response.get("input_tokens", 0)
                self._total_output_tokens += llm_response.tokens_used

                return llm_response

            except botocore.exceptions.ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                last_error = self._classify_client_error(e, error_code)

                if not last_error.retryable:
                    self._failure_count += 1
                    raise last_error from None

                # Retryable — continue loop
                logger.warning(
                    "Bedrock transient error (attempt %d/%d): %s",
                    attempt + 1, self._config.max_retries + 1, last_error.error_code,
                )

            except botocore.exceptions.ReadTimeoutError:
                last_error = BedrockTimeoutError()
                logger.warning(
                    "Bedrock timeout (attempt %d/%d)",
                    attempt + 1, self._config.max_retries + 1,
                )

            except botocore.exceptions.ConnectTimeoutError:
                last_error = BedrockTimeoutError("Bedrock connection timed out")
                logger.warning(
                    "Bedrock connect timeout (attempt %d/%d)",
                    attempt + 1, self._config.max_retries + 1,
                )

            except json.JSONDecodeError as e:
                # Malformed response — not retryable
                self._failure_count += 1
                raise BedrockError(
                    f"Malformed Bedrock response: {str(e)[:100]}",
                    retryable=False,
                    error_code="MALFORMED_RESPONSE",
                ) from None

            except Exception as e:
                # Unknown error — classify conservatively
                self._failure_count += 1
                raise BedrockError(
                    f"Unexpected Bedrock error: {type(e).__name__}",
                    retryable=False,
                    error_code="UNKNOWN",
                ) from None

        # All retries exhausted
        self._failure_count += 1
        if last_error:
            raise last_error
        raise BedrockError("Bedrock request failed after all retries", retryable=False)

    def _get_client(self) -> Any:
        """Get or create the Bedrock Runtime client.

        Uses standard AWS credential chain — never stores credentials.
        """
        if self._client is not None:
            return self._client

        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError:
            raise BedrockUnavailableError("boto3 is not installed")

        boto_config = BotoConfig(
            region_name=self._config.region,
            read_timeout=int(self._config.timeout_seconds),
            connect_timeout=10,
            retries={"max_attempts": 0},  # We handle retries ourselves
        )

        self._client = boto3.client(
            "bedrock-runtime",
            config=boto_config,
        )
        return self._client

    def _build_request_body(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Build the Bedrock invoke_model request body for Claude Messages API.

        Uses the Claude Messages API format supported by Bedrock.
        """
        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }

        if system_prompt:
            body["system"] = system_prompt

        return body

    def _parse_bedrock_response(
        self, response_body: dict[str, Any], elapsed_ms: float
    ) -> LLMResponse:
        """Parse Bedrock Claude response into LLMResponse.

        Never executes content. Only extracts text.
        """
        # Extract content from Claude Messages API response
        content_blocks = response_body.get("content", [])
        text_content = ""
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_content += block.get("text", "")

        # Extract usage
        usage = response_body.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        # Extract model info
        model_id = response_body.get("model", self._config.model_id)
        stop_reason = response_body.get("stop_reason", "")

        return LLMResponse(
            content=text_content,
            model=model_id,
            model_version=self._config.model_id,
            provider="bedrock",
            tokens_used=output_tokens,
            finish_reason=stop_reason,
            raw_response={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "stop_reason": stop_reason,
                "latency_ms": round(elapsed_ms, 1),
                # Never include credentials, request IDs with auth info, etc.
            },
        )

    def _classify_client_error(self, error: Any, error_code: str) -> BedrockError:
        """Classify AWS ClientError into typed BedrockError.

        Never includes credentials in error messages.
        """
        if error_code in _AUTH_ERROR_CODES:
            return BedrockAuthenticationError()

        if error_code in _THROTTLE_ERROR_CODES:
            return BedrockThrottlingError()

        if error_code in _SERVICE_ERROR_CODES:
            return BedrockServiceError()

        # Model not found
        if error_code == "ValidationException":
            message = str(error)[:200] if error else "Validation error"
            # Sanitize — remove any potential credential info
            if "key" in message.lower() or "secret" in message.lower():
                message = "Bedrock validation error (details redacted)"
            return BedrockError(message, retryable=False, error_code="VALIDATION")

        if error_code == "ModelNotReadyException":
            return BedrockError("Model not ready", retryable=True, error_code="MODEL_NOT_READY")

        # Default: non-retryable
        return BedrockError(
            f"Bedrock error: {error_code}",
            retryable=False,
            error_code=error_code or "UNKNOWN",
        )

    def reset_usage_stats(self) -> None:
        """Reset usage counters (for new research run)."""
        self._request_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_latency_ms = 0.0
        self._failure_count = 0
