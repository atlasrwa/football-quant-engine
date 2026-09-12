"""Canonical Model Thesis projection (DERIVED, read-only research analysis).

WHY THIS EXISTS
===============
The prospective evidence set stores BOTH sides of a two-sided over/under market
for the same fixture / market / line / bookmaker / cutoff (an ``over`` shadow AND
an ``under`` shadow, built from the same forecast commitment). Their model and
market probabilities are exact complements, so their settlements are mechanically
balanced (one side WIN implies the other LOSS). Counting both tells us nothing
about whether the model's *actual disagreement* with the market performed.

This module projects each paired snapshot down to the ONE side the model
preferred at freeze time — the canonical model thesis — so downstream analysis
counts the model's real position once, not the arithmetic identity of a
complementary pair.

STRICTLY DERIVED / READ-ONLY
============================
Nothing here mutates or deletes a shadow, evaluation, close, commitment, or
settlement. Both paired sides remain in their canonical ledgers untouched; the
thesis is a projection *over* them, fully reproducible from the parents. A thesis
is research evidence only: MODEL_THESIS != VALIDATED_SIGNAL. No stake, EV, ROI,
edge threshold, or signal promotion is produced.

FROZEN-INFORMATION ONLY FOR SIDE SELECTION
==========================================
The preferred side is chosen exclusively from the frozen pre-kickoff
``p_model`` vs ``p_market_devig`` on the parent shadows. No close, movement, or
result information influences which side is preferred. Close direction and
settlement are attached AFTER, as observed consequences of that frozen thesis.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional

from src.research.prospective.shadow_residual import (
    CLASSIFICATION,
    _FLAT_EPS,
    canonical_hash,
)

PROJECTION_VERSION = "model-thesis-projection/v1"
RECORD_TYPE = "MODEL_THESIS"

#: Numerical-equality tolerance for "no material disagreement". Reuses the SAME
#: epsilon the movement classifier uses (shadow_residual._FLAT_EPS = 1e-9). This
#: is a numerical-equality tolerance, NOT a betting/edge threshold: it only says
#: the two frozen probabilities are indistinguishable, so no side is preferred.
NEUTRAL_EPS = _FLAT_EPS


class ThesisClassification(str, Enum):
    """Whether a paired snapshot yields a canonical model-preferred side."""

    MODEL_PREFERS_SIDE = "MODEL_PREFERS_SIDE"
    NO_MATERIAL_DISAGREEMENT = "NO_MATERIAL_DISAGREEMENT"
    AMBIGUOUS = "AMBIGUOUS"
    INELIGIBLE = "INELIGIBLE"


class ThesisExclusionReason(str, Enum):
    """Why a group did not yield a MODEL_PREFERS_SIDE thesis (fail-closed)."""

    NONE = "NONE"
    MISSING_SIDE = "MISSING_SIDE"
    NOT_TWO_SIDED = "NOT_TWO_SIDED"
    DUPLICATE_SIDE = "DUPLICATE_SIDE"
    UNSUPPORTED_MULTIWAY = "UNSUPPORTED_MULTIWAY"
    NON_PROSPECTIVE_PARENT = "NON_PROSPECTIVE_PARENT"
    MISSING_COMMITMENT_LINK = "MISSING_COMMITMENT_LINK"
    MALFORMED_PROBABILITY = "MALFORMED_PROBABILITY"
    CONTRADICTORY_PAIR = "CONTRADICTORY_PAIR"
    AMBIGUOUS_PREFERENCE = "AMBIGUOUS_PREFERENCE"
    NO_MATERIAL_DISAGREEMENT = "NO_MATERIAL_DISAGREEMENT"


class CloseDirection(str, Enum):
    """Where the genuine closing market moved relative to the preferred side."""

    FINAL_TOWARD_MODEL = "FINAL_TOWARD_MODEL"
    FINAL_AWAY_FROM_MODEL = "FINAL_AWAY_FROM_MODEL"
    FINAL_FLAT = "FINAL_FLAT"
    NO_CLOSE = "NO_CLOSE"


#: The complementary pairs this projection supports. A market/selection space
#: outside this is refused (UNSUPPORTED_MULTIWAY) rather than guessed.
_COMPLEMENT = {"over": "under", "under": "over"}


def _is_probability(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 < float(v) < 1.0


def grouping_key(shadow: dict) -> tuple:
    """Canonical bookmaker-specific grouping key for a paired snapshot.

    A thesis is one model position per exact frozen market observation:

        fixture x competition x market x line x bookmaker
            x information_cutoff x market_observed_at x forecast_commitment_hash

    Bookmaker and cutoff are part of the key because the same fixture-market-line
    legitimately carries several bookmakers and several cutoffs (proven from live
    data); merging them would either mistake different books for one observation
    or mix pre-kickoff vintages. The commitment hash is included so two forecasts
    for the same fixture never merge.
    """
    return (
        shadow.get("fixture_id"),
        shadow.get("competition"),
        shadow.get("market"),
        shadow.get("line"),
        shadow.get("bookmaker"),
        round(float(shadow.get("information_cutoff")), 6)
        if shadow.get("information_cutoff") is not None
        else None,
        round(float(shadow.get("market_observed_at")), 6)
        if shadow.get("market_observed_at") is not None
        else None,
        shadow.get("forecast_commitment_hash"),
    )


@dataclass(frozen=True)
class ModelThesis:
    """One canonical model thesis derived from a paired market snapshot."""

    thesis_id: str
    fixture_id: str
    competition_id: Optional[str]
    market: str
    line: Optional[float]
    information_cutoff: float
    market_observed_at: float
    kickoff_ts: Optional[float]
    bookmaker: str

    preferred_selection: str
    opposite_selection: str
    p_model_preferred: float
    p_market_preferred: float
    edge_pp: float  # (p_model_preferred - p_market_preferred) * 100, always > 0

    preferred_shadow_id: str
    opposite_shadow_id: Optional[str]
    forecast_commitment_hash: str
    model_version: str

    # attached AFTER side selection (observed consequences, never inputs to it)
    close_p_market_preferred: Optional[float] = None
    close_delta_pp: Optional[float] = None
    close_direction: str = CloseDirection.NO_CLOSE.value
    settlement_outcome: str = "PENDING"  # WIN/LOSS/PUSH/VOID/PENDING
    result_statistic_value: Optional[float] = None

    classification: tuple[str, ...] = CLASSIFICATION
    thesis_classification: str = ThesisClassification.MODEL_PREFERS_SIDE.value
    record_type: str = RECORD_TYPE
    projection_version: str = PROJECTION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_type": self.record_type,
            "projection_version": self.projection_version,
            "classification": list(self.classification),
            "thesis_classification": self.thesis_classification,
            "thesis_id": self.thesis_id,
            "fixture_id": self.fixture_id,
            "competition_id": self.competition_id,
            "market": self.market,
            "line": self.line,
            "information_cutoff": self.information_cutoff,
            "market_observed_at": self.market_observed_at,
            "kickoff_ts": self.kickoff_ts,
            "bookmaker": self.bookmaker,
            "preferred_selection": self.preferred_selection,
            "opposite_selection": self.opposite_selection,
            "p_model_preferred": self.p_model_preferred,
            "p_market_preferred": self.p_market_preferred,
            "edge_pp": self.edge_pp,
            "preferred_shadow_id": self.preferred_shadow_id,
            "opposite_shadow_id": self.opposite_shadow_id,
            "forecast_commitment_hash": self.forecast_commitment_hash,
            "model_version": self.model_version,
            "close_p_market_preferred": self.close_p_market_preferred,
            "close_delta_pp": self.close_delta_pp,
            "close_direction": self.close_direction,
            "settlement_outcome": self.settlement_outcome,
            "result_statistic_value": self.result_statistic_value,
        }


@dataclass(frozen=True)
class ThesisResult:
    """Outcome of projecting one group: a thesis, or an explicit exclusion."""

    classification: ThesisClassification
    reason: ThesisExclusionReason
    thesis: Optional[ModelThesis]
    #: group identity for diagnostics even when excluded
    fixture_id: Optional[str]
    market: Optional[str]
    line: Optional[float]
    bookmaker: Optional[str]


def _valid_prospective_parent(s: dict, valid_hashes: Optional[frozenset[str]]) -> Optional[ThesisExclusionReason]:
    if s.get("record_type") != "SHADOW_RESIDUAL":
        return ThesisExclusionReason.NON_PROSPECTIVE_PARENT
    if s.get("provenance_kind") != "PROSPECTIVE_SHADOW":
        return ThesisExclusionReason.NON_PROSPECTIVE_PARENT
    if not frozenset(CLASSIFICATION).issubset(set(s.get("classification") or [])):
        return ThesisExclusionReason.NON_PROSPECTIVE_PARENT
    fch = s.get("forecast_commitment_hash")
    if not fch:
        return ThesisExclusionReason.MISSING_COMMITMENT_LINK
    if valid_hashes is not None and fch not in valid_hashes:
        return ThesisExclusionReason.MISSING_COMMITMENT_LINK
    if not _is_probability(s.get("p_model")) or not _is_probability(s.get("p_market_devig")):
        return ThesisExclusionReason.MALFORMED_PROBABILITY
    if s.get("selection") not in _COMPLEMENT:
        return ThesisExclusionReason.UNSUPPORTED_MULTIWAY
    return None


def project_group(
    members: list[dict],
    *,
    valid_commitment_hashes: Optional[frozenset[str]] = None,
) -> ThesisResult:
    """Reduce one grouping-key set of shadows to a canonical model thesis.

    Fails closed with an explicit reason for: missing side, not-two-sided,
    duplicate side, multiway, non-prospective parent, malformed probability,
    contradictory pair, ambiguous (exactly equal) preference, or numerically
    equal (no material disagreement). Side selection uses ONLY frozen
    ``p_model`` vs ``p_market_devig``.
    """
    fx = members[0].get("fixture_id") if members else None
    mk = members[0].get("market") if members else None
    ln = members[0].get("line") if members else None
    bk = members[0].get("bookmaker") if members else None

    def excluded(cl: ThesisClassification, reason: ThesisExclusionReason) -> ThesisResult:
        return ThesisResult(cl, reason, None, fx, mk, ln, bk)

    # parent validity first (any bad member fails the whole group closed)
    for s in members:
        bad = _valid_prospective_parent(s, valid_commitment_hashes)
        if bad is not None:
            cl = (
                ThesisClassification.INELIGIBLE
                if bad != ThesisExclusionReason.UNSUPPORTED_MULTIWAY
                else ThesisClassification.INELIGIBLE
            )
            return excluded(cl, bad)

    sels = [s.get("selection") for s in members]
    if len(members) == 1:
        return excluded(ThesisClassification.INELIGIBLE, ThesisExclusionReason.MISSING_SIDE)
    if len(members) > 2:
        return excluded(ThesisClassification.INELIGIBLE, ThesisExclusionReason.NOT_TWO_SIDED)
    if len(set(sels)) != 2:
        return excluded(ThesisClassification.INELIGIBLE, ThesisExclusionReason.DUPLICATE_SIDE)
    if set(sels) != {"over", "under"}:
        return excluded(ThesisClassification.INELIGIBLE, ThesisExclusionReason.UNSUPPORTED_MULTIWAY)

    by = {s["selection"]: s for s in members}
    over, under = by["over"], by["under"]

    # sanity: a legitimate two-sided market has (near-)complementary probabilities.
    # A pair that is not complementary is contradictory (fail closed).
    if abs(over["p_model"] + under["p_model"] - 1.0) > 1e-6:
        return excluded(ThesisClassification.INELIGIBLE, ThesisExclusionReason.CONTRADICTORY_PAIR)
    if abs(over["p_market_devig"] + under["p_market_devig"] - 1.0) > 1e-6:
        return excluded(ThesisClassification.INELIGIBLE, ThesisExclusionReason.CONTRADICTORY_PAIR)

    edge_over = over["p_model"] - over["p_market_devig"]
    edge_under = under["p_model"] - under["p_market_devig"]

    # neutral: model and market indistinguishable on both sides
    if abs(edge_over) <= NEUTRAL_EPS:
        return excluded(
            ThesisClassification.NO_MATERIAL_DISAGREEMENT,
            ThesisExclusionReason.NO_MATERIAL_DISAGREEMENT,
        )
    # ambiguous: neither side strictly positive (should not happen for a
    # complementary pair, but fail closed rather than guess)
    if (edge_over > 0) == (edge_under > 0):
        return excluded(
            ThesisClassification.AMBIGUOUS, ThesisExclusionReason.AMBIGUOUS_PREFERENCE
        )

    preferred, opposite = (over, under) if edge_over > 0 else (under, over)
    edge_pp = (preferred["p_model"] - preferred["p_market_devig"]) * 100.0

    ident = {
        "fixture_id": preferred["fixture_id"],
        "market": preferred["market"],
        "line": preferred["line"],
        "bookmaker": preferred["bookmaker"],
        "information_cutoff": preferred["information_cutoff"],
        "market_observed_at": preferred["market_observed_at"],
        "forecast_commitment_hash": preferred["forecast_commitment_hash"],
        "preferred_selection": preferred["selection"],
        "projection_version": PROJECTION_VERSION,
    }
    thesis = ModelThesis(
        thesis_id=canonical_hash(ident)[:32],
        fixture_id=preferred["fixture_id"],
        competition_id=preferred.get("competition"),
        market=preferred["market"],
        line=preferred.get("line"),
        information_cutoff=float(preferred["information_cutoff"]),
        market_observed_at=float(preferred["market_observed_at"]),
        kickoff_ts=preferred.get("kickoff_ts"),
        bookmaker=preferred.get("bookmaker", ""),
        preferred_selection=preferred["selection"],
        opposite_selection=opposite["selection"],
        p_model_preferred=float(preferred["p_model"]),
        p_market_preferred=float(preferred["p_market_devig"]),
        edge_pp=float(edge_pp),
        preferred_shadow_id=preferred["shadow_id"],
        opposite_shadow_id=opposite.get("shadow_id"),
        forecast_commitment_hash=preferred["forecast_commitment_hash"],
        model_version=preferred.get("model_version", ""),
    )
    return ThesisResult(
        ThesisClassification.MODEL_PREFERS_SIDE, ThesisExclusionReason.NONE, thesis, fx, mk, ln, bk
    )


def project_theses(
    shadows: Iterable[dict],
    *,
    valid_commitment_hashes: Optional[frozenset[str]] = None,
) -> tuple[list[ThesisResult], dict[str, int]]:
    """Project all shadows into canonical theses grouped by the canonical key.

    Returns ``(results, summary_counts)``. ``results`` has one entry per group
    (thesis or explicit exclusion); ``summary_counts`` tallies classifications
    and exclusion reasons. Deterministic (results sorted by thesis/group key).
    """
    from collections import defaultdict

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for s in shadows:
        groups[grouping_key(s)].append(s)

    results: list[ThesisResult] = []
    counts: dict[str, int] = defaultdict(int)
    for _, members in groups.items():
        r = project_group(members, valid_commitment_hashes=valid_commitment_hashes)
        results.append(r)
        counts[r.classification.value] += 1
        if r.classification is not ThesisClassification.MODEL_PREFERS_SIDE:
            counts[f"reason:{r.reason.value}"] += 1

    results.sort(
        key=lambda r: (
            r.thesis.thesis_id if r.thesis else "",
            r.fixture_id or "",
            r.market or "",
            str(r.line),
            r.bookmaker or "",
        )
    )
    return results, dict(sorted(counts.items()))
