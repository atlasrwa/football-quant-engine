"""Build the IMMUTABLE all-arm V8B.1 PILOT-50 selection freeze.

This is the seal that must exist and pass BEFORE any target outcome is opened. It binds, for
exactly the 50 pilot fixtures: fixture IDs, packet hashes, Sonnet statuses + selection id lists
+ per-fixture selection hashes, R selections + matching metadata + per-fixture hashes, H
selections + per-fixture hashes, and every load-bearing version/spec hash (scorer, aggregation,
inference/estimator, prompt, model, config, search universe, controls, chronological blocks).

It re-verifies the 22 frozen scientific artifacts + CHAMPION are byte-unchanged. It reads NO
target outcome. It fails closed (raises) if any load-bearing rule/artifact is missing or drifted.
"""
from __future__ import annotations

import hashlib
import json

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
OUT = f"{ENG}/V8B1_PILOT50_SELECTION_FREEZE.json"

CHAMPION_ARTIFACT = "data/discovery/pilotC_stat_mixer.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

MODEL_ID = "us.anthropic.claude-sonnet-4-6"


def _sha_file(path_from_root):
    with open(f"{ROOT}/{path_from_root}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _sha_obj(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def main():
    import sys
    sys.path.insert(0, ROOT)
    from src.research.hypothesis_v8b1 import controls as CT
    from src.research.hypothesis_v8b1 import scorer as SC
    from src.research.hypothesis_v8b1 import search as SE
    from src.research.hypothesis_v8b1 import prompt as PR

    # ---- 1. re-verify frozen scientific artifacts + CHAMPION (fail closed) ----
    fm = json.load(open(f"{ENG}/V8B1_FREEZE_MANIFEST.json"))
    drift = [p for p, h in fm["artifact_hashes"].items() if _sha_file(p) != h]
    if drift:
        raise SystemExit(f"FROZEN SCIENTIFIC ARTIFACT DRIFT -- refusing to freeze: {drift}")
    champ = _sha_file(CHAMPION_ARTIFACT)
    if champ != CHAMPION_EXPECTED:
        raise SystemExit("CHAMPION changed -- refusing to freeze")

    # ---- 2. load the three arms ----
    tm = json.load(open(f"{ENG}/V8B1_TRANCHE_50_MANIFEST.json"))
    pilot_ids = tm["fixture_ids_ordered"]
    assert len(pilot_ids) == 50 and len(set(pilot_ids)) == 50

    son = json.load(open(f"{ENG}/V8B1_TRANCHE_50_SELECTIONS.json"))
    son_by = {s["fixture_id"]: s for s in son["selections"]}

    tele = json.load(open(f"{ENG}/V8B1_TRANCHE_50_TELEMETRY.json"))
    packet_hash_by = {r["fixture_id"]: r["packet_hash"] for r in tele["results"]}

    R = {json.loads(l)["fixture_id"]: json.loads(l)
         for l in open(f"{ENG}/V8B1_PILOT50_CONTROL_R.jsonl")}
    H = {json.loads(l)["fixture_id"]: json.loads(l)
         for l in open(f"{ENG}/V8B1_PILOT50_CONTROL_H.jsonl")}

    assert set(son_by) == set(pilot_ids) == set(R) == set(H) == set(packet_hash_by), \
        "arm/fixture id set mismatch"

    # ---- 3. per-fixture all-arm binding ----
    fixtures = []
    status_counts = {}
    for fid in pilot_ids:
        s = son_by[fid]
        status_counts[s["status"]] = status_counts.get(s["status"], 0) + 1
        sonnet_ids = [x["hypothesis_id"] for x in s["final_selections"]]
        r = R[fid]
        h = H[fid]
        # per-arm, per-fixture selection hashes (over the id lists + structural metadata)
        sonnet_sel_hash = _sha_obj(s["final_selections"])
        r_sel_hash = _sha_obj(r["selections"])
        h_sel_hash = _sha_obj(h["selections"])
        fixtures.append({
            "fixture_id": fid,
            "packet_hash": packet_hash_by[fid],
            "sonnet_status": s["status"],
            "sonnet_k_valid": len(sonnet_ids),
            "sonnet_selection_ids": sonnet_ids,
            "sonnet_selection_hash": sonnet_sel_hash,
            "r_k_valid": r["k_valid"],
            "r_n_matched": r["n_matched"],
            "r_selection_ids": [x.get("hypothesis_id") for x in r["selections"]
                                if x["status"] == "MATCHED"],
            "r_matched_tiers": [x.get("matched_tier") for x in r["selections"]
                                if x["status"] == "MATCHED"],
            "r_n_unmatched": sum(1 for x in r["selections"] if x["status"] == "UNMATCHED"),
            "r_selection_hash": r_sel_hash,
            "h_k_valid": h["k_valid"],
            "h_selection_ids": h["heuristic_selection_ids"],
            "h_selection_hash": h_sel_hash,
        })

    total_k = sum(f["sonnet_k_valid"] for f in fixtures)

    freeze = {
        "freeze_version": "v8b1_pilot50_selection_freeze_v1",
        "immutable": True,
        "cohort": "V8B1_PILOT_50",
        "cohort_note": "exactly the 50 fixtures of the unauthorized-but-outcome-blind "
                       "operational tranche (commit c4b70eb30); see "
                       "V8B1_TRANCHE50_PROTOCOL_DEVIATION.json.",
        "n_target_fixtures": 50,
        "pilot_fixture_ids_ordered": pilot_ids,

        "model": {
            "model_id": MODEL_ID,
            "prompt_content_hash": PR.prompt_content_hash(),
            "config_stamp": tm["config_stamp"],
        },
        "search_universe": SE.version_stamp(),
        "controls": CT.version_stamp(),
        "scorer": SC.version_stamp(),

        "arm_source_files": {
            "sonnet_selections": "research/hypothesis_engine/V8B1_TRANCHE_50_SELECTIONS.json",
            "sonnet_selections_sha256": _sha_file("research/hypothesis_engine/V8B1_TRANCHE_50_SELECTIONS.json"),
            "control_R": "research/hypothesis_engine/V8B1_PILOT50_CONTROL_R.jsonl",
            "control_R_sha256": _sha_file("research/hypothesis_engine/V8B1_PILOT50_CONTROL_R.jsonl"),
            "control_H": "research/hypothesis_engine/V8B1_PILOT50_CONTROL_H.jsonl",
            "control_H_sha256": _sha_file("research/hypothesis_engine/V8B1_PILOT50_CONTROL_H.jsonl"),
            "controls_builder": "research/hypothesis_engine/_build_v8b1_pilot50_controls.py",
        },

        "spec_hashes": {
            "scorer_spec": _sha_file("research/hypothesis_engine/V8B1_SCORER_SPEC.md"),
            "aggregation_inference_spec": _sha_file("research/hypothesis_engine/V8B1_AGGREGATION_INFERENCE_SPEC.md"),
            "blind_control_spec": _sha_file("research/hypothesis_engine/V8B1_BLIND_CONTROL_SPEC.md"),
            "heuristic_spec": _sha_file("research/hypothesis_engine/V8B1_HEURISTIC_SPEC.md"),
            "chronological_blocks": _sha_file("research/hypothesis_engine/V8B1_CHRONOLOGICAL_BLOCKS.json"),
            "fixture_manifest": _sha_file("research/hypothesis_engine/V8B1_FIXTURE_MANIFEST.json"),
            "tranche_manifest": _sha_file("research/hypothesis_engine/V8B1_TRANCHE_50_MANIFEST.json"),
            "search_cap_amendment": _sha_file("research/hypothesis_engine/V8B1_SEARCH_CAP_AMENDMENT.json"),
        },
        "code_hashes": {
            "scorer_py": _sha_file("src/research/hypothesis_v8b1/scorer.py"),
            "controls_py": _sha_file("src/research/hypothesis_v8b1/controls.py"),
            "search_py": _sha_file("src/research/hypothesis_v8b1/search.py"),
            "estimator_py": _sha_file("src/research/hypothesis_v71/estimator.py"),
        },

        "aggregation_inference_binding": {
            "arm_score_rule": "mean of SCORE_OK fixture scores only; None if zero OK (NULL-is-not-ZERO)",
            "paired_difference_rule": "D_BLIND(T)=SONNET-BLIND, D_HEUR(T)=SONNET-HEUR; listwise (both sides non-None)",
            "inference_primitive": "src/research/hypothesis_v71/estimator.py::small_cluster_inference (UNCHANGED)",
            "clustering": "chronological blocks from V8B1_CHRONOLOGICAL_BLOCKS.json (frozen over the full 1000 manifest)",
            "pilot_scale_note": "the 50 pilot fixtures fall in only 2 of the 20 frozen chronological blocks "
                                "(block_000: 47, block_001: 3). g=2 < SIGN_FLIP_MIN_CLUSTERS=3, so the frozen "
                                "estimator returns inference_status=INSUFFICIENT_CLUSTERS_FOR_INFERENCE with a "
                                "point_estimate and p_value=None BY DESIGN. The pilot therefore reports DIRECTION "
                                "and MAGNITUDE (point estimates), and the frozen inference legitimately declines a "
                                "significance claim at n=50. No new clustering rule is invented.",
        },

        "frozen_scientific_artifacts_reverified": {
            "freeze_manifest": "research/hypothesis_engine/V8B1_FREEZE_MANIFEST.json",
            "n_artifacts": len(fm["artifact_hashes"]),
            "drift": drift,
            "all_byte_identical": drift == [],
        },
        "champion_unchanged": champ == CHAMPION_EXPECTED,
        "champion_sha256": champ,

        "status_counts": status_counts,
        "total_sonnet_k_valid": total_k,
        "total_r_matched": sum(f["r_n_matched"] for f in fixtures),
        "total_r_unmatched": sum(f["r_n_unmatched"] for f in fixtures),
        "total_h_selected": sum(len(f["h_selection_ids"]) for f in fixtures),

        "arms_frozen": {"SONNET": True, "R": True, "H": True},
        "scorer_frozen": True,
        "aggregation_frozen": True,
        "inference_frozen": True,

        "target_outcomes_viewed": False,
        "outcome_seal_declaration": "NO target outcome has been opened as of this freeze. The "
            "outcome seal is crossed only later, inside scorer.score_fixture via "
            "compiler.py::compile_query -> index.team_value(rec_i, ...), and ONLY for these 50 "
            "fixtures, ONLY after this freeze is written and verified.",

        "fixtures": fixtures,
    }

    freeze["freeze_self_hash"] = _sha_obj({k: v for k, v in freeze.items()})
    with open(OUT, "w") as f:
        json.dump(freeze, f, indent=1, default=str)

    print(f"[freeze] wrote {OUT}")
    print(f"[freeze] self_hash={freeze['freeze_self_hash']}")
    print(f"[freeze] status_counts={status_counts} total_k_valid={total_k} "
          f"R_matched={freeze['total_r_matched']} R_unmatched={freeze['total_r_unmatched']} "
          f"H_selected={freeze['total_h_selected']}")
    print(f"[freeze] scientific_drift={drift} champion_unchanged={freeze['champion_unchanged']} "
          f"target_outcomes_viewed={freeze['target_outcomes_viewed']}")


if __name__ == "__main__":
    main()
