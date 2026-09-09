"""Full FootyStats <-> TheStatsAPI competition crosswalk (data-driven universe).

This replaces the temporary hard-coded five-league universe with a crosswalk
derived from the authoritative provider-league registry
(``data/discovery/provider_league_registry.json``) through the canonical
identity infrastructure introduced in PR #3.

Identity truth is NOT re-invented here. We reuse
``load_competition_mappings`` (which links only ``mapping_status == "MATCHED"``
entries that carry exactly one TheStatsAPI competition id) as the Level-A
evidence, and classify every registry league into an explicit confidence:

    VERIFIED    - exactly one MATCHED TheStatsAPI comp id (auto-activatable)
    AMBIGUOUS   - matched-but-split / multiple comp ids (diagnostic only)
    UNRESOLVED  - no usable TheStatsAPI mapping
    API_UNSUPPORTED - registry marks it BLOCKED (provider lacks support)

No fuzzy / display-name matching is used to APPROVE a mapping; names are carried
for diagnostics only. Ambiguous candidates fail closed (never auto-activate).

The crosswalk is a pure function of the registry file contents, so it is
deterministic and testable without any network access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.research.identity.canonical import CanonicalRegistry, EntityKind
from src.research.identity.registry_loader import (
    DEFAULT_REGISTRY_PATH,
    FOOTYSTATS,
    THESTATSAPI,
    load_competition_mappings,
)


class IdentityStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PROBABLE = "PROBABLE"       # candidate with partial structural evidence
    AMBIGUOUS = "AMBIGUOUS"     # multiple candidates / split season
    UNRESOLVED = "UNRESOLVED"   # no usable mapping
    API_UNSUPPORTED = "API_UNSUPPORTED"  # provider lacks the competition


#: Registry mapping_status -> identity status (Level A). MATCHED-with-one-id is
#: resolved to VERIFIED downstream via the canonical registry link check.
_STATUS_MAP = {
    "MATCHED": IdentityStatus.VERIFIED,       # refined below by link check
    "SPLIT_OR_PARTIAL": IdentityStatus.AMBIGUOUS,
    "BLOCKED": IdentityStatus.API_UNSUPPORTED,
}


@dataclass(frozen=True)
class CrosswalkEntry:
    """One competition's crosswalk row (identity layer only; no live coverage).

    Coverage / market fields are added later by the coverage matrix. This
    entry captures identity + the registry's static provider metadata.
    """

    canonical_competition_id: Optional[str]
    canonical_name: str
    country: Optional[str]
    footystats_id: Optional[str]           # FS current_season_id (string)
    footystats_name: str
    thestatsapi_competition_id: Optional[str]
    thestatsapi_name: Optional[str]
    identity_status: IdentityStatus
    verification_method: str
    # Static provider capability flags (from the registry's TSA metadata).
    odds_available: Optional[bool]
    xg_available: Optional[bool]
    has_team_stats: Optional[bool]
    has_player_stats: Optional[bool]
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_competition_id": self.canonical_competition_id,
            "canonical_name": self.canonical_name,
            "country": self.country,
            "footystats_id": self.footystats_id,
            "footystats_name": self.footystats_name,
            "thestatsapi_competition_id": self.thestatsapi_competition_id,
            "thestatsapi_name": self.thestatsapi_name,
            "identity_status": self.identity_status.value,
            "verification_method": self.verification_method,
            "odds_available": self.odds_available,
            "xg_available": self.xg_available,
            "has_team_stats": self.has_team_stats,
            "has_player_stats": self.has_player_stats,
            "evidence": self.evidence,
        }


def _first(competitions: list, key: str) -> Optional[bool]:
    """Any-true across the registry's TSA competition metadata for a flag."""
    vals = [c.get(key) for c in competitions if isinstance(c, dict) and key in c]
    if not vals:
        return None  # UNKNOWN, never coerced to False
    return any(bool(v) for v in vals)


