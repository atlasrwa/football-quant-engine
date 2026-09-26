"""Execute V1.3 exploratory nested-stability experiment on frozen local data only."""
from __future__ import annotations
import argparse, concurrent.futures as cf, fcntl, hashlib, json, os, subprocess, sys
from pathlib import Path
from typing import Any, Dict
import numpy as np

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from src.research.item6.stage2.executor import fit_arm
from src.research.target_aware_market_panel import cohort_packets as CP
from src.research.target_aware_market_panel import predictive_v123 as BASE
from src.research.target_aware_market_panel import predictive_v13 as SEL
from src.research.target_aware_market_panel import predictive_eval_v123 as EV

OUT=ROOT/"research/target_aware_market_panel"
BINDING=OUT/"V1_3_EXPLORATORY_BINDING_V1.json"
FEATURE_FREEZE=OUT/"V1_2_3_FEATURE_FREEZE_MANIFEST_V1.json"
P0_SOURCE=OUT/"V1_2_4_OOS_PREDICTIONS_V1.jsonl"
PRED=OUT/"V1_3_EXPLORATORY_PREDICTIONS_V1.jsonl"
FOLD_DIAG=OUT/"V1_3_EXPLORATORY_FOLD_DIAGNOSTICS_V1.json"
PRED_FREEZE=OUT/"V1_3_EXPLORATORY_PREDICTION_FREEZE_V1.json"
EVAL=OUT/"V1_3_EXPLORATORY_EVALUATION_V1.json"
AUDIT=OUT/"V1_3_EXPLORATORY_EVALUATION_AUDIT_V1.md"
EVAL_FREEZE=OUT/"V1_3_EXPLORATORY_EVALUATION_FREEZE_V1.json"
CHAMPION=Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")
CHAMPION_SHA="0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"
CACHE="/home/ubuntu/data/thestatsapi/championship"
LOCK_PATH=Path("/home/ubuntu/data/thestatsapi/v1_3_exploratory.lock")
N_OUTER_JOBS=4

def fsha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a:str)->str: return subprocess.run(["git","-C",str(ROOT),*a],check=True,capture_output=True,text=True).stdout.strip()

class RunLock:
    def __enter__(self):
        LOCK_PATH.parent.mkdir(parents=True,exist_ok=True)
        self.fd=os.open(LOCK_PATH,os.O_CREAT|os.O_RDWR,0o644)
        try: fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd); raise SystemExit("V1_3_EXECUTION_LOCKED")
        os.ftruncate(self.fd,0); os.write(self.fd,f"{os.getpid()}\n".encode()); os.fsync(self.fd)
        return self
    def __exit__(self,*exc):
        fcntl.flock(self.fd,fcntl.LOCK_UN); os.close(self.fd)

def atomic_text(path:Path,text:str):
    tmp=path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with tmp.open("w") as f: f.write(text); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)

def atomic_jsonl(path:Path,rows):
    tmp=path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with tmp.open("w") as f:
        for r in rows: f.write(json.dumps(r,sort_keys=True,separators=(",",":"))+"\n")
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)

def _matrix_paths(manifest:Dict[str,Any],family:str):
    tag=family.lower()
    m0=next(Path(p) for p in manifest["files"] if p.endswith(f"{tag}_m0_strong.npy"))
    llm=next(Path(p) for p in manifest["files"] if p.endswith(f"{tag}_llm.npy"))
    for p in (m0,llm):
        if fsha(p)!=manifest["files"][str(p)]["sha256"]: raise RuntimeError(f"MATRIX_HASH_MISMATCH:{p}")
    return m0,llm

