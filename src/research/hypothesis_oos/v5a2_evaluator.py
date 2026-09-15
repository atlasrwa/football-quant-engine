"""V5A.2 frozen evaluator (`v5a2_evaluator_v1`). ZERO SPEND -- reads responses, calls nothing.

FROZEN BEFORE THE FIRST PAID CALL, and frozen in the same commit as the packets it scores.

EVERY THRESHOLD IS V5A.1'S, CARRIED FORWARD UNCHANGED.
`DISCIPLINE_TOLERANCE`, `MIN_SELF_NOISE_FLOOR`, `PRIMARY_METRIC` and the PASS/MIXED/FAIL
gate are byte-for-byte the same decisions, taken before V5A.1 ran and therefore not
reachable by anything V5A.1 revealed. Moving any of them now would be indistinguishable
from tuning the apparatus to rescue a result, which task S14 forbids.

WHAT IS NEW IS NOT A THRESHOLD BUT A DISTINCTION (task S13)
-----------------------------------------------------------
V5A.1 conflated two questions that have different answers:

    EXECUTION STATUS       did the battery run to completion?
    SCIENTIFIC STATUS      is there enough valid data to answer the research question?

V5A.1 stopped at 6 of 38 calls, so its execution status was STOPPED. But even had all 38
calls completed, 0 valid research-arm responses would have made the science unanswerable.
Reporting one number for both invites reading "FAIL" as "the research idea failed" when
what actually failed was the plumbing. So the verdict now carries both, and a scientific
verdict is only issued when the evaluability gate is met.

The evaluability minimums are set from what a paired comparison NEEDS, not from what
V5A.1 achieved -- V5A.1 is NON_EVALUABLE under them by a wide margin, which is the correct
description of what happened to it.

FAILURE CLASSIFICATION (task S15)
---------------------------------
`MODEL_SCHEMA_INVALID` is a scientific observation: the model wrote something outside a
contract it was shown. `INFRASTRUCTURE_CONTRACT_FAILURE` is our defect: the apparatus could
not express a legal response. V5A.1's stop rule counted them together, so the run was
halted by a rate that was really measuring our own namespace bug. They are separated here
and given different stop rules, because they warrant different responses.

Nothing in this module may change once execution begins.
"""
from __future__ import annotations

import math
import statistics

from src.research.hypothesis_engine import lifecycle, query_plan as QP
from src.research.hypothesis_engine import validator_v4 as V4
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a2_admissibility as ADM
from src.research.hypothesis_oos import v5a2_ontology as O

EVALUATOR_VERSION = "v5a2_evaluator_v1"

# ----------------------------------------------------------------------------------------
# FROZEN THRESHOLDS -- inherited from v5a1_evaluator_v1, unchanged.
# ----------------------------------------------------------------------------------------
DISCIPLINE_TOLERANCE = 0.05
MIN_SELF_NOISE_FLOOR = 0.5
PRIMARY_METRIC = "grounded_accepted_n"

# ----------------------------------------------------------------------------------------
# FROZEN EVALUABILITY MINIMUMS (task S13). New concept, not a relaxed threshold.
#
# Chosen from what the comparison requires:
#   * the primary analysis is a PAIRED per-fixture difference, so it needs fixtures with a
#     valid response in BOTH arms. The battery plans 10; 8 tolerates two losses while
#     leaving a paired sample that is not dominated by any single fixture.
#   * the self-noise floor is a pooled within-(fixture, arm) SD, which needs at least 3
#     repeatability groups per arm to be an estimate rather than an anecdote.
# ----------------------------------------------------------------------------------------
MIN_PAIRED_FIXTURES = 8
MIN_VALID_RESPONSES_PER_ARM = 8
MIN_REPEATABILITY_GROUPS_PER_ARM = 3

