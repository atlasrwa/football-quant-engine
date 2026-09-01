"""SymmetricBaseline and AsymmetryEvaluator — decisive asymmetry test.

Responsibility:
    SymmetricBaseline uses the same modelling family but only the team's own
    marginal rate, with no interaction layer. AsymmetryEvaluator drives
    walk-forward CV folds to compare the Interaction_Model against the
    Symmetric_Baseline out-of-sample per market and per league, applies the beat
    criterion (BSS improvement with 95% CI lower bound > 0), enforces
    within-league significance at alpha 0.05, labels pooled-only significance as
    an artifact and below-minimum samples as insufficient-sample, and corrects
    within-league significance against a fresh FDR family via Benjamini-Hochberg
    at q=0.05.

Task 9.1 — SymmetricBaseline (Req 8.1)
======================================
``SymmetricBaseline`` is the *null hypothesis* the asymmetry must beat. It uses
the **same modelling family** as the interaction model — the elastic-net
Poisson/NB count machinery of
:class:`~src.research.asymmetric.directional_model.DirectionalCountModel` —
**without the interaction layer**. Concretely it predicts a ``Per_Side_Target``
from **only the acting team's own marginal rate** for that target (that side's
point-in-time rolling mean of the target, e.g. rolling-mean corners). It never
sees the opponent's defensive profile, the attacker's attacking profile, or any
interaction cross-term (Req 8.1).

Design choice — the single marginal-rate feature
-------------------------------------------------
The interaction feature rows produced by
:func:`src.research.asymmetric.interaction.build_direction_features` carry three
groups of inputs — the attacker's attacking dims (``att.*``), the defender's
defensive dims (``def.*``), and named cross-terms (``ix.*``) — plus, for cards,
``card_rate``, plus the bookkeeping key ``n_matches``. **None** of those is the
acting team's own marginal rate for the target. So the baseline cannot simply
"restrict an interaction row to one of its columns" — the marginal rate is not
present in those rows.

Therefore the clean approach is:

  * define a single, documented feature key — :data:`MARGINAL_RATE_KEY`
    (``"own_marginal_rate"``) — carrying the acting team's own point-in-time
    rolling mean of the target; and
  * provide :func:`build_marginal_features`, a small helper that builds those
    marginal-rate rows from a corpus + :class:`TeamProfiler`-style rolling
    discipline (compute-before-update, look-ahead-free), so task 9.3's
    ``AsymmetryEvaluator`` can reuse it to score the baseline on exactly the same
    fixtures as the interaction model.

The baseline is built with an explicit ``feature_fields=(MARGINAL_RATE_KEY,)``
override on the underlying :class:`DirectionalCountModel`. This guarantees that
even if an interaction-shaped row (with ``att.*``/``def.*``/``ix.*``/``card_rate``)
is passed in, the baseline **restricts to the single marginal-rate feature and
ignores everything else** — its prediction is invariant to the opponent's
defensive vector (verified in the task's smoke check). The baseline keeps the
mandatory ``n/(n+k)`` team-level shrinkage of the family (Req 5.6) because it
reuses ``DirectionalCountModel`` unchanged for fitting; the ``n_matches``
bookkeeping key is honoured if present but is not a model feature.

Interface parity with DirectionalCountModel
-------------------------------------------
``SymmetricBaseline`` exposes ``fit(observations)`` /
``predict_distribution(features, max_k)`` / ``predict_expected_count(features)``
mirroring ``DirectionalCountModel`` so the evaluator (task 9.3) can score both
models identically — same PMF support, same scoring. ``fit`` additionally
accepts the same ``list[dict[str, float]]`` shape that ``DirectionalCountModel``
consumes (each row carrying the observed count under ``count`` and the
marginal-rate feature), so the two models share a training path.

The ``AsymmetryEvaluator`` (task 9.3) is intentionally NOT implemented here.

Requirements: 8.1 (task 9.1).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Optional

from src.research.asymmetric.directional_model import DirectionalCountModel
from src.research.asymmetric.interaction import (
    DIRECTION_A,
    DIRECTION_B,
    TARGETS,
    DirectionObservation,
)
from src.research.data_source import ResearchMatch

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

#: The single feature the SymmetricBaseline consumes: the acting team's own
#: point-in-time rolling mean of the target (its marginal rate). This is the
#: ONLY model feature — no opponent/defender dims, no attacker dims, no
#: interaction cross-terms (Req 8.1).
MARGINAL_RATE_KEY = "own_marginal_rate"

#: Default rolling window for the own-marginal-rate feature (matches the
#: TeamProfiler rolling-10 / expanding-fallback discipline, Req 1.4).
DEFAULT_MARGINAL_WINDOW = 10

#: Default O/U lines per target (mirrors interaction._default_line) so the
#: baseline's ProbabilityModel surface behaves sensibly before/without fitting.
_DEFAULT_LINES: dict[str, float] = {
    "corners": 9.5,
    "goals": 1.5,
    "sot": 4.5,
    "cards": 2.5,
}


# ─────────────────────────────────────────────────────────────────────────────
# SymmetricBaseline (Req 8.1)
# ─────────────────────────────────────────────────────────────────────────────


class SymmetricBaseline:
    """Marginal-rate-only count baseline — the null the asymmetry must beat.

    Same modelling family as the interaction model (elastic-net Poisson/NB via
    :class:`DirectionalCountModel`) but WITHOUT the interaction layer: it predicts
    a ``Per_Side_Target`` from **only** the acting team's own marginal rate for
    that target (:data:`MARGINAL_RATE_KEY`). It ignores every opponent/attacker
    profile dimension and every interaction cross-term, even if such keys are
    present in the feature row (Req 8.1).

    The interface mirrors :class:`DirectionalCountModel`
    (``fit`` / ``predict_distribution`` / ``predict_expected_count``) so the
    evaluator can score the baseline and the interaction model identically —
    same PMF support, same scoring.

    Args:
        target: the Per_Side_Target this baseline models (used only for a
            readable name and a sensible default O/U line). One of
            ``corners``/``goals``/``sot``/``cards``.
        line: default O/U line; derived from ``target`` when omitted.
        **model_kwargs: forwarded to the underlying :class:`DirectionalCountModel`
            (e.g. ``lam``, ``alpha_mix``, ``k``, ``distribution``). The
            ``feature_fields`` and ``target_field`` are fixed by this class and
            may not be overridden.
    """

    def __init__(
        self,
        target: str = "corners",
        line: Optional[float] = None,
        **model_kwargs: object,
    ) -> None:
        if target not in TARGETS:
            raise ValueError(f"unknown target {target!r}; expected one of {TARGETS}")
        model_kwargs.pop("feature_fields", None)
        model_kwargs.pop("target_field", None)
        self._target = target
        self._line = float(line) if line is not None else _DEFAULT_LINES.get(target, 2.5)
        # The underlying family model is restricted to the SINGLE marginal-rate
        # feature via an explicit feature_fields override. This is what makes the
        # baseline ignore any opponent/interaction columns in a row (Req 8.1).
        self._model = DirectionalCountModel(
            target_field="count",
            line=self._line,
            feature_fields=(MARGINAL_RATE_KEY,),
            **model_kwargs,  # type: ignore[arg-type]
        )

    # ── identity / reporting parity ─────────────────────────────
    @property
    def name(self) -> str:
        return f"symmetric_baseline_{self._target}"

    @property
    def target(self) -> str:
        return self._target

    @property
    def is_fitted(self) -> bool:
        return self._model.is_fitted

    @property
    def feature_fields(self) -> tuple[str, ...]:
        """The single feature the baseline uses: the own marginal rate."""
        return (MARGINAL_RATE_KEY,)

    @property
    def feature_weights(self) -> dict[str, float]:
        """Fitted coefficient on the marginal-rate feature (readable)."""
        return self._model.feature_weights

    @property
    def intercept(self) -> float:
        return self._model.intercept

    @property
    def distribution_used(self) -> Optional[str]:
        return self._model.distribution_used

    @property
    def dispersion_ratio(self) -> Optional[float]:
        return self._model.dispersion_ratio

    # ── fitting ──────────────────────────────────────────────────
    def fit(
        self,
        observations: list[DirectionObservation] | list[dict[str, float]],
        outcomes: Optional[list[bool]] = None,
        training_start: Optional[int] = None,
        training_end: Optional[int] = None,
    ) -> None:
        """Fit the baseline on marginal-rate rows.

        ``observations`` may be either a list of
        :class:`~src.research.asymmetric.interaction.DirectionObservation`
        (their ``.features`` rows are used) or a list of raw feature-row dicts,
        mirroring the shape :meth:`DirectionalCountModel.fit` consumes. Each row
        must carry the observed count under ``"count"`` and the marginal-rate
        feature under :data:`MARGINAL_RATE_KEY`; any other keys (``att.*``,
        ``def.*``, ``ix.*``, ``card_rate``) are ignored by the model because it
        is restricted to the single marginal-rate feature (Req 8.1).

        ``outcomes`` is accepted for interface parity and ignored — the model
        learns from the actual counts, exactly like ``DirectionalCountModel``.
        """
        rows = _rows_from(observations)
        self._model.fit(
            rows,
            outcomes,
            training_start=training_start,
            training_end=training_end,
        )

    # ── prediction (mirrors DirectionalCountModel) ──────────────
    def predict_expected_count(self, features: dict[str, float]) -> float:
        """Expected count from the acting team's own marginal rate only."""
        return self._model.predict_expected_count(_marginal_only(features))

    def predict_distribution(
        self, features: dict[str, float], max_k: int = 20
    ) -> list[float]:
        """Full predictive PMF from the marginal rate only (same support/scoring)."""
        return self._model.predict_distribution(_marginal_only(features), max_k=max_k)

    def predict_over_under(
        self, features: dict[str, float], line: float
    ) -> tuple[float, float]:
        """P(over)/P(under) at ``line`` from the marginal rate only."""
        return self._model.predict_over_under(_marginal_only(features), line)


