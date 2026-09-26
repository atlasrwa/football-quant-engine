"""Freeze the V1.2.4 predictive OOS execution binding before label access."""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, sys
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from src.research.target_aware_market_panel import cohort_packets as CP
from src.research.target_aware_market_panel import predictive_eval_v123 as EV

OUT=ROOT/"research/target_aware_market_panel"
BINDING=OUT/"V1_2_4_PREDICTIVE_OOS_BINDING_V1.json"
FEATURE_FREEZE=OUT/"V1_2_3_FEATURE_FREEZE_MANIFEST_V1.json"
FAIRNESS=OUT/"V1_2_2_PREDICTIVE_FAIRNESS_AUDIT_V1.json"
FOLDS=OUT/"TARGET_AWARE_FOLD_MANIFEST_V1.json"
TARGETS=OUT/"TARGET_UNIVERSE_V1.json"
REGISTRY=OUT/"SOL_CLASS_C_TEMPLATE_REGISTRY_V1.json"
PROTOCOL=OUT/"TARGET_AWARE_PANEL_PROTOCOL_V1.md"
SUPPORT_GATE=OUT/"V1_2_1_EVALUABILITY_GATE_DECISION_V1.json"
ABORT_V122=OUT/"V1_2_2_PREOUTCOME_ABORT_V1.json"
ABORT_V123=OUT/"V1_2_3_EXECUTION_ABORT_V1.json"
PREV_BINDING=OUT/"V1_2_3_PREDICTIVE_OOS_BINDING_V1.json"
REQ_ROOT=OUT/"out/sol_requests"
CHAMPION=Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")

EXPECTED={
 FEATURE_FREEZE:"c366abea89c98622f7e923c7206a6a719f2a68972b3a880d425a54d12786521a",
 FAIRNESS:"4f6395f1de25b28310849bdd43e72c1b1e8f27b28b68a6915b70b35cd04a0014",
 FOLDS:"f353068ec40864d56ac2c514a22e1199a9e237f58b1399e9739c71ae4488d3a1",
 TARGETS:"6b9cd9a8eef0e53153717cb5215c76a1ba23f01aeb3f3d0d46c133840d63cb79",
 REGISTRY:"2367b9ea5b3bad10b66c2958599069d574d5bc8c829d6066dc04b75aa069bf1b",
 PROTOCOL:"0ea8328ef94fc3256b144c5d83b879481b9cfba4e006d0f3dada020f65cf2eac",
 SUPPORT_GATE:"509cadfaefc095470783cf2250f20d0f18fa0b5407a64c3d700623ef8cda9273",
 ABORT_V122:"1c0183478076babe5edb96ace29330a57d82de980bbf3810aa23876b033a3396",
 ABORT_V123:"80ae6bb9be52dc0035253a432c77dcec63419b5525d30f9b10cf326b47536970",
 PREV_BINDING:"2741f677a8c0bd7b85e6281544d98542977d69f01146a79e2d3a510a79b7b20b",
 CHAMPION:"0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9",
}
CACHE="/home/ubuntu/data/thestatsapi/championship"

