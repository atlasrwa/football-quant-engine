"""Load ONLY high-confidence team mappings into a CanonicalRegistry.

The legacy ``data/mapping/team_crosswalk.json`` was built by name-similarity
fuzzy matching and contains confirmed-wrong entries (e.g. Leicester City ->
Manchester City at confidence 0.759). PR #3's identity rules forbid fuzzy
matching in the production/comparison path, so this loader admits ONLY entries
at or above a confidence threshold (default 0.9) and treats everything else as
unmapped (fail closed). Wrong mappings never enter the comparison.

Returns the registry plus a report of what was admitted/excluded so the
experiment can document its identity basis explicitly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.research.identity import CanonicalRegistry, EntityKind, ProviderRef

FOOTYSTATS = "footystats"
THESTATSAPI = "thestatsapi"
DEFAULT_CROSSWALK = "data/mapping/team_crosswalk.json"
DEFAULT_MIN_CONFIDENCE = 0.9


@dataclass(frozen=True)
class IdentitySetupReport:
    min_confidence: float
    admitted: int = 0
    excluded_low_confidence: int = 0
    leagues: dict[str, int] = field(default_factory=dict)
    excluded_examples: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "min_confidence": self.min_confidence,
            "admitted_team_maps": self.admitted,
            "excluded_low_confidence": self.excluded_low_confidence,
            "admitted_by_league": self.leagues,
            "excluded_examples": self.excluded_examples,
        }


def load_high_confidence_team_registry(
    crosswalk_path: str | Path = DEFAULT_CROSSWALK,
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    leagues: Optional[list[str]] = None,
) -> tuple[CanonicalRegistry, IdentitySetupReport, dict[str, dict[str, str]]]:
    """Build a CanonicalRegistry of TEAM entities from high-confidence maps only.

    Args:
        crosswalk_path: Path to the legacy team crosswalk JSON.
        min_confidence: Minimum confidence to admit a mapping (default 0.9).
        leagues: Restrict to these league names (None = all in the crosswalk).

    Returns:
        (registry, report, name_to_tm) where name_to_tm maps
        league -> {footystats_name -> thestats_id} for admitted teams only.
    """
    data = json.loads(Path(crosswalk_path).read_text())
    registry = CanonicalRegistry()
    admitted = 0
    excluded = 0
    by_league: dict[str, int] = {}
    excluded_examples: list[dict] = []
    name_to_tm: dict[str, dict[str, str]] = {}

    for league, teams in data.get("leagues", {}).items():
        if leagues is not None and league not in leagues:
            continue
        league_map: dict[str, str] = {}
        for t in teams:
            conf = float(t.get("confidence", 0.0))
            fs_name = t.get("footystats_name", "")
            tm_id = t.get("thestats_id", "")
            if conf < min_confidence:
                excluded += 1
                if len(excluded_examples) < 25:
                    excluded_examples.append({
                        "league": league,
                        "footystats_name": fs_name,
                        "thestats_id": tm_id,
                        "thestats_name": t.get("thestats_name", ""),
                        "confidence": conf,
                    })
                continue
            # FootyStats team identity here is the display name from the
            # crosswalk (the corpus keys teams by name); TheStatsAPI identity is
            # the tm_ id. Both are provider ids in the registry sense.
            registry.link([
                ProviderRef(FOOTYSTATS, EntityKind.TEAM, fs_name, fs_name),
                ProviderRef(THESTATSAPI, EntityKind.TEAM, tm_id, t.get("thestats_name", "")),
            ])
            league_map[fs_name] = tm_id
            admitted += 1
            by_league[league] = by_league.get(league, 0) + 1
        if league_map:
            name_to_tm[league] = league_map

    report = IdentitySetupReport(
        min_confidence=min_confidence,
        admitted=admitted,
        excluded_low_confidence=excluded,
        leagues=by_league,
        excluded_examples=excluded_examples,
    )
    return registry, report, name_to_tm
