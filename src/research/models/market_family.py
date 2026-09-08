"""Market families: one count process per family, every line read off one fit.

The unit of modelling here is a **market family**, not a line. ``corners`` is one
family whose distribution is fitted once and read at 7.5, 8.5, 9.5 and 10.5; it is
not four elastic nets that can disagree with each other. That is the whole point of
the count form: ``P(over 9.5) > P(over 8.5)`` is arithmetically impossible when both
come from the survival function of a single fitted distribution, whereas it is
merely unlikely when they come from two independent classifiers.

Each family declares:

* the **side count** it models (goals scored by one side, corners won by one side,
  ...) rather than the match total. The total is the convolution of the two sides,
  which is what lets the goals family answer "both teams to score" from the same
  fit instead of needing a separate BTTS classifier.
* a **compact, mechanism-motivated feature block**. These blocks are deliberately
  small and hand-declared. The 866-feature run added variance rather than signal,
  so there is no search here and no place to put one.
* the **lines** to publish, and for shots on target a stated rationale, because
  that market has no conventional line set.
* the **raw provider fields** it needs, so coverage can be audited per league and a
  family excluded where it is unbuildable instead of zero-filled.

Nothing in this module fits anything. It is the declaration the model, the
evaluator and the coverage audit all read, so the three cannot drift apart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

# ─────────────────────────────────────────────────────────────────────────────
# Family names
# ─────────────────────────────────────────────────────────────────────────────
FAMILY_GOALS = "goals"
FAMILY_CORNERS = "corners"
FAMILY_CARDS = "cards"
FAMILY_SHOTS_ON_TARGET = "shots_on_target"
FAMILY_FIRST_HALF_GOALS = "first_half_goals"
FAMILY_FIRST_HALF_CORNERS = "first_half_corners"
FAMILY_FIRST_HALF_CARDS = "first_half_cards"

#: Families whose totals are published as over/under lines.
ALL_FAMILY_NAMES: tuple[str, ...] = (
    FAMILY_GOALS,
    FAMILY_CORNERS,
    FAMILY_CARDS,
    FAMILY_SHOTS_ON_TARGET,
    FAMILY_FIRST_HALF_GOALS,
    FAMILY_FIRST_HALF_CORNERS,
    FAMILY_FIRST_HALF_CARDS,
)

#: BTTS is not a family. It is derived from the goals family's two side
#: distributions, so it cannot contradict the goals lines.
DERIVED_BTTS = "btts"


# ─────────────────────────────────────────────────────────────────────────────
# Raw provider fields
# ─────────────────────────────────────────────────────────────────────────────
#: Per-side count targets: (home-side field, away-side field).
#: Every family models a SIDE count; the match total is the convolution.
SIDE_TARGET_FIELDS: dict[str, tuple[str, str]] = {
    FAMILY_GOALS: ("homeGoalCount", "awayGoalCount"),
    FAMILY_CORNERS: ("team_a_corners", "team_b_corners"),
    FAMILY_CARDS: ("team_a_cards_num", "team_b_cards_num"),
    FAMILY_SHOTS_ON_TARGET: ("team_a_shotsOnTarget", "team_b_shotsOnTarget"),
    FAMILY_FIRST_HALF_GOALS: ("ht_goals_team_a", "ht_goals_team_b"),
    FAMILY_FIRST_HALF_CORNERS: ("team_a_fh_corners", "team_b_fh_corners"),
    FAMILY_FIRST_HALF_CARDS: ("team_a_fh_cards", "team_b_fh_cards"),
}

#: Cards are yellows + reds when the provider's combined field is absent.
_CARD_FALLBACK: dict[str, tuple[str, str]] = {
    "team_a_cards_num": ("team_a_yellow_cards", "team_a_red_cards"),
    "team_b_cards_num": ("team_b_yellow_cards", "team_b_red_cards"),
}

#: Rolling-form stats: stat name -> (home field, away field).
#: Only stats that exist across the broad corpus appear here. A feature block
#: naming anything else fails closed rather than silently becoming zero.
STAT_FIELDS: dict[str, tuple[str, str]] = {
    "goals": ("homeGoalCount", "awayGoalCount"),
    "shots_on_target": ("team_a_shotsOnTarget", "team_b_shotsOnTarget"),
    "shots": ("team_a_shots", "team_b_shots"),
    "shots_off_target": ("team_a_shotsOffTarget", "team_b_shotsOffTarget"),
    "xg": ("team_a_xg", "team_b_xg"),
    "dangerous_attacks": ("team_a_dangerous_attacks", "team_b_dangerous_attacks"),
    "attacks": ("team_a_attacks", "team_b_attacks"),
    "possession": ("team_a_possession", "team_b_possession"),
    "corners": ("team_a_corners", "team_b_corners"),
    "cards": ("team_a_cards_num", "team_b_cards_num"),
    "fouls": ("team_a_fouls", "team_b_fouls"),
    "first_half_goals": ("ht_goals_team_a", "ht_goals_team_b"),
    "first_half_corners": ("team_a_fh_corners", "team_b_fh_corners"),
    "first_half_cards": ("team_a_fh_cards", "team_b_fh_cards"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Feature blocks
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class FeatureBlock:
    """A compact, hand-declared feature block for one family.

    ``produce`` are stats read from the *counting* side's own recent production;
    ``concede`` are stats read from the *opposing* side's recent record of allowing
    them. That split is the attack/defence mechanism stated as features, and it is
    what makes a side count interpretable: a corner arrives because one team
    creates pressure and the other yields it.

    ``league_varying`` is the small set of slopes permitted to differ by league.
    Everything else has one global slope. Keeping this set tiny is deliberate:
    every league-varying slope is 25 extra parameters estimated on a few hundred
    rows each, which is precisely the variance that sank the independent
    per-league fits.

    ``unavailable_mechanisms`` records mechanisms that belong in this block on
    mechanism grounds but are absent from the broad corpus. They are named so the
    substitution is visible rather than silently forgotten.
    """

    produce: tuple[str, ...]
    concede: tuple[str, ...]
    league_varying: tuple[str, ...] = ()
    unavailable_mechanisms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.produce:
            raise ValueError("a feature block needs at least one produce stat")
        named = set(self.produce) | set(self.concede)
        unknown = sorted(named - set(STAT_FIELDS))
        if unknown:
            raise ValueError(
                "feature block names stats with no provider mapping: "
                + ", ".join(unknown)
            )
        unknown_varying = sorted(set(self.league_varying) - set(self.feature_names()))
        if unknown_varying:
            raise ValueError(
                "league_varying names features not in this block: "
                + ", ".join(unknown_varying)
            )

    def feature_names(self) -> tuple[str, ...]:
        """Feature names in a fixed order, so coefficient vectors are stable."""
        names = [f"own_produce_{stat}" for stat in self.produce]
        names += [f"opp_concede_{stat}" for stat in self.concede]
        names += list(SHARED_FEATURES)
        return tuple(names)


#: Shared across every family: side, and how much history stands behind the row.
#: ``support_n`` is the model's own view of how thin the evidence is; it is a
#: feature, not a filter, so a thin row is down-weighted rather than discarded.
#: A separate "deficit" feature was removed because it is ``window - support_n``
#: and therefore perfectly collinear with it.
SHARED_FEATURES: tuple[str, ...] = ("is_home", "support_n")


def _goal_block() -> FeatureBlock:
    """Goals / BTTS / first-half goals: chance quality and chance volume."""
    return FeatureBlock(
        produce=("shots_on_target", "xg", "shots", "dangerous_attacks"),
        concede=("shots_on_target", "xg"),
        league_varying=("own_produce_xg",),
        unavailable_mechanisms=(
            "shots_inside_box",
            "big_chances",
            "np_expected_goals",
        ),
    )


def _corner_block() -> FeatureBlock:
    """Corners: prior corners, territorial pressure, and blocked/off-target shots.

    ``shots_off_target`` is the closest broad-corpus stand-in for the mechanism
    that actually produces corners — a shot deflected or saved wide restarts play
    from the corner flag. ``dangerous_attacks`` stands in for final-third entries.
    """
    return FeatureBlock(
        produce=("corners", "dangerous_attacks", "shots_off_target"),
        concede=("corners", "dangerous_attacks"),
        league_varying=("own_produce_corners",),
        unavailable_mechanisms=(
            "final_third_entries",
            "accurate_crosses",
            "clearances",
        ),
    )


def _card_block() -> FeatureBlock:
    """Cards: fouls, prior cards, and the possession mismatch that drives both."""
    return FeatureBlock(
        produce=("fouls", "cards"),
        concede=("fouls", "cards"),
        league_varying=("own_produce_cards",),
        unavailable_mechanisms=("tackles", "ground_duels_percentage"),
    )


def _sot_block() -> FeatureBlock:
    """Shots on target: shot volume and territorial pressure."""
    return FeatureBlock(
        produce=("shots_on_target", "shots", "dangerous_attacks", "xg"),
        concede=("shots_on_target", "shots"),
        league_varying=("own_produce_shots",),
        unavailable_mechanisms=(
            "touches_in_penalty_area",
            "big_chances",
            "blocked_shots",
            "interceptions",
        ),
    )


def _first_half_goal_block() -> FeatureBlock:
    """First-half goals: the native half-split prior plus full-match chance quality.

    The half-split field is the direct prior for the market being forecast. The
    full-match chance-quality stats are kept because a half's goal count is a thin
    signal on its own — roughly one goal a half — and shot quality over the whole
    match is the more stable read on how likely a side is to score at all.
    """
    return FeatureBlock(
        produce=("first_half_goals", "shots_on_target", "xg"),
        concede=("first_half_goals", "shots_on_target"),
        league_varying=("own_produce_first_half_goals",),
        unavailable_mechanisms=("shots_inside_box", "big_chances", "np_expected_goals"),
    )


def _first_half_corner_block() -> FeatureBlock:
    return FeatureBlock(
        produce=("first_half_corners", "corners", "dangerous_attacks"),
        concede=("first_half_corners", "corners"),
        league_varying=("own_produce_first_half_corners",),
        unavailable_mechanisms=("final_third_entries", "accurate_crosses", "clearances"),
    )


def _first_half_card_block() -> FeatureBlock:
    return FeatureBlock(
        produce=("first_half_cards", "cards", "fouls"),
        concede=("first_half_cards", "fouls"),
        league_varying=("own_produce_first_half_cards",),
        unavailable_mechanisms=("tackles", "ground_duels_percentage"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# The families
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class MarketFamily:
    """One count process and every line published from it."""

    name: str
    lines: tuple[float, ...]
    features: FeatureBlock
    line_rationale: str
    #: Half-split families are only buildable where the provider populates them.
    requires_half_split: bool = False
    #: Minimum share of a league's completed fixtures that must carry the target
    #: for the family to be built for that league at all.
    min_coverage: float = 0.80

    def __post_init__(self) -> None:
        if self.name not in SIDE_TARGET_FIELDS:
            raise ValueError(f"no side target fields declared for family {self.name!r}")
        if not self.lines:
            raise ValueError(f"family {self.name!r} publishes no lines")
        if len(set(self.lines)) != len(self.lines):
            raise ValueError(f"family {self.name!r} has duplicate lines")
        if tuple(sorted(self.lines)) != self.lines:
            raise ValueError(f"family {self.name!r} lines must be sorted ascending")
        if not 0.0 < self.min_coverage <= 1.0:
            raise ValueError("min_coverage must be in (0, 1]")

    @property
    def side_fields(self) -> tuple[str, str]:
        return SIDE_TARGET_FIELDS[self.name]

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self.features.feature_names()

    @property
    def derives_btts(self) -> bool:
        """Only the full-match goals family carries the both-teams-to-score read."""
        return self.name == FAMILY_GOALS


#: Shots-on-target lines. Measured on the 15,362-fixture broad corpus, match
#: totals have median 9, interquartile range 6–11, and mean 8.75. The four lines
#: below sit inside that interquartile range and bracket the median, giving
#: P(over) from roughly 0.63 down to 0.28. Lines outside the IQR were rejected
#: because their cells settle too rarely to ever calibrate: at 12.5 the over
#: happens in about one match in eight, so a 30-day window would hold a handful of
#: positives per league and the reliability curve would be noise.
SHOTS_ON_TARGET_LINES: tuple[float, ...] = (7.5, 8.5, 9.5, 10.5)
SHOTS_ON_TARGET_RATIONALE = (
    "median 9, IQR 6-11, mean 8.75 on 15,362 completed fixtures; 7.5/8.5/9.5/10.5 "
    "lie inside the IQR and bracket the median (P(over) 0.63 down to 0.28). Tail "
    "lines were rejected because they settle too rarely to calibrate."
)


def default_market_families() -> tuple[MarketFamily, ...]:
    """Every family and line this engine publishes."""
    goal_block = _goal_block()
    corner_block = _corner_block()
    card_block = _card_block()
    return (
        MarketFamily(
            name=FAMILY_GOALS,
            lines=(2.5, 3.5),
            features=goal_block,
            line_rationale="conventional total-goals lines; BTTS derived from the same fit",
        ),
        MarketFamily(
            name=FAMILY_CORNERS,
            lines=(7.5, 8.5, 9.5, 10.5),
            features=corner_block,
            line_rationale="conventional total-corners ladder; monotone by construction",
        ),
        MarketFamily(
            name=FAMILY_CARDS,
            lines=(2.5, 3.5, 4.5),
            features=card_block,
            line_rationale="conventional total-cards ladder",
        ),
        MarketFamily(
            name=FAMILY_SHOTS_ON_TARGET,
            lines=SHOTS_ON_TARGET_LINES,
            features=_sot_block(),
            line_rationale=SHOTS_ON_TARGET_RATIONALE,
        ),
        MarketFamily(
            name=FAMILY_FIRST_HALF_GOALS,
            lines=(0.5, 1.5),
            features=_first_half_goal_block(),
            line_rationale="conventional first-half goals lines",
            requires_half_split=True,
        ),
        MarketFamily(
            name=FAMILY_FIRST_HALF_CORNERS,
            lines=(3.5, 4.5),
            features=_first_half_corner_block(),
            line_rationale=(
                "first-half corners run about half the full-match total (median 9), "
                "so 3.5/4.5 bracket the first-half median"
            ),
            requires_half_split=True,
        ),
        MarketFamily(
            name=FAMILY_FIRST_HALF_CARDS,
            lines=(0.5, 1.5),
            features=_first_half_card_block(),
            line_rationale=(
                "first-half cards are sparse; 0.5/1.5 are the only lines with mass "
                "on both sides"
            ),
            requires_half_split=True,
        ),
    )


def family_by_name(name: str) -> MarketFamily:
    for family in default_market_families():
        if family.name == name:
            return family
    raise KeyError(f"unknown market family {name!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Reading raw values
# ─────────────────────────────────────────────────────────────────────────────
def numeric(value: object) -> Optional[float]:
    """Coerce a provider value, treating the ``-1`` sentinel as missing.

    The provider writes ``-1`` for "not recorded" and ``0`` for "genuinely none".
    Collapsing those two would turn a missing corner count into a goalless-corner
    match, so negatives are refused rather than clamped.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result < 0.0:
        return None
    return result


