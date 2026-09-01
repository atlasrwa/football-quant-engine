"""Interaction_Model — two-direction fixture modelling with cards conditioning.

Responsibility
==============
Model each fixture as exactly two Directions and never collapse them:

    Direction A_attack_vs_B_defence : team A attacks, team B defends
    Direction B_attack_vs_A_defence : team B attacks, team A defends

Each Direction × Per_Side_Target (corners, goals, sot, cards) is a **separately
fitted** :class:`~src.research.asymmetric.directional_model.DirectionalCountModel`
— the two directions are two distinct hypotheses / estimators that never share a
parameter vector, so no single symmetric feature can reproduce both (Req 2.1,
2.2, 2.3; enforced by Property 1).

For a Direction "X-attack against Y-defence", each target's linear predictor is
built from three named groups of continuous inputs (Req 2.8):

    attacker's attacking-profile dimensions   (from team X)   -> ``att.<dim>``
    defender's defensive-profile dimensions   (from team Y)   -> ``def.<dim>``
    named interaction cross-terms             (X_att × Y_def) -> ``ix.<name>``

The attacker vector and the defender vector therefore enter **from different
teams**; swapping X and Y feeds a different input vector to a differently-fitted
estimator, so the two directions' outputs swap rather than stay put (Property 1).
There is deliberately no symmetric summary such as ``(X + Y) / 2``.

Every Per_Side_Target returns a **full predictive distribution** (PMF over
counts) rather than a point estimate (Req 2.4-2.7), via the underlying
Poisson/NB PMF.

Cards conditioning (Req 2.7, 2.11, 16.1-16.4)
=============================================
The cards target's feature row carries an extra conditioning term for the card
rate. :class:`RefereeCardRate` reuses the *expanding, look-ahead-free,
league-fallback* pattern of
:class:`src.features.referee_volatility.RefereeVolatilityCalculator`: for each
match it reads the relevant prior card rate from matches strictly BEFORE the
current one, then folds the current match in afterwards (compute-before-update).

**Audit-grounded two-mode design (Req 16).** The coverage audit established that
referee assignment is *not available pre-match* in either data source. So this
component distinguishes two explicit modes:

  * ``ConditioningMode.PRE_MATCH`` (the CLI / real prediction path): the
    **league-level expanding-window card rate is the PRIMARY and ONLY**
    conditioning signal. A referee-specific rate is *never* used, because the
    referee id is unknown before kickoff. ``referee_substituted`` is therefore
    **always True** on the cards prediction (Req 16.1, 16.3, 16.4).

  * ``ConditioningMode.BACKTEST`` (completed fixtures with a known post-match
    referee id): a **referee-specific** expanding-window card rate MAY be used,
    but only when the referee is assigned AND has at least ``min_referee_matches``
    prior observations. Otherwise the league-level expanding rate is substituted
    and ``referee_substituted=True`` is set (Req 16.2, 2.11). The substituted
    prediction is exactly the prediction produced by conditioning on the league
    rate (Property 5).

This refines — it does not replace — the cards-conditioning mechanics of the
Interaction_Model.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.11, 16.1, 16.2, 16.3,
16.4.
"""

from __future__ import annotations

import enum
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from src.research.asymmetric.directional_model import DirectionalCountModel
from src.research.asymmetric.models import (
    DirectionPrediction,
    FixturePrediction,
    TeamMatchProfiles,
)
from src.research.asymmetric.profiles import TeamProfiler
from src.research.data_source import ResearchMatch

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

#: The four Per_Side_Targets modelled per direction (Req 2.4-2.7).
TARGETS: tuple[str, ...] = ("corners", "goals", "sot", "cards")

#: Direction labels (match the ``DirectionPrediction.direction`` convention).
DIRECTION_A = "A_attack_vs_B_defence"
DIRECTION_B = "B_attack_vs_A_defence"

