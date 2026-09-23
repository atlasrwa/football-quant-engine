"""Output schema, validator and deterministic novelty compiler for Sol hypotheses.

The LLM must express each feature as a STRUCTURED template from a closed grammar, so the
engine (not the LLM) classifies novelty and compiles a generic panel feature.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.research.target_aware_market_panel import policy as POL

SCHEMA_VERSION = "target_aware_output_schema_v1"

SIDES = ("HOME", "AWAY")
PERSPECTIVES = ("FOR", "AGAINST")
WINDOWS = ("W5", "W10", "SEASON_TO_DATE", "VENUE_SEASON_TO_DATE")     # all strictly prior
PERIODS = ("FULL_MATCH", "FIRST_HALF", "SECOND_HALF")
HALF_OK_METRICS = frozenset(POL.HALF_PROVIDER_FIELDS)
SUPPORTED_METRICS = frozenset(m for v in POL.FAMILY_CONTEXT.values() for m in v)
FORBIDDEN_METRICS = frozenset({"blocked_shots", "npxg", "expected_goals", "goals_prevented",
                               "red_cards", "xg"})
TEMPLATE_TYPES = {
    "ROLLING_PROFILE": {"combine": {"IDENTITY"}, "n_components": (1, 1)},
    "PAIRWISE_COMBINATION": {"combine": {"SUM", "DIFFERENCE", "PRODUCT", "RATIO"},
                             "n_components": (2, 2)},
    "MULTI_DIMENSION_MATCHUP": {"combine": {"MEAN_PRODUCT"}, "n_components": (4, 12)},
    "OPPONENT_SIMILARITY_CONDITIONAL": {"combine": {"SIMILARITY_CONDITIONAL"},
                                        "n_components": (0, 0)},
    "STATE_DEVIATION": {"combine": {"RECENT_MINUS_LONG_RUN"}, "n_components": (0, 0)},
}
FORBIDDEN_OUTPUT_KEYS = frozenset({"probability", "p_model", "odds", "fair_odds", "ev", "edge",
                                   "stake", "confidence", "expected_effect_size",
                                   "feature_weight", "prediction", "pick", "direction",
                                   "kelly"})
FORBIDDEN_OUTPUT_VALUES = ("OVER", "UNDER")          # as standalone picks
REQUIRED_FIELDS = (
    "hypothesis_id", "target", "market_family", "fixture_context_observation",
    "predictive_mechanism", "future_target_label", "evidence_refs", "pre_match_feature_inputs",
    "feature_template", "opponent_profile_dimensions", "why_baseline_may_miss_it",
    "panel_generalization_rule", "deterministic_test_request", "confounders",
    "provider_constraints", "required_resolution", "same_match_information_required",
    "abstain_reason")

MAX_HYPOTHESES_PER_TARGET = 2

CLASSES = ("A_BASELINE_EQUIVALENT", "B_SIMPLE_INTERACTION", "C_CONTEXTUAL_TEMPLATE",
           "D_UNMEASURABLE", "E_PROVIDER_UNSUPPORTED", "F_SAME_MATCH_LEAKAGE",
           "G_DUPLICATE_TEMPLATE")


def output_schema() -> Dict[str, Any]:
    comp = {"side": list(SIDES), "metric": "one of the slice's metrics_in_slice",
            "perspective": list(PERSPECTIVES), "window": list(WINDOWS),
            "period": list(PERIODS)}
    return {
        "schema_version": SCHEMA_VERSION,
        "response": {"fixture_id": "string", "family": "string",
                     "hypotheses": "array (0..2 per target in this family slice)",
                     "abstentions": "array of {target, abstain_reason}"},
        "hypothesis_required_fields": list(REQUIRED_FIELDS),
        "field_rules": {
            "target": "exactly one target_id from the request's target list",
            "future_target_label": "the settlement rule of that target, copied from the request",
            "evidence_refs": "every ref must exist in the request's evidence_ref_index",
            "same_match_information_required": "must be false",
            "pre_match_feature_inputs": "list of component descriptions; every window is one of "
                                        f"{list(WINDOWS)} (all strictly before kickoff)",
            "feature_template": {
                "template_type": list(TEMPLATE_TYPES),
                "combine": {k: sorted(v["combine"]) for k, v in TEMPLATE_TYPES.items()},
                "components": comp,
                "similarity (OPPONENT_SIMILARITY_CONDITIONAL only)": {
                    "subject_side": list(SIDES), "subject_metric": "metric",
                    "subject_perspective": list(PERSPECTIVES),
                    "profile_side": "the OTHER side",
                    "profile_dimensions": "2-5 x {metric, perspective}; style only, never "
                                          "goals/strength"},
                "state (STATE_DEVIATION only)": {"side": list(SIDES),
                                                 "dimensions": "2-5 x {metric, perspective}"},
                "MULTI_DIMENSION_MATCHUP": "components in consecutive pairs (side X FOR, other "
                                           "side AGAINST) of the same metric; >= 2 pairs"},
            "abstain_reason": "null when proposing; a reason string when abstaining"},
        "forbidden_keys_anywhere": sorted(FORBIDDEN_OUTPUT_KEYS),
        "forbidden_content": ["numbers used as thresholds or weights", "probabilities",
                              "betting direction (OVER/UNDER as a pick)", "odds", "stakes"],
    }


def _walk_keys(o) -> Set[str]:
    ks: Set[str] = set()
    if isinstance(o, dict):
        for k, v in o.items():
            ks.add(str(k).lower())
            ks |= _walk_keys(v)
    elif isinstance(o, list):
        for v in o:
            ks |= _walk_keys(v)
    return ks


def forbidden_content(obj) -> List[str]:
    hits = sorted(k for k in _walk_keys(obj) if k in FORBIDDEN_OUTPUT_KEYS)
    return hits


def _comp_ok(c: Dict[str, Any]) -> Optional[str]:
    for k, allowed in (("side", SIDES), ("perspective", PERSPECTIVES), ("period", PERIODS)):
        if c.get(k) not in allowed:
            return f"component {k}={c.get(k)!r}"
    if c.get("window") not in WINDOWS:
        return "WINDOW_NOT_PRIOR"
    return None


def _all_metrics(t: Dict[str, Any]) -> List[Tuple[str, str]]:
    out = [(c.get("metric"), c.get("period", "FULL_MATCH")) for c in t.get("components", [])]
    s = t.get("similarity") or {}
    if s:
        out.append((s.get("subject_metric"), "FULL_MATCH"))
        out += [(d.get("metric"), "FULL_MATCH") for d in s.get("profile_dimensions", [])]
    st = t.get("state") or {}
    out += [(d.get("metric"), "FULL_MATCH") for d in st.get("dimensions", [])]
    return out


def canonical_key(h: Dict[str, Any], market_id: Optional[str] = None) -> str:
    """Identity = (market, template). Line-independent: the same template for another line of
    the same market, or from another fixture, is the same M1 column."""
    t = h.get("feature_template") or {}
    body = {"market": market_id or h.get("target"), "type": t.get("template_type"),
            "combine": t.get("combine"),
            "components": sorted(json.dumps(c, sort_keys=True) for c in t.get("components", [])),
            "similarity": t.get("similarity"), "state": t.get("state")}
    return json.dumps(body, sort_keys=True)


def classify(h: Dict[str, Any], *, target_ids: Set[str], family: str,
             evidence_refs: Set[str], seen_keys: Set[str],
             market_of: Optional[Dict[str, str]] = None) -> Tuple[str, List[str]]:
    """Deterministic class for one hypothesis. Precedence D > F > E > G > A/B/C."""
    why: List[str] = []
    missing = [f for f in REQUIRED_FIELDS if f not in h]
    if missing:
        return "D_UNMEASURABLE", [f"missing fields {missing}"]
    if forbidden_content(h):
        return "D_UNMEASURABLE", [f"forbidden keys {forbidden_content(h)}"]
    if h["target"] not in target_ids:
        return "D_UNMEASURABLE", ["target not in this request's target list"]
    bad_refs = [r for r in h["evidence_refs"] if r not in evidence_refs]
    if bad_refs or not h["evidence_refs"]:
        return "D_UNMEASURABLE", [f"unresolved evidence refs {bad_refs[:5]}"]
    t = h["feature_template"]
    tt = t.get("template_type") if isinstance(t, dict) else None
    if tt not in TEMPLATE_TYPES or t.get("combine") not in TEMPLATE_TYPES[tt]["combine"]:
        return "D_UNMEASURABLE", ["template_type/combine outside the grammar"]
    lo, hi = TEMPLATE_TYPES[tt]["n_components"]
    comps = t.get("components", [])
    if not lo <= len(comps) <= hi:
        return "D_UNMEASURABLE", ["component count outside the grammar"]
    if h["same_match_information_required"] is not False:
        return "F_SAME_MATCH_LEAKAGE", ["same_match_information_required is not false"]
    for c in comps:
        e = _comp_ok(c)
        if e == "WINDOW_NOT_PRIOR":
            return "F_SAME_MATCH_LEAKAGE", [f"window {c.get('window')!r} is not strictly prior"]
        if e:
            return "D_UNMEASURABLE", [e]
    if tt == "OPPONENT_SIMILARITY_CONDITIONAL":
        s = t.get("similarity") or {}
        dims = s.get("profile_dimensions") or []
        if s.get("subject_side") not in SIDES or s.get("profile_side") not in SIDES or \
                s.get("subject_side") == s.get("profile_side") or not 2 <= len(dims) <= 5 or \
                s.get("subject_perspective") not in PERSPECTIVES or \
                any(d.get("perspective") not in PERSPECTIVES for d in dims):
            return "D_UNMEASURABLE", ["malformed similarity block"]
        if any(d.get("metric") == "goals" for d in dims):
            return "D_UNMEASURABLE", ["profile dimensions must be style, not goals/strength"]
    if tt == "STATE_DEVIATION":
        st = t.get("state") or {}
        dims = st.get("dimensions") or []
        if st.get("side") not in SIDES or not 2 <= len(dims) <= 5 or \
                any(d.get("perspective") not in PERSPECTIVES for d in dims):
            return "D_UNMEASURABLE", ["malformed state block"]
    if tt == "MULTI_DIMENSION_MATCHUP":
        if len(comps) % 2:
            return "D_UNMEASURABLE", ["matchup components must be pairs"]
        for a, b in zip(comps[::2], comps[1::2]):
            if a.get("metric") != b.get("metric") or a.get("side") == b.get("side") or \
                    a.get("perspective") == b.get("perspective"):
                return "D_UNMEASURABLE", ["matchup pair must be same metric, opposite sides, "
                                          "FOR x AGAINST"]
    for m, per in _all_metrics(t):
        if m in FORBIDDEN_METRICS or m not in SUPPORTED_METRICS:
            return "E_PROVIDER_UNSUPPORTED", [f"metric {m!r} unsupported/forbidden"]
        if m not in POL.FAMILY_CONTEXT[family]:
            return "E_PROVIDER_UNSUPPORTED", [f"metric {m!r} not in the {family} slice"]
        if per != "FULL_MATCH" and m not in POL.HALF_CONTEXT.get(family, []):
            return "E_PROVIDER_UNSUPPORTED", [f"half-level {m!r} not in the {family} "
                                              "half-level context"]
    key = canonical_key(h, (market_of or {}).get(h["target"]))
    if key in seen_keys:
        return "G_DUPLICATE_TEMPLATE", ["identical canonical template already seen"]
    seen_keys.add(key)
    m0 = set(POL.FAMILY_CONTEXT[family])
    m0_half = set(POL.HALF_CONTEXT.get(family, []))

    def is_m0(c):
        if c["window"] not in POL.M0_WINDOWS:
            return False
        return c["metric"] in (m0 if c["period"] == "FULL_MATCH" else m0_half)
    if tt == "ROLLING_PROFILE":
        return ("A_BASELINE_EQUIVALENT" if is_m0(comps[0]) else "B_SIMPLE_INTERACTION"), [
            "single rolling mean"]
    if tt == "PAIRWISE_COMBINATION":
        if t["combine"] in ("SUM", "DIFFERENCE") and all(is_m0(c) for c in comps):
            return "A_BASELINE_EQUIVALENT", ["linear combination of M0 features"]
        return "B_SIMPLE_INTERACTION", ["pairwise combination (enumerable)"]
    return "C_CONTEXTUAL_TEMPLATE", [f"{tt} requires contextual structure"]


def compile_response(resp: Dict[str, Any], request: Dict[str, Any],
                     seen: Optional[Set[str]] = None) -> Dict[str, Any]:
    target_ids = {t["target_id"] for t in request["targets"]}
    market_of = {t["target_id"]: t["market_id"] for t in request["targets"]}
    refs = set(request["evidence_packet"]["evidence_ref_index"])
    seen = set() if seen is None else seen
    out, per_target = [], {}
    for h in resp.get("hypotheses", []):
        per_target[h.get("target")] = per_target.get(h.get("target"), 0) + 1
        if per_target[h.get("target")] > MAX_HYPOTHESES_PER_TARGET:
            cls, why = "D_UNMEASURABLE", ["exceeds the per-target volume limit (kept first 2)"]
        else:
            cls, why = classify(h, target_ids=target_ids, family=request["family"],
                                evidence_refs=refs, seen_keys=seen, market_of=market_of)
        out.append({"hypothesis_id": h.get("hypothesis_id"), "target": h.get("target"),
                    "class": cls, "reasons": why,
                    "panel_eligible": cls == "C_CONTEXTUAL_TEMPLATE"})
    over = [t for t, n in per_target.items() if n > MAX_HYPOTHESES_PER_TARGET]
    return {"fixture_id": request["fixture"]["fixture_id"], "family": request["family"],
            "classified": out, "targets_over_limit": over,
            "response_forbidden_keys": forbidden_content(resp)}


def compile_cohort(pairs: Sequence[Tuple[Dict[str, Any], Dict[str, Any]]]) -> Dict[str, Any]:
    """Compile all (response, request) pairs in the fixed order (fixture id, family) with ONE
    shared duplicate set, so identical templates across fixtures become one M1 column. The
    resulting class-C set is the frozen template family, fixed before any panel outcome."""
    ordered = sorted(pairs, key=lambda p: (p[1]["fixture"]["provider_fixture_id"],
                                           p[1]["family"]))
    seen: Set[str] = set()
    compiled = [compile_response(resp, req, seen) for resp, req in ordered]
    c_set = [{"fixture_id": c["fixture_id"], "family": c["family"], **h}
             for c in compiled for h in c["classified"] if h["panel_eligible"]]
    counts: Dict[str, int] = {}
    for c in compiled:
        for h in c["classified"]:
            counts[h["class"]] = counts.get(h["class"], 0) + 1
    return {"compiled": compiled, "class_counts": dict(sorted(counts.items())),
            "frozen_class_c_templates": c_set, "n_class_c": len(c_set),
            "secondary_lines_instantiated_from_primary_templates": True}
