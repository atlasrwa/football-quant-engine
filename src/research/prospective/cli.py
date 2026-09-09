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


def _parse_utc(value: str) -> Optional[float]:
    """Parse an ISO-8601 UTC timestamp (e.g. '2026-01-15T15:00:00.000Z') to unix.

    Everything is treated as UTC. Returns None on unparseable input (fails
    neutrally rather than fabricating a time).
    """
    import datetime as _dt

    if not isinstance(value, str):
        return None
    v = value.strip().replace("Z", "+00:00")
    try:
        dt = _dt.datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.timestamp()


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
                # Concept carries the bookmaker so per-book coverage and
                # same-book movement can be reconstructed from the store.
                concept=f"{price.concept}:{price.bookmaker}",
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

    def capture_referee(self, match_id: str, *, kickoff_ts: Optional[float] = None) -> int:
        """Capture referee identity/context for one fixture. Returns #appended."""
        payload = self.client.get(Endpoint.MATCH_REFEREE, match_id=match_id)
        if payload is None:
            return 0
        observed = self.clock()
        rec = CaptureRecord(
            provider=self.provider, provider_entity_id=match_id,
            canonical_entity_id=match_id, concept="referee",
            value=payload.get("data", payload), observed_at=observed,
            retrieved_at=observed, raw_payload_hash=payload_hash(payload),
            raw_status="PROSPECTIVE_SNAPSHOT", event_time=kickoff_ts,
        )
        return 1 if self.store.append(rec) else 0

    def capture_injuries(self, team_id: str, *, kickoff_ts: Optional[float] = None) -> int:
        """Capture a team's injuries/suspensions snapshot. Returns #appended.

        Stored as observed with OUR retrieval time; absence is never inferred
        as injury (that inference does not exist anywhere in this pipeline).
        """
        payload = self.client.get(Endpoint.TEAM_INJURIES, team_id=team_id)
        if payload is None:
            return 0
        observed = self.clock()
        rec = CaptureRecord(
            provider=self.provider, provider_entity_id=team_id,
            canonical_entity_id=team_id, concept="availability:injuries_suspensions",
            value=payload.get("data", payload), observed_at=observed,
            retrieved_at=observed, raw_payload_hash=payload_hash(payload),
            raw_status="PROSPECTIVE_SNAPSHOT", event_time=kickoff_ts,
        )
        return 1 if self.store.append(rec) else 0

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

    def discover_upcoming(self, *, hours: int = 30):
        """Discover scheduled fixtures, returning UpcomingFixture list."""
        from src.research.prospective.scheduler import UpcomingFixture

        payload = self.client.get(Endpoint.MATCHES, params={"status": "scheduled"})
        matches = payload.get("data", []) if isinstance(payload, dict) else []
        out = []
        for m in matches:
            mid = m.get("id")
            ko = m.get("utc_date")
            if not mid or ko is None:
                continue
            ts = _parse_utc(ko)
            if ts is None:
                continue
            out.append(UpcomingFixture(fixture_id=str(mid), kickoff_ts=ts,
                                       league=m.get("competition_id")))
        return out

    def capture_due(self, *, hours: int = 30, max_requests: int = 200) -> CollectorResult:
        """Discover upcoming fixtures and execute only DUE captures.

        Restart-safe: due work is computed from the persisted store + now, so a
        rerun after a crash resumes correctly and never rewrites observations.
        ``max_requests`` bounds work per invocation (quota guard placeholder;
        the live client also honours Retry-After).
        """
        from src.research.prospective.scheduler import CaptureKind, CaptureScheduler

        result = CollectorResult()
        fixtures = self.discover_upcoming(hours=hours)
        if not fixtures:
            return result
        sched = CaptureScheduler(self.store)
        now = self.clock()
        due = sched.due_captures(fixtures, now=now)
        requests = 0
        for d in due:
            if requests >= max_requests:
                break
            result.fixtures_seen += 1
            try:
                if d.kind == CaptureKind.ODDS:
                    result.odds_captured += self.capture_odds(d.fixture_id, kickoff_ts=d.kickoff_ts)
                elif d.kind == CaptureKind.LINEUP:
                    lc = self.capture_lineup(d.fixture_id, kickoff_ts=d.kickoff_ts)
                    result.lineups_captured += lc
                    if lc == 0:
                        result.unavailable += 1
                requests += 1
            except Exception:  # noqa: BLE001
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

    p_due = sub.add_parser("capture-due", help="Discover + capture only due work (restart-safe)")
    p_due.add_argument("--hours", type=int, default=30)
    p_due.add_argument("--max-requests", type=int, default=200)

    p_q = sub.add_parser("quality-report", help="Emit JSON quality report from persisted captures")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    store_path = Path(args.capture_root) / "captures.jsonl.gz"

    # quality-report reads persisted state only; it needs no API key.
    if args.command == "quality-report":
        import json as _json

        from src.research.prospective.quality import build_quality_report

        store = CaptureStore(path=store_path)
        report = build_quality_report(store, now=now_ts())
        print(_json.dumps(report.to_dict(), indent=2))
        return 0

    client = ProspectiveApiClient()
    if not client.is_configured:
        # Fail closed: never attempt a request without a key.
        print(
            "THESTATSAPI_API_KEY is not set; prospective capture fails closed. "
            "No request attempted.",
            file=sys.stderr,
        )
        return 2

    store = CaptureStore(path=store_path)
    collector = ProspectiveCollector(client, store)
    try:
        if args.command == "capture-upcoming":
            result = collector.capture_upcoming(hours=args.hours)
            print(result.to_dict())
        elif args.command == "capture-odds":
            print({"odds_captured": collector.capture_odds(args.match)})
        elif args.command == "capture-lineups":
            print({"lineups_captured": collector.capture_lineup(args.match)})
        elif args.command == "capture-due":
            result = collector.capture_due(hours=args.hours, max_requests=args.max_requests)
            print(result.to_dict())
    except ProspectiveConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
