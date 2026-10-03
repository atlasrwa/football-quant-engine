from src.research.layer4.freeze import build_model_freeze


def test_model_freeze_preserves_boundaries_and_selected_groups():
    d=build_model_freeze('.')
    assert d['boundaries']['protected_outcomes_scored']==0
    assert d['boundaries']['market_odds_used'] is False
    assert d['goals_total_2_5']['calibrator_candidate'] in {'IDENTITY','PLATT_GLOBAL','BETA_GLOBAL','ISOTONIC_GLOBAL','PLATT_ROLE_COMP_RIDGE_L1','PLATT_ROLE_COMP_RIDGE_L10','PLATT_ROLE_COMP_RIDGE_L100'}
    assert d['corners']['side']['registered_lines']==[2.5,3.5,4.5,5.5,6.5,7.5]
