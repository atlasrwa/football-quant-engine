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
#: The V8C modules bound into every receipt, by bare name (back-compat surface).
BOUND_MODULES = ("grammar", "pit_context", "historical_pit", "historical_similarity",
                 "compiler", "scorer", "cohort_stats", "pre_t", "universe", "controls",
                 "control_coverage", "aggregate", "aggregate_blocks", "blind_index",
                 "select_freeze", "score_frozen", "packet", "runner", "prompt", "anchor",
                 "structural_diagnostics", "bundle_gate",
                 "cache", "vintage", "receipt", "live_reachability", "env_semantics",
                 "freeze", "defect_ledger", "provenance", "golden", "harness")

#: EVERY source file whose bytes can change a measured result, by CANONICAL REPOSITORY PATH.
#:
#: Binding only `hypothesis_v8c/*` was not a binding of the scientific code. The compiler
#: delegates to `hypothesis_v71.compiler`, the similarity spec lives in `hypothesis_v7`, the
#: corpus is normalised by `matchup.corpus` and the provider adapters under `scripts/`, and
#: the capability contract is parsed by `hypothesis_v71.capability`. A change to any of them
#: changes what the engine measures while leaving a v8c-only anchor perfectly valid.
#:
#: `historical_similarity` and `prompt` were the two most load-bearing omissions: the first
#: decides historical cohort membership, the second is the exact text and tool schema the
#: model is shown.
BOUND_SOURCES = tuple(sorted(
    [f"src/research/hypothesis_v8c/{m}.py" for m in BOUND_MODULES]
    + [
        # ---- upstream scientific dependencies the v8c path calls into ----
        "src/research/hypothesis_v71/capability.py",
        "src/research/hypothesis_v71/compiler.py",
        "src/research/hypothesis_v71/corpus_index.py",
        "src/research/hypothesis_v71/engine.py",
        "src/research/hypothesis_v71/estimator.py",
        "src/research/hypothesis_v71/execution.py",
        "src/research/hypothesis_v71/invariants.py",
        "src/research/hypothesis_v71/ir.py",
        "src/research/hypothesis_v71/leakage.py",
        "src/research/hypothesis_v71/recency.py",
        "src/research/hypothesis_v71/similarity.py",
        "src/research/hypothesis_v7/similarity.py",
        "src/research/hypothesis_v7/pit.py",
        "src/research/hypothesis_v7/leakage.py",
        "src/research/hypothesis_v8b1/controls.py",
        "src/research/hypothesis_v8b1/search.py",
        # ---- loader / normaliser: what a "record" IS ----
        "src/research/matchup/corpus.py",
        "scripts/multisrc_corpus.py",
        "scripts/championship_adapter.py",
    ]))

#: The sources the SCORING process must actually have imported. Every one of these is
#: required to be loaded AND to match; a bound source outside this set is verified against the
#: commit but is legitimately not imported by process 2 (e.g. `control_coverage`, `golden`),
#: and is reported as git-verified-only rather than silently counted as executing-verified.
REQUIRED_EXECUTING_SOURCES = tuple(sorted([
    "src/research/hypothesis_v8c/anchor.py",
    "src/research/hypothesis_v8c/aggregate.py",
    "src/research/hypothesis_v8c/aggregate_blocks.py",
    "src/research/hypothesis_v8c/blind_index.py",
    "src/research/hypothesis_v8c/cache.py",
    "src/research/hypothesis_v8c/cohort_stats.py",
    "src/research/hypothesis_v8c/compiler.py",
    "src/research/hypothesis_v8c/grammar.py",
    "src/research/hypothesis_v8c/historical_pit.py",
    "src/research/hypothesis_v8c/historical_similarity.py",
    "src/research/hypothesis_v8c/packet.py",
    "src/research/hypothesis_v8c/pit_context.py",
    "src/research/hypothesis_v8c/pre_t.py",
    "src/research/hypothesis_v8c/prompt.py",
    "src/research/hypothesis_v8c/receipt.py",
    "src/research/hypothesis_v8c/runner.py",
    "src/research/hypothesis_v8c/score_frozen.py",
    "src/research/hypothesis_v8c/structural_diagnostics.py",
    "src/research/hypothesis_v8c/scorer.py",
    "src/research/hypothesis_v8c/select_freeze.py",
    "src/research/hypothesis_v8c/universe.py",
    "src/research/hypothesis_v8c/vintage.py",
    "src/research/hypothesis_v71/capability.py",
    "src/research/hypothesis_v71/compiler.py",
    "src/research/hypothesis_v71/corpus_index.py",
    "src/research/hypothesis_v71/invariants.py",
    "src/research/hypothesis_v71/similarity.py",
    "src/research/hypothesis_v7/similarity.py",
    "src/research/matchup/corpus.py",
]))

#: Import path -> repo path, for the executing-code check.
MODULE_PATH_FOR = {
    rel[len("src/"):].replace("/", ".")[:-3].replace("research.", "src.research.", 1): rel
    for rel in BOUND_SOURCES if rel.startswith("src/")}


#: The checkout this module is executing from. Derived from the module's own location, not
#: hardcoded, so the producer-code binding follows the interpreter rather than one machine's
#: path. `V8C_ROOT` overrides it for a relocated tree. A hardcoded "/home/ubuntu" here meant a
#: clean checkout elsewhere would hash THAT tree's modules while running its own -- which is
#: precisely the substitution the three-way binding exists to catch.
ROOT = os.environ.get(
    "V8C_ROOT",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))))


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
    for rel in BOUND_SOURCES:
        p = f"{ROOT}/{rel}"
        out[rel] = sha_file_bytes(p) if os.path.exists(p) else None
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
