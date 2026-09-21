"""ITEM 6 Stage-1 canonical Converse request builder + per-request byte budget (B1/B4).

`item6_request_builder_v1`. ZERO SPEND. Importing this module makes no network call.

WHAT THIS BINDS
The exact model-facing request is composed from FROZEN, byte-checked material:

  * system text   = the exact PROMPT_BODY region of the immutable ITEM6_MECHANISM_PROMPT_V1.md
                    (bound by its committed sha256; extracted verbatim, never paraphrased);
  * toolConfig    = a single forced tool whose inputSchema encodes the frozen
                    ITEM6_MECHANISM_SCHEMA_V1 response contract (K=5 mechanisms or abstention);
  * inferenceConfig = the deterministic settings used by the prior controlled Sonnet
                    experiments (temperature 0.0, topP 1.0, maxTokens 8192);
  * per-fixture   = the frozen fixture identity from the immutable Stage-1 cohort manifest
                    plus the point-in-time-safe evidence packet materialized at live time.

WHY A BYTE BUDGET INSTEAD OF A PRE-MATERIALIZED PACKET
The frozen Item 6 apparatus deliberately does NOT contain an evidence-packet builder (adding
one would be a scientific-input change, which this amendment must not make). The neutralized
pre-target packet is therefore materialized by the live pipeline at run time. To keep the
monetary guarantee valid WITHOUT that builder, every request carries a FROZEN hard ceiling
`MAX_REQUEST_UTF8_BYTES` on the total canonical request. The runner REFUSES to transmit any
fixture whose materialized request exceeds the budget (REQUEST_INTEGRITY_FAILURE). Because the
input-token upper bound is the UTF-8 byte length of the canonical request (see
v6_token_count), bounding the bytes bounds the billable input tokens, so the pre-call
reservation provably cannot understate. See `reservation_input_token_bound()`.

The skeleton request (system + tool schema + inference config + fixture identity, with an
EMPTY packet placeholder) is fully determined now and is what the frozen request-set binds
and hashes; the byte budget is what makes the yet-unmaterialized packet safe.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from src.research.item6 import schema as ITEM6_SCHEMA

REQUEST_BUILDER_VERSION = "item6_request_builder_v1"

# Frozen inference settings (deterministic; identical to the prior controlled Sonnet runs).
MODEL_PROFILE_ID = "us.anthropic.claude-sonnet-4-6"
BASE_MODEL_ID = "anthropic.claude-sonnet-4-6"
REGION = "us-east-1"
MAX_TOKENS = 8192
TEMPERATURE = 0.0
TOP_P_DECLARED = 1.0          # declared value
# topP is NOT placed on the wire: at temperature 0.0 sampling is greedy/deterministic and
# topP=1.0 is a no-op, so the Converse inferenceConfig carries only temperature + maxTokens,
# exactly as the frozen canonical request below shows. Both states are recorded explicitly.
TOP_P_ON_WIRE = None

TOOL_NAME = "emit_item6_mechanisms"

# Hard per-request UTF-8 byte ceiling. The skeleton (empty packet) is ~8 KB; the frozen
# power/cost artifact estimates a realistic per-fixture input of ~6,500 tokens (P90 ~9,000).
# 32768 bytes (32 KiB) is a deliberately generous ceiling: it dominates every realistic
# materialized packet (roughly 4-5x the estimated input) yet keeps the enforced monetary
# reservation sane. Because input tokens <= request UTF-8 bytes (byte-level BPE, see
# v6_token_count proof), this byte ceiling is ALSO the per-call input-token upper bound used
# for the pre-call reservation. The runner refuses to transmit any request exceeding it
# (REQUEST_INTEGRITY_FAILURE) rather than under-reserving, so the bound cannot be silently
# breached. Loose in the SAFE direction is what a hard bound requires; a future authorizer
# may re-freeze this ceiling (and the request set + run manifest) if packets prove larger.
MAX_REQUEST_UTF8_BYTES = 32768

ITEM6_PROMPT_PATH = "research/item6/ITEM6_MECHANISM_PROMPT_V1.md"
# committed sha256 of the immutable prompt file (verified before use; binds the system text).
ITEM6_PROMPT_SHA256 = "36b98540db4beb4ee8f7c70f919a179019f450ec3ebce96d9a28b50f95e171f0"

_PROMPT_BODY_START = "<!-- PROMPT_BODY_START"
_PROMPT_BODY_END = "<!-- PROMPT_BODY_END"


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_frozen_system_text(root: str = "/home/ubuntu") -> str:
    """Extract the exact PROMPT_BODY region from the immutable prompt file, after verifying
    the file's committed sha256. Raises if the prompt file has drifted (fail closed)."""
    path = f"{root}/{ITEM6_PROMPT_PATH}"
    with open(path, "rb") as f:
        raw = f.read()
    actual = _sha256_bytes(raw)
    if actual != ITEM6_PROMPT_SHA256:
        raise RuntimeError(
            f"ITEM6 prompt hash drift: expected {ITEM6_PROMPT_SHA256} got {actual}")
    txt = raw.decode("utf-8")
    start = txt.index(_PROMPT_BODY_START)
    start_end = txt.index("-->", start) + 3
    end = txt.index(_PROMPT_BODY_END, start_end)
    return txt[start_end:end]