#: Attacking / defensive profile dimension names, in vector order.
ATT_DIMS: tuple[str, ...] = (
    "width",
    "central_penetration",
    "volume_vs_quality",
    "set_piece_reliance",
    "directness",
)
DEF_DIMS: tuple[str, ...] = (
    "block_orientation",
    "aerial_vs_ground",
    "shot_suppression",
    "gk_contribution",
    "discipline",
)

#: Feature-row key prefixes.
ATT_PREFIX = "att."
DEF_PREFIX = "def."
IX_PREFIX = "ix."
#: Card-rate conditioning key (cards target only).
CARD_RATE_KEY = "card_rate"

#: Default max count support for returned PMFs, per target.
DEFAULT_MAX_K: dict[str, int] = {
    "corners": 20,
    "goals": 12,
    "sot": 15,
    "cards": 12,
}

#: How many prior matches a referee needs before a referee-specific rate is used
#: in BACKTEST mode (mirrors RefereeVolatilityCalculator.min_matches default).
DEFAULT_MIN_REFEREE_MATCHES = 5


# ─────────────────────────────────────────────────────────────────────────────
# Named interaction cross-terms (Req 2.8)
# ─────────────────────────────────────────────────────────────────────────────
#
# Each cross-term is an attacker-attacking-dimension multiplied by a
# defender-defensive-dimension, chosen so the term captures the mechanism that
# most plausibly drives that outcome. The names are surfaced verbatim as
# ``driving_features`` on the DirectionPrediction (Req 2.8, 9.3). These are the
# documented cross-terms for this engine:
#
#   corners: attacker.width          × defender.aerial_vs_ground
#            attacker.set_piece_reliance × defender.block_orientation
#   goals  : attacker.volume_vs_quality × defender.shot_suppression
#            attacker.central_penetration × defender.gk_contribution
#   sot    : attacker.central_penetration × defender.block_orientation
#            attacker.volume_vs_quality × defender.gk_contribution
#   cards  : attacker.directness      × defender.discipline
#            attacker.central_penetration × defender.block_orientation
#
# Each entry: cross_name -> (attacking_dim, defensive_dim).

CROSS_TERMS: dict[str, dict[str, tuple[str, str]]] = {
    "corners": {
        "width_x_aerial_vs_ground": ("width", "aerial_vs_ground"),
        "set_piece_x_block_orientation": ("set_piece_reliance", "block_orientation"),
    },
    "goals": {
        "volume_x_shot_suppression": ("volume_vs_quality", "shot_suppression"),
        "central_x_gk_contribution": ("central_penetration", "gk_contribution"),
    },
    "sot": {
        "central_x_block_orientation": ("central_penetration", "block_orientation"),
        "volume_x_gk_contribution": ("volume_vs_quality", "gk_contribution"),
    },
    "cards": {
        "directness_x_discipline": ("directness", "discipline"),
        "central_x_block_orientation": ("central_penetration", "block_orientation"),
    },
}


class ConditioningMode(str, enum.Enum):
    """Cards-conditioning mode (audit-grounded, Req 16).

    * ``PRE_MATCH`` — CLI / real prediction: league rate ONLY, referee-specific
      rate never used, ``referee_substituted`` always True.
    * ``BACKTEST`` — completed fixtures with a known post-match referee id: a
      referee-specific rate MAY be used when sufficiently observed, else the
      league rate is substituted and flagged.
    """

    PRE_MATCH = "pre_match"
    BACKTEST = "backtest"


# ─────────────────────────────────────────────────────────────────────────────
# RefereeCardRate — expanding, look-ahead-free, league-fallback (Task 5.1)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CardRateResult:
    """The resolved card-rate conditioning value for one match.

    Attributes:
        rate: the card rate used for conditioning (referee-specific or league).
        referee_substituted: True when the league-level rate was used in place
            of a referee-specific rate (always True in PRE_MATCH mode; True in
            BACKTEST when the referee is missing/insufficiently observed).
        league_rate: the league-level expanding card rate at this point in time
            (the PRIMARY pre-match signal).
        referee_rate: the referee-specific expanding card rate if one was
            computed and used, else ``None``.
    """

    rate: float
    referee_substituted: bool
    league_rate: float
    referee_rate: Optional[float] = None


