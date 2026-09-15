"""V5A.1 common evidence interface (`evidence_interface_v1`).

THE central fix for the aborted V5A. In V5A the two arms carried structurally different
packets, and the shared validator/firewall resolved references only through the V3-shaped
``packet["evidence"]`` key -- which Arm B did not have. Every Arm B hypothesis was therefore
rejected before a single token was generated.

Here BOTH arms serialize every model-visible fact through ONE contract, `EvidenceRecord`,
with ONE deterministic, collision-free, arm-neutral id grammar. The arms differ only in
WHICH records are present, never in how a record is shaped, named or resolved.

ZERO SPEND. This module builds and resolves evidence. It calls no model and no network.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

EVIDENCE_INTERFACE_VERSION = "evidence_interface_v1"

# ----------------------------------------------------------------------------------------
# Evidence types. Each means exactly one thing; none is overloaded to stand in for another.
# ----------------------------------------------------------------------------------------
MATCH_OBSERVATION = "MATCH_OBSERVATION"
DERIVED_SUMMARY = "DERIVED_SUMMARY"
OPPONENT_PROFILE_SUMMARY = "OPPONENT_PROFILE_SUMMARY"
FORMATION_CONTEXT = "FORMATION_CONTEXT"
AVAILABILITY_DECLARATION = "AVAILABILITY_DECLARATION"

EVIDENCE_TYPES = (MATCH_OBSERVATION, DERIVED_SUMMARY, OPPONENT_PROFILE_SUMMARY,
                  FORMATION_CONTEXT, AVAILABILITY_DECLARATION)

#: Derivation type says how the number came to exist. RAW_OBSERVATION is a canonical cell
#: copied verbatim; everything else is arithmetic over such cells, named explicitly.
RAW_OBSERVATION = "RAW_OBSERVATION"
UNWEIGHTED_MEAN = "UNWEIGHTED_MEAN"
COHORT_UNWEIGHTED_MEAN = "COHORT_UNWEIGHTED_MEAN"
COUNT = "COUNT"
DECLARATION = "DECLARATION"

DERIVATION_TYPES = (RAW_OBSERVATION, UNWEIGHTED_MEAN, COHORT_UNWEIGHTED_MEAN,
                    COUNT, DECLARATION)

SUBJECTS = ("HOME", "AWAY")

#: Venue scope of the evidence itself. ANY = not venue-conditioned.
VENUE_SCOPES = ("ANY", "HOME_ONLY", "AWAY_ONLY")

#: Window scope. ALL_PRIOR = the team's entire PIT-safe prior record (NOT the raw-row cap).
WINDOWS = ("ALL_PRIOR", "W5", "W10", "SINGLE_MATCH", "NOT_APPLICABLE")

#: Packet-exposure states. Distinct from provider availability and from derivability --
#: see `ExposureTriple`. This is the ONLY availability the model is asked to act on.
EXPOSED = "EXPOSED"
NOT_EXPOSED_IN_PACKET = "NOT_EXPOSED_IN_PACKET"
EXPOSED_LOW_COVERAGE = "EXPOSED_LOW_COVERAGE"
NOT_DERIVABLE_PIT_SAFE = "NOT_DERIVABLE_PIT_SAFE"
NOT_PROVIDED_BY_SOURCE = "NOT_PROVIDED_BY_SOURCE"

EXPOSURE_STATES = (EXPOSED, EXPOSED_LOW_COVERAGE, NOT_EXPOSED_IN_PACKET,
                   NOT_DERIVABLE_PIT_SAFE, NOT_PROVIDED_BY_SOURCE)

RELIABILITY_HIGH_N = 20
RELIABILITY_MEDIUM_N = 8


def reliability_for(n: Optional[int]) -> str:
    """Deterministic reliability label. The thresholds are serialized into the packet so a
    reader never has to guess what HIGH means (a V5A readability defect, N-4)."""
    if n is None:
        return "NOT_APPLICABLE"
    if n >= RELIABILITY_HIGH_N:
        return "HIGH"
    if n >= RELIABILITY_MEDIUM_N:
        return "MEDIUM"
    return "LOW"


RELIABILITY_RULE = (f"HIGH when sample_n >= {RELIABILITY_HIGH_N}; MEDIUM when sample_n >= "
                    f"{RELIABILITY_MEDIUM_N}; otherwise LOW. Purely a function of sample_n "
                    f"-- it says nothing about whether the quantity is useful.")


# ----------------------------------------------------------------------------------------
# Opponent-profile direction (V5A defect M-2: `HOME`/`AWAY` profile keys were ambiguous and
# actually inverted relative to the natural reading). Direction is now spelled out.
# ----------------------------------------------------------------------------------------
#: Short codes appear in the evidence_id; the full sentence is on every record as
#: `semantic_label`, so a citation stays short while the meaning stays explicit.
ATTACK_VS_DEF_SIMILAR = "ATK_VS_DEFSIM"
DEFENCE_VS_ATK_SIMILAR = "DEF_VS_ATKSIM"

DIRECTION_MEANING = {
    ATTACK_VS_DEF_SIMILAR:
        "the subject's ATTACKING output against past opponents whose DEFENSIVE profile "
        "resembles the upcoming opponent's",
    DEFENCE_VS_ATK_SIMILAR:
        "what the subject CONCEDED against past opponents whose ATTACKING profile "
        "resembles the upcoming opponent's",
}

PROFILE_DIRECTIONS = (ATTACK_VS_DEF_SIMILAR, DEFENCE_VS_ATK_SIMILAR)

_PROFILE_LABEL = {
    ("HOME", ATTACK_VS_DEF_SIMILAR):
        "HOME_TEAM_ATTACK_VS_OPPONENTS_DEFENSIVELY_SIMILAR_TO_AWAY_TEAM",
    ("HOME", DEFENCE_VS_ATK_SIMILAR):
        "HOME_TEAM_DEFENCE_VS_OPPONENTS_OFFENSIVELY_SIMILAR_TO_AWAY_TEAM",
    ("AWAY", ATTACK_VS_DEF_SIMILAR):
        "AWAY_TEAM_ATTACK_VS_OPPONENTS_DEFENSIVELY_SIMILAR_TO_HOME_TEAM",
    ("AWAY", DEFENCE_VS_ATK_SIMILAR):
        "AWAY_TEAM_DEFENCE_VS_OPPONENTS_OFFENSIVELY_SIMILAR_TO_HOME_TEAM",
}


def profile_semantic_label(subject: str, direction: str) -> str:
    return _PROFILE_LABEL[(subject, direction)]


# ----------------------------------------------------------------------------------------
# Evidence id grammar.
#
# Deterministic, collision-free, human-readable, arm-neutral. Every id is built by one of
# the constructors below; nothing anywhere else formats an id by hand.
#
#   MATCH:HOME:M01                              one historical match observation (a row)
#   MATCH:HOME:M01:corners_for                  one canonical cell of that row
#   SUMMARY:HOME:ALL_PRIOR:ANY:corners_for      a deterministic aggregate
#   SUMMARY:HOME:ALL_PRIOR:HOME_ONLY:corners_for
#   PROFILE:HOME:ATTACK_VS_...:shots_on_target_for
#   FORMATION:HOME                              formation coverage context
#   AVAIL:venue_splits                          an availability declaration
#
# Match slots are SUBJECT-QUALIFIED (V5A defect M-4: bare provider match ids collided across
# the two teams in 9 cases when the teams had met). HOME_M01 and AWAY_M01 can never collide.
# ----------------------------------------------------------------------------------------
_ID_SAFE = re.compile(r"^[A-Za-z0-9_]+$")


def _check(part: str, what: str) -> str:
    if not _ID_SAFE.match(part or ""):
        raise ValueError(f"{what} {part!r} is not id-safe ([A-Za-z0-9_]+)")
    return part


def match_slot(subject: str, ordinal: int) -> str:
    """Chronological slot within the subject's serialized rows. M01 is the OLDEST."""
    if subject not in SUBJECTS:
        raise ValueError(f"subject {subject!r} not in {SUBJECTS}")
    if ordinal < 1:
        raise ValueError(f"match ordinal must be >= 1, got {ordinal}")
    return f"M{ordinal:02d}"


