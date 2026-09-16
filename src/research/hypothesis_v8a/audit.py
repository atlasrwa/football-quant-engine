"""V8A deterministic structural audit (`v8a_audit_v1`). Brief sections 16, 17 and 22.

Every label in the V8A report is produced here, by code, from the candidate's STRUCTURE. The
model's own novelty prose is carried through as audit evidence and is never read by the
judge.

WHY THE FIREWALL IS RE-POINTED RATHER THAN REUSED AS-IS
-------------------------------------------------------
`firewall_v5.scan_hypothesis` iterates `v6_numeric_contract.PROSE_FIELDS`, which is exactly
`("question", "evidence_summary")` -- V6.1's field set. The V8A schema has none of those
fields. Calling it unchanged would scan nothing, return no findings, and present as a
flawless firewall record for an arm that was never actually checked. So V8A names its own
prose surfaces and drives `scan_prose_field` over each one explicitly. The tests in
`research/hypothesis_engine/_v8a_pipeline_tests.py` plant a probability in EVERY one of them
and assert each is caught.

ZERO SPEND. No effect is computed anywhere in this module.
"""
from __future__ import annotations

import hashlib
import json
import re

from src.research.hypothesis_engine import firewall_v5 as FW
from src.research.hypothesis_v71 import ir as IRM

from . import genericlib as G

AUDIT_VERSION = "v8a_audit_v1"

#: Every free-text surface the V8A schema exposes. A field added to the schema and not added
#: here would be unscanned, so the pipeline test asserts this list covers the schema.
PROSE_FIELDS = (
    "football_mechanism",
    "falsifiable_question",
    "falsifier",
    "similar_opponent_rationale",
    "formation_context",
)
#: Observations may reproduce a value the packet supplied; nothing else may.
EVIDENCE_BEARING_FIELDS = ("observation",)

_NUM_RX = re.compile(r"-?\d+(?:\.\d+)?")


# ---------------------------------------------------------------------------------------
# candidate -> the frozen V7.1 structural spec
# ---------------------------------------------------------------------------------------
def to_spec(cand: dict, *, home_is_team_a: bool = True) -> dict:
    """Translate a V8A candidate into the structural spec the frozen V7.1 IR compiles.

    TEAM_A / TEAM_B are the packet's matchup roles; the IR speaks HOME_TEAM / AWAY_TEAM.
    """
    subj = str(cand.get("subject") or "").upper()
    role = {"TEAM_A": "HOME_TEAM", "TEAM_B": "AWAY_TEAM"}.get(subj, subj)
    if not home_is_team_a:
        role = {"HOME_TEAM": "AWAY_TEAM", "AWAY_TEAM": "HOME_TEAM"}.get(role, role)
    caps = list(cand.get("provider_requirements") or [])
    conds = cand.get("conditions") or []
    if any(str(c.get("dimension")) == "opponent_profile" for c in conds):
        if "opponent_profile" not in caps:
            caps.append("opponent_profile")
    if str(cand.get("comparison")).upper() == "SIMILAR_OPPONENT_COHORT":
        if "opponent_profile" not in caps:
            caps.append("opponent_profile")
    return {
        "target_metrics": list(cand.get("target_metric") or []),
        "subject": role,
        "side": str(cand.get("metric_perspective") or "").upper(),
        "window": str(cand.get("window") or "ALL_PRIOR").upper(),
        "comparison": str(cand.get("comparison") or "").upper(),
        "conditions": conds,
        "research_family": cand.get("research_family"),
        "required_capabilities": caps,
    }


# ---------------------------------------------------------------------------------------
# validity / measurability
# ---------------------------------------------------------------------------------------
def compile_candidate(cand: dict) -> dict:
    spec = to_spec(cand)
    ir = IRM.build_ir(spec)
    return {"spec": spec, "ir_status": ir.status, "ir_ok": ir.status == IRM.OK,
            "describes": ir.describe() if ir.status == IRM.OK else None}


def measurability(cand: dict, cap) -> dict:
    """Can this corpus answer the question, at this fixture's competition?"""
    metrics = [str(m).strip().lower() for m in (cand.get("target_metric") or [])]
    unknown, unsupported, restricted = [], [], []
    for m in metrics:
        status, _detail = cap.classify_metric(m)
        if status == "UNKNOWN":
            unknown.append(m)
        elif status == "UNSUPPORTED":
            unsupported.append(m)
        elif status in ("RESTRICTED", "INSUFFICIENT_COVERAGE"):
            restricted.append(m)
    adm = None
    if metrics and not unknown and not unsupported:
        sets = [cap.admissible_competitions(m) for m in metrics]
        adm = sorted(set.intersection(*[set(s) for s in sets])) if sets else []
    return {
        "unknown_metrics": unknown,
        "unsupported_metrics": unsupported,
        "restricted_metrics": restricted,
        "admissible_competitions": adm,
        "measurable": bool(metrics) and not unknown and not unsupported and bool(adm),
        "unknown_is_not_zero": True,
    }


