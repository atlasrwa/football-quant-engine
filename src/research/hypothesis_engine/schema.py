"""`hypothesis_set_schema_v1` -- the LLM's entire output contract.

Generation-neutral: nothing here names a model, a vendor or a prompt revision, so both
arms of any future comparison are judged against one schema.

DESIGN NOTE -- why the schema IS the firewall's first layer
-----------------------------------------------------------
Every object is closed (`additionalProperties: false`) and every value-bearing field is
one of: an enum drawn from `vocabulary`, an id string matched against the evidence packet,
or a bounded free-text `question`. There is no field of type `number` anywhere in the
hypothesis body. A probability, an edge, an odds quote or an effect size therefore has no
legal place to be written -- it is a structural impossibility, not a filtered string.

The single free-text field (`question`) is the one residual surface, and
`firewall.scan_prose` covers exactly that field.

Inherited verbatim from the frozen legacy contract (`football_state_schema_v3`), because
that discipline was correct even though its target was not:
  * closed objects everywhere;
  * enum-only categorical values;
  * explicit evidence-id arrays;
  * no reasoning_trace / analysis_notes / thinking field.
"""
from __future__ import annotations

import hashlib
import json

from . import capability, vocabulary

SCHEMA_VERSION = "hypothesis_set_schema_v1"

#: Bounds on the free-text question. Long enough for a real conditional question, short
#: enough that it cannot become a narrative essay or a reasoning trace by another name.
QUESTION_MIN_CHARS = 20
QUESTION_MAX_CHARS = 320

MAX_HYPOTHESES = 12
MAX_TARGET_METRICS = 6
MAX_CONDITIONS = 5
MAX_EVIDENCE_REFS = 12
MAX_CONFOUNDERS = 6
MAX_REQUIRED_CAPABILITIES = 6


def _condition_item() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["dimension", "value"],
        "properties": {
            "dimension": {"type": "string", "enum": vocabulary.dimension_names()},
            "value": {"type": "string"},
            # Only meaningful for `opponent_profile`; the compiler requires it there and
            # rejects it elsewhere (a cross-field rule the schema cannot express).
            "axis": {"type": "string", "enum": list(vocabulary.PROFILE_AXES)},
        },
    }


def _hypothesis_item() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "hypothesis_id", "research_family", "subject", "question",
            "target_metrics", "side", "window", "conditions", "comparison",
            "evidence_refs", "candidate_confounders", "required_capabilities",
            "sufficiency", "priority",
        ],
        "properties": {
            "hypothesis_id": {"type": "string", "pattern": r"^H[0-9]{1,3}$"},
            "research_family": {"type": "string",
                                "enum": list(vocabulary.RESEARCH_FAMILIES)},
            "subject": {"type": "string",
                        "enum": list(vocabulary.SUBJECTS) + list(vocabulary.SUBJECT_ALIASES)},
            "question": {"type": "string",
                         "minLength": QUESTION_MIN_CHARS,
                         "maxLength": QUESTION_MAX_CHARS},
            "target_metrics": {
                "type": "array", "minItems": 1, "maxItems": MAX_TARGET_METRICS,
                "items": {"type": "string", "enum": capability.metric_names()},
            },
            "side": {"type": "string", "enum": list(vocabulary.SIDES)},
            "window": {"type": "string", "enum": list(vocabulary.WINDOWS)},
            "conditions": {
                "type": "array", "minItems": 0, "maxItems": MAX_CONDITIONS,
                "items": _condition_item(),
            },
            "comparison": {"type": "string", "enum": list(vocabulary.COMPARISONS)},
            "evidence_refs": {
                "type": "array", "minItems": 0, "maxItems": MAX_EVIDENCE_REFS,
                "items": {"type": "string"},
            },
            "candidate_confounders": {
                "type": "array", "minItems": 0, "maxItems": MAX_CONFOUNDERS,
                "items": {"type": "string"},
            },
            "required_capabilities": {
                "type": "array", "minItems": 0, "maxItems": MAX_REQUIRED_CAPABILITIES,
                "items": {"type": "string",
                          "enum": sorted(capability.CONTEXT_SOURCES)},
            },
            "sufficiency": {"type": "string", "enum": list(vocabulary.SUFFICIENCY)},
            "priority": {"type": "string", "enum": list(vocabulary.PRIORITY)},
        },
    }


def build_schema() -> dict:
    """The Bedrock tool input schema AND the deterministic validator's schema."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["fixture_id", "packet_hash", "hypotheses"],
        "properties": {
            "fixture_id": {"type": "string"},
            # Binds the response to the exact evidence that produced it. A response whose
            # packet_hash does not match the packet actually sent is unusable as a
            # research record, so the validator rejects it.
            "packet_hash": {"type": "string", "pattern": r"^[0-9a-f]{64}$"},
            "hypotheses": {
                "type": "array", "minItems": 0, "maxItems": MAX_HYPOTHESES,
                "items": _hypothesis_item(),
            },
        },
    }


def schema_content_hash() -> str:
    return hashlib.sha256(
        json.dumps(build_schema(), sort_keys=True).encode()).hexdigest()


def version_stamp() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "schema_content_hash": schema_content_hash(),
        "vocabulary_version": vocabulary.VOCABULARY_VERSION,
        "capability_inventory_version": capability.CAPABILITY_INVENTORY_VERSION,
    }