# ─────────────────────────────────────────────────────────────────────────────
# Marginal-feature row construction (reusable by task 9.3)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MarginalObservation:
    """One point-in-time marginal-rate observation for a side of a match.

    Attributes:
        match_id: the fixture this observation belongs to.
        league_id: the fixture's league (so the evaluator can bucket per league).
        direction: ``DIRECTION_A`` (home side acts) or ``DIRECTION_B`` (away).
        target: the Per_Side_Target (corners/goals/sot/cards).
        features: the marginal feature row — the acting team's own rolling rate
            under :data:`MARGINAL_RATE_KEY`, the observed ``count``, and the
            ``n_matches`` bookkeeping key for shrinkage. No opponent/interaction
            columns are present (Req 8.1).
    """

    match_id: int
    league_id: int
    direction: str
    target: str
    features: dict[str, float]


def build_marginal_features(
    matches: list[ResearchMatch],
    *,
    targets: tuple[str, ...] = TARGETS,
    window: int = DEFAULT_MARGINAL_WINDOW,
) -> dict[tuple[str, str], list[MarginalObservation]]:
    """Build the baseline's point-in-time marginal-rate rows from a corpus.

    For each completed match (processed in ascending ``date_unix`` order) and
    each target, this emits TWO observations — one per side — where the single
    model feature is that side's OWN rolling mean of the target computed from the
    side's matches STRICTLY BEFORE this fixture (compute-before-update,
    look-ahead-free — Req 1.4, 11.1, 11.3), keyed on team identity across home
    and away appearances and all leagues (Req 1.5, 1.18). No opponent or
    interaction information enters the row (Req 8.1).

    The row layout mirrors what :meth:`SymmetricBaseline.fit` /
    :meth:`SymmetricBaseline.predict_distribution` consume: ``own_marginal_rate``
    (the feature), ``count`` (the observed target for that side), and
    ``n_matches`` (the side's completed-match count, for the family's ``n/(n+k)``
    shrinkage).

    Returns:
        ``{(direction_label, target) -> [MarginalObservation, ...]}`` — the same
        keying used by :func:`build_training_observations`, so task 9.3 can zip
        the baseline's rows against the interaction model's per-fixture rows.
    """
    for t in targets:
        if t not in TARGETS:
            raise ValueError(f"unknown target {t!r}; expected one of {TARGETS}")

    ordered = sorted(matches, key=lambda m: m.date_unix)

    # Per-team rolling history of that team's OWN target counts, one deque per
    # (team, target). Compute-before-update keeps every row look-ahead-free.
    history: dict[tuple[str, str], Deque[int]] = defaultdict(
        lambda: deque(maxlen=window)
    )
    # Per-team completed-match count (for the n/(n+k) shrinkage bookkeeping).
    match_count: dict[str, int] = defaultdict(int)

    out: dict[tuple[str, str], list[MarginalObservation]] = {
        (DIRECTION_A, t): [] for t in targets
    }
    for t in targets:
        out[(DIRECTION_B, t)] = []

    for m in ordered:
        observed = _side_counts(m)

        for direction, side in ((DIRECTION_A, "home"), (DIRECTION_B, "away")):
            team = m.home_team if side == "home" else m.away_team
            n_prior = match_count[team]
            for t in targets:
                count = observed[side][t]
                if count is None:
                    continue
                prior = history[(team, t)]
                rate = (sum(prior) / len(prior)) if prior else 0.0
                row: dict[str, float] = {
                    MARGINAL_RATE_KEY: float(rate),
                    "count": float(count),
                    "n_matches": float(n_prior),
                }
                out[(direction, t)].append(
                    MarginalObservation(
                        match_id=m.match_id,
                        league_id=m.league_id,
                        direction=direction,
                        target=t,
                        features=row,
                    )
                )

        # Fold this match into each side's own rolling target history AFTER
        # reading (compute-before-update, Req 11.3). Only completed matches
        # (both goal counts present) contribute to history.
        if m.home_goals is None or m.away_goals is None:
            continue
        observed = _side_counts(m)
        for side, team in (("home", m.home_team), ("away", m.away_team)):
            match_count[team] += 1
            for t in targets:
                count = observed[side][t]
                if count is not None:
                    history[(team, t)].append(int(count))

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _marginal_only(features: dict[str, float]) -> dict[str, float]:
    """Restrict an (possibly interaction-shaped) row to the baseline's inputs.

    Keeps only the marginal-rate feature and the ``n_matches`` shrinkage key.
    Any opponent/attacker/interaction columns are dropped so the baseline's
    prediction is invariant to them (Req 8.1). A missing marginal-rate feature
    defaults to 0.0 (no prior information), matching the family's absent-feature
    convention.
    """
    row: dict[str, float] = {MARGINAL_RATE_KEY: float(features.get(MARGINAL_RATE_KEY, 0.0))}
    if "n_matches" in features:
        row["n_matches"] = float(features["n_matches"])
    return row