# ----------------------------------------------------------------------------------------
# FROZEN STOP RULES (task S15).
# ----------------------------------------------------------------------------------------
#: Unchanged from V5A.1 in both threshold and meaning -- but the numerator is now MODEL
#: schema-invalid only. In V5A.1 this rule fired at 2/6 on two INFRASTRUCTURE failures.
MODEL_SCHEMA_INVALID_RATE_STOP = 0.30
#: Made explicit rather than changed: V5A.1's rule was first evaluated at 6 calls, so 6 is
#: what it always was. Stating it stops the rate firing at 1/1.
MIN_CALLS_BEFORE_RATE_STOP = 6
#: Strictly stricter than anything V5A.1 had. Our own contract defects are expected to be
#: ZERO after this closure, so the first one halts the run rather than being averaged in.
INFRASTRUCTURE_CONTRACT_FAILURE_STOP_N = 1
#: Unchanged.
CONSECUTIVE_TRANSPORT_FAILURE_STOP_N = 3

#: Availability-aware dimensions, keyed on ONTOLOGY TERMS. V5A.1 keyed these on its private
#: availability names (`venue_splits`, `opponent_profile_response`); against a V5A.2 packet
#: those lookups would silently return "not exposed" and score every dimension as zero.
AVAILABILITY_DIMENSIONS = {
    "venue_use": O.HISTORICAL_VENUE_CONDITIONING,
    "recent_vs_long_use": "recent_window_summaries",
    "opponent_profile_use": "opponent_profile",
    "formation_use": "formation_recorded_history",
}

_EXPOSED = (E.EXPOSED, E.EXPOSED_LOW_COVERAGE)


def _refs(h):
    return list(h.get("evidence_refs") or [])


def _ref_kind(ref: str) -> str:
    return ref.split(":")[0] if ":" in ref else "OTHER"


def _is_interaction(h) -> bool:
    return len(h.get("conditions") or []) >= 2


def _degenerate(h) -> bool:
    return any(str(c.get("value")) == "ANY" for c in (h.get("conditions") or []))


def _meaningful_interaction(h, valid_ids, packet) -> bool:
    """Frozen classifier, identical in substance to V5A.1's."""
    conds = h.get("conditions") or []
    if len(conds) < 2:
        return False
    dims = [c.get("dimension") for c in conds]
    if len(set(dims)) != len(dims):
        return False
    if any(str(c.get("value")) == "ANY" for c in conds):
        return False
    if ADM.packet_admissibility_reasons(h, packet):
        return False
    return len({r for r in _refs(h) if r in valid_ids}) >= 2


def _blank_score() -> dict:
    d = {
        "parsed": False, "n_hypotheses": 0, "n_schema_ok": 0,
        "grounded_accepted_n": 0, "compiled_n": 0, "compilable_n": 0,
        "n_refs": 0, "n_valid_refs": 0, "n_fabricated_refs": 0,
        "n_abstentions": 0, "n_abstentions_with_refs": 0, "n_degenerate": 0,
        "n_interactions": 0, "n_meaningful_interactions": 0,
        "n_unsupported_dimension": 0, "n_firewall_blocked": 0,
        "ref_kinds": {}, "baselines": {}, "metric_families": {},
        "target_metrics": {}, "n_duplicate_hypotheses": 0,
        "whole_response_failure": None, "failure_class": None,
        "n_apparatus_defects": 0,
    }
    # Availability keys always present, so a whole-response failure never produces a
    # KeyError in the aggregation layer (the V5A.1 driver hit exactly that).
    for name in AVAILABILITY_DIMENSIONS:
        d[name] = 0
        d[f"{name}_available"] = False
    return d


