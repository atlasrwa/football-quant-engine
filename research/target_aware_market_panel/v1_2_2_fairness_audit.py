"""Outcome-blind fairness audit for Target-Aware Market Panel V1.2.2 predictive stage."""
from __future__ import annotations
import hashlib, json, re, subprocess, sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.research.target_aware_market_panel import cohort_packets as CP
OUT = ROOT / "research/target_aware_market_panel"
REQ_ROOT = OUT / "out/sol_requests"
FOLDS = OUT / "TARGET_AWARE_FOLD_MANIFEST_V1.json"
PROTOCOL = OUT / "TARGET_AWARE_PANEL_PROTOCOL_V1.md"
SUPPORT_FREEZE = OUT / "SOL_PANEL_SUPPORT_FREEZE_MANIFEST_V1_2_1.json"
AUDIT_OUT = OUT / "V1_2_2_PREDICTIVE_FAIRNESS_AUDIT_V1.json"
BASE_CACHE = "/home/ubuntu/data/thestatsapi/championship"

EXPECTED_FOLD_SHA = "f353068ec40864d56ac2c514a22e1199a9e237f58b1399e9739c71ae4488d3a1"
EXPECTED_SUPPORT_FREEZE_SHA = "d21f4ec5226eb56977cef2c733edfcef1287e5d756220e6496797c6816f1b40d"
EXPECTED_CHAMPION_SHA = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"
CHAMPION = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")

def fsha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args: str) -> str:
    return subprocess.run(["git","-C",str(ROOT),*args],check=True,capture_output=True,text=True).stdout.strip()

def walk_match_ids(x: Any, out: set[str]) -> None:
    if isinstance(x, dict):
        for v in x.values(): walk_match_ids(v, out)
    elif isinstance(x, list):
        for v in x: walk_match_ids(v, out)
    elif isinstance(x, str) and re.fullmatch(r"mt_\d+", x):
        out.add(x)
