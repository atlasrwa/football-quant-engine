"""Freeze V1.3 exploratory execution binding before V1.3 fits."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
OUT=ROOT/"research/target_aware_market_panel"
BINDING=OUT/"V1_3_EXPLORATORY_BINDING_V1.json"
PROTOCOL=OUT/"V1_3_EXPLORATORY_PROTOCOL_V1.json"
FEATURE_FREEZE=OUT/"V1_2_3_FEATURE_FREEZE_MANIFEST_V1.json"
V124_BINDING=OUT/"V1_2_4_PREDICTIVE_OOS_BINDING_V1.json"
V124_PRED=OUT/"V1_2_4_OOS_PREDICTIONS_V1.jsonl"
V124_EVAL=OUT/"V1_2_4_OOS_EVALUATION_V1.json"
V124_EVAL_FREEZE=OUT/"V1_2_4_OOS_EVALUATION_FREEZE_V1.json"
CHAMPION=Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")

EXPECTED={
 PROTOCOL:"fbeeff99e2fb17b6df58907885dc1c3f5265ab9e9b14082e39eaeef49b59fc17",
 FEATURE_FREEZE:"c366abea89c98622f7e923c7206a6a719f2a68972b3a880d425a54d12786521a",
 V124_BINDING:"c2c158520ac38761c1f1d4bf94da9b8bb0a24da8951668f6b8a41eca5c9ffae7",
 V124_PRED:"8c61de90e4de128ee070b9df84525b52016e543cd89c084cfc021534af251d08",
 V124_EVAL:"df9882e64ac9a9c265ae8c74d9ac94e96d0598a72e62dd5c91f188ebffcdda00",
 V124_EVAL_FREEZE:"afd24fe9e0945f571262267dc982f9d27b5136ef5774c5a3f9e2a6bea4a95095",
 CHAMPION:"0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9",
}

def fsha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a:str)->str: return subprocess.run(["git","-C",str(ROOT),*a],check=True,capture_output=True,text=True).stdout.strip()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--authorized-head",required=True); a=ap.parse_args()
    if git("rev-parse","HEAD")!=a.authorized_head: raise SystemExit("HEAD_MISMATCH")
    if git("status","--porcelain"): raise SystemExit("WORKTREE_NOT_CLEAN")
    if BINDING.exists(): raise SystemExit("OUTPUT_ALREADY_EXISTS")
    for p,h in EXPECTED.items():
        if fsha(p)!=h: raise SystemExit(f"HASH_MISMATCH:{p}")
    old=json.loads(V124_BINDING.read_text())
    srcs=[
      ROOT/"src/research/target_aware_market_panel/predictive_v13.py",
      ROOT/"research/target_aware_market_panel/run_exploratory_v1_3.py",
      ROOT/"src/research/target_aware_market_panel/predictive_v123.py",
      ROOT/"src/research/target_aware_market_panel/predictive_eval_v123.py",
      ROOT/"src/research/item6/stage2/executor.py",
      ROOT/"src/research/item6/stage2/model_specs.py",
    ]
    doc={
      "artifact_version":"target_aware_v1_3_exploratory_binding_v1",
      "authorized_binding_head":a.authorized_head,
      "scientific_role":"EXPLORATORY_MODEL_DEVELOPMENT_ONLY",
      "frozen_inputs":{str(p.relative_to(ROOT) if ROOT in p.parents else p):h for p,h in EXPECTED.items()},
      "source_hashes":{str(p.relative_to(ROOT)):fsha(p) for p in srcs},
      "primary_targets":old["primary_targets"],
      "family_order":old["family_order"],
      "scoring_sets":old["scoring_sets"],
      "scoring_set_hashes":old["scoring_set_hashes"],
      "selection_rule":json.loads(PROTOCOL.read_text())["selection_rule"],
      "final_fit_rule":json.loads(PROTOCOL.read_text())["final_fit_rule"],
      "evaluation_rule":json.loads(PROTOCOL.read_text())["scoring"],
      "data_policy":json.loads(PROTOCOL.read_text())["data_policy"],
      "provider_calls":0,"network_calls":0,
      "v1_2_4_oos_results_already_observed":True,
      "independent_confirmation":False,
      "champion_change_authorized":False,
      "v1_3_executed":False,
    }
    BINDING.write_text(json.dumps(doc,indent=1,sort_keys=True)+"\n")
    print(json.dumps({"status":"V1_3_EXPLORATORY_BINDING_FROZEN","sha256":fsha(BINDING),
      "n_targets":len(doc["primary_targets"]),"n_primary":len(doc["scoring_sets"]["primary_ids"]),
      "provider_calls":0},indent=2))
if __name__=="__main__": main()
