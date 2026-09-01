"""DerivedOutcomeCombiner — match-level outcomes from per-side distributions.

Responsibility
==============
Combine the two directions' per-side predictive distributions to produce
match-level :class:`~src.research.asymmetric.models.DerivedOutcomes`, and NEVER
model any Derived_Outcome directly (Req 2.9, 2.10). This mirrors the
derive-don't-model pattern of :mod:`src.research.models.derived_goals`
(``BTTSModel`` / ``CleanSheetModel`` derive from an already-fitted goals model
rather than fitting a fresh classifier): here the combiner is a pure function of
the eight :class:`~src.research.asymmetric.models.DirectionPrediction` PMFs and
holds no ``fit`` / training method at all.

Stated independence assumption (Req 3.1)
----------------------------------------
Under the STATED assumption that the two sides' per-side counts are conditionally
independent given their profiles:

  * ``total_corners`` / ``total_cards`` / ``total_goals`` are the **discrete
    convolution** of the two per-side count PMFs (the distribution of the sum of
    two independent count random variables);
  * ``btts_yes`` = ``P(sideA goals >= 1) * P(sideB goals >= 1)``;
  * ``clean_sheet_home`` = ``P(away goals == 0)`` (the home side keeps a clean
    sheet iff the away attacker scores zero);
  * ``clean_sheet_away`` = ``P(home goals == 0)``.

Direction A is "home attacks / away defends" and Direction B is "away attacks /
home defends" (matching
:mod:`src.research.asymmetric.interaction`). So Direction A's goals PMF is the
HOME side's goals and Direction B's goals PMF is the AWAY side's goals.

The assumption text is emitted as :data:`INDEPENDENCE_ASSUMPTION` and stored on
the result so :attr:`FixturePrediction.independence_assumption` can carry it
(Req 3.1).

Correlation attachment (Req 3.2-3.4)
------------------------------------
The combiner accepts an optional
:class:`~src.research.asymmetric.correlation.CorrelationStructureResult` (produced
by task 6.2's comparison) and attaches its ``implied_correlations`` /
``measured_correlations`` / ``correlation_red_flags`` onto the emitted
``DerivedOutcomes``. When none is supplied the combiner falls back to the
pure-independence comparison (implied correlations of ~0 for every pair), so the
measured structure and CIs are always reported alongside the outcome (Req 3.4).

Requirements: 2.9, 2.10, 3.1.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence

from src.research.asymmetric.correlation import (
    CorrelationStructureResult,
    compare_correlation_structure,
)
from src.research.asymmetric.models import DerivedOutcomes, DirectionPrediction

# ─────────────────────────────────────────────────────────────────────────────
# Stated independence assumption text (Req 3.1)
# ─────────────────────────────────────────────────────────────────────────────

INDEPENDENCE_ASSUMPTION: str = (
    "Derived match-level outcomes are computed by combining the two directions' "
    "per-side predictive distributions under the stated assumption that the two "
    "sides' per-side counts are conditionally independent given their profiles. "
    "Total corners/cards/goals are the discrete convolution of the two per-side "
    "count PMFs; both-teams-to-score is P(sideA goals>=1)*P(sideB goals>=1); "
    "clean sheet per side is the probability the opposing side scores zero. No "
    "derived outcome is modelled directly."
)

#: PMF-validity numerical tolerance.
PMF_TOLERANCE = 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# Discrete convolution helper (Req 2.9)
# ─────────────────────────────────────────────────────────────────────────────


def convolve_pmfs(pmf_a: Sequence[float], pmf_b: Sequence[float]) -> tuple[float, ...]:
    """Discrete convolution of two count PMFs -> the summed-count PMF.

    Given ``pmf_a`` over counts ``0..len(a)-1`` and ``pmf_b`` over ``0..len(b)-1``,
    returns the PMF of ``A + B`` over counts ``0..(len(a)-1)+(len(b)-1)`` under
    the independence assumption:

        P(A + B = k) = sum_{i} P(A = i) * P(B = k - i)

    The inputs are treated as (possibly slightly sub-normalised, from tail
    truncation) probability vectors; the output is renormalised so it stays a
    valid PMF — every entry in ``[0, 1]`` and the entries summing to 1 within
    tolerance (matching the guarantee from ``DirectionalCountModel``).

    Raises:
        ValueError: if either input is empty or contains a negative entry.
    """
    a = [float(x) for x in pmf_a]
    b = [float(x) for x in pmf_b]
    if not a or not b:
        raise ValueError("convolve_pmfs requires two non-empty PMFs")
    if any(x < 0.0 for x in a) or any(x < 0.0 for x in b):
        raise ValueError("PMF entries must be non-negative")

    out = [0.0] * (len(a) + len(b) - 1)
    for i, pa in enumerate(a):
        if pa == 0.0:
            continue
        for j, pb in enumerate(b):
            if pb == 0.0:
                continue
            out[i + j] += pa * pb

    total = math.fsum(out)
    if total <= 0.0:
        # Degenerate inputs (all mass zero): put all mass on 0 to stay a PMF.
        degenerate = [0.0] * len(out)
        degenerate[0] = 1.0
        return tuple(degenerate)
    return tuple(v / total for v in out)


def is_valid_pmf(pmf: Iterable[float], tolerance: float = PMF_TOLERANCE) -> bool:
    """Return True when ``pmf`` is a valid PMF (entries in [0,1], sum ~1)."""
    vals = [float(x) for x in pmf]
    if not vals:
        return False
    if any(x < -tolerance or x > 1.0 + tolerance for x in vals):
        return False
    return abs(math.fsum(vals) - 1.0) <= tolerance


def pmf_mean(pmf: Sequence[float]) -> float:
    """Mean (expected count) of a PMF over counts ``0, 1, 2, ...``."""
    return math.fsum(k * float(p) for k, p in enumerate(pmf))


def _prob_at_least_one(pmf: Sequence[float]) -> float:
    """P(count >= 1) = 1 - P(count == 0)."""
    if not pmf:
        return 0.0
    return max(0.0, min(1.0, 1.0 - float(pmf[0])))


def _prob_zero(pmf: Sequence[float]) -> float:
    """P(count == 0)."""
    if not pmf:
        return 0.0
    return max(0.0, min(1.0, float(pmf[0])))


# ─────────────────────────────────────────────────────────────────────────────
# DerivedOutcomeCombiner (Req 2.9, 2.10, 3.1)
# ─────────────────────────────────────────────────────────────────────────────


class DerivedOutcomeCombiner:
    """Derive match-level outcomes from the two directions' per-side PMFs.

    Pure derivation, no modelling: the combiner has NO ``fit`` / training method
    (Req 2.10). It consumes the eight per-side :class:`DirectionPrediction`
    distributions (2 directions x 4 targets) and produces a
    :class:`DerivedOutcomes` under the stated independence assumption (Req 2.9,
    3.1).

    The independence assumption text is exposed on
    :attr:`independence_assumption` so callers can attach it to
    :attr:`FixturePrediction.independence_assumption`.
    """

    def __init__(self, material_threshold: float | None = None) -> None:
        """Args:
        material_threshold: optional materiality floor forwarded to the
            correlation comparison when the combiner builds the comparison
            itself (i.e. when no precomputed correlation result is supplied).
        """
        self._material_threshold = material_threshold

    @property
    def independence_assumption(self) -> str:
        """The stated independence-assumption text (Req 3.1)."""
        return INDEPENDENCE_ASSUMPTION

    # -- convolution helper exposed as a method for convenience ---------- #
    @staticmethod
    def convolve(pmf_a: Sequence[float], pmf_b: Sequence[float]) -> tuple[float, ...]:
        """Discrete convolution of two per-side count PMFs (see :func:`convolve_pmfs`)."""
        return convolve_pmfs(pmf_a, pmf_b)

    def combine(
        self,
        directions: list[DirectionPrediction],
        *,
        correlation: Optional[CorrelationStructureResult] = None,
        implied_correlations: Optional[dict[str, float]] = None,
    ) -> DerivedOutcomes:
        """Combine the 8 per-side predictions into a :class:`DerivedOutcomes`.

        Pairs the corners PMF from Direction A with the corners PMF from Direction
        B (and likewise for cards and goals) and convolves them into match totals;
        derives BTTS and clean sheets from the goals PMFs. All under the stated
        independence assumption (Req 2.9, 3.1).

        Args:
            directions: the eight :class:`DirectionPrediction` objects — two
                directions (``A_attack_vs_B_defence`` = home attacks,
                ``B_attack_vs_A_defence`` = away attacks) times four targets
                (``corners``, ``cards``, ``goals``, ``sot``). Extra targets (e.g.
                ``sot``) are permitted and ignored for the derived totals.
            correlation: a precomputed correlation comparison (task 6.2) whose
                ``implied_correlations`` / ``measured_correlations`` /
                ``correlation_red_flags`` are attached verbatim to the result.
            implied_correlations: alternatively, a ``{pair -> implied}`` mapping
                from which the combiner builds the comparison itself (a hook for
                the correlation check to fill). Ignored when ``correlation`` is
                supplied.

        Returns:
            The :class:`DerivedOutcomes` with convolution total PMFs, BTTS,
            per-side clean sheets, and the attached correlation fields.

        Raises:
            ValueError: if the required per-side PMFs are missing from
                ``directions``.
        """
        from src.research.asymmetric.interaction import DIRECTION_A, DIRECTION_B

        by_key: dict[tuple[str, str], DirectionPrediction] = {
            (d.direction, d.target): d for d in directions
        }

        def pmf(direction: str, target: str) -> tuple[float, ...]:
            pred = by_key.get((direction, target))
            if pred is None:
                raise ValueError(
                    f"missing per-side prediction for direction={direction!r} "
                    f"target={target!r}; combine() needs both directions for "
                    f"corners/cards/goals"
                )
            return tuple(pred.distribution)

        # Home side = Direction A (home attacks); away side = Direction B.
        corners_home = pmf(DIRECTION_A, "corners")
        corners_away = pmf(DIRECTION_B, "corners")
        cards_home = pmf(DIRECTION_A, "cards")
        cards_away = pmf(DIRECTION_B, "cards")
        goals_home = pmf(DIRECTION_A, "goals")
        goals_away = pmf(DIRECTION_B, "goals")

        total_corners = convolve_pmfs(corners_home, corners_away)
        total_cards = convolve_pmfs(cards_home, cards_away)
        total_goals = convolve_pmfs(goals_home, goals_away)

        # BTTS = P(home scores >=1) * P(away scores >=1) under independence.
        btts_yes = _prob_at_least_one(goals_home) * _prob_at_least_one(goals_away)

        # Clean sheet home = away scores zero; clean sheet away = home scores zero.
        clean_sheet_home = _prob_zero(goals_away)
        clean_sheet_away = _prob_zero(goals_home)

        # Resolve the correlation fields (Req 3.2-3.4). Prefer a precomputed
        # result; otherwise build the comparison (defaults to the ~0 implied
        # correlations of the pure-independence path) so measured values + CIs
        # are always reported.
        corr = correlation
        if corr is None:
            if self._material_threshold is not None:
                corr = compare_correlation_structure(
                    implied_correlations,
                    material_threshold=self._material_threshold,
                )
            else:
                corr = compare_correlation_structure(implied_correlations)

        return DerivedOutcomes(
            total_corners=total_corners,
            total_cards=total_cards,
            total_goals=total_goals,
            btts_yes=float(max(0.0, min(1.0, btts_yes))),
            clean_sheet_home=float(clean_sheet_home),
            clean_sheet_away=float(clean_sheet_away),
            implied_correlations=dict(corr.implied_correlations),
            measured_correlations=dict(corr.measured_correlations),
            correlation_red_flags=tuple(corr.correlation_red_flags),
        )
