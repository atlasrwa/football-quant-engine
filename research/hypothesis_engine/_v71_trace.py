"""V7.1 SECTION 3: machine-readable semantic trace of the LLM-to-measurement path.

For every V6.1 hypothesis this walks the complete path

    V6.1 model response -> adjudication -> canonicalization -> deduplication
    -> comparator assignment -> cohort definition -> baseline definition
    -> compiler -> historical rows selected -> signal -> OOS estimator

and records, per stage: the inputs, the outputs, what information was LOST, which implicit
default was applied, and whether the stage failed closed. The trace exists to answer ONE
question for a human reader:

    "Did the deterministic query actually test the football question the structured
     hypothesis represents?"

DIAGNOSTIC AND STRUCTURAL ONLY. It reads no effect, no p-value, no OOS outcome. It runs
against the already-viewed V6.1/V7 universe, so nothing it produces is confirmatory.

ZERO SPEND. No Bedrock. No CHAMPION.
"""
from __future__ import annotations

import collections
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/src")

from src.research.hypothesis_v7 import analysis_spec as V7A
from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v71 import ontology as ONT

ROOT = "/home/ubuntu"
V7OUT = f"{ROOT}/research/hypothesis_oos/out/v7"
OUT = f"{ROOT}/research/hypothesis_oos/out/v7_1"

#: Condition dimensions the V7 executor's `_apply_conditions` actually implemented. Every
#: other dimension hit its `else: return []` branch -- a SILENT fallback that turned an
#: unsupported restriction into an empty cohort, indistinguishable downstream from a
#: genuinely unsupported hypothesis.
V7_IMPLEMENTED_DIMENSIONS = {"historical_venue_conditioning", "opponent_profile"}

#: Comparators the V7 executor branched on. Everything else fell through to a single generic
#: subject-vs-subject contrast regardless of the semantics `VALID_COMPARATORS` declared.
V7_IMPLEMENTED_COMPARATORS = {"SUBJECT_VENUE_BASELINE", "SUBJECT_RECENT_VS_LONG_BASELINE",
                              "SUBJECT_OVERALL_BASELINE"}


def _load_raw_hypotheses(exec_dir):
    rows = []
    raw = f"{exec_dir}/raw"
    for fn in sorted(os.listdir(raw)):
        if not fn.endswith(".json"):
            continue
        doc = json.load(open(f"{raw}/{fn}"))
        for h in (doc.get("payload") or {}).get("hypotheses") or []:
            rows.append((int(doc["seq"]), fn, h))
    return rows


def trace_one(spec, cap):
    """The per-hypothesis stage trace. Pure structure; no measurement."""
    stages = []

    # --- stage: comparator assignment -----------------------------------------------
    comparator = (spec.get("comparison") or "").strip().upper() or None
    declared = V7A.VALID_COMPARATORS.get(comparator)
    stages.append({
        "stage": "comparator_assignment",
        "input": {"comparison": comparator},
        "output": {"declared_semantics": declared},
        "information_lost": (None if declared else
                             "comparator has no declared semantics; V7 would refuse it"),
        "implicit_default": None,
        "v7_behaviour": ("implemented" if comparator in V7_IMPLEMENTED_COMPARATORS
                         else "SILENT FALLBACK to generic subject-vs-subject contrast"),
        "fails_closed": comparator in V7_IMPLEMENTED_COMPARATORS or declared is None,
    })

    # --- stage: condition normalisation ---------------------------------------------
    filters, dropped, unsupported = IRM.normalise_conditions(spec.get("conditions"))
    raw_conds = spec.get("conditions") or []
    v7_unknown = [c.get("dimension") for c in raw_conds
                  if isinstance(c, dict)
                  and c.get("dimension") not in V7_IMPLEMENTED_DIMENSIONS]
    stages.append({
        "stage": "condition_normalisation",
        "input": {"n_raw_conditions": len(raw_conds),
                  "dimensions": sorted({c.get("dimension") for c in raw_conds
                                        if isinstance(c, dict)})},
        "output": {"n_restrictive": len(filters),
                   "dropped_non_restrictive": list(dropped),
                   "unsupported": list(unsupported)},
        "information_lost": (
            "a non-restrictive value (ANY/ALL/null) was counted by V7 as a condition, which "
            "let a degenerate comparator bypass the degeneracy fast path"
            if dropped else None),
        "implicit_default": (
            "V7 `_apply_conditions` returned [] for an unrecognised dimension, so the cohort "
            "became EMPTY and the hypothesis was dropped as no-support rather than named as "
            "an unsupported restriction"
            if v7_unknown else None),
        "v7_behaviour": ("SILENT EMPTY COHORT" if v7_unknown else "implemented"),
        "fails_closed": not v7_unknown,
    })

    # --- stage: IR construction (V7.1 only; V7 had no such stage) -------------------
    ir = IRM.build_ir(spec)
    stages.append({
        "stage": "semantic_ir",
        "input": {k: spec.get(k) for k in
                  ("target_metrics", "subject", "side", "comparison", "window")},
        "output": {"status": ir.status, "ir_id": ir.ir_id()[:16],
                   "cohort": list(ir.cohort.key()) if ir.cohort else None,
                   "baseline": list(ir.baseline.key()) if ir.baseline else None},
        "information_lost": None,
        "implicit_default": None,
        "v7_behaviour": "STAGE ABSENT IN V7",
        "fails_closed": True,
    })

    # --- stage: structural invariants ------------------------------------------------
    inv = INV.check(ir, capability=cap)
    stages.append({
        "stage": "compiler_invariants",
        "input": {"ir_status": ir.status},
        "output": {"ok": inv["ok"], "codes": inv["codes"]},
        "information_lost": None,
        "implicit_default": None,
        "v7_behaviour": ("V7 emitted signal == 0 for an identical cohort/baseline and let a "
                         "full walk-forward run before classifying it TAUTOLOGICAL"
                         if INV.IDENTICAL_COHORT_BASELINE in inv["codes"] else "n/a"),
        "fails_closed": True,
    })

    # --- stage: capability / measurability -------------------------------------------
    status, adm, per_metric = cap.classify_metrics(ir.target_metrics)
    stages.append({
        "stage": "provider_capability",
        "input": {"target_metrics": list(ir.target_metrics)},
        "output": {"status": status, "admissible_competitions": sorted(adm),
                   "per_metric": {m: s for m, (s, _d) in per_metric.items()}},
        "information_lost": (
            "V7 required all six competitions, so a metric fully covered in a large frozen "
            "subset was discarded rather than measured on a reported restricted universe"
            if status == CAP.RESTRICTED else None),
        "implicit_default": None,
        "v7_behaviour": ("REJECTED (full-6 gate)" if status == CAP.RESTRICTED
                         else "same verdict"),
        "fails_closed": True,
    })

    answers_the_question = (
        ir.status == IRM.OK and inv["ok"]
        and status in (CAP.SUPPORTED, CAP.RESTRICTED))
    return {"ir_status": ir.status, "ir_id": ir.ir_id(),
            "reconstructed_meaning": ir.describe(),
            "invariant_codes": inv["codes"],
            "capability_status": status,
            "admissible_competitions": sorted(adm),
            "deterministic_query_tests_the_stated_question": answers_the_question,
            "stages": stages}


