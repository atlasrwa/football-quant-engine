"""Gate-A Phase 5: the external Git anchor, with adversarial tamper cases.

Every commit these tests make happens in a THROWAWAY repo under tmp_path. Nothing is committed
into the working repository: it is rooted at $HOME and carries unrelated untracked material.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from src.research.hypothesis_v8c import anchor as A

ANCHOR_REL = "evidence/anchor.json"


def _git(repo, *args):
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, f"git {args}: {out.stderr}"
    return out.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A scratch repo with a producer-code commit, then a separate anchor commit."""
    r = tmp_path / "scratch"
    (r / "src/research/hypothesis_v8c").mkdir(parents=True)
    (r / "evidence").mkdir()
    _git(r.parent, "init", "-q", str(r))
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "T")

    # --- the producing code, committed FIRST
    mod = r / "src/research/hypothesis_v8c/grammar.py"
    mod.write_text("GRAMMAR_VERSION = 'v8c_grammar_v1'\n")
    _git(r, "add", "src/research/hypothesis_v8c/grammar.py")
    _git(r, "commit", "-q", "-m", "producer code")
    producer_commit = _git(r, "rev-parse", "HEAD")

    # --- the artifacts it produced
    freeze = r / "evidence/freeze.json"
    receipt = r / "evidence/receipt.json"
    freeze.write_text(json.dumps({"selections": ["hyp_a"], "freeze_version": "v1"}, indent=1))

    from src.research.hypothesis_v8c import receipt as RC
    rc = RC.build_receipt(freeze_path=str(freeze), corpus_hash="CORPUS",
                          capability_hash="CAP", fixture_ids_ordered=["mt_1"],
                          classification="TEST")
    RC.write_receipt(rc, str(receipt))

    anchor = A.build_anchor(
        freeze_path=str(freeze), receipt_path=str(receipt),
        producer_code_commit=producer_commit,
        producer_code_hashes={"grammar": A._sha_bytes(mod.read_bytes())},
        classification="TEST", cohort_hash="COHORT")
    A.write_anchor(anchor, str(r / ANCHOR_REL))

    # --- the anchor lands in its OWN, LATER commit
    _git(r, "add", "evidence")
    _git(r, "commit", "-q", "-m", "anchor")
    anchor_commit = _git(r, "rev-parse", "HEAD")

    return {"root": str(r), "freeze": str(freeze), "receipt": str(receipt),
            "producer_commit": producer_commit, "anchor_commit": anchor_commit}


# ------------------------------------------------------------------ the happy path
def test_verifies_and_the_two_commits_are_distinct(repo):
    # `verify_executing=False`: this scratch repo holds a STUB grammar.py, so the interpreter
    # is deliberately not running it. The three-way executing-code binding is exercised in
    # test_process2_gate.py::test_changed_executing_code_refuses.
    out = A.verify_for_scoring(
        anchor_commit=repo["anchor_commit"], anchor_repo_relpath=ANCHOR_REL,
        freeze_path=repo["freeze"], receipt_path=repo["receipt"], repo_root=repo["root"],
        verify_executing=False)
    assert out["distinct_commits"] is True, (
        "the anchor commit must be later than the producer-code commit")
    assert out["producer_code_commit"] == repo["producer_commit"]
    assert out["anchor_commit"] == repo["anchor_commit"]
    assert out["producer_code"]["n_sources_required"] == 1
    assert out["verified_against_working_tree"] is False


def test_producer_commit_need_not_equal_head(repo):
    """HEAD is the anchor commit, not the producer commit. Verification must still pass."""
    head = _git(repo["root"], "rev-parse", "HEAD")
    assert head == repo["anchor_commit"] != repo["producer_commit"]
    A.verify_for_scoring(
        anchor_commit=repo["anchor_commit"], anchor_repo_relpath=ANCHOR_REL,
        freeze_path=repo["freeze"], receipt_path=repo["receipt"], repo_root=repo["root"],
        verify_executing=False)


