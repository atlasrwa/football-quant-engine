"""Synchronous TheStatsAPI HTTP client for research batch operations.

Safety features (parallel to FootyStatsResearchClient):
- Credentials read only from environment/argument, never committed, never
  serialized into research objects, logs, or hashes.
- Request timeouts on every call.
- Bounded retries with exponential backoff on transient transport errors.
- Explicit handling of 401/403 (auth) and 429 (rate limit).
- API-key redaction filter installed on the loggers most likely to render a
  full request URL (defense in depth).
- Optional file cache that is IDENTITY keyed (endpoint + params, excluding the
  key). Caching a match/fixtures/odds resource by its provider id can never
  violate point-in-time semantics because the resource identity does not depend
  on when it was requested; as-of decisions are made downstream from
  observation timestamps, not from cache freshness.

This client deliberately does NOT know the canonical schema — it returns raw
dicts. Normalization to ResearchMatch / OddsSnapshot happens in the normalizer
modules so raw payloads never reach model code.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

try:  # httpx is already a project dependency (used by the FootyStats client)
    import httpx
except Exception:  # pragma: no cover - import guard
    httpx = None  # type: ignore

from src.research.thestatsapi.exceptions import (
    TheStatsAPIAuthenticationError,
    TheStatsAPIConfigurationError,
    TheStatsAPIRateLimitError,
    TheStatsAPIResponseError,
    TheStatsAPITransportError,
)

logger = logging.getLogger(__name__)

# Redact api-key-looking query params and headers from any log record.
_KEY_QUERY_RE = re.compile(r"((?:api[_-]?key|key|token|apikey)=)[^&\s]+", re.IGNORECASE)
_REDACTED = r"\1<redacted>"


class _RedactApiKeyFilter(logging.Filter):
    """Logging filter that redacts key/token query params from records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if isinstance(record.msg, str):
                record.msg = _KEY_QUERY_RE.sub(_REDACTED, record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: (_KEY_QUERY_RE.sub(_REDACTED, v) if isinstance(v, str) else v)
                        for k, v in record.args.items()
                    }
                else:
                    record.args = tuple(
                        _KEY_QUERY_RE.sub(_REDACTED, a) if isinstance(a, str) else a
                        for a in record.args
                    )
        except Exception:  # pragma: no cover
            return True
        return True


_REDACT_FILTER = _RedactApiKeyFilter()
for _name in (__name__, "httpx", "httpcore", "httpcore.http11", "httpcore.connection"):
    logging.getLogger(_name).addFilter(_REDACT_FILTER)
for _handler in logging.getLogger().handlers:
    if _REDACT_FILTER not in _handler.filters:
        _handler.addFilter(_REDACT_FILTER)


_DEFAULT_BASE_URL = "https://api.thestatsapi.com"
_DEFAULT_RATE_LIMIT = 1.0
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_TIMEOUT = 30.0

# Environment variable names. API key is REQUIRED for live use.
_ENV_API_KEY = "THESTATSAPI_API_KEY"
_ENV_BASE_URL = "THESTATSAPI_BASE_URL"