def match_id(subject: str, ordinal: int) -> str:
    return f"MATCH:{_check(subject, 'subject')}:{match_slot(subject, ordinal)}"


def match_cell_id(subject: str, ordinal: int, metric: str, side: str) -> str:
    return f"{match_id(subject, ordinal)}:{_check(metric, 'metric')}_{side.lower()}"


def summary_id(subject: str, window: str, venue_scope: str, metric: str, side: str) -> str:
    if window not in WINDOWS:
        raise ValueError(f"window {window!r} not in {WINDOWS}")
    if venue_scope not in VENUE_SCOPES:
        raise ValueError(f"venue_scope {venue_scope!r} not in {VENUE_SCOPES}")
    return (f"SUMMARY:{_check(subject, 'subject')}:{window}:{venue_scope}:"
            f"{_check(metric, 'metric')}_{side.lower()}")


def profile_id(subject: str, direction: str, axis: str, metric: str, side: str) -> str:
    """The similarity AXIS is part of the id: two axes describing the same subject,
    direction and response metric are different evidence and must be separately citable."""
    if direction not in PROFILE_DIRECTIONS:
        raise ValueError(f"direction {direction!r} not in {PROFILE_DIRECTIONS}")
    return (f"PROFILE:{_check(subject, 'subject')}:{direction}:{_check(axis, 'axis')}:"
            f"{_check(metric, 'metric')}_{side.lower()}")


