"""V7.1 execution provenance & integrity (`v71_provenance_v1`). Sections 21-23 (closure).

Everything that must be TRUE the moment the confirmatory path runs, recomputed from disk at
preflight rather than trusted from a stale summary. Four independent commitments:

  1. SOURCE GRAPH   -- the actual code that will execute. The UNION of the transitive
                       repository-owned import closure (static, AST) and the runtime
                       `sys.modules` trace of the development execution path is hashed. A source
                       change after freeze causes execution refusal even if no version constant
                       was bumped, and executed code that is untracked or unresolvable makes the
                       freeze refuse outright. (section 22 / mission items 5-6)
  2. UPSTREAM V7    -- every V7 artifact V7.1 actually consumes, recomputed and compared with
                       the immutable proof. A proof file that is itself unchanged while a file
                       it references has changed must NOT pass. (mission item 6)
  3. FRESH CONTENT  -- the fresh confirmatory corpus, bound at CONTENT level, not just fixture
                       ids: every provider field the engine may consume, the exact null
                       representation, and a normalized-record hash. (mission item 7)
  4. HISTORICAL PIT -- a deterministic content snapshot of the development corpus used to build
                       point-in-time profiles, so it cannot silently mutate between freeze and
                       execution. (mission item 7)

An AUTHORIZATION token binds 1-4 together with the freeze manifest, so the one-way door
requires BOTH the explicit flag AND an artifact whose expected hashes match the live ones.

ZERO SPEND. Static analysis + file hashing + record normalization only. Reads NO outcome:
every field bound here is an INPUT, never an effect, correlation, p-value or terminal state.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import sysconfig

PROVENANCE_VERSION = "v71_provenance_v2"

ROOT = "/home/ubuntu"

#: Repository-local import roots, in resolution precedence order.
#:
#: These are the directories that are ACTUALLY on `sys.path` when the confirmatory path runs:
#: the driver inserts `<root>/src` then `<root>`, and `src/research/matchup/corpus.py` inserts
#: `<root>/scripts` when it is imported (see `SYS_PATH_MUTATIONS`). A module is first-party iff
#: it resolves to a repository-owned file under one of these roots.
#:
#: This replaces the `v71_provenance_v1` rule, which decided relevance by EXPERIMENT-NAME path
#: prefix (`src/research/hypothesis_v7*`, `research/hypothesis_engine`). That allowlist was
#: narrower than the real Python dependency graph, so the corpus layer the whole experiment
#: reads its data through escaped the freeze entirely (defect D16). Experiment naming must
#: never decide whether executed code is bound: only reachability may.
FIRST_PARTY_IMPORT_ROOTS = ("src", "", "scripts")

#: Load-bearing `sys.path` mutations performed by apparatus modules at import time. Recorded so
#: the resulting import root is explicit rather than incidental, and so a clean checkout can be
#: proven to reproduce it. `corpus.py` inserts the repository's `scripts/` directory, which is
#: how `multisrc_corpus` / `championship_adapter` become importable at all.
SYS_PATH_MUTATIONS = (
    {"module": "src/research/matchup/corpus.py",
     "inserts": "scripts",
     "absolute_in_source": "/home/ubuntu/scripts",
     "why": "makes the tracked provider adapters (multisrc_corpus, championship_adapter) "
            "importable; they are the corpus's provider layer",
     "bound_by_source_graph": True},
)

#: Path fragments that mark a file as environment/third-party rather than repository-owned,
#: even when it lives physically under the repository root (the venv does).
_ENVIRONMENT_MARKERS = (".venv/", "site-packages/", "dist-packages/", "node_modules/",
                        "__pycache__/")


# ======================================================================================
# generic hashing
# ======================================================================================
def sha_file(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def sha_obj(o) -> str:
    return hashlib.sha256(
        json.dumps(o, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


# ======================================================================================
# 1. source graph -- the code that actually executes
# ======================================================================================
def _is_environment_path(rel: str) -> bool:
    r = rel.replace(os.sep, "/")
    return any(m in ("/" + r) for m in _ENVIRONMENT_MARKERS) or r.startswith(".venv/")


def _resolve_first_party(mod: str, root: str, import_roots) -> list:
    """Every repository-owned file `mod` could resolve to, in import-root precedence order.

    Both the module form (`a/b.py`) and the package form (`a/b/__init__.py`) are considered, so
    a package and a same-named module are both discovered and the ambiguity is reportable.
    """
    rel = mod.replace(".", "/")
    found = []
    for r in import_roots:
        base = f"{r}/{rel}" if r else rel
        for cand in (f"{base}/__init__.py", f"{base}.py"):
            ap = os.path.join(root, cand)
            if os.path.isfile(ap) and not _is_environment_path(cand):
                if cand not in found:
                    found.append(cand)
    return found


def _installed_third_party(top: str) -> bool:
    """Whether a top-level name is an installed distribution (stdlib excluded)."""
    dirs = set()
    for key in ("purelib", "platlib"):
        d = sysconfig.get_paths().get(key)
        if d:
            dirs.add(d)
    for p in sys.path:
        if p and ("site-packages" in p or "dist-packages" in p):
            dirs.add(p)
    for d in dirs:
        if not os.path.isdir(d):
            continue
        if os.path.isdir(os.path.join(d, top)):
            return True
        try:
            for name in os.listdir(d):
                if name == top or name.startswith(top + "."):
                    return True
        except OSError:
            pass
    return False


def classify_import(mod: str, *, root: str = ROOT, import_roots=FIRST_PARTY_IMPORT_ROOTS):
    """Classify one imported name. Fails CLOSED: anything unrecognised is `unresolved`.

    Kinds:
      `first_party`        -- resolves to a repository-owned module file (bound, hashed);
      `first_party_symbol` -- a NAME imported from a repository-owned module (`from m import X`);
                              the module itself is bound separately, the symbol is not a file;
      `stdlib` / `third_party` -- not repository-owned, deliberately not bound;
      `unresolved`         -- cannot be placed. The freeze must refuse rather than guess.
    """
    paths = _resolve_first_party(mod, root, import_roots)
    if paths:
        return {"kind": "first_party", "path": paths[0], "also_resolves": paths[1:]}
    if "." in mod and _resolve_first_party(mod.rsplit(".", 1)[0], root, import_roots):
        return {"kind": "first_party_symbol", "path": None, "also_resolves": []}
    top = mod.split(".")[0]
    if top in getattr(sys, "stdlib_module_names", frozenset()) or top in sys.builtin_module_names:
        return {"kind": "stdlib", "path": None, "also_resolves": []}
    if _installed_third_party(top):
        return {"kind": "third_party", "path": None, "also_resolves": []}
    return {"kind": "unresolved", "path": None, "also_resolves": []}


def _imported_names(path: str, root: str):
    """Every module name imported by one file, including function-local and relative imports.

    Relative imports are resolved against the importing file's own package so that `from . import
    x` cannot hide a dependency.
    """
    try:
        tree = ast.parse(open(os.path.join(root, path)).read())
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return set()
    pkg = os.path.dirname(path).replace(os.sep, "/").replace("/", ".")
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    out.add(node.module)
                    for a in node.names:
                        out.add(f"{node.module}.{a.name}")
            else:
                # relative: climb `level-1` packages from this file's own package
                parts = [p for p in pkg.split(".") if p]
                base = ".".join(parts[:len(parts) - (node.level - 1)]) if node.level > 1 else pkg
                stem = f"{base}.{node.module}" if node.module else base
                if stem:
                    out.add(stem)
                    for a in node.names:
                        out.add(f"{stem}.{a.name}")
    return out


#: kept as the v1 name for callers that only want the raw import names of one file
_first_party_imports = _imported_names


def _ancestor_packages(mod: str, root: str, import_roots) -> list:
    """The `__init__.py` of every ancestor package of `mod` that exists in the repository.

    Python EXECUTES these on the way to the leaf module, so their bytes are part of what runs.
    Resolving only the leaf (as `v71_provenance_v1` did) leaves them unbound; the runtime trace
    caught `src/__init__.py` and `src/research/__init__.py` escaping exactly this way.
    """
    parts = mod.split(".")
    out = []
    for i in range(1, len(parts)):
        for cand in _resolve_first_party(".".join(parts[:i]), root, import_roots):
            if cand.endswith("/__init__.py") and cand not in out:
                out.append(cand)
    return out


def static_closure(entry_paths, *, root: str = ROOT, import_roots=FIRST_PARTY_IMPORT_ROOTS):
    """The transitive repository-owned file closure reachable from `entry_paths`.

    Returns `(importers, unresolved, ambiguous)` where `importers` maps each file on the closure
    to the set of files that import it. Reachability is the ONLY criterion: if the execution
    path can import a repository-owned module, that module is on the graph. Ancestor package
    `__init__.py` files are included because importing `a.b.c` executes `a` and `a.b` too.
    """
    importers = {p: set() for p in entry_paths}
    stack = list(entry_paths)
    unresolved, ambiguous = [], []
    while stack:
        cur = stack.pop()
        for mod in sorted(_imported_names(cur, root)):
            c = classify_import(mod, root=root, import_roots=import_roots)
            if c["kind"] in ("first_party", "first_party_symbol"):
                targets = _ancestor_packages(mod, root, import_roots)
                if c["kind"] == "first_party":
                    if c["also_resolves"]:
                        ambiguous.append({"module": mod, "chosen": c["path"],
                                          "also_resolves": c["also_resolves"],
                                          "imported_by": cur})
                    targets = targets + [c["path"]]
                for p in targets:
                    if p not in importers:
                        importers[p] = set()
                        stack.append(p)
                    if p not in entry_paths:
                        importers[p].add(cur)
            elif c["kind"] == "unresolved":
                unresolved.append({"module": mod, "imported_by": cur})
    return importers, unresolved, ambiguous


def source_closure(entry_paths, *, root: str = ROOT, import_roots=FIRST_PARTY_IMPORT_ROOTS):
    """Backwards-compatible view: just the sorted file list of the static closure."""
    importers, _u, _a = static_closure(entry_paths, root=root, import_roots=import_roots)
    return sorted(importers)


# ---- runtime mechanism ---------------------------------------------------------------
def runtime_first_party_files(*, root: str = ROOT, modules=None, exclude_modules=()) -> dict:
    """Repository-owned Python files currently present in `sys.modules`.

    The second, INDEPENDENT provenance mechanism. Static analysis can miss a dependency that a
    dynamic import, an `importlib` call, an unusual import style or a `sys.path` mutation
    introduces; whatever actually got imported cannot be missed. Environment code (the venv,
    site-packages) is excluded: it is third-party, pinned by the interpreter/dependency pins.

    `exclude_modules` drops named modules that exist ONLY because tracing is happening -- the
    tracer itself and the development harness it drives. They are not on the confirmatory path,
    so binding them would make an unrelated harness edit refuse a confirmatory run. The caller
    must declare them explicitly, and the trace artifact records the exclusion.
    """
    mods = sys.modules if modules is None else modules
    excluded = set(exclude_modules)
    rroot = os.path.realpath(root)
    out = {}
    for name, m in sorted((k, v) for k, v in list(mods.items()) if v is not None):
        if name in excluded:
            continue
        f = getattr(m, "__file__", None)
        if not f or not str(f).endswith(".py"):
            continue
        rf = os.path.realpath(f)
        if not rf.startswith(rroot + os.sep):
            continue
        rel = os.path.relpath(rf, rroot)
        if _is_environment_path(rel):
            continue
        out.setdefault(rel, name)
    return dict(sorted(out.items()))


def git_tracked_files(root: str = ROOT, ref: str = "HEAD"):
    """The set of paths tracked at `ref`, or None if git tracking cannot be determined."""
    try:
        r = subprocess.run(["git", "-C", root, "ls-tree", "-r", "--name-only", ref],
                           capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return set(r.stdout.splitlines())


def source_graph_commitment(entry_paths, *, root: str = ROOT, runtime_files=None,
                            git_ref: str = "HEAD",
                            import_roots=FIRST_PARTY_IMPORT_ROOTS) -> dict:
    """Hash the UNION of the static import closure and the runtime import trace.

    Two independent mechanisms, conservatively unioned (item 6): the static closure catches code
    that is reachable but was not exercised, the runtime trace catches code that was executed but
    is not statically discoverable. Binding the union means neither blind spot is load-bearing.

    Fails CLOSED on the two conditions that made the v1 graph unsound:
      * `UNTRACKED_EXECUTABLE_DEPENDENCY` -- executed code that is not in the git commit, so a
        clean checkout would not contain it (defect D16);
      * `UNRESOLVED_FIRST_PARTY_IMPORT` -- an import that cannot be placed as repository-owned,
        stdlib or installed third-party, so its provenance is unknown.
    """
    importers, unresolved, ambiguous = static_closure(entry_paths, root=root,
                                                      import_roots=import_roots)
    static_files = sorted(importers)
    runtime_files = dict(runtime_files or {})
    union = sorted(set(static_files) | set(runtime_files))

    tracked = git_tracked_files(root, git_ref)
    per_file, records, untracked, missing = {}, {}, [], []
    for f in union:
        ap = os.path.join(root, f)
        if not os.path.isfile(ap):
            missing.append(f)
            continue
        h = sha_file(ap)
        per_file[f] = h
        in_static, in_runtime = f in importers, f in runtime_files
        is_tracked = None if tracked is None else (f in tracked)
        if is_tracked is False:
            untracked.append(f)
        records[f] = {
            "sha256": h,
            "git_tracked": is_tracked,
            "resolution": ("both" if in_static and in_runtime
                           else "static" if in_static else "runtime"),
            "imported_by": sorted(importers.get(f, ())) or None,
            "runtime_module": runtime_files.get(f),
        }

    problems = []
    if tracked is None:
        problems.append("git tracking could not be determined; refusing to certify the "
                        "executable graph")
    for f in sorted(untracked):
        problems.append(f"UNTRACKED_EXECUTABLE_DEPENDENCY: {f}")
    for u in unresolved:
        problems.append(f"UNRESOLVED_FIRST_PARTY_IMPORT: {u['module']} "
                        f"(imported by {u['imported_by']})")
    for f in sorted(missing):
        problems.append(f"executable dependency absent from disk: {f}")
    for a in ambiguous:
        problems.append(f"AMBIGUOUS_FIRST_PARTY_RESOLUTION: {a['module']} -> {a['chosen']} "
                        f"but also {a['also_resolves']}")

    return {
        "provenance_version": PROVENANCE_VERSION,
        "entry_points": sorted(entry_paths),
        "import_roots": list(import_roots),
        "sys_path_mutations": [dict(m) for m in SYS_PATH_MUTATIONS],
        "git_ref": git_ref,
        "n_source_files": len(per_file),
        "source_file_hashes": per_file,
        "source_graph_sha256": sha_obj(per_file),
        "file_records": records,
        "static_files": static_files,
        "runtime_files": sorted(runtime_files),
        "runtime_only_files": sorted(set(runtime_files) - set(importers)),
        "static_only_files": sorted(set(importers) - set(runtime_files)),
        "counts": {
            "n_static": len(static_files),
            "n_runtime": len(runtime_files),
            "n_union": len(per_file),
            "n_untracked": len(untracked),
            "n_unresolved_first_party": len(unresolved),
            "n_ambiguous": len(ambiguous),
        },
        "untracked_executable_dependencies": sorted(untracked),
        "unresolved_first_party_imports": unresolved,
        "ambiguous_resolutions": ambiguous,
        "derivation": ("union of (a) AST transitive repository-owned import closure resolved "
                       "against the declared import roots and (b) the runtime sys.modules "
                       "trace of the development execution path"),
        "relevance_rule": ("reachability only -- experiment-name path prefixes are NEVER used "
                           "to decide whether executed code is bound"),
        "binds_version_constants_only": False,
        "reads_outcomes": False,
        "problems": problems,
        "ok": not problems,
    }


def verify_source_graph(frozen: dict, *, root: str = ROOT, runtime_files=None):
    """Recompute the executable graph and compare with a frozen commitment.

    A changed file, a new file on the closure, a removed file, an untracked dependency or an
    unresolvable first-party import all fail -- even when no version string moved. Frozen files
    are hashed DIRECTLY, so a runtime-only dependency stays verifiable when the caller supplies
    no live trace.
    """
    live = source_graph_commitment(frozen["entry_points"], root=root,
                                   runtime_files=runtime_files,
                                   import_roots=frozen.get("import_roots",
                                                           FIRST_PARTY_IMPORT_ROOTS))
    problems = []
    fh = frozen["source_file_hashes"]
    for f, h in sorted(fh.items()):
        ap = os.path.join(root, f)
        if not os.path.isfile(ap):
            problems.append(f"source file removed since freeze: {f}")
        elif sha_file(ap) != h:
            problems.append(f"source file changed since freeze: {f}")
    for f in sorted(set(live["source_file_hashes"]) - set(fh)):
        problems.append(f"source file added to the executable closure since freeze: {f}")
    problems += [p for p in live["problems"]
                 if p.startswith(("UNTRACKED_EXECUTABLE_DEPENDENCY",
                                  "UNRESOLVED_FIRST_PARTY_IMPORT",
                                  "AMBIGUOUS_FIRST_PARTY_RESOLUTION"))]
    if (not problems and set(live["source_file_hashes"]) == set(fh)
            and live["source_graph_sha256"] != frozen["source_graph_sha256"]):
        problems.append("source graph roll-up hash differs")
    return (not problems, problems, live)


# ======================================================================================
# 2. upstream V7 inputs -- recomputed, not trusted
# ======================================================================================
def upstream_v7_commitment(consumed_paths, *, root: str = ROOT) -> dict:
    """Content hashes of every V7 (and other upstream) artifact V7.1 actually consumes.

    Bound INDEPENDENTLY of V7's own preregistration hashes: verifying the immutability proof
    file is unchanged is not enough, because the proof is a summary that could remain identical
    while a file it lists changed on disk. Here we hash the referenced files themselves.
    """
    per_file = {}
    for p in sorted(set(consumed_paths)):
        ap = os.path.join(root, p)
        per_file[p] = sha_file(ap) if os.path.exists(ap) else None
    return {
        "provenance_version": PROVENANCE_VERSION,
        "n_upstream_inputs": len(per_file),
        "upstream_input_hashes": per_file,
        "upstream_sha256": sha_obj(per_file),
        "note": ("recomputed from the referenced files, so a proof file that is itself "
                 "unchanged cannot mask a changed input it references"),
        "reads_outcomes": False,
    }


def verify_upstream_v7(frozen: dict, *, root: str = ROOT):
    live = upstream_v7_commitment(list(frozen["upstream_input_hashes"]), root=root)
    problems = []
    for f, h in sorted(frozen["upstream_input_hashes"].items()):
        if live["upstream_input_hashes"].get(f) != h:
            problems.append(f"upstream input changed since freeze: {f}")
    return (not problems, problems, live)


# ======================================================================================
# 3 + 4. fresh content commitment & historical PIT snapshot
# ======================================================================================
#: The provider fields the V7.1 engine may consume from a normalized record. Bound at content
#: level so the SAME 317 fixture ids containing DIFFERENT values is refused. This list is the
#: union of what the metric contract can read plus the structural identity fields.
def _record_content(rec, metric_contract) -> dict:
    """A deterministic, effect-free content view of one record: identity + every consumable
    field + the exact null representation (None stays None; it is never coerced)."""
    def _readable(metric):
        row = metric_contract.get(metric)
        if not row or not row.get("block"):
            return None
        blk, fld = row["block"], row["field"]
        if blk == "base":
            b = rec.base or {}
            return [b.get(fld), b.get(row.get("field_away"))]
        pair = (getattr(rec, blk, None) or {}).get(fld)
        return list(pair) if pair else None

    fields = {m: _readable(m) for m in sorted(metric_contract)}
    return {
        "fixture_id": str(rec.fixture_id),
        "season_id": str(rec.season_id),
        "competition": rec.competition,
        "competition_id": str(getattr(rec, "competition_id", "") or ""),
        "kickoff_unix": int(rec.kickoff_unix),
        "home_id": str(rec.home_id),
        "away_id": str(rec.away_id),
        "consumable_fields": fields,
    }


def content_commitment(records, metric_contract) -> dict:
    """A deterministic content commitment over a set of records.

    Binds each record's identity, kickoff, teams, and every provider field the engine can
    consume (with nulls preserved as null). Returns per-fixture normalized-record hashes and a
    single roll-up hash. Computes NOTHING derived: no mean, correlation, effect or terminal
    state is read.
    """
    per_fixture = {}
    for rec in records:
        content = _record_content(rec, metric_contract)
        per_fixture[str(rec.fixture_id)] = sha_obj(content)
    return {
        "provenance_version": PROVENANCE_VERSION,
        "n_records": len(per_fixture),
        "normalized_record_hashes": dict(sorted(per_fixture.items())),
        "content_sha256": sha_obj(per_fixture),
        "binds": ["fixture_id", "season_id", "competition", "competition_id",
                  "kickoff_unix", "home_id", "away_id", "every_consumable_provider_field",
                  "exact_null_representation"],
        "level": "NORMALIZED_RECORD_CONTENT",
        "reads_outcomes": False,
    }


def verify_content(frozen: dict, records, metric_contract):
    """Recompute the content commitment and compare. Same ids + different values must fail."""
    live = content_commitment(records, metric_contract)
    problems = []
    fh = frozen["normalized_record_hashes"]
    lh = live["normalized_record_hashes"]
    if set(fh) != set(lh):
        missing = sorted(set(fh) - set(lh))
        extra = sorted(set(lh) - set(fh))
        if missing:
            problems.append(f"{len(missing)} committed fixtures absent at execution")
        if extra:
            problems.append(f"{len(extra)} unexpected fixtures present at execution")
    changed = [f for f in sorted(set(fh) & set(lh)) if fh[f] != lh[f]]
    if changed:
        problems.append(f"{len(changed)} fixtures now contain different content")
    if live["content_sha256"] != frozen["content_sha256"] and not problems:
        problems.append("content roll-up hash differs")
    return (not problems, problems, live)


def version_stamp() -> dict:
    return {"provenance_version": PROVENANCE_VERSION,
            "commitments": ["source_graph", "upstream_v7", "fresh_content",
                            "historical_pit_snapshot"],
            "source_change_after_freeze_refuses_even_without_version_bump": True,
            "upstream_recomputed_not_trusted_from_proof": True,
            "fresh_bound_at_content_level_not_only_fixture_ids": True,
            "executable_graph": {
                "mechanisms": ["static_import_closure", "runtime_sys_modules_trace"],
                "binds": "UNION",
                "import_roots": list(FIRST_PARTY_IMPORT_ROOTS),
                "relevance_rule": "reachability_only_never_experiment_name_prefix",
                "fails_closed_on": ["UNTRACKED_EXECUTABLE_DEPENDENCY",
                                    "UNRESOLVED_FIRST_PARTY_IMPORT",
                                    "AMBIGUOUS_FIRST_PARTY_RESOLUTION"],
                "requires_clean_checkout_executability": True,
                "supersedes": {
                    "version": "v71_provenance_v1",
                    "defect": "D16",
                    "reason": ("the closure was gated by a hard-coded experiment-name path "
                               "allowlist (src/research/hypothesis_v7*, "
                               "research/hypothesis_engine) narrower than the real Python "
                               "dependency graph, so the corpus layer every measurement reads "
                               "through was never bound and two of its files were not even "
                               "committed")}},
            "reads_outcomes": False}