class TheStatsAPIClient:
    """Synchronous TheStatsAPI client.

    The client is *live-optional*: it can be constructed without a key (so
    tests and cache-backed flows work), but any attempt to perform a network
    request without a key raises TheStatsAPIConfigurationError rather than
    sending a request with an empty credential.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        rate_limit: float = _DEFAULT_RATE_LIMIT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        timeout: float = _DEFAULT_TIMEOUT,
        cache_dir: Optional[Path] = None,
    ) -> None:
        # Never default to a real key. Empty means "not configured".
        self._api_key = api_key if api_key is not None else os.environ.get(_ENV_API_KEY, "")
        self._base_url = (base_url or os.environ.get(_ENV_BASE_URL, _DEFAULT_BASE_URL)).rstrip("/")
        self._rate_limit = rate_limit
        self._max_retries = max_retries
        self._timeout = timeout
        self._cache_dir = Path(cache_dir) if cache_dir else None
        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request_ts = 0.0
        self._client: Optional[Any] = None

    @property
    def is_configured(self) -> bool:
        """Whether a non-empty API key is available for live requests."""
        return bool(self._api_key)

    # -- caching (identity keyed, PIT-safe) ---------------------------------

    def _cache_key(self, endpoint: str, params: dict[str, Any]) -> str:
        # Exclude the api key from the cache key so cached files never encode a
        # credential and are portable across keys.
        safe = {k: v for k, v in sorted(params.items()) if k.lower() not in {"key", "api_key", "token", "apikey"}}
        canonical = json.dumps({"e": endpoint, "p": safe}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:24]

    def _cache_get(self, key: str) -> Optional[dict[str, Any]]:
        if not self._cache_dir:
            return None
        path = self._cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def _cache_put(self, key: str, payload: dict[str, Any]) -> None:
        if not self._cache_dir:
            return
        path = self._cache_dir / f"{key}.json"
        try:
            path.write_text(json.dumps(payload, separators=(",", ":")))
        except OSError:  # pragma: no cover
            logger.warning("Failed to write cache file %s", path)

    # -- rate limiting ------------------------------------------------------

    def _throttle(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_ts
        if elapsed < self._rate_limit:
            time.sleep(self._rate_limit - elapsed)
        self._last_request_ts = time.monotonic()

    def _ensure_client(self) -> Any:
        if httpx is None:  # pragma: no cover
            raise TheStatsAPITransportError("httpx is not available")
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    # -- request ------------------------------------------------------------

    def get(self, endpoint: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Perform a GET request, using the cache if available.

        Args:
            endpoint: Path under the base url (e.g. "/fixtures").
            params: Query params (the api key is added automatically).

        Returns:
            Parsed JSON payload as a dict.

        Raises:
            TheStatsAPIConfigurationError: If no key is configured.
            TheStatsAPIAuthenticationError / TheStatsAPIRateLimitError /
            TheStatsAPITransportError / TheStatsAPIResponseError as appropriate.
        """
        params = dict(params or {})
        cache_key = self._cache_key(endpoint, params)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if not self.is_configured:
            raise TheStatsAPIConfigurationError(
                f"{_ENV_API_KEY} is not set; cannot perform live request to {endpoint}. "
                "Provide an API key via environment or use a cache-backed data source."
            )

        client = self._ensure_client()
        request_params = dict(params)
        request_params["api_key"] = self._api_key
        url = f"{self._base_url}{endpoint}"

        last_exc: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            self._throttle()
            try:
                resp = client.get(url, params=request_params)
            except Exception as exc:  # httpx.RequestError and friends
                last_exc = exc
                wait = 2 ** (attempt - 1)
                logger.warning("Transport error on attempt %d/%d, retrying in %ss",
                               attempt, self._max_retries, wait)
                time.sleep(wait)
                continue

            status = resp.status_code
            if status in (401, 403):
                raise TheStatsAPIAuthenticationError(
                    f"Authentication failed ({status}) for {endpoint}"
                )
            if status == 429:
                retry_after = self._parse_retry_after(resp)
                if attempt >= self._max_retries:
                    raise TheStatsAPIRateLimitError(
                        f"Rate limited (429) for {endpoint}; retries exhausted",
                        retry_after=retry_after,
                    )
                wait = retry_after if retry_after is not None else 2 ** attempt
                logger.warning("Rate limited (429), backing off %ss (attempt %d/%d)",
                               wait, attempt, self._max_retries)
                time.sleep(wait)
                continue
            if status >= 500:
                last_exc = TheStatsAPITransportError(f"Server error {status} for {endpoint}")
                wait = 2 ** (attempt - 1)
                time.sleep(wait)
                continue
            if status >= 400:
                raise TheStatsAPIResponseError(f"Client error {status} for {endpoint}")

            try:
                payload = resp.json()
            except (ValueError, json.JSONDecodeError) as exc:
                raise TheStatsAPIResponseError(f"Invalid JSON from {endpoint}") from exc

            if not isinstance(payload, dict):
                raise TheStatsAPIResponseError(f"Expected object payload from {endpoint}")

            self._cache_put(cache_key, payload)
            return payload

        raise TheStatsAPITransportError(
            f"Request to {endpoint} failed after {self._max_retries} attempts"
        ) from last_exc

    @staticmethod
    def _parse_retry_after(resp: Any) -> Optional[float]:
        try:
            val = resp.headers.get("Retry-After")
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    def __enter__(self) -> "TheStatsAPIClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