def score_response(raw, packet) -> dict:
    """Score ONE model response against ONE packet. Pure function of the two."""
    out = _blank_score()
    if raw is None:
        out["whole_response_failure"] = "NO_TOOL_USE"
        return out
    out["parsed"] = True

    valid_ids = E.resolve_evidence_ids(packet)
    res = V4.validate(raw, packet=packet,
                      expected_packet_hash=packet["packet_hash"],
                      expected_fixture_id=packet["fixture_id"])
    if not res.accepted:
        out["whole_response_failure"] = res.failure
        out["failure_class"] = res.failure_class
        out["n_hypotheses"] = len(raw.get("hypotheses") or [])
        if res.failure in (lifecycle.NUMERICAL_AUTHORITY_VIOLATION,
                           lifecycle.LATENT_GRADING_VIOLATION):
            out["n_firewall_blocked"] = out["n_hypotheses"]
        return out

    # An apparatus defect on ANY hypothesis makes the whole response an apparatus event:
    # the stop rule that counts our own bugs must see it even when the response otherwise
    # validated.
    out["n_apparatus_defects"] = len(res.apparatus_defects)
    if res.apparatus_defects:
        out["failure_class"] = V4.INFRASTRUCTURE_CONTRACT_FAILURE

    hyps = (res.canonical_payload or raw).get("hypotheses") or []
    out["n_hypotheses"] = len(hyps)
    out["n_schema_ok"] = len(hyps)
    seen = set()

    for h, v in zip(hyps, res.verdicts):
        refs = _refs(h)
        out["n_refs"] += len(refs)
        good = [r for r in refs if r in valid_ids]
        out["n_valid_refs"] += len(good)
        out["n_fabricated_refs"] += len(refs) - len(good)
        for r in refs:
            out["ref_kinds"][_ref_kind(r)] = out["ref_kinds"].get(_ref_kind(r), 0) + 1

        abstaining = h.get("sufficiency") == "INSUFFICIENT_EVIDENCE"
        if abstaining:
            out["n_abstentions"] += 1
            # Task S5: an abstention citing the evidence for the gap is the PREFERRED
            # form, so it is counted separately rather than buried in the abstention total.
            if good:
                out["n_abstentions_with_refs"] += 1
        if _degenerate(h):
            out["n_degenerate"] += 1
        if _is_interaction(h):
            out["n_interactions"] += 1
            if _meaningful_interaction(h, valid_ids, packet):
                out["n_meaningful_interactions"] += 1
        if ADM.packet_admissibility_reasons(h, packet):
            out["n_unsupported_dimension"] += 1

        key = (h.get("subject"), tuple(sorted(h.get("target_metrics") or [])),
               h.get("side"), h.get("window"),
               tuple(sorted((c.get("dimension"), str(c.get("value")))
                            for c in (h.get("conditions") or []))),
               h.get("comparison"))
        if key in seen:
            out["n_duplicate_hypotheses"] += 1
        seen.add(key)

        cmp_ = h.get("comparison")
        out["baselines"][cmp_] = out["baselines"].get(cmp_, 0) + 1
        fam = h.get("research_family")
        out["metric_families"][fam] = out["metric_families"].get(fam, 0) + 1
        for m in (h.get("target_metrics") or []):
            out["target_metrics"][m] = out["target_metrics"].get(m, 0) + 1

        if v.accepted and not abstaining:
            out["grounded_accepted_n"] += 1

    # The compiler runs on TRANSLATED hypotheses -- `query_plan` speaks the internal
    # vocabulary and would reject every ontology term. `accepted_hypotheses` is already
    # translated by validator_v4, which is why it is used here rather than `hyps`.
    for h in res.accepted_hypotheses:
        if h.get("sufficiency") == "INSUFFICIENT_EVIDENCE":
            continue
        out["compilable_n"] += 1
        plans = QP.compile_hypothesis(h, fixture_id=packet["fixture_id"],
                                      cutoff_unix=packet["information_cutoff_unix"])
        if plans and all(getattr(p, "plan", None) is not None for p in plans):
            out["compiled_n"] += 1

    states = ADM.exposure_states(packet)
    for name, term in AVAILABILITY_DIMENSIONS.items():
        exposed = states.get(term) in _EXPOSED
        out[f"{name}_available"] = exposed
        out[name] = 0
        if not exposed:
            continue
        for h, v in zip(hyps, res.verdicts):
            if not v.accepted:
                continue
            good = [r for r in _refs(h) if r in valid_ids]
            conds = h.get("conditions") or []
            if term == O.HISTORICAL_VENUE_CONDITIONING:
                hit = (any(c.get("dimension") == O.HISTORICAL_VENUE_CONDITIONING
                           for c in conds)
                       or h.get("comparison") == "SUBJECT_VENUE_BASELINE"
                       or any(":HOME_ONLY:" in r or ":AWAY_ONLY:" in r for r in good))
            elif term == "recent_window_summaries":
                hit = (h.get("window") in ("W5", "W10")
                       or h.get("comparison") == "SUBJECT_RECENT_VS_LONG_BASELINE"
                       or any(":W5:" in r or ":W10:" in r for r in good))
            elif term == "opponent_profile":
                hit = (any(c.get("dimension") == "opponent_profile" for c in conds)
                       or any(r.startswith("PROFILE:") for r in good))
            else:
                hit = (any(str(c.get("dimension", "")).endswith("formation_family")
                           for c in conds)
                       or any(r.startswith("FORMATION:") for r in good))
            if hit:
                out[name] += 1
    return out


