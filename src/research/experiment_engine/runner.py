"""Experiment Runner — executes controlled historical experiments.

The runner takes:
- ExperimentConfig (what to test)
- ResearchDataset (data to test against)

And produces:
- ExperimentResult (complete evidence)

Key guarantees:
1. Temporal causality — no future information leaks
2. Reproducibility — same config + data = same result
3. Explicit failures — never converts errors to zeros
4. Separation of concerns — predictive vs economic metrics
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from scipy import stats as sp_stats

from src.research.calibration import CalibrationEvaluator
from src.research.ev_calculator import EVCalculator, probability_to_fair_odds
from src.research.experiment_engine.config import ExperimentConfig, OddsMode
from src.research.experiment_engine.dataset import ResearchDataset
from src.research.experiment_engine.hypothesis import ExperimentHypothesis
from src.research.experiment_engine.result import (
    BaselineComparison,
    EconomicMetrics,
    EVStatus,
    EvidenceClassification,
    EvidenceClassifier,
    ExperimentPrediction,
    ExperimentResult,
    ExperimentResultStatus,
    ObservationCounts,
    PredictiveMetrics,
    StatisticalEvidence,
)
from src.research.experiment_engine.temporal import SplitType, TemporalSplit, TemporalSplitFactory
from src.research.market import MarketCategory, MarketDirection, MarketOutcome, ResearchMarket
from src.research.probability import (
    HistoricalFrequencyModel,
    LogisticRegressionModel,
    PoissonModel,
    ProbabilityModel,
)


class ExperimentRunner:
    """Executes a controlled research experiment.

    Protocol:
    1. Validate configuration
    2. Apply temporal split to dataset
    3. Evaluate candidate conditions on training data
    4. Build training outcomes
    5. Fit model on training data ONLY
    6. Generate probabilities for evaluation data
    7. Compare with actual outcomes
    8. Calculate metrics (predictive + economic)
    9. Generate statistical evidence
    10. Classify result

    The runner never modifies the dataset or model in place.
    """

    def __init__(self, classifier: Optional[EvidenceClassifier] = None) -> None:
        """Initialize runner.

        Args:
            classifier: Evidence classifier (uses defaults if None).
        """
        self._classifier = classifier or EvidenceClassifier()
        self._calibration_evaluator = CalibrationEvaluator(n_bins=10, min_samples=10)

    def run(
        self,
        config: ExperimentConfig,
        dataset: ResearchDataset,
        model: ProbabilityModel,
    ) -> ExperimentResult:
        """Execute a complete experiment.

        Args:
            config: Experiment configuration.
            dataset: Prepared research dataset.
            model: Probability model instance (will be fitted internally).

        Returns:
            ExperimentResult with complete evidence.
        """
        # Step 1: Validate configuration
        is_valid, reason = config.validate()
        if not is_valid:
            return self._failure_result(
                config, ExperimentResultStatus.INVALID_CONFIGURATION, reason
            )

        hypothesis = config.hypothesis
        assert hypothesis is not None  # validated above

        # Step 2: Apply temporal split
        split = TemporalSplitFactory.from_timestamps(
            train_start=config.training_start,
            train_end=config.training_end,
            test_start=config.evaluation_start,
            test_end=config.evaluation_end,
        )
        valid, msg = split.validate()
        if not valid:
            return self._failure_result(
                config, ExperimentResultStatus.TEMPORAL_VIOLATION, msg
            )

        split_data = dataset.apply_split(split)
        train_data = split_data[SplitType.TRAIN]
        test_data = split_data[SplitType.TEST]

        # Step 3: Check minimum observations
        if len(train_data) < config.minimum_observations:
            return self._failure_result(
                config,
                ExperimentResultStatus.INSUFFICIENT_DATA,
                f"Training data has {len(train_data)} matches, "
                f"need {config.minimum_observations}",
            )
        if len(test_data) < 1:
            return self._failure_result(
                config,
                ExperimentResultStatus.INSUFFICIENT_DATA,
                "No test data available in evaluation period",
            )

        # Step 4: Build training features and outcomes
        market = dataset.market
        train_features, train_outcomes, train_counts = self._prepare_training_data(
            train_data, hypothesis, market
        )

        if len(train_features) < config.minimum_observations:
            return self._failure_result(
                config,
                ExperimentResultStatus.INSUFFICIENT_DATA,
                f"Only {len(train_features)} eligible training observations "
                f"(need {config.minimum_observations})",
            )

        # Step 5: Fit model on training data ONLY
        try:
            model.fit(train_features, train_outcomes)
        except Exception as e:
            return self._failure_result(
                config, ExperimentResultStatus.MODEL_FAILURE, str(e)
            )

        if not model.is_fitted:
            return self._failure_result(
                config,
                ExperimentResultStatus.MODEL_FAILURE,
                "Model failed to fit (is_fitted=False after fit())",
            )

        # Step 6: Generate predictions for evaluation data
        predictions, eval_counts = self._evaluate_test_data(
            test_data, hypothesis, market, model, config
        )

        # Merge counts
        total_counts = ObservationCounts(
            total_rows=len(train_data) + len(test_data),
            eligible_rows=eval_counts.eligible_rows,
            missing_rows=train_counts.missing_rows + eval_counts.missing_rows,
            invalid_rows=train_counts.invalid_rows + eval_counts.invalid_rows,
            insufficient_history_rows=(
                train_counts.insufficient_history_rows
                + eval_counts.insufficient_history_rows
            ),
            excluded_odds_filter=eval_counts.excluded_odds_filter,
        )

        if len(predictions) == 0:
            return self._failure_result(
                config,
                ExperimentResultStatus.INSUFFICIENT_DATA,
                "No valid predictions generated in evaluation period",
                observation_counts=total_counts,
            )

        # Step 7: Compute metrics
        predictive_metrics = self._compute_predictive_metrics(predictions)
        economic_metrics = self._compute_economic_metrics(predictions, config)
        baseline = self._compute_baseline(train_data, test_data, predictions, market, hypothesis)
        evidence = self._compute_statistical_evidence(predictions, baseline, config)

        # Step 8: Classify
        classification = self._classifier.classify(evidence, predictive_metrics)

        # Step 9: Build warnings and limitations
        warnings = self._generate_warnings(predictions, config, total_counts)
        limitations = self._generate_limitations(config, total_counts)

        return ExperimentResult(
            experiment_id=config.experiment_id,
            candidate_hash=hypothesis.candidate_hash,
            hypothesis_hash=hypothesis.content_hash,
            market_type=config.market_type,
            dataset_version=config.dataset_version,
            model_identity=f"{config.model_type}",
            training_period=(config.training_start, config.training_end),
            evaluation_period=(config.evaluation_start, config.evaluation_end),
            observation_counts=total_counts,
            predictions=tuple(predictions),
            predictive_metrics=predictive_metrics,
            economic_metrics=economic_metrics,
            baseline_comparison=baseline,
            statistical_evidence=evidence,
            classification=classification,
            status=ExperimentResultStatus.COMPLETED,
            warnings=tuple(warnings),
            limitations=tuple(limitations),
        )

    def _prepare_training_data(
        self,
        train_data: list[dict[str, Any]],
        hypothesis: ExperimentHypothesis,
        market: ResearchMarket,
    ) -> tuple[list[dict[str, float]], list[bool], ObservationCounts]:
        """Prepare training features and outcomes.

        For training, we use ALL matches (not conditioned on hypothesis)
        to give the model maximum information.

        Returns:
            (features, outcomes, observation_counts)
        """
        features: list[dict[str, float]] = []
        outcomes: list[bool] = []
        missing = 0
        invalid = 0

        for d in train_data:
            # Resolve outcome based on market category
            if market.is_over_under:
                # Over/Under: requires numeric target and line
                target_val = d.get(market.target_field)
                if target_val is None:
                    missing += 1
                    continue
                try:
                    target_float = float(target_val)
                except (TypeError, ValueError):
                    invalid += 1
                    continue
                outcome = market.resolve_outcome(target_float)
                if outcome is None:
                    # Push — exclude from training
                    invalid += 1
                    continue
                outcomes.append(outcome == MarketDirection.OVER)
            elif market.is_yes_no or market.is_three_way:
                # YES_NO (BTTS) and THREE_WAY (1X2): use general resolution
                gen_outcome = market.resolve_outcome_general(d)
                if gen_outcome is None:
                    missing += 1
                    continue
                # Encode based on hypothesis direction
                outcomes.append(gen_outcome.value == hypothesis.direction)
            else:
                missing += 1
                continue

            # Build feature dict from available numeric fields
            feat = self._extract_features(d, hypothesis.feature_ids)
            features.append(feat)

        counts = ObservationCounts(
            total_rows=len(train_data),
            eligible_rows=len(features),
            missing_rows=missing,
            invalid_rows=invalid,
            insufficient_history_rows=0,
        )
        return features, outcomes, counts

    def _evaluate_test_data(
        self,
        test_data: list[dict[str, Any]],
        hypothesis: ExperimentHypothesis,
        market: ResearchMarket,
        model: ProbabilityModel,
        config: ExperimentConfig,
    ) -> tuple[list[ExperimentPrediction], ObservationCounts]:
        """Generate predictions for test data.

        Two-phase architecture:
        1. Hypothesis layer: evaluate conditions + generate model probabilities
        2. Market layer: attach odds, compute EV, apply filters

        Only generates predictions where hypothesis conditions are met.
        """
        # Phase 1: Hypothesis layer — probabilities only, no odds
        raw_predictions, hyp_counts = self._generate_hypothesis_predictions(
            test_data, hypothesis, market, model
        )

        # Phase 2: Market layer — attach odds and compute EV
        predictions = self._apply_market_layer_to_predictions(
            raw_predictions, test_data, hypothesis, market, config
        )

        # Merge counts (market layer may exclude additional rows via odds filter)
        excluded_odds = sum(
            1 for p in predictions if p.ev_status == EVStatus.INVALID_ODDS
        )
        counts = ObservationCounts(
            total_rows=hyp_counts.total_rows,
            eligible_rows=hyp_counts.eligible_rows,
            missing_rows=hyp_counts.missing_rows,
            invalid_rows=hyp_counts.invalid_rows,
            insufficient_history_rows=hyp_counts.insufficient_history_rows,
            excluded_odds_filter=excluded_odds,
        )
        return predictions, counts

    def _generate_hypothesis_predictions(
        self,
        test_data: list[dict[str, Any]],
        hypothesis: ExperimentHypothesis,
        market: ResearchMarket,
        model: ProbabilityModel,
    ) -> tuple[list[dict[str, Any]], ObservationCounts]:
        """HYPOTHESIS LAYER: Generate probability predictions from model.

        This method ONLY:
        - Evaluates hypothesis conditions against features
        - Resolves actual outcomes from market definition
        - Runs the probability model to get P(outcome | features)

        It NEVER reads odds fields, computes EV, fair odds, or implied probability.

        Returns:
            Tuple of (raw_prediction_dicts, observation_counts).
            Each dict has: match_id, date_unix, model_probability, actual_outcome,
            is_hit, direction, conditions_met, data_index.
        """
        raw_predictions: list[dict[str, Any]] = []
        missing = 0
        invalid = 0
        insufficient_history = 0
        eligible = 0

        for idx, d in enumerate(test_data):
            match_id = d.get("match_id", 0)
            date_unix = d.get("date_unix", 0)

            # Extract features
            feat = self._extract_features(d, hypothesis.feature_ids)

            # Evaluate conditions
            conditions_result = hypothesis.evaluate_conditions(feat)
            if conditions_result is None:
                # Missing feature data
                missing += 1
                continue
            if not conditions_result:
                # Conditions not met — this match is not a prediction target
                continue

            # Resolve actual outcome based on market category
            if market.is_over_under:
                target_val = d.get(market.target_field)
                if target_val is None:
                    missing += 1
                    continue
                try:
                    target_float = float(target_val)
                except (TypeError, ValueError):
                    invalid += 1
                    continue
                actual_outcome_obj = market.resolve_outcome(target_float)
                if actual_outcome_obj is None:
                    # Push
                    invalid += 1
                    continue
                actual_outcome = actual_outcome_obj.value
                is_hit = actual_outcome == hypothesis.direction
            elif market.is_yes_no or market.is_three_way:
                gen_outcome = market.resolve_outcome_general(d)
                if gen_outcome is None:
                    missing += 1
                    continue
                actual_outcome = gen_outcome.value
                is_hit = actual_outcome == hypothesis.direction
            else:
                invalid += 1
                continue

            # Get model probability
            try:
                estimate = model.predict(feat)
                if hypothesis.direction in ("OVER", "YES", "HOME"):
                    model_prob = estimate.p_over
                else:
                    model_prob = estimate.p_under
            except Exception:
                invalid += 1
                continue

            eligible += 1

            raw_predictions.append({
                "data_index": idx,
                "match_id": match_id,
                "date_unix": date_unix,
                "model_probability": model_prob,
                "actual_outcome": actual_outcome,
                "is_hit": is_hit,
                "direction": hypothesis.direction,
            })

        counts = ObservationCounts(
            total_rows=len(test_data),
            eligible_rows=eligible,
            missing_rows=missing,
            invalid_rows=invalid,
            insufficient_history_rows=insufficient_history,
        )
        return raw_predictions, counts

    def _apply_market_layer_to_predictions(
        self,
        raw_predictions: list[dict[str, Any]],
        test_data: list[dict[str, Any]],
        hypothesis: ExperimentHypothesis,
        market: ResearchMarket,
        config: ExperimentConfig,
    ) -> list[ExperimentPrediction]:
        """MARKET LAYER: Attach odds and compute EV for hypothesis predictions.

        This method ONLY:
        - Reads market odds from match data
        - Computes implied probability, fair odds, and expected value
        - Applies odds filters

        It NEVER evaluates hypothesis conditions or runs the probability model.

        Args:
            raw_predictions: Output from _generate_hypothesis_predictions.
            test_data: Original test match dicts (for odds lookup).
            hypothesis: Hypothesis (for direction).
            market: Market definition (for odds field names).
            config: Experiment config (for odds mode and thresholds).

        Returns:
            List of ExperimentPrediction with full market data attached.
        """
        predictions: list[ExperimentPrediction] = []
        thresholds = config.thresholds

        for pred in raw_predictions:
            idx = pred["data_index"]
            d = test_data[idx]

            # Default: no market data
            ev_status = EVStatus.MISSING_ODDS
            market_odds: Optional[float] = None
            fair_odds: Optional[float] = None
            implied_prob: Optional[float] = None
            expected_value: Optional[float] = None

            if config.odds_mode != OddsMode.NO_ODDS:
                over_odds = d.get(market.odds_over_field)
                under_odds = d.get(market.odds_under_field)

                if over_odds is not None and under_odds is not None:
                    try:
                        over_odds_f = float(over_odds)
                        under_odds_f = float(under_odds)
                    except (TypeError, ValueError):
                        over_odds_f = None
                        under_odds_f = None

                    if over_odds_f is not None and under_odds_f is not None:
                        # Select odds for our direction
                        if hypothesis.direction in ("OVER", "YES", "HOME"):
                            chosen_odds = over_odds_f
                        else:
                            chosen_odds = under_odds_f

                        # Apply odds filter
                        if chosen_odds < thresholds.min_odds or chosen_odds > thresholds.max_odds:
                            # Still record prediction but without EV
                            ev_status = EVStatus.INVALID_ODDS
                        else:
                            market_odds = chosen_odds
                            implied_prob = 1.0 / chosen_odds if chosen_odds > 0 else None
                            fair_odds_val = probability_to_fair_odds(pred["model_probability"])
                            fair_odds = fair_odds_val
                            expected_value = pred["model_probability"] * chosen_odds - 1.0
                            ev_status = EVStatus.VALID

            predictions.append(ExperimentPrediction(
                match_id=pred["match_id"],
                prediction_timestamp=pred["date_unix"],
                information_timestamp=pred["date_unix"],
                outcome_timestamp=pred["date_unix"],  # post-match
                model_probability=pred["model_probability"],
                actual_outcome=pred["actual_outcome"],
                is_hit=pred["is_hit"],
                market_odds=market_odds,
                fair_odds=fair_odds,
                implied_probability=implied_prob,
                expected_value=expected_value,
                ev_status=ev_status,
                direction=pred["direction"],
                conditions_met=True,
            ))

        return predictions

    def _extract_features(
        self, match_dict: dict[str, Any], feature_ids: tuple[str, ...]
    ) -> dict[str, float]:
        """Extract numeric features from a match dict.

        Preserves None/missing — does NOT replace with 0.
        """
        feat: dict[str, float] = {}
        for key, val in match_dict.items():
            if isinstance(val, (int, float)) and val is not None:
                feat[key] = float(val)
        return feat

    def _compute_predictive_metrics(
        self, predictions: list[ExperimentPrediction]
    ) -> PredictiveMetrics:
        """Compute predictive quality metrics."""
        n = len(predictions)
        if n == 0:
            return PredictiveMetrics(sample_size=0)

        hits = [p for p in predictions if p.is_hit]
        hit_rate = len(hits) / n

        probs = [p.model_probability for p in predictions]
        actuals = [p.is_hit for p in predictions]
        model_prob_mean = float(np.mean(probs))
        actual_freq = float(np.mean([1.0 if a else 0.0 for a in actuals]))

        # Calibration via Batch 2 evaluator
        cal_result = self._calibration_evaluator.evaluate(
            probs, [bool(a) for a in actuals]
        )

        return PredictiveMetrics(
            sample_size=n,
            hit_rate=hit_rate,
            model_probability_mean=model_prob_mean,
            actual_frequency=actual_freq,
            brier_score=cal_result.brier_score,
            log_loss=cal_result.log_loss,
            ece=cal_result.ece,
            mce=cal_result.mce,
        )

    def _compute_economic_metrics(
        self, predictions: list[ExperimentPrediction], config: ExperimentConfig
    ) -> EconomicMetrics:
        """Compute economic metrics (only where odds available)."""
        if config.odds_mode == OddsMode.NO_ODDS:
            return EconomicMetrics(odds_available=False)

        ev_predictions = [
            p for p in predictions if p.ev_status == EVStatus.VALID
        ]

        if not ev_predictions:
            return EconomicMetrics(odds_available=False)

        evs = [p.expected_value for p in ev_predictions]
        odds = [p.market_odds for p in ev_predictions]

        # Simulate unit-stake betting
        profits: list[float] = []
        for p in ev_predictions:
            if p.is_hit:
                profits.append(p.market_odds - 1.0)
            else:
                profits.append(-1.0)

        total_pnl = sum(profits)
        n_bets = len(profits)
        roi_pct = (total_pnl / n_bets) * 100.0 if n_bets > 0 else 0.0

        # Max drawdown
        if profits:
            cumulative = np.cumsum(profits)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = running_max - cumulative
            max_dd = float(np.max(drawdowns))
        else:
            max_dd = 0.0

        positive_ev = [e for e in evs if e > 0]

        return EconomicMetrics(
            odds_available=True,
            mean_ev=float(np.mean(evs)),
            median_ev=float(np.median(evs)),
            positive_ev_rate=len(positive_ev) / len(evs) if evs else 0.0,
            mean_odds=float(np.mean(odds)),
            roi_pct=roi_pct,
            yield_pct=roi_pct,  # same as ROI for unit stakes
            number_of_bets=n_bets,
            total_profit_loss=total_pnl,
            max_drawdown=max_dd,
        )

    def _compute_baseline(
        self,
        train_data: list[dict[str, Any]],
        test_data: list[dict[str, Any]],
        predictions: list[ExperimentPrediction],
        market: ResearchMarket,
        hypothesis: ExperimentHypothesis,
    ) -> BaselineComparison:
        """Compute baseline comparison.

        Baseline: historical base rate from training data.
        Compares: does the candidate condition improve over
        the unconditional base rate?
        """
        # Compute baseline from training data
        baseline_hits = 0
        baseline_total = 0

        for d in train_data:
            if market.is_over_under:
                target_val = d.get(market.target_field)
                if target_val is None:
                    continue
                try:
                    target_float = float(target_val)
                except (TypeError, ValueError):
                    continue
                outcome = market.resolve_outcome(target_float)
                if outcome is None:
                    continue
                if outcome.value == hypothesis.direction:
                    baseline_hits += 1
                baseline_total += 1
            elif market.is_yes_no or market.is_three_way:
                gen_outcome = market.resolve_outcome_general(d)
                if gen_outcome is None:
                    continue
                if gen_outcome.value == hypothesis.direction:
                    baseline_hits += 1
                baseline_total += 1

        if baseline_total == 0 or not predictions:
            return BaselineComparison(baseline_name="historical_base_rate")

        baseline_freq = baseline_hits / baseline_total
        candidate_freq = sum(1 for p in predictions if p.is_hit) / len(predictions)
        improvement = candidate_freq - baseline_freq

        # Brier scores for comparison
        # Baseline Brier: predicting baseline_freq for every test match
        actuals = [1.0 if p.is_hit else 0.0 for p in predictions]
        baseline_brier = float(np.mean([(baseline_freq - a) ** 2 for a in actuals]))
        candidate_brier = float(
            np.mean([(p.model_probability - a) ** 2 for p, a in zip(predictions, actuals)])
        )

        return BaselineComparison(
            baseline_name="historical_base_rate",
            baseline_frequency=baseline_freq,
            candidate_frequency=candidate_freq,
            improvement=improvement,
            baseline_brier=baseline_brier,
            candidate_brier=candidate_brier,
            brier_improvement=baseline_brier - candidate_brier,
        )

    def _compute_statistical_evidence(
        self,
        predictions: list[ExperimentPrediction],
        baseline: BaselineComparison,
        config: ExperimentConfig,
    ) -> StatisticalEvidence:
        """Compute statistical evidence.

        Tests whether the candidate's hit rate significantly differs
        from the baseline rate.
        """
        n = len(predictions)
        if n < 2:
            return StatisticalEvidence(sample_size=n)

        hits = [1.0 if p.is_hit else 0.0 for p in predictions]
        mean_outcome = float(np.mean(hits))
        baseline_outcome = baseline.baseline_frequency

        if baseline_outcome is None:
            return StatisticalEvidence(
                sample_size=n,
                mean_outcome=mean_outcome,
            )

        difference = mean_outcome - baseline_outcome

        # Confidence interval for the difference (normal approximation)
        se = float(np.sqrt(mean_outcome * (1 - mean_outcome) / n))
        ci_lower = difference - 1.96 * se
        ci_upper = difference + 1.96 * se

        # Effect size (Cohen's h for proportions)
        # h = 2 * arcsin(sqrt(p1)) - 2 * arcsin(sqrt(p2))
        effect_size = abs(
            2 * math.asin(math.sqrt(max(0, min(1, mean_outcome))))
            - 2 * math.asin(math.sqrt(max(0, min(1, baseline_outcome))))
        )

        # One-sample proportion test against baseline
        # H0: p = baseline, H1: p > baseline (one-tailed)
        if baseline_outcome > 0 and baseline_outcome < 1:
            se_null = math.sqrt(baseline_outcome * (1 - baseline_outcome) / n)
            if se_null > 0:
                z_stat = difference / se_null
                p_value = float(1 - sp_stats.norm.cdf(z_stat))
            else:
                p_value = 1.0
        else:
            p_value = 1.0

        is_significant = p_value < config.thresholds.significance_level

        return StatisticalEvidence(
            sample_size=n,
            mean_outcome=mean_outcome,
            baseline_outcome=baseline_outcome,
            difference=difference,
            confidence_interval_lower=ci_lower,
            confidence_interval_upper=ci_upper,
            effect_size=effect_size,
            p_value=p_value,
            is_significant=is_significant,
            significance_level=config.thresholds.significance_level,
        )

    def _generate_warnings(
        self,
        predictions: list[ExperimentPrediction],
        config: ExperimentConfig,
        counts: ObservationCounts,
    ) -> list[str]:
        """Generate warnings about the experiment."""
        warnings = []

        if counts.missing_rows > counts.total_rows * 0.2:
            warnings.append(
                f"High missing data rate: {counts.missing_rows}/{counts.total_rows} "
                f"({counts.missing_rows / counts.total_rows * 100:.1f}%)"
            )

        if len(predictions) < 50:
            warnings.append(
                f"Small evaluation sample ({len(predictions)} predictions). "
                "Results may be unstable."
            )

        no_odds = [p for p in predictions if p.ev_status == EVStatus.MISSING_ODDS]
        if no_odds and config.odds_mode != OddsMode.NO_ODDS:
            warnings.append(
                f"{len(no_odds)}/{len(predictions)} predictions missing odds"
            )

        return warnings

    def _generate_limitations(
        self, config: ExperimentConfig, counts: ObservationCounts
    ) -> list[str]:
        """Document known limitations."""
        limitations = []

        if config.odds_mode == OddsMode.SYNTHETIC_ODDS:
            limitations.append(
                "Uses synthetic odds — do NOT make profitability claims"
            )
        elif config.odds_mode == OddsMode.NO_ODDS:
            limitations.append("No odds available — EV not calculated")

        limitations.append("Single temporal split — not walk-forward validated")
        limitations.append("No FDR correction applied")
        limitations.append("Research evidence only — not production approval")

        return limitations

    def _failure_result(
        self,
        config: ExperimentConfig,
        status: ExperimentResultStatus,
        reason: str,
        observation_counts: Optional[ObservationCounts] = None,
    ) -> ExperimentResult:
        """Create a failure result."""
        hypothesis = config.hypothesis
        return ExperimentResult(
            experiment_id=config.experiment_id,
            candidate_hash=hypothesis.candidate_hash if hypothesis else "",
            hypothesis_hash=hypothesis.content_hash if hypothesis else "",
            market_type=config.market_type,
            dataset_version=config.dataset_version,
            model_identity=config.model_type,
            training_period=(config.training_start or 0, config.training_end or 0),
            evaluation_period=(config.evaluation_start or 0, config.evaluation_end or 0),
            observation_counts=observation_counts or ObservationCounts(),
            status=status,
            warnings=(reason,),
            limitations=(
                "Experiment did not complete — no evidence produced",
            ),
        )
