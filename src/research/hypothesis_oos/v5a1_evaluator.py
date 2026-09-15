"""V5A.1 frozen evaluator (`v5a1_evaluator_v1`). ZERO SPEND -- reads responses, calls nothing.

FROZEN BEFORE THE FIRST PAID CALL. The V5A.1 preregistration named the rubric criteria and
the PASS/MIXED/FAIL gate wording but shipped no evaluator implementation and no numeric
threshold. Writing one after seeing responses would be exactly the tuning the mandate
forbids, so it is written and hashed here, before any response exists.

Nothing in this module may be changed once execution begins: not the normalization, the
evidence-reference rules, the meaningful-interaction classifier, the groundedness
definition, the availability denominators, the thresholds, the gates, or the repeatability
calculation.
"""
from __future__ import annotations

import json
import math
import statistics
from typing import Optional

from src.research.hypothesis_engine import lifecycle, query_plan as QP, validator_v3 as V3
from src.research.hypothesis_oos import v5a1_admissibility as ADM
from src.research.hypothesis_oos import v5a1_evidence as E

EVALUATOR_VERSION = "v5a1_evaluator_v1"

# ----------------------------------------------------------------------------------------
# FROZEN THRESHOLDS. Chosen before any response was seen; justified, not tuned.
# ----------------------------------------------------------------------------------------
#: A degradation of more than this in compilability / firewall-clean / fabricated-evidence
#: is "materially worse discipline". 5pp on ~12 hypotheses per call is under one hypothesis,
#: i.e. the smallest difference that is not a single-hypothesis accident.
DISCIPLINE_TOLERANCE = 0.05

#: The primary effect must exceed the measured self-noise floor. The floor is the pooled
#: within-(fixture,arm) standard deviation of the primary metric across repeat calls. If
#: repeatability yields no usable spread, MIN_SELF_NOISE_FLOOR is used instead so that a
#: zero floor can never manufacture a PASS.
MIN_SELF_NOISE_FLOOR = 0.5

#: Verdict requires the paired mean to beat the floor on the primary metric.
PRIMARY_METRIC = "grounded_accepted_n"

#: Availability-aware dimensions: scored only where the arm's packet EXPOSES them.
AVAILABILITY_DIMENSIONS = {
    "venue_use": "venue_splits",
    "recent_vs_long_use": "recent_vs_long",
    "opponent_profile_use": "opponent_profile_response",
    "formation_use": "formation_recorded_history",
}


# ----------------------------------------------------------------------------------------
# Per-response scoring
# ----------------------------------------------------------------------------------------
def _refs(h):
    return list(h.get("evidence_refs") or [])


def _ref_kind(ref: str) -> str:
    return ref.split(":")[0] if ":" in ref else "OTHER"


def _is_interaction(h) -> bool:
    return len(h.get("conditions") or []) >= 2


def _meaningful_interaction(h, valid_ids, packet) -> bool:
    """Frozen classifier. An interaction is meaningful when BOTH conditions are on
    distinct, packet-supported dimensions, the hypothesis is grounded in at least two
    distinct evidence items, and no condition is a degenerate ANY."""
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


def _degenerate(h) -> bool:
    conds = h.get("conditions") or []
    return any(str(c.get("value")) == "ANY" for c in conds)


