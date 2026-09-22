"""Item 6 Stage-1 PROVENANCE + scheme-aware hash verification (`item6_provenance_v1`).

ZERO PAID INFERENCE. No network, no LLM, no Bedrock. Importing or running this module makes
no API call of any kind.

WHY THIS MODULE EXISTS (two V5 provenance defects)

  DEFECT 1 -- SELF-REFERENTIAL EXECUTION HEAD.
  V5 embedded `execution_head_expected = 3dc1e4880...` inside a manifest that was itself
  committed at a LATER commit, so the field named the PARENT commit -- the one where the
  evidence apparatus did not yet exist. Replacing the value with the V5 commit sha would not
  fix it: the moment a successor manifest is committed, the actual execution HEAD becomes the
  successor's own sha and any self-declared value is stale again. An exact git HEAD cannot be
  non-circularly self-declared inside an artifact committed AT that head.

  The fix is to the provenance MODEL, not the value. Two distinct facts are separated:

    * APPARATUS PROVENANCE -- `apparatus_provenance_commit`: the commit that introduced the
      frozen scientific-input apparatus. Stable, historical, safely embeddable, and NOT a
      claim about the future runtime HEAD.
    * EXACT EXECUTION HEAD -- supplied EXTERNALLY by the authorizing human at run time
      (`authorized_execution_head`). The executor verifies `git HEAD == authorized head`
      before any CountTokens or Converse call and fails closed otherwise.

  Invariant: EXACT_EXECUTION_HEAD_SOURCE = EXTERNAL_HUMAN_AUTHORIZATION, never
  SELF_REFERENTIAL_MANIFEST_FIELD.

  DEFECT 2 -- AMBIGUOUS HASH SEMANTICS.
  V5's `new_scientific_input_artifact_hashes` mixed RAW FILE sha256 values (contract,
  materializer source, ...) with CANONICAL SELF-HASH values (the evidence packet set and the
  materialized request set, whose bound identity is the canonical hash of their own content
  EXCLUDING the self-hash field -- that is what the live provider verifies) under one dict
  with no discriminator. A verifier that assumes raw-file sha256 reports a FALSE DRIFT on the
  two set files. The fix is to make the scheme explicit per artifact and to verify with a
  scheme-aware verifier that fails closed on an unknown scheme or a scheme/method mismatch.

This module changes NO scientific treatment input: no prompt, schema, packet, request,
cohort, gate or threshold is touched by anything here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from typing import Any, Dict, Optional, Tuple

ITEM6_PROVENANCE_VERSION = "item6_provenance_v1"

ROOT_DEFAULT = "/home/ubuntu"

#: The commit that introduced the frozen Item 6 V5 point-in-time evidence-packet apparatus
#: (contract, materializer, frozen packet set, materialized request set, live packet
#: binding). Historical fact; NOT a claim about the future execution HEAD.
APPARATUS_PROVENANCE_COMMIT = "45876df4dca22ef8ad6838207add3fa54aa0c274"

EXACT_EXECUTION_HEAD_SOURCE = "EXTERNAL_HUMAN_AUTHORIZATION"

#: A manifest carrying this field is making a self-referential execution-head claim; V6+
#: refuses it.
SELF_REFERENTIAL_HEAD_FIELD = "execution_head_expected"

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProvenanceError(RuntimeError):
    """Base: a provenance invariant failed (always fail closed, never downgrade)."""


class HashSchemeError(ProvenanceError):
    """Raised when a hash scheme is unknown, missing, or inapplicable to the artifact."""


class HashMismatchError(ProvenanceError):
    """Raised when an artifact's content does not match its declared hash."""


class AuthorizedHeadError(ProvenanceError):
    """Raised when the externally authorized execution HEAD is missing/malformed/wrong."""


# ---------------------------------------------------------------------------------------
# hash schemes
# ---------------------------------------------------------------------------------------
class HashScheme:
    """The only hash schemes an Item 6 manifest may declare."""

    #: sha256 over the artifact's raw file bytes, exactly as committed.
    RAW_FILE_SHA256 = "RAW_FILE_SHA256"
    #: sha256 over canonical JSON (sort_keys, compact separators, ensure_ascii=False,
    #: allow_nan=False) of the artifact's parsed object with its OWN self-hash field removed.
    #: This is the identity the frozen packet provider and the live driver verify, and it is
    #: invariant under JSON re-indentation.
    CANONICAL_JSON_EXCLUDING_SELF_HASH = "CANONICAL_JSON_EXCLUDING_SELF_HASH"


