"""Test support: build a REAL external anchor for a freeze, in a throwaway git repo.

Every commit happens under tmp_path. Nothing is committed into the working repository, which
is rooted at $HOME and carries unrelated untracked material.

The scratch repo receives a COPY of the actual `hypothesis_v8c` modules, so the three-way
binding is exercised honestly: the anchor's claimed hashes, the bytes committed at
PRODUCER_CODE_COMMIT, and the files this interpreter has loaded are all the same bytes.
"""
from __future__ import annotations

import os
import shutil
import subprocess

from src.research.hypothesis_v8c import anchor as A
from src.research.hypothesis_v8c import receipt as RC

MODULE_DIR = "src/research/hypothesis_v8c"
#: The checkout THIS test file lives in -- not a hardcoded machine path, so a clean checkout
#: elsewhere anchors its own modules rather than another tree's.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
SRC = os.path.join(REPO, MODULE_DIR)


def _git(repo, *args):
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, f"git {' '.join(args)}: {out.stderr}"
    return out.stdout.strip()


def anchor_freeze(tmp_path, freeze_path, *, fixture_ids=("mt_1",),
                  classification="SYNTHETIC_ONLY", receipt_path=None):
    """-> kwargs for `score_frozen`: receipt_path, anchor_commit, anchor_repo_relpath, repo_root.

    The receipt is written next to the freeze (where `_run_v8c_score.py` looks for it).
    """
    repo = tmp_path / "anchor_repo"
    (repo / MODULE_DIR).mkdir(parents=True, exist_ok=True)
    (repo / "evidence").mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        _git(repo.parent, "init", "-q", str(repo))
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")

    for fn in sorted(os.listdir(SRC)):
        if fn.endswith(".py"):
            shutil.copy2(os.path.join(SRC, fn), repo / MODULE_DIR / fn)
    _git(repo, "add", MODULE_DIR)
    _git(repo, "commit", "-q", "--allow-empty", "-m", "producer code")
    producer_commit = _git(repo, "rev-parse", "HEAD")

    if receipt_path is None:
        receipt_path = str(freeze_path).replace(".json", "_receipt.json")
        RC.write_receipt(RC.build_receipt(
            freeze_path=str(freeze_path), corpus_hash="CORPUS", capability_hash="CAP",
            fixture_ids_ordered=list(fixture_ids), classification=classification),
            receipt_path)

    anchor_rel = "evidence/anchor.json"
    A.write_anchor(A.build_anchor(
        freeze_path=str(freeze_path), receipt_path=receipt_path,
        producer_code_commit=producer_commit,
        producer_code_hashes=RC.code_hashes(),
        classification=classification), str(repo / anchor_rel))
    _git(repo, "add", "evidence")
    _git(repo, "commit", "-q", "-m", "anchor")

    return {"receipt_path": receipt_path,
            "anchor_commit": _git(repo, "rev-parse", "HEAD"),
            "anchor_repo_relpath": anchor_rel,
            "repo_root": str(repo)}
