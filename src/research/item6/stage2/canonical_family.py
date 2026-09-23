"""ITEM 6 STAGE 2 canonical family representation (`item6_stage2_canonical_family_v1`).

Stage 1's `NEW_FAMILY_COUNT=280` is a SIGNATURE count, not a count of independent research
programmes. Stage 1's `family_signature` is built from the raw metric tuple plus novelty-signal
tuple, so two mechanisms expressing the same structural idea over slightly different metric sets
count twice. Reporting 280 as "280 novel families" would materially overstate the discovery.

This module separates the two things Stage 1 conflated:

  STRUCTURAL FAMILY      -- the shape of the hypothesis (what KIND of relationship it asserts).
                            Taken from the deterministically assigned required additive
                            grammar extension, which is single-valued per mechanism.
  METRIC INSTANTIATION   -- the structural family bound to a specific canonical metric tuple
                            and temporal-period signature.

Canonicalisation is purely syntactic and outcome-blind: AGAINST-perspective aliases are folded
onto their base metric + perspective, metric tuples are sorted, and period signatures are
reduced to the set of distinct periods actually cited. No predictive information participates.
"""
from __future__ import annotations

import collections
from typing import Dict, List, Sequence, Tuple

from src.research.item6.stage2 import provider_measurability as PM

CANONICAL_FAMILY_VERSION = "item6_stage2_canonical_family_v1"

# structural family <- required additive extension (single-valued, deterministic)
STRUCTURAL_FAMILIES: Dict[str, str] = {
    "GX_THRESHOLD_CONDITION": "SF_THRESHOLD_NONLINEARITY",
    "GX_CROSS_METRIC_JOINT": "SF_MULTIMETRIC_INTERACTION",
    "GX_HALF_STATE_INTERACTION": "SF_HALF_OR_GAME_STATE_INTERACTION",
    "GX_TWO_AXIS_PROFILE_INTERSECTION": "SF_TWO_AXIS_OPPONENT_PROFILE_INTERSECTION",
    "GX_SEQUENCE_REGIME": "SF_SEQUENCING_REGIME",
}


def structural_family(formalization: Dict) -> str:
    ext = formalization.get("required_extension")
    return STRUCTURAL_FAMILIES.get(str(ext), "SF_UNCLASSIFIED")


def canonical_metric_tuple(metrics: Sequence[str]) -> Tuple[Tuple[str, str], ...]:
    """Metric names folded to (base_metric, perspective), de-duplicated and sorted.

    `goals_conceded` and `goals` therefore canonicalise to ('goals','AGAINST') and
    ('goals','FOR') -- distinct instantiations of the same measurable field pair, which is how
    the deterministic engine already treats FOR/AGAINST.
    """
    out = set()
    for m in metrics:
        base, persp, _ = PM.resolve(m)
        if base is None:
            continue
        out.add((base, persp))
    return tuple(sorted(out))


def period_signature(formalization: Dict) -> Tuple[str, ...]:
    """Distinct evidence periods the mechanism actually cited, sorted."""
    from src.research.item6.stage2.funnel import parse_evidence_ref
    periods = set()
    for ref in formalization.get("valid_evidence_refs", ()):
        p = parse_evidence_ref(ref)
        if p:
            periods.add(p["period"])
    return tuple(sorted(periods))


def canonical_key(formalization: Dict) -> str:
    """Deterministic canonical identity: structural family + metric tuple + period signature."""
    sf = structural_family(formalization)
    mt = canonical_metric_tuple(formalization.get("distinct_metrics", ()))
    ps = period_signature(formalization)
    mt_s = "|".join(f"{b}.{p}" for b, p in mt)
    return f"{sf}::{mt_s}::{'+'.join(ps)}"


def build_canonical_registry(feasible_rows: Sequence[Dict],
                            formalizations_by_seq: Dict[int, Dict]) -> Dict[str, object]:
    """Canonical registry over the FEASIBLE funnel rows only.

    Returns structural-family level and metric-instantiation level views. Membership is
    recorded so every Stage-2 feature is traceable back to the Stage-1 mechanisms that
    motivated it.
    """
    by_struct: Dict[str, List[str]] = collections.defaultdict(list)
    by_inst: Dict[str, Dict[str, object]] = {}

    for r in feasible_rows:
        f = formalizations_by_seq[int(r["seq"])]
        sf = structural_family(f)
        key = canonical_key(f)
        mt = canonical_metric_tuple(f.get("distinct_metrics", ()))
        ps = period_signature(f)
        if key not in by_inst:
            by_inst[key] = {
                "canonical_key": key,
                "structural_family": sf,
                "canonical_metrics": [{"metric": b, "perspective": p} for b, p in mt],
                "period_signature": list(ps),
                "requires_half_resolution": any(p != "FULL_MATCH" for p in ps),
                "required_extension": f.get("required_extension"),
                "member_seqs": [],
                "member_mechanism_ids": [],
            }
        by_inst[key]["member_seqs"].append(int(r["seq"]))
        by_inst[key]["member_mechanism_ids"].append(
            f"{r.get('fixture_id')}::{r.get('mechanism_id_local')}")
        if key not in by_struct[sf]:
            by_struct[sf].append(key)

    instantiations = [by_inst[k] for k in sorted(by_inst)]
    for inst in instantiations:
        inst["n_members"] = len(inst["member_seqs"])

    structural = [
        {"structural_family": sf,
         "n_metric_instantiations": len(sorted(set(keys))),
         "canonical_keys": sorted(set(keys)),
         "n_member_mechanisms": sum(by_inst[k]["n_members"] for k in set(keys))}
        for sf, keys in sorted(by_struct.items())
    ]
    return {
        "canonical_family_version": CANONICAL_FAMILY_VERSION,
        "n_canonical_structural_families": len(structural),
        "n_canonical_metric_instantiations": len(instantiations),
        "structural_families": structural,
        "metric_instantiations": instantiations,
        "clustered_using_outcomes": False,
    }


def version_stamp() -> Dict[str, object]:
    return {
        "canonical_family_version": CANONICAL_FAMILY_VERSION,
        "n_structural_family_classes": len(STRUCTURAL_FAMILIES),
        "structural_family_source": "deterministic_required_additive_extension",
        "clustered_using_outcomes": False,
        "reads_outcomes": False,
    }