def build(authorized_head: str) -> dict[str, Any]:
    if git("rev-parse","HEAD") != authorized_head:
        raise RuntimeError("HEAD_MISMATCH")
    if git("status","--porcelain"):
        raise RuntimeError("WORKTREE_NOT_CLEAN")
    if fsha(FOLDS) != EXPECTED_FOLD_SHA:
        raise RuntimeError("FOLD_HASH_MISMATCH")
    if fsha(SUPPORT_FREEZE) != EXPECTED_SUPPORT_FREEZE_SHA:
        raise RuntimeError("SUPPORT_FREEZE_HASH_MISMATCH")
    if fsha(CHAMPION) != EXPECTED_CHAMPION_SHA:
        raise RuntimeError("CHAMPION_HASH_MISMATCH")
    reqs = sorted(REQ_ROOT.glob("mt_*/*.json"))
    if len(reqs) != 48:
        raise RuntimeError(f"REQUEST_COUNT_MISMATCH:{len(reqs)}")
    refs: set[str] = set()
    req_hashes = {}
    for p in reqs:
        req_hashes[str(p.relative_to(ROOT))] = fsha(p)
        walk_match_ids(json.loads(p.read_text()), refs)

    history_all, _ = CP.load_history(BASE_CACHE, include_gap_fetches=True)
    exposed_teams: set[str] = set()
    matched_refs = 0
    for mid in sorted(refs):
        hm = history_all.get(mid)
        if hm is None:
            continue
        matched_refs += 1
        for side in ("home_team","away_team"):
            tid = (hm.fixture.get(side) or {}).get("id")
            if tid is not None:
                exposed_teams.add(str(tid))
    folds = json.loads(FOLDS.read_text())
    base, _ = CP.load_history(BASE_CACHE, include_gap_fetches=False)
    per_fold = {str(i): {"all_oos":0,"frozen_primary":0,"strict_unseen":0} for i in range(5)}
    strict_ids = []
    primary_ids = []
    for fr in folds["rows"]:
        if fr["fold"] is None:
            continue
        mid = fr["match_id"]
        hm = base[mid]
        home = str((hm.fixture.get("home_team") or {}).get("id"))
        away = str((hm.fixture.get("away_team") or {}).get("id"))
        fid = str(fr["fold"])
        per_fold[fid]["all_oos"] += 1
        if not fr["involves_cohort_team"]:
            primary_ids.append(mid)
            per_fold[fid]["frozen_primary"] += 1
            if home not in exposed_teams and away not in exposed_teams:
                strict_ids.append(mid)
                per_fold[fid]["strict_unseen"] += 1

    train = [r for r in folds["rows"] if r["fold"] is None]
    oos = [r for r in folds["rows"] if r["fold"] is not None]
    return {
        "artifact_version":"target_aware_v1_2_2_predictive_fairness_audit_v1",
        "authorized_head":authorized_head,
        "source_fold_manifest_sha256":fsha(FOLDS),
        "source_v1_protocol_sha256":fsha(PROTOCOL),
        "source_v1_2_1_support_freeze_sha256":fsha(SUPPORT_FREEZE),
        "champion_sha256":fsha(CHAMPION),
        "n_sol_requests":len(reqs),
        "sol_request_hashes_sha256":hashlib.sha256(
            json.dumps(req_hashes,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "n_match_ids_referenced_in_sol_packets":len(refs),
        "n_referenced_match_ids_resolved":matched_refs,
        "n_team_ids_exposed_anywhere_in_sol_packet_history":len(exposed_teams),
        "panel_boundary_correction":{
            "frozen_protocol_text_claim":"panel rows 2024-08 through 2026-09-14",
            "actual_base_history_start_unix":min(h.kickoff_unix for h in base.values()),
            "actual_base_history_end_unix":max(h.kickoff_unix for h in base.values()),
            "train_only_min_kickoff_unix":min(r["kickoff"] for r in train),
            "train_only_max_kickoff_unix":max(r["kickoff"] for r in train),
            "oos_min_kickoff_unix":min(r["kickoff"] for r in oos),
            "oos_max_kickoff_unix":max(r["kickoff"] for r in oos),
            "interpretation":"2023-08 through 2024-10-22 is burn-in/training history; frozen OOS starts 2024-10-23. Do not rewrite the frozen V1 protocol; record this correction here."
        },
        "scoring_sets":{
            "frozen_primary_non_cohort":{"n":len(primary_ids),"sha256":hashlib.sha256("\n".join(primary_ids).encode()).hexdigest()},
            "strict_unseen_team_robustness":{"n":len(strict_ids),"sha256":hashlib.sha256("\n".join(strict_ids).encode()).hexdigest(),
                "definition":"frozen primary rows where neither team id appears in any historical match id referenced anywhere in the 48 Sol request packets"}
        },
        "per_fold":per_fold,
        "validity_interpretation":{
            "frozen_primary_role":"retrospective transferability screen; valid for testing incremental information of already-frozen templates on non-cohort fixtures, but not a clean feature-discovery holdout",
            "strict_unseen_role":"secondary robustness set; more independent from packet exposure but underpowered for a replacement primary endpoint",
            "prospective_requirement":"mandatory for any claim that the LLM discovery process generalizes or for feature promotion/production use",
            "primary_pass_does_not_equal_prospective_validation":True
        },
        "target_outcomes_read":False,"market_results_read":False,"model_fit":False,"oos_executed":False,"champion_changed":False
    }

def main() -> None:
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument("--authorized-head",required=True); a=ap.parse_args()
    if AUDIT_OUT.exists(): raise SystemExit(f"OUTPUT_ALREADY_EXISTS:{AUDIT_OUT}")
    doc=build(a.authorized_head)
    AUDIT_OUT.write_text(json.dumps(doc,indent=1,sort_keys=True)+"\n")
    print(json.dumps({"status":"V1_2_2_FAIRNESS_AUDIT_FROZEN","audit_sha256":fsha(AUDIT_OUT),
                      "frozen_primary_n":doc["scoring_sets"]["frozen_primary_non_cohort"]["n"],
                      "strict_unseen_n":doc["scoring_sets"]["strict_unseen_team_robustness"]["n"],
                      "target_outcomes_read":False},indent=2,sort_keys=True))
if __name__=="__main__": main()
