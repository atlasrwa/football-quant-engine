"""Machine-generated transitive blast-radius proof for the V7.1 changes (section 23).

Computes, by AST import analysis over the first-party source tree, the transitive closure of
every test module's imports, and reports which test modules can reach any V7.1 module added or
changed in this work. A test that cannot reach a changed module cannot be affected by the change.

ZERO SPEND. Static analysis only -- imports nothing it analyses.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/src")

from src.research.hypothesis_v71 import provenance as PV

ROOT = "/home/ubuntu"
# The declaration is DERIVED from disk, never hand-maintained.  A hand-written list is the
# defect class D14 found in V7's own blast-radius artifact: a module added after the list was
# written is silently excluded from the analysis, and the "no test reaches it" conclusion is
# then unproven for that module.  `test_15_blast_radius_declares_every_v71_module_on_disk`
# guards the class.
V71_PACKAGE = "src/research/hypothesis_v71"


def _declared_changed():
    d = os.path.join(ROOT, V71_PACKAGE)
    return {f"{V71_PACKAGE}/{f}" for f in sorted(os.listdir(d)) if f.endswith(".py")}


CHANGED = _declared_changed()


def imports_of(path: str):
    """First-party modules imported by `path`.

    Delegates to the provenance resolver rather than carrying a second copy of the analysis.
    This driver previously duplicated the walker AND its `node.level == 0` guard, so it shared
    the D16 blind spot: every `from . import x` was invisible, and the V7.1 package imports its
    interior that way. A reachability claim computed by a weaker mechanism than the real import
    graph understates blast radius, which is the same defect class D14 exists to prevent.
    """
    return PV._imported_names(path, ROOT)


def closure(start: str, cache: dict):
    """Transitive first-party file closure reachable from `start`.

    Uses the repaired resolver, so relative imports, ancestor packages, the `scripts/` import
    root and the corpus layer are all reachable -- one mechanism, one truth.
    """
    if start in cache:
        return cache[start]
    importers, _unresolved, _ambiguous = PV.static_closure([start], root=ROOT)
    cache[start] = set(importers)
    return cache[start]


def tracked_test_modules():
    """Every test module TRACKED at HEAD, sorted.

    Enumerated from git rather than from the working tree on purpose. Walking the filesystem
    counted untracked test files too (226 in a working tree against 219 in the commit), so the
    published artifact could not be reproduced from a clean checkout and went stale the moment a
    scratch test file appeared. Blast-radius evidence must describe the COMMIT.
    """
    tracked = PV.git_tracked_files(ROOT, "HEAD")
    if tracked is None:
        raise SystemExit("cannot determine git-tracked files; refusing to publish a "
                         "blast-radius claim that may not describe the commit")
    return sorted(p for p in tracked
                  if p.startswith("tests/") and os.path.basename(p).startswith("test_")
                  and p.endswith(".py"))


def main() -> int:
    tests = tracked_test_modules()

    cache = {}
    reaching, not_reaching = [], []
    for t in tests:
        reach = closure(t, cache)
        hit = sorted(reach & CHANGED)
        (reaching if hit else not_reaching).append(
            {"test_module": t, "changed_modules_reached": hit})

    # D14: V7's frozen blast-radius artifact omitted one V7 module from its changed set, so
    # its "no pre-existing test reaches changed code" claim was never checked for that module.
    # V7 is immutable and is NOT patched.  The claim is instead re-verified here, read-only.
    v7_declared = set(json.load(open(
        os.path.join(ROOT, "research/hypothesis_oos/out/v7/V7_BLAST_RADIUS.json")
    ))["changed_modules"])
    v7_dir = os.path.join(ROOT, "src/research/hypothesis_v7")
    v7_on_disk = {f"src/research/hypothesis_v7/{f}" for f in sorted(os.listdir(v7_dir))
                  if f.endswith(".py")}
    v7_undeclared = v7_on_disk - v7_declared
    v7_reaching = sorted(t for t in tests if closure(t, cache) & v7_undeclared)

    report = {
        "blast_radius_version": "v71_blast_radius_v2",
        "v7_undeclared_module_check": {
            "defect": "D14",
            "v7_modules_omitted_from_v7_blast_radius": sorted(v7_undeclared),
            "test_modules_reaching_them": v7_reaching,
            "v7_artifact_patched": False,
            "note": ("V7 is immutable, so its artifact is left exactly as frozen. This is an "
                     "independent read-only re-verification of the claim it failed to cover."),
        },
        "method": ("AST import analysis; transitive first-party closure per test module; a "
                   "test that cannot reach a changed module cannot be affected by the change"),
        "n_changed_modules": len(CHANGED),
        "changed_modules": sorted(CHANGED),
        "n_test_modules_scanned": len(tests),
        "n_test_modules_reaching_changed_code": len(reaching),
        "n_test_modules_not_reaching": len(not_reaching),
        "test_modules_reaching_changed_code": reaching,
        "test_modules_not_reaching": [r["test_module"] for r in not_reaching],
    }
    out = os.path.join(ROOT, "research/hypothesis_oos/out/v7_1/V7_1_BLAST_RADIUS.json")
    with open(out, "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    print(f"scanned {len(tests)} test modules")
    print(f"  reach changed V7.1 code : {len(reaching)}")
    for r in reaching:
        print(f"      {r['test_module']}  -> {len(r['changed_modules_reached'])} modules")
    print(f"  cannot reach it       : {len(not_reaching)}")
    print(f"  V7 modules undeclared in V7's own artifact : {sorted(v7_undeclared)}")
    print(f"      test modules reaching them            : {v7_reaching or 'none'}")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
