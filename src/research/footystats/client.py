"""Synchronous FootyStats API client for research use.

This is a research-layer client that does NOT modify the frozen
src/ingestion/client.py. It provides synchronous access suitable
for batch research operations.

Features:
- Synchronous (research doesn't need async)
- Rate limiting (respects 1800 req/hr)
- Exponential backoff retries
- Pagination support
- Credential injection from environment
- No credential serialization
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import re

import httpx

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# API-key redaction for logs
# --------------------------------------------------------------------------- #
# The FootyStats API authenticates via a ``key=<API_KEY>`` query parameter, so
# any log record that includes a request URL (notably httpx/httpcore INFO logs)
# would otherwise echo the real key. This filter scrubs the value of any
# ``key=...`` query param from every log record's message and args, wherever it
# is attached. It is installed on the httpx/httpcore loggers and this module's
# logger at import time so the key can never reach a handler in cleartext.
_KEY_QUERY_RE = re.compile(r"(key=)[^&\s\"']+")
_REDACTED = r"\1<redacted>"


class _RedactApiKeyFilter(logging.Filter):
    """Logging filter that redacts ``key=<value>`` query params from records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if isinstance(record.msg, str) and "key=" in record.msg:
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
        except Exception:  # pragma: no cover - never let logging break a request
            return True
        return True


_REDACT_FILTER = _RedactApiKeyFilter()

# Install on the loggers most likely to render a full request URL. A Filter on a
# logger only runs for records logged *at or below* that logger, so we attach it
# both to the named httpx/httpcore loggers (where the request line originates)
# and to any handlers on the root logger (which sees records that propagate up),
# giving defense-in-depth regardless of the host application's logging config.
for _name in (__name__, "httpx", "httpcore", "httpcore.http11", "httpcore.connection"):
    logging.getLogger(_name).addFilter(_REDACT_FILTER)


def _install_root_handler_redaction() -> None:
    """Attach the redaction filter to existing root handlers (idempotent).

    Handlers run their own filters on every record they emit, including records
    that propagate up from child loggers, so this catches the case where httpx
    logs on a differently-named logger than the ones enumerated above.
    """
    for _handler in logging.getLogger().handlers:
        if _REDACT_FILTER not in _handler.filters:
            _handler.addFilter(_REDACT_FILTER)


_install_root_handler_redaction()


_BASE_URL = "https://api.football-data-api.com"
_DEFAULT_RATE_LIMIT = 2.0  # seconds between requests (conservative)
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_TIMEOUT = 30.0
_DEFAULT_MAX_PER_PAGE = 300


class AuthenticationError(Exception):
    """Raised when API authentication fails."""
    pass


class RateLimitError(Exception):
    """Raised when rate limit is exhausted."""
    pass


