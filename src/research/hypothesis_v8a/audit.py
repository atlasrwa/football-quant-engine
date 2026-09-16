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
# Metric-name collision guard
# ---------------------------------------------------------------------------------------
#: `firewall_v5`'s predictive-marker set contains the word "chance", because in V6.1's terse
#: `question` field a sentence carrying "chance" plus a number was a claim about the upcoming
#: fixture. In THIS corpus `big_chances` is a METRIC NAME, and the V8A protocol asks for
#: flowing behavioural prose, so the model naturally writes "big chances" -- and every such
#: sentence was classified MODEL_AUTHORED_PREDICTIVE_QUANTIFICATION. Inspection of all 63
#: affected sentences found ZERO genuine predictive claims; every one reproduced an exact
#: packet value for the `big_chances` metric.
#:
#: `firewall_v2.mask_metric_lexicon` already masks approved metric names -- it simply does
#: not know the SPACE-SEPARATED prose spelling of them. This normalises the prose spelling to
#: the underscore form BEFORE scanning, so the existing masker handles it. It is an extension
#: of the lexicon to a second spelling of the same approved names, NOT a relaxation: the
#: masker's own rule still stands, and a masked term carrying a numeric literal is still
#: examined. Nothing outside the frozen metric vocabulary is touched.
def normalise_metric_prose(text: str, vocabulary) -> str:
    """Rewrite `big chances` -> `big_chances` for approved metric names only."""
    out = text or ""
    names = sorted({str(m) for m in vocabulary}, key=len, reverse=True)
    for name in names:
        if "_" not in name:
            continue
        spaced = name.replace("_", " ")
        out = re.sub(rf"\b{re.escape(spaced)}\b", name, out, flags=re.IGNORECASE)
        # singular form of a plural metric name, e.g. "big chance"
        if spaced.endswith("s"):
            out = re.sub(rf"\b{re.escape(spaced[:-1])}\b", name, out,
                         flags=re.IGNORECASE)
    return out


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
    # Canonicalise through the frozen V7 synonym map first: Arm A speaks V6.1's packet
    # vocabulary and Arm B speaks the capability contract's, and they must be scored on the
    # same metric identity or the comparison measures naming rather than research.
    metrics = [IRM.normalise_metric(m) for m in (cand.get("target_metric") or [])]
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
    metrics = {IRM.normalise_metric(m) for m in spec["target_metrics"]}

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


