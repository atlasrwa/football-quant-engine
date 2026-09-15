"""V7.1 RUNTIME first-party import trace (mission item 6B). Second provenance mechanism.

Static analysis is one opinion about what the confirmatory run executes. This driver produces an
INDEPENDENT one: it actually runs the development execution path in-process and records every
repository-owned Python module that ended up in `sys.modules`. Whatever was really imported
cannot be missed, so dynamic imports, `sys.path` mutation, unusual import styles and resolver
blind spots are all covered even when the AST walk would not see them.

Why this exists: the `v71_provenance_v1` static closure had TWO independent blind spots, both
instances of one defect class (a mechanism narrower than the real dependency graph) --

  * a hard-coded experiment-name path allowlist, which excluded the corpus layer
    (`src/research/matchup/corpus.py`, and through it `scripts/multisrc_corpus.py` and
    `scripts/championship_adapter.py`); and
  * `node.level == 0`, which silently dropped every `from . import X`, so the estimator,
    matching, compiler, confounders, invariants, ontology, recency and similarity modules --
    the scientific core -- were never bound either.

The freeze binds the UNION of this trace and the static closure, so neither mechanism is
load-bearing alone.

WHAT IS RUN: `_v71_synthetic_execution.development_exercise()` -- the real
`execution.run_experiment` over the historical, already-viewed walk-forward folds, built from
`corpus_index.load_records(include_fresh=False)`. The fresh confirmatory sample is NEVER opened
and no fresh outcome is computed, read or written.

ZERO SPEND. No Bedrock. No CHAMPION write. CONFIRMATORY_OOS_COMPUTED stays false.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/src")

from src.research.hypothesis_v71 import provenance as PV

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v7_1"
ENGINE_DIR = f"{ROOT}/research/hypothesis_engine"

TRACE_ARTIFACT = "V7_1_RUNTIME_IMPORT_TRACE.json"

#: The entry points whose real import behaviour is traced.
TRACED_ENTRY_POINTS = ("research/hypothesis_engine/_v71_execute.py",
                       "src/research/hypothesis_v71/execution.py")

#: Modules that exist ONLY because tracing is happening: this driver, and the development
#: harness it drives. Neither is on the confirmatory execution path -- the confirmatory entry
#: point does not import them -- so binding them into the executable graph would make an edit to
#: a development harness refuse an unrelated confirmatory run. They are excluded by NAME and the
#: exclusion is recorded in the artifact, so nothing is hidden. `_v71_execute.py` itself is a
#: real entry point and stays bound via the static closure.
TRACE_HARNESS_MODULES = ("__main__", "_v71_execute_traced", "_v71_synthetic_traced")


def _load_script(path, name):
    """Import a driver script by file path (they are scripts, not package modules).

    Only module-level code runs: every driver guards its work behind `__main__`, so importing
    the confirmatory executor records its import graph without executing a single check.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    t0 = time.time()

    # 1. the confirmatory executor's own import graph (module level only -- no preflight, no run)
    _load_script(f"{ENGINE_DIR}/_v71_execute.py", "_v71_execute_traced")

    # 2. the development execution path: the SAME machinery the authorized run calls, over
    #    historical folds only. This is what forces the corpus layer to be imported for real.
    syn = _load_script(f"{ENGINE_DIR}/_v71_synthetic_execution.py", "_v71_synthetic_traced")
    dev, _dev_result, _work = syn.development_exercise()

    # 3. snapshot every repository-owned module that actually got imported
    runtime = PV.runtime_first_party_files(root=ROOT,
                                           exclude_modules=TRACE_HARNESS_MODULES)

    static_only = PV.source_graph_commitment(list(TRACED_ENTRY_POINTS), root=ROOT)
    static_files = set(static_only["source_file_hashes"])
    runtime_not_static = sorted(set(runtime) - static_files)

    doc = {
        "classification": ["DEVELOPMENT_ONLY", "NON_CONFIRMATORY", "INPUT_ONLY"],
        "provenance_version": PV.PROVENANCE_VERSION,
        "trace_mechanism": "sys.modules snapshot after running the development execution path",
        "traced_entry_points": sorted(TRACED_ENTRY_POINTS),
        "trace_harness_modules_excluded": sorted(TRACE_HARNESS_MODULES),
        "exercised": "_v71_synthetic_execution.development_exercise()",
        "fresh_sample_opened": False,
        "confirmatory_oos_computed": False,
        "confirmatory_oos_viewed": False,
        "n_runtime_first_party_modules": len(runtime),
        "runtime_first_party_modules": runtime,
        "runtime_file_hashes": {f: PV.sha_file(os.path.join(ROOT, f))
                                for f in sorted(runtime)},
        "runtime_modules_absent_from_static_closure": runtime_not_static,
        "n_runtime_only": len(runtime_not_static),
        "development_exercise_summary": {
            k: dev.get(k) for k in
            ("n_treated_evaluable", "n_controls", "n_uniform_evaluable",
             "resume_is_deterministic_and_does_not_double_count")
        },
        # NOTE: no wall-clock field. This artifact is HASHED INTO THE FREEZE MANIFEST, so a
        # timing value would make a bound artifact differ on every run and refuse preflight
        # although nothing scientific changed. Duration goes to stdout only.
    }
    path = f"{OUT}/{TRACE_ARTIFACT}"
    json.dump(doc, open(path, "w"), indent=1, sort_keys=True)

    print("=== V7.1 RUNTIME IMPORT TRACE ===")
    print(f"  repository-owned modules imported : {len(runtime)}")
    print(f"  static closure                    : {len(static_files)}")
    print(f"  runtime-only (static blind spots)  : {len(runtime_not_static)}")
    for f in runtime_not_static:
        print(f"     ! {f}  (module {runtime[f]})")
    print(f"  fresh sample opened               : False")
    print(f"  elapsed                           : {round(time.time() - t0, 1)}s "
          f"(not recorded in the frozen artifact)")
    print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