def rates(s: dict) -> dict:
    n = s["n_hypotheses"] or 0
    ga = s["grounded_accepted_n"]
    return {
        "grounded_acceptance_rate": (ga / n) if n else 0.0,
        "valid_evidence_reference_rate": (s["n_valid_refs"] / s["n_refs"]) if s["n_refs"] else 0.0,
        "fabricated_evidence_rate": (s["n_fabricated_refs"] / s["n_refs"]) if s["n_refs"] else 0.0,
        "compilability": (s["compiled_n"] / s["compilable_n"]) if s["compilable_n"] else 0.0,
        "unsupported_dimension_rate": (s["n_unsupported_dimension"] / n) if n else 0.0,
        "firewall_clean_rate": 1.0 - ((s["n_firewall_blocked"] / n) if n else 0.0),
        "meaningful_conditionality": ((n - s["n_degenerate"]) / n) if n else 0.0,
        "meaningful_interaction_rate": (
            s["n_meaningful_interactions"] / s["n_interactions"]) if s["n_interactions"] else 0.0,
        "redundancy_rate": (s["n_duplicate_hypotheses"] / n) if n else 0.0,
        "baseline_diversity": len(s["baselines"]),
        "metric_family_diversity": len(s["metric_families"]),
        "evidence_specificity": (s["n_valid_refs"] / ga) if ga else 0.0,
        "abstention_rate": (s["n_abstentions"] / n) if n else 0.0,
        "grounded_abstention_rate": (
            s["n_abstentions_with_refs"] / s["n_abstentions"]) if s["n_abstentions"] else 0.0,
    }


def self_noise_floor(repeat_groups: list) -> dict:
    """Pooled within-(fixture, arm) SD of the primary metric across repeat calls."""
    sds, detail = [], []
    for g in repeat_groups:
        vals = list(g["values"])
        if len(vals) >= 2:
            sd = statistics.pstdev(vals)
            sds.append(sd)
            detail.append({"fixture_id": g["fixture_id"], "arm": g["arm"],
                           "n": len(vals), "values": vals, "sd": round(sd, 4),
                           "mean": round(statistics.fmean(vals), 4)})
    pooled = math.sqrt(sum(s * s for s in sds) / len(sds)) if sds else 0.0
    return {"pooled_sd": round(pooled, 4),
            "floor_used": round(max(pooled, MIN_SELF_NOISE_FLOOR), 4),
            "min_floor_applied": pooled < MIN_SELF_NOISE_FLOOR,
            "n_groups": len(detail), "groups": detail}