def formation_id(subject: str) -> str:
    return f"FORMATION:{_check(subject, 'subject')}"


def availability_id(dimension: str) -> str:
    return f"AVAIL:{_check(dimension, 'dimension')}"


ID_GRAMMAR_DOC = {
    "MATCH:<SUBJECT>:M<nn>":
        "one historical match observation. SUBJECT is HOME or AWAY (the subject team of "
        "the UPCOMING fixture). M01 is the OLDEST serialized match, M<n_rows> the most "
        "recent. Slots are subject-qualified, so HOME:M01 and AWAY:M01 are different "
        "matches even when the two teams played each other.",
    "MATCH:<SUBJECT>:M<nn>:<metric>_<for|against>":
        "one canonical cell of that match, from the subject team's perspective. "
        "_for = the subject recorded it; _against = its opponent in that match recorded it.",
    "SUMMARY:<SUBJECT>:<window>:<venue_scope>:<metric>_<for|against>":
        "a deterministic aggregate. window is ALL_PRIOR (the subject's ENTIRE PIT-safe "
        "prior record), W5 or W10. venue_scope is ANY, HOME_ONLY or AWAY_ONLY and refers "
        "to where the SUBJECT played in the matches being aggregated.",
    "PROFILE:<SUBJECT>:<direction>:<similarity_axis>:<metric>_<for|against>":
        "a historical response summary: how the subject behaved against a cohort of past "
        "opponents whose measured profile resembles the upcoming opponent. direction is "
        "ATK_VS_DEFSIM (the subject's attacking output against opponents defensively "
        "similar to the next opponent) or DEF_VS_ATKSIM (what the subject conceded against "
        "opponents offensively similar to the next opponent). similarity_axis names the "
        "measured axis the resemblance was computed on. Every such record also carries a "
        "full-sentence semantic_label, its cohort definition, cohort_n, and the subject's "
        "own baseline over all prior matches for the same metric.",
    "FORMATION:<SUBJECT>":
        "recorded-formation coverage context for the subject.",
    "AVAIL:<dimension>":
        "a declaration of whether a research dimension is exposed in THIS packet.",
}


