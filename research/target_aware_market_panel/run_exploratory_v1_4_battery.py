"""Execute V1.4 exploratory multi-angle battery on frozen local data only."""
from __future__ import annotations
import argparse, concurrent.futures as cf, fcntl, hashlib, json, os, subprocess, sys
from pathlib import Path
from typing import Any, Dict, List
import numpy as np

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from src.research.item6.stage2.executor import fit_arm
from src.research.target_aware_market_panel import cohort_packets as CP
from src.research.target_aware_market_panel import predictive_v123 as BASE
from src.research.target_aware_market_panel import predictive_v14 as V14
from src.research.target_aware_market_panel import predictive_eval_v123 as EV

OUT=ROOT/"research/target_aware_market_panel"
BINDING=OUT/"V1_4_EXPLORATORY_ANGLE_BATTERY_BINDING_V1.json"
FEATURE_FREEZE=OUT/"V1_2_3_FEATURE_FREEZE_MANIFEST_V1.json"
TEMPLATE_REGISTRY=OUT/"SOL_CLASS_C_TEMPLATE_REGISTRY_V1.json"
P0_SOURCE=OUT/"V1_2_4_OOS_PREDICTIONS_V1.jsonl"
PRED=OUT/"V1_4_EXPLORATORY_ANGLE_BATTERY_PREDICTIONS_V1.jsonl"
DIAG=OUT/"V1_4_EXPLORATORY_ANGLE_BATTERY_DIAGNOSTICS_V1.json"
PRED_FREEZE=OUT/"V1_4_EXPLORATORY_ANGLE_BATTERY_PREDICTION_FREEZE_V1.json"
EVAL=OUT/"V1_4_EXPLORATORY_ANGLE_BATTERY_EVALUATION_V1.json"
AUDIT=OUT/"V1_4_EXPLORATORY_ANGLE_BATTERY_AUDIT_V1.md"
EVAL_FREEZE=OUT/"V1_4_EXPLORATORY_ANGLE_BATTERY_EVALUATION_FREEZE_V1.json"
CHAMPION=Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")
CHAMPION_SHA="0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"
CACHE="/home/ubuntu/data/thestatsapi/championship"
LOCK_PATH=Path("/home/ubuntu/data/thestatsapi/v1_4_angle_battery.lock")
N_OUTER_JOBS=4
METHODS=("LLM_ONLY_LOGIT","PCA80_LOGIT","ORTHO_RIDGE_LOGIT",
         "GOALS_MULTI_ONLY_LOGIT","GOALS_SIM_ONLY_LOGIT","HGB_RAW_PARITY")

def fsha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a:str)->str:return subprocess.run(["git","-C",str(ROOT),*a],check=True,capture_output=True,text=True).stdout.strip()

class RunLock:
    def __enter__(self):
        LOCK_PATH.parent.mkdir(parents=True,exist_ok=True)
        self.fd=os.open(LOCK_PATH,os.O_CREAT|os.O_RDWR,0o644)
        try:fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd);raise SystemExit("V1_4_EXECUTION_LOCKED")
        os.ftruncate(self.fd,0);os.write(self.fd,f"{os.getpid()}\n".encode());os.fsync(self.fd)
        return self
    def __exit__(self,*exc):
        fcntl.flock(self.fd,fcntl.LOCK_UN);os.close(self.fd)

def atomic_text(path:Path,text:str):
    tmp=path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with tmp.open("w") as f:f.write(text);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def atomic_jsonl(path:Path,rows):
    tmp=path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with tmp.open("w") as f:
        for r in rows:f.write(json.dumps(r,sort_keys=True,separators=(",",":"))+"\n")
        f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def _matrix_paths(manifest:Dict[str,Any],family:str):
    tag=family.lower()
    m0=next(Path(p) for p in manifest["files"] if p.endswith(f"{tag}_m0_strong.npy"))
    llm=next(Path(p) for p in manifest["files"] if p.endswith(f"{tag}_llm.npy"))
    for p in (m0,llm):
        if fsha(p)!=manifest["files"][str(p)]["sha256"]:raise RuntimeError(f"MATRIX_HASH_MISMATCH:{p}")
    return m0,llm

def _load_p0():
    out={}
    for x in P0_SOURCE.read_text().splitlines():
        if not x.strip():continue
        r=json.loads(x);k=(r["target_id"],int(r["fold"]),r["match_id"])
        if k in out:raise RuntimeError(f"DUPLICATE_P0:{k}")
        out[k]=r
    return out

