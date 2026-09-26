"""Execute and evaluate the frozen Target-Aware V1.2.4 predictive OOS experiment."""
from __future__ import annotations
import argparse, concurrent.futures as cf, fcntl, hashlib, json, os, subprocess, sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict
import numpy as np

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from src.research.item6.stage2.executor import fit_arm, coverage_keep
from src.research.target_aware_market_panel import cohort_packets as CP
from src.research.target_aware_market_panel import predictive_v123 as V
from src.research.target_aware_market_panel import predictive_eval_v123 as EV

OUT=ROOT/"research/target_aware_market_panel"
BINDING=OUT/"V1_2_4_PREDICTIVE_OOS_BINDING_V1.json"
FEATURE_FREEZE=OUT/"V1_2_3_FEATURE_FREEZE_MANIFEST_V1.json"
PRED=OUT/"V1_2_4_OOS_PREDICTIONS_V1.jsonl"
FOLD_DIAG=OUT/"V1_2_4_OOS_FOLD_DIAGNOSTICS_V1.json"
PRED_FREEZE=OUT/"V1_2_4_OOS_PREDICTION_FREEZE_V1.json"
EVAL=OUT/"V1_2_4_OOS_EVALUATION_V1.json"
EVAL_AUDIT=OUT/"V1_2_4_OOS_EVALUATION_AUDIT_V1.md"
EVAL_FREEZE=OUT/"V1_2_4_OOS_EVALUATION_FREEZE_V1.json"
LOCK_PATH=Path("/home/ubuntu/data/thestatsapi/v1_2_4_predictive_oos.lock")
CHAMPION=Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")
CHAMPION_SHA="0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"
CACHE="/home/ubuntu/data/thestatsapi/championship"
N_OUTER_JOBS=4

def fsha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a:str)->str: return subprocess.run(["git","-C",str(ROOT),*a],check=True,capture_output=True,text=True).stdout.strip()

@contextmanager
def _execution_lock():
    """Fail closed if another V1.2.4 predict/evaluate process is active."""
    LOCK_PATH.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(LOCK_PATH,os.O_CREAT|os.O_RDWR,0o644)
    acquired=False
    try:
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            acquired=True
        except BlockingIOError:
            raise SystemExit("EXECUTION_ALREADY_RUNNING")
        os.ftruncate(fd,0)
        os.write(fd,f"pid={os.getpid()}\n".encode())
        os.fsync(fd)
        yield
    finally:
        if acquired:
            fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)

def _tmp_path(path:Path)->Path:
    return path.with_name(f".{path.name}.tmp.{os.getpid()}")

def _atomic_publish_text(path:Path,text_value:str)->None:
    tmp=_tmp_path(path)
    if tmp.exists(): raise SystemExit(f"STALE_TEMP_EXISTS:{tmp}")
    with tmp.open("x") as f:
        f.write(text_value); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)
    dfd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)

def _atomic_publish_jsonl(path:Path,rows)->None:
    tmp=_tmp_path(path)
    if tmp.exists(): raise SystemExit(f"STALE_TEMP_EXISTS:{tmp}")
    with tmp.open("x") as f:
        for row in rows:
            f.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n")
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)
    dfd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)

def _load_matrix_paths(manifest:Dict[str,Any],family:str):
    tag=family.lower()
    m0=next(Path(p) for p in manifest["files"] if p.endswith(f"{tag}_m0_strong.npy"))
    llm=next(Path(p) for p in manifest["files"] if p.endswith(f"{tag}_llm.npy"))
    for p in (m0,llm):
        if fsha(p)!=manifest["files"][str(p)]["sha256"]: raise RuntimeError(f"MATRIX_HASH_MISMATCH:{p}")
    return m0,llm

