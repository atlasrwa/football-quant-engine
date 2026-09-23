"""ITEM 6 STAGE 2 deterministic feasibility funnel (`item6_stage2_funnel_v1`).

Decides, for every frozen Stage-1 mechanism, whether it can be deterministically instantiated
as a Stage-2 feature against the FootyStats historical substrate.

ABSOLUTELY OUTCOME-BLIND. The funnel reads:
  * the frozen Stage-1 formalization records (f_class, deterministically-derived metric set,
    novelty signals, required additive extension, and the EVIDENCE REFS the mechanism cited);
  * the FootyStats measurement substrate (provider_measurability).
It never reads a target label, a market price, an OOS metric, or any model output. Nothing in
this module can be influenced by how well a family later predicts.

TWO DELIBERATE SOURCE CHOICES
-----------------------------
1. The measurement requirement is `distinct_metrics` -- the DETERMINISTICALLY derived metric
   set (baseline_equivalence.distinct_metrics) -- and NOT the mechanism's own
   `provider_requirements` field. `provider_requirements` is written by the LLM
   (schema.py: Mechanism.provider_requirements is parsed straight from the tool payload), so
   trusting it would let LLM self-assessment decide Stage-2 feasibility. It is rejected for the
   same reason LLM numeric thresholds are rejected: the model does not adjudicate its own
   measurability.

2. The temporal-resolution requirement is derived from the PERIOD field of the mechanism's
   cited evidence refs (`E:<role>:<metric>:<perspective>:<period>:<venue>:<window>`), not from
   the LLM's self-declared `temporal_resolution_requirement`. A half-state claim is only
   honoured when it is anchored in first/second-half evidence the mechanism actually cited, and
   the metric carrying that half citation must itself be half-capable in the corpus.

SEQUENCING DISCIPLINE
---------------------
The only point-in-time-safe sequence representation this substrate supports is the
FIRST_HALF -> SECOND_HALF transition WITHIN an already-completed prior match. Minute-level
event ordering does not exist in the corpus. A sequencing/regime mechanism that is not anchored
in half-period evidence is therefore rejected (S2F6) rather than approximated: synthesising a
pseudo-sequence out of full-match aggregates is explicitly forbidden.
"""
from __future__ import annotations

import collections
from typing import Dict, List, Optional, Sequence, Tuple

from src.research.item6.stage2 import provider_measurability as PM

FUNNEL_VERSION = "item6_stage2_funnel_v1"

# --- funnel statuses (terminal, mutually exclusive, deterministic precedence) --------------
S2F0 = "S2F0_INVALID_STAGE1_BINDING"
S2F1 = "S2F1_PROVIDER_UNAVAILABLE"
S2F2 = "S2F2_PACKET_ONLY_METRIC_NOT_HISTORICALLY_MEASURABLE"
S2F3 = "S2F3_INSUFFICIENT_POINT_IN_TIME_COVERAGE"
S2F4 = "S2F4_UNRESOLVED_PROVIDER_SEMANTICS"
S2F5 = "S2F5_DUPLICATE_OR_CANONICALLY_EQUIVALENT"
S2F6 = "S2F6_REQUIRES_UNSUPPORTED_TEMPORAL_RESOLUTION"
S2F7 = "S2F7_REQUIRES_NUMERIC_THRESHOLD_NOT_YET_DEFINED"
S2F8 = "S2F8_FEASIBLE_EXISTING_EXTENSION"
S2F9 = "S2F9_FEASIBLE_NEW_DETERMINISTIC_EXTENSION"

ALL_STATUSES: Tuple[str, ...] = (S2F0, S2F1, S2F2, S2F3, S2F4, S2F5, S2F6, S2F7, S2F8, S2F9)
FEASIBLE_STATUSES: Tuple[str, ...] = (S2F8, S2F9)

F4 = "F4_MEASURABLE_WITH_SAFE_ADDITIVE_GRAMMAR_EXTENSION"