def _template_type_indices(ff:Dict[str,Any])->Dict[str,Dict[str,List[int]]]:
    reg=json.loads(TEMPLATE_REGISTRY.read_text())
    bysig={t["canonical_signature_sha256"]:t["template_type"] for t in reg["templates"]}
    out={}
    for fam,meta in ff["families"].items():
        m={}
        for i,name in enumerate(meta["llm_feature_names"]):
            typ=bysig.get(name.split("M1.",1)[-1],"UNKNOWN")
            m.setdefault(typ,[]).append(i)
        out[fam]=m
    return out

def _preflight(head:str)->Dict[str,Any]:
    if git("rev-parse","HEAD")!=head:raise SystemExit("HEAD_MISMATCH")
    if git("status","--porcelain"):raise SystemExit("WORKTREE_NOT_CLEAN")
    if not BINDING.exists():raise SystemExit("BINDING_MISSING")
    if fsha(CHAMPION)!=CHAMPION_SHA:raise SystemExit("CHAMPION_HASH_MISMATCH")
    b=json.loads(BINDING.read_text())
    for rel,h in b["source_hashes"].items():
        p=ROOT/rel
        if fsha(p)!=h:raise SystemExit(f"SOURCE_HASH_MISMATCH:{rel}")
    for rel,h in b["frozen_inputs"].items():
        p=Path(rel) if rel.startswith("/") else ROOT/rel
        if fsha(p)!=h:raise SystemExit(f"FROZEN_INPUT_HASH_MISMATCH:{rel}")
    return b

