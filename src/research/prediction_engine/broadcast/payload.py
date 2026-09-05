"""The broadcast payload — a probability with provenance, and nothing more.

WHAT A PAYLOAD CONTAINS
=======================
For one fixture: the fixture and league, kickoff in UTC, the engine's probability
for each in-scope market **stated for both sides**, the provenance needed to check
the claim later (``model_version``, ``data_cutoff_utc``, ``generated_at_utc``), the
scope version it was published under, and a commitment hash over the exact payload.

WHAT IT MUST NOT CONTAIN
========================
No stake size, unit sizing, or Kelly fraction. No expected value, edge, or "value"
figure. No recommended side or pick. No confidence label unless the confidence rule
is declared in config and therefore applied identically to every fixture. No
language implying a bet should be placed. This is the permanent constraint from
:mod:`src.research._ev_deprecation`, and here it is enforced in code rather than
left to reviewer discipline: :func:`assert_forecast_only` inspects the rendered
message and **raises** before anything can be sent.

BOTH SIDES, ALWAYS
==================
:class:`MarketForecast` cannot hold one side without the other — ``p_under`` is the
exact complement of ``p_over``, and the renderer emits both figures on every market
row. Surfacing only the over is how a probability becomes an implied recommendation,
so :func:`assert_forecast_only` also verifies structurally that every market row
carries two complementary figures.

WHY THE HASH IS COMPUTED BEFORE SENDING
=======================================
The commitment hash is over the payload as published, including its timestamps —
which are semantic inputs here, not incidental metadata. Hashing before the send
means the stored record can be checked against the message that went out, and a
forecast cannot be quietly reworded after the result is known. Canonical JSON rules
follow :mod:`src.persistence.hashing`: sorted keys, compact separators, UTF-8,
computed here and never accepted from a caller.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from src.research.prediction_engine.broadcast.scope_config import (
    ConfidenceLabelRule,
    MarketSpec,
    ScopeConfig,
)

#: Payload contract. Bumping this changes every commitment hash, which is correct:
#: a payload with different semantics is not comparable to an older one.
FORECAST_PAYLOAD_CONTRACT = "forecast-broadcast-payload/v1"

#: Probabilities are stored at this precision and hashed as stored, so a recomputed
#: hash from the persisted record reproduces the published hash exactly.
_PROB_PLACES = 4


class ForecastContentError(ValueError):
    """The rendered message violates the forecast-only contract.

    Raised, never warned. A message that has drifted toward recommendation framing
    must not be delivered, so the failure has to stop the send.
    """


# ─────────────────────────────────────────────────────────────────────────────
# Forbidden content
# ─────────────────────────────────────────────────────────────────────────────
#: Vocabulary that must never appear in a published forecast. Matched on word
#: boundaries so ordinary football names are unaffected ("Betis" is not "bet",
#: "United" is not "unit", "Edgeley" is not "edge").
#:
#: The renderer in this module is the only producer of broadcast text and emits none
#: of these. This list is defence in depth: it makes a future edit that reintroduces
#: stake, EV, or tipping language fail loudly at send time instead of shipping.
FORBIDDEN_TOKENS: tuple[str, ...] = (
    # stake sizing / bankroll
    "stake", "stakes", "staking", "unit", "units", "kelly", "bankroll",
    "liability", "exposure",
    # EV / edge / value framing
    "ev", "roi", "edge", "edges", "value", "overlay", "overround", "vig",
    "devig", "fair",
    # recommendation / tipping
    "tip", "tips", "tipster", "pick", "picks", "selection", "recommend",
    "recommended", "recommendation", "advice", "advise",
    # placing a bet
    "bet", "bets", "betting", "bettor", "wager", "wagers", "wagering",
    "punt", "punter", "stakeout",
    # persuasion
    "lock", "banger", "banker", "nap", "guaranteed", "profit", "profitable",
    "winner", "beats", "sharp",
)

#: Multi-word phrasing that must never appear, checked case-insensitively.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    "expected value", "value bet", "beat the market", "beats the market",
    "+ev", "-ev", "worth backing", "worth a", "place a", "get on",
    "back the", "lay the", "double chance play", "best price",
)

#: Only permitted when a confidence rule is declared in config.
_CONFIDENCE_TOKENS: tuple[str, ...] = ("confidence", "confident")

_TOKEN_PATTERNS: dict[str, re.Pattern[str]] = {
    token: re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE)
    for token in FORBIDDEN_TOKENS + _CONFIDENCE_TOKENS
}


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Market forecast — two-sided by construction
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class MarketForecast:
    """One in-scope market's probability, stated for both sides.

    A market the engine could not price is represented with both probabilities
    ``None`` and a plain ``unavailable_reason``. It is still published: stating that
    a declared market could not be priced is part of honest coverage, whereas
    dropping the row would quietly narrow the published scope.
    """

    market: str
    line: Optional[float]
    over_label: str
    under_label: str
    p_over: Optional[float]
    p_under: Optional[float]
    unavailable_reason: Optional[str] = None
    confidence_label: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.p_over is None) != (self.p_under is None):
            raise ForecastContentError(
                f"market {self.market!r} has only one side priced; a forecast is "
                "published for both sides or for neither"
            )
        if self.p_over is None:
            if not self.unavailable_reason:
                raise ForecastContentError(
                    f"market {self.market!r} has no probability and no reason; an "
                    "unpriced market must say why"
                )
            return
        for side, value in (("over", self.p_over), ("under", self.p_under)):
            if not 0.0 <= float(value) <= 1.0:
                raise ForecastContentError(
                    f"market {self.market!r} {side} probability {value!r} is not a "
                    "probability"
                )
        total = round(float(self.p_over) + float(self.p_under), _PROB_PLACES)
        if abs(total - 1.0) > 10 ** -_PROB_PLACES:
            raise ForecastContentError(
                f"market {self.market!r} sides sum to {total} — the two sides of a "
                "published market must be exact complements"
            )

    @property
    def is_priced(self) -> bool:
        return self.p_over is not None

    def display_pair(self) -> tuple[str, str]:
        """Displayed over/under figures as whole-number percentages summing to 100%.

        The under side is the complement of the *displayed* over percentage, so the
        two figures shown always sum to 100% regardless of rounding. This is a
        presentation-only change: the stored/hashed probabilities keep ``_PROB_PLACES``
        precision, so commitment hashes are unaffected.
        """
        if not self.is_priced:
            return ("n/a", "n/a")
        over_pct = round(float(self.p_over) * 100.0)
        under_pct = 100 - over_pct
        return (f"{over_pct}%", f"{under_pct}%")

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "line": self.line,
            "over_label": self.over_label,
            "under_label": self.under_label,
            "p_over": self.p_over,
            "p_under": self.p_under,
            "unavailable_reason": self.unavailable_reason,
            "confidence_label": self.confidence_label,
        }


def build_market_forecast(
    spec: MarketSpec,
    p_over: Optional[float],
    *,
    unavailable_reason: Optional[str] = None,
    confidence_rule: Optional[ConfidenceLabelRule] = None,
) -> MarketForecast:
    """Build a two-sided market forecast from a one-sided engine probability.

    The engine reports ``P(over line)``; the under side is its exact complement.
    Deriving it here — rather than leaving it to a renderer — is what makes it
    impossible to publish a market with only the over surfaced.

    Args:
        spec: the declared market and its declared line.
        p_over: engine probability for the over side, or None if unavailable.
        unavailable_reason: required when ``p_over`` is None.
        confidence_rule: the config-declared confidence rule, applied identically
            to every market of every fixture. None means no label is emitted.
    """
    if p_over is None:
        return MarketForecast(
            market=spec.market, line=spec.line,
            over_label=spec.over_label, under_label=spec.under_label,
            p_over=None, p_under=None,
            unavailable_reason=unavailable_reason or "engine produced no probability",
        )
    over = round(float(p_over), _PROB_PLACES)
    under = round(1.0 - over, _PROB_PLACES)
    label = confidence_rule.label_for(over) if confidence_rule is not None else None
    return MarketForecast(
        market=spec.market, line=spec.line,
        over_label=spec.over_label, under_label=spec.under_label,
        p_over=over, p_under=under, confidence_label=label,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fixture payload
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class ForecastPayload:
    """The exact published artifact for one fixture, and its commitment hash."""

    fixture_id: str
    comp_id: Optional[str]
    league_label: Optional[str]
    home_team: str
    away_team: str
    kickoff_unix: int
    markets: tuple[MarketForecast, ...]
    model_version: str
    data_cutoff_utc: str
    generated_at_utc: str
    scope_version_hash: str
    horizon_hours_before_kickoff: int
    horizon_target_utc: str

    @property
    def kickoff_utc(self) -> str:
        return _iso(self.kickoff_unix)

    @property
    def fixture_label(self) -> str:
        return f"{self.home_team} vs {self.away_team}"

    @property
    def priced_markets(self) -> tuple[MarketForecast, ...]:
        return tuple(m for m in self.markets if m.is_priced)

    def canonical_dict(self) -> dict[str, Any]:
        """The exact object the commitment hash is computed over.

        Timestamps are included deliberately. In a commitment they are semantic
        inputs: when the forecast was generated, and how far back its data went, are
        part of the claim being made.
        """
        return {
            "payload_contract": FORECAST_PAYLOAD_CONTRACT,
            "fixture_id": self.fixture_id,
            "comp_id": self.comp_id,
            "league_label": self.league_label,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "kickoff_unix": int(self.kickoff_unix),
            "kickoff_utc": self.kickoff_utc,
            "markets": [m.canonical_dict() for m in self.markets],
            "model_version": self.model_version,
            "data_cutoff_utc": self.data_cutoff_utc,
            "generated_at_utc": self.generated_at_utc,
            "scope_version_hash": self.scope_version_hash,
            "horizon_hours_before_kickoff": int(self.horizon_hours_before_kickoff),
            "horizon_target_utc": self.horizon_target_utc,
        }

    def commitment_hash(self) -> str:
        """64-char SHA-256 over the payload's canonical JSON."""
        return _sha256(_canonical_json(self.canonical_dict()))