def _fit_job(job:Dict[str,Any])->Dict[str,Any]:
    m0=np.load(job["m0_path"],mmap_mode="r",allow_pickle=False)
    llm=np.load(job["llm_path"],mmap_mode="r",allow_pickle=False)
    tr=np.asarray(job["train_idx"],int); te=np.asarray(job["test_idx"],int); y=np.asarray(job["y"],float)
    X0tr=np.asarray(m0[tr],float); X0te=np.asarray(m0[te],float)
    XLtr=np.asarray(llm[tr],float); XLte=np.asarray(llm[te],float)
    k0=coverage_keep(X0tr,0.60); kl=coverage_keep(XLtr,0.60)
    if len(k0)<3:
        return {**job["meta"],"status":"UNFIT_M0_LT3_FEATURES","n_m0_kept":len(k0),"n_llm_kept":len(kl)}
    A0tr=X0tr[:,k0]; A0te=X0te[:,k0]
    A1tr=np.column_stack([A0tr,XLtr[:,kl]]) if kl else A0tr.copy()
    A1te=np.column_stack([A0te,XLte[:,kl]]) if kl else A0te.copy()
    r0=fit_arm(A0tr,y[tr],A0te); r1=fit_arm(A1tr,y[tr],A1te)
    diag={**job["meta"],"n_train":len(tr),"n_test":len(te),"n_m0_kept":len(k0),"n_llm_kept":len(kl),
          "m0_status":r0["status"],"m1_status":r1["status"],"m0_kept_indices":k0,"llm_kept_indices":kl}
    if r0["status"]!="FIT" or r1["status"]!="FIT":
        diag["status"]="SKIPPED_ARM_FIT_FAILURE"; return diag
    diag.update({"status":"FIT",
      "m0_selected_C":r0["selected_C"],"m0_selected_l1_ratio":r0["selected_l1_ratio"],
      "m1_selected_C":r1["selected_C"],"m1_selected_l1_ratio":r1["selected_l1_ratio"],
      "m0_cv_best_mean_neg_log_loss":r0["cv_best_mean_neg_log_loss"],
      "m1_cv_best_mean_neg_log_loss":r1["cv_best_mean_neg_log_loss"],
      "m0_n_calibration_pairs":r0["n_calibration_pairs"],"m1_n_calibration_pairs":r1["n_calibration_pairs"],
      "m0_n_convergence_warnings":r0["n_convergence_warnings"],"m1_n_convergence_warnings":r1["n_convergence_warnings"],
      "m0_nonzero_coef":int(np.sum(np.abs(r0["coef"])>1e-8)),
      "m1_nonzero_m0_coef":int(np.sum(np.abs(r1["coef"][:len(k0)])>1e-8)),
      "m1_nonzero_llm_coef":int(np.sum(np.abs(r1["coef"][len(k0):])>1e-8)),
      "p0_raw":[float(x) for x in r0["raw"]],"p1_raw":[float(x) for x in r1["raw"]],
      "p0":[float(x) for x in r0["final"]],"p1":[float(x) for x in r1["final"]]})
    return diag

def _preflight(authorized_head:str)->Dict[str,Any]:
    if git("rev-parse","HEAD")!=authorized_head: raise SystemExit("HEAD_MISMATCH")
    if git("status","--porcelain"): raise SystemExit("WORKTREE_NOT_CLEAN")
    if not BINDING.exists(): raise SystemExit("BINDING_MISSING")
    stale=sorted(OUT.glob(".V1_2_4_*.tmp.*"))
    if stale: raise SystemExit("STALE_TEMP_ARTIFACTS:"+",".join(str(p) for p in stale))
    if fsha(CHAMPION)!=CHAMPION_SHA: raise SystemExit("CHAMPION_HASH_MISMATCH")
    b=json.loads(BINDING.read_text())
    for rel,h in b["source_hashes"].items():
        p=ROOT/rel
        if fsha(p)!=h: raise SystemExit(f"SOURCE_HASH_MISMATCH:{rel}")
    for rel,h in b["frozen_inputs"].items():
        p=Path(rel) if rel.startswith("/") else ROOT/rel
        if fsha(p)!=h: raise SystemExit(f"FROZEN_INPUT_HASH_MISMATCH:{rel}")
    return b

