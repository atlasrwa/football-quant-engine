import json
from pathlib import Path
from research.target_aware_market_panel import run_exploratory_v1_4_battery as R

def test_methods_frozen():
    assert R.METHODS==("LLM_ONLY_LOGIT","PCA80_LOGIT","ORTHO_RIDGE_LOGIT",
                       "GOALS_MULTI_ONLY_LOGIT","GOALS_SIM_ONLY_LOGIT","HGB_RAW_PARITY")

def test_no_network_provider_client():
    src=Path("research/target_aware_market_panel/run_exploratory_v1_4_battery.py").read_text()
    for forbidden in ("requests.","httpx","boto3","THESTATS_API_KEY","FOOTYSTATS_API_KEY"):
        assert forbidden not in src

def test_protocol_is_exploratory_and_zero_api():
    d=json.loads(Path("research/target_aware_market_panel/V1_4_EXPLORATORY_ANGLE_BATTERY_PROTOCOL_V1.json").read_text())
    assert d["scientific_role"]=="EXPLORATORY_MODEL_DEVELOPMENT_ONLY"
    assert d["data_policy"]["provider_calls"]==0
    assert d["data_policy"]["network_calls"]==0
    assert d["shared_rules"]["no_adaptive_thresholds"] is True
    assert d["interpretation"]["prospective_confirmation_required"] is True