def tautology_checks(cand: dict) -> dict:
    """cohort == baseline, and condition == target, decided structurally."""
    spec = to_spec(cand)
    comparator = spec["comparison"]
    sig, kinds = G.condition_signature(spec["conditions"])
    metrics = {str(m).lower() for m in spec["target_metrics"]}

    # A venue-baseline comparator whose ONLY condition is that same venue compares a set
    # with itself.
    cohort_equals_baseline = False
    if comparator == "SUBJECT_VENUE_BASELINE" and kinds == ["VENUE"] and len(sig) == 1:
        cohort_equals_baseline = True
    if comparator == "SUBJECT_COMPETITION_BASELINE" and kinds == ["COMPETITION"]:
        # normalised form: the required filter IS the contrast, so this is not degenerate
        cohort_equals_baseline = False
    if comparator == "SUBJECT_CONDITIONAL_VS_BASELINE" and not sig:
        cohort_equals_baseline = True

    condition_equals_target = False
    for dim, axis, _val in sig:
        if dim == "opponent_profile" and axis:
            base = str(axis).lower().replace("_for", "").replace("_against", "")
            if base in {m.replace("_for", "").replace("_against", "") for m in metrics}:
                condition_equals_target = True
    return {"cohort_equals_baseline": cohort_equals_baseline,
            "condition_equals_target": condition_equals_target,
            "degenerate_conditions": G.is_degenerate(spec["conditions"]),
            "tautology": cohort_equals_baseline or G.is_degenerate(spec["conditions"])}


# ---------------------------------------------------------------------------------------
# firewall over the V8A prose surfaces
# ---------------------------------------------------------------------------------------
def packet_values(packet: dict) -> tuple:
    """Every numeric literal the packet actually supplied. Quoting one of these inside an
    observation is legitimate reproduction; authoring any other number is not."""
    vals = set()

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            vals.add(float(o))
    walk(packet)
    return tuple(sorted(vals))


def firewall_scan(cand: dict, index: int, *, values, sample_ns=()) -> list:
    """Drive firewall_v5 over EVERY V8A prose surface, naming each explicitly."""
    findings = []
    for field in PROSE_FIELDS:
        text = cand.get(field)
        if isinstance(text, str) and text:
            findings.extend(FW.scan_prose_field(
                text, f"$.candidates[{index}].{field}", field,
                values=values, sample_ns=sample_ns, evidence_bearing=False))
    for j, obs in enumerate(cand.get("behavioral_observations") or []):
        text = (obs or {}).get("observation")
        if isinstance(text, str) and text:
            findings.extend(FW.scan_prose_field(
                text,
                f"$.candidates[{index}].behavioral_observations[{j}].observation",
                "observation", values=values, sample_ns=sample_ns,
                evidence_bearing=True))
    crit = (cand.get("self_critique") or {}).get("notes")
    if isinstance(crit, str) and crit:
        findings.extend(FW.scan_prose_field(
            crit, f"$.candidates[{index}].self_critique.notes", "notes",
            values=values, sample_ns=sample_ns, evidence_bearing=False))
    return findings


def pass2_firewall_scan(resp: dict, index: int, *, values, sample_ns=()) -> list:
    """The second-pass surfaces. A predictive claim here is the specific thing brief
    section 15 forbids ("more predictive", "higher edge", "better effect")."""
    findings = []
    for field in ("reason",):
        text = resp.get(field)
        if isinstance(text, str) and text:
            findings.extend(FW.scan_prose_field(
                text, f"$.pass2[{index}].{field}", field,
                values=values, sample_ns=sample_ns, evidence_bearing=False))
    for key in ("shared_structure", "incremental_structure"):
        for j, item in enumerate(resp.get(key) or []):
            if isinstance(item, str) and item:
                findings.extend(FW.scan_prose_field(
                    item, f"$.pass2[{index}].{key}[{j}]", key,
                    values=values, sample_ns=sample_ns, evidence_bearing=False))
    return findings


#: Claims the second pass may never make (brief section 15). Structural novelty is not a
#: predictive claim, and a model asserting one has stepped outside its role.
PREDICTIVE_CLAIM_PHRASES = ("more predictive", "higher edge", "better effect",
                            "more likely to work", "stronger signal", "outperform",
                            "will generalise", "will generalize", "greater alpha")


def predictive_claims(resp: dict) -> list:
    blob = json.dumps(resp, default=str).lower()
    return sorted({p for p in PREDICTIVE_CLAIM_PHRASES if p in blob})


# ---------------------------------------------------------------------------------------
# evidence grounding
# ---------------------------------------------------------------------------------------
def evidence_ref_index(packet: dict) -> set:
    """Every reference string a candidate may legitimately cite."""
    refs = set()
    for side, nav in (packet.get("descriptive_navigation") or {}).items():
        for block, blk in (nav.get("blocks") or {}).items():
            refs.add(f"{side}.{block}")
            for metric in (blk.get("metrics") or {}):
                refs.add(f"{side}.{block}.{metric}")
    for side, raw in (packet.get("raw_historical_rows") or {}).items():
        refs.add(f"{side}.raw")
        for row in raw.get("rows") or []:
            refs.add(f"{side}.raw.{row['row_id']}")
    for m in (packet.get("capability_envelope") or {}).get("metrics") or {}:
        refs.add(f"capability_envelope.{m}")
    return refs


