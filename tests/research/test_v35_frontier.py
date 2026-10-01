import json
import math
from pathlib import Path

import numpy as np

from src.research.evidence_v32.modeling_v322 import LinearCount
from src.research.v35_frontier.market import corner_comparison
from src.research.v35_frontier.model import (
    FrozenLinearCount, blend_probability, export_linear_count,
)


def test_frozen_linear_count_reproduces_audited_linear_count():
    x = [
        [1.0, 2.0], [2.0, 1.0], [3.0, 4.0], [4.0, 3.0],
        [5.0, 6.0], [6.0, 5.0],
    ]
    y = [1, 2, 2, 3, 4, 4]
    fitted = LinearCount(x, y)
    frozen = FrozenLinearCount(export_linear_count(fitted))
    probe = [[2.5, 2.0], [5.5, 5.0]]
    assert np.allclose(fitted.predict(probe), frozen.predict(probe), rtol=1e-12, atol=1e-12)


def test_logit_blend_stays_between_parent_probabilities():
    p = blend_probability(0.40, 0.70, 0.25)
    assert 0.40 < p < 0.70
    assert math.isclose(blend_probability(0.40, 0.70, 0.0), 0.40, rel_tol=1e-7)
    assert math.isclose(blend_probability(0.40, 0.70, 1.0), 0.70, rel_tol=1e-7)


def test_corner_market_adapter_uses_only_supported_stack_lines():
    dist = {
        "probabilities": {
            "8.5": {
                "p_over": 0.61, "p_over_v3": 0.58,
                "p_over_pressure": 0.63, "pressure_weight": 0.7,
            },
            "9.5": {
                "p_over": 0.55, "p_over_v3": 0.52,
                "p_over_pressure": 0.57, "pressure_weight": 0.7,
            },
            "10.5": {
                "p_over": 0.48, "p_over_v3": 0.46,
                "p_over_pressure": 0.50, "pressure_weight": 0.7,
            },
        }
    }
    odds = {
        "data": {
            "bookmakers": [{
                "bookmaker": "Bet365",
                "markets": {
                    "match_corners": {
                        "7.5": {
                            "over": {"last_seen": 2.00},
                            "under": {"last_seen": 1.80},
                        },
                        "9.5": {
                            "over": {"last_seen": 1.95, "opening": 2.00},
                            "under": {"last_seen": 1.95, "opening": 1.90},
                        },
                    }
                },
            }]
        }
    }
    cmp = corner_comparison(dist, odds)
    assert cmp is not None
    assert cmp["line"] == 9.5
    assert cmp["p_model_over"] == 0.55
    assert cmp["model_parent_probabilities"]["v3"] == 0.52
    assert cmp["model_parent_probabilities"]["pressure"] == 0.57


def test_corner_market_adapter_abstains_when_only_unsupported_line_exists():
    dist = {
        "probabilities": {
            "8.5": {"p_over": 0.6, "p_over_v3": 0.6,
                    "p_over_pressure": 0.6, "pressure_weight": 0.5}
        }
    }
    odds = {
        "data": {
            "bookmakers": [{
                "bookmaker": "Bet365",
                "markets": {
                    "match_corners": {
                        "11.5": {
                            "over": {"last_seen": 2.0},
                            "under": {"last_seen": 1.8},
                        }
                    }
                },
            }]
        }
    }
    assert corner_comparison(dist, odds) is None
