"""Pydantic v2 data models for the Asymmetric Matchup Engine.

Responsibility:
    Define the frozen data models exchanged between components: profile
    dimensions, attacking/defensive profiles, per-team match profiles,
    directional and fixture predictions, derived outcomes, gate results,
    estimates with confidence intervals, asymmetry comparisons, and spend
    reports.

All models use pydantic v2 (``pydantic==2.6.1``) and are declared
``frozen`` via ``ConfigDict`` so that, once constructed, instances are
immutable value objects. This matches the codebase convention of treating
research outputs as frozen records and guarantees that a profile or
prediction cannot be mutated in place after it has been produced.

Requirements: 1.1, 1.2, 1.16, 2.4, 2.8, 3.1, 10.8, 10.9.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ProfileDimension(BaseModel):
    """A single named, continuous profile feature.

    ``value`` is the scalar computed for this dimension; ``source_fields``
    names the raw fields it was derived from; ``n_matches_used`` is the
    number of matches that contributed after any missing-field exclusion;
    ``missing_fields`` records fields that were unavailable (Req 1.17).
    """

    model_config = ConfigDict(frozen=True)

    name: str
    value: float
    source_fields: tuple[str, ...]
    n_matches_used: int
    missing_fields: tuple[str, ...] = ()


class AttackingProfile(BaseModel):
    """Continuous attacking profile for one team as of a point in time.

    ``team`` is used only as an aggregation key and never enters the feature
    vector (Req 1.3). The five dimensions are continuous (Req 1.2).
    """

    model_config = ConfigDict(frozen=True)

    team: str
    as_of_unix: int
    width: ProfileDimension
    central_penetration: ProfileDimension
    volume_vs_quality: ProfileDimension
    set_piece_reliance: ProfileDimension
    directness: ProfileDimension
    reduced: bool = False

    def vector(self) -> list[float]:
        """Return the continuous attacking feature vector (Req 1.2).

        The order is fixed and documented:
        ``[width, central_penetration, volume_vs_quality,
        set_piece_reliance, directness]`` — matching the declaration order
        of the dimensions above. Team identity is deliberately excluded.
        """
        return [
            self.width.value,
            self.central_penetration.value,
            self.volume_vs_quality.value,
            self.set_piece_reliance.value,
            self.directness.value,
        ]


class DefensiveProfile(BaseModel):
    """Continuous defensive profile for one team as of a point in time."""

    model_config = ConfigDict(frozen=True)

    team: str
    as_of_unix: int
    block_orientation: ProfileDimension
    aerial_vs_ground: ProfileDimension
    shot_suppression: ProfileDimension
    gk_contribution: ProfileDimension
    discipline: ProfileDimension
    reduced: bool = False

    def vector(self) -> list[float]:
        """Return the continuous defensive feature vector (Req 1.2).

        The order is fixed and documented:
        ``[block_orientation, aerial_vs_ground, shot_suppression,
        gk_contribution, discipline]`` — matching the declaration order of
        the dimensions above. Team identity is deliberately excluded.
        """
        return [
            self.block_orientation.value,
            self.aerial_vs_ground.value,
            self.shot_suppression.value,
            self.gk_contribution.value,
            self.discipline.value,
        ]


class TeamMatchProfiles(BaseModel):
    """The point-in-time attacking and defensive profiles for one team.

    ``insufficient`` is ``True`` when the team has fewer than five completed
    matches of history (Req 1.16).
    """

    model_config = ConfigDict(frozen=True)

    team: str
    n_history: int
    insufficient: bool
    attacking: AttackingProfile
    defensive: DefensiveProfile


class DirectionPrediction(BaseModel):
    """Per-side prediction for a single Direction and a single target.

    ``distribution`` is a full predictive PMF (Req 2.4-2.7);
    ``driving_features`` names the drivers used (Req 2.8, 9.3);
    ``referee_substituted`` flags the cards league-rate fallback (Req 2.11).
    """

    model_config = ConfigDict(frozen=True)

    direction: str
    attacker: str
    defender: str
    target: str
    distribution: tuple[float, ...]
    expected_value: float
    driving_features: tuple[str, ...]
    referee_substituted: bool = False


class DerivedOutcomes(BaseModel):
    """Match-level outcomes derived from the two Directions' per-side PMFs.

    Totals are convolution PMFs; ``btts_yes`` and clean-sheet probabilities
    are scalars. ``implied_correlations`` and ``measured_correlations``
    support the correlation-structure comparison (Req 3.2-3.4) and
    ``correlation_red_flags`` records material deviations (Req 3.3).
    """

    model_config = ConfigDict(frozen=True)

    total_corners: tuple[float, ...]
    total_cards: tuple[float, ...]
    total_goals: tuple[float, ...]
    btts_yes: float
    clean_sheet_home: float
    clean_sheet_away: float
    implied_correlations: dict[str, float]
    measured_correlations: dict[str, tuple[float, float]]
    correlation_red_flags: tuple[str, ...]


class FixturePrediction(BaseModel):
    """The full per-fixture prediction: two directions plus derived outcomes.

    ``independence_assumption`` states the assumption used to combine the
    per-side distributions into derived outcomes (Req 3.1).
    """

    model_config = ConfigDict(frozen=True)

    home_team: str
    away_team: str
    date_unix: int
    directions: tuple[DirectionPrediction, ...]
    derived: DerivedOutcomes
    independence_assumption: str


class GateCheckResult(BaseModel):
    """The result of a single gate check."""

    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    detail: str
    metric: float | None = None


class GateResult(BaseModel):
    """The aggregate result of a gate run.

    ``stopped_modelling`` is set when a failing check must halt modelling
    (Req 6.8).
    """

    model_config = ConfigDict(frozen=True)

    gate: str
    passed: bool
    checks: tuple[GateCheckResult, ...]
    stopped_modelling: bool


class Estimate(BaseModel):
    """A point estimate with a confidence interval (Req 10.8).

    An estimate whose CI spans zero is not treated as a result (Req 10.9).
    The interval is treated as *closed*: a bound that exactly touches zero
    (``ci_low == 0.0`` or ``ci_high == 0.0``) counts as spanning zero.
    """

    model_config = ConfigDict(frozen=True)

    point: float
    ci_low: float
    ci_high: float

    @property
    def spans_zero(self) -> bool:
        """True if the closed CI ``[ci_low, ci_high]`` contains zero (Req 10.9)."""
        return self.ci_low <= 0.0 <= self.ci_high

    @property
    def is_result(self) -> bool:
        """True if the estimate constitutes a result (its CI excludes zero)."""
        return not self.spans_zero


class AsymmetryComparison(BaseModel):
    """The Interaction vs Symmetric_Baseline comparison for one cell.

    ``league is None`` denotes a pooled comparison. ``verdict`` is one of
    ``"finding" | "artifact" | "fails" | "insufficient-sample"`` per the
    decision logic in Req 8.
    """

    model_config = ConfigDict(frozen=True)

    target: str
    direction: str
    league: str | None
    corpus: str
    bss_improvement: Estimate
    within_league_significant: bool
    pooled_only_artifact: bool
    insufficient_sample: bool
    fdr_passed: bool | None
    verdict: str


class SpendReport(BaseModel):
    """Live-fetch spend accounting for the Analysis_CLI (Req 12.4)."""

    model_config = ConfigDict(frozen=True)

    requests_made: int
    spend_units: float
    cap: float
    cap_exceeded: bool
