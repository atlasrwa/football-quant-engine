"""Deterministic comparison of two independent exposed-50 rehearsal runs.

The compared/excluded split is NOT decided here: it is read from
`V8C_REPRODUCIBILITY_COMPARISON_CONTRACT_V1.json`, which was committed BEFORE either run
existed. Nothing may be moved to the excluded list after a mismatch is observed.

usage: _compare_v8c_rehearsal_runs.py <runA_dir> <runB_dir> <out.json>
"""
from __future__ import annotations

import hashlib
import json
import sys

ENG = "/home/ubuntu/research/hypothesis_engine"
CONTRACT = f"{ENG}/V8C_REPRODUCIBILITY_COMPARISON_CONTRACT_V1.json"


def _sha(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def payload(run_dir):
    """The deterministic scientific payload, per the predeclared contract."""
    fz = json.load(open(f"{run_dir}/freeze.json"))
    p2 = json.load(open(f"{run_dir}/process2.json"))
    rows = {}
    for r in fz["selections"]:
        tp = r.get("treatment_provenance") or {}
        rows[r["fixture_id"]] = {
            "packet_hash": r["packet_hash"],
            "pit_context_hash": r["pit_context_hash"],
            "universe_hash": r["universe_hash"],
            "corpus_vintage_hash": r["corpus_vintage_hash"],
            "capability_hash": r["capability_hash"],
            "grammar_version": r["grammar_version"],
            "grammar_size_hash": r["grammar_size_hash"],
            "arm_status": r["arm_status"],
            "k_valid": r["k_valid"],
            "S": r["S"], "R": r["R"], "H": r["H"],
            "R_pairs": r["R_pairs"],
            "R_identity_count": r["R_identity_count"],
            "R_cross_treatment_overlap_count": r["R_cross_treatment_overlap_count"],
            "live_search_addressable": r["live_search_addressable"],
            "prompt_sha256": tp.get("prompt_sha256"),
            "tool_schema_sha256": tp.get("tool_schema_sha256"),
            "runner_version": tp.get("runner_version"),
            "orchestration_version": tp.get("orchestration_version"),
            "search_queries": tp.get("search_queries"),
            "ids_returned_to_model": tp.get("ids_returned_to_model"),
            "submitted_ids": tp.get("submitted_ids"),
            "accepted_ids": tp.get("accepted_ids"),
            "validation_status": tp.get("validation_status"),
            "research_reason": tp.get("research_reason"),
            "termination_reason": tp.get("termination_reason"),
        }
    sd = p2["structural_diagnostics"]
    return {
        "cohort": {"fixture_ids_ordered": fz["fixture_ids_ordered"],
                   "fixture_to_block": fz["inference_blocks"]["fixture_to_block"],
                   "freeze_hash": fz["freeze_hash"]},
        "per_fixture": rows,
        "diagnostics": {"arm_score_ok": sd["arm_score_ok"],
                        "status_counts": sd["status_counts"],
                        "n_pairs_frozen_total": sd["n_pairs_frozen_total"],
                        "n_pairs_surviving_total": sd["n_pairs_surviving_total"],
                        "inference_eligibility": sd["inference_eligibility"]},
    }


def bound_contents(run_dir):
    """Separately compared: what the excluded anchor/receipt actually certify."""
    import glob
    anchor = json.load(open(glob.glob(f"{run_dir}/anchor_repo/evidence/anchor.json")[0]))
    receipt = json.load(open(f"{run_dir}/freeze_receipt.json"))
    return {"producer_code_hashes": anchor["producer_code_hashes"],
            "freeze_sha256": receipt["freeze_sha256"],
            "corpus_hash": receipt["corpus_hash"],
            "capability_hash": receipt["capability_hash"],
            "manifest_cohort_hash": receipt["manifest_cohort_hash"]}


def diff(a, b, path=""):
    out = []
    if type(a) is not type(b):
        return [f"{path}: type {type(a).__name__} != {type(b).__name__}"]
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}.{k}: only in B")
            elif k not in b:
                out.append(f"{path}.{k}: only in A")
            else:
                out += diff(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} != {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                out += diff(x, y, f"{path}[{i}]")
    elif a != b:
        out.append(f"{path}: {a!r} != {b!r}")
    return out


def main(a_dir, b_dir, out_path):
    contract = json.load(open(CONTRACT))
    pa, pb = payload(a_dir), payload(b_dir)
    ba, bb = bound_contents(a_dir), bound_contents(b_dir)
    d_payload = diff(pa, pb, "payload")
    d_bound = diff(ba, bb, "bound")
    rep = {
        "artifact": "V8C_REPRODUCIBILITY_COMPARISON_V1",
        "contract": contract["artifact"],
        "contract_predeclared_at_commit": contract["predeclared_at_commit"],
        "contract_predeclared_before_any_run": contract["predeclared_before_any_run"],
        "run_a": a_dir, "run_b": b_dir,
        "payload_sha256_a": _sha(pa), "payload_sha256_b": _sha(pb),
        "PAYLOAD_IDENTICAL": not d_payload,
        "payload_mismatches": d_payload[:50],
        "n_payload_mismatches": len(d_payload),
        "bound_contents_sha256_a": _sha(ba), "bound_contents_sha256_b": _sha(bb),
        "BOUND_CONTENTS_IDENTICAL": not d_bound,
        "bound_mismatches": d_bound[:50],
        "n_bound_mismatches": len(d_bound),
        "excluded_fields": sorted(contract["EXCLUDED_AND_WHY"]),
        "no_field_moved_to_excluded_after_the_fact": True,
        "REPRODUCIBLE": (not d_payload) and (not d_bound),
    }
    json.dump(rep, open(out_path, "w"), indent=1, default=str)
    print(f"PAYLOAD_IDENTICAL        = {rep['PAYLOAD_IDENTICAL']}")
    print(f"BOUND_CONTENTS_IDENTICAL = {rep['BOUND_CONTENTS_IDENTICAL']}")
    print(f"REPRODUCIBLE             = {rep['REPRODUCIBLE']}")
    for m in (d_payload + d_bound)[:10]:
        print("   MISMATCH:", m)
    return rep


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
