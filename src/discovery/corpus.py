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
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# LEAGUE AND SEASON CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# 25 leagues × 2 seasons. These are the **completed** seasons that define the
# research temporal split (see DISCOVERY_SEASON_INDEX / HELDOUT_SEASON_INDEX below).
#
# THIS LIST IS NOT THE TRAINING CORPUS AND MUST NOT BE EXTENDED WITH THE CURRENT
# SEASON. The split indices are positional, so prepending a season here would
# silently reassign which data is "discovery" and which is "held out" — a change to
# every walk-forward result in the repo, made invisibly.
#
# The current season is resolved at run time instead, by
# :func:`resolve_current_seasons` reading the daily-refreshed provider registry. That
# is what stops the corpus ageing out: a hard-coded list of current seasons is correct
# for one year and then quietly wrong, which is exactly how the training corpus came
# to end on 2026-05-31 while forecasts were published in September 2026.
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

#: Provider league registry, refreshed daily by ``scripts/sync_provider_leagues.py
#: --refresh``. Holds each league's *current* season id as the provider reports it,
#: which is the authority for "which season is being played right now".
PROVIDER_LEAGUE_REGISTRY = Path(
    "/home/ubuntu/data/discovery/provider_league_registry.json"
)

#: How stale the registry may be before :func:`resolve_current_seasons` refuses it.
#: A registry that stopped refreshing would pin last season's id and reintroduce the
#: original failure one rollover later, so an unrefreshed registry has to be an error
#: rather than a silently accepted default.
REGISTRY_MAX_AGE_HOURS = 72.0


class SeasonResolutionError(RuntimeError):
    """The current season could not be resolved from the provider registry."""


def resolve_current_seasons(
    *,
    league_names: Optional[Iterable[str]] = None,
    registry_path: Path = PROVIDER_LEAGUE_REGISTRY,
    max_age_hours: float = REGISTRY_MAX_AGE_HOURS,
    now: Optional[datetime] = None,
) -> dict[str, dict[str, Any]]:
    """Resolve each league's current season id from the provider registry.

    This replaces the hard-coded current-season list that the corpus used to depend
    on. The registry is regenerated daily from the provider's own league list, so a
    season rollover propagates without a code change — which is the property the old
    arrangement lacked.

    Args:
        league_names: restrict to these FootyStats league names. ``None`` returns
            every league the registry knows.
        registry_path: the registry file.
        max_age_hours: refuse a registry older than this.
        now: evaluation time, for tests.

    Returns:
        ``{league_name: {"season_id": int, "season_year": Any, "country": str}}``,
        containing only leagues with a usable current season id.

    Raises:
        SeasonResolutionError: the registry is missing, unparseable, or stale. Failing
            loudly here is deliberate: silently returning ``{}`` would make the corpus
            refresh a no-op that reports success, which is the shape of the bug this
            whole change exists to remove.
    """
    if not registry_path.exists():
        raise SeasonResolutionError(
            f"provider league registry not found at {registry_path}. Run "
            "scripts/sync_provider_leagues.py --refresh before refreshing the corpus."
        )
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SeasonResolutionError(
            f"provider league registry at {registry_path} is unreadable: {exc}"
        ) from exc

    generated_raw = registry.get("generated_at")
    if not generated_raw:
        raise SeasonResolutionError(
            "provider league registry has no generated_at stamp, so its age cannot "
            "be checked; refusing to resolve current seasons from it"
        )
    try:
        generated_at = datetime.fromisoformat(str(generated_raw))
    except ValueError as exc:
        raise SeasonResolutionError(
            f"provider league registry generated_at {generated_raw!r} is not an ISO "
            f"timestamp: {exc}"
        ) from exc
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    age_hours = (reference - generated_at).total_seconds() / 3600.0
    if age_hours > float(max_age_hours):
        raise SeasonResolutionError(
            f"provider league registry is {age_hours:.1f}h old (limit "
            f"{max_age_hours:.0f}h), generated {generated_at.isoformat()}. A stale "
            "registry pins a stale season id, so current-season resolution is "
            "refused. Run scripts/sync_provider_leagues.py --refresh."
        )

    wanted = {str(n) for n in league_names} if league_names is not None else None
    resolved: dict[str, dict[str, Any]] = {}
    for entry in registry.get("leagues", []):
        footystats = entry.get("footystats") or {}
        name = footystats.get("name")
        season_id = footystats.get("current_season_id")
        if not name or season_id in (None, "", 0):
            continue
        if wanted is not None and str(name) not in wanted:
            continue
        try:
            resolved[str(name)] = {
                "season_id": int(season_id),
                "season_year": footystats.get("current_season_year"),
                "country": footystats.get("country"),
            }
        except (TypeError, ValueError):
            continue

    if wanted is not None:
        unresolved = sorted(wanted - set(resolved))
        if unresolved:
            raise SeasonResolutionError(
                "no current season id in the provider registry for: "
                f"{unresolved}. These leagues cannot be refreshed."
            )
    if not resolved:
        raise SeasonResolutionError(
            "provider league registry yielded no current season ids at all"
        )
    return resolved