# ------------------------------------------------------------------ adversarial
def test_editing_the_freeze_after_anchoring_is_caught(repo):
    with open(repo["freeze"], "w") as f:
        json.dump({"selections": ["hyp_SWAPPED"], "freeze_version": "v1"}, f, indent=1)
    with pytest.raises(A.AnchorError, match="freeze bytes"):
        A.verify_for_scoring(
            anchor_commit=repo["anchor_commit"], anchor_repo_relpath=ANCHOR_REL,
            freeze_path=repo["freeze"], receipt_path=repo["receipt"], repo_root=repo["root"])


def test_editing_freeze_and_reconsistently_rewriting_the_receipt_is_still_caught(repo):
    """THE POINT OF THE ANCHOR. The two-file scheme falls to this; the anchor does not."""
    from src.research.hypothesis_v8c import receipt as RC
    with open(repo["freeze"], "w") as f:
        json.dump({"selections": ["hyp_SWAPPED"], "freeze_version": "v1"}, f, indent=1)
    # The tamperer rewrites the receipt so the PAIR is internally consistent again.
    rc = RC.build_receipt(freeze_path=repo["freeze"], corpus_hash="CORPUS",
                          capability_hash="CAP", fixture_ids_ordered=["mt_1"],
                          classification="TEST")
    RC.write_receipt(rc, repo["receipt"])
    RC.verify_receipt(repo["receipt"], repo["freeze"])          # the old check now PASSES
    with pytest.raises(A.AnchorError):                          # the anchor still refuses
        A.verify_for_scoring(
            anchor_commit=repo["anchor_commit"], anchor_repo_relpath=ANCHOR_REL,
            freeze_path=repo["freeze"], receipt_path=repo["receipt"], repo_root=repo["root"])


def test_editing_the_working_tree_anchor_does_not_help(repo):
    """Verification reads the anchor from GIT, so rewriting the on-disk copy is inert."""
    import os
    with open(repo["freeze"], "w") as f:
        json.dump({"selections": ["hyp_SWAPPED"]}, f, indent=1)
    forged = A.build_anchor(
        freeze_path=repo["freeze"], receipt_path=repo["receipt"],
        producer_code_commit=repo["producer_commit"],
        producer_code_hashes={"grammar": A._sha_bytes(
            open(os.path.join(repo["root"], "src/research/hypothesis_v8c/grammar.py"),
                 "rb").read())},
        classification="TEST")
    A.write_anchor(forged, os.path.join(repo["root"], ANCHOR_REL))
    with pytest.raises(A.AnchorError, match="freeze bytes"):
        A.verify_for_scoring(
            anchor_commit=repo["anchor_commit"], anchor_repo_relpath=ANCHOR_REL,
            freeze_path=repo["freeze"], receipt_path=repo["receipt"], repo_root=repo["root"])


def test_missing_anchor_commit_refuses(repo):
    with pytest.raises(A.AnchorError, match="ANCHOR_COMMIT"):
        A.verify_for_scoring(
            anchor_commit=None, anchor_repo_relpath=ANCHOR_REL,
            freeze_path=repo["freeze"], receipt_path=repo["receipt"], repo_root=repo["root"])


def test_producer_code_mismatch_is_caught(repo):
    """The anchor claims a module hash the producer commit does not reproduce."""
    anchor = json.loads(A.read_blob_at(repo["anchor_commit"], ANCHOR_REL,
                                       repo_root=repo["root"]).decode())
    anchor["producer_code_hashes"]["grammar"] = "0" * 64
    with pytest.raises(A.AnchorError, match="does not reproduce"):
        A.verify_producer_code(anchor, repo_root=repo["root"])


def test_wrong_anchor_commit_refuses(repo):
    """Pointing at the producer commit, which has no anchor blob, must fail closed."""
    with pytest.raises(A.AnchorError):
        A.verify_for_scoring(
            anchor_commit=repo["producer_commit"], anchor_repo_relpath=ANCHOR_REL,
            freeze_path=repo["freeze"], receipt_path=repo["receipt"], repo_root=repo["root"])