def _fit_job(job:Dict[str,Any])->Dict[str,Any]:
    m0=np.load(job["m0_path"],mmap_mode="r",allow_pickle=False)
    llm=np.load(job["llm_path"],mmap_mode="r",allow_pickle=False)
    tr=np.asarray(job["train_idx"],int);te=np.asarray(job["test_idx"],int);y=np.asarray(job["y"],float)
    X0tr=np.asarray(m0[tr],float);X0te=np.asarray(m0[te],float)
    XLtr=np.asarray(llm[tr],float);XLte=np.asarray(llm[te],float)
    k0=V14.coverage_keep(X0tr);kl=V14.coverage_keep(XLtr)
    method=job["method"]
    diag={**job["meta"],"method":method,"n_train":len(tr),"n_test":len(te),
          "n_m0_kept":len(k0),"n_llm_kept":len(kl)}
    if method=="LLM_ONLY_LOGIT":
        if len(kl)<3:
            return {**diag,"status":"UNFIT_LLM_LT3","p1":[],"p1_raw":[]}
        r=fit_arm(XLtr[:,kl],y[tr],XLte[:,kl])
        diag["fit_status"]=r["status"]
        if r["status"]!="FIT":return {**diag,"status":"UNFIT","error":r.get("error"),"p1":[],"p1_raw":[]}
        return {**diag,"status":"FIT","fit_meta":{"C":r["selected_C"],"l1":r["selected_l1_ratio"]},
                "p1":[float(x) for x in r["final"]],"p1_raw":[float(x) for x in r["raw"]]}

    if method=="PCA80_LOGIT":
        A1tr,A1te,tmeta=V14.pca_augment(X0tr,X0te,XLtr,XLte,k0,kl)
        if not kl:
            return {**diag,"status":"ZERO_LLM_REUSE_M0","transform":tmeta,"p1":[],"p1_raw":[]}
        r=fit_arm(A1tr,y[tr],A1te);diag["fit_status"]=r["status"]
        if r["status"]!="FIT":return {**diag,"status":"UNFIT","transform":tmeta,"error":r.get("error"),"p1":[],"p1_raw":[]}
        return {**diag,"status":"FIT","transform":tmeta,
                "fit_meta":{"C":r["selected_C"],"l1":r["selected_l1_ratio"]},
                "p1":[float(x) for x in r["final"]],"p1_raw":[float(x) for x in r["raw"]]}

    if method=="ORTHO_RIDGE_LOGIT":
        A1tr,A1te,tmeta=V14.ortho_ridge_augment(X0tr,X0te,XLtr,XLte,k0,kl)
        if not kl:
            return {**diag,"status":"ZERO_LLM_REUSE_M0","transform":tmeta,"p1":[],"p1_raw":[]}
        r=fit_arm(A1tr,y[tr],A1te);diag["fit_status"]=r["status"]
        if r["status"]!="FIT":return {**diag,"status":"UNFIT","transform":tmeta,"error":r.get("error"),"p1":[],"p1_raw":[]}
        return {**diag,"status":"FIT","transform":tmeta,
                "fit_meta":{"C":r["selected_C"],"l1":r["selected_l1_ratio"]},
                "p1":[float(x) for x in r["final"]],"p1_raw":[float(x) for x in r["raw"]]}

    if method in ("GOALS_MULTI_ONLY_LOGIT","GOALS_SIM_ONLY_LOGIT"):
        typ="MULTI_DIMENSION_MATCHUP" if method=="GOALS_MULTI_ONLY_LOGIT" else "OPPONENT_SIMILARITY_CONDITIONAL"
        allowed=set(job["type_indices"].get(typ,[]));use=[j for j in kl if j in allowed]
        diag.update({"template_type":typ,"n_type_eligible":len(use)})
        if not use:
            return {**diag,"status":"ZERO_TYPE_REUSE_M0","p1":[],"p1_raw":[]}
        A1tr=np.column_stack([X0tr[:,k0],XLtr[:,use]])
        A1te=np.column_stack([X0te[:,k0],XLte[:,use]])
        r=fit_arm(A1tr,y[tr],A1te);diag["fit_status"]=r["status"]
        if r["status"]!="FIT":return {**diag,"status":"UNFIT","error":r.get("error"),"p1":[],"p1_raw":[]}
        return {**diag,"status":"FIT","fit_meta":{"C":r["selected_C"],"l1":r["selected_l1_ratio"]},
                "p1":[float(x) for x in r["final"]],"p1_raw":[float(x) for x in r["raw"]]}

    if method=="HGB_RAW_PARITY":
        if len(k0)<3:return {**diag,"status":"UNFIT_M0_LT3","p0":[],"p1":[],"p0_raw":[],"p1_raw":[]}
        A0tr=X0tr[:,k0];A0te=X0te[:,k0]
        A1tr=np.column_stack([A0tr,XLtr[:,kl]]) if kl else A0tr.copy()
        A1te=np.column_stack([A0te,XLte[:,kl]]) if kl else A0te.copy()
        r0=V14.fit_hgb_arm(A0tr,y[tr],A0te);r1=V14.fit_hgb_arm(A1tr,y[tr],A1te)
        diag.update({"m0_status":r0["status"],"m1_status":r1["status"]})
        if r0["status"]!="FIT" or r1["status"]!="FIT":
            return {**diag,"status":"UNFIT","p0":[],"p1":[],"p0_raw":[],"p1_raw":[]}
        return {**diag,"status":"FIT","p0":[float(x) for x in r0["final"]],
                "p1":[float(x) for x in r1["final"]],
                "p0_raw":[float(x) for x in r0["raw"]],"p1_raw":[float(x) for x in r1["raw"]],
                "n_calibration_pairs_m0":r0["n_calibration_pairs"],"n_calibration_pairs_m1":r1["n_calibration_pairs"]}
    raise RuntimeError(f"UNKNOWN_METHOD:{method}")