def main():
    os.makedirs(OUT, exist_ok=True)
    cov = json.load(open(f"{V7OUT}/V7_COVERAGE_MATRIX.json"))
    cap = CAP.CapabilityContract(cov)
    cap.assert_block_is_not_provider()

    universe = json.load(open(f"{V7OUT}/V7_HYPOTHESIS_UNIVERSE.json"))
    qualified_ids = {(h["response_seq"], h["hypothesis_id"]) for h in universe["hypotheses"]}

    raw = _load_raw_hypotheses(f"{ROOT}/research/hypothesis_oos/out/v6_1/execution")
    rows, counts = [], collections.Counter()
    for seq, fn, h in raw:
        qualified = (seq, h.get("hypothesis_id")) in qualified_ids
        t = trace_one(h, cap)
        counts[("qualified" if qualified else "unqualified", t["ir_status"],
                tuple(t["invariant_codes"]), t["capability_status"])] += 1
        rows.append({"response_seq": seq, "raw_file": fn,
                     "hypothesis_id": h.get("hypothesis_id"),
                     "v6_1_qualified": qualified,
                     "stated_question": h.get("question"),
                     **t})

    q = [r for r in rows if r["v6_1_qualified"]]
    summary = {
        "n_raw": len(rows), "n_qualified": len(q),
        "qualified_ir_status": dict(collections.Counter(r["ir_status"] for r in q)),
        "qualified_invariant_codes": dict(collections.Counter(
            c for r in q for c in r["invariant_codes"])),
        "qualified_capability_status": dict(collections.Counter(
            r["capability_status"] for r in q)),
        "qualified_query_tests_stated_question": sum(
            1 for r in q if r["deterministic_query_tests_the_stated_question"]),
    }
    doc = {"trace_version": "v71_trace_v1",
           "classification": ["DIAGNOSTIC_ONLY", "NON_CONFIRMATORY",
                              "OUTCOME_ALREADY_VIEWED"],
           "reads_effects": False, "reads_pvalues": False, "reads_oos_outcomes": False,
           "ontology_version": ONT.ONTOLOGY_VERSION,
           "ir_version": IRM.IR_VERSION,
           "invariants_version": INV.INVARIANTS_VERSION,
           "capability_version": CAP.CAPABILITY_VERSION,
           "summary": summary, "rows": rows}
    path = f"{OUT}/V7_1_SEMANTIC_TRACE.json"
    json.dump(doc, open(path, "w"), indent=1, sort_keys=True)
    print(json.dumps(summary, indent=1))
    print(f"\nwritten: {path}")


if __name__ == "__main__":
    main()