# ----------------------------------------------------------------------------------------
# The record contract
# ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class EvidenceRecord:
    """One citable fact. Every model-visible fact in either arm is one of these.

    `value` is the number (or, for declarations and formation context, the state). Nothing
    the model can cite exists outside this contract.
    """

    evidence_id: str
    evidence_type: str
    subject: Optional[str] = None
    metric: Optional[str] = None
    side: Optional[str] = None
    value: object = None
    units: Optional[str] = None
    window: str = "NOT_APPLICABLE"
    venue_scope: str = "ANY"
    fixture_ref: Optional[str] = None
    opponent_ref: Optional[str] = None
    competition_ref: Optional[str] = None
    formation: Optional[str] = None
    sample_n: Optional[int] = None
    coverage: Optional[float] = None
    reliability: str = "NOT_APPLICABLE"
    provider_provenance: Optional[str] = None
    cutoff: Optional[int] = None
    derivation_type: str = RAW_OBSERVATION
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.evidence_type not in EVIDENCE_TYPES:
            raise ValueError(f"evidence_type {self.evidence_type!r} not in {EVIDENCE_TYPES}")
        if self.derivation_type not in DERIVATION_TYPES:
            raise ValueError(f"derivation_type {self.derivation_type!r} not in "
                             f"{DERIVATION_TYPES}")
        if self.window not in WINDOWS:
            raise ValueError(f"window {self.window!r} not in {WINDOWS}")
        if self.venue_scope not in VENUE_SCOPES:
            raise ValueError(f"venue_scope {self.venue_scope!r} not in {VENUE_SCOPES}")
        if self.subject is not None and self.subject not in SUBJECTS:
            raise ValueError(f"subject {self.subject!r} not in {SUBJECTS}")

    def to_dict(self) -> dict:
        d = {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "subject": self.subject,
            "metric": self.metric,
            "side": self.side,
            "value": self.value,
            "units": self.units,
            "window": self.window,
            "venue_scope": self.venue_scope,
            "fixture_ref": self.fixture_ref,
            "opponent_ref": self.opponent_ref,
            "competition_ref": self.competition_ref,
            "formation": self.formation,
            "sample_n": self.sample_n,
            "coverage": self.coverage,
            "reliability": self.reliability,
            "provider_provenance": self.provider_provenance,
            "cutoff": self.cutoff,
            "derivation_type": self.derivation_type,
        }
        d.update(self.extra or {})
        return {k: v for k, v in d.items() if v is not None}


class DuplicateEvidenceId(ValueError):
    """Raised at CONSTRUCTION when two records claim the same id. Never a warning: a
    duplicate id makes a citation ambiguous, which is the defect this interface exists to
    remove."""


def assert_unique(records: Iterable[EvidenceRecord]) -> list[EvidenceRecord]:
    seen: dict[str, EvidenceRecord] = {}
    out = []
    for r in records:
        if r.evidence_id in seen:
            raise DuplicateEvidenceId(
                f"duplicate evidence_id {r.evidence_id!r} "
                f"({seen[r.evidence_id].evidence_type} vs {r.evidence_type})")
        seen[r.evidence_id] = r
        out.append(r)
    return out


# ----------------------------------------------------------------------------------------
# Exposure triple (task §8): provider availability, deterministic derivability, and packet
# exposure are three different things. V5A conflated them and told Arm A that nothing was
# unavailable while withholding four whole evidence classes.
# ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ExposureTriple:
    dimension: str
    provider_available: bool
    derivable_pit_safe: bool
    exposed_to_llm: str          # one of EXPOSURE_STATES
    note: str = ""
    coverage: Optional[float] = None

    def __post_init__(self):
        if self.exposed_to_llm not in EXPOSURE_STATES:
            raise ValueError(f"exposed_to_llm {self.exposed_to_llm!r} not in "
                             f"{EXPOSURE_STATES}")

    def to_dict(self) -> dict:
        d = {"dimension": self.dimension,
             "PROVIDER_AVAILABLE": self.provider_available,
             "DERIVABLE_PIT_SAFE": self.derivable_pit_safe,
             "EXPOSED_TO_LLM": self.exposed_to_llm,
             "note": self.note}
        if self.coverage is not None:
            d["coverage"] = self.coverage
        return d

    def as_record(self) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=availability_id(self.dimension),
            evidence_type=AVAILABILITY_DECLARATION,
            value=self.exposed_to_llm,
            derivation_type=DECLARATION,
            extra={"PROVIDER_AVAILABLE": self.provider_available,
                   "DERIVABLE_PIT_SAFE": self.derivable_pit_safe,
                   "EXPOSED_TO_LLM": self.exposed_to_llm,
                   "dimension": self.dimension,
                   "note": self.note})


# ----------------------------------------------------------------------------------------
# Resolution -- the arm-neutral half of the fix.
#
# One function, used by validator_v3 AND firewall_v3, for BOTH arms. It walks the packet's
# ordered sections and returns every citable id. There is no arm-specific branch.
# ----------------------------------------------------------------------------------------
def _table_ids(section) -> list:
    """Ids from a RECORD_TABLE section: shared metadata declared once, one compact row per
    record (task §12). The id is always the first column."""
    cols = (section.get("columns") or [])
    if "evidence_id" not in cols:
        return []
    i = cols.index("evidence_id")
    return [row[i] for row in (section.get("rows") or []) if len(row) > i and row[i]]