def predict(head:str)->None:
    b=_preflight(head)
    for p in (PRED,DIAG,PRED_FREEZE):
        if p.exists():raise SystemExit(f"OUTPUT_ALREADY_EXISTS:{p}")
    ff=json.loads(FEATURE_FREEZE.read_text())
    folds=json.loads(BASE.FOLDS.read_text());rows=folds["rows"]
    base,_=CP.load_history(CACHE,include_gap_fetches=False)
    p0map=_load_p0();type_idx=_template_type_indices(ff)
    primary=set(b["scoring_sets"]["primary_ids"]);strict=set(b["scoring_sets"]["strict_unseen_ids"])
    jobs=[]
    target_y={}
    for target in b["primary_targets"]:
        fam=target["family"];m0p,llmp=_matrix_paths(ff,fam)
        y=np.full(len(rows),np.nan,float)
        for i,row in enumerate(rows):
            v=BASE.label_for_target(base[row["match_id"]],target)
            if v is not None:y[i]=float(v)
        target_y[target["target_id"]]=y
        methods=["LLM_ONLY_LOGIT","PCA80_LOGIT","ORTHO_RIDGE_LOGIT","HGB_RAW_PARITY"]
        if fam=="GOALS":methods+=["GOALS_MULTI_ONLY_LOGIT","GOALS_SIM_ONLY_LOGIT"]
        for method in methods:
            for fid,fd in sorted(folds["folds"].items(),key=lambda kv:int(kv[0])):
                tr=[i for i,r in enumerate(rows) if float(r["kickoff"])<float(fd["test_start"]) and np.isfinite(y[i])]
                te=[i for i,r in enumerate(rows) if str(r["fold"])==str(fid) and np.isfinite(y[i])]
                jobs.append({"method":method,"m0_path":str(m0p),"llm_path":str(llmp),
                    "train_idx":tr,"test_idx":te,"y":y.tolist(),"type_indices":type_idx[fam],
                    "meta":{"target_id":target["target_id"],"market_id":target["market_id"],
                    "family":fam,"fold":int(fid),"line":target["line"]}})
    results=[]
    with cf.ProcessPoolExecutor(max_workers=N_OUTER_JOBS) as ex:
        futs=[ex.submit(_fit_job,j) for j in jobs]
        for fut in cf.as_completed(futs):results.append(fut.result())
    results.sort(key=lambda x:(x["method"],x["family"],x["target_id"],x["fold"]))
    pred=[];diag=[]
    tlookup={t["target_id"]:t for t in b["primary_targets"]}
    for r in results:
        rr=dict(r);p1=rr.pop("p1",[]);p1raw=rr.pop("p1_raw",[])
        p0=rr.pop("p0",[]);p0raw=rr.pop("p0_raw",[])
        ok=rr["status"] in ("FIT","ZERO_LLM_REUSE_M0","ZERO_TYPE_REUSE_M0")
        if not ok:
            diag.append(rr);continue
        y=target_y[rr["target_id"]]
        te=[i for i,row in enumerate(rows) if str(row["fold"])==str(rr["fold"]) and np.isfinite(y[i])]
        if rr["method"]=="HGB_RAW_PARITY":
            if not (len(te)==len(p0)==len(p1)):raise RuntimeError("HGB_PREDICTION_LENGTH_MISMATCH")
        elif rr["status"]=="FIT":
            if not (len(te)==len(p1)):raise RuntimeError("PREDICTION_LENGTH_MISMATCH")
        for pos,i in enumerate(te):
            row=rows[i];key=(rr["target_id"],int(rr["fold"]),row["match_id"]);old=p0map.get(key)
            if old is None:raise RuntimeError(f"MISSING_FROZEN_P0:{key}")
            if rr["method"]=="HGB_RAW_PARITY":
                q0=float(p0[pos]);q0r=float(p0raw[pos]);q1=float(p1[pos]);q1r=float(p1raw[pos])
                baseline_role="HGB_STRONG_M0"
            else:
                q0=float(old["p0"]);q0r=float(old["p0_raw"]);baseline_role="FROZEN_V1_2_4_STRONG_M0"
                if rr["status"] in ("ZERO_LLM_REUSE_M0","ZERO_TYPE_REUSE_M0"):
                    q1=q0;q1r=q0r
                else:
                    q1=float(p1[pos]);q1r=float(p1raw[pos])
            pred.append({"method":rr["method"],"baseline_role":baseline_role,
                "match_id":row["match_id"],"kickoff":row["kickoff"],"fold":rr["fold"],
                "target_id":rr["target_id"],"market_id":rr["market_id"],"family":rr["family"],
                "line":rr["line"],"y":int(old["y"]),"p0":q0,"p0_raw":q0r,"p1":q1,"p1_raw":q1r,
                "is_primary":row["match_id"] in primary,"is_strict_unseen":row["match_id"] in strict})
        diag.append(rr)
    pred.sort(key=lambda x:(x["method"],x["target_id"],x["fold"],x["kickoff"],x["match_id"]))
    atomic_jsonl(PRED,pred)
    ddoc={"artifact_version":"target_aware_v1_4_angle_battery_diagnostics_v1",
      "authorized_execution_head":head,"binding_sha256":fsha(BINDING),
      "n_jobs":len(diag),"n_fit_jobs":sum(x["status"]=="FIT" for x in diag),
      "n_reuse_jobs":sum(x["status"] in ("ZERO_LLM_REUSE_M0","ZERO_TYPE_REUSE_M0") for x in diag),
      "n_failed_jobs":sum(x["status"] not in ("FIT","ZERO_LLM_REUSE_M0","ZERO_TYPE_REUSE_M0") for x in diag),
      "jobs":diag,"provider_calls":0,"network_calls":0,"market_results_read":False,
      "champion_sha256":fsha(CHAMPION),"champion_changed":False}
    atomic_text(DIAG,json.dumps(ddoc,indent=1,sort_keys=True)+"\n")
    freeze={"artifact_version":"target_aware_v1_4_angle_battery_prediction_freeze_v1",
      "authorized_execution_head":head,"binding_sha256":fsha(BINDING),
      "predictions_sha256":fsha(PRED),"diagnostics_sha256":fsha(DIAG),
      "n_prediction_rows":len(pred),"n_jobs":len(diag),"n_failed_jobs":ddoc["n_failed_jobs"],
      "methods":list(METHODS),"provider_calls":0,"network_calls":0,"market_results_read":False,
      "champion_sha256":fsha(CHAMPION),"champion_changed":False}
    atomic_text(PRED_FREEZE,json.dumps(freeze,indent=1,sort_keys=True)+"\n")
    print(json.dumps({"status":"V1_4_ANGLE_BATTERY_PREDICTIONS_FROZEN",
      "prediction_freeze_sha256":fsha(PRED_FREEZE),"n_prediction_rows":len(pred),
      "n_jobs":len(diag),"n_failed_jobs":ddoc["n_failed_jobs"]},indent=2))