class RefereeCardRate:
    """Expanding-window card-rate conditioning for the cards target.

    Reuses the exact expanding / look-ahead-free / league-fallback pattern of
    :class:`src.features.referee_volatility.RefereeVolatilityCalculator`: for
    each match, the conditioning rate is computed from matches occurring
    strictly BEFORE it; the current match's data is folded in only afterwards.

    The card "rate" is the mean total cards per match (yellow + red on both
    sides), computed either league-wide (expanding) or per referee (expanding).

    Audit-grounded two-mode behaviour (Req 16):
      * ``PRE_MATCH``: always returns the league-level expanding rate and sets
        ``referee_substituted=True`` — referee assignment is unavailable
        pre-match, so a referee-specific rate is never used (Req 16.1, 16.3).
      * ``BACKTEST``: uses the referee-specific expanding rate when the match has
        a known referee with >= ``min_referee_matches`` prior observations,
        otherwise substitutes the league rate and sets ``referee_substituted=True``
        (Req 16.2, 2.11).

    Args:
        min_referee_matches: minimum prior officiated matches before a
            referee-specific rate is used in BACKTEST mode (default 5).
    """

    def __init__(self, min_referee_matches: int = DEFAULT_MIN_REFEREE_MATCHES) -> None:
        if min_referee_matches < 1:
            raise ValueError(
                f"min_referee_matches must be >= 1, got {min_referee_matches}"
            )
        self._min_referee_matches = min_referee_matches

    @property
    def min_referee_matches(self) -> int:
        return self._min_referee_matches

    # -- match card total helper (NULL != ZERO tolerant) ----------------- #
    @staticmethod
    def _match_cards(match: ResearchMatch) -> Optional[int]:
        """Total cards for a match (yellow + red, both sides); None if unknown."""
        if match.total_cards is not None:
            return int(match.total_cards)
        parts = [
            match.yellow_cards_home,
            match.yellow_cards_away,
            match.red_cards_home,
            match.red_cards_away,
        ]
        present = [p for p in parts if p is not None]
        if not present:
            return None
        return sum(int(p) for p in present)

    # -- expanding computation ------------------------------------------- #
    def compute_rates(
        self,
        matches: list[ResearchMatch],
        mode: ConditioningMode = ConditioningMode.PRE_MATCH,
    ) -> dict[int, CardRateResult]:
        """Compute the per-match card-rate conditioning value (look-ahead-free).

        For each match at time T, the rate is computed from matches strictly
        before T (expanding). In BACKTEST mode, when the match's referee has
        >= ``min_referee_matches`` prior observations, the referee-specific
        expanding rate is used; otherwise (and always in PRE_MATCH mode) the
        league-level expanding rate is substituted and flagged.

        Args:
            matches: matches to compute rates for (any order; sorted internally).
            mode: PRE_MATCH (league only) or BACKTEST (referee-specific allowed).

        Returns:
            ``{match_id -> CardRateResult}``.
        """
        if not matches:
            return {}

        ordered = sorted(matches, key=lambda m: m.date_unix)

        # Expanding accumulators, keyed by league and by referee.
        league_cards: dict[int, list[int]] = defaultdict(list)
        referee_cards: dict[str, list[int]] = defaultdict(list)

        out: dict[int, CardRateResult] = {}
        for m in ordered:
            league_rate = self._mean(league_cards[m.league_id])

            if mode == ConditioningMode.BACKTEST and m.referee is not None:
                ref_history = referee_cards[m.referee]
                if len(ref_history) >= self._min_referee_matches:
                    ref_rate = self._mean(ref_history)
                    out[m.match_id] = CardRateResult(
                        rate=ref_rate,
                        referee_substituted=False,
                        league_rate=league_rate,
                        referee_rate=ref_rate,
                    )
                else:
                    out[m.match_id] = CardRateResult(
                        rate=league_rate,
                        referee_substituted=True,
                        league_rate=league_rate,
                        referee_rate=None,
                    )
            else:
                # PRE_MATCH always, or BACKTEST with a missing referee.
                out[m.match_id] = CardRateResult(
                    rate=league_rate,
                    referee_substituted=True,
                    league_rate=league_rate,
                    referee_rate=None,
                )

            # Fold this match in AFTER reading (compute-before-update).
            cards = self._match_cards(m)
            if cards is not None:
                league_cards[m.league_id].append(cards)
                if m.referee is not None:
                    referee_cards[m.referee].append(cards)

        return out

    def rate_for_prediction(
        self,
        league_id: int,
        as_of_unix: int,
        history: list[ResearchMatch],
        referee: Optional[str] = None,
        mode: ConditioningMode = ConditioningMode.PRE_MATCH,
    ) -> CardRateResult:
        """Resolve the card-rate conditioning value for a single fixture.

        Only matches strictly before ``as_of_unix`` contribute (look-ahead-free).
        In PRE_MATCH mode the league expanding rate is always used
        (``referee_substituted=True``); in BACKTEST mode a referee-specific rate
        is used only when ``referee`` is set and has >= ``min_referee_matches``
        prior observations, else the league rate is substituted and flagged.
        """
        league_cards: list[int] = []
        referee_cards: list[int] = []
        for m in sorted(history, key=lambda x: x.date_unix):
            if m.date_unix >= as_of_unix:
                continue
            cards = self._match_cards(m)
            if cards is None:
                continue
            if m.league_id == league_id:
                league_cards.append(cards)
            if referee is not None and m.referee == referee:
                referee_cards.append(cards)

        league_rate = self._mean(league_cards)

        if (
            mode == ConditioningMode.BACKTEST
            and referee is not None
            and len(referee_cards) >= self._min_referee_matches
        ):
            ref_rate = self._mean(referee_cards)
            return CardRateResult(
                rate=ref_rate,
                referee_substituted=False,
                league_rate=league_rate,
                referee_rate=ref_rate,
            )
        return CardRateResult(
            rate=league_rate,
            referee_substituted=True,
            league_rate=league_rate,
            referee_rate=None,
        )

    @staticmethod
    def _mean(values: list[int]) -> float:
        """Mean of a list of ints; 0.0 for empty (no prior information)."""
        if not values:
            return 0.0
        return float(sum(values)) / float(len(values))


