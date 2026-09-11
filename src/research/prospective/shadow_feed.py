"""Research-only Telegram feed for persisted SHADOW_RESIDUAL records.

DATA ACCUMULATION MODE. This module turns ALREADY-PERSISTED, immutable
prospective shadow-residual records (and their later movement evaluations) into
clearly labelled RESEARCH-ONLY Telegram cards. It is purely a UX / integration
layer over data that PR #11 already froze to disk.

Hard boundaries (mission sections 2, 10, 11, 15):
- CONSUME ONLY. It reads ``data/prospective/shadow_residuals.jsonl`` and
  ``data/prospective/shadow_evaluations.jsonl`` via the append-only stores. It
  NEVER recomputes a residual, re-runs the model, calls a provider, reconstructs
  a missing shadow, or settles an outcome. If a record is absent, it says
  nothing.
- PROSPECTIVE ONLY. Only records with ``record_type == SHADOW_RESIDUAL`` and
  ``provenance_kind == PROSPECTIVE_SHADOW`` whose ``classification`` contains
  RESEARCH_ONLY / NOT_VALIDATED / NOT_ACTIONABLE may enter the live feed.
  RECONSTRUCTED_SHADOW records (and anything malformed) are dropped, fail-closed.
- NOT A SIGNAL. Messages are emitted only as SHADOW_RESEARCH /
  SHADOW_RESEARCH_UPDATE (never VALIDATED_SIGNAL / STRATEGY_ACTION), routed
  through :func:`research_notify.build_research_shadow_message` which enforces
  the type restriction and the research content guard. It does not consult and
  never weakens :func:`can_publish_validated_signals`.

Delivery / dedup (mission sections 8, 9): each card carries a deterministic
``event_id`` (``shadow:{shadow_id}`` / ``shadow_eval:{evaluation_id}``) and is
delivered at most once through the existing restart-safe
:class:`research_notify_delivery.NotifyLedger`. Reusing that ledger means a
service restart never replays shadow history.

Noise control (mission section 14): records are grouped by fixture and a
per-tick message cap is applied; anything over the cap is simply left unseen for
the next tick (the ledger guarantees it is picked up later). Selection for the
cap is neutral (deterministic order of first appearance) — NEVER by residual
magnitude, and residuals are never filtered by a magnitude threshold.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from src.research.prospective.research_notify import (
    MessageType,
    NotifyMessage,
    build_research_shadow_message,
)
from src.research.prospective.research_notify_delivery import (
    DeliveryResult,
    NotifyLedger,
    deliver,
)
from src.research.prediction_engine.broadcast.delivery import (
    RecordingTransport,
    TelegramTransport,
)
from src.research.prospective.shadow_residual import (
    CLASSIFICATION as _REQUIRED_CLASSIFICATION,
)
from src.research.prospective.shadow_store import (
    DEFAULT_SHADOW_ROOT,
    SHADOW_CANDIDATES_FILE,
    SHADOW_EVALUATIONS_FILE,
    ShadowEvaluationStore,
    ShadowResidualStore,
)

# --- constants -------------------------------------------------------------

SHADOW_RECORD_TYPE = "SHADOW_RESIDUAL"
EVALUATION_RECORD_TYPE = "SHADOW_RESIDUAL_EVALUATION"
PROSPECTIVE_PROVENANCE = "PROSPECTIVE_SHADOW"

#: Every classification token that MUST be present for a record to be publishable
#: on the live research feed. Fail closed if any is missing / malformed.
REQUIRED_CLASSIFICATION: frozenset[str] = frozenset(_REQUIRED_CLASSIFICATION)

#: Default maximum number of Telegram messages emitted in one tick. Neutral
#: operational cap for noise control (mission section 4/14): it bounds message
#: volume, never selects "best" residuals. Remaining unseen records are left for
#: the next tick and are picked up via the ledger.
DEFAULT_MAX_MESSAGES_PER_TICK = 8

#: A fixture-resolver returns a human-readable label for a fixture id, or None
#: if it cannot resolve one WITHOUT a network/model call. Default is None (we
#: fall back to a concise fixture identifier). A caller may inject a resolver
#: backed by already-persisted local state; this module never calls a provider.
FixtureNameResolver = Callable[[str], Optional[str]]


# ---------------------------------------------------------------------------
# Publication boundary: explicit opt-in + DEDICATED research channel
#
# The shadow-research feed is research-only, but delivering it to Telegram is
# still an external publication. Two independent guards protect it (both must
# pass before anything is sent live):
#
#   1. RESEARCH_SHADOW_FEED_PUBLISH must be explicitly enabled. Unset / empty /
#      malformed / unknown => DISABLED (fail closed). No capture tick can start
#      sending research cards without an operator deliberately turning this on.
#
#   2. Delivery uses a DEDICATED research Telegram channel resolved ONLY from
#      RESEARCH_TELEGRAM_BOT_TOKEN + RESEARCH_TELEGRAM_CHAT_ID. There is NO
#      fallback to the SIGNALS_* / HEARTBEAT_* / FORECAST_BROADCAST_* consumer
#      credentials, so a research card can never be routed into the consumer
#      signals channel just because those variables happen to be set. If the
#      dedicated pair is absent, the transport fails closed (sends nothing).
# ---------------------------------------------------------------------------

#: Env flag that must be explicitly enabled to allow ANY live shadow-feed send.
SHADOW_FEED_PUBLISH_ENV = "RESEARCH_SHADOW_FEED_PUBLISH"

#: Exact tokens that enable publication (case-insensitive, trimmed). Anything
#: else — including unset — leaves the feed OFF.
_SHADOW_FEED_PUBLISH_ENABLED_TOKENS: frozenset[str] = frozenset({"1", "TRUE", "ON", "ENABLED"})

#: Dedicated research-channel credentials. NO consumer-channel fallback.
RESEARCH_TELEGRAM_TOKEN_ENV = "RESEARCH_TELEGRAM_BOT_TOKEN"
RESEARCH_TELEGRAM_CHAT_ENV = "RESEARCH_TELEGRAM_CHAT_ID"


def shadow_feed_publication_enabled() -> bool:
    """Whether the operator has explicitly opted in to live shadow-feed sends.

    Fail closed: unset / empty / malformed / unknown => False. This gate is
    INDEPENDENT of message eligibility — an enabled flag never makes a
    non-publishable record publishable; it only permits delivery of records
    that are already publishable.
    """
    raw = os.environ.get(SHADOW_FEED_PUBLISH_ENV)
    if raw is None:
        return False
    return raw.strip().upper() in _SHADOW_FEED_PUBLISH_ENABLED_TOKENS


def research_telegram_transport() -> Optional[TelegramTransport]:
    """Build a transport bound to the DEDICATED research channel, or None.

    Resolves credentials ONLY from :data:`RESEARCH_TELEGRAM_TOKEN_ENV` and
    :data:`RESEARCH_TELEGRAM_CHAT_ENV`. It deliberately does NOT reuse the
    default :class:`TelegramTransport` env resolution (which would fall back to
    the consumer SIGNALS_* / HEARTBEAT_* channel). Returns None when the
    dedicated pair is not fully configured, so the caller fails closed rather
    than routing research cards to a consumer audience.
    """
    token = os.environ.get(RESEARCH_TELEGRAM_TOKEN_ENV)
    chat = os.environ.get(RESEARCH_TELEGRAM_CHAT_ENV)
    if not token or not chat:
        return None
    # Pin the env tuples to the dedicated names ONLY (single-element tuples): no
    # silent fallback to any consumer channel is possible from this transport.
    return TelegramTransport(
        token_env=(RESEARCH_TELEGRAM_TOKEN_ENV,),
        chat_env=(RESEARCH_TELEGRAM_CHAT_ENV,),
    )


# ---------------------------------------------------------------------------
# Fail-closed classification / provenance gate
# ---------------------------------------------------------------------------


def _classification_ok(record: dict) -> bool:
    """True iff the record's classification contains all required tokens.

    Fails closed on anything malformed: missing key, wrong type, or a token set
    that does not include RESEARCH_ONLY / NOT_VALIDATED / NOT_ACTIONABLE.
    """
    raw = record.get("classification")
    if not isinstance(raw, (list, tuple)):
        return False
    try:
        tokens = {str(t) for t in raw}
    except TypeError:
        return False
    return REQUIRED_CLASSIFICATION.issubset(tokens)


# ---------------------------------------------------------------------------
# Fail-closed scientific-field validation (BLOCKER 2)
#
# Telegram is an observability surface: a corrupt / incomplete research record
# must NEVER be rendered with fabricated zero values ("Market: 0.0%",
# "Residual: +0.0 pp"). Every SCIENTIFIC field the card displays is validated
# up front; anything missing / non-finite / out-of-range makes the record
# non-publishable (missing truth stays missing). Presentation-only fallback
# (a human fixture NAME degrading to the fixture id) is unaffected — that is a
# display fallback, not a scientific-value fallback.
# ---------------------------------------------------------------------------

import math as _math

#: Movement directions the evaluation card may display. Anything else fails
#: closed (mirrors shadow_residual.MovementDirection; no new definition).
_VALID_MOVEMENT_DIRECTIONS: frozenset[str] = frozenset(
    {"TOWARD_MODEL", "AWAY_FROM_MODEL", "FLAT"}
)


def _is_finite_number(value) -> bool:
    """True iff value is a real (non-bool) int/float that is finite (no NaN/inf)."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return _math.isfinite(float(value))


