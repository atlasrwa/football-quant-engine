"""football_state_schema_v3 — hardened structured-output contract (patch §11-§16, §22).

This is a NEW schema version; the frozen `schema.py` (football_state_schema_v2) is untouched.

What V3 adds over V2:
  * A REQUIRED `counter_evidence_search` field on EVERY assessment (team-state and matchup),
    with enum {PERFORMED, SKIPPED} (patch §12). This makes "I looked and found nothing"
    distinguishable from "I never looked". An empty `counter_evidence_ids` is only VALID
    when `counter_evidence_search == PERFORMED` — enforced by validator_v3, not the schema
    (the schema cannot express that cross-field constraint).

Everything else is inherited unchanged from the frozen contract:
  * closed objects (`additionalProperties: false`) everywhere (patch §12 "closed-object rules");
  * ontology enums for mechanism / level / assessment / confidence / uncertainty_factors;
  * NO probability / prediction / narrative fields (patch §46);
  * NO reasoning_trace / analysis_notes / thinking fields (patch §47).

The schema is used both as the Bedrock tool input schema (structured output) and by the
deterministic validator_v3.
"""
from __future__ import annotations
from src.research.llm_matchup import ontology as ONT

# Counter-evidence search state (patch §12). SKIPPED is only legitimate for an UNKNOWN
# assessment where there was literally no allowed PIT-safe evidence to search.
COUNTER_EVIDENCE_SEARCH = ["PERFORMED", "SKIPPED"]


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
    return {"type": "array", "minItems": min_items, "items": {"type": "string"}}


def _uncertainty_array():
    return {"type": "array", "items": {"type": "string", "enum": ONT.UNCERTAINTY_FACTORS}}


def _state_item() -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["mechanism", "level", "confidence", "evidence_ids",
                     "counter_evidence_ids", "counter_evidence_search",
                     "uncertainty_factors", "preferred_evidence_level"],
        "properties": {
            "mechanism": {"type": "string", "enum": ONT.mechanism_ids()},
            "level": {"type": "string", "enum": ONT.LEVELS},
            "confidence": {"type": "string", "enum": ONT.CONFIDENCE},
            "evidence_ids": _evidence_id_array(0),
            "counter_evidence_ids": _evidence_id_array(0),
            "counter_evidence_search": {"type": "string", "enum": COUNTER_EVIDENCE_SEARCH},
            "uncertainty_factors": _uncertainty_array(),
            "preferred_evidence_level": {"type": "string", "enum": ONT.EVIDENCE_LEVELS},
        },
    }


def _matchup_item() -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["mechanism", "assessment", "confidence", "supporting_evidence_ids",
                     "counter_evidence_ids", "counter_evidence_search", "uncertainty_factors"],
        "properties": {
            "mechanism": {"type": "string", "enum": ONT.mechanism_ids()},
            "assessment": {"type": "string", "enum": ONT.ADVANTAGE_LEVELS + ONT.LEVELS},
            "confidence": {"type": "string", "enum": ONT.CONFIDENCE},
            "supporting_evidence_ids": _evidence_id_array(0),
            "counter_evidence_ids": _evidence_id_array(0),
            "counter_evidence_search": {"type": "string", "enum": COUNTER_EVIDENCE_SEARCH},
            "uncertainty_factors": _uncertainty_array(),
        },
    }


def schema_content_hash() -> str:
    import hashlib, json
    return hashlib.sha256(json.dumps(build_schema(), sort_keys=True).encode()).hexdigest()
