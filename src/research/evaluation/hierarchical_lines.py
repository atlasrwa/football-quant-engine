"""Walk-forward evaluation of the hierarchical line set. Calibration leads.

**The primary endpoint is calibration, and it is not a contrast.** Every prior
evaluation in this repo asked "does the model beat a baseline?", and the answer was
always a small effect that mostly failed FDR correction. That question is closed
and out of scope: this engine exists to produce calibrated probabilities across a
full line set, so the question that matters is whether each cell's stated
probabilities match the rate things actually happen at.

So the null hypothesis per cell is ``these forecasts are calibrated``, tested by
parametric bootstrap: resample outcomes from the model's own predicted
probabilities, recompute expected calibration error, and ask how often the
resampled error is as large as the observed one. A **finding is a detection of
miscalibration** — a cell the model is getting wrong — with a fresh
Benjamini-Hochberg family over every league x market x line cell. That inverts the
usual direction deliberately: FDR correction here protects against crying "broken"
too often, and no arrangement of these results can be read as a skill claim.

Brier and log loss are reported as supporting figures. Skill against naive
climatology is computed and reported per cell, and is **explicitly unresolved**:
the pooled-versus-within-league question is still open, the effects are small, and
the content gate blocks skill claims. Every cell carries
``skill_claim_blocked: true`` so no downstream reader can quietly promote it.

Discipline held throughout:

* Expanding folds in kickoff order. Standardisation, dispersion selection, the
  negative-binomial dispersion, every empirical-Bayes prior variance and every
  shrinkage weight are fitted inside the training fold only.
* Compute-before-update over complete equal-kickoff batches: no fixture is scored
  after a same-kickoff fixture has updated rolling history.
* Climatology is league-and-line specific and estimated from the training snapshot
  of each fold, never from the whole corpus.
* The bootstrap resamples whole date or league-week blocks. Fixtures in a
  match-week are not independent.
* Every preregistered cell appears in the report, including insufficient ones,
  with machine-readable reasons.
* Monotonicity across the line ladder is checked on every scored fixture and the
  violation count is reported. It should be zero, by construction.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Optional, Sequence

import numpy as np
from scipy.stats import norm

from src.research.models.hierarchical_market_model import (
    HierarchicalConfig,
    HierarchicalCountModel,
)
from src.research.models.market_family import (
    DERIVED_BTTS,
    MarketFamily,
    default_market_families,
)
from src.research.models.side_rows import FixtureRows, training_rows

SCHEMA_VERSION = "hierarchical-line-evaluation/v1"

VERDICT_CALIBRATED = "calibrated"
VERDICT_MISCALIBRATED = "miscalibrated"
VERDICT_INSUFFICIENT = "insufficient"

BTTS_DERIVED = "btts_derived"
BTTS_DIRECT = "btts_direct"


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class HierarchicalEvalConfig:
    """Walk-forward and inference settings, all preregistered."""

    #: Labelled side rows required before the first fit.
    min_global_train: int = 2000
    #: Equal-kickoff batches between refits. A refit is a fold boundary.
    refit_every_kickoff_batches: int = 100
    #: Prior rows a league needs before its fixtures are scored at all.
    min_league_train: int = 60
    #: Scored predictions a cell needs before any figure is published for it.
    #: Mirrors the spirit of the live minimum-sample gate: an ECE on 20
    #: predictions is noise.
    min_cell_predictions: int = 100
    min_bootstrap_blocks: int = 5
    bootstrap_draws: int = 1000
    #: "date" or "league_week".
    bootstrap_block: str = "league_week"
    calibration_bins: int = 10
    fdr_q: float = 0.05
    climatology_prior: float = 1.0
    seed: int = 20260907
    #: Compare derived BTTS against a directly fitted classifier.
    evaluate_btts_contrast: bool = True

    def __post_init__(self) -> None:
        if self.bootstrap_block not in ("date", "league_week"):
            raise ValueError("bootstrap_block must be 'date' or 'league_week'")
        if not 0.0 < self.fdr_q < 1.0:
            raise ValueError("fdr_q must be in (0, 1)")
        if self.calibration_bins < 2:
            raise ValueError("calibration_bins must be at least 2")


@dataclass(frozen=True, slots=True)
class _Prediction:
    """One scored (fixture, family, line) row."""

    fixture_id: str
    league: str
    family: str
    line: float
    kickoff: int
    date_block: str
    league_week_block: str
    outcome: float
    p_model: float
    p_climatology: float
    fold_id: int
    window_used_home: int
    window_used_away: int
    window_shrunk: bool


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────
def expected_calibration_error(
    probabilities: np.ndarray, outcomes: np.ndarray, bins: int
) -> float:
    """Weighted mean absolute gap between stated and realised rates."""
    if len(probabilities) == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(probabilities)
    error = 0.0
    for index in range(bins):
        low, high = edges[index], edges[index + 1]
        if index == bins - 1:
            mask = (probabilities >= low) & (probabilities <= high)
        else:
            mask = (probabilities >= low) & (probabilities < high)
        count = int(mask.sum())
        if count == 0:
            continue
        error += (count / total) * abs(
            float(probabilities[mask].mean()) - float(outcomes[mask].mean())
        )
    return error


def reliability_curve(
    probabilities: np.ndarray, outcomes: np.ndarray, bins: int
) -> list[dict[str, object]]:
    """Bin-by-bin reliability, so a reader can see *where* a cell goes wrong."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    curve: list[dict[str, object]] = []
    for index in range(bins):
        low, high = edges[index], edges[index + 1]
        if index == bins - 1:
            mask = (probabilities >= low) & (probabilities <= high)
        else:
            mask = (probabilities >= low) & (probabilities < high)
        count = int(mask.sum())
        curve.append(
            {
                "bin_lower": round(float(low), 4),
                "bin_upper": round(float(high), 4),
                "n": count,
                "mean_predicted": (
                    round(float(probabilities[mask].mean()), 6) if count else None
                ),
                "observed_rate": (
                    round(float(outcomes[mask].mean()), 6) if count else None
                ),
            }
        )
    return curve