class FootyStatsResearchClient:
    """Synchronous FootyStats API client for research batch operations.

    Credentials are loaded from environment or passed explicitly.
    Never serialized into research objects, logs, or hashes.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = _BASE_URL,
        rate_limit: float = _DEFAULT_RATE_LIMIT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        timeout: float = _DEFAULT_TIMEOUT,
        cache_dir: Optional[Path] = None,
    ) -> None:
        """Initialize research client.

        Args:
            api_key: API key. If None, reads from FOOTYSTATS_API_KEY env var.
            base_url: API base URL.
            rate_limit: Minimum seconds between requests.
            max_retries: Max retry attempts.
            timeout: Request timeout seconds.
            cache_dir: Directory for response caching. None = no caching.
        """
        self._api_key = api_key or os.environ.get("FOOTYSTATS_API_KEY", "example")
        self._base_url = base_url.rstrip("/")
        self._rate_limit = rate_limit
        self._max_retries = max_retries
        self._timeout = timeout
        self._last_request_time: float = 0.0
        self._request_count: int = 0
        self._cache_dir = cache_dir

        # Re-scan root handlers so redaction covers handlers added after import
        # (callers commonly configure logging before constructing a client).
        _install_root_handler_redaction()

        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def request_count(self) -> int:
        """Total requests made this session."""
        return self._request_count

    def _throttle(self) -> None:
        """Enforce rate limiting."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._rate_limit:
            wait = self._rate_limit - elapsed
            time.sleep(wait)

    def _cache_key(self, endpoint: str, params: dict[str, Any]) -> str:
        """Generate deterministic cache key."""
        # Exclude API key from cache key (security)
        cache_params = {k: v for k, v in sorted(params.items()) if k != "key"}
        return f"{endpoint.strip('/')}_{json.dumps(cache_params, sort_keys=True)}.json"

    def _cache_get(self, key: str) -> Optional[dict[str, Any]]:
        """Get from file cache."""
        if not self._cache_dir:
            return None
        # Sanitize key for filesystem
        safe_key = key.replace("/", "_").replace(" ", "_").replace('"', "")[:200]
        path = self._cache_dir / safe_key
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        return None

    def _cache_put(self, key: str, data: dict[str, Any]) -> None:
        """Store in file cache."""
        if not self._cache_dir:
            return
        safe_key = key.replace("/", "_").replace(" ", "_").replace('"', "")[:200]
        path = self._cache_dir / safe_key
        with open(path, "w") as f:
            json.dump(data, f)

    def _request(
        self, endpoint: str, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Make API request with rate limiting, retries, and caching.

        Args:
            endpoint: API endpoint path.
            params: Query parameters (key added automatically).

        Returns:
            Parsed JSON response.

        Raises:
            AuthenticationError: On 401/403.
            RateLimitError: On 429 after retries exhausted.
            httpx.HTTPStatusError: On other HTTP errors after retries.
        """
        request_params = {"key": self._api_key}
        if params:
            request_params.update(params)

        # Check cache first
        cache_key = self._cache_key(endpoint, request_params)
        cached = self._cache_get(cache_key)
        if cached is not None:
            logger.debug("Cache hit: %s", endpoint)
            return cached

        url = f"{self._base_url}{endpoint}"
        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            self._throttle()
            self._last_request_time = time.monotonic()
            self._request_count += 1

            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url, params=request_params)

                    if response.status_code in (401, 403):
                        raise AuthenticationError(
                            f"Authentication failed (HTTP {response.status_code}). "
                            "Check FOOTYSTATS_API_KEY."
                        )

                    if response.status_code == 429:
                        if attempt < self._max_retries:
                            wait = 2 ** attempt
                            logger.warning("Rate limited. Waiting %ds...", wait)
                            time.sleep(wait)
                            continue
                        raise RateLimitError("Rate limit exhausted after retries.")

                    response.raise_for_status()
                    data = response.json()

                    # Cache successful responses
                    self._cache_put(cache_key, data)
                    return data

            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403):
                    raise AuthenticationError(str(e))
                last_error = e
                if attempt < self._max_retries:
                    wait = 2 ** (attempt - 1)
                    logger.warning(
                        "Request error (attempt %d/%d): %s. Retrying in %ds...",
                        attempt, self._max_retries, str(e)[:100], wait,
                    )
                    time.sleep(wait)

        raise last_error  # type: ignore[misc]

    def fetch_league_list(self) -> list[dict[str, Any]]:
        """Fetch available leagues.

        Returns:
            List of league dicts with season arrays.
        """
        response = self._request("/league-list", {"chosen_leagues_only": "true"})
        return response.get("data", [])

    def fetch_season_matches(
        self,
        season_id: int,
        max_per_page: int = _DEFAULT_MAX_PER_PAGE,
    ) -> list[dict[str, Any]]:
        """Fetch ALL matches for a season (handles pagination).

        Args:
            season_id: FootyStats season/competition ID.
            max_per_page: Results per page (max 500).

        Returns:
            Complete list of raw match records for the season.
        """
        all_matches: list[dict[str, Any]] = []
        page = 1

        while True:
            response = self._request(
                "/league-matches",
                {"season_id": season_id, "max_per_page": max_per_page, "page": page},
            )

            matches = response.get("data", [])
            all_matches.extend(matches)

            pager = response.get("pager", {})
            current_page = pager.get("current_page", 1)
            max_page = pager.get("max_page", 1)

            logger.info(
                "Season %d: page %d/%d, got %d matches (total so far: %d)",
                season_id, current_page, max_page, len(matches), len(all_matches),
            )

            if current_page >= max_page or not matches:
                break
            page += 1

        return all_matches

    def fetch_match_detail(self, match_id: int) -> dict[str, Any]:
        """Fetch detailed data for a single match.

        Args:
            match_id: FootyStats match ID.

        Returns:
            Raw match detail dict.
        """
        response = self._request("/match", {"match_id": match_id})
        return response.get("data", response)
