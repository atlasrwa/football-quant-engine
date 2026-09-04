"""Public reliability reporting — the artifact that makes calibration checkable.

Calibration is only a credible claim if anyone can check it. This module builds
the public reliability report:

* a **reliability curve** per market, per league — predicted-probability bucket
  vs realized rate, with the count in each bucket;
* **running ECE and Brier**, with the sample size shown at EQUAL prominence
  (a metric without its N is not reported);
* a **minimum-sample gate** — below ~200 settled predictions per market/league
  cell no calibration figure is displayed; instead "insufficient settled
  predictions — N of ~200" is shown (an ECE on 20 predictions is noise);
* a **base-rate-collapse flag** — if a model collapses to a near-constant
  (base-rate) predictor, that is flagged rather than reported as good ECE, since
  a constant predictor is trivially calibrated; and
* the mandatory **honest framing** on the rendered artifact.

Everything here reuses :func:`src.research.prediction_engine.calibration_metrics.calibration_report`
(which itself reuses the out-of-sample-only ``CalibrationEvaluator``) and the
validated-scope labels. It fits no model and contains NO stake sizing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.research.calibration import CalibrationBin
from src.research.prediction_engine.calibration_metrics import (
    CalibrationReport,
    calibration_report,
)
from src.research.prediction_engine.scope import (
    MIN_SETTLED_FOR_CALIBRATION,
    MarketScope,
    MarketStatus,
    honest_framing_lines,
    market_status,
)


# ─────────────────────────────────────────────────────────────────────────────
# One market/league reliability cell
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ReliabilityBucket:
    """One reliability-curve bucket: predicted band vs realized rate + count."""

    bin_low: float
    bin_high: float
    predicted_mean: float
    realized_rate: float
    count: int

    def render(self) -> str:
        return (
            f"    [{self.bin_low:.1f}-{self.bin_high:.1f}) "
            f"predicted {self.predicted_mean:.3f}  realized {self.realized_rate:.3f}  "
            f"(n={self.count})"
        )


@dataclass(frozen=True)
class ReliabilityCell:
    """The public reliability report for one market/league cell."""

    market: str
    league_label: Optional[str]
    scope: MarketScope
    report: CalibrationReport

    # ── gate / collapse ──────────────────────────────────────────
    @property
    def displayable(self) -> bool:
        """True iff a calibration figure may be displayed (validated/shown-with-label,
        gate met, not collapsed). Excluded markets are never displayable."""
        if self.scope.status is MarketStatus.EXCLUDED:
            return False
        return self.report.publishable and not self.report.collapse.collapsed

    @property
    def buckets(self) -> tuple[ReliabilityBucket, ...]:
        if self.report.calibration is None:
            return ()
        out: list[ReliabilityBucket] = []
        for b in self.report.calibration.bins:
            assert isinstance(b, CalibrationBin)
            out.append(
                ReliabilityBucket(
                    bin_low=b.bin_start,
                    bin_high=b.bin_end,
                    predicted_mean=b.predicted_mean,
                    realized_rate=b.actual_frequency,
                    count=b.count,
                )
            )
        return tuple(out)

    def render_lines(self) -> list[str]:
        league = self.league_label if self.league_label else "POOLED"
        lines = [f"{self.market.upper()} @ {league}  [{self.scope.label}]"]

        # Sample size is always shown FIRST, at equal prominence with any metric.
        lines.append(f"    settled predictions: n = {self.report.n_settled}")

        if self.scope.status is MarketStatus.EXCLUDED:
            lines.append(f"    {self.scope.reason}")
            return lines

        # Minimum-sample gate.
        if not self.report.gate_met:
            lines.append(f"    {self.report.gate_notice}")
            return lines

        # Base-rate-collapse flag takes precedence over reporting a good ECE.
        if self.report.collapse.collapsed:
            lines.append(
                "    BASE-RATE COLLAPSE: " + self.report.collapse.detail
            )
            lines.append(
                "    calibration figures suppressed — a constant predictor is "
                "trivially calibrated, so its ECE is not evidence of skill."
            )
            return lines

        cal = self.report.calibration
        assert cal is not None
        # ECE / Brier reported WITH the sample size at equal prominence.
        ece = f"{cal.ece:.4f}" if cal.ece is not None else "n/a"
        brier = f"{cal.brier_score:.4f}" if cal.brier_score is not None else "n/a"
        lines.append(f"    ECE = {ece}   Brier = {brier}   (n = {cal.n_predictions})")
        # BSS-vs-naive is a supporting figure, shown ONLY for validated cells. On
        # a no-demonstrated-skill OR provisional (under-re-validation) cell, a
        # positive BSS number sitting above the caveat reads as self-contradictory
        # (BSS measures sharpness vs the base rate, not an edge), so it is
        # deliberately suppressed there.
        if (
            self.scope.status is MarketStatus.VALIDATED
            and self.report.bss is not None
            and self.report.bss.bss is not None
        ):
            lines.append(
                f"    BSS vs naive base rate = {self.report.bss.bss:+.4f} "
                f"(supporting figure; n = {self.report.bss.n})"
            )
        if self.scope.status is MarketStatus.PROVISIONAL:
            lines.append(
                "    NOTE: UNDER RE-VALIDATION — prior skill figure withdrawn "
                "(same-match feature leakage found by audit); BSS suppressed, "
                "calibration shown for transparency only, not as an edge."
            )
        if self.scope.status is MarketStatus.NO_DEMONSTRATED_SKILL:
            lines.append(
                "    NOTE: no demonstrated skill over base rate in this league — "
                "calibration shown for transparency, not as an actionable edge."
            )
        lines.append("    reliability curve (predicted bucket vs realized rate):")
        for bucket in self.buckets:
            if bucket.count > 0:
                lines.append(bucket.render())
        return lines


def build_reliability_cell(
    market: str,
    predicted: Sequence[float],
    outcomes: Sequence[bool],
    *,
    league_label: Optional[str] = None,
    minimum: int = MIN_SETTLED_FOR_CALIBRATION,
    n_bins: int = 10,
) -> ReliabilityCell:
    """Build one market/league reliability cell from settled predictions.

    Args:
        market: market key (its validated status is resolved here).
        predicted: out-of-sample predicted probabilities of the market outcome.
        outcomes: realized binary outcomes (same length as ``predicted``).
        league_label: the league for this cell (``None`` for pooled).
        minimum: minimum-sample gate (default ~200).
        n_bins: reliability-curve buckets.
    """
    scope = market_status(market, league_label)
    report = calibration_report(
        market, predicted, outcomes,
        league_label=league_label, minimum=minimum, n_bins=n_bins,
    )
    return ReliabilityCell(
        market=market, league_label=league_label, scope=scope, report=report
    )


# ─────────────────────────────────────────────────────────────────────────────
# The full public report
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ReliabilityReport:
    """The assembled public reliability report across market/league cells."""

    cells: tuple[ReliabilityCell, ...]

    def displayable_cells(self) -> list[ReliabilityCell]:
        return [c for c in self.cells if c.displayable]

    def gated_cells(self) -> list[ReliabilityCell]:
        return [
            c for c in self.cells
            if c.scope.status is not MarketStatus.EXCLUDED and not c.report.gate_met
        ]

    def render(self) -> str:
        """Render the public artifact, with the mandatory honest framing appended."""
        lines: list[str] = []
        lines.append("=" * 78)
        lines.append("PUBLIC RELIABILITY REPORT — CALIBRATED PREDICTION ENGINE")
        lines.append("=" * 78)
        lines.append(
            "Calibration is the claim: when the model says 65%, the outcome should "
            "happen about 65% of the time."
        )
        lines.append(
            f"Minimum-sample gate: no calibration figure below ~{MIN_SETTLED_FOR_CALIBRATION} "
            "settled predictions per cell. Every metric is shown with its sample size."
        )
        lines.append("")
        for c in self.cells:
            lines.extend(c.render_lines())
            lines.append("")
        lines.append("-" * 78)
        lines.append("HONEST FRAMING")
        lines.extend(honest_framing_lines(prefix="  "))
        lines.append("=" * 78)
        return "\n".join(lines)


def build_reliability_report(
    cells_input: Sequence[tuple[str, Optional[str], Sequence[float], Sequence[bool]]],
    *,
    minimum: int = MIN_SETTLED_FOR_CALIBRATION,
    n_bins: int = 10,
) -> ReliabilityReport:
    """Assemble a public reliability report from per-cell settled predictions.

    Args:
        cells_input: an iterable of ``(market, league_label, predicted, outcomes)``
            tuples — one per market/league cell to report.
        minimum: minimum-sample gate (default ~200).
        n_bins: reliability-curve buckets.
    """
    cells = tuple(
        build_reliability_cell(
            market, predicted, outcomes,
            league_label=league_label, minimum=minimum, n_bins=n_bins,
        )
        for (market, league_label, predicted, outcomes) in cells_input
    )
    return ReliabilityReport(cells=cells)
