"""Directional calls — "Team A takes more corners than Team B", with probability.

Alongside the calibrated probability (the rigorous claim), the engine produces a
**directional call** (the legible one): e.g. "the home side takes more corners
than the away side". These are checkable by anyone with a match report, need no
bookmaker line, and are unambiguous to settle — which makes them the natural
public-facing output.

The directional call is derived from the two per-side predictive count PMFs the
validated engine already produces (Direction A = home side, Direction B = away
side). Under the engine's stated conditional-independence assumption, the
probability that side A's count exceeds side B's is:

    P(A > B) = sum_{a > b} P(A = a) * P(B = b)

with P(A = B) and P(B > A) computed the same way. We report the full triple so
ties are explicit rather than folded into one side. This mirrors the
derive-don't-model discipline of
:class:`~src.research.asymmetric.derived.DerivedOutcomeCombiner`: no new model is
fitted; the call is a pure function of the two PMFs.

NO STAKE SIZING here: a directional call is a statement about the world, never a
recommendation to bet on it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class DirectionalCall:
    """A probabilistic directional call between two sides for one market.

    Attributes:
        market: the market key (corners/cards/goals/...).
        side_a_label / side_b_label: readable side labels (e.g. "home"/"away").
        p_a_more: P(side A count > side B count).
        p_b_more: P(side B count > side A count).
        p_tie: P(side A count == side B count).
        expected_a / expected_b: expected counts (PMF means) for reference.
    """

    market: str
    side_a_label: str
    side_b_label: str
    p_a_more: float
    p_b_more: float
    p_tie: float
    expected_a: float
    expected_b: float

    @property
    def called_side(self) -> Optional[str]:
        """The side called to have more, or None if the more-likely side ties.

        The call names whichever of A/B has the higher probability of the larger
        count. If ``p_a_more == p_b_more`` exactly, no side is called.
        """
        if self.p_a_more > self.p_b_more:
            return self.side_a_label
        if self.p_b_more > self.p_a_more:
            return self.side_b_label
        return None

    @property
    def call_probability(self) -> float:
        """Probability attached to the called side (the max of the two)."""
        return max(self.p_a_more, self.p_b_more)

    def statement(self) -> str:
        """A plain, settleable sentence — the legible public-facing output."""
        called = self.called_side
        if called is None:
            return (
                f"{self.market}: neither side is favoured to record more "
                f"(P={self.p_a_more:.3f} each way, tie P={self.p_tie:.3f})"
            )
        other = self.side_b_label if called == self.side_a_label else self.side_a_label
        return (
            f"{self.market}: {called} takes more than {other} "
            f"(P={self.call_probability:.3f}; tie P={self.p_tie:.3f})"
        )

    def statement_no_probability(self) -> str:
        """The directional statement WITHOUT any probability figure.

        Used when the accuracy gate passed but the calibration gate did not, so
        the direction may be stated but its confidence must be withheld.
        """
        called = self.called_side
        if called is None:
            return f"{self.market}: neither side is clearly favoured to record more"
        other = self.side_b_label if called == self.side_a_label else self.side_a_label
        return f"{self.market}: {called} takes more than {other}"


def _normalize(pmf: Sequence[float]) -> list[float]:
    vals = [max(0.0, float(x)) for x in pmf]
    total = math.fsum(vals)
    if total <= 0.0:
        return [1.0] + [0.0] * (len(vals) - 1) if vals else [1.0]
    return [v / total for v in vals]


def directional_probabilities(
    pmf_a: Sequence[float], pmf_b: Sequence[float]
) -> tuple[float, float, float]:
    """Return ``(P(A>B), P(B>A), P(A==B))`` from two independent count PMFs.

    Each PMF is over counts ``0, 1, 2, ...``. The inputs are renormalised for
    numerical safety, so slightly sub-normalised tail-truncated PMFs (as produced
    by the count models) are handled correctly. The three returned probabilities
    sum to 1 within floating-point tolerance.

    Raises:
        ValueError: if either PMF is empty.
    """
    if not pmf_a or not pmf_b:
        raise ValueError("directional_probabilities requires two non-empty PMFs")
    a = _normalize(pmf_a)
    b = _normalize(pmf_b)

    p_a_more = 0.0
    p_tie = 0.0
    for i, pa in enumerate(a):
        if pa == 0.0:
            continue
        for j, pb in enumerate(b):
            if pb == 0.0:
                continue
            joint = pa * pb
            if i > j:
                p_a_more += joint
            elif i == j:
                p_tie += joint
    p_b_more = 1.0 - p_a_more - p_tie
    # Clamp for numerical safety.
    p_a_more = min(1.0, max(0.0, p_a_more))
    p_b_more = min(1.0, max(0.0, p_b_more))
    p_tie = min(1.0, max(0.0, p_tie))
    return p_a_more, p_b_more, p_tie


def _pmf_mean(pmf: Sequence[float]) -> float:
    norm = _normalize(pmf)
    return math.fsum(k * p for k, p in enumerate(norm))


def directional_call(
    market: str,
    pmf_a: Sequence[float],
    pmf_b: Sequence[float],
    *,
    side_a_label: str = "home",
    side_b_label: str = "away",
) -> DirectionalCall:
    """Build a :class:`DirectionalCall` from the two per-side count PMFs.

    Pure derivation from the PMFs the validated engine already produces — no new
    model is fitted (derive-don't-model). Direction A is conventionally the home
    side and Direction B the away side, matching
    :mod:`src.research.asymmetric.interaction`.
    """
    p_a_more, p_b_more, p_tie = directional_probabilities(pmf_a, pmf_b)
    return DirectionalCall(
        market=market,
        side_a_label=side_a_label,
        side_b_label=side_b_label,
        p_a_more=p_a_more,
        p_b_more=p_b_more,
        p_tie=p_tie,
        expected_a=_pmf_mean(pmf_a),
        expected_b=_pmf_mean(pmf_b),
    )
