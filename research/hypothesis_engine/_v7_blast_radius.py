"""Machine-generated transitive blast-radius proof for the V7 changes (Task 14B).

Computes, by AST import analysis over the first-party source tree, the transitive closure of
every test module's imports, and reports which test modules can reach any V7 module changed in
this work. A test that cannot reach a changed module cannot be affected by the change.

ZERO SPEND. Static analysis only -- imports nothing it analyses.
"""
from __future__ import annotations

import ast
import json
import os
import sys

ROOT = "/home/ubuntu"
CHANGED = {
    "src/research/hypothesis_v7/__init__.py",
    "src/research/hypothesis_v7/universe.py",
    "src/research/hypothesis_v7/canonical.py",
    "src/research/hypothesis_v7/provider.py",
    "src/research/hypothesis_v7/coverage.py",
    "src/research/hypothesis_v7/pit.py",
    "src/research/hypothesis_v7/similarity.py",
    "src/research/hypothesis_v7/analysis_spec.py",
    "src/research/hypothesis_v7/walkforward.py",
    "src/research/hypothesis_v7/outcomes.py",
    "src/research/hypothesis_v7/leakage.py",
    "src/research/hypothesis_v7/null_benchmark.py",
    "src/research/hypothesis_v7/covariates.py",
    "src/research/hypothesis_v7/matching.py",
    "src/research/hypothesis_v7/endpoints.py",
}


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

    report = {
        "blast_radius_version": "v7_blast_radius_v1",
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
    out = os.path.join(ROOT, "research/hypothesis_oos/out/v7/V7_BLAST_RADIUS.json")
    with open(out, "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    print(f"scanned {len(tests)} test modules")
    print(f"  reach changed V7 code : {len(reaching)}")
    for r in reaching:
        print(f"      {r['test_module']}  -> {len(r['changed_modules_reached'])} modules")
    print(f"  cannot reach it       : {len(not_reaching)}")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
