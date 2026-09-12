"""Append-only FINAL settlement for genuine PROSPECTIVE_SHADOW records.

WHAT THIS IS
============
A shadow residual is a frozen, pre-kickoff *model-vs-market* observation. A
movement evaluation records how the market later *moved* (TOWARD/AWAY/FLAT).
Neither says what the match actually did. This module adds the missing,
strictly-downstream axis: once a fixture has reached a canonical final state,
grade the frozen model side into WIN / LOSS / PUSH / VOID against the real
result statistic.

TWO SEPARATE SCIENTIFIC AXES (never collapsed)
==============================================
* market movement   -> TOWARD_MODEL / AWAY_FROM_MODEL / FLAT   (shadow_residual)
* realized outcome  -> WIN / LOSS / PUSH / VOID                (this module)

A settlement is evidence about the *event*; a movement is evidence about the
*market*. They are reported as distinct dimensions and never merged into a
single "model right/wrong" flag.

STRICT DOWNSTREAM / APPEND-ONLY
===============================
This module NEVER mutates a shadow, an evaluation, a forecast commitment, the
frontier, or any historical record. A settlement references a pre-existing,
persisted, VERIFIED prospective shadow by id + payload hash and is written to a
separate append-only ledger. A settlement can never create or upgrade
prospective status: a non-prospective parent is refused before any grading.

FAIL CLOSED
===========
Every eligibility condition and every result-provenance requirement fails
closed. A fixture that has not reached a canonical final state, a missing result
statistic, or a market whose result concept cannot be proven identical to the
market concept produces NO settlement (an explicit ``UNSETTLED_*`` reason is
returned to the caller for observability) rather than a fabricated outcome.

RESEARCH ONLY
=============
Every settlement record carries the frozen research classification
(RESEARCH_ONLY / NOT_VALIDATED / NOT_ACTIONABLE). Nothing here computes ROI,
edge, stake, or a validated signal, and nothing here can reach the consumer
publication path.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.research.prospective.shadow_residual import (
    CLASSIFICATION,
    ShadowProvenanceKind,
    canonical_hash,
)

RECORD_TYPE = "SHADOW_SETTLEMENT"
SETTLEMENT_CONTRACT_VERSION = "shadow-settlement-payload/v1"

#: The result statistic each market is graded against. This is the ONE place
#: the market concept is bound to a result concept; a market absent here is
#: refused (UNSUPPORTED_MARKET) rather than graded against a guessed statistic.
#:
#: These bindings are proven identical to the market key in the audit:
#:   * total_goals  -> final total goals   (score.home + score.away)
#:   * match_corners-> final total corners (corner_kicks home + away)
#:   * total_cards  -> final total cards   (yellow+red, both sides; raw count,
#:                     NOT booking points, NOT yellow-only, NOT reds-weighted)
MARKET_RESULT_STATISTIC: dict[str, str] = {
    "total_goals": "total_goals",
    "match_corners": "total_corners",
    "total_cards": "total_cards",
}


class SettlementOutcome(str, Enum):
    """Realized outcome of the frozen model side. Distinct from movement.

    Mirrors :class:`src.domain.settlement.SettlementOutcome` values (WIN/LOSS/
    PUSH/VOID) so the vocabulary matches the rest of the engine, and adds an
    explicit ``UNSETTLED`` sentinel used only when the caller asks for a reason
    on a parent that could not be graded. ``UNSETTLED`` is NEVER written to the
    ledger — an ungradeable parent produces no settlement record at all.
    """

    WIN = "WIN"
    LOSS = "LOSS"
    PUSH = "PUSH"
    VOID = "VOID"
    UNSETTLED = "UNSETTLED"


class SettlementRefusal(str, Enum):
    """Why a shadow could not be settled (fail-closed, for observability only)."""

    NONE = "NONE"
    PARENT_NOT_FOUND = "PARENT_NOT_FOUND"
    PARENT_NOT_SHADOW_RESIDUAL = "PARENT_NOT_SHADOW_RESIDUAL"
    PARENT_NOT_PROSPECTIVE = "PARENT_NOT_PROSPECTIVE"
    PARENT_NOT_FINALIZED = "PARENT_NOT_FINALIZED"
    COMMITMENT_LINK_UNVERIFIED = "COMMITMENT_LINK_UNVERIFIED"
    INVALID_FIXTURE_IDENTITY = "INVALID_FIXTURE_IDENTITY"
    INVALID_COMPETITION_IDENTITY = "INVALID_COMPETITION_IDENTITY"
    INVALID_MARKET_IDENTITY = "INVALID_MARKET_IDENTITY"
    UNSUPPORTED_MARKET = "UNSUPPORTED_MARKET"
    FIXTURE_NOT_FINAL = "FIXTURE_NOT_FINAL"
    RESULT_STATISTIC_MISSING = "RESULT_STATISTIC_MISSING"
    UNSETTLED_RESULT_SEMANTICS = "UNSETTLED_RESULT_SEMANTICS"


#: Canonical final-fixture states (union of the normalizer's _FINISHED_STATUSES
#: and pilotC_settle._FINISHED, lower-cased). A settlement requires the result
#: provenance to assert one of these; anything else fails closed.
FINAL_FIXTURE_STATES: frozenset[str] = frozenset(
    {"finished", "complete", "completed", "played", "ft", "full-time", "ended"}
)


@dataclass(frozen=True)
class FixtureResult:
    """A canonical, post-event final-result observation for one fixture.

    This is a *value object*: the settlement core never performs I/O. A resolver
    (default: provider + TheStatsAPINormalizer, cache-first) constructs it from
    canonical provider evidence; tests construct it directly. ``status`` must be
    a canonical final state, and each statistic is ``None`` when the provider did
    not supply it (NULL != ZERO), which fails the relevant market closed.
    """

    fixture_id: str
    status: str
    #: Result statistics keyed by the MARKET_RESULT_STATISTIC values. A missing
    #: key or a ``None`` value means "the provider did not report it" and fails
    #: that market closed — never treated as zero.
    statistics: dict[str, Optional[float]] = field(default_factory=dict)
    #: When the final-result evidence was observed (unix). Recorded on the
    #: settlement so a later provider correction is auditable.
    observed_at: Optional[float] = None
    #: Where the final result came from (e.g. "thestatsapi:match_detail+stats").
    source: str = ""

    def is_final(self) -> bool:
        return isinstance(self.status, str) and self.status.strip().lower() in FINAL_FIXTURE_STATES

    def statistic(self, result_key: str) -> Optional[float]:
        v = self.statistics.get(result_key)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None


def grade_over_under(selection: str, line: Optional[float], actual: float) -> SettlementOutcome:
    """Grade an over/under total. Pure; identical semantics to the engine grader.

    Mirrors :meth:`src.domain.factories.SettlementFactory._resolve_outcome`:
      * line is None                 -> VOID
      * OVER : actual > line  -> WIN ; actual == line -> PUSH ; else LOSS
      * UNDER: actual < line  -> WIN ; actual == line -> PUSH ; else LOSS
      * unknown selection            -> VOID

    Integer lines PUSH on an exact tie (e.g. line 3, actual 3); half-lines can
    never tie so only WIN/LOSS. Line semantics are the engine's, not assumed.
    """
    if line is None:
        return SettlementOutcome.VOID
    sel = str(selection).strip().lower()
    if sel == "over":
        if actual > line:
            return SettlementOutcome.WIN
        if actual == line:
            return SettlementOutcome.PUSH
        return SettlementOutcome.LOSS
    if sel == "under":
        if actual < line:
            return SettlementOutcome.WIN
        if actual == line:
            return SettlementOutcome.PUSH
        return SettlementOutcome.LOSS
    return SettlementOutcome.VOID


@dataclass(frozen=True)
class SettlementRefusalError(Exception):
    """Fail-closed refusal carrying the machine-readable reason."""

    reason: SettlementRefusal
    detail: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.reason.value}: {self.detail}"


@dataclass(frozen=True)
class ShadowSettlementRecord:
    """An immutable final-settlement record referencing a prospective shadow."""

    # parent linkage (immutable references; the parent is never mutated)
    shadow_id: str
    shadow_payload_hash: str
    forecast_commitment_hash: str

    # event / market identity (copied verbatim from the parent shadow)
    fixture_id: str
    competition: Optional[str]
    market: str
    selection: str
    line: Optional[float]
    bookmaker: str
    kickoff_ts: Optional[float]

    # frozen model/market context (for reporting; copied from the parent)
    p_model: float
    p_market_devig: float
    model_version: str

    # result + settlement
    final_fixture_state: str
    result_statistic_key: str
    result_statistic_value: float
    settlement_outcome: str
    result_observed_at: Optional[float]
    result_source: str

    # meta
    provenance_kind: str = ShadowProvenanceKind.PROSPECTIVE_SHADOW.value
    record_type: str = RECORD_TYPE
    settlement_contract_version: str = SETTLEMENT_CONTRACT_VERSION
    classification: tuple[str, ...] = CLASSIFICATION
    created_at: float = 0.0
    settlement_id: str = ""

    def identity_fields(self) -> dict[str, Any]:
        """Immutable dedup identity: parent + the exact result graded.

        Depends on the parent shadow, its payload hash, and the final result
        statistic actually used. A repeated run over the same final result
        produces the same ``settlement_id`` (idempotent). A later provider
        *correction* that changes the statistic yields a DIFFERENT id, so it is
        appended as a new record rather than silently overwriting the first.
        """
        return {
            "shadow_id": self.shadow_id,
            "shadow_payload_hash": self.shadow_payload_hash,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "result_statistic_key": self.result_statistic_key,
            "result_statistic_value": self.result_statistic_value,
            "settlement_outcome": self.settlement_outcome,
        }

    def compute_settlement_id(self) -> str:
        return canonical_hash(self.identity_fields())[:32]

    def finalize(self, *, created_at: Optional[float] = None) -> "ShadowSettlementRecord":
        from dataclasses import replace

        return replace(
            self,
            settlement_id=self.compute_settlement_id(),
            created_at=(time.time() if created_at is None else float(created_at)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_type": self.record_type,
            "settlement_contract_version": self.settlement_contract_version,
            "classification": list(self.classification),
            "provenance_kind": self.provenance_kind,
            "settlement_id": self.settlement_id,
            "shadow_id": self.shadow_id,
            "shadow_payload_hash": self.shadow_payload_hash,
            "forecast_commitment_hash": self.forecast_commitment_hash,
            "fixture_id": self.fixture_id,
            "competition": self.competition,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "bookmaker": self.bookmaker,
            "kickoff_ts": self.kickoff_ts,
            "p_model": self.p_model,
            "p_market_devig": self.p_market_devig,
            "model_version": self.model_version,
            "final_fixture_state": self.final_fixture_state,
            "result_statistic_key": self.result_statistic_key,
            "result_statistic_value": self.result_statistic_value,
            "settlement_outcome": self.settlement_outcome,
            "result_observed_at": self.result_observed_at,
            "result_source": self.result_source,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Parent eligibility + settlement construction (pure; no I/O)
# ---------------------------------------------------------------------------

_REQUIRED_CLASSIFICATION = frozenset(CLASSIFICATION)


def check_parent_eligible(
    shadow: dict,
    *,
    valid_commitment_hashes: Optional[frozenset[str]] = None,
) -> None:
    """Fail closed unless ``shadow`` is a genuine, settleable prospective parent.

    Raises :class:`SettlementRefusalError` with a precise reason. ``shadow`` is a
    persisted shadow-record dict (as read from ``shadow_residuals.jsonl``).

    ``valid_commitment_hashes`` (when provided) is the set of forecast commitment
    hashes present in the canonical commitment ledgers; the parent's
    ``forecast_commitment_hash`` must be in it. When ``None`` the linkage check
    is skipped (the caller has already verified it) but never inverted.
    """
    if not isinstance(shadow, dict):
        raise SettlementRefusalError(SettlementRefusal.PARENT_NOT_FOUND, "parent is not a record")
    if shadow.get("record_type") != "SHADOW_RESIDUAL":
        raise SettlementRefusalError(
            SettlementRefusal.PARENT_NOT_SHADOW_RESIDUAL,
            f"parent record_type={shadow.get('record_type')!r}",
        )
    if shadow.get("provenance_kind") != ShadowProvenanceKind.PROSPECTIVE_SHADOW.value:
        # Reconstructed / anything else must NEVER enter prospective settlement.
        raise SettlementRefusalError(
            SettlementRefusal.PARENT_NOT_PROSPECTIVE,
            f"parent provenance_kind={shadow.get('provenance_kind')!r}",
        )
    if not shadow.get("shadow_id") or not shadow.get("shadow_payload_hash"):
        raise SettlementRefusalError(SettlementRefusal.PARENT_NOT_FINALIZED, "missing id/hash")
    if not _REQUIRED_CLASSIFICATION.issubset(set(shadow.get("classification") or [])):
        raise SettlementRefusalError(
            SettlementRefusal.PARENT_NOT_PROSPECTIVE, "parent classification not research-only"
        )
    fch = shadow.get("forecast_commitment_hash")
    if not fch:
        raise SettlementRefusalError(
            SettlementRefusal.COMMITMENT_LINK_UNVERIFIED, "parent has no commitment hash"
        )
    if valid_commitment_hashes is not None and fch not in valid_commitment_hashes:
        raise SettlementRefusalError(
            SettlementRefusal.COMMITMENT_LINK_UNVERIFIED,
            "parent commitment hash not present in canonical commitment ledgers",
        )
    if not shadow.get("fixture_id"):
        raise SettlementRefusalError(SettlementRefusal.INVALID_FIXTURE_IDENTITY, "no fixture_id")
    if not shadow.get("competition"):
        raise SettlementRefusalError(
            SettlementRefusal.INVALID_COMPETITION_IDENTITY, "no competition"
        )
    if not (shadow.get("market") and shadow.get("selection") and shadow.get("line") is not None):
        raise SettlementRefusalError(
            SettlementRefusal.INVALID_MARKET_IDENTITY, "market/selection/line incomplete"
        )
    if shadow.get("market") not in MARKET_RESULT_STATISTIC:
        raise SettlementRefusalError(
            SettlementRefusal.UNSUPPORTED_MARKET,
            f"no canonical result binding for market {shadow.get('market')!r}",
        )


def build_settlement(
    shadow: dict,
    result: FixtureResult,
    *,
    valid_commitment_hashes: Optional[frozenset[str]] = None,
    created_at: Optional[float] = None,
) -> ShadowSettlementRecord:
    """Grade one prospective shadow against a canonical final result.

    Fails closed (raises :class:`SettlementRefusalError`) if the parent is not a
    genuine settleable prospective shadow, the fixture is not final, the required
    result statistic is missing, or the market has no canonical result binding.

    Never mutates ``shadow``. Returns a finalized, idempotent settlement record.
    """
    check_parent_eligible(shadow, valid_commitment_hashes=valid_commitment_hashes)

    if result is None or result.fixture_id != shadow.get("fixture_id"):
        raise SettlementRefusalError(
            SettlementRefusal.INVALID_FIXTURE_IDENTITY, "result fixture mismatch"
        )
    if not result.is_final():
        raise SettlementRefusalError(
            SettlementRefusal.FIXTURE_NOT_FINAL, f"fixture status={result.status!r} not final"
        )

    market = shadow["market"]
    result_key = MARKET_RESULT_STATISTIC.get(market)
    if result_key is None:  # defensive; check_parent_eligible already gated this
        raise SettlementRefusalError(SettlementRefusal.UNSUPPORTED_MARKET, market)

    actual = result.statistic(result_key)
    if actual is None:
        # NULL != ZERO: a missing statistic fails the market closed, never 0.
        raise SettlementRefusalError(
            SettlementRefusal.RESULT_STATISTIC_MISSING,
            f"final {result_key} not reported for fixture {result.fixture_id}",
        )

    outcome = grade_over_under(shadow["selection"], shadow.get("line"), actual)
    if outcome is SettlementOutcome.UNSETTLED:  # pragma: no cover - grader never returns this
        raise SettlementRefusalError(SettlementRefusal.UNSETTLED_RESULT_SEMANTICS, market)

    rec = ShadowSettlementRecord(
        shadow_id=shadow["shadow_id"],
        shadow_payload_hash=shadow["shadow_payload_hash"],
        forecast_commitment_hash=shadow["forecast_commitment_hash"],
        fixture_id=shadow["fixture_id"],
        competition=shadow.get("competition"),
        market=market,
        selection=shadow["selection"],
        line=shadow.get("line"),
        bookmaker=shadow.get("bookmaker", ""),
        kickoff_ts=shadow.get("kickoff_ts"),
        p_model=float(shadow.get("p_model")),
        p_market_devig=float(shadow.get("p_market_devig")),
        model_version=shadow.get("model_version", ""),
        final_fixture_state=str(result.status).strip().lower(),
        result_statistic_key=result_key,
        result_statistic_value=float(actual),
        settlement_outcome=outcome.value,
        result_observed_at=result.observed_at,
        result_source=result.source,
    )
    return rec.finalize(created_at=created_at)
