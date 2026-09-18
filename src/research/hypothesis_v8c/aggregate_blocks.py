"""V8C chronological inference blocks (`v8c_blocks_v1`) -- supports P1-F.

Extracted from `aggregate.py` so PROCESS 1 can compute and FREEZE the blocks without importing
anything that can read an outcome. `aggregate.py` imports them back, so there is exactly one
implementation and the two processes cannot drift.

Blocks are a pure function of the cohort's fixture order. They never see a score.
"""
from __future__ import annotations

import math

from src.research.hypothesis_v71 import estimator as EST

BLOCKS_VERSION = "v8c_blocks_v1"

MIN_QUALIFYING_BLOCKS = EST.SIGN_FLIP_MIN_CLUSTERS       # 3
MAX_CLUSTERS = EST.MAX_ENUMERATED_G                      # 20
MIN_PAIRED_PER_BLOCK = 5


# ---- frozen-before-outcome chronological blocks -------------------------------------------
def target_n_blocks(n_cohort_fixtures: int) -> int:
    """G(N) over the COHORT size, fixed before any outcome. No clamp up."""
    if n_cohort_fixtures < MIN_QUALIFYING_BLOCKS * MIN_PAIRED_PER_BLOCK:
        return 0
    return min(MAX_CLUSTERS, n_cohort_fixtures // MIN_PAIRED_PER_BLOCK)


def chronological_blocks(fixture_ids_in_kickoff_order) -> dict:
    """Contiguous, ceiling-divided blocks over the cohort's own kickoff order.

    A pure function of the fixture list -- never of any score. Frozen before outcomes.
    """
    fids = [str(f) for f in fixture_ids_in_kickoff_order]
    n = len(fids)
    g = target_n_blocks(n)
    if g == 0:
        mapping = {fid: "block_000" for fid in fids}
        return {"n_fixtures": n, "target_n_blocks": 0, "block_size": n,
                "n_blocks_actual": 1 if n else 0, "fixture_to_block": mapping,
                "block_sizes": {"block_000": n} if n else {},
                "below_exact_inference_size": True,
                "min_paired_per_block": MIN_PAIRED_PER_BLOCK,
                "min_qualifying_blocks": MIN_QUALIFYING_BLOCKS,
                "frozen_before_any_outcome_opened": True}
    block_size = math.ceil(n / g)
    mapping, sizes = {}, {}
    for i, fid in enumerate(fids):
        label = f"block_{i // block_size:03d}"
        mapping[fid] = label
        sizes[label] = sizes.get(label, 0) + 1
    return {"n_fixtures": n, "target_n_blocks": g, "block_size": block_size,
            "n_blocks_actual": len(sizes), "fixture_to_block": mapping,
            "block_sizes": dict(sorted(sizes.items())),
            "below_exact_inference_size": False,
            "min_paired_per_block": MIN_PAIRED_PER_BLOCK,
            "min_qualifying_blocks": MIN_QUALIFYING_BLOCKS,
            "frozen_before_any_outcome_opened": True}


