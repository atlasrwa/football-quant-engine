#!/usr/bin/env python3
"""Pilot C — weekly covered-league FIXTURE DISCOVERY.

THE PROBLEM THIS SOLVES. The scheduled forward loop (scripts/pilotC_forward_loop.py)
drains a fixed fixture universe (`_pilotC_fixture_list.json`) and, once drained, has
nothing to process. Cron keeps firing every 6 hours, finds nothing, and reports zero
activity indefinitely. That does not look like a failure — it looks like a healthy
system with no fixtures. This module is the missing inflow: it discovers UPCOMING
fixtures in the covered leagues and merges them into the fixture universe so the loop
always has fresh, settleable games to commit before kickoff.

WHAT "COVERED LEAGUES" MEANS HERE. Per the covered-league top-up plan, we do NOT
broaden to new leagues (that costs requests and dilutes per-cell power). Discovery is
restricted to the four leagues that already have corpus team-history coverage:

    Championship (comp_8321), EPL (comp_3039), Ligue 2 (comp_9777), La Liga 2 (comp_0976)

These are TheStatsAPI competition ids (a different id space from the FootyStats
season_ids used to build the corpus — the two are bridged by TEAM NAME downstream in
covered_league_topup / pilotC_forward_predict, exactly as before). We query each
competition's CURRENT season implicitly: TheStatsAPI's /football/matches returns the
active season when `status=scheduled` is given without a season_id, so we never pin a
stale season_id.

SETTLEABILITY GATE (both teams must be in the corpus). A fixture can only be
predicted and later settled if BOTH of its teams have corpus history — that is the
exact gate pilotC_forward_predict applies (`if home not in corpus_teams or away not
in corpus_teams: continue`) and the tier0 rule in covered_league_topup. So discovery
only ADDS fixtures whose both teams are in the corpus; adding uncoverable fixtures
would inflate the "available" denominator with games the loop can never commit or
settle. This matters for two of the four named leagues: La Liga 2 is not present in
the FootyStats corpus (CORPUS_SEASONS has Spain LA LIGA top-flight, not the Segunda),
and current Ligue 2 rosters only partly overlap the corpus (promotion/relegation
churn). Discovery therefore fetches all four leagues (cheap, cache-first) but reports,
per league, both how many upcoming fixtures were SEEN and how many are actually
COVERED/settleable — so the corpus gap is surfaced loudly rather than hidden. If
La Liga 2 coverage is wanted, the corpus must be extended deliberately (out of scope
for this task and forbidden by the top-up policy's "no new leagues implicitly" rule).

LOOK-AHEAD WINDOW — 10 days (env PILOTC_DISCOVERY_WINDOW_DAYS).
Covered-league fixtures cluster on weekends. The forward loop runs every 6 hours and
must commit each fixture at least MIN_HOURS_BEFORE_KICKOFF (2h) before kickoff — a
missed pre-kickoff window is PERMANENT sample loss (the ledger never backdates). A
10-day forward window, refreshed twice weekly (every ~3.5 days), means every upcoming
fixture is discovered and merged 2-3 times before it kicks off. Even if one discovery
run is skipped and two consecutive 6-hourly loop runs fail, a fixture discovered ~10
days out still has ample margin to be committed >2h pre-kickoff. The window is sized
to the commit margin with generous redundancy, not to the (much shorter) commit window
itself.

IDEMPOTENT. Discovery MERGES into the existing universe by match id (mt_...). A
fixture already present is never duplicated; its metadata is refreshed in place
(status/kickoff can change as the API updates). Re-running discovery any number of
times yields the same universe.

CACHE-FIRST + QUOTA-CAPPED + REPORTED. Every page fetch goes through the cache-first
TheStatsAPI client. Because scheduled-fixture listings change over time (games move to
finished, kickoff times shift), a permanently-cached page would go stale, so the cache
key is bucketed by UTC DATE: same-day re-runs cost ZERO budget (idempotent, free),
while a new day re-fetches once. A hard per-run live-request cap
(PILOTC_DISCOVERY_REQUEST_CAP, default 40) protects the monthly budget; the client
aborts cleanly (SystemExit) rather than exceeding it. Every run reports requests used
and projects the weekly consumption rate so the runway to the 2027 readout stays
visible.

THREE STATES, NEVER CONFLATED. Discovery writes a status file
(data/discovery/pilotC_discovery_status.json) recording exactly one of:
  * "found"      — ran, found N upcoming covered fixtures (healthy)
  * "empty"      — ran, found ZERO (possibly legitimate, e.g. international break)
  * "failed"     — did not complete (network/auth/cap/exception)
The health report reads this so a silent failure can never masquerade as an empty week
or as success.

DISTINCT FROM PIPELINE A. This only ever writes Pilot C's fixture universe
(data/thestatsapi/championship/_pilotC_fixture_list.json). It never touches Pipeline
A's data. Discovered fixtures are plain fixtures in the pre-registered covered leagues;
nothing here creates ad-hoc/demo predictions.

Usage:
    python3 scripts/pilotC_fixture_discovery.py            # discover + merge
    python3 scripts/pilotC_fixture_discovery.py --dry-run  # report only, no merge/write
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

# Load env so a cron invocation (which does not source ~/.bashrc) still gets the
# THESTATS_API_KEY. Mirrors pilotC_forward_loop's loader.
_ENV_PATH = "/home/ubuntu/.env"
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import thestatsapi_client as api  # noqa: E402

# ── covered leagues (TheStatsAPI competition ids) ────────────────────────────
# These four leagues already have corpus team-history coverage. Do NOT add new
# leagues here — that is explicitly out of scope for the top-up policy.
COVERED_LEAGUES = {
    "comp_8321": "England Championship",
    "comp_3039": "England Premier League",
    "comp_9777": "France Ligue 2",
    "comp_0976": "Spain La Liga 2",
}

FIXTURE_LIST = Path("/home/ubuntu/data/thestatsapi/championship/_pilotC_fixture_list.json")
STATUS_FILE = Path("/home/ubuntu/data/discovery/pilotC_discovery_status.json")
DISCOVERY_LOG = Path("/home/ubuntu/data/discovery/pilotC_discovery_log.jsonl")

# Look-ahead window (days). See module docstring for the sizing rationale.
WINDOW_DAYS = int(os.environ.get("PILOTC_DISCOVERY_WINDOW_DAYS", "10"))
# Hard per-run live-request cap for discovery. 4 leagues x ~6 pages worst case = 24;
# 40 gives headroom while still protecting the monthly budget.
REQUEST_CAP = int(os.environ.get("PILOTC_DISCOVERY_REQUEST_CAP", "40"))
# Twice-weekly cadence assumed for the weekly-consumption projection.
DISCOVERY_RUNS_PER_WEEK = float(os.environ.get("PILOTC_DISCOVERY_RUNS_PER_WEEK", "2"))
PER_PAGE = 100
_SCHEDULED_STATES = {"scheduled", "upcoming", "not_started", "timed", "fixture"}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _utc_to_unix(utc_date: str) -> float | None:
    if not utc_date:
        return None
    try:
        return datetime.fromisoformat(utc_date.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _load_universe() -> dict:
    if FIXTURE_LIST.exists():
        try:
            return json.load(open(FIXTURE_LIST))
        except Exception:
            pass
    return {"generated": _now_iso(), "match_ids": [], "meta": {}}


def _write_status(state: str, payload: dict) -> None:
    """Record exactly one of found/empty/failed so the health report can tell them apart."""
    rec = {"state": state, "generated": _now_iso(), **payload}
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(rec, open(STATUS_FILE, "w"), indent=2, default=str)
    DISCOVERY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DISCOVERY_LOG, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def _fetch_league_scheduled(comp_id: str, day_bucket: str) -> tuple[list[dict], int, bool]:
    """Fetch all scheduled-fixture pages for one competition's current season.

    Cache key is bucketed by UTC day so same-day re-runs are free but a new day
    refreshes. Returns (fixtures, live_requests_used_delta, ok).
    """
    before = api.live_requests_made()
    fixtures: list[dict] = []
    ck0 = f"discovery_{comp_id}_scheduled_{day_bucket}_p1"
    data, meta = api.get_json(
        "/football/matches",
        params={"competition_id": comp_id, "status": "scheduled",
                "per_page": PER_PAGE, "page": 1},
        cache_key=ck0, allow_status=(200, 404, 422))
    if not data or meta.get("http_status") != 200:
        return [], api.live_requests_made() - before, meta.get("http_status") in (200, 404)
    fixtures.extend(data.get("data", []))
    total_pages = int(data.get("meta", {}).get("total_pages", 1) or 1)
    for p in range(2, total_pages + 1):
        ck = f"discovery_{comp_id}_scheduled_{day_bucket}_p{p}"
        pg, pmeta = api.get_json(
            "/football/matches",
            params={"competition_id": comp_id, "status": "scheduled",
                    "per_page": PER_PAGE, "page": p},
            cache_key=ck, allow_status=(200, 404, 422))
        if pg and pmeta.get("http_status") == 200:
            fixtures.extend(pg.get("data", []))
    return fixtures, api.live_requests_made() - before, True


def _load_corpus_teams() -> set[str]:
    """Team names with corpus history — the settleability gate (both must be present).

    Uses the same loader as the predictor/top-up so discovery's notion of "covered"
    is identical to what actually gets predicted and settled downstream.
    """
    import pilotC_stat_mixer as mix
    ms = mix.load_corpus()
    hist = mix.build_histories(ms)
    return set(hist.keys())


def discover(dry_run: bool = False) -> dict:
    """Discover upcoming covered-league fixtures and merge into the universe.

    Returns a stats dict. Always writes the discovery status file (found/empty/failed)
    unless dry_run, in which case it reports without writing the universe.
    """
    run_start = time.time()
    now = time.time()
    horizon = now + WINDOW_DAYS * 86400
    day_bucket = datetime.now(timezone.utc).strftime("%Y%m%d")

    # Respect the per-run discovery cap on top of the client's own cap.
    api.MAX_LIVE_REQUESTS = min(api.MAX_LIVE_REQUESTS, REQUEST_CAP)

    # Settleability gate: both teams must be in the corpus. If the corpus cannot be
    # loaded we degrade to "add everything in-window" but flag it loudly, since
    # without the gate the universe would fill with uncoverable fixtures.
    corpus_load_error = None
    try:
        corpus_teams = _load_corpus_teams()
    except Exception as e:
        corpus_teams = set()
        corpus_load_error = f"{type(e).__name__}: {str(e)[:120]}"

    quota_before = api.budget_snapshot().get("last_monthly_remaining")
    universe = _load_universe()
    meta = universe.setdefault("meta", {})
    match_ids = universe.setdefault("match_ids", [])
    existing_ids = set(match_ids)

    per_league: dict[str, dict] = {}
    total_in_window = 0
    total_covered_in_window = 0
    added = 0
    refreshed = 0
    requests_used = 0
    hit_cap = False
    errors: list[str] = []

    # If the corpus cannot be loaded, the settleability gate CANNOT be applied.
    # Adding fixtures blind would pollute the universe with uncoverable games that
    # the loop can never commit or settle — inflating the "available" denominator and
    # corrupting the pre-registered sample's covered-fixture accounting. That is the
    # exact silent-failure mode this whole task exists to prevent, so we refuse to
    # merge: report FAILED (broken inflow) and let the health report flag it loudly
    # rather than write junk that looks like healthy discovery.
    if corpus_load_error:
        errors.append(
            f"corpus load failed ({corpus_load_error}) — settleability gate CANNOT be "
            f"applied; refusing to merge (would add uncoverable fixtures). This is a "
            f"BROKEN inflow, not an empty week. Fix the corpus/interpreter (the loop "
            f"must run under the venv that has sklearn) and re-run.")
        stats = {
            "generated": _now_iso(),
            "window_days": WINDOW_DAYS,
            "covered_leagues": COVERED_LEAGUES,
            "per_league": {},
            "upcoming_fixtures_in_window_seen": 0,
            "covered_settleable_fixtures_in_window": 0,
            "fixtures_added": 0,
            "fixtures_refreshed_in_place": 0,
            "universe_size_after": len(match_ids),
            "requests": {
                "live_requests_used_this_run": 0,
                "per_run_request_cap": REQUEST_CAP,
                "monthly_remaining_before": quota_before,
                "monthly_remaining_after": quota_before,
                "monthly_quota_used_this_run": 0,
                "assumed_discovery_runs_per_week": DISCOVERY_RUNS_PER_WEEK,
                "projected_weekly_request_consumption": 0.0,
                "weeks_of_runway_at_this_rate": None,
                "note": "Discovery aborted before any fetch — corpus/gate unavailable.",
            },
            "errors": errors,
            "hit_request_cap": False,
            "duration_seconds": round(time.time() - run_start, 1),
            "dry_run": dry_run,
            "state": "failed",
            "SEPARATION_NOTE": "Writes only Pilot C's fixture universe; never Pipeline A.",
        }
        _write_status("failed", stats)
        _print_summary(stats)
        return stats

    for comp_id, name in COVERED_LEAGUES.items():
        try:
            fixtures, used, ok = _fetch_league_scheduled(comp_id, day_bucket)
            requests_used += used
        except SystemExit as e:
            # client hit a cap / abort — record and stop cleanly (partial discovery)
            hit_cap = True
            errors.append(f"{name}: client abort (SystemExit {e.code})")
            break
        except Exception as e:  # network/parse — treat as failure for this league
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
            per_league[comp_id] = {"league": name, "error": str(e)[:120]}
            continue

        in_window = 0
        covered_in_window = 0
        league_added = 0
        for fx in fixtures:
            status = str(fx.get("status", "")).lower()
            if status not in _SCHEDULED_STATES:
                continue
            ts = _utc_to_unix(fx.get("utc_date"))
            if ts is None:
                continue
            # Only fixtures inside the look-ahead window and still in the future.
            if ts <= now or ts > horizon:
                continue
            in_window += 1
            home = (fx.get("home_team") or {}).get("name")
            away = (fx.get("away_team") or {}).get("name")
            # Settleability gate: both teams must have corpus history (identical to
            # the gate pilotC_forward_predict / covered_league_topup apply). corpus_teams
            # is guaranteed non-empty here — a failed corpus load aborts above.
            both_covered = home in corpus_teams and away in corpus_teams
            if not both_covered:
                continue
            covered_in_window += 1
            mid = fx.get("id")
            if not mid:
                continue
            row = {"ts": ts, "comp": comp_id, "status": "scheduled",
                   "home": home, "away": away}
            if mid in existing_ids:
                # Idempotent refresh in place (do not duplicate).
                meta[mid] = {**meta.get(mid, {}), **row}
                refreshed += 1
            else:
                meta[mid] = row
                match_ids.append(mid)
                existing_ids.add(mid)
                added += 1
                league_added += 1
        total_in_window += in_window
        total_covered_in_window += covered_in_window
        per_league[comp_id] = {
            "league": name,
            "fixtures_returned": len(fixtures),
            "upcoming_in_window": in_window,
            "covered_settleable_in_window": covered_in_window,
            "added": league_added,
            "coverage_gap": in_window - covered_in_window,
        }

    quota_after = api.budget_snapshot().get("last_monthly_remaining")
    try:
        quota_used = int(quota_before) - int(quota_after)
    except Exception:
        quota_used = None

    # Weekly consumption projection (explicit runway visibility).
    weekly_requests = round(requests_used * DISCOVERY_RUNS_PER_WEEK, 1)
    weeks_of_runway = None
    try:
        if weekly_requests > 0 and quota_after is not None:
            weeks_of_runway = round(int(quota_after) / weekly_requests, 1)
    except Exception:
        pass

    stats = {
        "generated": _now_iso(),
        "window_days": WINDOW_DAYS,
        "covered_leagues": COVERED_LEAGUES,
        "per_league": per_league,
        "upcoming_fixtures_in_window_seen": total_in_window,
        "covered_settleable_fixtures_in_window": total_covered_in_window,
        "fixtures_added": added,
        "fixtures_refreshed_in_place": refreshed,
        "universe_size_after": len(match_ids),
        "requests": {
            "live_requests_used_this_run": requests_used,
            "per_run_request_cap": REQUEST_CAP,
            "monthly_remaining_before": quota_before,
            "monthly_remaining_after": quota_after,
            "monthly_quota_used_this_run": quota_used,
            "assumed_discovery_runs_per_week": DISCOVERY_RUNS_PER_WEEK,
            "projected_weekly_request_consumption": weekly_requests,
            "weeks_of_runway_at_this_rate": weeks_of_runway,
            "note": "Cache-first: pages already fetched today cost ZERO. Weekly "
                    "consumption is discovery only; the 6-hourly odds fetch/settle "
                    "phases are separately cache-first and mostly free on re-runs.",
        },
        "errors": errors,
        "hit_request_cap": hit_cap,
        "duration_seconds": round(time.time() - run_start, 1),
        "dry_run": dry_run,
        "SEPARATION_NOTE": "Writes only Pilot C's fixture universe; never Pipeline A. "
                           "Discovered fixtures are pre-registered covered-league games, "
                           "not ad-hoc/demo predictions.",
    }

    # Decide the state (never conflate the three failure modes). "found"/"empty" are
    # judged on SETTLEABLE (both-covered) fixtures, since uncoverable ones do not
    # advance the sample. A hard failure that prevented reaching the API is "failed".
    # (Corpus-load failure is handled earlier: it aborts before any fetch as "failed".)
    reached_api = any("error" not in v for v in per_league.values())
    if not reached_api and errors:
        state = "failed"
    elif total_covered_in_window > 0 or added > 0:
        state = "found"
    else:
        # Ran to completion, reached the API, but found nothing settleable in-window.
        state = "empty" if reached_api else "failed"

    if not dry_run and state != "failed":
        universe["generated"] = _now_iso()
        universe["last_discovery"] = stats["generated"]
        FIXTURE_LIST.parent.mkdir(parents=True, exist_ok=True)
        json.dump(universe, open(FIXTURE_LIST, "w"), indent=2, default=str)

    stats["state"] = state
    _write_status(state, stats)

    _print_summary(stats)
    return stats


def _print_summary(stats: dict) -> None:
    print("=== Pilot C fixture discovery ===")
    print(f"state: {stats['state'].upper()}  window={stats['window_days']}d")
    for comp, d in stats["per_league"].items():
        if "error" in d:
            print(f"  {d['league']:26s} ERROR: {d['error']}")
        else:
            gap = f" (corpus gap {d['coverage_gap']})" if d.get("coverage_gap") else ""
            print(f"  {d['league']:26s} returned={d['fixtures_returned']:4d} "
                  f"in_window={d['upcoming_in_window']:3d} "
                  f"settleable={d['covered_settleable_in_window']:3d} "
                  f"added={d['added']:3d}{gap}")
    print(f"upcoming in window (seen): {stats['upcoming_fixtures_in_window_seen']}  "
          f"covered/settleable: {stats['covered_settleable_fixtures_in_window']}")
    print(f"added={stats['fixtures_added']} refreshed={stats['fixtures_refreshed_in_place']} "
          f"universe_size={stats['universe_size_after']}")
    rq = stats["requests"]
    print(f"requests used this run: {rq['live_requests_used_this_run']} "
          f"(cap {rq['per_run_request_cap']}); monthly remaining "
          f"{rq['monthly_remaining_before']} -> {rq['monthly_remaining_after']}")
    print(f"projected weekly consumption: {rq['projected_weekly_request_consumption']} req/wk "
          f"=> ~{rq['weeks_of_runway_at_this_rate']} weeks of runway at this rate")
    if stats["errors"]:
        print("errors:", stats["errors"][:5])
    if stats["dry_run"]:
        print("(dry run — universe not written)")


def main():
    ap = argparse.ArgumentParser(description="Pilot C weekly covered-league fixture discovery")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be discovered without writing the universe")
    args = ap.parse_args()
    return discover(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