def resolve_current_seasons_for_competitions(
    comp_ids: Iterable[str],
    *,
    registry_path: Path = PROVIDER_LEAGUE_REGISTRY,
    max_age_hours: float = REGISTRY_MAX_AGE_HOURS,
    now: Optional[datetime] = None,
) -> dict[str, dict[str, Any]]:
    """Current seasons for leagues identified by *TheStatsAPI* competition id.

    The broadcast scope declares leagues by TheStatsAPI ``comp_id`` while the training
    corpus is FootyStats-keyed. The registry holds both sides of that crosswalk, so
    this resolves one to the other rather than duplicating the mapping in a second
    place where the two could drift apart.

    Args:
        comp_ids: TheStatsAPI competition ids, e.g. ``comp_8321``.

    Returns:
        ``{league_name: {"season_id", "season_year", "country", "comp_id"}}``.

    Raises:
        SeasonResolutionError: the registry is unusable, or a requested competition
            has no FootyStats current season.
        """
    if not registry_path.exists():
        raise SeasonResolutionError(
            f"provider league registry not found at {registry_path}"
        )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    # Reuse the age/validity check rather than reimplementing it.
    resolve_current_seasons(
        registry_path=registry_path, max_age_hours=max_age_hours, now=now
    )

    wanted = {str(c) for c in comp_ids}
    resolved: dict[str, dict[str, Any]] = {}
    for entry in registry.get("leagues", []):
        competitions = {
            str(c) for c in ((entry.get("thestatsapi") or {}).get("competition_ids") or [])
        }
        matched = competitions & wanted
        if not matched:
            continue
        footystats = entry.get("footystats") or {}
        name = footystats.get("name")
        season_id = footystats.get("current_season_id")
        if not name or season_id in (None, "", 0):
            continue
        resolved[str(name)] = {
            "season_id": int(season_id),
            "season_year": footystats.get("current_season_year"),
            "country": footystats.get("country"),
            "comp_id": sorted(matched)[0],
        }

    missing = sorted(
        wanted
        - {str(v.get("comp_id")) for v in resolved.values()}
    )
    if missing:
        raise SeasonResolutionError(
            "no FootyStats current season could be resolved for in-scope "
            f"competition(s): {missing}. The provider crosswalk in "
            f"{registry_path} does not map them, so their current-season matches "
            "cannot enter the training corpus."
        )
    return resolved

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


def _find_league_for_season(season_id: int) -> Optional[tuple[str, int]]:
    """Find which league/season-index a season_id belongs to in CORPUS_SEASONS.

    Returns:
        (league_name, season_index) if the season_id is a known corpus season,
        else None (the season is not part of the registered corpus).
    """
    for league_name, seasons in CORPUS_SEASONS.items():
        for idx, season_info in enumerate(seasons):
            if int(season_info["id"]) == int(season_id):
                return league_name, idx
    return None


