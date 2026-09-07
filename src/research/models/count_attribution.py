"""Per-fixture attribution: why this number, in football terms, from the fit.

The customer is making their own decision, so a bare probability is not enough —
the output has to say what is driving it. This module produces that explanation
and it produces it from one place only: the fitted model.

**What this is.** For each side of a fixture, ``log mu`` is a sum of terms:
``weight x standardised feature value`` for each feature, plus the league
intercept, plus the two team states. Those terms *are* the explanation. Ranking
them by absolute size and naming each one in football language gives an honest
account of the model's arithmetic. The direction of every statement is the sign of
a fitted contribution; the magnitude is its size. Nothing is asserted that the
model does not itself compute.

**What this deliberately is not.** It is not a rule miner. Searching for
condition-pairs and thresholds — "when crosses > p70 and opponent clearances >
p60, corners exceed 10.5 in 68% of matches" — discretises continuous features,
discards information, and manufactures exactly the multiple-testing burden that
wiped out every prior discovery run under FDR correction. The regression already
learns those conditions continuously and with far fewer degrees of freedom. There
is no threshold search here and no place to add one.

It is also not a hand-authored narrative. :data:`FEATURE_LEXICON` is a vocabulary,
not a heuristic: it maps a feature name to a noun phrase and nothing else. It
carries no direction, no magnitude and no conditional logic. If a fitted weight
flips sign, every statement built from that feature flips with it automatically.

**Near the base rate, it says so.** ``no strong signal either way`` is a real
output, not a fallback, and it is decided by comparing the fixture against a
reference fixture built from the model's own training means. Manufacturing a
narrative for a fixture the model is neutral on would be the most misleading
thing this layer could do.

The content gate applies to everything generated here: no skill, edge, expected
value, or recommendation language. That is asserted by
``tests/research/test_count_attribution.py::test_explanations_pass_the_content_gate``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from src.research.models.hierarchical_market_model import (
    HierarchicalCountModel,
    MatchCountDistribution,
    NotFittedError,
    SideRow,
)
from src.research.models.market_family import MarketFamily

# ─────────────────────────────────────────────────────────────────────────────
# Vocabulary
# ─────────────────────────────────────────────────────────────────────────────
#: Feature name -> the football thing it measures, as a noun phrase.
#: Direction and weight come from the fit, never from this table. Every phrase is
#: neutral: it describes a quantity, it does not say whether more of it is good.
FEATURE_LEXICON: dict[str, str] = {
    "own_produce_corners": "corners won",
    "own_produce_dangerous_attacks": "attacking pressure",
    "own_produce_shots_off_target": "shots going wide or blocked",
    "own_produce_shots_on_target": "shots on target",
    "own_produce_shots": "shot volume",
    "own_produce_xg": "chance quality",
    "own_produce_fouls": "fouls committed",
    "own_produce_cards": "cards collected",
    "own_produce_first_half_goals": "first-half goals scored",
    "own_produce_first_half_corners": "first-half corners won",
    "own_produce_first_half_cards": "first-half cards collected",
    "opp_concede_corners": "corners conceded",
    "opp_concede_dangerous_attacks": "attacking pressure allowed",
    "opp_concede_shots_on_target": "shots on target allowed",
    "opp_concede_shots": "shots allowed",
    "opp_concede_xg": "chance quality allowed",
    "opp_concede_fouls": "fouls drawn",
    "opp_concede_cards": "cards drawn from opponents",
    "opp_concede_first_half_goals": "first-half goals conceded",
    "opp_concede_first_half_corners": "first-half corners conceded",
    "is_home": "home advantage",
    "support_n": "how many recent matches stand behind the estimate",
}

#: What each family is counting, for readable statements.
COUNT_NOUN: dict[str, str] = {
    "goals": "goals",
    "corners": "corners",
    "cards": "cards",
    "shots_on_target": "shots on target",
    "first_half_goals": "first-half goals",
    "first_half_corners": "first-half corners",
    "first_half_cards": "first-half cards",
}

LEAN_OVER = "higher"
LEAN_UNDER = "lower"
LEAN_NEUTRAL = "neutral"

NO_SIGNAL_STATEMENT = "no strong signal either way"

#: How far the fixture's line probabilities must move away from a league-typical
#: fixture before the model is treated as saying anything. Three points of
#: probability is about the resolution a reader can act on and comfortably inside
#: the model's own uncertainty on a thin fixture.
DEFAULT_SIGNAL_THRESHOLD = 0.03

#: Standardised distance from the training mean, mapped to plain description.
#: This describes the *feature value*, which is data. Whether it matters is the
#: weight's job.
_MAGNITUDE_BANDS: tuple[tuple[float, str], ...] = (
    (1.5, "far above their norm"),
    (0.75, "well above their norm"),
    (0.25, "above their norm"),
    (-0.25, "around their norm"),
    (-0.75, "below their norm"),
    (-1.5, "well below their norm"),
)


#: Features that take the same value for every fixture and so cancel against the
#: reference fixture. They are real terms in ``log mu`` and stay in the audit
#: record, but they explain nothing about why one fixture differs from another,
#: so they never appear as ranked drivers.
_STRUCTURAL_FEATURES: frozenset[str] = frozenset({"is_home", "support_n"})


def _magnitude_phrase(standardised: float) -> str:
    for threshold, phrase in _MAGNITUDE_BANDS:
        if standardised >= threshold:
            return phrase
    return "far below their norm"


# ─────────────────────────────────────────────────────────────────────────────
# Drivers
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class Driver:
    """One additive term in ``log mu``, with everything behind it kept.

    ``contribution`` is ``weight * standardised_value``. Its sign is the only
    source of the direction in any statement built from this driver.
    """

    kind: str
    feature: Optional[str]
    team: str
    raw_value: Optional[float]
    standardised_value: Optional[float]
    weight: Optional[float]
    contribution: float
    #: Set for team-state drivers, so thin evidence can be stated as such.
    n_observations: Optional[int] = None
    shrinkage_weight: Optional[float] = None

    @property
    def pushes_up(self) -> bool:
        return self.contribution > 0.0

    @property
    def magnitude(self) -> float:
        return abs(self.contribution)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": self.kind,
            "feature": self.feature,
            "team": self.team,
            "contribution": round(self.contribution, 6),
            "direction": "up" if self.pushes_up else "down",
        }
        if self.raw_value is not None:
            payload["raw_value"] = round(self.raw_value, 4)
        if self.standardised_value is not None:
            payload["standardised_value"] = round(self.standardised_value, 4)
        if self.weight is not None:
            payload["weight"] = round(self.weight, 6)
        if self.n_observations is not None:
            payload["n_observations"] = self.n_observations
        if self.shrinkage_weight is not None:
            payload["shrinkage_weight"] = round(self.shrinkage_weight, 4)
        return payload


@dataclass(frozen=True, slots=True)
class MarketExplanation:
    """The ranked drivers behind one family's lines, and the readable form."""

    family: str
    count_noun: str
    expected_total: float
    reference_total: float
    lean: str
    signal_strength: float
    line_probabilities: Mapping[float, float]
    reference_probabilities: Mapping[float, float]
    drivers: tuple[Driver, ...]
    statements: tuple[str, ...]
    thin_evidence_note: Optional[str] = None

    @property
    def has_signal(self) -> bool:
        return self.lean != LEAN_NEUTRAL

    def text(self) -> str:
        """One readable paragraph, safe to publish under the content gate."""
        if not self.has_signal:
            body = (
                f"{self.count_noun}: {NO_SIGNAL_STATEMENT}. The model puts this "
                f"fixture close to a typical one in this league "
                f"({self.expected_total:.1f} expected against "
                f"{self.reference_total:.1f} for the league norm)."
            )
        else:
            direction = "leans higher" if self.lean == LEAN_OVER else "leans lower"
            body = (
                f"{self.count_noun} {direction}: "
                + "; ".join(self.statements)
                + f". Expected {self.count_noun} {self.expected_total:.1f} against "
                f"{self.reference_total:.1f} for a league-typical fixture."
            )
        if self.thin_evidence_note:
            body += " " + self.thin_evidence_note
        return body

    def to_dict(self) -> dict[str, object]:
        return {
            "family": self.family,
            "expected_total": round(self.expected_total, 4),
            "reference_total": round(self.reference_total, 4),
            "lean": self.lean,
            "has_signal": self.has_signal,
            "signal_strength": round(self.signal_strength, 6),
            "line_probabilities": {
                str(line): round(value, 6)
                for line, value in sorted(self.line_probabilities.items())
            },
            "reference_probabilities": {
                str(line): round(value, 6)
                for line, value in sorted(self.reference_probabilities.items())
            },
            "drivers": [driver.to_dict() for driver in self.drivers],
            "statements": list(self.statements),
            "text": self.text(),
            "attribution_source": "fitted_model_coefficients",
            "thin_evidence_note": self.thin_evidence_note,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Building the explanation
# ─────────────────────────────────────────────────────────────────────────────
def _side_drivers(
    model: HierarchicalCountModel, row: SideRow, *, count_noun: str
) -> list[Driver]:
    layer = model.global_layer
    if layer is None:
        raise NotFittedError(f"{model.family.name} model is not fitted")
    drivers: list[Driver] = []
    for name in model.feature_names:
        mean = layer.feature_means[name]
        scale = layer.feature_scales[name]
        raw_value = float(row.features.get(name, mean))
        standardised = (raw_value - mean) / scale
        weight = layer.weights[name]
        slope = model.league_slopes.get((row.league, name))
        if slope is not None:
            weight += slope.posterior
        drivers.append(
            Driver(
                kind="feature",
                feature=name,
                team=row.counting_label if name.startswith("own_") else row.opposing_label,
                raw_value=raw_value,
                standardised_value=standardised,
                weight=weight,
                contribution=weight * standardised,
            )
        )

    attack = model.attack_effects.get((row.league, row.counting_team))
    if attack is not None:
        drivers.append(
            Driver(
                kind="team_attack",
                feature=None,
                team=row.counting_label,
                raw_value=None,
                standardised_value=None,
                weight=None,
                contribution=attack.posterior,
                n_observations=attack.n_observations,
                shrinkage_weight=attack.shrinkage_weight,
            )
        )
    concede = model.concede_effects.get((row.league, row.opposing_team))
    if concede is not None:
        drivers.append(
            Driver(
                kind="team_concede",
                feature=None,
                team=row.opposing_label,
                raw_value=None,
                standardised_value=None,
                weight=None,
                contribution=concede.posterior,
                n_observations=concede.n_observations,
                shrinkage_weight=concede.shrinkage_weight,
            )
        )
    return drivers


def _statement(driver: Driver, count_noun: str) -> Optional[str]:
    """Render one driver. Direction comes from the fitted contribution's sign."""
    if driver.kind == "feature":
        assert driver.feature is not None
        if driver.feature in _STRUCTURAL_FEATURES:
            return None  # structural; reported separately, never as a driver
        phrase = FEATURE_LEXICON.get(driver.feature)
        if phrase is None:
            return None
        magnitude = _magnitude_phrase(driver.standardised_value or 0.0)
        return f"{driver.team} {phrase} {magnitude}"
    if driver.kind == "team_attack":
        tendency = "generates more" if driver.pushes_up else "generates fewer"
        return f"{driver.team} {tendency} {count_noun} than the league"
    if driver.kind == "team_concede":
        tendency = "allows more" if driver.pushes_up else "allows fewer"
        return f"{driver.team} {tendency} {count_noun} than the league"
    return None


def _reference_row(model: HierarchicalCountModel, row: SideRow) -> SideRow:
    """The same fixture stripped to a league-typical one.

    Every feature is set to its training mean and both team states are removed by
    naming teams the model has never seen. What remains is the league intercept —
    which is precisely "a typical fixture in this league", the reference the
    signal test needs. Deriving it from the fit means the neutrality threshold is
    not a hand-set base rate either.
    """
    layer = model.global_layer
    assert layer is not None
    features = dict(layer.feature_means)
    features["is_home"] = 1.0 if row.is_home else 0.0
    return SideRow(
        fixture_id=row.fixture_id,
        league=row.league,
        season=row.season,
        kickoff_unix=row.kickoff_unix,
        counting_team="\x00reference",
        opposing_team="\x00reference",
        is_home=row.is_home,
        features=features,
        count=None,
    )


def explain_market(
    model: HierarchicalCountModel,
    home_row: SideRow,
    away_row: SideRow,
    *,
    max_drivers: int = 3,
    signal_threshold: float = DEFAULT_SIGNAL_THRESHOLD,
) -> MarketExplanation:
    """Rank the fitted contributions behind one family's published lines."""
    family: MarketFamily = model.family
    count_noun = COUNT_NOUN.get(family.name, family.name.replace("_", " "))
    fixture = model.predict_match(home_row, away_row)
    reference = model.predict_match(
        _reference_row(model, home_row), _reference_row(model, away_row)
    )

    line_probabilities = {line: fixture.p_over(line) for line in family.lines}
    reference_probabilities = {line: reference.p_over(line) for line in family.lines}
    deltas = [
        line_probabilities[line] - reference_probabilities[line] for line in family.lines
    ]
    signed = max(deltas, key=abs) if deltas else 0.0
    signal_strength = abs(signed)
    if signal_strength < signal_threshold:
        lean = LEAN_NEUTRAL
    else:
        lean = LEAN_OVER if signed > 0 else LEAN_UNDER

    drivers = _side_drivers(model, home_row, count_noun=count_noun) + _side_drivers(
        model, away_row, count_noun=count_noun
    )
    # Rank by how much each term actually moved log mu, in the leaning direction.
    # Structural terms are excluded from the ranking: they take the same value in
    # every fixture and therefore cancel against the reference, so they explain
    # none of why *this* fixture differs. They stay in ``drivers`` for audit.
    relevant = [
        driver
        for driver in drivers
        if driver.feature not in _STRUCTURAL_FEATURES
        and driver.magnitude > 1e-9
        and (lean == LEAN_NEUTRAL or driver.pushes_up == (lean == LEAN_OVER))
    ]
    relevant.sort(key=lambda driver: driver.magnitude, reverse=True)
    ranked = tuple(relevant[:max_drivers])

    statements: list[str] = []
    seen: set[str] = set()
    for driver in ranked:
        rendered = _statement(driver, count_noun)
        if rendered and rendered not in seen:
            seen.add(rendered)
            statements.append(rendered)

    if lean != LEAN_NEUTRAL and not statements:
        # The lean came from terms with no readable form; say so rather than invent.
        lean = LEAN_NEUTRAL

    note = _thin_evidence_note(model, home_row, away_row)
    return MarketExplanation(
        family=family.name,
        count_noun=count_noun,
        expected_total=fixture.expected_total,
        reference_total=reference.expected_total,
        lean=lean,
        signal_strength=signal_strength,
        line_probabilities=line_probabilities,
        reference_probabilities=reference_probabilities,
        drivers=tuple(drivers),
        statements=tuple(statements),
        thin_evidence_note=note,
    )


def _thin_evidence_note(
    model: HierarchicalCountModel, home_row: SideRow, away_row: SideRow
) -> Optional[str]:
    """State plainly when the estimate rests mostly on the league, not the teams.

    A low shrinkage weight means the team's own record barely moved its state, so
    the number is close to a league-average side. That belongs in the explanation,
    because a reader who is not told will assume the opposite.
    """
    notes: list[str] = []
    for row in (home_row, away_row):
        attack = model.attack_effects.get((row.league, row.counting_team))
        if attack is None:
            notes.append(
                f"{row.counting_label} has no fitted team state, so this rests on the "
                "league average"
            )
            continue
        if attack.shrinkage_weight < 0.35:
            notes.append(
                f"{row.counting_label}'s estimate leans on the league average "
                f"({attack.n_observations} match-sides of its own record)"
            )
        if attack.prior_season_decay > 0.25 and abs(attack.prior_season_contribution) > 1e-6:
            notes.append(
                f"{row.counting_label} still carries prior-season information at "
                f"{attack.prior_season_decay:.0%} weight"
            )
    if not notes:
        return None
    return "Note: " + "; ".join(notes) + "."


def explain_fixture(
    models: Mapping[str, HierarchicalCountModel],
    rows_by_family: Mapping[str, tuple[SideRow, SideRow]],
    *,
    max_drivers: int = 3,
) -> dict[str, MarketExplanation]:
    """Explain every family published for one fixture."""
    explanations: dict[str, MarketExplanation] = {}
    for family_name, model in models.items():
        rows = rows_by_family.get(family_name)
        if rows is None:
            continue
        explanations[family_name] = explain_market(
            model, rows[0], rows[1], max_drivers=max_drivers
        )
    return explanations


def render_explanations(explanations: Sequence[MarketExplanation]) -> str:
    """Render explanations as published lines, one per family."""
    return "\n".join(f"  {item.text()}" for item in explanations)
