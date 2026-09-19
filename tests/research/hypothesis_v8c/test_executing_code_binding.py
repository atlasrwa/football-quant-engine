"""REPAIR 1: the executing-code binding must be COMPLETE and MANDATORY.

Three defects this pins:

  * `not_loaded` modules were appended to a list and SKIPPED, then counted in
    `n_modules_verified`, while the function returned `executing_code_verified: bool(flag)` --
    the flag, not the outcome. A required module could be certified without being verified.
  * only `hypothesis_v8c/*` was bound, so a change to the compiler, the similarity spec, the
    corpus loader or a provider adapter left the anchor valid while changing results.
  * a module imported from a DIFFERENT checkout passed whenever its bytes matched.
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from src.research.hypothesis_v8c import anchor as A
from src.research.hypothesis_v8c import receipt as RC
from src.research.hypothesis_v8c import score_frozen as SFZ

ANCHOR_REL = "evidence/anchor.json"
MODDIR = "src/research/hypothesis_v8c"


def _git(repo, *a):
    out = subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, f"git {a}: {out.stderr}"
    return out.stdout.strip()


@pytest.fixture
def anchored(tmp_path):
    """A scratch repo holding a COPY of every bound source, at its canonical path."""
    r = tmp_path / "repo"
    (r / "evidence").mkdir(parents=True)
    _git(r.parent, "init", "-q", str(r))
    _git(r, "config", "user.email", "t@e.com")
    _git(r, "config", "user.name", "T")
    import shutil
    for rel in RC.BOUND_SOURCES:
        dst = r / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f"/home/ubuntu/{rel}", dst)
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "producer code")
    producer = _git(r, "rev-parse", "HEAD")

    fz = r / "evidence/freeze.json"
    rp = r / "evidence/receipt.json"
    fz.write_text(json.dumps({"selections": ["x"]}, indent=1))
    RC.write_receipt(RC.build_receipt(freeze_path=str(fz), corpus_hash="C",
                                      capability_hash="K", fixture_ids_ordered=["mt_1"],
                                      classification="TEST"), str(rp))
    A.write_anchor(A.build_anchor(freeze_path=str(fz), receipt_path=str(rp),
                                  producer_code_commit=producer,
                                  producer_code_hashes=RC.code_hashes(),
                                  classification="TEST"), str(r / ANCHOR_REL))
    _git(r, "add", "evidence")
    _git(r, "commit", "-q", "-m", "anchor")
    return {"root": str(r), "freeze": str(fz), "receipt": str(rp),
            "producer": producer, "anchor": _git(r, "rev-parse", "HEAD")}


def _anchor_doc(a):
    return json.loads(A.read_blob_at(a["anchor"], ANCHOR_REL, repo_root=a["root"]).decode())


# ---------------------------------------------------------------- coverage completeness
def test_the_two_critical_omissions_are_now_bound():
    """`historical_similarity` decides cohort membership; `prompt` is what the model sees."""
    assert f"{MODDIR}/historical_similarity.py" in RC.BOUND_SOURCES
    assert f"{MODDIR}/prompt.py" in RC.BOUND_SOURCES


def test_upstream_scientific_dependencies_are_bound():
    """A v8c-only binding is not a binding of the scientific code."""
    for rel in ("src/research/hypothesis_v71/compiler.py",
                "src/research/hypothesis_v71/similarity.py",
                "src/research/hypothesis_v7/similarity.py",
                "src/research/hypothesis_v71/capability.py",
                "src/research/matchup/corpus.py",
                "scripts/multisrc_corpus.py",
                "scripts/championship_adapter.py"):
        assert rel in RC.BOUND_SOURCES, f"{rel} is not bound"


def test_every_bound_source_resolves():
    h = RC.code_hashes()
    unresolved = [k for k, v in h.items() if v is None]
    assert not unresolved, f"bound sources that do not exist: {unresolved}"


def test_omitted_dependency_is_refused(anchored):
    """An anchor that simply leaves a required source out must not verify."""
    doc = _anchor_doc(anchored)
    doc["producer_code_hashes"].pop(f"{MODDIR}/historical_similarity.py")
    with pytest.raises(A.AnchorError, match="incomplete"):
        A.verify_producer_code(doc, repo_root=anchored["root"],
                               require_modules=RC.BOUND_SOURCES, verify_executing=False)


# ---------------------------------------------------------------- changed code
@pytest.mark.parametrize("rel", [f"{MODDIR}/historical_similarity.py",
                                 "src/research/hypothesis_v71/compiler.py",
                                 "src/research/matchup/corpus.py"])
def test_changed_bound_source_is_refused(anchored, rel):
    doc = _anchor_doc(anchored)
    doc["producer_code_hashes"][rel] = "0" * 64
    with pytest.raises(A.AnchorError, match="does not reproduce"):
        A.verify_producer_code(doc, repo_root=anchored["root"],
                               require_modules=[rel], verify_executing=False)


# ---------------------------------------------------------------- not-loaded / wrong checkout
def test_unloaded_required_module_is_refused_not_skipped(anchored):
    """THE defect: a module this interpreter never imported was skipped and still counted."""
    doc = _anchor_doc(anchored)
    fake = f"{MODDIR}/__never_imported__.py"
    import shutil
    shutil.copy2(f"/home/ubuntu/{MODDIR}/prompt.py", f"{anchored['root']}/{fake}")
    _git(anchored["root"], "add", "-A")
    _git(anchored["root"], "commit", "-q", "-m", "add unimported source")
    new_producer = _git(anchored["root"], "rev-parse", "HEAD")
    doc["producer_code_commit"] = new_producer
    doc["producer_code_hashes"][fake] = A._sha_bytes(
        open(f"{anchored['root']}/{fake}", "rb").read())
    with pytest.raises(A.AnchorError, match="unverified source"):
        A.verify_producer_code(doc, repo_root=anchored["root"],
                               require_modules=[fake], verify_executing=True,
                               require_executing=[fake],
                               expected_exec_root="/home/ubuntu")


def test_foreign_checkout_import_is_refused(anchored):
    """Identical bytes from ANOTHER tree must not satisfy the executing-code check."""
    doc = _anchor_doc(anchored)
    rel = f"{MODDIR}/prompt.py"
    with pytest.raises(A.AnchorError, match="unverified source"):
        # the real module is loaded from /home/ubuntu; pin a different expected root
        A.verify_producer_code(doc, repo_root=anchored["root"], require_modules=[rel],
                               verify_executing=True, require_executing=[rel],
                               expected_exec_root=str(anchored["root"]))


def test_executing_verified_reports_the_outcome_not_the_flag(anchored):
    doc = _anchor_doc(anchored)
    rel = f"{MODDIR}/prompt.py"
    out = A.verify_producer_code(doc, repo_root=anchored["root"], require_modules=[rel],
                                 verify_executing=True, require_executing=[rel],
                                 expected_exec_root="/home/ubuntu")
    assert out["executing_code_verified"] is True
    assert out["n_executing_verified"] == out["n_required_executing"] == 1
    assert out["unverified_sources"] == []

    off = A.verify_producer_code(doc, repo_root=anchored["root"], require_modules=[rel],
                                 verify_executing=False)
    assert off["executing_code_verified"] is False, (
        "with executing verification off, the field must be False -- it reported the FLAG")


# ---------------------------------------------------------------- entry-point mandates
def test_score_frozen_has_no_executing_code_bypass():
    import inspect
    ps = inspect.signature(SFZ.score_frozen).parameters
    assert "verify_executing_code" not in ps, "the scoring path still exposes a bypass"
    for name in ("receipt_path", "anchor_commit", "anchor_repo_relpath"):
        assert ps[name].default is inspect.Parameter.empty


def test_score_frozen_requires_the_full_source_set():
    import inspect
    src = inspect.getsource(SFZ.score_frozen)
    assert "RCPT.BOUND_SOURCES" in src, "scoring binds only the v8c module list"
    assert "verify_executing=True" in src


def test_missing_anchor_still_refuses(anchored):
    with pytest.raises(A.AnchorError, match="ANCHOR_COMMIT"):
        A.verify_for_scoring(anchor_commit=None, anchor_repo_relpath=ANCHOR_REL,
                             freeze_path=anchored["freeze"],
                             receipt_path=anchored["receipt"], repo_root=anchored["root"])


def test_jointly_rewritten_freeze_and_receipt_still_refused(anchored):
    """The two-file scheme falls to a consistent rewrite; the anchor must not."""
    with open(anchored["freeze"], "w") as f:
        json.dump({"selections": ["SWAPPED"]}, f)
    RC.write_receipt(RC.build_receipt(freeze_path=anchored["freeze"], corpus_hash="C",
                                      capability_hash="K", fixture_ids_ordered=["mt_1"],
                                      classification="TEST"), anchored["receipt"])
    RC.verify_receipt(anchored["receipt"], anchored["freeze"])        # old check passes
    with pytest.raises(A.AnchorError):
        A.verify_for_scoring(anchor_commit=anchored["anchor"], anchor_repo_relpath=ANCHOR_REL,
                             freeze_path=anchored["freeze"],
                             receipt_path=anchored["receipt"], repo_root=anchored["root"],
                             verify_executing=False)