def ingest_on_demand_season(
    season_id: int,
    *,
    force_refetch: bool = False,
    update_manifest: bool = True,
) -> dict[str, Any]:
    """On-demand ingest of a single season into the discovery corpus.

    This is the Option-A "on-demand engine" path: for a season the engine is
    asked to run against, fetch the WHOLE season via the same research client
    and cache-key format the corpus already uses, writing it into
    CORPUS_CACHE_DIR. This keeps the corpus composed of whole, replayable
    seasons (never individual live fixtures), so the existing loaders
    (`_load_cached_season`, `_load_matches_by_index`) pick it up unchanged and
    the temporal split contract is preserved.

    Behaviour:
    - Cache-first: if the season file already exists and force_refetch is
      False, no API call is made.
    - Quota-capped: reuses FootyStatsResearchClient's rate limiting/retries.
    - Refresh: force_refetch re-pulls the season (e.g. to pick up newly
      completed matches for a season already in the corpus).

    Args:
        season_id: FootyStats season/competition ID to ingest.
        force_refetch: If True, bypass the on-disk cache and re-fetch.
        update_manifest: If True, record this season in the corpus manifest
            under an "on_demand_seasons" list so refreshes are auditable.

    Returns:
        A summary dict: {season_id, league (or None if unregistered),
        season_index (or None), total_matches, completed_matches,
        from_cache (bool), api_requests}.
    """
    sys.path.insert(0, "/home/ubuntu")

    # Load env (same lightweight loader as build_corpus)
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

    # Detect whether this season is already cached (cache-first decision).
    existing = list(CORPUS_CACHE_DIR.glob(f"*season_id:_{season_id}*"))
    had_cache = len(existing) > 0

    if had_cache and not force_refetch:
        matches = _load_cached_season(season_id)
        completed = [m for m in matches if m.get("status") == "complete"]
        logger.info(
            "On-demand season %d served from cache: %d total, %d completed",
            season_id, len(matches), len(completed),
        )
        summary = _on_demand_summary(
            season_id, len(matches), len(completed), from_cache=True, api_requests=0
        )
        if update_manifest:
            _record_on_demand(summary, force_refetch=force_refetch)
        return summary

    # Fetch (or refresh) the whole season through the corpus client/key format.
    if force_refetch and had_cache:
        for path in existing:
            path.unlink()
        logger.info("force_refetch: cleared %d cached file(s) for season %d",
                    len(existing), season_id)

    client = FootyStatsResearchClient(
        api_key=os.environ.get("FOOTYSTATS_API_KEY", ""),
        cache_dir=CORPUS_CACHE_DIR,
    )
    matches = client.fetch_season_matches(season_id)
    completed = [m for m in matches if m.get("status") == "complete"]

    logger.info(
        "On-demand season %d ingested: %d total, %d completed (%d API requests)",
        season_id, len(matches), len(completed), client.request_count,
    )

    summary = _on_demand_summary(
        season_id, len(matches), len(completed),
        from_cache=False, api_requests=client.request_count,
    )
    if update_manifest:
        _record_on_demand(summary, force_refetch=force_refetch)
    return summary


def _on_demand_summary(
    season_id: int,
    total: int,
    completed: int,
    *,
    from_cache: bool,
    api_requests: int,
) -> dict[str, Any]:
    """Build the on-demand ingest summary dict, annotating league membership."""
    registration = _find_league_for_season(season_id)
    league_name = registration[0] if registration else None
    season_index = registration[1] if registration else None
    return {
        "season_id": season_id,
        "league": league_name,
        "season_index": season_index,
        "registered": registration is not None,
        "total_matches": total,
        "completed_matches": completed,
        "from_cache": from_cache,
        "api_requests": api_requests,
    }


def _record_on_demand(summary: dict[str, Any], *, force_refetch: bool) -> None:
    """Append/update an on-demand ingest record in the corpus manifest.

    Kept separate from the CORPUS_SEASONS-derived counts so it never alters
    the discovery/held-out split figures. Purely an audit trail of on-demand
    refreshes.
    """
    manifest: dict[str, Any] = {}
    if CORPUS_MANIFEST_FILE.exists():
        with open(CORPUS_MANIFEST_FILE) as f:
            manifest = json.load(f)

    records: list[dict[str, Any]] = manifest.get("on_demand_seasons", [])
    entry = {
        **summary,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "force_refetch": force_refetch,
    }
    # Replace any prior record for the same season_id, keep newest.
    records = [r for r in records if r.get("season_id") != summary["season_id"]]
    records.append(entry)
    manifest["on_demand_seasons"] = records

    CORPUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CORPUS_MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)


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