def fsha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a:str)->str: return subprocess.run(["git","-C",str(ROOT),*a],check=True,capture_output=True,text=True).stdout.strip()
def walk(x:Any,out:set[str])->None:
    if isinstance(x,dict):
        for v in x.values(): walk(v,out)
    elif isinstance(x,list):
        for v in x: walk(v,out)
    elif isinstance(x,str) and re.fullmatch(r"mt_\d+",x): out.add(x)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--authorized-head",required=True); a=ap.parse_args()
    if git("rev-parse","HEAD")!=a.authorized_head: raise SystemExit("HEAD_MISMATCH")
    if git("status","--porcelain"): raise SystemExit("WORKTREE_NOT_CLEAN")
    for p,h in EXPECTED.items():
        if fsha(p)!=h: raise SystemExit(f"HASH_MISMATCH:{p}")
    if BINDING.exists(): raise SystemExit("OUTPUT_ALREADY_EXISTS")
    reqs=sorted(REQ_ROOT.glob("mt_*/*.json"))
    if len(reqs)!=48: raise SystemExit("REQUEST_COUNT_MISMATCH")
    refs=set()
    for p in reqs: walk(json.loads(p.read_text()),refs)
    hall,_=CP.load_history(CACHE,include_gap_fetches=True)
    exposed=set()
    for mid in refs:
        hm=hall.get(mid)
        if hm:
            for side in ("home_team","away_team"):
                tid=(hm.fixture.get(side) or {}).get("id")
                if tid is not None: exposed.add(str(tid))
    base,_=CP.load_history(CACHE,include_gap_fetches=False)
    folds=json.loads(FOLDS.read_text())
    primary=[]; strict=[]; all_oos=[]
    for r in folds["rows"]:
        if r["fold"] is None: continue
        mid=r["match_id"]; all_oos.append(mid)
        if not r["involves_cohort_team"]:
            primary.append(mid)
            hm=base[mid]
            h=str((hm.fixture.get("home_team") or {}).get("id"))
            aw=str((hm.fixture.get("away_team") or {}).get("id"))
            if h not in exposed and aw not in exposed: strict.append(mid)
    fair=json.loads(FAIRNESS.read_text())
    if len(primary)!=3057 or len(strict)!=396: raise SystemExit("SCORING_SET_COUNT_MISMATCH")
    if hashlib.sha256("\n".join(primary).encode()).hexdigest()!=fair["scoring_sets"]["frozen_primary_non_cohort"]["sha256"]:
        raise SystemExit("PRIMARY_SET_HASH_MISMATCH")
    if hashlib.sha256("\n".join(strict).encode()).hexdigest()!=fair["scoring_sets"]["strict_unseen_team_robustness"]["sha256"]:
        raise SystemExit("STRICT_SET_HASH_MISMATCH")
    targets=[t for t in json.loads(TARGETS.read_text())["targets"] if t["line_role"]=="PRIMARY"]
    if len(targets)!=8: raise SystemExit("PRIMARY_TARGET_COUNT_MISMATCH")
    srcs=[
      ROOT/"src/research/target_aware_market_panel/predictive_v123.py",
      ROOT/"src/research/target_aware_market_panel/predictive_eval_v123.py",
      ROOT/"src/research/item6/stage2/executor.py",
      ROOT/"src/research/item6/stage2/model_specs.py",
      ROOT/"research/target_aware_market_panel/run_predictive_oos_v1_2_4.py",
    ]
    doc={
      "artifact_version":"target_aware_v1_2_4_predictive_oos_binding_v1",
      "authorized_binding_head":a.authorized_head,
      "frozen_inputs":{str(p.relative_to(ROOT) if ROOT in p.parents else p):h for p,h in EXPECTED.items()},
      "source_hashes":{str(p.relative_to(ROOT)):fsha(p) for p in srcs},
      "primary_targets":targets,
      "family_order":list(EV.FAMILY_ORDER),
      "scoring_sets":{"all_oos_ids":all_oos,"primary_ids":primary,"strict_unseen_ids":strict},
      "scoring_set_hashes":{
        "all_oos":hashlib.sha256("\n".join(all_oos).encode()).hexdigest(),
        "primary":hashlib.sha256("\n".join(primary).encode()).hexdigest(),
        "strict_unseen":hashlib.sha256("\n".join(strict).encode()).hexdigest()},
      "model_rule":{
        "m0":"strong deterministic baseline only",
        "m1":"identical strong baseline plus frozen class-C Sol features",
        "coverage_threshold":0.60,
        "fit_routine":"src.research.item6.stage2.executor.fit_arm",
        "both_arms_tuned_independently_under_identical_grid":True,
        "fold_failure_rule":"if either arm fails a fold/target, score neither arm for that fold/target"},
      "evaluation_rule":{
        "family_target_weighting":"equal weight across primary targets within family",
        "bootstrap":"paired ISO-week block bootstrap, 10000 resamples, seed 0",
        "family_multiplicity":"Holm-Bonferroni across four fixed families at alpha 0.05",
        "pass_requires":["delta>0","95% CI lower>0","delta>=0.001 nats",
                         "ECE_M1<=ECE_M0+0.005","Holm-adjusted p<=0.05"],
        "strict_unseen_role":"secondary robustness only; never substitutes for frozen primary"},
      "execution_safety":{
        "repair_scope":"execution-only; scientific design inherited unchanged from V1.2.3",
        "parent_v1_2_3_target_outcomes_read":True,
        "scientific_result_observed_before_v1_2_4_binding":False,
        "v1_2_3_binding_sha256":"2741f677a8c0bd7b85e6281544d98542977d69f01146a79e2d3a510a79b7b20b",
        "v1_2_3_abort_sha256":"80ae6bb9be52dc0035253a432c77dcec63419b5525d30f9b10cf326b47536970",
        "exclusive_single_run_lock":True,
        "lock_path":"/home/ubuntu/data/thestatsapi/v1_2_4_predictive_oos.lock",
        "atomic_final_artifact_publication":True,
        "prediction_freeze_is_completion_marker":True,
        "evaluation_freeze_is_completion_marker":True},
      "interpretation_rule":{
        "historical_primary":"retrospective transferability screen, not pristine feature-discovery holdout",
        "prospective_validation_required_for_promotion":True,
        "a_historical_pass_does_not_authorize_champion_change":True},
      "target_outcomes_read":False,"market_results_read":False,"model_fit":False,"oos_executed":False,
      "champion_changed":False,
    }
    BINDING.write_text(json.dumps(doc,indent=1,sort_keys=True)+"\n")
    print(json.dumps({"status":"V1_2_4_PREDICTIVE_BINDING_FROZEN","sha256":fsha(BINDING),
      "n_primary":len(primary),"n_strict":len(strict),"n_targets":len(targets),"target_outcomes_read":False},indent=2))
if __name__=="__main__": main()