def _compare_method(rows:List[Dict[str,Any]],flag:str)->Dict[str,Any]:
    applicable=sorted({r["family"] for r in rows})
    grouped={f:{} for f in applicable}
    for r in rows:
        if flag!="all" and not r[flag]:continue
        grouped[r["family"]].setdefault(r["target_id"],[]).append(r)
    comps={};rawp={}
    for fam in applicable:
        c=EV.family_compare(grouped.get(fam,{}));comps[fam]=c
        rawp[fam]=float(c["one_sided_p"]) if c.get("status")=="OK" else 1.0
    adj=EV.holm_adjust(rawp) if rawp else {}
    return {"applicable_families":applicable,"comparisons":comps,
            "raw_p_for_holm":rawp,"holm_adjusted_p":adj}

def _reference_summary(path:Path)->Dict[str,Any]:
    d=json.loads(path.read_text())
    section=d["primary_scoring_set"]
    out={}
    for fam,c in section["comparisons"].items():
        out[fam]={"delta_logloss_m0_minus_m1":c.get("delta_logloss_m0_minus_m1"),
                  "ci_lower":c.get("ci_lower"),"ci_upper":c.get("ci_upper"),
                  "holm_adjusted_p":section["holm_adjusted_p"].get(fam)}
    return {"sha256":fsha(path),"families":out}

