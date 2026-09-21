"""ITEM 6 freeze builder. FAILS CLOSED unless every gate passes:
  - all Item-6 tests pass (anti-imitation, anti-baseline, provider-safety, point-in-time,
    gate+rehearsal),
  - the stand-in rehearsal shows the apparatus can register BOTH a PASS (MODE_RICH) and a FAIL
    (MODE_POOR, ARM_GD_CONTROL) — i.e. the instrument is falsifiable,
  - the cohort has zero V1/V2/V3 overlap,
  - CHAMPION is unchanged,
  - the prompt body contains no worked football example (anti-imitation suite),
  - zero paid calls / zero spend.

Records exact sha256 of every load-bearing file. Mirrors the V8B.2 freeze discipline.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys

ROOT = "/home/ubuntu"
ITEM6 = f"{ROOT}/research/item6"
OUT = f"{ITEM6}/ITEM6_FREEZE_MANIFEST.json"
PY = f"{ROOT}/.venv/bin/python"
CHAMPION = "data/discovery/pilotC_stat_mixer.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

CODE_FILES = [
    "src/research/item6/__init__.py",
    "src/research/item6/baseline_coverage.py",
    "src/research/item6/provider_vocab.py",
    "src/research/item6/schema.py",
    "src/research/item6/baseline_equivalence.py",
    "src/research/item6/formalizer.py",
    "src/research/item6/stage1_metrics.py",
    "src/research/item6/stage1_gate.py",
    "src/research/item6/control_generator.py",
    "src/research/item6/registry.py",
    "src/research/item6/harness.py",
    "src/research/item6/quality_protocol.py",
]
DOC_FILES = [
    "research/item6/ITEM6_RESEARCH_PROTOCOL_V1.md",
    "research/item6/DETERMINISTIC_BASELINE_COVERAGE_SPEC_V1.md",
    "research/item6/DETERMINISTIC_BASELINE_COVERAGE_SPEC_V1.json",
    "research/item6/ITEM6_MECHANISM_PROMPT_V1.md",
    "research/item6/ITEM6_MECHANISM_SCHEMA_V1.md",
    "research/item6/NOVEL_FAMILY_REGISTRY_SCHEMA_V1.md",
    "research/item6/NOVEL_FAMILY_REGISTRY_SCHEMA_V1.json",
    "research/item6/STAGE1_QUALITY_PROTOCOL_V1.md",
    "research/item6/STAGE1_GATE_V1.md",
    "research/item6/STAGE1_POWER_AND_COST_V1.md",
    "research/item6/STAGE2_FRAMEWORK_V1.md",
    "research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json",
    "research/item6/ITEM6_VERSION_STAMPS.json",
]
TEST_FILES = [
    "tests/research/item6/test_anti_imitation.py",
    "tests/research/item6/test_anti_baseline.py",
    "tests/research/item6/test_provider_safety.py",
    "tests/research/item6/test_point_in_time.py",
    "tests/research/item6/test_gate_and_rehearsal.py",
]


class FreezeRefused(Exception):
    pass


def _sha_file(rel):
    with open(f"{ROOT}/{rel}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _sha_obj(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def _pytest(node):
    r = subprocess.run([PY, "-m", "pytest", node, "-q", "--no-header"],
                       cwd=ROOT, capture_output=True, text=True)
    ok = r.returncode == 0
    print(f"  pytest {node} -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        print(r.stdout[-1500:])
    return ok


def main():
    checks = {}

    checks["ITEM6_TESTS_PASS"] = _pytest("tests/research/item6")

    # rehearsal falsifiability: RICH pass, POOR fail, control fail
    rehearsal = json.load(open(f"{ITEM6}/out/STANDIN_REHEARSAL.json"))
    res = rehearsal["results"]
    checks["APPARATUS_CAN_PASS"] = res["MODE_RICH"]["gate_passed"] is True
    checks["APPARATUS_CAN_FAIL_POOR"] = res["MODE_POOR"]["gate_passed"] is False
    checks["APPARATUS_CAN_FAIL_CONTROL"] = res["ARM_GD_CONTROL"]["gate_passed"] is False
    checks["REHEARSAL_ZERO_SPEND"] = rehearsal["made_paid_call"] is False

    # cohort overlap
    cohort = json.load(open(f"{ITEM6}/ITEM6_STAGE1_COHORT_MANIFEST_V1.json"))
    checks["COHORT_ZERO_V1V2V3_OVERLAP"] = (
        cohort["v1_fixture_overlap"] == 0
        and cohort["v2_fixture_overlap"] == 0
        and cohort["v3_fixture_overlap"] == 0)

    # champion unchanged
    champ = _sha_file(CHAMPION)
    checks["CHAMPION_UNCHANGED"] = champ == CHAMPION_EXPECTED
    print(f"  champion_unchanged -> {checks['CHAMPION_UNCHANGED']}")

    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise FreezeRefused(f"ITEM6 freeze REFUSED; failing gates: {failed}")

    manifest = {
        "freeze_version": "item6_freeze_manifest_v1",
        "experiment": "ITEM6_NOVEL_HYPOTHESIS_DISCOVERY_AND_INCREMENTAL_VALUE",
        "gates": checks,
        "two_stage_design": True,
        "stage1_required_before_stage2": True,
        "no_worked_football_example": True,
        "old_grammar_forced_during_discovery": False,
        "no_llm_numerical_prediction": True,
        "oos_blinded_during_stage1": True,
        "champion_independent": True,
        "champion_unchanged": checks["CHAMPION_UNCHANGED"],
        "champion_sha256": champ,
        "live_sonnet_calls": 0,
        "bedrock_paid_calls": 0,
        "new_spend_usd": 0,
        "k_mechanisms_per_fixture": 5,
        "abstention_allowed": True,
        "stage1_selected_n_fixtures": cohort["n_selected"],
        "cohort_manifest_hash": cohort["manifest_hash"],
        "rehearsal_results": {m: {"gate_passed": res[m]["gate_passed"],
                                  "n_novel_families": res[m]["n_novel_families"]}
                              for m in ("MODE_RICH", "MODE_POOR", "ARM_GD_CONTROL")},
        "code_hashes": {p: _sha_file(p) for p in CODE_FILES},
        "doc_hashes": {p: _sha_file(p) for p in DOC_FILES},
        "test_hashes": {p: _sha_file(p) for p in TEST_FILES},
        "stage2_activation": "BLOCKED_UNLESS_STAGE1_PASS",
    }
    manifest["freeze_self_hash"] = _sha_obj(manifest)
    with open(OUT, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(f"\n[freeze] ALL GATES PASS. wrote {OUT}")
    print(f"[freeze] self_hash={manifest['freeze_self_hash']}")


if __name__ == "__main__":
    try:
        main()
    except FreezeRefused as e:
        print(f"\n*** {e} ***")
        sys.exit(4)
