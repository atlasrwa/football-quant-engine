"""V8C aggregation, paired endpoints and inference (`v8c_aggregate_v2`).

Repairs P1 R PAIRING and P1 INFERENCE.

TWO DIFFERENT ESTIMANDS -- named differently so they are never read as comparable
--------------------------------------------------------------------------------
S-v-R is MATCHED-PAIR level. Every Sonnet selection carries a structurally matched blind
counterpart `(S_ID, R_ID, tier)`, and the difference is taken WITHIN the pair:

    d_i(T)      = score(S_i, T) - score(R_i, T)     for each surviving pair i at T
    D_R(T)      = mean over surviving pairs at T
    a pair drops when EITHER side is non-OK -- the PAIR drops, not the fixture

The V8B/V8C-v1 rule compared `mean(all S SCORE_OK)` against `mean(all R SCORE_OK)`, which
could put the mean of three surviving S hypotheses against one surviving R hypothesis. That is
not a paired comparison; the matching was thrown away at the last step.

S-v-H is ARM-MEAN level, because H is a policy baseline rather than a per-hypothesis
counterfactual:

    D_H(T) = mean(S SCORE_OK at T) - mean(H SCORE_OK at T)

THE INFERENCE RULE -- P1 INFERENCE
----------------------------------
Chronological blocks are frozen BEFORE any outcome, from the cohort fixture list alone.
QUALIFICATION is evaluated after scoring:

    a block QUALIFIES iff it contains >= MIN_PAIRED_PER_BLOCK (5) actual valid paired
    fixture differences
    exact sign-flip requires >= MIN_QUALIFYING_BLOCKS (3) qualifying blocks

So four paired fixtures spread across four frozen blocks yields FOUR blocks with one
difference each, ZERO qualifying blocks, and INSUFFICIENT_CLUSTERS_FOR_INFERENCE -- never
EXACT. The previous rule partitioned by count and would have returned EXACT there, building a
sign-flip reference distribution out of single fixtures wearing cluster labels.

Inference runs over QUALIFYING blocks only. The full-set descriptive mean is reported beside
it, explicitly labelled, so nothing is silently dropped.

No p-value is ever invented. ZERO SPEND.
"""
from __future__ import annotations

import math
import statistics

from src.research.hypothesis_v71 import estimator as EST
from src.research.hypothesis_v8c import cohort_stats as SC

AGGREGATE_VERSION = "v8c_aggregate_v2"

#: Imported from the frozen estimator -- not re-chosen here.
MIN_QUALIFYING_BLOCKS = EST.SIGN_FLIP_MIN_CLUSTERS       # 3
MAX_CLUSTERS = EST.MAX_ENUMERATED_G                      # 20
#: The smallest block whose mean is an AVERAGE rather than one fixture restated.
MIN_PAIRED_PER_BLOCK = 5

ARM_S, ARM_R, ARM_H = "S", "R", "H"

NO_PAIRED_EVALUABLE_FIXTURES = "NO_PAIRED_EVALUABLE_FIXTURES"
INSUFFICIENT_CLUSTERS = "INSUFFICIENT_CLUSTERS_FOR_INFERENCE"


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


# ---- arm scores ---------------------------------------------------------------------------
def _ok(records, fid, arm):
    return [r for r in records if r["fixture_id"] == fid and r["arm"] == arm
            and r["status"] == SC.SCORE_OK and r.get("score") is not None]


def arm_mean(records, fid, arm):
    """Equal-weight mean of an arm's SCORE_OK scores at T; None when it has zero (never 0.0)."""
    oks = _ok(records, fid, arm)
    if not oks:
        return None, [], {}
    attr = {}
    for r in records:
        if r["fixture_id"] == fid and r["arm"] == arm and (
                r["status"] != SC.SCORE_OK or r.get("score") is None):
            attr[r["status"]] = attr.get(r["status"], 0) + 1
    return (sum(r["score"] for r in oks) / len(oks),
            sorted(r["hypothesis_id"] for r in oks), attr)