def firewall_scan(cand: dict, index: int, *, values, sample_ns=(), vocabulary=()) -> list:
    """Drive firewall_v5 over EVERY V8A prose surface, naming each explicitly."""
    def norm(t):
        return normalise_metric_prose(t, vocabulary) if vocabulary else t

    findings = []
    for field in PROSE_FIELDS:
        text = cand.get(field)
        if isinstance(text, str) and text:
            findings.extend(FW.scan_prose_field(
                norm(text), f"$.candidates[{index}].{field}", field,
                values=values, sample_ns=sample_ns, evidence_bearing=False))
    for j, obs in enumerate(cand.get("behavioral_observations") or []):
        text = (obs or {}).get("observation")
        if isinstance(text, str) and text:
            findings.extend(FW.scan_prose_field(
                norm(text),
                f"$.candidates[{index}].behavioral_observations[{j}].observation",
                "observation", values=values, sample_ns=sample_ns,
                evidence_bearing=True))
    crit = (cand.get("self_critique") or {}).get("notes")
    if isinstance(crit, str) and crit:
        findings.extend(FW.scan_prose_field(
            norm(crit), f"$.candidates[{index}].self_critique.notes", "notes",
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
    """Every reference string a candidate may legitimately cite.

    Built by WALKING the packet and emitting the real dotted path of every node, rather
    than by hand-writing a shorthand. The first version of this function invented an
    abbreviated form (`TEAM_A.long_run_home.shots_for`) while the model -- correctly --
    cited the genuine path (`TEAM_A.blocks.long_run_home.metrics.shots_for`). Every
    reference then scored as hallucinated, which would have reported a perfectly grounded
    arm as 100% ungrounded on the single most important grounding metric.

    Common equivalent spellings of the same real node are accepted, because a citation is
    grounded if it POINTS AT SOMETHING THE PACKET CONTAINS -- the test is existence, not
    a preferred notation.
    """
    refs: set = set()

    def walk(node, path):
        if path:
            refs.add(path)
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for item in node:
                rid = item.get("row_id") if isinstance(item, dict) else None
                if rid:
                    walk(item, f"{path}.{rid}")

    for root in ("descriptive_navigation", "raw_historical_rows", "capability_envelope"):
        walk(packet.get(root) or {}, root)
        # the same subtree without its root prefix: the model is shown the packet as one
        # object and may address a side directly as `TEAM_A....`
        walk(packet.get(root) or {}, "")

    # `TEAM_A.raw.ROW:03` -- the natural short form for a raw row.
    for side, raw in (packet.get("raw_historical_rows") or {}).items():
        refs.add(f"{side}.raw")
        for row in raw.get("rows") or []:
            refs.add(f"{side}.raw.{row.get('row_id')}")

    # Bounded aliases: the SAME real node with a purely structural container level elided
    # (`TEAM_A.blocks.long_run_home.big_chances_against` for
    #  `TEAM_A.blocks.long_run_home.metrics.big_chances_against`). A citation is grounded
    # when it resolves unambiguously to something the packet contains; dropping a container
    # key is a notational elision, not an invented reference. This is deliberately an ALIAS
    # SET DERIVED FROM REAL PATHS, never a pattern match: a metric that does not exist in
    # that block, or a row id the packet lacks, still has no alias and still fails.
    for path in list(refs):
        for container in (".blocks.", ".metrics."):
            if container in path:
                refs.add(path.replace(container, ".", 1))
        if ".blocks." in path and ".metrics." in path:
            refs.add(path.replace(".blocks.", ".", 1).replace(".metrics.", ".", 1))
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
    fw = firewall_scan(cand, index, values=values, vocabulary=vocabulary)
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


# ---------------------------------------------------------------------------------------
# Arm A adapter -- schema_v4 responses speak a DIFFERENT field vocabulary
# ---------------------------------------------------------------------------------------
#: V6.1's `schema_v4` names its fields `target_metrics` / `side` / HOME_TEAM|AWAY_TEAM, while
#: the V8A schema uses `target_metric` / `metric_perspective` / TEAM_A|TEAM_B. Feeding a
#: schema_v4 hypothesis to `to_spec` would silently yield an empty metric list and an
#: unmapped subject, so EVERY Arm A candidate would land INVALID and Arm B would appear to
#: win on measurability through a field-name mismatch alone. This adapter exists so the
#: A-vs-B contrast measures protocol rather than nomenclature.
def armA_to_spec(h: dict) -> dict:
    """schema_v4 hypothesis -> the same structural spec the V7.1 IR compiles.

    Near-identity: `target_metrics`, `subject`, `side`, `window`, `conditions` and
    `comparison` already carry the IR's own names -- which is exactly what
    `controls.derive_marginals` reads off V6.1 hypotheses.
    """
    return {
        "target_metrics": list(h.get("target_metrics") or []),
        "subject": str(h.get("subject") or "").upper(),
        "side": str(h.get("side") or "").upper(),
        "window": str(h.get("window") or "ALL_PRIOR").upper(),
        "comparison": str(h.get("comparison") or "").upper(),
        "conditions": h.get("conditions") or [],
        "research_family": h.get("research_family"),
        "required_capabilities": list(h.get("required_capabilities") or []),
    }


def armA_as_v8a_candidate(h: dict) -> dict:
    """A thin V8A-shaped VIEW of an Arm A hypothesis, for the shared structural scorers.

    Only the structural fields are mapped. The V8A-only reasoning surfaces stay ABSENT
    rather than being invented, so Arm A is never credited with observations, a mechanism,
    a falsifier or a self-critique that its protocol never asked it for.
    """
    subj = str(h.get("subject") or "").upper()
    return {
        "candidate_id": h.get("hypothesis_id"),
        "research_family": h.get("research_family"),
        "subject": {"HOME_TEAM": "TEAM_A", "AWAY_TEAM": "TEAM_B"}.get(subj, subj),
        "opponent": {"HOME_TEAM": "TEAM_B", "AWAY_TEAM": "TEAM_A"}.get(subj),
        "target_metric": list(h.get("target_metrics") or []),
        "metric_perspective": str(h.get("side") or "").upper(),
        "comparison": str(h.get("comparison") or "").upper(),
        "window": str(h.get("window") or "ALL_PRIOR").upper(),
        "conditions": h.get("conditions") or [],
        "provider_requirements": list(h.get("required_capabilities") or []),
    }


def armA_evidence_ref_index(packet: dict) -> set:
    """Every evidence id the V6.1 packet actually contains.

    Arm A cites V6.1 ids (`MATCH:HOME:M01`, `AVAIL:competition`, summary row ids), never the
    V8A dotted paths. Scoring it against the V8A ref index would report a 100% hallucination
    rate by construction.
    """
    refs: set = set()

    def walk(o):
        if isinstance(o, dict):
            ev = o.get("evidence_id")
            if isinstance(ev, str):
                refs.add(ev)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(packet)

    # V6.1's DERIVED_SUMMARIES and OPPONENT_PROFILE_SUMMARIES are COLUMNAR: each row is a
    # list whose first column is `evidence_id`. A dict-only walk finds the AVAILABILITY_MAP
    # declarations and nothing else, so every SUMMARY:/PROFILE: citation -- which is most of
    # what Arm A actually cites -- would score as hallucinated.
    for sec in packet.get("sections") or []:
        cols = sec.get("columns")
        if not cols or "evidence_id" not in cols:
            continue
        i = cols.index("evidence_id")
        for row in sec.get("rows") or []:
            if isinstance(row, list) and len(row) > i and isinstance(row[i], str):
                refs.add(row[i])
    return refs


def armA_firewall_scan(h: dict, index: int, *, packet) -> list:
    """Arm A's prose lives in `question` / `evidence_summary`, which is exactly what
    `firewall_v5.scan_hypothesis` iterates. Use it unchanged for Arm A."""
    return FW.scan_hypothesis(h, index, packet=packet)


def audit_armA_hypothesis(h, index, *, cap, packet, library_keys, vocabulary, valid_refs):
    """The deterministic record for one Arm A hypothesis, scored by the SAME structural
    rules as Arm B but through Arm A's own field and evidence vocabulary."""
    view = armA_as_v8a_candidate(h)
    spec = armA_to_spec(h)
    ir = IRM.build_ir(spec)
    meas = measurability(view, cap)
    taut = tautology_checks(view)
    fw = armA_firewall_scan(h, index, packet=packet)
    blocking = FW.blocking(fw)

    cited = [r for r in (h.get("evidence_refs") or [])]
    bad = [r for r in cited if r not in valid_refs]

    ir_ok = ir.status == IRM.OK and meas["measurable"] and not taut["tautology"]
    ir_status = ir.status
    if ir.status == IRM.OK and not meas["measurable"]:
        ir_status = "UNSUPPORTED_OR_UNKNOWN_METRIC"
    if ir.status == IRM.OK and taut["tautology"]:
        ir_status = "TAUTOLOGY_OR_DEGENERATE_COHORT"

    return {
        "candidate_id": h.get("hypothesis_id"),
        "compiler": {"spec": spec, "ir_status": ir.status, "ir_ok": ir.status == IRM.OK,
                     "describes": ir.describe() if ir.status == IRM.OK else None},
        "measurability": meas,
        "tautology": taut,
        "firewall": {"n_findings": len(fw), "n_blocking": len(blocking),
                     "blocking_paths": [f.path for f in blocking][:10],
                     "clean": not blocking},
        "evidence_refs": {"n_cited": len(cited), "n_hallucinated": len(bad),
                          "hallucinated_refs": sorted(set(bad))[:20],
                          "all_refs_valid": not bad},
        "character": classify_character(view),
        "complexity": complexity(view),
        "novelty_verdict": G.judge(spec, library_keys, vocabulary,
                                   ir_ok=ir_ok, ir_status=ir_status),
        "schema_valid": True,
        "sufficiency": h.get("sufficiency"),
    }


# ---------------------------------------------------------------------------------------
# Firewall adjudication -- separating an instrument artifact from a genuine breach
# ---------------------------------------------------------------------------------------
#: Explicit references to the UPCOMING fixture. A numeric sentence carrying one of these is a
#: claim about the match that has not been played, which is the thing the firewall exists to
#: stop -- regardless of which field it appears in.
FUTURE_CLAIM_MARKERS = (
    "upcoming fixture", "in this match", "in the coming match", "next match",
    "will likely", "will be", "expected to be", "should be lower", "should be higher",
    "is expected to", "we expect", "this fixture will",
)

#: Deriving a NEW quantity from supplied values (e.g. inferring a league average from one
#: team's mean) is forbidden by brief section 7 even when it is about history.
DERIVED_QUANTITY_MARKERS = ("implied by", "implies a", "which implies", "extrapolat")


def sentences_of(text: str):
    return [s.strip() for s in re.split(r"(?<=[.;])\s+", text or "") if s.strip()]


def adjudicate_numeric_sentence(sentence: str) -> str:
    """Classify ONE numeric sentence. Deterministic, and reported with the sentence itself
    so a reader can check the call rather than trust it.

        FUTURE_CLAIM       a numeric claim about the fixture not yet played -- a real breach
        DERIVED_QUANTITY   a new quantity derived from supplied values -- a real breach
        HISTORICAL_DESCRIPTION  a characterisation of observed prior behaviour -- permitted
    """
    low = (sentence or "").lower()
    if not _NUM_RX.search(low):
        return "NO_NUMERIC"
    if any(m in low for m in FUTURE_CLAIM_MARKERS):
        return "FUTURE_CLAIM"
    if any(m in low for m in DERIVED_QUANTITY_MARKERS):
        return "DERIVED_QUANTITY"
    return "HISTORICAL_DESCRIPTION"


def adjudicate_candidate_prose(cand: dict) -> dict:
    """Every numeric sentence in a candidate's prose, with its adjudication and its text."""
    out = {"FUTURE_CLAIM": [], "DERIVED_QUANTITY": [], "HISTORICAL_DESCRIPTION": 0}
    texts = [cand.get(f) for f in PROSE_FIELDS]
    texts += [(o or {}).get("observation")
              for o in (cand.get("behavioral_observations") or [])]
    texts.append((cand.get("self_critique") or {}).get("notes"))
    for t in texts:
        if not isinstance(t, str):
            continue
        for sent in sentences_of(t):
            verdict = adjudicate_numeric_sentence(sent)
            if verdict in ("FUTURE_CLAIM", "DERIVED_QUANTITY"):
                out[verdict].append(sent[:400])
            elif verdict == "HISTORICAL_DESCRIPTION":
                out["HISTORICAL_DESCRIPTION"] += 1
    out["genuine_breach"] = bool(out["FUTURE_CLAIM"] or out["DERIVED_QUANTITY"])
    return out


def adjudicate_armA_prose(h: dict) -> dict:
    out = {"FUTURE_CLAIM": [], "DERIVED_QUANTITY": [], "HISTORICAL_DESCRIPTION": 0}
    for t in (h.get("question"), h.get("evidence_summary")):
        if not isinstance(t, str):
            continue
        for sent in sentences_of(t):
            verdict = adjudicate_numeric_sentence(sent)
            if verdict in ("FUTURE_CLAIM", "DERIVED_QUANTITY"):
                out[verdict].append(sent[:400])
            elif verdict == "HISTORICAL_DESCRIPTION":
                out["HISTORICAL_DESCRIPTION"] += 1
    out["genuine_breach"] = bool(out["FUTURE_CLAIM"] or out["DERIVED_QUANTITY"])
    return out
