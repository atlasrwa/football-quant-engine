"""formation_structure_v1 — neutral formation identity + explicit structural attributes.

V3 patch SS9-SS12: formation remains a first-class football-resolution variable, but the
Sonnet-facing packet must stop exposing the human-readable label ("4-2-3-1") and the
human-readable family name ("BACK4_1STRIKER") -- both carry pretrained tactical stereotypes
a model can lean on instead of the measured behavioral evidence. This module provides:

  * a NEUTRAL formation_id ("F_07") for the exact formation, from the versioned, explicit,
    auditable FORMATION_STRUCTURE_V1.json table (formations outside that table resolve to
    the closed "F_UNK" token -- SS10: unknown/unusual formations fail safely, no invented
    id);
  * a NEUTRAL family_id ("FF_03") for the formation FAMILY (FORMATION_FAMILY_V1.json's
    family names, id-mapped here rather than duplicating a second source of truth);
  * explicit STRUCTURAL attributes (back_line_count / holding_midfield_count /
    advanced_midfield_count / midfield_count / forward_line_count) derived from the
    formation string's own digit-band notation -- this is what lets Sonnet reason about
    "what structure this represents" without ever seeing the label itself (SS4, SS9).

This module NEVER uses club, league, or manager knowledge -- purely digit-band parsing, same
authority basis as FORMATION_FAMILY_V1.json's own derivation rule.
"""
from __future__ import annotations
import json
import os
from typing import Optional

from src.research.llm_matchup import formation as FM

FORMATION_STRUCTURE_VERSION = "formation_structure_v1"
#: The versioned structure table, resolved from THIS module's own canonical location:
#: <repo>/src/research/llm_matchup/hardening/ -> <repo>/research/llm_matchup/. It is a
#: frozen scientific INPUT hashed into the V3 generation fingerprint, so it must come from
#: the executing checkout for that fingerprint to describe the run. A hardcoded
#: "/home/ubuntu" here made `current_generation_fingerprint()` unusable in an independent
#: checkout and, where the deployed tree existed, let it hash a foreign table.
_STRUCTURE_JSON = os.path.join(
    os.path.realpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), *([os.pardir] * 4))),
    "research", "llm_matchup", "FORMATION_STRUCTURE_V1.json")

UNKNOWN_FORMATION_ID = "F_UNK"

_TABLE: Optional[dict] = None


def _load() -> dict:
    global _TABLE
    if _TABLE is None:
        with open(_STRUCTURE_JSON) as f:
            _TABLE = json.load(f)
    return _TABLE


def _derive_structure(formation: str) -> dict:
    """The auditable digit-band derivation rule (FORMATION_STRUCTURE_V1.json's
    `derivation_rule`), applied at lookup time for any formation not in the explicit table."""
    empty = {"back_line_count": None, "holding_midfield_count": None,
             "advanced_midfield_count": None, "midfield_count": None,
             "forward_line_count": None, "n_bands": None, "structure_known": False}
    try:
        bands = [int(x) for x in formation.split("-")]
    except (ValueError, AttributeError):
        return empty
    if len(bands) < 2 or any(b <= 0 for b in bands):
        return empty
    back, forward = bands[0], bands[-1]
    middle = bands[1:-1]
    if len(middle) == 1:
        return {"back_line_count": back, "holding_midfield_count": None,
                "advanced_midfield_count": None, "midfield_count": middle[0],
                "forward_line_count": forward, "n_bands": len(bands), "structure_known": True}
    if len(middle) == 2:
        return {"back_line_count": back, "holding_midfield_count": middle[0],
                "advanced_midfield_count": middle[1], "midfield_count": sum(middle),
                "forward_line_count": forward, "n_bands": len(bands), "structure_known": True}
    return empty


def formation_structure(formation: Optional[str]) -> dict:
    """Total function: neutral formation_id + structural attributes for an exact formation
    string. Formations outside the explicit, reviewed table always get formation_id=F_UNK
    (SS10 -- the neutral-id namespace is closed to reviewed formations) even when their
    digit-band structure is technically parseable; the structural counts themselves are
    still safely derivable and returned (they carry no identity)."""
    table = _load()
    norm = FM.normalize_formation(formation)
    if norm is None:
        return {"formation_id": UNKNOWN_FORMATION_ID, "back_line_count": None,
                "holding_midfield_count": None, "advanced_midfield_count": None,
                "midfield_count": None, "forward_line_count": None,
                "structure_known": False, "structure_version": FORMATION_STRUCTURE_VERSION}
    entry = table["exact_to_structure"].get(norm)
    if entry is not None:
        out = {k: v for k, v in entry.items() if k != "n_bands"}
        out["structure_version"] = FORMATION_STRUCTURE_VERSION
        return out
    derived = _derive_structure(norm)
    out = {"formation_id": UNKNOWN_FORMATION_ID,
           **{k: v for k, v in derived.items() if k != "n_bands"}}
    out["structure_version"] = FORMATION_STRUCTURE_VERSION
    return out


def family_id(family: Optional[str]) -> str:
    """Neutral id for a FORMATION_FAMILY_V1 family name (e.g. BACK4_1STRIKER -> FF_03)."""
    table = _load()
    ids = table["neutral_family_ids"]
    return ids.get(family, table["unknown_family_id"])


def structure_content_hash() -> str:
    import hashlib
    return hashlib.sha256(open(_STRUCTURE_JSON, "rb").read()).hexdigest()
