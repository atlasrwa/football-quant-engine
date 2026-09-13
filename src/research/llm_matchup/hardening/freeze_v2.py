"""Freeze the hardened LLM_MATCHUP_V2 generation (patch §28, §29, §30, §54).

After hardening, we create a NEW frozen generation manifest — the exact instrument that Phase
C will (later) be allowed to use. It records and hashes:
  * Bedrock model identity (default + region);
  * prompt version + prompt CONTENT hash (sonnet_prompt_v3);
  * schema version + schema CONTENT hash (football_state_schema_v3);
  * validator module content hash (validator_v3);
  * ontology / cohort / packet / formation policy / family versions;
  * inference parameters + repeatability-call count + neutral-identifier default;
  * the generation_hash over all of the above (proves no silent change afterward);
  * the frozen B2 fixture selection hash (UNCHANGED — patch §30) so we prove the fixture
    universe was not cherry-picked;
  * the HARDENING_CONTROL_SET fixture ids (the stratified control fixtures used by the
    studies), kept SEPARATE from B2 (patch §30);
  * hashes of every hardening study artifact produced under out/hardening/.

Writes ONLY research/llm_matchup/out/FREEZE_LLM_MATCHUP_V2.json. Never mutates PHASE_B_V1 or
any Phase-B artifact. Re-running without --force refuses to overwrite (immutability) and emits
a drift re-verification side file, exactly like the Phase-B freeze.

Run: .venv/bin/python -m src.research.llm_matchup.hardening.freeze_v2 [--force]
"""
from __future__ import annotations
import os, sys, json, hashlib, subprocess, time, glob

from src.research.llm_matchup.hardening import versions_v2 as V2
from src.research.llm_matchup.hardening import prompt_v3 as PR3
from src.research.llm_matchup.hardening import schema_v3 as SCH3

ROOT = "/home/ubuntu"
OUT = os.path.join(ROOT, "research/llm_matchup/out")
HARD_OUT = os.path.join(OUT, "hardening")
SRC_DIR = os.path.join(ROOT, "src/research/llm_matchup/hardening")
FREEZE_PATH = os.path.join(OUT, "FREEZE_LLM_MATCHUP_V2.json")

# The hardened instrument source modules whose content defines the generation.
V2_MODULES = [
    "versions_v2.py", "prompt_v3.py", "schema_v3.py", "validator_v3.py", "adapter_v3.py",
    "neutralize.py", "repeatability.py", "sampling.py", "feature_matrix.py",
    "surrogate_ladder.py", "ablation_noise.py", "aggregate.py", "eligibility.py",
    "counter_golden.py",
]


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception as e:  # pragma: no cover
        return f"<git-error: {e}>"


def _read_json(path):
    try:
        return json.load(open(path))
    except Exception:
        return None


def _control_set_ids() -> list[str]:
    """The HARDENING_CONTROL_SET = distinct fixtures actually exercised by the hardening
    studies (read from the call manifest). Kept SEPARATE from the frozen B2 universe (§30)."""
    ids = set()
    man = os.path.join(HARD_OUT, "hardened_call_manifest.csv")
    if os.path.exists(man):
        import csv
        for r in csv.DictReader(open(man)):
            fid = r.get("fixture_id")
            if fid:
                ids.add(fid)
    return sorted(ids)


def build_manifest() -> dict:
    prompt_hash = PR3.prompt_content_hash()
    schema_hash = SCH3.schema_content_hash()
    content_hashes = {m: (_sha256_file(os.path.join(SRC_DIR, m))
                          if os.path.exists(os.path.join(SRC_DIR, m)) else None)
                      for m in V2_MODULES}
    gen_hash = V2.generation_hash(extra={"prompt_content": prompt_hash,
                                         "schema_content": schema_hash,
                                         "module_hashes": content_hashes})

    # frozen B2 selection (UNCHANGED — patch §30)
    b2_sel = _read_json(os.path.join(OUT, "b2_selection.json")) or {}
    phase_b_freeze = _read_json(os.path.join(OUT, "FREEZE_PHASE_B_V1.json")) or {}

    # hardening artifact hashes
    artifact_hashes = {}
    for p in sorted(glob.glob(os.path.join(HARD_OUT, "*"))):
        if os.path.isfile(p):
            artifact_hashes[os.path.basename(p)] = _sha256_file(p)

    manifest = {
        "generation_id": V2.GENERATION_ID,
        "frozen_unix": int(time.time()),
        "note": ("Hardened LLM measurement instrument. Frozen BEFORE Phase C. No silent "
                 "change afterward (any prompt/schema/ontology/validator edit => new "
                 "generation). Upstream of the probability engine (patch §2)."),
        "git": {"commit": _git("rev-parse", "HEAD"),
                "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
                "head_subject": _git("log", "-1", "--pretty=%s")},
        "version_identity": V2.version_stamp(),
        "bedrock": {"default_model_id": V2.DEFAULT_BEDROCK_MODEL_ID,
                    "region": V2.DEFAULT_BEDROCK_REGION,
                    "inference_config": V2.INFERENCE_CONFIG,
                    "repeatability_calls": V2.REPEATABILITY_CALLS,
                    "neutral_identifiers_default": V2.NEUTRAL_IDENTIFIERS_DEFAULT},
        "prompt_content_hash": prompt_hash,
        "schema_content_hash": schema_hash,
        "module_content_hashes": content_hashes,
        "generation_hash": gen_hash,
        "b2_selection": {
            "selection_hash": b2_sel.get("selection_hash"),
            "n_selected": b2_sel.get("n_selected"),
            "note": "UNCHANGED frozen B2 universe (patch §30 — not cherry-picked)",
        },
        "phase_b_v1_freeze_hash": phase_b_freeze.get("freeze_hash"),
        "hardening_control_set": _control_set_ids(),
        "hardening_artifact_hashes": artifact_hashes,
    }
    manifest["freeze_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items() if k != "freeze_hash"},
                   sort_keys=True, default=str).encode()).hexdigest()
    return manifest


def freeze(force: bool = False) -> dict:
    os.makedirs(OUT, exist_ok=True)
    manifest = build_manifest()
    if os.path.exists(FREEZE_PATH) and not force:
        existing = _read_json(FREEZE_PATH) or {}
        drift = existing.get("generation_hash") != manifest["generation_hash"]
        side = os.path.join(OUT, f"FREEZE_LLM_MATCHUP_V2.reverify.{manifest['frozen_unix']}.json")
        json.dump({"existing_generation_hash": existing.get("generation_hash"),
                   "recomputed_generation_hash": manifest["generation_hash"],
                   "instrument_drift_detected": drift, "recomputed": manifest},
                  open(side, "w"), indent=2, default=str)
        print(json.dumps({"action": "reverify", "existing": FREEZE_PATH,
                          "instrument_drift_detected": drift, "side_file": side}, indent=2))
        return existing
    json.dump(manifest, open(FREEZE_PATH, "w"), indent=2, default=str)
    print(json.dumps({"action": "frozen", "path": FREEZE_PATH,
                      "generation_id": V2.GENERATION_ID,
                      "generation_hash": manifest["generation_hash"],
                      "freeze_hash": manifest["freeze_hash"],
                      "n_control_fixtures": len(manifest["hardening_control_set"]),
                      "b2_selection_hash": manifest["b2_selection"]["selection_hash"]}, indent=2))
    return manifest


if __name__ == "__main__":
    freeze(force="--force" in sys.argv)