# ─────────────────────────────────────────────────────────────────────────────
# Feature-row construction (shared by fit + predict, and reusable by tasks 9/13)
# ─────────────────────────────────────────────────────────────────────────────


def build_direction_features(
    attacker: TeamMatchProfiles,
    defender: TeamMatchProfiles,
    target: str,
    *,
    card_rate: Optional[float] = None,
) -> dict[str, float]:
    """Build one direction's feature row for ``target`` (Req 2.8).

    The row is the attacker's attacking-profile dimensions (``att.<dim>``), the
    defender's defensive-profile dimensions (``def.<dim>``), the named
    interaction cross-terms for the target (``ix.<name>``), and — for the cards
    target — the card-rate conditioning term (``card_rate``). The attacker's
    completed-match count is carried as ``n_matches`` so the DirectionalCountModel
    applies its mandatory ``n/(n+k)`` team-level shrinkage (Req 5.6).

    Args:
        attacker: the attacking team's point-in-time profiles.
        defender: the defending team's point-in-time profiles.
        target: one of ``corners``, ``goals``, ``sot``, ``cards``.
        card_rate: the expanding card-rate conditioning value (cards only).

    Returns:
        A ``dict[str, float]`` feature row (excludes the observed count).
    """
    if target not in TARGETS:
        raise ValueError(f"unknown target {target!r}; expected one of {TARGETS}")

    att = attacker.attacking
    dfn = defender.defensive

    att_values = {dim: getattr(att, dim).value for dim in ATT_DIMS}
    def_values = {dim: getattr(dfn, dim).value for dim in DEF_DIMS}

    row: dict[str, float] = {}
    for dim in ATT_DIMS:
        row[f"{ATT_PREFIX}{dim}"] = float(att_values[dim])
    for dim in DEF_DIMS:
        row[f"{DEF_PREFIX}{dim}"] = float(def_values[dim])

    for cross_name, (a_dim, d_dim) in CROSS_TERMS[target].items():
        row[f"{IX_PREFIX}{cross_name}"] = float(att_values[a_dim] * def_values[d_dim])

    if target == "cards" and card_rate is not None:
        row[CARD_RATE_KEY] = float(card_rate)

    # Carry the attacker's history count for team-level shrinkage (Req 5.6).
    row["n_matches"] = float(attacker.n_history)
    return row


