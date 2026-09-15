"""Machine-generated transitive blast-radius proof for the V7.1 changes (section 23).

Computes, by AST import analysis over the first-party source tree, the transitive closure of
every test module's imports, and reports which test modules can reach any V7.1 module added or
changed in this work. A test that cannot reach a changed module cannot be affected by the change.

ZERO SPEND. Static analysis only -- imports nothing it analyses.
"""
from __future__ import annotations

import ast
import json
import os
import sys

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



def _module_to_path(mod: str):
    """Map a dotted first-party module name to a file under ROOT, if it exists."""
    rel = mod.replace(".", "/")
    for cand in (f"{rel}.py", f"{rel}/__init__.py"):
        if os.path.exists(os.path.join(ROOT, cand)):
            return cand
    return None


def imports_of(path: str):
    """First-party modules imported by `path` (absolute dotted names resolved under ROOT)."""
    out = set()
    try:
        tree = ast.parse(open(os.path.join(ROOT, path)).read())
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError):
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                out.add(node.module)
                for a in node.names:
                    out.add(f"{node.module}.{a.name}")
    return out


def closure(start: str, cache: dict):
    """Transitive first-party file closure reachable from `start`."""
    if start in cache:
        return cache[start]
    cache[start] = set()          # cycle guard
    seen = {start}
    stack = [start]
    while stack:
        cur = stack.pop()
        for mod in imports_of(cur):
            p = _module_to_path(mod)
            if p and p not in seen:
                seen.add(p)
                stack.append(p)
    cache[start] = seen
    return seen


def main() -> int:
    tests = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "tests")):
        for fn in files:
            if fn.startswith("test_") and fn.endswith(".py"):
                tests.append(os.path.relpath(os.path.join(dirpath, fn), ROOT))
    tests.sort()

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
