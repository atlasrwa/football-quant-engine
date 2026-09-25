from pathlib import Path
from research.target_aware_market_panel import v1_2_2_build_feature_freeze as B

def test_feature_freezer_is_outcome_blind():
    s=Path("research/target_aware_market_panel/v1_2_2_build_feature_freeze.py").read_text()
    assert "label_for_target" not in s
    assert '"target_outcomes_read":False' in s
    assert '"model_fit":False' in s
    assert "predict_proba" not in s

def test_feature_freezer_pins_frozen_inputs():
    assert B.FAIR_SHA=="4f6395f1de25b28310849bdd43e72c1b1e8f27b28b68a6915b70b35cd04a0014"
    assert B.SUPPORT_SHA=="d21f4ec5226eb56977cef2c733edfcef1287e5d756220e6496797c6816f1b40d"
    assert B.FOLD_SHA=="f353068ec40864d56ac2c514a22e1199a9e237f58b1399e9739c71ae4488d3a1"

def test_feature_freezer_direct_help():
    import subprocess,sys
    p=subprocess.run([sys.executable,"research/target_aware_market_panel/v1_2_2_build_feature_freeze.py","--help"],
                     cwd=B.ROOT,capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    assert "--authorized-head" in p.stdout
