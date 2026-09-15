"""D16 regression battery: the executable dependency graph must equal the REAL import graph.

The v1 mechanism claimed to derive the executable closure mechanically but decided relevance
with a hard-coded experiment-name path allowlist and ignored relative imports, so it bound 17 of
the 35 files that actually execute -- omitting the corpus layer, the estimator, the matching and
the confounders -- while still reporting itself verified. Two of the omitted files were not even
committed, so a clean checkout of the frozen commit could not import the apparatus.

Every test here attacks the CLASS, not the instance: a dependency may not escape the freeze by
living outside an experiment-named directory, by being imported relatively, by being an ancestor
package, by being reached only at runtime, or by being untracked. Code integrity and data
integrity are independent commitments: identical data must not excuse changed code.

Nothing here reads a confirmatory outcome.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile

import pytest

from src.research.hypothesis_v71 import provenance as PV

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v7_1"
ENTRY = ("research/hypothesis_engine/_v71_execute.py",
         "src/research/hypothesis_v71/execution.py")

#: the four files the v1 prefix allowlist excluded outright
CORPUS_LAYER = ("src/research/matchup/__init__.py",
                "src/research/matchup/corpus.py",
                "scripts/multisrc_corpus.py",
                "scripts/championship_adapter.py")

#: files the v1 mechanism dropped because they are imported with `from . import x`
RELATIVE_IMPORT_VICTIMS = ("src/research/hypothesis_v71/estimator.py",
                           "src/research/hypothesis_v71/matching.py",
                           "src/research/hypothesis_v71/confounders.py",
                           "src/research/hypothesis_v71/compiler.py",
                           "src/research/hypothesis_v71/similarity.py",
                           "src/research/hypothesis_v71/recency.py",
                           "src/research/hypothesis_v71/invariants.py",
                           "src/research/hypothesis_v71/ontology.py")


# ======================================================================================
# helpers: a throwaway git repository with a controlled import graph
# ======================================================================================
def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          check=True)


def _mini_repo(files: dict, tracked=None):
    """Create a temp git repo containing `files`; commit `tracked` (default: all)."""
    repo = tempfile.mkdtemp(prefix="v71_dep_")
    for rel, body in files.items():
        ap = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w") as fh:
            fh.write(body)
    _git(repo, "init", "-q")
    for rel in (tracked if tracked is not None else list(files)):
        _git(repo, "add", "--", rel)
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "x")
    return repo


def _commit(repo, entry=("driver.py",), **kw):
    return PV.source_graph_commitment(list(entry), root=repo, **kw)


# ======================================================================================
# 1. untracked executable dependency -> the freeze must refuse
# ======================================================================================
def test_16_untracked_executable_dependency_refuses_the_freeze():
    """The exact failure that broke the clean checkout: reachable code absent from the commit."""
    repo = _mini_repo({
        "driver.py": "from src.pkg import mod\n",
        "src/pkg/__init__.py": "",
        "src/pkg/mod.py": "X = 1\n",
    }, tracked=["driver.py", "src/pkg/__init__.py"])          # mod.py deliberately untracked
    try:
        sg = _commit(repo)
        assert "src/pkg/mod.py" in sg["source_file_hashes"], "must still be DISCOVERED"
        assert sg["counts"]["n_untracked"] == 1
        assert sg["untracked_executable_dependencies"] == ["src/pkg/mod.py"]
        assert not sg["ok"]
        assert any(p.startswith("UNTRACKED_EXECUTABLE_DEPENDENCY") for p in sg["problems"])
        assert sg["file_records"]["src/pkg/mod.py"]["git_tracked"] is False
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_16_a_fully_tracked_graph_is_accepted():
    """Negative control: the guard must not reject a clean graph (else it is vacuous)."""
    repo = _mini_repo({
        "driver.py": "from src.pkg import mod\n",
        "src/pkg/__init__.py": "",
        "src/pkg/mod.py": "X = 1\n",
    })
    try:
        sg = _commit(repo)
        assert sg["counts"]["n_untracked"] == 0
        assert sg["counts"]["n_unresolved_first_party"] == 0
        assert sg["ok"], sg["problems"]
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ======================================================================================
# 2. prefix escape -- relevance must be reachability, never a path prefix
# ======================================================================================
def test_16_dependency_outside_the_experiment_prefix_is_bound():
    """A tracked dependency in a directory unrelated to any experiment name must be bound."""
    repo = _mini_repo({
        "driver.py": "from src.totally_unrelated_area import thing\n",
        "src/totally_unrelated_area/__init__.py": "",
        "src/totally_unrelated_area/thing.py": "Y = 2\n",
    })
    try:
        sg = _commit(repo)
        target = "src/totally_unrelated_area/thing.py"
        assert target in sg["source_file_hashes"]
        # and it would have been invisible to the superseded rule
        assert not target.startswith(("src/research/hypothesis_v7", "research/hypothesis_engine"))
        assert sg["relevance_rule"].startswith("reachability only")
        assert sg["ok"], sg["problems"]
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ======================================================================================
# 3. script-root import
# ======================================================================================
def test_16_script_root_dependency_is_bound_and_hashed():
    """A module importable only because `scripts/` is an import root must be bound + hashed."""
    repo = _mini_repo({
        "driver.py": "import helper\n",
        "scripts/helper.py": "Z = 3\n",
    })
    try:
        sg = _commit(repo)
        assert "scripts/helper.py" in sg["source_file_hashes"]
        rec = sg["file_records"]["scripts/helper.py"]
        assert len(rec["sha256"]) == 64
        assert rec["git_tracked"] is True
        assert rec["imported_by"] == ["driver.py"]
        assert "scripts" in sg["import_roots"]
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ======================================================================================
# 4. relative imports -- the second v1 blind spot
# ======================================================================================
def test_16_relative_imports_are_followed():
    repo = _mini_repo({
        "driver.py": "from src.pkg import a\n",
        "src/pkg/__init__.py": "",
        "src/pkg/a.py": "from . import b\n",
        "src/pkg/b.py": "from .c import thing\n",
        "src/pkg/c.py": "thing = 1\n",
    })
    try:
        sg = _commit(repo)
        files = set(sg["source_file_hashes"])
        assert {"src/pkg/a.py", "src/pkg/b.py", "src/pkg/c.py"} <= files
        assert sg["file_records"]["src/pkg/b.py"]["imported_by"] == ["src/pkg/a.py"]
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_16_ancestor_packages_are_bound():
    """Importing `a.b.c` executes `a/__init__.py` and `a/b/__init__.py` too."""
    repo = _mini_repo({
        "driver.py": "from src.pkg.sub import leaf\n",
        "src/__init__.py": "",
        "src/pkg/__init__.py": "",
        "src/pkg/sub/__init__.py": "",
        "src/pkg/sub/leaf.py": "L = 1\n",
    })
    try:
        sg = _commit(repo)
        files = set(sg["source_file_hashes"])
        assert {"src/__init__.py", "src/pkg/__init__.py", "src/pkg/sub/__init__.py",
                "src/pkg/sub/leaf.py"} <= files
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ======================================================================================
# 5. runtime-only dependency -- the independent second mechanism
# ======================================================================================
def test_16_runtime_only_dependency_is_caught_by_the_trace():
    """A module the static walk cannot see (imported via importlib) is still bound and REPORTED."""
    repo = _mini_repo({
        "driver.py": ("import importlib\n"
                      "m = importlib.import_module('src.pkg.dynamic')\n"),
        "src/pkg/__init__.py": "",
        "src/pkg/dynamic.py": "D = 1\n",
    })
    try:
        static = _commit(repo)
        assert "src/pkg/dynamic.py" not in static["source_file_hashes"], \
            "precondition: a dynamic import is invisible to static analysis"

        union = _commit(repo, runtime_files={"src/pkg/dynamic.py": "src.pkg.dynamic"})
        assert "src/pkg/dynamic.py" in union["source_file_hashes"]
        assert union["runtime_only_files"] == ["src/pkg/dynamic.py"]
        assert union["file_records"]["src/pkg/dynamic.py"]["resolution"] == "runtime"
        assert union["counts"]["n_runtime"] == 1
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_16_runtime_trace_excludes_environment_code_and_finds_repo_code():
    """The trace must bind repository modules and never venv/site-packages third parties."""
    live = PV.runtime_first_party_files(root=ROOT)
    assert "src/research/hypothesis_v71/provenance.py" in live
    assert not any(".venv/" in f or "site-packages" in f for f in live)


# ======================================================================================
# 6. removed / changed bound dependencies must refuse at preflight
# ======================================================================================
def test_16_removed_bound_dependency_refuses_preflight():
    repo = _mini_repo({
        "driver.py": "from src.pkg import mod\n",
        "src/pkg/__init__.py": "",
        "src/pkg/mod.py": "X = 1\n",
    })
    try:
        frozen = _commit(repo)
        os.remove(os.path.join(repo, "src/pkg/mod.py"))
        ok, problems, _live = PV.verify_source_graph(frozen, root=repo)
        assert not ok
        assert any("removed since freeze" in p and "mod.py" in p for p in problems)
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_16_changed_dependency_bytes_refuse_preflight_without_a_version_bump():
    repo = _mini_repo({
        "driver.py": "from src.pkg import mod\n",
        "src/pkg/__init__.py": "",
        "src/pkg/mod.py": "X = 1\n",
    })
    try:
        frozen = _commit(repo)
        with open(os.path.join(repo, "src/pkg/mod.py"), "w") as fh:
            fh.write("X = 1\n# behaviourally irrelevant edit, no version constant touched\n")
        ok, problems, _live = PV.verify_source_graph(frozen, root=repo)
        assert not ok
        assert any("changed since freeze" in p and "mod.py" in p for p in problems)
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_16_same_data_different_code_still_refuses():
    """Code integrity and data integrity are INDEPENDENT commitments.

    The data file is byte-identical throughout; only a bound source file changes. The source
    commitment must still refuse -- an unchanged dataset may never excuse changed code.
    """
    repo = _mini_repo({
        "driver.py": "from src.pkg import mod\n",
        "src/pkg/__init__.py": "",
        "src/pkg/mod.py": "X = 1\n",
        "data/input.json": '{"rows": [1, 2, 3]}\n',
    })
    try:
        frozen = _commit(repo)
        data_before = PV.sha_file(os.path.join(repo, "data/input.json"))
        with open(os.path.join(repo, "src/pkg/mod.py"), "w") as fh:
            fh.write("X = 2\n")
        data_after = PV.sha_file(os.path.join(repo, "data/input.json"))
        assert data_before == data_after, "the dataset is deliberately untouched"
        ok, problems, _live = PV.verify_source_graph(frozen, root=repo)
        assert not ok
        assert any("changed since freeze" in p for p in problems)
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# ---- the same two guards, against the REAL frozen graph -------------------------------
def _frozen_graph():
    path = f"{OUT}/V7_1_PROVENANCE.json"
    if not os.path.exists(path):
        pytest.skip("V7_1_PROVENANCE.json absent")
    return json.load(open(path))["source_graph"]


def test_16_changed_script_dependency_refuses_preflight():
    """scripts/multisrc_corpus.py is a real bound dependency; changed bytes must refuse."""
    frozen = copy.deepcopy(_frozen_graph())
    key = "scripts/multisrc_corpus.py"
    assert key in frozen["source_file_hashes"], "the provider script must be bound at all"
    frozen["source_file_hashes"][key] = "0" * 64
    ok, problems, _live = PV.verify_source_graph(frozen)
    assert not ok
    assert any(key in p and "changed since freeze" in p for p in problems)


def test_16_changed_corpus_loader_refuses_preflight():
    """src/research/matchup/corpus.py -- the file the v1 graph could not see -- must refuse."""
    frozen = copy.deepcopy(_frozen_graph())
    key = "src/research/matchup/corpus.py"
    assert key in frozen["source_file_hashes"], "the corpus loader must be bound at all"
    frozen["source_file_hashes"][key] = "0" * 64
    ok, problems, _live = PV.verify_source_graph(frozen)
    assert not ok
    assert any(key in p and "changed since freeze" in p for p in problems)


def test_16_changed_estimator_refuses_preflight():
    """The estimator was invisible to v1 because engine.py imports it relatively."""
    frozen = copy.deepcopy(_frozen_graph())
    key = "src/research/hypothesis_v71/estimator.py"
    assert key in frozen["source_file_hashes"], "the estimator must be bound at all"
    frozen["source_file_hashes"][key] = "0" * 64
    ok, problems, _live = PV.verify_source_graph(frozen)
    assert not ok
    assert any(key in p for p in problems)


# ======================================================================================
# 7. unresolvable imports fail closed
# ======================================================================================
def test_16_unresolvable_first_party_import_fails_closed():
    repo = _mini_repo({"driver.py": "import definitely_not_a_real_module_qzx\n"})
    try:
        sg = _commit(repo)
        assert sg["counts"]["n_unresolved_first_party"] == 1
        assert not sg["ok"]
        assert any(p.startswith("UNRESOLVED_FIRST_PARTY_IMPORT") for p in sg["problems"])
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_16_stdlib_and_third_party_are_not_treated_as_first_party():
    repo = _mini_repo({"driver.py": "import os, json\nimport pytest\n"})
    try:
        sg = _commit(repo)
        assert sg["counts"]["n_unresolved_first_party"] == 0, sg["problems"]
        assert sg["source_file_hashes"] == {
            "driver.py": PV.sha_file(os.path.join(repo, "driver.py"))}
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_16_classify_import_places_every_kind():
    assert PV.classify_import("src.research.hypothesis_v71.estimator")["kind"] == "first_party"
    assert PV.classify_import("multisrc_corpus")["kind"] == "first_party"
    assert PV.classify_import("os")["kind"] == "stdlib"
    assert PV.classify_import("numpy")["kind"] == "third_party"
    assert PV.classify_import("definitely_not_a_real_module_qzx")["kind"] == "unresolved"
    # a NAME imported from a repository module is not itself a file
    assert (PV.classify_import("src.research.hypothesis_v71.estimator.CLUSTER_UNIT")["kind"]
            == "first_party_symbol")


# ======================================================================================
# 8. the real frozen graph must be complete
# ======================================================================================
def test_16_corpus_layer_and_scripts_are_bound_in_the_frozen_graph():
    frozen = _frozen_graph()
    files = set(frozen["source_file_hashes"])
    missing = [f for f in CORPUS_LAYER if f not in files]
    assert not missing, f"corpus layer escaped the freeze again: {missing}"


def test_16_relative_import_victims_are_bound_in_the_frozen_graph():
    frozen = _frozen_graph()
    files = set(frozen["source_file_hashes"])
    missing = [f for f in RELATIVE_IMPORT_VICTIMS if f not in files]
    assert not missing, f"relatively-imported modules escaped the freeze again: {missing}"


def test_16_frozen_graph_has_no_untracked_or_unresolved_dependencies():
    frozen = _frozen_graph()
    counts = frozen["counts"]
    assert counts["n_untracked"] == 0, frozen["untracked_executable_dependencies"]
    assert counts["n_unresolved_first_party"] == 0, frozen["unresolved_first_party_imports"]
    assert counts["n_ambiguous"] == 0, frozen["ambiguous_resolutions"]


def test_16_every_bound_file_is_tracked_and_hashed():
    frozen = _frozen_graph()
    for path, rec in sorted(frozen["file_records"].items()):
        assert rec["git_tracked"] is True, f"{path} is not tracked at the frozen commit"
        assert len(rec["sha256"]) == 64, path
        assert rec["resolution"] in ("static", "runtime", "both"), path


def test_16_frozen_graph_binds_the_union_of_both_mechanisms():
    frozen = _frozen_graph()
    assert frozen["counts"]["n_runtime"] > 0, "the runtime trace must have been supplied"
    assert frozen["counts"]["n_union"] >= frozen["counts"]["n_static"]
    assert frozen["counts"]["n_union"] >= frozen["counts"]["n_runtime"]
    both = [p for p, r in frozen["file_records"].items() if r["resolution"] == "both"]
    assert both, "the two mechanisms must corroborate each other on real files"


def test_16_the_frozen_graph_is_strictly_larger_than_the_superseded_v1_graph():
    frozen = _frozen_graph()
    assert frozen["provenance_version"] == "v71_provenance_v2"
    assert len(frozen["source_file_hashes"]) > 17, \
        "v1 bound 17 files; the repaired graph must bind the code v1 missed"


def test_16_sys_path_mutation_is_declared_and_its_root_is_understood():
    """The corpus loader's `sys.path` insert is load-bearing, so it is declared, not incidental."""
    frozen = _frozen_graph()
    muts = {m["module"]: m for m in frozen["sys_path_mutations"]}
    assert "src/research/matchup/corpus.py" in muts
    mut = muts["src/research/matchup/corpus.py"]
    assert mut["inserts"] == "scripts"
    assert mut["bound_by_source_graph"] is True
    assert mut["inserts"] in frozen["import_roots"]
    # and the modules that insert becomes importable are actually bound
    assert "scripts/multisrc_corpus.py" in frozen["source_file_hashes"]


