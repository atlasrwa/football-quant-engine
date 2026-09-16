"""Tests for the V8B.1 prompt + tool schemas. The central claim under test: the numerical
firewall is STRUCTURAL (no field of type number/integer exists anywhere in
submit_selections_input_schema()), not merely a prompt instruction the model could ignore.
"""
from __future__ import annotations

import json

from src.research.hypothesis_v8b1 import prompt as PR


def _walk_types(schema, found):
    if isinstance(schema, dict):
        t = schema.get("type")
        if t is not None:
            found.add(t if isinstance(t, str) else tuple(t))
        for v in schema.values():
            _walk_types(v, found)
    elif isinstance(schema, list):
        for v in schema:
            _walk_types(v, found)


def test_submit_selections_schema_has_no_numeric_field_anywhere():
    """Structural numerical firewall: walk the ENTIRE submit_selections schema tree and
    confirm no subschema declares type 'number' or 'integer'."""
    schema = PR.submit_selections_input_schema()
    types_found = set()
    _walk_types(schema, types_found)
    assert "number" not in types_found
    assert "integer" not in types_found


def test_search_tool_schema_MAY_use_integer_but_only_for_bounded_pagination():
    """The search tool's own inputs may legitimately be integers (max_conditions,
    max_results) -- these are QUERY parameters, never a hypothesis's numeric effect. Confirm
    they are bounded (minimum/maximum present) rather than open-ended."""
    schema = PR._search_tool_input_schema()
    for field in ("max_conditions", "max_results"):
        prop = schema["properties"][field]
        assert prop["type"] == "integer"
        assert "minimum" in prop and "maximum" in prop


def test_selection_item_requires_hypothesis_id_shaped_like_a_real_ir_id():
    schema = PR._selection_item_schema()
    assert schema["properties"]["hypothesis_id"]["pattern"] == r"^[0-9a-f]{64}$"
    assert "additionalProperties" in schema and schema["additionalProperties"] is False


def test_max_selections_is_eight_and_zero_is_valid():
    schema = PR.submit_selections_input_schema()
    sel = schema["properties"]["final_selections"]
    assert sel["minItems"] == 0
    assert sel["maxItems"] == PR.MAX_SELECTIONS == 8


def test_all_objects_are_closed_additionalProperties_false():
    """Every object-typed subschema must be closed -- mirrors the discipline already audited
    in hypothesis_engine/schema.py."""
    schema = PR.submit_selections_input_schema()

    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False, f"unclosed object: {node}"
            for v in node.values():
                check(v)
        elif isinstance(node, list):
            for v in node:
                check(v)
    check(schema)


def test_prompt_content_hash_is_deterministic():
    assert PR.prompt_content_hash() == PR.prompt_content_hash()


def test_tool_specs_are_valid_json_serializable():
    specs = PR.tool_specs()
    assert len(specs) == 2
    assert {s["name"] for s in specs} == {"search_hypotheses", "submit_selections"}
    json.dumps(specs)  # must not raise


def test_version_stamp_declares_structural_firewall():
    stamp = PR.version_stamp()
    assert stamp["numerical_firewall"].startswith("structural")
    assert stamp["abstention_is_valid"] is True
    assert stamp["hypothesis_id_must_be_search_returned"] is True
