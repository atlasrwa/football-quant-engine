"""Live FootyStats API client with rate limiting and disk caching.

Provides async access to FootyStats JSON endpoints with token-bucket
rate limiting and content-hash disk caching to avoid duplicate credit
consumption.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


class TokenBucket:
    """Async-compatible token bucket rate limiter.

    Allows `capacity` requests initially, then refills at `rate` tokens/second.
    """

    def __init__(self, rate: float = 1.0, capacity: int = 60) -> None:
        """Initialize token bucket.

        Args:
            rate: Tokens added per second (default 1.0 = 60/min).
            capacity: Maximum burst capacity.
        """
        self.rate = rate
        self.capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            self._refill()
            while self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self.rate
                await asyncio.sleep(wait_time)
                self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    @property
    def available_tokens(self) -> float:
        """Current available tokens (approximate)."""
        self._refill()
        return self._tokens


class DiskCache:
    """Simple file-based disk cache with TTL support.

    Uses JSON files keyed by content hash. No external dependencies.
    """

    def __init__(self, cache_dir: str = "data/cache") -> None:
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, ttl: int = 3600) -> dict | None:
        """Get cached value if not expired.

        Args:
            key: Cache key.
            ttl: Time-to-live in seconds.

        Returns:
            Cached data or None if miss/expired.
        """
        path = self._path(key)
        if not path.exists():
            return None

        try:
            with open(path, "r") as f:
                entry = json.load(f)
            if time.time() - entry.get("_ts", 0) > ttl:
                path.unlink(missing_ok=True)
                return None
            return entry.get("data")
        except (json.JSONDecodeError, OSError):
            return None

    def put(self, key: str, data: Any) -> None:
        """Store value in cache.

        Args:
            key: Cache key.
            data: JSON-serializable data.
        """
        path = self._path(key)
        entry = {"_ts": time.time(), "data": data}
        try:
            with open(path, "w") as f:
                json.dump(entry, f)
        except OSError as e:
            logger.warning("Cache write failed for key %s: %s", key, e)

    def _path(self, key: str) -> Path:
        """Get file path for a cache key."""
        return self._dir / f"{key}.json"

    @staticmethod
    def make_key(endpoint: str, params: dict) -> str:
        """Generate a deterministic cache key from endpoint + params."""
        content = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()


class FootyStatsAPIClient:
    """Async client for the FootyStats JSON API.

    Features:
    - Token-bucket rate limiting (60 req/min default)
    - Disk cache with configurable TTL
    - Exponential backoff retry on 429/5xx
    - API key via environment variable
    """

    BASE_URL = "https://api.football-data-api.com"
    MAX_RETRIES = 3

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: str = "data/cache",
        rate_limit: float = 1.0,
        rate_capacity: int = 60,
        cache_ttl_live: int = 3600,
        cache_ttl_historical: int = 86400,
        timeout: float = 30.0,
    ) -> None:
        """Initialize API client.

        Args:
            api_key: FootyStats API key (falls back to FOOTYSTATS_API_KEY env var).
            cache_dir: Directory for disk cache.
            rate_limit: Tokens per second for rate limiter.
            rate_capacity: Maximum burst capacity.
            cache_ttl_live: Cache TTL for live/today data (seconds).
            cache_ttl_historical: Cache TTL for historical data (seconds).
            timeout: HTTP request timeout (seconds).
        """
        self.api_key = api_key or os.environ.get("FOOTYSTATS_API_KEY", "")
        self.cache = DiskCache(cache_dir)
        self.rate_limiter = TokenBucket(rate=rate_limit, capacity=rate_capacity)
        self.cache_ttl_live = cache_ttl_live
        self.cache_ttl_historical = cache_ttl_historical
        self.timeout = timeout

    async def get_todays_matches(
        self, league_id: int | None = None
    ) -> List[dict]:
        """Fetch today's matches across leagues.

        Args:
            league_id: Optional league filter.

        Returns:
            List of match dicts.
        """
        params: Dict[str, Any] = {}
        if league_id is not None:
            params["league_id"] = league_id

        data = await self._request("/todays-matches", params, ttl=self.cache_ttl_live)
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        if isinstance(data, list):
            return data
        return []

    async def get_match(self, match_id: int) -> dict:
        """Fetch detailed stats for a single match.

        Args:
            match_id: FootyStats match ID.

        Returns:
            Match detail dict.
        """
        params = {"match_id": match_id}
        data = await self._request("/match", params, ttl=self.cache_ttl_historical)
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data if isinstance(data, dict) else {}

    async def get_league_referees(self, league_id: int) -> List[dict]:
        """Fetch referee statistics for a league.

        Args:
            league_id: League ID.

        Returns:
            List of referee stat dicts.
        """
        params = {"league_id": league_id}
        data = await self._request("/league-referees", params, ttl=self.cache_ttl_historical)
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        if isinstance(data, list):
            return data
        return []

    async def _request(
        self, endpoint: str, params: Dict[str, Any], ttl: int = 3600
    ) -> Any:
        """Make a rate-limited, cached API request with retry.

        Args:
            endpoint: API endpoint path.
            params: Query parameters.
            ttl: Cache TTL for this request.

        Returns:
            Parsed JSON response.
        """
        # Check cache first
        cache_key = self.cache.make_key(endpoint, params)
        cached = self.cache.get(cache_key, ttl=ttl)
        if cached is not None:
            logger.debug("Cache hit: %s", endpoint)
            return cached

        # Rate limit
        await self.rate_limiter.acquire()

        # Build request
        url = f"{self.BASE_URL}{endpoint}"
        request_params = {**params, "key": self.api_key}

        # Retry with exponential backoff
        last_error: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url, params=request_params)

                if response.status_code == 200:
                    data = response.json()
                    self.cache.put(cache_key, data)
                    return data
                elif response.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning("Rate limited (429), waiting %ds", wait)
                    await asyncio.sleep(wait)
                elif response.status_code >= 500:
                    wait = 2 ** (attempt + 1)
                    logger.warning("Server error %d, retry in %ds", response.status_code, wait)
                    await asyncio.sleep(wait)
                else:
                    logger.error("API error %d: %s", response.status_code, response.text[:200])
                    return {}

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                wait = 2 ** (attempt + 1)
                logger.warning("Request failed (%s), retry in %ds", type(e).__name__, wait)
                await asyncio.sleep(wait)

        logger.error("All retries exhausted for %s: %s", endpoint, last_error)
        return {}
