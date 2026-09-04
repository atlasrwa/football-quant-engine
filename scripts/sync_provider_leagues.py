#!/usr/bin/env python3
"""Build a fail-closed FootyStats <-> TheStatsAPI league registry.

This synchronizes provider identities and capabilities; it does NOT promote a
league into Pilot C. Every new league/market remains research-only until its
corpus, mapping, odds, calibration, and forward evidence pass separate gates.

Default operation is cache-only and spends no API quota. ``--refresh`` fetches a
fresh daily-bucketed provider inventory (normally three live requests).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/home/ubuntu")
FOOTY_CACHE = ROOT / ".cache/footystats_research/league-list_{chosen_leagues_only:_true}.json"
STATS_CACHE = (
    ROOT / "data/thestatsapi/championship/competitions_list_p1.json",
    ROOT / "data/thestatsapi/championship/competitions_list_p2.json",
)
CORPUS_MANIFEST = ROOT / "data/discovery/corpus/manifest.json"
OUTPUT = ROOT / "data/discovery/provider_league_registry.json"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# Reviewed identities. Splits are explicit rather than hidden behind fuzzy matching.
# None means TheStatsAPI's current competition inventory has no defensible counterpart.
REVIEWED_CROSSWALK: dict[str, tuple[str, ...] | None] = {
    "USA MLS": ("comp_9799",),
    "Scotland Premiership": ("comp_6387",),
    "Germany Bundesliga": ("comp_4643",),
    "England Premier League": ("comp_3039",),
    "Portugal Liga NOS": ("comp_8385",),
    "Turkey Süper Lig": ("comp_9235",),
    "England Championship": ("comp_8321",),
    "England EFL League One": ("comp_0196",),
    "England EFL League Two": ("comp_4023",),
    "Spain La Liga": ("comp_8814",),
    "Spain Segunda División": ("comp_0976",),
    "Norway Eliteserien": ("comp_1992",),
    "Netherlands Eredivisie": ("comp_3809",),
    "Finland Veikkausliiga": ("comp_2674",),
    "France Ligue 1": ("comp_0256",),
    "Italy Serie A": ("comp_5840",),
    "France Ligue 2": ("comp_9777",),
    "Italy Serie B": ("comp_5450",),
    "Belgium Pro League": ("comp_8531",),
    "Germany 2. Bundesliga": ("comp_0406",),
    "Austria Bundesliga": ("comp_4893",),
    "Austria 2. Liga": ("comp_4519",),
    "Australia A-League": ("comp_6151",),
    "Brazil Serie A": ("comp_4795",),
    "Sweden Allsvenskan": ("comp_1002",),
    "Argentina Primera División": ("comp_4540",),
    "Poland 1. Liga": None,
    "Switzerland Super League": ("comp_4084",),
    "Japan J1 League": ("comp_6240",),
    "Greece Super League": ("comp_4008",),
    "Poland Ekstraklasa": ("comp_9711",),
    "Mexico Liga MX": ("comp_298265", "comp_137103"),
    "Norway First Division": ("comp_9715",),
    "Croatia Prva HNL": ("comp_1941",),
    "Serbia SuperLiga": ("comp_1965",),
    "Slovenia PrvaLiga": ("comp_9722",),
    "Slovakia Super Liga": ("comp_2576",),
    "Republic of Ireland Premier Division": ("comp_9788",),
    "Colombia Categoria Primera A": ("comp_720692",),
    "Israel Israeli Premier League": ("comp_6429",),
    "Czech Republic First League": ("comp_9766",),
    "Denmark Superliga": ("comp_7938",),
    "Belgium First Division B": ("comp_7218",),
    "Bulgaria First League": ("comp_3758",),
    "Cyprus First Division": ("comp_2593",),
    "Hungary NB I": ("comp_3664",),
    "Iceland Úrvalsdeild": ("comp_8338",),
    "Saudi Arabia Professional League": ("comp_45025",),
    "Romania Liga I": ("comp_9639",),
}

# Provider representation is not one-to-one for these annual competitions.
REPRESENTATION_NOTES = {
    "Mexico Liga MX": "TheStatsAPI separates Apertura and Clausura competitions.",
    "Colombia Categoria Primera A": "Only the Apertura counterpart is present in the cached TheStatsAPI inventory.",
}


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _cached_inventories() -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    footy = json.loads(FOOTY_CACHE.read_text()).get("data", [])
    stats: list[dict[str, Any]] = []
    for path in STATS_CACHE:
        stats.extend(json.loads(path.read_text()).get("data", []))
    return footy, stats, 0


def _refreshed_inventories() -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    _load_env()
    from src.research.footystats.client import FootyStatsResearchClient
    import thestatsapi_client as stats_api

    bucket = datetime.now(timezone.utc).strftime("%Y%m%d")
    footy_client = FootyStatsResearchClient(
        cache_dir=ROOT / ".cache/footystats_research/league_sync" / bucket
    )
    footy = footy_client.fetch_league_list()
    stats: list[dict[str, Any]] = []
    page = 1
    while True:
        payload, _ = stats_api.get_json(
            "/football/competitions",
            params={"page": page, "per_page": 100},
            cache_key=f"league_sync_competitions_{bucket}_p{page}",
        )
        stats.extend(payload.get("data", []))
        if page >= int(payload.get("meta", {}).get("total_pages", 1) or 1):
            break
        page += 1
    return footy, stats, footy_client.request_count + stats_api.live_requests_made()


def _current_footy_season(league: dict[str, Any]) -> dict[str, Any] | None:
    seasons = league.get("season") or []
    return max(seasons, key=lambda row: int(row.get("year") or 0), default=None)


def build_registry(
    footy_leagues: list[dict[str, Any]], stats_competitions: list[dict[str, Any]]
) -> dict[str, Any]:
    from src.research.forward.league_coverage import COVERED_LEAGUE_COMP_IDS

    stats_by_id = {row["id"]: row for row in stats_competitions if row.get("id")}
    manifest = json.loads(CORPUS_MANIFEST.read_text()) if CORPUS_MANIFEST.exists() else {}
    corpus_by_name = {row["league"]: row for row in manifest.get("leagues", [])}
    rows: list[dict[str, Any]] = []

    for footy in footy_leagues:
        name = footy.get("name")
        reviewed_ids = REVIEWED_CROSSWALK.get(name)
        comps = [stats_by_id[cid] for cid in (reviewed_ids or ()) if cid in stats_by_id]
        missing_ids = [cid for cid in (reviewed_ids or ()) if cid not in stats_by_id]
        corpus = corpus_by_name.get(name)
        season_count = len((corpus or {}).get("seasons", []))
        current = _current_footy_season(footy)

        if name not in REVIEWED_CROSSWALK or reviewed_ids is None or missing_ids:
            mapping_status = "BLOCKED"
        elif name in REPRESENTATION_NOTES:
            mapping_status = "SPLIT_OR_PARTIAL"
        else:
            mapping_status = "MATCHED"

        existing_pilot = any(cid in COVERED_LEAGUE_COMP_IDS for cid in (reviewed_ids or ()))
        if mapping_status == "BLOCKED":
            model_status = "BLOCKED_PROVIDER_MAPPING"
        elif season_count < 2:
            model_status = "BLOCKED_NO_TWO_SEASON_CORPUS"
        elif existing_pilot:
            model_status = "PILOT_C_EXISTING_SCOPE"
        else:
            model_status = "RESEARCH_ONLY_NOT_VALIDATED"

        rows.append({
            "footystats": {
                "name": name,
                "country": footy.get("country"),
                "current_season_id": (current or {}).get("id"),
                "current_season_year": (current or {}).get("year"),
            },
            "thestatsapi": {
                "competition_ids": list(reviewed_ids or ()),
                "competitions": [
                    {
                        "id": comp.get("id"),
                        "name": comp.get("name"),
                        "country": comp.get("country"),
                        "odds_available": bool(comp.get("odds_available")),
                        "live_odds_available": bool(comp.get("live_odds_available")),
                        "xg_available": bool(comp.get("xg_available")),
                        "has_team_stats": bool(comp.get("has_team_stats")),
                        "has_player_stats": bool(comp.get("has_player_stats")),
                    }
                    for comp in comps
                ],
            },
            "mapping_status": mapping_status,
            "representation_note": REPRESENTATION_NOTES.get(name),
            "corpus": {
                "complete_seasons": season_count,
                "completed_matches": sum(
                    int(s.get("completed_matches") or 0)
                    for s in (corpus or {}).get("seasons", [])
                ),
            },
            "model_status": model_status,
            "production_enabled": False,
            "production_note": (
                "Registry synchronization is metadata only. Enablement requires "
                "league-market backtesting, calibration, and attested forward evidence."
            ),
        })

    footy_names = {row.get("name") for row in footy_leagues}
    unreviewed = sorted(name for name in footy_names if name not in REVIEWED_CROSSWALK)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["model_status"]] = counts.get(row["model_status"], 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": "all provider matches start fail-closed; synchronization does not imply model eligibility",
        "footystats_chosen_leagues": len(footy_leagues),
        "thestatsapi_competitions": len(stats_competitions),
        "reviewed_crosswalk_entries": len(REVIEWED_CROSSWALK),
        "unreviewed_footystats_names": unreviewed,
        "summary": counts,
        "leagues": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="refresh daily provider inventories")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    footy, stats, live_requests = (
        _refreshed_inventories() if args.refresh else _cached_inventories()
    )
    registry = build_registry(footy, stats)
    registry["inventory_mode"] = "daily-refresh" if args.refresh else "cache-only"
    registry["live_requests"] = live_requests
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(args.output.suffix + ".tmp")
    tmp.write_text(json.dumps(registry, indent=2, sort_keys=True, ensure_ascii=False))
    tmp.replace(args.output)

    print(
        f"synced {registry['footystats_chosen_leagues']} FootyStats leagues against "
        f"{registry['thestatsapi_competitions']} TheStatsAPI competitions; "
        f"live_requests={live_requests}"
    )
    for status, count in sorted(registry["summary"].items()):
        print(f"  {status}: {count}")
    if registry["unreviewed_footystats_names"]:
        print("unreviewed:", ", ".join(registry["unreviewed_footystats_names"]))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
