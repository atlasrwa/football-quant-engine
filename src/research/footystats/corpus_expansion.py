"""Deterministic, cache-first FootyStats corpus expansion.

Planning reads only local registry, manifest, inventory, and season-cache files.  The
only path allowed to fetch is explicit execution, which delegates every target to
``src.discovery.corpus.ingest_on_demand_season``.  A league is registered only after
two completed seasons pass the corpus validation gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.research.footystats.league_governance import (
    CorpusState,
    MIN_VALIDATED_SEASON_COMPLETION,
    MIN_VALIDATED_SEASON_MATCHES,
    SCHEMA_VERSION as READINESS_SCHEMA_VERSION,
    build_league_readiness,
)

PLAN_SCHEMA_VERSION = "corpus-expansion-plan/v2"
EXPANSION_REGISTRY_SCHEMA_VERSION = "corpus-expansion-registry/v1"
DEFAULT_REGISTRY = Path("data/discovery/provider_league_registry.json")
DEFAULT_MANIFEST = Path("data/discovery/corpus/manifest.json")
DEFAULT_CACHE_DIR = Path("data/discovery/corpus")
DEFAULT_LEAGUE_INVENTORY = (
    Path.home()
    / ".cache/footystats_research/league-list_{chosen_leagues_only:_true}.json"
)
DEFAULT_EXPANSION_REGISTRY = Path(
    "data/discovery/corpus/expanded_league_seasons.json"
)
_PAGE_RE = re.compile(r"(?:^|,)_?page:_([0-9]+)(?:,|\})")
_SEASON_RE = re.compile(r"(?:^|,)_?season_id:_([0-9]+)(?:,|\})")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def load_json(path: Path | str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _semantic_registry(registry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reviewed_crosswalk_entries": registry.get("reviewed_crosswalk_entries"),
        "leagues": sorted(
            registry.get("leagues", []),
            key=lambda row: str(row.get("footystats", {}).get("name", "")),
        ),
    }


def _semantic_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    leagues = []
    for row in manifest.get("leagues", []):
        leagues.append(
            {
                "league": row.get("league"),
                "seasons": sorted(
                    row.get("seasons", []),
                    key=lambda season: int(season.get("season_id", -1)),
                ),
            }
        )
    return {"leagues": sorted(leagues, key=lambda row: str(row["league"]))}


def _semantic_inventory(inventory: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for row in inventory.get("data", []):
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "name": row.get("name"),
                "season": sorted(
                    (
                        {"id": season.get("id"), "year": season.get("year")}
                        for season in row.get("season", [])
                        if isinstance(season, Mapping)
                    ),
                    key=lambda season: (str(season["year"]), str(season["id"])),
                ),
            }
        )
    return {"data": sorted(rows, key=lambda row: str(row["name"]))}


def _season_cache_pages(
    cache_dir: Path | str, season_id: int
) -> tuple[dict[str, Any], dict[int, tuple[Path, Mapping[str, Any]]]]:
    """Return cache inspection and exact parsed pages for one season ID."""

    cache_dir = Path(cache_dir)
    broad_paths = sorted(
        cache_dir.glob(f"*season_id:_{int(season_id)}*"), key=lambda path: path.name
    )
    paths = []
    for path in broad_paths:
        match = _SEASON_RE.search(path.name)
        if match is not None and int(match.group(1)) == int(season_id):
            paths.append(path)
    if not paths:
        if broad_paths:
            return (
                {
                    "status": "CACHE_KEY_COLLISION",
                    "pages_present": [],
                    "pages_expected": None,
                    "reason": "only prefix-colliding season cache keys were found",
                },
                {},
            )
        return (
            {"status": "CACHE_MISS", "pages_present": [], "pages_expected": None},
            {},
        )

    pages: dict[int, tuple[Path, Mapping[str, Any]]] = {}
    try:
        for path in paths:
            match = _PAGE_RE.search(path.name)
            if match is None:
                continue
            page = int(match.group(1))
            payload = load_json(path)
            if page in pages:
                raise ValueError(f"duplicate cache page {page}")
            pages[page] = (path, payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return (
            {
                "status": "CACHE_INVALID",
                "pages_present": sorted(pages),
                "pages_expected": None,
                "reason": str(exc),
            },
            pages,
        )

    if 1 not in pages:
        return (
            {
                "status": "CACHE_INCOMPLETE",
                "pages_present": sorted(pages),
                "pages_expected": None,
                "reason": "page 1 is absent",
            },
            pages,
        )
    pager = pages[1][1].get("pager", {})
    try:
        expected_count = int(pager.get("max_page", 1))
    except (AttributeError, TypeError, ValueError):
        return (
            {
                "status": "CACHE_INVALID",
                "pages_present": sorted(pages),
                "pages_expected": None,
                "reason": "page 1 pager.max_page is invalid",
            },
            pages,
        )
    if expected_count < 1:
        return (
            {
                "status": "CACHE_INVALID",
                "pages_present": sorted(pages),
                "pages_expected": expected_count,
                "reason": "page 1 pager.max_page must be positive",
            },
            pages,
        )
    expected = set(range(1, expected_count + 1))
    present = set(pages)
    if not expected.issubset(present):
        return (
            {
                "status": "CACHE_INCOMPLETE",
                "pages_present": sorted(present),
                "pages_expected": expected_count,
                "missing_pages": sorted(expected - present),
            },
            pages,
        )
    for page in sorted(expected):
        payload = pages[page][1]
        if not isinstance(payload.get("data", []), list):
            return (
                {
                    "status": "CACHE_INVALID",
                    "pages_present": sorted(present),
                    "pages_expected": expected_count,
                    "reason": f"page {page} data is not a list",
                },
                pages,
            )
        page_pager = payload.get("pager", {})
        if not isinstance(page_pager, Mapping):
            return (
                {
                    "status": "CACHE_INVALID",
                    "pages_present": sorted(present),
                    "pages_expected": expected_count,
                    "reason": f"page {page} pager is not an object",
                },
                pages,
            )
        current_page = page_pager.get("current_page", page)
        try:
            declared_page = int(current_page)
        except (TypeError, ValueError):
            declared_page = -1
        if declared_page != page:
            return (
                {
                    "status": "CACHE_INVALID",
                    "pages_present": sorted(present),
                    "pages_expected": expected_count,
                    "reason": f"page {page} declares current_page={current_page}",
                },
                pages,
            )
    return (
        {
            "status": "CACHE_COMPLETE",
            "pages_present": sorted(present),
            "pages_expected": expected_count,
            "match_records": sum(
                len(pages[page][1].get("data", [])) for page in expected
            ),
        },
        {page: pages[page] for page in sorted(expected)},
    )


def inspect_season_cache(cache_dir: Path | str, season_id: int) -> dict[str, Any]:
    """Verify that every exact page declared by page one exists and parses."""

    inspection, _ = _season_cache_pages(cache_dir, season_id)
    return inspection


def _season_period(value: Any) -> tuple[int, int] | None:
    """Normalize calendar (2025) and split-year (20252026) season values."""

    digits = str(value)
    if not digits.isdigit() or len(digits) not in {4, 8}:
        return None
    start = int(digits[:4])
    end = start if len(digits) == 4 else int(digits[4:])
    if not (1900 <= start <= 2200) or end not in {start, start + 1}:
        return None
    return start, end


def _season_sort_key(season: Mapping[str, Any]) -> tuple[int, int, int]:
    period = _season_period(season.get("year"))
    if period is None:
        raise ValueError(f"invalid FootyStats season year {season.get('year')!r}")
    try:
        season_id = int(season["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("FootyStats season id must be an integer") from exc
    return period[0], period[1], season_id


def _inventory_by_name(inventory: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = inventory.get("data", [])
    if not isinstance(rows, list):
        raise ValueError("FootyStats league inventory data must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("name"), str):
            raise ValueError("every FootyStats inventory row must have a string name")
        name = str(row["name"])
        if name in result:
            raise ValueError(f"duplicate FootyStats inventory league {name!r}")
        result[name] = row
    return result


def _ordered_inventory_seasons(
    row: Mapping[str, Any], league_name: str
) -> list[dict[str, Any]]:
    seasons = row.get("season", [])
    if not isinstance(seasons, list):
        raise ValueError(f"inventory seasons for {league_name!r} must be a list")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for raw in seasons:
        if not isinstance(raw, Mapping):
            raise ValueError(f"invalid inventory season for {league_name!r}")
        sort_key = _season_sort_key(raw)
        season_id = sort_key[2]
        if season_id in seen_ids:
            raise ValueError(
                f"duplicate inventory season_id {season_id} for {league_name!r}"
            )
        seen_ids.add(season_id)
        normalized.append({"id": season_id, "year": str(raw["year"])})
    return sorted(normalized, key=_season_sort_key, reverse=True)


def _validated_season_descriptor(season: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        season_id = int(season["season_id"])
        total = int(season["total_matches"])
        completed = int(season["completed_matches"])
    except (KeyError, TypeError, ValueError):
        return None
    completion = completed / total if total > 0 else 0.0
    if (
        total <= 0
        or completed > total
        or completed < MIN_VALIDATED_SEASON_MATCHES
        or completion < MIN_VALIDATED_SEASON_COMPLETION
    ):
        return None
    year = str(season.get("year", ""))
    if _season_period(year) is None:
        return None
    return {
        "season_id": season_id,
        "year": year,
        "total_matches": total,
        "completed_matches": completed,
        "completion_ratio": round(completion, 6),
    }


def _empty_expansion_registry() -> dict[str, Any]:
    return {
        "schema_version": EXPANSION_REGISTRY_SCHEMA_VERSION,
        "validation_policy": {
            "minimum_seasons": 2,
            "minimum_matches_per_season": MIN_VALIDATED_SEASON_MATCHES,
            "minimum_completion_ratio": MIN_VALIDATED_SEASON_COMPLETION,
        },
        "leagues": {},
    }


def _validate_expansion_registry(registry: Mapping[str, Any]) -> None:
    if registry.get("schema_version") != EXPANSION_REGISTRY_SCHEMA_VERSION:
        raise ValueError("unsupported corpus expansion registry version")
    if not isinstance(registry.get("leagues"), Mapping):
        raise ValueError("expansion registry leagues must be an object keyed by league key")


def _registry_seasons(
    registry: Mapping[str, Any] | None, league_key: str
) -> list[dict[str, Any]]:
    if registry is None:
        return []
    _validate_expansion_registry(registry)
    row = registry["leagues"].get(league_key)
    if row is None:
        return []
    if not isinstance(row, Mapping) or not isinstance(row.get("seasons"), list):
        raise ValueError(f"invalid expansion registry row for {league_key!r}")
    if row.get("league_key") != league_key:
        raise ValueError(f"expansion registry key mismatch for {league_key!r}")
    seasons = []
    seen_ids: set[int] = set()
    for season in row["seasons"]:
        if not isinstance(season, Mapping):
            raise ValueError(f"invalid expansion season for {league_key!r}")
        validated = _validated_season_descriptor(season)
        if validated is None:
            raise ValueError(f"unvalidated expansion season for {league_key!r}")
        season_id = int(validated["season_id"])
        if season_id in seen_ids:
            raise ValueError(
                f"duplicate expansion season_id {season_id} for {league_key!r}"
            )
        seen_ids.add(season_id)
        seasons.append(validated)
    return seasons


def _priority_components(league: Mapping[str, Any]) -> dict[str, Any]:
    capabilities = league["provider_capabilities"]
    mapping_ready = league["mapping_status"] != "BLOCKED"
    representation_complete = league["mapping_status"] == "MATCHED"
    stats_score = sum(
        bool(capabilities[field])
        for field in ("team_stats_available", "player_stats_available", "xg_available")
    )
    current_id = league["footystats"].get("current_season_id")
    current_period = _season_period(league["footystats"].get("current_season_year"))
    return {
        "provider_mapping": mapping_ready,
        "complete_representation": representation_complete,
        "odds_available": bool(capabilities["odds_available"]),
        "stats_capability_count": stats_score,
        "current_season_available": current_id is not None and current_period is not None,
    }


def _latest_two(seasons: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique = {int(season["season_id"]): dict(season) for season in seasons}
    return sorted(
        unique.values(),
        key=lambda season: (
            _season_period(season["year"]) or (0, 0),
            int(season["season_id"]),
        ),
        reverse=True,
    )[:2]


def build_expansion_plan(
    provider_registry: Mapping[str, Any],
    corpus_manifest: Mapping[str, Any],
    league_inventory: Mapping[str, Any] | None = None,
    *,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    expansion_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Plan the exact completed seasons needed to reach two per missing league."""

    if league_inventory is None:
        league_inventory = load_json(DEFAULT_LEAGUE_INVENTORY)
    readiness = build_league_readiness(provider_registry, corpus_manifest)
    inventory_by_name = _inventory_by_name(league_inventory)
    candidates: list[dict[str, Any]] = []

    for league in readiness["leagues"]:
        existing = _latest_two(
            list(league["corpus"]["validated_seasons"])
            + _registry_seasons(expansion_registry, league["key"])
        )
        if len(existing) >= 2:
            continue

        components = _priority_components(league)
        name = league["footystats"]["name"]
        inventory_row = inventory_by_name.get(name)
        ordered_inventory = (
            _ordered_inventory_seasons(inventory_row, name)
            if inventory_row is not None
            else []
        )
        current = ordered_inventory[0] if ordered_inventory else None
        current_id = current["id"] if current is not None else None
        current_year = current["year"] if current is not None else None
        components["current_season_available"] = current is not None
        targets: list[dict[str, Any]] = []
        action = "EXPAND_COMPLETED_SEASONS"
        reason: str | None = None

        if not components["provider_mapping"]:
            action = "BLOCKED_PROVIDER_MAPPING"
            reason = "provider mapping is unavailable"
        elif inventory_row is None:
            action = "BLOCKED_NO_INVENTORY_LEAGUE"
            reason = "league is absent from cached FootyStats inventory"
        elif current is None:
            action = "BLOCKED_NO_CURRENT_SEASON"
            reason = "cached inventory has no parseable current season"
        else:
            existing_ids = {int(season["season_id"]) for season in existing}
            needed = 2 - len(existing)
            selected = [
                season for season in ordered_inventory[1:] if season["id"] not in existing_ids
            ][:needed]
            for season in selected:
                cache = inspect_season_cache(cache_dir, int(season["id"]))
                if cache["status"] == "CACHE_KEY_COLLISION":
                    target_action = "BLOCKED_CACHE_KEY_COLLISION"
                elif cache["status"] == "CACHE_COMPLETE":
                    target_action = "INGEST_FROM_CACHE"
                else:
                    target_action = "FETCH_COMPLETED_SEASON"
                targets.append(
                    {
                        "season_id": season["id"],
                        "season_year": season["year"],
                        "cache": cache,
                        "action": target_action,
                    }
                )
            if len(selected) < needed:
                action = "BLOCKED_INSUFFICIENT_COMPLETED_HISTORY"
                reason = f"only {len(selected)} of {needed} required predecessor seasons exist"
            elif any(
                target["action"] == "BLOCKED_CACHE_KEY_COLLISION"
                for target in targets
            ):
                action = "BLOCKED_TARGET_CACHE_KEY_COLLISION"
                reason = "at least one required target has a cache-key collision"

        candidates.append(
            {
                "league_key": league["key"],
                "league_name": name,
                "corpus_state": league["corpus"]["state"],
                "current_season_id": current_id,
                "current_season_year": current_year,
                "existing_validated_seasons": existing,
                "seasons_needed": 2 - len(existing),
                "priority_components": components,
                "targets": targets,
                "action": action,
                "reason": reason,
            }
        )

    def priority(row: Mapping[str, Any]) -> tuple[Any, ...]:
        value = row["priority_components"]
        return (
            -int(value["provider_mapping"]),
            -int(value["complete_representation"]),
            -int(value["odds_available"]),
            -int(value["stats_capability_count"]),
            -int(value["current_season_available"]),
            str(row["league_key"]),
        )

    candidates.sort(key=priority)
    for rank, candidate in enumerate(candidates, start=1):
        candidate["priority_rank"] = rank

    payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "readiness_schema_version": READINESS_SCHEMA_VERSION,
        "source_fingerprints": {
            "provider_registry": _fingerprint(_semantic_registry(provider_registry)),
            "corpus_manifest": _fingerprint(_semantic_manifest(corpus_manifest)),
            "league_inventory": _fingerprint(_semantic_inventory(league_inventory)),
        },
        "default_mode": "PLAN_ONLY_NO_FETCH",
        "candidate_count": len(candidates),
        "target_count": sum(len(candidate["targets"]) for candidate in candidates),
        "candidates": candidates,
    }
    payload["plan_hash"] = _fingerprint(payload)
    return payload


