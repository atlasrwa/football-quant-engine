"""Experimental Picks — presentation-layer foundation (NOT enabled for consumers).

This module is preparation for a SEPARATE, future consumer-facing "Experimental
Picks" Telegram channel. It adds three small, deterministic pieces and NOTHING
that publishes to consumers:

1. :class:`ExperimentalPublicationState` + :func:`resolve_experimental_publication_state`
   — an INDEPENDENT publication boundary (``EXPERIMENTAL_PUBLICATION_STATE``),
   defaulting to ``OFF``. It is deliberately NOT the validated-signal boundary
   (``SIGNAL_PUBLICATION_STATE`` in :mod:`src.research._data_accumulation_mode`)
   and must never be conflated with it.

2. :class:`ExperimentalPick` — a pure presentation PROJECTION derived ONLY from
   a valid, publishable PROSPECTIVE shadow-residual record. It creates NO new
   scientific evidence, never mutates the shadow, and FAILS CLOSED (raises)
   rather than fabricating or defaulting any field.

3. :func:`render_experimental_pick` — a pure consumer renderer producing the
   consumer Telegram copy. It performs NO sending.

Hard boundaries preserved by this module:
- A pick may only ever be built from a ``PROSPECTIVE_SHADOW`` record that passes
  the existing :func:`shadow_feed.is_publishable_shadow` gate. A
  ``RECONSTRUCTED_SHADOW`` (or malformed record) can NEVER become a pick.
- No odds-derived EV / ROI is computed or exposed. The model-vs-market
  difference is surfaced as a neutral "gap" in percentage points — never called
  "edge" or "EV".
- Publication requires BOTH (a) a scientifically eligible prospective record AND
  (b) a publication state that allows it. The state can NEVER override
  scientific eligibility (see :func:`can_publish_experimental_picks`).
- The current research monitor is unaffected: it does not consult this module,
  and this module does not change any research message.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

# Reuse the EXISTING publishability gate (provenance + scientific-field
# validation). We never re-implement or weaken it here.
from src.research.prospective.shadow_feed import (
    PROSPECTIVE_PROVENANCE,
    is_publishable_shadow,
)

# ---------------------------------------------------------------------------
# Consumer publication state (INDEPENDENT of SIGNAL_PUBLICATION_STATE)
# ---------------------------------------------------------------------------

#: Environment variable controlling the Experimental Picks consumer channel.
#: This is a SEPARATE boundary from ``SIGNAL_PUBLICATION_STATE`` (validated
#: signals). Keep the two concepts distinct: research-candidate publication is
#: never validated-signal promotion.
EXPERIMENTAL_PUBLICATION_ENV = "EXPERIMENTAL_PUBLICATION_STATE"


class ExperimentalPublicationState(str, Enum):
    """Consumer-publication authorization for Experimental Picks.

    ``OFF`` is the safe default for every unrecognized input. ``BETA`` and
    ``PUBLIC`` exist as forward-looking states; this PR does not implement a
    full consumer channel for them.
    """

    OFF = "OFF"
    BETA = "BETA"
    PUBLIC = "PUBLIC"


def resolve_experimental_publication_state() -> ExperimentalPublicationState:
    """Resolve the Experimental Picks publication state (fail closed to OFF).

    Only the exact tokens ``BETA`` / ``PUBLIC`` (case-insensitive, trimmed)
    yield those states. Unset / empty / malformed / unknown => ``OFF``. This is
    the single seam a future consumer channel would consult; it never reads
    ``SIGNAL_PUBLICATION_STATE``.
    """
    raw = os.environ.get(EXPERIMENTAL_PUBLICATION_ENV)
    if raw is None:
        return ExperimentalPublicationState.OFF
    val = raw.strip().upper()
    if val == ExperimentalPublicationState.PUBLIC.value:
        return ExperimentalPublicationState.PUBLIC
    if val == ExperimentalPublicationState.BETA.value:
        return ExperimentalPublicationState.BETA
    return ExperimentalPublicationState.OFF


def experimental_publication_enabled() -> bool:
    """Whether the publication STATE alone permits any Experimental Pick message.

    ``OFF`` => False (no message may ever be sent). ``BETA`` / ``PUBLIC`` => True
    at the STATE level only. This is NOT sufficient on its own to publish: a
    scientifically eligible prospective record is ALSO required (see
    :func:`can_publish_experimental_pick`).
    """
    return resolve_experimental_publication_state() is not ExperimentalPublicationState.OFF


# ---------------------------------------------------------------------------
# Fail-closed field access (no fabricated / defaulted scientific values)
# ---------------------------------------------------------------------------


class ExperimentalPickError(ValueError):
    """Raised when a pick cannot be legitimately projected from a record.

    Every failure mode fails CLOSED: a reconstructed source, missing forecast
    provenance, a malformed probability, a missing/invalid timestamp, an invalid
    bookmaker/market identity, or a fake zero default all raise rather than
    produce a fabricated pick.
    """


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _is_probability(value: Any) -> bool:
    return _is_finite_number(value) and 0.0 < float(value) < 1.0


def _req_str(record: dict, key: str) -> str:
    v = record.get(key)
    if not isinstance(v, str) or v.strip() == "":
        raise ExperimentalPickError(f"missing/invalid text field {key!r}")
    return v.strip()


def _req_prob(record: dict, key: str) -> float:
    v = record.get(key)
    if not _is_probability(v):
        raise ExperimentalPickError(f"missing/invalid probability field {key!r}")
    return float(v)


def _req_num(record: dict, key: str) -> float:
    v = record.get(key)
    if not _is_finite_number(v):
        raise ExperimentalPickError(f"missing/invalid numeric field {key!r}")
    return float(v)


def _req_odds(record: dict, key: str) -> float:
    v = record.get(key)
    # Decimal odds must be a finite number strictly greater than 1.0. A zero /
    # negative / <=1.0 value is never a valid locked price (fail closed; never a
    # fabricated 0.0).
    if not _is_finite_number(v) or float(v) <= 1.0:
        raise ExperimentalPickError(f"missing/invalid decimal-odds field {key!r}")
    return float(v)


# ---------------------------------------------------------------------------
# The presentation projection
# ---------------------------------------------------------------------------


#: Classification constants carried on every pick (never inferred, never
#: mistaken for a validated/actionable signal).
_CLASSIFICATION = "EXPERIMENTAL"
_VALIDATION_STATE = "UNVALIDATED"
_ACTIONABILITY = "NOT_ACTIONABLE"


@dataclass(frozen=True)
class ExperimentalPick:
    """A deterministic presentation projection of ONE prospective shadow record.

    This object carries NO scientific evidence of its own: every value is copied
    verbatim from the source shadow record (odds/probabilities preserved
    exactly). It never mutates the shadow. It exists purely so a future consumer
    channel has a stable, safe view to render.
    """

    experimental_pick_id: str
    fixture_id: str
    competition: Optional[str]
    kickoff_timestamp: float
    market_family: str
    selection: str
    line: float
    bookmaker: str
    locked_odds: float
    locked_market_probability: float
    engine_probability: float
    model_market_gap_pp: float
    locked_at: float
    minutes_before_kickoff: int
    forecast_id: str
    model_version: str
    source_shadow_id: str
    classification: str = _CLASSIFICATION
    validation_state: str = _VALIDATION_STATE
    actionability: str = _ACTIONABILITY

    def to_dict(self) -> dict[str, Any]:
        return {
            "experimental_pick_id": self.experimental_pick_id,
            "fixture_id": self.fixture_id,
            "competition": self.competition,
            "kickoff_timestamp": self.kickoff_timestamp,
            "market_family": self.market_family,
            "selection": self.selection,
            "line": self.line,
            "bookmaker": self.bookmaker,
            "locked_odds": self.locked_odds,
            "locked_market_probability": self.locked_market_probability,
            "engine_probability": self.engine_probability,
            "model_market_gap_pp": self.model_market_gap_pp,
            "locked_at": self.locked_at,
            "minutes_before_kickoff": self.minutes_before_kickoff,
            "forecast_id": self.forecast_id,
            "model_version": self.model_version,
            "source_shadow_id": self.source_shadow_id,
            "classification": self.classification,
            "validation_state": self.validation_state,
            "actionability": self.actionability,
        }


def _locked_odds_for_selection(record: dict, selection: str) -> float:
    """The exact decimal odds locked for this selection (never recomputed).

    over -> raw_over_odds, under -> raw_under_odds. Any other selection, or a
    missing/invalid price, fails closed.
    """
    sel = selection.strip().lower()
    if sel == "over":
        return _req_odds(record, "raw_over_odds")
    if sel == "under":
        return _req_odds(record, "raw_under_odds")
    raise ExperimentalPickError(f"unsupported selection {selection!r}; cannot locate locked odds")


def build_experimental_pick(record: dict) -> ExperimentalPick:
    """Project a publishable PROSPECTIVE shadow record into an ExperimentalPick.

    Strictly fail-closed. A pick is produced ONLY when the record:
      * passes :func:`shadow_feed.is_publishable_shadow` (record_type,
        PROSPECTIVE_SHADOW provenance, research classification, non-empty
        shadow_id, and all scientific fields present/finite/in-range), AND
      * has a PROSPECTIVE provenance (reconstructed shadows are refused), AND
      * carries valid parent forecast provenance (forecast_commitment_hash +
        model_version), a valid locked decimal price for the selection, and a
        valid pre-kickoff timing (information_cutoff < kickoff_ts).

    Anything missing / malformed / reconstructed raises
    :class:`ExperimentalPickError`. No value is ever defaulted or fabricated.
    The source shadow record is never mutated.
    """
    if not isinstance(record, dict):
        raise ExperimentalPickError("shadow record must be a dict")

    # Provenance: reconstructed shadows can NEVER become a pick. We check this
    # explicitly (in addition to is_publishable_shadow) so the intent is loud.
    if record.get("provenance_kind") != PROSPECTIVE_PROVENANCE:
        raise ExperimentalPickError(
            "refusing to build a pick from a non-prospective shadow "
            f"(provenance_kind={record.get('provenance_kind')!r}); reconstructed "
            "shadows are never eligible for consumer publication"
        )

    # Full publishability gate (reuses the canonical fail-closed validation).
    if not is_publishable_shadow(record):
        raise ExperimentalPickError(
            "shadow record failed is_publishable_shadow (malformed provenance, "
            "classification, id, or scientific fields); refusing to project a pick"
        )

    # Parent forecast provenance MUST be present (no orphan picks).
    forecast_id = _req_str(record, "forecast_commitment_hash")
    model_version = _req_str(record, "model_version")

    # Scientific probabilities (validated again defensively; preserved exactly).
    engine_probability = _req_prob(record, "p_model")
    locked_market_probability = _req_prob(record, "p_market_devig")

    # Timing: strictly pre-kickoff, both timestamps valid.
    locked_at = _req_num(record, "information_cutoff")
    kickoff_timestamp = _req_num(record, "kickoff_ts")
    if not (locked_at < kickoff_timestamp):
        raise ExperimentalPickError("information_cutoff is not strictly before kickoff")
    minutes_before_kickoff = int((kickoff_timestamp - locked_at) // 60)
    if minutes_before_kickoff <= 0:
        raise ExperimentalPickError("non-positive minutes before kickoff; refusing pick")

    # Market identity + exact locked price.
    market_family = _req_str(record, "market")
    selection = _req_str(record, "selection")
    line = _req_num(record, "line")
    bookmaker = _req_str(record, "bookmaker")
    locked_odds = _locked_odds_for_selection(record, selection)

    source_shadow_id = _req_str(record, "shadow_id")

    # Model-vs-market difference as neutral percentage points. This is NOT an
    # edge and NOT EV: it is purely the difference between two already-persisted
    # probabilities, surfaced for research transparency.
    model_market_gap_pp = (engine_probability - locked_market_probability) * 100.0

    # A deterministic pick id derived from the source shadow id (stable input ->
    # stable id). It carries no new evidence.
    experimental_pick_id = f"exp_{source_shadow_id}"

    competition = record.get("competition")
    if competition is not None and not isinstance(competition, str):
        raise ExperimentalPickError("competition must be a string or absent")

    return ExperimentalPick(
        experimental_pick_id=experimental_pick_id,
        fixture_id=_req_str(record, "fixture_id"),
        competition=competition,
        kickoff_timestamp=kickoff_timestamp,
        market_family=market_family,
        selection=selection,
        line=line,
        bookmaker=bookmaker,
        locked_odds=locked_odds,
        locked_market_probability=locked_market_probability,
        engine_probability=engine_probability,
        model_market_gap_pp=model_market_gap_pp,
        locked_at=locked_at,
        minutes_before_kickoff=minutes_before_kickoff,
        forecast_id=forecast_id,
        model_version=model_version,
        source_shadow_id=source_shadow_id,
    )


# ---------------------------------------------------------------------------
# Combined eligibility (scientific eligibility AND publication state)
# ---------------------------------------------------------------------------


def is_pick_eligible(record: dict) -> bool:
    """Whether a record is SCIENTIFICALLY eligible to become a pick.

    This is purely the scientific gate (prospective + publishable). It does NOT
    consider the publication state — see :func:`can_publish_experimental_pick`.
    """
    try:
        build_experimental_pick(record)
        return True
    except ExperimentalPickError:
        return False


def can_publish_experimental_pick(record: dict) -> bool:
    """Whether a specific record may be published as an Experimental Pick NOW.

    Requires BOTH, and the state can NEVER override scientific eligibility:
      1. the record is scientifically eligible (:func:`is_pick_eligible`), AND
      2. the publication state allows it (:func:`experimental_publication_enabled`).

    With the default ``EXPERIMENTAL_PUBLICATION_STATE=OFF`` this is always False,
    so no Experimental Pick message can be sent.
    """
    return experimental_publication_enabled() and is_pick_eligible(record)


# ---------------------------------------------------------------------------
# Consumer renderer (pure; performs NO sending)
# ---------------------------------------------------------------------------

#: Verbs that would imply a recommendation / action. The renderer must never
#: emit any of these (defence in depth; the template contains none).
_FORBIDDEN_RENDER_TERMS: tuple[str, ...] = (
    "bet", "wager", "stake", "buy", "sell", "take", "play",
    "edge", "ev", "roi", "profit", "value", "lock of", "tip",
    "back the", "lay the", "guaranteed",
)


def _fmt_pct(p: float) -> str:
    """Probability in (0,1) -> integer percentage, e.g. 0.61 -> '61%'."""
    return f"{round(float(p) * 100.0)}%"


def _fmt_gap_pp(gap_pp: float) -> str:
    """Signed percentage-point gap, e.g. +7.0 -> '+7pp', -3.0 -> '-3pp'."""
    return f"{round(float(gap_pp)):+d}pp"


def _fmt_odds(odds: float) -> str:
    """Decimal odds, trimmed of noise but exact, e.g. 1.85 -> '1.85'."""
    return f"{float(odds):.2f}"


def _selection_label(selection: str, line: float) -> str:
    """Consumer selection label, e.g. ('over', 2.5) -> 'Over 2.5'."""
    sel = str(selection).strip().capitalize()
    return f"{sel} {float(line):g}"


def _fixture_label(pick: ExperimentalPick, fixture_name: Optional[str]) -> str:
    """Human fixture label. Presentation-only fallback to the fixture id.

    A fixture NAME is a display convenience, not a scientific value, so degrading
    to the fixture id is acceptable (unlike scientific fields, which fail closed
    in :func:`build_experimental_pick`).
    """
    if fixture_name is not None and str(fixture_name).strip() != "":
        return str(fixture_name).strip()
    return f"Fixture {pick.fixture_id}"


def render_experimental_pick(
    pick: ExperimentalPick,
    *,
    sequence_number: int,
    fixture_name: Optional[str] = None,
) -> str:
    """Render the consumer Telegram copy for an eligible ExperimentalPick.

    Pure and deterministic: the same pick + sequence number + fixture name
    always renders identical text. Performs NO sending. Preserves the exact
    locked odds and probabilities from the source. Uses consumer-readable
    terminology only: no internal labels (e.g. SHADOW_RESIDUAL), no
    profitability/validation claims, no recommendation verbs, and never calls
    the model-market gap "edge" or "EV".
    """
    fixture = _fixture_label(pick, fixture_name)
    selection = _selection_label(pick.selection, pick.line)
    header = f"\U0001f9ea EXPERIMENTAL PICK #{int(sequence_number):03d}"

    lines = [
        header,
        "",
        fixture,
        "",
        f"{selection} @ {_fmt_odds(pick.locked_odds)}",
        "",
        f"Engine: {_fmt_pct(pick.engine_probability)}",
        f"Market: {_fmt_pct(pick.locked_market_probability)}",
        f"Gap: {_fmt_gap_pp(pick.model_market_gap_pp)}",
        "",
        f"\U0001f512 Locked {pick.minutes_before_kickoff}m before kickoff",
        "",
        "TESTING \u2014 NOT VALIDATED",
        "Research only. Not actionable.",
    ]
    text = "\n".join(lines)
    _assert_render_safe(text)
    return text


def _assert_render_safe(text: str) -> None:
    """Defence in depth: refuse to emit forbidden promotional/action terms.

    Neutralises the approved negative label "not actionable" first (so the
    "Not actionable." footer is allowed), then rejects any recommendation verb
    or profitability/validation vocabulary. Word-boundary matching avoids false
    positives (e.g. "kickoff" contains no forbidden word; "Market" is allowed).
    """
    import re

    low = f" {text.lower()} "
    low = low.replace("not actionable", " ")
    for term in _FORBIDDEN_RENDER_TERMS:
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", low):
            raise ExperimentalPickError(
                f"experimental-pick copy contains forbidden term {term!r}; "
                "consumer picks must never imply action, profitability, or validation"
            )
