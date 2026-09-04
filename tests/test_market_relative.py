"""Tests for the market-relative (residual-vs-market) count model.

These lock in the two guarantees that make the model an HONEST measurement instrument:
  1. lambda inversion round-trips against the Poisson over-probability.
  2. With no residual weights (unfitted, or degenerate fit), predict == de-vigged market
     (the model defers to the price; it cannot fabricate an edge from nothing).
  3. Rows without a usable market prior abstain (return the market value / None), never
     invent a lambda.
  4. A fitted, centred residual leaves the market prediction unchanged for a row AT the
     training feature mean (offset-preserving centring).
"""
import math

import numpy as np
import pytest
from scipy.stats import poisson

from src.research.models.market_relative import (
    MarketRelativeCountModel,
    implied_lambda_from_p_over,
)


def test_lambda_inversion_roundtrip():
    for lam in (2.0, 3.5, 4.7, 9.5, 10.2, 15.0):
        for line in (2.5, 3.5, 9.5):
            p = 1.0 - float(poisson.cdf(int(math.floor(line)), lam))
            back = implied_lambda_from_p_over(p, line)
            assert back is not None
            assert abs(back - lam) < 1e-3


def test_degenerate_probability_abstains():
    assert implied_lambda_from_p_over(0.0, 9.5) is None
    assert implied_lambda_from_p_over(1.0, 9.5) is None
    assert implied_lambda_from_p_over(None, 9.5) is None


def test_unfitted_predict_equals_market():
    m = MarketRelativeCountModel(target_field="total_corners", line=9.5,
                                 feature_fields=("shots_home", "shots_away"), l2=5.0)
    feat = {"market_over_odds": 1.90, "market_under_odds": 1.95,
            "shots_home": 5.0, "shots_away": 4.0, "total_corners": 11}
    p_market = m.devig_p_over(feat)
    assert p_market is not None
    assert abs(m.predict_p_over(feat) - p_market) < 1e-9


def test_missing_odds_abstain():
    m = MarketRelativeCountModel(target_field="total_corners", line=9.5,
                                 feature_fields=("shots_home",), l2=5.0)
    assert m.devig_p_over({"market_over_odds": None, "market_under_odds": 1.9}) is None
    # predict on a row with no market prior returns None (abstain), not a fabricated prob
    assert m.predict_p_over({"market_over_odds": None, "market_under_odds": 1.9}) is None


def test_fit_defers_to_market_when_too_few_rows():
    m = MarketRelativeCountModel(target_field="total_corners", line=9.5,
                                 feature_fields=("shots_home", "shots_away"), l2=5.0)
    # only 5 rows -> below the 30-row floor -> beta stays 0 -> predict == market
    rows = [{"market_over_odds": 1.9, "market_under_odds": 1.95,
             "shots_home": float(i), "shots_away": float(i), "total_corners": 8 + i}
            for i in range(5)]
    m.fit(rows)
    assert m.params is not None
    assert m.params.beta_l2_norm == 0.0
    for r in rows:
        assert abs(m.predict_p_over(r) - m.devig_p_over(r)) < 1e-9


def test_row_at_training_mean_reproduces_market_after_fit():
    # Build a synthetic training set where the count is driven partly by a feature, so
    # the fit produces nonzero beta; a row AT the feature mean must still equal market
    # (centring makes the offset exact at the mean).
    rng = np.random.default_rng(0)
    rows = []
    for _ in range(300):
        x = float(rng.normal(0, 1))
        lam = math.exp(math.log(10.0) + 0.15 * x)
        y = int(rng.poisson(lam))
        # market prior ~ true-ish lambda 10 (fixed odds) so offset is stable
        rows.append({"market_over_odds": 1.90, "market_under_odds": 1.95,
                     "feat": x, "total_corners": y})
    m = MarketRelativeCountModel(target_field="total_corners", line=9.5,
                                 feature_fields=("feat",), l2=0.5)
    m.fit(rows)
    assert m.params is not None
    mean_feat = m.params.feature_means["feat"]
    row_at_mean = {"market_over_odds": 1.90, "market_under_odds": 1.95, "feat": mean_feat}
    assert abs(m.predict_p_over(row_at_mean) - m.devig_p_over(row_at_mean)) < 1e-9



def test_fit_rejects_fractional_count_targets():
    model = MarketRelativeCountModel(
        target_field="total_corners", line=9.5, feature_fields=("shots_home",)
    )
    with pytest.raises(ValueError, match="non-negative integer count"):
        model.fit([
            {
                "market_over_odds": 1.9,
                "market_under_odds": 1.95,
                "shots_home": 5.0,
                "total_corners": 9.5,
            }
        ])
