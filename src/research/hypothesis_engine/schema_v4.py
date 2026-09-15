"""`hypothesis_set_schema_v4` -- the V6 output contract, split so one item can fail alone.

TWO CHANGES FROM `schema_v3`, AND NOTHING ELSE
----------------------------------------------
C1 -- THE SPLIT (§3). `schema_v3.build_schema()` is a WHOLE-DOCUMENT schema, and
`validator_v4` validates the whole payload against it in one call:

    errs = validator.validate_schema_against(schema_v3.build_schema(), canon)
    if errs:
        return ValidationResultV4(False, lifecycle.SCHEMA_INVALID, errs, ...)

One bad enum in `hypotheses[7]` fails the `hypotheses` array, fails the document, and
returns a whole-response rejection -- no matter how the caller loops afterwards. Structuring
the loop differently cannot fix it; the SCHEMA has to be split.

    envelope_schema()          fixture_id + packet_hash + `hypotheses` is an array of
                               OBJECTS. Nothing about their contents. Failing this is the
                               only structural condition from which individual hypotheses
                               cannot be recovered, and it is the sole source of
                               RESPONSE_PARSE_FATAL.
    hypothesis_item_schema()   the full closed item contract, applied to ONE element.

The composed `build_schema()` is retained and is still what the Bedrock tool spec sends:
the model must be shown the complete contract. What changed is how a RESPONSE is judged,
not what the model is asked for. `test_v6_composed_schema_equals_v3_plus_evidence_summary`
asserts the two stay in step.

C2 -- `evidence_summary` (§4). One OPTIONAL bounded free-text field per hypothesis, whose
contract permits a packet-supplied value to be reproduced under `firewall_v5`'s frame rule.

`firewall_v2`'s own docstring names the absence of this field as the real defect:

    "This is still a discipline breach ... but it is bucketed separately, because the fix
     is ARCHITECTURAL (give the model a structural evidence reference) rather than a
     matter of the model claiming authority it does not have."

V5A.2 had `question` as its only free-text field, so the single legitimate reason to write
a number and the single illegitimate one shared one surface and had to share one verdict.
Now they do not. The field is OPTIONAL: a model that never needs to reproduce a value is
not pushed into writing one, and §16's "do not require citation volume for its own sake"
applies to reproduced values as much as to ids.

`schema.py`, `schema_v2.py` and `schema_v3.py` ARE NOT EDITED. Their content hashes are in
the frozen V2/V3/V5A/V5A.1/V5A.2 preregistrations.

ZERO SPEND.
"""
from __future__ import annotations

import copy
import hashlib
import json

from . import capability, schema as schema_v1, schema_v2, schema_v3, vocabulary

SCHEMA_VERSION = "hypothesis_set_schema_v4"

QUESTION_MIN_CHARS = schema_v1.QUESTION_MIN_CHARS
QUESTION_MAX_CHARS = schema_v1.QUESTION_MAX_CHARS
MAX_HYPOTHESES = schema_v1.MAX_HYPOTHESES
MAX_CONDITIONS = schema_v1.MAX_CONDITIONS
MAX_REQUIRED_CAPABILITIES = schema_v1.MAX_REQUIRED_CAPABILITIES

#: Bounded hard enough that the field cannot become a reasoning trace by another name --
#: the discipline `schema.py` inherited from the legacy contract and gives as its reason
#: for having no `analysis_notes` field. Long enough to state what one or two cited records
#: contain, which is all it is for.
EVIDENCE_SUMMARY_MAX_CHARS = 400
EVIDENCE_SUMMARY_FIELD = "evidence_summary"


def hypothesis_item_schema() -> dict:
    """The closed contract for ONE hypothesis. `schema_v3`'s item, plus `evidence_summary`.

    Built by deepcopy from `schema_v3.build_schema()` so the ontology-projected enums
    (`conditions[].dimension`, `required_capabilities`) are the SAME objects V5A.2 froze,
    reached by the same call. No enum is restated here and none may be.
    """
    item = copy.deepcopy(schema_v3.build_schema()["properties"]["hypotheses"]["items"])
    item["properties"][EVIDENCE_SUMMARY_FIELD] = {
        "type": "string",
        "maxLength": EVIDENCE_SUMMARY_MAX_CHARS,
        "description":
            "OPTIONAL. What the evidence you cited actually contains. This is the ONLY "
            "field in which a value the packet supplied may be written out, and only as a "
            "plain record of what was observed -- say what was recorded, cited or "
            "measured, and in which cohort. A number that is a claim about the upcoming "
            "fixture, or about any advantage, probability, price or effect, is forbidden "
            "here exactly as it is everywhere else.",
    }
    return item


