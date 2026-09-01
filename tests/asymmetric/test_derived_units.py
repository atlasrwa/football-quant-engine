"""Unit tests: derive-don't-model and reported correlation constants (task 6.5).

Two assertions grounded in the requirements:

  * Req 2.10 — no Derived_Outcome is modelled directly: the
    :class:`DerivedOutcomeCombiner` only *consumes* per-side
    :class:`DirectionPrediction` objects and has NO ``fit`` / training method.
  * Req 3.4 — the measured Correlation_Structure constants (cards x corners
    -0.033, cards x goals -0.030, corners x goals -0.028) and the +/-0.016 95%
    CI are reported alongside any correlation comparison.

These are example-based ``pytest`` tests (not property tests).
"""

from __future__ import annotations

import inspect

from src.research.asymmetric import derived as derived_module
from src.research.asymmetric.correlation import (
    CARDS_CORNERS_CORR,
    CARDS_GOALS_CORR,
    CORNERS_GOALS_CORR,
    CORRELATION_CI_HALFWIDTH,
    PAIR_CARDS_CORNERS,
    PAIR_CARDS_GOALS,
    PAIR_CORNERS_GOALS,
    compare_correlation_structure,
)
from src.research.asymmetric.derived import (
    INDEPENDENCE_ASSUMPTION,
    DerivedOutcomeCombiner,
)
from src.research.asymmetric.interaction import DIRECTION_A, DIRECTION_B
from src.research.asymmetric.models import DirectionPrediction


# ─────────────────────────────────────────────────────────────────────────────
# Req 2.10 — derive, don't model
# ─────────────────────────────────────────────────────────────────────────────


def test_combiner_has_no_fit_or_training_method():
    """The combiner consumes per-side predictions only; it has no fit/train (Req 2.10)."""
    combiner = DerivedOutcomeCombiner()
    for forbidden in ("fit", "train", "partial_fit", "learn"):
        assert not hasattr(combiner, forbidden), (
            f"DerivedOutcomeCombiner must not expose a {forbidden!r} method — "
            f"derived outcomes are combined, never modelled directly (Req 2.10)"
        )


def test_combine_signature_consumes_direction_predictions_only():
    """combine() takes a list of DirectionPredictions (per-side inputs) (Req 2.10)."""
    sig = inspect.signature(DerivedOutcomeCombiner.combine)
    params = list(sig.parameters)
    # self, directions, then keyword-only correlation hooks.
    assert params[0] == "self"
    assert params[1] == "directions"


def test_derived_module_defines_no_model_class():
    """The derived module contains no ProbabilityModel subclass (no direct modelling)."""
    from src.research.probability import ProbabilityModel

    for _name, obj in inspect.getmembers(derived_module, inspect.isclass):
        if obj is ProbabilityModel:
            continue
        assert not issubclass(obj, ProbabilityModel), (
            f"{_name} models a derived outcome directly, violating Req 2.10"
        )


def _dp(direction: str, target: str, dist: tuple[float, ...]) -> DirectionPrediction:
    return DirectionPrediction(
        direction=direction,
        attacker="H" if direction == DIRECTION_A else "A",
        defender="A" if direction == DIRECTION_A else "H",
        target=target,
        distribution=dist,
        expected_value=1.0,
        driving_features=("f",),
    )


def _eight_predictions() -> list[DirectionPrediction]:
    corners = (0.1, 0.2, 0.3, 0.2, 0.2)
    cards = (0.3, 0.4, 0.3)
    goals = (0.4, 0.35, 0.25)
    return [
        _dp(DIRECTION_A, "corners", corners),
        _dp(DIRECTION_B, "corners", corners),
        _dp(DIRECTION_A, "cards", cards),
        _dp(DIRECTION_B, "cards", cards),
        _dp(DIRECTION_A, "goals", goals),
        _dp(DIRECTION_B, "goals", goals),
    ]


def test_combine_emits_independence_assumption_text():
    """The stated independence assumption is available to carry on FixturePrediction (Req 3.1)."""
    combiner = DerivedOutcomeCombiner()
    assert combiner.independence_assumption == INDEPENDENCE_ASSUMPTION
    assert "independent" in INDEPENDENCE_ASSUMPTION.lower()
    assert "convolution" in INDEPENDENCE_ASSUMPTION.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Req 3.4 — measured constants + CI reported alongside the comparison
# ─────────────────────────────────────────────────────────────────────────────


def test_measured_constants_have_expected_values():
    """The measured Correlation_Structure constants match the audit (Req 3.2, 3.4)."""
    assert CARDS_CORNERS_CORR == -0.033
    assert CARDS_GOALS_CORR == -0.030
    assert CORNERS_GOALS_CORR == -0.028
    assert CORRELATION_CI_HALFWIDTH == 0.016


def test_combine_attaches_measured_correlations_and_cis():
    """combine() attaches measured values + CIs to every DerivedOutcomes (Req 3.4)."""
    combiner = DerivedOutcomeCombiner()
    outcomes = combiner.combine(_eight_predictions())

    assert outcomes.measured_correlations[PAIR_CARDS_CORNERS] == (
        -0.033, 0.016,
    )
    assert outcomes.measured_correlations[PAIR_CARDS_GOALS] == (-0.030, 0.016)
    assert outcomes.measured_correlations[PAIR_CORNERS_GOALS] == (-0.028, 0.016)
    # Implied correlations reported for every covered pair (independence -> ~0).
    assert set(outcomes.implied_correlations) == {
        PAIR_CARDS_CORNERS, PAIR_CARDS_GOALS, PAIR_CORNERS_GOALS,
    }
    # Near-zero implied correlations do not trip the red flag.
    assert outcomes.correlation_red_flags == ()


def test_combine_attaches_precomputed_correlation_result():
    """A precomputed correlation comparison is attached verbatim (Req 3.3, 3.4)."""
    combiner = DerivedOutcomeCombiner()
    corr = compare_correlation_structure({PAIR_CARDS_CORNERS: 0.5})
    outcomes = combiner.combine(_eight_predictions(), correlation=corr)
    assert outcomes.implied_correlations[PAIR_CARDS_CORNERS] == 0.5
    assert len(outcomes.correlation_red_flags) == 1


def test_describe_reports_measured_and_ci():
    """Each comparison's describe() line reports measured value and CI (Req 3.4)."""
    corr = compare_correlation_structure()
    for cmp in corr.comparisons:
        text = cmp.describe()
        assert "measured=" in text
        assert "CI" in text
