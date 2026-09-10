"""Immutable prospective SHADOW_RESIDUAL instrumentation (research-only).

This module freezes, at an eligible information cutoff ``T``, the join between

    * a contemporaneous COMMITTED model forecast (``p_model``), and
    * a contemporaneous, de-vigged own market snapshot (``p_market_devig``)

for one exact market key (bookmaker, market, selection, line), together with
their disagreement/residual and full PIT + provenance metadata. Freezing the
candidate up front means later market movement can be evaluated WITHOUT
reconstructing the earlier candidate after the fact.

Everything here is RESEARCH_ONLY / NOT_VALIDATED / NOT_ACTIONABLE. A residual
is a disagreement FEATURE, never "alpha", "edge", or a betting opportunity.

Design constraints honoured (mission "instrumentation only"):
- No model is (re)run. ``p_model`` is read from an already-committed forecast
  record; the shadow references its ``forecast_commitment_hash`` /
  ``model_version`` / ``scope_version_hash``.
- No provider call. Market prices come from the append-only prospective
  capture store (``src.research.prospective.storage.CaptureStore``).
- De-vig reuses the existing engine (``src.research.reconciliation.devig`` via
  ``odds_capture.market_over_probability``). No new de-vig method is invented.
- PIT: the chosen market snapshot must have ``observed_at <= T`` (the existing
  ``ProviderObservation.available_at`` semantics); post-kickoff and future
  snapshots are rejected; no ``last_seen`` timing evidence, no cross-book /
  cross-line / cross-selection substitution.
- No residual thresholding / filtering / bookmaker ranking. Every eligible
  candidate is persisted.

Provenance kind:
- ``PROSPECTIVE_SHADOW``   : created live, prospectively, at/after deployment.
- ``RECONSTRUCTED_SHADOW`` : rebuilt from historical persisted state for tests
  / diagnostics. It MUST NOT be claimed to have been committed at its
  historical cutoff.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.research.prospective.odds_capture import market_over_probability

# --- constants -------------------------------------------------------------

RECORD_TYPE = "SHADOW_RESIDUAL"
PAYLOAD_CONTRACT_VERSION = "shadow-residual-payload/v1"
EVALUATION_CONTRACT_VERSION = "shadow-residual-evaluation/v1"

#: Frozen research classification carried on every record so it can never be
#: mistaken for a validated/actionable signal.
CLASSIFICATION: tuple[str, ...] = ("RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE")

#: Logit clipping consistent with the rest of the prospective research code
#: (see fundamental.py / price_discovery.py use of a 1e-9 epsilon).
_EPS = 1e-9

#: Movement classification when neither TOWARD nor AWAY (no move / degenerate).
_FLAT_EPS = 1e-9


class ShadowProvenanceKind(str, Enum):
    """How a shadow record came to exist. Never conflate these."""

    #: Created live from state that was persisted BEFORE the cutoff, at/after
    #: deployment. This is the only kind that may be treated as prospective.
    PROSPECTIVE_SHADOW = "PROSPECTIVE_SHADOW"
    #: Rebuilt from historical persisted state (tests / diagnostics). Never
    #: claimed to have been frozen live at its historical cutoff.
    RECONSTRUCTED_SHADOW = "RECONSTRUCTED_SHADOW"


class MovementDirection(str, Enum):
    TOWARD_MODEL = "TOWARD_MODEL"
    AWAY_FROM_MODEL = "AWAY_FROM_MODEL"
    FLAT = "FLAT"


def logit(p: float) -> float:
    """Numerically clipped logit, consistent with existing research code."""
    p = min(max(p, _EPS), 1.0 - _EPS)
    return math.log(p / (1.0 - p))


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def canonical_hash(obj: Any) -> str:
    """64-char lowercase SHA-256 over an object's canonical JSON.

    Mirrors ``src.research.prediction_engine.broadcast.scope_config.canonical_hash``
    so shadow provenance hashing matches the repository convention.
    """
    return _sha256(_canonical_json(obj))


# ---------------------------------------------------------------------------
# Inputs (thin, provenance-carrying views over already-persisted state)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ForecastLeg:
    """The committed-forecast side of the join (already persisted; not re-run).

    ``p_model`` is the champion probability of ``selection`` for
    (market, line). The commitment/model/scope hashes are referenced verbatim
    from the source FORECAST_COMMITTED record.
    """

    fixture_id: str
    competition: Optional[str]
    kickoff_ts: Optional[float]
    market: str
    selection: str
    line: Optional[float]
    p_model: float
    generated_at: float
    forecast_commitment_hash: str
    model_version: str
    scope_version_hash: str


@dataclass(frozen=True)
class MarketLeg:
    """The market side of the join for one exact key at one snapshot.

    Carries the RAW paired decimal odds so the de-vig is reproducible, plus the
    snapshot provenance needed to recover the exact captured price.
    """

    fixture_id: str
    provider: str
    bookmaker: str
    market: str
    selection: str
    line: Optional[float]
    over_odds: float
    under_odds: float
    observed_at: float
    retrieved_at: float
    raw_payload_hash: str


# ---------------------------------------------------------------------------
# The immutable shadow record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShadowResidualRecord:
    """A frozen model-vs-market residual candidate at information cutoff T.

    Immutable: later market movement never edits this record; a separate
    :class:`ShadowMovementEvaluation` references it by ``shadow_id`` /
    ``shadow_payload_hash``.
    """

    # identity / event
    fixture_id: str
    competition: Optional[str]
    kickoff_ts: Optional[float]

    # PIT timing
    information_cutoff: float
    generated_at: float
    market_observed_at: float
    market_retrieved_at: float

    # exact market identity
    provider: str
    bookmaker: str
    market: str
    selection: str
    line: Optional[float]

    # probabilities
    p_model: float
    raw_over_odds: float
    raw_under_odds: float
    raw_implied_probability: float
    p_market_devig: float
    devig_method: str

    # residuals (both persisted; no thresholding)
    raw_probability_residual: float
    logit_residual: float

    # forecast provenance
    forecast_commitment_hash: str
    model_version: str
    scope_version_hash: str

    # market provenance
    market_snapshot_hash: str

    # record meta
    provenance_kind: str
    record_type: str = RECORD_TYPE
    payload_contract_version: str = PAYLOAD_CONTRACT_VERSION
    classification: tuple[str, ...] = CLASSIFICATION
    created_at: float = 0.0
    shadow_id: str = ""
    shadow_payload_hash: str = ""

    # -- deterministic identity ------------------------------------------

    def identity_fields(self) -> dict[str, Any]:
        """The fields that define the LOGICAL candidate (dedup identity).

        A repeated run over unchanged state produces the same ``shadow_id``:
        it depends only on the fixture, the exact market key, the referenced
        forecast commitment, and the market snapshot instant. It deliberately
        excludes wall-clock ``created_at`` so idempotency holds across runs.
        """
        return {
            "fixture_id": self.fixture_id,
            "bookmaker": self.bookmaker,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "forecast_commitment_hash": self.forecast_commitment_hash,
            "market_observed_at": self.market_observed_at,
            "information_cutoff": self.information_cutoff,
        }

    def compute_shadow_id(self) -> str:
        return canonical_hash(self.identity_fields())[:32]

    def _payload_for_hash(self) -> dict[str, Any]:
        """Everything scientific about the candidate (excludes created_at)."""
        return {
            "record_type": self.record_type,
            "payload_contract_version": self.payload_contract_version,
            "classification": list(self.classification),
            "provenance_kind": self.provenance_kind,
            "fixture_id": self.fixture_id,
            "competition": self.competition,
            "kickoff_ts": self.kickoff_ts,
            "information_cutoff": self.information_cutoff,
            "generated_at": self.generated_at,
            "market_observed_at": self.market_observed_at,
            "market_retrieved_at": self.market_retrieved_at,
            "provider": self.provider,
            "bookmaker": self.bookmaker,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "p_model": self.p_model,
            "raw_over_odds": self.raw_over_odds,
            "raw_under_odds": self.raw_under_odds,
            "raw_implied_probability": self.raw_implied_probability,
            "p_market_devig": self.p_market_devig,
            "devig_method": self.devig_method,
            "raw_probability_residual": self.raw_probability_residual,
            "logit_residual": self.logit_residual,
            "forecast_commitment_hash": self.forecast_commitment_hash,
            "model_version": self.model_version,
            "scope_version_hash": self.scope_version_hash,
            "market_snapshot_hash": self.market_snapshot_hash,
            "shadow_id": self.shadow_id,
        }

    def compute_payload_hash(self) -> str:
        return canonical_hash(self._payload_for_hash())

    def finalize(self, *, created_at: Optional[float] = None) -> "ShadowResidualRecord":
        """Return a copy with ``shadow_id``, ``shadow_payload_hash``, created_at set.

        ``shadow_id`` is computed first (identity), then embedded in the payload
        hash so the payload hash also commits to the id.
        """
        from dataclasses import replace

        sid = self.compute_shadow_id()
        stamped = replace(
            self,
            shadow_id=sid,
            created_at=(time.time() if created_at is None else float(created_at)),
        )
        return replace(stamped, shadow_payload_hash=stamped.compute_payload_hash())

    def to_dict(self) -> dict[str, Any]:
        d = self._payload_for_hash()
        d["created_at"] = self.created_at
        d["shadow_payload_hash"] = self.shadow_payload_hash
        return d


class ShadowJoinError(ValueError):
    """Raised when a shadow candidate cannot be legitimately constructed."""


def _market_snapshot_hash(m: MarketLeg) -> str:
    """Deterministic hash pinning the exact captured price used."""
    return canonical_hash(
        {
            "provider": m.provider,
            "bookmaker": m.bookmaker,
            "market": m.market,
            "selection": m.selection,
            "line": m.line,
            "over_odds": m.over_odds,
            "under_odds": m.under_odds,
            "observed_at": m.observed_at,
            "raw_payload_hash": m.raw_payload_hash,
        }
    )[:32]


def build_shadow_residual(
    *,
    forecast: ForecastLeg,
    market: MarketLeg,
    information_cutoff: float,
    provenance_kind: ShadowProvenanceKind,
    devig_method: str = "multiplicative",
    created_at: Optional[float] = None,
) -> ShadowResidualRecord:
    """Freeze one shadow-residual candidate at ``information_cutoff`` (=T).

    PIT join rule (fails closed):
      * ``forecast.generated_at <= T``            (model available by T)
      * ``market.observed_at   <= T``             (price available by T)
      * ``market.observed_at   < kickoff``        (pre-kickoff; no post-KO price)
      * exact key match on fixture/market/selection/line between the two legs
        (canonical ids only; never display-name joins).

    De-vig uses the existing engine; the residual is p_model - p_market_devig
    (and the logit form), with NO thresholding.
    """
    # --- exact-key alignment (canonical identity; no name joins) ---
    if forecast.fixture_id != market.fixture_id:
        raise ShadowJoinError("fixture identity mismatch; refusing cross-fixture join")
    if forecast.market != market.market:
        raise ShadowJoinError("market mismatch; refusing cross-market join")
    if forecast.selection != market.selection:
        raise ShadowJoinError("selection mismatch; refusing cross-selection join")
    if forecast.line != market.line:
        raise ShadowJoinError("line mismatch; refusing cross-line join")

    # --- PIT timing gates ---
    if forecast.generated_at > information_cutoff:
        raise ShadowJoinError("forecast generated_at is after the information cutoff")
    if market.observed_at > information_cutoff:
        raise ShadowJoinError("market snapshot observed_at is after the information cutoff")
    if forecast.kickoff_ts is not None and market.observed_at >= forecast.kickoff_ts:
        raise ShadowJoinError("market snapshot is not strictly pre-kickoff")

    # --- de-vig (existing engine); raw implied for provenance/audit ---
    p_over = market_over_probability(market.over_odds, market.under_odds, method=devig_method)
    p_devig = p_over if market.selection == "over" else 1.0 - p_over
    if not (0.0 < p_devig < 1.0):
        raise ShadowJoinError("de-vigged market probability is degenerate")
    sel_odds = market.over_odds if market.selection == "over" else market.under_odds
    raw_implied = 1.0 / sel_odds

    raw_resid = forecast.p_model - p_devig
    logit_resid = logit(forecast.p_model) - logit(p_devig)

    rec = ShadowResidualRecord(
        fixture_id=forecast.fixture_id,
        competition=forecast.competition,
        kickoff_ts=forecast.kickoff_ts,
        information_cutoff=float(information_cutoff),
        generated_at=float(forecast.generated_at),
        market_observed_at=float(market.observed_at),
        market_retrieved_at=float(market.retrieved_at),
        provider=market.provider,
        bookmaker=market.bookmaker,
        market=market.market,
        selection=market.selection,
        line=market.line,
        p_model=float(forecast.p_model),
        raw_over_odds=float(market.over_odds),
        raw_under_odds=float(market.under_odds),
        raw_implied_probability=float(raw_implied),
        p_market_devig=float(p_devig),
        devig_method=devig_method,
        raw_probability_residual=float(raw_resid),
        logit_residual=float(logit_resid),
        forecast_commitment_hash=forecast.forecast_commitment_hash,
        model_version=forecast.model_version,
        scope_version_hash=forecast.scope_version_hash,
        market_snapshot_hash=_market_snapshot_hash(market),
        provenance_kind=provenance_kind.value,
    )
    return rec.finalize(created_at=created_at)


# ---------------------------------------------------------------------------
# Later movement evaluation (separate, append-only, references the shadow)
# ---------------------------------------------------------------------------


def classify_movement(
    *,
    raw_probability_residual: float,
    p_market_earlier: float,
    p_market_later: float,
) -> MovementDirection:
    """Direction of later market movement relative to the model's disagreement.

    TOWARD_MODEL  : the market moved in the SAME direction as the earlier
                    residual sign (model was higher -> market rose; model was
                    lower -> market fell).
    AWAY_FROM_MODEL: the market moved opposite the residual sign.
    FLAT          : no move (or residual sign is zero -> no direction to test).

    This is research evidence, NOT betting profit and NOT alpha.
    """
    move = p_market_later - p_market_earlier
    if abs(move) <= _FLAT_EPS or abs(raw_probability_residual) <= _FLAT_EPS:
        return MovementDirection.FLAT
    same_direction = (raw_probability_residual > 0) == (move > 0)
    return MovementDirection.TOWARD_MODEL if same_direction else MovementDirection.AWAY_FROM_MODEL


@dataclass(frozen=True)
class ShadowMovementEvaluation:
    """A later same-key market observation evaluated against a frozen shadow.

    References the immutable shadow by id + payload hash; NEVER mutates it.
    """

    shadow_id: str
    shadow_payload_hash: str

    fixture_id: str
    bookmaker: str
    market: str
    selection: str
    line: Optional[float]

    p_market_earlier: float
    later_observed_at: float
    later_market_devig: float
    later_market_snapshot_hash: str

    delta_probability: float
    delta_logit: float
    movement_direction: str

    record_type: str = "SHADOW_RESIDUAL_EVALUATION"
    evaluation_contract_version: str = EVALUATION_CONTRACT_VERSION
    classification: tuple[str, ...] = CLASSIFICATION
    created_at: float = 0.0
    evaluation_id: str = ""

    def identity_fields(self) -> dict[str, Any]:
        return {
            "shadow_id": self.shadow_id,
            "shadow_payload_hash": self.shadow_payload_hash,
            "later_observed_at": self.later_observed_at,
            "later_market_snapshot_hash": self.later_market_snapshot_hash,
        }

    def compute_evaluation_id(self) -> str:
        return canonical_hash(self.identity_fields())[:32]

    def finalize(self, *, created_at: Optional[float] = None) -> "ShadowMovementEvaluation":
        from dataclasses import replace

        return replace(
            self,
            evaluation_id=self.compute_evaluation_id(),
            created_at=(time.time() if created_at is None else float(created_at)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_type": self.record_type,
            "evaluation_contract_version": self.evaluation_contract_version,
            "classification": list(self.classification),
            "evaluation_id": self.evaluation_id,
            "shadow_id": self.shadow_id,
            "shadow_payload_hash": self.shadow_payload_hash,
            "fixture_id": self.fixture_id,
            "bookmaker": self.bookmaker,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "p_market_earlier": self.p_market_earlier,
            "later_observed_at": self.later_observed_at,
            "later_market_devig": self.later_market_devig,
            "later_market_snapshot_hash": self.later_market_snapshot_hash,
            "delta_probability": self.delta_probability,
            "delta_logit": self.delta_logit,
            "movement_direction": self.movement_direction,
            "created_at": self.created_at,
        }


def build_movement_evaluation(
    *,
    shadow: ShadowResidualRecord,
    later_market: MarketLeg,
    information_cutoff_later: Optional[float] = None,
    devig_method: Optional[str] = None,
    created_at: Optional[float] = None,
) -> ShadowMovementEvaluation:
    """Evaluate later same-key market movement against a frozen shadow.

    Requires the SAME bookmaker+market+selection+line as the shadow, and a
    strictly later ``observed_at``. Uses the shadow's own de-vig method so the
    two probabilities are comparable. Never mutates the shadow.
    """
    if shadow.shadow_id == "" or shadow.shadow_payload_hash == "":
        raise ShadowJoinError("shadow record is not finalized (missing id/hash)")
    # exact-key continuity
    if (
        shadow.fixture_id != later_market.fixture_id
        or shadow.bookmaker != later_market.bookmaker
        or shadow.market != later_market.market
        or shadow.selection != later_market.selection
        or shadow.line != later_market.line
    ):
        raise ShadowJoinError("later market key differs; refusing cross-key movement")
    if later_market.observed_at <= shadow.market_observed_at:
        raise ShadowJoinError("later market snapshot is not strictly later than the shadow")
    if shadow.kickoff_ts is not None and later_market.observed_at >= shadow.kickoff_ts:
        raise ShadowJoinError("later market snapshot is not strictly pre-kickoff")

    method = devig_method or shadow.devig_method
    p_over = market_over_probability(
        later_market.over_odds, later_market.under_odds, method=method
    )
    p_later = p_over if later_market.selection == "over" else 1.0 - p_over
    if not (0.0 < p_later < 1.0):
        raise ShadowJoinError("later de-vigged market probability is degenerate")

    delta_p = p_later - shadow.p_market_devig
    delta_l = logit(p_later) - logit(shadow.p_market_devig)
    direction = classify_movement(
        raw_probability_residual=shadow.raw_probability_residual,
        p_market_earlier=shadow.p_market_devig,
        p_market_later=p_later,
    )

    return ShadowMovementEvaluation(
        shadow_id=shadow.shadow_id,
        shadow_payload_hash=shadow.shadow_payload_hash,
        fixture_id=shadow.fixture_id,
        bookmaker=shadow.bookmaker,
        market=shadow.market,
        selection=shadow.selection,
        line=shadow.line,
        p_market_earlier=shadow.p_market_devig,
        later_observed_at=float(later_market.observed_at),
        later_market_devig=float(p_later),
        later_market_snapshot_hash=_market_snapshot_hash(later_market),
        delta_probability=float(delta_p),
        delta_logit=float(delta_l),
        movement_direction=direction.value,
    ).finalize(created_at=created_at)
