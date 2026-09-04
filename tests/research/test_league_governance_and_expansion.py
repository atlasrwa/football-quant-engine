import copy
import json
from pathlib import Path

import pytest

from src.research.footystats.corpus_expansion import (
    EXPANSION_REGISTRY_SCHEMA_VERSION,
    build_expansion_plan,
    execute_expansion_plan,
    inspect_season_cache,
    load_expanded_completed_matches,
    load_expanded_league_names,
)
from src.research.footystats.league_governance import (
    CorpusState,
    EXPECTED_REVIEWED_LEAGUES,
    LeagueTier,
    SpatialCapability,
    build_league_readiness,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data/discovery/provider_league_registry.json"
MANIFEST = ROOT / "data/discovery/corpus/manifest.json"


def _load(path: Path):
    return json.loads(path.read_text())


def _previous_years(current_year: object) -> tuple[str, str]:
    value = str(current_year)
    if len(value) == 4:
        year = int(value)
        return str(year - 1), str(year - 2)
    start = int(value[:4])
    return f"{start - 1}{start}", f"{start - 2}{start - 1}"


def _inventory(registry: dict | None = None) -> dict:
    registry = registry or _load(REGISTRY)
    rows = []
    for index, row in enumerate(registry["leagues"], start=1):
        current = dict(row["footystats"])
        if current["name"] == "Argentina Primera División":
            # The checked-in provider registry is intentionally stale for this league;
            # the cached inventory is the source of truth for current/predecessor order.
            current["current_season_id"] = 900_000 + index
            current["current_season_year"] = 2026
        latest, older = _previous_years(current["current_season_year"])
        rows.append(
            {
                "name": current["name"],
                "country": current["country"],
                "season": [
                    {"id": 200_000 + index * 10 + 2, "year": older},
                    {"id": current["current_season_id"], "year": current["current_season_year"]},
                    {"id": 200_000 + index * 10 + 1, "year": latest},
                ],
            }
        )
    return {"data": rows}


def test_canonical_readiness_covers_all_49_and_fails_closed():
    readiness = build_league_readiness(_load(REGISTRY), _load(MANIFEST))
    assert readiness["reviewed_league_count"] == EXPECTED_REVIEWED_LEAGUES == 49
    assert len(readiness["leagues"]) == 49
    assert len({row["key"] for row in readiness["leagues"]}) == 49
    assert {row["tier"] for row in readiness["leagues"]} == {LeagueTier.UNKNOWN.value}
    assert not any(row["production_enabled"] for row in readiness["leagues"])

    state_counts = {
        state: sum(row["corpus"]["state"] == state for row in readiness["leagues"])
        for state in CorpusState
    }
    assert state_counts == {
        CorpusState.VALIDATED: 25,
        CorpusState.HIERARCHICAL_RESEARCH: 23,
        CorpusState.BLOCKED: 1,
    }
    for row in readiness["leagues"]:
        assert row["spatial"]["match_level_endpoints"]["status"] == (
            SpatialCapability.BLOCKED_UNAVAILABLE.value
        )
        assert row["spatial"]["player_season_profiles"]["status"] == (
            SpatialCapability.BLOCKED_UNVERIFIED_ORIENTATION.value
        )


def test_player_profile_requires_explicit_orientation_certification():
    readiness = build_league_readiness(
        _load(REGISTRY),
        _load(MANIFEST),
        certified_player_profile_orientation={"spain_la_liga"},
    )
    by_key = {row["key"]: row for row in readiness["leagues"]}
    assert by_key["spain_la_liga"]["spatial"]["player_season_profiles"]["status"] == (
        SpatialCapability.CERTIFIED.value
    )
    assert by_key["spain_la_liga"]["spatial"]["match_level_endpoints"]["status"] == (
        SpatialCapability.BLOCKED_UNAVAILABLE.value
    )


def _cache_page(
    path: Path,
    season_id: int,
    page: int,
    max_page: int,
    data: list[dict] | None = None,
) -> None:
    filename = (
        f"league-matches_{{max_per_page:_300,_page:_{page},"
        f"_season_id:_{season_id}}}.json"
    )
    (path / filename).write_text(
        json.dumps(
            {
                "data": data if data is not None else [{"id": f"{season_id}-{page}"}],
                "pager": {"current_page": page, "max_page": max_page},
            }
        )
    )


def test_cache_inspection_requires_every_declared_page(tmp_path):
    assert inspect_season_cache(tmp_path, 123)["status"] == "CACHE_MISS"
    _cache_page(tmp_path, 123, 1, 2)
    incomplete = inspect_season_cache(tmp_path, 123)
    assert incomplete["status"] == "CACHE_INCOMPLETE"
    assert incomplete["missing_pages"] == [2]
    _cache_page(tmp_path, 123, 2, 2)
    complete = inspect_season_cache(tmp_path, 123)
    assert complete["status"] == "CACHE_COMPLETE"
    assert complete["match_records"] == 2


def test_plan_selects_two_latest_predecessors_for_calendar_and_split_years(tmp_path):
    registry = _load(REGISTRY)
    manifest = _load(MANIFEST)
    inventory = _inventory(registry)
    first = build_expansion_plan(registry, manifest, inventory, cache_dir=tmp_path)

    shuffled_registry = copy.deepcopy(registry)
    shuffled_registry["leagues"].reverse()
    shuffled_manifest = copy.deepcopy(manifest)
    shuffled_manifest["leagues"].reverse()
    shuffled_inventory = copy.deepcopy(inventory)
    shuffled_inventory["data"].reverse()
    for row in shuffled_inventory["data"]:
        row["season"].reverse()
    second = build_expansion_plan(
        shuffled_registry, shuffled_manifest, shuffled_inventory, cache_dir=tmp_path
    )

    assert first == second
    assert first["candidate_count"] == 24
    assert first["target_count"] == 46
    assert first["candidates"][-1]["league_key"] == "poland_1_liga"
    assert first["candidates"][-1]["action"] == "BLOCKED_PROVIDER_MAPPING"
    assert all(
        row["priority_rank"] == index
        for index, row in enumerate(first["candidates"], 1)
    )

    efl = next(
        row for row in first["candidates"] if row["league_key"] == "england_efl_league_one"
    )
    assert [target["season_year"] for target in efl["targets"]] == [
        "20252026",
        "20242025",
    ]
    assert efl["current_season_id"] not in {
        target["season_id"] for target in efl["targets"]
    }

    argentina = next(
        row for row in first["candidates"] if row["league_key"] == "argentina_primera_division"
    )
    assert [target["season_year"] for target in argentina["targets"]] == ["2025", "2024"]
    assert "league_inventory" in first["source_fingerprints"]


def test_execution_is_explicit_validates_both_targets_and_registers_atomically(tmp_path):
    plan = build_expansion_plan(
        _load(REGISTRY), _load(MANIFEST), _inventory(), cache_dir=tmp_path
    )
    calls = []

    def ingest(season_id, *, force_refetch, update_manifest):
        calls.append((season_id, force_refetch, update_manifest))
        return {
            "season_id": season_id,
            "total_matches": 110,
            "completed_matches": 105,
            "from_cache": False,
        }

    registry_path = tmp_path / "expanded.json"
    assert calls == []
    results = execute_expansion_plan(
        plan,
        ingest_season=ingest,
        expansion_registry_path=registry_path,
        limit=2,
    )
    assert len(results) == 2
    assert calls == [
        (results[0]["season_id"], False, False),
        (results[1]["season_id"], False, False),
    ]
    assert all(result["validated"] and result["registered"] for result in results)
    persisted = _load(registry_path)
    assert persisted["schema_version"] == EXPANSION_REGISTRY_SCHEMA_VERSION
    entry = persisted["leagues"][results[0]["league_key"]]
    assert entry["league_name"] == results[0]["league_name"]
    assert [season["season_id"] for season in entry["seasons"]] == [
        result["season_id"] for result in results
    ]
    assert not list(tmp_path.glob("*.tmp"))


def test_execution_does_not_register_partial_or_underfilled_seasons(tmp_path):
    plan = build_expansion_plan(
        _load(REGISTRY), _load(MANIFEST), _inventory(), cache_dir=tmp_path
    )

    def ingest(season_id, *, force_refetch, update_manifest):
        completed = 99 if len(calls) == 0 else 100
        calls.append(season_id)
        return {
            "season_id": season_id,
            "total_matches": 105,
            "completed_matches": completed,
        }

    calls: list[int] = []
    registry_path = tmp_path / "expanded.json"
    results = execute_expansion_plan(
        plan,
        ingest_season=ingest,
        expansion_registry_path=registry_path,
        limit=2,
    )
    assert [result["validated"] for result in results] == [False, True]
    assert not any(result["registered"] for result in results)
    assert _load(registry_path)["leagues"] == {}


def test_partial_seasons_do_not_pass_validated_corpus_gate():
    registry = _load(REGISTRY)
    manifest = _load(MANIFEST)
    target = next(row for row in manifest["leagues"] if row["league"] == "USA MLS")
    for season in target["seasons"]:
        season["completed_matches"] = 1
    readiness = build_league_readiness(registry, manifest)
    usa = next(row for row in readiness["leagues"] if row["key"] == "usa_mls")
    assert usa["corpus"]["state"] == CorpusState.HIERARCHICAL_RESEARCH.value


def test_cache_inspection_rejects_season_id_prefix_collision(tmp_path):
    _cache_page(tmp_path, 1234, 1, 1)
    result = inspect_season_cache(tmp_path, 123)
    assert result["status"] == "CACHE_KEY_COLLISION"


def test_execution_repairs_incomplete_target_cache_with_force_refetch(tmp_path):
    initial = build_expansion_plan(
        _load(REGISTRY), _load(MANIFEST), _inventory(), cache_dir=tmp_path
    )
    candidate = next(row for row in initial["candidates"] if row["targets"])
    season_id = candidate["targets"][0]["season_id"]
    _cache_page(tmp_path, season_id, 1, 2)
    plan = build_expansion_plan(
        _load(REGISTRY), _load(MANIFEST), _inventory(), cache_dir=tmp_path
    )
    candidate = next(
        row for row in plan["candidates"] if row["league_key"] == candidate["league_key"]
    )
    assert candidate["targets"][0]["cache"]["status"] == "CACHE_INCOMPLETE"
    calls = []

    def ingest(target_id, *, force_refetch, update_manifest):
        calls.append((target_id, force_refetch, update_manifest))
        return {"season_id": target_id, "total_matches": 100, "completed_matches": 100}

    one_target_plan = copy.deepcopy(plan)
    one_target_plan["candidates"] = [candidate]
    one_target_plan["candidates"][0]["targets"] = [candidate["targets"][0]]
    execute_expansion_plan(
        one_target_plan,
        ingest_season=ingest,
        expansion_registry_path=tmp_path / "expanded.json",
    )
    assert calls == [(season_id, True, False)]


def _expanded_registry_payload() -> dict:
    return {
        "schema_version": EXPANSION_REGISTRY_SCHEMA_VERSION,
        "validation_policy": {
            "minimum_seasons": 2,
            "minimum_matches_per_season": 100,
            "minimum_completion_ratio": 0.95,
        },
        "leagues": {
            "example_league": {
                "league_key": "example_league",
                "league_name": "Example League",
                "seasons": [
                    {
                        "season_id": 101,
                        "year": "20252026",
                        "total_matches": 105,
                        "completed_matches": 101,
                        "completion_ratio": round(101 / 105, 6),
                    },
                    {
                        "season_id": 100,
                        "year": "20242025",
                        "total_matches": 100,
                        "completed_matches": 100,
                        "completion_ratio": 1.0,
                    },
                ],
            }
        },
    }


def test_cache_only_loader_reads_exact_pages_deduplicates_and_annotates(tmp_path):
    registry_path = tmp_path / "expanded.json"
    registry_path.write_text(json.dumps(_expanded_registry_payload()))
    newer = [{"id": "same", "status": "complete"}] + [
        {"id": f"newer-{index}", "status": "complete"} for index in range(99)
    ]
    scheduled = [
        {"id": f"future-{index}", "status": "scheduled"} for index in range(4)
    ]
    older = [
        {"id": f"older-{index}", "status": "complete"} for index in range(100)
    ]
    _cache_page(tmp_path, 101, 1, 2, newer + scheduled)
    _cache_page(tmp_path, 101, 2, 2, [{"id": "same", "status": "complete"}])
    _cache_page(tmp_path, 100, 1, 1, older)

    matches = load_expanded_completed_matches(registry_path, cache_dir=tmp_path)
    assert len(matches) == 200
    assert matches[0]["id"] == "same"
    assert len({match["id"] for match in matches}) == 200
    assert not any(str(match["id"]).startswith("future-") for match in matches)
    assert {match["_league"] for match in matches} == {"Example League"}
    assert {match["_season"] for match in matches} == {"20252026", "20242025"}
    assert load_expanded_league_names(registry_path) == ("Example League",)


def test_cache_only_loader_rejects_duplicate_season_descriptors(tmp_path):
    payload = _expanded_registry_payload()
    seasons = payload["leagues"]["example_league"]["seasons"]
    seasons[1] = copy.deepcopy(seasons[0])
    registry_path = tmp_path / "expanded.json"
    registry_path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="duplicate expansion season_id"):
        load_expanded_completed_matches(registry_path, cache_dir=tmp_path)


def test_cache_only_loader_rejects_cache_count_drift(tmp_path):
    registry_path = tmp_path / "expanded.json"
    registry_path.write_text(json.dumps(_expanded_registry_payload()))
    _cache_page(tmp_path, 101, 1, 1, [{"id": "newer", "status": "complete"}])
    _cache_page(tmp_path, 100, 1, 1, [{"id": "older", "status": "complete"}])

    with pytest.raises(ValueError, match="cache counts do not match registry"):
        load_expanded_completed_matches(registry_path, cache_dir=tmp_path)