def driving_feature_names(target: str, *, cards_referee_term: bool = False) -> tuple[str, ...]:
    """Return the named driving features for a target (Req 2.8, 9.3).

    These are surfaced verbatim on ``DirectionPrediction.driving_features`` so
    reporting and the CLI can name what drove each prediction.
    """
    names: list[str] = []
    names.extend(f"{ATT_PREFIX}{dim}" for dim in ATT_DIMS)
    names.extend(f"{DEF_PREFIX}{dim}" for dim in DEF_DIMS)
    names.extend(f"{IX_PREFIX}{name}" for name in CROSS_TERMS[target])
    if target == "cards" and cards_referee_term:
        names.append(CARD_RATE_KEY)
    return tuple(names)


# ─────────────────────────────────────────────────────────────────────────────
# Directional training observations
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DirectionObservation:
    """One historical directional observation (attacker vs defender, one target).

    ``features`` is the feature row (from :func:`build_direction_features`) plus
    the observed ``count`` under the target's count field, so it can be fed
    directly to :meth:`DirectionalCountModel.fit`.
    """

    target: str
    features: dict[str, float]


@dataclass
class FixtureContext:
    """Everything needed to predict one fixture (CLI / evaluator input).

    Attributes:
        home_team / away_team: the fixture's two teams.
        date_unix: kickoff timestamp (point-in-time cut-off).
        home_profiles / away_profiles: point-in-time TeamMatchProfiles for each.
        league_id: the fixture's league (for league card-rate conditioning).
        card_rate_home / card_rate_away: resolved card-rate conditioning values
            for each attacking side (may be equal — both are league rate in
            PRE_MATCH mode). When None the InteractionModel resolves them.
        referee_substituted_home / referee_substituted_away: whether the card
            rate for each side was a league-level substitution.
    """

    home_team: str
    away_team: str
    date_unix: int
    home_profiles: TeamMatchProfiles
    away_profiles: TeamMatchProfiles
    league_id: int = 0
    card_rate_home: Optional[float] = None
    card_rate_away: Optional[float] = None
    referee_substituted_home: bool = True
    referee_substituted_away: bool = True