def _preflight(head:str)->Dict[str,Any]:
    if git("rev-parse","HEAD")!=head: raise SystemExit("HEAD_MISMATCH")
    if git("status","--porcelain"): raise SystemExit("WORKTREE_NOT_CLEAN")
    if not BINDING.exists(): raise SystemExit("BINDING_MISSING")
    if fsha(CHAMPION)!=CHAMPION_SHA: raise SystemExit("CHAMPION_HASH_MISMATCH")
    b=json.loads(BINDING.read_text())
    for rel,h in b["source_hashes"].items():
        p=ROOT/rel
        if fsha(p)!=h: raise SystemExit(f"SOURCE_HASH_MISMATCH:{rel}")
    for rel,h in b["frozen_inputs"].items():
        p=Path(rel) if rel.startswith("/") else ROOT/rel
        if fsha(p)!=h: raise SystemExit(f"FROZEN_INPUT_HASH_MISMATCH:{rel}")
    return b

def _fit_job(job:Dict[str,Any])->Dict[str,Any]:
    m0=np.load(job["m0_path"],mmap_mode="r",allow_pickle=False)
    llm=np.load(job["llm_path"],mmap_mode="r",allow_pickle=False)
    tr=np.asarray(job["train_idx"],int); te=np.asarray(job["test_idx"],int)
    y=np.asarray(job["y"],float)
    X0tr=np.asarray(m0[tr],float); X0te=np.asarray(m0[te],float)
    XLtr=np.asarray(llm[tr],float); XLte=np.asarray(llm[te],float)
    k0=SEL.coverage_keep(X0tr); kl=SEL.coverage_keep(XLtr)
    if len(k0)<3:
        return {**job["meta"],"status":"UNFIT_M0_LT3_FEATURES"}
    sel=SEL.stable_llm_selection(X0tr,XLtr,y[tr],k0,kl)
    selected=list(sel["selected_llm_indices"])
    diag={**job["meta"],"status":"SELECTION_COMPLETE","n_train":len(tr),"n_test":len(te),
          "n_m0_kept":len(k0),"n_llm_eligible":len(kl),"n_llm_selected":len(selected),
          "selected_llm_indices":selected,
          "selected_llm_names":[job["llm_names"][j] for j in selected],
          "selection":sel}
    if not selected:
        diag["status"]="FIT_ZERO_SELECTED_REUSE_M0"
        diag["p1"]=[]; diag["p1_raw"]=[]
        return diag
    A1tr=np.column_stack([X0tr[:,k0],XLtr[:,selected]])
    A1te=np.column_stack([X0te[:,k0],XLte[:,selected]])
    r=fit_arm(A1tr,y[tr],A1te)
    diag["m1_status"]=r["status"]
    if r["status"]!="FIT":
        diag["status"]="SKIPPED_M1_FIT_FAILURE"
        diag["error"]=r.get("error")
        return diag
    diag.update({"status":"FIT","selected_C":r["selected_C"],
      "selected_l1_ratio":r["selected_l1_ratio"],
      "cv_best_mean_neg_log_loss":r["cv_best_mean_neg_log_loss"],
      "n_calibration_pairs":r["n_calibration_pairs"],
      "n_convergence_warnings":r["n_convergence_warnings"],
      "m1_nonzero_m0_coef":int(np.sum(np.abs(r["coef"][:len(k0)])>1e-8)),
      "m1_nonzero_selected_llm_coef":int(np.sum(np.abs(r["coef"][len(k0):])>1e-8)),
      "p1":[float(x) for x in r["final"]],"p1_raw":[float(x) for x in r["raw"]]})
    return diag

def _load_p0():
    rows=[json.loads(x) for x in P0_SOURCE.read_text().splitlines() if x.strip()]
    m={}
    for r in rows:
        k=(r["target_id"],int(r["fold"]),r["match_id"])
        if k in m: raise RuntimeError(f"DUPLICATE_P0:{k}")
        m[k]=r
    return m