def build_crosswalk(path: str | Path = DEFAULT_REGISTRY_PATH) -> list[CrosswalkEntry]:
    """Build the full crosswalk from the registry (one row per league).

    Every registry league gets exactly one row (no silent omission). VERIFIED
    status is confirmed by the canonical registry link (Level A), not by name.
    """
    p = Path(path)
    data = json.loads(p.read_text())
    leagues = data.get("leagues", [])

    # Level A: link MATCHED+single-id entries via the canonical registry. This
    # is the authoritative confirmation that a competition is VERIFIED.
    canon = CanonicalRegistry()
    load_competition_mappings(canon, p)

    entries: list[CrosswalkEntry] = []
    for entry in leagues:
        if not isinstance(entry, dict):
            continue
        fs = entry.get("footystats", {}) or {}
        ts = entry.get("thestatsapi", {}) or {}
        comp_ids = ts.get("competition_ids", []) or []
        comps = ts.get("competitions", []) or []
        mapping_status = entry.get("mapping_status", "")

        fs_name = fs.get("name", "")
        fs_country = fs.get("country")
        fs_season_id = fs.get("current_season_id")
        fs_id = str(fs_season_id) if fs_season_id is not None else None

        base_status = _STATUS_MAP.get(mapping_status, IdentityStatus.UNRESOLVED)

        # Confirm VERIFIED strictly: exactly one comp id AND the canonical
        # registry actually linked it (fail closed otherwise).
        ts_comp_id: Optional[str] = None
        ts_name: Optional[str] = None
        method = f"registry:{mapping_status or 'UNKNOWN'}"
        identity = base_status

        if base_status == IdentityStatus.VERIFIED:
            if len(comp_ids) == 1 and fs_id is not None:
                linked = canon.translate(
                    from_provider=FOOTYSTATS, to_provider=THESTATSAPI,
                    kind=EntityKind.COMPETITION, provider_id=fs_id,
                )
                if linked == comp_ids[0]:
                    ts_comp_id = comp_ids[0]
                    identity = IdentityStatus.VERIFIED
                    method = "level_a_registry_matched_single_id"
                else:
                    # Registry said MATCHED but the canonical link disagrees or
                    # is absent — refuse to auto-verify.
                    identity = IdentityStatus.AMBIGUOUS
                    method = "level_a_link_mismatch"
            else:
                identity = IdentityStatus.AMBIGUOUS
                method = "matched_but_multiple_or_missing_id"

        if ts_comp_id is None and comp_ids:
            # Ambiguous / split: keep the ids as diagnostic evidence only.
            ts_comp_id = None  # never auto-join an ambiguous id
        # Name (diagnostic only).
        if comps:
            for c in comps:
                if isinstance(c, dict) and c.get("id") == ts_comp_id:
                    ts_name = c.get("name")
                    break
            if ts_name is None and isinstance(comps[0], dict):
                ts_name = comps[0].get("name")

        canonical_id = None
        if identity == IdentityStatus.VERIFIED and fs_id is not None:
            ent = canon.try_resolve(FOOTYSTATS, EntityKind.COMPETITION, fs_id)
            canonical_id = ent.canonical_id if ent else None

        entries.append(
            CrosswalkEntry(
                canonical_competition_id=canonical_id,
                canonical_name=fs_name,
                country=fs_country,
                footystats_id=fs_id,
                footystats_name=fs_name,
                thestatsapi_competition_id=ts_comp_id,
                thestatsapi_name=ts_name,
                identity_status=identity,
                verification_method=method,
                odds_available=_first(comps, "odds_available"),
                xg_available=_first(comps, "xg_available"),
                has_team_stats=_first(comps, "has_team_stats"),
                has_player_stats=_first(comps, "has_player_stats"),
                evidence={
                    "mapping_status": mapping_status,
                    "thestatsapi_competition_ids": comp_ids,
                    "footystats_current_season_year": fs.get("current_season_year"),
                },
            )
        )
    return entries


def crosswalk_summary(entries: list[CrosswalkEntry]) -> dict[str, int]:
    """Count entries by identity status (deterministic)."""
    from collections import Counter

    c = Counter(e.identity_status.value for e in entries)
    return {"total": len(entries), **dict(sorted(c.items()))}
