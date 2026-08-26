"""Season-Level Stability Reporting — regime analysis across seasons.

Reports performance metrics broken down by:
- Season
- Fold
- League
- Market

Uses EXISTING statistical infrastructure — does NOT create new tests.
Wraps existing WalkForwardResult and FoldResult for season-level views.

Key metrics per season:
- Number of folds
- Positive fold ratio
- Aggregate p-value
- Brier score
- EV/ROI when odds available
- Sample size
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SeasonFoldMetrics:
    """Metrics for a single fold within a season."""
    fold_index: int
    season: str
    league_id: int
    sample_size: int
    p_value: Optional[float] = None
    brier_score: Optional[float] = None
    hit_rate: Optional[float] = None
    ev_per_bet: Optional[float] = None
    roi: Optional[float] = None
    is_positive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_index": self.fold_index,
            "season": self.season,
            "league_id": self.league_id,
            "sample_size": self.sample_size,
            "p_value": self.p_value,
            "brier_score": self.brier_score,
            "hit_rate": self.hit_rate,
            "ev_per_bet": self.ev_per_bet,
            "roi": self.roi,
            "is_positive": self.is_positive,
        }


@dataclass(frozen=True)
class SeasonStabilityReport:
    """Stability report for a single season within multi-season research."""
    season: str
    season_id: int
    league_id: int
    total_folds: int
    positive_folds: int
    sample_size: int
    aggregate_p_value: Optional[float] = None
    mean_brier: Optional[float] = None
    mean_roi: Optional[float] = None
    max_drawdown: Optional[float] = None
    fold_metrics: tuple[SeasonFoldMetrics, ...] = ()

    @property
    def positive_fold_ratio(self) -> float:
        if self.total_folds == 0:
            return 0.0
        return self.positive_folds / self.total_folds

    @property
    def is_stable(self) -> bool:
        """Conservative stability check — majority of folds positive."""
        return self.positive_fold_ratio >= 0.6 and self.total_folds >= 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "season_id": self.season_id,
            "league_id": self.league_id,
            "total_folds": self.total_folds,
            "positive_folds": self.positive_folds,
            "positive_fold_ratio": round(self.positive_fold_ratio, 3),
            "sample_size": self.sample_size,
            "aggregate_p_value": self.aggregate_p_value,
            "mean_brier": self.mean_brier,
            "mean_roi": self.mean_roi,
            "max_drawdown": self.max_drawdown,
            "is_stable": self.is_stable,
        }


@dataclass
class MultiSeasonStabilityReport:
    """Aggregate stability across all seasons."""
    hypothesis_id: str
    market_type: str
    total_seasons: int = 0
    stable_seasons: int = 0
    total_folds: int = 0
    positive_folds: int = 0
    total_sample_size: int = 0
    overall_p_value: Optional[float] = None
    season_reports: list[SeasonStabilityReport] = field(default_factory=list)

    @property
    def stable_season_ratio(self) -> float:
        if self.total_seasons == 0:
            return 0.0
        return self.stable_seasons / self.total_seasons

    @property
    def overall_positive_fold_ratio(self) -> float:
        if self.total_folds == 0:
            return 0.0
        return self.positive_folds / self.total_folds

    @property
    def is_regime_stable(self) -> bool:
        """Whether the hypothesis shows stability across seasons/regimes."""
        return (
            self.total_seasons >= 2
            and self.stable_season_ratio >= 0.5
            and self.overall_positive_fold_ratio >= 0.5
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "market_type": self.market_type,
            "total_seasons": self.total_seasons,
            "stable_seasons": self.stable_seasons,
            "stable_season_ratio": round(self.stable_season_ratio, 3),
            "total_folds": self.total_folds,
            "positive_folds": self.positive_folds,
            "overall_positive_fold_ratio": round(self.overall_positive_fold_ratio, 3),
            "total_sample_size": self.total_sample_size,
            "overall_p_value": self.overall_p_value,
            "is_regime_stable": self.is_regime_stable,
            "per_season": [sr.to_dict() for sr in self.season_reports],
        }


def build_season_stability_report(
    hypothesis_id: str,
    market_type: str,
    fold_results: list[dict[str, Any]],
    matches_by_season: Optional[dict[str, list[dict[str, Any]]]] = None,
) -> MultiSeasonStabilityReport:
    """Build a multi-season stability report from walk-forward fold results.

    Args:
        hypothesis_id: The hypothesis being evaluated.
        market_type: Market type being tested.
        fold_results: List of fold result dicts from walk-forward.
            Each should contain: fold_index, season (optional), league_id (optional),
            sample_size, p_value, brier_score, hit_rate, ev_per_bet, roi, is_positive.
        matches_by_season: Optional mapping of season->match data for coverage.

    Returns:
        MultiSeasonStabilityReport with per-season breakdown.
    """
    # Group folds by season
    season_folds: dict[str, list[dict[str, Any]]] = {}
    for fold in fold_results:
        season = fold.get("season", "unknown")
        if season not in season_folds:
            season_folds[season] = []
        season_folds[season].append(fold)

    # Build per-season reports
    season_reports: list[SeasonStabilityReport] = []
    total_folds = 0
    positive_folds = 0
    total_sample = 0

    for season, folds in sorted(season_folds.items()):
        fold_metrics = []
        season_positive = 0
        season_sample = 0

        for fold in folds:
            is_positive = fold.get("is_positive", False)
            sample = fold.get("sample_size", 0)
            season_sample += sample

            fm = SeasonFoldMetrics(
                fold_index=fold.get("fold_index", 0),
                season=season,
                league_id=fold.get("league_id", 0),
                sample_size=sample,
                p_value=fold.get("p_value"),
                brier_score=fold.get("brier_score"),
                hit_rate=fold.get("hit_rate"),
                ev_per_bet=fold.get("ev_per_bet"),
                roi=fold.get("roi"),
                is_positive=is_positive,
            )
            fold_metrics.append(fm)
            if is_positive:
                season_positive += 1

        # Compute season-level aggregates
        p_values = [f.get("p_value") for f in folds if f.get("p_value") is not None]
        brier_scores = [f.get("brier_score") for f in folds if f.get("brier_score") is not None]
        rois = [f.get("roi") for f in folds if f.get("roi") is not None]

        season_report = SeasonStabilityReport(
            season=season,
            season_id=folds[0].get("season_id", 0) if folds else 0,
            league_id=folds[0].get("league_id", 0) if folds else 0,
            total_folds=len(folds),
            positive_folds=season_positive,
            sample_size=season_sample,
            aggregate_p_value=min(p_values) if p_values else None,  # Conservative
            mean_brier=sum(brier_scores) / len(brier_scores) if brier_scores else None,
            mean_roi=sum(rois) / len(rois) if rois else None,
            fold_metrics=tuple(fold_metrics),
        )
        season_reports.append(season_report)

        total_folds += len(folds)
        positive_folds += season_positive
        total_sample += season_sample

    # Sort season reports chronologically (by season label)
    season_reports.sort(key=lambda sr: sr.season)

    return MultiSeasonStabilityReport(
        hypothesis_id=hypothesis_id,
        market_type=market_type,
        total_seasons=len(season_reports),
        stable_seasons=sum(1 for sr in season_reports if sr.is_stable),
        total_folds=total_folds,
        positive_folds=positive_folds,
        total_sample_size=total_sample,
        season_reports=season_reports,
    )
