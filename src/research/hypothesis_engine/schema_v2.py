"""`hypothesis_set_schema_v2` -- the V3 output contract.

Exactly one thing changes from `hypothesis_set_schema_v1`, and it is the change that makes
the V2 encoding defect impossible:

    v1:  "value": {"type": "string"}                      # free string
    v2:  "value": <closed enum, narrowed per dimension>   # projected from the contract

plus the cross-field rule the v1 schema could not express and the compiler enforced alone:
`axis` is REQUIRED for a dimension that declares axes (`opponent_profile`) and FORBIDDEN
for one that does not.

NO ENUM IS DECLARED HERE. Every enum is taken from `condition_contract`, which in turn
projects `vocabulary.DIMENSIONS`. The rest of the document is taken verbatim from
`schema.build_schema()`, so the two versions cannot drift on anything except the condition
contract itself.

v1 IS LEFT BYTE-IDENTICAL AND STILL IMPORTED BY THE FROZEN V2 PIPELINE. `schema.py` is not
edited: `SONNET46_HYPOTHESIS_V2` is a permanently frozen FAIL and its artifacts must remain
exactly reproducible from the code that produced them.
"""
from __future__ import annotations

import copy
import hashlib
import json

from . import capability, condition_contract, schema as schema_v1, vocabulary

SCHEMA_VERSION = "hypothesis_set_schema_v2"

# Re-exported so callers never have to reach across to v1 for a bound.
QUESTION_MIN_CHARS = schema_v1.QUESTION_MIN_CHARS
QUESTION_MAX_CHARS = schema_v1.QUESTION_MAX_CHARS
MAX_HYPOTHESES = schema_v1.MAX_HYPOTHESES
MAX_CONDITIONS = schema_v1.MAX_CONDITIONS


def build_schema() -> dict:
    """The Bedrock tool input schema AND the deterministic validator's schema."""
    doc = copy.deepcopy(schema_v1.build_schema())
    item = doc["properties"]["hypotheses"]["items"]
    item["properties"]["conditions"]["items"] = condition_contract.condition_schema()
    return doc


def schema_content_hash() -> str:
    return hashlib.sha256(
        json.dumps(build_schema(), sort_keys=True).encode()).hexdigest()


def version_stamp() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "schema_content_hash": schema_content_hash(),
        "condition_contract_version": condition_contract.CONTRACT_VERSION,
        "vocabulary_version": vocabulary.VOCABULARY_VERSION,
        "capability_inventory_version": capability.CAPABILITY_INVENTORY_VERSION,
    }