def build_tool_schema() -> Dict[str, Any]:
    """A JSON Schema encoding the frozen mechanism-response contract. It is DERIVED from the
    frozen schema constants (required fields, K, abstention token, forbidden keys) so it can
    never silently diverge from `src/research/item6/schema.py`. It adds NO scientific field."""
    mech_props = {
        "mechanism_id_local": {"type": "string"},
        "mechanism_statement": {"type": "string"},
        "observable_variables": {"type": "array", "items": {"type": "string"},
                                 "minItems": 1},
        "conditioning_logic": {"type": "string"},
        "expected_relationship_to_test": {"type": "string"},
        "why_not_baseline_equivalent": {"type": "string"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "data_resolution_required": {"type": "string", "enum": ["match", "half"]},
        "provider_requirements": {"type": "array", "items": {"type": "string"}},
        "self_overlap_with": {"type": "array", "items": {"type": "string"}},
    }
    assert set(mech_props) == set(ITEM6_SCHEMA.REQUIRED_MECHANISM_FIELDS), \
        "tool schema fields must equal the frozen required mechanism fields"
    return {
        "type": "object",
        "properties": {
            "fixture_id": {"type": "string"},
            "abstention": {"type": "string",
                           "enum": [ITEM6_SCHEMA.ABSTENTION_TOKEN]},
            "mechanisms": {
                "type": "array",
                "maxItems": ITEM6_SCHEMA.K_MECHANISMS_PER_FIXTURE,
                "items": {
                    "type": "object",
                    "properties": mech_props,
                    "required": list(ITEM6_SCHEMA.REQUIRED_MECHANISM_FIELDS),
                    "additionalProperties": False,
                },
            },
        },
        "required": ["fixture_id", "mechanisms"],
        "additionalProperties": False,
    }


def tool_config() -> Dict[str, Any]:
    """The forced-tool Converse toolConfig for Item 6 mechanism discovery."""
    return {
        "tools": [{"toolSpec": {
            "name": TOOL_NAME,
            "description": ("Return the fixture's discovered mechanisms (or an explicit "
                            "abstention) per the frozen Item 6 mechanism schema."),
            "inputSchema": {"json": build_tool_schema()}}}],
        "toolChoice": {"tool": {"name": TOOL_NAME}},
    }


def canonical_bytes(obj: Any) -> bytes:
    """Frozen canonical serialization: UTF-8, sorted keys, tight separators, no NaN.
    Deterministic and independent of dict insertion order / PYTHONHASHSEED."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def build_user_payload(fixture: Dict[str, Any],
                       evidence_packet: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The user-turn content. Fixture identity comes from the frozen cohort manifest; the
    point-in-time-safe evidence packet is supplied by the live pipeline (None -> empty
    skeleton placeholder, used for the frozen request-set binding)."""
    return {
        "fixture_id": fixture["fixture_id"],
        "fixture_identity": {
            "home_id": fixture.get("home_id"),
            "away_id": fixture.get("away_id"),
            "competition": fixture.get("competition"),
            "kickoff_unix": fixture.get("kickoff_unix"),
        },
        "evidence_packet": evidence_packet if evidence_packet is not None else {},
    }


def canonical_request(fixture: Dict[str, Any], system_text: str,
                      evidence_packet: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The ONE authoritative Converse request. Accounting hashes this; the driver sends it.

    inferenceConfig carries temperature + maxTokens only (topP is a no-op at temp 0 and is
    deliberately omitted from the wire; see TOP_P_ON_WIRE)."""
    return {
        "modelId": MODEL_PROFILE_ID,
        "system": [{"text": system_text}],
        "messages": [{"role": "user", "content": [{"text": json.dumps(
            build_user_payload(fixture, evidence_packet),
            sort_keys=True, separators=(",", ":"), ensure_ascii=False)}]}],
        "inferenceConfig": {"temperature": TEMPERATURE, "maxTokens": MAX_TOKENS},
        "toolConfig": tool_config(),
    }


def request_sha256(request: Dict[str, Any]) -> str:
    return _sha256_bytes(canonical_bytes(request))


def request_byte_len(request: Dict[str, Any]) -> int:
    return len(canonical_bytes(request))


def reservation_input_token_bound(request: Dict[str, Any]) -> int:
    """Conservative input-token upper bound for the monetary reservation.

    For the ACTUAL live request we bound input tokens by the request's own canonical UTF-8
    byte length (byte-level BPE => tokens <= bytes; see v6_token_count proof). But the
    RESERVATION must be computed BEFORE the packet is materialized, so the runner reserves
    against the frozen ceiling MAX_REQUEST_UTF8_BYTES and refuses to transmit anything larger.
    We therefore return the frozen ceiling here: it dominates the true byte length of every
    admissible request and so can never understate the billable input tokens."""
    return MAX_REQUEST_UTF8_BYTES


def within_byte_budget(request: Dict[str, Any]) -> bool:
    return request_byte_len(request) <= MAX_REQUEST_UTF8_BYTES


def version_stamp() -> Dict[str, Any]:
    return {
        "request_builder_version": REQUEST_BUILDER_VERSION,
        "model_profile_id": MODEL_PROFILE_ID,
        "base_model_id": BASE_MODEL_ID,
        "region": REGION,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "top_p_declared": TOP_P_DECLARED,
        "top_p_on_wire": TOP_P_ON_WIRE,
        "tool_name": TOOL_NAME,
        "max_request_utf8_bytes": MAX_REQUEST_UTF8_BYTES,
        "prompt_sha256": ITEM6_PROMPT_SHA256,
        "input_token_bound_method": "utf8_byte_upper_bound_over_canonical_request_capped_at_max_request_bytes",
        "output_token_reservation_method": "frozen_max_tokens_always",
    }
