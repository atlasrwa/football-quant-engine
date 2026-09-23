"""Compile the six frozen ChatGPT hypotheses into deterministic ResearchQuerySpecs.

Validation only; nothing is measured. Reads the frozen hypotheses and the packet's evidence-ref
index / fixture identity. Reads no match data and no outcome.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.research.dual_provider_llm import packet as P
from src.research.dual_provider_llm.measurement import query_spec as Q
from src.research.dual_provider_llm.measurement import support as S
from src.research.dual_provider_llm.measurement.pit_history import (FORBIDDEN_METRICS,
                                                                     SUPPORTED_METRICS)

EXPECTED_IDS = (
    "DP1_BOX_PRESSURE_MATCHUP", "DP2_WIDE_CENTRAL_INTERACTION",
    "DP3_ALBACETE_DIRECT_PROGRESSION", "DP4_GIRONA_CURRENT_TERRITORIAL_REGIME",
    "DP5_ALBACETE_RECENT_TERRITORIAL_EXPANSION", "DP6_PRESSURE_RESOLUTION_CLEARANCE_PROFILE")
PROSE_FIELDS = ("research_question", "football_rationale", "deterministic_measurement_plan",
                "similarity_dimensions", "confounders", "provider_constraints")


class CompileError(ValueError):
    pass


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def spec_metrics(spec: Dict[str, Any]) -> List[str]:
    ms = set(spec.get("input_metrics", []))
    for key in ("similarity_dimensions", "state_dimensions"):
        ms |= {m for m, _ in spec.get(key, [])}
    ms |= {m for m, _ in spec["outputs"].get("metrics", [])}
    return sorted(ms)


def numeric_tokens(h: Dict[str, Any]) -> List[str]:
    """Numbers appearing in the hypothesis prose (window names like RECENT_5 are labels)."""
    text = json.dumps({k: h.get(k) for k in PROSE_FIELDS}, ensure_ascii=False)
    return re.findall(r"(?<![A-Za-z_0-9.])\d+(?:\.\d+)?%?", text)


def _walk_numbers(o, path="") -> List[Tuple[str, Any]]:
    """Every numeric leaf that is NOT inside a {"constant", "value"} reference."""
    out = []
    if isinstance(o, dict):
        if set(o) == {"constant", "value"} and o["constant"] in S.PROTOCOL_CONSTANTS:
            return out
        for k, v in o.items():
            out += _walk_numbers(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            out += _walk_numbers(v, f"{path}[{i}]")
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        out.append((path, o))
    return out


def compile_all(hyp_path: Path, packet_path: Path) -> Dict[str, Any]:
    hyp_bytes, pk_bytes = hyp_path.read_bytes(), packet_path.read_bytes()
    hyp, pk = json.loads(hyp_bytes), json.loads(pk_bytes)
    if hyp.get("source_packet_sha256") != sha(pk_bytes):
        raise CompileError("hypotheses were not generated from this packet")
    mechs = hyp["mechanisms"]
    if tuple(m["mechanism_id"] for m in mechs) != EXPECTED_IDS:
        raise CompileError("mechanism ids differ from the frozen six")
    idx = pk["evidence_ref_index"]
    refs = set(idx["aggregate_refs"]) | set(idx["raw_refs"])
    concepts = set(pk["field_scope"]["concepts"])
    specs = {s["mechanism_id"]: s for s in Q.specs()}
    compiled, audits = [], []
    for h in mechs:
        mid = h["mechanism_id"]
        s = dict(specs[mid])
        issues: List[str] = []
        missing_refs = [r for r in h["evidence_refs"] if r not in refs]
        variables = [v.split(":", 1)[1] for v in h["variables"]]
        if any(not v.startswith("thestatsapi:") for v in h["variables"]):
            raise CompileError(f"{mid}: non-TheStatsAPI variable")
        bad_vars = [v for v in variables if v not in concepts]
        ms = spec_metrics(s)
        unsupported = [m for m in ms if m not in SUPPORTED_METRICS or m in FORBIDDEN_METRICS]
        prose = json.dumps({k: h.get(k) for k in PROSE_FIELDS}, ensure_ascii=False)
        prose_only = {p["metric"]: p["quote"] for p in s["metrics_named_in_prose_only"]}
        for m, q in prose_only.items():
            if q not in prose:
                raise CompileError(f"{mid}: prose quote for {m} not found in the hypothesis")
        outside = [m for m in ms if m not in variables and m not in prose_only]
        stray = _walk_numbers(s)
        if missing_refs or bad_vars or unsupported or outside or stray:
            raise CompileError(f"{mid}: refs={missing_refs} vars={bad_vars} "
                               f"unsupported={unsupported} outside={outside} numbers={stray}")
        if "blocked_shots" in ms:
            raise CompileError(f"{mid}: blocked_shots used")
        for m in prose_only:
            issues.append(f"'{m}' is used because the hypothesis names it in prose "
                          f"('{prose_only[m]}') although it is absent from its variables list")
        s.update({
            "scientific_question": h["research_question"],
            "frozen_evidence_refs": h["evidence_refs"],
            "hypothesis_variables": variables,
            "relationship_type": h["relationship_type"],
            "llm_similarity_dimensions_verbatim": h["similarity_dimensions"],
            "llm_confounders_verbatim": h["confounders"],
            "llm_measurement_plan_verbatim_non_authoritative": h["deterministic_measurement_plan"],
            "numeric_tokens_in_hypothesis_prose": numeric_tokens(h),
            "numeric_tokens_used_as_parameters": [],
        })
        compiled.append(s)
        if mid == "DP2_WIDE_CENTRAL_INTERACTION":
            issues.append("provider semantics: accurate_crosses may count corner deliveries and "
                          "touches_in_box set-piece touches (possible mechanical/reverse link)")
        if mid == "DP5_ALBACETE_RECENT_TERRITORIAL_EXPANSION":
            issues.append("primary is descriptive (no valid exchangeable null); excluded from "
                          "BH; recent away block spans the summer break")
        if mid == "DP4_GIRONA_CURRENT_TERRITORIAL_REGIME":
            issues.append("recent windows straddle LaLiga -> LaLiga 2; reference matches are "
                          "excluded from the comparison pool")
        if mid in ("DP1_BOX_PRESSURE_MATCHUP", "DP6_PRESSURE_RESOLUTION_CLEARANCE_PROFILE"):
            issues.append("DP1 and DP6 share the population and 2 of 4 profile dimensions; "
                          "their neighbour sets will overlap")
        audits.append({
            "MECHANISM_ID": mid, "COMPILABLE": True,
            "PRIMARY_POPULATION": s["population_definition"],
            "PRIMARY_OUTPUT": s["primary_measurement"]["statistic"],
            "INPUT_METRICS": ms,
            "SIMILARITY_REQUIRED": s["design"] in ("NEIGHBOR_GROUP_DIFFERENCE",
                                                   "STATE_RESIDUAL_GROUP_DIFFERENCE"),
            "SIMILARITY_DIMENSIONS": [f"{m}.{p}" for m, p in s["similarity_dimensions"]],
            "MIN_SUPPORT": s["minimum_sample_requirements"],
            "CONFOUNDERS": s["confounders"],
            "PIT_SAFE": True, "PROVIDER_SAFE": True, "NUMERIC_LLM_INPUT_USED": False,
            "OPEN_ISSUES": issues,
        })
    return {
        "protocol_version": S.PROTOCOL_VERSION,
        "source_hypotheses_path": "research/dual_provider_llm/out/direct_pilot/"
                                  "CHATGPT_HYPOTHESES_V1.json",
        "source_hypotheses_sha256": sha(hyp_bytes),
        "source_packet_sha256": sha(pk_bytes),
        "target_context": {"fixture_id": pk["fixture"]["fixture_id"],
                           "cutoff_unix": pk["cutoff_unix"],
                           "home_team_id": pk["fixture"]["home_team"]["provider_team_id"],
                           "away_team_id": pk["fixture"]["away_team"]["provider_team_id"],
                           "target_outcome_read": False},
        "protocol_constants": {k: {"value": v, "rationale": r}
                               for k, (v, r) in sorted(S.PROTOCOL_CONSTANTS.items())},
        "similarity_method": Q.SIMILARITY,
        "competition_policy": Q.COMMON_COMPETITION,
        "bh_family": [s["mechanism_id"] for s in compiled
                      if s["primary_measurement"].get("in_bh_family")],
        "bh_q": S.c("BH_Q"),
        "specs": compiled,
        "audits": audits,
        "outcomes_read": False, "historical_effects_computed": False, "model_fit": False,
        "p_model_produced": False,
    }


def dumps(doc: Dict[str, Any]) -> str:
    return json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