def predict(authorized_head:str)->None:
    b=_preflight(authorized_head)
    for p in (PRED,FOLD_DIAG,PRED_FREEZE):
        if p.exists(): raise SystemExit(f"OUTPUT_ALREADY_EXISTS:{p}")
    ff=json.loads(FEATURE_FREEZE.read_text())
    folds=json.loads(V.FOLDS.read_text()); rows=folds["rows"]
    base,_=CP.load_history(CACHE,include_gap_fetches=False)
    if len(rows)!=5620: raise SystemExit("ROW_COUNT_MISMATCH")
    primary=set(b["scoring_sets"]["primary_ids"]); strict=set(b["scoring_sets"]["strict_unseen_ids"])
    jobs=[]
    for target in b["primary_targets"]:
        family=target["family"]; m0p,llmp=_load_matrix_paths(ff,family)
        y=np.full(len(rows),np.nan,dtype=float)
        for i,r in enumerate(rows):
            v=V.label_for_target(base[r["match_id"]],target)
            if v is not None: y[i]=float(v)
        for fid,fd in sorted(folds["folds"].items(),key=lambda kv:int(kv[0])):
            tr=[i for i,r in enumerate(rows) if float(r["kickoff"])<float(fd["test_start"]) and np.isfinite(y[i])]
            te=[i for i,r in enumerate(rows) if str(r["fold"])==str(fid) and np.isfinite(y[i])]
            jobs.append({"m0_path":str(m0p),"llm_path":str(llmp),"train_idx":tr,"test_idx":te,
                         "y":y.tolist(),"meta":{"target_id":target["target_id"],"market_id":target["market_id"],
                         "family":family,"fold":int(fid),"line":target["line"]}})
    results=[]
    with cf.ProcessPoolExecutor(max_workers=N_OUTER_JOBS) as ex:
        futs=[ex.submit(_fit_job,j) for j in jobs]
        for fut in cf.as_completed(futs): results.append(fut.result())
    results.sort(key=lambda x:(x["family"],x["target_id"],x["fold"]))
    pred_rows=[]; diag=[]
    for r in results:
        rr=dict(r)
        p0=rr.pop("p0",[]); p1=rr.pop("p1",[]); raw0=rr.pop("p0_raw",[]); raw1=rr.pop("p1_raw",[])
        if rr["status"]=="FIT":
            target=next(t for t in b["primary_targets"] if t["target_id"]==rr["target_id"])
            y=np.full(len(rows),np.nan,dtype=float)
            for i,row in enumerate(rows):
                v=V.label_for_target(base[row["match_id"]],target)
                if v is not None: y[i]=float(v)
            te=[i for i,row in enumerate(rows) if str(row["fold"])==str(rr["fold"]) and np.isfinite(y[i])]
            if not (len(te)==len(p0)==len(p1)): raise RuntimeError("PREDICTION_LENGTH_MISMATCH")
            for k,i in enumerate(te):
                row=rows[i]; mid=row["match_id"]
                pred_rows.append({"match_id":mid,"kickoff":row["kickoff"],"fold":rr["fold"],
                  "target_id":rr["target_id"],"market_id":rr["market_id"],"family":rr["family"],
                  "line":rr["line"],"y":int(y[i]),"p0_raw":raw0[k],"p1_raw":raw1[k],
                  "p0":p0[k],"p1":p1[k],"is_primary":mid in primary,"is_strict_unseen":mid in strict})
        diag.append(rr)
    pred_rows.sort(key=lambda x:(x["target_id"],x["fold"],x["kickoff"],x["match_id"]))
    _atomic_publish_jsonl(PRED,pred_rows)
    fold_doc={"artifact_version":"target_aware_v1_2_4_oos_fold_diagnostics_v1",
      "authorized_execution_head":authorized_head,"binding_sha256":fsha(BINDING),
      "n_jobs":len(diag),"jobs":diag,"target_outcomes_read":True,"market_results_read":False,
      "model_fit":True,"oos_executed":True,"champion_sha256":fsha(CHAMPION)}
    _atomic_publish_text(FOLD_DIAG,json.dumps(fold_doc,indent=1,sort_keys=True)+"\n")
    freeze={"artifact_version":"target_aware_v1_2_4_oos_prediction_freeze_v1",
      "authorized_execution_head":authorized_head,"binding_sha256":fsha(BINDING),
      "predictions_sha256":fsha(PRED),"fold_diagnostics_sha256":fsha(FOLD_DIAG),
      "n_prediction_rows":len(pred_rows),"n_fit_jobs":sum(1 for x in diag if x["status"]=="FIT"),
      "n_skipped_jobs":sum(1 for x in diag if x["status"]!="FIT"),
      "target_outcomes_read":True,"market_results_read":False,"model_fit":True,"oos_executed":True,
      "champion_sha256":fsha(CHAMPION),"champion_changed":False}
    _atomic_publish_text(PRED_FREEZE,json.dumps(freeze,indent=1,sort_keys=True)+"\n")
    print(json.dumps({"status":"V1_2_4_OOS_PREDICTIONS_FROZEN","prediction_freeze_sha256":fsha(PRED_FREEZE),
      "n_prediction_rows":len(pred_rows),"n_fit_jobs":freeze["n_fit_jobs"],"n_skipped_jobs":freeze["n_skipped_jobs"]},indent=2))

