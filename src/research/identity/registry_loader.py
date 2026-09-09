"""Seed the canonical registry from the existing provider-league registry.

The repository already maintains a FootyStats <-> TheStatsAPI league crosswalk
at ``data/discovery/provider_league_registry.json`` (synced by
``scripts/sync_provider_leagues.py``). Rather than duplicate that mapping, this
loader ingests it into a ``CanonicalRegistry`` as COMPETITION entities.

Only entries with ``mapping_status == "MATCHED"`` and exactly one TheStatsAPI
competition id are linked automatically; anything ambiguous (multiple comp ids,
unmatched) is SKIPPED and reported, never guessed. This keeps the production
path free of speculative joins.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.research.identity.canonical import (
    CanonicalRegistry,
    EntityKind,
    IdentityConflictError,
    ProviderRef,
)

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_PATH = "data/discovery/provider_league_registry.json"

FOOTYSTATS = "footystats"
THESTATSAPI = "thestatsapi"


def load_competition_mappings(
    registry: CanonicalRegistry,
    path: str | Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    """Load MATCHED league mappings into ``registry`` as COMPETITION entities.

    Returns a report dict with counts of linked/skipped/conflicted entries.
    """
    p = Path(path)
    report: dict[str, Any] = {"linked": 0, "skipped_ambiguous": 0, "skipped_unmatched": 0, "conflicts": []}
    if not p.exists():
        logger.warning("Provider league registry not found at %s", p)
        report["error"] = "registry_not_found"
        return report

    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read registry %s: %s", p, exc)
        report["error"] = "registry_unreadable"
        return report

    for entry in data.get("leagues", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("mapping_status") != "MATCHED":
            report["skipped_unmatched"] += 1
            continue

        fs = entry.get("footystats") or {}
        tsa = entry.get("thestatsapi") or {}
        fs_id = fs.get("current_season_id")  # league-level fs identifier used in corpus
        comp_ids = tsa.get("competition_ids") or []

        # Only link unambiguous 1:1 competition mappings automatically.
        if fs_id is None or len(comp_ids) != 1:
            report["skipped_ambiguous"] += 1
            continue

        fs_ref = ProviderRef(
            provider=FOOTYSTATS,
            kind=EntityKind.COMPETITION,
            provider_id=str(fs_id),
            display_name=str(fs.get("name", "")),
        )
        tsa_ref = ProviderRef(
            provider=THESTATSAPI,
            kind=EntityKind.COMPETITION,
            provider_id=str(comp_ids[0]),
            display_name=str((tsa.get("competitions") or [{}])[0].get("name", "")),
        )
        try:
            registry.link([fs_ref, tsa_ref])
            report["linked"] += 1
        except IdentityConflictError as exc:
            report["conflicts"].append(str(exc))
            logger.warning("Identity conflict linking league %s: %s", fs.get("name"), exc)

    return report