def paired_sr_at_fixture(records, fid, pair_triples) -> dict:
    """MATCHED-PAIR S-v-R at one fixture. `pair_triples` is the FROZEN [(s_id, r_id, tier)].

    A pair contributes iff BOTH of its own hypotheses reached SCORE_OK at this fixture. A
    dropped pair does not remove the fixture -- other pairs at the same fixture still count.
    """
    by = {(r["arm"], r["hypothesis_id"]): r for r in records if r["fixture_id"] == fid}
    diffs, kept, dropped = [], [], []
    for t in pair_triples:
        s_id, r_id, tier = t["s_id"], t.get("r_id"), t.get("tier")
        if r_id is None:
            dropped.append({"s_id": s_id, "r_id": None, "tier": tier,
                            "reason": "UNMATCHED_DISTINCT_CONTROL"})
            continue
        rs, rr = by.get((ARM_S, s_id)), by.get((ARM_R, r_id))
        s_ok = rs is not None and rs["status"] == SC.SCORE_OK and rs.get("score") is not None
        r_ok = rr is not None and rr["status"] == SC.SCORE_OK and rr.get("score") is not None
        if s_ok and r_ok:
            d = rs["score"] - rr["score"]
            diffs.append(d)
            kept.append({"s_id": s_id, "r_id": r_id, "tier": tier, "pair_diff": d})
        else:
            dropped.append({"s_id": s_id, "r_id": r_id, "tier": tier,
                            "reason": ("S_NOT_OK" if not s_ok else "R_NOT_OK")})
    return {"fixture_id": str(fid),
            "D_R": (sum(diffs) / len(diffs)) if diffs else None,
            "n_pairs_frozen": len(pair_triples), "n_pairs_surviving": len(diffs),
            "surviving_pairs": kept, "dropped_pairs": dropped}


def per_fixture_endpoints(records, fixture_ids_ordered, pair_triples_by_fixture) -> list:
    """Both endpoints at every fixture, in the frozen cohort order."""
    out = []
    for fid in fixture_ids_ordered:
        fid = str(fid)
        s_mean, s_ids, s_attr = arm_mean(records, fid, ARM_S)
        h_mean, h_ids, h_attr = arm_mean(records, fid, ARM_H)
        _r_mean, r_ids, r_attr = arm_mean(records, fid, ARM_R)
        sr = paired_sr_at_fixture(records, fid, pair_triples_by_fixture.get(fid, []))
        out.append({
            "fixture_id": fid,
            "D_R": sr["D_R"],                       # matched-pair level
            "D_H": (s_mean - h_mean) if (s_mean is not None and h_mean is not None) else None,
            "S_arm_mean": s_mean, "H_arm_mean": h_mean,
            "S_ids": s_ids, "H_ids": h_ids, "R_ids": r_ids,
            "n_pairs_frozen": sr["n_pairs_frozen"],
            "n_pairs_surviving": sr["n_pairs_surviving"],
            "surviving_pairs": sr["surviving_pairs"], "dropped_pairs": sr["dropped_pairs"],
            "attrition": {"S": s_attr, "R": r_attr, "H": h_attr},
        })
    return out


# ---- inference over QUALIFYING blocks ------------------------------------------------------
def qualifying_blocks(per_fixture, key, fixture_to_block) -> dict:
    """Which frozen blocks carry >= MIN_PAIRED_PER_BLOCK actual valid paired differences."""
    counts = {}
    for pf in per_fixture:
        if pf.get(key) is None:
            continue
        b = fixture_to_block[pf["fixture_id"]]
        counts[b] = counts.get(b, 0) + 1
    qual = sorted(b for b, n in counts.items() if n >= MIN_PAIRED_PER_BLOCK)
    return {"paired_per_block": dict(sorted(counts.items())),
            "qualifying_blocks": qual, "n_qualifying_blocks": len(qual),
            "min_paired_per_block": MIN_PAIRED_PER_BLOCK,
            "min_qualifying_blocks": MIN_QUALIFYING_BLOCKS}