# ═══════════════════════════════════════════════════════════════
# ON-DEMAND RICH (TheStatsAPI) CORPUS INGEST
# ═══════════════════════════════════════════════════════════════
#
# The Broad (FootyStats) corpus has ``ingest_on_demand_season`` above. The Rich
# (TheStatsAPI) corpus previously had only a *cache-only* read path
# (``src.research.asymmetric.corpus.RichCorpusLoader`` ->
# ``scripts/multisrc_corpus.py`` -> ``scripts/championship_adapter.py``); its
# cache files could only be populated by hand-run scripts. This section adds the
# symmetric on-demand ENGINE path for the Rich corpus:
#
#   fetch (APIs) -> map/adapt -> save to corpus -> register -> loadable
#
# Discipline (mirrors the Broad on-demand path and the project's zero-API rule):
#   * Reuse, do not reimplement. Fetching reuses ``scripts/multisrc_fetch.py``
#     (fixtures + per-match /stats) which writes the EXACT cache files
#     ``RichCorpusLoader`` reads; adaptation reuses ``championship_adapter`` via
#     ``multisrc_corpus.load_season``. No stat is re-derived here.
#   * Cache-first + quota-capped. ``thestatsapi_client`` returns cached files
#     with zero budget and enforces a hard local live-request cap
#     (``THESTATS_MAX_REQUESTS``). Re-runs cost nothing.
#   * New leagues supported. Any competition the API covers can be ingested by
#     passing its ``comp_id`` + ``season_id`` + a ``tag``; the league is
#     persisted to the on-demand registry so ``RichCorpusLoader`` picks it up
#     unchanged (static corpus entries are never overwritten).
#   * Isolation. This lives on the on-demand engine side (``src/discovery``); the
#     zero-API build/backtest path (``src/research/asymmetric``) never imports it.

# Rich (TheStatsAPI) corpus cache dir — the same dir the fetch client and the
# RichCorpusLoader default to.
RICH_CORPUS_CACHE_DIR = Path("/home/ubuntu/data/thestatsapi/championship")
RICH_ON_DEMAND_MANIFEST_FILE = RICH_CORPUS_CACHE_DIR / "_on_demand_manifest.json"

# scripts/ is not an importable package in this codebase, so load the reused
# modules by file path (same technique as src/research/asymmetric/corpus.py).
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _load_script_module(module_name: str, filename: str) -> Any:
    """Import a ``scripts/<filename>`` module by path (no network on import).

    ``scripts/`` is placed on ``sys.path`` first so intra-scripts imports
    (e.g. ``multisrc_fetch`` importing ``thestatsapi_client``, and
    ``multisrc_corpus`` importing ``championship_adapter``) resolve.
    """
    import importlib.util

    scripts_dir = str(_SCRIPTS_DIR)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load {filename} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rich_fixture_prefix_for_tag(multisrc: Any, tag: str) -> str:
    """The fixture/stat filename prefix for a tag.

    A tag already known to the static registry reuses its declared prefix so an
    on-demand top-up of a static league writes to the SAME files the loader
    already reads. A brand-new tag uses the tag itself as its prefix.
    """
    leagues = getattr(multisrc, "LEAGUES", {})
    if tag in leagues:
        return leagues[tag].get("fixture_prefix", tag)
    return tag


