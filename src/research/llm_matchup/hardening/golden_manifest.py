"""Frozen golden/live-smoke fixture manifest + generation-compatibility fingerprint
(V3 checkpoint mandate §2, §4, §5).

The golden_v3 smoke batch was interrupted mid-run by an external AWS Bedrock daily-token
quota. Before resuming later, we must be able to prove that whatever resumes is the SAME
experimental generation, not an accidental mix of pre- and post-edit observations. This
module:

  * computes a `generation_fingerprint` -- content hashes of every scientific input that
    must stay identical across a resume (prompt text, output schema, ontology, the
    neutralization transform's own source, the formation-structure table, the sampling
    parameters, model id/region, inference config);
  * freezes the deterministic fixture id list actually selected for the smoke batch (never
    regenerated -- `save_manifest_if_absent` refuses to overwrite an existing manifest);
  * exposes `check_compatible(frozen, current)` so a resume can ABORT_RESUME_GENERATION_MISMATCH
    instead of silently mixing generations.

`sampling_params.n` is explicitly EXCLUDED from the compatibility check: the smoke batch
`n` grew from 15 to 20 by strict prefix-extension during the interrupted run (never a
replacement of the original 15 -- `select_stratified` is prefix-stable in `n`), and a future
resume growing `n` further is a legitimate, approved extension, not a generation change.
Every other input must match exactly.


SOURCE BINDING (added by the source-binding repair)
---------------------------------------------------
The fingerprint must describe the code that is actually executing. It previously hashed
`sampling.py` and `neutralize_v3.py` through hardcoded `/home/ubuntu/...` paths, so an
independent checkout could run its own edited sources while this function certified the
DEPLOYED tree's bytes -- and `check_compatible` then reported `compatible: True`. Both
covered modules are now resolved from the loaded module objects, their origins verified
against this checkout, and only then hashed. See `current_generation_fingerprint` for the
exact contract and its limit.
"""
from __future__ import annotations
import hashlib
import json
import os

from src.research.llm_matchup import ontology as ONT
from src.research.llm_matchup.hardening import prompt_v4 as PR4
from src.research.llm_matchup.hardening import schema_v3 as SCH3
from src.research.llm_matchup.hardening import formation_structure as FS
from src.research.llm_matchup.hardening import versions_v3 as V3

OUT = "/home/ubuntu/research/llm_matchup/out/hardening_v3"
MANIFEST_PATH = os.path.join(OUT, "golden_v3_fixture_manifest.json")


class SourceBindingError(RuntimeError):
    """A covered scientific module was not loaded from THIS checkout.

    Raised before any fingerprint value is produced, so a fingerprint that would not
    describe the executing code is never returned, recorded or compared.
    """


#: This module's own canonical directory: <repo>/src/research/llm_matchup/hardening.
#: Derived from `__file__` and from nothing else -- no environment variable, no caller
#: argument and no hardcoded tree participates.
_HARDENING_DIR = os.path.dirname(os.path.realpath(__file__))

#: Where this module must sit relative to the repository root, used to derive the root and
#: then to re-verify the layout. A rename or a relocated package is an explicit failure,
#: never a silent hash of whatever happens to be on disk.
_HARDENING_RELPATH = os.path.join("src", "research", "llm_matchup", "hardening")

#: <repo>, canonicalised, derived by walking up from this module's own location.
REPO_ROOT = os.path.realpath(os.path.join(_HARDENING_DIR, *([os.pardir] * 4)))

#: The covered scientific source modules, as {import name: basename}. These are the two
#: inputs the fingerprint hashes from source FILES rather than from loaded state.
_COVERED_MODULES = {
    "src.research.llm_matchup.hardening.sampling": "sampling.py",
    "src.research.llm_matchup.hardening.neutralize_v3": "neutralize_v3.py",
}


def _expected_hardening_dir() -> str:
    """The hardening package's location implied by the derived root, re-verified.

    `REPO_ROOT` is derived by walking up from `_HARDENING_DIR`, so joining the relative
    path back on must return exactly `_HARDENING_DIR`. It will not if this file has been
    moved out of its expected repository-relative location, and that is an explicit
    failure rather than a fingerprint over an unexpected directory.
    """
    expected = os.path.realpath(os.path.join(REPO_ROOT, _HARDENING_RELPATH))
    if expected != _HARDENING_DIR:
        raise SourceBindingError(
            "inconsistent source binding: this module is at "
            f"{_HARDENING_DIR!r}, but the root derived from it ({REPO_ROOT!r}) implies "
            f"{expected!r}. Refusing to fingerprint an unverified layout.")
    return expected


