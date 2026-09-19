"""V8C exposed-50 COMPOSED rehearsal (`v8c_exposed50_rehearsal_v2`) -- audit finding 5.

EVIDENCE_CLASS = DEVELOPMENT_REAL_CORPUS_COMPOSED_REHEARSAL

SUPERSEDES `_run_v8c_exposed50_rehearsal.py`, which bypassed the experiment it claimed to
rehearse. That script ran ONE process, kept its selection hash in memory, called
`scorer.score_fixture` directly, passed the literal string "REHEARSAL_PACKET" instead of a
real evidence packet, and wrote `DATA_BINDING_PASS=True` as a hardcoded boolean without
verifying any freeze path. The prior artifact is PRESERVED, not overwritten.

WHAT THIS ONE DOES INSTEAD -- the actual entry points, in the actual order:

    prevalidate   the bundle is proven exposed-only from CACHE FILENAMES, before `load_records`
    PROCESS 1     `select_freeze.select_cohort` -- real PIT-safe packets, mocked Converse
                  through `runner.run_fixture_converse`, the authoritative submission
                  contract, R/H selection, full treatment provenance, predeclared inference
                  blocks. Writes freeze + receipt, and EXITS.
    ANCHOR        freeze and receipt are hashed into an anchor artifact, committed to git.
    PROCESS 2     `score_frozen.score_frozen` with the anchor PINNED -- verifies the anchor,
                  the receipt, the complete freeze schema and every per-fixture binding, and
                  validates the inference blocks, all before the first target read.

The two processes are separate OS processes. The seal is an operating-system fact.

OUTCOME DISCIPLINE. The exposed-50 outcomes are DEVELOPMENT data. This script reports endpoint
ASSEMBLY and matched-pair RETENTION via `aggregate.structural_only`, and never computes, reads
or emits an arm mean, a paired difference, an effect direction, a p-value or a winner.
`FORBIDDEN_OUTPUT_KEYS` is asserted against the finished artifact.

ZERO Sonnet calls. ZERO spend. The reserve is never loaded.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
sys.path.insert(0, ROOT)
sys.path.insert(0, f"{ROOT}/scripts")

OUT = f"{ENG}/V8C_EXPOSED50_REHEARSAL_V2.json"
CLASSIFICATION = "DEVELOPMENT_REAL_CORPUS_COMPOSED_REHEARSAL"

FORBIDDEN_OUTPUT_KEYS = (
    "mean_s_score", "mean_r_score", "mean_h_score", "s_minus_r", "effect", "effect_size",
    "p_value", "winner", "direction", "sonnet_better", "sonnet_worse", "advantage",
    "mean_diff", "median_diff", "descriptive_all_fixtures", "inference", "diff",
)

STANDIN_VERSION = "v8c_deterministic_s_standin_v2"


def _sha(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


# ============================================================== PREVALIDATION
def prevalidate_bundle(bundle_root: str) -> dict:
    """Prove the cache is exposed-only from FILENAMES, before any record is loaded.

    Checking for sealed ids AFTER `load_records` is too late: by then their statistics have
    been parsed into memory. Cache filenames encode the fixture id (`stats_<id>.json`,
    `<prefix>_stats_<id>.json`), so the intersection is decidable with zero parsing and zero
    content reads.
    """
    cache = os.path.join(bundle_root, "data", "thestatsapi", "championship")
    sealed_path = os.path.join(bundle_root, "research", "hypothesis_engine",
                               "V8C_SEALED947_EXCLUSION_IDS.json")
    sealed = set(json.load(open(sealed_path))["sealed_fixture_ids"])

    names = os.listdir(cache)
    stats_ids = set()
    for fn in names:
        if "stats_" in fn and fn.endswith(".json"):
            stats_ids.add(fn.rsplit("stats_", 1)[1][:-5])
    leaked = sorted(stats_ids & sealed)
    if leaked:
        raise SystemExit(
            f"PREVALIDATION FAILED: {len(leaked)} sealed reserve fixture(s) have statistics "
            f"in this cache ({leaked[:5]}). Refusing to construct an index.")
    return {"cache_root": cache, "n_cache_files": len(names),
            "n_stats_files": len(stats_ids), "n_sealed_ids_checked": len(sealed),
            "sealed_stats_files_found": 0,
            "method": "filename-only intersection, performed BEFORE load_records",
            "parsed_any_file": False}


def _apparatus(bundle_root):
    sys.path.insert(0, os.path.join(bundle_root, "loader_adapter"))
    import v8c_dev_paths
    v8c_dev_paths.install()
    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    cap = CAP.CapabilityContract(json.load(open(v8c_dev_paths.COVERAGE_MATRIX)))
    recs = CI.load_records(include_fresh=True)
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    index = CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)
    return v8c_dev_paths, cap, index, len(recs)


def make_converse(k):
    """A DETERMINISTIC stand-in driven through the REAL Converse loop. Not a model."""
    state = {"seen": [], "turn": 0}

    def converse(**kw):
        state["turn"] += 1
        if state["turn"] == 1:
            return {"output": {"message": {"role": "assistant", "content": [
                {"toolUse": {"toolUseId": "t1", "name": "search_hypotheses",
                             "input": {"max_results": 50}}}]}}, "stopReason": "tool_use"}
        for blk in kw["messages"][-1]["content"]:
            for c in blk.get("toolResult", {}).get("content", []):
                for r in (c.get("json") or {}).get("results", []):
                    state["seen"].append(r["hypothesis_id"])
        ids = sorted(set(state["seen"]))[:k]
        return {"output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "t2", "name": "submit_selections",
                         "input": {"hypothesis_ids": ids,
                                   "research_reason":
                                       "deterministic stand-in; no football judgement"}}}]}},
            "stopReason": "tool_use"}

    return converse


# ============================================================== PROCESS 1
def process_1(bundle_root, outdir, k=4, n_limit=None):
    """Select, freeze, write, EXIT. Never imports a scorer."""
    from src.research.hypothesis_v8c import runner as RUN
    from src.research.hypothesis_v8c import select_freeze as SF
    from src.research.hypothesis_v8c import receipt as RCPT
    from src.research.hypothesis_v8c import vintage as VIN

    pre = prevalidate_bundle(bundle_root)
    paths, cap, index, n_recs = _apparatus(bundle_root)
    pilot = json.load(open(paths.SELECTION_FREEZE))["pilot_fixture_ids_ordered"]
    if n_limit:
        pilot = pilot[:n_limit]
    positions = [index.pos_of_fixture[f] for f in pilot]

    def s_runner(fu, capability, *, grammar_kwargs=None, packet=None):
        """The REAL Converse loop, handed the REAL packet `select_cohort` just built."""
        return RUN.run_fixture_converse(
            fu, capability, converse=make_converse(k),
            packet=json.dumps(packet, sort_keys=True, default=str),
            model_id="DETERMINISTIC_STANDIN", resolved_model_id=None,
            model_config_stamp={"standin": STANDIN_VERSION},
            grammar_kwargs=grammar_kwargs)

    t0 = time.time()
    payload = SF.select_cohort(
        index, positions, capability=cap, fixture_ids=pilot, k=k,
        classification=CLASSIFICATION, progress=True, s_runner=s_runner,
        model_id="DETERMINISTIC_STANDIN", resolved_model_id=None,
        model_config_stamp={"standin": STANDIN_VERSION})

    os.makedirs(outdir, exist_ok=True)
    fp = os.path.join(outdir, "freeze.json")
    SF.write_freeze(payload, fp)
    rp = os.path.join(outdir, "freeze_receipt.json")
    RCPT.write_receipt(RCPT.build_receipt(
        freeze_path=fp, corpus_hash=VIN.corpus_vintage_full(index),
        capability_hash=VIN.capability_hash(cap),
        fixture_ids_ordered=payload["fixture_ids_ordered"],
        classification=CLASSIFICATION), rp)

    json.dump({"phase": "PROCESS_1_COMPLETE", "prevalidation": pre,
               "n_records": n_recs, "n_fixtures": len(pilot),
               "freeze_path": fp, "receipt_path": rp,
               "freeze_hash": payload["freeze_hash"],
               "scorer_was_loaded": any("scorer" in m for m in sys.modules),
               "elapsed_s": round(time.time() - t0, 1)},
              open(os.path.join(outdir, "process1.json"), "w"), indent=1, default=str)
    print(f"[p1] freeze {payload['freeze_hash'][:16]} -> {fp}", flush=True)


# ============================================================== PROCESS 2
def process_2(bundle_root, outdir, anchor_commit, anchor_rel, repo_root):
    """Verify the pinned anchor and every binding, then score."""
    from src.research.hypothesis_v8c import aggregate as AG
    from src.research.hypothesis_v8c import score_frozen as SFZ

    prevalidate_bundle(bundle_root)
    _paths, cap, index, n_recs = _apparatus(bundle_root)
    fp = os.path.join(outdir, "freeze.json")
    rp = os.path.join(outdir, "freeze_receipt.json")

    t0 = time.time()
    res = SFZ.score_frozen(fp, index, capability=cap, receipt_path=rp,
                           anchor_commit=anchor_commit, anchor_repo_relpath=anchor_rel,
                           repo_root=repo_root, progress=True)

    # OUTCOME-FREE projection only. The effect-bearing halves are never read here.
    out = {"phase": "PROCESS_2_COMPLETE",
           "n_records": n_recs,
           "freeze_hash_verified": res["freeze_hash_verified"],
           "receipt_verified": res["receipt_verified"],
           "anchor_verified": res["anchor_verified"],
           "anchor_commit": res["anchor_commit"],
           "producer_code_commit": res["producer_code_commit"],
           "executing_code_verified": res["executing_code_verified"],
           "blocks_validated_before_any_target_read":
               res["blocks_validated_before_any_target_read"],
           "binding_verified_fixtures": res["binding_verified_fixtures"],
           "endpoint_S_vs_R_structural": AG.structural_only(res["endpoint_S_vs_R"]),
           "endpoint_S_vs_H_structural": AG.structural_only(res["endpoint_S_vs_H"]),
           "arm_score_ok": {arm: sum(1 for r in res["records"]
                                     if r["arm"] == arm and r["status"] == "SCORE_OK")
                            for arm in ("S", "R", "H")},
           "n_records_scored": len(res["records"]),
           "elapsed_s": round(time.time() - t0, 1)}
    json.dump(out, open(os.path.join(outdir, "process2.json"), "w"), indent=1, default=str)
    print(f"[p2] verified {out['binding_verified_fixtures']} fixtures", flush=True)


# ============================================================== DRIVER
def run(bundle_root, outdir, k=4, n_limit=None):
    """prevalidate -> P1 (own process) -> anchor+commit -> P2 (own process) -> report."""
    os.makedirs(outdir, exist_ok=True)
    me = os.path.abspath(__file__)
    t0 = time.time()

    r1 = subprocess.run([sys.executable, me, "select", bundle_root, outdir, str(k)]
                        + ([str(n_limit)] if n_limit else []), cwd=ROOT)
    if r1.returncode != 0:
        raise SystemExit(f"PROCESS 1 failed with {r1.returncode}")
    p1 = json.load(open(os.path.join(outdir, "process1.json")))

    # ---- anchor the freeze externally, in a throwaway repo ----
    sys.path.insert(0, f"{ROOT}/tests/research/hypothesis_v8c")
    from _anchor_support import anchor_freeze
    import pathlib
    akw = anchor_freeze(pathlib.Path(outdir), p1["freeze_path"],
                        fixture_ids=[], classification=CLASSIFICATION,
                        receipt_path=p1["receipt_path"])

    r2 = subprocess.run([sys.executable, me, "score", bundle_root, outdir,
                         akw["anchor_commit"], akw["anchor_repo_relpath"], akw["repo_root"]],
                        cwd=ROOT)
    if r2.returncode != 0:
        raise SystemExit(f"PROCESS 2 failed with {r2.returncode}")
    p2 = json.load(open(os.path.join(outdir, "process2.json")))

    fz = json.load(open(p1["freeze_path"]))
    rows = fz["selections"]
    prov_complete = all(r.get("treatment_provenance") for r in rows)
    real_packets = all(r.get("packet_hash") and r["packet_hash"] != "REHEARSAL_PACKET"
                       for r in rows)

    report = {
        "rehearsal_version": "v8c_exposed50_rehearsal_v2",
        "EVIDENCE_CLASS": CLASSIFICATION,
        "supersedes": {"artifact": "V8C_EXPOSED50_REHEARSAL.json",
                       "preserved": True,
                       "why": ("v1 ran one process, held its selection hash in memory, called "
                               "the scorer directly, passed a literal placeholder packet, and "
                               "hardcoded DATA_BINDING_PASS=True")},
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "composed_through_real_entry_points": {
            "process_1": "select_freeze.select_cohort",
            "process_2": "score_frozen.score_frozen",
            "s_arm": "runner.run_fixture_converse (mocked transport)",
            "separate_os_processes": True},
        "PREVALIDATION": p1["prevalidation"],
        "N_FIXTURES": p1["n_fixtures"],
        "N_RECORDS": p1["n_records"],
        "SCORER_LOADED_IN_PROCESS_1": p1["scorer_was_loaded"],
        "FREEZE_HASH": p1["freeze_hash"],
        # ---- every PASS below is DERIVED from an executed check ----
        "ANCHOR_VERIFIED": p2["anchor_verified"],
        "RECEIPT_VERIFIED": p2["receipt_verified"],
        "EXECUTING_CODE_VERIFIED": p2["executing_code_verified"],
        "BLOCKS_VALIDATED_BEFORE_ANY_TARGET_READ":
            p2["blocks_validated_before_any_target_read"],
        "DATA_BINDING_PASS": p2["binding_verified_fixtures"] == p1["n_fixtures"],
        "DATA_BINDING_VERIFIED_FIXTURES": p2["binding_verified_fixtures"],
        "TREATMENT_PROVENANCE_COMPLETE": prov_complete,
        "REAL_PACKETS_USED": real_packets,
        "OUTCOME_SEAL_PASS": p1["prevalidation"]["sealed_stats_files_found"] == 0,
        "OUTCOME_SEAL_IS_STRUCTURAL_AND_PREVALIDATED": True,
        "ARM_SCORE_OK": p2["arm_score_ok"],
        "N_RECORDS_SCORED": p2["n_records_scored"],
        "ENDPOINT_S_vs_R_STRUCTURAL": p2["endpoint_S_vs_R_structural"],
        "ENDPOINT_S_vs_H_STRUCTURAL": p2["endpoint_S_vs_H_structural"],
        "S_SET_SIZES": sorted({r["k_valid"] for r in rows}),
        "ARM_STATUS_COUNTS": {st: sum(1 for r in rows if r["arm_status"] == st)
                              for st in sorted({r["arm_status"] for r in rows})},
        "R_IDENTITY_COUNT": sum(r["R_identity_count"] for r in rows),
        "R_CROSS_TREATMENT_OVERLAP_COUNT":
            sum(r["R_cross_treatment_overlap_count"] for r in rows),
        "LIVE_SEARCH_UNREACHABLE_COUNT":
            sum(r["reachability_live"]["n_live_unreachable"] for r in rows),
        "effect_direction_computed": False,
        "effect_fields_withheld": ["arm means", "paired differences", "inference", "p-values"],
        "sonnet_calls": 0, "spend_usd": 0,
        "elapsed_s": round(time.time() - t0, 1),
    }
    # Check actual KEYS, recursively. A substring scan over the serialised blob also matches
    # the NAMES of the fields we deliberately record as withheld, which is the opposite of a
    # leak -- it is the disclosure that they were withheld.
    def _keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from _keys(v)
        elif isinstance(o, list):
            for x in o:
                yield from _keys(x)

    present = set(_keys(report))
    leaked = sorted(present & set(FORBIDDEN_OUTPUT_KEYS))
    assert not leaked, f"rehearsal emitted a forbidden key: {leaked}"

    with open(OUT, "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(f"\n[rehearsal-v2] wrote {OUT}")
    for key in ("N_FIXTURES", "ANCHOR_VERIFIED", "EXECUTING_CODE_VERIFIED",
                "BLOCKS_VALIDATED_BEFORE_ANY_TARGET_READ", "DATA_BINDING_PASS",
                "TREATMENT_PROVENANCE_COMPLETE", "REAL_PACKETS_USED", "OUTCOME_SEAL_PASS",
                "ARM_SCORE_OK", "S_SET_SIZES"):
        print(f"    {key} = {report[key]}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "select":
        process_1(sys.argv[2], sys.argv[3], k=int(sys.argv[4]),
                  n_limit=int(sys.argv[5]) if len(sys.argv) > 5 else None)
    elif cmd == "score":
        process_2(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])
    elif cmd == "run":
        run(sys.argv[2], sys.argv[3], k=int(sys.argv[4]) if len(sys.argv) > 4 else 4,
            n_limit=int(sys.argv[5]) if len(sys.argv) > 5 else None)
    elif cmd == "prevalidate":
        print(json.dumps(prevalidate_bundle(sys.argv[2]), indent=1))
    else:
        raise SystemExit("usage: run|select|score|prevalidate <bundle> <outdir> [k] [n_limit]")
