"""Structural anti-outcome-leak tests for the selectivity-test selectors.

Mirrors the feature anti-leak discipline (tests/test_prior_only_features.py) but for
the SELECTION rules: a selector may read ONLY strictly-prior context; a selector that
touches the fixture's outcome must RAISE.
"""
import sys
import pytest

sys.path.insert(0, "/home/ubuntu"); sys.path.insert(0, "/home/ubuntu/scripts")

from selectivity_test import (
    SelectionContext, make_rules, assert_selector_prior_only,
    _FORBIDDEN_CTX_ATTRS, RULE_NAMES,
)


def _ctx(**kw):
    d = dict(home_prior_n=8, away_prior_n=9, home_rate=5.0, away_rate=3.0,
             home_var=1.0, away_var=2.0, p_over=0.6, base=0.5,
             season_index=20, season_len=46)
    d.update(kw)
    return SelectionContext(**d)


def _rules():
    thresholds = {"var_lo_tercile": 2.0, "gap_hi_tercile": 1.5}
    return make_rules(thresholds, conf_hi=0.05)


def test_all_preregistered_rules_are_prior_only():
    """Every pre-registered selector passes the structural guard (reads only
    prior-only attributes, never the outcome)."""
    rules = _rules()
    assert set(rules) == set(RULE_NAMES)
    ctx = _ctx()
    for name, rule in rules.items():
        assert_selector_prior_only(rule, ctx)  # must not raise


@pytest.mark.parametrize("bad_attr", sorted(_FORBIDDEN_CTX_ATTRS))
def test_selector_touching_outcome_raises(bad_attr):
    """A selector that reads a post-match/outcome attribute must raise under the
    structural guard."""
    def leaky_selector(c):
        return getattr(c, bad_attr) > 0
    with pytest.raises(AttributeError):
        assert_selector_prior_only(leaky_selector, _ctx())


def test_selector_reading_unknown_attr_raises():
    """A selector reaching for any attribute outside the prior-only allow-list raises
    (defends against a future selector silently depending on non-prior state)."""
    def sneaky(c):
        return c.some_future_field > 1
    with pytest.raises(AttributeError):
        assert_selector_prior_only(sneaky, _ctx())


def test_selector_cannot_mutate_context():
    """Selectors must not mutate the context."""
    def mutator(c):
        c.p_over = 0.99
        return True
    with pytest.raises(AttributeError):
        assert_selector_prior_only(mutator, _ctx())


def test_selection_context_has_no_outcome_field():
    """SelectionContext must not expose any outcome attribute by construction."""
    ctx = _ctx()
    for name in _FORBIDDEN_CTX_ATTRS:
        assert not hasattr(ctx, name), f"SelectionContext unexpectedly exposes {name!r}"


def test_rules_behave_as_specified():
    """Sanity: the rules select as pre-registered on a crafted context."""
    rules = _rules()
    # both teams have >=5,>=8 priors but not >=12
    ctx = _ctx(home_prior_n=8, away_prior_n=8)
    assert rules["data_conf_N5"](ctx) is True
    assert rules["data_conf_N8"](ctx) is True
    assert rules["data_conf_N12"](ctx) is False
    # combined_var = 3.0 > 2.0 threshold -> not stable
    assert rules["stable"](ctx) is False
    # rate_gap = 2.0 >= 1.5 -> extreme
    assert rules["extreme_diff"](ctx) is True
    # conf = |0.6-0.5| = 0.1 >= 0.05 -> high_conf
    assert rules["high_conf"](ctx) is True
    # season_frac = 20/46 ~ 0.43 < 0.5 -> not mid_late
    assert rules["mid_late_season"](ctx) is False
    # stable_AND_extreme = False (stable False)
    assert rules["stable_AND_extreme"](ctx) is False


def test_stable_and_extreme_combination():
    rules = _rules()
    # low combined_var (<=2) AND high rate_gap (>=1.5)
    ctx = _ctx(home_var=0.5, away_var=0.5, home_rate=6.0, away_rate=3.0)
    assert rules["stable"](ctx) is True
    assert rules["extreme_diff"](ctx) is True
    assert rules["stable_AND_extreme"](ctx) is True
