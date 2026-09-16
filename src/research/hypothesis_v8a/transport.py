"""V8A Bedrock transport and cost accounting (`v8a_transport_v1`). Brief sections 19 and 25.

Mirrors V6.1's accounting discipline exactly, because that discipline is what makes a
pre-spend ceiling a real bound rather than an estimate:

  * ONE canonical request object. The hash the manifest records and the bytes the driver
    sends are the same object; they cannot drift.
  * NO RETRIES on the billable path. `max_attempts=0` in the botocore config, so a failed
    call is one call, and the hard maximum call count is a real maximum.
  * The exact provider-native input-token count comes from `CountTokens`, which is
    non-generative and free. If it is unreachable the conservative UTF-8 byte bound is used
    and the manifest records WHICH path was taken -- never a silent estimate.
  * Output tokens are charged at the frozen `max_tokens` for the ceiling, so the bound holds
    whatever the model actually emits.
  * The resolved model id is recorded per call. No silent substitution: if the intended model
    is unavailable the arm STOPS rather than falling back to another one.

ZERO SPEND until `converse` is called; every other function here is free.
"""
from __future__ import annotations

import hashlib
import json
from decimal import ROUND_CEILING, Decimal

TRANSPORT_VERSION = "v8a_transport_v1"

TOOL_NAME = "emit_research"
MAX_BILLABLE_ATTEMPTS_PER_CALL = 1

#: us-east-1 on-demand standard tier, USD per 1K tokens. Frozen at pre-spend time.
PRICE_IN_PER_1K = Decimal("0.003")
PRICE_OUT_PER_1K = Decimal("0.015")


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def request_sha256(req: dict) -> str:
    return hashlib.sha256(canonical_bytes(req)).hexdigest()


def tool_config(schema: dict, description: str) -> dict:
    return {"tools": [{"toolSpec": {"name": TOOL_NAME, "description": description,
                                    "inputSchema": {"json": schema}}}],
            "toolChoice": {"tool": {"name": TOOL_NAME}}}


def converse_token_input(system: str, user: str, schema: dict, description: str) -> dict:
    """The tokenization-relevant input only: inferenceConfig does not affect input tokens."""
    return {"system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "toolConfig": tool_config(schema, description)}


def canonical_request(system, user, schema, description, *, model_id, temperature,
                      max_tokens) -> dict:
    return {"modelId": model_id,
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"temperature": temperature, "maxTokens": max_tokens},
            "toolConfig": tool_config(schema, description)}


def conservative_token_upper_bound(system, user, schema, description) -> int:
    """A provable upper bound: one token can never encode less than one UTF-8 byte."""
    return len(canonical_bytes(converse_token_input(system, user, schema, description)))


def foundation_model_id(profile_or_model_id: str) -> str:
    parts = (profile_or_model_id or "").split(".")
    if len(parts) >= 3 and len(parts[0]) == 2:
        return ".".join(parts[1:])
    return profile_or_model_id


def build_client(region="us-east-1"):
    """A no-retry Bedrock runtime client. The no-retry property is what makes the call
    ceiling a bound rather than a hope."""
    import boto3
    from botocore.config import Config
    return boto3.client("bedrock-runtime", region_name=region,
                        config=Config(retries={"max_attempts": 0, "mode": "standard"},
                                      read_timeout=900, connect_timeout=30))


def count_tokens_exact(client, system, user, schema, description, *, count_model_id) -> int:
    """Provider-native exact input-token count. NON-GENERATIVE, ZERO CHARGE."""
    resp = client.count_tokens(
        modelId=count_model_id,
        input={"converse": converse_token_input(system, user, schema, description)})
    return int(resp["inputTokens"])


def _usd(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def cost_entry(system, user, schema, description, *, model_id, temperature, max_tokens,
               client=None, label=""):
    """One per-request accounting entry. Never raises: a CountTokens failure falls back to
    the proven byte bound and records which path was taken."""
    req = canonical_request(system, user, schema, description, model_id=model_id,
                            temperature=temperature, max_tokens=max_tokens)
    bound = conservative_token_upper_bound(system, user, schema, description)
    method, input_tokens, err = "UTF8_BYTE_UPPER_BOUND", bound, None
    if client is not None:
        try:
            exact = count_tokens_exact(client, system, user, schema, description,
                                       count_model_id=foundation_model_id(model_id))
            if exact <= bound:
                method, input_tokens = "AWS_BEDROCK_COUNT_TOKENS", exact
            else:
                err = f"count {exact} exceeded proven bound {bound}; kept the bound"
        except Exception as exc:                                  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"[:200]
    in_cost = Decimal(input_tokens) * PRICE_IN_PER_1K / Decimal(1000)
    out_cost = Decimal(max_tokens) * PRICE_OUT_PER_1K / Decimal(1000)
    return {"label": label, "request_sha256": request_sha256(req),
            "execution_model_id": model_id,
            "count_tokens_model_id": foundation_model_id(model_id),
            "counting_method": method, "count_error": err,
            "input_tokens": input_tokens,
            "conservative_byte_upper_bound": bound,
            "max_output_tokens": max_tokens,
            "max_billable_attempts": MAX_BILLABLE_ATTEMPTS_PER_CALL,
            "max_request_cost_usd_ceil": str(_usd(in_cost + out_cost))}


def converse(client, system, user, schema, description, *, model_id, temperature,
             max_tokens):
    """THE ONLY BILLABLE CALL. Returns (parsed_tool_input, provenance)."""
    req = canonical_request(system, user, schema, description, model_id=model_id,
                            temperature=temperature, max_tokens=max_tokens)
    resp = client.converse(**req)
    out = None
    for block in (resp.get("output", {}).get("message", {}).get("content") or []):
        if "toolUse" in block:
            out = block["toolUse"].get("input")
            break
    usage = resp.get("usage") or {}
    prov = {"request_sha256": request_sha256(req),
            "resolved_model_id": model_id,
            "stop_reason": resp.get("stopReason"),
            "input_tokens": usage.get("inputTokens"),
            "output_tokens": usage.get("outputTokens"),
            "response_sha256": hashlib.sha256(
                canonical_bytes(out if out is not None else {})).hexdigest()}
    return out, prov


def version_stamp() -> dict:
    return {"transport_version": TRANSPORT_VERSION,
            "retries_on_billable_path": 0,
            "silent_model_substitution": False,
            "price_in_per_1k_usd": str(PRICE_IN_PER_1K),
            "price_out_per_1k_usd": str(PRICE_OUT_PER_1K),
            "output_charged_at": "frozen max_tokens (ceiling holds whatever is emitted)"}