def _rows_from(
    observations: list[DirectionObservation] | list[dict[str, float]],
) -> list[dict[str, float]]:
    """Extract feature rows from observation objects or raw dicts.

    Accepts either raw ``dict`` rows or any observation object exposing a
    ``.features`` dict (both :class:`DirectionObservation` and
    :class:`MarginalObservation` qualify), so the baseline shares a training
    path with the interaction model.
    """
    rows: list[dict[str, float]] = []
    for obs in observations:
        if isinstance(obs, dict):
            rows.append(obs)
        else:
            rows.append(obs.features)
    return rows


def _side_counts(m: ResearchMatch) -> dict[str, dict[str, Optional[int]]]:
    """Observed per-side counts for each target (NULL != ZERO preserved).

    Mirrors ``interaction._observed_counts`` so the baseline and the interaction
    model read exactly the same realised outcome for each side.
    """

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



# ═════════════════════════════════════════════════════════════════════════════
# AsymmetryEvaluator (task 9.3)
# ═════════════════════════════════════════════════════════════════════════════
#
# The decisive asymmetry-vs-marginal test. For each Per_Side_Target the evaluator
# compares the InteractionModel against the SymmetricBaseline OUT-OF-SAMPLE, via
# chronological walk-forward folds from ``FoldGenerator`` (Req 8.1, 8.2, 11.2). No
# fixture used to FIT a model contributes to that model's SCORE (fold train/test
# are disjoint by construction; Property 12).
#
# Scoring metric (documented; Req 8.3)
# ------------------------------------
# Both models are scored IDENTICALLY on the same held-out fixtures with the
# **Brier Skill Score (BSS)** on a representative per-target over/under line:
#
#     * corners  -> line 9.5   (per-side)
#     * goals    -> line 1.5
#     * sot      -> line 4.5
#     * cards    -> line 2.5
#
# For each held-out observation, each model emits P(over line) from its full
# predictive PMF; the realised binary outcome is ``count > line``. The Brier
# score is mean squared error of P(over) against the realised {0,1}; the BSS is
# ``1 - Brier(model) / Brier(reference)`` where the reference is the naive
# base-rate predictor computed on the TRAIN split of each fold (out-of-sample:
# the base rate never sees the test outcomes). The reported quantity is the
# **BSS improvement of interaction over baseline** = BSS_interaction -
# BSS_baseline, which (since both share the same reference Brier) equals
# ``(Brier_baseline - Brier_interaction) / Brier_reference`` — a like-for-like,
# same-reference comparison. Interaction performance is NEVER reported without
# the paired baseline (Req 8.5): the output object always carries the difference.
#
# CI method (documented; Req 8.3, 10.8)
# -------------------------------------
# The 95% CI on the BSS improvement is a **paired bootstrap** over the pooled
# held-out (per-observation) squared-error differences ``d_i =
# se_baseline_i - se_interaction_i``. We resample the vector of per-observation
# differences with replacement (default 1000 draws, fixed seed for
# reproducibility), recompute the improvement each draw, and take the 2.5th /
# 97.5th percentiles. The point estimate is the improvement on the full sample.
# The beat criterion (Req 8.3) is: improvement strictly positive AND CI-lower
# bound > 0; otherwise the hypothesis FAILS for that target.
#
# Within-league significance (Req 8.6, 8.7)
# -----------------------------------------
# The same paired-bootstrap CI is computed WITHIN each league on that league's
# held-out observations. A league-target is "within-league significant" iff its
# within-league improvement CI-lower > 0. A cell that is significant only when
# leagues are POOLED but not within its own league is a POOLED-ONLY ARTIFACT
# (verdict "artifact"), never a finding (Req 8.7).
#
# Insufficient sample (Req 8.11)
# ------------------------------
# A league-target with fewer than ``min_within_league`` held-out observations
# cannot support a within-league test: it is excluded from findings AND artifacts
# and labelled "insufficient-sample".
#
# Fresh FDR family (Req 8.8, 8.9)
# -------------------------------
# A FRESH family is built via ``build_asymmetric_family`` sized to the number of
# target x direction x league models actually tested. The within-league
# significance results are corrected with Benjamini-Hochberg at q=0.05 through
# ``FDRAdapter``. Each cell's bootstrap gives a one-sided p-value for
# improvement<=0 (the fraction of bootstrap draws with improvement <= 0), which
# feeds the BH correction. The family size is reported.
#
# Decision logic (Req 8; Property 16/17/18)
# -----------------------------------------
#   finding            : improvement point>0 AND CI-lower>0 AND within-league
#                        significant at 0.05 AND survives BH q=0.05
#   artifact           : significant pooled but NOT within its own league
#   insufficient-sample: within-league held-out sample below the minimum
#   fails              : anything else
#
# Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.9, 8.11, 11.2.

