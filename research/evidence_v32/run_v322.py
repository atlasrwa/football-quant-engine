"""Run frozen V3.2.2 expanded development comparisons. Offline only."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from src.research.evidence_v32.modeling import (
    binary_metrics, event_outcomes, event_probabilities, joint_distribution,
    paired_gain, estimate_nb_dispersion, fit_dc_rho,
)
from src.research.evidence_v32.modeling_v322 import (
    COMPLETION_BUFFER_SECONDS, DirectHistGB, DirectLogistic, HistGBCount,
    LinearCount, UnsupportedFeatures, build_panel, count_scales, platt_apply,
    platt_fit, side_design,
)

ROOT=Path(__file__).resolve().parent
SPEC=ROOT/"SPEC_V32_2.json"
EVIDENCE=ROOT/"out/evidence_v2/evidence.jsonl"
OUTPUT=ROOT/"out/model_comparison_v3"
REPO=ROOT.parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_rows():
    return [json.loads(x) for x in EVIDENCE.read_text().splitlines() if x.strip()]
def split_fold(rows, fold):
    rows=sorted(rows,key=lambda r:(r["kickoff_ts"],r["match_id"]))
    groups=sorted({float(r["kickoff_ts"]) for r in rows})
    if len(groups)<10:
        return [],[],[]
    def boundary(frac):
        idx=min(max(int(math.ceil(len(groups)*frac))-1,0),len(groups)-1)
        return groups[idx]
    a,b,c=(boundary(fold[k]) for k in ("train_end","cal_end","test_end"))
    train=[r for r in rows if r["kickoff_ts"]<=a]
    cal=[r for r in rows if a<r["kickoff_ts"]<=b]
    test=[r for r in rows if b<r["kickoff_ts"]<=c]
    if cal:
        first=min(r["cutoff_ts"] for r in cal)
        train=[r for r in train if r["kickoff_ts"]+COMPLETION_BUFFER_SECONDS<first]
    if test:
        first=min(r["cutoff_ts"] for r in test)
        cal=[r for r in cal if r["kickoff_ts"]+COMPLETION_BUFFER_SECONDS<first]
    return train,cal,test

def key_for_arm(arm):
    if arm=="BASE_POISSON":
        return "base"
    if arm=="RICH_POISSON":
        return "primary"
    if arm=="DEEP_SIMILAR_POISSON":
        return "similar"
    if arm=="DEEP_POISSON_XG":
        return "xg"
    return "deep"

def count_kind(arm):
    if arm=="DEEP_NB":
        return "nb"
    if arm=="DEEP_DC":
        return "dc"
    return "poisson"
def fit_count_arm(arm,train,cal,test,family):
    key=key_for_arm(arm)
    ytrain=np.asarray([r["y"] for r in train],float)
    ycal=np.asarray([r["y"] for r in cal],float)
    cls=HistGBCount if arm=="DEEP_HISTGB_POISSON" else LinearCount
    model=cls(side_design(train,key),ytrain.ravel())
    cal_raw=model.predict(side_design(cal,key)).reshape(-1,2)
    scales=count_scales(cal_raw,ycal)
    cal_means=cal_raw*scales[None,:]
    test_means=model.predict(side_design(test,key)).reshape(-1,2)*scales[None,:]
    kind=count_kind(arm)
    dispersion=estimate_nb_dispersion(ycal.ravel(),cal_means.ravel()) if kind=="nb" else 1e-6
    rho=fit_dc_rho(cal_means,ycal) if kind=="dc" else 0.0
    predictions=[]; count_losses=[]
    for row,means in zip(test,test_means):
        joint=joint_distribution(float(means[0]),float(means[1]),kind,
            dispersion=dispersion,rho=rho,max_count=40 if family=="cards" else 20)
        actual=[int(x) for x in row["y"]]
        cell=float(joint[actual[0],actual[1]]) if max(actual)<joint.shape[0] else 1e-12
        count_losses.append(-math.log(max(cell,1e-12)))
        probs=event_probabilities(joint,family)
        outcomes=event_outcomes(actual,family)
        for target,event in outcomes.items():
            p=float(np.clip(probs[target],1e-8,1-1e-8))
            predictions.append({
                "match_id":row["match_id"],"competition_id":row["competition_id"],
                "date":row["date"],"target":target,"event":event,"p":p,
                "loss":float(-event*math.log(p)-(1-event)*math.log1p(-p)),
            })
    fit={"arm":arm,"key":key,"train_n":len(train),"calibration_n":len(cal),
         "test_n":len(test),"calibration_scales":[float(x) for x in scales],
         "distribution":kind,"nb_dispersion":float(dispersion) if kind=="nb" else None,
         "dc_rho":float(rho) if kind=="dc" else None,
         "joint_count_log_loss":float(np.mean(count_losses))}
    return fit,predictions
def fit_direct_btts(arm,train,cal,test):
    xtrain=[r["match_deep"] for r in train]
    xcal=[r["match_deep"] for r in cal]
    xtest=[r["match_deep"] for r in test]
    ytrain=np.asarray([int(r["y"][0]>0 and r["y"][1]>0) for r in train],int)
    ycal=np.asarray([int(r["y"][0]>0 and r["y"][1]>0) for r in cal],int)
    cls=DirectLogistic if arm=="DIRECT_LOGISTIC" else DirectHistGB
    model=cls(xtrain,ytrain)
    cal_raw=model.predict(xcal)
    beta=platt_fit(cal_raw,ycal)
    ptest=platt_apply(model.predict(xtest),beta)
    predictions=[]
    for row,p in zip(test,ptest):
        event=int(row["y"][0]>0 and row["y"][1]>0)
        p=float(np.clip(p,1e-8,1-1e-8))
        predictions.append({
            "match_id":row["match_id"],"competition_id":row["competition_id"],
            "date":row["date"],"target":"BTTS","event":event,"p":p,
            "loss":float(-event*math.log(p)-(1-event)*math.log1p(-p)),
        })
    return {
        "arm":arm,"train_n":len(train),"calibration_n":len(cal),"test_n":len(test),
        "platt_intercept":float(beta[0]),"platt_slope":float(beta[1]),
    },predictions

def summarize_arm_predictions(predictions):
    by_target=defaultdict(list)
    for row in predictions:
        by_target[row["target"]].append(row)
    return {target:binary_metrics(rows) for target,rows in sorted(by_target.items())}

def compare(base,candidate):
    lookup={(r["match_id"],r["target"],r["fold"]):r for r in candidate}
    matched_base=[]; matched_candidate=[]
    for row in base:
        key=(row["match_id"],row["target"],row["fold"])
        other=lookup.get(key)
        if other is not None:
            matched_base.append(row); matched_candidate.append(other)
    gain=paired_gain(matched_base,matched_candidate,seed=3220)
    bm=binary_metrics(matched_base); cm=binary_metrics(matched_candidate)
    gain["brier_delta_candidate_minus_base"]=(
        cm.get("brier")-bm.get("brier") if cm.get("brier") is not None else None)
    gain["paired_brier_n"]=len(matched_base)
    return gain
def run_count_cohort(panel,family,eligible_key,arms,spec):
    eligible=[r for r in panel if r[eligible_key]]
    pooled={arm:[] for arm in arms}; fits=[]; fold_states=[]
    minimum=spec["walk_forward"]
    for idx,fold in enumerate(spec["folds"],1):
        train,cal,test=split_fold(eligible,fold)
        counts={"train":len(train),"calibration":len(cal),"test":len(test)}
        if (len(train)<minimum["minimum_train"] or
            len(cal)<minimum["minimum_calibration"] or
            len(test)<minimum["minimum_test"]):
            fold_states.append({"fold":idx,"state":"INSUFFICIENT_SUPPORT","counts":counts})
            continue
        failures=[]
        for arm in arms:
            try:
                fit,pred=fit_count_arm(arm,train,cal,test,family)
            except (UnsupportedFeatures,ValueError) as exc:
                failures.append({"arm":arm,"reason":str(exc)})
                continue
            fit["fold"]=idx; fits.append(fit)
            pooled[arm].extend(dict(r,fold=idx) for r in pred)
        fold_states.append({"fold":idx,"state":"FITTED_DEVELOPMENT",
                            "counts":counts,"failures":failures})
    return eligible,pooled,fits,fold_states

def run_direct_btts(panel,spec):
    eligible=[r for r in panel if r["eligible_deep"]]
    pooled={arm:[] for arm in ("DIRECT_LOGISTIC","DIRECT_HISTGB")}
    fits=[]; states=[]; minimum=spec["walk_forward"]
    for idx,fold in enumerate(spec["folds"],1):
        train,cal,test=split_fold(eligible,fold)
        counts={"train":len(train),"calibration":len(cal),"test":len(test)}
        if (len(train)<minimum["minimum_train"] or
            len(cal)<minimum["minimum_calibration"] or
            len(test)<minimum["minimum_test"]):
            states.append({"fold":idx,"state":"INSUFFICIENT_SUPPORT","counts":counts})
            continue
        failures=[]
        for arm in pooled:
            try:
                fit,pred=fit_direct_btts(arm,train,cal,test)
            except (UnsupportedFeatures,ValueError) as exc:
                failures.append({"arm":arm,"reason":str(exc)})
                continue
            fit["fold"]=idx; fits.append(fit)
            pooled[arm].extend(dict(r,fold=idx) for r in pred)
        states.append({"fold":idx,"state":"FITTED_DEVELOPMENT",
                       "counts":counts,"failures":failures})
    return pooled,fits,states
def pooled_results(pooled,baseline,allowed_targets=None):
    targets=sorted({r["target"] for rows in pooled.values() for r in rows})
    if allowed_targets is not None:
        targets=[t for t in targets if t in allowed_targets]
    out={}
    for target in targets:
        by_arm={arm:[r for r in rows if r["target"]==target]
                for arm,rows in pooled.items()}
        metrics={arm:binary_metrics(rows) for arm,rows in by_arm.items()}
        comparisons={}
        base=by_arm.get(baseline,[])
        for arm,rows in by_arm.items():
            if arm==baseline or not base or not rows:
                continue
            comparisons[arm]=compare(base,rows)
        out[target]={"baseline":baseline,"metrics":metrics,"vs_baseline":comparisons,
                     "state":"DEVELOPMENT_ONLY","market_state":"MARKET_UNTESTED"}
    return out

def main():
    spec=json.loads(SPEC.read_text())
    if spec["version"]!="EVIDENCE_V32_2_DEVELOPMENT_1":
        raise RuntimeError("unexpected V32.2 spec")
    if OUTPUT.exists():
        raise RuntimeError("immutable V32.2 model output already exists")
    rows=read_rows()
    goals_panel=build_panel(rows,"goals")
    cards_panel=build_panel(rows,"cards")

    goals_arms=["BASE_POISSON","RICH_POISSON","DEEP_POISSON",
                "DEEP_HISTGB_POISSON","DEEP_NB","DEEP_DC"]
    goals_eligible,goals_pred,goals_fits,goals_states=run_count_cohort(
        goals_panel,"goals","eligible_deep",goals_arms,spec)
    sim_eligible,sim_pred,sim_fits,sim_states=run_count_cohort(
        goals_panel,"goals","eligible_similar",
        ["DEEP_POISSON","DEEP_SIMILAR_POISSON"],spec)
    xg_eligible,xg_pred,xg_fits,xg_states=run_count_cohort(
        goals_panel,"goals","eligible_xg",
        ["DEEP_POISSON","DEEP_POISSON_XG"],spec)

    cards_arms=["BASE_POISSON","RICH_POISSON","DEEP_POISSON",
                "DEEP_HISTGB_POISSON","DEEP_NB"]
    cards_eligible,cards_pred,cards_fits,cards_states=run_count_cohort(
        cards_panel,"cards","eligible_deep",cards_arms,spec)
    direct_pred,direct_fits,direct_states=run_direct_btts(goals_panel,spec)
    joint_btts=[r for r in goals_pred["DEEP_POISSON"] if r["target"]=="BTTS"]
    btts_pred={"JOINT_DEEP_POISSON":joint_btts,**direct_pred}
    goal_targets={"home>1.5","away>1.5","total>2.5","total>3.5"}
    card_targets={"home_yellow>1.5","away_yellow>1.5","total_yellow>3.5"}

    results={
        "version":spec["version"],"state":"DEVELOPMENT_ONLY",
        "goals":{
            "support_n":len(goals_eligible),"folds":goals_states,"fits":goals_fits,
            "targets":pooled_results(goals_pred,"BASE_POISSON",goal_targets),
        },
        "btts":{
            "support_n":len(goals_eligible),"folds":direct_states,"fits":direct_fits,
            "targets":pooled_results(btts_pred,"JOINT_DEEP_POISSON",{"BTTS"}),
        },
        "cards":{
            "support_n":len(cards_eligible),"folds":cards_states,"fits":cards_fits,
            "targets":pooled_results(cards_pred,"BASE_POISSON",card_targets),
            "semantic_target":"PROVIDER_NATIVE_YELLOW_CARDS_NOT_BOOKMAKER_BOOKINGS",
        },
        "similar_opponent":{
            "support_n":len(sim_eligible),"folds":sim_states,"fits":sim_fits,
            "targets":pooled_results(sim_pred,"DEEP_POISSON",goal_targets),
        },
        "xg_support_matched":{
            "support_n":len(xg_eligible),"folds":xg_states,"fits":xg_fits,
            "targets":pooled_results(xg_pred,"DEEP_POISSON",goal_targets|{"BTTS"}),
        },
    }
    support={
        "evidence_rows":len(rows),
        "goals":{"core":sum(r["eligible_core"] for r in goals_panel),
                 "primary":sum(r["eligible_primary"] for r in goals_panel),
                 "deep":sum(r["eligible_deep"] for r in goals_panel),
                 "similar":sum(r["eligible_similar"] for r in goals_panel),
                 "xg":sum(r["eligible_xg"] for r in goals_panel)},
        "cards":{"core":sum(r["eligible_core"] for r in cards_panel),
                 "primary":sum(r["eligible_primary"] for r in cards_panel),
                 "deep":sum(r["eligible_deep"] for r in cards_panel)},
    }
    OUTPUT.mkdir(parents=True)
    (OUTPUT/"results.json").write_text(
        json.dumps(results,indent=2,sort_keys=True,allow_nan=False)+"\n")
    (OUTPUT/"support.json").write_text(
        json.dumps(support,indent=2,sort_keys=True,allow_nan=False)+"\n")
    all_predictions=[]
    for section,pools in (
        ("goals",goals_pred),("btts",btts_pred),("cards",cards_pred),
        ("similar",sim_pred),("xg",xg_pred)):
        for arm,preds in pools.items():
            for row in preds:
                all_predictions.append({"section":section,"arm":arm,**row})
    with open(OUTPUT/"predictions.jsonl","w",encoding="utf-8") as fh:
        for row in all_predictions:
            fh.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n")

    manifest={
        "version":spec["version"],"state":"DEVELOPMENT_ONLY","live_calls":0,
        "market_state":"MARKET_UNTESTED","promotions":0,
        "corners_imported_or_refit":False,
        "spec_sha256":sha(SPEC),"evidence_sha256":sha(EVIDENCE),
        "runner_sha256":sha(Path(__file__)),
        "modeling_sha256":sha(REPO/"src/research/evidence_v32/modeling_v322.py"),
    }
    for path in sorted(OUTPUT.iterdir()):
        manifest.setdefault("files",{})[path.name]=sha(path)
    (OUTPUT/"manifest.json").write_text(
        json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"support":support,
        "folds":{
            "goals":goals_states,"btts":direct_states,"cards":cards_states,
            "similar":sim_states,"xg":xg_states}},indent=2))

if __name__=="__main__":
    main()
