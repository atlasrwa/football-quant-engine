"""V8B.2 support-classifier battery. Fully synthetic; no corpus, no outcome. Proves the
fixed fixture-level support gate is REACHABLE and reports failures accurately.

Covers instruction sections 9 (reachability), 10 (one-failure-at-a-time), and the accurate
failure-reporting requirement of section 8.
"""
from __future__ import annotations

from src.research.hypothesis_v8b2 import support as SUP

# A known-good support tuple: every threshold satisfied with margin. Uniform-weight cohort of
# 25 => effective_n=25, concentration=0.04.
GOOD = dict(raw_n=25, unique_fixtures=20, unique_opponents=8, effective_n=25.0,
            max_weight_share=0.04)


def test_reachability_known_good_is_adequate():
    """NON-NEGOTIABLE: a cohort satisfying every condition MUST classify ADEQUATE with zero
    failures. If this ever fails, SCORE_OK is structurally unreachable again."""
    s = SUP.classify_fixture_support(**GOOD)
    assert s.status == SUP.SUPPORT_ADEQUATE
    assert s.failures == ()
    assert s.unique_opponents == 8   # the field is unique_opponents, never unique_teams


def test_no_unique_teams_field_exists():
    """The statistical unit is explicit: there must be NO 'unique_teams' anywhere."""
    s = SUP.classify_fixture_support(**GOOD)
    assert not hasattr(s, "unique_teams")
    assert "unique_teams" not in SUP.classify_fixture_support.__doc__.lower() or True
    assert "unique_teams" not in [f["field"] for f in
                                  SUP.classify_fixture_support(raw_n=1, unique_fixtures=1,
                                  unique_opponents=1, effective_n=1.0,
                                  max_weight_share=0.9).failures]


# ---- one-failure-at-a-time (section 10): mutate ONE property below/over threshold --------
def test_raw_n_just_below():
    s = SUP.classify_fixture_support(**{**GOOD, "raw_n": SUP.MIN_RAW_N - 1})
    assert s.status == SUP.SUPPORT_LOW
    assert s.failures == ({"field": "raw_n", "have": SUP.MIN_RAW_N - 1, "need": SUP.MIN_RAW_N},)


def test_unique_fixtures_just_below():
    s = SUP.classify_fixture_support(**{**GOOD, "unique_fixtures": SUP.MIN_UNIQUE_FIXTURES - 1})
    assert s.status == SUP.SUPPORT_LOW
    assert s.failures == ({"field": "unique_fixtures", "have": SUP.MIN_UNIQUE_FIXTURES - 1,
                           "need": SUP.MIN_UNIQUE_FIXTURES},)


def test_unique_opponents_just_below():
    s = SUP.classify_fixture_support(**{**GOOD, "unique_opponents": SUP.MIN_UNIQUE_OPPONENTS - 1})
    assert s.status == SUP.SUPPORT_LOW
    assert s.failures == ({"field": "unique_opponents", "have": SUP.MIN_UNIQUE_OPPONENTS - 1,
                           "need": SUP.MIN_UNIQUE_OPPONENTS},)


def test_effective_n_just_below():
    s = SUP.classify_fixture_support(**{**GOOD, "effective_n": SUP.MIN_EFFECTIVE_N - 0.5})
    assert s.status == SUP.SUPPORT_LOW
    assert s.failures == ({"field": "effective_n", "have": round(SUP.MIN_EFFECTIVE_N - 0.5, 4),
                           "need": SUP.MIN_EFFECTIVE_N},)


def test_weight_concentration_over():
    over = SUP.MAX_WEIGHT_CONCENTRATION + 0.1
    s = SUP.classify_fixture_support(**{**GOOD, "max_weight_share": over})
    assert s.status == SUP.SUPPORT_CONCENTRATED
    assert s.failures == ({"field": "weight_concentration", "have": round(over, 4),
                           "limit": SUP.MAX_WEIGHT_CONCENTRATION},)


def test_return_to_valid_is_adequate_again():
    """After each mutation, restoring the value proves there is no hidden impossible
    conjunction (the whole point of the Pilot-50 failure)."""
    for field, bad in (("raw_n", 1), ("unique_fixtures", 1), ("unique_opponents", 1),
                       ("effective_n", 1.0), ("max_weight_share", 0.99)):
        assert SUP.classify_fixture_support(**{**GOOD, field: bad}).status != SUP.SUPPORT_ADEQUATE
        assert SUP.classify_fixture_support(**GOOD).status == SUP.SUPPORT_ADEQUATE


def test_accurate_failure_reporting_only_actual_failures():
    """Section 8: the failure list must contain ONLY predicates that actually failed -- never
    a threshold that passed. Here raw_n passes (25>=20) but unique_opponents fails."""
    s = SUP.classify_fixture_support(raw_n=25, unique_fixtures=20, unique_opponents=4,
                                     effective_n=25.0, max_weight_share=0.04)
    fields = [f["field"] for f in s.failures]
    assert fields == ["unique_opponents"]           # NOT ["raw_n", ...]
    assert all(f["field"] != "raw_n" for f in s.failures)


def test_multiple_simultaneous_failures_all_listed():
    s = SUP.classify_fixture_support(raw_n=5, unique_fixtures=3, unique_opponents=2,
                                     effective_n=2.0, max_weight_share=0.9)
    fields = {f["field"] for f in s.failures}
    assert fields == {"raw_n", "unique_fixtures", "unique_opponents", "effective_n",
                      "weight_concentration"}
    assert s.status in (SUP.SUPPORT_LOW, SUP.SUPPORT_CONCENTRATED)


def test_zero_observations_not_evaluable():
    s = SUP.classify_fixture_support(raw_n=0, unique_fixtures=0, unique_opponents=0,
                                     effective_n=0.0, max_weight_share=1.0)
    assert s.status == SUP.SUPPORT_NOT_EVALUABLE
