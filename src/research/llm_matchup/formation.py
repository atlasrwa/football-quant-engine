"""formation_policy_v1 — two-concept formation model (Phase B).

This module implements the ARCHITECTURAL CORRECTION mandated for Phase B: resolved
historical formation is now a first-class football-RESOLUTION variable, while pre-match
formation availability remains conceptually separate.

Two concepts, never conflated:

  RESOLVED_FORMATION   — how a team ACTUALLY lined up in a COMPLETED historical match.
                         Read from the cached lineup payload (`confirmed:true`). Lacks a
                         trustworthy announcement timestamp, but that does NOT invalidate
                         its use as historical football-resolution evidence.

  PREMATCH_FORMATION   — formation information legitimately available BEFORE the target
                         fixture (announced / timestamped feed / projected / model).
                         This is the only formation that may enter a forward prediction.
                         Represented by the FormationInput interface (designed, not yet
                         productionised).

HARD LEAKAGE RULE (enforced by callers + tests):
  * For HISTORICAL SOURCE matches (kickoff < target cutoff): resolved formation allowed.
  * For the TARGET fixture: resolved formation is FORBIDDEN as evidence. Only a
    FormationInput (ANNOUNCED / PROJECTED / UNKNOWN) may be attached, and never the
    target's own final recorded formation.

The family mapping is deterministic and versioned (FORMATION_FAMILY_V1.json). A family is
a CONDITIONING KEY only; it carries no behavioral assumption. Behavior is measured
elsewhere from the evidence.
"""
from __future__ import annotations
import os
import json
import glob
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional

# --- versions (kept here to avoid a hard import cycle; mirrored in versions.py) --
FORMATION_POLICY_VERSION = "formation_policy_v1"
FORMATION_FAMILY_VERSION = "formation_family_v1"

_LINEUP_CACHE = "/home/ubuntu/data/thestatsapi/championship"
_FAMILY_JSON = "/home/ubuntu/research/llm_matchup/FORMATION_FAMILY_V1.json"

UNKNOWN_FORMATION = "UNKNOWN_FORMATION"


# ---------------------------------------------------------------------------
# Formation family mapping (deterministic, versioned)
# ---------------------------------------------------------------------------
_FAMILY_TABLE: Optional[dict] = None


def _load_family_table() -> dict:
    global _FAMILY_TABLE
    if _FAMILY_TABLE is None:
        with open(_FAMILY_JSON) as f:
            _FAMILY_TABLE = json.load(f)
    return _FAMILY_TABLE


def formation_family(formation: Optional[str]) -> str:
    """Map an exact resolved formation string to its versioned family.

    Total function: returns UNKNOWN_FORMATION for null/blank/unparseable input.
    Uses the explicit table first, then the documented digit-structure derivation rule so
    the mapping is defined for every syntactically valid formation. Never uses club or
    league knowledge.
    """
    if not formation or not isinstance(formation, str):
        return UNKNOWN_FORMATION
    key = formation.strip()
    if not key:
        return UNKNOWN_FORMATION
    table = _load_family_table()
    exact = table["exact_to_family"]
    if key in exact:
        return exact[key]
    # deterministic derivation from digit structure
    try:
        bands = [int(x) for x in key.split("-")]
    except (ValueError, AttributeError):
        return UNKNOWN_FORMATION
    if len(bands) < 2 or any(b <= 0 for b in bands):
        return UNKNOWN_FORMATION
    defenders, forwards = bands[0], bands[-1]
    second = bands[1] if len(bands) >= 2 else 0
    if defenders == 5:
        return "BACK5_DEFENSIVE"
    if defenders == 3:
        return "BACK3_WINGBACK" if second >= 4 else "BACK3_OTHER"
    if defenders == 4:
        if forwards == 2:
            return "BACK4_2STRIKER"
        if forwards == 1:
            return "BACK4_1STRIKER"
        return "BACK4_OTHER"
    return UNKNOWN_FORMATION


def normalize_formation(formation: Optional[str]) -> Optional[str]:
    """Return a cleaned exact formation string, or None if absent/blank."""
    if not formation or not isinstance(formation, str):
        return None
    s = formation.strip()
    return s or None


# ---------------------------------------------------------------------------
# RESOLVED formation reader (historical source matches ONLY)
# ---------------------------------------------------------------------------
@dataclass
class ResolvedFormation:
    """How a team actually lined up in a COMPLETED historical match.

    source_type is fixed to RESOLVED. This is football-resolution evidence, NOT a
    forecast input. `has_announcement_timestamp` is always False for this data source and
    is recorded explicitly so downstream consumers never mistake it for pre-match-known.
    """
    fixture_id: str
    side: str                       # "home" | "away"
    formation: Optional[str]        # exact resolved formation, or None
    family: str                     # versioned family (UNKNOWN_FORMATION if absent)
    confirmed: bool
    source_type: str = "RESOLVED"
    has_announcement_timestamp: bool = False
    family_version: str = FORMATION_FAMILY_VERSION
    policy_version: str = FORMATION_POLICY_VERSION


