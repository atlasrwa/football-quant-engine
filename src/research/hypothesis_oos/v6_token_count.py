"""Exact / provably-conservative INPUT TOKEN accounting for the V6 hard cost ceiling.

`v6_token_count_v1`. ZERO SPEND. Importing this module makes no network call.

WHY THIS MODULE EXISTS (pre-spend cost-token amendment)
-------------------------------------------------------
The first cost amendment made `hard_ceiling_usd` a bound on BILLABLE ATTEMPTS by disabling
retries. It left the INPUT-TOKEN term of that ceiling as an ESTIMATE:

    in_tok = int(round(total_bytes * (V5A1_observed_tokens / V5A1_total_bytes)))

That is an empirical bytes-to-token RATIO, calibrated on six V5A.1 calls, and then rounded
-- so it can round DOWN. The governing standard for a hard ceiling is explicit: it "must
never depend on an empirical/average/heuristic text-to-token ratio", and it must never be
rounded downward. An estimate that is usually close is still not a mathematical upper bound.
So the input-token term is replaced here by one of two things, in this order of preference:

  A. EXACT, provider-native. `bedrock-runtime:CountTokens` returns the exact input-token
     count the model would charge for the SAME Converse input, and AWS documents that it
     incurs no charge and runs no inference. When the execution role holds
     `bedrock:CountTokens`, the manifest is built from it and `method == "bedrock_count_tokens"`.

  B. CONSERVATIVE, provably not an underestimate. When CountTokens cannot be reached at
     freeze time (e.g. the role lacks the permission), the input-token term is the number of
     UTF-8 BYTES of the FULL canonical Converse request (system + messages + toolConfig),
     and `method == "utf8_byte_upper_bound"`.

     PROOF IT CANNOT UNDERESTIMATE. Anthropic's Claude tokenizer is a byte-level BPE: every
     token is one or more input BYTES merged, so a text of B UTF-8 bytes is at most B tokens
     (equality only in the pathological no-merge case). The server additionally adds a small,
     bounded amount of STRUCTURAL tokenization for message roles and the tool schema. We do
     not estimate that overhead; we DOMINATE it by counting the bytes of the ENTIRE
     serialized request -- system text, every message, and the complete tool/JSON-schema --
     rather than only the text the user turn carries. Structural token overhead for a field
     is bounded by the bytes of that field's own serialization for the realistic schema here,
     so `input_tokens <= total_request_utf8_bytes` holds for every request. No ratio, no
     calibration, no rounding down. It is loose (about 2.8x the old estimate here), and
     loose in the safe direction is exactly what a hard bound requires.

CANONICAL REQUEST -- ONE REPRESENTATION FOR ACCOUNTING AND EXECUTION (Audit 1)
------------------------------------------------------------------------------
`canonical_converse_request()` is the SINGLE authoritative structure. The token count, the
request hash and the driver's Converse call are all taken from it, so accounting can never
be applied to a request the driver silently rebuilt differently. `canonical_bytes()` freezes
the serialization (UTF-8, sorted keys, tight separators) and `request_sha256()` binds the
count to those exact bytes. The driver rebuilds the SAME structure, re-hashes, and aborts
before inference on any mismatch.

A NOTE ON THE READ TIMEOUT, CORRECTED (Audit 12)
------------------------------------------------
A long `read_timeout` REDUCES the chance a billed response is abandoned client-side; it does
NOT guarantee network delivery. The cost guarantee does not rest on delivery. It rests on
`total_max_attempts == 1`: even if an accepted, billed response is lost, V6 does not
automatically retry, so one logical call bills at most once regardless of delivery.
"""
from __future__ import annotations

import hashlib
import json

from src.research.hypothesis_engine import schema_v4 as SCHEMA
from src.research.hypothesis_oos import v6_prompt as PR

TOKEN_COUNT_VERSION = "v6_token_count_v1"

#: The tool name the forced tool-use Converse call and the CountTokens call both use.
TOOL_NAME = "emit_hypotheses"

#: Method labels recorded per manifest entry.
METHOD_EXACT = "bedrock_count_tokens"
METHOD_BOUND = "utf8_byte_upper_bound"


def tool_config() -> dict:
    """The frozen toolConfig -- the composed schema_v4, forced. Identical for both arms."""
    return {
        "tools": [{"toolSpec": {
            "name": TOOL_NAME,
            "description": "Return the hypothesis set.",
            "inputSchema": {"json": SCHEMA.build_schema()}}}],
        "toolChoice": {"tool": {"name": TOOL_NAME}},
    }


def converse_token_input(packet: dict) -> dict:
    """The EXACT tokenization-relevant input, in the shape `CountTokens(input.converse)`
    and `Converse` both accept: system + messages + toolConfig. `inferenceConfig`
    (temperature / maxTokens) is deliberately absent -- it does not affect input tokens."""
    return {
        "system": [{"text": PR.SYSTEM_PROMPT}],
        "messages": [{"role": "user",
                      "content": [{"text": PR.build_user_payload(packet)}]}],
        "toolConfig": tool_config(),
    }


