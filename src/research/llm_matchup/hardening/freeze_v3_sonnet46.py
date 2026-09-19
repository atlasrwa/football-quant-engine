"""Freeze the LLM_MATCHUP_V3_SONNET46 generation — the Sonnet 4.6 arm's scientific record.

Writes ONLY research/llm_matchup/out/FREEZE_LLM_MATCHUP_V3_SONNET46.json.

NEVER touches, and must never be made to touch:
  * research/llm_matchup/out/FREEZE_LLM_MATCHUP_V2.json          (the V2 generation's freeze)
  * research/llm_matchup/out/V3_CHECKPOINT.md                    (the 4.5 arm's checkpoint)
  * research/llm_matchup/out/hardening_v3/**                     (the 4.5 arm's artifacts)
A separate freeze path is asserted at runtime, so a rename cannot silently collide.

Records, per the mandate:
  * the EXACT resolved Bedrock model identity actually observed in the live calls (not merely
    the requested id), plus the requested profile id, ARN, region and inference config;
  * every shared content hash (prompt / output schema / ontology / neutralization module /
    formation structure / sampling module) so the single-variable claim is machine-checkable;
  * the inherited fixture manifest hash, proving the same 20 fixtures as the 4.5 arm;
  * the explicit diff vs the 4.5 arm (must be model id + generation id only);
  * content hashes of every 4.6 artifact produced;
  * the git commit/branch and working-tree state at freeze time;
  * an honest completeness block: which parts of the validation sequence ran, which did not,
    and why. A freeze must never imply more evidence than was collected.

Re-running without --force refuses to overwrite and instead emits a drift re-verification side
file, exactly like freeze_v2.
"""
from __future__ import annotations
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

from src.research.llm_matchup.hardening import controls_v3_sonnet46 as C46
from src.research.llm_matchup.hardening import golden_manifest as GM
from src.research.llm_matchup.hardening import golden_v3_sonnet46 as G46
from src.research.llm_matchup.hardening import versions_v3 as V45
from src.research.llm_matchup.hardening import versions_v3_sonnet46 as V46

ROOT = "/home/ubuntu"
OUT = os.path.join(ROOT, "research/llm_matchup/out")
SRC_DIR = os.path.join(ROOT, "src/research/llm_matchup/hardening")
FREEZE_PATH = os.path.join(OUT, "FREEZE_LLM_MATCHUP_V3_SONNET46.json")

# Paths this module must NEVER write. (V3_CHECKPOINT.md lives in research/llm_matchup/, NOT
# in research/llm_matchup/out/ -- an earlier version of this list had it in the wrong place,
# which meant the guard silently protected a non-existent path.)
PROTECTED = (
    os.path.join(OUT, "FREEZE_LLM_MATCHUP_V2.json"),
    os.path.join(ROOT, "research/llm_matchup/V3_CHECKPOINT.md"),
    os.path.join(OUT, "hardening_v3"),
)

# The 4.6 instrument's source modules. Note versions_v3.py / prompt_v4.py / schema_v3.py /
# validator_v3.py / neutralize_v3.py are SHARED with the 4.5 arm by design -- hashing them here
# records that they were unchanged, it does not claim ownership of them.
MODULES = [
    "versions_v3.py", "versions_v3_sonnet46.py", "prompt_v4.py", "schema_v3.py",
    "validator_v3.py", "adapter_v4.py", "neutralize_v3.py", "formation_structure.py",
    "repeatability.py", "ablation_noise.py", "sampling.py", "golden_manifest.py",
    "golden_v3_sonnet46.py", "controls_v3_sonnet46.py", "audit_prespend.py",
    "audit_request.py", "counter_golden.py", "eligibility.py",
    "eligibility_v3_sonnet46.py",
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
    except Exception as e:
        return f"<git-error: {e}>"


def _read_json(path):
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path))
    except Exception:
        return None


