"""Correlation_Structure constants and implied-vs-measured comparison.

Responsibility
==============
Encode the empirically measured near-zero cross-market correlation constants on
the Broad_Corpus, compute the correlation *implied* by the per-side model, and
red-flag any material deviation while ALWAYS reporting the measured values and
their 95% confidence intervals alongside the comparison.

Measured Correlation_Structure (Broad_Corpus, Req 3.2, 3.4)
-----------------------------------------------------------
The audit measured near-zero cross-market correlations with a 95% CI half-width
of approximately ``+/-0.016``:

    cards x corners  = -0.033
    cards x goals    = -0.030
    corners x goals  = -0.028

These are encoded below as named constants together with the shared CI
half-width. They are always surfaced next to any comparison (Req 3.4).

How the implied correlation is computed (Req 3.2)
-------------------------------------------------
The Engine derives every match-level outcome by combining the two directions'
per-side count distributions **independently** (see
:mod:`src.research.asymmetric.derived` — totals are the discrete convolution of
two independent per-side PMFs). Under that stated independence assumption, two
*different* match-total markets (e.g. total cards and total corners) are
constructed from disjoint, independent per-side PMFs and therefore have an
implied match-total cross-market correlation of **exactly 0** — there is no
shared latent term coupling them.

So the implied cross-market correlation is defined precisely as:

    implied_corr(X, Y) = Corr[ total_X , total_Y ]  under the model's joint

and, because the model combines the per-side markets independently, this equals
0 *unless a dependency is deliberately introduced* between the markets (for
example, a shared conditioning term, or a supplied joint sample from which a
Pearson correlation is measured). The value of the check is therefore to
**detect** any such introduced dependency: if the model ever couples two markets
(implied correlation moves away from ~0), the comparison surfaces whether that
introduced correlation is consistent with the measured near-zero structure or
whether it deviates materially and must be red-flagged.

:func:`implied_correlation_from_samples` computes the implied correlation from a
supplied joint sample (paired match-total draws) via Pearson's correlation; when
no dependency is introduced the samples are independent and this returns ~0, as
expected. :func:`implied_independence_correlation` returns the analytic 0 for the
pure-independence path.

Red-flag rule (Req 3.3)
-----------------------
A pair is red-flagged when the implied correlation lies OUTSIDE the tolerance
band around the measured value:

    measured +/- max(ci_halfwidth, material_threshold)

with a default ``material_threshold = 0.05``. The band widens to the material
threshold so that a difference within ordinary sampling noise (the CI) OR within
a materiality floor is not flagged; only a genuinely material departure raises a
red flag.

Requirements: 3.2, 3.3, 3.4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Measured Correlation_Structure constants (Broad_Corpus) — Req 3.2, 3.4
# ─────────────────────────────────────────────────────────────────────────────

#: Measured cross-market correlation: cards x corners.
CARDS_CORNERS_CORR: float = -0.033
#: Measured cross-market correlation: cards x goals.
CARDS_GOALS_CORR: float = -0.030
#: Measured cross-market correlation: corners x goals.
CORNERS_GOALS_CORR: float = -0.028
#: Shared 95% CI half-width for the measured correlations (~ +/-0.016).
CORRELATION_CI_HALFWIDTH: float = 0.016

#: Default materiality floor for the red-flag tolerance band (Req 3.3).
DEFAULT_MATERIAL_THRESHOLD: float = 0.05

#: Canonical (order-independent) market-pair keys.
PAIR_CARDS_CORNERS = "cards_corners"
PAIR_CARDS_GOALS = "cards_goals"
PAIR_CORNERS_GOALS = "corners_goals"

#: Measured value + CI half-width per canonical pair key (Req 3.2, 3.4).
MEASURED_CORRELATIONS: dict[str, tuple[float, float]] = {
    PAIR_CARDS_CORNERS: (CARDS_CORNERS_CORR, CORRELATION_CI_HALFWIDTH),
    PAIR_CARDS_GOALS: (CARDS_GOALS_CORR, CORRELATION_CI_HALFWIDTH),
    PAIR_CORNERS_GOALS: (CORNERS_GOALS_CORR, CORRELATION_CI_HALFWIDTH),
}

#: The three cross-market pairs the Correlation_Structure covers.
CORRELATION_PAIRS: tuple[str, ...] = (
    PAIR_CARDS_CORNERS,
    PAIR_CARDS_GOALS,
    PAIR_CORNERS_GOALS,
)

#: Map an unordered pair of market names to its canonical key.
_PAIR_LOOKUP: dict[frozenset[str], str] = {
    frozenset({"cards", "corners"}): PAIR_CARDS_CORNERS,
    frozenset({"cards", "goals"}): PAIR_CARDS_GOALS,
    frozenset({"corners", "goals"}): PAIR_CORNERS_GOALS,
}


def canonical_pair_key(market_a: str, market_b: str) -> str:
    """Return the canonical (order-independent) key for two markets.

    Raises:
        ValueError: if the pair is not one of the three covered cross-market
            pairs (cards x corners, cards x goals, corners x goals).
    """
    key = _PAIR_LOOKUP.get(frozenset({market_a, market_b}))
    if key is None:
        raise ValueError(
            f"unknown market pair ({market_a!r}, {market_b!r}); expected a pair "
            f"drawn from cards/corners/goals"
        )
    return key


# ─────────────────────────────────────────────────────────────────────────────
# Implied-correlation computation (Req 3.2)
# ─────────────────────────────────────────────────────────────────────────────


def implied_independence_correlation() -> float:
    """Analytic implied cross-market correlation under pure independence.

    Because the Engine combines the per-side markets independently (Req 3.1), two
    different match-total markets share no latent term and their implied
    correlation is exactly ``0.0``. This is the value the check expects unless a
    dependency has been deliberately introduced (Req 3.2).
    """
    return 0.0


def implied_correlation_from_samples(
    totals_a: Iterable[float], totals_b: Iterable[float]
) -> float:
    """Pearson correlation between paired match-total samples of two markets.

    Given paired draws of two match-total markets (e.g. total cards and total
    corners) from the model's joint, this measures the implied cross-market
    correlation. Under the model's independence assumption the two sample vectors
    are independent and this returns ~0; a non-zero value indicates the model has
    coupled the two markets, which the comparison then checks against the
    measured near-zero structure (Req 3.2).

    Degenerate inputs (fewer than two paired points, or a zero-variance vector)
    yield ``0.0`` — with no variability there is no measurable linear
    dependence.
    """
    a = np.asarray(list(totals_a), dtype=float)
    b = np.asarray(list(totals_b), dtype=float)
    if a.size != b.size:
        raise ValueError(
            f"paired samples must have equal length, got {a.size} and {b.size}"
        )
    if a.size < 2:
        return 0.0
    if float(np.std(a)) == 0.0 or float(np.std(b)) == 0.0:
        return 0.0
    corr = float(np.corrcoef(a, b)[0, 1])
    if not np.isfinite(corr):
        return 0.0
    # Guard against tiny floating-point excursions outside [-1, 1].
    return max(-1.0, min(1.0, corr))


# ─────────────────────────────────────────────────────────────────────────────
# Comparison + red-flag logic (Req 3.3, 3.4)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CorrelationComparison:
    """One implied-vs-measured cross-market correlation comparison.

    Attributes:
        pair: canonical pair key (e.g. ``"cards_corners"``).
        implied: the correlation implied by the per-side model.
        measured: the measured Correlation_Structure value (Req 3.2).
        ci_halfwidth: the measured value's 95% CI half-width (Req 3.4).
        tolerance: the red-flag tolerance ``max(ci_halfwidth, material_threshold)``.
        red_flag: True when ``implied`` lies outside ``measured +/- tolerance``.
    """

    pair: str
    implied: float
    measured: float
    ci_halfwidth: float
    tolerance: float
    red_flag: bool

    @property
    def deviation(self) -> float:
        """Signed distance of the implied value from the measured value."""
        return self.implied - self.measured

    def describe(self) -> str:
        """Human-readable one-line summary that always reports measured+CI (Req 3.4)."""
        status = "RED FLAG" if self.red_flag else "ok"
        return (
            f"{self.pair}: implied={self.implied:+.4f} vs "
            f"measured={self.measured:+.4f} (95% CI +/-{self.ci_halfwidth:.4f}), "
            f"tolerance=+/-{self.tolerance:.4f} -> {status}"
        )


def compare_correlation(
    pair: str,
    implied: float,
    material_threshold: float = DEFAULT_MATERIAL_THRESHOLD,
) -> CorrelationComparison:
    """Compare one implied correlation against the measured structure (Req 3.3, 3.4).

    Red-flags when ``implied`` lies outside ``measured +/- max(ci, material)``.
    The measured value and its CI are carried on the returned comparison so they
    are always reported alongside the check (Req 3.4).

    Raises:
        ValueError: if ``pair`` is not one of the covered canonical pair keys.
    """
    if pair not in MEASURED_CORRELATIONS:
        raise ValueError(
            f"unknown correlation pair {pair!r}; expected one of {CORRELATION_PAIRS}"
        )
    if material_threshold < 0.0:
        raise ValueError(f"material_threshold must be >= 0, got {material_threshold}")
    measured, ci = MEASURED_CORRELATIONS[pair]
    tolerance = max(ci, material_threshold)
    red_flag = abs(implied - measured) > tolerance
    return CorrelationComparison(
        pair=pair,
        implied=float(implied),
        measured=float(measured),
        ci_halfwidth=float(ci),
        tolerance=float(tolerance),
        red_flag=bool(red_flag),
    )


@dataclass(frozen=True)
class CorrelationStructureResult:
    """The full implied-vs-measured comparison across all covered pairs.

    Fields mirror the ``DerivedOutcomes`` correlation fields so the combiner can
    attach them directly (Req 3.3, 3.4):

        implied_correlations   : ``{pair -> implied}``
        measured_correlations  : ``{pair -> (value, ci_halfwidth)}``
        correlation_red_flags  : tuple of human-readable red-flag descriptions
    """

    comparisons: tuple[CorrelationComparison, ...]
    implied_correlations: dict[str, float]
    measured_correlations: dict[str, tuple[float, float]]
    correlation_red_flags: tuple[str, ...]


def compare_correlation_structure(
    implied_correlations: Optional[dict[str, float]] = None,
    material_threshold: float = DEFAULT_MATERIAL_THRESHOLD,
) -> CorrelationStructureResult:
    """Compare implied correlations for all covered pairs against measured (Req 3.2-3.4).

    Args:
        implied_correlations: ``{pair -> implied}`` for any subset of the covered
            pairs. Pairs omitted default to the pure-independence implied value
            (``0.0``, :func:`implied_independence_correlation`), since the Engine
            combines per-side markets independently.
        material_threshold: materiality floor for the tolerance band (Req 3.3).

    Returns:
        A :class:`CorrelationStructureResult` whose dict fields line up with the
        ``DerivedOutcomes`` correlation fields, always carrying the measured
        values and CIs (Req 3.4) and the red-flag descriptions (Req 3.3).
    """
    supplied = dict(implied_correlations or {})
    comparisons: list[CorrelationComparison] = []
    implied_out: dict[str, float] = {}
    red_flags: list[str] = []

    for pair in CORRELATION_PAIRS:
        implied = supplied.get(pair, implied_independence_correlation())
        cmp = compare_correlation(pair, implied, material_threshold=material_threshold)
        comparisons.append(cmp)
        implied_out[pair] = cmp.implied
        if cmp.red_flag:
            red_flags.append(cmp.describe())

    return CorrelationStructureResult(
        comparisons=tuple(comparisons),
        implied_correlations=implied_out,
        measured_correlations=dict(MEASURED_CORRELATIONS),
        correlation_red_flags=tuple(red_flags),
    )