def build_training_observations(
    matches: list[ResearchMatch],
    profiler: TeamProfiler,
    *,
    targets: tuple[str, ...] = TARGETS,
    mode: ConditioningMode = ConditioningMode.BACKTEST,
    referee_card_rate: Optional[RefereeCardRate] = None,
    leagues: Optional[dict[int, str]] = None,
) -> dict[tuple[str, str], list[DirectionObservation]]:
    """Build per-(direction, target) training rows from a corpus + TeamProfiler.

    This is the reusable helper referenced by tasks 9 (evaluator) and 13
    (wiring): it walks the corpus point-in-time, and for each completed match it
    emits, for each target, TWO directional observations — one for each side
    attacking the other — using each side's point-in-time attacking profile
    against the opponent's point-in-time defensive profile (Req 2.1, 2.2). Team
    identity is only an aggregation key inside the profiler; the observations
    carry no identity feature (Req 1.3).

    The observed count per target is read from the correct side of the match:
      corners -> that side's corners; goals -> that side's goals;
      sot -> that side's shots on target; cards -> that side's total cards.

    Cards observations carry the expanding card-rate conditioning term. In
    BACKTEST mode a referee-specific rate is used where available (Req 16.2);
    the mode is BACKTEST by default because this builds *training* rows over
    completed fixtures with known post-match referee ids.

    Returns:
        ``{(direction_label, target) -> [DirectionObservation, ...]}`` keyed by
        the two direction labels and each target. The two directions are kept as
        separate keys so each is fit by a separate estimator (Req 2.3).
    """
    profiles_map = profiler.compute_profiles_map(matches, leagues=leagues)

    ref_rate = referee_card_rate or RefereeCardRate()
    rate_map = ref_rate.compute_rates(matches, mode=mode)

    out: dict[tuple[str, str], list[DirectionObservation]] = {
        (DIRECTION_A, t): [] for t in targets
    }
    for t in targets:
        out[(DIRECTION_B, t)] = []

    for m in matches:
        if m.home_goals is None or m.away_goals is None:
            continue
        home_prof = profiles_map.get(m.match_id)
        away_prof = profiles_map.get(-m.match_id)
        if home_prof is None or away_prof is None:
            continue
        # Skip fixtures where either side has no prior history to profile from.
        if home_prof.n_history == 0 or away_prof.n_history == 0:
            continue

        card_rate = rate_map.get(m.match_id)
        cr_val = card_rate.rate if card_rate is not None else 0.0

        observed = _observed_counts(m)

        for direction, attacker, defender, side in (
            (DIRECTION_A, home_prof, away_prof, "home"),
            (DIRECTION_B, away_prof, home_prof, "away"),
        ):
            for t in targets:
                count = observed[side][t]
                if count is None:
                    continue
                feats = build_direction_features(
                    attacker,
                    defender,
                    t,
                    card_rate=cr_val if t == "cards" else None,
                )
                feats["count"] = float(count)
                out[(direction, t)].append(
                    DirectionObservation(target=t, features=feats)
                )

    return out


