#!/usr/bin/env python3
"""Discover upcoming fixtures across the FULL dual-provider league universe.

WHY THIS EXISTS
===============
``scripts/pilotC_fixture_discovery.py`` refreshes upcoming fixtures for Pilot C's
four pre-registered competitions only. The shared universe file it writes still
*contains* rows from an older broad fetch, so it looks wide — but every row with a
future kickoff belongs to one of those four leagues. Any downstream stage that
"reads the fixture universe" was therefore still Pilot-C scoped in practice, even
after the declared-scope gate was removed. That is the last behavioral Pilot-C
dependency on the forecast side.

This run discovers upcoming fixtures for every competition in the safe FootyStats x
TheStatsAPI intersection and writes them to a SEPARATE universe file. Pilot C's own
file is never written here: its sample is pre-registered and must stay exactly as
its pre-registration defines it. Widening a frozen experiment's sample would
invalidate the experiment; adding a second, wider universe alongside it does not.

WHAT IS AND IS NOT A GATE
=========================
* Competition eligibility IS a gate — the dual-provider intersection decides which
  competitions are queried at all.
* Corpus team history is NOT a gate here. Pilot-C discovery excludes fixtures whose
  teams lack corpus history, because an unsettleable fixture would pollute a
  pre-registered sample. For research the opposite is true: a competition existing
  in both providers should keep accumulating provider observations even before it
  has a fittable model, and the forecast stage already fails closed per fixture when
  history is missing. So such fixtures are DISCOVERED and COUNTED, and the model
  stage abstains on them later with a stated reason.

BUDGET
======
Cache-first and bucketed by UTC day, so same-day re-runs are free. A hard per-run
live-request cap bounds the spend, and competitions are ordered by capture priority
then nearest kickoff so the cap truncates the least useful work first rather than
whatever happened to be last. Known-unsupported competitions are never queried.

USAGE
=====
    python3 scripts/research_fixture_discovery.py
    python3 scripts/research_fixture_discovery.py --dry-run
    python3 scripts/research_fixture_discovery.py --request-cap 120
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

_ENV_PATH = "/home/ubuntu/.env"
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH) as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

import thestatsapi_client as api  # noqa: E402

from src.research.scope.market_scope import build_research_scope  # noqa: E402

#: The research fixture universe. Deliberately NOT Pilot C's file.
FIXTURE_LIST = Path("/home/ubuntu/data/research/research_fixture_universe.json")
STATUS_FILE = Path("/home/ubuntu/data/research/research_discovery_status.json")
DISCOVERY_LOG = Path("/home/ubuntu/data/research/research_discovery_log.jsonl")

#: Look-ahead window (days).
WINDOW_DAYS = int(os.environ.get("RESEARCH_DISCOVERY_WINDOW_DAYS", "7"))

#: Hard per-run live-request cap. 46 competitions x ~1-2 pages typical. The budget
#: exists to be used for coverage, but a runaway pagination loop must still be bounded.
REQUEST_CAP = int(os.environ.get("RESEARCH_DISCOVERY_REQUEST_CAP", "150"))

PER_PAGE = 100
_SCHEDULED_STATES = {"scheduled", "upcoming", "not_started", "timed", "fixture"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_to_unix(utc_date: str) -> Optional[float]:
    if not utc_date:
        return None
    try:
        return datetime.fromisoformat(utc_date.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return None


def _load_universe() -> dict[str, Any]:
    if FIXTURE_LIST.exists():
        try:
            return json.load(open(FIXTURE_LIST))
        except Exception:  # noqa: BLE001
            pass
    return {"generated": _now_iso(), "match_ids": [], "meta": {}}


def _write_status(state: str, payload: dict[str, Any]) -> None:
    """Record exactly one of found/empty/failed, so they stay distinguishable.

    An empty result and a failed run look identical in a fixture count; recorded
    separately here so a silent discovery outage can never read as a quiet week.
    """
    record = {"state": state, "generated": _now_iso(), **payload}
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(record, open(STATUS_FILE, "w"), indent=2, default=str)
    DISCOVERY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DISCOVERY_LOG, "a") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def _fetch_scheduled(comp_id: str, day_bucket: str) -> tuple[list[dict], int, bool]:
    """Fetch all scheduled-fixture pages for one competition.

    Cache key is bucketed by UTC day so same-day re-runs cost nothing but a new day
    refreshes. Returns ``(fixtures, live_requests_used, ok)``.

    A 404/422 is a legitimate "this competition has no scheduled-fixture feed"
    answer and counts as ``ok`` — it is recorded as an explicit zero rather than a
    failure, and the cached probe stops us re-spending on it every run.
    """
    before = api.live_requests_made()
    fixtures: list[dict] = []
    params = {
        "competition_id": comp_id,
        "status": "scheduled",
        "per_page": PER_PAGE,
        "page": 1,
    }
    data, meta = api.get_json(
        "/football/matches",
        params=params,
        cache_key=f"research_discovery_{comp_id}_scheduled_{day_bucket}_p1",
        allow_status=(200, 404, 422),
    )
    if not data or meta.get("http_status") != 200:
        return [], api.live_requests_made() - before, meta.get("http_status") in (200, 404, 422)

    fixtures.extend(data.get("data", []))
    total_pages = int(data.get("meta", {}).get("total_pages", 1) or 1)
    for page in range(2, total_pages + 1):
        pg, pmeta = api.get_json(
            "/football/matches",
            params={**params, "page": page},
            cache_key=f"research_discovery_{comp_id}_scheduled_{day_bucket}_p{page}",
            allow_status=(200, 404, 422),
        )
        if pg and pmeta.get("http_status") == 200:
            fixtures.extend(pg.get("data", []))
    return fixtures, api.live_requests_made() - before, True


def _corpus_teams() -> tuple[set[str], Optional[str]]:
    """Team names with corpus history — for REPORTING model readiness, not gating."""
    try:
        import pilotC_stat_mixer as mix

        return set(mix.build_histories(mix.load_corpus())), None
    except Exception as exc:  # noqa: BLE001
        return set(), f"{type(exc).__name__}: {str(exc)[:120]}"


def discover(
    *,
    dry_run: bool = False,
    request_cap: int = REQUEST_CAP,
    window_days: int = WINDOW_DAYS,
    competition_ids: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Discover upcoming fixtures across the dual-provider universe.

    Returns a stats dict. Always writes the status file (found/empty/failed) unless
    ``dry_run``, in which case it reports without writing the universe.
    """
    run_start = time.time()
    now = time.time()
    horizon = now + window_days * 86400
    day_bucket = datetime.now(timezone.utc).strftime("%Y%m%d")

    api.MAX_LIVE_REQUESTS = min(api.MAX_LIVE_REQUESTS, request_cap)

    scope = build_research_scope()
    teams, corpus_error = _corpus_teams()

    # Order by capture priority then name: if the request cap binds, it truncates
    # the least-prioritised competitions rather than an arbitrary tail.
    competitions = sorted(
        (c for c in scope.competitions if c.has_processable_market),
        key=lambda c: (c.capture_priority if c.capture_priority is not None else 9, c.canonical_name),
    )
    if competition_ids is not None:
        wanted = set(competition_ids)
        competitions = [c for c in competitions if c.competition_id in wanted]

    universe = _load_universe()
    meta: dict[str, Any] = universe.get("meta") or {}
    match_ids: list[str] = list(universe.get("match_ids") or [])
    existing = set(match_ids)

    stats: dict[str, Any] = {
        "generated": _now_iso(),
        "window_days": window_days,
        "request_cap": request_cap,
        "scope_rule": "dual_provider_intersection",
        "registry_leagues_total": len(scope.universe.leagues),
        "dual_provider_eligible": len(scope.universe.eligible),
        "leagues_excluded": len(scope.universe.excluded),
        "league_exclusion_reasons": scope.universe.exclusion_summary(),
        "competitions_queried": 0,
        "competitions_with_upcoming": 0,
        "competitions_failed": 0,
        "upcoming_in_window": 0,
        "with_corpus_history": 0,
        "without_corpus_history": 0,
        "added": 0,
        "refreshed": 0,
        "live_requests": 0,
        "cap_reached": False,
        "corpus_load_error": corpus_error,
        "per_league": {},
    }

    for comp in competitions:
        if stats["live_requests"] >= request_cap:
            stats["cap_reached"] = True
            break
        comp_id = comp.competition_id
        try:
            fixtures, used, ok = _fetch_scheduled(comp_id, day_bucket)
        except SystemExit as exc:
            # The client aborts on budget exhaustion or broken auth. Distinguish
            # them: a clean budget stop is a choice, an auth failure is a fault.
            code, clean, reason = api.describe_abort(exc)
            stats["cap_reached"] = bool(clean)
            stats["per_league"][comp_id] = {
                "league": comp.canonical_name,
                "error": f"abort {code}: {reason}",
            }
            if not clean:
                stats["competitions_failed"] += 1
            break
        except Exception as exc:  # noqa: BLE001 - one league must not sink the run
            stats["competitions_failed"] += 1
            stats["per_league"][comp_id] = {
                "league": comp.canonical_name,
                "error": f"{type(exc).__name__}: {str(exc)[:120]}",
            }
            continue

        stats["live_requests"] += used
        stats["competitions_queried"] += 1
        if not ok:
            stats["competitions_failed"] += 1

        in_window = 0
        with_history = 0
        added = 0
        refreshed = 0
        for fixture in fixtures:
            if str(fixture.get("status", "")).lower() not in _SCHEDULED_STATES:
                continue
            ts = _utc_to_unix(fixture.get("utc_date"))
            if ts is None or ts <= now or ts > horizon:
                continue
            in_window += 1
            home = (fixture.get("home_team") or {}).get("name")
            away = (fixture.get("away_team") or {}).get("name")
            has_history = bool(teams) and home in teams and away in teams
            if has_history:
                with_history += 1
            mid = fixture.get("id")
            if not mid:
                continue
            row = {
                "ts": ts,
                "comp": comp_id,
                "status": "scheduled",
                "home": home,
                "away": away,
                # Reported, never used as an exclusion here. The model stage decides.
                "both_teams_in_corpus": has_history,
            }
            if mid in existing:
                meta[mid] = {**meta.get(mid, {}), **row}
                refreshed += 1
            else:
                meta[mid] = row
                match_ids.append(mid)
                existing.add(mid)
                added += 1

        stats["upcoming_in_window"] += in_window
        stats["with_corpus_history"] += with_history
        stats["without_corpus_history"] += in_window - with_history
        stats["added"] += added
        stats["refreshed"] += refreshed
        if in_window:
            stats["competitions_with_upcoming"] += 1
        stats["per_league"][comp_id] = {
            "league": comp.canonical_name,
            "fixtures_returned": len(fixtures),
            "upcoming_in_window": in_window,
            "with_corpus_history": with_history,
            "model_prerequisites_missing": in_window - with_history,
            "added": added,
            "refreshed": refreshed,
        }

    stats["duration_seconds"] = round(time.time() - run_start, 2)

    if not dry_run:
        universe["generated"] = _now_iso()
        universe["last_discovery"] = _now_iso()
        universe["meta"] = meta
        universe["match_ids"] = match_ids
        universe["scope_rule"] = "dual_provider_intersection"
        FIXTURE_LIST.parent.mkdir(parents=True, exist_ok=True)
        tmp = FIXTURE_LIST.with_suffix(".json.tmp")
        json.dump(universe, open(tmp, "w"), indent=2, default=str)
        tmp.replace(FIXTURE_LIST)

    if stats["competitions_failed"] and not stats["competitions_with_upcoming"]:
        state = "failed"
    elif stats["upcoming_in_window"]:
        state = "found"
    else:
        state = "empty"
    if not dry_run:
        _write_status(state, stats)
    stats["state"] = state
    return stats


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Discover upcoming fixtures across the dual-provider universe"
    )
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--request-cap", type=int, default=REQUEST_CAP)
    parser.add_argument("--window-days", type=int, default=WINDOW_DAYS)
    parser.add_argument(
        "--competition", action="append", default=None,
        help="restrict to a competition id (repeatable)",
    )
    args = parser.parse_args(argv)

    stats = discover(
        dry_run=args.dry_run,
        request_cap=args.request_cap,
        window_days=args.window_days,
        competition_ids=args.competition,
    )
    compact = {k: v for k, v in stats.items() if k != "per_league"}
    print(json.dumps(compact, indent=2, default=str))
    print(f"per_league: {len(stats['per_league'])} competitions")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
