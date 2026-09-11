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
from dataclasses import dataclass, field
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
from src.research.prospective.odds_capture import OVER_UNDER_MARKET_KEYS, OddsSemantics, extract_prices
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


#: Coverage-matrix artifact produced by scripts/prospective_coverage_scan.py.
COVERAGE_MATRIX_PATH = Path("research/evaluation/prospective_coverage_matrix.json")


def load_active_universe(*, include_partial: bool = True, path: Path = COVERAGE_MATRIX_PATH):
    """Load the ACTIVE competition universe from the coverage-matrix artifact.

    Reconstructs :class:`ActiveCompetition`-like entries from the persisted
    matrix so the collector's universe is data-driven, not hard-coded. Falls
    back to an empty universe if the artifact is missing (fail closed — the
    operator must run the coverage scan first).
    """
    import json

    from src.research.prospective.activation import ActiveCompetition

    if not Path(path).exists():
        return []
    data = json.loads(Path(path).read_text())
    allowed = {"CAPTURE_READY"}
    if include_partial:
        allowed.add("CAPTURE_PARTIAL")
    out = []
    for r in data.get("rows", []):
        if r.get("identity_status") != "VERIFIED":
            continue
        if r.get("capture_classification") not in allowed:
            continue
        cid = r.get("thestatsapi_competition_id")
        if not cid:
            continue
        markets = tuple(
            m for m, s in sorted((r.get("market_eligibility") or {}).items())
            if s in ("READY", "PARTIAL")
        )
        if not markets:
            continue
        out.append(ActiveCompetition(
            canonical_name=r.get("canonical_name", ""),
            country=r.get("country"),
            thestatsapi_competition_id=cid,
            thestatsapi_season_id=r.get("thestatsapi_season_id"),
            capture_priority=r.get("capture_priority", 3),
            eligible_markets=markets,
        ))
    out.sort(key=lambda a: (a.capture_priority, a.canonical_name))
    return out


def universe_report(*, path: Path = COVERAGE_MATRIX_PATH) -> dict:
    """Summarise the data-driven universe from the persisted coverage matrix.

    Reads the committed coverage-matrix artifact (no network) and returns the
    step-30 universe counts so the quality report is self-describing:
    competitions_expected / mapped / verified / capture_ready, plus the full
    identity + classification funnel. Returns an explicit ``artifact_present:
    false`` block when the scan has not been run yet (never fabricates counts).
    """
    import json

    p = Path(path)
    if not p.exists():
        return {"artifact_present": False}
    data = json.loads(p.read_text())
    rows = data.get("rows", [])

    def n_ident(status: str) -> int:
        return sum(1 for r in rows if r.get("identity_status") == status)

    def n_class(klass: str) -> int:
        return sum(1 for r in rows if r.get("capture_classification") == klass)

    # "Mapped" = has any TheStatsAPI competition id OR a resolved identity;
    # here we treat every row that carries a thestatsapi_competition_id as
    # mapped, plus VERIFIED rows (which always carry one). UNKNOWN stays out.
    mapped = sum(1 for r in rows if r.get("thestatsapi_competition_id"))
    return {
        "artifact_present": True,
        "artifact_path": str(p),
        "competitions_expected": len(rows),
        "competitions_mapped": mapped,
        "competitions_verified": n_ident("VERIFIED"),
        "competitions_ambiguous": n_ident("AMBIGUOUS"),
        "competitions_unresolved": n_ident("UNRESOLVED"),
        "competitions_api_unsupported": n_ident("API_UNSUPPORTED"),
        "competitions_capture_ready": n_class("CAPTURE_READY"),
        "competitions_capture_partial": n_class("CAPTURE_PARTIAL"),
        "competitions_market_insufficient": n_class("MARKET_COVERAGE_INSUFFICIENT"),
    }


