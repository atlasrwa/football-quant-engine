from src.research.layer5.market_surface import (
    MarketPoint,
    MarketSurface,
    TwoWayQuote,
    build_market_point,
    build_market_surface,
    isotonic_nonincreasing,
)
from src.research.layer5.disagreement import (
    ModelMarketPoint,
    evaluate_single_line,
    evaluate_surface,
)


def _quote(line, over, under, *, ts=1000.0, book="bet365", bundle="b1"):
    return TwoWayQuote(
        fixture_id="fx1",
        market_key="CORNERS_TOTAL",
        bookmaker=book,
        line=line,
        over_odds=over,
        under_odds=under,
        observed_at=ts,
        bundle_id=bundle,
    )


def _model(line, p, *, ci=(-0.005, 0.005), support=100, flags=()):
    return ModelMarketPoint(
        line=line,
        p_model_over=p,
        dynamic_supported=True,
        calibration_bin_unique_fixtures=support,
        reliability_ci_low=ci[0],
        reliability_ci_high=ci[1],
        ood_flags=tuple(flags),
    )


def test_isotonic_nonincreasing_pool_adjacent_violators():
    clean = isotonic_nonincreasing([0.60, 0.62, 0.40])
    assert clean == (0.61, 0.61, 0.40)


def test_surface_rejects_cross_book_and_future_quotes():
    q = [_quote(8.5, 1.9, 1.9), _quote(9.5, 2.0, 1.8, book="pinnacle"), _quote(10.5, 2.2, 1.7)]
    assert build_market_surface(q, prediction_cutoff=1200).reason == "CROSS_BOOK_BLEND_FORBIDDEN"
    future = [_quote(x, 2.0, 1.9, ts=1300) for x in (8.5, 9.5, 10.5)]
    assert build_market_surface(future, prediction_cutoff=1200).reason == "MARKET_HORIZON_MISSING"


def test_surface_rejects_stale_and_sparse_bundles():
    stale = [_quote(x, 2.0, 1.9, ts=100) for x in (8.5, 9.5, 10.5)]
    assert build_market_surface(stale, prediction_cutoff=2000).reason == "MARKET_SNAPSHOT_TOO_OLD"
    sparse = [_quote(x, 2.0, 1.9) for x in (8.5, 10.5, 12.5)]
    assert build_market_surface(sparse, prediction_cutoff=1200).reason == "SURFACE_TOO_SPARSE"


def test_bounded_isotonic_repair_and_severe_incoherence_abstention():
    # Construct three fair probabilities ~0.60, 0.62, 0.40 using symmetric
    # two-way vig. The small first inversion is repaired to ~0.61/0.61.
    small = [
        _quote(8.5, 1.60, 2.40),
        _quote(9.5, 1.55, 2.53),
        _quote(10.5, 2.40, 1.60),
    ]
    s = build_market_surface(small, prediction_cutoff=1200)
    assert s.is_ok
    assert all(s.points[i].p_over_clean >= s.points[i + 1].p_over_clean for i in range(len(s.points)-1))
    severe = [
        _quote(8.5, 2.50, 1.55),
        _quote(9.5, 1.45, 2.80),
        _quote(10.5, 2.80, 1.45),
    ]
    assert build_market_surface(severe, prediction_cutoff=1200).reason == "MARKET_SURFACE_INCOHERENT"


def test_single_line_requires_support_gap_and_reliability_adjusted_gap():
    q = TwoWayQuote("fx1", "GOALS_TOTAL", "bet365", 2.5, 2.0, 2.0, 1000, "b1")
    market = build_market_point(q, prediction_cutoff=1200)
    ok = evaluate_single_line(market, _model(2.5, 0.58, ci=(-0.01, 0.01)))
    assert ok.eligible and ok.side == "OVER"
    assert ok.evidence_class == "SINGLE_LINE_SUPPORTED"
    too_uncertain = evaluate_single_line(market, _model(2.5, 0.58, ci=(-0.07, 0.07)))
    assert too_uncertain.reason == "RELIABILITY_ADJUSTED_GAP_TOO_SMALL"
    ood = evaluate_single_line(market, _model(2.5, 0.58, flags=("INTENSITY_HIGH",)))
    assert ood.reason == "MODEL_OOD"


