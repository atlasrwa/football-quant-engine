import json
from pathlib import Path

import numpy as np

from research.evidence_v32.run_v322 import split_fold
from src.research.evidence_v32.modeling_v322 import (
    HistGBCount, _similar, platt_apply, platt_fit,
)

def test_walk_forward_fold_is_disjoint_and_purged():
    rows=[]
    start=1_700_000_000.0
    for i in range(1000):
        ts=start+i*86400
        rows.append({"kickoff_ts":ts,"cutoff_ts":ts-24*3600,"match_id":str(i)})
    fold={"train_end":.4,"cal_end":.5,"test_end":.6}
    train,cal,test=split_fold(rows,fold)
    assert set(r["match_id"] for r in train).isdisjoint(r["match_id"] for r in cal)
    assert set(r["match_id"] for r in cal).isdisjoint(r["match_id"] for r in test)
    assert max(r["kickoff_ts"]+4*3600 for r in train)<min(r["cutoff_ts"] for r in cal)
    assert max(r["kickoff_ts"]+4*3600 for r in cal)<min(r["cutoff_ts"] for r in test)

def test_platt_calibration_is_bounded_and_deterministic():
    raw=np.array([.1,.2,.35,.55,.7,.85,.9,.4,.6,.3])
    y=np.array([0,0,0,1,1,1,1,0,1,0])
    beta=platt_fit(raw,y)
    out=platt_apply(raw,beta)
    assert np.all((out>0)&(out<1))
    assert np.allclose(beta,platt_fit(raw,y))
def test_similar_opponent_requires_minimum_comparables():
    q={"opp_goals":1.0,"opp_shots":10.0,"opp_sot":3.0,
       "opp_box":6.0,"opp_entries":35.0}
    entries=[]
    for i in range(4):
        entries.append({"ts":1000+i,"own":{"goals":1.0},
                        "opponent_profile":dict(q)})
    value,n=_similar(entries,q,"goals","goals",10000.0)
    assert value is None and n==4
    entries.append({"ts":1005,"own":{"goals":2.0},"opponent_profile":dict(q)})
    value,n=_similar(entries,q,"goals","goals",10000.0)
    assert n==5 and np.isfinite(value)

def test_histgb_poisson_predictions_are_positive():
    x=np.array([[1.,2.],[2.,1.],[3.,2.],[4.,3.],[5.,4.],[6.,5.]]*10)
    y=np.array([0.,1.,1.,2.,2.,3.]*10)
    model=HistGBCount(x,y)
    assert np.all(model.predict(x[:5])>0)

def test_spec_preregisters_similarity_and_xg_before_results():
    path=Path("research/evidence_v32/SPEC_V32_2.json")
    spec=json.loads(path.read_text())
    assert "DEEP_SIMILAR_POISSON" in spec["goals_models"]
    assert spec["optional_xg_model"].startswith("DEEP_POISSON_XG")
    assert spec["registered_before_new_results"] is True
