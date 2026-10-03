from src.research.layer4.protocol import *


def test_calibration_and_protected_boundaries_are_frozen():
    d=protocol_v1().to_dict(); b=d['scientific_boundary']
    assert b['calibration_fit_window']=={'start_ts':CALIBRATION_START_TS,'end_exclusive_ts':CALIBRATION_FIT_END_TS}
    assert b['calibration_select_window']=={'start_ts':CALIBRATION_FIT_END_TS,'end_exclusive_ts':CALIBRATION_END_TS}
    assert b['protected_outcomes_allowed'] is False
    assert b['market_odds_allowed'] is False


def test_corner_ensemble_is_one_coherent_weight_across_frozen_ladders():
    d=protocol_v1().to_dict()['corners']
    assert tuple(d['side_lines'])==CORNERS_SIDE_LINES
    assert tuple(d['total_lines'])==CORNERS_TOTAL_LINES
    assert tuple(d['nb2_weight_grid'])==CORNERS_NB2_WEIGHT_GRID
    assert 'complete joint count distributions' in d['coherent_mixture']


def test_goal_diversifier_is_small_and_intensity_based():
    d=protocol_v1().to_dict()['goals']
    assert max(d['diversifier_weight_grid'])==0.20
    assert d['equal_weight_0_5']=='diagnostic_only_not_eligible'
    assert 'expected_total' in d['blend_contract']


def test_calibration_has_no_line_specific_models_and_partial_pooling_challenger():
    d=protocol_v1().to_dict()['calibration']
    assert 'PLATT_ROLE_COMP_RIDGE_L10' in d['candidate_methods']
    assert 'no line-specific calibrators' in d['coherence']
    assert d['isotonic_support']['min_unique_fixtures']==250


def test_uncertainty_contract_does_not_claim_fixture_confidence_interval():
    d=protocol_v1().to_dict()['prediction_support_metadata']
    assert 'NOT an individual-fixture probability confidence interval' in d['reliability_band']
    assert 'diagnostic metadata only' in d['ood_policy']
