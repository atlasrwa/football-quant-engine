"""V7 walk-forward design + discovery/confirmation split + candidate lock + arm control.
Phases 12, 13, 20, 21, 22, 23. FROZEN before any confirmatory OOS computation.

- Rolling-origin temporal folds over the corpus timeline; every transformation in a fold is
  fitted on the training PAST only. Random train/test splitting is FORBIDDEN as primary OOS.
- An explicit DEVELOPMENT window precedes the CONFIRMATORY window; deterministic tuning is
  permitted only on DEVELOPMENT and is labelled as such, never confirmatory.
- Candidate specifications are hashed and locked BEFORE OOS; a candidate changed after any OOS
  inspection loses confirmatory status.
- The Base-vs-Research control is matched on (originating fixture, target family, canonical
  metric, measurability class), NOT raw counts, so verbosity cannot reward an arm.

ZERO SPEND. No effects computed. No OOS outcomes read.
"""
from __future__ import annotations

import datetime
import hashlib
import json

WALKFORWARD_VERSION = "v7_walkforward_v3"

# corpus timeline (verified from corpus_adapter): 2023-08 .. 2026-05, ~3 seasons.
# Development window = the earliest history used only for apparatus validation + permitted
# deterministic tuning. Confirmatory OOS begins strictly AFTER development ends.
DEVELOPMENT_END_ISO = "2024-12-31"          # dev = corpus start .. 2024-12-31 inclusive
CONFIRMATORY_START_ISO = "2025-01-01"       # confirmatory OOS folds begin here

# rolling-origin folds over the confirmatory window. Each fold: train = all history strictly
# before the fold's validation block; validate = the fold's forward block. Frozen boundaries.
FOLD_VALIDATION_MONTHS = 3                  # each validation block is a 3-month forward span
MIN_TRAINING_HISTORY_DAYS = 365             # a fold needs >=1yr of prior history to train
RETRAIN_SCHEDULE = "EACH_FOLD_FROM_PAST_ONLY"
FOLD_WEIGHTING = "EQUAL_ACROSS_FOLDS"       # no fold is up-weighted after seeing results
MISSING_FEATURE_BEHAVIOR = "EXCLUDE_OBSERVATION_RECORD_COUNT"
RANDOM_SPLIT_ALLOWED_AS_PRIMARY = False     # HARD: temporal only for primary evidence


def _iso_to_unix(iso: str) -> int:
    return int(datetime.datetime.strptime(iso, "%Y-%m-%d")
               .replace(tzinfo=datetime.timezone.utc).timestamp())


def build_folds(corpus_min_unix: int, corpus_max_unix: int) -> dict:
    """Deterministic rolling-origin confirmatory folds. Returns fold boundaries only (no data,
    no outcomes)."""
    conf_start = _iso_to_unix(CONFIRMATORY_START_ISO)
    dev_end = _iso_to_unix(DEVELOPMENT_END_ISO)
    folds = []
    block = FOLD_VALIDATION_MONTHS * 30 * 86400
    start = conf_start
    i = 0
    while start < corpus_max_unix:
        end = start + block
        train_days = (start - corpus_min_unix) / 86400.0
        folds.append({
            "fold_index": i,
            "train_end_unix": start,
            "train_end_iso": datetime.datetime.utcfromtimestamp(start).strftime("%Y-%m-%d"),
            "validate_start_unix": start,
            "validate_end_unix": min(end, corpus_max_unix),
            "validate_end_iso": datetime.datetime.utcfromtimestamp(
                min(end, corpus_max_unix)).strftime("%Y-%m-%d"),
            "train_history_days": round(train_days, 1),
            "min_history_satisfied": train_days >= MIN_TRAINING_HISTORY_DAYS,
        })
        start = end
        i += 1
    return {
        "walkforward_version": WALKFORWARD_VERSION,
        "development_window": {"start_iso": datetime.datetime.utcfromtimestamp(
            corpus_min_unix).strftime("%Y-%m-%d"), "end_iso": DEVELOPMENT_END_ISO,
            "purpose": "apparatus validation + permitted deterministic tuning ONLY; "
                       "never confirmatory evidence"},
        "confirmatory_window": {"start_iso": CONFIRMATORY_START_ISO,
                                "end_iso": datetime.datetime.utcfromtimestamp(
                                    corpus_max_unix).strftime("%Y-%m-%d")},
        "dev_end_unix": dev_end, "confirmatory_start_unix": conf_start,
        "fold_validation_months": FOLD_VALIDATION_MONTHS,
        "min_training_history_days": MIN_TRAINING_HISTORY_DAYS,
        "retrain_schedule": RETRAIN_SCHEDULE, "fold_weighting": FOLD_WEIGHTING,
        "missing_feature_behavior": MISSING_FEATURE_BEHAVIOR,
        "random_split_allowed_as_primary": RANDOM_SPLIT_ALLOWED_AS_PRIMARY,
        "n_confirmatory_folds": len(folds),
        "folds_with_min_history": sum(1 for f in folds if f["min_history_satisfied"]),
        "folds": folds,
    }


