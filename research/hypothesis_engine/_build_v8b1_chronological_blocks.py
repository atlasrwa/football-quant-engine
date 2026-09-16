"""Freezes the chronological block assignment used by V8B1_AGGREGATION_INFERENCE_SPEC.md's
clustering rule, over the fixtures in V8B1_FIXTURE_MANIFEST.json. Fixed BEFORE any target
outcome is opened -- block membership is a pure function of a fixture's position in the
manifest's own chronological order, never of any score.

Rule: contiguous blocks of BLOCK_SIZE fixtures each, in the manifest's chronological order
(ties broken by fixture_id, matching the manifest's own ordering exactly). BLOCK_SIZE is fixed
at build time to a value that yields at least MIN_BLOCKS_FOR_EXACT_ENUMERATION blocks (so the
sign-flip test in estimator.small_cluster_inference gets a genuinely exact enumeration rather
than a degenerate few-cluster case), reported explicitly rather than chosen post-hoc.
"""
from __future__ import annotations

import hashlib
import json

ROOT = "/home/ubuntu"

#: Target: comfortably above SIGN_FLIP_MIN_CLUSTERS=3 and within MAX_ENUMERATED_G=20 (both
#: from src.research.hypothesis_v71.estimator, reused unchanged) -- chosen here as a ROUND
#: block count decided BEFORE looking at any fixture-level score, not tuned to it.
TARGET_N_BLOCKS = 20
COMPETITION_SECONDARY_CLUSTER_NOTE = (
    "competition is reported as a SECONDARY, DESCRIPTIVE-ONLY clustering "
    "(mirrors engine.py's own fold-vs-competition dual reporting); never the primary "
    "inferential clustering, never selected post-hoc to improve a result")


def build() -> dict:
    manifest = json.load(open(f"{ROOT}/research/hypothesis_engine/V8B1_FIXTURE_MANIFEST.json"))
    fixtures = manifest["fixtures"]  # already in chronological order per the manifest builder
    n = len(fixtures)
    block_size = max(1, -(-n // TARGET_N_BLOCKS))  # ceiling division: guarantees <= TARGET_N_BLOCKS blocks, each >= 1
    blocks = {}
    for i, f in enumerate(fixtures):
        block_id = f"block_{i // block_size:03d}"
        blocks[f["fixture_id"]] = block_id

    n_blocks_actual = len(set(blocks.values()))
    block_sizes = {}
    for bid in blocks.values():
        block_sizes[bid] = block_sizes.get(bid, 0) + 1

    out = {
        "chronological_blocks_version": "v8b1_chrono_blocks_v1",
        "source_manifest_hash": manifest["manifest_hash"],
        "n_fixtures": n,
        "target_n_blocks": TARGET_N_BLOCKS,
        "block_size": block_size,
        "n_blocks_actual": n_blocks_actual,
        "block_sizes": block_sizes,
        "fixture_to_block": blocks,
        "competition_secondary_cluster_note": COMPETITION_SECONDARY_CLUSTER_NOTE,
        "within_estimator_small_cluster_bounds": (
            n_blocks_actual >= 3 and n_blocks_actual <= 20),  # SIGN_FLIP_MIN_CLUSTERS..MAX_ENUMERATED_G
        "frozen_before_any_outcome_opened": True,
    }
    out["blocks_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in out.items() if k != "blocks_hash"},
                   sort_keys=True, default=str).encode()).hexdigest()
    return out


if __name__ == "__main__":
    out = build()
    path = f"{ROOT}/research/hypothesis_engine/V8B1_CHRONOLOGICAL_BLOCKS.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(f"wrote {path}")
    print(f"n_blocks_actual={out['n_blocks_actual']} block_size={out['block_size']} "
          f"within_bounds={out['within_estimator_small_cluster_bounds']} "
          f"hash={out['blocks_hash'][:16]}")
