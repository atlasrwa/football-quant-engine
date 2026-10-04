from src.research.evaluation.layer31_protocol import (
    SIDE_LINES, TOTAL_LINES, protocol_v1, protocol_v2,
)


def test_protocol_has_no_market_or_future_outcome_access():
    p=protocol_v1()
    assert p.source_partition == "DEVELOPMENT"
    assert p.market_odds_allowed is False
    assert p.calibration_outcomes_allowed is False
    assert p.protected_outcomes_allowed is False


def test_lines_are_frozen_and_complete():
    assert SIDE_LINES == (2.5,3.5,4.5,5.5,6.5,7.5)
    assert TOTAL_LINES == (7.5,8.5,9.5,10.5,11.5,12.5)


def test_protocol_primary_hypotheses_do_not_select_best_line():
    d=protocol_v1().to_dict()
    assert set(d['hypotheses']) == {'SIDE_CORNERS','TOTAL_CORNERS'}
    assert 'No best-line search' in d['multiplicity_policy']
    for h in d['hypotheses'].values():
        assert 'diagnostic only' in h['line_results']

def test_v2_changes_only_version_binding():
    v1=protocol_v1().to_dict()
    v2=protocol_v2().to_dict()
    assert v2["version"] == "qfe-layer3.1-market-event-coverage-v2-pit-horizon"
    assert v2["frozen_on"] == "2026-10-03"
    for key in v1:
        if key not in {"version","frozen_on"}:
            assert v2[key] == v1[key]