# ======================================================================================
# 10. artifacts the freeze BINDS must be reproducible
# ======================================================================================
#: keys whose values are wall-clock or environment noise rather than scientific content
NONDETERMINISTIC_KEYS = ("seconds", "elapsed", "elapsed_seconds", "duration", "timestamp",
                         "created_at", "created_utc", "generated_at", "run_at", "started_at",
                         "finished_at", "now")


def _keys_recursively(obj, out=None):
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(k)
            _keys_recursively(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys_recursively(v, out)
    return out


def test_16_bound_artifacts_carry_no_wall_clock_fields():
    """A hashed artifact containing a duration changes on every run.

    That would make the freeze self-invalidating: re-running a harness would refuse preflight
    although nothing scientific moved, and the freeze would be binding a value that cannot be
    reproduced. Found on `V7_1_DEV_EXECUTION_EXERCISE.json` ("seconds") during the D16 repair.
    """
    manifest_path = f"{OUT}/V7_1_FREEZE_MANIFEST.json"
    if not os.path.exists(manifest_path):
        pytest.skip("freeze manifest absent")
    manifest = json.load(open(manifest_path))
    offenders = {}
    for name in sorted(manifest["artifact_hashes"]):
        path = f"{OUT}/{name}"
        if not os.path.exists(path) or not name.endswith(".json"):
            continue
        try:
            doc = json.load(open(path))
        except (ValueError, UnicodeDecodeError):
            continue
        bad = sorted({k for k in _keys_recursively(doc) if k in NONDETERMINISTIC_KEYS})
        if bad:
            offenders[name] = bad
    assert not offenders, f"bound artifacts carry non-reproducible fields: {offenders}"


def test_16_bound_artifacts_declare_the_frozen_engine_spec():
    """D17: a bound diagnostic generated under superseded code must not be freezable.

    v2 froze a replay carrying engine_spec_hash 4138f90b while pinning 25527df6, so the
    evaluability gate's precision input could not be reproduced from the committed source.
    """
    manifest_path = f"{OUT}/V7_1_FREEZE_MANIFEST.json"
    if not os.path.exists(manifest_path):
        pytest.skip("freeze manifest absent")
    manifest = json.load(open(manifest_path))
    pinned = manifest["engine_spec_hash"]
    stale = {}
    for name in sorted(manifest["artifact_hashes"]):
        path = f"{OUT}/{name}"
        if not name.endswith(".json") or not os.path.exists(path):
            continue
        try:
            doc = json.load(open(path))
        except (ValueError, UnicodeDecodeError):
            continue
        declared = doc.get("engine_spec_hash") if isinstance(doc, dict) else None
        if declared is not None and declared != pinned:
            stale[name] = declared
    assert not stale, f"bound artifacts produced under a superseded engine spec: {stale}"


def test_16_blast_radius_test_reachability_is_not_stale():
    """The published blast radius must match a LIVE re-derivation, test modules included.

    The D14 repair guarded the changed-MODULE set against drift but not the reachable-TEST set,
    so adding a test module left the bound artifact silently stale (6 reaching / 225 scanned on
    disk vs 7 / 226 live). A reachability claim is evidence; stale evidence is worse than none.
    """
    path = f"{OUT}/V7_1_BLAST_RADIUS.json"
    if not os.path.exists(path):
        pytest.skip("blast radius artifact absent")
    published = json.load(open(path))

    # enumerated from git, exactly as the driver does: the claim must describe the COMMIT, not
    # whatever scratch test files happen to sit in a working tree
    tracked = PV.git_tracked_files(ROOT, "HEAD")
    assert tracked is not None, "git tracking could not be determined"
    tests_tracked = sorted(p for p in tracked
                           if p.startswith("tests/")
                           and os.path.basename(p).startswith("test_") and p.endswith(".py"))
    assert published["n_test_modules_scanned"] == len(tests_tracked), (
        f"published scan covered {published['n_test_modules_scanned']} test modules, "
        f"{len(tests_tracked)} are tracked at HEAD")

    changed = set(published["changed_modules"])
    live_reaching = set()
    for t in tests_tracked:
        importers, _u, _a = PV.static_closure([t], root=ROOT)
        if set(importers) & changed:
            live_reaching.add(t)
    declared = {r["test_module"] for r in published["test_modules_reaching_changed_code"]}
    assert declared == live_reaching, {
        "missing_from_artifact": sorted(live_reaching - declared),
        "stale_in_artifact": sorted(declared - live_reaching)}


def test_16_bound_artifact_hashes_all_recompute():
    """Every artifact the manifest binds must still hash to its frozen value."""
    manifest_path = f"{OUT}/V7_1_FREEZE_MANIFEST.json"
    if not os.path.exists(manifest_path):
        pytest.skip("freeze manifest absent")
    manifest = json.load(open(manifest_path))
    bad = []
    for name, expected in sorted(manifest["artifact_hashes"].items()):
        path = f"{OUT}/{name}"
        if not os.path.exists(path):
            bad.append(f"{name}: missing")
        elif PV.sha_file(path) != expected:
            bad.append(f"{name}: hash differs")
    assert not bad, bad


# ======================================================================================
# 11. clean-checkout executability must be PROVEN, not assumed
# ======================================================================================
def test_16_clean_checkout_proof_exists_and_binds_the_freeze_manifest():
    """v2 verified every hash it bound and still could not run. Executability is now proven."""
    proof_path = f"{OUT}/V7_1_CLEAN_CHECKOUT_PROOF.json"
    if not os.path.exists(proof_path):
        pytest.skip("clean-checkout proof not yet produced for this head")
    proof = json.load(open(proof_path))
    manifest_sha = PV.sha_file(f"{OUT}/V7_1_FREEZE_MANIFEST.json")
    assert proof["freeze_manifest_sha256"] == manifest_sha, \
        "the proof was taken against a different freeze manifest"
    assert proof["clean_checkout_executable"] is True
    assert proof["git_status_porcelain_empty"] is True
    assert proof["copied_executable_py_files"] == 0
    for stage, ok in sorted(proof["stages"].items()):
        assert ok is True, f"clean-checkout stage failed: {stage}"
    assert proof["confirmatory_oos_computed"] is False
    assert proof["confirmatory_oos_viewed"] is False