def predict(head:str):
    b=_preflight(head)
    for p in (PRED,FOLD_DIAG,PRED_FREEZE):
        if p.exists(): raise SystemExit(f"OUTPUT_ALREADY_EXISTS:{p}")
    ff=json.loads(FEATURE_FREEZE.read_text())
    folds=json.loads(BASE.FOLDS.read_text()); rows=folds["rows"]
    if any(rows[i]["kickoff"]>rows[i+1]["kickoff"] for i in range(len(rows)-1)):
        raise SystemExit("FOLD_ROWS_NOT_CHRONOLOGICAL")
    base,_=CP.load_history(CACHE,include_gap_fetches=False)
    p0map=_load_p0()
    primary=set(b["scoring_sets"]["primary_ids"]); strict=set(b["scoring_sets"]["strict_unseen_ids"])
    jobs=[]
    for target in b["primary_targets"]:
        family=target["family"]; m0p,llmp=_matrix_paths(ff,family)
        llm_names=ff["families"][family]["llm_feature_names"]
        y=np.full(len(rows),np.nan,float)
        for i,row in enumerate(rows):
            v=BASE.label_for_target(base[row["match_id"]],target)
            if v is not None: y[i]=float(v)
        for fid,fd in sorted(folds["folds"].items(),key=lambda kv:int(kv[0])):
            tr=[i for i,r in enumerate(rows) if float(r["kickoff"])<float(fd["test_start"]) and np.isfinite(y[i])]
            te=[i for i,r in enumerate(rows) if str(r["fold"])==str(fid) and np.isfinite(y[i])]
            jobs.append({"m0_path":str(m0p),"llm_path":str(llmp),"train_idx":tr,"test_idx":te,
                         "y":y.tolist(),"llm_names":llm_names,
                         "meta":{"target_id":target["target_id"],"market_id":target["market_id"],
                         "family":family,"fold":int(fid),"line":target["line"],"test_idx":te}})
    results=[]
    with cf.ProcessPoolExecutor(max_workers=N_OUTER_JOBS) as ex:
        futs=[ex.submit(_fit_job,j) for j in jobs]
        for fut in cf.as_completed(futs): results.append(fut.result())
    results.sort(key=lambda x:(x["family"],x["target_id"],x["fold"]))
    pred=[]; diag=[]
    for r in results:
        rr=dict(r); te=rr.pop("test_idx")
        p1=rr.pop("p1",[]); raw1=rr.pop("p1_raw",[])
        if rr["status"] not in ("FIT","FIT_ZERO_SELECTED_REUSE_M0"):
            diag.append(rr); continue
        for pos,i in enumerate(te):
            row=rows[i]; key=(rr["target_id"],int(rr["fold"]),row["match_id"])
            old=p0map.get(key)
            if old is None: raise RuntimeError(f"MISSING_FROZEN_M0:{key}")
            if rr["status"]=="FIT_ZERO_SELECTED_REUSE_M0":
                q1=float(old["p0"]); q1r=float(old["p0_raw"])
            else:
                q1=float(p1[pos]); q1r=float(raw1[pos])
            pred.append({"match_id":row["match_id"],"kickoff":row["kickoff"],"fold":rr["fold"],
              "target_id":rr["target_id"],"market_id":rr["market_id"],"family":rr["family"],
              "line":rr["line"],"y":int(old["y"]),"p0":float(old["p0"]),"p0_raw":float(old["p0_raw"]),
              "p1":q1,"p1_raw":q1r,"is_primary":row["match_id"] in primary,
              "is_strict_unseen":row["match_id"] in strict})
        diag.append(rr)
    pred.sort(key=lambda x:(x["target_id"],x["fold"],x["kickoff"],x["match_id"]))
    atomic_jsonl(PRED,pred)
    fdoc={"artifact_version":"target_aware_v1_3_exploratory_fold_diagnostics_v1",
      "authorized_execution_head":head,"binding_sha256":fsha(BINDING),"n_jobs":len(diag),
      "jobs":diag,"scientific_role":"EXPLORATORY_MODEL_DEVELOPMENT_ONLY",
      "provider_calls":0,"network_calls":0,"champion_sha256":fsha(CHAMPION)}
    atomic_text(FOLD_DIAG,json.dumps(fdoc,indent=1,sort_keys=True)+"\n")
    freeze={"artifact_version":"target_aware_v1_3_exploratory_prediction_freeze_v1",
      "authorized_execution_head":head,"binding_sha256":fsha(BINDING),
      "predictions_sha256":fsha(PRED),"fold_diagnostics_sha256":fsha(FOLD_DIAG),
      "n_prediction_rows":len(pred),"n_fit_or_zero_selected_jobs":sum(
        1 for x in diag if x["status"] in ("FIT","FIT_ZERO_SELECTED_REUSE_M0")),
      "n_failed_jobs":sum(1 for x in diag if x["status"] not in ("FIT","FIT_ZERO_SELECTED_REUSE_M0")),
      "provider_calls":0,"network_calls":0,"market_results_read":False,
      "champion_sha256":fsha(CHAMPION),"champion_changed":False}
    atomic_text(PRED_FREEZE,json.dumps(freeze,indent=1,sort_keys=True)+"\n")
    print(json.dumps({"status":"V1_3_EXPLORATORY_PREDICTIONS_FROZEN",
      "prediction_freeze_sha256":fsha(PRED_FREEZE),"n_prediction_rows":len(pred),
      "n_failed_jobs":freeze["n_failed_jobs"]},indent=2))

