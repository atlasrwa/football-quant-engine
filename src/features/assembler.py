"""Feature Assembler: combines all feature calculators into a unified pipeline.

Produces MatchFeatures vectors for each match given historical context.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from src.features.referee_volatility import RefereeVolatilityCalculator
from src.features.rolling_form import RollingFormCalculator
from src.features.xg_efficiency import XGEfficiencyCalculator
from src.models.config import StrategyConfig
from src.models.features import MatchFeatures
from src.models.match import Match

logger = logging.getLogger(__name__)


class FeatureAssembler:
    """Combines xG efficiency, rolling form, and referee volatility into
    a single feature vector per match.

    Processes matches chronologically and respects temporal ordering
    (no look-ahead bias).
    """

    def __init__(self, config: Optional[StrategyConfig] = None) -> None:
        """Initialize with strategy config for calculator parameters.

        Args:
            config: Strategy configuration. Uses defaults if None.
        """
        self._config = config or StrategyConfig()

        self._xg_calc = XGEfficiencyCalculator(
            window=self._config.xg_rolling_window
        )
        self._form_calc = RollingFormCalculator(
            window=self._config.form_rolling_window
        )
        self._ref_calc = RefereeVolatilityCalculator(
            min_matches=self._config.referee_min_matches
        )

    @property
    def config(self) -> StrategyConfig:
        """The strategy configuration used."""
        return self._config

    def assemble(self, matches: List[Match]) -> List[MatchFeatures]:
        """Assemble feature vectors for all matches.

        Matches must be sorted chronologically by date_unix. The assembler
        computes all features in a look-ahead-free manner.

        Args:
            matches: List of Match objects sorted by date_unix.

        Returns:
            List of MatchFeatures sorted chronologically.
            Matches that cannot produce valid features are skipped.
        """
        if not matches:
            return []

        # Sort to guarantee chronological order
        sorted_matches = sorted(matches, key=lambda m: m.date_unix)

        # Compute all feature components
        xg_map = self._xg_calc.compute_rolling_map(sorted_matches)
        form_map = self._form_calc.compute_rolling_map(sorted_matches)
        ref_map = self._ref_calc.compute_index(sorted_matches)

        # Assemble feature vectors
        features: List[MatchFeatures] = []
        skipped = 0

        for match in sorted_matches:
            try:
                home_xg_delta, away_xg_delta = xg_map[match.id]
                home_form, away_form = form_map[match.id]
                ref_volatility = ref_map[match.id]

                feature = MatchFeatures(
                    match_id=match.id,
                    date_unix=match.date_unix,
                    home_xg_eff_delta_rolling=round(home_xg_delta, 6),
                    away_xg_eff_delta_rolling=round(away_xg_delta, 6),
                    home_rolling_form=round(home_form, 6),
                    away_rolling_form=round(away_form, 6),
                    referee_volatility_index=round(ref_volatility, 6),
                    total_goals=match.total_goals,
                    over_under_line=match.over_under_line,
                    over_odds=match.over_odds,
                    under_odds=match.under_odds,
                )
                features.append(feature)

            except (KeyError, ValueError) as e:
                skipped += 1
                logger.warning(
                    "Skipping match %d during assembly: %s", match.id, e
                )

        # Log completeness stats
        total = len(sorted_matches)
        assembled = len(features)
        completeness = (assembled / total * 100) if total > 0 else 0.0
        logger.info(
            "Feature assembly: %d/%d matches (%.1f%% complete, %d skipped)",
            assembled, total, completeness, skipped,
        )

        return features

    def assemble_single(
        self,
        match: Match,
        history: List[Match],
    ) -> MatchFeatures:
        """Assemble features for a single match given its historical context.

        The match is appended to the history and features are computed for
        it in context. This is useful for real-time or streaming scenarios.

        Args:
            match: The target match to compute features for.
            history: Prior matches providing context (sorted chronologically).

        Returns:
            MatchFeatures for the target match.

        Raises:
            ValueError: If features cannot be computed for the match.
        """
        # Combine history + target, ensuring target is last
        all_matches = sorted(
            history + [match], key=lambda m: m.date_unix
        )

        # Compute all features
        features = self.assemble(all_matches)

        # Find our target match in the results
        for f in features:
            if f.match_id == match.id:
                return f

        raise ValueError(
            f"Could not compute features for match {match.id}"
        )