# ---- candidate lock (Phase 22/23): hash candidate specs BEFORE OOS --------------------
def candidate_lock_hash(candidate_specs: list) -> str:
    """Deterministic hash over the ordered, canonicalized candidate specifications. Any change
    to a candidate after this hash is computed invalidates confirmatory status."""
    blob = json.dumps(sorted(candidate_specs, key=lambda c: c.get("canonical_hypothesis_id",
                                                                   "")),
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---- arm control (Phase 20/21): verbosity-neutral matched comparison ------------------
CONTROL_PRIMARY_ENDPOINT = (
    "rate at which a canonical hypothesis-family reaches OOS_SURVIVES, compared between "
    "BASE-origin and RESEARCH-origin families, matched within (originating fixture, "
    "multiplicity family, canonical metric, measurability class), with fixture/family "
    "clustering. Raw hypothesis counts are NEVER the endpoint; an arm is not rewarded for "
    "producing more hypotheses.")
CONTROL_SECONDARY = ("continuous OOS-quality score (shrinkage-adjusted, fold-direction-stable) "
                     "compared arm-vs-arm with clustered inference.")


#: Minimum matched-cell support for the PRIMARY arm-comparison endpoint to be answerable.
#: Frozen here, and evaluable RIGHT NOW because cell membership is a pure function of the
#: immutable V6.1 universe plus the measurability gate -- it consults NO outcome. A design
#: that cannot reach these numbers cannot answer the primary question, and saying so BEFORE
#: OOS is the point of the gate.
MIN_MATCHED_CELLS = 12
MIN_MATCHED_FIXTURES = 5
MIN_FAMILIES_PER_ARM_IN_MATCHED = 12


def matched_cells(dedup_families: list, measurable_ids=None) -> dict:
    """Define verbosity-neutral matched cells for the arm comparison.

    A cell is keyed by (originating fixture, multiplicity family, canonical metric). Base and
    Research families are placed into cells; cells present in only one arm are recorded as
    OPPORTUNITY-only and excluded from the matched primary (reported separately).

    When `measurable_ids` is supplied the cells are restricted to MEASURABLE families, which
    is what the frozen primary endpoint actually specifies (it matches within measurability
    class). No effects are consulted -- measurability is an effect-blind schema/coverage gate.
    """
    from src.research.hypothesis_v7 import analysis_spec as A
    keep = set(measurable_ids) if measurable_ids is not None else None
    cells = {}
    for fam in dedup_families:
        if keep is not None and fam["canonical_hypothesis_id"] not in keep:
            continue
        cspec = fam["canonical_spec"]
        mf = A.multiplicity_family_of(cspec.get("FAMILY"))
        metric_key = ",".join(cspec.get("TARGET") or [])
        for origin in fam["origins"]:
            key = f"{origin['originating_fixture']}|{mf}|{metric_key}"
            c = cells.setdefault(key, {"cell": key, "base": 0, "research": 0,
                                       "fixture": origin["originating_fixture"]})
            c[origin["arm"]] = c.get(origin["arm"], 0) + 1
    matched = [c for c in cells.values() if c["base"] > 0 and c["research"] > 0]
    base_only = [c for c in cells.values() if c["base"] > 0 and c["research"] == 0]
    research_only = [c for c in cells.values() if c["research"] > 0 and c["base"] == 0]
    return {"restricted_to_measurable": measurable_ids is not None,
            "n_cells": len(cells), "n_matched_cells": len(matched),
            "n_base_only_cells": len(base_only),
            "n_research_only_cells": len(research_only),
            "n_matched_fixtures": len({c["fixture"] for c in matched}),
            "n_base_families_in_matched": sum(c["base"] for c in matched),
            "n_research_families_in_matched": sum(c["research"] for c in matched),
            "matched_cells": sorted(matched, key=lambda c: c["cell"]),
            "note": "matched cells drive the primary arm comparison; single-arm cells are "
                    "opportunity structure, reported separately, never counted as arm wins"}


def endpoint_feasibility(matched: dict) -> dict:
    """Can the FROZEN primary arm-comparison endpoint actually be answered?

    Evaluated BEFORE any OOS computation, from outcome-blind structure only. If the matched
    design is degenerate, no amount of OOS computation can rescue it, and the scientifically
    honest move is to say so now rather than to run the folds and then quietly substitute a
    different endpoint. Returns the verdict plus the frozen fallback that applies.
    """
    reasons = []
    if matched["n_matched_cells"] < MIN_MATCHED_CELLS:
        reasons.append(f"n_matched_cells={matched['n_matched_cells']} < "
                       f"{MIN_MATCHED_CELLS}")
    if matched["n_matched_fixtures"] < MIN_MATCHED_FIXTURES:
        reasons.append(f"n_matched_fixtures={matched['n_matched_fixtures']} < "
                       f"{MIN_MATCHED_FIXTURES}")
    for arm in ("base", "research"):
        k = f"n_{arm}_families_in_matched"
        if matched[k] < MIN_FAMILIES_PER_ARM_IN_MATCHED:
            reasons.append(f"{k}={matched[k]} < {MIN_FAMILIES_PER_ARM_IN_MATCHED}")
    feasible = not reasons
    return {
        "primary_endpoint_feasible": feasible,
        "thresholds": {"min_matched_cells": MIN_MATCHED_CELLS,
                       "min_matched_fixtures": MIN_MATCHED_FIXTURES,
                       "min_families_per_arm_in_matched":
                           MIN_FAMILIES_PER_ARM_IN_MATCHED},
        "reasons": reasons or ["matched design supports the primary endpoint"],
        "evaluated_before_oos": True,
        "depends_on_effect": False,
        "fallback_if_infeasible": FALLBACK_ENDPOINT,
        "consequence": ("V7_PRE_OOS_BLOCKED for the arm-comparison endpoint: confirmatory OOS "
                        "may not be authorized against an endpoint the design cannot answer"),
    }


# ---- Phase 20 Control B: the deterministic null benchmark endpoint -------------------
#: Because the matched arm design was proven infeasible before OOS, the PRIMARY control is the
#: deterministic null benchmark: mechanically enumerated generic hypotheses pushed through the
#: identical pipeline. Frozen thresholds for that endpoint to be answerable.
MIN_NULL_MEASURABLE_FAMILIES = 30
MAX_ORIGIN_MEASURABILITY_RATE_GAP = 0.25   # null must not be crippled by construction
MAX_ORIGIN_COMPARATOR_REJECT_GAP = 0.25

NULL_PRIMARY_ENDPOINT = (
    "rate at which a canonical hypothesis-family reaches OOS_SURVIVES, compared between "
    "V6.1-ORIGIN families and DETERMINISTIC_NULL families, on count-balanced measurable sets, "
    "with family/metric clustering. Both origins pass through the identical canonicalization, "
    "deduplication, measurability, support, fold and outcome-class pipeline; the ONLY "
    "difference is where the question came from. If V6.1 hypotheses do not exceed the "
    "mechanically enumerated null, the LLM added no football information.")


def null_endpoint_feasibility(*, n_null_measurable, v61_measurability_rate,
                              null_measurability_rate, v61_comparator_reject_rate,
                              null_comparator_reject_rate) -> dict:
    """Can the FROZEN null-benchmark endpoint be answered, and is the null construction FAIR?

    Two failure modes are checked, both outcome-blind. (1) Too few measurable null families to
    compare against. (2) The null is disadvantaged BY CONSTRUCTION -- if it fails measurability
    or comparator screening at a very different rate from V6.1, any survival gap would reflect
    grammar rather than football content.
    """
    reasons = []
    if n_null_measurable < MIN_NULL_MEASURABLE_FAMILIES:
        reasons.append(f"n_null_measurable={n_null_measurable} < "
                       f"{MIN_NULL_MEASURABLE_FAMILIES}")
    meas_gap = abs(v61_measurability_rate - null_measurability_rate)
    if meas_gap > MAX_ORIGIN_MEASURABILITY_RATE_GAP:
        reasons.append(f"measurability-rate gap {meas_gap:.3f} > "
                       f"{MAX_ORIGIN_MEASURABILITY_RATE_GAP} (null disadvantaged by "
                       f"construction)")
    comp_gap = abs(v61_comparator_reject_rate - null_comparator_reject_rate)
    if comp_gap > MAX_ORIGIN_COMPARATOR_REJECT_GAP:
        reasons.append(f"comparator-reject-rate gap {comp_gap:.3f} > "
                       f"{MAX_ORIGIN_COMPARATOR_REJECT_GAP} (null disadvantaged by "
                       f"construction)")
    return {"null_endpoint_feasible": not reasons,
            "n_null_measurable": n_null_measurable,
            "v61_measurability_rate": round(v61_measurability_rate, 4),
            "null_measurability_rate": round(null_measurability_rate, 4),
            "measurability_rate_gap": round(meas_gap, 4),
            "v61_comparator_reject_rate": round(v61_comparator_reject_rate, 4),
            "null_comparator_reject_rate": round(null_comparator_reject_rate, 4),
            "comparator_reject_rate_gap": round(comp_gap, 4),
            "thresholds": {
                "min_null_measurable_families": MIN_NULL_MEASURABLE_FAMILIES,
                "max_origin_measurability_rate_gap": MAX_ORIGIN_MEASURABILITY_RATE_GAP,
                "max_origin_comparator_reject_gap": MAX_ORIGIN_COMPARATOR_REJECT_GAP},
            "evaluated_before_oos": True, "depends_on_effect": False,
            "reasons": reasons or ["null benchmark supports the primary endpoint"]}


FALLBACK_ENDPOINT = (
    "If and only if the matched design is declared INFEASIBLE here -- before any OOS -- the "
    "arm comparison is DEMOTED to descriptive reporting (per-arm survival profiles with "
    "fixture/family clustering and explicit opportunity-structure accounting) and is NEVER "
    "reported as a confirmatory arm effect. The V7 hypothesis-level endpoints (measurability, "
    "support, confounder survival, OOS survival, stability) remain confirmatory in their own "
    "right because they do not require an arm contrast. This substitution rule is frozen NOW, "
    "outcome-blind; it may not be invoked after inspecting any OOS result.")


def version_stamp() -> dict:
    return {"walkforward_version": WALKFORWARD_VERSION,
            "primary_is_temporal": True,
            "random_split_allowed_as_primary": RANDOM_SPLIT_ALLOWED_AS_PRIMARY,
            "development_end": DEVELOPMENT_END_ISO,
            "confirmatory_start": CONFIRMATORY_START_ISO,
            "fold_validation_months": FOLD_VALIDATION_MONTHS,
            "retrain_schedule": RETRAIN_SCHEDULE,
            "candidate_lock": "SHA-256 over canonical candidate specs before OOS; "
                              "post-OOS change invalidates confirmatory status",
            "control_primary_endpoint": NULL_PRIMARY_ENDPOINT,
            "control_arm_endpoint_demoted": CONTROL_PRIMARY_ENDPOINT,
            "control_secondary": CONTROL_SECONDARY,
            "fallback_endpoint": FALLBACK_ENDPOINT,
            "min_null_measurable_families": MIN_NULL_MEASURABLE_FAMILIES,
            "max_origin_measurability_rate_gap": MAX_ORIGIN_MEASURABILITY_RATE_GAP,
            "min_matched_cells": MIN_MATCHED_CELLS,
            "min_matched_fixtures": MIN_MATCHED_FIXTURES,
            "min_families_per_arm_in_matched": MIN_FAMILIES_PER_ARM_IN_MATCHED,
            "verbosity_neutral": True}