def _summary_descriptor(
    target: Mapping[str, Any], summary: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        returned_id = int(summary["season_id"])
    except (KeyError, TypeError, ValueError):
        return None, "ingest summary has no valid season_id"
    if returned_id != int(target["season_id"]):
        return None, "ingest summary season_id does not match target"
    candidate = {
        "season_id": returned_id,
        "year": str(target["season_year"]),
        "total_matches": summary.get("total_matches"),
        "completed_matches": summary.get("completed_matches"),
    }
    descriptor = _validated_season_descriptor(candidate)
    if descriptor is None:
        return (
            None,
            f"season requires >= {MIN_VALIDATED_SEASON_MATCHES} completed matches "
            f"and >= {MIN_VALIDATED_SEASON_COMPLETION:.0%} completion",
        )
    return descriptor, None


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def execute_expansion_plan(
    plan: Mapping[str, Any],
    *,
    ingest_season: Callable[..., dict[str, Any]] | None = None,
    expansion_registry_path: Path | str = DEFAULT_EXPANSION_REGISTRY,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Ingest planned targets and register only complete validated two-season sets.

    Raw season pages may be cached during an attempted expansion, but the shared
    corpus manifest is deliberately untouched here.  The expansion registry is
    the sole promoted state and is written only after both requested seasons
    validate, preventing a failed two-season attempt from being represented as
    a partially expanded corpus.
    """

    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ValueError("unsupported corpus expansion plan version")
    if limit is not None and limit < 1:
        raise ValueError("execution limit must be positive")
    if ingest_season is None:
        # Deferred import is intentional: plan-only mode cannot instantiate a client.
        from src.discovery.corpus import ingest_on_demand_season

        ingest_season = ingest_on_demand_season

    registry_path = Path(expansion_registry_path)
    if registry_path.exists():
        registry = load_json(registry_path)
        _validate_expansion_registry(registry)
        registry = json.loads(json.dumps(registry))
    else:
        registry = _empty_expansion_registry()

    actionable: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for candidate in plan.get("candidates", []):
        if candidate.get("action") != "EXPAND_COMPLETED_SEASONS":
            continue
        for target in candidate.get("targets", []):
            if target.get("action") in {"INGEST_FROM_CACHE", "FETCH_COMPLETED_SEASON"}:
                actionable.append((candidate, target))
    if limit is not None:
        actionable = actionable[:limit]

    results: list[dict[str, Any]] = []
    validated_by_league: dict[str, list[dict[str, Any]]] = {}
    executed_ids_by_league: dict[str, set[int]] = {}
    for candidate, target in actionable:
        cache_status = str(target.get("cache", {}).get("status"))
        summary = ingest_season(
            int(target["season_id"]),
            force_refetch=cache_status in {"CACHE_INCOMPLETE", "CACHE_INVALID"},
            update_manifest=False,
        )
        descriptor, rejection_reason = _summary_descriptor(target, summary)
        league_key = str(candidate["league_key"])
        executed_ids_by_league.setdefault(league_key, set()).add(int(target["season_id"]))
        if descriptor is not None:
            validated_by_league.setdefault(league_key, []).append(descriptor)
        results.append(
            {
                "priority_rank": candidate["priority_rank"],
                "league_key": league_key,
                "league_name": candidate["league_name"],
                "season_id": target["season_id"],
                "season_year": target["season_year"],
                "validated": descriptor is not None,
                "rejection_reason": rejection_reason,
                "summary": summary,
                "registered": False,
            }
        )

    for candidate in plan.get("candidates", []):
        league_key = str(candidate.get("league_key", ""))
        if candidate.get("action") != "EXPAND_COMPLETED_SEASONS":
            continue
        required_ids = {int(target["season_id"]) for target in candidate.get("targets", [])}
        if not required_ids.issubset(executed_ids_by_league.get(league_key, set())):
            continue
        successful_ids = {
            int(season["season_id"])
            for season in validated_by_league.get(league_key, [])
        }
        if not required_ids.issubset(successful_ids):
            continue
        combined = _latest_two(
            list(candidate.get("existing_validated_seasons", []))
            + validated_by_league.get(league_key, [])
        )
        if len(combined) < 2:
            continue
        registry["leagues"][league_key] = {
            "league_key": league_key,
            "league_name": candidate["league_name"],
            "seasons": combined,
        }
        for result in results:
            if result["league_key"] == league_key:
                result["registered"] = True

    registry["leagues"] = {
        key: registry["leagues"][key] for key in sorted(registry["leagues"])
    }
    _atomic_write_json(registry_path, registry)
    return results


def load_expanded_league_names(
    registry_path: Path | str = DEFAULT_EXPANSION_REGISTRY,
) -> tuple[str, ...]:
    """Return stable reporting names from the cache-only expansion registry."""

    path = Path(registry_path)
    if not path.exists():
        return ()
    registry = load_json(path)
    _validate_expansion_registry(registry)
    names = []
    for key, row in sorted(registry["leagues"].items()):
        if not isinstance(row, Mapping) or not isinstance(row.get("league_name"), str):
            raise ValueError(f"invalid expansion registry league {key!r}")
        if len(_registry_seasons(registry, str(key))) < 2:
            raise ValueError(f"expanded league {key!r} has fewer than two seasons")
        name = str(row["league_name"])
        if name in names:
            raise ValueError(f"duplicate expansion registry league name {name!r}")
        names.append(name)
    return tuple(names)


def load_expanded_completed_matches(
    registry_path: Path | str = DEFAULT_EXPANSION_REGISTRY,
    *,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
) -> list[dict[str, Any]]:
    """Load, deduplicate, and annotate exact registered cache pages without APIs."""

    path = Path(registry_path)
    if not path.exists():
        return []
    registry = load_json(path)
    _validate_expansion_registry(registry)
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()

    for league_key, row in sorted(registry["leagues"].items()):
        if not isinstance(row, Mapping) or not isinstance(row.get("league_name"), str):
            raise ValueError(f"invalid expansion registry league {league_key!r}")
        league_name = str(row["league_name"])
        seasons = _registry_seasons(registry, str(league_key))
        if len(seasons) < 2:
            raise ValueError(f"expanded league {league_key!r} has fewer than two seasons")
        for season in sorted(
            seasons,
            key=lambda value: (
                _season_period(value["year"]) or (0, 0),
                int(value["season_id"]),
            ),
            reverse=True,
        ):
            inspection, pages = _season_cache_pages(cache_dir, int(season["season_id"]))
            if inspection["status"] != "CACHE_COMPLETE":
                raise ValueError(
                    f"registered season {season['season_id']} cache is "
                    f"{inspection['status']}"
                )
            raw_records: list[Mapping[str, Any]] = []
            for page in sorted(pages):
                for raw_match in pages[page][1].get("data", []):
                    if not isinstance(raw_match, Mapping):
                        raise ValueError(
                            f"season {season['season_id']} page {page} contains a non-object match"
                        )
                    raw_records.append(raw_match)
            completed_records = [
                raw_match
                for raw_match in raw_records
                if str(raw_match.get("status", "")).casefold() == "complete"
            ]
            observed = {
                "season_id": season["season_id"],
                "year": season["year"],
                "total_matches": len(raw_records),
                "completed_matches": len(completed_records),
            }
            if (
                len(raw_records) != int(season["total_matches"])
                or len(completed_records) != int(season["completed_matches"])
            ):
                raise ValueError(
                    f"registered season {season['season_id']} cache counts do not match registry"
                )
            if _validated_season_descriptor(observed) is None:
                raise ValueError(
                    f"registered season {season['season_id']} cache no longer passes validation"
                )
            for raw_match in completed_records:
                fixture_id = raw_match.get("id", raw_match.get("match_id"))
                identity = (
                    f"id:{fixture_id}"
                    if fixture_id is not None
                    else "payload:" + _fingerprint(raw_match)
                )
                if identity in seen:
                    continue
                seen.add(identity)
                match = dict(raw_match)
                match["_league"] = league_name
                match["_season"] = str(season["year"])
                matches.append(match)
    return matches


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_LEAGUE_INVENTORY)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--expansion-registry", type=Path, default=DEFAULT_EXPANSION_REGISTRY
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="explicitly execute targets; cache misses may fetch through existing ingest code",
    )
    parser.add_argument("--limit", type=int, help="maximum prioritized season targets to execute")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = load_json(args.registry)
    manifest = load_json(args.manifest)
    inventory = load_json(args.inventory)
    expanded = (
        load_json(args.expansion_registry) if args.expansion_registry.exists() else None
    )
    plan = build_expansion_plan(
        registry,
        manifest,
        inventory,
        cache_dir=args.cache_dir,
        expansion_registry=expanded,
    )
    output: dict[str, Any] = dict(plan)
    if args.execute:
        output["execution"] = execute_expansion_plan(
            plan,
            expansion_registry_path=args.expansion_registry,
            limit=args.limit,
        )
    print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