KNOWN_HASH_SCHEMES = frozenset({
    HashScheme.RAW_FILE_SHA256,
    HashScheme.CANONICAL_JSON_EXCLUDING_SELF_HASH,
})


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def raw_file_sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def canonical_self_excluded_sha256(obj: Dict[str, Any], self_hash_field: str) -> str:
    body = {k: v for k, v in obj.items() if k != self_hash_field}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def compute_artifact_hash(entry: Dict[str, Any], root: str = ROOT_DEFAULT) -> str:
    """Compute an artifact's hash under its DECLARED scheme. Fails closed on an unknown
    scheme or on a scheme that cannot be applied to this artifact (e.g. canonical-JSON on a
    non-JSON source file, or a declared self-hash field the document does not carry)."""
    scheme = entry.get("hash_scheme")
    if scheme not in KNOWN_HASH_SCHEMES:
        raise HashSchemeError(
            f"unknown or missing hash_scheme {scheme!r}; known: {sorted(KNOWN_HASH_SCHEMES)}")
    rel = entry.get("path")
    if not rel:
        raise HashSchemeError("artifact entry has no path")
    path = rel if os.path.isabs(rel) else f"{root}/{rel}"
    if not os.path.exists(path):
        raise ProvenanceError(f"artifact missing on disk: {rel}")

    if scheme == HashScheme.RAW_FILE_SHA256:
        return raw_file_sha256(path)

    # CANONICAL_JSON_EXCLUDING_SELF_HASH
    field = entry.get("self_hash_field")
    if not field:
        raise HashSchemeError(
            f"{rel}: scheme {scheme} requires a self_hash_field naming the document's own "
            f"hash key")
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (ValueError, UnicodeDecodeError) as e:
        raise HashSchemeError(
            f"{rel}: scheme {scheme} is inapplicable -- not parseable JSON ({type(e).__name__})"
        ) from e
    if not isinstance(obj, dict):
        raise HashSchemeError(f"{rel}: scheme {scheme} requires a JSON object at the top level")
    if field not in obj:
        raise HashSchemeError(
            f"{rel}: scheme {scheme} declared self_hash_field {field!r}, absent from document")
    return canonical_self_excluded_sha256(obj, field)


def verify_artifact(name: str, entry: Dict[str, Any], root: str = ROOT_DEFAULT) -> str:
    """Verify one scheme-tagged artifact entry. Returns the computed hash on success.

    Fails closed (raises) on: unknown/missing scheme; inapplicable scheme; missing file;
    wrong hash. For CANONICAL_JSON_EXCLUDING_SELF_HASH the document's OWN recorded self-hash
    must ALSO equal the declared value, so the manifest and the artifact cannot disagree.
    """
    declared = entry.get("sha256")
    if not isinstance(declared, str) or not _SHA256_RE.match(declared):
        raise ProvenanceError(f"{name}: declared sha256 is not a 64-hex digest: {declared!r}")
    got = compute_artifact_hash(entry, root=root)
    if got != declared:
        raise HashMismatchError(
            f"{name} ({entry.get('path')}): {entry['hash_scheme']} hash {got} != declared "
            f"{declared}")
    if entry["hash_scheme"] == HashScheme.CANONICAL_JSON_EXCLUDING_SELF_HASH:
        rel = entry["path"]
        path = rel if os.path.isabs(rel) else f"{root}/{rel}"
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        recorded = obj.get(entry["self_hash_field"])
        if recorded != declared:
            raise HashMismatchError(
                f"{name}: document self-hash {recorded} != declared {declared}")
    return got


def verify_manifest_artifacts(manifest: Dict[str, Any],
                              root: str = ROOT_DEFAULT) -> Dict[str, Any]:
    """Verify every artifact in a V6+ manifest's `artifact_hash_index`. Returns a report.

    The index is the AUTHORITATIVE, unambiguous artifact identity record: every entry names
    its path, its hash scheme and its digest, so no verifier has to guess which scheme a
    value was produced under.
    """
    index = manifest.get("artifact_hash_index")
    if not isinstance(index, dict) or not index:
        raise ProvenanceError("manifest has no artifact_hash_index (V6+ requirement)")
    problems = []
    n_by_scheme: Dict[str, int] = {s: 0 for s in sorted(KNOWN_HASH_SCHEMES)}
    n_unknown = 0
    for name in sorted(index):
        entry = index[name]
        scheme = entry.get("hash_scheme") if isinstance(entry, dict) else None
        if scheme not in KNOWN_HASH_SCHEMES:
            n_unknown += 1
        try:
            verify_artifact(name, entry, root=root)
        except ProvenanceError as e:
            problems.append(str(e))
            continue
        n_by_scheme[scheme] += 1
    return {
        "ok": not problems and n_unknown == 0,
        "n_artifacts": len(index),
        "n_by_scheme": n_by_scheme,
        "n_unknown_hash_schemes": n_unknown,
        "problems": problems,
        "provenance_version": ITEM6_PROVENANCE_VERSION,
    }