def envelope_schema() -> dict:
    """The response skeleton: identity fields, and `hypotheses` is an array of objects.

    Says NOTHING about what is inside an element. That is the point -- failing this schema
    is the only condition under which individual hypotheses cannot be recovered reliably,
    which is exactly §3's definition of RESPONSE_FATAL.
    """
    doc = copy.deepcopy(schema_v3.build_schema())
    doc["properties"]["hypotheses"] = {
        "type": "array", "minItems": 0, "maxItems": MAX_HYPOTHESES,
        "items": {"type": "object"},
    }
    return doc


def build_schema() -> dict:
    """The composed contract. This is what the Bedrock tool spec carries.

    The model is shown the COMPLETE contract, item constraints and all. Splitting is how a
    RESPONSE is adjudicated, never a relaxation of what was asked for -- a model whose
    hypothesis is rejected here was shown the rule it broke.
    """
    doc = envelope_schema()
    doc["properties"]["hypotheses"]["items"] = hypothesis_item_schema()
    return doc


def schema_content_hash() -> str:
    return hashlib.sha256(json.dumps(build_schema(), sort_keys=True).encode()).hexdigest()


def envelope_content_hash() -> str:
    return hashlib.sha256(
        json.dumps(envelope_schema(), sort_keys=True).encode()).hexdigest()


def item_content_hash() -> str:
    return hashlib.sha256(
        json.dumps(hypothesis_item_schema(), sort_keys=True).encode()).hexdigest()


def diff_against_v3() -> dict:
    """Every key path on which v4's composed schema differs from v3's. Audited, not assumed.

    `test_v6_composed_schema_equals_v3_plus_evidence_summary` asserts this returns exactly
    the one expected addition, so a future edit that quietly widens an enum or drops a
    bound cannot pass unnoticed.
    """
    v3 = schema_v3.build_schema()
    v4 = build_schema()
    v4_stripped = copy.deepcopy(v4)
    v4_stripped["properties"]["hypotheses"]["items"]["properties"].pop(
        EVIDENCE_SUMMARY_FIELD, None)
    return {
        "identical_after_removing_evidence_summary": v4_stripped == v3,
        "added_item_properties": [EVIDENCE_SUMMARY_FIELD],
        "removed_item_properties": sorted(
            set(v3["properties"]["hypotheses"]["items"]["properties"])
            - set(v4["properties"]["hypotheses"]["items"]["properties"])),
        "required_unchanged": (v3["properties"]["hypotheses"]["items"]["required"]
                               == v4["properties"]["hypotheses"]["items"]["required"]),
        "evidence_summary_is_optional":
            EVIDENCE_SUMMARY_FIELD
            not in v4["properties"]["hypotheses"]["items"]["required"],
    }


def version_stamp() -> dict:
    from src.research.hypothesis_oos import v5a2_contract as C
    from src.research.hypothesis_oos import v5a2_ontology as O
    return {
        "schema_version": SCHEMA_VERSION,
        "schema_content_hash": schema_content_hash(),
        "envelope_content_hash": envelope_content_hash(),
        "item_content_hash": item_content_hash(),
        "evidence_summary_max_chars": EVIDENCE_SUMMARY_MAX_CHARS,
        "condition_contract_version": C.CONTRACT_VERSION,
        "ontology_version": O.ONTOLOGY_VERSION,
        "vocabulary_version": vocabulary.VOCABULARY_VERSION,
        "capability_inventory_version": capability.CAPABILITY_INVENTORY_VERSION,
        "frozen_predecessor_schema_v2_hash": schema_v2.schema_content_hash(),
        "frozen_predecessor_schema_v3_hash": schema_v3.schema_content_hash(),
    }