def brier(probabilities: np.ndarray, outcomes: np.ndarray) -> float:
    return float(np.mean((probabilities - outcomes) ** 2))


def log_loss(probabilities: np.ndarray, outcomes: np.ndarray) -> float:
    clipped = np.clip(probabilities, 1e-12, 1.0 - 1e-12)
    return float(
        -np.mean(outcomes * np.log(clipped) + (1.0 - outcomes) * np.log(1.0 - clipped))
    )


def _metrics(
    probabilities: np.ndarray, outcomes: np.ndarray, bins: int
) -> dict[str, float]:
    return {
        "ece": expected_calibration_error(probabilities, outcomes, bins),
        "brier": brier(probabilities, outcomes),
        "log_loss": log_loss(probabilities, outcomes),
    }


def _stable_seed(base: int, *parts: object) -> int:
    digest = hashlib.sha256(
        "|".join([str(base), *(str(part) for part in parts)]).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big")


# ─────────────────────────────────────────────────────────────────────────────
# The evaluator
# ─────────────────────────────────────────────────────────────────────────────
class HierarchicalLineEvaluator:
    """Expanding walk-forward evaluation of every family and every line."""

    def __init__(
        self,
        config: HierarchicalEvalConfig | None = None,
        *,
        model_config: HierarchicalConfig | None = None,
    ) -> None:
        self.config = config or HierarchicalEvalConfig()
        self.model_config = model_config or HierarchicalConfig()

    # ── entry point ───────────────────────────────────────────────────────
    def evaluate(
        self,
        fixtures_by_family: Mapping[str, Sequence[FixtureRows]],
        families: Sequence[MarketFamily] | None = None,
        *,
        preregistered_leagues: Sequence[str] | None = None,
    ) -> dict[str, object]:
        families = tuple(families or default_market_families())
        predictions: list[_Prediction] = []
        diagnostics: list[dict[str, object]] = []
        btts_records: list[dict[str, object]] = []
        fit_reports: list[dict[str, object]] = []

        for family in families:
            fixtures = fixtures_by_family.get(family.name) or []
            if not fixtures:
                diagnostics.append(
                    {
                        "family": family.name,
                        "status": "no_rows",
                        "reason": "no fixtures carried this family's target",
                    }
                )
                continue
            family_predictions, family_diagnostics, family_btts, reports = (
                self._walk_forward(family, fixtures)
            )
            predictions.extend(family_predictions)
            diagnostics.append(family_diagnostics)
            btts_records.extend(family_btts)
            fit_reports.extend(reports)

        leagues = tuple(
            preregistered_leagues
            or sorted({prediction.league for prediction in predictions})
        )
        cells = self._build_cells(predictions, families, leagues)
        family_size = self._apply_benjamini_hochberg(cells)
        pooled = self._pooled_rows(predictions, families)
        btts_summary = self._btts_summary(btts_records)

        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "config": {
                **asdict(self.config),
                "primary_endpoint": "expected_calibration_error",
                "primary_hypothesis": (
                    "H0: the cell's forecasts are calibrated. A finding is a "
                    "detection of miscalibration, not a skill claim."
                ),
                "null_distribution": (
                    "parametric bootstrap: outcomes resampled from the model's own "
                    "predicted probabilities over whole "
                    f"{self.config.bootstrap_block} blocks"
                ),
                "supporting_metrics": ["brier", "log_loss"],
                "skill_status": (
                    "reported but unresolved; the pooled-versus-within-league "
                    "question is open and the content gate blocks skill claims"
                ),
                "climatology": (
                    "league-and-line specific, estimated from each expanding fold's "
                    "training snapshot only"
                ),
                "preprocessing": (
                    "standardisation, dispersion selection and every shrinkage "
                    "weight are fitted inside the training fold"
                ),
            },
            "families": [
                {
                    "name": family.name,
                    "lines": list(family.lines),
                    "line_rationale": family.line_rationale,
                    "feature_names": list(family.feature_names),
                    "league_varying_slopes": list(family.features.league_varying),
                    "unavailable_mechanisms": list(
                        family.features.unavailable_mechanisms
                    ),
                    "requires_half_split": family.requires_half_split,
                }
                for family in families
            ],
            "governance": {
                "preregistered_cell_count": len(cells),
                "valid_family_size": family_size,
                "fdr_method": "Benjamini-Hochberg step-up",
                "fdr_q": self.config.fdr_q,
                "fdr_family_scope": "every league x market x line cell, fresh family",
                "q_values": "monotone BH adjusted p-values over the valid family",
                "invalid_cells_retained": True,
                "finding_means": "miscalibration detected",
                "skill_claims": "blocked",
                "pooled_only_positives": (
                    "pooled rows are reported alongside per-league cells and never "
                    "as a substitute for them; a pooled figure that no league "
                    "reproduces is an artifact of between-league dispersion"
                ),
            },
            "walk_forward": {
                "fold_type": "expanding chronological",
                "equal_kickoff_batches": True,
                "strict_train_before_score": True,
                "family_diagnostics": diagnostics,
            },
            "fit_reports": fit_reports,
            "monotonicity": self._monotonicity_summary(diagnostics),
            "cells": cells,
            "pooled_rows": pooled,
            "btts_contrast": btts_summary,
        }

    # ── walk forward ──────────────────────────────────────────────────────
    def _walk_forward(
        self, family: MarketFamily, fixtures: Sequence[FixtureRows]
    ) -> tuple[
        list[_Prediction], dict[str, object], list[dict[str, object]], list[dict[str, object]]
    ]:
        ordered = sorted(fixtures, key=lambda item: (item.kickoff_unix, item.fixture_id))
        predictions: list[_Prediction] = []
        btts_records: list[dict[str, object]] = []
        fit_reports: list[dict[str, object]] = []

        training: list[FixtureRows] = []
        league_counts: dict[str, int] = {}
        model: Optional[HierarchicalCountModel] = None
        direct_btts: Optional[_DirectBttsModel] = None
        climatology: dict[tuple[str, float], float] = {}
        fold_id = 0
        batches_since_refit = 0
        skipped_not_ready = 0
        skipped_no_window = 0
        prediction_failures = 0
        monotonicity_violations = 0
        scored_fixtures = 0

        for batch in _kickoff_batches(ordered):
            labelled = training_rows(training)
            if len(labelled) >= self.config.min_global_train and (
                model is None
                or batches_since_refit >= self.config.refit_every_kickoff_batches
            ):
                candidate = HierarchicalCountModel(family, self.model_config)
                try:
                    candidate.fit(labelled)
                except (ValueError, RuntimeError):
                    candidate = None  # type: ignore[assignment]
                if candidate is not None:
                    model = candidate
                    climatology = self._fit_climatology(family, training)
                    fold_id += 1
                    batches_since_refit = 0
                    if family.derives_btts and self.config.evaluate_btts_contrast:
                        direct_btts = _DirectBttsModel(family.feature_names)
                        direct_btts.fit(training)
                    fit_reports.append(
                        {"fold_id": fold_id, **model.fit_report()}
                    )

            if model is not None:
                for fixture in batch:
                    if league_counts.get(fixture.league, 0) < self.config.min_league_train:
                        skipped_not_ready += 1
                        continue
                    if fixture.gate_reason is not None:
                        skipped_no_window += 1
                        continue
                    if fixture.total_count is None:
                        continue
                    try:
                        distribution = model.predict_match(
                            fixture.home_row, fixture.away_row
                        )
                    except (ValueError, RuntimeError, OverflowError, KeyError):
                        prediction_failures += 1
                        continue

                    probabilities = [
                        distribution.p_over(line) for line in family.lines
                    ]
                    if any(not math.isfinite(value) for value in probabilities):
                        prediction_failures += 1
                        continue
                    # Monotonicity is guaranteed by construction; verify anyway,
                    # because "guaranteed" is a claim about code that can change.
                    for earlier, later in zip(probabilities, probabilities[1:]):
                        if later > earlier + 1e-12:
                            monotonicity_violations += 1

                    scored_fixtures += 1
                    for line, probability in zip(family.lines, probabilities):
                        reference = climatology.get((fixture.league, line))
                        if reference is None:
                            prediction_failures += 1
                            continue
                        predictions.append(
                            _Prediction(
                                fixture_id=fixture.fixture_id,
                                league=fixture.league,
                                family=family.name,
                                line=line,
                                kickoff=fixture.kickoff_unix,
                                date_block=fixture.date_block,
                                league_week_block=fixture.league_week_block,
                                outcome=(
                                    1.0 if fixture.total_count > line else 0.0
                                ),
                                p_model=probability,
                                p_climatology=reference,
                                fold_id=fold_id,
                                window_used_home=fixture.home_form.window.used,
                                window_used_away=fixture.away_form.window.used,
                                window_shrunk=(
                                    fixture.home_form.window.shrunk
                                    or fixture.away_form.window.shrunk
                                ),
                            )
                        )

                    if family.derives_btts and self.config.evaluate_btts_contrast:
                        observed = fixture.both_scored()
                        if observed is not None and direct_btts is not None:
                            direct = direct_btts.predict(fixture)
                            if direct is not None:
                                btts_records.append(
                                    {
                                        "fixture_id": fixture.fixture_id,
                                        "league": fixture.league,
                                        "outcome": observed,
                                        BTTS_DERIVED: distribution.p_both_score(),
                                        BTTS_DIRECT: direct,
                                        "fold_id": fold_id,
                                    }
                                )

            # Compute-before-update: this batch enters training only now.
            training.extend(batch)
            for fixture in batch:
                league_counts[fixture.league] = league_counts.get(fixture.league, 0) + 1
            batches_since_refit += 1

        diagnostics = {
            "family": family.name,
            "status": "scored" if predictions else "no_predictions",
            "n_input_fixtures": len(ordered),
            "n_folds": fold_id,
            "n_scored_fixtures": scored_fixtures,
            "n_scored_fixture_lines": len(predictions),
            "skipped_league_not_ready": skipped_not_ready,
            "skipped_no_current_season_window": skipped_no_window,
            "prediction_failures": prediction_failures,
            "monotonicity_violations": monotonicity_violations,
        }
        return predictions, diagnostics, btts_records, fit_reports

    def _fit_climatology(
        self, family: MarketFamily, training: Sequence[FixtureRows]
    ) -> dict[tuple[str, float], float]:
        """League-and-line over-rates from the training snapshot only."""
        totals: dict[str, list[float]] = {}
        for fixture in training:
            if fixture.total_count is None:
                continue
            totals.setdefault(fixture.league, []).append(fixture.total_count)
        prior = self.config.climatology_prior
        climatology: dict[tuple[str, float], float] = {}
        for league, counts in totals.items():
            for line in family.lines:
                over = sum(1 for count in counts if count > line)
                denominator = len(counts) + 2.0 * prior
                climatology[(league, line)] = (
                    (over + prior) / denominator if denominator > 0 else 0.5
                )
        return climatology

    # ── cells ─────────────────────────────────────────────────────────────
    def _build_cells(
        self,
        predictions: Sequence[_Prediction],
        families: Sequence[MarketFamily],
        leagues: Sequence[str],
    ) -> list[dict[str, object]]:
        grouped: dict[tuple[str, str, float], list[_Prediction]] = {}
        for prediction in predictions:
            grouped.setdefault(
                (prediction.league, prediction.family, prediction.line), []
            ).append(prediction)

        cells: list[dict[str, object]] = []
        for league in leagues:
            for family in families:
                for line in family.lines:
                    records = grouped.get((league, family.name, line), [])
                    cells.append(self._make_cell(league, family, line, records))
        return cells

    def _make_cell(
        self,
        league: str,
        family: MarketFamily,
        line: float,
        records: Sequence[_Prediction],
    ) -> dict[str, object]:
        reasons = self._insufficient_reasons(records)
        cell: dict[str, object] = {
            "league": league,
            "family": family.name,
            "line": line,
            "status": "insufficient" if reasons else "tested",
            "insufficient_reasons": reasons,
            "n_predictions": len(records),
            "n_blocks": len({self._block_id(record) for record in records}),
            "skill_claim_blocked": True,
            "calibration": None,
            "reliability_curve": [],
            "supporting": None,
            "skill_secondary": None,
            "window_support": None,
            "fdr": {
                "raw_p": None,
                "threshold": None,
                "rank": None,
                "family_size": None,
                "reject": False,
                "q_value": None,
            },
            "verdict": VERDICT_INSUFFICIENT,
        }
        if reasons:
            return cell

        probabilities = np.array([record.p_model for record in records], dtype=float)
        outcomes = np.array([record.outcome for record in records], dtype=float)
        reference = np.array(
            [record.p_climatology for record in records], dtype=float
        )
        bins = self.config.calibration_bins

        observed = _metrics(probabilities, outcomes, bins)
        baseline = _metrics(reference, outcomes, bins)
        calibration_test = self._calibration_test(records, probabilities, league, family, line)

        cell["calibration"] = {
            "ece": round(observed["ece"], 6),
            "ece_null_mean": round(calibration_test["null_mean"], 6),
            "ece_null_ci95": [
                round(calibration_test["null_ci95"][0], 6),
                round(calibration_test["null_ci95"][1], 6),
            ],
            "p_miscalibration": round(calibration_test["p_value"], 6),
            "observed_rate": round(float(outcomes.mean()), 6),
            "mean_predicted": round(float(probabilities.mean()), 6),
            "bins": bins,
        }
        cell["reliability_curve"] = reliability_curve(probabilities, outcomes, bins)
        cell["supporting"] = {
            "brier": round(observed["brier"], 6),
            "log_loss": round(observed["log_loss"], 6),
            "climatology_brier": round(baseline["brier"], 6),
            "climatology_log_loss": round(baseline["log_loss"], 6),
            "climatology_ece": round(baseline["ece"], 6),
        }
        cell["skill_secondary"] = {
            "brier_delta_vs_climatology": round(
                baseline["brier"] - observed["brier"], 6
            ),
            "status": "reported_but_unresolved",
            "note": (
                "secondary and not corrected in this family; the "
                "pooled-versus-within-league question is open and no skill claim "
                "may be drawn from this figure"
            ),
        }
        used = [
            min(record.window_used_home, record.window_used_away)
            for record in records
        ]
        cell["window_support"] = {
            "median_window_matches_used": float(np.median(used)),
            "share_shrunk_window": round(
                float(np.mean([record.window_shrunk for record in records])), 4
            ),
        }
        cell["fdr"]["raw_p"] = round(calibration_test["p_value"], 6)
        return cell

    def _calibration_test(
        self,
        records: Sequence[_Prediction],
        probabilities: np.ndarray,
        league: str,
        family: MarketFamily,
        line: float,
    ) -> dict[str, object]:
        """Parametric bootstrap test of ``H0: this cell is calibrated``.

        Outcomes are resampled from the model's own stated probabilities, so the
        null distribution of expected calibration error carries the cell's exact
        sample size and probability spread. Resampling is done over whole blocks
        so the null respects the same dependence structure the data has: an entire
        match-week is redrawn together, not individual fixtures.
        """
        bins = self.config.calibration_bins
        blocks: dict[str, list[int]] = {}
        for index, record in enumerate(records):
            blocks.setdefault(self._block_id(record), []).append(index)
        block_indexes = [np.asarray(value, dtype=int) for _, value in sorted(blocks.items())]

        seed = _stable_seed(self.config.seed, league, family.name, line, "calibration")
        rng = np.random.default_rng(seed)
        observed_outcomes = np.array([record.outcome for record in records], dtype=float)
        observed_ece = expected_calibration_error(probabilities, observed_outcomes, bins)

        null_values: list[float] = []
        for _ in range(self.config.bootstrap_draws):
            selected = rng.integers(0, len(block_indexes), size=len(block_indexes))
            indexes = np.concatenate([block_indexes[i] for i in selected])
            resampled_probabilities = probabilities[indexes]
            simulated = (
                rng.random(len(indexes)) < resampled_probabilities
            ).astype(float)
            null_values.append(
                expected_calibration_error(resampled_probabilities, simulated, bins)
            )
        null_array = np.array(null_values, dtype=float)
        # One-sided: only calibration error LARGER than the null is evidence of
        # miscalibration. The +1 correction keeps the p-value strictly positive.
        p_value = float((np.sum(null_array >= observed_ece) + 1) / (len(null_array) + 1))
        return {
            "p_value": p_value,
            "null_mean": float(null_array.mean()),
            "null_ci95": (
                float(np.quantile(null_array, 0.025)),
                float(np.quantile(null_array, 0.975)),
            ),
        }

    def _insufficient_reasons(self, records: Sequence[_Prediction]) -> list[str]:
        reasons: list[str] = []
        if not records:
            reasons.append("no_walk_forward_predictions")
            return reasons
        if len(records) < self.config.min_cell_predictions:
            reasons.append(f"n_predictions<{self.config.min_cell_predictions}")
        blocks = len({self._block_id(record) for record in records})
        if blocks < self.config.min_bootstrap_blocks:
            reasons.append(f"n_blocks<{self.config.min_bootstrap_blocks}")
        return reasons

    def _block_id(self, record: _Prediction) -> str:
        if self.config.bootstrap_block == "date":
            return record.date_block
        return record.league_week_block

    # ── FDR ───────────────────────────────────────────────────────────────
    def _apply_benjamini_hochberg(self, cells: Sequence[dict[str, object]]) -> int:
        """One fresh BH pass over every valid cell in the family."""
        indexed: list[tuple[float, int]] = []
        for index, cell in enumerate(cells):
            if cell["status"] != "tested":
                continue
            raw = cell["fdr"]["raw_p"]  # type: ignore[index]
            if raw is None or not math.isfinite(float(raw)):
                continue
            indexed.append((float(raw), index))

        family_size = len(indexed)
        for cell in cells:
            cell["fdr"]["family_size"] = family_size  # type: ignore[index]
        if family_size == 0:
            return 0

        indexed.sort()
        cutoff = 0
        raw_adjusted: list[float] = []
        for rank, (p_value, _) in enumerate(indexed, start=1):
            threshold = self.config.fdr_q * rank / family_size
            if p_value <= threshold:
                cutoff = rank
            raw_adjusted.append(min(1.0, p_value * family_size / rank))
        monotone = list(raw_adjusted)
        for position in range(len(monotone) - 2, -1, -1):
            monotone[position] = min(monotone[position], monotone[position + 1])

        for rank, (p_value, index) in enumerate(indexed, start=1):
            cell = cells[index]
            cell["fdr"] = {
                "raw_p": round(p_value, 6),
                "threshold": round(self.config.fdr_q * rank / family_size, 8),
                "rank": rank,
                "family_size": family_size,
                "reject": rank <= cutoff,
                "q_value": round(monotone[rank - 1], 6),
            }
            cell["verdict"] = (
                VERDICT_MISCALIBRATED if rank <= cutoff else VERDICT_CALIBRATED
            )
        return family_size

    # ── pooled rows and summaries ─────────────────────────────────────────
    def _pooled_rows(
        self, predictions: Sequence[_Prediction], families: Sequence[MarketFamily]
    ) -> list[dict[str, object]]:
        """Cross-league figures, published *beside* per-league cells.

        Pooled numbers are reported because they are the only figures with enough
        sample to be stable at this stage, and flagged because a pooled positive
        that no league reproduces is an artifact of between-league dispersion, not
        a result.
        """
        grouped: dict[tuple[str, float], list[_Prediction]] = {}
        for prediction in predictions:
            grouped.setdefault((prediction.family, prediction.line), []).append(
                prediction
            )
        rows: list[dict[str, object]] = []
        for family in families:
            for line in family.lines:
                records = grouped.get((family.name, line), [])
                if len(records) < self.config.min_cell_predictions:
                    rows.append(
                        {
                            "league": "POOLED",
                            "family": family.name,
                            "line": line,
                            "status": "insufficient",
                            "n_predictions": len(records),
                        }
                    )
                    continue
                probabilities = np.array(
                    [record.p_model for record in records], dtype=float
                )
                outcomes = np.array([record.outcome for record in records], dtype=float)
                reference = np.array(
                    [record.p_climatology for record in records], dtype=float
                )
                observed = _metrics(probabilities, outcomes, self.config.calibration_bins)
                baseline = _metrics(reference, outcomes, self.config.calibration_bins)
                rows.append(
                    {
                        "league": "POOLED",
                        "family": family.name,
                        "line": line,
                        "status": "tested",
                        "n_predictions": len(records),
                        "n_leagues": len({record.league for record in records}),
                        "ece": round(observed["ece"], 6),
                        "brier": round(observed["brier"], 6),
                        "log_loss": round(observed["log_loss"], 6),
                        "observed_rate": round(float(outcomes.mean()), 6),
                        "mean_predicted": round(float(probabilities.mean()), 6),
                        "climatology_ece": round(baseline["ece"], 6),
                        "climatology_brier": round(baseline["brier"], 6),
                        "skill_claim_blocked": True,
                        "note": (
                            "pooled figures never substitute for per-league cells; "
                            "a pooled positive no league reproduces is an artifact"
                        ),
                    }
                )
        return rows

    def _btts_summary(
        self, records: Sequence[Mapping[str, object]]
    ) -> dict[str, object]:
        """Derived-from-goals BTTS against a directly fitted classifier.

        The derived version is preferred on architectural grounds: it cannot
        contradict the goals lines. That preference is only defensible if it does
        not cost accuracy out of sample, which is what this measures.
        """
        if not records:
            return {
                "status": "not_evaluated",
                "reason": "no BTTS records; goals family produced no scored fixtures",
            }
        outcomes = np.array([float(record["outcome"]) for record in records])
        derived = np.array([float(record[BTTS_DERIVED]) for record in records])
        direct = np.array([float(record[BTTS_DIRECT]) for record in records])
        bins = self.config.calibration_bins
        derived_metrics = _metrics(derived, outcomes, bins)
        direct_metrics = _metrics(direct, outcomes, bins)

        by_league: dict[str, dict[str, object]] = {}
        leagues = {str(record["league"]) for record in records}
        for league in sorted(leagues):
            mask = np.array([str(record["league"]) == league for record in records])
            if int(mask.sum()) < self.config.min_cell_predictions:
                by_league[league] = {
                    "status": "insufficient",
                    "n": int(mask.sum()),
                }
                continue
            league_derived = _metrics(derived[mask], outcomes[mask], bins)
            league_direct = _metrics(direct[mask], outcomes[mask], bins)
            by_league[league] = {
                "status": "tested",
                "n": int(mask.sum()),
                "derived": {k: round(v, 6) for k, v in league_derived.items()},
                "direct": {k: round(v, 6) for k, v in league_direct.items()},
                "derived_preferred_on_log_loss": (
                    league_derived["log_loss"] <= league_direct["log_loss"]
                ),
            }

        tested = [
            value for value in by_league.values() if value.get("status") == "tested"
        ]
        derived_wins = sum(
            1 for value in tested if value["derived_preferred_on_log_loss"]
        )
        return {
            "status": "tested",
            "n_predictions": len(records),
            "derived": {k: round(v, 6) for k, v in derived_metrics.items()},
            "direct": {k: round(v, 6) for k, v in direct_metrics.items()},
            "direct_model": "logistic regression on the goals feature block, refit per fold",
            "leagues_where_derived_preferred_on_log_loss": derived_wins,
            "leagues_tested": len(tested),
            "per_league": by_league,
            "decision_rule": (
                "keep the derived version unless it underperforms the direct model "
                "out of sample; coherence with the goals lines is the tiebreak"
            ),
            "derived_kept": derived_metrics["log_loss"] <= direct_metrics["log_loss"],
        }

    def _monotonicity_summary(
        self, diagnostics: Sequence[Mapping[str, object]]
    ) -> dict[str, object]:
        violations = sum(
            int(item.get("monotonicity_violations") or 0) for item in diagnostics
        )
        checked = sum(int(item.get("n_scored_fixtures") or 0) for item in diagnostics)
        return {
            "fixtures_checked": checked,
            "violations": violations,
            "guarantee": (
                "every line is the survival function of one convolved total PMF, so "
                "P(over a) >= P(over b) for a < b holds by construction"
            ),
            "holds": violations == 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Direct BTTS comparator
# ─────────────────────────────────────────────────────────────────────────────
class _DirectBttsModel:
    """A plain logistic regression on the goals feature block.

    Present only so the derived-versus-direct comparison is an honest one: the
    comparator gets the same features, the same training fold and the same
    standardisation discipline as the count model.
    """

    def __init__(self, feature_names: Sequence[str]) -> None:
        self.feature_names = tuple(feature_names)
        self._coefficients: Optional[np.ndarray] = None
        self._intercept = 0.0
        self._means: Optional[np.ndarray] = None
        self._scales: Optional[np.ndarray] = None

    def fit(self, fixtures: Sequence[FixtureRows]) -> None:
        rows: list[np.ndarray] = []
        labels: list[float] = []
        for fixture in fixtures:
            outcome = fixture.both_scored()
            if outcome is None:
                continue
            rows.append(self._design(fixture))
            labels.append(outcome)
        if len(rows) < 200 or len(set(labels)) < 2:
            self._coefficients = None
            return
        x = np.vstack(rows)
        y = np.array(labels, dtype=float)
        self._means = x.mean(axis=0)
        scales = x.std(axis=0, ddof=0)
        self._scales = np.where(scales < 1e-9, 1.0, scales)
        standardised = (x - self._means) / self._scales

        from scipy.optimize import minimize

        def negative_log_likelihood(params: np.ndarray) -> float:
            logits = np.clip(params[0] + standardised @ params[1:], -30.0, 30.0)
            probabilities = 1.0 / (1.0 + np.exp(-logits))
            probabilities = np.clip(probabilities, 1e-12, 1.0 - 1e-12)
            likelihood = float(
                np.sum(y * np.log(probabilities) + (1.0 - y) * np.log(1.0 - probabilities))
            )
            return -(likelihood - 0.02 * float(np.sum(params[1:] ** 2)))

        start = np.zeros(standardised.shape[1] + 1)
        start[0] = math.log(max(1e-6, y.mean()) / max(1e-6, 1.0 - y.mean()))
        result = minimize(
            negative_log_likelihood,
            start,
            method="L-BFGS-B",
            options={"maxiter": 300, "ftol": 1e-8},
        )
        estimate = result.x if np.all(np.isfinite(result.x)) else start
        self._intercept = float(estimate[0])
        self._coefficients = np.asarray(estimate[1:], dtype=float)

    def _design(self, fixture: FixtureRows) -> np.ndarray:
        home = fixture.home_row.features
        away = fixture.away_row.features
        return np.array(
            [float(home.get(name, 0.0)) for name in self.feature_names]
            + [float(away.get(name, 0.0)) for name in self.feature_names],
            dtype=float,
        )

    def predict(self, fixture: FixtureRows) -> Optional[float]:
        if self._coefficients is None or self._means is None or self._scales is None:
            return None
        standardised = (self._design(fixture) - self._means) / self._scales
        logit = float(
            np.clip(self._intercept + standardised @ self._coefficients, -30.0, 30.0)
        )
        return float(1.0 / (1.0 + math.exp(-logit)))


def _kickoff_batches(
    ordered: Sequence[FixtureRows],
) -> list[list[FixtureRows]]:
    batches: list[list[FixtureRows]] = []
    cursor = 0
    while cursor < len(ordered):
        kickoff = ordered[cursor].kickoff_unix
        end = cursor + 1
        while end < len(ordered) and ordered[end].kickoff_unix == kickoff:
            end += 1
        batches.append(list(ordered[cursor:end]))
        cursor = end
    return batches