# ---------------------------------------------------------------------------------------
# execution-head policy
# ---------------------------------------------------------------------------------------
def resolve_git_head(root: str = ROOT_DEFAULT) -> Optional[str]:
    """Resolve the repository's current HEAD commit sha, offline.

    Filesystem first (`.git/HEAD` -> loose ref -> packed-refs), so the check does not depend
    on a git binary; `git rev-parse HEAD` is the fallback. Returns None if HEAD cannot be
    resolved -- callers MUST treat that as a hard refusal, never as a pass.
    """
    git_dir = os.path.join(root, ".git")
    try:
        with open(os.path.join(git_dir, "HEAD"), "r", encoding="utf-8") as f:
            head = f.read().strip()
        if not head.startswith("ref:"):
            return head if _SHA1_RE.match(head) else None
        ref = head.split(":", 1)[1].strip()
        loose = os.path.join(git_dir, ref)
        if os.path.exists(loose):
            with open(loose, "r", encoding="utf-8") as f:
                sha = f.read().strip()
            if _SHA1_RE.match(sha):
                return sha
        packed = os.path.join(git_dir, "packed-refs")
        if os.path.exists(packed):
            with open(packed, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(("#", "^")):
                        continue
                    parts = line.split(" ", 1)
                    if len(parts) == 2 and parts[1].strip() == ref and _SHA1_RE.match(parts[0]):
                        return parts[0]
    except OSError:
        pass
    try:
        out = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=30)
        sha = out.stdout.strip()
        if out.returncode == 0 and _SHA1_RE.match(sha):
            return sha
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def require_authorized_execution_head(authorized_execution_head: Optional[str],
                                      root: str = ROOT_DEFAULT,
                                      actual_head: Optional[str] = None) -> str:
    """Fail closed unless an EXTERNALLY supplied authorized HEAD equals the actual git HEAD.

    This is the ONLY sanctioned source of the exact execution head. An apparatus provenance
    commit recorded in a manifest is historical context and can never substitute for it.
    Returns the verified sha; raises AuthorizedHeadError otherwise.
    """
    if authorized_execution_head is None or not str(authorized_execution_head).strip():
        raise AuthorizedHeadError(
            "authorized execution head not supplied: LIVE execution requires an external "
            "AUTHORIZED_EXECUTION_HEAD from the authorizing human (the manifest never "
            "self-declares the runtime HEAD)")
    head = str(authorized_execution_head).strip().lower()
    if not _SHA1_RE.match(head):
        raise AuthorizedHeadError(
            f"authorized execution head malformed (need a full 40-hex commit sha): "
            f"{authorized_execution_head!r}")
    actual = actual_head if actual_head is not None else resolve_git_head(root)
    if actual is None:
        raise AuthorizedHeadError("actual git HEAD could not be resolved; refusing to run")
    actual = actual.strip().lower()
    if actual != head:
        raise AuthorizedHeadError(
            f"authorized execution head mismatch: authorized {head} != actual git HEAD "
            f"{actual}")
    return actual


def assert_execution_head_policy(manifest: Dict[str, Any]) -> Tuple[str, str]:
    """Assert a manifest follows the externalized execution-head policy.

    Refuses a manifest that (a) still carries the self-referential `execution_head_expected`
    field, or (b) does not declare EXACT_EXECUTION_HEAD_SOURCE = EXTERNAL_HUMAN_AUTHORIZATION.
    Returns (apparatus_provenance_commit, exact_execution_head_source).
    """
    if SELF_REFERENTIAL_HEAD_FIELD in manifest:
        raise ProvenanceError(
            f"manifest carries the self-referential field {SELF_REFERENTIAL_HEAD_FIELD!r} "
            f"({manifest[SELF_REFERENTIAL_HEAD_FIELD]!r}); the exact execution head must come "
            f"from external human authorization, not from the manifest")
    source = manifest.get("exact_execution_head_source")
    if source != EXACT_EXECUTION_HEAD_SOURCE:
        raise ProvenanceError(
            f"manifest must declare exact_execution_head_source="
            f"{EXACT_EXECUTION_HEAD_SOURCE!r}; got {source!r}")
    apparatus = manifest.get("apparatus_provenance_commit")
    if not isinstance(apparatus, str) or not _SHA1_RE.match(apparatus):
        raise ProvenanceError(
            f"manifest must bind apparatus_provenance_commit as a 40-hex sha; got "
            f"{apparatus!r}")
    return apparatus, source


def version_stamp() -> Dict[str, Any]:
    return {
        "provenance_version": ITEM6_PROVENANCE_VERSION,
        "known_hash_schemes": sorted(KNOWN_HASH_SCHEMES),
        "hash_schemes_explicit": True,
        "hash_verifier_scheme_aware": True,
        "unknown_scheme_fails_closed": True,
        "exact_execution_head_source": EXACT_EXECUTION_HEAD_SOURCE,
        "apparatus_provenance_commit": APPARATUS_PROVENANCE_COMMIT,
        "self_referential_execution_head_supported": False,
        "makes_no_network_call": True,
    }
