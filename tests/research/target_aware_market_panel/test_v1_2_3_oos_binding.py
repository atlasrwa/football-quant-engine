from pathlib import Path
from research.target_aware_market_panel import v1_2_3_make_oos_binding as B

def test_binding_generator_is_outcome_blind():
    src=Path("research/target_aware_market_panel/v1_2_3_make_oos_binding.py").read_text()
    assert '"target_outcomes_read":False' in src
    assert '"model_fit":False' in src
    assert "predict_proba" not in src
    assert "label_for_target" not in src

def test_binding_pins_strong_feature_freeze_and_fairness():
    assert B.EXPECTED[B.FEATURE_FREEZE]=="c366abea89c98622f7e923c7206a6a719f2a68972b3a880d425a54d12786521a"
    assert B.EXPECTED[B.FAIRNESS]=="4f6395f1de25b28310849bdd43e72c1b1e8f27b28b68a6915b70b35cd04a0014"

def test_binding_declares_strict_as_secondary_only():
    src=Path("research/target_aware_market_panel/v1_2_3_make_oos_binding.py").read_text()
    assert "secondary robustness only" in src
    assert "prospective_validation_required_for_promotion" in src