def _observed_counts(m: ResearchMatch) -> dict[str, dict[str, Optional[int]]]:
    """Observed per-side counts for each target (NULL != ZERO preserved)."""

    def cards(y: Optional[int], r: Optional[int]) -> Optional[int]:
        if y is None and r is None:
            return None
        return (y or 0) + (r or 0)

    return {
        "home": {
            "corners": m.corners_home,
            "goals": m.home_goals,
            "sot": m.shots_on_target_home,
            "cards": cards(m.yellow_cards_home, m.red_cards_home),
        },
        "away": {
            "corners": m.corners_away,
            "goals": m.away_goals,
            "sot": m.shots_on_target_away,
            "cards": cards(m.yellow_cards_away, m.red_cards_away),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# InteractionModel (Task 5.2)
# ─────────────────────────────────────────────────────────────────────────────


class InteractionModel:
    """Two-direction fixture model producing 2 directions × 4 targets predictions.

    Each (direction, target) pair is a **separately fitted**
    :class:`DirectionalCountModel` (Req 2.1-2.3). ``fit`` trains all of them from
    directional observations; ``predict_fixture`` produces the eight
    :class:`DirectionPrediction` objects (two directions × four targets), each a
    full predictive distribution with named driving features and the cards
    ``referee_substituted`` flag (Req 2.4-2.8, 2.11).

    Args:
        targets: which Per_Side_Targets to model (default all four).
        mode: cards-conditioning mode for prediction — ``PRE_MATCH`` (CLI: league
            rate only, always substituted) or ``BACKTEST`` (referee-specific
            where available). Defaults to ``PRE_MATCH`` so the safe, audit-honest
            behaviour is the default (Req 16.3).
        referee_card_rate: the RefereeCardRate helper (default constructed).
    """

    def __init__(
        self,
        targets: tuple[str, ...] = TARGETS,
        mode: ConditioningMode = ConditioningMode.PRE_MATCH,
        referee_card_rate: Optional[RefereeCardRate] = None,
    ) -> None:
        for t in targets:
            if t not in TARGETS:
                raise ValueError(f"unknown target {t!r}; expected one of {TARGETS}")
        self._targets = tuple(targets)
        self._mode = mode
        self._referee_card_rate = referee_card_rate or RefereeCardRate()
        # (direction, target) -> fitted DirectionalCountModel
        self._models: dict[tuple[str, str], DirectionalCountModel] = {}
        self._fitted = False

    @property
    def targets(self) -> tuple[str, ...]:
        return self._targets

    @property
    def mode(self) -> ConditioningMode:
        return self._mode

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def model_for(self, direction: str, target: str) -> Optional[DirectionalCountModel]:
        """Return the fitted DirectionalCountModel for a (direction, target)."""
        return self._models.get((direction, target))

    # -- fitting --------------------------------------------------------- #
    def fit(
        self,
        dataset: dict[tuple[str, str], list[DirectionObservation]],
    ) -> None:
        """Fit each (direction, target) DirectionalCountModel independently.

        ``dataset`` is the mapping produced by :func:`build_training_observations`
        (or an equivalent). Each key's observations are fed to a *separate*
        estimator, so the two directions never share a parameter vector (Req 2.3).
        """
        self._models = {}
        for direction in (DIRECTION_A, DIRECTION_B):
            for target in self._targets:
                obs = dataset.get((direction, target), [])
                rows = [o.features for o in obs]
                model = DirectionalCountModel(
                    target_field="count",
                    line=_default_line(target),
                )
                model.fit(rows)
                self._models[(direction, target)] = model
        self._fitted = True

    # -- prediction ------------------------------------------------------ #
    def predict_direction(
        self,
        direction: str,
        attacker: TeamMatchProfiles,
        defender: TeamMatchProfiles,
        target: str,
        *,
        card_rate: Optional[float] = None,
        referee_substituted: bool = True,
    ) -> DirectionPrediction:
        """Predict one (direction, target) as a full predictive distribution."""
        model = self._models.get((direction, target))
        feats = build_direction_features(
            attacker, defender, target, card_rate=card_rate if target == "cards" else None
        )
        max_k = DEFAULT_MAX_K[target]
        if model is not None:
            pmf = model.predict_distribution(feats, max_k=max_k)
            ev = model.predict_expected_count(feats)
        else:
            # Unfitted fallback: valid PMF from the default line as a prior mean.
            fallback = DirectionalCountModel(
                target_field="count", line=_default_line(target)
            )
            pmf = fallback.predict_distribution(feats, max_k=max_k)
            ev = fallback.predict_expected_count(feats)

        return DirectionPrediction(
            direction=direction,
            attacker=attacker.team,
            defender=defender.team,
            target=target,
            distribution=tuple(pmf),
            expected_value=float(ev),
            driving_features=driving_feature_names(
                target, cards_referee_term=(target == "cards")
            ),
            referee_substituted=(referee_substituted if target == "cards" else False),
        )

    def predict_fixture(self, fixture_ctx: FixtureContext) -> list[DirectionPrediction]:
        """Produce the 2 directions × N targets DirectionPredictions.

        Direction A = home attacks / away defends; Direction B = away attacks /
        home defends. Card-rate conditioning is resolved per attacking side; in
        PRE_MATCH mode both are the league rate and ``referee_substituted`` is
        always True (Req 16.1, 16.3).
        """
        home = fixture_ctx.home_profiles
        away = fixture_ctx.away_profiles

        cr_home = fixture_ctx.card_rate_home
        cr_away = fixture_ctx.card_rate_away
        sub_home = fixture_ctx.referee_substituted_home
        sub_away = fixture_ctx.referee_substituted_away

        preds: list[DirectionPrediction] = []
        for target in self._targets:
            preds.append(
                self.predict_direction(
                    DIRECTION_A,
                    home,
                    away,
                    target,
                    card_rate=cr_home,
                    referee_substituted=sub_home,
                )
            )
            preds.append(
                self.predict_direction(
                    DIRECTION_B,
                    away,
                    home,
                    target,
                    card_rate=cr_away,
                    referee_substituted=sub_away,
                )
            )
        return preds


def _default_line(target: str) -> float:
    """A sensible default O/U line per target for the ProbabilityModel interface."""
    return {"corners": 9.5, "goals": 1.5, "sot": 4.5, "cards": 2.5}.get(target, 2.5)
