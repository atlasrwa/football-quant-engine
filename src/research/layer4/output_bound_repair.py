"""Deterministic Layer 4 V3 output-bound repair.

This module does not re-run calibrator selection. It binds the already selected
V2 calibrators and only enforces the frozen probability output bound.
"""
from __future__ import annotations
import gzip, hashlib, json
from pathlib import Path
from typing import Any

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.layer4.calibrators import calibrator_from_spec
from src.research.layer4.calibration_run import (
    GROUPS, _arrays, _bin_index, _diagnostic_intercept_slope, _reliability_band,
    load_raw_rows,
)

V3_CALIBRATION_VERSION="qfe-layer4-calibration-run-v3-output-bound"
V3_MODEL_FREEZE_VERSION="qfe-v2-layer4-standalone-pmodel-v3-output-bound"

def _read(path:Path)->dict[str,Any]:
    d=json.loads(Path(path).read_text())
    if not isinstance(d,dict): raise ValueError(path)
    return d

def _clip(p:float,eps:float)->float:
    return min(max(float(p),float(eps)),1.0-float(eps))

def _apply_bounded(cal,rows,eps:float)->list[float]:
    return [_clip(cal.transform(float(r["raw_probability"]),role=r.get("role"),competition_ref=r.get("competition_ref")),eps) for r in rows]

def _assert_monotone(rows,probs):
    groups={}
    for r,p in zip(rows,probs,strict=True):
        groups.setdefault((r["fixture_key"],r["group"],r.get("role")),[]).append((float(r["line"]),float(p)))
    for key,vals in groups.items():
        vals=sorted(vals); ps=[x[1] for x in vals]
        if any(ps[i+1]>ps[i]+1e-12 for i in range(len(ps)-1)):
            raise ValueError(f"bounded calibrated ladder non-monotone: {key}")

def _support_bins(group_rows,cal_probs,protocol):
    bins=list(protocol["probability_bins"]); minfix=int(protocol["reliability_min_unique_fixtures"])
    seed=int(protocol["bootstrap_seed"]); reps=int(protocol["bootstrap_replicates"])
    out=[]
    for i in range(len(bins)-1):
        idx=[j for j,r in enumerate(group_rows) if _bin_index(float(r["raw_probability"]),bins)==i]
        rows=[group_rows[j] for j in idx]
        ps=[cal_probs[j] for j in idx]
        if not rows:
            out.append({"bin_index":i,"raw_probability_low":bins[i],"raw_probability_high":bins[i+1],"event_cells":0,"unique_fixtures":0,"supported":False}); continue
        _,y,w,_,_=_arrays(rows); unique=len({r["fixture_key"] for r in rows}); sw=sum(w)
        base={"bin_index":i,"raw_probability_low":bins[i],"raw_probability_high":bins[i+1],"event_cells":len(rows),"unique_fixtures":unique,"supported":unique>=minfix,
              "mean_raw_probability":sum(float(r["raw_probability"])*ww for r,ww in zip(rows,w,strict=True))/sw,
              "mean_calibrated_probability":sum(pp*ww for pp,ww in zip(ps,w,strict=True))/sw,
              "observed_rate":sum(int(yy)*ww for yy,ww in zip(y,w,strict=True))/sw}
        base["reliability_error_ci"]=_reliability_band(rows,ps,w,seed,reps) if unique>=minfix else None
        out.append(base)
    return out