@dataclass
class CollectorResult:
    """Outcome of a collector run (for reporting / testing).

    Metrics are semantically explicit and separated: discovery is NOT the same
    as due. ``fixtures_seen`` is retained for backward compat (== fixtures we
    attempted a due capture on).
    """

    fixtures_seen: int = 0
    odds_captured: int = 0
    lineups_captured: int = 0
    unavailable: int = 0
    errors: int = 0
    # --- explicit funnel counts ---
    competitions_active: int = 0
    fixtures_discovered: int = 0
    fixtures_inside_horizon: int = 0
    fixtures_due: int = 0
    early_due: int = 0
    mid_due: int = 0
    late_due: int = 0
    final_due: int = 0
    quota_limited: bool = False
    health: str = "HEALTHY"
    per_competition: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "health": self.health,
            "competitions_active": self.competitions_active,
            "fixtures_discovered": self.fixtures_discovered,
            "fixtures_inside_horizon": self.fixtures_inside_horizon,
            "fixtures_due": self.fixtures_due,
            "due_by_vintage": {
                "EARLY": self.early_due, "MID": self.mid_due,
                "LATE": self.late_due, "FINAL": self.final_due,
            },
            "odds_captured": self.odds_captured,
            "lineups_captured": self.lineups_captured,
            "unavailable": self.unavailable,
            "quota_limited": self.quota_limited,
            "errors": self.errors,
            "fixtures_seen": self.fixtures_seen,
            "per_competition": self.per_competition,
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

    def capture_odds(
        self,
        match_id: str,
        *,
        kickoff_ts: Optional[float] = None,
        markets: Optional[set] = None,
    ) -> int:
        """Capture the current odds snapshot for one fixture. Returns #appended.

        ``markets`` optionally restricts extraction to a league's eligible
        markets so we never normalize markets a competition does not price.
        """
        payload = self.client.get(Endpoint.MATCH_ODDS, match_id=match_id)
        if payload is None:
            return 0
        observed = self.clock()
        ph = payload_hash(payload)
        market_keys = tuple(markets) if markets else OVER_UNDER_MARKET_KEYS
        prices = extract_prices(
            payload,
            payload_hash=ph,
            field="last_seen",
            semantics=OddsSemantics.PROSPECTIVE_SNAPSHOT,
            observed_at=observed,
            markets=market_keys,
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

    def discover_upcoming(self, *, hours: int = 30, competition_ids: Optional[Sequence[str]] = None):
        """Discover scheduled fixtures within ``hours``, scoped to the universe.

        Uses the live ``date_from``/``date_to`` filters (UTC) to bound the
        window and iterates the initial operational universe's competition ids
        so we find NEAR-TERM fixtures in supported leagues rather than the API's
        unscoped first page. Falls back to an unscoped ``status=scheduled``
        query only when no competition ids are available.
        """
        import datetime as _dt

        from src.research.prospective.scheduler import UpcomingFixture
        from src.research.prospective.universe import universe_competition_ids

        now = self.clock()
        horizon = now + hours * 3600
        date_from = _dt.datetime.fromtimestamp(now, _dt.timezone.utc).date().isoformat()
        date_to = _dt.datetime.fromtimestamp(horizon, _dt.timezone.utc).date().isoformat()

        comps = list(competition_ids) if competition_ids is not None else list(universe_competition_ids())
        queries: list[dict] = []
        if comps:
            for cid in comps:
                queries.append({"status": "scheduled", "competition_id": cid,
                                "date_from": date_from, "date_to": date_to, "per_page": 100})
        else:
            queries.append({"status": "scheduled", "date_from": date_from,
                            "date_to": date_to, "per_page": 100})

        out: list = []
        seen: set = set()
        for params in queries:
            payload = self.client.get(Endpoint.MATCHES, params=params)
            matches = payload.get("data", []) if isinstance(payload, dict) else []
            for m in matches:
                mid = m.get("id")
                ko = m.get("utc_date")
                if not mid or ko is None or mid in seen:
                    continue
                ts = _parse_utc(ko)
                if ts is None:
                    continue
                # Bound to the requested horizon (defensive; API date filter is
                # day-granular so a fixture on date_to could exceed `hours`).
                if not (now <= ts <= horizon):
                    continue
                seen.add(mid)
                out.append(UpcomingFixture(fixture_id=str(mid), kickoff_ts=ts,
                                           league=m.get("competition_id")))
        return out

    def capture_due(
        self,
        *,
        hours: int = 30,
        max_requests: int = 400,
        active_competitions: Optional[Sequence] = None,
        include_partial: bool = True,
    ) -> CollectorResult:
        """Discover upcoming fixtures across the ACTIVE universe and capture due work.

        Restart-safe: due work is computed from the persisted store + now, so a
        rerun after a crash resumes correctly and never rewrites observations.
        Metrics separate discovered / inside-horizon / due. A reserve-aware
        quota guard stops issuing work when the monthly reserve is threatened.
        Only markets a competition is eligible for are captured.
        """
        from src.research.prospective.scheduler import (
            CaptureKind,
            CaptureScheduler,
            UpcomingFixture,
        )
        from src.research.prospective.quota import QuotaGuard

        result = CollectorResult()
        active = (
            list(active_competitions)
            if active_competitions is not None
            else load_active_universe(include_partial=include_partial)
        )
        result.competitions_active = len(active)
        if not active:
            result.health = "NO_UPCOMING_FIXTURES"
            return result

        sched = CaptureScheduler(self.store)
        now = self.clock()
        guard = QuotaGuard(
            monthly_limit=(getattr(self.client, "last_rate_limit", None).monthly_limit
                           if getattr(self.client, "last_rate_limit", None) else None)
        )
        requests = 0
        due_all: list = []

        for comp in active:
            cid = comp.thestatsapi_competition_id if hasattr(comp, "thestatsapi_competition_id") else comp["thestatsapi_competition_id"]
            eligible = set(comp.eligible_markets if hasattr(comp, "eligible_markets") else comp.get("eligible_markets", []))
            fixtures = self.discover_upcoming(hours=hours, competition_ids=[cid])
            # Discovery already bounds to [now, horizon]; count them.
            result.fixtures_discovered += len(fixtures)
            result.fixtures_inside_horizon += len(fixtures)
            comp_due = sched.due_captures(fixtures, now=now)
            due_all.extend((comp, d) for d in comp_due)
            if fixtures or comp_due:
                cname = comp.canonical_name if hasattr(comp, "canonical_name") else comp.get("canonical_name")
                result.per_competition[cname] = {
                    "discovered": len(fixtures), "due": len(comp_due),
                }

        result.fixtures_due = len(due_all)
        for _, d in due_all:
            v = d.vintage.value
            if v == "EARLY":
                result.early_due += 1
            elif v == "MID":
                result.mid_due += 1
            elif v == "LATE":
                result.late_due += 1
            elif v == "FINAL":
                result.final_due += 1

        for comp, d in due_all:
            if requests >= max_requests:
                break
            rl = getattr(self.client, "last_rate_limit", None)
            if rl is not None and not guard.may_request(rl):
                result.quota_limited = True
                break
            eligible = set(comp.eligible_markets if hasattr(comp, "eligible_markets")
                           else comp.get("eligible_markets", []))
            result.fixtures_seen += 1
            try:
                if d.kind == CaptureKind.ODDS:
                    result.odds_captured += self.capture_odds(
                        d.fixture_id, kickoff_ts=d.kickoff_ts, markets=eligible or None)
                elif d.kind == CaptureKind.LINEUP:
                    lc = self.capture_lineup(d.fixture_id, kickoff_ts=d.kickoff_ts)
                    result.lineups_captured += lc
                    if lc == 0:
                        result.unavailable += 1
                requests += 1
            except Exception:  # noqa: BLE001
                result.errors += 1

        # Health: fixtures discovered but nothing due yet is a normal waiting
        # state, not an error / empty universe.
        if result.fixtures_discovered > 0 and result.fixtures_due == 0:
            result.health = "HEALTHY_WAITING_FOR_VINTAGE"
        elif result.fixtures_discovered == 0:
            result.health = "HEALTHY_WAITING_FOR_VINTAGE"  # active universe, off-matchday
        elif result.quota_limited:
            result.health = "QUOTA_LIMITED"
        else:
            result.health = "HEALTHY"
        return result


def _run_shadow_after_capture(*, capture_root: Path, broadcast_root: Optional[Path] = None) -> None:
    """Run the prospective shadow-residual processor over just-persisted state.

    Called at the END of a successful ``capture-due`` tick, inside the same
    single-instance flock the capture run already holds. It performs NO provider
    request (reads only the append-only capture store + the committed broadcast
    ledger) and runs NO model.

    Failure isolation (mission BLOCKER 2): a shadow-processing failure must
    never corrupt capture data or fail the parent capture run. All exceptions
    are caught here; the outcome is written to a SEPARATE shadow ops log
    (``shadow_ops.jsonl``) so a shadow failure is observable without affecting
    the capture ops record or the process exit code.
    """
    from src.research.prospective import shadow_process
    from src.research.prospective.ops_log import append_run, hostname, OpsRunRecord

    shadow_ops_path = Path(capture_root) / "shadow_ops.jsonl"
    started = now_ts()
    try:
        kwargs = {"shadow_root": Path(capture_root)}
        if broadcast_root is not None:
            kwargs["broadcast_root"] = Path(broadcast_root)
        res = shadow_process.run(**kwargs)
        finished = now_ts()
        note = (
            f"shadow: kind={res.provenance_kind} "
            f"new_candidates={res.candidates_new} "
            f"pre_frontier_excluded={res.candidates_pre_frontier_excluded} "
            f"new_evaluations={res.evaluations_new} "
            f"frontier={res.frontier_established_at}"
        )
        append_run(
            OpsRunRecord(
                run_started_at=started,
                run_finished_at=finished,
                duration_seconds=round(finished - started, 3),
                exit_status="OK",
                health_state="SHADOW_OK",
                odds_captured=0,
                errors=0,
                hostname=hostname(),
                note=note,
            ),
            path=shadow_ops_path,
        )
    except Exception as exc:  # noqa: BLE001 - shadow failure must never crash capture
        finished = now_ts()
        append_run(
            OpsRunRecord(
                run_started_at=started,
                run_finished_at=finished,
                duration_seconds=round(finished - started, 3),
                exit_status="ERROR",
                health_state="SHADOW_FAILED",
                errors=1,
                hostname=hostname(),
                note=f"shadow processing failed (isolated; capture unaffected): {type(exc).__name__}",
            ),
            path=shadow_ops_path,
        )


def _publish_shadow_feed_after_capture(*, capture_root: Path) -> None:
    """Publish just-persisted PROSPECTIVE_SHADOW records to the research feed.

    Additive UX step (mission: Telegram shadow research feed). Runs AFTER the
    shadow processor has appended any new records, inside the same capture tick /
    flock. It is strictly consume-only: it reads the append-only shadow ledgers
    and delivers research-only Telegram cards for records not already delivered.
    It performs NO provider request, runs NO model, recomputes NO residual, and
    can only emit the non-reserved SHADOW_RESEARCH / SHADOW_RESEARCH_UPDATE types.

    Publication boundary (fail closed): a LIVE send happens ONLY when the
    operator has explicitly enabled ``RESEARCH_SHADOW_FEED_PUBLISH`` AND a
    dedicated research Telegram channel (``RESEARCH_TELEGRAM_BOT_TOKEN`` +
    ``RESEARCH_TELEGRAM_CHAT_ID``) is configured. There is NO fallback to the
    consumer SIGNALS_* / HEARTBEAT_* channel. With either guard unmet, the
    just-frozen records are simply left unseen for a later tick — the default
    deployment publishes nothing.

    Failure isolation (same discipline as ``_run_shadow_after_capture``): any
    error is caught and recorded to the SEPARATE shadow ops log; a Telegram or
    formatting problem must never corrupt capture data or fail the capture run.
    Delivery itself is already failure-isolated per message by ``deliver``.
    """
    from src.research.prospective import shadow_feed
    from src.research.prospective.ops_log import append_run, hostname, OpsRunRecord

    # Separate ops log from the shadow PROCESSOR's shadow_ops.jsonl, so this
    # additive UX step never displaces the processor's own ops record.
    shadow_ops_path = Path(capture_root) / "shadow_feed_ops.jsonl"
    started = now_ts()
    try:
        res = shadow_feed.publish_shadow_feed(shadow_root=Path(capture_root))
        finished = now_ts()
        note = (
            "shadow_feed: "
            f"shadows_seen={res.shadows_seen} published={res.shadows_published} "
            f"queued={res.shadows_queued} "
            f"evals_seen={res.evaluations_seen} evals_published={res.evaluations_published} "
            f"messages_sent={res.messages_sent}"
        )
        append_run(
            OpsRunRecord(
                run_started_at=started,
                run_finished_at=finished,
                duration_seconds=round(finished - started, 3),
                exit_status="OK",
                health_state="SHADOW_FEED_OK",
                odds_captured=0,
                errors=0,
                hostname=hostname(),
                note=note,
            ),
            path=shadow_ops_path,
        )
    except Exception as exc:  # noqa: BLE001 - feed failure must never crash capture
        finished = now_ts()
        append_run(
            OpsRunRecord(
                run_started_at=started,
                run_finished_at=finished,
                duration_seconds=round(finished - started, 3),
                exit_status="ERROR",
                health_state="SHADOW_FEED_FAILED",
                errors=1,
                hostname=hostname(),
                note=(
                    "shadow feed publish failed (isolated; capture unaffected): "
                    f"{type(exc).__name__}"
                ),
            ),
            path=shadow_ops_path,
        )


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

    p_sh = sub.add_parser(
        "scheduler-health",
        help="Report operational scheduler health from the ops run log (no network)",
    )
    p_sh.add_argument(
        "--stale-after",
        type=int,
        default=None,
        help="Seconds since last run before the scheduler is STALE (default ~3 ticks).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    store_path = Path(args.capture_root) / "captures.jsonl.gz"

    # quality-report reads persisted state only; it needs no API key.
    if args.command == "quality-report":
        import json as _json

        from src.research.prospective.coverage_funnel import analysis_support
        from src.research.prospective.quality import build_quality_report

        store = CaptureStore(path=store_path)
        report = build_quality_report(store, now=now_ts())
        out = report.to_dict()
        # Step-30: make the report self-describing about the data-driven
        # universe and the coverage-bias funnel (UNKNOWN never coerced).
        out["universe"] = universe_report()
        out["analysis_support"] = analysis_support(store).to_dict()
        print(_json.dumps(out, indent=2))
        return 0

    # scheduler-health reads the operational run log only; no API key / network.
    # A green API with a dead timer must not read as HEALTHY, so this is a
    # deliberately independent signal from quality-report.
    if args.command == "scheduler-health":
        import json as _json

        from src.research.prospective.ops_log import DEFAULT_OPS_LOG
        from src.research.prospective.scheduler_health import (
            DEFAULT_STALE_AFTER_SECONDS,
            assess_health,
        )

        stale_after = args.stale_after if args.stale_after else DEFAULT_STALE_AFTER_SECONDS
        health = assess_health(
            now=now_ts(),
            path=Path(args.capture_root) / DEFAULT_OPS_LOG.name,
            stale_after_seconds=stale_after,
        )
        print(_json.dumps(health.to_dict(), indent=2))
        # Non-zero exit when the scheduler is not healthy, so a systemd/cron
        # watchdog or a manual check surfaces the failure via exit code too.
        return 0 if health.health == "HEALTHY" else 1

    client = ProspectiveApiClient()
    if not client.is_configured:
        # Fail closed: never attempt a request without a key.
        from src.research.prospective.api_contract import ENV_API_KEY_ALIASES

        # Record an operational run so scheduler-health can distinguish a dead
        # timer (STALE) from a running-but-misconfigured one (AUTH_FAILED).
        if args.command in ("capture-due", "capture-upcoming"):
            from src.research.prospective.ops_log import OpsRunRecord, append_run, hostname

            _t = now_ts()
            append_run(
                OpsRunRecord(
                    run_started_at=_t,
                    run_finished_at=_t,
                    duration_seconds=0.0,
                    exit_status="AUTH_FAILED",
                    health_state="AUTH_FAILED",
                    hostname=hostname(),
                    note="no API key configured; fail closed",
                ),
                path=Path(args.capture_root) / "ops_runs.jsonl",
            )
        print(
            f"No API key set (checked {', '.join(ENV_API_KEY_ALIASES)}); "
            "prospective capture fails closed. No request attempted.",
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
            from src.research.prospective.ops_log import OpsRunRecord, append_run, hostname

            started = now_ts()
            result = collector.capture_due(hours=args.hours, max_requests=args.max_requests)
            finished = now_ts()
            print(result.to_dict())

            # Derive an operational exit status from the run outcome. This is
            # the run's OWN self-report; scheduler-health additionally checks
            # freshness so a dead timer can never read HEALTHY.
            if result.quota_limited:
                exit_status = "QUOTA_LIMITED"
            elif result.errors > 0:
                exit_status = "PARTIAL_FAILURE"
            else:
                exit_status = "OK"

            rl = getattr(client, "last_rate_limit", None)
            quota_remaining = rl.monthly_remaining if rl is not None else None

            append_run(
                OpsRunRecord(
                    run_started_at=started,
                    run_finished_at=finished,
                    duration_seconds=round(finished - started, 3),
                    exit_status=exit_status,
                    health_state=result.health,
                    fixtures_discovered=result.fixtures_discovered,
                    fixtures_inside_horizon=result.fixtures_inside_horizon,
                    fixtures_due=result.fixtures_due,
                    odds_captured=result.odds_captured,
                    lineups_captured=result.lineups_captured,
                    availability_captured=0,
                    referees_captured=0,
                    errors=result.errors,
                    quota_remaining=quota_remaining,
                    quota_limited=result.quota_limited,
                    competitions_active=result.competitions_active,
                    hostname=hostname(),
                ),
                path=Path(args.capture_root) / "ops_runs.jsonl",
            )

            # --- Prospective shadow-residual processing (BLOCKER 2 wiring) ---
            # The capture above has ALREADY safely persisted its observations and
            # logged its ops record. Only now do we run the shadow processor,
            # in-process, over that just-persisted state. This makes shadow
            # instrumentation operational on the normal scheduled path with:
            #   * ZERO incremental provider requests (reads persisted state only),
            #   * no new timer / no scheduler-cadence change (same 15-min tick),
            #   * the SAME flock the capture run already holds (no new/overlapping
            #     writer; single-instance discipline preserved),
            #   * idempotency preserved (append-only, dedup on shadow_id),
            #   * the live PROSPECTIVE FRONTIER gating provenance so only
            #     post-frontier candidates become PROSPECTIVE_SHADOW.
            # Shadow failure is ISOLATED: it is recorded as a separate ops record
            # and NEVER corrupts capture data or fails the parent capture run
            # (the research capture already succeeded and is what matters).
            _run_shadow_after_capture(capture_root=Path(args.capture_root))

            # --- Prospective shadow research Telegram feed (additive UX) ---
            # Consume-only publication of the records the processor just froze:
            # research-only PROSPECTIVE_SHADOW cards + later movement updates,
            # deduped via the existing restart-safe notify ledger. No provider /
            # model call; distinct from validated-signal publication; isolated so
            # a Telegram failure never affects the capture run.
            _publish_shadow_feed_after_capture(capture_root=Path(args.capture_root))

    except ProspectiveConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
