"""V8C development structural diagnostics (`v8c_structural_diagnostics_v1`) -- REPAIR 3.

THE DEFECT
----------
`score_frozen` called `aggregate.per_fixture_endpoints` and `aggregate.endpoint`, which
COMPUTE arm means, paired differences, dispersion and `small_cluster_inference`.
`aggregate.structural_only` then removed those fields from the returned dict.

That supports the claim "not EMITTED". It does not support "not COMPUTED". For a development
rehearsal over outcomes that are already exposed, the distinction is the whole point: a
treatment-control difference that exists in the process, even briefly, is a computed effect.

THE REPAIR
----------
This module assembles the same structural facts from STATUSES and IDENTITIES only. It never
reads `record["score"]`, never subtracts one arm from another, and never calls an estimator.

    SCORE_OK counts          from `record["status"]`
    pair retention           from the frozen (s_id, r_id) triples: a pair SURVIVES iff BOTH
                             members reached SCORE_OK. No score value is compared.
    block membership         from the frozen fixture -> block mapping
    inference ELIGIBILITY    from paired COUNTS per block against the frozen floors --
                             whether inference COULD run, never what it would say

`assert_no_score_read` is the mechanical guard: the records handed in are stripped of their
`score` field first, so a future edit that tries to read one raises instead of silently
working.

The confirmatory definitions in `aggregate` are untouched. This is an additional path, not a
replacement, and it is reachable only through an explicit development mode.

ZERO SPEND. Computes no effect, no direction, no p-value.
"""
from __future__ import annotations

from src.research.hypothesis_v8c import aggregate as AG
from src.research.hypothesis_v8c import cohort_stats as SC

STRUCTURAL_DIAGNOSTICS_VERSION = "v8c_structural_diagnostics_v1"

#: Reused from the confirmatory path so eligibility is judged by the SAME floors.
MIN_PAIRED_PER_BLOCK = AG.MIN_PAIRED_PER_BLOCK
MIN_QUALIFYING_BLOCKS = AG.MIN_QUALIFYING_BLOCKS
ARM_S, ARM_R, ARM_H = AG.ARM_S, AG.ARM_R, AG.ARM_H


class ScoreValueRead(Exception):
    """A diagnostics path tried to read a score value. Nothing may."""


class _NoScore:
    """Stands in for a score value so any read is loud rather than silent."""

    def __repr__(self):                       # pragma: no cover - defensive
        return "<score withheld from the development diagnostics path>"

    def _forbid(self, *_a, **_k):
        raise ScoreValueRead(
            "the development diagnostics path read a score value; it must work from "
            "statuses and identities only")

    __float__ = __int__ = __add__ = __sub__ = __mul__ = __lt__ = __gt__ = _forbid
    __eq__ = _forbid
    __hash__ = None


def strip_scores(records) -> list:
    """Records with every score value replaced by a poisoned sentinel."""
    return [{**r, "score": _NoScore()} if "score" in r else dict(r) for r in records]


def structural_diagnostics(records, fixture_ids_ordered, pair_triples_by_fixture,
                           fixture_to_block) -> dict:
    """Assembly facts only. Reads `status` and identity; never a score."""
    recs = strip_scores(records)
    ok = {(str(r["fixture_id"]), r["arm"], r["hypothesis_id"])
          for r in recs if r["status"] == SC.SCORE_OK}

    arm_ok = {a: sum(1 for (_f, arm, _h) in ok if arm == a) for a in (ARM_S, ARM_R, ARM_H)}
    status_counts = {}
    for r in recs:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    per_fixture, paired_per_block = [], {}
    for fid in fixture_ids_ordered:
        fid = str(fid)
        triples = pair_triples_by_fixture.get(fid, [])
        frozen = [t for t in triples if t.get("r_id")]
        surviving = [t for t in frozen
                     if (fid, ARM_S, t["s_id"]) in ok and (fid, ARM_R, t["r_id"]) in ok]
        block = fixture_to_block.get(fid)
        if surviving:
            paired_per_block[block] = paired_per_block.get(block, 0) + 1
        per_fixture.append({
            "fixture_id": fid,
            "block": block,
            "n_pairs_frozen": len(frozen),
            "n_pairs_surviving": len(surviving),
            "surviving_pair_ids": [(t["s_id"], t["r_id"]) for t in surviving],
            "s_ok": sum(1 for (f, a, _h) in ok if f == fid and a == ARM_S),
            "r_ok": sum(1 for (f, a, _h) in ok if f == fid and a == ARM_R),
            "h_ok": sum(1 for (f, a, _h) in ok if f == fid and a == ARM_H),
        })

    qualifying = sorted(b for b, n in paired_per_block.items() if n >= MIN_PAIRED_PER_BLOCK)
    return {
        "structural_diagnostics_version": STRUCTURAL_DIAGNOSTICS_VERSION,
        "computed_from": "record statuses and frozen identities",
        "reads_score_values": False,
        "calls_effect_aggregation": False,
        "calls_statistical_inference": False,
        "arm_score_ok": arm_ok,
        "status_counts": dict(sorted(status_counts.items())),
        "n_records": len(recs),
        "n_fixtures": len(per_fixture),
        "n_fixtures_with_surviving_pair": sum(1 for p in per_fixture
                                              if p["n_pairs_surviving"]),
        "n_pairs_frozen_total": sum(p["n_pairs_frozen"] for p in per_fixture),
        "n_pairs_surviving_total": sum(p["n_pairs_surviving"] for p in per_fixture),
        "block_membership": {str(b): sorted(p["fixture_id"] for p in per_fixture
                                            if p["block"] == b)
                             for b in sorted({p["block"] for p in per_fixture}, key=str)},
        "inference_eligibility": {
            "paired_per_block": {str(k): v for k, v in sorted(paired_per_block.items(),
                                                              key=lambda kv: str(kv[0]))},
            "qualifying_blocks": [str(b) for b in qualifying],
            "n_qualifying_blocks": len(qualifying),
            "min_paired_per_block": MIN_PAIRED_PER_BLOCK,
            "min_qualifying_blocks": MIN_QUALIFYING_BLOCKS,
            "would_inference_be_available": len(qualifying) >= MIN_QUALIFYING_BLOCKS,
            "note": ("ELIGIBILITY only -- whether inference COULD run on this structure, "
                     "never what it would conclude"),
        },
        "per_fixture": per_fixture,
    }


def version_stamp() -> dict:
    return {"structural_diagnostics_version": STRUCTURAL_DIAGNOSTICS_VERSION,
            "repairs": ["REPAIR-3-EFFECT-NOT-COMPUTED"],
            "was": ("score_frozen computed arm means, paired differences and inference, then "
                    "aggregate.structural_only stripped them -- 'not emitted', not "
                    "'not computed'"),
            "now": "assembled from statuses and identities; no effect is ever formed",
            "reads_score_values": False,
            "shares_validation_and_scoring_machinery": True,
            "confirmatory_definitions_unchanged": True,
            "min_paired_per_block": MIN_PAIRED_PER_BLOCK,
            "min_qualifying_blocks": MIN_QUALIFYING_BLOCKS}
