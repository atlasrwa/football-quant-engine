import numpy as np
from src.research.target_aware_market_panel import predictive_v13 as V

def test_constants_are_frozen():
    assert V.STABILITY_SPLITS == 3
    assert V.MIN_STABILITY_VOTES == 2
    assert V.MIN_SUCCESSFUL_SUBFITS == 2
    assert V.NONZERO_COEF == 1e-8
    assert V.OUTER_COVERAGE == 0.60

def test_coverage_keep():
    X=np.array([[1,np.nan,1],[2,np.nan,np.nan],[3,2,1],[4,3,1],[5,4,np.nan]],float)
    assert V.coverage_keep(X,0.60)==[0,1,2]

def test_stability_vote_and_sign_rule(monkeypatch):
    calls=[]
    coefs=[
      np.array([1.0,0.2,-0.3]),
      np.array([1.0,0.1,-0.4]),
      np.array([1.0,0.0, 0.5]),
    ]
    def fake_fit(X,y):
        i=len(calls); calls.append((len(X),len(y)))
        return {"status":"FIT","coef":coefs[i],"selected_C":0.1,"selected_l1_ratio":0.5,
                "cv_best_mean_neg_log_loss":-0.5,"n_convergence_warnings":0}
    monkeypatch.setattr(V,"fit_selection_model",fake_fit)
    X0=np.arange(120,dtype=float).reshape(60,2)
    XL=np.arange(120,dtype=float).reshape(60,2)
    y=(np.arange(60)%2).astype(float)
    out=V.stable_llm_selection(X0,XL,y,[0],[0,1])
    assert out["selected_llm_indices"] == [0]
    assert out["vote_counts"]["0"] == 2
    assert out["vote_counts"]["1"] == 3
    assert out["signs"]["1"] == [-1,-1,1]

def test_insufficient_subfits_selects_zero(monkeypatch):
    seq=[{"status":"FIT","coef":np.array([1.,0.2]),"selected_C":0.1,"selected_l1_ratio":0.5,
          "cv_best_mean_neg_log_loss":-0.5,"n_convergence_warnings":0},
         {"status":"UNFIT_EXCEPTION","error":"x"},
         {"status":"UNFIT_EXCEPTION","error":"x"}]
    monkeypatch.setattr(V,"fit_selection_model",lambda X,y:seq.pop(0))
    X0=np.arange(60,dtype=float).reshape(30,2); XL=X0.copy(); y=(np.arange(30)%2).astype(float)
    out=V.stable_llm_selection(X0,XL,y,[0],[0])
    assert out["selected_llm_indices"] == []
    assert out["status"] == "INSUFFICIENT_SUCCESSFUL_SUBFITS"
