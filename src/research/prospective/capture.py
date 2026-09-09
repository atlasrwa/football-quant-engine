"""Prospective observation capture — the most important infrastructure.

An append-only capture layer for odds / lineups / match-context. Every capture
is turned into a :class:`~src.research.observation.model.ProviderObservation`
(reusing the existing provenance layer) plus a raw payload record retained for
audit. Earlier observations are NEVER overwritten.

Retrieval time is captured as an ACTUAL wall-clock timestamp at fetch. It is
never backfilled and never snapped to a vintage target.

This module also holds the read-only, key-redacting request helper. It fails
closed when no API key is configured: rather than sending a request with an
empty credential, it raises. The key is never printed, logged, hashed, or
serialized.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.research.observation.model import MISSING, ObservationKey, ProviderObservation
from src.research.prospective.api_contract import (
    ENV_API_KEY,
    Endpoint,
    ProspectiveClientConfig,
    endpoint_path,
)

logger = logging.getLogger(__name__)

# Defense in depth: redact anything that looks like a key/token in log records.
_KEY_RE = re.compile(r"((?:api[_-]?key|key|token|apikey|bearer)\s*[=:]?\s*)\S+", re.IGNORECASE)


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if isinstance(record.msg, str):
                record.msg = _KEY_RE.sub(r"\1<redacted>", record.msg)
        except Exception:  # pragma: no cover
            return True
        return True


_REDACT = _RedactFilter()
for _name in (__name__, "httpx", "httpcore"):
    logging.getLogger(_name).addFilter(_REDACT)


class ProspectiveConfigError(RuntimeError):
    """Raised when a live request is attempted without an API key."""


class ProspectiveTransportError(RuntimeError):
    """Raised on transport failure after retries."""


def payload_hash(payload: Any) -> str:
    """Deterministic content hash of a raw payload (16 hex chars)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class ProspectiveApiClient:
    """Read-only TheStatsAPI client for prospective capture.

    Uses the LIVE base URL (``/api``) and Bearer-header auth per the verified
    docs. Injectable ``transport`` makes it fully testable without network.
    """

    config: ProspectiveClientConfig = field(default_factory=ProspectiveClientConfig)
    #: Optional injected transport for tests: (url, headers, params) -> (status, json).
    transport: Optional[Callable[[str, dict, dict], tuple[int, Any]]] = None
    _last_request: float = 0.0

    @property
    def is_configured(self) -> bool:
        return self.config.is_configured

    def _auth_header(self) -> dict[str, str]:
        import os

        key = os.environ.get(ENV_API_KEY, "")
        if not key:
            raise ProspectiveConfigError(
                f"{ENV_API_KEY} is not set; refusing to send a request with an "
                "empty credential. Prospective capture fails closed."
            )
        # Header value is constructed locally and never logged.
        return {"Authorization": f"Bearer {key}"}

    def _throttle(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self.config.rate_limit_seconds:
            time.sleep(self.config.rate_limit_seconds - elapsed)
        self._last_request = time.monotonic()

    def get(self, endpoint: Endpoint, *, params: Optional[dict] = None, **path: str) -> Any:
        """GET a verified endpoint, returning parsed JSON.

        Raises:
            ProspectiveConfigError: If no API key is configured.
            ProspectiveTransportError: On persistent transport failure.
        """
        if not self.is_configured:
            raise ProspectiveConfigError(
                f"{ENV_API_KEY} is not set; cannot capture {endpoint.name}. "
                "Fails closed."
            )
        headers = self._auth_header()
        url = f"{self.config.resolve_base_url()}{endpoint_path(endpoint, **path)}"
        query = dict(params or {})

        if self.transport is not None:
            status, body = self.transport(url, headers, query)
            if status == 404:
                return None
            if status >= 400:
                raise ProspectiveTransportError(f"HTTP {status} for {endpoint.name}")
            return body

        try:  # pragma: no cover - exercised only with a live key
            import httpx
        except Exception as exc:  # pragma: no cover
            raise ProspectiveTransportError("httpx unavailable") from exc

        last: Optional[Exception] = None
        for attempt in range(1, self.config.max_retries + 1):  # pragma: no cover
            self._throttle()
            try:
                with httpx.Client(timeout=self.config.timeout_seconds) as client:
                    resp = client.get(url, headers=headers, params=query)
            except Exception as exc:
                last = exc
                time.sleep(2 ** (attempt - 1))
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                retry = resp.headers.get("Retry-After")
                time.sleep(float(retry) if retry else 2 ** attempt)
                continue
            if resp.status_code >= 500:
                last = ProspectiveTransportError(f"server {resp.status_code}")
                time.sleep(2 ** (attempt - 1))
                continue
            if resp.status_code >= 400:
                raise ProspectiveTransportError(f"HTTP {resp.status_code} for {endpoint.name}")
            return resp.json()
        raise ProspectiveTransportError(f"{endpoint.name} failed after retries") from last


# ---------------------------------------------------------------------------
# Capture records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaptureRecord:
    """One append-only prospective capture.

    Carries everything the mission requires an observation to retain plus the
    raw payload hash for audit. It composes a
    :class:`ProviderObservation` (via :meth:`to_observation`) for use with the
    existing :class:`~src.research.observation.store.ObservationStore`.

    Attributes:
        provider: Source provider id (e.g. "thestatsapi").
        provider_entity_id: The provider's own id for the fixture ("mt_...").
        canonical_entity_id: Canonical fixture id (resolved via identity layer).
        fixture_id: Convenience alias of canonical_entity_id for readers.
        concept: The observed concept (e.g. "odds:match_corners:over:9.5").
        value: The observed value; MISSING sentinel when nothing was observed,
            None when observed-but-absent.
        event_time: Kickoff time (unix) when applicable.
        observed_at: ACTUAL retrieval time (unix). Never backfilled.
        retrieved_at: Same as observed_at for a live snapshot (kept explicit).
        forecast_cutoff: The vintage cutoff this capture targets (unix), or None.
        raw_payload_hash: Content hash of the source payload.
        raw_status: Provider-native semantic status (see odds_capture).
        vintage: Target capture window label.
    """

    provider: str
    provider_entity_id: str
    canonical_entity_id: str
    concept: str
    value: Any
    observed_at: float
    retrieved_at: float
    raw_payload_hash: str
    raw_status: str = "PROSPECTIVE_SNAPSHOT"
    event_time: Optional[float] = None
    forecast_cutoff: Optional[float] = None
    vintage: Optional[str] = None

    @property
    def fixture_id(self) -> str:
        return self.canonical_entity_id

    def to_observation(self) -> ProviderObservation:
        """Compose the reusable ProviderObservation for the observation store."""
        return ProviderObservation(
            key=ObservationKey(canonical_entity_id=self.canonical_entity_id, concept=self.concept),
            source=self.provider,
            provider_entity_id=self.provider_entity_id,
            value=self.value,
            event_time=int(self.event_time) if self.event_time is not None else None,
            observed_at=int(self.observed_at),
            retrieved_at=int(self.retrieved_at),
            payload_hash=self.raw_payload_hash,
            observed_at_is_estimated=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_entity_id": self.provider_entity_id,
            "canonical_entity_id": self.canonical_entity_id,
            "concept": self.concept,
            "value": "MISSING" if self.value is MISSING else self.value,
            "event_time": self.event_time,
            "observed_at": self.observed_at,
            "retrieved_at": self.retrieved_at,
            "forecast_cutoff": self.forecast_cutoff,
            "raw_payload_hash": self.raw_payload_hash,
            "raw_status": self.raw_status,
            "vintage": self.vintage,
        }


def now_ts() -> float:
    """Actual wall-clock time (unix). Isolated for test injection."""
    return time.time()
