"""Unit tests for FootyStats live API client."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from src.engine.analysis.data.footystats_api import (
    DiskCache,
    FootyStatsAPIClient,
    TokenBucket,
)


class TestTokenBucket:
    """Tests for the async token bucket rate limiter."""

    def test_initial_capacity(self):
        """Bucket starts with full capacity."""
        bucket = TokenBucket(rate=1.0, capacity=10)
        assert bucket.available_tokens == pytest.approx(10.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_acquire_decrements(self):
        """Each acquire reduces available tokens."""
        bucket = TokenBucket(rate=1.0, capacity=10)
        await bucket.acquire()
        assert bucket.available_tokens < 10.0

    @pytest.mark.asyncio
    async def test_acquire_multiple(self):
        """Multiple acquires deplete tokens."""
        bucket = TokenBucket(rate=100.0, capacity=5)
        for _ in range(5):
            await bucket.acquire()
        # Should be near 0 (with some refill from high rate)
        assert bucket.available_tokens < 1.5

    @pytest.mark.asyncio
    async def test_refill_over_time(self):
        """Tokens refill based on elapsed time and rate."""
        bucket = TokenBucket(rate=100.0, capacity=10)
        # Drain 5 tokens
        for _ in range(5):
            await bucket.acquire()
        # Wait a bit for refill
        await asyncio.sleep(0.05)
        # Should have refilled ~5 tokens at 100/s
        assert bucket.available_tokens > 3.0

    @pytest.mark.asyncio
    async def test_capacity_cap(self):
        """Tokens never exceed capacity."""
        bucket = TokenBucket(rate=1000.0, capacity=5)
        await asyncio.sleep(0.1)  # Would generate 100 tokens
        assert bucket.available_tokens <= 5.0

    @pytest.mark.asyncio
    async def test_acquire_waits_when_empty(self):
        """Acquire blocks when no tokens available."""
        bucket = TokenBucket(rate=100.0, capacity=1)
        await bucket.acquire()  # Drain the single token

        start = time.monotonic()
        await bucket.acquire()  # Must wait for refill
        elapsed = time.monotonic() - start

        # Should have waited ~0.01s (1 token at 100/s)
        assert elapsed >= 0.005


class TestDiskCache:
    """Tests for the file-based disk cache."""

    def test_put_and_get(self, tmp_path):
        """Basic put/get cycle."""
        cache = DiskCache(str(tmp_path))
        cache.put("key1", {"value": 42})

        result = cache.get("key1")
        assert result == {"value": 42}

    def test_get_miss(self, tmp_path):
        """Missing key returns None."""
        cache = DiskCache(str(tmp_path))
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self, tmp_path):
        """Expired entries return None."""
        cache = DiskCache(str(tmp_path))
        cache.put("key1", {"value": 1})

        # Manually backdate the timestamp
        path = cache._path("key1")
        with open(path, "r") as f:
            entry = json.load(f)
        entry["_ts"] = time.time() - 7200  # 2 hours ago
        with open(path, "w") as f:
            json.dump(entry, f)

        # TTL of 1 hour → expired
        assert cache.get("key1", ttl=3600) is None

    def test_ttl_not_expired(self, tmp_path):
        """Fresh entries within TTL are returned."""
        cache = DiskCache(str(tmp_path))
        cache.put("key1", {"value": 1})

        result = cache.get("key1", ttl=3600)
        assert result == {"value": 1}

    def test_make_key_deterministic(self):
        """Same inputs produce same cache key."""
        key1 = DiskCache.make_key("/endpoint", {"a": 1, "b": 2})
        key2 = DiskCache.make_key("/endpoint", {"b": 2, "a": 1})
        assert key1 == key2  # sorted params

    def test_make_key_different_endpoints(self):
        """Different endpoints produce different keys."""
        key1 = DiskCache.make_key("/endpoint1", {"a": 1})
        key2 = DiskCache.make_key("/endpoint2", {"a": 1})
        assert key1 != key2

    def test_overwrite(self, tmp_path):
        """Putting same key overwrites previous value."""
        cache = DiskCache(str(tmp_path))
        cache.put("key1", {"v": 1})
        cache.put("key1", {"v": 2})

        assert cache.get("key1") == {"v": 2}


class TestFootyStatsAPIClient:
    """Tests for FootyStatsAPIClient (without live network)."""

    def test_initialization(self, tmp_path):
        """Client initializes with provided params."""
        client = FootyStatsAPIClient(
            api_key="test_key",
            cache_dir=str(tmp_path),
            rate_limit=2.0,
            rate_capacity=120,
        )
        assert client.api_key == "test_key"
        assert client.cache_ttl_live == 3600
        assert client.cache_ttl_historical == 86400

    def test_api_key_from_env(self, tmp_path, monkeypatch):
        """API key falls back to environment variable."""
        monkeypatch.setenv("FOOTYSTATS_API_KEY", "env_key")
        client = FootyStatsAPIClient(cache_dir=str(tmp_path))
        assert client.api_key == "env_key"

    @pytest.mark.asyncio
    async def test_cache_hit_avoids_request(self, tmp_path):
        """Cached data is returned without making HTTP requests."""
        client = FootyStatsAPIClient(api_key="test", cache_dir=str(tmp_path))

        # Pre-populate cache
        cache_key = client.cache.make_key("/todays-matches", {})
        client.cache.put(cache_key, {"data": [{"id": 1}]})

        # This should hit cache (no network needed)
        result = await client.get_todays_matches()
        assert result == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_get_match_cache_hit(self, tmp_path):
        """get_match returns cached data."""
        client = FootyStatsAPIClient(api_key="test", cache_dir=str(tmp_path))

        cache_key = client.cache.make_key("/match", {"match_id": 123})
        client.cache.put(cache_key, {"data": {"id": 123, "goals": 3}})

        result = await client.get_match(123)
        assert result == {"id": 123, "goals": 3}

    @pytest.mark.asyncio
    async def test_get_league_referees_cache_hit(self, tmp_path):
        """get_league_referees returns cached data."""
        client = FootyStatsAPIClient(api_key="test", cache_dir=str(tmp_path))

        cache_key = client.cache.make_key("/league-referees", {"league_id": 4759})
        client.cache.put(cache_key, {"data": [{"name": "Ref1"}]})

        result = await client.get_league_referees(4759)
        assert result == [{"name": "Ref1"}]

    @pytest.mark.asyncio
    async def test_empty_response_on_network_failure(self, tmp_path):
        """Returns empty on total network failure (all retries exhausted)."""
        client = FootyStatsAPIClient(
            api_key="test",
            cache_dir=str(tmp_path),
            timeout=0.01,  # Very short timeout → immediate failure
        )
        # Point to non-routable address
        client.BASE_URL = "http://192.0.2.1"  # RFC 5737 test address

        result = await client._request("/test", {}, ttl=60)
        assert result == {}