def build_forecast_payload(
    *,
    config: ScopeConfig,
    fixture_id: str,
    comp_id: Optional[str],
    home_team: str,
    away_team: str,
    kickoff_unix: float,
    probabilities: dict[tuple[str, Optional[float]], Optional[float]],
    unavailable_reasons: Optional[dict[tuple[str, Optional[float]], str]] = None,
    model_version: str,
    data_cutoff_utc: str,
    generated_at_utc: str,
) -> ForecastPayload:
    """Assemble a fixture payload covering **every** market in declared scope.

    The market list is driven entirely by ``config.markets``. A market absent from
    ``probabilities`` becomes an explicitly unavailable row rather than a missing
    one, and no market outside declared scope can be added — the loop never reads
    keys that the config did not declare.

    There is no filtering here by probability, by how confident the engine is, or by
    anything else. Every declared market is represented for every fixture.

    Note the absence of a price argument. The forecast layer has no parameter through
    which a price could reach it, which is what keeps the two layers separate by
    construction rather than by convention.

    Args:
        config: the declared scope in force.
        fixture_id: provider fixture identifier.
        comp_id: provider competition identifier.
        home_team: home team name.
        away_team: away team name.
        kickoff_unix: kickoff as a UTC epoch.
        probabilities: engine ``P(over line)`` keyed by ``(market, line)`` cell.
        unavailable_reasons: plain reasons keyed by cell, for unpriced markets.
        model_version: content hash identifying the model that produced these
            probabilities.
        data_cutoff_utc: latest observation the model was fitted on.
        generated_at_utc: when this payload was generated.

    Returns:
        The assembled :class:`ForecastPayload`.
    """
    reasons = unavailable_reasons or {}
    markets: list[MarketForecast] = []
    for spec in config.markets:
        cell = spec.cell
        markets.append(
            build_market_forecast(
                spec,
                probabilities.get(cell),
                unavailable_reason=reasons.get(cell),
                confidence_rule=config.confidence_label_rule,
            )
        )

    horizon_target = _iso(float(kickoff_unix) - config.horizon_seconds)
    return ForecastPayload(
        fixture_id=str(fixture_id),
        comp_id=comp_id,
        league_label=config.league_label(comp_id),
        home_team=str(home_team),
        away_team=str(away_team),
        kickoff_unix=int(float(kickoff_unix)),
        markets=tuple(markets),
        model_version=model_version,
        data_cutoff_utc=data_cutoff_utc,
        generated_at_utc=generated_at_utc,
        scope_version_hash=config.scope_version_hash,
        horizon_hours_before_kickoff=config.horizon_hours_before_kickoff,
        horizon_target_utc=horizon_target,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────
def render_message(payload: ForecastPayload) -> str:
    """Render the Telegram message: a probability with provenance, nothing more.

    Plain text with no ``parse_mode``, matching the transport convention used by the
    other Telegram senders in this repo (no markup means no escaping burden and no
    chance of a team name breaking the message).

    Every market row states both sides. Every message states the model version, the
    data cutoff, when it was generated, and the commitment hash over the payload —
    the four things needed to check the forecast against the record afterwards.
    """
    lines: list[str] = []
    lines.append("FORECAST")
    lines.append(payload.fixture_label)
    if payload.league_label:
        lines.append(payload.league_label)
    lines.append(f"Kick-off: {payload.kickoff_utc}")
    lines.append("")
    lines.append(f"Model probabilities (published at T-{payload.horizon_hours_before_kickoff}h):")

    for market in payload.markets:
        if not market.is_priced:
            lines.append(f"  {market.over_label}: not published — {market.unavailable_reason}")
            continue
        over_display, under_display = market.display_pair()
        row = (
            f"  {market.over_label} {over_display}"
            f"  /  {market.under_label} {under_display}"
        )
        if market.confidence_label:
            row += f"  [{market.confidence_label}]"
        lines.append(row)

    lines.append("")
    lines.append(f"model_version: {payload.model_version}")
    lines.append(f"data_cutoff_utc: {payload.data_cutoff_utc}")
    lines.append(f"generated_at_utc: {payload.generated_at_utc}")
    lines.append(f"commitment: {payload.commitment_hash()}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# The content gate
# ─────────────────────────────────────────────────────────────────────────────
def find_forbidden_content(
    text: str, *, allow_confidence_label: bool = False
) -> tuple[str, ...]:
    """Return every forbidden token or phrase found in ``text``.

    Args:
        text: the rendered message.
        allow_confidence_label: True only when a confidence rule is declared in
            config, which is the sole condition under which a confidence label may
            appear at all.
    """
    found: list[str] = []
    lowered = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            found.append(f"phrase:{phrase}")
    for token, pattern in _TOKEN_PATTERNS.items():
        if token in _CONFIDENCE_TOKENS and allow_confidence_label:
            continue
        if pattern.search(text):
            found.append(f"token:{token}")
    return tuple(sorted(set(found)))


def assert_forecast_only(
    text: str,
    payload: ForecastPayload,
    *,
    allow_confidence_label: bool = False,
) -> None:
    """Fail closed unless ``text`` is a two-sided probability with provenance.

    Two independent checks, because either one alone is escapable:

    1. **Vocabulary.** No stake, EV/edge/value, tipping, or bet-placement language.
    2. **Structure.** Every priced market shows two figures that sum to 1.00, and
       the provenance fields are all present. A message that dropped the under side
       would pass a word-list check while still implying a recommendation, so the
       structural check is the one that actually guarantees two-sidedness.

    Raises:
        ForecastContentError: on any violation. The caller must not send.
    """
    forbidden = find_forbidden_content(
        text, allow_confidence_label=allow_confidence_label
    )
    if forbidden:
        raise ForecastContentError(
            "message contains content forbidden in a forecast broadcast "
            f"({', '.join(forbidden)}). A broadcast is a probability with "
            "provenance: no stake sizing, no expected value or edge, no "
            "recommended side, and no language implying a bet should be placed."
        )

    for market in payload.priced_markets:
        over_display, under_display = market.display_pair()
        if market.over_label not in text or market.under_label not in text:
            raise ForecastContentError(
                f"market {market.market!r} does not state both sides in the message; "
                "surfacing only one side turns a probability into a recommendation"
            )
        if over_display not in text or under_display not in text:
            raise ForecastContentError(
                f"market {market.market!r} does not show both probabilities"
            )
        # display_pair() renders whole-number percentages like "59%"/"41%"; parse the
        # numeric part and require the two shown sides to sum to 100%.
        over_pct = float(over_display.rstrip("%"))
        under_pct = float(under_display.rstrip("%"))
        if abs(over_pct + under_pct - 100.0) > 1e-9:
            raise ForecastContentError(
                f"market {market.market!r} displayed sides do not sum to 100%"
            )

    for field_name, value in (
        ("model_version", payload.model_version),
        ("data_cutoff_utc", payload.data_cutoff_utc),
        ("generated_at_utc", payload.generated_at_utc),
    ):
        if not value or f"{field_name}: {value}" not in text:
            raise ForecastContentError(
                f"message lacks required provenance field {field_name!r}; a forecast "
                "without provenance cannot be checked later"
            )
    if payload.commitment_hash() not in text:
        raise ForecastContentError(
            "message lacks the commitment hash over its own payload"
        )


def render_checked_message(
    payload: ForecastPayload, config: ScopeConfig
) -> str:
    """Render and gate in one step, so no caller can send an ungated message."""
    text = render_message(payload)
    assert_forecast_only(
        text, payload, allow_confidence_label=config.emits_confidence_label
    )
    return text


def payload_from_canonical_dict(obj: dict[str, Any]) -> ForecastPayload:
    """Rebuild a payload from its persisted canonical form.

    Used to verify a stored record's hash and to re-send a queued message with its
    original hash intact. A rebuilt payload must reproduce the published hash
    exactly; if it does not, the record and the message have diverged.
    """
    contract = obj.get("payload_contract")
    if contract != FORECAST_PAYLOAD_CONTRACT:
        raise ForecastContentError(
            f"unsupported payload_contract {contract!r}; expected "
            f"{FORECAST_PAYLOAD_CONTRACT!r}"
        )
    markets = tuple(
        MarketForecast(
            market=m["market"],
            line=m.get("line"),
            over_label=m["over_label"],
            under_label=m["under_label"],
            p_over=m.get("p_over"),
            p_under=m.get("p_under"),
            unavailable_reason=m.get("unavailable_reason"),
            confidence_label=m.get("confidence_label"),
        )
        for m in obj.get("markets", [])
    )
    return ForecastPayload(
        fixture_id=obj["fixture_id"],
        comp_id=obj.get("comp_id"),
        league_label=obj.get("league_label"),
        home_team=obj["home_team"],
        away_team=obj["away_team"],
        kickoff_unix=int(obj["kickoff_unix"]),
        markets=markets,
        model_version=obj["model_version"],
        data_cutoff_utc=obj["data_cutoff_utc"],
        generated_at_utc=obj["generated_at_utc"],
        scope_version_hash=obj["scope_version_hash"],
        horizon_hours_before_kickoff=int(obj["horizon_hours_before_kickoff"]),
        horizon_target_utc=obj["horizon_target_utc"],
    )


def verify_commitment(record_payload: dict[str, Any], commitment_hash: str) -> bool:
    """True iff ``record_payload`` re-hashes to ``commitment_hash``."""
    try:
        rebuilt = payload_from_canonical_dict(record_payload)
    except (ForecastContentError, KeyError, TypeError):
        return False
    return rebuilt.commitment_hash() == commitment_hash


def iter_declared_cells(config: ScopeConfig) -> Iterable[tuple[str, Optional[float]]]:
    """The declared market cells. The only cells any producer may compute."""
    for spec in config.markets:
        yield spec.cell