def _is_probability(value) -> bool:
    """True iff value is a finite number strictly in (0, 1)."""
    return _is_finite_number(value) and 0.0 < float(value) < 1.0


def _nonempty_str(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def shadow_scientific_fields_ok(record: dict) -> bool:
    """Validate every SCIENTIFIC field a shadow card relies on (fail closed).

    Requires (all must be present, correctly typed, finite, and in-range):
      * non-empty ``fixture_id`` / ``shadow_id`` / ``bookmaker`` / ``market`` /
        ``selection``
      * ``line`` finite (this pipeline only emits over/under line markets, so a
        line is always required — no new market semantics are invented)
      * ``p_model`` and ``p_market_devig`` finite and strictly in (0, 1)
      * ``raw_probability_residual`` finite
      * ``information_cutoff`` and ``kickoff_ts`` finite, with
        ``information_cutoff < kickoff_ts`` (the frozen shadow is pre-kickoff)
    """
    if not isinstance(record, dict):
        return False
    for key in ("fixture_id", "shadow_id", "bookmaker", "market", "selection"):
        if not _nonempty_str(record.get(key)):
            return False
    if not _is_finite_number(record.get("line")):
        return False
    if not _is_probability(record.get("p_model")):
        return False
    if not _is_probability(record.get("p_market_devig")):
        return False
    if not _is_finite_number(record.get("raw_probability_residual")):
        return False
    cutoff = record.get("information_cutoff")
    kickoff = record.get("kickoff_ts")
    if not _is_finite_number(cutoff) or not _is_finite_number(kickoff):
        return False
    if not (float(cutoff) < float(kickoff)):
        return False
    return True


def evaluation_scientific_fields_ok(record: dict) -> bool:
    """Validate every SCIENTIFIC field an evaluation card displays (fail closed).

    Requires:
      * non-empty ``evaluation_id`` / ``shadow_id`` / ``fixture_id`` /
        ``bookmaker`` / ``market`` / ``selection``
      * ``line`` finite
      * ``p_market_earlier`` and ``later_market_devig`` finite and in (0, 1)
      * ``delta_probability`` finite
      * ``later_observed_at`` finite
      * ``movement_direction`` in {TOWARD_MODEL, AWAY_FROM_MODEL, FLAT}
    """
    if not isinstance(record, dict):
        return False
    for key in ("evaluation_id", "shadow_id", "fixture_id", "bookmaker", "market", "selection"):
        if not _nonempty_str(record.get(key)):
            return False
    if not _is_finite_number(record.get("line")):
        return False
    if not _is_probability(record.get("p_market_earlier")):
        return False
    if not _is_probability(record.get("later_market_devig")):
        return False
    if not _is_finite_number(record.get("delta_probability")):
        return False
    if not _is_finite_number(record.get("later_observed_at")):
        return False
    if record.get("movement_direction") not in _VALID_MOVEMENT_DIRECTIONS:
        return False
    return True


def is_publishable_shadow(record: dict) -> bool:
    """Gate for a SHADOW_RESIDUAL candidate entering the LIVE research feed.

    Requires (all, fail-closed):
      * ``record_type == SHADOW_RESIDUAL``
      * ``provenance_kind == PROSPECTIVE_SHADOW`` (RECONSTRUCTED_SHADOW is never
        published as if it were live)
      * classification contains RESEARCH_ONLY / NOT_VALIDATED / NOT_ACTIONABLE
      * a non-empty ``shadow_id`` (the dedup / delivery key)
      * ALL scientific fields the card renders are present, finite and in-range
        (see :func:`shadow_scientific_fields_ok`) — no zero-default rendering.
    """
    if not isinstance(record, dict):
        return False
    if record.get("record_type") != SHADOW_RECORD_TYPE:
        return False
    if record.get("provenance_kind") != PROSPECTIVE_PROVENANCE:
        return False
    if not _classification_ok(record):
        return False
    if not record.get("shadow_id"):
        return False
    if not shadow_scientific_fields_ok(record):
        return False
    return True


def is_structurally_valid_evaluation(record: dict) -> bool:
    """Structural + scientific validity of an evaluation record ITSELF.

    This does NOT prove the referenced parent shadow is prospective; that is
    checked separately (see :func:`is_publishable_evaluation`). Requires:
      * ``record_type == SHADOW_RESIDUAL_EVALUATION``
      * classification contains RESEARCH_ONLY / NOT_VALIDATED / NOT_ACTIONABLE
      * non-empty ``evaluation_id`` (dedup key) and ``shadow_id`` (parent link)
      * all displayed scientific fields valid (see
        :func:`evaluation_scientific_fields_ok`)
    """
    if not isinstance(record, dict):
        return False
    if record.get("record_type") != EVALUATION_RECORD_TYPE:
        return False
    if not _classification_ok(record):
        return False
    if not record.get("evaluation_id"):
        return False
    if not record.get("shadow_id"):
        return False
    if not evaluation_scientific_fields_ok(record):
        return False
    return True


def is_publishable_evaluation(record: dict, *, shadow_lookup: dict) -> bool:
    """Gate for a SHADOW_RESIDUAL_EVALUATION entering the LIVE research feed.

    An evaluation is publishable IFF (BLOCKER 1 — parent-provenance proof):
      1. the evaluation itself is structurally + scientifically valid
         (:func:`is_structurally_valid_evaluation`), AND
      2. its ``shadow_id`` resolves to a persisted PARENT shadow in
         ``shadow_lookup``, AND
      3. that parent passes :func:`is_publishable_shadow` (i.e. it is a
         legitimate PROSPECTIVE_SHADOW with valid scientific fields).

    Consequences (all fail closed):
      * a RECONSTRUCTED_SHADOW parent  -> NEVER publish
      * a missing parent               -> NEVER publish
      * a malformed parent             -> NEVER publish
      * a prospective, valid parent    -> eligible

    Provenance is proven by PARENT LINKAGE, never inferred from the evaluation's
    own classification (which reconstructed evaluations may also carry).
    """
    if not is_structurally_valid_evaluation(record):
        return False
    if not isinstance(shadow_lookup, dict):
        return False
    parent = shadow_lookup.get(record.get("shadow_id"))
    if not isinstance(parent, dict):
        return False
    if not is_publishable_shadow(parent):
        return False
    return True


# ---------------------------------------------------------------------------
# Presentation helpers (pure formatting over already-persisted numbers)
# ---------------------------------------------------------------------------


def format_pp(residual: float) -> str:
    """Format a probability residual as signed percentage points.

    +0.058 -> "+5.8 pp"; -0.031 -> "-3.1 pp"; 0.0 -> "+0.0 pp".
    The value is the persisted ``raw_probability_residual`` — never recomputed.
    """
    pp = float(residual) * 100.0
    # Avoid a "-0.0 pp" artefact for values that round to zero.
    if abs(pp) < 0.05:
        pp = 0.0
    return f"{pp:+.1f} pp"


def format_probability_pct(p: float) -> str:
    """Format a probability in [0, 1] as a percentage, e.g. 0.512 -> '51.2%'."""
    return f"{float(p) * 100.0:.1f}%"


def format_t_minus(*, kickoff_ts: Optional[float], information_cutoff: float) -> str:
    """Time-to-kickoff label from ``kickoff_ts - information_cutoff``.

    Represents WHEN THE SHADOW WAS FROZEN, not when Telegram delivered it
    (mission section 5). Examples: "T-58m", "T-1h 42m". If kickoff is unknown,
    or the cutoff is at/after kickoff, returns "T-?".
    """
    if kickoff_ts is None or information_cutoff is None:
        return "T-?"
    delta = float(kickoff_ts) - float(information_cutoff)
    if delta <= 0:
        return "T-?"
    total_minutes = int(delta // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours > 0:
        return f"T-{hours}h {minutes:02d}m"
    return f"T-{minutes}m"


def _line_label(market: str, selection: str, line) -> str:
    """Compose the exact selection label, e.g. 'Goals - Over 2.5'.

    Preserves the exact persisted market / selection / line; never collapses
    different lines or selections.
    """
    sel = str(selection).strip().capitalize()
    if line is None:
        return f"{market} - {sel}"
    # Render the line without trailing zeros noise but keep the exact value.
    line_str = f"{float(line):g}"
    return f"{market} - {sel} {line_str}"


def _fixture_label(record: dict, resolver: Optional[FixtureNameResolver]) -> str:
    """Human label for a fixture, falling back to a concise fixture identifier.

    Uses an injected resolver ONLY (already-persisted local state); if it
    returns nothing, we degrade to ``fixture {id}`` rather than making any API
    call (mission section 3).
    """
    fixture_id = str(record.get("fixture_id", "")) or "unknown"
    if resolver is not None:
        try:
            name = resolver(fixture_id)
        except Exception:  # noqa: BLE001 - a resolver must never break the feed
            name = None
        if name:
            return str(name)
    return f"fixture {fixture_id}"


def _competition_label(record: dict) -> Optional[str]:
    """The competition this shadow belongs to, or ``None`` when not persisted.

    Rendered because shadows now span the whole dual-provider league universe. While
    coverage was the four Pilot-C leagues a reader could infer the competition from
    the fixture; across 40+ competitions that inference is no longer available, and a
    research observation whose league is unidentifiable is much harder to interpret.

    The value is emitted exactly as persisted on the record (the canonical
    TheStatsAPI competition id). No lookup, no mapping table, and no display-name
    join: a wrong league label on a research card would be worse than none, and any
    name resolution here would be a second source of identity truth competing with
    the canonical registry. Absent/blank yields ``None`` and the line is omitted
    rather than rendered as "unknown".
    """
    raw = record.get("competition")
    if raw is None:
        return None
    label = str(raw).strip()
    return label or None


def _short_ref(shadow_id: str) -> str:
    return str(shadow_id)[:8]


class ShadowCardError(ValueError):
    """Raised if a card is asked to render a missing/invalid SCIENTIFIC field.

    Rendering is only ever reached for records that already passed the
    publishable gate, so this is a defence-in-depth guarantee: a scientific
    value is NEVER fabricated as 0.0. (Presentation-only fixture NAME fallback
    to the fixture id is handled separately and is not a scientific value.)
    """


def _req_prob(record: dict, key: str) -> float:
    v = record.get(key)
    if not _is_probability(v):
        raise ShadowCardError(f"missing/invalid probability field {key!r}")
    return float(v)


def _req_num(record: dict, key: str) -> float:
    v = record.get(key)
    if not _is_finite_number(v):
        raise ShadowCardError(f"missing/invalid numeric field {key!r}")
    return float(v)


def _req_str(record: dict, key: str) -> str:
    v = record.get(key)
    if not _nonempty_str(v):
        raise ShadowCardError(f"missing/invalid text field {key!r}")
    return v.strip()


# ---------------------------------------------------------------------------
# Card rendering
# ---------------------------------------------------------------------------

_HEADER_SHADOW = "\U0001f9ea SHADOW RESIDUAL \u2014 RESEARCH ONLY"
_HEADER_GROUP = "\U0001f9ea SHADOW RESEARCH"
_HEADER_UPDATE = "\U0001f9ea SHADOW UPDATE \u2014 RESEARCH RESULT"
_FOOTER_LINES = ("\U0001f512 NOT VALIDATED", "\U0001f6ab NOT ACTIONABLE")

#: Neutral human wording for each movement direction (mission section 7). This
#: is evidence collection: TOWARD is not a "win", AWAY is not a "loss".
_DIRECTION_LABEL = {
    "TOWARD_MODEL": "Direction: TOWARD MODEL \u2705",
    "AWAY_FROM_MODEL": "Direction: AWAY FROM MODEL",
    "FLAT": "Direction: FLAT",
}


def render_shadow_card(record: dict, *, resolver: Optional[FixtureNameResolver] = None) -> str:
    """Render a single research-only shadow-residual card from a persisted dict.

    All numbers come straight from the record; nothing is recomputed.
    """
    fixture = _fixture_label(record, resolver)
    # Scientific fields: strict access (no zero-default). Rendering is only
    # reached for gated records, so these are guaranteed present; the strict
    # accessors are defence in depth against a fabricated 0.0.
    market_label = _line_label(_req_str(record, "market"), _req_str(record, "selection"),
                               _req_num(record, "line"))
    bookmaker = _req_str(record, "bookmaker")
    tminus = format_t_minus(
        kickoff_ts=_req_num(record, "kickoff_ts"),
        information_cutoff=_req_num(record, "information_cutoff"),
    )
    p_market = format_probability_pct(_req_prob(record, "p_market_devig"))
    p_model = format_probability_pct(_req_prob(record, "p_model"))
    resid = format_pp(_req_num(record, "raw_probability_residual"))
    ref = _short_ref(_req_str(record, "shadow_id"))

    lines = [
        _HEADER_SHADOW,
        "",
        f"\u26bd {fixture}",
    ]
    competition = _competition_label(record)
    if competition:
        lines.append(f"\U0001f3c6 {competition}")
    lines += [
        f"\U0001f4ca {market_label}",
        f"\U0001f3e6 {bookmaker}",
        f"\u23f1 {tminus}",
        "",
        f"Market: {p_market}",
        f"Research model: {p_model}",
        f"Residual: {resid}",
        "",
        f"Ref: {ref}",
        *_FOOTER_LINES,
    ]
    return "\n".join(lines)


def render_shadow_group_card(
    records: list[dict], *, resolver: Optional[FixtureNameResolver] = None
) -> str:
    """Render a fixture-grouped research card for several shadows.

    Groups by (bookmaker) within one fixture for readability, listing each exact
    market/selection/line with its own market/model probabilities and residual.
    Probabilities are NEVER merged across bookmakers or lines; each shadow keeps
    its exact per-shadow identity. Records are shown in their given order (never
    ranked by residual magnitude).
    """
    if not records:
        return ""
    fixture = _fixture_label(records[0], resolver)
    # Use the smallest T-minus label available for a single "frozen around" hint;
    # this is display-only and does not alter any per-shadow value.
    tminus = _group_frozen_hint(records)

    lines = [f"{_HEADER_GROUP} \u2014 {fixture}", ""]
    competition = _competition_label(records[0])
    if competition:
        lines.append(f"\U0001f3c6 {competition}")
        lines.append("")
    by_book: dict[str, list[dict]] = {}
    order: list[str] = []
    for r in records:
        book = str(r.get("bookmaker", "")).strip() or "unknown"
        if book not in by_book:
            by_book[book] = []
            order.append(book)
        by_book[book].append(r)

    for book in order:
        lines.append(book)
        for r in by_book[book]:
            market_label = _line_label(_req_str(r, "market"), _req_str(r, "selection"),
                                       _req_num(r, "line"))
            p_market = format_probability_pct(_req_prob(r, "p_market_devig"))
            p_model = format_probability_pct(_req_prob(r, "p_model"))
            resid = format_pp(_req_num(r, "raw_probability_residual"))
            lines.append(f"\u2022 {market_label}: Market {p_market} | Model {p_model} | {resid}")
        lines.append("")

    lines.append(f"\u23f1 Frozen around {tminus}")
    lines.append("\U0001f512 Research only \u00b7 Not validated \u00b7 Not actionable")
    return "\n".join(lines).rstrip()


def _group_frozen_hint(records: list[dict]) -> str:
    labels = [
        format_t_minus(
            kickoff_ts=r.get("kickoff_ts"),
            information_cutoff=r.get("information_cutoff"),
        )
        for r in records
    ]
    known = [l for l in labels if l != "T-?"]
    return known[0] if known else "T-?"


def render_evaluation_card(record: dict, *, resolver: Optional[FixtureNameResolver] = None,
                           shadow_lookup: Optional[dict] = None) -> str:
    """Render a research-result (movement) update card from a persisted eval.

    ``shadow_lookup`` optionally maps ``shadow_id`` -> the original shadow dict
    so the initial residual can be shown. It is an already-persisted record, not
    a recomputation. Everything degrades gracefully if the original is absent.
    """
    fixture = _fixture_label(record, resolver)
    # Scientific fields: strict access (no zero-default).
    market_label = _line_label(_req_str(record, "market"), _req_str(record, "selection"),
                               _req_num(record, "line"))
    bookmaker = _req_str(record, "bookmaker")

    p_market_earlier = format_probability_pct(_req_prob(record, "p_market_earlier"))
    later = format_probability_pct(_req_prob(record, "later_market_devig"))
    movement = format_pp(_req_num(record, "delta_probability"))
    md = record.get("movement_direction")
    if md not in _VALID_MOVEMENT_DIRECTIONS:
        raise ShadowCardError(f"invalid movement_direction {md!r}")
    direction = _DIRECTION_LABEL[md]
    ref = _short_ref(_req_str(record, "shadow_id"))

    # Optional enrichment from the frozen original shadow (persisted, not re-run).
    # This is a validated PARENT shadow (the evaluation only publishes when its
    # parent is publishable), so its scientific fields are trustworthy here.
    model_line = None
    initial_resid_line = None
    if shadow_lookup:
        original = shadow_lookup.get(record.get("shadow_id"))
        if isinstance(original, dict) and _is_probability(original.get("p_model")) \
                and _is_finite_number(original.get("raw_probability_residual")):
            model_line = f"Research model: {format_probability_pct(original['p_model'])}"
            initial_resid_line = (
                f"Initial residual: {format_pp(original['raw_probability_residual'])}"
            )

    lines = [
        _HEADER_UPDATE,
        "",
        f"\u26bd {fixture}",
    ]
    # Prefer the evaluation's own competition; fall back to the frozen parent
    # shadow, which always carries it. Never inferred from anything else.
    competition = _competition_label(record)
    if competition is None and shadow_lookup:
        parent = shadow_lookup.get(record.get("shadow_id"))
        if isinstance(parent, dict):
            competition = _competition_label(parent)
    if competition:
        lines.append(f"\U0001f3c6 {competition}")
    lines += [
        f"\U0001f4ca {market_label}",
        f"\U0001f3e6 {bookmaker}",
        "",
        f"Initial market: {p_market_earlier}",
    ]
    if model_line:
        lines.append(model_line)
    if initial_resid_line:
        lines.append(initial_resid_line)
    lines += [
        "",
        f"Later market: {later}",
        f"Movement: {movement}",
        "",
        direction,
        "",
        "\U0001f52c Added to prospective research sample",
        f"Ref: {ref}",
        *_FOOTER_LINES,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Message building (through the guarded research-shadow path)
# ---------------------------------------------------------------------------


def shadow_event_id(record: dict) -> str:
    return f"shadow:{record.get('shadow_id')}"


def evaluation_event_id(record: dict) -> str:
    return f"shadow_eval:{record.get('evaluation_id')}"


def _fixture_group_event_id(records: list[dict]) -> str:
    """Deterministic dedup id for a grouped fixture card.

    A group card is delivered once per exact SET of shadow ids in it, so the
    same combination is never re-sent, while a later NEW shadow in the same
    fixture forms a different set and is delivered as its own group.
    """
    ids = sorted(str(r.get("shadow_id")) for r in records)
    key = ",".join(ids)
    # Keep the id short but collision-resistant enough for dedup purposes.
    import hashlib

    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return f"shadow_group:{digest}"


def build_shadow_message(
    record: dict, *, now: float, main_sha: str = "", resolver: Optional[FixtureNameResolver] = None
) -> NotifyMessage:
    text = render_shadow_card(record, resolver=resolver)
    return build_research_shadow_message(
        MessageType.SHADOW_RESEARCH, shadow_event_id(record), text,
        generated_at=now, main_sha=main_sha,
    )


def build_group_message(
    records: list[dict], *, now: float, main_sha: str = "",
    resolver: Optional[FixtureNameResolver] = None,
) -> NotifyMessage:
    text = render_shadow_group_card(records, resolver=resolver)
    return build_research_shadow_message(
        MessageType.SHADOW_RESEARCH, _fixture_group_event_id(records), text,
        generated_at=now, main_sha=main_sha,
    )


def build_evaluation_message(
    record: dict, *, now: float, main_sha: str = "",
    resolver: Optional[FixtureNameResolver] = None, shadow_lookup: Optional[dict] = None,
) -> NotifyMessage:
    text = render_evaluation_card(record, resolver=resolver, shadow_lookup=shadow_lookup)
    return build_research_shadow_message(
        MessageType.SHADOW_RESEARCH_UPDATE, evaluation_event_id(record), text,
        generated_at=now, main_sha=main_sha,
    )


# ---------------------------------------------------------------------------
# Selection / batching (neutral, magnitude-agnostic)
# ---------------------------------------------------------------------------


def select_unseen_shadows(records: Iterable[dict], *, ledger: NotifyLedger) -> list[dict]:
    """Filter to publishable, not-yet-delivered shadows, preserving order.

    Deduplicates by ``shadow_id`` within the batch and against the ledger. No
    residual-magnitude filtering or ranking whatsoever.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for r in records:
        if not is_publishable_shadow(r):
            continue
        sid = str(r.get("shadow_id"))
        if sid in seen:
            continue
        if ledger.already_sent(shadow_event_id(r)):
            continue
        seen.add(sid)
        out.append(r)
    return out


def select_unseen_evaluations(
    records: Iterable[dict], *, ledger: NotifyLedger, shadow_lookup: dict
) -> list[dict]:
    """Filter to publishable, not-yet-delivered evaluations, preserving order.

    An evaluation is only publishable when its parent shadow (resolved via
    ``shadow_lookup``) is itself publishable-prospective (BLOCKER 1). Dedup by
    ``evaluation_id`` within the batch and against the ledger.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for r in records:
        if not is_publishable_evaluation(r, shadow_lookup=shadow_lookup):
            continue
        eid = str(r.get("evaluation_id"))
        if eid in seen:
            continue
        if ledger.already_sent(evaluation_event_id(r)):
            continue
        seen.add(eid)
        out.append(r)
    return out


def group_by_fixture(records: list[dict]) -> list[list[dict]]:
    """Group publishable shadows by fixture id, preserving first-seen order.

    Grouping is a display/noise-control convenience; each shadow keeps its exact
    per-shadow identity (nothing is merged numerically).
    """
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for r in records:
        fid = str(r.get("fixture_id"))
        if fid not in groups:
            groups[fid] = []
            order.append(fid)
        groups[fid].append(r)
    return [groups[f] for f in order]


@dataclass
class ShadowFeedResult:
    """Observability for one publish tick (never a promotion metric)."""

    shadows_seen: int = 0
    shadows_published: int = 0
    shadows_queued: int = 0
    evaluations_seen: int = 0
    evaluations_published: int = 0
    evaluations_queued: int = 0
    messages_sent: int = 0
    delivery_results: list[DeliveryResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "shadows_seen": self.shadows_seen,
            "shadows_published": self.shadows_published,
            "shadows_queued": self.shadows_queued,
            "evaluations_seen": self.evaluations_seen,
            "evaluations_published": self.evaluations_published,
            "evaluations_queued": self.evaluations_queued,
            "messages_sent": self.messages_sent,
        }


# ---------------------------------------------------------------------------
# Public entrypoint: publish persisted shadow records to Telegram
# ---------------------------------------------------------------------------


def publish_shadow_feed(
    *,
    shadow_root: Path = DEFAULT_SHADOW_ROOT,
    ledger: Optional[NotifyLedger] = None,
    transport=None,
    dry_run: bool = False,
    now: Optional[float] = None,
    main_sha: str = "",
    max_messages: int = DEFAULT_MAX_MESSAGES_PER_TICK,
    group_by_fixture_cards: bool = True,
    resolver: Optional[FixtureNameResolver] = None,
    require_optin: bool = True,
) -> ShadowFeedResult:
    """Read persisted shadow records and deliver research-only Telegram cards.

    Consume-only: reads the append-only shadow stores, filters to publishable +
    unseen records, batches them (grouped by fixture, capped per tick), and
    delivers each through the restart-safe ledger. Never recomputes anything,
    never calls a provider or model, never publishes a reserved signal type.

    ``max_messages`` caps messages sent this tick; anything beyond is left as
    "queued" (unseen), to be delivered on a later tick via the ledger. The cap
    is neutral (order of appearance), never by residual magnitude.

    Publication boundary (fail closed on the LIVE default path):
      * ``dry_run=True`` always renders without sending or recording (tests /
        inspection).
      * An explicitly injected ``transport`` is used as-is (tests and advanced
        callers own their routing).
      * Otherwise (live, no injected transport) BOTH guards must pass or nothing
        is sent this tick:
          - ``require_optin`` and :func:`shadow_feed_publication_enabled` — the
            operator must have explicitly enabled ``RESEARCH_SHADOW_FEED_PUBLISH``;
          - a DEDICATED research channel must be configured
            (:func:`research_telegram_transport` returns a transport, never the
            consumer SIGNALS_* / HEARTBEAT_* fallback).
        If either guard fails, publishable records are simply left unseen
        ("queued") for a later tick — never routed to a consumer channel.
    """
    import time as _time

    now = _time.time() if now is None else now
    ledger = ledger or NotifyLedger(path=Path(shadow_root) / "notify_ledger.json")

    candidate_store = ShadowResidualStore(path=Path(shadow_root) / SHADOW_CANDIDATES_FILE)
    evaluation_store = ShadowEvaluationStore(path=Path(shadow_root) / SHADOW_EVALUATIONS_FILE)

    all_shadows = list(candidate_store.read_all_dicts())
    all_evaluations = list(evaluation_store.read_all_dicts())

    # A lookup mapping shadow_id -> the persisted parent shadow. Includes ALL
    # persisted shadows (prospective, reconstructed, malformed) so evaluation
    # parent-linkage validation (BLOCKER 1) can re-check the parent with
    # is_publishable_shadow and reject non-prospective / malformed parents.
    shadow_lookup = {
        str(r.get("shadow_id")): r for r in all_shadows if r.get("shadow_id")
    }

    unseen_shadows = select_unseen_shadows(all_shadows, ledger=ledger)
    unseen_evaluations = select_unseen_evaluations(
        all_evaluations, ledger=ledger, shadow_lookup=shadow_lookup
    )

    result = ShadowFeedResult(
        shadows_seen=len(unseen_shadows),
        evaluations_seen=len(unseen_evaluations),
    )

    # Build a plan of (message, member_shadow_ids) so a fixture-GROUP card can
    # mark EACH member shadow delivered on success. Per-shadow dedup keys
    # (``shadow:{id}``) — not the group id — are the durable at-most-once key, so
    # a later NEW shadow in the same fixture never re-sends already-delivered
    # shadows (they are already excluded by select_unseen_shadows).
    plan: list[tuple[NotifyMessage, list[str]]] = []
    budget = max(0, int(max_messages))

    # --- shadows first (fixture-grouped or one-per-shadow) ---
    if group_by_fixture_cards:
        for group in group_by_fixture(unseen_shadows):
            if len(plan) >= budget:
                break
            msg = build_group_message(group, now=now, main_sha=main_sha, resolver=resolver)
            member_ids = [shadow_event_id(r) for r in group]
            plan.append((msg, member_ids))
    else:
        for r in unseen_shadows:
            if len(plan) >= budget:
                break
            msg = build_shadow_message(r, now=now, main_sha=main_sha, resolver=resolver)
            plan.append((msg, [shadow_event_id(r)]))

    n_shadow_msgs = len(plan)

    # --- evaluations (one per evaluation) with remaining budget ---
    for r in unseen_evaluations:
        if len(plan) >= budget:
            break
        msg = build_evaluation_message(
            r, now=now, main_sha=main_sha, resolver=resolver, shadow_lookup=shadow_lookup
        )
        # An evaluation's own event_id IS its durable dedup key; no extra members.
        plan.append((msg, []))

    published_shadow_ids: set[str] = set()
    published_eval_ids: set[str] = set()

    # Resolve the effective transport with the publication boundary enforced on
    # the LIVE default path (see the docstring). An injected transport (tests /
    # advanced callers) or a dry run bypasses the env gates by design.
    if dry_run:
        transport = transport or RecordingTransport()
    elif transport is None:
        # Live path, no injected transport: BOTH guards must pass, else send
        # nothing this tick (records stay unseen / queued for a later tick).
        if require_optin and not shadow_feed_publication_enabled():
            return result  # opt-in not enabled: nothing published
        transport = research_telegram_transport()
        if transport is None:
            return result  # no dedicated research channel: fail closed
    for idx, (msg, member_ids) in enumerate(plan):
        res = deliver(msg, transport=transport, ledger=ledger, dry_run=dry_run)
        result.delivery_results.append(res)
        if res.sent:
            result.messages_sent += 1
            if idx < n_shadow_msgs:
                # Record each member shadow's per-shadow key so it is never
                # re-published, even if a future group re-includes context.
                for member in member_ids:
                    ledger.record_member(member, parent=msg)
                    published_shadow_ids.add(member)
            else:
                published_eval_ids.add(msg.event_id)

    result.shadows_published = len(published_shadow_ids)
    result.shadows_queued = result.shadows_seen - result.shadows_published
    result.evaluations_published = len(published_eval_ids)
    result.evaluations_queued = result.evaluations_seen - result.evaluations_published

    return result
