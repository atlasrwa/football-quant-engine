from src.research.target_aware_market_panel import predictive_eval_v123 as E

def _r(mid,k,y,p0,p1):
    return {"match_id":mid,"kickoff":k,"y":y,"p0":p0,"p1":p1}

def test_holm_adjust_is_step_down_monotone():
    got=E.holm_adjust({"A":0.001,"B":0.01,"C":0.03,"D":0.2})
    assert got["A"] <= got["B"] <= got["C"] <= got["D"]
    assert got["A"] == 0.004

def test_family_compare_equal_weights_targets_not_rows():
    # target A has two rows with improvement; B has one row with deterioration.
    # Point estimate must be mean(target means), not pooled 3-row mean.
    rows={
      "A":[_r("a1",1704067200,1,0.6,0.7),_r("a2",1704672000,0,0.4,0.3)],
      "B":[_r("b1",1704067200,1,0.8,0.7)],
    }
    c=E.family_compare(rows,resamples=200,seed=0)
    da=c["target_details"]["A"]["delta_logloss"]
    db=c["target_details"]["B"]["delta_logloss"]
    assert abs(c["delta_logloss_m0_minus_m1"] - (da+db)/2) < 1e-12
    assert c["n_targets"] == 2

def test_gate_requires_all_frozen_clauses():
    c={"status":"OK","delta_logloss_m0_minus_m1":0.002,"ci_lower":0.0001,
       "ece_m0":0.03,"ece_m1":0.034}
    assert E.gate(c,0.04)["pass"] is True
    assert E.gate(c,0.06)["pass"] is False
    c["ece_m1"]=0.04
    assert E.gate(c,0.04)["pass"] is False
