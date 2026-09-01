"""Reporting — complete, honest headline report assembly (Req 10).

Responsibility:
    Assemble a single, honest report from an :class:`AsymmetryReport` (the output
    of :class:`~src.research.asymmetric.evaluation.AsymmetryEvaluator`) plus the
    optional fitted models and calibration inputs. The report carries, per the
    design's Reporting section:

    * headline per-side vs baseline per market and per league (Req 10.1, 8.4);
    * the Rich vs Broad corpus comparison (Req 10.2, 4.4, 4.5);
    * readable elastic-net coefficients per dimension (Req 10.3, 5.7);
    * ECE and reliability curves per target via the existing
      :class:`~src.research.calibration.CalibrationEvaluator` (Req 10.4);
    * out-of-sample BSS vs the naive baseline, Brier, and ECE (Req 10.5);
    * ALL results including failures, with no post-hoc selection (Req 10.6);
    * the fresh FDR family size (Req 10.7, 8.9);
    * a confidence interval for EVERY reported estimate (Req 10.8); and
    * an explicit "not a result" label on any estimate whose CI spans zero
      (Req 10.9, Property 15).

Design decisions:
    * **Render, do not recompute.** Verdicts, BSS-improvement estimates, FDR
      family, and within-league/artifact/insufficient-sample flags are computed
      by the evaluator (task 9) and are attached verbatim here — the report never
      re-runs the decision logic or re-selects results, which is exactly the
      "no post-hoc selection" guarantee of Req 10.6.
    * **CI-spanning-zero suppression is a labelling step, not a filter.** Every
      estimate is still listed (Req 10.6); those whose CI spans zero are labelled
      ``not a result`` (Req 10.9) via :attr:`Estimate.is_result`, and are never
      counted among the findings.
    * **Calibration is out-of-sample only.** Reliability/ECE are computed via the
      reused ``CalibrationEvaluator``, which enforces its own out-of-sample
      contract; this module only forwards already-held-out predictions/outcomes.

This module imports only the isolated asymmetric package and the general-purpose
``src.research.calibration`` building block (no prior-effort modules).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from src.research.asymmetric.evaluation import (
    VERDICT_ARTIFACT,
    VERDICT_FAILS,
    VERDICT_FINDING,
    VERDICT_INSUFFICIENT,
    AsymmetryReport,
)
from src.research.asymmetric.interaction import InteractionModel
from src.research.asymmetric.models import AsymmetryComparison, Estimate
from src.research.calibration import CalibrationEvaluator, CalibrationResult

# The label attached to any estimate whose CI spans zero (Req 10.9).
NOT_A_RESULT_LABEL = "not a result"


# ─────────────────────────────────────────────────────────────────────────────
# Estimate rendering (Req 10.8, 10.9, Property 15)
# ─────────────────────────────────────────────────────────────────────────────
def format_estimate(est: Estimate) -> str:
    """Render an estimate with its CI and the CI-spanning-zero label (Req 10.8/10.9).

    Every estimate is shown with ``[ci_low, ci_high]``; if the closed CI spans
    zero, the estimate is explicitly labelled ``not a result`` (Req 10.9). This is
    the single, canonical rendering used everywhere an estimate appears so the
    suppression rule can never be accidentally skipped.
    """
    base = f"{est.point:+.4f} [95% CI {est.ci_low:+.4f}, {est.ci_high:+.4f}]"
    if not est.is_result:
        return f"{base}  ({NOT_A_RESULT_LABEL}: CI spans zero)"
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Coefficient reporting (Req 10.3)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CoefficientReport:
    """Readable elastic-net coefficients for one (direction, target) model.

    Attributes:
        direction: the direction label.
        target: the per-side target.
        intercept: fitted intercept on the log-rate scale.
        coefficients: ``{feature_name -> weight}`` on the original feature scale,
            directly readable per Req 10.3 (elastic-net keeps them interpretable).
        distribution: the selected distribution ("poisson" | "negative_binomial").
        dispersion_ratio: the empirical variance/mean ratio reported (Req 5.3).
        n_observations: number of fit observations.
    """

    direction: str
    target: str
    intercept: float
    coefficients: dict[str, float]
    distribution: Optional[str]
    dispersion_ratio: Optional[float]
    n_observations: int

    def top_features(self, k: int = 5) -> list[tuple[str, float]]:
        """The ``k`` features with the largest absolute weight (descending)."""
        return sorted(
            self.coefficients.items(), key=lambda kv: abs(kv[1]), reverse=True
        )[:k]


def coefficient_reports(model: InteractionModel) -> list[CoefficientReport]:
    """Extract readable coefficient reports from a fitted InteractionModel (Req 10.3).

    Returns one :class:`CoefficientReport` per fitted (direction, target)
    DirectionalCountModel. An unfitted model yields an empty list.
    """
    reports: list[CoefficientReport] = []
    if not model.is_fitted:
        return reports
    from src.research.asymmetric.interaction import DIRECTION_A, DIRECTION_B

    for direction in (DIRECTION_A, DIRECTION_B):
        for target in model.targets:
            dcm = model.model_for(direction, target)
            if dcm is None or dcm.params is None:
                continue
            reports.append(
                CoefficientReport(
                    direction=direction,
                    target=target,
                    intercept=dcm.intercept,
                    coefficients=dict(dcm.feature_weights),
                    distribution=dcm.distribution_used,
                    dispersion_ratio=dcm.dispersion_ratio,
                    n_observations=dcm.params.n_observations,
                )
            )
    return reports


# ─────────────────────────────────────────────────────────────────────────────
# Calibration reporting (Req 10.4, 10.5, 5.7)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TargetCalibration:
    """Out-of-sample calibration for one target (Req 10.4, 10.5).

    ``result`` is the reused :class:`CalibrationResult` (Brier, log-loss, ECE,
    reliability bins). ``target`` names the per-side target and ``line`` records
    the O/U threshold whose tail probability was calibrated (Req 5.7 tail bins).
    """

    target: str
    line: float
    result: CalibrationResult

    @property
    def ece(self) -> Optional[float]:
        return self.result.ece

    @property
    def brier(self) -> Optional[float]:
        return self.result.brier_score


def calibration_for_target(
    target: str,
    line: float,
    predicted_probabilities: Sequence[float],
    actual_outcomes: Sequence[bool],
    *,
    n_bins: int = 10,
    min_samples: int = 10,
) -> TargetCalibration:
    """Compute out-of-sample calibration for one target via CalibrationEvaluator.

    The predictions MUST already be out-of-sample (held-out) — the reused
    evaluator computes Brier/log-loss/ECE and reliability (tail) bins against the
    realised outcomes (Req 5.7, 10.4, 10.5). This is a thin, honest forwarder.
    """
    evaluator = CalibrationEvaluator(n_bins=n_bins, min_samples=min_samples)
    result = evaluator.evaluate(list(predicted_probabilities), list(actual_outcomes))
    return TargetCalibration(target=target, line=line, result=result)


# ─────────────────────────────────────────────────────────────────────────────
# Rich vs Broad comparison (Req 10.2, 4.4, 4.5)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RichBroadComparison:
    """Side-by-side rich-vs-broad verdict counts per (target, direction, league).

    Each entry pairs the rich-corpus comparison with the broad-corpus comparison
    for the same cell so the report can show how the reduced Broad profile fares
    against the full Rich profile (Req 4.4, 4.5, 10.2).
    """

    cell: tuple[str, str, Optional[str]]  # (target, direction, league)
    rich: Optional[AsymmetryComparison]
    broad: Optional[AsymmetryComparison]


def compare_rich_broad(
    rich_report: AsymmetryReport,
    broad_report: Optional[AsymmetryReport],
) -> list[RichBroadComparison]:
    """Align rich and broad comparisons cell-by-cell (Req 10.2, 4.4, 4.5).

    Cells present in either report are emitted; a cell absent from one corpus
    carries ``None`` on that side. When ``broad_report`` is ``None`` (single-corpus
    run) every entry carries only the rich comparison.
    """

    def key(c: AsymmetryComparison) -> tuple[str, str, Optional[str]]:
        return (c.target, c.direction, c.league)

    rich_map = {key(c): c for c in rich_report.comparisons}
    broad_map = (
        {key(c): c for c in broad_report.comparisons} if broad_report else {}
    )
    cells = sorted(
        set(rich_map) | set(broad_map),
        key=lambda t: (t[0], t[1], t[2] or ""),
    )
    return [
        RichBroadComparison(cell=cell, rich=rich_map.get(cell), broad=broad_map.get(cell))
        for cell in cells
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Assembled report (Req 10.1, 10.6, 10.7)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AsymmetryReportDocument:
    """The assembled, honest report document (Req 10).

    Holds every comparison (including failures, Req 10.6), the fresh FDR family
    size (Req 10.7), readable coefficients (Req 10.3), per-target calibration
    (Req 10.4/10.5), and the rich-vs-broad comparison (Req 10.2). ``render()``
    produces the human-readable text; all estimates are rendered through
    :func:`format_estimate` so the CI and the CI-spanning-zero label are always
    present (Req 10.8, 10.9).
    """

    rich_report: AsymmetryReport
    broad_report: Optional[AsymmetryReport]
    coefficients: tuple[CoefficientReport, ...]
    calibration: tuple[TargetCalibration, ...]
    rich_broad: tuple[RichBroadComparison, ...]

    # ── convenience accessors ────────────────────────────────────
    @property
    def family_size(self) -> int:
        """The fresh FDR family size (Req 10.7, 8.9)."""
        return self.rich_report.family_size

    def all_comparisons(self) -> list[AsymmetryComparison]:
        """Every comparison, findings and failures alike (Req 10.6)."""
        return list(self.rich_report.comparisons)

    def findings(self) -> list[AsymmetryComparison]:
        return self.rich_report.findings()

    def verdict_counts(self) -> dict[str, int]:
        counts = {
            VERDICT_FINDING: 0,
            VERDICT_ARTIFACT: 0,
            VERDICT_FAILS: 0,
            VERDICT_INSUFFICIENT: 0,
        }
        for c in self.rich_report.comparisons:
            counts[c.verdict] = counts.get(c.verdict, 0) + 1
        return counts

    # ── rendering ────────────────────────────────────────────────
    def render(self) -> str:
        """Render the full report as text (Req 10.1-10.9)."""
        lines: list[str] = []
        lines.append("=" * 78)
        lines.append("ASYMMETRIC MATCHUP ENGINE — RESULTS REPORT")
        lines.append("=" * 78)
        lines.append("")

        # Headline / summary (Req 10.1, 10.6, 10.7).
        counts = self.verdict_counts()
        lines.append(
            f"Fresh FDR family size (hypotheses tested): {self.family_size}"
        )
        lines.append(
            "Verdicts: "
            f"{counts[VERDICT_FINDING]} finding(s), "
            f"{counts[VERDICT_ARTIFACT]} artifact(s), "
            f"{counts[VERDICT_FAILS]} fail(s), "
            f"{counts[VERDICT_INSUFFICIENT]} insufficient-sample."
        )
        lines.append(
            f"Walk-forward folds: {self.rich_report.n_folds}; "
            f"min within-league sample: {self.rich_report.min_within_league}."
        )
        lines.append("")

        # Per-side vs baseline, per market and per league (Req 10.1, 8.4, 8.5).
        lines.append("-" * 78)
        lines.append(
            "HEADLINE — Interaction vs Symmetric_Baseline "
            "(BSS improvement, per target/direction/league)"
        )
        lines.append(
            "Every comparison is shown, including failures (no post-hoc "
            "selection, Req 10.6). Interaction is never reported without its "
            "paired baseline (Req 8.5)."
        )
        lines.append("-" * 78)
        for c in self._sorted_comparisons(self.rich_report.comparisons):
            league = c.league if c.league is not None else "POOLED"
            lines.append(
                f"[{c.corpus}] {c.target:<8} {c.direction:<22} {league:<14} "
                f"verdict={c.verdict}"
            )
            lines.append(
                f"    BSS improvement: {format_estimate(c.bss_improvement)}"
            )
            flags = []
            if c.within_league_significant:
                flags.append("within-league sig")
            if c.pooled_only_artifact:
                flags.append("pooled-only artifact")
            if c.insufficient_sample:
                flags.append("insufficient-sample")
            if c.fdr_passed is True:
                flags.append("survives BH q=0.05")
            elif c.fdr_passed is False:
                flags.append("fails BH q=0.05")
            if flags:
                lines.append("    flags: " + ", ".join(flags))
        lines.append("")

        # Rich vs Broad (Req 10.2, 4.4, 4.5).
        if self.rich_broad:
            lines.append("-" * 78)
            lines.append("RICH vs BROAD corpus comparison (Req 10.2, 4.4, 4.5)")
            lines.append("-" * 78)
            for rb in self.rich_broad:
                target, direction, league = rb.cell
                league_label = league if league is not None else "POOLED"
                rich_v = rb.rich.verdict if rb.rich else "—"
                broad_v = rb.broad.verdict if rb.broad else "—"
                lines.append(
                    f"{target:<8} {direction:<22} {league_label:<14} "
                    f"rich={rich_v:<18} broad={broad_v}"
                )
            lines.append("")

        # Readable elastic-net coefficients (Req 10.3).
        if self.coefficients:
            lines.append("-" * 78)
            lines.append("READABLE ELASTIC-NET COEFFICIENTS (Req 10.3, 5.7)")
            lines.append("-" * 78)
            for cr in self.coefficients:
                lines.append(
                    f"{cr.direction} / {cr.target}: "
                    f"dist={cr.distribution}, dispersion_ratio="
                    f"{_fmt_opt(cr.dispersion_ratio)}, n={cr.n_observations}"
                )
                lines.append(f"    intercept: {cr.intercept:+.4f}")
                for name, weight in cr.top_features():
                    lines.append(f"    {name:<28} {weight:+.4f}")
            lines.append("")

        # Calibration per target (Req 10.4, 10.5, 5.7).
        if self.calibration:
            lines.append("-" * 78)
            lines.append(
                "CALIBRATION per target — out-of-sample "
                "(Brier, ECE, reliability; Req 10.4, 10.5, 5.7)"
            )
            lines.append("-" * 78)
            for tc in self.calibration:
                res = tc.result
                if res.is_valid:
                    lines.append(
                        f"{tc.target} (line {tc.line}): "
                        f"Brier={_fmt_opt(res.brier_score)}, "
                        f"log_loss={_fmt_opt(res.log_loss)}, "
                        f"ECE={_fmt_opt(res.ece)}, "
                        f"MCE={_fmt_opt(res.mce)}, n={res.n_predictions}"
                    )
                    lines.append(
                        f"    reliability bins: {len(res.bins)} "
                        "(predicted vs actual per bin)"
                    )
                else:
                    lines.append(
                        f"{tc.target} (line {tc.line}): calibration unavailable "
                        f"({res.status.value}: {res.reason})"
                    )
            lines.append("")

        lines.append("=" * 78)
        lines.append("END OF REPORT")
        lines.append("=" * 78)
        return "\n".join(lines)

    @staticmethod
    def _sorted_comparisons(
        comparisons: Sequence[AsymmetryComparison],
    ) -> list[AsymmetryComparison]:
        return sorted(
            comparisons,
            key=lambda c: (c.corpus, c.target, c.direction, c.league or ""),
        )


def _fmt_opt(value: Optional[float]) -> str:
    """Format an optional float, or ``n/a`` when None."""
    return f"{value:.4f}" if value is not None else "n/a"


# ─────────────────────────────────────────────────────────────────────────────
# Top-level assembly (Req 10.1-10.9)
# ─────────────────────────────────────────────────────────────────────────────
def assemble_report(
    rich_report: AsymmetryReport,
    *,
    broad_report: Optional[AsymmetryReport] = None,
    interaction_model: Optional[InteractionModel] = None,
    calibration: Optional[Sequence[TargetCalibration]] = None,
) -> AsymmetryReportDocument:
    """Assemble the honest report document from evaluator output (Req 10).

    Args:
        rich_report: the Rich_Corpus :class:`AsymmetryReport` (required).
        broad_report: the Broad_Corpus report for the rich-vs-broad comparison
            (Req 10.2); optional for a single-corpus run.
        interaction_model: a fitted InteractionModel whose readable coefficients
            are extracted (Req 10.3); optional.
        calibration: precomputed per-target calibrations (Req 10.4/10.5),
            typically produced by :func:`calibration_for_target` on held-out
            predictions; optional.

    Returns:
        An :class:`AsymmetryReportDocument` carrying ALL comparisons (Req 10.6),
        the fresh FDR family size (Req 10.7), coefficients, calibration, and the
        rich-vs-broad comparison, ready for :meth:`AsymmetryReportDocument.render`.
    """
    coeffs = (
        tuple(coefficient_reports(interaction_model))
        if interaction_model is not None
        else ()
    )
    calib = tuple(calibration) if calibration is not None else ()
    rich_broad = tuple(compare_rich_broad(rich_report, broad_report))
    return AsymmetryReportDocument(
        rich_report=rich_report,
        broad_report=broad_report,
        coefficients=coeffs,
        calibration=calib,
        rich_broad=rich_broad,
    )
