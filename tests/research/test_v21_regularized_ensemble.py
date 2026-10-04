import numpy as np

from src.research.evaluation.v21_regularized_ensemble import (
    EventCell,
    fit_regularized_simplex,
)


def _synthetic_cells():
    cells = []
    for index in range(120):
        outcome = index % 2 == 0
        # Component 0 is good, component 1 mediocre, component 2 inverted.
        probs = (
            0.75 if outcome else 0.25,
            0.60 if outcome else 0.40,
            0.25 if outcome else 0.75,
        )
        cells.append(
            EventCell(
                fixture_key=f"fx-{index}",
                kickoff_ts=1000 + index,
                fold_id="D1",
                outcome=outcome,
                probabilities=probs,
                cell_weight=1.0,
            )
        )
    return cells


def test_simplex_optimizer_is_nonnegative_normalized_and_data_responsive():
    weights = fit_regularized_simplex(
        _synthetic_cells(),
        anchor_weights=[1 / 3, 1 / 3, 1 / 3],
        ridge_lambda=0.0,
    )
    assert np.all(weights >= -1e-12)
    assert np.all(weights <= 1.0 + 1e-12)
    assert abs(float(weights.sum()) - 1.0) < 1e-10
    assert weights[0] > weights[1] > weights[2]


def test_strong_ridge_stays_closer_to_frozen_anchor():
    anchor = np.asarray([0.8, 0.2, 0.0])
    weak = fit_regularized_simplex(
        _synthetic_cells(),
        anchor_weights=anchor.tolist(),
        ridge_lambda=0.0,
    )
    strong = fit_regularized_simplex(
        _synthetic_cells(),
        anchor_weights=anchor.tolist(),
        ridge_lambda=1.0,
    )
    assert np.linalg.norm(strong - anchor) < np.linalg.norm(weak - anchor)
