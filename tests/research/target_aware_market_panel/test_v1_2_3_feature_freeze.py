from pathlib import Path
from research.target_aware_market_panel import v1_2_3_build_feature_freeze as B

def test_builder_is_outcome_blind():
    s=Path("research/target_aware_market_panel/v1_2_3_build_feature_freeze.py").read_text()
    assert "label_for_target" not in s
    assert '"target_outcomes_read":False' in s
    assert '"model_fit":False' in s
    assert "predict_proba" not in s

def test_builder_pins_aborted_parent_and_old_freeze():
    assert B.OLD_SHA=="e4ff5e59331035605ac76687aaf0d30e020e925aab0e2f573356ea6a79289e07"
    assert B.ABORT_SHA=="1c0183478076babe5edb96ace29330a57d82de980bbf3810aa23876b033a3396"

def test_direct_help():
    import subprocess,sys
    p=subprocess.run([sys.executable,"research/target_aware_market_panel/v1_2_3_build_feature_freeze.py","--help"],
                     cwd=B.ROOT,capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    assert "--authorized-head" in p.stdout
