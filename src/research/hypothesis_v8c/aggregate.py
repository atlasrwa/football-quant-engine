"""V8C arm aggregation, paired endpoints and inference (`v8c_aggregate_v1`) -- repairs P1
`D-V8C-P1-INFSIZE`.

The aggregation SEMANTICS are the frozen V8B.1 ones (V8B1_AGGREGATION_INFERENCE_SPEC.md),
promoted from an ad-hoc analysis script into a tested module with PREDECLARED behaviour for
every state the experiment can actually reach (§18). Nothing here is improvised after a live
run, because the six aggregation cases and the four pairing cases are asserted in
tests/research/hypothesis_v8c/test_aggregation.py BEFORE any fresh outcome exists.

    ARM_SCORE(T) = mean of that arm's SCORE_OK fixture scores at T
                 = None when the arm has ZERO SCORE_OK at T   (never 0.0 -- NULL is not ZERO)

    D_R(T) = ARM_SCORE_S(T) - ARM_SCORE_R(T)     only where BOTH are not None (LISTWISE)
    D_H(T) = ARM_SCORE_S(T) - ARM_SCORE_H(T)     only where BOTH are not None (LISTWISE)

A fixture contributes AT MOST ONE value to each endpoint. There is no cross-fixture pairing
and no silent fixture substitution -- both are asserted, not merely intended.

THE INFERENCE DEFECT THIS REPAIRS
---------------------------------
The frozen chronological blocks are 20 blocks x 50 fixtures over the 1000-fixture manifest. A
fresh pilot of realistic size falls inside one or two of them, so
`estimator.small_cluster_inference` returns INSUFFICIENT_CLUSTERS_FOR_INFERENCE by
construction -- which is exactly what V8B.2's paired_n=4 retrospective produced. The inference
path was undefined for the experiment actually intended.

V8C predeclares a PILOT-SCOPED blocking rule, derived from the estimator's OWN frozen bounds
rather than chosen to produce a number:

    G(n) = 0                        if n == 0
         = INSUFFICIENT             if n <  MIN_CLUSTERS * MIN_FIXTURES_PER_BLOCK  (= 15)
         = min(MAX_ENUMERATED_G, floor(n / MIN_FIXTURES_PER_BLOCK))   otherwise

MIN_FIXTURES_PER_BLOCK = 5 is the smallest block for which a block mean is an AVERAGE rather
than a single fixture restated. 3 and 20 are `estimator.SIGN_FLIP_MIN_CLUSTERS` and
`estimator.MAX_ENUMERATED_G`, both frozen upstream and imported, not re-chosen here. Blocks are
contiguous in kickoff order, ceiling-divided -- the same construction the 1000-fixture blocks
used.

Note the deliberate ABSENCE of a `max(3, ...)` clamp. Clamping would manufacture three clusters
out of four paired fixtures, whose "block means" would be single fixtures wearing a cluster
label -- a sign-flip reference distribution built from nothing. The two frozen minimums
therefore MULTIPLY rather than trade off, and they yield the operational requirement that the
experiment must know before it spends:

    PAIRED_FIXTURES_REQUIRED_FOR_EXACT_INFERENCE = 3 clusters x 5 fixtures = 15 per endpoint

Below 15 paired fixtures the estimator's own INSUFFICIENT_CLUSTERS_FOR_INFERENCE state is
returned explicitly and the pilot is interpreted descriptively. That is a predeclared
interpretation, not a fallback invented after seeing a result.

INFERENCE_REACHABLE means the semantics are DEFINED and the small-N state is returned
EXPLICITLY at the intended size. It does NOT mean a significant p-value, and no p-value is
required to pass (§20). No p-value is ever invented.

ZERO SPEND. Reads no target outcome directly -- it consumes already-computed FixtureScores.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from src.research.hypothesis_v71 import estimator as EST
from src.research.hypothesis_v8b2 import scorer as SC

AGGREGATE_VERSION = "v8c_aggregate_v1"

#: Imported from the frozen estimator -- NOT re-chosen here.
MIN_CLUSTERS = EST.SIGN_FLIP_MIN_CLUSTERS        # 3
MAX_CLUSTERS = EST.MAX_ENUMERATED_G              # 20
#: The one new constant: the smallest block whose mean is an average, not one fixture restated.
MIN_FIXTURES_PER_BLOCK = 5

ARM_S, ARM_R, ARM_H = "S", "R", "H"
ARMS = (ARM_S, ARM_R, ARM_H)

NO_PAIRED_EVALUABLE_FIXTURES = "NO_PAIRED_EVALUABLE_FIXTURES"


@dataclass(frozen=True)
class ArmScore:
    """One arm at one fixture. `score is None` means the arm had zero SCORE_OK here."""
    fixture_id: str
    arm: str
    score: float | None
    n_score_ok: int
    n_selections: int
    contributing_ids: tuple
    attrition: dict            # non-OK status -> count, the research-yield ledger


def arm_score(records, fixture_id, arm) -> ArmScore:
    """ARM_SCORE(T) for one arm: the equal-weight mean of its SCORE_OK scores at T.

    Non-OK selections are EXCLUDED from the mean and ledgered in `attrition` -- never coerced
    to 0.0. An arm with zero SCORE_OK returns `score=None`, so the fixture drops out of every
    paired endpoint for that arm (listwise), rather than contributing a fabricated zero.
    """
    rows = [r for r in records if r["fixture_id"] == fixture_id and r["arm"] == arm]
    oks = [r for r in rows if r["status"] == SC.SCORE_OK and r.get("score") is not None]
    attrition = {}
    for r in rows:
        if r["status"] != SC.SCORE_OK or r.get("score") is None:
            attrition[r["status"]] = attrition.get(r["status"], 0) + 1
    score = (sum(r["score"] for r in oks) / len(oks)) if oks else None
    return ArmScore(fixture_id=str(fixture_id), arm=arm, score=score, n_score_ok=len(oks),
                    n_selections=len(rows),
                    contributing_ids=tuple(sorted(r["hypothesis_id"] for r in oks)),
                    attrition=dict(sorted(attrition.items())))


def per_fixture_arm_scores(records, fixture_ids_ordered) -> list[dict]:
    """ARM_SCORE for all three arms at every fixture, in the frozen manifest order."""
    out = []
    for fid in fixture_ids_ordered:
        row = {"fixture_id": str(fid)}
        for arm in ARMS:
            a = arm_score(records, fid, arm)
            row[arm] = a.score
            row[f"{arm}_n_score_ok"] = a.n_score_ok
            row[f"{arm}_n_selections"] = a.n_selections
            row[f"{arm}_ids"] = list(a.contributing_ids)
            row[f"{arm}_attrition"] = a.attrition
        out.append(row)
    return out


# ---- pilot-scoped chronological blocking (§20) -------------------------------------------
#: Both frozen minimums must hold simultaneously: >=3 clusters AND >=5 fixtures per cluster.
MIN_PAIRED_FIXTURES_FOR_EXACT_INFERENCE = MIN_CLUSTERS * MIN_FIXTURES_PER_BLOCK      # 15


def target_n_blocks(n_fixtures: int) -> int:
    """G(n): the block count, a pure function of the fixture COUNT.

    Returns 0 when exact inference is not available at this size -- either no fixtures at all,
    or fewer than MIN_PAIRED_FIXTURES_FOR_EXACT_INFERENCE. There is deliberately NO clamp up to
    MIN_CLUSTERS: manufacturing three clusters from four fixtures would build a sign-flip
    reference distribution out of single fixtures relabelled as block means.
    """
    if n_fixtures <= 0 or n_fixtures < MIN_PAIRED_FIXTURES_FOR_EXACT_INFERENCE:
        return 0
    return min(MAX_CLUSTERS, n_fixtures // MIN_FIXTURES_PER_BLOCK)


def chronological_blocks(fixture_ids_in_kickoff_order) -> dict:
    """Contiguous, ceiling-divided chronological blocks over the PILOT's own fixtures.

    Same construction as the frozen 1000-fixture blocks, applied to the pilot's own kickoff
    ordering. A function of the fixture list alone -- never of any score (§6 of the frozen
    aggregation spec, restated at pilot scope).
    """
    fids = [str(f) for f in fixture_ids_in_kickoff_order]
    n = len(fids)
    g = target_n_blocks(n)
    if g == 0:
        # Below the exact-inference size every fixture is still labelled -- as ONE block -- so
        # downstream code has a total mapping and the estimator itself reports the small-N
        # state, rather than this function silently dropping fixtures.
        mapping = {fid: "block_000" for fid in fids}
        return {"n_fixtures": n, "target_n_blocks": 0, "block_size": n,
                "n_blocks_actual": 1 if n else 0, "fixture_to_block": mapping,
                "block_sizes": {"block_000": n} if n else {},
                "within_estimator_small_cluster_bounds": False,
                "below_exact_inference_size": True,
                "min_paired_fixtures_for_exact_inference":
                    MIN_PAIRED_FIXTURES_FOR_EXACT_INFERENCE,
                "rule": "G(n) = 0 below 3 clusters x 5 fixtures; one label, small-N state",
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
            "within_estimator_small_cluster_bounds":
                MIN_CLUSTERS <= len(sizes) <= MAX_CLUSTERS,
            "below_exact_inference_size": False,
            "min_paired_fixtures_for_exact_inference":
                MIN_PAIRED_FIXTURES_FOR_EXACT_INFERENCE,
            "rule": "G(n) = min(MAX_ENUMERATED_G, n // MIN_FIXTURES_PER_BLOCK), no clamp up",
            "derived_from": "estimator.SIGN_FLIP_MIN_CLUSTERS / estimator.MAX_ENUMERATED_G",
            "frozen_before_any_outcome_opened": True}


# ---- paired endpoints ---------------------------------------------------------------------
def paired_endpoint(per_fixture, control_arm, fixture_to_block) -> dict:
    """D(T) = S(T) - control(T), listwise over fixtures where BOTH are not None.

    One value per fixture, maximum. No cross-fixture pairing. No substitution. A fixture where
    either side is None contributes to NEITHER endpoint (it may still appear in the separate,
    unpaired research-yield ledger).
    """
    rows, excluded = [], {"S_none": 0, "control_none": 0, "both_none": 0}
    for pf in per_fixture:
        s, c = pf.get(ARM_S), pf.get(control_arm)
        if s is None and c is None:
            excluded["both_none"] += 1
            continue
        if s is None:
            excluded["S_none"] += 1
            continue
        if c is None:
            excluded["control_none"] += 1
            continue
        rows.append({"fixture_id": pf["fixture_id"], "S": s, control_arm: c, "diff": s - c,
                     "S_ids": pf.get(f"{ARM_S}_ids", []),
                     f"{control_arm}_ids": pf.get(f"{control_arm}_ids", [])})

    assert len({r["fixture_id"] for r in rows}) == len(rows), (
        "a fixture contributed more than one paired difference")

    diffs = [r["diff"] for r in rows]
    clusters = [fixture_to_block[r["fixture_id"]] for r in rows]
    if diffs:
        inference = EST.small_cluster_inference(diffs, clusters)
    else:
        inference = {"primary_p_value": None, "point_estimate": None, "n_clusters": 0,
                     "inference_status": NO_PAIRED_EVALUABLE_FIXTURES,
                     "primary_method": EST.SMALL_CLUSTER_METHOD}
    return {"control_arm": control_arm,
            "paired_n": len(diffs),
            "n_blocks_spanned": len(set(clusters)),
            "excluded_fixtures": excluded,
            "mean_diff": (sum(diffs) / len(diffs)) if diffs else None,
            "median_diff": statistics.median(diffs) if diffs else None,
            "stdev_diff": statistics.pstdev(diffs) if len(diffs) >= 2 else None,
            "pos_zero_neg": _pos_zero_neg(diffs),
            "inference": inference,
            "rows": rows}


def _pos_zero_neg(diffs, eps=1e-12) -> dict:
    pos = sum(1 for d in diffs if d > eps)
    neg = sum(1 for d in diffs if d < -eps)
    return {"positive": pos, "zero": len(diffs) - pos - neg, "negative": neg}


def inference_reachability(n_paired_fixtures: int) -> dict:
    """Is the inference path DEFINED at this paired-fixture count, and which state does it
    return? Reports the state honestly; it does not require a p-value (§20)."""
    g = target_n_blocks(n_paired_fixtures)
    if n_paired_fixtures == 0:
        state = NO_PAIRED_EVALUABLE_FIXTURES
    elif g < MIN_CLUSTERS:
        state = "INSUFFICIENT_CLUSTERS_FOR_INFERENCE"
    else:
        state = "EXACT"
    return {"n_paired_fixtures": n_paired_fixtures, "implied_n_blocks": g,
            "min_paired_fixtures_for_exact_inference":
                MIN_PAIRED_FIXTURES_FOR_EXACT_INFERENCE,
            "expected_inference_status": state,
            "semantics_defined": True,
            "exact_enumeration_available": state == "EXACT",
            "n_sign_vectors": (1 << g) if state == "EXACT" else 0,
            "small_n_state_is_explicit": True,
            "p_value_invented_when_underpowered": False}


def version_stamp() -> dict:
    return {"aggregate_version": AGGREGATE_VERSION,
            "repairs": ["D-V8C-P1-INFSIZE"],
            "arm_score_rule": "equal-weight mean of SCORE_OK only; None when zero SCORE_OK",
            "null_is_not_zero": True,
            "pairing_rule": "LISTWISE: fixture contributes only where BOTH sides are not None",
            "one_value_per_fixture_per_endpoint": True,
            "cross_fixture_pairing": False,
            "fixture_substitution": False,
            "block_rule": "G(n) = min(20, n // 5), no clamp up; contiguous in kickoff order",
            "min_paired_fixtures_for_exact_inference":
                MIN_PAIRED_FIXTURES_FOR_EXACT_INFERENCE,
            "min_fixtures_per_block": MIN_FIXTURES_PER_BLOCK,
            "min_clusters": MIN_CLUSTERS, "max_clusters": MAX_CLUSTERS,
            "inference_primitive": EST.ESTIMATOR_VERSION,
            "inference_method": EST.SMALL_CLUSTER_METHOD,
            "invents_p_values": False}
