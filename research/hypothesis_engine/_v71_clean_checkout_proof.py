"""V7.1 CLEAN-CHECKOUT EXECUTABILITY PROOF (mission item 10).

The v2 freeze verified every hash it bound -- 32 artifacts, the interpreter, CHAMPION, the
upstream V7 inputs and its own source graph all matched -- and the apparatus still could not run,
because the code that loads the corpus was neither bound nor committed. Self-consistency is
therefore not evidence of executability, and hashing the working tree is not evidence that the
COMMIT works.

This driver is meant to be run INSIDE an isolated checkout of the candidate apparatus commit,
presented at the same absolute root the apparatus hard-codes. It demonstrates, from that
checkout alone, that the frozen commit can:

  * present an empty `git status --porcelain`;
  * contain no untracked executable Python under the code roots (nothing was copied in);
  * import every V7.1 module;
  * build the corpus;
  * verify the fresh CONTENT commitment;
  * verify the historical point-in-time snapshot;
  * rebuild the full confirmatory execution plan;
  * run the DEVELOPMENT_ONLY execution path end to end;
  * pass preflight while REFUSING to compute without an authorization token;
  * pass the V7.1 test suite.

The proof binds `freeze_manifest_sha256`, so a proof and a freeze cannot drift apart: if the
apparatus is re-frozen, the old proof no longer matches and the guard test fails.

Git-ignored DATA may legitimately be supplied to the checkout (it is not in the commit); ignored
or copied `.py` may NOT, and this driver checks that.

ZERO SPEND. No Bedrock. No CHAMPION write. No fresh outcome: the fresh sample is opened only for
its INPUT content commitment, never for an effect. CONFIRMATORY_OOS_COMPUTED stays false.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/src")

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v7_1"
ENGINE_DIR = f"{ROOT}/research/hypothesis_engine"
ARTIFACT = "V7_1_CLEAN_CHECKOUT_PROOF.json"

#: directories whose Python files are apparatus code; untracked `.py` here means something was
#: copied into the checkout, which would invalidate the whole point of the exercise.
CODE_ROOTS = ("src", "scripts", "research", "tests")

#: every module of the V7.1 package must import from the clean commit
V71_MODULES = (
    "authorization", "bugledger", "capability", "compiler", "confounders", "controls",
    "corpus_index", "covariate_bridge", "engine", "estimator", "evaluability", "execution",
    "freshsample", "golden", "invariants", "ir", "leakage", "matching", "ontology",
    "provenance", "recency", "similarity",
)


def _git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)


def _load_script(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    t0 = time.time()
    stages, detail, failures = {}, {}, []

    def stage(name, ok, info=None):
        stages[name] = bool(ok)
        if info is not None:
            detail[name] = info
        if not ok:
            failures.append(name)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {info}" if info else ""))

    print("=== V7.1 CLEAN-CHECKOUT EXECUTABILITY PROOF ===")

    # ---- 1. the checkout is clean and identifiable ------------------------------------
    head = _git("rev-parse", "HEAD").stdout.strip()
    porcelain = _git("status", "--porcelain").stdout
    # NOTE: taken BEFORE this driver writes its own artifact.
    stage("git_status_porcelain_empty", porcelain.strip() == "",
          f"head={head[:9]}" if porcelain.strip() == "" else
          f"{len(porcelain.splitlines())} entries")

    # ---- 2. nothing executable was copied in ------------------------------------------
    untracked_py = [p for p in _git("ls-files", "--others", "--exclude-standard",
                                    "--", *CODE_ROOTS).stdout.splitlines()
                    if p.endswith(".py")]
    ignored_py = [p for p in _git("ls-files", "--others", "--ignored", "--exclude-standard",
                                  "--", *CODE_ROOTS).stdout.splitlines()
                  if p.endswith(".py")]
    stage("no_untracked_executable_py", not untracked_py, str(untracked_py or "none"))
    stage("no_ignored_executable_py", not ignored_py, str(ignored_py or "none"))

    # ---- 3. every V7.1 module imports from the clean commit ---------------------------
    import_failures = []
    for m in V71_MODULES:
        try:
            __import__(f"src.research.hypothesis_v71.{m}")
        except Exception as exc:                                    # noqa: BLE001
            import_failures.append(f"{m}: {type(exc).__name__}: {exc}")
    stage("imports_all_v71_modules", not import_failures,
          str(import_failures or f"{len(V71_MODULES)} modules"))

    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v71 import freshsample as FS
    from src.research.hypothesis_v71 import provenance as PV

    # ---- 4. the corpus builds ---------------------------------------------------------
    records = development = confirmatory = None
    try:
        records = CI.load_records(include_fresh=True)
        development, confirmatory = FS.partition(records)
        ok = bool(records) and bool(development) and bool(confirmatory)
    except Exception as exc:                                        # noqa: BLE001
        ok = False
        detail["corpus_error"] = f"{type(exc).__name__}: {exc}"
    stage("corpus_builds", ok,
          f"{len(records or [])} records = {len(development or [])} development "
          f"+ {len(confirmatory or [])} fresh")

    manifest_path = f"{OUT}/V7_1_FREEZE_MANIFEST.json"
    manifest = json.load(open(manifest_path))
    manifest_sha = PV.sha_file(manifest_path)

    # ---- 5. fresh CONTENT + historical PIT commitments verify -------------------------
    committed = json.load(open(f"{OUT}/V7_1_FRESH_CONTENT_COMMITMENT.json"))
    fresh_ok, fresh_problems, _l = PV.verify_content(
        committed["fresh_content"], confirmatory, CAP.METRIC_SEMANTICS)
    stage("fresh_content_verifies", fresh_ok,
          str(fresh_problems or committed["fresh_content"]["content_sha256"][:16]))
    pit_ok, pit_problems, _l2 = PV.verify_content(
        committed["historical_pit_snapshot"], development, CAP.METRIC_SEMANTICS)
    stage("historical_pit_content_verifies", pit_ok,
          str(pit_problems or committed["historical_pit_snapshot"]["content_sha256"][:16]))

    # ---- 6. the executable graph verifies (static mechanism, in-process) --------------
    # The RUNTIME mechanism is verified by the executor's own dry run in stage 7, which runs in
    # a SEPARATE process. It must: this driver deliberately imports every V7.1 module and the
    # development harness, so its own `sys.modules` contains modules the confirmatory path never
    # imports. Judging the runtime trace of this process would conflate the harness with the
    # apparatus; the executor's own process is the honest place to check what the run imports.
    prov = json.load(open(f"{OUT}/V7_1_PROVENANCE.json"))
    sg_ok, sg_problems, live_sg = PV.verify_source_graph(prov["source_graph"], root=ROOT)
    stage("executable_graph_verifies", sg_ok, str(sg_problems or
          f"{len(prov['source_graph']['source_file_hashes'])} files bound"))
    stage("no_untracked_executable_dependency",
          live_sg["counts"]["n_untracked"] == 0,
          str(live_sg["untracked_executable_dependencies"] or 0))
    stage("no_unresolved_first_party_import",
          live_sg["counts"]["n_unresolved_first_party"] == 0,
          str(live_sg["unresolved_first_party_imports"] or 0))

    # ---- 7. the executor itself: own process, full preflight, door stays shut ---------
    # Running the real driver as a subprocess is the faithful test: same interpreter, same
    # entry point, no harness modules in the process, and it verifies the source graph against
    # BOTH mechanisms including its own live runtime trace.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    dry = subprocess.run([sys.executable, f"{ENGINE_DIR}/_v71_execute.py"],
                         cwd=ROOT, capture_output=True, text=True, env=env)
    dry_doc = {}
    dry_path = f"{OUT}/V7_1_DRY_RUN.json"
    if os.path.exists(dry_path):
        dry_doc = json.load(open(dry_path))
    dchecks = dry_doc.get("preflight") or {}
    stage("executor_dry_run_exits_clean", dry.returncode == 0,
          f"rc={dry.returncode}" + (f" {dry.stderr.strip().splitlines()[-1:]}"
                                    if dry.returncode else ""))
    stage("preflight_ok", bool(dchecks.get("ok")), str(dchecks.get("problems") or "no problems"))
    stage("executable_graph_verifies_against_runtime_trace",
          bool(dchecks.get("source_graph_reverified")),
          f"{dchecks.get('source_graph_n_files')} bound / "
          f"{dchecks.get('runtime_first_party_modules')} imported live")
    stage("authorization_absent_and_run_refused",
          dry_doc.get("authorization", {}).get("authorized") is False
          and dry_doc.get("confirmatory_oos_computed") is False,
          "token absent -> the executor computes nothing")
    stage("no_cloud_modules_loaded", not dchecks.get("cloud_modules_loaded"),
          str(dchecks.get("cloud_modules_loaded") or "none"))
    stage("interpreter_matches_freeze", bool(dchecks.get("interpreter_matches_freeze")),
          str(dchecks.get("interpreter")))
    stage("champion_unchanged",
          dchecks.get("champion_sha256") == manifest["champion_sha256"],
          str(dchecks.get("champion_sha256", ""))[:16])
    stage("zero_overlap_reverified", bool(dchecks.get("zero_overlap_reverified")),
          str(dchecks.get("confirmatory_fixture_sha256", ""))[:16])
    detail["dry_run_plan"] = dry_doc.get("plan")

    # the plan must rebuild in-process too, so a failure is attributable
    plan = None
    try:
        ex = _load_script(f"{ENGINE_DIR}/_v71_execute.py", "_v71_execute_proof")
        checks, _m, fresh_manifest, (dev2, conf2) = ex.preflight()
        plan, _folds = ex.build_plan(fresh_manifest, dev2, conf2)
        plan_ok = bool(plan.treated) and bool(plan.controls)
    except Exception as exc:                                        # noqa: BLE001
        plan_ok = False
        detail["plan_error"] = f"{type(exc).__name__}: {exc}"
    stage("execution_plan_rebuilds", plan_ok,
          f"treated={len(plan.treated)} controls={len(plan.controls)} "
          f"uniform={len(plan.uniform)}" if plan_ok else str(detail.get("plan_error")))

    # ---- 8. the DEVELOPMENT_ONLY execution path runs end to end -----------------------
    dev_ok = False
    try:
        syn = _load_script(f"{ENGINE_DIR}/_v71_synthetic_execution.py", "_v71_synthetic_proof")
        dev_summary, _res, _work = syn.development_exercise()
        dev_ok = (dev_summary["confirmatory_oos_computed"] is False
                  and dev_summary["resume_is_deterministic_and_does_not_double_count"])
        detail["development_execution"] = {
            k: dev_summary.get(k) for k in
            ("n_treated_evaluable", "n_controls", "n_uniform_evaluable",
             "resume_is_deterministic_and_does_not_double_count", "seconds")}
    except Exception as exc:                                        # noqa: BLE001
        detail["development_error"] = f"{type(exc).__name__}: {exc}"
    stage("development_execution_path_runs", dev_ok,
          str(detail.get("development_execution") or detail.get("development_error")))

    # ---- 9. the V7.1 test suite passes from the clean commit --------------------------
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/research/hypothesis_v71/",
                        "-q", "-p", "no:cacheprovider", "--no-header"],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    tail = [ln for ln in r.stdout.strip().splitlines() if ln.strip()][-1:] or [""]
    stage("v71_test_suite_passes", r.returncode == 0, tail[0])
    detail["v71_test_suite"] = tail[0]

    # ---- proof ------------------------------------------------------------------------
    executable = not failures
    doc = {
        "classification": ["INPUT_ONLY", "NON_CONFIRMATORY"],
        "proof_version": "v71_clean_checkout_proof_v1",
        "clean_checkout_executable": executable,
        "verified_commit": head,
        "freeze_manifest_sha256": manifest_sha,
        "freeze_version": manifest["freeze_version"],
        "root_presented_at": ROOT,
        "git_status_porcelain_empty": stages["git_status_porcelain_empty"],
        "copied_executable_py_files": len(untracked_py) + len(ignored_py),
        "untracked_executable_py": untracked_py,
        "ignored_executable_py": ignored_py,
        "stages": stages,
        "failed_stages": failures,
        "detail": detail,
        "interpreter": {"executable": sys.executable,
                        "version": sys.version.split()[0],
                        "implementation": sys.implementation.name},
        "confirmatory_oos_computed": False,
        "confirmatory_oos_viewed": False,
        "authorization_token_minted": False,
        "seconds": round(time.time() - t0, 1),
        "why": ("v2 verified every hash it bound and still could not import the apparatus; a "
                "freeze is only ready when the COMMIT is proven to execute"),
    }
    path = f"{OUT}/{ARTIFACT}"
    json.dump(doc, open(path, "w"), indent=1, sort_keys=True)
    print(f"\nCLEAN_CHECKOUT_EXECUTABLE={executable}")
    if failures:
        print("FAILED STAGES:", failures)
    print(f"verified_commit={head}")
    print(f"freeze_manifest_sha256={manifest_sha}")
    print(f"wrote {path}")
    return 0 if executable else 1


if __name__ == "__main__":
    sys.exit(main())
