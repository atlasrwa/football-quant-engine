"""V7.1 confirmatory execution driver. Section 21.

The driver is the ONLY place authorization lives. The scientific machinery is in
`src.research.hypothesis_v71.execution`; the driver decides WHETHER to run it (authorization)
and WITH WHICH fold positions (the fresh confirmatory sample). The future authorized run calls
exactly the same `execution.run_experiment` this file already calls in the dry path -- there is
no separate real-run-only code.

Two independent conditions are BOTH required to compute a confirmatory outcome:
  * the explicit `--authorize` flag;
  * a valid `V7_1_CONFIRMATORY_AUTHORIZATION.json` token whose bound hashes match the LIVE
    freeze manifest, executable source graph, upstream V7 inputs and fresh content.
The token does not exist during the closure mission, so `--authorize` alone still refuses.
Opening the door later needs no code change -- only the (deliberately) missing token.

Preflight, all fail-closed:
  * every artifact hash in the V7.1 freeze manifest recomputes;
  * the experiment id and output directory are the V7.1 ones, never V7's;
  * the fresh manifest's zero-overlap proof still holds at fixture-identifier level;
  * the fresh CONTENT commitment still holds (same ids AND same values), not only the ids;
  * every consumed upstream V7 artifact recomputes to its frozen hash (proof-independent);
  * the executable SOURCE GRAPH recomputes -- a code change refuses even without a version bump;
  * the evaluability gate says the apparatus can answer its own question;
  * the engine spec hash matches the frozen one;
  * CHAMPION is unchanged, and is never opened for writing;
  * no Bedrock, AWS or model-invocation module is imported anywhere on the path.

Without `--authorize` the driver runs every preflight check, BUILDS the full execution plan,
and STOPS before evaluating a single family: it computes no outcome and writes no evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/src")

from src.research.hypothesis_v71 import authorization as AUTH
from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import engine as EN
from src.research.hypothesis_v71 import evaluability as EVAL
from src.research.hypothesis_v71 import execution as EX
from src.research.hypothesis_v71 import freshsample as FS
from src.research.hypothesis_v71 import provenance as PV

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v7_1"
V7OUT = f"{ROOT}/research/hypothesis_oos/out/v7"
CHAMPION = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"

EXPERIMENT_ID = "V7_1_HARDENED_HYPOTHESIS_VALIDATION"

#: The entry points whose transitive first-party import closure IS the executable code.
SOURCE_ENTRY_POINTS = ("research/hypothesis_engine/_v71_execute.py",
                       "src/research/hypothesis_v71/execution.py")

#: Any of these on the import path means the run would touch cloud infrastructure. The driver
#: refuses rather than proceeding; infrastructure is out of scope for this work.
FORBIDDEN_MODULE_TOKENS = ("boto3", "botocore", "bedrock", "converse", "counttokens")


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


class PreflightFailed(Exception):
    """A frozen precondition does not hold. Nothing is computed."""


def _load(path):
    return json.load(open(path))


def preflight():
    checks, problems = {}, []

    manifest_path = f"{OUT}/V7_1_FREEZE_MANIFEST.json"
    if not os.path.exists(manifest_path):
        raise PreflightFailed("freeze manifest absent: run _v71_freeze.py first")
    manifest = _load(manifest_path)

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

    fresh = _load(f"{OUT}/V7_1_FRESH_OOS_MANIFEST.json")
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

    # ---- fresh CONTENT commitment (item 7): same ids AND same values -------------------
    content_ok = True
    content_path = f"{OUT}/V7_1_FRESH_CONTENT_COMMITMENT.json"
    if os.path.exists(content_path):
        frozen_content = _load(content_path)["fresh_content"]
        content_ok, content_problems, _live = PV.verify_content(
            frozen_content, confirmatory, CAP.METRIC_SEMANTICS)
        problems += content_problems
        checks["fresh_content_sha256"] = frozen_content["content_sha256"]
    else:
        content_ok = False
        problems.append("fresh content commitment absent: run _v71_freeze.py")
        checks["fresh_content_sha256"] = None
    checks["fresh_content_reverified"] = content_ok

    # ---- upstream V7 inputs (item 6): recomputed, not trusted from the proof -----------
    prov_path = f"{OUT}/V7_1_PROVENANCE.json"
    upstream_ok = source_ok = True
    if os.path.exists(prov_path):
        prov = _load(prov_path)
        upstream_ok, up_problems, _l = PV.verify_upstream_v7(prov["upstream_v7"], root=ROOT)
        source_ok, src_problems, _l2 = PV.verify_source_graph(prov["source_graph"], root=ROOT)
        problems += up_problems + src_problems
        checks["upstream_sha256"] = prov["upstream_v7"]["upstream_sha256"]
        checks["source_graph_sha256"] = prov["source_graph"]["source_graph_sha256"]
    else:
        upstream_ok = source_ok = False
        problems.append("provenance commitment absent: run _v71_freeze.py")
        checks["upstream_sha256"] = checks["source_graph_sha256"] = None
    checks["upstream_reverified"] = upstream_ok
    checks["source_graph_reverified"] = source_ok

    gate = fresh.get("evaluability_gate") or {}
    checks["evaluability_verdict"] = gate.get("verdict")
    if gate.get("verdict") != EVAL.READY:
        problems.append(f"evaluability gate says {gate.get('verdict')}")

    if EN.spec_hash() != manifest["engine_spec_hash"]:
        problems.append("engine spec hash does not match the freeze")
    checks["engine_spec_hash"] = EN.spec_hash()

    frozen_interp = manifest.get("interpreter")
    live_interp = {"executable": sys.executable, "version": sys.version.split()[0],
                   "implementation": sys.implementation.name}
    checks["interpreter"] = live_interp
    checks["interpreter_matches_freeze"] = frozen_interp == live_interp
    if frozen_interp is None:
        problems.append("freeze manifest records no interpreter to pin against")
    elif frozen_interp != live_interp:
        problems.append(f"interpreter differs from the freeze: frozen={frozen_interp} "
                        f"live={live_interp}")

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


def check_authorization(checks):
    """Verify the confirmatory authorization token against the LIVE bindings. The token does
    not exist during the closure mission, so this returns authorized=False by design."""
    expected = AUTH.build_expected(
        experiment=EXPERIMENT_ID,
        freeze_manifest_sha256=sha_file(f"{OUT}/V7_1_FREEZE_MANIFEST.json"),
        source_graph_sha256=checks.get("source_graph_sha256"),
        upstream_sha256=checks.get("upstream_sha256"),
        fresh_content_sha256=checks.get("fresh_content_sha256"))
    token_path = f"{OUT}/{AUTH.AUTHORIZATION_ARTIFACT}"
    token = _load(token_path) if os.path.exists(token_path) else None
    return AUTH.verify(token, expected)


def build_plan(fresh, development, confirmatory):
    """Construct the full ExecutionPlan a real run would use, WITHOUT evaluating a family.

    Reuses the frozen treated universe, control pools and matching from disk. The fold
    positions are the fresh confirmatory folds; nothing here reads an outcome.
    """
    cov = _load(f"{V7OUT}/V7_COVERAGE_MATRIX.json")
    cap = CAP.CapabilityContract(cov)
    cap.assert_block_is_not_provider()
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    index = CI.PITIndex(development + confirmatory, metrics, CAP.METRIC_SEMANTICS)

    # treated + uniform + marginal specs, rebuilt from the frozen pools/universe
    treated_specs, uniform_specs, marginal_specs = _load_specs(cap)
    matching = _load(f"{OUT}/V7_1_MATCHING.json")["match"]
    weights = _load(f"{OUT}/V7_1_MATCHING_WEIGHTS.json")
    matching = dict(matching, control_weights=weights)

    fold_ids = fresh["fold_fixture_ids"]
    folds = []
    for k in sorted(fold_ids):
        positions = [index.pos_of_fixture[f] for f in fold_ids[k]
                     if f in index.pos_of_fixture]
        folds.append({"fold_index": int(k), "positions": positions})

    plan = EX.prepare_execution(
        index, folds, treated_specs=treated_specs, uniform_specs=uniform_specs,
        marginal_specs=marginal_specs, matching=matching, capability=cap,
        classification=EX.CLASS_CONFIRMATORY)
    return plan, folds


def _load_specs(cap):
    """Rebuild the {id: spec} maps for the treated arm, the uniform pool and the marginal pool
    from the frozen artifacts. Deterministic; reads no outcome."""
    from src.research.hypothesis_v71 import ir as IRM

    dedup = _load(f"{V7OUT}/V7_DEDUPLICATION.json")
    universe = _load(f"{V7OUT}/V7_HYPOTHESIS_UNIVERSE.json")
    origin_to_cid = {o["v7_hypothesis_id"]: f["canonical_hypothesis_id"]
                     for f in dedup["families"] for o in f["origins"]}
    treated_specs = {}
    for h in universe["hypotheses"]:
        cid = origin_to_cid.get(h["v7_hypothesis_id"])
        if cid and cid not in treated_specs:
            treated_specs[cid] = h["spec"]

    uniform_pool = _load(f"{OUT}/V7_1_CONTROL_UNIFORM_POOL.json")["pool"]
    marginal_pool = _load(f"{OUT}/V7_1_CONTROL_MARGINAL_POOL.json")["pool"]
    uniform_specs = {f"uniform_{p['null_index']}": p for p in uniform_pool}
    marginal_specs = {f"null_{p['null_index']}": p for p in marginal_pool}
    _ = IRM  # keep the import meaningful for the source-graph closure
    return treated_specs, uniform_specs, marginal_specs


def main(argv):
    authorized_flag = "--authorize" in argv
    checks, manifest, fresh, (development, confirmatory) = preflight()
    auth = check_authorization(checks)

    plan, folds = build_plan(fresh, development, confirmatory)

    print("=== V7.1 EXECUTION DRIVER ===")
    print(f"  mode                  : {'AUTHORIZED RUN' if authorized_flag else 'DRY RUN'}")
    print(f"  experiment            : {checks['experiment_id']}")
    print(f"  artifacts verified    : {checks['artifacts_verified']} "
          f"(failing: {len(checks['artifacts_failing'])})")
    print(f"  zero overlap          : {checks['zero_overlap_reverified']}")
    print(f"  fresh content bound   : {checks['fresh_content_reverified']}")
    print(f"  upstream V7 reverified: {checks['upstream_reverified']}")
    print(f"  source graph reverif. : {checks['source_graph_reverified']}")
    print(f"  evaluability          : {checks['evaluability_verdict']}")
    print(f"  engine spec           : {checks['engine_spec_hash'][:16]}")
    print(f"  CHAMPION              : {checks['champion_sha256'][:16]}")
    print(f"  interpreter pinned    : {checks['interpreter_matches_freeze']} "
          f"({checks['interpreter']['executable']} {checks['interpreter']['version']})")
    print(f"  cloud modules loaded  : {checks['cloud_modules_loaded'] or 'none'}")
    print(f"  authorization token   : "
          f"{'valid' if auth['authorized'] else 'ABSENT/INVALID'}")
    print(f"  treated evaluable     : {len(plan.treated)}")
    print(f"  controls rebuilt      : {len(plan.controls)}")
    print(f"  uniform evaluable     : {len(plan.uniform)}")
    print(f"  folds                 : "
          f"{ {f['fold_index']: len(f['positions']) for f in folds} }")

    if not checks["ok"]:
        print("\nPREFLIGHT FAILED -- nothing computed:")
        for p in checks["problems"]:
            print("   -", p)

    # --- the one-way door: BOTH the flag AND a valid token, else refuse and compute nothing
    if not (authorized_flag and auth["authorized"]):
        print("\nDRY RUN COMPLETE. No confirmatory outcome was computed, read or written.")
        print("CONFIRMATORY_OOS_COMPUTED=false  CONFIRMATORY_OOS_VIEWED=false")
        if authorized_flag and not auth["authorized"]:
            print("REFUSING TO OPEN OOS: --authorize was given but the authorization token "
                  "is absent or does not match the live freeze/source/content:")
            for p in auth["problems"]:
                print("   -", p)
        json.dump({"driver_version": "v71_execute_v2", "mode": "DRY_RUN",
                   "preflight": checks,
                   "authorization": auth,
                   "fold_position_counts": {f["fold_index"]: len(f["positions"])
                                            for f in folds},
                   "plan": {"treated_evaluable": len(plan.treated),
                            "controls_rebuilt": len(plan.controls),
                            "uniform_evaluable": len(plan.uniform)},
                   "confirmatory_oos_computed": False,
                   "confirmatory_oos_viewed": False},
                  open(f"{OUT}/V7_1_DRY_RUN.json", "w"), indent=1, sort_keys=True)
        return 0

    # --- authorized AND token valid: run the SAME machinery the dry path built -----------
    if not checks["ok"]:
        print("\nREFUSING TO RUN: preflight failed under --authorize.")
        return 2
    result = EX.run_experiment(plan, OUT, experiment_id=EXPERIMENT_ID,
                               champion_sha256=checks["champion_sha256"], persist=True)
    json.dump(result, open(f"{OUT}/V7_1_CONFIRMATORY_RESULT.json", "w"),
              indent=1, sort_keys=True, default=str)
    print("\nCONFIRMATORY RUN COMPLETE.")
    print(f"CONFIRMATORY_OOS_COMPUTED=true  evidence_bundle "
          f"{result['evidence_bundle_sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