def side_counts(
    match: Mapping[str, object], family: str
) -> Optional[tuple[float, float]]:
    """Return ``(home_side_count, away_side_count)`` or ``None`` if unbuildable."""
    home_field, away_field = SIDE_TARGET_FIELDS[family]
    values: list[float] = []
    for field_name in (home_field, away_field):
        value = numeric(match.get(field_name))
        if value is None and field_name in _CARD_FALLBACK:
            yellow_key, red_key = _CARD_FALLBACK[field_name]
            yellow = numeric(match.get(yellow_key))
            if yellow is None:
                return None
            value = yellow + (numeric(match.get(red_key)) or 0.0)
        if value is None:
            return None
        values.append(value)
    return values[0], values[1]


def stat_value(
    match: Mapping[str, object], stat: str, *, home: bool
) -> Optional[float]:
    """One team's own value of ``stat`` in ``match``."""
    home_field, away_field = STAT_FIELDS[stat]
    field_name = home_field if home else away_field
    value = numeric(match.get(field_name))
    if value is None and field_name in _CARD_FALLBACK:
        yellow_key, red_key = _CARD_FALLBACK[field_name]
        yellow = numeric(match.get(yellow_key))
        if yellow is None:
            return None
        value = yellow + (numeric(match.get(red_key)) or 0.0)
    return value


