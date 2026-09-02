"""Per-fixture multi-market readout — the public-facing output.

For a given fixture this assembles the full picture across markets — corners
(match total and per side), cards (match total and per side), goals, BTTS — each
carrying:

* the **calibrated probability** (the rigorous claim, the primary output),
* the **directional call** — a SEPARATE claim that is GATED: it is shown only for
  market/league cells where it was proven out-of-sample to beat the
  always-pick-the-favoured-side (home-advantage) baseline, and its probability is
  shown only where that call is also calibrated. Everywhere else the call is
  SUPPRESSED with a plain reason (never shown with a caveat),
* the named **profile features** driving it, and
* its **validated status in that league**.

Crucially, each market is labelled by its validated status:

* corners, cards -> validated skill (except cards in the Championship);
* goals, BTTS    -> at par with naive, shown but explicitly marked
  "no demonstrated skill over base rate".

The calibrated-probability claim and the directional-call claim are INDEPENDENT.
Corners/cards probabilities are validated; directional calls for those same
markets are NOT (they do not beat the home-advantage baseline) and are therefore
suppressed. The directional gate is data-driven, resolved via
:func:`src.research.prediction_engine.scope.directional_status`.

A fixture readout may show a high BTTS probability, but if BTTS has no
demonstrated skill in that league that MUST be stated alongside the number. A
confident-looking probability from a model with no edge over the base rate is
exactly the thing that misleads people.

This module derives everything from the validated engine's per-side PMFs and
derived outcomes (:class:`~src.research.asymmetric.models.FixturePrediction`).
It fits no new model and — per the permanent constraint — contains NO stake
sizing, Kelly fraction, or bankroll guidance of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from src.research.asymmetric.derived import pmf_mean
from src.research.asymmetric.models import DerivedOutcomes, DirectionPrediction, FixturePrediction
from src.research.prediction_engine.directional import DirectionalCall, directional_call
from src.research.prediction_engine.scope import (
    DirectionalStatus,
    MarketScope,
    MarketStatus,
    directional_status,
    honest_framing_lines,
    market_status,
)

# Direction labels must match src.research.asymmetric.interaction.
_DIRECTION_A = "A_attack_vs_B_defence"  # home side acts
_DIRECTION_B = "B_attack_vs_A_defence"  # away side acts


def _prob_over(pmf: Sequence[float], line: float) -> float:
    """P(count > line) from a count PMF (line is a half-integer O/U threshold)."""
    total = 0.0
    for k, p in enumerate(pmf):
        if k > line:
            total += float(p)
    return max(0.0, min(1.0, total))


# ─────────────────────────────────────────────────────────────────────────────
# Per-market readout
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MarketReadout:
    """One market's readout within a fixture.

    Attributes:
        market: market key.
        scope: the validated status of this market in this league.
        p_over_total: calibrated P(match total > line), when a total applies.
        total_line: the O/U line the total probability is for (None if n/a).
        expected_total: expected match total (PMF mean), for reference.
        directional: the per-side directional call (None for symmetric markets
            like BTTS where there is no A-vs-B count comparison).
        dir_status: the data-driven directional gate result for this market/league
            (governs whether the call is emitted, shown with a probability, or
            suppressed with a plain reason).
        driving_features: named features driving the per-side predictions.
    """

    market: str
    scope: MarketScope
    p_over_total: Optional[float]
    total_line: Optional[float]
    expected_total: Optional[float]
    directional: Optional[DirectionalCall]
    dir_status: Optional[DirectionalStatus]
    driving_features: tuple[str, ...]

    @property
    def status_label(self) -> str:
        return self.scope.label

    @property
    def is_validated(self) -> bool:
        return self.scope.is_validated

    def render_lines(self) -> list[str]:
        """Human-readable lines for this market, always carrying the status label."""
        lines: list[str] = []
        header = f"{self.market.upper()}  [{self.status_label}]"
        lines.append(header)
        if self.scope.status is MarketStatus.EXCLUDED:
            lines.append(f"    {self.scope.reason}")
            return lines
        if self.p_over_total is not None and self.total_line is not None:
            lines.append(
                f"    match total: P(over {self.total_line}) = {self.p_over_total:.3f} "
                f"(E[total] = {self.expected_total:.2f})"
            )
        # Directional call is GATED (data-driven, from scope.directional_status):
        # emitted only where it beats the home-advantage baseline; the probability
        # is shown only where it is also calibrated. Elsewhere it is SUPPRESSED
        # (a plain reason, never a caveated call).
        if self.directional is not None and self.dir_status is not None:
            if self.dir_status.emit_call and self.dir_status.show_probability:
                lines.append(f"    directional call: {self.directional.statement()}")
            elif self.dir_status.emit_call:
                # Accuracy gate passed but calibration failed: state direction,
                # withhold the probability figure.
                lines.append(
                    f"    directional call: {self.directional.statement_no_probability()} "
                    "(confidence withheld — not calibrated)"
                )
            else:
                lines.append(f"    {self.dir_status.reason}")
        if self.driving_features:
            lines.append(
                "    driving features: " + ", ".join(self.driving_features[:6])
            )
        if self.scope.status is MarketStatus.NO_DEMONSTRATED_SKILL:
            lines.append(
                "    NOTE: no demonstrated skill over base rate in this league — "
                "shown for completeness, not as a prediction worth acting on."
            )
        return lines


@dataclass(frozen=True)
class FixtureReadout:
    """The full per-fixture, multi-market readout — the public-facing artifact."""

    home_team: str
    away_team: str
    league_label: Optional[str]
    date_unix: int
    markets: tuple[MarketReadout, ...]

    def market(self, key: str) -> Optional[MarketReadout]:
        for m in self.markets:
            if m.market == key:
                return m
        return None

    def validated_markets(self) -> tuple[str, ...]:
        return tuple(m.market for m in self.markets if m.is_validated)

    def render(self) -> str:
        """Render the readout as text, with the mandatory honest framing appended."""
        lines: list[str] = []
        lines.append("=" * 74)
        lines.append(
            f"FIXTURE READOUT — {self.home_team} vs {self.away_team}"
            + (f"  ({self.league_label})" if self.league_label else "")
        )
        lines.append("=" * 74)
        lines.append("")
        for m in self.markets:
            lines.extend(m.render_lines())
            lines.append("")
        lines.append("-" * 74)
        lines.append("HONEST FRAMING")
        lines.extend(honest_framing_lines(prefix="  "))
        lines.append("=" * 74)
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Assembly from the validated engine's FixturePrediction
# ─────────────────────────────────────────────────────────────────────────────

#: Default match-total O/U lines used for the "match total" probability per
#: market (representative lines matching the validated engine's scoring lines).
DEFAULT_TOTAL_LINES: dict[str, float] = {
    "corners": 9.5,
    "cards": 4.5,
    "goals": 2.5,
}


def _side_pmf(
    fixture: FixturePrediction, direction: str, target: str
) -> Optional[tuple[float, ...]]:
    for dp in fixture.directions:
        if dp.direction == direction and dp.target == target:
            return tuple(dp.distribution)
    return None


def _driving_features(fixture: FixturePrediction, target: str) -> tuple[str, ...]:
    names: list[str] = []
    for dp in fixture.directions:
        if dp.target == target:
            for f in dp.driving_features:
                if f not in names:
                    names.append(f)
    return tuple(names)


def build_fixture_readout(
    fixture: FixturePrediction,
    *,
    league_label: Optional[str] = None,
    total_lines: Optional[dict[str, float]] = None,
) -> FixtureReadout:
    """Assemble the multi-market readout from a validated-engine FixturePrediction.

    For corners and cards it builds the match-total probability (from the derived
    convolution PMF) and the per-side directional call (from the two per-side
    PMFs). For goals it builds the match-total and the directional call but
    labels it "no demonstrated skill over base rate". For BTTS it reports the
    derived probability with the same no-skill label and no directional call
    (BTTS is not an A-vs-B count comparison).

    Each market carries its validated status via
    :func:`src.research.prediction_engine.scope.market_status`, so a
    Championship fixture's cards market is rendered as EXCLUDED with its reason.

    Args:
        fixture: the validated engine's per-fixture prediction (per-side PMFs +
            derived outcomes).
        league_label: league identifier used for scope resolution.
        total_lines: optional override of the per-market total O/U lines.
    """
    lines_map = {**DEFAULT_TOTAL_LINES, **(total_lines or {})}
    derived: DerivedOutcomes = fixture.derived

    readouts: list[MarketReadout] = []

    # ---- corners (validated) : match total + directional --------------------
    readouts.append(
        _count_market_readout(
            fixture,
            derived_total=derived.total_corners,
            market="corners",
            target="corners",
            league_label=league_label,
            line=lines_map.get("corners", 9.5),
        )
    )

    # ---- cards (validated except Championship) : match total + directional --
    cards_scope = market_status("cards", league_label)
    if cards_scope.status is MarketStatus.EXCLUDED:
        # Do not present a cards prediction where it is not validated.
        readouts.append(
            MarketReadout(
                market="cards", scope=cards_scope, p_over_total=None,
                total_line=None, expected_total=None, directional=None,
                dir_status=None, driving_features=(),
            )
        )
    else:
        readouts.append(
            _count_market_readout(
                fixture,
                derived_total=derived.total_cards,
                market="cards",
                target="cards",
                league_label=league_label,
                line=lines_map.get("cards", 4.5),
            )
        )

    # ---- goals (no demonstrated skill) : match total + directional, labelled -
    readouts.append(
        _count_market_readout(
            fixture,
            derived_total=derived.total_goals,
            market="goals",
            target="goals",
            league_label=league_label,
            line=lines_map.get("goals", 2.5),
        )
    )

    # ---- BTTS (no demonstrated skill) : probability only, no directional -----
    btts_scope = market_status("btts", league_label)
    readouts.append(
        MarketReadout(
            market="btts",
            scope=btts_scope,
            p_over_total=float(derived.btts_yes),
            total_line=None,
            expected_total=None,
            directional=None,
            dir_status=None,
            driving_features=_driving_features(fixture, "goals"),
        )
    )

    return FixtureReadout(
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        league_label=league_label,
        date_unix=fixture.date_unix,
        markets=tuple(readouts),
    )


def _count_market_readout(
    fixture: FixturePrediction,
    *,
    derived_total: Sequence[float],
    market: str,
    target: str,
    league_label: Optional[str],
    line: float,
) -> MarketReadout:
    """Build a count-market readout: match-total probability + directional call."""
    scope = market_status(market, league_label)
    p_over = _prob_over(derived_total, line)
    expected_total = pmf_mean(derived_total)

    pmf_home = _side_pmf(fixture, _DIRECTION_A, target)
    pmf_away = _side_pmf(fixture, _DIRECTION_B, target)
    call: Optional[DirectionalCall] = None
    if pmf_home is not None and pmf_away is not None:
        call = directional_call(
            market, pmf_home, pmf_away, side_a_label="home", side_b_label="away"
        )
    dir_status = directional_status(market, league_label)

    return MarketReadout(
        market=market,
        scope=scope,
        p_over_total=p_over,
        total_line=line,
        expected_total=expected_total,
        directional=call,
        dir_status=dir_status,
        driving_features=_driving_features(fixture, target),
    )
