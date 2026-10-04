import pytest

from src.research.layer5.diagnostics import compute_surface_diagnostics
from src.research.layer5.disagreement import ModelMarketPoint
from src.research.layer5.market_relative import (
    MarketRelativeRow,
    fit_market_only_benchmark,
    run_incremental_information_experiment,
)
from src.research.layer5.market_surface import MarketPoint, MarketSurface


def _surface(points):
    return MarketSurface(
        status="OK",
        reason=None,
        fixture_id="fx",
        market_key="CORNERS_TOTAL",
        bookmaker="pinnacle",
        prediction_cutoff=1000.0,
        observed_at_min=900.0,
        observed_at_max=900.0,
        bundle_id="b",
        points=tuple(
            MarketPoint(
                line=line,
                over_odds=2.0,
                under_odds=2.0,
                overround=1.0,
                p_over_raw=p,
                p_over_shin=p,
                p_over_clean=p,
                isotonic_adjustment=0.0,
            )
            for line, p in points
        ),
        max_abs_repair=0.0,
        mean_abs_repair=0.0,
    )


def _model(line, probability):
    return ModelMarketPoint(
        line=line,
        p_model_over=probability,
        dynamic_supported=True,
        calibration_bin_unique_fixtures=100,
        reliability_ci_low=-0.01,
        reliability_ci_high=0.01,
    )


def test_surface_diagnostics_measure_broad_gap_and_median_displacement():
    market = _surface([(8.5, 0.70), (9.5, 0.50), (10.5, 0.30)])
    models = [_model(8.5, 0.80), _model(9.5, 0.60), _model(10.5, 0.40)]
    d = compute_surface_diagnostics(market, models)
    assert d.paired_lines == (8.5, 9.5, 10.5)
    assert d.mean_signed_over_probability_gap == pytest.approx(0.10)
    assert d.mean_absolute_probability_gap == pytest.approx(0.10)
    assert d.dominant_direction == "OVER"
    assert d.same_sign_fraction == 1.0
    assert d.market_median_crossing_line == pytest.approx(9.5)
    assert d.qfe_median_crossing_line == pytest.approx(10.0)
    assert d.median_crossing_displacement == pytest.approx(0.5)
    assert d.maximum_local_gap_diagnostic_only == pytest.approx(0.10)


def test_surface_diagnostics_do_not_extrapolate_missing_tail_median():
    market = _surface([(8.5, 0.80), (9.5, 0.70), (10.5, 0.60)])
    models = [_model(8.5, 0.85), _model(9.5, 0.75), _model(10.5, 0.65)]
    d = compute_surface_diagnostics(market, models)
    assert d.market_median_crossing_line is None
    assert d.qfe_median_crossing_line is None
    assert d.median_crossing_displacement is None


def test_surface_diagnostics_reject_nonmonotone_qfe_ladder():
    market = _surface([(8.5, 0.70), (9.5, 0.50), (10.5, 0.30)])
    models = [_model(8.5, 0.70), _model(9.5, 0.45), _model(10.5, 0.55)]
    with pytest.raises(ValueError, match="QFE probability ladder"):
        compute_surface_diagnostics(market, models)


def _synthetic_rows(count=300):
    rows = []
    low_seen = 0
    high_seen = 0
    for i in range(count):
        high = i % 2 == 1
        phase = "CALIBRATION_FIT" if i < 180 else "CALIBRATION_SELECT"
        if high:
            outcome = (high_seen % 10) < 7
            high_seen += 1
            p_market = 0.60
            p_model = 0.70
        else:
            outcome = (low_seen % 10) < 3
            low_seen += 1
            p_market = 0.40
            p_model = 0.30
        rows.append(
            MarketRelativeRow(
                fixture_key=f"fx-{i:04d}",
                phase=phase,
                group="GOALS_TOTAL",
                p_market=p_market,
                p_model=p_model,
                outcome_over=outcome,
                line=2.5,
            )
        )
    return rows


def test_market_only_benchmark_enforces_minimum_matched_fixture_support():
    result = fit_market_only_benchmark(_synthetic_rows(200))
    assert result.status == "INELIGIBLE"
    assert result.reason == "INSUFFICIENT_MATCHED_PREPROTECTED_FIXTURES"


def test_market_only_platt_and_incremental_stack_are_separate_from_p_model():
    rows = _synthetic_rows(300)
    benchmark = fit_market_only_benchmark(rows)
    assert benchmark.status == "OK"
    assert benchmark.total_unique_fixtures == 300
    assert benchmark.selected_candidate in {"IDENTITY", "PLATT_GLOBAL"}
    assert benchmark.selected_spec is not None

    result = run_incremental_information_experiment(rows)
    assert result.status == "OK"
    assert result.stack_spec["method"] == "MARKET_ANCHORED_LOGISTIC_STACK"
    assert result.stack_spec["penalty_anchor"] == {"beta_market": 1.0, "beta_qfe": 0.0}
    assert result.log_loss_improvement_market_minus_stack is not None
    assert result.brier_improvement_market_minus_stack is not None