def required_stats(families: Iterable[MarketFamily]) -> tuple[str, ...]:
    """Every rolling stat any of ``families`` reads, in declaration order."""
    seen: dict[str, None] = {}
    for family in families:
        for stat in (*family.features.produce, *family.features.concede):
            seen.setdefault(stat, None)
    return tuple(seen)


# ─────────────────────────────────────────────────────────────────────────────
# Coverage audit
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class FamilyCoverage:
    """How much of one league's history can build one family."""

    league: str
    family: str
    n_fixtures: int
    n_buildable: int
    buildable: bool
    reason: str

    @property
    def coverage(self) -> float:
        return self.n_buildable / self.n_fixtures if self.n_fixtures else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "league": self.league,
            "family": self.family,
            "n_fixtures": self.n_fixtures,
            "n_buildable": self.n_buildable,
            "coverage": round(self.coverage, 4),
            "buildable": self.buildable,
            "reason": self.reason,
        }


def audit_family_coverage(
    matches: Sequence[Mapping[str, object]],
    families: Sequence[MarketFamily] | None = None,
    *,
    league_field: str = "_league",
    min_fixtures: int = 100,
) -> tuple[FamilyCoverage, ...]:
    """Report per league and family how many fixtures carry the target.

    A family is excluded for a league when the provider does not populate it,
    rather than zero-filled into existence. The half-split families are the live
    concern: the schema audit confirmed those fields are per-half rather than
    cumulative, but population rates vary by provider and league, so the decision
    has to be made from measured coverage.
    """
    families = tuple(families or default_market_families())
    totals: dict[str, int] = {}
    built: dict[tuple[str, str], int] = {}
    for match in matches:
        if str(match.get("status") or "").casefold() != "complete":
            continue
        league = str(match.get(league_field) or match.get("league") or "")
        if not league:
            continue
        totals[league] = totals.get(league, 0) + 1
        for family in families:
            if side_counts(match, family.name) is not None:
                key = (league, family.name)
                built[key] = built.get(key, 0) + 1

    reports: list[FamilyCoverage] = []
    for league in sorted(totals):
        n_fixtures = totals[league]
        for family in families:
            n_buildable = built.get((league, family.name), 0)
            coverage = n_buildable / n_fixtures if n_fixtures else 0.0
            if n_buildable < min_fixtures:
                buildable = False
                reason = (
                    f"only {n_buildable} fixtures carry the target "
                    f"(minimum {min_fixtures})"
                )
            elif coverage < family.min_coverage:
                buildable = False
                reason = (
                    f"coverage {coverage:.1%} below the {family.min_coverage:.0%} "
                    "floor; excluded rather than zero-filled"
                )
            else:
                buildable = True
                reason = f"coverage {coverage:.1%}"
            reports.append(
                FamilyCoverage(
                    league=league,
                    family=family.name,
                    n_fixtures=n_fixtures,
                    n_buildable=n_buildable,
                    buildable=buildable,
                    reason=reason,
                )
            )
    return tuple(reports)


