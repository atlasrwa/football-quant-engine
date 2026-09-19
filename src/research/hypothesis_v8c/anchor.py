"""V8C external Git anchor (`v8c_anchor_v1`) -- Gate A Phase 5.

THE DEFECT
----------
`freeze.json` + `receipt.json` is a TWO-FILE anchor, and both files are mutually editable by
whoever holds the working tree. Editing the freeze changes `receipt.freeze_sha256`; but the
editor can then rewrite the receipt and recompute `receipt_hash`. The pair is tamper-evident
against accident, not against intent. Nothing outside the editor's control pins either file.

THE ANCHOR
----------
A third artifact -- the ANCHOR -- carries the exact SHA256 of BOTH files and is committed to
Git. Git commits are content-addressed and append-only in practice, so the commit id is a name
the producer cannot retroactively change without rewriting history (which a reviewer sees).

    PROCESS 1   write freeze -> write receipt -> hash both -> write anchor -> git commit it
    PROCESS 2   requires an explicit ANCHOR_COMMIT, reads the anchor blob AT THAT COMMIT, and
                verifies it names exactly the freeze and receipt bytes being supplied

TWO DIFFERENT COMMITS, DELIBERATELY
-----------------------------------
    PRODUCER_CODE_COMMIT   the commit whose CODE produced the freeze
    ANCHOR_COMMIT          the commit that CONTAINS the anchor artifact

They are necessarily different: committing the anchor creates a new commit AFTER the one whose
code ran. Requiring `producer_commit == HEAD` -- the old check -- is therefore unsatisfiable in
the real workflow and would be routinely bypassed, which is worse than no check.

So the two are verified against different things:

    producer module hashes  <-  verified against PRODUCER_CODE_COMMIT (`git show <c>:<path>`)
    freeze / receipt bytes  <-  verified against ANCHOR_COMMIT

Neither is verified against the working tree, which is exactly the point: the working tree is
what the editor controls.

ZERO SPEND. Reads no target outcome. Opening an outcome is the CALLER's next step, and only
after `verify_for_scoring` returns.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import subprocess

ANCHOR_VERSION = "v8c_anchor_v1"

#: The checkout this module is executing from. Derived from the module's own location, not
#: hardcoded, so the producer-code binding follows the interpreter rather than one machine's
#: path. `V8C_ROOT` overrides it for a relocated tree. A hardcoded "/home/ubuntu" here meant a
#: clean checkout elsewhere would hash THAT tree's modules while running its own -- which is
#: precisely the substitution the three-way binding exists to catch.
ROOT = os.environ.get(
    "V8C_ROOT",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))))


class AnchorError(Exception):
    """The anchor is missing, unreachable, or does not name these artifacts. Nothing is scored."""


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(path: str) -> str:
    with open(path, "rb") as f:
        return _sha_bytes(f.read())


def _git(args, *, repo_root=None, binary=False):
    out = subprocess.run(["git", *args], cwd=repo_root or ROOT,
                         capture_output=True, timeout=60)
    if out.returncode != 0:
        raise AnchorError(f"git {' '.join(args)} failed: "
                          f"{out.stderr.decode('utf-8', 'replace').strip()}")
    return out.stdout if binary else out.stdout.decode("utf-8")


def read_blob_at(commit: str, repo_relpath: str, *, repo_root=None) -> bytes:
    """The exact BYTES of `repo_relpath` as committed at `commit`."""
    return _git(["show", f"{commit}:{repo_relpath}"], repo_root=repo_root, binary=True)


def current_commit(*, repo_root=None) -> str:
    return _git(["rev-parse", "HEAD"], repo_root=repo_root).strip()


# ------------------------------------------------------------------ PROCESS 1: build
def build_anchor(*, freeze_path, receipt_path, producer_code_commit,
                 producer_code_hashes, classification, cohort_hash=None,
                 corpus_hash=None, capability_hash=None, extra=None) -> dict:
    """The anchor artifact. Names both files by content, and names the CODE commit separately
    from the commit this artifact will itself land in."""
    a = {
        "anchor_version": ANCHOR_VERSION,
        "freeze_filename": os.path.basename(freeze_path),
        "freeze_sha256": sha_file(freeze_path),
        "receipt_filename": os.path.basename(receipt_path),
        "receipt_sha256": sha_file(receipt_path),
        "producer_code_commit": producer_code_commit,
        "producer_code_hashes": dict(producer_code_hashes),
        "cohort_hash": cohort_hash,
        "corpus_hash": corpus_hash,
        "capability_hash": capability_hash,
        "classification": classification,
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "note": ("ANCHOR_COMMIT is the commit CONTAINING this file and is necessarily later "
                 "than producer_code_commit; it is supplied by the verifier, never stored "
                 "here, because a file cannot name the commit that will contain it."),
    }
    a["anchor_hash"] = _anchor_hash(a)
    return a


def _anchor_hash(a: dict) -> str:
    core = {k: v for k, v in a.items() if k != "anchor_hash"}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def write_anchor(anchor: dict, path: str) -> str:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(anchor, f, indent=1, sort_keys=True, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return anchor["anchor_hash"]


# ------------------------------------------------------------------ PROCESS 2: verify
def verify_anchor_at_commit(*, anchor_commit, anchor_repo_relpath, freeze_path,
                            receipt_path, repo_root=None) -> dict:
    """Verify the COMMITTED anchor names exactly these freeze and receipt bytes.

    Reads the anchor from Git at `anchor_commit`, NOT from the working tree.
    """
    if not anchor_commit:
        raise AnchorError("ANCHOR_COMMIT was not supplied: refusing to score")
    raw = read_blob_at(anchor_commit, anchor_repo_relpath, repo_root=repo_root)
    try:
        anchor = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise AnchorError(f"anchor blob at {anchor_commit} is not valid JSON: {e}")

    claimed = anchor.get("anchor_hash")
    if not claimed or claimed != _anchor_hash(anchor):
        raise AnchorError("anchor_hash does not match the committed anchor's own content")

    actual_freeze = sha_file(freeze_path)
    if actual_freeze != anchor.get("freeze_sha256"):
        raise AnchorError(
            f"freeze bytes {actual_freeze} do not match the anchor committed at "
            f"{anchor_commit} ({anchor.get('freeze_sha256')})")

    actual_receipt = sha_file(receipt_path)
    if actual_receipt != anchor.get("receipt_sha256"):
        raise AnchorError(
            f"receipt bytes {actual_receipt} do not match the anchor committed at "
            f"{anchor_commit} ({anchor.get('receipt_sha256')})")
    return anchor


def verify_producer_code(anchor: dict, *, repo_root=None, require_modules=None,
                         verify_executing=True, expected_exec_root=None,
                         require_executing=None) -> dict:
    """THREE-WAY binding of the scientific code, by CANONICAL REPOSITORY PATH.

        anchor claim == bytes at PRODUCER_CODE_COMMIT == bytes of the file this interpreter
                                                         actually imported

    Three defects this replaces:

      * a module that was NOT LOADED was appended to a `not_loaded` list and skipped, then
        counted in `n_modules_verified`, while the function returned
        `executing_code_verified: bool(verify_executing)` -- the FLAG, not the outcome. A
        required module could therefore be reported verified without being verified at all.
      * only `hypothesis_v8c/*` was bound, so a change to the compiler, the similarity spec,
        the corpus loader or a provider adapter left the anchor valid while changing results.
      * an import resolved from a DIFFERENT checkout satisfied the check as long as the bytes
        matched; `expected_exec_root` now pins where a loaded module may live.

    A required source that cannot be verified is an ERROR. Nothing is certified by omission.
    """
    import sys as _sys

    from src.research.hypothesis_v8c import receipt as _RC

    commit = anchor.get("producer_code_commit")
    if not commit or commit == "UNKNOWN":
        raise AnchorError("anchor carries no producer_code_commit: cannot verify producer code")

    claimed = anchor.get("producer_code_hashes") or {}
    required = list(require_modules) if require_modules is not None else sorted(claimed)
    if not required:
        raise AnchorError("anchor declares NO producer code hashes: refusing to score on a "
                          "vacuously-satisfied code binding")
    undeclared = sorted(m for m in required if claimed.get(m) in (None, ""))
    if undeclared:
        raise AnchorError(
            f"anchor's producer code coverage is incomplete: {len(undeclared)} source(s) carry "
            f"no hash ({undeclared[:5]}) -- an incomplete binding is not a binding")

    path_for = dict(_RC.MODULE_PATH_FOR)
    rel_to_import = {v: k for k, v in path_for.items()}
    exec_root = os.path.abspath(expected_exec_root or ROOT)

    must_execute = set(require_executing if require_executing is not None
                       else _RC.REQUIRED_EXECUTING_SOURCES)
    mismatches, missing, unverified, git_only = [], [], [], []
    git_verified = exec_verified = exec_verified_required = 0
    for key in required:
        expected = claimed[key]
        rel = key if key.endswith(".py") else f"src/research/hypothesis_v8c/{key}.py"
        try:
            at_commit = _sha_bytes(read_blob_at(commit, rel, repo_root=repo_root))
        except AnchorError:
            missing.append(rel)
            continue
        if at_commit != expected:
            mismatches.append({"source": rel, "at_commit": at_commit, "in_anchor": expected,
                               "which": "GIT"})
            continue
        git_verified += 1
        if not verify_executing:
            continue

        mod_name = rel_to_import.get(rel)
        m = _sys.modules.get(mod_name) if mod_name else None
        f = getattr(m, "__file__", None) if m is not None else None
        if not f or not os.path.exists(f):
            if rel in must_execute:
                # NOT a skip. A source this process is REQUIRED to run, but never imported,
                # cannot be certified as the code that is executing.
                unverified.append({"source": rel, "reason": "NOT_LOADED_IN_THIS_INTERPRETER"})
            else:
                git_only.append(rel)      # bound and git-verified; legitimately not imported
            continue
        f = os.path.abspath(f)
        if not f.startswith(exec_root + os.sep):
            # Cross-checkout substitution: identical bytes from another tree must not pass.
            unverified.append({"source": rel, "reason": "LOADED_FROM_FOREIGN_CHECKOUT",
                               "loaded_from": f, "expected_root": exec_root})
            continue
        with open(f, "rb") as fh:
            executing = _sha_bytes(fh.read())
        if executing != expected:
            mismatches.append({"source": rel, "executing": executing, "in_anchor": expected,
                               "which": "EXECUTING"})
            continue
        exec_verified += 1
        if rel in must_execute:
            exec_verified_required += 1

    if missing or mismatches or unverified:
        raise AnchorError(
            f"producer code does not reproduce the anchor: {len(mismatches)} hash mismatch(es), "
            f"{len(missing)} missing file(s), {len(unverified)} unverified source(s). "
            f"{mismatches[:2]} {missing[:2]} {unverified[:2]}")

    if verify_executing:
        needed = [r for r in required if r in must_execute]
        unbound = sorted(set(must_execute) - set(required))
        if unbound:
            # A source declared REQUIRED-EXECUTING but absent from the bound set would never
            # be hashed at all -- an unverifiable requirement is a broken contract, not a pass.
            raise AnchorError(
                f"required-executing sources are not bound and so were never verified: "
                f"{unbound}")
        if exec_verified_required < len(needed):
            raise AnchorError(
                f"executing-code verification is incomplete: {exec_verified_required}/"
                f"{len(needed)} required-executing sources verified")

    return {"producer_code_commit": commit,
            "n_sources_required": len(required),
            "n_git_verified": git_verified,
            "n_executing_verified": exec_verified,
            # the OUTCOME, never the flag
            "n_required_executing": len([r for r in required if r in must_execute]),
            "n_executing_verified_required": exec_verified_required,
            "n_git_verified_only": len(git_only),
            "git_verified_only_sources": sorted(git_only),
            "executing_code_verified": (
                bool(verify_executing)
                and exec_verified_required == len([r for r in required if r in must_execute])),
            "expected_exec_root": exec_root,
            "unverified_sources": unverified}


def verify_for_scoring(*, anchor_commit, anchor_repo_relpath, freeze_path, receipt_path,
                       repo_root=None, verify_code=True, require_modules=None,
                       verify_executing=True, expected_exec_root=None,
                       require_executing=None) -> dict:
    """The complete PROCESS 2 gate. Raises before any caller can open a target outcome.

    Ordering matters: the external anchor is checked FIRST, because it is the only check whose
    reference is outside the working tree.
    """
    anchor = verify_anchor_at_commit(
        anchor_commit=anchor_commit, anchor_repo_relpath=anchor_repo_relpath,
        freeze_path=freeze_path, receipt_path=receipt_path, repo_root=repo_root)
    code = (verify_producer_code(anchor, repo_root=repo_root,
                                 require_modules=require_modules,
                                 verify_executing=verify_executing,
                                 expected_exec_root=expected_exec_root,
                                 require_executing=require_executing)
            if verify_code else None)

    from src.research.hypothesis_v8c import receipt as RC
    rcpt = RC.verify_receipt(receipt_path, freeze_path)   # NOT require_commit=HEAD
    return {"anchor": anchor, "receipt": rcpt, "producer_code": code,
            "anchor_commit": anchor_commit,
            "producer_code_commit": anchor.get("producer_code_commit"),
            "distinct_commits": anchor_commit != anchor.get("producer_code_commit"),
            "verified_against_working_tree": False}


def version_stamp() -> dict:
    return {"anchor_version": ANCHOR_VERSION,
            "repairs": ["P0-B-EXTERNAL-ANCHOR"],
            "was": "freeze.json + receipt.json, both editable by the same holder",
            "now": "a third artifact committed to Git, read back via `git show <commit>:<path>`",
            "distinguishes": ["PRODUCER_CODE_COMMIT", "ANCHOR_COMMIT"],
            "producer_code_verified_against": "PRODUCER_CODE_COMMIT",
            "freeze_and_receipt_verified_against": "ANCHOR_COMMIT",
            "requires_producer_commit_equals_head": False,
            "why_not": ("committing the anchor necessarily creates a later commit, so that "
                        "check is unsatisfiable in the real workflow and would be bypassed"),
            "anchor_commit_must_be_explicit": True,
            "reads_working_tree_for_verification": False,
            "binds_executing_code": True,
            "three_way_binding": ["anchor claim", "bytes at PRODUCER_CODE_COMMIT",
                                  "file loaded by this interpreter"],
            "refuses_vacuous_or_incomplete_producer_hashes": True}