def endpoint(per_fixture, key, fixture_to_block, *, label) -> dict:
    """One endpoint: descriptive over ALL paired fixtures, inference over QUALIFYING blocks."""
    rows = [pf for pf in per_fixture if pf.get(key) is not None]
    all_diffs = [pf[key] for pf in rows]
    q = qualifying_blocks(per_fixture, key, fixture_to_block)

    inf_rows = [pf for pf in rows
                if fixture_to_block[pf["fixture_id"]] in set(q["qualifying_blocks"])]
    inf_diffs = [pf[key] for pf in inf_rows]
    inf_clusters = [fixture_to_block[pf["fixture_id"]] for pf in inf_rows]

    if not all_diffs:
        inference = {"primary_p_value": None, "point_estimate": None, "n_clusters": 0,
                     "inference_status": NO_PAIRED_EVALUABLE_FIXTURES,
                     "primary_method": EST.SMALL_CLUSTER_METHOD}
    elif q["n_qualifying_blocks"] < MIN_QUALIFYING_BLOCKS:
        inference = {
            "primary_p_value": None,
            "point_estimate": (sum(inf_diffs) / len(inf_diffs)) if inf_diffs else None,
            "n_clusters": q["n_qualifying_blocks"],
            "inference_status": INSUFFICIENT_CLUSTERS,
            "primary_method": EST.SMALL_CLUSTER_METHOD,
            "why": (f"{q['n_qualifying_blocks']} block(s) carry >= "
                    f"{MIN_PAIRED_PER_BLOCK} paired differences; "
                    f"{MIN_QUALIFYING_BLOCKS} required"),
        }
    else:
        inference = EST.small_cluster_inference(inf_diffs, inf_clusters)

    return {"label": label, "estimand": key,
            "paired_n_all": len(all_diffs),
            "paired_n_in_inference": len(inf_diffs),
            "n_blocks_spanned": len({fixture_to_block[pf["fixture_id"]] for pf in rows}),
            "block_qualification": q,
            "descriptive_all_fixtures": {
                "mean_diff": (sum(all_diffs) / len(all_diffs)) if all_diffs else None,
                "median_diff": statistics.median(all_diffs) if all_diffs else None,
                "stdev_diff": statistics.pstdev(all_diffs) if len(all_diffs) >= 2 else None,
                "pos_zero_neg": _pos_zero_neg(all_diffs),
                "note": "descriptive over EVERY paired fixture; NOT the inferential set"},
            "inference": inference,
            "rows": [{"fixture_id": pf["fixture_id"], "diff": pf[key],
                      "block": fixture_to_block[pf["fixture_id"]]} for pf in rows]}


def _pos_zero_neg(diffs, eps=1e-12) -> dict:
    pos = sum(1 for d in diffs if d > eps)
    neg = sum(1 for d in diffs if d < -eps)
    return {"positive": pos, "zero": len(diffs) - pos - neg, "negative": neg}


def inference_reachability(paired_per_block: dict) -> dict:
    """Would inference be available given this distribution of paired differences per block?"""
    qual = [b for b, n in paired_per_block.items() if n >= MIN_PAIRED_PER_BLOCK]
    total = sum(paired_per_block.values())
    if total == 0:
        state = NO_PAIRED_EVALUABLE_FIXTURES
    elif len(qual) < MIN_QUALIFYING_BLOCKS:
        state = INSUFFICIENT_CLUSTERS
    else:
        state = "EXACT"
    return {"n_paired_total": total, "n_qualifying_blocks": len(qual),
            "min_paired_per_block": MIN_PAIRED_PER_BLOCK,
            "min_qualifying_blocks": MIN_QUALIFYING_BLOCKS,
            "expected_inference_status": state, "semantics_defined": True,
            "exact_enumeration_available": state == "EXACT",
            "n_sign_vectors": (1 << len(qual)) if state == "EXACT" else 0,
            "p_value_invented_when_underpowered": False}


def version_stamp() -> dict:
    return {"aggregate_version": AGGREGATE_VERSION,
            "repairs": ["P1-R-PAIRING", "P1-INFERENCE"],
            "estimands": {
                "S_vs_R": "MATCHED-PAIR: mean over surviving (S_i,R_i) pair differences at T",
                "S_vs_H": "ARM-MEAN: mean(S SCORE_OK) - mean(H SCORE_OK) at T"},
            "estimands_are_not_comparable": True,
            "pair_drop_rule": "a pair drops when EITHER side is non-OK; the FIXTURE does not",
            "null_is_not_zero": True,
            "blocks_frozen_before_outcomes": True,
            "block_qualification": (f">= {MIN_PAIRED_PER_BLOCK} actual valid paired "
                                    f"differences in the block"),
            "exact_requires": f">= {MIN_QUALIFYING_BLOCKS} qualifying blocks",
            "four_paired_across_four_blocks": INSUFFICIENT_CLUSTERS,
            "inference_primitive": EST.ESTIMATOR_VERSION,
            "inference_method": EST.SMALL_CLUSTER_METHOD,
            "invents_p_values": False}