def check_evidence_refs(cand: dict, valid: set) -> dict:
    cited, bad = [], []
    for obs in cand.get("behavioral_observations") or []:
        for r in (obs or {}).get("evidence_refs") or []:
            cited.append(r)
            if r not in valid:
                bad.append(r)
    return {"n_cited": len(cited), "n_hallucinated": len(bad),
            "hallucinated_refs": sorted(set(bad))[:20],
            "all_refs_valid": not bad}


# ---------------------------------------------------------------------------------------
# research character + complexity (brief sections 17 and 22)
# ---------------------------------------------------------------------------------------
def classify_character(cand: dict) -> dict:
    """Deterministic classification of what KIND of football question this is."""
    spec = to_spec(cand)
    sig, kinds = G.condition_signature(spec["conditions"])
    comparator = spec["comparison"]
    side = spec["side"]
    subj, opp = cand.get("subject"), cand.get("opponent")

    has_profile = "OPPONENT_PROFILE" in kinds
    has_venue = "VENUE" in kinds
    similar = comparator == "SIMILAR_OPPONENT_COHORT"

    # An attack x defense interaction means the MEASURED perspective is set against an
    # opponent characterised on the OPPOSITE perspective -- not merely that two teams exist.
    attack_defense = False
    for dim, axis, _v in sig:
        if dim == "opponent_profile" and axis:
            axis_l = str(axis).lower()
            if side == "FOR" and axis_l.endswith("_against"):
                attack_defense = True
            if side == "AGAINST" and axis_l.endswith("_for"):
                attack_defense = True
    if similar:
        attack_defense = attack_defense or side == "FOR"

    return {
        "attack_defense_interaction": bool(attack_defense),
        "similar_opponent": bool(similar),
        "recent_vs_long_run": comparator == "SUBJECT_RECENT_VS_LONG_BASELINE"
                              or spec["window"] in ("W5", "W10"),
        "venue_interaction": bool(has_venue),
        "formation_context_used": bool((cand.get("formation_context") or "").strip()),
        "half_state_conditional": False,   # structurally impossible in this corpus
        "opponent_profile_conditioned": bool(has_profile),
        "multi_kind_interaction": len([k for k in kinds if k != "NONE"]) > 1,
        "subject_opponent_distinct": bool(subj and opp and subj != opp),
        "research_family": cand.get("research_family"),
    }


def complexity(cand: dict) -> dict:
    """Brief section 17: complexity is recorded and flagged, never rewarded."""
    spec = to_spec(cand)
    sig, kinds = G.condition_signature(spec["conditions"])
    n_cond = len(sig)
    n_targets = len(spec["target_metrics"])
    # Each extra restriction multiplies the stratification burden on a finite history.
    burden = (2 ** n_cond) * max(1, n_targets)
    return {"n_cohort_conditions": n_cond,
            "n_condition_kinds": len([k for k in kinds if k != "NONE"]),
            "n_target_metrics": n_targets,
            "implied_stratification_burden": burden,
            "excessive_complexity": n_cond > 2 or n_targets > 3,
            "fragmentation_risk": burden > 8}


def audit_candidate(cand, index, *, cap, packet, library_keys, vocabulary, valid_refs,
                    values):
    """The complete deterministic record for one candidate."""
    comp = compile_candidate(cand)
    meas = measurability(cand, cap)
    taut = tautology_checks(cand)
    fw = firewall_scan(cand, index, values=values)
    blocking = FW.blocking(fw)
    refs = check_evidence_refs(cand, valid_refs)

    ir_ok = comp["ir_ok"] and meas["measurable"] and not taut["tautology"]
    ir_status = comp["ir_status"]
    if comp["ir_ok"] and not meas["measurable"]:
        ir_status = "UNSUPPORTED_OR_UNKNOWN_METRIC"
    if comp["ir_ok"] and taut["tautology"]:
        ir_status = "TAUTOLOGY_OR_DEGENERATE_COHORT"

    verdict = G.judge(to_spec(cand), library_keys, vocabulary,
                      ir_ok=ir_ok, ir_status=ir_status)

    return {
        "candidate_id": cand.get("candidate_id"),
        "compiler": comp,
        "measurability": meas,
        "tautology": taut,
        "firewall": {"n_findings": len(fw), "n_blocking": len(blocking),
                     "blocking_paths": [f.path for f in blocking][:10],
                     "clean": not blocking},
        "evidence_refs": refs,
        "character": classify_character(cand),
        "complexity": complexity(cand),
        "novelty_verdict": verdict,
        "schema_valid": True,
    }


def record_hash(rec) -> str:
    return hashlib.sha256(
        json.dumps(rec, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def version_stamp() -> dict:
    return {"audit_version": AUDIT_VERSION,
            "firewall": FW.FIREWALL_VERSION,
            "prose_fields_scanned": list(PROSE_FIELDS) + ["behavioral_observations[].observation",
                                                          "self_critique.notes"],
            "llm_sets_the_label": False,
            "computes_effects": False}
