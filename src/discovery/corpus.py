"""Corpus builder for metric discovery.

Pulls last 2 completed seasons for all 25 leagues, caches to disk.
One-time API cost — historical data is immutable, never re-fetched.

After caching, the entire discovery process runs offline against local
data with zero API calls.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# LEAGUE AND SEASON CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# 25 leagues × 2 seasons (last 2 completed before 2026/27 current season)
CORPUS_SEASONS: dict[str, list[dict[str, Any]]] = {
    "Australia A-League": [{"id": 16036, "year": "20252026"}, {"id": 13703, "year": "20242025"}],
    "Austria Bundesliga": [{"id": 14923, "year": "20252026"}, {"id": 12472, "year": "20242025"}],
    "Belgium Pro League": [{"id": 14937, "year": "20252026"}, {"id": 12137, "year": "20242025"}],
    "Brazil Serie A": [{"id": 14231, "year": "2025"}, {"id": 11321, "year": "2024"}],
    "Denmark Superliga": [{"id": 15055, "year": "20252026"}, {"id": 12132, "year": "20242025"}],
    "England Championship": [{"id": 14930, "year": "20252026"}, {"id": 12451, "year": "20242025"}],
    "England Premier League": [{"id": 15050, "year": "20252026"}, {"id": 12325, "year": "20242025"}],
    "Finland Veikkausliiga": [{"id": 14089, "year": "2025"}, {"id": 11120, "year": "2024"}],
    "France Ligue 1": [{"id": 14932, "year": "20252026"}, {"id": 12337, "year": "20242025"}],
    "France Ligue 2": [{"id": 14954, "year": "20252026"}, {"id": 12338, "year": "20242025"}],
    "Germany 2. Bundesliga": [{"id": 14931, "year": "20252026"}, {"id": 12528, "year": "20242025"}],
    "Germany Bundesliga": [{"id": 14968, "year": "20252026"}, {"id": 12529, "year": "20242025"}],
    "Greece Super League": [{"id": 15163, "year": "20252026"}, {"id": 12734, "year": "20242025"}],
    "Italy Serie A": [{"id": 15068, "year": "20252026"}, {"id": 12530, "year": "20242025"}],
    "Italy Serie B": [{"id": 15632, "year": "20252026"}, {"id": 12621, "year": "20242025"}],
    "Netherlands Eredivisie": [{"id": 14936, "year": "20252026"}, {"id": 12322, "year": "20242025"}],
    "Norway Eliteserien": [{"id": 16260, "year": "2025"}, {"id": 17353, "year": "2024"}],
    "Poland Ekstraklasa": [{"id": 15031, "year": "20252026"}, {"id": 12120, "year": "20242025"}],
    "Portugal Liga NOS": [{"id": 15115, "year": "20252026"}, {"id": 12931, "year": "20242025"}],
    "Scotland Premiership": [{"id": 15000, "year": "20252026"}, {"id": 12455, "year": "20242025"}],
    "Spain La Liga": [{"id": 14956, "year": "20252026"}, {"id": 12316, "year": "20242025"}],
    "Sweden Allsvenskan": [{"id": 16263, "year": "2025"}, {"id": 17350, "year": "2024"}],
    "Switzerland Super League": [{"id": 15047, "year": "20252026"}, {"id": 12326, "year": "20242025"}],
    "Turkey Süper Lig": [{"id": 14972, "year": "20252026"}, {"id": 12641, "year": "20242025"}],
    "USA MLS": [{"id": 13973, "year": "2025"}, {"id": 10977, "year": "2024"}],
}

CORPUS_CACHE_DIR = Path("/home/ubuntu/data/discovery/corpus")
CORPUS_MANIFEST_FILE = CORPUS_CACHE_DIR / "manifest.json"

# Temporal split boundary for discovery vs held-out
# Discovery: season 1 (earlier/older, typically 2024/25 or 2024)
# Held-out: season 2 (later/newer, typically 2025/26 or 2025)
# This preserves walk-forward discipline: we discover on older data, validate on newer.
DISCOVERY_SEASON_INDEX = 1   # Second element (older season)
HELDOUT_SEASON_INDEX = 0     # First element (newer season)


@dataclass
class CorpusStats:
    """Statistics about the cached corpus."""
    total_leagues: int
    total_seasons: int
    total_matches: int
    completed_matches: int
    discovery_matches: int
    heldout_matches: int
    coverage_gaps: list[dict[str, Any]]
    leagues_detail: list[dict[str, Any]]


# ═══════════════════════════════════════════════════════════════
# RAW FIELDS USED FOR METRIC GENERATION
# These are the confirmed point-in-time-safe fields from FootyStats.
# ═══════════════════════════════════════════════════════════════

STAT_FIELDS = [
    # Corners
    "team_a_corners", "team_b_corners",
    "team_a_fh_corners", "team_b_fh_corners",
    "team_a_2h_corners", "team_b_2h_corners",
    # Cards
    "team_a_yellow_cards", "team_b_yellow_cards",
    "team_a_red_cards", "team_b_red_cards",
    "team_a_fh_cards", "team_b_fh_cards",
    "team_a_2h_cards", "team_b_2h_cards",
    # Shots
    "team_a_shots", "team_b_shots",
    "team_a_shotsOnTarget", "team_b_shotsOnTarget",
    "team_a_shotsOffTarget", "team_b_shotsOffTarget",
    # Possession & attacks
    "team_a_possession", "team_b_possession",
    "team_a_attacks", "team_b_attacks",
    "team_a_dangerous_attacks", "team_b_dangerous_attacks",
    # Discipline
    "team_a_fouls", "team_b_fouls",
    "team_a_offsides", "team_b_offsides",
    # Set pieces
    "team_a_freekicks", "team_b_freekicks",
    "team_a_throwins", "team_b_throwins",
    "team_a_goalkicks", "team_b_goalkicks",
    # Goals
    "homeGoalCount", "awayGoalCount", "overallGoalCount",
    # xG
    "team_a_xg", "team_b_xg",
    # Pre-match (point-in-time safe)
    "team_a_xg_prematch", "team_b_xg_prematch",
    "pre_match_home_ppg", "pre_match_away_ppg",
    # Penalties
    "team_a_penalties_won", "team_b_penalties_won",
    "team_a_penalty_goals", "team_b_penalty_goals",
    "team_a_penalty_missed", "team_b_penalty_missed",
]

# Outcome fields (targets, NOT used as inputs)
OUTCOME_FIELDS = [
    "homeGoalCount", "awayGoalCount", "overallGoalCount",
    "team_a_corners", "team_b_corners",
    "team_a_yellow_cards", "team_b_yellow_cards",
    "team_a_red_cards", "team_b_red_cards",
    "team_a_shotsOnTarget", "team_b_shotsOnTarget",
    "btts",
]


def build_corpus(force_refetch: bool = False) -> CorpusStats:
    """Build the discovery corpus from FootyStats API.

    Fetches last 2 completed seasons for all 25 leagues and caches to disk.
    Subsequent calls use the cache (immutable historical data).

    Args:
        force_refetch: If True, ignore cache and re-fetch (rarely needed).

    Returns:
        CorpusStats with size/coverage information.
    """
    sys.path.insert(0, "/home/ubuntu")

    # Load env
    env_path = Path("/home/ubuntu/.env")
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())

    from src.research.footystats.client import FootyStatsResearchClient

    CORPUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    client = FootyStatsResearchClient(
        api_key=os.environ.get("FOOTYSTATS_API_KEY", ""),
        cache_dir=CORPUS_CACHE_DIR,
    )

    stats: dict[str, Any] = {
        "leagues": [],
        "total_matches": 0,
        "completed_matches": 0,
        "gaps": [],
    }

    for league_name, seasons in CORPUS_SEASONS.items():
        league_stat = {"league": league_name, "seasons": []}

        for season_info in seasons:
            season_id = season_info["id"]
            season_year = season_info["year"]

            logger.info("Fetching %s %s (season_id=%d)...", league_name, season_year, season_id)

            try:
                matches = client.fetch_season_matches(season_id)
                completed = [m for m in matches if m.get("status") == "complete"]

                season_stat = {
                    "season_id": season_id,
                    "year": season_year,
                    "total_matches": len(matches),
                    "completed_matches": len(completed),
                }
                league_stat["seasons"].append(season_stat)
                stats["total_matches"] += len(matches)
                stats["completed_matches"] += len(completed)

                # Check for coverage gaps
                if len(completed) < 100:
                    stats["gaps"].append({
                        "league": league_name,
                        "season": season_year,
                        "completed": len(completed),
                        "note": "Low match count — may be in progress or have data issues",
                    })

                logger.info(
                    "  %s %s: %d total, %d completed",
                    league_name, season_year, len(matches), len(completed),
                )

            except Exception as e:
                logger.error("Failed to fetch %s %s: %s", league_name, season_year, str(e))
                stats["gaps"].append({
                    "league": league_name,
                    "season": season_year,
                    "error": str(e)[:100],
                })

        stats["leagues"].append(league_stat)

    # Save manifest
    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "total_leagues": len(CORPUS_SEASONS),
        "total_seasons": sum(len(v) for v in CORPUS_SEASONS.values()),
        "total_matches": stats["total_matches"],
        "completed_matches": stats["completed_matches"],
        "coverage_gaps": stats["gaps"],
        "api_requests": client.request_count,
        "split_boundary": {
            "discovery": "Older season per league (index 1 in CORPUS_SEASONS)",
            "heldout": "Newer season per league (index 0 in CORPUS_SEASONS)",
            "rationale": "Temporal split preserves walk-forward discipline. Discovery on older data, validate on newer.",
        },
        "leagues": stats["leagues"],
    }

    with open(CORPUS_MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info("Corpus built: %d leagues, %d matches (%d completed), %d gaps",
                len(CORPUS_SEASONS), stats["total_matches"],
                stats["completed_matches"], len(stats["gaps"]))

    return _load_corpus_stats()


def _load_corpus_stats() -> CorpusStats:
    """Load corpus stats from manifest."""
    if not CORPUS_MANIFEST_FILE.exists():
        return CorpusStats(0, 0, 0, 0, 0, 0, [], [])

    with open(CORPUS_MANIFEST_FILE) as f:
        manifest = json.load(f)

    # Count discovery vs held-out
    discovery_count = 0
    heldout_count = 0
    for league_stat in manifest.get("leagues", []):
        seasons = league_stat.get("seasons", [])
        if len(seasons) >= 2:
            heldout_count += seasons[0].get("completed_matches", 0)
            discovery_count += seasons[1].get("completed_matches", 0)
        elif len(seasons) == 1:
            discovery_count += seasons[0].get("completed_matches", 0)

    return CorpusStats(
        total_leagues=manifest.get("total_leagues", 0),
        total_seasons=manifest.get("total_seasons", 0),
        total_matches=manifest.get("total_matches", 0),
        completed_matches=manifest.get("completed_matches", 0),
        discovery_matches=discovery_count,
        heldout_matches=heldout_count,
        coverage_gaps=manifest.get("coverage_gaps", []),
        leagues_detail=manifest.get("leagues", []),
    )


def load_discovery_set() -> list[dict[str, Any]]:
    """Load the discovery set (older seasons) from cached corpus.

    These matches are used for generating and screening candidate metrics.
    The held-out set (newer seasons) is NEVER touched during search.
    """
    return _load_matches_by_index(DISCOVERY_SEASON_INDEX)


def load_heldout_set() -> list[dict[str, Any]]:
    """Load the held-out set (newer seasons) from cached corpus.

    WARNING: This must ONLY be called during final validation (Step 6).
    Any access during search compromises the entire exercise.
    """
    return _load_matches_by_index(HELDOUT_SEASON_INDEX)


def _load_matches_by_index(season_index: int) -> list[dict[str, Any]]:
    """Load completed matches for a specific season index across all leagues."""
    all_matches = []

    for league_name, seasons in CORPUS_SEASONS.items():
        if season_index >= len(seasons):
            continue
        season_info = seasons[season_index]
        season_id = season_info["id"]

        # Load from cache
        matches = _load_cached_season(season_id)
        completed = [m for m in matches if m.get("status") == "complete"]

        # Annotate with league info
        for m in completed:
            m["_league"] = league_name
            m["_season"] = season_info["year"]

        all_matches.extend(completed)

    return all_matches


def _load_cached_season(season_id: int) -> list[dict[str, Any]]:
    """Load a cached season's matches from disk."""
    all_matches = []

    # The client caches with a specific key format
    for cache_file in CORPUS_CACHE_DIR.glob(f"*season_id:_{season_id}*"):
        with open(cache_file) as f:
            data = json.load(f)
        if isinstance(data, dict) and "data" in data:
            all_matches.extend(data["data"])

    return all_matches
