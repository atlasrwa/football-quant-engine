"""Build V1.2.3 strong-baseline feature freeze without reading target labels."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from src.research.target_aware_market_panel import predictive_v123 as V

OUT=ROOT/"research/target_aware_market_panel"
OLD=OUT/"V1_2_2_FEATURE_FREEZE_MANIFEST_V1.json"
ABORT=OUT/"V1_2_2_PREOUTCOME_ABORT_V1.json"
MANIFEST=OUT/"V1_2_3_FEATURE_FREEZE_MANIFEST_V1.json"
DATA=Path("/home/ubuntu/data/target_aware_market_panel/v1_2_3_features")
OLD_SHA="e4ff5e59331035605ac76687aaf0d30e020e925aab0e2f573356ea6a79289e07"
ABORT_SHA="1c0183478076babe5edb96ace29330a57d82de980bbf3810aa23876b033a3396"
CHAMPION=Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")
CHAMPION_SHA="0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

def fsha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a): return subprocess.run(["git","-C",str(ROOT),*a],check=True,capture_output=True,text=True).stdout.strip()

def cov(x,folds):
    out={}
    for fid,fd in sorted(folds["folds"].items(),key=lambda kv:int(kv[0])):
        ix=[i for i,r in enumerate(folds["rows"]) if float(r["kickoff"])<float(fd["test_start"])]
        rate=np.mean(~np.isnan(x[ix]),axis=0)
        out[fid]={"n_train":len(ix),"n_ge_60":int(np.sum(rate>=0.60)),
                  "min":float(rate.min()),"median":float(np.median(rate)),"max":float(rate.max())}
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--authorized-head",required=True); a=ap.parse_args()
    if git("rev-parse","HEAD")!=a.authorized_head: raise SystemExit("HEAD_MISMATCH")
    if git("status","--porcelain"): raise SystemExit("WORKTREE_NOT_CLEAN")
    if fsha(OLD)!=OLD_SHA or fsha(ABORT)!=ABORT_SHA or fsha(CHAMPION)!=CHAMPION_SHA:
        raise SystemExit("FROZEN_INPUT_HASH_MISMATCH")
    if DATA.exists() or MANIFEST.exists(): raise SystemExit("OUTPUT_ALREADY_EXISTS")
    old=json.loads(OLD.read_text()); folds=json.loads(V.FOLDS.read_text())
    base,pre,h=V.load_histories(); fixtures=V.fixtures_from_folds(base); V.memoize_history(h)
    DATA.mkdir(parents=True)
    files={}; fams={}
    for fam in ("GOALS","CORNERS","TEAM_TOTALS","BOOKINGS"):
        om=old["families"][fam]
        old_m0_path=next(Path(k) for k in old["files"] if k.endswith(f"{fam.lower()}_m0.npy"))
        old_llm_path=next(Path(k) for k in old["files"] if k.endswith(f"{fam.lower()}_llm.npy"))
        if fsha(old_m0_path)!=old["files"][str(old_m0_path)]["sha256"] or fsha(old_llm_path)!=old["files"][str(old_llm_path)]["sha256"]:
            raise SystemExit(f"OLD_MATRIX_HASH_MISMATCH:{fam}")
        old_m0=np.load(old_m0_path,allow_pickle=False)
        llm=np.load(old_llm_path,allow_pickle=False)
        sn,sx=V.build_strong_matrix(h,fixtures,fam)
        strong=np.column_stack([old_m0,sx])
        mp=DATA/f"{fam.lower()}_m0_strong.npy"; lp=DATA/f"{fam.lower()}_llm.npy"
        np.save(mp,strong,allow_pickle=False); np.save(lp,llm,allow_pickle=False)
        files[str(mp)]={"sha256":fsha(mp),"shape":list(strong.shape),"dtype":str(strong.dtype)}
        files[str(lp)]={"sha256":fsha(lp),"shape":list(llm.shape),"dtype":str(llm.dtype),
                        "source_v1_2_2_sha256":old["files"][str(old_llm_path)]["sha256"]}
        names=list(om["m0_feature_names"])+sn
        fams[fam]={"m0_feature_names":names,"llm_feature_names":list(om["llm_feature_names"]),
                   "n_original_m0":len(om["m0_feature_names"]),"n_added_strong_controls":len(sn),
                   "n_m0":len(names),"n_llm":len(om["llm_feature_names"]),
                   "m0_training_coverage":cov(strong,folds),"llm_training_coverage":cov(llm,folds)}
    doc={"artifact_version":"target_aware_v1_2_3_feature_freeze_v1",
         "authorized_head":a.authorized_head,"parent_v1_2_2_feature_freeze_sha256":OLD_SHA,
         "v1_2_2_preoutcome_abort_sha256":ABORT_SHA,
         "repair_scope":"append deterministic multi-season W20, same-venue W10, and all-prior EWMA-H10 controls to M0; M1 receives identical baseline controls; Sol matrices unchanged",
         "n_rows":5620,"families":fams,"files":files,
         "predictive_v123_sha256":fsha(ROOT/"src/research/target_aware_market_panel/predictive_v123.py"),
         "champion_sha256":fsha(CHAMPION),"target_outcomes_read":False,"market_results_read":False,
         "model_fit":False,"oos_executed":False,"champion_changed":False}
    MANIFEST.write_text(json.dumps(doc,indent=1,sort_keys=True)+"\n")
    print(json.dumps({"status":"V1_2_3_FEATURE_FREEZE_COMPLETE","manifest_sha256":fsha(MANIFEST),
                      "families":{f:{"n_m0":x["n_m0"],"n_llm":x["n_llm"]} for f,x in fams.items()},
                      "target_outcomes_read":False},indent=2,sort_keys=True))
if __name__=="__main__": main()