def _group(rows,flag:str):
    out={f:{} for f in EV.FAMILY_ORDER}
    for r in rows:
        if flag!="all" and not r[flag]: continue
        out[r["family"]].setdefault(r["target_id"],[]).append(r)
    return out

def _compare(rows,flag:str):
    grouped=_group(rows,flag); comps={}; rawp={}
    for fam in EV.FAMILY_ORDER:
        c=EV.family_compare(grouped.get(fam,{})); comps[fam]=c
        rawp[fam]=float(c["one_sided_p"]) if c.get("status")=="OK" else 1.0
    return {"comparisons":comps,"raw_p_for_holm":rawp,"holm_adjusted_p":EV.holm_adjust(rawp)}

def evaluate(head:str):
    b=_preflight(head)
    if EVAL.exists() or AUDIT.exists() or EVAL_FREEZE.exists(): raise SystemExit("EVALUATION_OUTPUT_EXISTS")
    if not (PRED.exists() and FOLD_DIAG.exists() and PRED_FREEZE.exists()):
        raise SystemExit("PREDICTION_FREEZE_MISSING")
    pf=json.loads(PRED_FREEZE.read_text())
    if fsha(PRED)!=pf["predictions_sha256"] or fsha(FOLD_DIAG)!=pf["fold_diagnostics_sha256"]:
        raise SystemExit("PREDICTION_HASH_MISMATCH")
    rows=[json.loads(x) for x in PRED.read_text().splitlines() if x.strip()]
    primary=_compare(rows,"is_primary"); strict=_compare(rows,"is_strict_unseen"); all_oos=_compare(rows,"all")
    screens={fam:EV.gate(primary["comparisons"][fam],primary["holm_adjusted_p"][fam]) for fam in EV.FAMILY_ORDER}
    screen_pass=[f for f in EV.FAMILY_ORDER if screens[f]["pass"]]
    fd=json.loads(FOLD_DIAG.read_text())
    sel_summary={}
    for fam in EV.FAMILY_ORDER:
        jj=[j for j in fd["jobs"] if j["family"]==fam]
        counts=[int(j.get("n_llm_selected",0)) for j in jj]
        freq={}
        for j in jj:
            for name in j.get("selected_llm_names",[]):
                freq[name]=freq.get(name,0)+1
        sel_summary[fam]={
          "n_jobs":len(jj),"selected_count_min":min(counts) if counts else 0,
          "selected_count_median":float(np.median(counts)) if counts else 0.0,
          "selected_count_max":max(counts) if counts else 0,
          "n_unique_llm_selected":len(freq),
          "feature_outer_job_frequency":dict(sorted(freq.items(),key=lambda kv:(-kv[1],kv[0]))),
          "zero_selected_jobs":sum(1 for c in counts if c==0)}
    doc={"artifact_version":"target_aware_v1_3_exploratory_evaluation_v1",
      "authorized_evaluation_head":head,"binding_sha256":fsha(BINDING),
      "prediction_freeze_sha256":fsha(PRED_FREEZE),
      "scientific_role":"EXPLORATORY_MODEL_DEVELOPMENT_ONLY",
      "primary_scoring_set":{"n_unique_fixtures":len({r["match_id"] for r in rows if r["is_primary"]}),**primary},
      "strict_unseen_robustness":{"n_unique_fixtures":len({r["match_id"] for r in rows if r["is_strict_unseen"]}),**strict},
      "all_oos_secondary":{"n_unique_fixtures":len({r["match_id"] for r in rows}),**all_oos},
      "exploratory_screen_checks":screens,"families_passing_exploratory_screen":screen_pass,
      "selection_summary":sel_summary,
      "interpretation":{
        "same_historical_oos_already_seen_in_v1_2_4":True,
        "independent_confirmation":False,
        "prospective_confirmation_required":True,
        "champion_promotion_allowed":False},
      "provider_calls":0,"network_calls":0,"market_results_read":False,
      "champion_sha256":fsha(CHAMPION),"champion_changed":False}
    atomic_text(EVAL,json.dumps(doc,indent=1,sort_keys=True)+"\n")
    lines=["# V1.3 Exploratory Nested-Stability Evaluation","",
      "**Role: exploratory model development only. This is not independent confirmation.**","",
      f"- Primary fixtures: **{doc['primary_scoring_set']['n_unique_fixtures']}**",
      f"- Strict unseen-team fixtures: **{doc['strict_unseen_robustness']['n_unique_fixtures']}**",
      f"- Families passing the old numerical screen descriptively: **{', '.join(screen_pass) if screen_pass else 'none'}**","",
      "| Family | Delta Log Loss M0-M1_STABLE | 95% CI | Holm p | Selected median [min,max] |",
      "|---|---:|---:|---:|---:|"]
    for fam in EV.FAMILY_ORDER:
        c=primary["comparisons"][fam]; s=sel_summary[fam]
        if c.get("status")=="OK":
            lines.append(f"| {fam} | {c['delta_logloss_m0_minus_m1']:.6f} | [{c['ci_lower']:.6f}, {c['ci_upper']:.6f}] | {primary['holm_adjusted_p'][fam]:.6f} | {s['selected_count_median']:.1f} [{s['selected_count_min']},{s['selected_count_max']}] |")
        else:
            lines.append(f"| {fam} | NA | NA | {primary['holm_adjusted_p'][fam]:.6f} | {s['selected_count_median']:.1f} [{s['selected_count_min']},{s['selected_count_max']}] |")
    lines += ["","No API/provider calls were made. CHAMPION unchanged.",
              "Any positive result requires a newly frozen prospective confirmation."]
    atomic_text(AUDIT,"\n".join(lines)+"\n")
    freeze={"artifact_version":"target_aware_v1_3_exploratory_evaluation_freeze_v1",
      "authorized_evaluation_head":head,"binding_sha256":fsha(BINDING),
      "prediction_freeze_sha256":fsha(PRED_FREEZE),"evaluation_sha256":fsha(EVAL),
      "audit_sha256":fsha(AUDIT),"families_passing_exploratory_screen":screen_pass,
      "scientific_role":"EXPLORATORY_MODEL_DEVELOPMENT_ONLY",
      "provider_calls":0,"network_calls":0,"champion_sha256":fsha(CHAMPION),"champion_changed":False}
    atomic_text(EVAL_FREEZE,json.dumps(freeze,indent=1,sort_keys=True)+"\n")
    print(json.dumps({"status":"V1_3_EXPLORATORY_EVALUATION_COMPLETE",
      "evaluation_sha256":fsha(EVAL),"evaluation_freeze_sha256":fsha(EVAL_FREEZE),
      "families_passing_exploratory_screen":screen_pass},indent=2))

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    for name in ("predict","evaluate"):
        q=sub.add_parser(name); q.add_argument("--authorized-head",required=True)
    a=ap.parse_args()
    with RunLock():
        (predict if a.cmd=="predict" else evaluate)(a.authorized_head)

if __name__=="__main__":
    main()
