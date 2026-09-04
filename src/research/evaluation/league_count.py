"""Governed league evaluation for coherent count-distribution model arms.

This module keeps model fitting, fixture alignment, multiplicity correction, and
verdict assignment in one reusable path.  The primary preregistered endpoint is
the paired Brier-score improvement (reference loss minus candidate loss).  Log
loss and ECE are reported with the same block-bootstrap treatment as secondary
endpoints; BH is applied once to every valid primary endpoint in the complete
league x market-line x contrast family.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

import numpy as np
from scipy.stats import norm

from src.research.models.hierarchical_count import (
    COUNT_ARMS,
    HIERARCHICAL_ARM,
    INDEPENDENT_ARM,
    POOLED_ARM,
    CountMarketSpec,
    LeagueCountModel,
)
from src.research.models.prior_only_features import CARDS_FEATURES, CORNERS_FEATURES

CLIMATOLOGY_ARM = "league_climatology"
ALL_EVALUATED_ARMS = COUNT_ARMS + (CLIMATOLOGY_ARM,)

VERDICT_FINDING = "finding"
VERDICT_ARTIFACT = "pooled-only-artifact"
VERDICT_FAILS = "fails"
VERDICT_INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class Contrast:
    name: str
    candidate: str
    reference: str

    def __post_init__(self) -> None:
        if self.candidate not in ALL_EVALUATED_ARMS:
            raise ValueError(f"unknown candidate arm {self.candidate!r}")
        if self.reference not in ALL_EVALUATED_ARMS:
            raise ValueError(f"unknown reference arm {self.reference!r}")
        if self.candidate == self.reference:
            raise ValueError("contrast arms must differ")


DEFAULT_CONTRASTS: tuple[Contrast, ...] = (
    Contrast("pooled_vs_climatology", POOLED_ARM, CLIMATOLOGY_ARM),
    Contrast("independent_vs_climatology", INDEPENDENT_ARM, CLIMATOLOGY_ARM),
    Contrast("hierarchical_vs_climatology", HIERARCHICAL_ARM, CLIMATOLOGY_ARM),
    Contrast("independent_vs_pooled", INDEPENDENT_ARM, POOLED_ARM),
    Contrast("hierarchical_vs_pooled", HIERARCHICAL_ARM, POOLED_ARM),
    Contrast("hierarchical_vs_independent", HIERARCHICAL_ARM, INDEPENDENT_ARM),
)


@dataclass(frozen=True, slots=True)
class LeagueCountEvaluationConfig:
    min_global_train: int = 200
    min_league_train: int = 40
    refit_every_kickoff_batches: int = 20
    min_cell_predictions: int = 30
    min_bootstrap_blocks: int = 5
    bootstrap_draws: int = 2000
    bootstrap_block: str = "league_week"
    calibration_bins: int = 10
    climatology_prior: float = 1.0
    fdr_q: float = 0.05
    alpha: float = 0.05
    seed: int = 20260902

    def __post_init__(self) -> None:
        positive = (
            self.min_global_train,
            self.min_league_train,
            self.refit_every_kickoff_batches,
            self.min_cell_predictions,
            self.min_bootstrap_blocks,
            self.bootstrap_draws,
            self.calibration_bins,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("sample, fold, bin, and bootstrap settings must be positive")
        if self.bootstrap_block not in {"date", "league_week"}:
            raise ValueError("bootstrap_block must be 'date' or 'league_week'")
        if self.climatology_prior < 0.0:
            raise ValueError("climatology_prior must be non-negative")
        if not 0.0 < self.fdr_q < 1.0 or not 0.0 < self.alpha < 1.0:
            raise ValueError("fdr_q and alpha must be in (0, 1)")


@dataclass(slots=True)
class LeagueCountEvaluationReport:
    schema_version: str
    generated_at: str
    config: dict[str, object]
    markets: list[dict[str, object]]
    contrasts: list[dict[str, str]]
    governance: dict[str, object]
    walk_forward: dict[str, object]
    pooled_results: list[dict[str, object]]
    cells: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _Prediction:
    fixture_id: str
    league: str
    market: str
    line: float
    kickoff: int
    date_block: str
    league_week_block: str
    outcome: float
    probabilities: dict[str, float]
    fold_id: int


# Broad-corpus strictly-prior feature families. Goal predictors are deliberately
# distinct from corner predictors and use only each team's historical post-match
# production, never the fixture being predicted.
GOALS_FEATURES: tuple[str, ...] = (
    "shots_home",
    "shots_away",
    "shots_on_target_home",
    "shots_on_target_away",
    "xg_home",
    "xg_away",
    "dangerous_attacks_home",
    "dangerous_attacks_away",
)

# Raw broad-corpus stat used to construct each CountRegressionModel feature.
# Every mapping is explicit so unsupported provider fields fail closed below.
_FEATURE_SOURCES: dict[str, tuple[str, str]] = {
    "dangerous_attacks_home": ("dangerous_attacks", "home"),
    "dangerous_attacks_away": ("dangerous_attacks", "away"),
    "attacks_home": ("attacks", "home"),
    "attacks_away": ("attacks", "away"),
    "possession_home": ("possession", "home"),
    "possession_away": ("possession", "away"),
    "shots_home": ("shots", "home"),
    "shots_away": ("shots", "away"),
    "shots_on_target_home": ("shots_on_target", "home"),
    "shots_on_target_away": ("shots_on_target", "away"),
    "xg_home": ("xg", "home"),
    "xg_away": ("xg", "away"),
    "fouls_home": ("fouls", "home"),
    "fouls_away": ("fouls", "away"),
}
_RAW_STAT_KEYS: dict[str, tuple[str, str]] = {
    "dangerous_attacks": ("team_a_dangerous_attacks", "team_b_dangerous_attacks"),
    "attacks": ("team_a_attacks", "team_b_attacks"),
    "possession": ("team_a_possession", "team_b_possession"),
    "shots": ("team_a_shots", "team_b_shots"),
    "shots_on_target": ("team_a_shotsOnTarget", "team_b_shotsOnTarget"),
    "xg": ("team_a_xg", "team_b_xg"),
    "fouls": ("team_a_fouls", "team_b_fouls"),
}


def default_count_markets() -> tuple[CountMarketSpec, ...]:
    """The preregistered broad-corpus count markets and reporting lines."""
    return (
        CountMarketSpec(
            name="goals",
            target_field="total_goals",
            lines=(1.5, 2.5, 3.5),
            feature_fields=GOALS_FEATURES,
        ),
        CountMarketSpec(
            name="corners",
            target_field="total_corners",
            lines=(8.5, 9.5, 10.5),
            feature_fields=CORNERS_FEATURES,
        ),
        CountMarketSpec(
            name="cards",
            target_field="total_cards",
            lines=(3.5, 4.5),
            feature_fields=CARDS_FEATURES,
        ),
    )


def build_broad_count_rows(
    matches: Sequence[Mapping[str, object]],
    markets: Sequence[CountMarketSpec],
    *,
    window: int = 10,
    min_prior: int = 3,
) -> dict[str, list[dict[str, object]]]:
    """Adapt FootyStats broad fixtures into strictly-prior model rows.

    Fixtures sharing a kickoff are emitted as a batch before *any* outcome or
    realised stat in that batch updates rolling history.  Team histories and
    neutral feature priors are league-local.  The count target is carried only
    because ``CountRegressionModel.fit`` reads it as its label; no target or
    current-fixture statistic is included in ``feature_fields``.
    """
    if window <= 0 or min_prior <= 0:
        raise ValueError("window and min_prior must be positive")
    names = [market.name for market in markets]
    if not names:
        raise ValueError("at least one market is required")
    if len(set(names)) != len(names):
        raise ValueError("market names must be unique")
    requested_features = set().union(*(market.feature_fields for market in markets))
    unsupported_features = sorted(requested_features - set(_FEATURE_SOURCES))
    if unsupported_features:
        raise ValueError(
            "broad-corpus prior feature provenance is not defined for: "
            + ", ".join(unsupported_features)
        )

    deduplicated: dict[str, Mapping[str, object]] = {}
    for match in matches:
        if str(match.get("status") or "").casefold() != "complete":
            continue
        kickoff = _integer(match.get("date_unix"))
        if kickoff is None or kickoff <= 0:
            continue
        fixture_id = _fixture_id(match)
        deduplicated.setdefault(fixture_id, match)
    ordered = sorted(deduplicated.values(), key=lambda m: (_integer(m.get("date_unix")) or 0, _fixture_id(m)))

    history: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    league_sum: dict[tuple[str, str], float] = defaultdict(float)
    league_n: dict[tuple[str, str], int] = defaultdict(int)
    rows: dict[str, list[dict[str, object]]] = {market.name: [] for market in markets}

    cursor = 0
    while cursor < len(ordered):
        kickoff = _integer(ordered[cursor].get("date_unix")) or 0
        end = cursor + 1
        while end < len(ordered) and (_integer(ordered[end].get("date_unix")) or 0) == kickoff:
            end += 1
        batch = ordered[cursor:end]

        for match in batch:
            league = str(match.get("_league") or match.get("league") or "")
            if not league:
                continue
            home_id = match.get("homeID", match.get("home_id"))
            away_id = match.get("awayID", match.get("away_id"))
            if home_id is None or away_id is None:
                continue
            common: dict[str, object] = {
                "_fixture_id": _fixture_id(match),
                "_league": league,
                "_season": str(match.get("_season") or match.get("season") or ""),
                "date_unix": kickoff,
                "home_team_id": home_id,
                "away_team_id": away_id,
                "_date_block": datetime.fromtimestamp(kickoff, tz=timezone.utc).date().isoformat(),
                "_league_week_block": _league_week_block(match, league, kickoff),
            }
            all_features = set().union(*(market.feature_fields for market in markets))
            for feature_name in all_features:
                stat, side = _FEATURE_SOURCES[feature_name]
                team_id = home_id if side == "home" else away_id
                prior = history[(league, str(team_id), stat)][-window:]
                if len(prior) >= min_prior:
                    value = float(np.mean(prior))
                else:
                    key = (league, stat)
                    value = league_sum[key] / league_n[key] if league_n[key] else 0.0
                common[feature_name] = value

            for market in markets:
                target = _target_value(match, market.target_field)
                if target is None:
                    continue
                row = dict(common)
                row[market.target_field] = target
                rows[market.name].append(row)

        # Compute-before-update for the complete equal-kickoff batch.
        for match in batch:
            league = str(match.get("_league") or match.get("league") or "")
            home_id = match.get("homeID", match.get("home_id"))
            away_id = match.get("awayID", match.get("away_id"))
            if not league or home_id is None or away_id is None:
                continue
            for stat, (home_key, away_key) in _RAW_STAT_KEYS.items():
                for team_id, raw_key in ((home_id, home_key), (away_id, away_key)):
                    value = _number(match.get(raw_key))
                    if value is None:
                        continue
                    history[(league, str(team_id), stat)].append(value)
                    league_sum[(league, stat)] += value
                    league_n[(league, stat)] += 1
        cursor = end

    return rows


class LeagueCountEvaluator:
    """Expanding equal-kickoff walk-forward evaluation of every count arm."""

    def __init__(
        self,
        config: LeagueCountEvaluationConfig | None = None,
        *,
        contrasts: Sequence[Contrast] = DEFAULT_CONTRASTS,
    ) -> None:
        self.config = config or LeagueCountEvaluationConfig()
        self.contrasts = tuple(contrasts)
        if not self.contrasts or len({contrast.name for contrast in self.contrasts}) != len(
            self.contrasts
        ):
            raise ValueError("contrasts must be non-empty with unique names")

    def evaluate(
        self,
        rows_by_market: Mapping[str, Sequence[Mapping[str, object]]],
        markets: Sequence[CountMarketSpec],
        *,
        preregistered_leagues: Sequence[str] | None = None,
    ) -> LeagueCountEvaluationReport:
        market_names = [market.name for market in markets]
        if len(set(market_names)) != len(market_names):
            raise ValueError("market names must be unique")
        missing = [name for name in market_names if name not in rows_by_market]
        if missing:
            raise ValueError(f"missing rows for markets: {missing}")

        if preregistered_leagues is None:
            leagues = sorted(
                {
                    str(row.get("_league"))
                    for name in market_names
                    for row in rows_by_market[name]
                    if row.get("_league") is not None
                }
            )
        else:
            leagues = sorted(set(map(str, preregistered_leagues)))
        if not leagues:
            raise ValueError("at least one preregistered league is required")

        predictions: list[_Prediction] = []
        market_diagnostics: list[dict[str, object]] = []
        for market in markets:
            scored, diagnostics = self._walk_forward(rows_by_market[market.name], market)
            predictions.extend(scored)
            market_diagnostics.append(diagnostics)

        pooled_results = self._pooled_results(predictions, markets)
        pooled_lookup = {
            (entry["market"], entry["line"], entry["contrast"]): entry
            for entry in pooled_results
        }

        cells: list[dict[str, object]] = []
        for league in leagues:
            for market in markets:
                for line in market.lines:
                    records = [
                        record
                        for record in predictions
                        if record.league == league
                        and record.market == market.name
                        and record.line == line
                    ]
                    for contrast in self.contrasts:
                        cells.append(self._make_cell(league, market.name, line, contrast, records))

        valid_cells = self._apply_bh(cells)
        group_has_finding: dict[tuple[object, object, object], bool] = defaultdict(bool)
        for cell in cells:
            key = (cell["market"], cell["line"], cell["contrast"])
            group_has_finding[key] = group_has_finding[key] or self._is_finding(cell)

        for cell in cells:
            key = (cell["market"], cell["line"], cell["contrast"])
            pooled = pooled_lookup[key]
            cell["pooled_context"] = {
                "status": pooled["status"],
                "n_predictions": pooled["n_predictions"],
                "primary_effect": pooled.get("effects", {}).get("brier"),
                "any_league_finding": group_has_finding[key],
            }
            cell["verdict"] = self._classify(
                cell,
                pooled,
                any_league_finding=group_has_finding[key],
            )
            cell["pooled_only_positive"] = cell["verdict"] == VERDICT_ARTIFACT

        tested_fixture_sets = {
            f"{market.name}:{line}": len(
                {
                    record.fixture_id
                    for record in predictions
                    if record.market == market.name and record.line == line
                }
            )
            for market in markets
            for line in market.lines
        }
        return LeagueCountEvaluationReport(
            schema_version="league-count-evaluation/v1",
            generated_at=datetime.now(timezone.utc).isoformat(),
            config={
                **asdict(self.config),
                "primary_endpoint": "paired_brier_improvement",
                "effect_direction": "reference_loss_minus_candidate_loss; positive favors candidate",
                "bootstrap_method": "paired cluster bootstrap over complete date/league-week blocks",
                "p_value": "one-sided normal-tail p-value using the paired block-bootstrap standard error",
                "feature_provenance": "league-local strictly-prior rolling means; equal-kickoff compute-before-update",
                "climatology": "league and line specific, estimated from each expanding fold's train snapshot only",
            },
            markets=[
                {
                    "name": market.name,
                    "target_field": market.target_field,
                    "lines": list(market.lines),
                    "feature_fields": list(market.feature_fields),
                    "distribution": market.distribution,
                }
                for market in markets
            ],
            contrasts=[asdict(contrast) for contrast in self.contrasts],
            governance={
                "preregistered_cell_count": len(leagues)
                * sum(len(market.lines) for market in markets)
                * len(self.contrasts),
                "valid_family_size": valid_cells,
                "fdr_method": "Benjamini-Hochberg step-up",
                "fdr_q": self.config.fdr_q,
                "q_values": "monotone BH adjusted p-values over the full valid preregistered family",
                "invalid_cells_retained": True,
                "pooled_only_positive_classification": VERDICT_ARTIFACT,
            },
            walk_forward={
                "fold_type": "expanding chronological",
                "equal_kickoff_batches": True,
                "strict_train_before_score": True,
                "market_diagnostics": market_diagnostics,
                "aligned_fixture_counts": tested_fixture_sets,
            },
            pooled_results=pooled_results,
            cells=cells,
        )

    def _walk_forward(
        self,
        raw_rows: Sequence[Mapping[str, object]],
        market: CountMarketSpec,
    ) -> tuple[list[_Prediction], dict[str, object]]:
        rows = sorted(
            (dict(row) for row in raw_rows),
            key=lambda row: (_integer(row.get("date_unix")) or 0, str(row.get("_fixture_id"))),
        )
        seen: set[str] = set()
        unique_rows: list[dict[str, object]] = []
        for row in rows:
            fixture_id = str(row.get("_fixture_id") or "")
            if not fixture_id or fixture_id in seen:
                continue
            seen.add(fixture_id)
            if _target_number(row.get(market.target_field)) is None:
                continue
            unique_rows.append(row)

        training: list[dict[str, object]] = []
        league_training_n: dict[str, int] = defaultdict(int)
        model: LeagueCountModel | None = None
        climatology: dict[tuple[str, float], float] = {}
        batches_since_refit = self.config.refit_every_kickoff_batches
        fold_id = 0
        refits = 0
        skipped_not_ready = 0
        prediction_failures = 0
        scored: list[_Prediction] = []

        cursor = 0
        while cursor < len(unique_rows):
            kickoff = _integer(unique_rows[cursor].get("date_unix")) or 0
            end = cursor + 1
            while end < len(unique_rows) and (_integer(unique_rows[end].get("date_unix")) or 0) == kickoff:
                end += 1
            batch = unique_rows[cursor:end]

            if len(training) >= self.config.min_global_train and (
                model is None
                or batches_since_refit >= self.config.refit_every_kickoff_batches
            ):
                model = LeagueCountModel(market)
                model.fit(training)
                climatology = self._fit_climatology(training, market)
                fold_id += 1
                refits += 1
                batches_since_refit = 0

            if model is not None:
                for row in batch:
                    league = str(row["_league"])
                    if league_training_n[league] < self.config.min_league_train:
                        skipped_not_ready += 1
                        continue
                    count = float(row[market.target_field])
                    for line in market.lines:
                        try:
                            probabilities = {
                                arm: model.predict_over(row, arm=arm, line=line)
                                for arm in COUNT_ARMS
                            }
                            probabilities[CLIMATOLOGY_ARM] = climatology[(league, line)]
                        except (KeyError, RuntimeError, ValueError, OverflowError):
                            prediction_failures += 1
                            continue
                        if not all(math.isfinite(value) for value in probabilities.values()):
                            prediction_failures += 1
                            continue
                        scored.append(
                            _Prediction(
                                fixture_id=str(row["_fixture_id"]),
                                league=league,
                                market=market.name,
                                line=line,
                                kickoff=kickoff,
                                date_block=str(row["_date_block"]),
                                league_week_block=str(row["_league_week_block"]),
                                outcome=float(count > line),
                                probabilities=probabilities,
                                fold_id=fold_id,
                            )
                        )
                batches_since_refit += 1

            # No row in this kickoff batch enters training until all are scored.
            training.extend(batch)
            for row in batch:
                league_training_n[str(row["_league"])] += 1
            cursor = end

        return scored, {
            "market": market.name,
            "n_input_rows": len(raw_rows),
            "n_unique_labeled_rows": len(unique_rows),
            "n_refits": refits,
            "n_folds": fold_id,
            "n_scored_fixture_lines": len(scored),
            "n_scored_unique_fixtures": len({record.fixture_id for record in scored}),
            "skipped_before_league_ready": skipped_not_ready,
            "prediction_failures": prediction_failures,
        }

    def _fit_climatology(
        self, training: Sequence[Mapping[str, object]], market: CountMarketSpec
    ) -> dict[tuple[str, float], float]:
        by_league: dict[str, list[float]] = defaultdict(list)
        for row in training:
            by_league[str(row["_league"])].append(float(row[market.target_field]))
        prior = self.config.climatology_prior
        output: dict[tuple[str, float], float] = {}
        for league, counts in by_league.items():
            for line in market.lines:
                over = sum(count > line for count in counts)
                denominator = len(counts) + 2.0 * prior
                output[(league, line)] = (
                    (over + prior) / denominator if denominator > 0.0 else 0.5
                )
        return output

    def _make_cell(
        self,
        league: str,
        market: str,
        line: float,
        contrast: Contrast,
        records: Sequence[_Prediction],
    ) -> dict[str, object]:
        reasons = self._insufficient_reasons(records)
        metrics = self._arm_metrics(records)
        cell: dict[str, object] = {
            "league": league,
            "market": market,
            "line": line,
            "contrast": contrast.name,
            "candidate": contrast.candidate,
            "reference": contrast.reference,
            "status": "insufficient" if reasons else "tested",
            "insufficient_reasons": reasons,
            "n_predictions": len(records),
            "n_blocks": len({self._block_id(record) for record in records}),
            "fixture_ids": [record.fixture_id for record in records],
            "identical_fixture_ids_across_arms": all(
                set(record.probabilities) == set(ALL_EVALUATED_ARMS) for record in records
            ),
            "arm_metrics": metrics,
            "effects": {},
            "fdr": {
                "raw_p": None,
                "threshold": None,
                "rank": None,
                "family_size": None,
                "reject": False,
                "q_value": None,
            },
        }
        if not reasons:
            cell["effects"] = self._bootstrap_effects(records, contrast, league, market, line)
        return cell

    def _pooled_results(
        self, predictions: Sequence[_Prediction], markets: Sequence[CountMarketSpec]
    ) -> list[dict[str, object]]:
        output: list[dict[str, object]] = []
        for market in markets:
            for line in market.lines:
                records = [
                    record
                    for record in predictions
                    if record.market == market.name and record.line == line
                ]
                for contrast in self.contrasts:
                    reasons = self._insufficient_reasons(records)
                    entry: dict[str, object] = {
                        "market": market.name,
                        "line": line,
                        "contrast": contrast.name,
                        "candidate": contrast.candidate,
                        "reference": contrast.reference,
                        "status": "insufficient" if reasons else "tested",
                        "insufficient_reasons": reasons,
                        "n_predictions": len(records),
                        "n_leagues": len({record.league for record in records}),
                        "n_blocks": len({self._block_id(record) for record in records}),
                        "arm_metrics": self._arm_metrics(records),
                        "effects": {},
                    }
                    if not reasons:
                        entry["effects"] = self._bootstrap_effects(
                            records, contrast, "POOLED", market.name, line
                        )
                    output.append(entry)
        return output

    def _insufficient_reasons(self, records: Sequence[_Prediction]) -> list[str]:
        reasons: list[str] = []
        if not records:
            reasons.append("no_walk_forward_predictions")
        elif len(records) < self.config.min_cell_predictions:
            reasons.append(
                f"n_predictions<{self.config.min_cell_predictions}"
            )
        n_blocks = len({self._block_id(record) for record in records})
        if records and n_blocks < self.config.min_bootstrap_blocks:
            reasons.append(f"n_blocks<{self.config.min_bootstrap_blocks}")
        return reasons

    def _block_id(self, record: _Prediction) -> str:
        return (
            record.date_block
            if self.config.bootstrap_block == "date"
            else record.league_week_block
        )

    def _arm_metrics(self, records: Sequence[_Prediction]) -> dict[str, object]:
        if not records:
            return {}
        outcomes = np.asarray([record.outcome for record in records], dtype=float)
        output: dict[str, object] = {}
        for arm in ALL_EVALUATED_ARMS:
            probabilities = np.asarray(
                [record.probabilities[arm] for record in records], dtype=float
            )
            output[arm] = _metrics(
                probabilities, outcomes, bins=self.config.calibration_bins
            )
        return output

    def _bootstrap_effects(
        self,
        records: Sequence[_Prediction],
        contrast: Contrast,
        league: str,
        market: str,
        line: float,
    ) -> dict[str, object]:
        outcomes = np.asarray([record.outcome for record in records], dtype=float)
        candidate = np.asarray(
            [record.probabilities[contrast.candidate] for record in records], dtype=float
        )
        reference = np.asarray(
            [record.probabilities[contrast.reference] for record in records], dtype=float
        )
        groups: dict[str, list[int]] = defaultdict(list)
        for index, record in enumerate(records):
            groups[self._block_id(record)].append(index)
        blocks = [np.asarray(indexes, dtype=int) for _, indexes in sorted(groups.items())]
        seed = _stable_seed(self.config.seed, league, market, line, contrast.name)
        rng = np.random.default_rng(seed)

        point = _metric_effects(candidate, reference, outcomes, self.config.calibration_bins)
        boot: dict[str, list[float]] = {name: [] for name in point}
        for _ in range(self.config.bootstrap_draws):
            selected = rng.integers(0, len(blocks), size=len(blocks))
            indexes = np.concatenate([blocks[int(block_index)] for block_index in selected])
            values = _metric_effects(
                candidate[indexes],
                reference[indexes],
                outcomes[indexes],
                self.config.calibration_bins,
            )
            for name, value in values.items():
                boot[name].append(value)

        output: dict[str, object] = {}
        for name, point_value in point.items():
            values = np.asarray(boot[name], dtype=float)
            low, high = np.quantile(values, [0.025, 0.975])
            standard_error = float(np.std(values, ddof=1))
            if standard_error > 0.0 and math.isfinite(standard_error):
                p_value = float(norm.cdf(-point_value / standard_error))
            else:
                p_value = 0.0 if point_value > 0.0 else 1.0
            output[name] = {
                "point": float(point_value),
                "ci95": [float(low), float(high)],
                "bootstrap_standard_error": standard_error,
                "p_one_sided": p_value,
            }
        return output

    def _apply_bh(self, cells: list[dict[str, object]]) -> int:
        indexed: list[tuple[int, float]] = []
        for index, cell in enumerate(cells):
            if cell["status"] != "tested":
                continue
            effects = cell["effects"]
            p_value = float(effects["brier"]["p_one_sided"])  # type: ignore[index]
            if math.isfinite(p_value):
                indexed.append((index, p_value))
        indexed.sort(key=lambda item: (item[1], item[0]))
        family_size = len(indexed)
        if not indexed:
            return 0

        cutoff = 0
        raw_adjusted: list[float] = []
        for rank, (_, p_value) in enumerate(indexed, 1):
            threshold = self.config.fdr_q * rank / family_size
            if p_value <= threshold:
                cutoff = rank
            raw_adjusted.append(min(1.0, p_value * family_size / rank))
        monotone_q = raw_adjusted[:]
        for index in range(family_size - 2, -1, -1):
            monotone_q[index] = min(monotone_q[index], monotone_q[index + 1])

        for rank, ((cell_index, p_value), q_value) in enumerate(
            zip(indexed, monotone_q), 1
        ):
            cells[cell_index]["fdr"] = {
                "raw_p": p_value,
                "threshold": self.config.fdr_q * rank / family_size,
                "rank": rank,
                "family_size": family_size,
                "reject": rank <= cutoff,
                "q_value": q_value,
            }
        for cell in cells:
            if cell["status"] != "tested":
                cell["fdr"]["family_size"] = family_size  # type: ignore[index]
        return family_size

    def _is_finding(self, cell: Mapping[str, object]) -> bool:
        if cell["status"] != "tested":
            return False
        effect = cell["effects"]["brier"]  # type: ignore[index]
        fdr = cell["fdr"]
        return (
            float(effect["point"]) > 0.0
            and float(effect["ci95"][0]) > 0.0
            and bool(fdr["reject"])
        )

    def _classify(
        self,
        cell: Mapping[str, object],
        pooled: Mapping[str, object],
        *,
        any_league_finding: bool = False,
    ) -> str:
        if cell["status"] != "tested":
            return VERDICT_INSUFFICIENT
        if self._is_finding(cell):
            return VERDICT_FINDING

        pooled_effects = pooled.get("effects") or {}
        pooled_brier = pooled_effects.get("brier")
        pooled_positive = (
            pooled.get("status") == "tested"
            and pooled_brier is not None
            and float(pooled_brier["point"]) > 0.0
            and float(pooled_brier["ci95"][0]) > 0.0
            and float(pooled_brier["p_one_sided"]) <= self.config.alpha
        )
        if pooled_positive and not any_league_finding:
            return VERDICT_ARTIFACT
        return VERDICT_FAILS


def _metrics(probabilities: np.ndarray, outcomes: np.ndarray, bins: int) -> dict[str, float]:
    clipped = np.clip(probabilities, 1e-12, 1.0 - 1e-12)
    return {
        "brier": float(np.mean((probabilities - outcomes) ** 2)),
        "log_loss": float(
            -np.mean(outcomes * np.log(clipped) + (1.0 - outcomes) * np.log(1.0 - clipped))
        ),
        "ece": _ece(probabilities, outcomes, bins),
    }


def _metric_effects(
    candidate: np.ndarray,
    reference: np.ndarray,
    outcomes: np.ndarray,
    bins: int,
) -> dict[str, float]:
    candidate_metrics = _metrics(candidate, outcomes, bins)
    reference_metrics = _metrics(reference, outcomes, bins)
    return {
        name: reference_metrics[name] - candidate_metrics[name]
        for name in ("brier", "log_loss", "ece")
    }


def _ece(probabilities: np.ndarray, outcomes: np.ndarray, bins: int) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(probabilities)
    if total == 0:
        return 0.0
    value = 0.0
    for index in range(bins):
        if index == bins - 1:
            mask = (probabilities >= edges[index]) & (probabilities <= edges[index + 1])
        else:
            mask = (probabilities >= edges[index]) & (probabilities < edges[index + 1])
        count = int(np.sum(mask))
        if count:
            value += count / total * abs(float(np.mean(probabilities[mask]) - np.mean(outcomes[mask])))
    return float(value)


def _stable_seed(base: int, *parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, (base,) + parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _fixture_id(match: Mapping[str, object]) -> str:
    value = match.get("id", match.get("match_id"))
    if value is not None:
        return str(value)
    return "fixture:" + ":".join(
        str(match.get(key, ""))
        for key in ("date_unix", "homeID", "awayID", "competition_id")
    )


def _league_week_block(match: Mapping[str, object], league: str, kickoff: int) -> str:
    season = str(match.get("_season") or match.get("season") or "")
    for key in ("game_week", "gameWeek", "week", "round", "roundID"):
        value = match.get(key)
        if value not in (None, "", -1, "-1"):
            return f"{league}:{season}:provider-week:{value}"
    iso = datetime.fromtimestamp(kickoff, tz=timezone.utc).isocalendar()
    return f"{league}:{season}:iso-week:{iso.year}-{iso.week:02d}"


def _target_value(match: Mapping[str, object], target_field: str) -> float | None:
    if target_field == "total_goals":
        direct = _number(match.get("totalGoalCount"))
        if direct is None:
            direct = _number(match.get("overallGoalCount"))
        if direct is not None:
            return direct
        home = _number(match.get("homeGoalCount"))
        away = _number(match.get("awayGoalCount"))
        return home + away if home is not None and away is not None else None
    if target_field == "total_corners":
        direct = _number(match.get("totalCornerCount"))
        if direct is not None:
            return direct
        home = _number(match.get("team_a_corners"))
        away = _number(match.get("team_b_corners"))
        return home + away if home is not None and away is not None else None
    if target_field == "total_cards":
        home_yellow = _number(match.get("team_a_yellow_cards"))
        away_yellow = _number(match.get("team_b_yellow_cards"))
        if home_yellow is None or away_yellow is None:
            return None
        home_red = _number(match.get("team_a_red_cards")) or 0.0
        away_red = _number(match.get("team_b_red_cards")) or 0.0
        return home_yellow + away_yellow + home_red + away_red
    return _number(match.get(target_field))


def _number(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0.0:
        return None
    return number


def _target_number(value: object) -> float | None:
    return _number(value)


def _integer(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