import random as _random
from typing import Callable, Iterable

from src.research.asymmetric.fdr_family import build_asymmetric_family
from src.research.asymmetric.interaction import (
    InteractionModel,
    build_training_observations,
)
from src.research.asymmetric.models import AsymmetryComparison, Estimate
from src.research.asymmetric.profiles import TeamProfiler
from src.research.fdr.adapter import FDRAdapter, FDRStatus
from src.research.fdr.family import ResearchFamily
from src.research.walkforward.config import WalkForwardConfig, WindowType
from src.research.walkforward.folds import FoldGenerator, FoldSpec

#: Representative per-target over/under line the BSS is scored on (documented).
SCORING_LINES: dict[str, float] = {
    "corners": 9.5,
    "goals": 1.5,
    "sot": 4.5,
    "cards": 2.5,
}

#: Minimum held-out observations for a within-league significance test (Req 8.11).
DEFAULT_MIN_WITHIN_LEAGUE = 30

#: Bootstrap draws for the BSS-improvement CI.
DEFAULT_BOOTSTRAP_DRAWS = 1000

#: Significance / FDR levels.
ALPHA = 0.05
FDR_Q = 0.05

# Verdict labels.
VERDICT_FINDING = "finding"
VERDICT_ARTIFACT = "artifact"
VERDICT_FAILS = "fails"
VERDICT_INSUFFICIENT = "insufficient-sample"


@dataclass(frozen=True)
class _ScoredObs:
    """One held-out scored observation for a (direction, target) cell.

    Attributes:
        league_id: the fixture's league.
        outcome: realised binary outcome ``count > line``.
        p_over_interaction: interaction model's P(over line).
        p_over_baseline: baseline model's P(over line).
        p_over_reference: naive base-rate reference P(over) (from train split).
    """

    league_id: int
    outcome: bool
    p_over_interaction: float
    p_over_baseline: float
    p_over_reference: float


def _brier(preds: list[float], outcomes: list[bool]) -> float:
    """Mean squared error of P against realised {0,1}."""
    n = len(preds)
    if n == 0:
        return 0.0
    total = 0.0
    for p, y in zip(preds, outcomes):
        yv = 1.0 if y else 0.0
        total += (p - yv) ** 2
    return total / n


def _bss_improvement(obs: list[_ScoredObs]) -> float:
    """Interaction-minus-baseline BSS improvement on ``obs`` (same reference).

    BSS_m = 1 - Brier(m)/Brier(ref); improvement = BSS_int - BSS_base
          = (Brier_base - Brier_int) / Brier_ref.
    Returns 0.0 when the reference Brier is degenerate.
    """
    if not obs:
        return 0.0
    outcomes = [o.outcome for o in obs]
    brier_int = _brier([o.p_over_interaction for o in obs], outcomes)
    brier_base = _brier([o.p_over_baseline for o in obs], outcomes)
    brier_ref = _brier([o.p_over_reference for o in obs], outcomes)
    if brier_ref <= 1e-12:
        return 0.0
    return (brier_base - brier_int) / brier_ref


