"""Shared synthetic-registry builders for the dual-provider scope tests.

Every fixture here is a deterministic JSON artifact in a tmp dir. No provider
access, no runtime data, and no dependency on the live registry — so these tests
assert the *rule*, not the current state of the world.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Sequence

#: Three representative competitions OUTSIDE the historical Pilot-C four
#: (comp_3039 EPL / comp_8321 Championship / comp_9777 Ligue 2 / comp_0976 La Liga 2).
#: Used throughout to prove eligibility does not depend on Pilot-C membership.
NON_PILOT_C = (
    ("Germany Bundesliga", "comp_5840", "Germany"),
    ("USA MLS", "comp_9799", "USA"),
    ("Netherlands Eredivisie", "comp_4795", "Netherlands"),
    ("Portugal Liga NOS", "comp_5450", "Portugal"),
)

#: The four Pilot-C competition ids, for tests that need to name them.
PILOT_C_COMP_IDS = ("comp_3039", "comp_8321", "comto_9777", "comp_0976")


def league_entry(
    *,
    name: str,
    comp_ids: Sequence[str],
    country: str = "Nowhere",
    footystats_season_id: Optional[int] = 10_001,
    mapping_status: str = "MATCHED",
    model_status: str = "RESEARCH_ONLY_NOT_VALIDATED",
    complete_seasons: int = 2,
    odds_available: bool = True,
    representation_note: Optional[str] = None,
    competitions: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """One provider-registry league row.

    Mirrors the shape written by ``scripts/sync_provider_leagues.py`` so the tests
    exercise the real ``build_crosswalk`` -> identity-registry -> scope path rather
    than a simplified stand-in.
    """
    comps = competitions
    if comps is None:
        comps = [
            {
                "id": cid,
                "name": f"{name} ({cid})",
                "country": country,
                "odds_available": odds_available,
                "live_odds_available": False,
                "xg_available": True,
                "has_team_stats": True,
                "has_player_stats": True,
            }
            for cid in comp_ids
        ]
    return {
        "footystats": {
            "name": name,
            "country": country,
            "current_season_id": footystats_season_id,
            "current_season_year": 2026,
        },
        "thestatsapi": {
            "competition_ids": list(comp_ids),
            "competitions": comps,
        },
        "mapping_status": mapping_status,
        "representation_note": representation_note,
        "corpus": {"complete_seasons": complete_seasons, "completed_matches": 700},
        "model_status": model_status,
        "production_enabled": False,
    }


def write_registry(path: Path, leagues: Sequence[dict[str, Any]]) -> Path:
    """Write a synthetic provider registry with unique FootyStats season ids.

    Season ids must be distinct or the canonical identity registry would be asked
    to link one FootyStats competition to several TheStatsAPI ones, which is a
    conflict rather than the state under test.
    """
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(leagues):
        row = json.loads(json.dumps(entry))  # deep copy
        if row["footystats"].get("current_season_id") is not None:
            row["footystats"]["current_season_id"] = 20_000 + index
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-09-11T00:00:00+00:00",
                "policy": "synthetic test registry",
                "leagues": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def write_coverage_matrix(
    path: Path,
    rows: Sequence[dict[str, Any]],
) -> Path:
    """Write a synthetic coverage matrix (the market-evidence artifact)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"summary": {"total": len(rows)}, "recon": {}, "rows": list(rows)}, indent=2),
        encoding="utf-8",
    )
    return path


def coverage_row(
    *,
    comp_id: str,
    canonical_name: str,
    market_eligibility: dict[str, str],
    identity_status: str = "VERIFIED",
    capture_classification: str = "CAPTURE_PARTIAL",
    capture_priority: int = 3,
    country: str = "Nowhere",
) -> dict[str, Any]:
    """One coverage-matrix row supplying per-market evidence."""
    return {
        "canonical_competition_id": f"canon_{comp_id}",
        "canonical_name": canonical_name,
        "country": country,
        "footystats_id": None,
        "footystats_name": canonical_name,
        "thestatsapi_competition_id": comp_id,
        "thestatsapi_name": canonical_name,
        "identity_status": identity_status,
        "verification_method": "level_a_registry_matched_single_id",
        "odds_available": True,
        "xg_available": True,
        "has_team_stats": True,
        "has_player_stats": True,
        "evidence": {},
        "thestatsapi_season_id": f"season_{comp_id}",
        "capture_classification": capture_classification,
        "capture_priority": capture_priority,
        "market_eligibility": dict(market_eligibility),
        "reason": "synthetic test row",
    }


ALL_READY = {
    "total_goals": "READY",
    "match_corners": "READY",
    "total_cards": "READY",
    "match_shots_on_target": "READY",
}



def executable_symbols(module) -> set[str]:
    """Every name a module actually references in executable code.

    Docstrings and comments are excluded. Substring scans over raw source cannot
    be used for these assertions, because the modules under test legitimately
    *document* the boundaries they must not cross — naming
    ``can_publish_validated_signals`` in a docstring to say "this is never read"
    is exactly the documentation we want, and a text scan would forbid it.

    Returns:
        Imported module/alias names, attribute names, and bare identifiers.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
                names.update(alias.name.split("."))
                if alias.asname:
                    names.add(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
                names.update(node.module.split("."))
            for alias in node.names:
                names.add(alias.name)
                if alias.asname:
                    names.add(alias.asname)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def assert_not_referenced(module, forbidden) -> None:
    """Assert a module references none of ``forbidden`` in executable code."""
    referenced = executable_symbols(module)
    for name in forbidden:
        assert name not in referenced, (
            f"{module.__name__} references {name!r} in executable code"
        )