def resolve_evidence_ids(packet: Optional[dict]) -> set:
    """Every evidence_id a hypothesis may legitimately cite in this packet.

    ONE function, used by validator_v3 AND firewall_v3, for BOTH arms. There is no
    arm-specific branch anywhere in it -- that absence is the HS-1 fix.

    Match rows and summary tables are serialized compactly (shared metadata once, then a
    value matrix), so their cell ids are DERIVED here rather than serialized tens of
    thousands of times. The citation space stays complete without the metadata bloat that
    pushed V5A's real evidence to 11% of the prompt.
    """
    if not packet:
        return set()
    ids: set = set()
    for section in packet.get("sections") or []:
        if section.get("section_type") == "MATCH_LEVEL_OBSERVATIONS":
            for block in (section.get("blocks") or []):
                cols = block.get("cell_columns") or []
                for row in (block.get("rows") or []):
                    rid = row.get("evidence_id")
                    if not rid:
                        continue
                    ids.add(rid)
                    ids.update(f"{rid}:{c}" for c in cols)
        else:
            ids.update(_table_ids(section))
            for rec in (section.get("records") or []):
                if rec.get("evidence_id"):
                    ids.add(rec["evidence_id"])
    return ids


def resolve_evidence_values(packet: Optional[dict]) -> tuple:
    """Every numeric value the packet SUPPLIED, for the firewall's provenance test.

    Arm-neutral by construction. (In V5A the equivalent returned 76 values for Arm A and 0
    for Arm B, because it read a key only Arm A had.)
    """
    if not packet:
        return ()
    out: list = []

    def take(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(float(v))

    for section in packet.get("sections") or []:
        if section.get("section_type") == "MATCH_LEVEL_OBSERVATIONS":
            for block in (section.get("blocks") or []):
                for row in (block.get("rows") or []):
                    for v in (row.get("cells") or []):
                        take(v)
        else:
            # Only the MEASURED FOOTBALL QUANTITIES count as supplied evidence values.
            # Sample sizes (sample_n, baseline_n, cohort_n) and coverage rates are metadata
            # about an estimate, and they are small integers that collide with plausible
            # metric values -- including them would let the firewall label a copied
            # predictive number as "reproduces a packet value" (class B) when it is a
            # class A violation. Both classes block, so this changes labelling accuracy,
            # not enforcement, and it is symmetric across arms either way.
            cols = section.get("columns") or []
            num_idx = [i for i, c in enumerate(cols)
                       if c in ("value", "cohort_value", "baseline_value")]
            for row in (section.get("rows") or []):
                for i in num_idx:
                    if i < len(row):
                        take(row[i])
            for rec in (section.get("records") or []):
                take(rec.get("value"))
    return tuple(out)


def evidence_records_of(packet: Optional[dict]) -> list:
    """Flatten a packet back to record dicts (row cells and table rows expanded). Used by
    the superset proof and the exposure audit, never by the model."""
    if not packet:
        return []
    out: list = []
    for section in packet.get("sections") or []:
        if section.get("section_type") == "MATCH_LEVEL_OBSERVATIONS":
            for block in (section.get("blocks") or []):
                cols = block.get("cell_columns") or []
                for row in (block.get("rows") or []):
                    rid = row.get("evidence_id")
                    out.append(dict({k: v for k, v in row.items() if k != "cells"},
                                    evidence_type=MATCH_OBSERVATION))
                    for c, v in zip(cols, row.get("cells") or []):
                        out.append({"evidence_id": f"{rid}:{c}",
                                    "evidence_type": MATCH_OBSERVATION,
                                    "metric_column": c, "value": v,
                                    "subject": row.get("subject")})
        else:
            cols = section.get("columns") or []
            shared = section.get("shared") or {}
            for row in (section.get("rows") or []):
                out.append(dict(shared, **dict(zip(cols, row))))
            for rec in (section.get("records") or []):
                out.append(dict(rec))
    return out


def serialize(body: dict) -> str:
    """THE serialization. `sort_keys=False`: section order is semantically load-bearing in
    V5A.1 (alphabetical key order is exactly what buried V5A's match rows at 81-96% of the
    prompt), so the hash must pin the order as well as the content. Packet construction is
    deterministic, so the bytes are reproducible."""
    return json.dumps(body, sort_keys=False, separators=(",", ":"), default=str)


def packet_hash(body: dict) -> str:
    clean = {k: v for k, v in body.items() if k != "packet_hash"}
    return hashlib.sha256(serialize(clean).encode()).hexdigest()
