#!/usr/bin/env python3
"""Refresh the training corpus with completed current-season matches.

WHY THIS EXISTS
===============
Three data paths ran in this repo and the first two never fed the third:

1. Fixture discovery  -> ``_pilotC_fixture_list.json``            (current)
2. Settlement         -> ``forecast_eval_match_*`` / ``_stats_*`` (current)
3. Forecast training  -> ``load_corpus()`` over ``data/discovery/corpus/``

Nothing wrote current-season matches into (3). The corpus held the last two
*completed* seasons and nothing else, so on 2026-09-05 the engine published forecasts
whose newest observation was 2026-05-31. This script is path (3)'s missing producer.

WHAT IT DOES
============
For each league in declared broadcast scope it resolves the league's **current**
season id from the daily-refreshed provider registry — never from a hard-coded list —
re-fetches that whole season through the same FootyStats client and cache-key format
the corpus already uses, and reports what changed.

WHAT IT DELIBERATELY REUSES
===========================
``src.discovery.corpus.ingest_on_demand_season`` does the fetching and writing. It
already speaks the cache-key format ``load_corpus()`` globs for, already applies the
client's rate limiting and retries, and already records refreshes in the corpus
manifest. A second fetcher here would be a second thing to keep in step with the
loader, and the two would drift.

WHY IN-SCOPE LEAGUES BY DEFAULT
===============================
The model pools matches across all corpus leagues, but the features that decide a
published forecast are the *rolling per-team* windows for the two teams playing. Those
teams are always in a declared-scope league. Refreshing the four in-scope seasons
therefore fixes every feature that reaches a published number, at four seasons of
quota per run instead of forty-nine. ``--all-leagues`` refreshes the wider pooled
training set and is meant for a weekly run, not a 15-minute one.

This split is also what the freshness gate measures against: the gate benchmarks the
corpus against in-scope fixtures only, so the default here and the gate agree by
construction rather than by coincidence.

WHY FORCE-REFETCH IS ALWAYS ON FOR A CURRENT SEASON
===================================================
The underlying ingest is cache-first, which is right for a completed season —
historical data is immutable. A current season is the opposite: its file is correct
when written and stale a week later. Serving it from cache is precisely the bug being
fixed, so a current-season refresh always re-fetches. Completed seasons are never
touched by this script.

USAGE
=====
    python3 scripts/refresh_corpus.py                 # in-scope leagues
    python3 scripts/refresh_corpus.py --all-leagues   # every registry league
    python3 scripts/refresh_corpus.py --dry-run       # resolve and report, no fetch
    python3 scripts/refresh_corpus.py --quota-report  # projected steady-state cost
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

from src.discovery.corpus import (
    CORPUS_CACHE_DIR,
    SeasonResolutionError,
    ingest_on_demand_season,
    resolve_current_seasons,
    resolve_current_seasons_for_competitions,
)
from src.research.prediction_engine.broadcast.corpus_snapshot import (
    fingerprint_matches,
    observations_per_season,
)
from src.research.prediction_engine.broadcast.scope_config import (
    DEFAULT_CONFIG_PATH,
    ScopeConfigError,
    load_scope_config,
)

#: Where the refresh states what it did. Read by the health report and by anyone
#: asking "when did current-season data last actually arrive".
REFRESH_REPORT = CORPUS_CACHE_DIR / "_refresh_report.json"

logger = logging.getLogger("refresh_corpus")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_targets(
    *, all_leagues: bool, config_path: Path = DEFAULT_CONFIG_PATH
) -> dict[str, dict[str, Any]]:
    """The leagues and current season ids this refresh should fetch.

    Raises:
        SeasonResolutionError: the registry is stale or cannot map a declared league.
            Refusing beats returning an empty target set, which would let the refresh
            report success while fetching nothing.
    """
    if all_leagues:
        return resolve_current_seasons()
    config = load_scope_config(config_path, require_recorded_change=False)
    comp_ids = [league.comp_id for league in config.leagues]
    return resolve_current_seasons_for_competitions(comp_ids)


def refresh(
    *,
    all_leagues: bool = False,
    dry_run: bool = False,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """Re-fetch the current season for each target league.

    Returns:
        A report dict: per-league outcomes, total API requests spent, and the corpus
        fingerprint before and after. The before/after hashes are the honest answer to
        "did this refresh change anything" — a request count alone cannot distinguish
        a successful no-op from a fetch that silently returned nothing new.
    """
    import pilotC_stat_mixer as mix

    started = time.time()
    before = fingerprint_matches(mix.load_corpus())

    report: dict[str, Any] = {
        "report_contract": "corpus-refresh/v1",
        "started_at_utc": _now_iso(),
        "dry_run": dry_run,
        "mode": "all_leagues" if all_leagues else "in_scope_leagues",
        "corpus_before": before.provenance_dict(),
        "leagues": [],
        "api_requests": 0,
        "errors": [],
    }

    try:
        targets = resolve_targets(all_leagues=all_leagues, config_path=config_path)
    except (SeasonResolutionError, ScopeConfigError) as exc:
        logger.error("cannot resolve current seasons: %s", exc)
        report["errors"].append(f"season_resolution: {exc}")
        report["finished_at_utc"] = _now_iso()
        return report

    report["target_count"] = len(targets)
    logger.info(
        "refreshing %d current season(s): %s",
        len(targets),
        ", ".join(f"{name} ({info['season_id']})" for name, info in sorted(targets.items())),
    )

    for league_name, info in sorted(targets.items()):
        season_id = int(info["season_id"])
        entry: dict[str, Any] = {
            "league": league_name,
            "season_id": season_id,
            "season_year": info.get("season_year"),
        }
        if dry_run:
            entry["status"] = "resolved_only"
            report["leagues"].append(entry)
            continue
        try:
            # force_refetch: a current season gains matches every week, so serving it
            # from cache would reproduce the staleness this script exists to fix.
            outcome = ingest_on_demand_season(season_id, force_refetch=True)
            entry.update(
                status="fetched",
                total_matches=outcome.get("total_matches"),
                completed_matches=outcome.get("completed_matches"),
                api_requests=outcome.get("api_requests", 0),
            )
            report["api_requests"] += int(outcome.get("api_requests") or 0)
        except Exception as exc:  # noqa: BLE001 - one league must not sink the refresh
            # Recorded per league rather than aborting: a provider hiccup on one
            # league should not deny the others their current data. The freshness
            # gate is what decides whether the resulting corpus is publishable, so a
            # partial refresh cannot quietly become a published forecast.
            logger.error("league %s season %d failed: %s", league_name, season_id, exc)
            entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            report["errors"].append(f"{league_name} ({season_id}): {exc}")
        report["leagues"].append(entry)

    after = fingerprint_matches(mix.load_corpus())
    report["corpus_after"] = after.provenance_dict()
    report["corpus_changed"] = before.content_hash != after.content_hash
    report["matches_added"] = after.match_count - before.match_count
    report["season_coverage"] = {
        season_id: coverage
        for season_id, coverage in observations_per_season(mix.load_corpus()).items()
        if any(str(int(t["season_id"])) == season_id for t in targets.values())
    }
    report["elapsed_seconds"] = round(time.time() - started, 1)
    report["finished_at_utc"] = _now_iso()

    if not dry_run:
        REFRESH_REPORT.parent.mkdir(parents=True, exist_ok=True)
        REFRESH_REPORT.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
    return report


def quota_report(*, config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Projected provider cost of the refresh, measured rather than guessed.

    Counts the pages actually on disk per target season, because the per-season
    request count is one request per page of 300 matches and that is a property of the
    season's size, not something to estimate.
    """
    in_scope = resolve_targets(all_leagues=False, config_path=config_path)
    everything = resolve_current_seasons()

    def pages_for(season_id: int) -> int:
        return max(1, len(list(CORPUS_CACHE_DIR.glob(f"*season_id:_{season_id}*"))))

    in_scope_requests = sum(pages_for(int(i["season_id"])) for i in in_scope.values())
    all_requests = sum(pages_for(int(i["season_id"])) for i in everything.values())
    return {
        "report_contract": "corpus-refresh-quota/v1",
        "generated_at_utc": _now_iso(),
        "in_scope_seasons": len(in_scope),
        "in_scope_requests_per_refresh": in_scope_requests,
        "all_league_seasons": len(everything),
        "all_league_requests_per_refresh": all_requests,
        "steady_state": {
            "in_scope_daily_refresh": in_scope_requests,
            "in_scope_monthly": in_scope_requests * 30,
            "all_leagues_weekly": all_requests,
            "all_leagues_monthly": all_requests * 4,
            "combined_monthly": in_scope_requests * 30 + all_requests * 4,
        },
        "note": (
            "One request per 300-match page per season. Completed seasons are never "
            "re-fetched, so this is the whole recurring cost of keeping the training "
            "corpus current."
        ),
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-leagues", action="store_true",
                        help="refresh every league in the provider registry, not just "
                             "declared broadcast scope")
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve current seasons and report; fetch nothing")
    parser.add_argument("--quota-report", action="store_true",
                        help="print projected provider cost and exit")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="refresh_corpus: %(levelname)s %(message)s"
    )

    if args.quota_report:
        print(json.dumps(quota_report(config_path=Path(args.config)),
                         indent=2, sort_keys=True, default=str))
        return 0

    report = refresh(
        all_leagues=args.all_leagues,
        dry_run=args.dry_run,
        config_path=Path(args.config),
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