def evaluability(n_paired_fixtures: int, n_valid_base: int, n_valid_research: int,
                 n_repeat_groups_base: int, n_repeat_groups_research: int) -> dict:
    """Is there enough valid data to answer the research question at all? (task S13)

    Entirely independent of WHAT the data says. A run can complete every call and still be
    NON_EVALUABLE, and a run can be EVALUABLE and return a clean negative result.
    """
    failures = []
    if n_paired_fixtures < MIN_PAIRED_FIXTURES:
        failures.append(f"only {n_paired_fixtures} fixtures have a valid response in BOTH "
                        f"arms; the paired comparison needs {MIN_PAIRED_FIXTURES}")
    if n_valid_base < MIN_VALID_RESPONSES_PER_ARM:
        failures.append(f"base arm has {n_valid_base} valid responses; "
                        f"needs {MIN_VALID_RESPONSES_PER_ARM}")
    if n_valid_research < MIN_VALID_RESPONSES_PER_ARM:
        failures.append(f"research arm has {n_valid_research} valid responses; "
                        f"needs {MIN_VALID_RESPONSES_PER_ARM}")
    if n_repeat_groups_base < MIN_REPEATABILITY_GROUPS_PER_ARM:
        failures.append(f"base arm has {n_repeat_groups_base} repeatability groups; the "
                        f"self-noise floor needs {MIN_REPEATABILITY_GROUPS_PER_ARM}")
    if n_repeat_groups_research < MIN_REPEATABILITY_GROUPS_PER_ARM:
        failures.append(f"research arm has {n_repeat_groups_research} repeatability "
                        f"groups; needs {MIN_REPEATABILITY_GROUPS_PER_ARM}")
    return {"scientific_status": "EVALUABLE" if not failures else "NON_EVALUABLE",
            "reasons": failures,
            "minimums": {"paired_fixtures": MIN_PAIRED_FIXTURES,
                         "valid_responses_per_arm": MIN_VALID_RESPONSES_PER_ARM,
                         "repeatability_groups_per_arm": MIN_REPEATABILITY_GROUPS_PER_ARM},
            "observed": {"paired_fixtures": n_paired_fixtures,
                         "valid_base": n_valid_base, "valid_research": n_valid_research,
                         "repeat_groups_base": n_repeat_groups_base,
                         "repeat_groups_research": n_repeat_groups_research}}


def classify_stop(n_calls: int, n_model_schema_invalid: int,
                  n_infrastructure_failures: int, n_consecutive_transport_failures: int,
                  spend_usd: float, ceiling_usd: float) -> list:
    """Every stop rule, evaluated together. Returns a list of fired rules (possibly empty).

    Separating the two schema-failure classes is the whole point: V5A.1's single rule fired
    on 2 INFRASTRUCTURE failures out of 6 calls and reported the run as a MODEL discipline
    problem.
    """
    fired = []
    if n_infrastructure_failures >= INFRASTRUCTURE_CONTRACT_FAILURE_STOP_N:
        fired.append({"rule": "V5A2_STOP_INFRASTRUCTURE_CONTRACT_FAILURE",
                      "detail": f"{n_infrastructure_failures} apparatus contract "
                                f"failure(s); expected 0 after V5A.2 closure",
                      "class": "APPARATUS"})
    if n_calls >= MIN_CALLS_BEFORE_RATE_STOP:
        rate = n_model_schema_invalid / n_calls
        if rate > MODEL_SCHEMA_INVALID_RATE_STOP:
            fired.append({"rule": "V5A2_STOP_MODEL_SCHEMA_INVALID_RATE",
                          "detail": f"{n_model_schema_invalid}/{n_calls} = {rate:.3f} > "
                                    f"{MODEL_SCHEMA_INVALID_RATE_STOP}",
                          "class": "MODEL"})
    if n_consecutive_transport_failures >= CONSECUTIVE_TRANSPORT_FAILURE_STOP_N:
        fired.append({"rule": "V5A2_STOP_TRANSPORT",
                      "detail": f"{n_consecutive_transport_failures} consecutive transport "
                                f"failures", "class": "APPARATUS"})
    if spend_usd > ceiling_usd:
        fired.append({"rule": "V5A2_STOP_COST_CEILING",
                      "detail": f"${spend_usd:.4f} > ${ceiling_usd:.4f}",
                      "class": "APPARATUS"})
    return fired