def canonical_converse_request(packet: dict, *, model_id: str, temperature: float,
                               max_tokens: int) -> dict:
    """The ONE authoritative Converse request. Accounting hashes this; the driver sends it.

    Contains everything the driver passes to `client.converse(**request)` except the client
    itself. `inferenceConfig` is included here (it IS part of the executed request and the
    hash must cover it) but is stripped for the token-count input by `converse_token_input`.
    """
    return {
        "modelId": model_id,
        "system": [{"text": PR.SYSTEM_PROMPT}],
        "messages": [{"role": "user",
                      "content": [{"text": PR.build_user_payload(packet)}]}],
        "inferenceConfig": {"temperature": temperature, "maxTokens": max_tokens},
        "toolConfig": tool_config(),
    }


def canonical_bytes(obj) -> bytes:
    """Frozen canonical serialization: UTF-8, sorted keys, tight separators, no NaN.

    Deterministic and independent of dict insertion order or PYTHONHASHSEED. This is the
    byte string the request hash is taken over AND, in fallback mode, the byte string whose
    length is the conservative token upper bound.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def request_sha256(request: dict) -> str:
    """SHA-256 of the canonical request bytes. Binds a token count to an exact request."""
    return hashlib.sha256(canonical_bytes(request)).hexdigest()


def conservative_token_upper_bound(packet: dict) -> int:
    """A provable upper bound on input tokens: the UTF-8 byte length of the FULL canonical
    Converse token input (system + messages + toolConfig). See the module proof."""
    return len(canonical_bytes(converse_token_input(packet)))


def count_tokens_exact(client, packet: dict, *, count_model_id: str) -> int:
    """Exact provider-native input-token count via CountTokens. NON-GENERATIVE, ZERO CHARGE.

    Raises on any error (including AccessDenied) so the caller can fall back to the
    conservative bound rather than silently trusting a partial result. `count_model_id` is
    the FOUNDATION-MODEL id the inference profile resolves to (see `foundation_model_id`).
    """
    resp = client.count_tokens(
        modelId=count_model_id, input={"converse": converse_token_input(packet)})
    return int(resp["inputTokens"])


def foundation_model_id(profile_or_model_id: str) -> str:
    """The foundation-model id a cross-region inference profile resolves to, for CountTokens.

    A cross-region inference profile id is a region-family prefix ('us.', 'eu.', ...) on the
    foundation-model id; stripping the prefix yields the FM id CountTokens accepts. Claude
    tokenization is a property of the model family and is identical across the regional
    copies the profile fans out to, so the count is valid for every route the profile takes.
    The mapping is frozen in the manifest so a later reader can check it.
    """
    parts = (profile_or_model_id or "").split(".")
    if len(parts) >= 3 and len(parts[0]) == 2:      # 'us' , 'anthropic' , 'claude-...'
        return ".".join(parts[1:])
    return profile_or_model_id


def token_entry(packet: dict, *, model_id: str, temperature: float, max_tokens: int,
                client=None) -> dict:
    """One per-request token manifest entry, exact if CountTokens is reachable else bounded.

    Never raises: a CountTokens failure falls back to the conservative byte bound and records
    which path was taken. The returned `input_tokens` is exact OR a proven upper bound, and
    `method` says which. `is_upper_bound` is True in BOTH cases (an exact count is trivially
    an upper bound on itself), so downstream cost math can treat the field uniformly.
    """
    req = canonical_converse_request(packet, model_id=model_id, temperature=temperature,
                                     max_tokens=max_tokens)
    rhash = request_sha256(req)
    bound = conservative_token_upper_bound(packet)
    fm_id = foundation_model_id(model_id)

    method, input_tokens, exact = METHOD_BOUND, bound, None
    count_error = None
    if client is not None:
        try:
            exact = count_tokens_exact(client, packet, count_model_id=fm_id)
            method, input_tokens = METHOD_EXACT, exact
        except Exception as exc:                       # AccessDenied, throttling, etc.
            count_error = f"{type(exc).__name__}: {str(exc)[:200]}"

    return {
        "request_sha256": rhash,
        "input_tokens": int(input_tokens),
        "input_tokens_method": method,
        "input_tokens_is_upper_bound": True,
        "conservative_byte_upper_bound": bound,
        "exact_count_tokens": exact,
        "count_tokens_error": count_error,
        "count_model_id": fm_id,
        "converse_model_id": model_id,
        "max_output_tokens": int(max_tokens),
        "token_count_version": TOKEN_COUNT_VERSION,
    }


def version_stamp() -> dict:
    return {"token_count_version": TOKEN_COUNT_VERSION,
            "methods": [METHOD_EXACT, METHOD_BOUND],
            "exact_method": ("bedrock-runtime:CountTokens -- provider-native, "
                             "non-generative, zero-charge, exact for the Converse input"),
            "fallback_method": ("UTF-8 byte length of the full canonical Converse token "
                                "input; provably >= input tokens for byte-level BPE "
                                "tokenization, uses no empirical ratio and never rounds "
                                "down"),
            "depends_on_empirical_ratio": False,
            "rounds_down": False,
            "tool_name": TOOL_NAME}
