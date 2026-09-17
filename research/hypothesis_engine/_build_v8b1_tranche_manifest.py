"""Builds and freezes V8B1_TRANCHE_50_MANIFEST.json -- the preregistered 50-fixture operational
tranche, derived deterministically from the already-frozen V8B1_FIXTURE_MANIFEST.

Selection rule (deterministic, no randomness, no manual choice): walk V8B1_FIXTURE_MANIFEST
fixtures in their canonical stored order, skip the 3 declared T2 canary fixtures, take the
FIRST 50 remaining. No replacement, no reordering.

Records source manifest path+hash, exclusion list, selection rule, the exact ordered 50 IDs,
runner/version/model-config hashes, and a tranche-manifest content hash. Read-only w.r.t. the
model. No spend. Does NOT embed git_head (so re-running to verify is safe and idempotent).
"""
from __future__ import annotations

import hashlib
import json

ROOT = "/home/ubuntu"

SOURCE_MANIFEST = "research/hypothesis_engine/V8B1_FIXTURE_MANIFEST.json"
MODEL_CONFIG = "research/hypothesis_engine/V8B1_MODEL_CONFIG.json"
RUNNER_MODULE = "src/research/hypothesis_v8b1/runner.py"
SEARCH_MODULE = "src/research/hypothesis_v8b1/search.py"
PACKET_MODULE = "src/research/hypothesis_v8b1/packet.py"
PROMPT_MODULE = "src/research/hypothesis_v8b1/prompt.py"
CONTROLS_MODULE = "src/research/hypothesis_v8b1/controls.py"
SCORER_MODULE = "src/research/hypothesis_v8b1/scorer.py"
FREEZE_CHAIN = "research/hypothesis_engine/V8B1_PRESPEND_FREEZE_CHAIN.json"
CHAMPION_ARTIFACT = "data/discovery/pilotC_stat_mixer.json"

T2_CANARY_EXCLUSIONS = ["mt_012232342", "mt_406686877", "mt_581141428"]
N_TRANCHE = 50


def _sha(path):
    with open(f"{ROOT}/{path}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def build() -> dict:
    src = json.load(open(f"{ROOT}/{SOURCE_MANIFEST}"))
    excl = set(T2_CANARY_EXCLUSIONS)

    ordered_ids = []
    for f in src["fixtures"]:
        fid = f["fixture_id"]
        if fid in excl:
            continue
        ordered_ids.append(fid)
        if len(ordered_ids) == N_TRANCHE:
            break

    if len(ordered_ids) != N_TRANCHE:
        raise SystemExit(f"could not select {N_TRANCHE} fixtures (got {len(ordered_ids)})")

    # sanity: exclusions really were skipped and no duplicates
    assert not (set(ordered_ids) & excl), "an excluded T2 canary leaked into the tranche"
    assert len(set(ordered_ids)) == N_TRANCHE, "duplicate fixture id in tranche"

    # sonnet model_config resolved config stamp (the exact inference config the runner uses)
    mc = json.load(open(f"{ROOT}/{MODEL_CONFIG}"))
    cfg = mc["chosen_configuration"]
    config_stamp = {"max_tokens": cfg["max_tokens"], "temperature": cfg["temperature"],
                    "thinking": cfg["thinking"]}

    import sys
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from src.research.hypothesis_v8b1 import runner as RN
    runner_vs = RN.version_stamp()

    chain = json.load(open(f"{ROOT}/{FREEZE_CHAIN}"))

    manifest = {
        "tranche_manifest_version": "v8b1_tranche_50_manifest_v1",
        "purpose": "preregistered 50-fixture V8B.1 operational tranche (real experiment; "
                   "selections frozen, target outcomes sealed)",
        "source_manifest": SOURCE_MANIFEST,
        "source_manifest_hash_recomputed": _sha(SOURCE_MANIFEST),
        "source_manifest_declared_hash": src.get("manifest_hash"),
        "t2_canary_exclusions": T2_CANARY_EXCLUSIONS,
        "selection_rule": ("walk V8B1_FIXTURE_MANIFEST fixtures in canonical stored order, skip "
                           "the 3 T2 canary exclusions, take the first 50 remaining; no "
                           "randomness, no manual selection, no replacement, no reordering"),
        "n_tranche": N_TRANCHE,
        "fixture_ids_ordered": ordered_ids,
        "runner_version_stamp": runner_vs,
        "config_stamp": config_stamp,
        "model_id": mc["model_id"],
        "region": mc["region"],
        "component_hashes": {
            RUNNER_MODULE: _sha(RUNNER_MODULE),
            SEARCH_MODULE: _sha(SEARCH_MODULE),
            PACKET_MODULE: _sha(PACKET_MODULE),
            PROMPT_MODULE: _sha(PROMPT_MODULE),
            CONTROLS_MODULE: _sha(CONTROLS_MODULE),
            SCORER_MODULE: _sha(SCORER_MODULE),
        },
        "freeze_chain_head": chain["head"],
        "champion_artifact": CHAMPION_ARTIFACT,
        "champion_artifact_sha256": _sha(CHAMPION_ARTIFACT),
        "champion_artifact_sha256_expected":
            "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9",
        "target_outcomes_viewed": False,
        "selections_will_be_frozen_outcomes_sealed": True,
    }
    manifest["tranche_manifest_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items() if k != "tranche_manifest_hash"},
                   sort_keys=True, default=str).encode()).hexdigest()
    return manifest


if __name__ == "__main__":
    out = build()
    path = f"{ROOT}/research/hypothesis_engine/V8B1_TRANCHE_50_MANIFEST.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(f"wrote {path}")
    print(f"n fixtures: {out['n_tranche']}")
    print(f"first 3 tranche ids: {out['fixture_ids_ordered'][:3]}")
    print(f"last id: {out['fixture_ids_ordered'][-1]}")
    print(f"champion match: {out['champion_artifact_sha256'] == out['champion_artifact_sha256_expected']}")
    print(f"tranche_manifest_hash: {out['tranche_manifest_hash'][:16]}")
