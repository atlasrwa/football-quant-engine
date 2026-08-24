"""FootyStats API client with rate limiting and retry logic."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Default API base URL
_BASE_URL = "https://api.football-data-api.com"


class FootyStatsClient:
    """Async HTTP client for the FootyStats API.

    Features:
    - Configurable API key (defaults to 'example' for sandbox).
    - Rate limiting (default: 1 request/second).
    - Exponential backoff retries (max 3 attempts) for 4xx/5xx errors.
    """

    def __init__(
        self,
        api_key: str = "example",
        base_url: str = _BASE_URL,
        rate_limit: float = 1.0,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> None:
        """Initialize FootyStatsClient.

        Args:
            api_key: FootyStats API key. Use 'example' for sandbox.
            base_url: API base URL.
            rate_limit: Minimum seconds between requests.
            max_retries: Maximum retry attempts on failure.
            timeout: HTTP request timeout in seconds.
        """
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._rate_limit = rate_limit
        self._max_retries = max_retries
        self._timeout = timeout
        self._last_request_time: float = 0.0

    @property
    def api_key(self) -> str:
        """The configured API key."""
        return self._api_key

    async def _throttle(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._rate_limit:
            wait = self._rate_limit - elapsed
            logger.debug("Rate limit: waiting %.2fs", wait)
            await asyncio.sleep(wait)

    async def _request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a single API request with retries and rate limiting.

        Args:
            endpoint: API endpoint path (e.g., '/league-matches').
            params: Query parameters (key is added automatically).

        Returns:
            Parsed JSON response dict.

        Raises:
            httpx.HTTPStatusError: If all retry attempts fail.
        """
        url = f"{self._base_url}{endpoint}"
        request_params = {"key": self._api_key}
        if params:
            request_params.update(params)

        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            await self._throttle()
            self._last_request_time = time.monotonic()

            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, params=request_params)
                    response.raise_for_status()
                    return response.json()

            except httpx.HTTPStatusError as e:
                last_error = e
                wait_time = 2 ** (attempt - 1)  # 1s, 2s, 4s
                logger.warning(
                    "HTTP %d on attempt %d/%d for %s. Retrying in %ds...",
                    e.response.status_code,
                    attempt,
                    self._max_retries,
                    endpoint,
                    wait_time,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(wait_time)

            except httpx.RequestError as e:
                last_error = e
                wait_time = 2 ** (attempt - 1)
                logger.warning(
                    "Request error on attempt %d/%d for %s: %s. Retrying in %ds...",
                    attempt,
                    self._max_retries,
                    endpoint,
                    str(e),
                    wait_time,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(wait_time)

        # All retries exhausted
        raise last_error  # type: ignore[misc]

    async def fetch_league_matches(
        self, league_id: int, season: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch all matches for a league season.

        Args:
            league_id: The FootyStats league identifier.
            season: Optional season filter.

        Returns:
            List of raw match dicts from the API response.
        """
        params: Dict[str, Any] = {"league_id": league_id}
        if season:
            params["season"] = season

        logger.info("Fetching league matches: league_id=%d, season=%s", league_id, season)
        response = await self._request("/league-matches", params=params)

        matches = response.get("data", [])
        logger.info("Received %d matches from API", len(matches))
        return matches

    async def fetch_match_detail(self, match_id: int) -> Dict[str, Any]:
        """Fetch detailed data for a single match.

        Args:
            match_id: The FootyStats match identifier.

        Returns:
            Raw match detail dict from the API response.
        """
        logger.info("Fetching match detail: match_id=%d", match_id)
        response = await self._request("/match", params={"match_id": match_id})
        return response.get("data", response)
