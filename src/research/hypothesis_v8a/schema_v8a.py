"""V8A response schemas (`v8a_schema_v1`). Brief sections 14 and 15.

TWO schemas, one per pass, frozen and hashed before any model call.

PASS 1 -- first-pass candidates. Adds the reasoning surfaces V6.1's `schema_v4` had no place
for: behavioural observations with evidence references, an explicit football mechanism, an
explicit falsifier, and a self-critique. The V6.1 audit showed the incumbent schema went
straight from packet to structured answer with no intermediate surface at all; that absence
is the thing V8A is testing.

PASS 2 -- the generic novelty challenge. The model may KEEP, REFINE or ABSTAIN. Its
`incremental_structure` prose is AUDIT EVIDENCE ONLY and never sets the label -- the
deterministic canonicaliser in `genericlib.judge` owns that decision (brief sections 11/16).

STRUCTURAL FIELDS SPEAK THE COMPILER'S VOCABULARY
------------------------------------------------
`comparison`, `subject`, `side`, `window`, `conditions[].dimension` and
`conditions[].value` are the frozen V7.1 ontology terms. There is no second vocabulary and
nothing for the model to translate -- the same single-language discipline V5A.2 introduced
after three competing vocabularies caused a real defect.

ZERO SPEND.
"""
from __future__ import annotations

import hashlib
import json

from src.research.hypothesis_v71 import ontology as O

SCHEMA_VERSION = "v8a_schema_v1"

#: Brief section 21. Deliberately LOWER than V6.1's 12: abstention is successful behaviour
#: and filling slots earns nothing.
MAX_HYPOTHESES = 8
MAX_CONDITIONS = 4
MAX_OBSERVATIONS = 8
MAX_EVIDENCE_REFS = 12

COMPARATORS = sorted(O.COMPARATOR_BINDINGS)
FILTER_DIMENSIONS = sorted(O.FILTER_DIMENSIONS)
WINDOWS = list(O.WINDOWS)
PERSPECTIVES = list(O.PERSPECTIVES)
SUBJECTS = ["TEAM_A", "TEAM_B"]

RESEARCH_FAMILIES = ["ATTACK_VOLUME", "ATTACK_QUALITY", "DEFENSIVE_CONCESSION",
                     "DEFENSIVE_SUPPRESSION", "SET_PIECE_GENERATION",
                     "TEMPO_AND_TERRITORY", "DISCIPLINE",
                     "OPPONENT_PROFILE_INTERACTION", "FORM_VS_BASELINE", "VENUE_EFFECT"]

RISK = ["NONE", "LOW", "HIGH"]
ACTIONS = ["KEEP", "REFINE", "ABSTAIN"]


def _condition_schema():
    return {
        "type": "object", "additionalProperties": False,
        "required": ["dimension", "value"],
        "properties": {
            "dimension": {"type": "string", "enum": FILTER_DIMENSIONS,
                          "description": "A frozen filter dimension. This corpus honours "
                                         "exactly these three."},
            "axis": {"type": "string",
                     "description": "Required for opponent_profile: the profile axis."},
            "value": {"type": "string",
                      "description": "HOME/AWAY for venue; HIGH/MID/LOW for "
                                     "opponent_profile; SAME for competition."},
        },
    }


def candidate_schema():
    """One first-pass candidate (brief section 14)."""
    return {
        "type": "object", "additionalProperties": False,
        "required": ["candidate_id", "research_family", "subject", "opponent",
                     "target_metric", "metric_perspective", "behavioral_observations",
                     "football_mechanism", "comparison", "window", "conditions",
                     "falsifiable_question", "falsifier", "self_critique",
                     "provider_requirements", "support_risk", "coverage_risk"],
        "properties": {
            "candidate_id": {"type": "string"},
            "research_family": {"type": "string", "enum": RESEARCH_FAMILIES},
            "subject": {"type": "string", "enum": SUBJECTS,
                        "description": "Whose behaviour is MEASURED."},
            "opponent": {"type": "string", "enum": SUBJECTS,
                         "description": "The other side of the matchup."},
            "target_metric": {
                "type": "array", "minItems": 1, "maxItems": 5,
                "items": {"type": "string"},
                "description": "Metric names exactly as the capability envelope spells "
                               "them. A name the envelope does not list is not a metric."},
            "metric_perspective": {
                "type": "string", "enum": PERSPECTIVES,
                "description": "FOR = the subject's own value (its ATTACK side). "
                               "AGAINST = what the subject concedes (its DEFENSE side)."},
            "behavioral_observations": {
                "type": "array", "minItems": 1, "maxItems": MAX_OBSERVATIONS,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["observation", "evidence_refs"],
                    "properties": {
                        "observation": {
                            "type": "string", "minLength": 20, "maxLength": 500,
                            "description": "What the supplied evidence SHOWS. Describe "
                                           "measurable behaviour, never a prediction."},
                        "evidence_refs": {
                            "type": "array", "minItems": 1, "maxItems": MAX_EVIDENCE_REFS,
                            "items": {"type": "string"},
                            "description": "Paths into the packet you actually read, e.g. "
                                           "'TEAM_A.recent_last_5.shots_on_target_for' or "
                                           "'TEAM_B.raw.ROW:07'."},
                    },
                },
            },
            "football_mechanism": {
                "type": "string", "minLength": 30, "maxLength": 900,
                "description": "The football interaction that might explain the "
                               "observation. Not a restatement of the observation."},
            "comparison": {"type": "string", "enum": COMPARATORS,
                           "description": "The frozen comparator defining cohort vs "
                                          "baseline. You do not invent either."},
            "window": {"type": "string", "enum": WINDOWS},
            "conditions": {"type": "array", "maxItems": MAX_CONDITIONS,
                           "items": _condition_schema()},
            "similar_opponent_rationale": {
                "type": "string", "maxLength": 500,
                "description": "Only for SIMILAR_OPPONENT_COHORT: why similarity is the "
                               "right cohort. The engine computes similarity; you do not."},
            "formation_context": {
                "type": "string", "maxLength": 500,
                "description": "Optional. Formation may MOTIVATE a question only by "
                               "pointing at raw behaviour that actually differs. It can "
                               "never be a cohort condition in this corpus."},
            "falsifiable_question": {"type": "string", "minLength": 30, "maxLength": 600},
            "falsifier": {
                "type": "string", "minLength": 20, "maxLength": 600,
                "description": "The deterministic result that would leave the mechanism "
                               "unsupported. A result consistent with no systematic "
                               "difference is sufficient. Do NOT invent a numeric "
                               "threshold."},
            "self_critique": {
                "type": "object", "additionalProperties": False,
                "required": ["is_just_recent_vs_long_run", "is_just_home_vs_away",
                             "condition_equals_target", "cohort_equals_baseline",
                             "could_opponent_strength_explain_it", "is_overconditioned",
                             "likely_generic_enumeration_would_generate_this", "notes"],
                "properties": {
                    "is_just_recent_vs_long_run": {"type": "boolean"},
                    "is_just_home_vs_away": {"type": "boolean"},
                    "condition_equals_target": {"type": "boolean"},
                    "cohort_equals_baseline": {"type": "boolean"},
                    "could_opponent_strength_explain_it": {"type": "boolean"},
                    "is_overconditioned": {"type": "boolean"},
                    "likely_generic_enumeration_would_generate_this": {"type": "boolean"},
                    "notes": {"type": "string", "maxLength": 600},
                },
            },
            "provider_requirements": {"type": "array", "items": {"type": "string"},
                                      "maxItems": 12},
            "support_risk": {"type": "string", "enum": RISK},
            "coverage_risk": {"type": "string", "enum": RISK},
        },
    }


