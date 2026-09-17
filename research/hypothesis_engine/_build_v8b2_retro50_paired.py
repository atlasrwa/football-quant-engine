"""Stage 2: fixture-level aggregation + honest paired differences for the V8B.2 retrospective
rescore, using the FROZEN V8B.1/V8B.2 aggregation rule. Then freeze the primary numeric result.

Frozen aggregation rule (V8B1_AGGREGATION_INFERENCE_SPEC.md, unchanged):
  ARM_SCORE(T) = mean of SCORE_OK fixture scores only; None if the arm has 0 SCORE_OK at T.
  D_SR(T) = ARM_SCORE_S(T) - ARM_SCORE_R(T), only where BOTH are not None (listwise).
  D_SH(T) = ARM_SCORE_S(T) - ARM_SCORE_H(T), only where BOTH are not None (listwise).
Inference: estimator.small_cluster_inference over the frozen chronological blocks; below
SIGN_FLIP_MIN_CLUSTERS=3 it returns INSUFFICIENT_CLUSTERS_FOR_INFERENCE by design (no invented p).

Writes V8B2_RETRO50_PAIRED_SR.json, V8B2_RETRO50_PAIRED_SH.json, V8B2_RETRO50_PRIMARY_RESULT.json.
No imputation, no cross-fixture substitution, no new aggregation.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import sys

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
sys.path.insert(0, ROOT)

RESCORE = f"{ENG}/V8B2_RETRO50_RESCORE.json"
BLOCKS = f"{ENG}/V8B1_CHRONOLOGICAL_BLOCKS.json"
OUT_SR = f"{ENG}/V8B2_RETRO50_PAIRED_SR.json"
OUT_SH = f"{ENG}/V8B2_RETRO50_PAIRED_SH.json"
OUT_PRIMARY = f"{ENG}/V8B2_RETRO50_PRIMARY_RESULT.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def _sha_file(p):
    with open(f"{ROOT}/{p}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _sha_obj(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def _arm_score(records, fid, arm):
    """Frozen ARM_SCORE(T): mean of SCORE_OK scores only; None if zero OK. Returns
    (score_or_None, contributing_hypothesis_ids)."""
    oks = [r for r in records if r["fixture_id"] == fid and r["arm"] == arm
           and r["status"] == "SCORE_OK" and r["score"] is not None]
    if not oks:
        return None, []
    return sum(r["score"] for r in oks) / len(oks), [r["hypothesis_id"] for r in oks]


def _pos_zero_neg(diffs, eps=1e-12):
    pos = sum(1 for d in diffs if d > eps)
    neg = sum(1 for d in diffs if d < -eps)
    zero = len(diffs) - pos - neg
    return {"positive": pos, "zero": zero, "negative": neg}


def main():
    d = json.load(open(RESCORE))
    records = d["records"]
    fixtures = d and json.load(open(f"{ENG}/V8B1_PILOT50_SELECTION_FREEZE.json"))["pilot_fixture_ids_ordered"]
    blocks = json.load(open(BLOCKS))["fixture_to_block"]

    from src.research.hypothesis_v71 import estimator as EST

    # fixture-level arm scores
    per_fixture = []
    for fid in fixtures:
        s, s_ids = _arm_score(records, fid, "S")
        r, r_ids = _arm_score(records, fid, "R")
        h, h_ids = _arm_score(records, fid, "H")
        per_fixture.append({"fixture_id": fid, "S": s, "R": r, "H": h,
                            "S_ids": s_ids, "R_ids": r_ids, "H_ids": h_ids})

    def paired(arm):
        rows = []
        for pf in per_fixture:
            other = pf[arm]
            if pf["S"] is not None and other is not None:
                rows.append({"fixture_id": pf["fixture_id"], "S": pf["S"], arm: other,
                             "diff": pf["S"] - other,
                             "S_ids": pf["S_ids"], f"{arm}_ids": pf[f"{arm}_ids"]})
        diffs = [x["diff"] for x in rows]
        cls = [blocks[x["fixture_id"]] for x in rows]
        n_blocks = len(set(cls))
        if diffs:
            inf = EST.small_cluster_inference(diffs, cls)
        else:
            inf = {"primary_p_value": None, "point_estimate": None, "n_clusters": 0,
                   "inference_status": "NO_PAIRED_EVALUABLE_FIXTURES"}
        summary = {
            "paired_n": len(diffs),
            "n_blocks_spanned": n_blocks,
            "mean_diff": (sum(diffs) / len(diffs)) if diffs else None,
            "median_diff": statistics.median(diffs) if diffs else None,
            "stdev_diff": (statistics.pstdev(diffs) if len(diffs) >= 2 else None),
            "pos_zero_neg": _pos_zero_neg(diffs) if diffs else {"positive": 0, "zero": 0, "negative": 0},
            "inference": inf,
            "rows": rows,
        }
        return summary

    sr = paired("R")
    sh = paired("H")

    n_s_fix = sum(1 for pf in per_fixture if pf["S"] is not None)
    n_r_fix = sum(1 for pf in per_fixture if pf["R"] is not None)
    n_h_fix = sum(1 for pf in per_fixture if pf["H"] is not None)

    for path, obj, label in ((OUT_SR, sr, "S_vs_R"), (OUT_SH, sh, "S_vs_H")):
        payload = {"label": f"V8B2_RETRO50_PAIRED_{label}",
                   "evidence_class": "POST_OUTCOME_SCORER_REPAIR_DIAGNOSTIC", **obj}
        with open(path, "w") as f:
            json.dump(payload, f, indent=1, default=str)

    # research yield + support-failure counts (evaluability, NOT wins)
    from collections import Counter
    def arm_status_counts(arm):
        rs = [r for r in records if r["arm"] == arm]
        return {"total": len(rs), **dict(Counter(r["status"] for r in rs))}
    s_fail = Counter()
    for r in records:
        if r["arm"] == "S":
            for fld in r.get("support_failures", []):
                s_fail[fld] += 1

    champ_ok = _sha_file("data/discovery/pilotC_stat_mixer.json") == CHAMPION_EXPECTED

    primary = {
        "result_version": "v8b2_retro50_primary_result_v1",
        "label": "V8B2_RETROSPECTIVE_CORRECTED_PILOT50",
        "evidence_class": "POST_OUTCOME_SCORER_REPAIR_DIAGNOSTIC",
        "frozen_before_trace_review": True,
        "n_target_fixtures": 50,
        "rescore_sha256": _sha_file("research/hypothesis_engine/V8B2_RETRO50_RESCORE.json"),
        "scorer_version": d["scorer_version"],

        "evaluability_note": "SCORE_OK COUNTS ARE EVALUABILITY, NOT WINS. Arm quality is judged "
                             "only by the frozen scores among paired evaluable fixtures.",
        "arm_status_counts": {"S": arm_status_counts("S"), "R": arm_status_counts("R"),
                              "H": arm_status_counts("H")},
        "fixtures_with_score": {"S": n_s_fix, "R": n_r_fix, "H": n_h_fix},

        "endpoint_S_vs_R": {
            "paired_n": sr["paired_n"], "mean_diff": sr["mean_diff"],
            "median_diff": sr["median_diff"], "stdev_diff": sr["stdev_diff"],
            "pos_zero_neg": sr["pos_zero_neg"],
            "inference_status": sr["inference"].get("inference_status"),
            "point_estimate": sr["inference"].get("point_estimate"),
            "primary_p_value": sr["inference"].get("primary_p_value"),
            "n_blocks_spanned": sr["n_blocks_spanned"],
        },
        "endpoint_S_vs_H": {
            "paired_n": sh["paired_n"], "mean_diff": sh["mean_diff"],
            "median_diff": sh["median_diff"], "stdev_diff": sh["stdev_diff"],
            "pos_zero_neg": sh["pos_zero_neg"],
            "inference_status": sh["inference"].get("inference_status"),
            "point_estimate": sh["inference"].get("point_estimate"),
            "primary_p_value": sh["inference"].get("primary_p_value"),
            "n_blocks_spanned": sh["n_blocks_spanned"],
        },
        "sonnet_vs_blind": ("UNDEFINED_NO_PAIRED_EVALUABLE_FIXTURES" if sr["paired_n"] == 0
                            else "SEE_ENDPOINT_S_VS_R"),
        "sonnet_vs_heuristic": ("UNDEFINED_NO_PAIRED_EVALUABLE_FIXTURES" if sh["paired_n"] == 0
                                else "SEE_ENDPOINT_S_VS_H"),

        "research_yield_sonnet": {
            "fixtures": 50, "ok": 47, "abstain": 2, "invalid": 1,
            "valid_selections": arm_status_counts("S")["total"],
            "score_ok": arm_status_counts("S").get("SCORE_OK", 0),
            "score_ok_rate": round(arm_status_counts("S").get("SCORE_OK", 0)
                                   / max(1, arm_status_counts("S")["total"]), 4),
            "support_failure_counts": dict(s_fail),
        },
        "champion_unchanged": champ_ok,
        "champion_sha256": CHAMPION_EXPECTED,
        "new_sonnet_calls": 0,
        "sealed_947_outcomes_viewed": False,
        "per_fixture_arm_scores": per_fixture,
    }
    primary["primary_result_self_hash"] = _sha_obj({k: v for k, v in primary.items()})
    with open(OUT_PRIMARY, "w") as f:
        json.dump(primary, f, indent=1, default=str)

    print(f"[paired] S-v-R: paired_n={sr['paired_n']} mean={sr['mean_diff']} "
          f"median={sr['median_diff']} pzn={sr['pos_zero_neg']} "
          f"inf={sr['inference'].get('inference_status')}")
    print(f"[paired] S-v-H: paired_n={sh['paired_n']} mean={sh['mean_diff']} "
          f"inf={sh['inference'].get('inference_status')}")
    print(f"[paired] fixtures_with_score S={n_s_fix} R={n_r_fix} H={n_h_fix}")
    print(f"[paired] primary self_hash={primary['primary_result_self_hash']}")
    print(f"[paired] champion_unchanged={champ_ok}")


if __name__ == "__main__":
    main()
