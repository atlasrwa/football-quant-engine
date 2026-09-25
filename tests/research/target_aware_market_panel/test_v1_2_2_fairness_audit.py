from pathlib import Path
from research.target_aware_market_panel import v1_2_2_fairness_audit as A

def test_fairness_audit_is_outcome_blind():
    src = Path("research/target_aware_market_panel/v1_2_2_fairness_audit.py").read_text()
    assert '"target_outcomes_read":False' in src
    assert '"model_fit":False' in src
    assert '"oos_executed":False' in src
    assert "predict_proba" not in src and "LogisticRegression" not in src

def test_fairness_audit_pins_prior_freezes():
    assert A.EXPECTED_FOLD_SHA == "f353068ec40864d56ac2c514a22e1199a9e237f58b1399e9739c71ae4488d3a1"
    assert A.EXPECTED_SUPPORT_FREEZE_SHA == "d21f4ec5226eb56977cef2c733edfcef1287e5d756220e6496797c6816f1b40d"

def test_strict_unseen_is_secondary_not_primary():
    src = Path("research/target_aware_market_panel/v1_2_2_fairness_audit.py").read_text()
    assert "retrospective transferability screen" in src
    assert "secondary robustness set" in src
    assert "mandatory for any claim" in src


def test_fairness_audit_direct_invocation_help():
    import subprocess, sys
    p = subprocess.run([sys.executable, "research/target_aware_market_panel/v1_2_2_fairness_audit.py", "--help"],
                       cwd=A.ROOT, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "--authorized-head" in p.stdout