def score_response(raw, packet) -> dict:
    """Score ONE model response against ONE packet. Pure function of the two."""
    out = {
        "parsed": raw is not None,
        "n_hypotheses": 0, "n_schema_ok": 0,
        "grounded_accepted_n": 0, "compiled_n": 0, "compilable_n": 0,
        "n_refs": 0, "n_valid_refs": 0, "n_fabricated_refs": 0,
        "n_abstentions": 0, "n_degenerate": 0,
        "n_interactions": 0, "n_meaningful_interactions": 0,
        "n_unsupported_dimension": 0, "n_firewall_blocked": 0,
        "ref_kinds": {}, "baselines": {}, "metric_families": {},
        "target_metrics": {}, "n_duplicate_hypotheses": 0,
        "whole_response_failure": None,
    }
    if raw is None:
        out["whole_response_failure"] = "NO_TOOL_USE"
        return out

    valid_ids = E.resolve_evidence_ids(packet)
    res = V3.validate(raw, packet=packet,
                      expected_packet_hash=packet["packet_hash"],
                      expected_fixture_id=packet["fixture_id"])
    if not res.accepted:
        out["whole_response_failure"] = res.failure
        out["n_hypotheses"] = len(raw.get("hypotheses") or [])
        if res.failure in (lifecycle.NUMERICAL_AUTHORITY_VIOLATION,
                           lifecycle.LATENT_GRADING_VIOLATION):
            out["n_firewall_blocked"] = out["n_hypotheses"]
        return out

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

        if h.get("sufficiency") == "INSUFFICIENT_EVIDENCE":
            out["n_abstentions"] += 1
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

        if v.accepted and h.get("sufficiency") != "INSUFFICIENT_EVIDENCE":
            out["grounded_accepted_n"] += 1
            plans = QP.compile_hypothesis(h, fixture_id=packet["fixture_id"],
                                          cutoff_unix=packet["information_cutoff_unix"])
            out["compilable_n"] += 1
            if plans and all(getattr(p, "plan", None) is not None for p in plans):
                out["compiled_n"] += 1

    # availability-aware dimension use (task §30): counted ONLY where exposed
    states = ADM.exposure_states(packet)
    for name, dim in AVAILABILITY_DIMENSIONS.items():
        exposed = states.get(dim) in (E.EXPOSED, E.EXPOSED_LOW_COVERAGE)
        out[f"{name}_available"] = exposed
        out[name] = 0
        if not exposed:
            continue
        for h, v in zip(hyps, res.verdicts):
            if not v.accepted:
                continue
            good = [r for r in _refs(h) if r in valid_ids]
            if dim == "venue_splits":
                hit = (any(c.get("dimension") == "venue" for c in h.get("conditions") or [])
                       or h.get("comparison") == "SUBJECT_VENUE_BASELINE"
                       or any(":HOME_ONLY:" in r or ":AWAY_ONLY:" in r for r in good))
            elif dim == "recent_vs_long":
                hit = (h.get("window") in ("W5", "W10")
                       or h.get("comparison") == "SUBJECT_RECENT_VS_LONG_BASELINE"
                       or any(":W5:" in r or ":W10:" in r for r in good))
            elif dim == "opponent_profile_response":
                hit = (any(c.get("dimension") == "opponent_profile"
                           for c in h.get("conditions") or [])
                       or any(r.startswith("PROFILE:") for r in good))
            else:
                hit = (any(c.get("dimension", "").endswith("formation_family")
                           for c in h.get("conditions") or [])
                       or any(r.startswith("FORMATION:") for r in good))
            if hit:
                out[name] += 1
    return out


# ----------------------------------------------------------------------------------------
# Derived rates
# ----------------------------------------------------------------------------------------
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
        "meaningful_conditionality": (
            (n - s["n_degenerate"]) / n) if n else 0.0,
        "meaningful_interaction_rate": (
            s["n_meaningful_interactions"] / s["n_interactions"]) if s["n_interactions"] else 0.0,
        "redundancy_rate": (s["n_duplicate_hypotheses"] / n) if n else 0.0,
        "baseline_diversity": len(s["baselines"]),
        "metric_family_diversity": len(s["metric_families"]),
        "evidence_specificity": (s["n_valid_refs"] / ga) if ga else 0.0,
        "abstention_rate": (s["n_abstentions"] / n) if n else 0.0,
    }


# ----------------------------------------------------------------------------------------
# Self-noise and the frozen verdict
# ----------------------------------------------------------------------------------------
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
            "groups": detail}


def verdict(paired: list, floor: float, disc: dict) -> dict:
    """The FROZEN gate. Inputs: paired per-fixture differences on the primary metric, the
    self-noise floor, and the discipline deltas (research minus base)."""
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


def version_stamp() -> dict:
    return {"evaluator_version": EVALUATOR_VERSION,
            "primary_metric": PRIMARY_METRIC,
            "discipline_tolerance": DISCIPLINE_TOLERANCE,
            "min_self_noise_floor": MIN_SELF_NOISE_FLOOR}