def ingest_on_demand_rich_season(
    comp_id: str,
    season_id: str,
    tag: str,
    *,
    display: Optional[str] = None,
    force_refetch: bool = False,
    stats_limit: Optional[int] = None,
    update_manifest: bool = True,
) -> dict[str, Any]:
    """On-demand ingest of a single Rich (TheStatsAPI) league-season.

    This is the Rich-corpus counterpart to :func:`ingest_on_demand_season`. For a
    competition/season the engine is asked to run against, it fetches the WHOLE
    season's fixtures + per-match stats via the same cache-first, quota-capped
    TheStatsAPI client the corpus was originally built with, adapts them into the
    FootyStats-schema match dicts the model consumes, writes them into
    RICH_CORPUS_CACHE_DIR in the loader's exact key format, and registers the
    league so :class:`RichCorpusLoader` loads it unchanged.

    Any competition the API covers is supported — pass its TheStatsAPI
    ``comp_id`` (e.g. ``"comp_9777"``), the ``season_id`` (e.g. ``"sn_3057202"``),
    and a short ``tag`` (e.g. ``"ligue2"``) that namespaces the cache files.

    Behaviour:
    - Cache-first: fixtures/stats already on disk are reused with zero API
      budget. ``force_refetch`` deletes this season's cache files first to force
      a re-pull (e.g. to pick up newly-finished matches).
    - Quota-capped: reuses ``thestatsapi_client``'s hard local request cap
      (``THESTATS_MAX_REQUESTS``) and 12-req/min pacing. A live fetch requires
      ``THESTATS_API_KEY`` in the environment; without it, only cached data can
      be served (a live call aborts inside the client).
    - Zero re-derivation: mapping delegates to ``championship_adapter`` via
      ``multisrc_corpus.load_season``; NULL != ZERO is preserved end to end.

    Args:
        comp_id: TheStatsAPI competition id (e.g. ``"comp_9777"``).
        season_id: TheStatsAPI season id (e.g. ``"sn_3057202"``).
        tag: Short league tag namespacing the cache files (e.g. ``"ligue2"``).
        display: Human-readable league label (defaults to ``tag``).
        force_refetch: If True, clear this season's cache files and re-fetch.
        stats_limit: Optional cap on how many matches' /stats to fetch (useful
            for a bounded probe; None fetches all fixtures' stats).
        update_manifest: If True, record this ingest in the rich on-demand
            manifest audit trail.

    Returns:
        Summary dict: {comp_id, season_id, tag, display, registered (bool),
        total_fixtures, adapted_matches, stats_live_fetched, stats_from_cache,
        from_cache (bool — no live requests were made), api_requests,
        fixture_file, buildable_fields}.
    """
    _load_env_for_thestats()

    RICH_CORPUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    multisrc = _load_script_module("_ondemand_multisrc_corpus", "multisrc_corpus.py")
    fetch = _load_script_module("_ondemand_multisrc_fetch", "multisrc_fetch.py")
    client = _load_script_module("_ondemand_thestats_client", "thestatsapi_client.py")

    # Ensure every reused module targets the rich corpus cache dir.
    cache_dir = str(RICH_CORPUS_CACHE_DIR)
    for mod in (multisrc, fetch, client):
        if hasattr(mod, "CACHE"):
            mod.CACHE = cache_dir
        if hasattr(mod, "CACHE_DIR"):
            mod.CACHE_DIR = cache_dir

    prefix = _rich_fixture_prefix_for_tag(multisrc, tag)
    fixture_file = RICH_CORPUS_CACHE_DIR / (
        f"_all_fixtures_{prefix}_{season_id}.json" if prefix
        else f"_all_fixtures_{season_id}.json"
    )

    requests_before = client.live_requests_made()

    # force_refetch: clear this season's fixture + stats cache so the client
    # re-pulls instead of serving stale files.
    if force_refetch:
        removed = _clear_rich_season_cache(prefix, season_id)
        logger.info(
            "force_refetch: cleared %d cached rich file(s) for %s %s",
            removed, tag, season_id,
        )

    # Step 1: fixtures. Cache-first at the ASSEMBLED-file level: if the
    # _all_fixtures_<prefix>_<season>.json already exists and we are not
    # force-refetching, load it directly and skip pagination (zero API). Only
    # call the paginating fetcher when the assembled file is absent or a refresh
    # was requested. This mirrors the Broad on-demand path's cache-first rule and
    # keeps a fully-cached season strictly zero-cost.
    if fixture_file.exists() and not force_refetch:
        with open(fixture_file) as fh:
            fx_out = json.load(fh)
        logger.info("Rich on-demand: fixtures served from cache for %s %s (%d)",
                    tag, season_id, fx_out.get("n", len(fx_out.get("fixtures", []))))
    else:
        logger.info("Rich on-demand: fetching fixtures for %s %s (comp=%s)...",
                    tag, season_id, comp_id)
        fx_out = fetch.fetch_fixtures(comp_id, season_id, prefix or tag)
    total_fixtures = int(fx_out.get("n", len(fx_out.get("fixtures", []))))

    # Step 2: per-match /stats. Cache-first per match inside fetch_stats. When
    # every match's stats file already exists this makes zero live requests; a
    # live call requires THESTATS_API_KEY and is capped by the client's budget.
    logger.info("Rich on-demand: resolving per-match stats for %s %s...",
                tag, season_id)
    stats_live, stats_cached = fetch.fetch_stats(
        comp_id, season_id, prefix or tag, stats_limit
    )

    # Step 3: register the league so RichCorpusLoader picks it up. Static
    # entries are never overwritten (merge_on_demand_registry lets them win).
    multisrc.register_on_demand_league(
        tag,
        display=display or tag,
        comp=comp_id,
        season_id=season_id,
        fixture_prefix=prefix,
    )

    # Step 4: map/adapt via the existing loader (championship_adapter) to prove
    # the season is loadable and to report buildable-field coverage. No re-derive.
    adapted = multisrc.load_season(tag, season_id)
    buildable = _rich_buildable_fields(adapted)

    api_requests = client.live_requests_made() - requests_before
    from_cache = api_requests == 0

    logger.info(
        "Rich on-demand ingest complete: %s %s — %d fixtures, %d adapted "
        "(stats live=%d cached=%d, %d API requests)",
        tag, season_id, total_fixtures, len(adapted),
        stats_live, stats_cached, api_requests,
    )

    summary: dict[str, Any] = {
        "comp_id": comp_id,
        "season_id": season_id,
        "tag": tag,
        "display": display or tag,
        "registered": True,
        "total_fixtures": total_fixtures,
        "adapted_matches": len(adapted),
        "stats_live_fetched": stats_live,
        "stats_from_cache": stats_cached,
        "from_cache": from_cache,
        "api_requests": api_requests,
        "fixture_file": str(fixture_file),
        "buildable_fields": buildable,
    }

    if update_manifest:
        _record_rich_on_demand(summary, force_refetch=force_refetch)

    return summary