def buildable_leagues(
    coverage: Sequence[FamilyCoverage], family: str
) -> tuple[str, ...]:
    return tuple(
        report.league
        for report in coverage
        if report.family == family and report.buildable
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dispersion audit
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class DispersionReport:
    """Measured overdispersion of one family's side counts in one league.

    Football counts are usually overdispersed relative to Poisson, but "usually"
    is not a licence to assume it. This is the check, reported per family and per
    league, so the negative-binomial choice is a finding rather than a habit.
    """

    league: str
    family: str
    n_observations: int
    mean: float
    variance: float
    variance_mean_ratio: float
    overdispersed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "league": self.league,
            "family": self.family,
            "n_observations": self.n_observations,
            "mean": round(self.mean, 4),
            "variance": round(self.variance, 4),
            "variance_mean_ratio": round(self.variance_mean_ratio, 4),
            "overdispersed": self.overdispersed,
        }


POOLED_LEAGUE_LABEL = "POOLED"


def audit_dispersion(
    matches: Sequence[Mapping[str, object]],
    families: Sequence[MarketFamily] | None = None,
    *,
    league_field: str = "_league",
    threshold: float = 1.20,
    min_observations: int = 50,
) -> tuple[DispersionReport, ...]:
    """Measure variance/mean of side counts per family, per league and pooled."""
    families = tuple(families or default_market_families())
    samples: dict[tuple[str, str], list[float]] = {}
    for match in matches:
        if str(match.get("status") or "").casefold() != "complete":
            continue
        league = str(match.get(league_field) or match.get("league") or "")
        if not league:
            continue
        for family in families:
            counts = side_counts(match, family.name)
            if counts is None:
                continue
            for key in ((league, family.name), (POOLED_LEAGUE_LABEL, family.name)):
                samples.setdefault(key, []).extend(counts)

    reports: list[DispersionReport] = []
    for (league, family_name), values in sorted(samples.items()):
        n = len(values)
        if n < min_observations:
            continue
        mean = sum(values) / n
        variance = sum((value - mean) ** 2 for value in values) / (n - 1)
        ratio = variance / mean if mean > 0 else 0.0
        reports.append(
            DispersionReport(
                league=league,
                family=family_name,
                n_observations=n,
                mean=mean,
                variance=variance,
                variance_mean_ratio=ratio,
                overdispersed=ratio > threshold,
            )
        )
    return tuple(reports)
