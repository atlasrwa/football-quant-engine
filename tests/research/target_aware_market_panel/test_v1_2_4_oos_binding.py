from pathlib import Path
from research.target_aware_market_panel import v1_2_4_make_oos_binding as B

def test_binding_generator_is_outcome_blind():
    src=Path("research/target_aware_market_panel/v1_2_4_make_oos_binding.py").read_text()
    assert '"target_outcomes_read":False' in src
    assert '"model_fit":False' in src
    assert "predict_proba" not in src
    assert "label_for_target" not in src

def test_binding_pins_strong_feature_freeze_and_fairness():
    assert B.EXPECTED[B.FEATURE_FREEZE]=="c366abea89c98622f7e923c7206a6a719f2a68972b3a880d425a54d12786521a"
    assert B.EXPECTED[B.FAIRNESS]=="4f6395f1de25b28310849bdd43e72c1b1e8f27b28b68a6915b70b35cd04a0014"

def test_binding_declares_strict_as_secondary_only():
    src=Path("research/target_aware_market_panel/v1_2_4_make_oos_binding.py").read_text()
    assert "secondary robustness only" in src
    assert "prospective_validation_required_for_promotion" in src


def test_binding_pins_v123_abort_and_previous_binding():
    assert B.EXPECTED[B.ABORT_V123] == "80ae6bb9be52dc0035253a432c77dcec63419b5525d30f9b10cf326b47536970"
    assert B.EXPECTED[B.PREV_BINDING] == "2741f677a8c0bd7b85e6281544d98542977d69f01146a79e2d3a510a79b7b20b"

def test_binding_declares_execution_safety_only_repair():
    src=Path("research/target_aware_market_panel/v1_2_4_make_oos_binding.py").read_text()
    assert "execution-only; scientific design inherited unchanged from V1.2.3" in src
    assert "exclusive_single_run_lock" in src
    assert "atomic_final_artifact_publication" in src
