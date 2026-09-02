"""Experiment reporting — human-readable summaries.

.. deprecated:: EV framing only
    The EV/edge columns rendered here (Mean/Median EV, +EV rate, ROI) belong to
    the deprecated market-comparison layer — the market-beating objective is
    closed. Those fields are retained for internal research only and are **not a
    product claim**; do not surface them in user-facing output. The calibration
    and accuracy metrics in these reports remain valid and feed the calibrated
    prediction engine (``src.research.prediction_engine``). See
    ``src.research._ev_deprecation``.

Generates clear, neutral research reports.
Does NOT claim the strategy works.
"""

from __future__ import annotations

from typing import Optional

from src.research.experiment_engine.result import (
    EvidenceClassification,
    ExperimentResult,
    ExperimentResultStatus,
    EVStatus,
)


class ExperimentReporter:
    """Generates human-readable experiment summaries."""

    def generate_summary(self, result: ExperimentResult) -> str:
        """Generate a complete experiment summary.

        Args:
            result: Completed experiment result.

        Returns:
            Multi-line formatted summary string.
        """
        lines = []
        lines.append("=" * 60)
        lines.append("RESEARCH EXPERIMENT REPORT")
        lines.append("=" * 60)
        lines.append("")

        # Identity
        lines.append(f"Experiment ID:    {result.experiment_id}")
        lines.append(f"Status:           {result.status.value}")
        lines.append(f"Classification:   {result.classification.value}")
        lines.append("")

        # Market
        lines.append(f"Market:           {result.market_type}")
        lines.append(f"Model:            {result.model_identity}")
        lines.append("")

        # Hypothesis
        lines.append(f"Candidate Hash:   {result.candidate_hash}")
        lines.append(f"Hypothesis Hash:  {result.hypothesis_hash}")
        lines.append("")

        # Temporal
        lines.append("TEMPORAL DESIGN")
        lines.append("-" * 40)
        lines.append(f"Training:         {result.training_period[0]} → {result.training_period[1]}")
        lines.append(f"Evaluation:       {result.evaluation_period[0]} → {result.evaluation_period[1]}")
        if result.validation_period:
            lines.append(f"Validation:       {result.validation_period[0]} → {result.validation_period[1]}")
        lines.append("")

        # Observations
        counts = result.observation_counts
        lines.append("OBSERVATIONS")
        lines.append("-" * 40)
        lines.append(f"Total rows:       {counts.total_rows}")
        lines.append(f"Eligible:         {counts.eligible_rows}")
        lines.append(f"Missing:          {counts.missing_rows}")
        lines.append(f"Invalid:          {counts.invalid_rows}")
        lines.append(f"Predictions:      {result.prediction_count}")
        lines.append("")

        if result.status != ExperimentResultStatus.COMPLETED:
            lines.append("EXPERIMENT DID NOT COMPLETE")
            lines.append(f"Reason: {result.warnings[0] if result.warnings else 'Unknown'}")
            lines.append("")
            return "\n".join(lines)

        # Predictive metrics
        pm = result.predictive_metrics
        lines.append("PREDICTIVE METRICS")
        lines.append("-" * 40)
        lines.append(f"Sample size:      {pm.sample_size}")
        lines.append(f"Hit rate:         {self._fmt_pct(pm.hit_rate)}")
        lines.append(f"Model P(mean):    {self._fmt_float(pm.model_probability_mean)}")
        lines.append(f"Actual freq:      {self._fmt_float(pm.actual_frequency)}")
        lines.append(f"Brier score:      {self._fmt_float(pm.brier_score)}")
        lines.append(f"Log loss:         {self._fmt_float(pm.log_loss)}")
        lines.append(f"ECE:              {self._fmt_float(pm.ece)}")
        lines.append(f"MCE:              {self._fmt_float(pm.mce)}")
        lines.append("")

        # Baseline comparison
        bl = result.baseline_comparison
        lines.append("BASELINE COMPARISON")
        lines.append("-" * 40)
        lines.append(f"Baseline:         {bl.baseline_name}")
        lines.append(f"Baseline freq:    {self._fmt_float(bl.baseline_frequency)}")
        lines.append(f"Candidate freq:   {self._fmt_float(bl.candidate_frequency)}")
        lines.append(f"Improvement:      {self._fmt_float(bl.improvement)}")
        lines.append(f"Baseline Brier:   {self._fmt_float(bl.baseline_brier)}")
        lines.append(f"Candidate Brier:  {self._fmt_float(bl.candidate_brier)}")
        lines.append(f"Brier improve:    {self._fmt_float(bl.brier_improvement)}")
        lines.append("")

        # Economic metrics
        em = result.economic_metrics
        lines.append("ECONOMIC METRICS")
        lines.append("-" * 40)
        if em.odds_available:
            lines.append(f"Odds:             AVAILABLE")
            lines.append(f"Mean EV:          {self._fmt_float(em.mean_ev)}")
            lines.append(f"Median EV:        {self._fmt_float(em.median_ev)}")
            lines.append(f"+EV rate:         {self._fmt_pct(em.positive_ev_rate)}")
            lines.append(f"Mean odds:        {self._fmt_float(em.mean_odds)}")
            lines.append(f"ROI:              {self._fmt_pct(em.roi_pct, is_pct=True)}")
            lines.append(f"# Bets:           {em.number_of_bets}")
            lines.append(f"Total P&L:        {self._fmt_float(em.total_profit_loss)}")
            lines.append(f"Max drawdown:     {self._fmt_float(em.max_drawdown)}")
        else:
            lines.append(f"Odds:             NOT AVAILABLE")
            lines.append(f"EV:               MISSING_ODDS")
        lines.append("")

        # Statistical evidence
        ev = result.statistical_evidence
        lines.append("STATISTICAL EVIDENCE")
        lines.append("-" * 40)
        lines.append(f"Sample size:      {ev.sample_size}")
        lines.append(f"Mean outcome:     {self._fmt_float(ev.mean_outcome)}")
        lines.append(f"Baseline:         {self._fmt_float(ev.baseline_outcome)}")
        lines.append(f"Difference:       {self._fmt_float(ev.difference)}")
        lines.append(f"CI:               [{self._fmt_float(ev.confidence_interval_lower)}, {self._fmt_float(ev.confidence_interval_upper)}]")
        lines.append(f"Effect size:      {self._fmt_float(ev.effect_size)}")
        lines.append(f"p-value:          {self._fmt_float(ev.p_value)}")
        lines.append(f"Significant:      {ev.is_significant} (α={ev.significance_level})")
        lines.append("")

        # Warnings
        if result.warnings:
            lines.append("WARNINGS")
            lines.append("-" * 40)
            for w in result.warnings:
                lines.append(f"  • {w}")
            lines.append("")

        # Limitations
        if result.limitations:
            lines.append("LIMITATIONS")
            lines.append("-" * 40)
            for lim in result.limitations:
                lines.append(f"  • {lim}")
            lines.append("")

        # Classification
        lines.append("=" * 60)
        lines.append(f"RESEARCH CLASSIFICATION: {result.classification.value}")
        lines.append("")
        lines.append("NOTE: This is a research label, not production approval.")
        lines.append("No profitability claim is made by this classification.")
        lines.append("=" * 60)

        return "\n".join(lines)

    def _fmt_float(self, val: Optional[float], decimals: int = 4) -> str:
        if val is None:
            return "N/A"
        return f"{val:.{decimals}f}"

    def _fmt_pct(self, val: Optional[float], is_pct: bool = False) -> str:
        if val is None:
            return "N/A"
        if is_pct:
            return f"{val:.2f}%"
        return f"{val * 100:.2f}%"