def _observed_model_identities() -> dict:
    """The model identity ACTUALLY observed in live 4.6 responses, from the ledger. This is the
    authoritative record: the requested id is an intention, the resolved id is an observation."""
    ledger = G46.load_ledger()
    requested, resolved = set(), set()
    for e in (ledger.get("fixtures") or {}).values():
        for a in e.get("attempts", []) or []:
            if a.get("model_id"):
                requested.add(a["model_id"])
            if a.get("resolved_model_id"):
                resolved.add(a["resolved_model_id"])
    return {
        "requested_model_ids_observed": sorted(requested),
        "resolved_model_ids_observed": sorted(resolved),
        "single_model_identity_confirmed": len(resolved) == 1,
    }


def build_manifest() -> dict:
    m46 = G46.build_or_load_manifest()
    frozen45 = GM.load_manifest(G46.SONNET45_MANIFEST_PATH) or {}
    summary = _read_json(G46.SUMMARY_PATH) or {}
    controls = _read_json(C46.CONTROLS_PATH) or {}
    repeat = _read_json(C46.REPEAT_PATH) or {}
    counter = _read_json(C46.COUNTER_PATH) or {}
    prespend = _read_json(G46.PRESPEND_AUDIT_PATH) or {}
    elig = _read_json(os.path.join(G46.OUT, "golden_v3_sonnet46_eligibility.json")) or {}

    module_hashes = {}
    for mod in MODULES:
        p = os.path.join(SRC_DIR, mod)
        if os.path.exists(p):
            module_hashes[mod] = _sha256_file(p)

    artifact_hashes = {}
    for p in sorted(glob.glob(os.path.join(G46.OUT, "*"))):
        if os.path.isfile(p):
            artifact_hashes[os.path.basename(p)] = _sha256_file(p)

    version_payload = {
        "version_stamp": V46.version_stamp(),
        "content_hashes": G46.content_hashes(),
        "bedrock": {
            "requested_model_id": V46.DEFAULT_BEDROCK_MODEL_ID,
            "inference_profile_arn": V46.BEDROCK_INFERENCE_PROFILE_ARN,
            "base_model_id": V46.BEDROCK_BASE_MODEL_ID,
            "region": V46.DEFAULT_BEDROCK_REGION,
            "inference_config": V46.INFERENCE_CONFIG,
            "model_id_is_date_pinned": V46.MODEL_ID_IS_DATE_PINNED,
        },
        "fixture_manifest_hash": m46["fixture_manifest_hash"],
        "module_hashes": module_hashes,
    }
    generation_hash = hashlib.sha256(
        json.dumps(version_payload, sort_keys=True, default=str).encode()).hexdigest()

    # --- honest completeness accounting ------------------------------------------------
    completeness = {
        "prespend_audit": bool(prespend) and prespend.get("all_clean") is True,
        "golden_batch": bool(summary),
        "identity_controls": bool(controls),
        "repeatability": bool(repeat),
        "behavior_sensitivity": bool(controls.get("controls", {}).get(
            "D_behavior_sensitivity_formation_ablation")),
        "counter_evidence": bool(counter),
        "mechanism_eligibility": bool(elig),
        "surrogate_analysis": False,
        "phase_c": False,
    }

    manifest = {
        "freeze": "FREEZE_LLM_MATCHUP_V3_SONNET46",
        "generation_id": V46.GENERATION_ID,
        "arm": "SONNET_4_6",
        "parallel_arm": {
            "generation_id": V45.GENERATION_ID,
            "status": "FROZEN_AND_UNTOUCHED_BY_THIS_FREEZE",
            "note": ("The Sonnet 4.5 arm is a SEPARATE scientific generation with its own "
                     "manifest, ledger, cache and artifacts. This freeze neither reads nor "
                     "writes its results, other than inheriting its fixture id list."),
            "inherited_fixture_manifest_hash": frozen45.get("fixture_manifest_hash"),
        },
        **version_payload,
        "generation_hash": generation_hash,
        "model_identity_observed": _observed_model_identities(),
        "single_variable_proof": {
            "diff_vs_sonnet45": V46.diff_vs_v45(),
            "fingerprint_diff_vs_frozen_45_manifest": G46.manifest_vs_45_fingerprint_diff(),
            "fixture_selection_identical_to_45": (
                m46["fixture_manifest_hash"] == frozen45.get("fixture_manifest_hash")),
            "fixture_ids_identical_to_45": (
                m46.get("fixture_ids") == frozen45.get("fixture_ids")),
        },
        "results": {
            "golden_counts": summary.get("counts"),
            "golden_acceptance": summary.get("acceptance"),
            "tokens": summary.get("tokens"),
            "latency_s": summary.get("latency_s"),
            "cost_usd_estimate": summary.get("cost_usd_estimate"),
            "state_metrics_distribution": summary.get("state_metrics_distribution"),
            "rates": summary.get("rates"),
            "identity_gate": controls.get("identity_gate"),
            "controls_headline": {
                k: {kk: vv for kk, vv in v.items() if kk != "rows"}
                for k, v in (controls.get("controls") or {}).items()
            },
            "interpretation": controls.get("interpretation"),
            "repeatability_pooled": repeat.get("pooled"),
            "self_noise_pooled": repeat.get("self_noise_pooled"),
            "counter_evidence": {k: v for k, v in counter.items()
                                 if k not in ("rows", "call_log")},
            "eligibility": {k: v for k, v in elig.items() if k != "rows"},
        },
        "prespend_audit": {k: v for k, v in prespend.items() if k != "reports"},
        "artifact_hashes": artifact_hashes,
        "completeness": completeness,
        "phase_c_status": {
            "fed_into_phase_c": False,
            "champion_modified": False,
            "contextual_challenger_modified": False,
            "note": ("Mandate SS28: Phase C was deliberately NOT touched. Nothing here has "
                     "been promoted, and no predictive evaluation was performed. Predictive "
                     "value remains an open Phase-C question."),
        },
        "git": {
            "branch": _git("branch", "--show-current"),
            "head": _git("rev-parse", "HEAD"),
            "dirty_paths_llm_matchup": _git("status", "--short", "--",
                                            "src/research/llm_matchup", "research/llm_matchup"),
        },
        "frozen_unix": int(time.time()),
    }
    manifest["freeze_hash"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, default=str).encode()).hexdigest()
    return manifest