def _lineup_path(fixture_id: str) -> str:
    """Resolve the lineup cache path for a fixture id.

    Corpus fixture_ids carry the `mt_` prefix (e.g. "mt_581147491"); the cache files are
    named lineups_mt_<digits>.json. Accept either form.
    """
    fid = str(fixture_id)
    core = fid[len("mt_"):] if fid.startswith("mt_") else fid
    return os.path.join(_LINEUP_CACHE, f"lineups_mt_{core}.json")


def load_resolved_formation(fixture_id: str) -> Optional[dict[str, ResolvedFormation]]:
    """Read the resolved (actually-played) formation for a completed historical match.

    Returns {"home": ResolvedFormation, "away": ResolvedFormation} or None if no lineup
    cache exists. Fail-closed: a missing/unparseable formation becomes family
    UNKNOWN_FORMATION with formation=None (never fabricated).
    """
    path = _lineup_path(str(fixture_id))
    if not os.path.exists(path):
        return None
    try:
        d = json.load(open(path)).get("data", {})
    except Exception:
        return None
    confirmed = bool(d.get("confirmed", False))
    out: dict[str, ResolvedFormation] = {}
    for side in ("home", "away"):
        blk = d.get(side) or {}
        form = normalize_formation(blk.get("formation"))
        out[side] = ResolvedFormation(
            fixture_id=str(fixture_id), side=side, formation=form,
            family=formation_family(form), confirmed=confirmed,
        )
    return out


def has_resolved_formation(fixture_id: str) -> bool:
    r = load_resolved_formation(fixture_id)
    if r is None:
        return False
    return any(v.formation is not None for v in r.values())


def resolved_coverage_index() -> dict[str, dict]:
    """Deterministic index of all fixtures for which a resolved formation exists.

    Returns fixture_id -> {"home": formation|None, "away": formation|None,
    "home_family": ..., "away_family": ..., "confirmed": bool}. Used by the selection
    policy and coverage reporting. No network, cache-only.
    """
    idx: dict[str, dict] = {}
    for p in glob.glob(os.path.join(_LINEUP_CACHE, "lineups_mt_*.json")):
        core = os.path.basename(p)[len("lineups_mt_"):-len(".json")]
        fid = f"mt_{core}"          # match corpus fixture_id form
        r = load_resolved_formation(fid)
        if r is None:
            continue
        idx[fid] = {
            "home": r["home"].formation, "away": r["away"].formation,
            "home_family": r["home"].family, "away_family": r["away"].family,
            "confirmed": r["home"].confirmed,
        }
    return idx


# ---------------------------------------------------------------------------
# PREMATCH formation interface (forecast input) — designed, not productionised
# ---------------------------------------------------------------------------
class FormationSourceType(str, Enum):
    ANNOUNCED = "ANNOUNCED"        # official announced lineup / timestamped feed
    PROJECTED = "PROJECTED"        # deterministic projection or formation model output
    UNKNOWN = "UNKNOWN"            # no legitimate pre-match formation information


class FormationConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


@dataclass
class FormationInput:
    """The ONLY formation object that may enter a forward prediction (Phase C+).

    This is deliberately separate from ResolvedFormation. It NEVER originates from the
    target fixture's own final recorded formation. In Phase B it is designed and exercised
    by tests, but no live projection model is built (brief §12, §13).

    For FORMATION_UNCERTAIN handling, `distribution` may carry {formation: weight} whose
    weights sum to ~1.0; when present the consumer may marginalise over it.
    """
    formation: Optional[str]
    formation_family: str
    source_type: str                # FormationSourceType value
    confidence: str                 # FormationConfidence value
    source_version: str
    distribution: Optional[dict[str, float]] = None
    policy_version: str = FORMATION_POLICY_VERSION
    family_version: str = FORMATION_FAMILY_VERSION

    @staticmethod
    def unknown(source_version: str = "phase_b_no_prematch") -> "FormationInput":
        """The honest default when no pre-match formation information exists."""
        return FormationInput(
            formation=None, formation_family=UNKNOWN_FORMATION,
            source_type=FormationSourceType.UNKNOWN.value,
            confidence=FormationConfidence.UNKNOWN.value,
            source_version=source_version, distribution=None,
        )

    @staticmethod
    def announced(formation: str, source_version: str) -> "FormationInput":
        return FormationInput(
            formation=normalize_formation(formation),
            formation_family=formation_family(formation),
            source_type=FormationSourceType.ANNOUNCED.value,
            confidence=FormationConfidence.HIGH.value,
            source_version=source_version,
        )

    @staticmethod
    def projected(formation: Optional[str], source_version: str,
                  confidence: str = FormationConfidence.MEDIUM.value,
                  distribution: Optional[dict[str, float]] = None) -> "FormationInput":
        return FormationInput(
            formation=normalize_formation(formation),
            formation_family=formation_family(formation),
            source_type=FormationSourceType.PROJECTED.value,
            confidence=confidence, source_version=source_version,
            distribution=distribution,
        )

    def to_dict(self) -> dict:
        return asdict(self)


def assert_not_target_resolved(finput: FormationInput) -> None:
    """Guard: a FormationInput used for a target fixture must not be a RESOLVED source.

    RESOLVED is not even a valid source_type for FormationInput; this belt-and-braces
    check makes the leakage boundary explicit and testable.
    """
    if finput.source_type == "RESOLVED":
        raise ValueError("LEAKAGE: target-fixture formation must not be RESOLVED historical formation")