def _load_env_for_thestats() -> None:
    """Load env vars from /home/ubuntu/.env (lightweight, same as build_corpus).

    THESTATS_API_KEY is what the TheStatsAPI client reads. It may live only in
    the shell environment; setdefault never clobbers an already-exported value.
    """
    sys.path.insert(0, "/home/ubuntu")
    env_path = Path("/home/ubuntu/.env")
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


def _clear_rich_season_cache(prefix: str, season_id: str) -> int:
    """Delete the fixture + stats + paginated-matches cache files for a season.

    Returns the number of files removed. Only touches files scoped to this
    season/prefix so other leagues' caches are untouched.
    """
    removed = 0
    tag = prefix or ""
    patterns = []
    if prefix:
        patterns.append(f"_all_fixtures_{prefix}_{season_id}.json")
        patterns.append(f"{prefix}_matches_{season_id}_p*.json")
        patterns.append(f"{prefix}_stats_*.json")
    else:
        patterns.append(f"_all_fixtures_{season_id}.json")
        patterns.append(f"matches_{season_id}_p*.json")
        patterns.append("stats_*.json")

    # Note: stats files are keyed by match id, not season, so we scope the stats
    # clear to the fixtures actually in THIS season to avoid nuking other seasons
    # of the same league that share the prefix.
    season_match_ids: set[str] = set()
    fx_path = RICH_CORPUS_CACHE_DIR / (
        f"_all_fixtures_{prefix}_{season_id}.json" if prefix
        else f"_all_fixtures_{season_id}.json"
    )
    if fx_path.exists():
        try:
            with open(fx_path) as fh:
                data = json.load(fh)
            season_match_ids = {str(f.get("id")) for f in data.get("fixtures", [])}
        except (json.JSONDecodeError, OSError):
            season_match_ids = set()

    for path in RICH_CORPUS_CACHE_DIR.glob("*"):
        name = path.name
        # fixtures + paginated matches for this season/prefix
        if prefix and (name == f"_all_fixtures_{prefix}_{season_id}.json"
                       or name.startswith(f"{prefix}_matches_{season_id}_p")):
            path.unlink(missing_ok=True)
            removed += 1
            continue
        if not prefix and (name == f"_all_fixtures_{season_id}.json"
                           or name.startswith(f"matches_{season_id}_p")):
            path.unlink(missing_ok=True)
            removed += 1
            continue
        # stats files scoped to this season's match ids only
        if season_match_ids:
            for mid in season_match_ids:
                if name in (f"{prefix}_stats_{mid}.json", f"stats_{mid}.json"):
                    path.unlink(missing_ok=True)
                    removed += 1
                    break
    return removed