def _verified_source_path(module, basename: str) -> str:
    """Canonical path of `module`'s source, proven to belong to THIS checkout.

    The check is on ORIGIN, not on content: a byte-identical copy of `sampling.py` loaded
    from another checkout is rejected, because the question this answers is "is the code
    that will run the code this fingerprint describes", not "do the bytes match".
    """
    origin = getattr(module, "__file__", None)
    if not origin:
        raise SourceBindingError(
            f"{module.__name__} has no __file__ (namespace package, frozen or extension "
            "module?), so its source origin cannot be verified.")
    origin = os.path.realpath(origin)
    expected = os.path.join(_expected_hardening_dir(), basename)
    if origin != expected:
        raise SourceBindingError(
            f"{module.__name__} was loaded from {origin!r}, but this checkout's copy is "
            f"{expected!r}. The generation fingerprint would describe code other than the "
            "code that is executing. Refusing to certify it.")
    if not os.path.isfile(origin):
        raise SourceBindingError(
            f"{module.__name__} resolves to {origin!r}, which is not a readable file.")
    return origin


def verify_source_binding() -> dict:
    """Verify every covered module's loaded origin and return {name: verified path}.

    Importing here rather than at module scope is deliberate: `sampling` pulls in the
    match corpus, and `golden_manifest` is imported by lightweight consumers that must not
    pay that cost. In the real resume path both modules are already imported, so this
    resolves them from `sys.modules` and verifies the objects actually in use.
    """
    import importlib

    verified = {}
    for dotted, basename in _COVERED_MODULES.items():
        module = importlib.import_module(dotted)
        verified[dotted] = _verified_source_path(module, basename)
    return verified


#: Retained as the public paths these hashes are taken from -- now bound to the executing
#: checkout instead of a hardcoded deployed tree. `controls_v3_core` and `golden_v3_sonnet46`
#: hash `NEUTRALIZE_MODULE_PATH` directly, so they are corrected by this binding too.
SAMPLING_MODULE_PATH = os.path.join(_HARDENING_DIR, "sampling.py")
NEUTRALIZE_MODULE_PATH = os.path.join(_HARDENING_DIR, "neutralize_v3.py")


