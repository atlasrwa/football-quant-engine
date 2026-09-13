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

_SRC = "/home/ubuntu/src/research/llm_matchup/hardening"
SAMPLING_MODULE_PATH = os.path.join(_SRC, "sampling.py")
NEUTRALIZE_MODULE_PATH = os.path.join(_SRC, "neutralize_v3.py")


def _sha256_file(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def current_generation_fingerprint(n: int, max_scan: int = 200) -> dict:
    """Every scientific input that must be IDENTICAL across a resume (checkpoint §5)."""
    return {
        "version_stamp": V3.version_stamp(),
        "prompt_content_hash": PR4.prompt_content_hash(),
        "schema_content_hash": SCH3.schema_content_hash(),
        "ontology_content_hash": _sha256_json(ONT.to_dict()),
        "neutralization_module_hash": _sha256_file(NEUTRALIZE_MODULE_PATH),
        "formation_structure_hash": FS.structure_content_hash(),
        "sampling_module_hash": _sha256_file(SAMPLING_MODULE_PATH),
        "bedrock_model_id": V3.DEFAULT_BEDROCK_MODEL_ID,
        "bedrock_region": V3.DEFAULT_BEDROCK_REGION,
        "inference_config": V3.INFERENCE_CONFIG,
        "sampling_params": {"n": n, "max_scan": max_scan},
    }


def build_manifest(fixture_ids: list[str], n: int, max_scan: int = 200) -> dict:
    fp = current_generation_fingerprint(n, max_scan)
    return {
        "study": "golden_v3_fixture_manifest",
        "generation_id": V3.GENERATION_ID,
        "n_fixtures": len(fixture_ids),
        "fixture_ids": fixture_ids,
        "fixture_manifest_hash": _sha256_json(fixture_ids),
        "generation_fingerprint": fp,
        "note": ("Deterministic stratified selection (hardening.sampling.select_stratified), "
                "prefix-stable in n. Ids 0-14 are byte-identical to the original n=15 golden "
                "smoke batch; ids 15-19 are an approved n=15->20 extension attempted under "
                "the SAME generation during the same interrupted run -- never a replacement "
                "of the original 15 (V3 checkpoint mandate SS2: never regenerate/replace)."),
    }


def load_manifest() -> dict | None:
    if not os.path.exists(MANIFEST_PATH):
        return None
    return json.load(open(MANIFEST_PATH))


def save_manifest_if_absent(manifest: dict) -> str:
    """Persist ONLY if no manifest exists yet. Freezing must never silently overwrite a
    prior frozen fixture set (checkpoint SS2: never regenerate the sample)."""
    if os.path.exists(MANIFEST_PATH):
        return "EXISTS_UNCHANGED"
    os.makedirs(OUT, exist_ok=True)
    json.dump(manifest, open(MANIFEST_PATH, "w"), indent=2, default=str)
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
