import numpy as np
from src.research.target_aware_market_panel import predictive_v14 as V

def test_constants():
    assert V.OUTER_COVERAGE==0.60
    assert V.PCA_VARIANCE==0.80
    assert V.RIDGE_ALPHA_GRID==(0.1,1.0,10.0,100.0)
    assert V.HGB_PARAMS["random_state"]==0
    assert V.HGB_PARAMS["early_stopping"] is False

def test_pca_augment_train_only_shape():
    rng=np.random.default_rng(0)
    X0=rng.normal(size=(100,5)); XL=rng.normal(size=(100,8))
    A,B,m=V.pca_augment(X0[:80],X0[80:],XL[:80],XL[80:],list(range(5)),list(range(8)))
    assert A.shape[0]==80 and B.shape[0]==20
    assert A.shape[1]==5+m["n_components"]
    assert m["explained_variance_ratio_sum"]>=0.80

def test_ortho_ridge_augment_shape_and_alpha():
    rng=np.random.default_rng(1)
    X0=rng.normal(size=(100,5)); XL=X0[:,:3]@rng.normal(size=(3,4))+rng.normal(size=(100,4))*.2
    A,B,m=V.ortho_ridge_augment(X0[:80],X0[80:],XL[:80],XL[80:],list(range(5)),list(range(4)))
    assert A.shape==(80,9) and B.shape==(20,9)
    assert m["alpha"] in V.RIDGE_ALPHA_GRID
    assert m["n_residual_features"]==4

def test_hgb_arm_returns_probabilities():
    rng=np.random.default_rng(2)
    X=rng.normal(size=(180,6)); y=(X[:,0]+.3*X[:,1]+rng.normal(size=180)>.0).astype(float)
    r=V.fit_hgb_arm(X[:150],y[:150],X[150:])
    assert r["status"]=="FIT"
    assert len(r["final"])==30
    assert np.all((r["final"]>=.01)&(r["final"]<=.99))