# Rich per-side fields surfaced by championship_adapter._rich_fields, plus the
# core adapted fields. Reported as buildable coverage so the caller can see what
# the ingested season actually populates (NULL != ZERO: a None cell is not
# buildable). Mirrors the fields RichCorpusLoader maps into ResearchMatch.
_RICH_CORE_FIELDS = (
    "team_a_yellow_cards", "team_b_yellow_cards",
    "team_a_fouls", "team_b_fouls",
    "team_a_shotsOnTarget", "team_b_shotsOnTarget",
    "team_a_xg", "team_b_xg",
    "homeGoalCount", "awayGoalCount",
)
_RICH_BLOCK_FIELDS = (
    "corner_kicks", "big_chances", "np_expected_goals", "touches_in_penalty_area",
    "shots_inside_box", "shots_outside_box", "blocked_shots", "tackles",
    "interceptions", "clearances", "saves", "high_claims", "goals_prevented",
)


def _rich_buildable_fields(adapted: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-field populated-fraction over the adapted matches (NULL != ZERO).

    Returns a compact dict: {"n": <matches>, "core": {field: frac},
    "rich": {field: frac}}. A field counts as populated for a match when its
    value is non-None (for rich pairs, when the (home, away) pair is present).
    """
    n = len(adapted)
    if n == 0:
        return {"n": 0, "core": {}, "rich": {}}

    core: dict[str, float] = {}
    for field in _RICH_CORE_FIELDS:
        populated = sum(1 for m in adapted if m.get(field) is not None)
        core[field] = round(populated / n, 4)

    rich: dict[str, float] = {}
    for field in _RICH_BLOCK_FIELDS:
        populated = sum(
            1 for m in adapted if (m.get("_rich") or {}).get(field) is not None
        )
        rich[field] = round(populated / n, 4)

    return {"n": n, "core": core, "rich": rich}


def _record_rich_on_demand(summary: dict[str, Any], *, force_refetch: bool) -> None:
    """Append/update a rich on-demand ingest record in the rich manifest.

    Kept in a dedicated manifest (``_on_demand_manifest.json``) in the rich cache
    dir so it never touches the Broad-corpus manifest or the discovery/held-out
    split figures. Purely an audit trail keyed by (tag, season_id).
    """
    manifest: dict[str, Any] = {}
    if RICH_ON_DEMAND_MANIFEST_FILE.exists():
        try:
            with open(RICH_ON_DEMAND_MANIFEST_FILE) as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, OSError):
            manifest = {}

    records: list[dict[str, Any]] = manifest.get("rich_on_demand_seasons", [])
    entry = {
        **summary,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "force_refetch": force_refetch,
    }
    key = (summary["tag"], summary["season_id"])
    records = [
        r for r in records
        if (r.get("tag"), r.get("season_id")) != key
    ]
    records.append(entry)
    manifest["rich_on_demand_seasons"] = records

    RICH_CORPUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(RICH_ON_DEMAND_MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)
