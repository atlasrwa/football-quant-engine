"""Build and freeze outcome-blind V1.2.2 predictive feature matrices."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.research.target_aware_market_panel import predictive_v122 as V

OUT=ROOT/"research/target_aware_market_panel"
FAIR=OUT/"V1_2_2_PREDICTIVE_FAIRNESS_AUDIT_V1.json"
SUPPORT=OUT/"SOL_PANEL_SUPPORT_FREEZE_MANIFEST_V1_2_1.json"
MANIFEST=OUT/"V1_2_2_FEATURE_FREEZE_MANIFEST_V1.json"
DATA=Path("/home/ubuntu/data/target_aware_market_panel/v1_2_2_features")
FAIR_SHA="4f6395f1de25b28310849bdd43e72c1b1e8f27b28b68a6915b70b35cd04a0014"
SUPPORT_SHA="d21f4ec5226eb56977cef2c733edfcef1287e5d756220e6496797c6816f1b40d"
FOLD_SHA="f353068ec40864d56ac2c514a22e1199a9e237f58b1399e9739c71ae4488d3a1"
CHAMPION=Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")
CHAMPION_SHA="0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

def fsha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a): return subprocess.run(["git","-C",str(ROOT),*a],check=True,capture_output=True,text=True).stdout.strip()

def coverage_by_fold(x,folds):
    out={}
    rows=folds["rows"]
    for fid,fd in sorted(folds["folds"].items(),key=lambda kv:int(kv[0])):
        idx=[i for i,r in enumerate(rows) if float(r["kickoff"]) < float(fd["test_start"])]
        rate=np.mean(~np.isnan(x[idx]),axis=0)
        out[fid]={"n_train":len(idx),"n_ge_60":int(np.sum(rate>=0.60)),
                  "min":float(np.min(rate)) if len(rate) else None,
                  "median":float(np.median(rate)) if len(rate) else None,
                  "max":float(np.max(rate)) if len(rate) else None}
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--authorized-head",required=True); a=ap.parse_args()
    if git("rev-parse","HEAD")!=a.authorized_head: raise SystemExit("HEAD_MISMATCH")
    if git("status","--porcelain"): raise SystemExit("WORKTREE_NOT_CLEAN")
    if fsha(FAIR)!=FAIR_SHA or fsha(SUPPORT)!=SUPPORT_SHA or fsha(V.FOLDS)!=FOLD_SHA:
        raise SystemExit("FROZEN_INPUT_HASH_MISMATCH")
    if fsha(CHAMPION)!=CHAMPION_SHA: raise SystemExit("CHAMPION_HASH_MISMATCH")
    if MANIFEST.exists() or DATA.exists(): raise SystemExit("OUTPUT_ALREADY_EXISTS")
    DATA.mkdir(parents=True)
    base,pre,h=V.load_histories(); fixtures=V.fixtures_from_folds(base); V.memoize_history(h)
    folds=json.loads(V.FOLDS.read_text()); byfam=V.class_c_by_family()
    files={}; fammeta={}
    for fam in ("GOALS","CORNERS","TEAM_TOTALS","BOOKINGS"):
        m0n,m0,llmn,llm=V.build_family_matrix(h,fixtures,fam,byfam[fam])
        for kind,arr in (("m0",m0),("llm",llm)):
            path=DATA/f"{fam.lower()}_{kind}.npy"; np.save(path,arr,allow_pickle=False)
            files[str(path)]={"sha256":fsha(path),"shape":list(arr.shape),"dtype":str(arr.dtype)}
        fammeta[fam]={"m0_feature_names":m0n,"llm_feature_names":llmn,
                      "n_m0":len(m0n),"n_llm":len(llmn),
                      "m0_training_coverage":coverage_by_fold(m0,folds),
                      "llm_training_coverage":coverage_by_fold(llm,folds)}
    row_ids=[r["match_id"] for r in folds["rows"]]
    doc={"artifact_version":"target_aware_v1_2_2_feature_freeze_v1",
         "authorized_head":a.authorized_head,"fairness_audit_sha256":fsha(FAIR),
         "support_freeze_sha256":fsha(SUPPORT),"fold_manifest_sha256":fsha(V.FOLDS),
         "raw_prehistory_manifest_sha256":fsha(V.RAW_MANIFEST),
         "predictive_semantics_sha256":fsha(ROOT/"src/research/target_aware_market_panel/predictive_v122.py"),
         "row_order":"exact TARGET_AWARE_FOLD_MANIFEST_V1.json rows order",
         "n_rows":len(row_ids),
         "row_ids_sha256":hashlib.sha256("\n".join(row_ids).encode()).hexdigest(),
         "history_counts":{"base":len(base),"prehistory":len(pre),"combined":len(base)+len(pre)},
         "families":fammeta,"files":files,"champion_sha256":fsha(CHAMPION),
         "target_outcomes_read":False,"market_results_read":False,"model_fit":False,
         "oos_executed":False,"champion_changed":False}
    MANIFEST.write_text(json.dumps(doc,indent=1,sort_keys=True)+"\n")
    print(json.dumps({"status":"V1_2_2_FEATURE_FREEZE_COMPLETE","manifest_sha256":fsha(MANIFEST),
                      "n_rows":len(row_ids),"families":{k:{"n_m0":v["n_m0"],"n_llm":v["n_llm"]} for k,v in fammeta.items()},
                      "target_outcomes_read":False},indent=2,sort_keys=True))
if __name__=="__main__": main()
