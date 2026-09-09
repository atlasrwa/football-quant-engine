"""Tests for provider reconciliation policies.

Central invariant: the reconciler NEVER selects the numerically larger value.
"""

from __future__ import annotations

from src.research.observation import MISSING, ObservationKey, ProviderObservation
from src.research.reconciliation import (
    ReconciledField,
    Reconciler,
    ReconciliationPolicy,
    SelectionOutcome,
)


def _obs(source, value, pid, support=None):
    return ProviderObservation(
        key=ObservationKey("fx", "avg_corners"),
        source=source, provider_entity_id=pid, value=value,
        observed_at=100, support=support,
    )


def _inputs(fs=4.8, tsa=6.2):
    return {
        "footystats": _obs("footystats", fs, "251", support=10),
        "thestatsapi": _obs("thestatsapi", tsa, "tm_5290", support=12),
    }


class TestNeverPicksMax:
    def test_footystats_only_returns_footystats_not_larger(self):
        r = Reconciler(ReconciliationPolicy.FOOTYSTATS_ONLY).reconcile("avg_corners", _inputs())
        assert r.value == 4.8 and r.source == "footystats"

    def test_thestatsapi_only_returns_thestatsapi_by_policy_not_magnitude(self):
        # It returns 6.2, but ONLY because the policy says THESTATSAPI_ONLY —
        # the same reconciler returns the SMALLER value if the smaller is TSA.
        r = Reconciler(ReconciliationPolicy.THESTATSAPI_ONLY).reconcile("avg_corners", _inputs())
        assert r.value == 6.2 and r.source == "thestatsapi"
        r2 = Reconciler(ReconciliationPolicy.THESTATSAPI_ONLY).reconcile(
            "avg_corners", _inputs(fs=9.9, tsa=1.1))
        assert r2.value == 1.1  # smaller, proving magnitude is irrelevant

    def test_preferred_returns_preferred_regardless_of_magnitude(self):
        r = Reconciler(
            ReconciliationPolicy.PREFERRED_PROVIDER_WITH_FALLBACK, preferred="footystats"
        ).reconcile("avg_corners", _inputs())
        assert r.value == 4.8  # smaller, but preferred

    def test_disagreement_always_measurable(self):
        r = Reconciler(ReconciliationPolicy.FOOTYSTATS_ONLY).reconcile("avg_corners", _inputs())
        assert abs(r.disagreement - 1.4) < 1e-9


class TestValidatedBlend:
    def test_refuses_to_blend_on_disagreement(self):
        r = Reconciler(
            ReconciliationPolicy.VALIDATED_BLEND, blend_abs_tolerance=0.5
        ).reconcile("avg_corners", _inputs())  # 4.8 vs 6.2, diff 1.4 > 0.5
        assert r.value is MISSING
        assert r.outcome == SelectionOutcome.DISAGREEMENT_UNRESOLVED
        assert abs(r.disagreement - 1.4) < 1e-9

    def test_blends_within_tolerance(self):
        r = Reconciler(
            ReconciliationPolicy.VALIDATED_BLEND, blend_abs_tolerance=0.5
        ).reconcile("avg_corners", _inputs(fs=5.0, tsa=5.1))
        assert r.outcome == SelectionOutcome.BLENDED
        assert abs(r.value - 5.05) < 1e-9
        assert r.source == "blend"


class TestFallbackRespectsNullVsMissing:
    def test_observed_none_does_not_fall_back(self):
        inputs = {
            "footystats": _obs("footystats", None, "251"),  # observed-absent
            "thestatsapi": _obs("thestatsapi", 6.2, "tm_5290"),
        }
        r = Reconciler(
            ReconciliationPolicy.PREFERRED_PROVIDER_WITH_FALLBACK, preferred="footystats"
        ).reconcile("avg_corners", inputs)
        # Preferred provider observed absence -> respected, no fallback.
        assert r.value is None and r.source == "footystats"
        assert r.outcome == SelectionOutcome.SELECTED

    def test_true_missing_falls_back(self):
        inputs = {"thestatsapi": _obs("thestatsapi", 6.2, "tm_5290")}  # fs absent entirely
        r = Reconciler(
            ReconciliationPolicy.PREFERRED_PROVIDER_WITH_FALLBACK, preferred="footystats"
        ).reconcile("avg_corners", inputs)
        assert r.value == 6.2 and r.source == "thestatsapi"
        assert r.outcome == SelectionOutcome.FELL_BACK

    def test_no_value_when_nothing_present(self):
        r = Reconciler(
            ReconciliationPolicy.PREFERRED_PROVIDER_WITH_FALLBACK
        ).reconcile("avg_corners", {})
        assert r.value is MISSING and r.outcome == SelectionOutcome.NO_VALUE


class TestDevig:
    def test_two_way_sums_to_one(self):
        from src.research.reconciliation.devig import devig
        res = devig({"OVER": 1.80, "UNDER": 2.00})
        assert abs(sum(res.fair_probabilities.values()) - 1.0) < 1e-9
        assert res.margin > 0

    def test_three_way_sums_to_one(self):
        from src.research.reconciliation.devig import devig
        res = devig({"HOME": 1.55, "DRAW": 4.2, "AWAY": 5.5})
        assert abs(sum(res.fair_probabilities.values()) - 1.0) < 1e-9

    def test_invalid_odds_rejected(self):
        import pytest
        from src.research.reconciliation.devig import devig
        with pytest.raises(ValueError):
            devig({"OVER": 0.5, "UNDER": 2.0})
