"""V1.4 exploratory angle-battery transforms and nonlinear fitter.

All transforms are fitted inside the outer training fold. No network/provider access.
"""
from __future__ import annotations
from typing import Any, Dict, List, Sequence, Tuple
import warnings
import numpy as np

OUTER_COVERAGE=0.60
PCA_VARIANCE=0.80
RIDGE_ALPHA_GRID=(0.1,1.0,10.0,100.0)
RIDGE_CV_SPLITS=3
HGB_CALIBRATION_SPLITS=3
HGB_PARAMS={
 "learning_rate":0.05,
 "max_iter":200,
 "max_leaf_nodes":15,
 "min_samples_leaf":30,
 "l2_regularization":1.0,
 "random_state":0,
 "early_stopping":False,
}

def coverage_keep(X:np.ndarray,min_rate:float=OUTER_COVERAGE)->List[int]:
    if X.shape[0]==0:return []
    return [int(i) for i in np.where(np.mean(~np.isnan(X),axis=0)>=min_rate)[0]]

def pca_augment(X0tr:np.ndarray,X0te:np.ndarray,XLtr:np.ndarray,XLte:np.ndarray,
                k0:Sequence[int],kl:Sequence[int])->Tuple[np.ndarray,np.ndarray,Dict[str,Any]]:
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    k0=list(k0); kl=list(kl)
    if not kl:
        return X0tr[:,k0],X0te[:,k0],{"n_components":0,"explained_variance_ratio_sum":0.0}
    imp=SimpleImputer(strategy="median").fit(XLtr[:,kl])
    Ltr=imp.transform(XLtr[:,kl]); Lte=imp.transform(XLte[:,kl])
    sc=StandardScaler().fit(Ltr); Ltr=sc.transform(Ltr); Lte=sc.transform(Lte)
    pca=PCA(n_components=PCA_VARIANCE,svd_solver="full").fit(Ltr)
    Ztr=pca.transform(Ltr); Zte=pca.transform(Lte)
    return (np.column_stack([X0tr[:,k0],Ztr]),np.column_stack([X0te[:,k0],Zte]),
            {"n_components":int(Ztr.shape[1]),
             "explained_variance_ratio_sum":float(np.sum(pca.explained_variance_ratio_))})

def ortho_ridge_augment(X0tr:np.ndarray,X0te:np.ndarray,XLtr:np.ndarray,XLte:np.ndarray,
                        k0:Sequence[int],kl:Sequence[int])->Tuple[np.ndarray,np.ndarray,Dict[str,Any]]:
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import GridSearchCV,TimeSeriesSplit
    k0=list(k0); kl=list(kl)
    if not kl:
        return X0tr[:,k0],X0te[:,k0],{"alpha":None,"n_residual_features":0}
    i0=SimpleImputer(strategy="median").fit(X0tr[:,k0])
    il=SimpleImputer(strategy="median").fit(XLtr[:,kl])
    A0tr=i0.transform(X0tr[:,k0]); A0te=i0.transform(X0te[:,k0])
    Ltr=il.transform(XLtr[:,kl]); Lte=il.transform(XLte[:,kl])
    s0=StandardScaler().fit(A0tr); sl=StandardScaler().fit(Ltr)
    A0trs=s0.transform(A0tr); A0tes=s0.transform(A0te)
    Ltrs=sl.transform(Ltr); Ltes=sl.transform(Lte)
    cv=TimeSeriesSplit(n_splits=RIDGE_CV_SPLITS)
    search=GridSearchCV(Ridge(),{"alpha":list(RIDGE_ALPHA_GRID)},cv=cv,
                        scoring="neg_mean_squared_error",refit=True,n_jobs=1,error_score="raise")
    search.fit(A0trs,Ltrs)
    Rtr=Ltrs-search.best_estimator_.predict(A0trs)
    Rte=Ltes-search.best_estimator_.predict(A0tes)
    return (np.column_stack([X0tr[:,k0],Rtr]),np.column_stack([X0te[:,k0],Rte]),
            {"alpha":float(search.best_params_["alpha"]),
             "cv_best_mean_neg_mse":float(search.best_score_),
             "n_residual_features":int(Rtr.shape[1])})

def fit_hgb_arm(Xtr:np.ndarray,ytr:np.ndarray,Xte:np.ndarray)->Dict[str,Any]:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.isotonic import IsotonicRegression
    from sklearn.model_selection import TimeSeriesSplit
    if len(set(np.asarray(ytr).tolist()))<2:
        return {"status":"UNFIT_SINGLE_CLASS"}
    cv=TimeSeriesSplit(n_splits=HGB_CALIBRATION_SPLITS)
    op=[]; oy=[]
    try:
        for tr,va in cv.split(Xtr):
            if len(set(np.asarray(ytr)[tr].tolist()))<2:
                return {"status":"UNFIT_CALIBRATION_SINGLE_CLASS"}
            m=HistGradientBoostingClassifier(**HGB_PARAMS).fit(Xtr[tr],np.asarray(ytr)[tr])
            op.append(m.predict_proba(Xtr[va])[:,1]); oy.append(np.asarray(ytr)[va])
        full=HistGradientBoostingClassifier(**HGB_PARAMS).fit(Xtr,ytr)
        raw=full.predict_proba(Xte)[:,1]
    except Exception as exc:
        return {"status":"UNFIT_EXCEPTION","error":f"{type(exc).__name__}: {exc}"}
    op=np.concatenate(op); oy=np.concatenate(oy)
    iso=IsotonicRegression(out_of_bounds="clip",y_min=0.0,y_max=1.0,increasing=True).fit(op,oy)
    cal=iso.predict(raw)
    final=np.clip(cal,0.01,0.99)
    return {"status":"FIT","raw":raw,"final":final,"n_calibration_pairs":int(len(op))}

def version_stamp()->Dict[str,Any]:
    return {"artifact_version":"target_aware_predictive_v1_4_angle_battery_v1",
            "outer_coverage":OUTER_COVERAGE,"pca_variance":PCA_VARIANCE,
            "ridge_alpha_grid":list(RIDGE_ALPHA_GRID),"ridge_cv_splits":RIDGE_CV_SPLITS,
            "hgb_calibration_splits":HGB_CALIBRATION_SPLITS,"hgb_params":dict(HGB_PARAMS),
            "network_calls":0,"provider_calls":0}