def _sha256_file(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def current_generation_fingerprint(n: int, max_scan: int = 200, gen=V3) -> dict:
    """Every scientific input that must be IDENTICAL across a resume (checkpoint §5).

    `gen` selects the generation module (default `versions_v3` = Sonnet 4.5 arm). Because
    `bedrock_model_id` is part of the fingerprint, the Sonnet 4.6 arm is automatically a
    DISTINCT generation: a 4.6 result can never satisfy the 4.5 manifest's compatibility
    check, so tomorrow's 4.5 resume cannot be contaminated by today's 4.6 work.

    THE DECLARED CONTRACT
    ---------------------
    Two different situations, two different outcomes, neither of them silent:

    * A covered source is EDITED inside this checkout -> its hash changes -> the value
      returned here differs from the frozen manifest's, `check_compatible` reports a
      mismatch and a resume aborts ABORT_RESUME_GENERATION_MISMATCH. Ordinary drift.
    * A covered module is LOADED FROM A DIFFERENT CHECKOUT -> `SourceBindingError` is
      raised here, before any fingerprint exists. This fires even when the foreign bytes
      are identical, because origin, not content, is what is being established.

    A stale fingerprint is never silently retained, and there is no fallback: no
    `/home/ubuntu`, no environment-selected root, no second candidate directory.

    THE GUARANTEE, AND ITS LIMIT
    ----------------------------
    What is proven: the modules named in `_COVERED_MODULES` were imported from this
    checkout's own `hardening/` directory, and the bytes hashed are the bytes of those
    verified files as they are on disk at call time.

    What is NOT proven: that the in-memory code objects still correspond to those bytes.
    A module reloaded, monkeypatched or otherwise mutated after import would still pass,
    and the source file could be rewritten after this call. Source-file hashing cannot
    establish in-memory code identity, and this function does not claim to.
    """
    verified = verify_source_binding()
    sampling_src = verified["src.research.llm_matchup.hardening.sampling"]
    neutralize_src = verified["src.research.llm_matchup.hardening.neutralize_v3"]
    return {
        "version_stamp": gen.version_stamp(),
        "prompt_content_hash": PR4.prompt_content_hash(),
        "schema_content_hash": SCH3.schema_content_hash(),
        "ontology_content_hash": _sha256_json(ONT.to_dict()),
        "neutralization_module_hash": _sha256_file(neutralize_src),
        "formation_structure_hash": FS.structure_content_hash(),
        "sampling_module_hash": _sha256_file(sampling_src),
        "bedrock_model_id": gen.DEFAULT_BEDROCK_MODEL_ID,
        "bedrock_region": gen.DEFAULT_BEDROCK_REGION,
        "inference_config": gen.INFERENCE_CONFIG,
        "sampling_params": {"n": n, "max_scan": max_scan},
    }


def build_manifest(fixture_ids: list[str], n: int, max_scan: int = 200, gen=V3,
                   note: str | None = None) -> dict:
    fp = current_generation_fingerprint(n, max_scan, gen=gen)
    return {
        "study": "golden_v3_fixture_manifest",
        "generation_id": gen.GENERATION_ID,
        "n_fixtures": len(fixture_ids),
        "fixture_ids": fixture_ids,
        "fixture_manifest_hash": _sha256_json(fixture_ids),
        "generation_fingerprint": fp,
        "note": note or (
                "Deterministic stratified selection (hardening.sampling.select_stratified), "
                "prefix-stable in n. Ids 0-14 are byte-identical to the original n=15 golden "
                "smoke batch; ids 15-19 are an approved n=15->20 extension attempted under "
                "the SAME generation during the same interrupted run -- never a replacement "
                "of the original 15 (V3 checkpoint mandate SS2: never regenerate/replace)."),
    }


def load_manifest(manifest_path: str | None = None) -> dict | None:
    """Load a frozen fixture manifest.

    `manifest_path` defaults to the MODULE-LEVEL `MANIFEST_PATH` resolved AT CALL TIME, not
    at function-definition time. This is deliberate and load-bearing: binding the default in
    the signature (`manifest_path: str = MANIFEST_PATH`) snapshots the path at import and
    silently defeats `monkeypatch.setattr(GM, "MANIFEST_PATH", ...)`, which is how the
    offline resume tests isolate themselves from the real Sonnet 4.5 artifacts. That exact
    bug let `test_resume_aborts_when_no_manifest` load the REAL frozen 4.5 manifest, skip its
    intended ABORT_NO_FROZEN_MANIFEST path, and write fake OK attempts into the REAL 4.5
    execution ledger. Keep the None sentinel.
    """
    manifest_path = manifest_path or MANIFEST_PATH
    if not os.path.exists(manifest_path):
        return None
    return json.load(open(manifest_path))


def save_manifest_if_absent(manifest: dict, manifest_path: str | None = None) -> str:
    """Persist ONLY if no manifest exists yet. Freezing must never silently overwrite a
    prior frozen fixture set (checkpoint SS2: never regenerate the sample).

    `manifest_path` resolves the module-level default at CALL TIME -- see `load_manifest`.
    """
    manifest_path = manifest_path or MANIFEST_PATH
    if os.path.exists(manifest_path):
        return "EXISTS_UNCHANGED"
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    json.dump(manifest, open(manifest_path, "w"), indent=2, default=str)
    return "CREATED"


def check_compatible(frozen_manifest: dict, current_fingerprint: dict) -> dict:
    """Compare a frozen manifest's generation_fingerprint against a freshly computed one.
    `sampling_params` is intentionally excluded (see module docstring)."""
    ffp = frozen_manifest["generation_fingerprint"]
    mismatches = []
    for key in ffp:
        if key == "sampling_params":
            continue
        if ffp[key] != current_fingerprint.get(key):
            mismatches.append({"field": key, "frozen": ffp[key],
                               "current": current_fingerprint.get(key)})
    return {"compatible": len(mismatches) == 0, "mismatches": mismatches}
