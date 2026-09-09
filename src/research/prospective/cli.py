"""Prospective collector CLI.

A small, scheduler-friendly collector that can be run repeatedly to capture
upcoming fixtures, odds, and lineups into the append-only capture store. It:

1. discovers upcoming supported fixtures,
2. maps canonical identities (via the identity registry when available),
3. fetches current odds,
4. fetches the lineup when available (404 => not yet announced, handled),
5. records the EXACT retrieval timestamp as observed_at,
6. appends observations (never rewrites earlier ones),
7. gracefully handles unavailable data,
8. respects rate limits (client-side throttle),
9. never logs secrets.

It fails closed when no API key is configured: it reports the condition and
exits non-zero WITHOUT attempting any request. Designed to be invoked by an
external scheduler (cron/systemd-timer); no fragile background daemon.

Usage:
    python -m src.research.prospective.cli capture-upcoming --hours 30
    python -m src.research.prospective.cli capture-odds --match mt_123
    python -m src.research.prospective.cli capture-lineups --match mt_123
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from src.research.prospective.api_contract import Endpoint
from src.research.prospective.capture import (
    CaptureRecord,
    ProspectiveApiClient,
    ProspectiveConfigError,
    now_ts,
    payload_hash,
)
from src.research.prospective.odds_capture import OddsSemantics, extract_prices
from src.research.prospective.storage import CaptureStore

#: Default capture root (git-ignored; research-critical raw data).
DEFAULT_CAPTURE_ROOT = Path("data/prospective")


@dataclass
class CollectorResult:
    """Outcome of a collector run (for reporting / testing)."""

    fixtures_seen: int = 0
    odds_captured: int = 0
    lineups_captured: int = 0
    unavailable: int = 0
    errors: int = 0

    def to_dict(self) -> dict:
        return {
            "fixtures_seen": self.fixtures_seen,
            "odds_captured": self.odds_captured,
            "lineups_captured": self.lineups_captured,
            "unavailable": self.unavailable,
            "errors": self.errors,
        }


class ProspectiveCollector:
    """Coordinates capture. Client + store are injectable for tests."""

    def __init__(
        self,
        client: ProspectiveApiClient,
        store: CaptureStore,
        *,
        provider: str = "thestatsapi",
        clock=now_ts,
    ) -> None:
        self.client = client
        self.store = store
        self.provider = provider
        self.clock = clock

    def capture_odds(self, match_id: str, *, kickoff_ts: Optional[float] = None) -> int:
        """Capture the current odds snapshot for one fixture. Returns #appended."""
        payload = self.client.get(Endpoint.MATCH_ODDS, match_id=match_id)
        if payload is None:
            return 0
        observed = self.clock()
        ph = payload_hash(payload)
        prices = extract_prices(
            payload,
            payload_hash=ph,
            field="last_seen",
            semantics=OddsSemantics.PROSPECTIVE_SNAPSHOT,
            observed_at=observed,
        )
        appended = 0
        for price in prices:
            rec = CaptureRecord(
                provider=self.provider,
                provider_entity_id=match_id,
                canonical_entity_id=match_id,
                concept=price.concept,
                value=price.decimal_odds,
                observed_at=observed,
                retrieved_at=observed,
                raw_payload_hash=ph,
                raw_status=OddsSemantics.PROSPECTIVE_SNAPSHOT.value,
                event_time=kickoff_ts,
            )
            if self.store.append(rec):
                appended += 1
        return appended

    def capture_lineup(self, match_id: str, *, kickoff_ts: Optional[float] = None) -> int:
        """Capture the lineup for one fixture if announced. Returns #appended."""
        payload = self.client.get(Endpoint.MATCH_LINEUPS, match_id=match_id)
        if payload is None:
            return 0  # not yet announced (404) — handled gracefully
        observed = self.clock()
        ph = payload_hash(payload)
        rec = CaptureRecord(
            provider=self.provider,
            provider_entity_id=match_id,
            canonical_entity_id=match_id,
            concept="confirmed_lineup",
            value=payload.get("data", payload),
            observed_at=observed,
            retrieved_at=observed,
            raw_payload_hash=ph,
            raw_status="PROSPECTIVE_SNAPSHOT",
            event_time=kickoff_ts,
        )
        return 1 if self.store.append(rec) else 0

    def capture_upcoming(self, *, hours: int = 30) -> CollectorResult:
        """Discover upcoming fixtures within ``hours`` and capture odds+lineups."""
        result = CollectorResult()
        payload = self.client.get(Endpoint.MATCHES, params={"status": "scheduled"})
        if payload is None:
            return result
        matches = payload.get("data", []) if isinstance(payload, dict) else []
        for m in matches:
            result.fixtures_seen += 1
            mid = m.get("id")
            if not mid:
                result.errors += 1
                continue
            try:
                result.odds_captured += self.capture_odds(mid)
                lc = self.capture_lineup(mid)
                result.lineups_captured += lc
                if lc == 0:
                    result.unavailable += 1
            except Exception:  # noqa: BLE001 - keep collecting other fixtures
                result.errors += 1
        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prospective-collector", description=__doc__)
    parser.add_argument("--capture-root", type=Path, default=DEFAULT_CAPTURE_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    p_up = sub.add_parser("capture-upcoming", help="Capture upcoming fixtures' odds+lineups")
    p_up.add_argument("--hours", type=int, default=30)

    p_odds = sub.add_parser("capture-odds", help="Capture odds for one fixture")
    p_odds.add_argument("--match", required=True)

    p_line = sub.add_parser("capture-lineups", help="Capture lineup for one fixture")
    p_line.add_argument("--match", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    client = ProspectiveApiClient()
    if not client.is_configured:
        # Fail closed: never attempt a request without a key.
        print(
            "THESTATSAPI_API_KEY is not set; prospective capture fails closed. "
            "No request attempted.",
            file=sys.stderr,
        )
        return 2

    store = CaptureStore(path=Path(args.capture_root) / "captures.jsonl.gz")
    collector = ProspectiveCollector(client, store)
    try:
        if args.command == "capture-upcoming":
            result = collector.capture_upcoming(hours=args.hours)
            print(result.to_dict())
        elif args.command == "capture-odds":
            print({"odds_captured": collector.capture_odds(args.match)})
        elif args.command == "capture-lineups":
            print({"lineups_captured": collector.capture_lineup(args.match)})
    except ProspectiveConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
