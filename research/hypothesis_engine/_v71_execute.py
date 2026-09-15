"""V7.1 confirmatory execution driver. Section 21.

The driver exists BEFORE authorization so it can be dry-run: without the explicit
`--authorize` flag it performs every preflight check, constructs every object a real run
would construct, walks the frozen fold manifest, and then STOPS before the first confirmatory
effect. Running it in that mode computes no outcome and writes no evidence.

Preflight, all fail-closed:
  * every artifact hash in the V7.1 freeze manifest recomputes;
  * the experiment id and output directory are the V7.1 ones, never V7's;
  * the fresh manifest's zero-overlap proof still holds at fixture-identifier level;
  * the evaluability gate says the apparatus can answer its own question;
  * the engine spec hash matches the frozen one;
  * CHAMPION is unchanged, and is never opened for writing;
  * no Bedrock, AWS or model-invocation module is imported anywhere on the path.

On a real run, per-family evidence is flushed to disk BEFORE any aggregate is computed, so an
interruption leaves partial evidence rather than nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/src")

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import engine as EN
from src.research.hypothesis_v71 import evaluability as EVAL
from src.research.hypothesis_v71 import freshsample as FS
from src.research.hypothesis_v71 import similarity as SIM

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v7_1"
V7OUT = f"{ROOT}/research/hypothesis_oos/out/v7"
CHAMPION = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"

EXPERIMENT_ID = "V7_1_HARDENED_HYPOTHESIS_VALIDATION"

#: Any of these on the import path means the run would touch cloud infrastructure. The driver
#: refuses rather than proceeding; infrastructure is out of scope for this work.
FORBIDDEN_MODULE_TOKENS = ("boto3", "botocore", "bedrock", "converse", "counttokens")


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


class PreflightFailed(Exception):
    """A frozen precondition does not hold. Nothing is computed."""


def preflight():
    checks, problems = {}, []

    manifest_path = f"{OUT}/V7_1_FREEZE_MANIFEST.json"
    if not os.path.exists(manifest_path):
        raise PreflightFailed("freeze manifest absent: run _v71_freeze.py first")
    manifest = json.load(open(manifest_path))

    if manifest["experiment"] != EXPERIMENT_ID:
        problems.append(f"experiment id is {manifest['experiment']!r}")
    checks["experiment_id"] = manifest["experiment"]

    bad = []
    for name, expected in manifest["artifact_hashes"].items():
        path = f"{OUT}/{name}"
        if not os.path.exists(path):
            bad.append(f"{name}: missing")
        elif sha_file(path) != expected:
            bad.append(f"{name}: hash changed")
    checks["artifacts_verified"] = len(manifest["artifact_hashes"])
    checks["artifacts_failing"] = bad
    if bad:
        problems.append(f"{len(bad)} frozen artifacts differ")

    if os.path.realpath(OUT) == os.path.realpath(V7OUT):
        problems.append("output directory is V7's")
    checks["output_dir"] = OUT
    checks["refuses_v7_output_dir"] = True

    fresh = json.load(open(f"{OUT}/V7_1_FRESH_OOS_MANIFEST.json"))
    records = CI.load_records(include_fresh=True)
    development, confirmatory = FS.partition(records)
    overlap = FS.zero_overlap_proof(confirmatory, development)
    checks["zero_overlap_reverified"] = (overlap["disjoint_from_development"]
                                         and overlap["disjoint_from_v7_confirmatory"])
    if not checks["zero_overlap_reverified"]:
        problems.append("fresh sample no longer disjoint")
    if overlap["confirmatory_fixture_sha256"] != \
            fresh["zero_overlap"]["confirmatory_fixture_sha256"]:
        problems.append("the fresh confirmatory fixture set has changed since the freeze")
    checks["confirmatory_fixture_sha256"] = overlap["confirmatory_fixture_sha256"]

    gate = fresh.get("evaluability_gate") or {}
    checks["evaluability_verdict"] = gate.get("verdict")
    if gate.get("verdict") != EVAL.READY:
        problems.append(f"evaluability gate says {gate.get('verdict')}")

    if EN.spec_hash() != manifest["engine_spec_hash"]:
        problems.append("engine spec hash does not match the freeze")
    checks["engine_spec_hash"] = EN.spec_hash()

    champ = sha_file(CHAMPION)
    checks["champion_sha256"] = champ
    if champ != manifest["champion_sha256"]:
        problems.append("CHAMPION changed since the freeze")

    loaded = [m for m in sys.modules
              if any(tok in m.lower() for tok in FORBIDDEN_MODULE_TOKENS)]
    checks["cloud_modules_loaded"] = loaded
    if loaded:
        problems.append(f"cloud/model modules on the path: {loaded}")

    checks["problems"] = problems
    checks["ok"] = not problems
    return checks, manifest, fresh, (development, confirmatory)


def main(argv):
    authorized = "--authorize" in argv
    checks, manifest, fresh, (development, confirmatory) = preflight()

    print("=== V7.1 EXECUTION DRIVER ===")
    print(f"  mode                  : {'AUTHORIZED RUN' if authorized else 'DRY RUN'}")
    print(f"  experiment            : {checks['experiment_id']}")
    print(f"  artifacts verified    : {checks['artifacts_verified']} "
          f"(failing: {len(checks['artifacts_failing'])})")
    print(f"  zero overlap          : {checks['zero_overlap_reverified']}")
    print(f"  evaluability          : {checks['evaluability_verdict']}")
    print(f"  engine spec           : {checks['engine_spec_hash'][:16]}")
    print(f"  CHAMPION              : {checks['champion_sha256'][:16]}")
    print(f"  cloud modules loaded  : {checks['cloud_modules_loaded'] or 'none'}")

    # Construct everything a real run constructs, so the dry run exercises the real path.
    cov = json.load(open(f"{V7OUT}/V7_COVERAGE_MATRIX.json"))
    cap = CAP.CapabilityContract(cov)
    cap.assert_block_is_not_provider()
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    index = CI.PITIndex(development + confirmatory, metrics, CAP.METRIC_SEMANTICS)
    SIM.SimilarityEngine(index)
    fold_ids = fresh["fold_fixture_ids"]
    positions = {k: [index.pos_of_fixture[f] for f in v if f in index.pos_of_fixture]
                 for k, v in fold_ids.items()}
    print(f"  index                 : {len(index.recs)} records")
    print(f"  folds                 : "
          f"{ {k: len(v) for k, v in sorted(positions.items())} }")

    if not checks["ok"]:
        print("\nPREFLIGHT FAILED -- nothing computed:")
        for p in checks["problems"]:
            print("   -", p)
    if not authorized:
        print("\nDRY RUN COMPLETE. No confirmatory outcome was computed, read or written.")
        print("CONFIRMATORY_OOS_COMPUTED=false  CONFIRMATORY_OOS_VIEWED=false")
        json.dump({"driver_version": "v71_execute_v1", "mode": "DRY_RUN",
                   "preflight": checks,
                   "fold_position_counts": {k: len(v) for k, v in positions.items()},
                   "confirmatory_oos_computed": False,
                   "confirmatory_oos_viewed": False},
                  open(f"{OUT}/V7_1_DRY_RUN.json", "w"), indent=1, sort_keys=True)
        return 0

    if not checks["ok"]:
        print("\nREFUSING TO RUN: preflight failed under --authorize.")
        return 2
    print("\nAuthorized execution is not implemented in this mission: section 28 forbids "
          "computing any confirmatory outcome. A separate authorization is required.")
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