def build_v3(repo_root:Path)->tuple[dict[str,Any],list[dict[str,Any]],dict[str,Any]]:
    repo_root=Path(repo_root)
    repair=_read(repo_root/"evidence/layer4/QFE_LAYER4_OUTPUT_BOUND_V3_PROTOCOL.json")
    v2=_read(repo_root/"evidence/layer4/QFE_LAYER4_CALIBRATION_V2_PIT.json")
    v2_freeze=_read(repo_root/"evidence/layer4/QFE_LAYER4_MODEL_FREEZE_V2_PIT.json")
    raw_summary,rows=load_raw_rows(repo_root)
    if v2["calibration_run_hash"]!=repair["parent_calibration_run_hash"]: raise ValueError("parent calibration binding mismatch")
    if v2_freeze["model_freeze_hash"]!=repair["aborted_parent_model_freeze_hash"]: raise ValueError("parent freeze binding mismatch")
    eps=float(repair["output_probability_clip"])
    group_results={g["group"]:g for g in v2["group_results"]}
    output=[]; diagnostics={}
    selected={}
    for group in GROUPS:
        gr=[r for r in rows if r["group"]==group]
        spec=group_results[group]["final_refit_spec"]
        selected[group]=group_results[group]["selected_candidate"]
        if selected[group]!=repair["selected_methods"][group]: raise ValueError("selected method drift")
        cal=calibrator_from_spec(spec)
        probs=_apply_bounded(cal,gr,eps)
        _assert_monotone(gr,probs)
        _,y,w,_,_=_arrays(gr)
        diag=_diagnostic_intercept_slope(probs,y,w,eps)
        support=_support_bins(gr,probs,{
            "probability_bins":[0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0],
            "reliability_min_unique_fixtures":30,
            "bootstrap_seed":20261002,
            "bootstrap_replicates":4000,
        })
        diagnostics[group]={"calibration_intercept_slope":diag,"support_bins":support}
        by={b["bin_index"]:b for b in support}
        for r,p in zip(gr,probs,strict=True):
            bi=_bin_index(float(r["raw_probability"]),[0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0]); sb=by[bi]
            output.append({**r,"p_model":p,"selected_calibrator":selected[group],"raw_probability_bin":bi,
                "calibration_bin_event_cells":sb["event_cells"],"calibration_bin_unique_fixtures":sb["unique_fixtures"],
                "calibration_bin_mean_prediction":sb.get("mean_calibrated_probability"),"calibration_bin_observed_rate":sb.get("observed_rate"),
                "calibration_bin_reliability_error_ci":sb.get("reliability_error_ci")})
    output.sort(key=lambda r:(r["kickoff_ts"],r["fixture_key"],r["group"],r.get("role") or "",r["line"]))
    if any(not (eps<=float(r["p_model"])<=1-eps) for r in output): raise ValueError("p_model bound violation")
    result={"version":V3_CALIBRATION_VERSION,"repair_protocol_hash":repair["protocol_hash"],"parent_calibration_run_hash":v2["calibration_run_hash"],
            "raw_calibration_hash":raw_summary["raw_calibration_hash"],"selected_methods":selected,"selection_reused_from_v2":True,
            "diagnostics":diagnostics,"row_count":len(output),"rows_hash":sha256_json(output),"output_probability_clip":eps,
            "protected_rows_scored":0,"market_odds_used":False}
    result["calibration_run_hash"]=sha256_json(result)
    freeze={"version":V3_MODEL_FREEZE_VERSION,"scientific_status":"STANDALONE_PMODEL_OUTPUT_BOUND_REPAIR_CALIBRATION_EXPOSED_NO_MARKET",
            "repair_protocol_hash":repair["protocol_hash"],"parent_v2_model_freeze_hash":v2_freeze["model_freeze_hash"],
            "parent_v2_calibration_run_hash":v2["calibration_run_hash"],"v3_calibration_run_hash":result["calibration_run_hash"],
            "output_probability_clip":{"lower":eps,"upper":1-eps},"selection_reused_from_v2":True,
            "goals_total_2_5":{**v2_freeze["goals_total_2_5"],"calibrator_spec":group_results["GOALS_TOTAL"]["final_refit_spec"]},
            "corners":v2_freeze["corners"],"prediction_support":{**v2_freeze["prediction_support"],"v3_diagnostics":diagnostics},
            "selection_evidence":v2_freeze["selection_evidence"],
            "boundaries":{"market_odds_used":False,"protected_outcomes_scored":0,"commercial_claim_allowed":False,
                          "calibration_outcomes_already_exposed":True,"future_predictions_must_apply_output_clip":True}}
    freeze["model_freeze_hash"]=sha256_json(freeze)
    return result,output,freeze

def write_v3(repo_root:Path,result,rows,freeze):
    e=Path(repo_root)/"evidence/layer4"
    raw="".join(canonical_json(r)+"\n" for r in rows).encode()
    gz=gzip.compress(raw,compresslevel=9,mtime=0)
    summary={**result,"rows_file":"QFE_LAYER4_CALIBRATED_ROWS_V3_BOUND.jsonl.gz","rows_file_sha256":hashlib.sha256(gz).hexdigest(),"rows_encoding":"canonical-jsonl+gzip(mtime=0)"}
    payloads=(
        (e/"QFE_LAYER4_CALIBRATION_V3_BOUND.json",(canonical_json(summary)+"\n").encode()),
        (e/"QFE_LAYER4_CALIBRATED_ROWS_V3_BOUND.jsonl.gz",gz),
        (e/"QFE_LAYER4_MODEL_FREEZE_V3_BOUND.json",(canonical_json(freeze)+"\n").encode()),
    )
    for path,payload in payloads:
        if path.exists():
            if path.read_bytes()!=payload:
                raise FileExistsError(f"Layer4 V3 artifact differs: {path}")
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(payload)
    return summary
