"""Dixon-Coles bivariate Poisson model for football goal prediction.

Implements the Dixon & Coles (1997) model which models home and away goals
as correlated Poisson processes with:
- Per-team attack strength (alpha_i)
- Per-team defense strength (beta_i)
- Home advantage parameter (gamma)
- Low-score correlation correction (rho) for 0-0, 1-0, 0-1, 1-1 scorelines

This is the standard sharp-bettor baseline for goal markets. It respects
that football scores are low-count, correlated data — not a generic
regression target.

Reference: Dixon, M.J. & Coles, S.G. (1997) "Modelling Association Football
Scores and Inefficiencies in the Football Betting Market"

Key properties:
- Team strengths fitted via MLE on expanding window (look-ahead-free)
- Time-decay weighting (recent matches weighted more heavily)
- Correlation correction for low scores (rho parameter)
- Produces full scoreline distribution, from which O/U at any line is derived
- Implements ProbabilityModel ABC for integration with research pipeline
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson

from src.research.probability import (
    ModelIdentity,
    PredictionResult,
    PredictionStatus,
    ProbabilityEstimate,
    ProbabilityModel,
    TrainingMetadata,
)


# ═══════════════════════════════════════════════════════════════
# DIXON-COLES MODEL
# ═══════════════════════════════════════════════════════════════


@dataclass
class TeamStrength:
    """Attack and defense strength for a single team."""

    attack: float = 0.0
    defense: float = 0.0


@dataclass(frozen=True, slots=True)
class DixonColesParams:
    """Fitted Dixon-Coles model parameters."""

    team_attack: dict[str, float]
    team_defense: dict[str, float]
    home_advantage: float
    rho: float  # Low-score correlation correction
    n_teams: int
    n_matches: int


class DixonColesModel(ProbabilityModel):
    """Dixon-Coles bivariate Poisson model for goal prediction.

    Models home goals ~ Poisson(lambda_home) and away goals ~ Poisson(lambda_away)
    where:
        lambda_home = alpha_home * beta_away * gamma
        lambda_away = alpha_away * beta_home

    With a correlation correction (tau/rho) for scorelines 0-0, 1-0, 0-1, 1-1.

    Produces P(total_goals > line) for over/under markets at any line.

    Parameters:
        line: The over/under line (default 2.5 for standard goals O/U).
        time_decay: Exponential decay half-life in days (default 365).
            Matches older than this get exponentially less weight.
        min_team_matches: Minimum matches a team must have before getting
            individual parameters (otherwise uses league average).
        max_goals: Maximum goal count per side for probability grid (default 10).
        shrinkage_factor: Controls strength of empirical Bayes shrinkage toward
            league-average team strength. Higher = more regularization. The
            effective penalty per team is shrinkage_factor / team_match_count,
            so teams with fewer matches are shrunk harder toward the mean.
            Set to 0 to disable shrinkage (original MLE behavior).
        prior_params: Optional DixonColesParams from a prior season. When
            provided, teams that exist in both seasons are shrunk toward their
            prior-season strength instead of the cross-sectional mean. New
            teams (promoted) still shrink toward the league average.
    """

    def __init__(
        self,
        line: float = 2.5,
        time_decay_days: float = 365.0,
        min_team_matches: int = 3,
        max_goals: int = 10,
        shrinkage_factor: float = 12.0,
        prior_params: Optional["DixonColesParams"] = None,
    ) -> None:
        self._line = line
        self._time_decay_days = time_decay_days
        self._min_team_matches = min_team_matches
        self._max_goals = max_goals
        self._shrinkage_factor = shrinkage_factor
        self._prior_params = prior_params

        # Fitted state
        self._params: Optional[DixonColesParams] = None
        self._fitted = False
        self._training_metadata: Optional[TrainingMetadata] = None
        self._team_match_counts: dict[str, int] = {}

    @property
    def name(self) -> str:
        return "dixon_coles"

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def training_metadata(self) -> Optional[TrainingMetadata]:
        return self._training_metadata

    @property
    def params(self) -> Optional[DixonColesParams]:
        """Fitted parameters (None if not fitted)."""
        return self._params

    def _get_parameters(self) -> dict[str, Any]:
        return {
            "line": self._line,
            "time_decay_days": self._time_decay_days,
            "min_team_matches": self._min_team_matches,
            "max_goals": self._max_goals,
            "shrinkage_factor": self._shrinkage_factor,
            "has_prior": self._prior_params is not None,
        }

    def fit(
        self,
        features: list[dict[str, float]],
        outcomes: list[bool],
        training_start: Optional[int] = None,
        training_end: Optional[int] = None,
    ) -> None:
        """Fit Dixon-Coles model on match data.

        Extracts home_team, away_team, home_goals, away_goals from features.
        The `outcomes` parameter (bool) is accepted for interface compatibility
        but the model uses actual goal counts for fitting.

        Required keys in each feature dict:
        - home_team (or home_team_id): team identifier (stored as string)
        - away_team (or away_team_id): team identifier
        - home_goals: integer goals scored by home team
        - away_goals: integer goals scored by away team
        - date_unix: match timestamp (for time decay weighting)
        """
        if not features:
            self._fitted = True
            self._params = None
            return

        # Extract match data
        matches = self._extract_match_data(features)
        if len(matches) < 10:
            # Too few matches — fall back to simple Poisson
            self._fit_simple_poisson(matches)
            return

        # Count team appearances
        self._team_match_counts = defaultdict(int)
        for m in matches:
            self._team_match_counts[m["home_team"]] += 1
            self._team_match_counts[m["away_team"]] += 1

        # Get all teams with enough matches
        all_teams = sorted(set(
            t for t, c in self._team_match_counts.items()
            if c >= self._min_team_matches
        ))

        if len(all_teams) < 4:
            self._fit_simple_poisson(matches)
            return

        # Compute time-decay weights
        if training_end is not None:
            ref_time = training_end
        else:
            ref_time = max(m["date_unix"] for m in matches)

        decay_rate = math.log(2) / (self._time_decay_days * 86400)
        weights = []
        for m in matches:
            age_seconds = ref_time - m["date_unix"]
            w = math.exp(-decay_rate * max(0, age_seconds))
            weights.append(w)

        # MLE optimization
        self._fit_mle(matches, all_teams, weights)

        # Record training metadata
        if training_start is not None and training_end is not None:
            self._training_metadata = TrainingMetadata(
                training_start=training_start,
                training_end=training_end,
                sample_size=len(matches),
                feature_names=("home_team", "away_team", "home_goals", "away_goals"),
            )

        self._fitted = True

    def predict(self, features: dict[str, float]) -> ProbabilityEstimate:
        """Predict P(over) and P(under) for the configured line.

        Requires home_team and away_team in features.
        Uses fitted team strengths to compute expected goals,
        then integrates over the scoreline grid.
        """
        if self._params is None:
            return ProbabilityEstimate(p_over=0.5, p_under=0.5, model_name=self.name)

        home_team = self._get_team_id(features, "home")
        away_team = self._get_team_id(features, "away")

        # Get expected goals (lambda)
        lambda_home, lambda_away = self._get_expected_goals(home_team, away_team)

        # Compute full scoreline probability grid
        p_over, p_under = self._compute_over_under(lambda_home, lambda_away, self._line)

        # Clip to avoid extreme values
        p_over = max(0.01, min(0.99, p_over))
        p_under = 1.0 - p_over

        return ProbabilityEstimate(
            p_over=p_over,
            p_under=p_under,
            model_name=self.name,
        )

    def predict_scoreline(
        self, features: dict[str, float]
    ) -> np.ndarray:
        """Return full scoreline probability matrix P(home=i, away=j).

        Shape: (max_goals+1, max_goals+1).
        Includes Dixon-Coles correlation correction for low scores.
        """
        if self._params is None:
            # Uniform-ish fallback
            n = self._max_goals + 1
            grid = np.ones((n, n)) / (n * n)
            return grid

        home_team = self._get_team_id(features, "home")
        away_team = self._get_team_id(features, "away")
        lambda_home, lambda_away = self._get_expected_goals(home_team, away_team)

        return self._scoreline_grid(lambda_home, lambda_away)

    def predict_match_probabilities(
        self, features: dict[str, float]
    ) -> tuple[float, float, float]:
        """Return P(home_win), P(draw), P(away_win) from scoreline grid.

        Useful for 1X2 markets and as input to derived models.
        """
        grid = self.predict_scoreline(features)
        n = grid.shape[0]

        p_home = 0.0
        p_draw = 0.0
        p_away = 0.0

        for i in range(n):
            for j in range(n):
                if i > j:
                    p_home += grid[i, j]
                elif i == j:
                    p_draw += grid[i, j]
                else:
                    p_away += grid[i, j]

        return p_home, p_draw, p_away

    def predict_over_under(
        self, features: dict[str, float], line: float
    ) -> tuple[float, float]:
        """Predict P(over) and P(under) for an arbitrary line.

        Unlike predict() which uses the configured line, this allows
        any line to be evaluated from the same fitted model.
        """
        if self._params is None:
            return 0.5, 0.5

        home_team = self._get_team_id(features, "home")
        away_team = self._get_team_id(features, "away")
        lambda_home, lambda_away = self._get_expected_goals(home_team, away_team)

        return self._compute_over_under(lambda_home, lambda_away, line)

    def get_expected_goals(self, features: dict[str, float]) -> tuple[float, float]:
        """Return (expected_home_goals, expected_away_goals) for a match.

        Useful for downstream models (BTTS, clean sheet) that need
        the underlying Poisson rates.
        """
        if self._params is None:
            return 1.3, 1.1  # League average fallback

        home_team = self._get_team_id(features, "home")
        away_team = self._get_team_id(features, "away")
        return self._get_expected_goals(home_team, away_team)

    # ──────────────────────────────────────────────────────────
    # Internal: MLE fitting
    # ──────────────────────────────────────────────────────────

    def _extract_match_data(self, features: list[dict[str, float]]) -> list[dict[str, Any]]:
        """Extract structured match data from feature dicts."""
        matches = []
        for feat in features:
            home_goals = feat.get("home_goals")
            away_goals = feat.get("away_goals")
            if home_goals is None or away_goals is None:
                continue

            home_team = self._get_team_id(feat, "home")
            away_team = self._get_team_id(feat, "away")
            if home_team is None or away_team is None:
                continue

            matches.append({
                "home_team": home_team,
                "away_team": away_team,
                "home_goals": int(home_goals),
                "away_goals": int(away_goals),
                "date_unix": int(feat.get("date_unix", 0)),
            })
        return matches

    def _get_team_id(self, features: dict[str, float], side: str) -> Optional[str]:
        """Extract team identifier from features.

        Tries multiple possible field names. Returns string ID.
        """
        # Try numeric team ID first (more reliable)
        id_key = f"{side}_team_id"
        if id_key in features:
            return str(int(features[id_key]))

        # Try string-encoded team name (stored as hash in numeric features)
        name_key = f"{side}_team"
        if name_key in features:
            val = features[name_key]
            if isinstance(val, str):
                return val
            # If it's a numeric hash, convert to string
            return str(int(val))

        # Try the match_dict style
        for key in [f"{side}_team_name", f"{side}Team"]:
            if key in features:
                return str(features[key])

        return None

    def _fit_mle(
        self,
        matches: list[dict],
        teams: list[str],
        weights: list[float],
    ) -> None:
        """Fit model parameters via maximum likelihood estimation.

        Parameters vector:
        [attack_0, ..., attack_n-1, defense_0, ..., defense_n-1, home_adv, rho]

        Constraint: sum(attack) = n_teams (identifiability)

        Empirical Bayes shrinkage: L2 penalty on log(attack) and log(defense)
        pulls team strengths toward 1.0 (league average). The penalty weight
        for each team is shrinkage_factor / n_matches_for_that_team, so teams
        with fewer matches in the training window are regularized more heavily.
        """
        team_idx = {t: i for i, t in enumerate(teams)}
        n_teams = len(teams)

        # Filter matches to only those with known teams
        valid_matches = []
        valid_weights = []
        for m, w in zip(matches, weights):
            if m["home_team"] in team_idx and m["away_team"] in team_idx:
                valid_matches.append(m)
                valid_weights.append(w)

        if len(valid_matches) < 10:
            self._fit_simple_poisson(matches)
            return

        valid_weights = np.array(valid_weights)

        # Compute per-team match counts (within valid matches only)
        team_match_counts = np.zeros(n_teams)
        for m in valid_matches:
            team_match_counts[team_idx[m["home_team"]]] += 1
            team_match_counts[team_idx[m["away_team"]]] += 1
        # Ensure minimum of 1 to avoid division by zero
        team_match_counts = np.maximum(team_match_counts, 1.0)

        # Per-team shrinkage penalty weights: shrinkage_factor / n_matches
        # Teams with fewer matches get pulled harder toward league average
        shrinkage_weights = self._shrinkage_factor / team_match_counts

        def neg_log_likelihood(params):
            """Negative log-likelihood with empirical Bayes shrinkage penalty."""
            attacks = params[:n_teams]
            defenses = params[n_teams:2 * n_teams]
            home_adv = params[2 * n_teams]
            rho = params[2 * n_teams + 1]

            # Identifiability constraint penalty
            constraint_penalty = 100.0 * (np.mean(attacks) - 1.0) ** 2

            # Empirical Bayes shrinkage: penalize deviation of each team's
            # log(attack) and log(defense) from the cross-sectional mean.
            # This reduces variance of team-specific estimates while
            # preserving the overall goal rate (no bias toward under-prediction).
            # Penalty is stronger for teams with fewer matches.
            if self._shrinkage_factor > 0:
                log_attacks = np.log(np.maximum(attacks, 0.001))
                log_defenses = np.log(np.maximum(defenses, 0.001))
                # Penalize squared deviation from cross-sectional mean
                mean_log_att = np.mean(log_attacks)
                mean_log_def = np.mean(log_defenses)
                shrinkage_penalty = np.sum(
                    shrinkage_weights * (
                        (log_attacks - mean_log_att) ** 2
                        + (log_defenses - mean_log_def) ** 2
                    )
                )
            else:
                shrinkage_penalty = 0.0

            # Vectorized computation
            home_idx = np.array([team_idx[m["home_team"]] for m in valid_matches])
            away_idx = np.array([team_idx[m["away_team"]] for m in valid_matches])
            hg = np.array([m["home_goals"] for m in valid_matches])
            ag = np.array([m["away_goals"] for m in valid_matches])

            lambda_home = np.maximum(0.001, attacks[home_idx] * defenses[away_idx] * home_adv)
            lambda_away = np.maximum(0.001, attacks[away_idx] * defenses[home_idx])

            # Poisson log-likelihood: y*log(lam) - lam - log(y!)
            ll_home = hg * np.log(lambda_home) - lambda_home - gammaln(hg + 1)
            ll_away = ag * np.log(lambda_away) - lambda_away - gammaln(ag + 1)

            # Dixon-Coles tau correction (vectorized for common cases)
            tau = np.ones(len(valid_matches))
            mask_00 = (hg == 0) & (ag == 0)
            mask_10 = (hg == 1) & (ag == 0)
            mask_01 = (hg == 0) & (ag == 1)
            mask_11 = (hg == 1) & (ag == 1)

            tau[mask_00] = np.maximum(1e-10, 1.0 - lambda_home[mask_00] * lambda_away[mask_00] * rho)
            tau[mask_10] = np.maximum(1e-10, 1.0 + lambda_away[mask_10] * rho)
            tau[mask_01] = np.maximum(1e-10, 1.0 + lambda_home[mask_01] * rho)
            tau[mask_11] = np.maximum(1e-10, 1.0 - rho)

            ll = np.sum(valid_weights * (ll_home + ll_away + np.log(tau)))
            return -ll + constraint_penalty + shrinkage_penalty

        # Pre-compute indices for vectorized access

        # Initial parameters
        # Start with attack=1, defense=1, home_adv=1.3, rho=-0.05
        x0 = np.ones(2 * n_teams + 2)
        x0[2 * n_teams] = 1.3  # home advantage
        x0[2 * n_teams + 1] = -0.05  # rho

        # Bounds: attack/defense > 0, home_adv in [0.5, 3], rho in [-0.5, 0.5]
        bounds = (
            [(0.01, 5.0)] * n_teams  # attacks
            + [(0.01, 5.0)] * n_teams  # defenses
            + [(0.5, 3.0)]  # home advantage
            + [(-0.5, 0.5)]  # rho
        )

        # Optimize
        result = minimize(
            neg_log_likelihood,
            x0,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 100, "ftol": 1e-4},
        )

        if not result.success and result.fun > neg_log_likelihood(x0):
            # Optimization didn't improve — use initial values
            result.x = x0

        # Extract parameters
        opt_params = result.x
        attacks = opt_params[:n_teams]
        defenses = opt_params[n_teams:2 * n_teams]
        home_adv = opt_params[2 * n_teams]
        rho = np.clip(opt_params[2 * n_teams + 1], -0.5, 0.5)

        # Normalize attacks to mean 1 (identifiability)
        attack_mean = np.mean(attacks)
        if attack_mean > 0:
            attacks = attacks / attack_mean
            defenses = defenses * attack_mean

        # Post-hoc empirical Bayes shrinkage: pull each team's parameters
        # toward the fitted league means based on their sample size.
        # This reduces variance for low-data teams while preserving the
        # overall goal rate calibration (unlike shrinking toward 1.0 which
        # can bias total expected goals downward).
        #
        # When prior_params is available (from a prior season), teams that
        # existed last season are shrunk toward their prior-season strength
        # instead of the cross-sectional mean. This gives better priors for
        # early-season predictions when current-season data is sparse.
        #
        # shrinkage_weight = n_matches / (n_matches + kappa)
        # - 8 matches: weight=0.25 (75% pull toward prior)
        # - 15 matches: weight=0.38 (62% pull toward prior)
        # - 30 matches: weight=0.56 (44% pull toward prior)
        if self._shrinkage_factor > 0:
            kappa = self._shrinkage_factor * 2.0

            # Compute the log-mean of attacks and defenses (after normalization)
            log_attack_mean = np.mean(np.log(np.maximum(attacks, 0.001)))
            log_defense_mean = np.mean(np.log(np.maximum(defenses, 0.001)))

            for i in range(n_teams):
                n_team = team_match_counts[i]
                weight = n_team / (n_team + kappa)

                # Determine shrinkage target for this team
                team_name = teams[i]
                if (self._prior_params is not None
                        and team_name in self._prior_params.team_attack
                        and team_name in self._prior_params.team_defense):
                    # Use prior-season strength as target
                    prior_attack = self._prior_params.team_attack[team_name]
                    prior_defense = self._prior_params.team_defense[team_name]
                    target_log_attack = math.log(max(prior_attack, 0.001))
                    target_log_defense = math.log(max(prior_defense, 0.001))
                else:
                    # New team (promoted) or no prior — use cross-sectional mean
                    target_log_attack = log_attack_mean
                    target_log_defense = log_defense_mean

                # Shrink toward target on log scale
                log_attack = math.log(max(attacks[i], 0.001))
                log_defense = math.log(max(defenses[i], 0.001))
                attacks[i] = math.exp(
                    weight * log_attack + (1 - weight) * target_log_attack
                )
                defenses[i] = math.exp(
                    weight * log_defense + (1 - weight) * target_log_defense
                )

            # Re-normalize attacks to mean 1 (identifiability)
            attack_mean = np.mean(attacks)
            if attack_mean > 0:
                attacks = attacks / attack_mean
                defenses = defenses * attack_mean

        team_attack = {teams[i]: float(attacks[i]) for i in range(n_teams)}
        team_defense = {teams[i]: float(defenses[i]) for i in range(n_teams)}

        self._params = DixonColesParams(
            team_attack=team_attack,
            team_defense=team_defense,
            home_advantage=float(home_adv),
            rho=float(rho),
            n_teams=n_teams,
            n_matches=len(valid_matches),
        )

    def _fit_simple_poisson(self, matches: list[dict]) -> None:
        """Fallback: fit simple Poisson with league-average rates."""
        if not matches:
            self._params = None
            self._fitted = True
            return

        home_goals = [m["home_goals"] for m in matches]
        away_goals = [m["away_goals"] for m in matches]

        avg_home = max(0.1, sum(home_goals) / len(home_goals))
        avg_away = max(0.1, sum(away_goals) / len(away_goals))

        # Single "average" team
        all_teams = set()
        for m in matches:
            all_teams.add(m["home_team"])
            all_teams.add(m["away_team"])

        team_attack = {t: 1.0 for t in all_teams}
        team_defense = {t: 1.0 for t in all_teams}

        self._params = DixonColesParams(
            team_attack=team_attack,
            team_defense=team_defense,
            home_advantage=avg_home / max(0.1, avg_away),
            rho=0.0,
            n_teams=len(all_teams),
            n_matches=len(matches),
        )
        self._fitted = True

    # ──────────────────────────────────────────────────────────
    # Internal: Prediction
    # ──────────────────────────────────────────────────────────

    def _get_expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        """Compute expected goals for a match given team strengths."""
        params = self._params
        assert params is not None

        # Get team parameters (fall back to 1.0 for unknown teams)
        alpha_home = params.team_attack.get(home_team, 1.0)
        beta_away = params.team_defense.get(away_team, 1.0)
        alpha_away = params.team_attack.get(away_team, 1.0)
        beta_home = params.team_defense.get(home_team, 1.0)

        lambda_home = alpha_home * beta_away * params.home_advantage
        lambda_away = alpha_away * beta_home

        # Clip to reasonable range
        lambda_home = max(0.1, min(6.0, lambda_home))
        lambda_away = max(0.1, min(6.0, lambda_away))

        return lambda_home, lambda_away

    def _scoreline_grid(self, lambda_home: float, lambda_away: float) -> np.ndarray:
        """Compute full scoreline probability grid with DC correction."""
        n = self._max_goals + 1
        grid = np.zeros((n, n))
        rho = self._params.rho if self._params else 0.0

        for i in range(n):
            for j in range(n):
                p_home = poisson.pmf(i, lambda_home)
                p_away = poisson.pmf(j, lambda_away)
                tau = self._tau(i, j, lambda_home, lambda_away, rho)
                grid[i, j] = p_home * p_away * tau

        # Normalize (grid should sum to ~1 but floating point may deviate)
        total = grid.sum()
        if total > 0:
            grid = grid / total

        return grid

    def _compute_over_under(
        self, lambda_home: float, lambda_away: float, line: float
    ) -> tuple[float, float]:
        """Compute P(over) and P(under) from scoreline grid."""
        grid = self._scoreline_grid(lambda_home, lambda_away)
        n = grid.shape[0]

        p_over = 0.0
        for i in range(n):
            for j in range(n):
                if i + j > line:
                    p_over += grid[i, j]

        p_under = 1.0 - p_over
        return p_over, p_under

    @staticmethod
    def _tau(
        home_goals: int, away_goals: int,
        lambda_home: float, lambda_away: float,
        rho: float,
    ) -> float:
        """Dixon-Coles correlation correction factor.

        Only modifies probabilities for low-scoring outcomes:
        - (0,0): tau = 1 - lambda_home * lambda_away * rho
        - (1,0): tau = 1 + lambda_away * rho
        - (0,1): tau = 1 + lambda_home * rho
        - (1,1): tau = 1 - rho
        - All others: tau = 1

        Args:
            home_goals: Home team goals.
            away_goals: Away team goals.
            lambda_home: Expected home goals.
            lambda_away: Expected away goals.
            rho: Correlation parameter (typically small negative).

        Returns:
            Multiplicative correction factor (always > 0).
        """
        if home_goals == 0 and away_goals == 0:
            return max(1e-10, 1.0 - lambda_home * lambda_away * rho)
        elif home_goals == 1 and away_goals == 0:
            return max(1e-10, 1.0 + lambda_away * rho)
        elif home_goals == 0 and away_goals == 1:
            return max(1e-10, 1.0 + lambda_home * rho)
        elif home_goals == 1 and away_goals == 1:
            return max(1e-10, 1.0 - rho)
        else:
            return 1.0

    # ──────────────────────────────────────────────────────────
    # Confidence / uncertainty
    # ──────────────────────────────────────────────────────────

    def prediction_confidence(self, features: dict[str, float]) -> float:
        """Estimate prediction confidence based on data availability.

        Returns a value in [0, 1] reflecting:
        - Whether both teams have sufficient match history
        - How many total matches the model was trained on
        """
        if self._params is None:
            return 0.0

        home_team = self._get_team_id(features, "home")
        away_team = self._get_team_id(features, "away")

        home_matches = self._team_match_counts.get(home_team, 0) if home_team else 0
        away_matches = self._team_match_counts.get(away_team, 0) if away_team else 0

        # Confidence based on min team matches (saturates at ~20 matches)
        min_matches = min(home_matches, away_matches)
        team_confidence = min(1.0, min_matches / 20.0)

        # Confidence based on total model training size
        model_confidence = min(1.0, self._params.n_matches / 200.0)

        # Whether teams are in the model at all
        known_home = home_team in self._params.team_attack if home_team else False
        known_away = away_team in self._params.team_attack if away_team else False
        known_factor = 1.0 if (known_home and known_away) else 0.5

        return team_confidence * model_confidence * known_factor