def evaluate(head:str)->None:
    _preflight(head)
    if EVAL.exists() or AUDIT.exists() or EVAL_FREEZE.exists():raise SystemExit("EVALUATION_OUTPUT_EXISTS")
    if not (PRED.exists() and DIAG.exists() and PRED_FREEZE.exists()):raise SystemExit("PREDICTION_FREEZE_MISSING")
    pf=json.loads(PRED_FREEZE.read_text())
    if fsha(PRED)!=pf["predictions_sha256"] or fsha(DIAG)!=pf["diagnostics_sha256"]:
        raise SystemExit("PREDICTION_HASH_MISMATCH")
    rows=[json.loads(x) for x in PRED.read_text().splitlines() if x.strip()]
    diag=json.loads(DIAG.read_text())
    methods={}
    for method in METHODS:
        mr=[r for r in rows if r["method"]==method]
        primary=_compare_method(mr,"is_primary");strict=_compare_method(mr,"is_strict_unseen");all_oos=_compare_method(mr,"all")
        screens={}
        for fam,c in primary["comparisons"].items():
            screens[fam]=EV.gate(c,primary["holm_adjusted_p"][fam])
        methods[method]={
          "n_prediction_rows":len(mr),
          "primary":{"n_unique_fixtures":len({r["match_id"] for r in mr if r["is_primary"]}),**primary},
          "strict_unseen":{"n_unique_fixtures":len({r["match_id"] for r in mr if r["is_strict_unseen"]}),**strict},
          "all_oos":{"n_unique_fixtures":len({r["match_id"] for r in mr}),**all_oos},
          "exploratory_screen_checks":screens,
          "families_passing_old_screen":[f for f,g in screens.items() if g["pass"]]}
    transform_summary={}
    for method in METHODS:
        jj=[j for j in diag["jobs"] if j["method"]==method]
        rec={"n_jobs":len(jj),"n_fit":sum(j["status"]=="FIT" for j in jj),
             "n_reuse":sum(j["status"] in ("ZERO_LLM_REUSE_M0","ZERO_TYPE_REUSE_M0") for j in jj),
             "n_failed":sum(j["status"] not in ("FIT","ZERO_LLM_REUSE_M0","ZERO_TYPE_REUSE_M0") for j in jj)}
        if method=="PCA80_LOGIT":
            vals=[j["transform"]["n_components"] for j in jj if j.get("transform")]
            rec["pca_components_min_median_max"]=[min(vals),float(np.median(vals)),max(vals)] if vals else []
        if method=="ORTHO_RIDGE_LOGIT":
            vals=[j["transform"]["alpha"] for j in jj if j.get("transform") and j["transform"]["alpha"] is not None]
            rec["ridge_alpha_counts"]={str(a):sum(float(x)==float(a) for x in vals) for a in sorted(set(vals))}
        if method.startswith("GOALS_"):
            vals=[j.get("n_type_eligible",0) for j in jj]
            rec["type_eligible_min_median_max"]=[min(vals),float(np.median(vals)),max(vals)] if vals else []
        transform_summary[method]=rec
    refs={
      "RAW_ALL_V1_2_4":_reference_summary(OUT/"V1_2_4_OOS_EVALUATION_V1.json"),
      "STABILITY_V1_3":_reference_summary(OUT/"V1_3_EXPLORATORY_EVALUATION_V1.json")
    }
    doc={"artifact_version":"target_aware_v1_4_angle_battery_evaluation_v1",
      "authorized_evaluation_head":head,"binding_sha256":fsha(BINDING),
      "prediction_freeze_sha256":fsha(PRED_FREEZE),
      "scientific_role":"EXPLORATORY_MODEL_DEVELOPMENT_ONLY",
      "methods":methods,"transform_summary":transform_summary,"reference_results":refs,
      "interpretation":{"independent_confirmation":False,"prospective_confirmation_required":True,
        "champion_promotion_allowed":False,"cross_test_winner_is_not_confirmatory":True},
      "provider_calls":0,"network_calls":0,"market_results_read":False,
      "champion_sha256":fsha(CHAMPION),"champion_changed":False}
    atomic_text(EVAL,json.dumps(doc,indent=1,sort_keys=True)+"\n")
    lines=["# V1.4 Exploratory LLM Angle Battery","",
      "**Development evidence only — the historical OOS period was already observed.**","",
      "| Method | Family | Delta Log Loss | 95% CI | Holm p | Old screen |",
      "|---|---|---:|---:|---:|---|"]
    for method in METHODS:
        pr=methods[method]["primary"]
        for fam in pr["applicable_families"]:
            c=pr["comparisons"][fam];g=methods[method]["exploratory_screen_checks"][fam]
            if c.get("status")=="OK":
                lines.append(f"| {method} | {fam} | {c['delta_logloss_m0_minus_m1']:.6f} | [{c['ci_lower']:.6f}, {c['ci_upper']:.6f}] | {pr['holm_adjusted_p'][fam]:.6f} | {'PASS' if g['pass'] else 'FAIL'} |")
    lines+=["","References: V1.2.4 raw-all and V1.3 stability are included in the JSON scorecard.",
      "No API/provider/network calls were made. CHAMPION unchanged.",
      "Any promising mechanism must be frozen prospectively before it can support a predictive claim."]
    atomic_text(AUDIT,"\n".join(lines)+"\n")
    freeze={"artifact_version":"target_aware_v1_4_angle_battery_evaluation_freeze_v1",
      "authorized_evaluation_head":head,"binding_sha256":fsha(BINDING),
      "prediction_freeze_sha256":fsha(PRED_FREEZE),"evaluation_sha256":fsha(EVAL),
      "audit_sha256":fsha(AUDIT),"methods":list(METHODS),
      "provider_calls":0,"network_calls":0,"champion_sha256":fsha(CHAMPION),"champion_changed":False}
    atomic_text(EVAL_FREEZE,json.dumps(freeze,indent=1,sort_keys=True)+"\n")
    print(json.dumps({"status":"V1_4_ANGLE_BATTERY_EVALUATION_COMPLETE",
      "evaluation_sha256":fsha(EVAL),"evaluation_freeze_sha256":fsha(EVAL_FREEZE)},indent=2))

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="cmd",required=True)
    for name in ("predict","evaluate"):
        q=sub.add_parser(name);q.add_argument("--authorized-head",required=True)
    a=ap.parse_args()
    with RunLock():(predict if a.cmd=="predict" else evaluate)(a.authorized_head)
if __name__=="__main__":main()