def verdict(paired: list, floor: float, disc: dict) -> dict:
    """The FROZEN scientific gate. Identical in substance to V5A.1's.

    Only issued when `evaluability` returns EVALUABLE; `final_verdict` enforces that.
    """
    diffs = [p["diff"] for p in paired]
    mean_diff = statistics.fmean(diffs) if diffs else 0.0
    n_pos = sum(1 for d in diffs if d > 0)
    n_neg = sum(1 for d in diffs if d < 0)

    degraded = []
    if disc["compilability_delta"] < -DISCIPLINE_TOLERANCE:
        degraded.append("compilability")
    if disc["firewall_clean_delta"] < -DISCIPLINE_TOLERANCE:
        degraded.append("firewall_clean_rate")
    if disc["fabricated_evidence_delta"] > DISCIPLINE_TOLERANCE:
        degraded.append("fabricated_evidence_rate")
    if disc["unsupported_dimension_delta"] > DISCIPLINE_TOLERANCE:
        degraded.append("unsupported_dimension_rate")

    if degraded:
        v = "FAIL"
        why = (f"the research arm materially degraded discipline on {degraded} "
               f"(tolerance {DISCIPLINE_TOLERANCE})")
    elif mean_diff > floor:
        v = "PASS"
        why = (f"mean paired {PRIMARY_METRIC} difference {mean_diff:.4f} exceeds the "
               f"self-noise floor {floor:.4f}, with no material discipline degradation")
    elif mean_diff <= 0:
        v = "FAIL"
        why = (f"mean paired {PRIMARY_METRIC} difference {mean_diff:.4f} shows no "
               f"improvement")
    else:
        v = "MIXED"
        why = (f"mean paired {PRIMARY_METRIC} difference {mean_diff:.4f} is positive but "
               f"within the self-noise floor {floor:.4f}")
    return {"verdict": v, "reason": why, "mean_paired_diff": round(mean_diff, 4),
            "self_noise_floor": floor, "n_fixtures_research_higher": n_pos,
            "n_fixtures_base_higher": n_neg,
            "n_fixtures_tied": len(diffs) - n_pos - n_neg,
            "discipline_degraded": degraded,
            "discipline_tolerance": DISCIPLINE_TOLERANCE}


def final_verdict(execution_status: str, evaluability_result: dict,
                  paired: list, floor: float, disc: dict) -> dict:
    """The two statuses, reported together and never collapsed (task S13).

    A scientific verdict is issued ONLY when the run is EVALUABLE. Otherwise the scientific
    status is NON_EVALUABLE and no PASS/MIXED/FAIL is produced at all -- because with too
    little valid data, "FAIL" would be a claim the data cannot support.
    """
    out = {"execution_status": execution_status,
           "scientific_status": evaluability_result["scientific_status"],
           "evaluability": evaluability_result}
    if evaluability_result["scientific_status"] != "EVALUABLE":
        out["scientific_verdict"] = None
        out["reason"] = ("no scientific verdict is issued: "
                         + "; ".join(evaluability_result["reasons"]))
        return out
    sv = verdict(paired, floor, disc)
    out["scientific_verdict"] = sv["verdict"]
    out["reason"] = sv["reason"]
    out["detail"] = sv
    return out


def version_stamp() -> dict:
    return {"evaluator_version": EVALUATOR_VERSION,
            "primary_metric": PRIMARY_METRIC,
            "discipline_tolerance": DISCIPLINE_TOLERANCE,
            "min_self_noise_floor": MIN_SELF_NOISE_FLOOR,
            "min_paired_fixtures": MIN_PAIRED_FIXTURES,
            "min_valid_responses_per_arm": MIN_VALID_RESPONSES_PER_ARM,
            "min_repeatability_groups_per_arm": MIN_REPEATABILITY_GROUPS_PER_ARM,
            "model_schema_invalid_rate_stop": MODEL_SCHEMA_INVALID_RATE_STOP,
            "min_calls_before_rate_stop": MIN_CALLS_BEFORE_RATE_STOP,
            "infrastructure_contract_failure_stop_n": INFRASTRUCTURE_CONTRACT_FAILURE_STOP_N,
            "consecutive_transport_failure_stop_n": CONSECUTIVE_TRANSPORT_FAILURE_STOP_N,
            "thresholds_inherited_from": "v5a1_evaluator_v1 (unchanged)"}