def pass1_schema():
    return {
        "type": "object", "additionalProperties": False,
        "required": ["fixture_id", "reconnaissance", "interaction_map", "candidates"],
        "properties": {
            "fixture_id": {"type": "string"},
            "reconnaissance": {
                "type": "object", "additionalProperties": False,
                "required": ["team_a_attack", "team_a_defense",
                             "team_b_attack", "team_b_defense"],
                "properties": {
                    k: {"type": "array", "minItems": 0, "maxItems": 8,
                        "items": {"type": "string", "minLength": 20, "maxLength": 400}}
                    for k in ("team_a_attack", "team_a_defense",
                              "team_b_attack", "team_b_defense")
                },
            },
            "interaction_map": {
                "type": "object", "additionalProperties": False,
                "required": ["a_attack_vs_b_defense", "b_attack_vs_a_defense"],
                "properties": {
                    "a_attack_vs_b_defense": {"type": "array", "maxItems": 8,
                                              "items": {"type": "string",
                                                        "maxLength": 400}},
                    "b_attack_vs_a_defense": {"type": "array", "maxItems": 8,
                                              "items": {"type": "string",
                                                        "maxLength": 400}},
                    "tensions": {"type": "array", "maxItems": 6,
                                 "items": {"type": "string", "maxLength": 400}},
                    "asymmetries": {"type": "array", "maxItems": 6,
                                    "items": {"type": "string", "maxLength": 400}},
                    "regime_changes": {"type": "array", "maxItems": 6,
                                       "items": {"type": "string", "maxLength": 400}},
                },
            },
            "candidates": {"type": "array", "minItems": 0, "maxItems": MAX_HYPOTHESES,
                           "items": candidate_schema()},
            "abstention_reason": {"type": "string", "maxLength": 600},
        },
    }


def pass2_schema():
    """The generic novelty challenge response (brief section 15)."""
    return {
        "type": "object", "additionalProperties": False,
        "required": ["candidate_id", "action", "closest_generic_structures",
                     "shared_structure", "incremental_structure", "reason"],
        "properties": {
            "candidate_id": {"type": "string"},
            "action": {"type": "string", "enum": ACTIONS},
            "closest_generic_structures": {"type": "array", "maxItems": 3,
                                           "items": {"type": "string"}},
            "shared_structure": {"type": "array", "maxItems": 10,
                                 "items": {"type": "string", "maxLength": 300}},
            "incremental_structure": {
                "type": "array", "maxItems": 10,
                "items": {"type": "string", "maxLength": 300},
                "description": "AUDIT EVIDENCE ONLY. This does not set the label; a "
                               "deterministic canonicaliser does."},
            "reason": {"type": "string", "minLength": 20, "maxLength": 900},
            "final_candidate": candidate_schema(),
        },
    }


def schema_content_hash() -> str:
    blob = {"version": SCHEMA_VERSION,
            "pass1": pass1_schema(), "pass2": pass2_schema(),
            "max_hypotheses": MAX_HYPOTHESES}
    return hashlib.sha256(
        json.dumps(blob, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def version_stamp() -> dict:
    return {"schema_version": SCHEMA_VERSION,
            "schema_content_hash": schema_content_hash(),
            "max_hypotheses": MAX_HYPOTHESES,
            "adds_over_schema_v4": ["behavioral_observations[] with evidence_refs",
                                    "football_mechanism", "falsifier", "self_critique",
                                    "explicit subject/opponent matchup roles",
                                    "second pass: generic novelty challenge"],
            "llm_sets_the_novelty_label": False}