def _manual_surface(points):
    return MarketSurface(
        status="OK",
        reason=None,
        fixture_id="fx1",
        market_key="CORNERS_TOTAL",
        bookmaker="bet365",
        prediction_cutoff=1200,
        observed_at_min=1000,
        observed_at_max=1000,
        bundle_id="b1",
        points=tuple(
            MarketPoint(
                line=line,
                over_odds=2.0,
                under_odds=2.0,
                overround=1.05,
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


def test_surface_line_selection_uses_market_centrality_not_maximum_gap():
    market = _manual_surface([(8.5, 0.70), (9.5, 0.50), (10.5, 0.30)])
    models = [
        _model(8.5, 0.76),   # +6 pp
        _model(9.5, 0.56),   # +6 pp, market-centered
        _model(10.5, 0.50),  # +20 pp, largest gap
    ]
    d = evaluate_surface(market, models)
    assert d.eligible
    assert d.line == 9.5
    assert d.line != 10.5
    assert d.corroborating_lines == (8.5, 9.5, 10.5)


def test_surface_rejects_opposite_strong_disagreement():
    market = _manual_surface([(8.5, 0.70), (9.5, 0.50), (10.5, 0.30)])
    models = [_model(8.5, 0.77), _model(9.5, 0.56), _model(10.5, 0.23)]
    d = evaluate_surface(market, models)
    assert not d.eligible
    assert d.reason == "CROSS_LINE_DIRECTION_CONFLICT"


def test_surface_requires_adjacent_corroboration():
    market = _manual_surface([(8.5, 0.70), (9.5, 0.50), (10.5, 0.30)])
    models = [_model(8.5, 0.71), _model(9.5, 0.58), _model(10.5, 0.31)]
    d = evaluate_surface(market, models)
    assert not d.eligible
    assert d.reason == "CROSS_LINE_NOT_CORROBORATED"


def test_bundle_selector_uses_latest_complete_bundle_not_best_price():
    from src.research.layer5.market_surface import select_latest_complete_bundle

    rows = [
        _quote(8.5, 3.0, 1.4, ts=900, bundle="old"),
        _quote(9.5, 3.0, 1.4, ts=900, bundle="old"),
        _quote(10.5, 3.0, 1.4, ts=900, bundle="old"),
        # Newer complete bundle has deliberately less attractive OVER prices.
        _quote(8.5, 1.8, 2.1, ts=1000, bundle="new"),
        _quote(9.5, 1.8, 2.1, ts=1000, bundle="new"),
        _quote(10.5, 1.8, 2.1, ts=1000, bundle="new"),
        # Future bundle must never enter selection.
        _quote(8.5, 4.0, 1.3, ts=1300, bundle="future"),
        _quote(9.5, 4.0, 1.3, ts=1300, bundle="future"),
        _quote(10.5, 4.0, 1.3, ts=1300, bundle="future"),
    ]
    chosen = select_latest_complete_bundle(
        rows,
        prediction_cutoff=1200,
        bookmaker="bet365",
        market_key="CORNERS_TOTAL",
        minimum_adjacent_lines=3,
    )
    assert chosen
    assert {q.bundle_id for q in chosen} == {"new"}


def test_bundle_selector_does_not_fall_back_based_on_price_quality():
    from src.research.layer5.market_surface import select_latest_complete_bundle

    rows = [
        _quote(8.5, 2.0, 2.0, ts=900, bundle="old"),
        _quote(9.5, 2.0, 2.0, ts=900, bundle="old"),
        _quote(10.5, 2.0, 2.0, ts=900, bundle="old"),
        # Structurally complete but invalid odds; selector still chooses it.
        # build_market_surface must then abstain rather than cherry-pick old.
        _quote(8.5, 1.0, 2.0, ts=1000, bundle="new"),
        _quote(9.5, 1.0, 2.0, ts=1000, bundle="new"),
        _quote(10.5, 1.0, 2.0, ts=1000, bundle="new"),
    ]
    chosen = select_latest_complete_bundle(
        rows,
        prediction_cutoff=1200,
        bookmaker="bet365",
        market_key="CORNERS_TOTAL",
        minimum_adjacent_lines=3,
    )
    assert {q.bundle_id for q in chosen} == {"new"}
    assert build_market_surface(chosen, prediction_cutoff=1200).status == "ABSTAIN"


def test_surface_never_selects_central_line_below_five_pp_gate():
    market = _manual_surface([(8.5, 0.70), (9.5, 0.50), (10.5, 0.30)])
    models = [
        _model(8.5, 0.76),  # +6 pp strong
        _model(9.5, 0.54),  # +4 pp support-only, most market-central
        _model(10.5, 0.36), # +6 pp strong
    ]
    d = evaluate_surface(market, models)
    assert d.eligible
    assert d.absolute_gap >= 0.05
    assert d.line in (8.5, 10.5)
    assert d.line != 9.5


def test_benchmark_bookmaker_selection_uses_frozen_hierarchy_not_best_price():
    from src.research.layer5.market_surface import select_benchmark_bundle
    rows = []
    # Bet365 has dramatically more attractive prices, but Pinnacle is first and
    # structurally complete; price attractiveness may not choose the book.
    for line in (8.5, 9.5, 10.5):
        rows.append(_quote(line, 4.0, 1.3, book="bet365", bundle="b365"))
        rows.append(_quote(line, 1.9, 1.9, book="pinnacle", bundle="pin"))
    chosen = select_benchmark_bundle(
        rows,
        prediction_cutoff=1200,
        market_key="CORNERS_TOTAL",
        minimum_adjacent_lines=3,
    )
    assert chosen
    assert {q.bookmaker for q in chosen} == {"pinnacle"}


def test_selected_book_price_failure_does_not_authorize_fallback():
    from src.research.layer5.market_surface import select_benchmark_bundle
    rows = []
    for line in (8.5, 9.5, 10.5):
        # Pinnacle structurally complete but invalid decimal odds.
        rows.append(_quote(line, 1.0, 2.0, book="pinnacle", bundle="pin"))
        rows.append(_quote(line, 2.0, 2.0, book="bet365", bundle="b365"))
    chosen = select_benchmark_bundle(
        rows,
        prediction_cutoff=1200,
        market_key="CORNERS_TOTAL",
        minimum_adjacent_lines=3,
    )
    assert {q.bookmaker for q in chosen} == {"pinnacle"}
    assert build_market_surface(chosen, prediction_cutoff=1200).status == "ABSTAIN"