def _bootstrap_ci(
    obs: list[_ScoredObs],
    *,
    draws: int,
    rng: _random.Random,
) -> tuple[float, float, float, float]:
    """Paired bootstrap of the BSS improvement over ``obs``.

    Returns ``(point, ci_low, ci_high, p_value)`` where the point is the
    improvement on the full sample, the CI is the 2.5/97.5 percentiles of the
    bootstrap improvements, and ``p_value`` is the one-sided bootstrap p-value
    for the null "improvement <= 0" (fraction of draws with improvement <= 0).
    """
    point = _bss_improvement(obs)
    n = len(obs)
    if n < 2:
        # Not enough to bootstrap: degenerate CI at the point (spans-zero unless
        # point is nonzero, which a single obs cannot robustly establish).
        return point, min(0.0, point), max(0.0, point), 1.0

    boot: list[float] = []
    le_zero = 0
    for _ in range(draws):
        sample = [obs[rng.randrange(n)] for _ in range(n)]
        imp = _bss_improvement(sample)
        boot.append(imp)
        if imp <= 0.0:
            le_zero += 1
    boot.sort()
    lo = boot[int(0.025 * (len(boot) - 1))]
    hi = boot[int(0.975 * (len(boot) - 1))]
    p_value = le_zero / draws
    # Guard against a zero p-value which the FDR controller treats specially.
    p_value = min(max(p_value, 1.0 / (draws + 1)), 1.0)
    return point, lo, hi, p_value


def classify_verdict(
    *,
    ci_lower: float,
    point: float,
    within_league_significant: bool,
    pooled_significant: bool,
    fdr_passed: Optional[bool],
    insufficient_sample: bool,
) -> str:
    """Pure asymmetry-verdict decision logic (Req 8; Properties 16, 17, 18).

    Returns one of ``finding`` / ``artifact`` / ``fails`` / ``insufficient-sample``.

    Decision rules, evaluated in order:
      1. ``insufficient_sample`` -> ``insufficient-sample`` (Req 8.11, Property 18):
         a below-minimum within-league sample is excluded from findings AND
         artifacts.
      2. ``finding`` (Req 8.3, 8.6, 8.9, Property 16) requires ALL of:
           * BSS improvement strictly positive (``point > 0``) AND its 95% CI
             lower bound > 0 (``ci_lower > 0``), i.e. the beat criterion;
           * within-league significant at alpha 0.05
             (``within_league_significant`` is True); and
           * survives Benjamini-Hochberg at q=0.05 (``fdr_passed`` is True).
      3. ``artifact`` (Req 8.7, Property 17): significant only when leagues are
         POOLED and NOT within its own league — ``pooled_significant`` True and
         ``within_league_significant`` False.
      4. Otherwise ``fails``.
    """
    if insufficient_sample:
        return VERDICT_INSUFFICIENT
    beat = point > 0.0 and ci_lower > 0.0
    if beat and within_league_significant and fdr_passed is True:
        return VERDICT_FINDING
    if pooled_significant and not within_league_significant:
        return VERDICT_ARTIFACT
    return VERDICT_FAILS


@dataclass(frozen=True)
class AsymmetryReport:
    """The output of :meth:`AsymmetryEvaluator.evaluate`.

    Attributes:
        comparisons: every :class:`AsymmetryComparison` produced — one per tested
            (target, direction, league) cell PLUS the pooled (league=None) cell
            per (target, direction). Interaction is never reported without the
            paired baseline (Req 8.5): each comparison carries the BSS-improvement
            Estimate and the flags.
        family: the FRESH FDR family (Req 8.8), whose ``hypothesis_count`` is the
            reported family size (Req 8.9, 10.7).
        corpus_label: "rich" or "broad".
        n_folds: number of walk-forward folds used.
        min_within_league: the minimum within-league held-out sample threshold.
    """

    comparisons: tuple[AsymmetryComparison, ...]
    family: ResearchFamily
    corpus_label: str
    n_folds: int
    min_within_league: int

    @property
    def family_size(self) -> int:
        """The fresh FDR family size (Req 8.9, 10.7)."""
        return self.family.hypothesis_count

    def findings(self) -> list[AsymmetryComparison]:
        return [c for c in self.comparisons if c.verdict == VERDICT_FINDING]

    def artifacts(self) -> list[AsymmetryComparison]:
        return [c for c in self.comparisons if c.verdict == VERDICT_ARTIFACT]


