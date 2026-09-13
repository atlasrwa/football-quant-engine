"""football_state_schema_v1 — strict structured output contract for the LLM.

The LLM returns ONLY a football STATE object conforming to this JSON Schema. It contains
no probabilities (brief §32). Every object sets additionalProperties=false (brief §22).
Every mechanism assessment must cite evidence_ids and provide counter_evidence_ids +
uncertainty_factors (brief §19, §20). All labels are ontology enums (brief §16).

The schema is emitted to schema.json and used both as the Bedrock tool input schema
and by the deterministic validator.
"""
from __future__ import annotations
from src.research.llm_matchup import ontology as ONT


def build_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["fixture_id", "information_cutoff_unix", "context_flags",
                     "team_a_states", "team_b_states", "matchup_states"],
        "properties": {
            "fixture_id": {"type": "string"},
            "information_cutoff_unix": {"type": "integer"},
            "context_flags": {
                "type": "object", "additionalProperties": False,
                "required": list(ONT.CONTEXT_FLAGS.keys()),
                "properties": {k: {"type": "string", "enum": v}
                               for k, v in ONT.CONTEXT_FLAGS.items()},
            },
            "team_a_states": {"type": "array", "items": _state_item()},
            "team_b_states": {"type": "array", "items": _state_item()},
            "matchup_states": {"type": "array", "items": _matchup_item()},
        },
    }


def _evidence_id_array(min_items=0):
    return {"type": "array", "minItems": min_items,
            "items": {"type": "string"}}


def _uncertainty_array():
    return {"type": "array",
            "items": {"type": "string", "enum": ONT.UNCERTAINTY_FACTORS}}


def _state_item() -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["mechanism", "level", "confidence", "evidence_ids",
                     "counter_evidence_ids", "uncertainty_factors", "preferred_evidence_level"],
        "properties": {
            "mechanism": {"type": "string", "enum": ONT.mechanism_ids()},
            "level": {"type": "string", "enum": ONT.LEVELS},
            "confidence": {"type": "string", "enum": ONT.CONFIDENCE},
            "evidence_ids": _evidence_id_array(0),
            "counter_evidence_ids": _evidence_id_array(0),
            "uncertainty_factors": _uncertainty_array(),
            "preferred_evidence_level": {"type": "string", "enum": ONT.EVIDENCE_LEVELS},
        },
    }


def _matchup_item() -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["mechanism", "assessment", "confidence", "supporting_evidence_ids",
                     "counter_evidence_ids", "uncertainty_factors"],
        "properties": {
            "mechanism": {"type": "string", "enum": ONT.mechanism_ids()},
            "assessment": {"type": "string", "enum": ONT.ADVANTAGE_LEVELS + ONT.LEVELS},
            "confidence": {"type": "string", "enum": ONT.CONFIDENCE},
            "supporting_evidence_ids": _evidence_id_array(0),
            "counter_evidence_ids": _evidence_id_array(0),
            "uncertainty_factors": _uncertainty_array(),
        },
    }
