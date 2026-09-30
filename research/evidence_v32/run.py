"""Execute the registered V3.2 offline development comparison.

No network access, no market calls, no deployment, and no corner-model import.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from src.research.evidence_v32.modeling import (
    COMPLETION_BUFFER_SECONDS, CountRegressor, UnsupportedFeatures,
    binary_metrics, build_panel, calibrate_scales, design,
    estimate_nb_dispersion, event_outcomes, event_probabilities,
    fit_dc_rho, joint_distribution, paired_gain,
)

ROOT = Path(__file__).resolve().parent
SPEC_PATH = ROOT / "SPEC.json"
EVIDENCE_PATH = ROOT / "out/evidence_v1/evidence.jsonl"
OUTPUT = ROOT / "out/model_comparison_v1"
def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _read_rows():
    return [json.loads(line) for line in EVIDENCE_PATH.read_text().splitlines() if line.strip()]

def _timestamp_groups(rows):
    return sorted({float(r["kickoff_ts"]) for r in rows})

def _split(rows, train_fraction: float, calibration_fraction: float):
    rows=sorted(rows,key=lambda r:(r["kickoff_ts"],r["match_id"]))
    groups=_timestamp_groups(rows)
    if len(groups)<3:
        return [],[],[]
    train_at=groups[min(max(int(len(groups)*train_fraction)-1,0),len(groups)-1)]
    cal_at=groups[min(max(int(len(groups)*(train_fraction+calibration_fraction))-1,0),len(groups)-1)]
    train=[r for r in rows if r["kickoff_ts"]<=train_at]
    calibration=[r for r in rows if train_at<r["kickoff_ts"]<=cal_at]
    test=[r for r in rows if r["kickoff_ts"]>cal_at]
    if calibration:
        first=min(r["cutoff_ts"] for r in calibration)
        train=[r for r in train if r["kickoff_ts"]+COMPLETION_BUFFER_SECONDS<first]
    if test:
        first=min(r["cutoff_ts"] for r in test)
        calibration=[r for r in calibration if r["kickoff_ts"]+COMPLETION_BUFFER_SECONDS<first]
    return train,calibration,test
def _arms(family):
    arms=["BASE_POISSON","RICH_POISSON","RICH_NB"]
    if family=="goals":
        arms.append("RICH_DC_GOALS_ONLY")
    return arms

def _fit_arm(arm, train, calibration, test, family):
    ytrain=np.asarray([r["y"] for r in train],dtype=float)
    ycal=np.asarray([r["y"] for r in calibration],dtype=float)
    model=CountRegressor(design(train,arm),ytrain.ravel())
    train_means=model.predict(design(train,arm)).reshape(-1,2)
    cal_means=model.predict(design(calibration,arm)).reshape(-1,2)
    scales=calibrate_scales(cal_means,ycal)
    test_means=model.predict(design(test,arm)).reshape(-1,2)*scales[None,:]
    dispersion=estimate_nb_dispersion(ytrain,train_means) if arm=="RICH_NB" else 1e-6
    rho=fit_dc_rho(train_means,ytrain) if arm=="RICH_DC_GOALS_ONLY" else 0.0
    kind="nb" if arm=="RICH_NB" else "dc" if arm=="RICH_DC_GOALS_ONLY" else "poisson"
    predictions=[]; count_losses=[]
    for row,means in zip(test,test_means):
        joint=joint_distribution(float(means[0]),float(means[1]),kind,
                                 dispersion=dispersion,rho=rho,
                                 max_count=40 if family=="cards" else 20)
        actual=[int(x) for x in row["y"]]
        prob=float(joint[actual[0],actual[1]]) if max(actual)<joint.shape[0] else 1e-12
        count_losses.append(-math.log(max(prob,1e-12)))
        probs=event_probabilities(joint,family)
        outcomes=event_outcomes(actual,family)
        for target,event in outcomes.items():
            p=float(np.clip(probs[target],1e-8,1-1e-8))
            predictions.append({
                "match_id":row["match_id"],"competition_id":row["competition_id"],
                "date":row["date"],"target":target,"event":event,"p":p,
                "loss":float(-event*math.log(p)-(1-event)*math.log1p(-p)),
                "mean_home":float(means[0]),"mean_away":float(means[1]),
            })
    fit={
        "arm":arm,"distribution":kind,"train_n":len(train),"calibration_n":len(calibration),
        "test_n":len(test),"calibration_scales":[float(x) for x in scales],
        "nb_dispersion":float(dispersion) if arm=="RICH_NB" else None,
        "dc_rho":float(rho) if arm=="RICH_DC_GOALS_ONLY" else None,
        "mean_joint_count_log_loss":float(np.mean(count_losses)),
    }
    return fit,predictions

def _target_results(predictions, fits, family, fold_name, tolerance):
    targets=sorted({r["target"] for rows in predictions.values() for r in rows})
    out={}
    for target in targets:
        by_arm={arm:[dict(r,fold=fold_name) for r in rows if r["target"]==target]
                for arm,rows in predictions.items()}
        metrics={arm:binary_metrics(rows) for arm,rows in by_arm.items()}
        base=by_arm["BASE_POISSON"]
        comparisons={}
        for arm,rows in by_arm.items():
            if arm=="BASE_POISSON":
                continue
            gain=paired_gain(base,rows)
            gain["brier_delta_candidate_minus_base"]=(
                metrics[arm]["brier"]-metrics["BASE_POISSON"]["brier"])
            gain["calibration_noninferiority_descriptive"]=(
                gain["brier_delta_candidate_minus_base"]<=tolerance)
            comparisons[arm]=gain
        out[target]={
            "family":family,"fold":fold_name,"state":"DEVELOPMENT_ONLY",
            "market_state":"MARKET_UNTESTED","metrics":metrics,
            "vs_base":comparisons,
        }
    return out

def run_family(rows, family, spec):
    panel=build_panel(rows,family)
    eligible=[r for r in panel if r["eligible_rich"]]
    folds=[("PRIMARY_60_20_20",0.60,0.20)]
    if len(eligible)>=160:
        folds.append(("SECONDARY_EXPANDING_70_15_15",0.70,0.15))
    result={"family":family,"panel_rows":len(panel),"eligible_rich_rows":len(eligible),
            "folds":{},"support_state":"SUPPORTED" if eligible else "UNSUPPORTED"}
    for name,train_frac,cal_frac in folds:
        train,cal,test=_split(eligible,train_frac,cal_frac)
        counts={"train":len(train),"calibration":len(cal),"test":len(test)}
        minimum=(spec["minimum_train"],spec["minimum_calibration"],spec["minimum_test"])
        if len(train)<minimum[0] or len(cal)<minimum[1] or len(test)<minimum[2]:
            result["folds"][name]={"state":"INSUFFICIENT_SUPPORT","counts":counts}
            continue
        fits=[]; predictions={}; failures=[]
        for arm in _arms(family):
            try:
                fit,pred=_fit_arm(arm,train,cal,test,family)
            except UnsupportedFeatures as exc:
                failures.append({"arm":arm,"reason":str(exc)}); continue
            fits.append(fit); predictions[arm]=pred
        if "BASE_POISSON" not in predictions:
            result["folds"][name]={"state":"UNSUPPORTED","counts":counts,
                                   "failures":failures}; continue
        common=set(predictions)
        expected=set(_arms(family))
        state="FITTED_DEVELOPMENT" if common==expected else "PARTIAL_SUPPORT"
        result["folds"][name]={
            "state":state,"counts":counts,"fits":fits,"failures":failures,
            "targets":_target_results(predictions,fits,family,name,
                spec["calibration_brier_noninferiority_tolerance"]),
            "train_ids":[r["match_id"] for r in train],
            "calibration_ids":[r["match_id"] for r in cal],
            "test_ids":[r["match_id"] for r in test],
        }
    return result,panel

def main():
    spec=json.loads(SPEC_PATH.read_text())
    if spec["version"]!="EVIDENCE_V32_DEVELOPMENT_2":
        raise RuntimeError("unexpected V3.2 specification version")
    if OUTPUT.exists():
        raise RuntimeError("immutable output already exists")
    rows=_read_rows()
    results={}; support={}
    for family in ("goals","cards"):
        results[family],panel=run_family(rows,family,spec)
        support[family]={
            "panel_rows":len(panel),
            "eligible_core_rows":sum(r["eligible_core"] for r in panel),
            "eligible_rich_rows":sum(r["eligible_rich"] for r in panel),
            "competitions":sorted({r["competition_id"] for r in panel if r["eligible_rich"]}),
        }
    OUTPUT.mkdir(parents=True)
    (OUTPUT/"results.json").write_text(json.dumps(results,indent=2,sort_keys=True,allow_nan=False)+"\n")
    (OUTPUT/"support.json").write_text(json.dumps(support,indent=2,sort_keys=True,allow_nan=False)+"\n")
    manifest={
        "version":spec["version"],"state":"DEVELOPMENT_ONLY","live_calls":0,
        "corners_imported_or_refit":False,"evidence_sha256":_hash(EVIDENCE_PATH),
        "spec_sha256":_hash(SPEC_PATH),"runner_sha256":_hash(Path(__file__)),
        "models":["BASE_POISSON","RICH_POISSON","RICH_NB","RICH_DC_GOALS_ONLY"],
        "market_state":"MARKET_UNTESTED","promotions":0,
    }
    for p in sorted(OUTPUT.iterdir()):
        manifest.setdefault("files",{})[p.name]=_hash(p)
    (OUTPUT/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"support":support,
        "fold_states":{f:{k:v["state"] for k,v in d["folds"].items()}
                       for f,d in results.items()}},indent=2))

if __name__=="__main__":
    main()
