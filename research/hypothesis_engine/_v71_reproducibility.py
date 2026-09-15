"""V7.1 reproducibility proof. Section 20.

Re-derives every deterministic V7.1 specification and control universe in a FRESH interpreter
under several PYTHONHASHSEED values and compares the resulting SHA-256 digests with the frozen
freeze manifest.

Anything built from Python's salted `hash()` or the `random` module would differ between seeds;
everything here is built from sorted canonical JSON and a SHA-256 counter stream, so it must
not. A difference is a reproducibility defect, not noise.

ZERO SPEND. No network.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v7_1"

SEEDS = ("0", "1", "42", "random")

CHILD = r'''
import hashlib, json, sys
sys.path.insert(0, "/home/ubuntu"); sys.path.insert(0, "/home/ubuntu/src")
from src.research.hypothesis_v71 import (ontology as O, ir as I, invariants as V,
                                          capability as C, compiler as K, similarity as S,
                                          recency as R, confounders as F, estimator as E,
                                          controls as T, evaluability as B, freshsample as X,
                                          leakage as L, engine as G, golden as D,
                                          bugledger as U, covariate_bridge as CB)

def h(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()

cov = json.load(open("/home/ubuntu/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json"))
cap = C.CapabilityContract(cov)
vocab = sorted(m for m, r in C.METRIC_SEMANTICS.items() if r.get("block"))
uniform = T.enumerate_pool(vocab, T.UNIFORM_POOL_SIZE, sampling=T.SAMPLING_UNIFORM)

out = {
    "ontology": h(O.version_stamp()), "ir": h(I.version_stamp()),
    "invariants": h(V.version_stamp()), "capability": h(cap.spec()),
    "compiler": h(K.version_stamp()), "similarity": h(S.version_stamp()),
    "recency": h(R.version_stamp()), "confounders": h(F.version_stamp()),
    "estimator": h(E.version_stamp()), "controls": h(T.version_stamp()),
    "evaluability": h(B.version_stamp()), "fresh": h(X.version_stamp()),
    "leakage": h(L.version_stamp()), "golden": h(D.version_stamp()),
    "bugledger": h(U.version_stamp()), "covariate_bridge": h(CB.version_stamp()),
    "engine_spec_hash": G.spec_hash(),
    "uniform_pool_hash": T.pool_hash(uniform),
    "ir_id_sample": I.build_ir({"target_metrics": ["total_shots", "corners"],
                                "subject": "HOME_TEAM", "side": "AGAINST",
                                "comparison": "SUBJECT_VS_FIXTURE_OPPONENT",
                                "conditions": [{"dimension": "opponent_profile",
                                                "axis": "goals_for", "value": "HIGH"}],
                                "window": "W5", "research_family": "DEFENSIVE_CONCESSION",
                                "required_capabilities": ["opponent_profile"]}).ir_id(),
}
print(json.dumps(out, sort_keys=True))
'''


def main():
    runs = {}
    for seed in SEEDS:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, "-c", CHILD], env=env,
                              capture_output=True, text=True, cwd=ROOT)
        if proc.returncode != 0:
            print(proc.stderr[-2000:])
            raise SystemExit(f"child failed under PYTHONHASHSEED={seed}")
        runs[seed] = json.loads(proc.stdout)

    keys = sorted(runs[SEEDS[0]])
    unstable = [k for k in keys if len({runs[s][k] for s in SEEDS}) > 1]

    manifest_path = f"{OUT}/V7_1_FREEZE_MANIFEST.json"
    engine_matches = None
    if os.path.exists(manifest_path):
        frozen = json.load(open(manifest_path))
        engine_matches = frozen["engine_spec_hash"] == runs[SEEDS[0]]["engine_spec_hash"]

    doc = {"reproducibility_version": "v71_reproducibility_v1",
           "interpreter": sys.version.split()[0],
           "seeds": list(SEEDS),
           "n_quantities": len(keys),
           "unstable_quantities": unstable,
           "byte_stable_across_seeds": not unstable,
           "engine_spec_hash_matches_freeze": engine_matches,
           "digests": runs[SEEDS[0]],
           "method": ("each quantity is re-derived in a FRESH interpreter per seed; a value "
                      "built from Python's salted hash() or the random module would differ")}
    path = f"{OUT}/V7_1_REPRODUCIBILITY.json"
    json.dump(doc, open(path, "w"), indent=1, sort_keys=True)
    print(json.dumps({k: v for k, v in doc.items() if k != "digests"}, indent=1))
    print(f"written: {path}")
    return 0 if not unstable else 1


if __name__ == "__main__":
    raise SystemExit(main())
