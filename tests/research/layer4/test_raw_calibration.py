import numpy as np
from types import SimpleNamespace

from src.research.evaluation.chronology import CALIBRATION_START_TS
from src.research.evaluation.similar_oof import GOALS_FEATURES, SimilarContextConfig
from src.research.layer4.raw_calibration import (
    _percentile,
    _reference_thresholds,
    _similar_goal_predictions,
)


def test_percentile_is_monotone_and_bounded():
    x=np.asarray([1.,2.,3.,4.])
    vals=[_percentile(x,v) for v in (0.,1.,2.5,4.,5.)]
    assert vals==sorted(vals)
    assert all(0<=v<=1 for v in vals)


def test_reference_thresholds_are_ordered():
    t=_reference_thresholds(list(range(1000)))
    assert t['low']<t['high']

def _pit_row(key, kickoff, goals):
    return SimpleNamespace(
        fixture_key=key,
        kickoff_ts=kickoff,
        competition_ref="comp_1",
        targets={"goals_total_regulation": goals},
        features={name: 1.0 for name in GOALS_FEATURES},
    )


def test_similar_calibration_respects_t6h_availability_and_equality() -> None:
    target_ts = CALIBRATION_START_TS + 24 * 3600
    rows = [
        _pit_row("old", target_ts - 24 * 3600, 1.0),
        _pit_row("boundary", target_ts - 12 * 3600, 10.0),
        _pit_row("too_recent", target_ts - 6 * 3600, 100.0),
        _pit_row("target", target_ts, 0.0),
    ]
    corpus = SimpleNamespace(pit=SimpleNamespace(rows=rows))
    config = SimilarContextConfig(
        k_neighbors=10,
        distance_floor=0.25,
        prior_weight=0.0,
        min_observed_dimensions=1,
    )

    predictions = _similar_goal_predictions(corpus, config)

    # The exact 12-hour kickoff gap is admissible:
    # source+6h == target-6h. The 6-hour-gap source is unavailable.
    predicted, neighbors = predictions["target"]
    assert neighbors == 2
    assert predicted == 5.5