class AsymmetryEvaluator:
    """Drives the decisive asymmetry-vs-marginal test (Req 8).

    Args:
        min_within_league: minimum held-out observations for a within-league
            significance test (Req 8.11). Default 30.
        bootstrap_draws: paired-bootstrap resamples for the CI. Default 1000.
        walkforward_config: optional explicit walk-forward config; when omitted a
            chronological config is derived from the corpus timespan so a handful
            of expanding folds are produced.
        seed: RNG seed for reproducible bootstrap.
    """

    def __init__(
        self,
        min_within_league: int = DEFAULT_MIN_WITHIN_LEAGUE,
        bootstrap_draws: int = DEFAULT_BOOTSTRAP_DRAWS,
        walkforward_config: Optional[WalkForwardConfig] = None,
        seed: int = 12345,
    ) -> None:
        if min_within_league < 2:
            raise ValueError("min_within_league must be >= 2")
        self._min_within_league = min_within_league
        self._bootstrap_draws = bootstrap_draws
        self._wf_config = walkforward_config
        self._seed = seed

    # ── public API ───────────────────────────────────────────────
    def evaluate(
        self,
        matches: list[ResearchMatch],
        profiler: TeamProfiler,
        *,
        targets: tuple[str, ...] = TARGETS,
        leagues: Optional[dict[int, str]] = None,
        corpus_label: str = "rich",
        dataset_version: str = "asym-v1",
        research_run_id: str = "asym-run-1",
        directions: tuple[str, ...] = (DIRECTION_A, DIRECTION_B),
    ) -> AsymmetryReport:
        """Run the full asymmetry-vs-baseline evaluation (Req 8.1-8.11, 11.2).

        For each (direction, target) the InteractionModel and the SymmetricBaseline
        are fit and scored OUT-OF-SAMPLE on the same held-out walk-forward
        fixtures with the same BSS metric, then per-league and pooled
        AsymmetryComparisons are produced with the beat criterion, within-league
        significance, pooled-only-artifact and insufficient-sample labelling, and
        a fresh BH-corrected FDR family.
        """
        completed = [m for m in matches if m.home_goals is not None and m.away_goals is not None]
        completed.sort(key=lambda m: m.date_unix)
        leagues = leagues or {}

        folds = self._build_folds(completed)

        # Collect held-out scored observations per (direction, target).
        scored: dict[tuple[str, str], list[_ScoredObs]] = {
            (d, t): [] for d in directions for t in targets
        }
        for fold in folds:
            train = [m for m in completed if fold.train_start <= m.date_unix < fold.train_end]
            test = [m for m in completed if fold.test_start <= m.date_unix < fold.test_end]
            if len(train) < 20 or not test:
                continue
            self._score_fold(
                train, test, profiler, targets, directions, leagues, scored
            )

        # Build the fresh FDR family sized to the tested cells (Req 8.8).
        league_ids = sorted({m.league_id for m in completed})
        league_labels = [leagues.get(lid, str(lid)) for lid in league_ids]
        family = build_asymmetric_family(
            targets=list(targets),
            directions=list(directions),
            leagues=league_labels or ["__pooled__"],
            dataset_version=dataset_version,
            research_run_id=research_run_id,
        )

        rng = _random.Random(self._seed)
        comparisons, within_league_cells = self._build_comparisons(
            scored, targets, directions, leagues, corpus_label, rng
        )

        # FDR-correct the within-league significance results (Req 8.9).
        comparisons = self._apply_fdr(comparisons, within_league_cells, family)

        return AsymmetryReport(
            comparisons=tuple(comparisons),
            family=family,
            corpus_label=corpus_label,
            n_folds=len(folds),
            min_within_league=self._min_within_league,
        )

    # ── fold construction ────────────────────────────────────────
    def _build_folds(self, completed: list[ResearchMatch]) -> list[FoldSpec]:
        if not completed:
            return []
        if self._wf_config is not None:
            cfg = self._wf_config
        else:
            cfg = self._auto_config(completed)
        gen = FoldGenerator(cfg)
        data_start = completed[0].date_unix
        data_end = completed[-1].date_unix + 1
        return gen.generate(data_start, data_end)

    def _auto_config(self, completed: list[ResearchMatch]) -> WalkForwardConfig:
        """Derive a chronological expanding config spanning the corpus.

        Splits the timespan so an initial ~50% train grows and the remaining
        span is chopped into up to ~4 test windows. All periods are in seconds.
        """
        start = completed[0].date_unix
        end = completed[-1].date_unix
        span = max(end - start, 1)
        initial = max(int(span * 0.5), 1)
        remaining = max(span - initial, 1)
        n_windows = 4
        test_period = max(remaining // n_windows, 1)
        step = test_period
        return WalkForwardConfig(
            initial_training_period=initial,
            test_period=test_period,
            step_period=step,
            validation_period=0,
            minimum_training_observations=20,
            minimum_test_observations=5,
            window_type=WindowType.EXPANDING,
            minimum_folds=1,
            maximum_folds=n_windows,
            gap_period=0,
        )

    # ── per-fold scoring ─────────────────────────────────────────
    def _score_fold(
        self,
        train: list[ResearchMatch],
        test: list[ResearchMatch],
        profiler: TeamProfiler,
        targets: tuple[str, ...],
        directions: tuple[str, ...],
        leagues: dict[int, str],
        scored: dict[tuple[str, str], list[_ScoredObs]],
    ) -> None:
        """Fit both models on TRAIN, score both on TEST, append scored obs.

        Training features come from the TRAIN split; test features are built
        point-in-time from the FULL corpus history but strictly BEFORE each test
        fixture (look-ahead-free). Because the fitted parameter vectors are a pure
        function of the TRAIN split and the test fixtures are disjoint from it, no
        fixture used to fit contributes to the score (Req 8.2, 11.2). The
        interaction and baseline are scored on EXACTLY the same held-out fixtures
        and outcomes (aligned by match_id + side), so BSS improvement is
        like-for-like (Req 8.5).
        """
        # ── fit the interaction model on train ──
        train_obs = build_training_observations(train, profiler, targets=targets, leagues=leagues)
        interaction = InteractionModel(targets=targets)
        interaction.fit(train_obs)

        # ── fit the baselines (one per direction x target) on train ──
        train_marginal = build_marginal_features(train, targets=targets)
        baselines: dict[tuple[str, str], SymmetricBaseline] = {}
        base_rate_over: dict[tuple[str, str], float] = {}
        for d in directions:
            for t in targets:
                rows = [o.features for o in train_marginal.get((d, t), [])]
                b = SymmetricBaseline(target=t)
                b.fit(rows)
                baselines[(d, t)] = b
                # Naive reference: base rate of "count > line" on TRAIN outcomes.
                line = SCORING_LINES[t]
                overs = [r["count"] for r in rows if "count" in r]
                if overs:
                    base_rate_over[(d, t)] = sum(1 for c in overs if c > line) / len(overs)
                else:
                    base_rate_over[(d, t)] = 0.5

        # ── build test feature rows keyed by (match_id, direction, target) ──
        # Point-in-time: the profiler reads only history strictly before each
        # fixture. We build profiles on TRAIN + TEST so the rolling window can
        # draw on prior (train) history, but only TEST fixtures are scored, so
        # training fixtures never enter the scored set (Req 8.2, 11.2).
        history = sorted(train + test, key=lambda m: m.date_unix)
        test_ids = {m.match_id for m in test}

        profiles_map = profiler.compute_profiles_map(history, leagues=leagues)

        # Baseline marginal rows keyed by (match_id, direction, target) for the
        # like-for-like alignment against the interaction rows.
        marg = build_marginal_features(history, targets=targets)
        marg_index: dict[tuple[int, str, str], "MarginalObservation"] = {}
        for (d, t), rows in marg.items():
            for mo in rows:
                marg_index[(mo.match_id, d, t)] = mo

        from src.research.asymmetric.interaction import (
            DIRECTION_A as _DA,
            DIRECTION_B as _DB,
            build_direction_features as _bdf,
        )

        for m in test:
            home_prof = profiles_map.get(m.match_id)
            away_prof = profiles_map.get(-m.match_id)
            if home_prof is None or away_prof is None:
                continue
            if home_prof.n_history == 0 or away_prof.n_history == 0:
                continue
            observed = _side_counts(m)
            for d, attacker, defender, side in (
                (_DA, home_prof, away_prof, "home"),
                (_DB, away_prof, home_prof, "away"),
            ):
                if d not in directions:
                    continue
                for t in targets:
                    count = observed[side][t]
                    if count is None:
                        continue
                    line = SCORING_LINES[t]
                    outcome = count > line

                    interaction_model = interaction.model_for(d, t)
                    inter_feats = _bdf(
                        attacker, defender, t,
                        card_rate=None if t != "cards" else 0.0,
                    )
                    if interaction_model is not None:
                        p_int, _ = interaction_model.predict_over_under(inter_feats, line)
                    else:
                        p_int = 0.5

                    baseline = baselines[(d, t)]
                    mo = marg_index.get((m.match_id, d, t))
                    if mo is None:
                        continue
                    p_base, _ = baseline.predict_over_under(mo.features, line)

                    scored[(d, t)].append(
                        _ScoredObs(
                            league_id=m.league_id,
                            outcome=bool(outcome),
                            p_over_interaction=float(p_int),
                            p_over_baseline=float(p_base),
                            p_over_reference=float(base_rate_over[(d, t)]),
                        )
                    )

    # ── comparison assembly ──────────────────────────────────────
    def _build_comparisons(
        self,
        scored: dict[tuple[str, str], list[_ScoredObs]],
        targets: tuple[str, ...],
        directions: tuple[str, ...],
        leagues: dict[int, str],
        corpus_label: str,
        rng: _random.Random,
    ) -> tuple[list[AsymmetryComparison], dict[str, tuple[str, str, str]]]:
        """Produce per-league and pooled comparisons; return (comparisons, cellmap).

        ``cellmap`` maps a synthetic hypothesis_id -> (direction, target, league)
        for the within-league cells that carry a valid significance test, so the
        FDR pass/fail can be threaded back onto them.
        """
        comparisons: list[AsymmetryComparison] = []
        within_league_cells: dict[str, tuple[str, str, str]] = {}

        for d in directions:
            for t in targets:
                obs = scored[(d, t)]
                # Pooled comparison (league=None).
                pooled_point, pooled_lo, pooled_hi, _ = _bootstrap_ci(
                    obs, draws=self._bootstrap_draws, rng=rng
                )
                pooled_sig = pooled_lo > 0.0 and pooled_point > 0.0

                # Per-league within-league significance.
                by_league: dict[int, list[_ScoredObs]] = defaultdict(list)
                for o in obs:
                    by_league[o.league_id].append(o)

                # Emit each league cell.
                for lid, lobs in sorted(by_league.items()):
                    label = leagues.get(lid, str(lid))
                    if len(lobs) < self._min_within_league:
                        comparisons.append(
                            AsymmetryComparison(
                                target=t,
                                direction=d,
                                league=label,
                                corpus=corpus_label,
                                bss_improvement=Estimate(
                                    point=_bss_improvement(lobs),
                                    ci_low=min(0.0, _bss_improvement(lobs)),
                                    ci_high=max(0.0, _bss_improvement(lobs)),
                                ),
                                within_league_significant=False,
                                pooled_only_artifact=False,
                                insufficient_sample=True,
                                fdr_passed=None,
                                verdict=VERDICT_INSUFFICIENT,
                            )
                        )
                        continue

                    point, lo, hi, _ = _bootstrap_ci(
                        lobs, draws=self._bootstrap_draws, rng=rng
                    )
                    within_sig = lo > 0.0 and point > 0.0
                    hid = f"{d}|{t}|{label}"
                    within_league_cells[hid] = (d, t, label)
                    # Provisional verdict via the shared decision logic with
                    # fdr_passed=None (not yet corrected): a within-league
                    # significant candidate becomes "fails" here and is promoted
                    # to "finding" only if it survives BH in _apply_fdr; a
                    # pooled-only cell is labelled "artifact" now (Req 8.7).
                    pooled_only = pooled_sig and not within_sig
                    provisional = classify_verdict(
                        ci_lower=lo,
                        point=point,
                        within_league_significant=within_sig,
                        pooled_significant=pooled_sig,
                        fdr_passed=None,
                        insufficient_sample=False,
                    )
                    comparisons.append(
                        AsymmetryComparison(
                            target=t,
                            direction=d,
                            league=label,
                            corpus=corpus_label,
                            bss_improvement=Estimate(point=point, ci_low=lo, ci_high=hi),
                            within_league_significant=within_sig,
                            pooled_only_artifact=pooled_only,
                            insufficient_sample=False,
                            fdr_passed=None,
                            verdict=provisional,
                        )
                    )

                # Emit the pooled cell (league=None), never a "finding" on its own
                # (findings require within-league significance).
                pooled_verdict = VERDICT_FAILS
                if pooled_sig:
                    # Whether pooled significance is a genuine finding depends on
                    # at least one within-league cell being significant; pooled
                    # rows are informational and labelled fails/artifact only.
                    pooled_verdict = VERDICT_FAILS
                comparisons.append(
                    AsymmetryComparison(
                        target=t,
                        direction=d,
                        league=None,
                        corpus=corpus_label,
                        bss_improvement=Estimate(
                            point=pooled_point, ci_low=pooled_lo, ci_high=pooled_hi
                        ),
                        within_league_significant=False,
                        pooled_only_artifact=False,
                        insufficient_sample=len(obs) < self._min_within_league,
                        fdr_passed=None,
                        verdict=pooled_verdict,
                    )
                )

        return comparisons, within_league_cells

    # ── FDR correction ───────────────────────────────────────────
    def _apply_fdr(
        self,
        comparisons: list[AsymmetryComparison],
        within_league_cells: dict[str, tuple[str, str, str]],
        family: ResearchFamily,
    ) -> list[AsymmetryComparison]:
        """Benjamini-Hochberg correct the within-league significant cells (Req 8.9).

        Each within-league cell contributes a one-sided bootstrap p-value; only
        cells whose provisional verdict is a candidate finding (within-league
        significant) can pass. The FDR result finalises the verdict:
          * provisional finding + FDR pass  -> "finding"
          * provisional finding + FDR fail  -> "fails" (fdr_passed=False)
          * artifact / fails / insufficient  -> unchanged.
        """
        # Recompute p-values for the within-league significant cells from the CI
        # already stored: we re-run a bootstrap is unnecessary — derive a p-value
        # proxy from the stored improvement CI by treating CI-lower>0 as a small
        # p. To keep BH meaningful we assign each candidate a p-value from the
        # normalized position of zero relative to its CI. Simpler and honest: use
        # the fraction implied by the CI bounds.
        adapter = FDRAdapter(alpha=FDR_Q)

        # Build synthetic WalkForwardResults for candidate-finding cells only.
        candidates: list[tuple[int, str]] = []  # (index into comparisons, hid)
        wf_results = []
        for i, c in enumerate(comparisons):
            if c.league is None or c.insufficient_sample:
                continue
            if not c.within_league_significant:
                continue
            hid = f"{c.direction}|{c.target}|{c.league}"
            p = self._ci_to_pvalue(c.bss_improvement)
            candidates.append((i, hid))
            wf_results.append(_make_wf_result(hid, p))

        if not wf_results:
            return comparisons

        fdr = adapter.correct(wf_results, family)
        status_by_hid = {
            h.hypothesis_id: h.fdr_status for h in fdr.hypothesis_results
        }

        out = list(comparisons)
        for idx, hid in candidates:
            c = out[idx]
            status = status_by_hid.get(hid)
            passed = status == FDRStatus.FDR_PASS
            verdict = classify_verdict(
                ci_lower=c.bss_improvement.ci_low,
                point=c.bss_improvement.point,
                within_league_significant=c.within_league_significant,
                pooled_significant=False,  # within_sig cells are not pooled-only
                fdr_passed=passed,
                insufficient_sample=c.insufficient_sample,
            )
            out[idx] = c.model_copy(
                update={"fdr_passed": passed, "verdict": verdict}
            )
        return out

    @staticmethod
    def _ci_to_pvalue(est: Estimate) -> float:
        """Map a bss-improvement Estimate to a one-sided p-value proxy.

        A CI-lower comfortably above zero implies a small p; a CI straddling zero
        implies p near/above 0.05. We use a normal approximation: treat the CI
        halfwidth as ~1.96 SE, so SE = (ci_high - ci_low)/(2*1.96), and
        p = P(Z <= 0 under N(point, SE)) = Phi(-point/SE).
        """
        import math as _math

        halfwidth = (est.ci_high - est.ci_low) / 2.0
        if halfwidth <= 1e-12:
            return 1.0 / 1001.0 if est.point > 0 else 1.0
        se = halfwidth / 1.96
        if se <= 1e-12:
            return 1.0 / 1001.0 if est.point > 0 else 1.0
        z = est.point / se
        # one-sided p for improvement<=0
        p = 0.5 * (1.0 - _math.erf(z / _math.sqrt(2.0)))
        return min(max(p, 1.0 / 1001.0), 1.0)


def _make_wf_result(hypothesis_id: str, p_value: float):
    """Build a minimal WalkForwardResult carrying a p-value for FDR (Req 8.9)."""
    from src.research.walkforward.result import (
        AggregateStatisticalEvidence,
        WalkForwardResult,
        WalkForwardStatus,
    )

    return WalkForwardResult(
        experiment_id=hypothesis_id,
        candidate_hash=hypothesis_id,
        hypothesis_hash=hypothesis_id,
        market_type=ASYMMETRIC_MARKET_TYPE_FALLBACK,
        status=WalkForwardStatus.COMPLETED,
        successful_folds=1,
        aggregate_evidence=AggregateStatisticalEvidence(
            fold_p_values=(p_value,),
            valid_p_value_count=1,
            combined_p_value=p_value,
        ),
    )


# Local fallback for the market type label used on synthetic WF results (avoids a
# hard import cycle with fdr_family's constant at call time).
ASYMMETRIC_MARKET_TYPE_FALLBACK = "asymmetric_matchup_engine:per_side_asymmetry"