def freeze(force: bool = False) -> dict:
    # Hard guard: this module writes exactly one path, and never a protected one.
    assert FREEZE_PATH not in PROTECTED
    for p in PROTECTED:
        assert os.path.abspath(FREEZE_PATH) != os.path.abspath(p), f"refusing to write {p}"
        assert not os.path.abspath(FREEZE_PATH).startswith(os.path.abspath(p) + os.sep)

    os.makedirs(OUT, exist_ok=True)
    manifest = build_manifest()
    if os.path.exists(FREEZE_PATH) and not force:
        existing = _read_json(FREEZE_PATH) or {}
        drift = existing.get("generation_hash") != manifest["generation_hash"]
        side = os.path.join(
            OUT, f"FREEZE_LLM_MATCHUP_V3_SONNET46.reverify.{manifest['frozen_unix']}.json")
        json.dump({"existing_generation_hash": existing.get("generation_hash"),
                   "recomputed_generation_hash": manifest["generation_hash"],
                   "instrument_drift_detected": drift, "recomputed": manifest},
                  open(side, "w"), indent=2, default=str)
        print(json.dumps({"action": "reverify", "existing": FREEZE_PATH,
                          "instrument_drift_detected": drift, "side_file": side}, indent=2))
        return existing
    json.dump(manifest, open(FREEZE_PATH, "w"), indent=2, default=str)
    print(json.dumps({"action": "frozen", "path": FREEZE_PATH,
                      "generation_id": manifest["generation_id"],
                      "generation_hash": manifest["generation_hash"],
                      "freeze_hash": manifest["freeze_hash"],
                      "resolved_model_ids": manifest["model_identity_observed"][
                          "resolved_model_ids_observed"],
                      "completeness": manifest["completeness"]}, indent=2))
    return manifest


if __name__ == "__main__":
    freeze(force="--force" in sys.argv)
