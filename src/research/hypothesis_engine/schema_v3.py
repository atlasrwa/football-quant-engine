"""`hypothesis_set_schema_v3` -- the V5A.2 output contract.

Exactly two things change from `schema_v2`, and together they close D1:

    v2:  conditions[].dimension    enum <- vocabulary.dimension_names()
         required_capabilities     enum <- sorted(capability.CONTEXT_SOURCES)
                                   ^^ two disjoint namespaces, neither of them the one the
                                      packet advertises. `opponent_profile` was legal in
                                      the first and illegal in the second, whose correct
                                      token for it was `competition`.

    v3:  conditions[].dimension    enum <- v5a2_ontology.condition_dimension_terms()
         required_capabilities     enum <- v5a2_ontology.capability_terms()
                                   ^^ ONE namespace, and it is the same one the packet's
                                      availability map declares.

NO ENUM IS DECLARED HERE. Both come from `v5a2_ontology` by function call, so
`test_schema_enums_are_the_ontology` can assert identity rather than equality of content
and a hand-edited third copy cannot appear.

`schema.py` and `schema_v2.py` ARE NOT EDITED and remain byte-identical: their content
hashes are recorded in the frozen V2, V3 and V5A preregistrations, and those experiments
must stay exactly reproducible from the code that produced them. V3 continues to use v2.
"""
from __future__ import annotations

import copy
import hashlib
import json

from . import capability, schema as schema_v1, schema_v2, vocabulary

SCHEMA_VERSION = "hypothesis_set_schema_v3"

QUESTION_MIN_CHARS = schema_v1.QUESTION_MIN_CHARS
QUESTION_MAX_CHARS = schema_v1.QUESTION_MAX_CHARS
MAX_HYPOTHESES = schema_v1.MAX_HYPOTHESES
MAX_CONDITIONS = schema_v1.MAX_CONDITIONS
MAX_REQUIRED_CAPABILITIES = schema_v1.MAX_REQUIRED_CAPABILITIES


def build_schema() -> dict:
    """The Bedrock tool input schema AND the deterministic validator's schema."""
    from src.research.hypothesis_oos import v5a2_contract as C
    from src.research.hypothesis_oos import v5a2_ontology as O

    doc = copy.deepcopy(schema_v1.build_schema())
    item = doc["properties"]["hypotheses"]["items"]
    item["properties"]["conditions"]["items"] = C.condition_schema()
    item["properties"]["required_capabilities"]["items"] = {
        "type": "string", "enum": O.capability_terms()}
    return doc


def schema_content_hash() -> str:
    return hashlib.sha256(json.dumps(build_schema(), sort_keys=True).encode()).hexdigest()


def version_stamp() -> dict:
    from src.research.hypothesis_oos import v5a2_contract as C
    from src.research.hypothesis_oos import v5a2_ontology as O
    return {
        "schema_version": SCHEMA_VERSION,
        "schema_content_hash": schema_content_hash(),
        "condition_contract_version": C.CONTRACT_VERSION,
        "ontology_version": O.ONTOLOGY_VERSION,
        "vocabulary_version": vocabulary.VOCABULARY_VERSION,
        "capability_inventory_version": capability.CAPABILITY_INVENTORY_VERSION,
        "frozen_predecessor_schema_v2_hash": schema_v2.schema_content_hash(),
    }
