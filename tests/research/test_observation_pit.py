"""Tests for the observation model and point-in-time safety."""

from __future__ import annotations

from src.research.observation import (
    MISSING,
    ObservationKey,
    ObservationStore,
    ProviderObservation,
)


def _obs(concept, value, observed_at, source="footystats", retrieved_at=None, pid="1"):
    return ProviderObservation(
        key=ObservationKey("fx", concept),
        source=source,
        provider_entity_id=pid,
        value=value,
        observed_at=observed_at,
        retrieved_at=retrieved_at,
    )


class TestMissingnessSemantics:
    def test_missing_none_zero_distinct(self):
        missing = _obs("x", MISSING, 100)
        none_obs = _obs("x", None, 100)
        zero_obs = _obs("x", 0, 100)
        assert not missing.has_value
        assert none_obs.has_value and none_obs.is_null
        assert zero_obs.has_value and not zero_obs.is_null and zero_obs.value == 0


class TestAsOfPointInTime:
    def test_later_retrieval_cannot_rewrite_history(self):
        store = ObservationStore()
        k = ObservationKey("fx", "total_corners")
        store.append(_obs("total_corners", 9, observed_at=100, retrieved_at=100))
        # Revised value observed at 400 but only retrieved at 500.
        store.append(_obs("total_corners", 11, observed_at=400, retrieved_at=500))
        # As of cutoff 200, only the value available then (9) may be returned.
        assert store.as_of(k, 200).value == 9
        # As of 450, the revised value is now legitimately available.
        assert store.as_of(k, 450).value == 11

    def test_future_observation_excluded(self):
        store = ObservationStore()
        k = ObservationKey("fx", "goals")
        store.append(_obs("goals", 3, observed_at=1000))
        assert store.as_of(k, 500) is None  # observed after cutoff

    def test_append_only_history_retained(self):
        store = ObservationStore()
        k = ObservationKey("fx", "c")
        store.append(_obs("c", 1, observed_at=100))
        store.append(_obs("c", 2, observed_at=200))
        assert len(store.history(k)) == 2

    def test_append_idempotent(self):
        store = ObservationStore()
        o = _obs("c", 1, observed_at=100)
        assert store.append(o) is True
        assert store.append(o) is False

    def test_missing_observed_at_fails_safe(self):
        store = ObservationStore()
        k = ObservationKey("fx", "c")
        store.append(_obs("c", 5, observed_at=None))
        # Cannot prove availability -> excluded from finite cutoff.
        assert store.as_of(k, 1000) is None
        # No-restriction cutoff (None) returns it.
        assert store.as_of(k, None) is not None

    def test_as_of_by_source(self):
        store = ObservationStore()
        k = ObservationKey("fx", "avg")
        store.append(_obs("avg", 4.8, observed_at=100, source="footystats"))
        store.append(_obs("avg", 6.2, observed_at=100, source="thestatsapi"))
        by_src = store.as_of_by_source(k, 200)
        assert set(by_src) == {"footystats", "thestatsapi"}
        assert by_src["footystats"].value == 4.8
        assert by_src["thestatsapi"].value == 6.2
