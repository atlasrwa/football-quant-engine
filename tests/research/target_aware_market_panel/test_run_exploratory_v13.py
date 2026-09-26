import json
from pathlib import Path
import numpy as np
from research.target_aware_market_panel import run_exploratory_v1_3 as R

def test_runner_has_no_provider_or_network_client():
    src=Path("research/target_aware_market_panel/run_exploratory_v1_3.py").read_text()
    for forbidden in ("requests.", "boto3", "httpx", "TheStatsAPI", "FOOTYSTATS_API_KEY", "THESTATS_API_KEY"):
        assert forbidden not in src

def test_zero_selected_does_not_refit_m1(tmp_path,monkeypatch):
    m0=np.arange(240,dtype=float).reshape(60,4)
    llm=np.arange(120,dtype=float).reshape(60,2)
    p0=tmp_path/"m0.npy"; pl=tmp_path/"llm.npy"; np.save(p0,m0); np.save(pl,llm)
    monkeypatch.setattr(R.SEL,"stable_llm_selection",lambda *a,**k:{
      "status":"ZERO_STABLE_LLM","successful_subfits":3,"selected_llm_indices":[],
      "vote_counts":{},"signs":{},"subfits":[]})
    def forbidden(*a,**k): raise AssertionError("fit_arm must not run for zero selection")
    monkeypatch.setattr(R,"fit_arm",forbidden)
    y=(np.arange(60)%2).astype(float)
    job={"m0_path":str(p0),"llm_path":str(pl),"train_idx":list(range(45)),
         "test_idx":list(range(45,60)),"y":y.tolist(),"llm_names":["a","b"],
         "meta":{"target_id":"T","market_id":"M","family":"GOALS","fold":0,"line":2.5,
                 "test_idx":list(range(45,60))}}
    out=R._fit_job(job)
    assert out["status"]=="FIT_ZERO_SELECTED_REUSE_M0"
    assert out["n_llm_selected"]==0

def test_protocol_explicitly_exploratory_and_zero_api():
    d=json.loads(Path("research/target_aware_market_panel/V1_3_EXPLORATORY_PROTOCOL_V1.json").read_text())
    assert d["scientific_role"]=="EXPLORATORY_MODEL_DEVELOPMENT_ONLY"
    assert d["data_policy"]["provider_calls"]==0
    assert d["selection_rule"]["uses_outer_test_labels"] is False
    assert d["selection_rule"]["uses_v1_2_4_oos_effects_for_selection"] is False
    assert d["interpretation"]["prospective_confirmation_required"] is True