def _group(rows,flag:str):
    out={f:{} for f in EV.FAMILY_ORDER}
    for r in rows:
        if flag!="all" and not r[flag]:
            continue
        out[r["family"]].setdefault(r["target_id"],[]).append(r)
    return out

def _compare_set(rows,flag:str)->Dict[str,Any]:
    grouped=_group(rows,flag); comps={}; rawp={}
    for fam in EV.FAMILY_ORDER:
        c=EV.family_compare(grouped.get(fam,{}))
        comps[fam]=c
        rawp[fam]=float(c["one_sided_p"]) if c.get("status")=="OK" else 1.0
    adj=EV.holm_adjust(rawp)
    return {"comparisons":comps,"raw_p_for_holm":rawp,"holm_adjusted_p":adj}

def evaluate(authorized_head:str)->None:
    _preflight(authorized_head)
    if EVAL.exists() or EVAL_AUDIT.exists() or EVAL_FREEZE.exists():
        raise SystemExit("EVALUATION_OUTPUT_EXISTS")
    if not (PRED.exists() and FOLD_DIAG.exists() and PRED_FREEZE.exists()):
        raise SystemExit("PREDICTION_FREEZE_MISSING")
    pf=json.loads(PRED_FREEZE.read_text())
    if fsha(PRED)!=pf["predictions_sha256"] or fsha(FOLD_DIAG)!=pf["fold_diagnostics_sha256"]:
        raise SystemExit("PREDICTION_HASH_MISMATCH")
    if pf["binding_sha256"]!=fsha(BINDING):
        raise SystemExit("BINDING_HASH_MISMATCH")
    rows=[json.loads(x) for x in PRED.read_text().splitlines() if x.strip()]
    primary=_compare_set(rows,"is_primary")
    strict=_compare_set(rows,"is_strict_unseen")
    all_oos=_compare_set(rows,"all")
    gates={}
    for fam in EV.FAMILY_ORDER:
        gates[fam]=EV.gate(primary["comparisons"][fam],primary["holm_adjusted_p"][fam])
    passing=[f for f in EV.FAMILY_ORDER if gates[f]["pass"]]
    doc={"artifact_version":"target_aware_v1_2_4_oos_evaluation_v1",
      "authorized_evaluation_head":authorized_head,"binding_sha256":fsha(BINDING),
      "prediction_freeze_sha256":fsha(PRED_FREEZE),
      "primary_scoring_set":{"role":"FROZEN PRIMARY retrospective transferability screen",
                             "n_unique_fixtures":len({r["match_id"] for r in rows if r["is_primary"]}),
                             **primary},
      "strict_unseen_robustness":{"role":"SECONDARY robustness; not a replacement primary endpoint",
                                  "n_unique_fixtures":len({r["match_id"] for r in rows if r["is_strict_unseen"]}),
                                  **strict},
      "all_oos_secondary":{"role":"SECONDARY all frozen OOS rows",
                           "n_unique_fixtures":len({r["match_id"] for r in rows}),**all_oos},
      "family_gates":gates,"families_passing_primary_gate":passing,
      "interpretation":{
        "historical_pass_means":"incremental retrospective predictive information beyond the strengthened deterministic baseline under the frozen screen",
        "historical_pass_does_not_mean":"prospective validation, market edge, production readiness, or CHAMPION promotion",
        "prospective_validation_required_for_promotion":True},
      "target_outcomes_read":True,"market_results_read":False,"model_fit":True,"oos_executed":True,
      "champion_sha256":fsha(CHAMPION),"champion_changed":False}
    _atomic_publish_text(EVAL,json.dumps(doc,indent=1,sort_keys=True)+"\n")
    lines=["# V1.2.4 Strong-Baseline OOS Evaluation","",
      f"- Frozen primary fixtures: **{doc['primary_scoring_set']['n_unique_fixtures']}**",
      f"- Strict unseen-team robustness fixtures: **{doc['strict_unseen_robustness']['n_unique_fixtures']}**",
      f"- Families passing the frozen primary gate: **{', '.join(passing) if passing else 'none'}**","",
      "| Family | Delta log loss M0-M1 | 95% CI | Holm p | ECE M0 | ECE M1 | Gate |",
      "|---|---:|---:|---:|---:|---:|---|"]
    for fam in EV.FAMILY_ORDER:
        c=primary["comparisons"][fam]; g=gates[fam]
        if c.get("status")=="OK":
            lines.append(f"| {fam} | {c['delta_logloss_m0_minus_m1']:.6f} | [{c['ci_lower']:.6f}, {c['ci_upper']:.6f}] | {primary['holm_adjusted_p'][fam]:.6f} | {c['ece_m0']:.6f} | {c['ece_m1']:.6f} | {'PASS' if g['pass'] else 'FAIL'} |")
        else:
            lines.append(f"| {fam} | NA | NA | {primary['holm_adjusted_p'][fam]:.6f} | NA | NA | FAIL |")
    lines += ["","This is a retrospective transferability screen. Prospective validation remains mandatory before any feature promotion or CHAMPION change.","",
      "Evaluation artifact SHA256: "+fsha(EVAL),"CHAMPION unchanged."]
    _atomic_publish_text(EVAL_AUDIT,"\n".join(lines)+"\n")
    eval_freeze={"artifact_version":"target_aware_v1_2_4_oos_evaluation_freeze_v1",
      "authorized_evaluation_head":authorized_head,"binding_sha256":fsha(BINDING),
      "prediction_freeze_sha256":fsha(PRED_FREEZE),"evaluation_sha256":fsha(EVAL),
      "evaluation_audit_sha256":fsha(EVAL_AUDIT),"families_passing_primary_gate":passing,
      "target_outcomes_read":True,"market_results_read":False,"model_fit":True,"oos_executed":True,
      "champion_sha256":fsha(CHAMPION),"champion_changed":False}
    _atomic_publish_text(EVAL_FREEZE,json.dumps(eval_freeze,indent=1,sort_keys=True)+"\n")
    print(json.dumps({"status":"V1_2_4_OOS_EVALUATION_COMPLETE","evaluation_sha256":fsha(EVAL),
      "evaluation_freeze_sha256":fsha(EVAL_FREEZE),
      "families_passing_primary_gate":passing,"champion_changed":False},indent=2))

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    for name in ("predict","evaluate"):
        p=sub.add_parser(name); p.add_argument("--authorized-head",required=True)
    a=ap.parse_args()
    with _execution_lock():
        if a.cmd=="predict":
            predict(a.authorized_head)
        else:
            evaluate(a.authorized_head)
if __name__=="__main__":
    main()