# Extensions expressible with the engine's EXISTING deterministic machinery (rolling
# per-metric aggregates, comparators, conditioning bands) once a threshold policy supplies the
# cut points: threshold conditions and cross-metric joints over full-match rolling features.
EXISTING_EXTENSIONS: Tuple[str, ...] = ("GX_THRESHOLD_CONDITION", "GX_CROSS_METRIC_JOINT")
# Extensions requiring genuinely NEW deterministic machinery built for Stage 2.
NEW_EXTENSIONS: Tuple[str, ...] = ("GX_HALF_STATE_INTERACTION",
                                   "GX_TWO_AXIS_PROFILE_INTERSECTION",
                                   "GX_SEQUENCE_REGIME")

HALF_ASSERTING_SIGNALS: Tuple[str, ...] = ("US_HALF_STATE_OR_GAME_STATE", "US_SEQUENCING_REGIME")
HALF_ASSERTING_EXTENSIONS: Tuple[str, ...] = ("GX_HALF_STATE_INTERACTION", "GX_SEQUENCE_REGIME")

PERIOD_FULL = "FULL_MATCH"


def parse_evidence_ref(ref: str) -> Optional[Dict[str, str]]:
    """`E:<role>:<metric>:<perspective>:<period>:<venue>:<window>` -> dict, or None."""
    parts = ref.split(":")
    if len(parts) != 7 or parts[0] != "E":
        return None
    return {"role": parts[1], "metric": parts[2], "perspective": parts[3],
            "period": parts[4], "venue": parts[5], "window": parts[6]}


def half_resolution_metrics_required(formalization: Dict) -> List[str]:
    """Metrics the mechanism cited at FIRST_HALF / SECOND_HALF resolution (sorted)."""
    out = set()
    for ref in formalization.get("valid_evidence_refs", ()):
        p = parse_evidence_ref(ref)
        if p and p["period"] != PERIOD_FULL:
            out.add(p["metric"])
    return sorted(out)


def _asserts_half_or_sequence(f: Dict) -> bool:
    sig = set(f.get("novelty_signals", ()))
    return bool(sig & set(HALF_ASSERTING_SIGNALS)) or \
        f.get("required_extension") in HALF_ASSERTING_EXTENSIONS


def classify_mechanism(f: Dict) -> Dict[str, object]:
    """Terminal funnel status for ONE frozen Stage-1 formalization record.

    Precedence is fixed and documented; the first matching rule wins so the status is a
    deterministic function of the frozen record plus the provider substrate.
    S2F3 (coverage) and S2F5 (duplicate collapse) are corpus/corpus-wide properties and are
    applied by the batch pass, not here.
    """
    reasons: List[str] = []

    # 1. S2F0 -- the Stage-1 binding must be an accepted, grounded, leak-free F4 record.
    if f.get("f_class") != F4 or not f.get("grounded") or not f.get("provider_safe") \
            or f.get("future_leakage") or not f.get("counts_as_novel_measurable"):
        return {"status": S2F0, "reasons": ["not an accepted grounded leak-free F4 mechanism"]}

    metrics = list(f.get("distinct_metrics", ()))
    if not metrics:
        return {"status": S2F0, "reasons": ["no deterministically derived metric"]}

    # 2. S2F4 -- a concept outside the frozen Stage-1 discovery vocabulary has no agreed
    #    semantics and must not be guessed at.
    from src.research.item6.provider_vocab import PROVIDER_METRICS
    unknown = sorted(m for m in metrics
                     if m not in PROVIDER_METRICS and m not in PM.AGAINST_ALIAS)
    if unknown:
        return {"status": S2F4, "reasons": [f"semantics unresolved: {unknown}"]}

    # 3. S2F2 -- packet-only structural observables carry no historical measurement path.
    packet_only = sorted(m for m in metrics if m in PM.STRUCTURAL_OBSERVABLES)
    if packet_only:
        return {"status": S2F2, "reasons": [f"packet-only structural observable: {packet_only}"]}

    # 4. S2F1 -- the FootyStats corpus records no field for the concept at all.
    absent = PM.unmeasurable_metrics(metrics)
    if absent:
        return {"status": S2F1, "reasons": [f"no FootyStats field: {absent}"]}

    # 5. S2F6 -- temporal resolution. A half/sequence claim must be anchored in half-period
    #    evidence, and every metric cited at half resolution must be half-capable.
    half_needed = half_resolution_metrics_required(f)
    not_half_capable = [m for m in half_needed if not PM.is_half_capable(m)]
    if not_half_capable:
        return {"status": S2F6,
                "reasons": [f"half resolution cited for non-half-capable metric: "
                            f"{sorted(not_half_capable)}"]}
    if _asserts_half_or_sequence(f) and not half_needed:
        return {"status": S2F6,
                "reasons": ["asserts half-state/sequencing novelty but cites no first/second-"
                            "half evidence; no point-in-time-safe sequence representation "
                            "exists at full-match resolution"]}

    # 6. S2F7 -- a required threshold with no deterministic policy to supply it. The frozen
    #    Stage-2 threshold policy covers every continuous measurable metric via in-fold
    #    quantile binning, so this is expected to be empty; it stays as a fail-closed branch.
    ext = f.get("required_extension")
    if ext is None:
        return {"status": S2F0, "reasons": ["F4 without a required additive extension"]}
    if ext not in EXISTING_EXTENSIONS + NEW_EXTENSIONS:
        return {"status": S2F7, "reasons": [f"no deterministic policy for extension {ext}"]}

    status = S2F8 if ext in EXISTING_EXTENSIONS else S2F9
    return {"status": status,
            "reasons": reasons or [f"feasible via {ext}"],
            "required_extension": ext,
            "half_resolution_metrics": half_needed}


