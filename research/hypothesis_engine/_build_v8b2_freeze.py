"""V8B.2 freeze builder. FAILS CLOSED unless every reachability/PIT/determinism/mutation gate
passes AND the general evaluator contract certifies the scorer's SCORE_OK is reachable.

Systemic upgrade (instruction section 14): the freeze builder REFUSES to freeze a scorer whose
terminal success state SCORE_OK has no passing, UNCONDITIONAL reachability test artifact. This
prevents the V8B.1 class of bug (a frozen scorer whose success state was structurally
unreachable and never proven) from ever recurring.

Required gates (all must be true, else raise FreezeRefused):
  SCORE_OK_SYNTHETIC_REACHABLE      -- tests/.../test_scorer.py::test_score_ok_is_reachable_end_to_end
  SCORE_OK_REAL_CORPUS_REACHABLE    -- V8B2_EXPOSED50_SCORER_REGRESSION.json shows >=1 SCORE_OK
  SUPPORT_FAILURE_MUTATION_TESTS    -- one-failure-at-a-time tests pass
  PIT_TESTS                         -- PIT test cases pass
  DETERMINISM                       -- determinism test passes
  EVALUATOR_CONTRACT                -- tests/research/test_evaluator_contract.py passes
  CHAMPION_UNCHANGED
Records exact hashes of every load-bearing file.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
OUT = f"{ENG}/V8B2_FREEZE_MANIFEST.json"
REGRESSION = f"{ENG}/V8B2_EXPOSED50_SCORER_REGRESSION.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

PY = f"{ROOT}/.venv/bin/python"


class FreezeRefused(Exception):
    pass


def _sha_file(p):
    with open(f"{ROOT}/{p}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _sha_obj(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def _pytest(node) -> bool:
    r = subprocess.run([PY, "-m", "pytest", node, "-q", "--no-header"],
                       cwd=ROOT, capture_output=True, text=True)
    ok = r.returncode == 0
    print(f"  pytest {node} -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(r.stdout[-1500:])
    return ok


def main():
    checks = {}

    # ---- 1. synthetic reachability (the NON-NEGOTIABLE gate) ----
    checks["SCORE_OK_SYNTHETIC_REACHABLE"] = _pytest(
        "tests/research/hypothesis_v8b2/test_scorer.py::test_score_ok_is_reachable_end_to_end")

    # ---- 2. mutation, PIT, determinism (whole scorer+support suite) ----
    checks["SUPPORT_FAILURE_MUTATION_TESTS"] = _pytest(
        "tests/research/hypothesis_v8b2/test_support.py")
    checks["PIT_AND_DETERMINISM_TESTS"] = _pytest(
        "tests/research/hypothesis_v8b2/test_scorer.py")

    # ---- 3. general evaluator contract ----
    checks["EVALUATOR_CONTRACT"] = _pytest("tests/research/test_evaluator_contract.py")

    # ---- 4. real-corpus reachability from the regression artifact ----
    real_ok = False
    reg = None
    try:
        reg = json.load(open(REGRESSION))
        total_ok = sum(reg["arms"][a]["score_ok"] for a in reg["arms"])
        real_ok = total_ok >= 1 and reg.get("champion_unchanged", False)
        print(f"  real-corpus SCORE_OK across arms = {total_ok} -> "
              f"{'PASS' if real_ok else 'FAIL'}")
    except FileNotFoundError:
        print("  regression artifact missing -> FAIL")
    checks["SCORE_OK_REAL_CORPUS_REACHABLE"] = real_ok

    # ---- 5. CHAMPION unchanged ----
    champ = _sha_file("data/discovery/pilotC_stat_mixer.json")
    checks["CHAMPION_UNCHANGED"] = champ == CHAMPION_EXPECTED
    print(f"  champion_unchanged -> {checks['CHAMPION_UNCHANGED']}")

    # ---- FAIL CLOSED ----
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise FreezeRefused(f"V8B.2 freeze REFUSED; failing gates: {failed}")

    from src.research.hypothesis_v8b2 import scorer as SC
    from src.research.hypothesis_v8b2 import support as SUP
    sys.path.insert(0, ROOT)

    manifest = {
        "freeze_version": "v8b2_freeze_manifest_v1",
        "supersedes_scorer": "v8b1_scorer_v1",
        "reason": "fix P1: fixture-level support gate used unique_teams(=1) vs "
                  "MIN_UNIQUE_TEAMS(=6) -> SCORE_OK structurally unreachable. V8B.2 uses "
                  "unique_opponents (fixture-level diversity analogue, threshold 6, "
                  "effect-blind translation).",
        "gates": checks,
        "known_good_reachability_test": True,
        "scorer_version": SC.version_stamp()["scorer_version"],
        "support_version": SUP.version_stamp()["fixture_support_version"],
        "threshold_change": SUP.version_stamp()["corrected"],
        "code_hashes": {
            "v8b2_scorer_py": _sha_file("src/research/hypothesis_v8b2/scorer.py"),
            "v8b2_support_py": _sha_file("src/research/hypothesis_v8b2/support.py"),
            "v8b2_test_scorer_py": _sha_file("tests/research/hypothesis_v8b2/test_scorer.py"),
            "v8b2_test_support_py": _sha_file("tests/research/hypothesis_v8b2/test_support.py"),
            "evaluator_contract_test_py": _sha_file("tests/research/test_evaluator_contract.py"),
            "regression_driver_py": _sha_file("research/hypothesis_engine/_run_v8b2_exposed50_regression.py"),
            "frozen_v8b1_scorer_py_UNCHANGED": _sha_file("src/research/hypothesis_v8b1/scorer.py"),
            "v7_pit_py": _sha_file("src/research/hypothesis_v7/pit.py"),
        },
        "artifact_hashes": {
            "exposed50_regression": _sha_file("research/hypothesis_engine/V8B2_EXPOSED50_SCORER_REGRESSION.json"),
        },
        "real_corpus_score_ok_by_arm": {a: reg["arms"][a]["score_ok"] for a in reg["arms"]},
        "champion_unchanged": checks["CHAMPION_UNCHANGED"],
        "champion_sha256": champ,
        "llm_layer_changed": False,
        "scientific_parameters_changed": "support gate diversity unit only (unique_teams -> "
                                         "unique_opponents); no LLM/prompt/packet/search/control "
                                         "/other-threshold change",
        "sealed_947_outcomes_viewed": False,
    }
    manifest["freeze_self_hash"] = _sha_obj(manifest)
    with open(OUT, "w") as f:
        json.dump(manifest, f, indent=1, default=str)
    print(f"\n[freeze] ALL GATES PASS. wrote {OUT}")
    print(f"[freeze] self_hash={manifest['freeze_self_hash']}")


if __name__ == "__main__":
    try:
        main()
    except FreezeRefused as e:
        print(f"\n*** {e} ***")
        sys.exit(4)
