"""Versioned, fail-closed governance metadata for reviewed football leagues.

Provider inventory describes availability, not statistical eligibility.  This module
is the canonical identity and readiness projection for the 49 manually reviewed
FootyStats leagues.  Mutable provider/corpus files are inputs; policy and stable keys
are versioned here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "league-readiness/v1"
POLICY_VERSION = "senior-quant-readiness/v1"
EXPECTED_REVIEWED_LEAGUES = 49
MIN_VALIDATED_SEASON_MATCHES = 100
MIN_VALIDATED_SEASON_COMPLETION = 0.95


class LeagueTier(StrEnum):
    """Production tier.  V1 intentionally has no permissive value."""

    UNKNOWN = "UNKNOWN"


class CorpusState(StrEnum):
    VALIDATED = "VALIDATED"
    HIERARCHICAL_RESEARCH = "HIERARCHICAL_RESEARCH"
    BLOCKED = "BLOCKED"


class SpatialCapability(StrEnum):
    BLOCKED_UNAVAILABLE = "BLOCKED_UNAVAILABLE"
    BLOCKED_UNVERIFIED_ORIENTATION = "BLOCKED_UNVERIFIED_ORIENTATION"
    CERTIFIED = "CERTIFIED"


@dataclass(frozen=True, slots=True)
class ReviewedLeague:
    key: str
    footystats_name: str


# Keys are permanent external identifiers.  Rename provider display names only by
# adding an alias in a later schema version; never recycle a key.
REVIEWED_LEAGUES: tuple[ReviewedLeague, ...] = tuple(
    ReviewedLeague(key, name)
    for key, name in (
        ("usa_mls", "USA MLS"),
        ("scotland_premiership", "Scotland Premiership"),
        ("germany_bundesliga", "Germany Bundesliga"),
        ("england_premier_league", "England Premier League"),
        ("portugal_liga_nos", "Portugal Liga NOS"),
        ("turkey_super_lig", "Turkey Süper Lig"),
        ("england_championship", "England Championship"),
        ("england_efl_league_one", "England EFL League One"),
        ("england_efl_league_two", "England EFL League Two"),
        ("spain_la_liga", "Spain La Liga"),
        ("spain_segunda_division", "Spain Segunda División"),
        ("norway_eliteserien", "Norway Eliteserien"),
        ("netherlands_eredivisie", "Netherlands Eredivisie"),
        ("finland_veikkausliiga", "Finland Veikkausliiga"),
        ("france_ligue_1", "France Ligue 1"),
        ("italy_serie_a", "Italy Serie A"),
        ("france_ligue_2", "France Ligue 2"),
        ("italy_serie_b", "Italy Serie B"),
        ("belgium_pro_league", "Belgium Pro League"),
        ("germany_2_bundesliga", "Germany 2. Bundesliga"),
        ("austria_bundesliga", "Austria Bundesliga"),
        ("austria_2_liga", "Austria 2. Liga"),
        ("australia_a_league", "Australia A-League"),
        ("brazil_serie_a", "Brazil Serie A"),
        ("sweden_allsvenskan", "Sweden Allsvenskan"),
        ("argentina_primera_division", "Argentina Primera División"),
        ("poland_1_liga", "Poland 1. Liga"),
        ("switzerland_super_league", "Switzerland Super League"),
        ("japan_j1_league", "Japan J1 League"),
        ("greece_super_league", "Greece Super League"),
        ("poland_ekstraklasa", "Poland Ekstraklasa"),
        ("mexico_liga_mx", "Mexico Liga MX"),
        ("norway_first_division", "Norway First Division"),
        ("croatia_prva_hnl", "Croatia Prva HNL"),
        ("serbia_superliga", "Serbia SuperLiga"),
        ("slovenia_prvaliga", "Slovenia PrvaLiga"),
        ("slovakia_super_liga", "Slovakia Super Liga"),
        (
            "republic_of_ireland_premier_division",
            "Republic of Ireland Premier Division",
        ),
        ("colombia_categoria_primera_a", "Colombia Categoria Primera A"),
        ("israel_premier_league", "Israel Israeli Premier League"),
        ("czech_republic_first_league", "Czech Republic First League"),
        ("denmark_superliga", "Denmark Superliga"),
        ("belgium_first_division_b", "Belgium First Division B"),
        ("bulgaria_first_league", "Bulgaria First League"),
        ("cyprus_first_division", "Cyprus First Division"),
        ("hungary_nb_i", "Hungary NB I"),
        ("iceland_urvalsdeild", "Iceland Úrvalsdeild"),
        ("saudi_arabia_professional_league", "Saudi Arabia Professional League"),
        ("romania_liga_i", "Romania Liga I"),
    )
)

LEAGUE_BY_NAME = {league.footystats_name: league for league in REVIEWED_LEAGUES}
LEAGUE_BY_KEY = {league.key: league for league in REVIEWED_LEAGUES}

if len(REVIEWED_LEAGUES) != EXPECTED_REVIEWED_LEAGUES:
    raise RuntimeError("canonical reviewed league set must contain exactly 49 leagues")
if len(LEAGUE_BY_NAME) != len(REVIEWED_LEAGUES) or len(LEAGUE_BY_KEY) != len(
    REVIEWED_LEAGUES
):
    raise RuntimeError("canonical league names and keys must be unique")


def _manifest_by_league(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = manifest.get("leagues", [])
    if not isinstance(rows, list):
        raise ValueError("corpus manifest leagues must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("league"), str):
            raise ValueError("every corpus league row must have a string league name")
        name = row["league"]
        if name in result:
            raise ValueError(f"duplicate corpus league {name!r}")
        result[name] = row
    return result


def _validated_corpus_seasons(row: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if row is None:
        return []
    seasons = row.get("seasons", [])
    if not isinstance(seasons, list):
        raise ValueError("corpus seasons must be a list")
    valid: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for season in seasons:
        if not isinstance(season, Mapping):
            continue
        season_id = season.get("season_id")
        completed = season.get("completed_matches", 0)
        total = season.get("total_matches", 0)
        if not all(isinstance(value, int) for value in (season_id, completed, total)):
            continue
        if season_id in seen_ids:
            raise ValueError(f"duplicate corpus season_id {season_id}")
        seen_ids.add(season_id)
        completion = completed / total if total > 0 else 0.0
        if (
            total >= MIN_VALIDATED_SEASON_MATCHES
            and completion >= MIN_VALIDATED_SEASON_COMPLETION
        ):
            valid.append(
                {
                    "season_id": season_id,
                    "year": str(season.get("year", "")),
                    "total_matches": total,
                    "completed_matches": completed,
                    "completion_ratio": round(completion, 6),
                }
            )
    return sorted(valid, key=lambda item: (item["year"], item["season_id"]))


def _provider_capabilities(row: Mapping[str, Any]) -> dict[str, Any]:
    provider = row.get("thestatsapi", {})
    competitions = provider.get("competitions", []) if isinstance(provider, Mapping) else []
    if not isinstance(competitions, list):
        raise ValueError("thestatsapi competitions must be a list")

    def any_capability(field: str) -> bool:
        return any(isinstance(comp, Mapping) and comp.get(field) is True for comp in competitions)

    return {
        "competition_ids": sorted(
            str(value)
            for value in (provider.get("competition_ids", []) if isinstance(provider, Mapping) else [])
        ),
        "odds_available": any_capability("odds_available"),
        "live_odds_available": any_capability("live_odds_available"),
        "team_stats_available": any_capability("has_team_stats"),
        "player_stats_available": any_capability("has_player_stats"),
        "xg_available": any_capability("xg_available"),
    }


def build_league_readiness(
    provider_registry: Mapping[str, Any],
    corpus_manifest: Mapping[str, Any],
    *,
    certified_player_profile_orientation: Iterable[str] = (),
) -> dict[str, Any]:
    """Build the canonical v1 readiness projection.

    ``certified_player_profile_orientation`` contains stable league keys backed by
    an external orientation certification.  Absence always blocks player-season
    spatial profiles.  Match-level spatial data is unavailable in the reviewed
    provider contract and cannot be overridden in v1.
    """

    registry_rows = provider_registry.get("leagues", [])
    if not isinstance(registry_rows, list):
        raise ValueError("provider registry leagues must be a list")
    by_name: dict[str, Mapping[str, Any]] = {}
    for row in registry_rows:
        footystats = row.get("footystats", {}) if isinstance(row, Mapping) else {}
        name = footystats.get("name") if isinstance(footystats, Mapping) else None
        if not isinstance(name, str):
            raise ValueError("every provider row must have footystats.name")
        if name in by_name:
            raise ValueError(f"duplicate provider league {name!r}")
        by_name[name] = row

    expected = set(LEAGUE_BY_NAME)
    actual = set(by_name)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"reviewed league identity drift: missing={missing}, extra={extra}")
    if provider_registry.get("reviewed_crosswalk_entries") not in (None, 49):
        raise ValueError("provider registry reviewed_crosswalk_entries must equal 49")

    manifest = _manifest_by_league(corpus_manifest)
    certifications = set(certified_player_profile_orientation)
    unknown_certifications = certifications - set(LEAGUE_BY_KEY)
    if unknown_certifications:
        raise ValueError(f"unknown spatial certification keys: {sorted(unknown_certifications)}")

    output: list[dict[str, Any]] = []
    for identity in sorted(REVIEWED_LEAGUES, key=lambda item: item.key):
        source = by_name[identity.footystats_name]
        footystats = source["footystats"]
        mapping_status = str(source.get("mapping_status", "BLOCKED"))
        seasons = _validated_corpus_seasons(manifest.get(identity.footystats_name))
        if mapping_status == "BLOCKED":
            corpus_state = CorpusState.BLOCKED
            reasons = ["provider_mapping_unavailable"]
        elif len(seasons) >= 2:
            corpus_state = CorpusState.VALIDATED
            reasons = ["two_or_more_completed_corpus_seasons"]
        else:
            corpus_state = CorpusState.HIERARCHICAL_RESEARCH
            reasons = ["fewer_than_two_completed_corpus_seasons"]

        player_status = (
            SpatialCapability.CERTIFIED
            if identity.key in certifications
            else SpatialCapability.BLOCKED_UNVERIFIED_ORIENTATION
        )
        output.append(
            {
                "key": identity.key,
                "footystats": {
                    "name": identity.footystats_name,
                    "country": str(footystats.get("country", "")),
                    "current_season_id": footystats.get("current_season_id"),
                    "current_season_year": footystats.get("current_season_year"),
                },
                "tier": LeagueTier.UNKNOWN.value,
                "production_enabled": False,
                "mapping_status": mapping_status,
                "representation_note": source.get("representation_note"),
                "provider_capabilities": _provider_capabilities(source),
                "corpus": {
                    "state": corpus_state.value,
                    "reasons": reasons,
                    "validated_seasons": seasons,
                },
                "spatial": {
                    "match_level_endpoints": {
                        "status": SpatialCapability.BLOCKED_UNAVAILABLE.value,
                        "reason": "reviewed providers expose no certified match-level spatial endpoint",
                    },
                    "player_season_profiles": {
                        "status": player_status.value,
                        "reason": (
                            "orientation certification supplied"
                            if player_status is SpatialCapability.CERTIFIED
                            else "provider x/y orientation is not certified stable across teams and seasons"
                        ),
                    },
                },
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "reviewed_league_count": EXPECTED_REVIEWED_LEAGUES,
        "fail_closed_policy": (
            "All leagues remain tier UNKNOWN and production-disabled until a later "
            "version records league-market backtests, calibration, and attested forward evidence."
        ),
        "corpus_validation_policy": {
            "minimum_seasons": 2,
            "minimum_matches_per_season": MIN_VALIDATED_SEASON_MATCHES,
            "minimum_completion_ratio": MIN_VALIDATED_SEASON_COMPLETION,
        },
        "leagues": output,
    }