def run_funnel(formalizations: Sequence[Dict]) -> Dict[str, object]:
    """Classify every frozen Stage-1 formalization. Returns per-mechanism rows + counts.

    Duplicate collapse (S2F5) is applied AFTER per-mechanism classification, over the
    canonical family key, so that the surviving representative of a canonically equivalent
    group is chosen deterministically (lowest sort order), never by predictive merit.
    """
    from src.research.item6.stage2.canonical_family import canonical_key

    rows: List[Dict[str, object]] = []
    for idx, f in enumerate(formalizations):
        res = classify_mechanism(f)
        rows.append({
            "seq": idx,
            "fixture_id": f.get("_fixture_id"),
            "mechanism_id_local": f.get("mechanism_id_local"),
            "metrics": sorted(f.get("distinct_metrics", ())),
            "novelty_signals": sorted(f.get("novelty_signals", ())),
            "required_extension": f.get("required_extension"),
            "canonical_key": canonical_key(f),
            **res,
        })

    # S2F5: within the feasible set, collapse canonically equivalent mechanisms.
    seen: Dict[str, int] = {}
    for r in sorted(rows, key=lambda x: (str(x["canonical_key"]), str(x["fixture_id"]),
                                         str(x["mechanism_id_local"]))):
        if r["status"] not in FEASIBLE_STATUSES:
            continue
        k = str(r["canonical_key"])
        if k in seen:
            r["status"] = S2F5
            r["reasons"] = [f"canonically equivalent to seq {seen[k]}"]
            r["collapsed_into_seq"] = seen[k]
        else:
            seen[k] = int(r["seq"])

    counts = collections.Counter(str(r["status"]) for r in rows)
    return {
        "funnel_version": FUNNEL_VERSION,
        "provider_measurability_version": PM.PROVIDER_MEASURABILITY_VERSION,
        "n_mechanisms_in": len(rows),
        "status_counts": {s: int(counts.get(s, 0)) for s in ALL_STATUSES},
        "n_feasible": sum(int(counts.get(s, 0)) for s in FEASIBLE_STATUSES),
        "n_infeasible": len(rows) - sum(int(counts.get(s, 0)) for s in FEASIBLE_STATUSES),
        "n_distinct_feasible_canonical_keys": len(seen),
        "rows": sorted(rows, key=lambda x: int(x["seq"])),
        "reads_outcomes": False,
        "reads_llm_provider_requirements": False,
    }


def version_stamp() -> Dict[str, object]:
    return {
        "funnel_version": FUNNEL_VERSION,
        "statuses": list(ALL_STATUSES),
        "feasible_statuses": list(FEASIBLE_STATUSES),
        "measurement_requirement_source": "deterministic_distinct_metrics",
        "llm_provider_requirements_used": False,
        "temporal_resolution_source": "cited_evidence_ref_period",
        "llm_temporal_declaration_used": False,
        "reads_outcomes": False,
    }
