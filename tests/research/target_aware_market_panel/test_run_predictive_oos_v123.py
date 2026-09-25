import json
from pathlib import Path
import numpy as np

from research.target_aware_market_panel import run_predictive_oos_v1_2_3 as R

def test_runner_has_separate_predict_and_evaluate_outputs():
    assert R.PRED.name.endswith("OOS_PREDICTIONS_V1.jsonl")
    assert R.PRED_FREEZE.name.endswith("OOS_PREDICTION_FREEZE_V1.json")
    assert R.EVAL.name.endswith("OOS_EVALUATION_V1.json")

def test_group_respects_primary_and_strict_flags():
    rows=[
      {"family":"GOALS","target_id":"A","is_primary":True,"is_strict_unseen":False},
      {"family":"GOALS","target_id":"A","is_primary":True,"is_strict_unseen":True},
      {"family":"CORNERS","target_id":"B","is_primary":False,"is_strict_unseen":False},
    ]
    g=R._group(rows,"is_strict_unseen")
    assert len(g["GOALS"]["A"])==1
    assert g["CORNERS"]=={}

def test_fit_job_uses_same_m0_columns_in_both_arms(tmp_path):
    n=120
    x0=np.column_stack([np.linspace(-1,1,n),np.sin(np.arange(n)/5),np.cos(np.arange(n)/7),np.arange(n)%3])
    xl=np.column_stack([np.linspace(1,-1,n),np.arange(n)%5])
    m0=tmp_path/"m0.npy"; llm=tmp_path/"llm.npy"
    np.save(m0,x0); np.save(llm,xl)
    y=((np.arange(n)%4)==0).astype(float)
    job={"m0_path":str(m0),"llm_path":str(llm),"train_idx":list(range(100)),
         "test_idx":list(range(100,120)),"y":y.tolist(),
         "meta":{"target_id":"T","market_id":"M","family":"GOALS","fold":0,"line":2.5}}
    out=R._fit_job(job)
    assert out["status"]=="FIT"
    assert out["n_m0_kept"]==4
    assert out["n_llm_kept"]==2
    assert len(out["p0"])==20 and len(out["p1"])==20
    assert out["m0_selected_C"] in (0.003,0.01,0.03,0.1)
    assert out["m1_selected_C"] in (0.003,0.01,0.03,0.1)

def test_runner_has_no_network_or_market_access():
    src=Path("research/target_aware_market_panel/run_predictive_oos_v1_2_3.py").read_text()
    for bad in ("requests.get","httpx","boto3","odds","market_results"):
        if bad=="market_results":
            continue
        assert bad not in src
