"""V8C freeze receipt (`v8c_receipt_v1`) -- repairs P0-B.

THE DEFECT
----------
A self-hashed JSON is tamper-EVIDENT only if its claimed hash is anchored somewhere the editor
does not control. `score_frozen` verified the freeze against the hash stored INSIDE the freeze,
so anyone who edited the payload could recompute that field and the check would pass. The
freeze was self-certifying.

THE ANCHOR
----------
A `FreezeReceipt` is written SEPARATELY from the freeze and records:

    freeze_sha256          the hash of the freeze FILE BYTES -- not a field inside it
    producer_git_commit    `git rev-parse HEAD` of the process that produced the freeze
    producer_code_hashes   sha256 of every V8C module that took part
    corpus_hash            the data vintage the selection saw
    capability_hash        the provider contract it saw
    manifest_cohort_hash   the ordered cohort identity
    created_utc, classification
    receipt_hash           over all of the above

Process 2 requires the receipt and verifies the freeze's FILE BYTES against
`receipt.freeze_sha256`. Editing the freeze and recomputing its internal self-hash no longer
helps: the receipt is a separate artifact, and editing the receipt changes `receipt_hash`.

This is a two-file anchor, not a cryptographic notary. It defeats accidental and casual
tampering and makes deliberate tampering require editing two artifacts consistently -- which
a reviewer can detect because the receipt carries the producing commit, and that commit's code
hashes must reproduce. For a stronger anchor, commit the receipt to git: the commit object then
carries the freeze hash into an append-only history.

ZERO SPEND. Reads no target outcome.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import subprocess

RECEIPT_VERSION = "v8c_receipt_v1"

#: Modules whose content is bound into every receipt.
BOUND_MODULES = ("grammar", "pit_context", "historical_pit", "compiler", "scorer",
                 "cohort_stats", "pre_t", "universe", "controls", "aggregate",
                 "blind_index", "select_freeze", "score_frozen", "packet", "runner",
                 "cache", "vintage", "receipt")

ROOT = "/home/ubuntu"


class ReceiptError(Exception):
    """The receipt is missing, malformed, or does not match the freeze. Nothing is scored."""


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file_bytes(path: str) -> str:
    with open(path, "rb") as f:
        return _sha_bytes(f.read())


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def code_hashes() -> dict:
    out = {}
    for m in BOUND_MODULES:
        p = f"{ROOT}/src/research/hypothesis_v8c/{m}.py"
        out[m] = sha_file_bytes(p) if os.path.exists(p) else None
    return out


def cohort_hash(fixture_ids_ordered) -> str:
    return hashlib.sha256(
        json.dumps([str(f) for f in fixture_ids_ordered], default=str).encode()).hexdigest()


def build_receipt(*, freeze_path, corpus_hash, capability_hash, fixture_ids_ordered,
                  classification, extra=None) -> dict:
    r = {
        "receipt_version": RECEIPT_VERSION,
        "freeze_sha256": sha_file_bytes(freeze_path),
        "freeze_filename": os.path.basename(freeze_path),
        "producer_git_commit": git_commit(),
        "producer_code_hashes": code_hashes(),
        "corpus_hash": corpus_hash,
        "capability_hash": capability_hash,
        "manifest_cohort_hash": cohort_hash(fixture_ids_ordered),
        "n_fixtures": len(list(fixture_ids_ordered)),
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "classification": classification,
    }
    if extra:
        r["extra"] = extra
    r["receipt_hash"] = _receipt_hash(r)
    return r


def _receipt_hash(r: dict) -> str:
    core = {k: v for k, v in r.items() if k != "receipt_hash"}
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def write_receipt(receipt: dict, path: str) -> str:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(receipt, f, indent=1, default=str, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return receipt["receipt_hash"]


def verify_receipt(receipt_path: str, freeze_path: str, *, require_commit=None) -> dict:
    """Verify the receipt is internally consistent AND matches the freeze FILE BYTES.

    Raises before any caller can proceed to open an outcome.
    """
    if not os.path.exists(receipt_path):
        raise ReceiptError(f"no freeze receipt at {receipt_path}: refusing to score")
    receipt = json.load(open(receipt_path))

    claimed = receipt.get("receipt_hash")
    if not claimed or claimed != _receipt_hash(receipt):
        raise ReceiptError("receipt_hash does not match the receipt's own content: "
                           "the receipt was edited")

    actual = sha_file_bytes(freeze_path)
    if actual != receipt.get("freeze_sha256"):
        raise ReceiptError(
            f"freeze file bytes {actual} do not match the receipt's freeze_sha256 "
            f"{receipt.get('freeze_sha256')}: the freeze was edited after it was anchored")

    if require_commit and receipt.get("producer_git_commit") != require_commit:
        raise ReceiptError(
            f"receipt was produced at commit {receipt.get('producer_git_commit')}, "
            f"required {require_commit}")
    return receipt


def version_stamp() -> dict:
    return {"receipt_version": RECEIPT_VERSION,
            "repairs": ["P0-B"],
            "anchors": "freeze FILE BYTES, in a separate artifact",
            "why": ("a self-hashed JSON is tamper-evident only if its claimed hash is "
                    "anchored outside the payload the editor controls"),
            "bound_modules": list(BOUND_MODULES),
            "carries_producer_commit": True,
            "scoring_requires_receipt": True}
