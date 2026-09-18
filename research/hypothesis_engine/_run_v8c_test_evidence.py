"""Emit V8C_TEST_RESULTS.json from ACTUAL pytest outcomes (P1-G).

Runs the suite, captures the node ids that genuinely PASSED, and stamps provenance. The
defect ledger then DERIVES p0_open / p1_open from that node list -- no literal is written and
none is read.

ZERO Sonnet calls. No sealed-947 access.
"""
from __future__ import annotations

import json
import subprocess
import sys

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
sys.path.insert(0, ROOT)
OUT = f"{ENG}/V8C_TEST_RESULTS.json"


def main():
    from src.research.hypothesis_v8c import cache as CACHE
    from src.research.hypothesis_v8c import defect_ledger as DL
    from src.research.hypothesis_v8c import harness as H
    from src.research.hypothesis_v8c import provenance as PROV
    from src.research.hypothesis_v8c import runner as RUN
    from src.research.hypothesis_v8c import vintage as VIN

    champ = H.assert_champion_unchanged()

    # -- run the suite and capture per-node outcomes ------------------------------------
    rc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/research/hypothesis_v8c/", "-q",
         "-p", "no:cacheprovider", "--tb=no", "-rA"],
        cwd=ROOT, capture_output=True, text=True, timeout=3600)

    passed, failed = [], []
    for line in rc.stdout.splitlines():
        if line.startswith("PASSED "):
            passed.append(line.split(" ", 1)[1].strip())
        elif line.startswith(("FAILED ", "ERROR ")):
            failed.append(line.split(" ", 1)[1].strip())

    ledger = DL.evaluate(passed)

    # -- authoritative call ledger: a V8C cache entry is the ONLY trace a paid call leaves --
    import os
    n_cached = (len([f for f in os.listdir(CACHE.CACHE_DIR) if f.endswith(".json")])
                if os.path.isdir(CACHE.CACHE_DIR) else 0)

    seal = subprocess.run(
        [sys.executable, "-c",
         "import sys;from src.research.hypothesis_v8c import select_freeze,universe,controls,"
         "pre_t,grammar,pit_context,blind_index,cohort_stats;"
         "print(sorted(m for m in sys.modules if 'scorer' in m))"],
        cwd=ROOT, capture_output=True, text=True)
    seal_clean = seal.returncode == 0 and seal.stdout.strip() == "[]"

    iso = CACHE.assert_isolated_from_v8b1()
    cap, index, _ = H.build(check_champion=False)

    out = {
        "test_results_version": "v8c_test_results_v2",
        "passed_node_ids": sorted(passed),
        "failed_node_ids": sorted(failed),
        "n_passed": len(passed), "n_failed": len(failed),
        "pytest_returncode": rc.returncode,

        # DERIVED, not declared:
        "defect_ledger": ledger,
        "p0_open_derived": ledger["p0_open"], "p1_open_derived": ledger["p1_open"],

        "outcome_seal": "PASS" if seal_clean else "FAIL",
        "pre_t_import_set_scorer_modules": seal.stdout.strip(),
        "cache_isolation": "PASS" if iso["directories_distinct"] else "FAIL",
        "cache_isolation_evidence": iso,

        # authoritative call ledger rather than a declared integer
        "sonnet_call_ledger": {
            "total_calls": n_cached,
            "source": "count of entries in the V8C cache namespace",
            "v8c_cache_dir": CACHE.CACHE_DIR,
            "runner_performs_model_call_in_this_mission":
                RUN.version_stamp()["performs_model_call_in_v8c_mission"],
        },
        "sealed_947_referenced": False,
        "champion_sha256": champ,
    }
    out[PROV.PROVENANCE_KEY] = PROV.stamp(
        corpus_hash=VIN.corpus_vintage_full(index),
        capability_hash=VIN.capability_hash(cap))

    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, default=str, sort_keys=True)

    print(f"[tests] passed={len(passed)} failed={len(failed)}")
    print(f"[tests] DERIVED p0_open={ledger['p0_open']}/{ledger['p0_total']} "
          f"p1_open={ledger['p1_open']}/{ledger['p1_total']}")
    print(f"[tests] closed P0: {ledger['p0_closed']}")
    print(f"[tests] closed P1: {ledger['p1_closed']}")
    print(f"[tests] still open: {ledger['open_ids']}")
    print(f"[tests] sonnet calls (cache-ledger) = {n_cached}")
    print(f"[tests] wrote {OUT}")


if __name__ == "__main__":
    main()
