"""ITEM 6 Stage-1 authoritative provider-side input-token counter (execution amendment v2).

`item6_token_counter_v1`. ZERO SPEND. Importing this module makes no network call, and a
CountTokens request is NOT a model inference treatment: it invokes the AWS Bedrock
`CountTokens` control operation, which returns only an input-token count and generates no
model output, consumes no generation budget, and is priced/billed as a token-count request,
not as inference.

WHY THIS EXISTS (the narrow zero-spend amendment)
The prior pre-call monetary proof reserved input cost from a UTF-8 byte upper bound
(canonical_request bytes <= MAX_REQUEST_UTF8_BYTES, tokens <= bytes). That safely bounds the
tokens represented by the transmitted request bytes, but a tool-enabled provider request may
involve provider-side/system token accounting not literally represented by canonical
transmitted UTF-8 bytes. The reservation therefore must not depend EXCLUSIVELY on the byte
bound. AWS Bedrock exposes a model-specific `CountTokens` operation whose returned count
"matches the token count that would be charged if the same input were sent to the model in
an InvokeModel or Converse request". We use that count as the AUTHORITATIVE pre-inference
input-cost reservation. The byte ceiling remains an independent safety constraint.

COUNT MUST MATCH THE ACTUAL REQUEST
The CountTokens input is DERIVED from the exact final canonical Converse request that would
be transmitted for inference: the same system prompt, the same user message(s), the same
tool definition/schema, the same tool choice, the same model/profile. We compute a
`count_input_sha256` over the derived CountTokens payload AND bind it to the
`inference_request_sha256` of the request it was derived from. The runner freezes the request
after counting; if any counted field changes it must RECOUNT (never count request A then
transmit request B).

FAIL CLOSED
If CountTokens is unavailable (no client / no capability), errors, returns malformed
accounting, cannot target the frozen model/profile, or cannot represent the exact inference
request, this module returns a CountResult with `ok == False` and a frozen status string
(PRECALL_TOKEN_COUNT_UNAVAILABLE / PRECALL_TOKEN_COUNT_ERROR / PRECALL_TOKEN_COUNT_MALFORMED /
PRECALL_TOKEN_COUNT_REQUEST_MISMATCH). It NEVER falls back to an optimistic estimate; the
runner must block the paid inference on any non-ok result.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

TOKEN_COUNTER_VERSION = "item6_token_counter_v1"

# Frozen execution statuses for the counting phase (all block inference; never optimistic).
PRECALL_TOKEN_COUNT_OK = "PRECALL_TOKEN_COUNT_OK"
PRECALL_TOKEN_COUNT_UNAVAILABLE = "PRECALL_TOKEN_COUNT_UNAVAILABLE"
PRECALL_TOKEN_COUNT_ERROR = "PRECALL_TOKEN_COUNT_ERROR"
PRECALL_TOKEN_COUNT_MALFORMED = "PRECALL_TOKEN_COUNT_MALFORMED"
PRECALL_TOKEN_COUNT_REQUEST_MISMATCH = "PRECALL_TOKEN_COUNT_REQUEST_MISMATCH"

BLOCKING_STATUSES = frozenset({
    PRECALL_TOKEN_COUNT_UNAVAILABLE,
    PRECALL_TOKEN_COUNT_ERROR,
    PRECALL_TOKEN_COUNT_MALFORMED,
    PRECALL_TOKEN_COUNT_REQUEST_MISMATCH,
})


def _canonical_bytes(obj: Any) -> bytes:
    """Frozen canonical serialization identical to the request builder's (UTF-8, sorted
    keys, tight separators, no NaN). Deterministic and PYTHONHASHSEED-independent."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha256(obj: Any) -> str:
    return hashlib.sha256(_canonical_bytes(obj)).hexdigest()


class CountTokensRequestMismatch(RuntimeError):
    """Raised when the CountTokens payload does not represent the exact inference request."""


def build_count_tokens_input(canonical_request: Dict[str, Any]) -> Dict[str, Any]:
    """Map the EXACT canonical Converse inference request to a Bedrock CountTokens input.

    The CountTokens `converse` input is a tagged union member carrying the same conversation
    material the model would see: system, messages, toolConfig (and optionally
    additionalModelRequestFields). `modelId` is a TOP-LEVEL CountTokens parameter, not a
    member of the converse block, and `inferenceConfig` (temperature/maxTokens) is an
    OUTPUT/generation control that does not affect input tokenization and is not part of the
    CountTokens converse input. We therefore lift modelId to the top level and forward the
    input-bearing fields verbatim. This construction is byte-identical to the transmitted
    request for every field that contributes input tokens; nothing is paraphrased or dropped
    that the model would tokenize as input.

    Returns a dict {"modelId": ..., "input": {"converse": {...}}} ready to splat into
    client.count_tokens(**payload).
    """
    if "modelId" not in canonical_request:
        raise CountTokensRequestMismatch("canonical request missing modelId")
    if "messages" not in canonical_request:
        raise CountTokensRequestMismatch("canonical request missing messages")
    if "system" not in canonical_request:
        raise CountTokensRequestMismatch("canonical request missing system")
    if "toolConfig" not in canonical_request:
        # A tool-enabled inference request MUST carry its tool schema; counting a request
        # without the tool schema that inference uses is an integrity failure (adversarial
        # test 6). We refuse to build a skeleton count for a richer inference request.
        raise CountTokensRequestMismatch("canonical request missing toolConfig")

    converse: Dict[str, Any] = {
        "messages": canonical_request["messages"],
        "system": canonical_request["system"],
        "toolConfig": canonical_request["toolConfig"],
    }
    if "additionalModelRequestFields" in canonical_request:
        converse["additionalModelRequestFields"] = \
            canonical_request["additionalModelRequestFields"]

    return {"modelId": canonical_request["modelId"], "input": {"converse": converse}}


def count_input_fingerprint(canonical_request: Dict[str, Any]) -> Dict[str, str]:
    """The identity pair binding a token count to a specific inference request.

    * inference_request_sha256 -- the full canonical Converse request (what the runner hashes
      and transmits);
    * count_input_sha256       -- the derived CountTokens payload (what we send to CountTokens).

    Both are recomputed after counting; if either changes the runner must recount.
    """
    return {
        "inference_request_sha256": _sha256(canonical_request),
        "count_input_sha256": _sha256(build_count_tokens_input(canonical_request)),
    }


@dataclass
class CountResult:
    """Outcome of one CountTokens attempt. `ok` is True ONLY when a positive integer input
    token count was returned for the exact inference request; otherwise `status` is a frozen
    blocking status and `input_tokens` is None. The runner must block inference unless ok."""
    ok: bool
    status: str
    input_tokens: Optional[int]
    inference_request_sha256: str
    count_input_sha256: str
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "input_tokens": self.input_tokens,
            "inference_request_sha256": self.inference_request_sha256,
            "count_input_sha256": self.count_input_sha256,
            "detail": self.detail,
            "token_counter_version": TOKEN_COUNTER_VERSION,
        }


@dataclass
class CountTokensCounters:
    """Execution-control call accounting. These are NOT scientific model treatments and MUST
    NOT increment MODEL_CALLS_PER_FIXTURE / PAID_TREATMENTS / SONNET_GENERATION_CALLS."""
    n_requests: int = 0
    n_success: int = 0
    n_failure: int = 0
    events: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "N_COUNT_TOKENS_REQUESTS": self.n_requests,
            "N_COUNT_TOKENS_SUCCESS": self.n_success,
            "N_COUNT_TOKENS_FAILURE": self.n_failure,
            "is_model_inference_treatment": False,
            "increments_paid_treatments": False,
            "increments_sonnet_generation_calls": False,
        }


# A CountTokens callable: takes the boto3-style kwargs {modelId, input} and returns the
# provider response dict {"inputTokens": int}. Tests inject a deterministic local stand-in;
# production passes a bound `bedrock_runtime_client.count_tokens`.
CountTokensFn = Callable[..., Dict[str, Any]]


def count_input_tokens(canonical_request: Dict[str, Any],
                       count_tokens_fn: Optional[CountTokensFn],
                       counters: Optional[CountTokensCounters] = None) -> CountResult:
    """Authoritatively count the input tokens for the EXACT inference request. Fails closed.

    Steps:
      1. derive the CountTokens payload from the canonical inference request (raises/blocks if
         the request cannot be represented, e.g. missing tool schema);
      2. if no counter capability is supplied -> PRECALL_TOKEN_COUNT_UNAVAILABLE (block);
      3. call CountTokens; any exception -> PRECALL_TOKEN_COUNT_ERROR (block);
      4. validate the response is a positive integer inputTokens -> otherwise
         PRECALL_TOKEN_COUNT_MALFORMED (block);
      5. re-derive the fingerprint and confirm the counted payload still equals the request's
         payload (request immutability after count) -> otherwise
         PRECALL_TOKEN_COUNT_REQUEST_MISMATCH (block).
    """
    counters = counters or CountTokensCounters()

    # 1. derive payload + identity (may reveal the request cannot be represented).
    try:
        fp = count_input_fingerprint(canonical_request)
        payload = build_count_tokens_input(canonical_request)
    except CountTokensRequestMismatch as e:
        counters.n_requests += 1
        counters.n_failure += 1
        counters.events.append({"event": "COUNT_REQUEST_UNREPRESENTABLE", "detail": str(e)})
        return CountResult(False, PRECALL_TOKEN_COUNT_REQUEST_MISMATCH, None,
                           inference_request_sha256="", count_input_sha256="",
                           detail=str(e)[:200])

    ireq_sha = fp["inference_request_sha256"]
    cin_sha = fp["count_input_sha256"]

    # 2. capability unavailable -> fail closed (no optimistic fallback).
    if count_tokens_fn is None:
        counters.n_requests += 1
        counters.n_failure += 1
        counters.events.append({"event": "COUNT_UNAVAILABLE"})
        return CountResult(False, PRECALL_TOKEN_COUNT_UNAVAILABLE, None,
                           ireq_sha, cin_sha, detail="no CountTokens capability supplied")

    # 3. call CountTokens (control operation; NOT inference).
    counters.n_requests += 1
    try:
        resp = count_tokens_fn(**payload)
    except Exception as e:  # noqa: BLE001  provider/transport/validation errors all fail closed
        counters.n_failure += 1
        counters.events.append({"event": "COUNT_ERROR", "detail": str(e)[:200]})
        return CountResult(False, PRECALL_TOKEN_COUNT_ERROR, None,
                           ireq_sha, cin_sha, detail=str(e)[:200])

    # 4. validate accounting shape.
    if not isinstance(resp, dict) or "inputTokens" not in resp:
        counters.n_failure += 1
        counters.events.append({"event": "COUNT_MALFORMED", "detail": "no inputTokens"})
        return CountResult(False, PRECALL_TOKEN_COUNT_MALFORMED, None,
                           ireq_sha, cin_sha, detail="response missing inputTokens")
    tokens = resp["inputTokens"]
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
        counters.n_failure += 1
        counters.events.append({"event": "COUNT_MALFORMED", "detail": repr(tokens)})
        return CountResult(False, PRECALL_TOKEN_COUNT_MALFORMED, None,
                           ireq_sha, cin_sha, detail=f"bad inputTokens: {tokens!r}")

    # 5. request immutability after count: the payload we counted must STILL equal the
    #    payload derived from the request we are about to transmit. (Defends against A->B.)
    fp2 = count_input_fingerprint(canonical_request)
    if fp2["inference_request_sha256"] != ireq_sha or fp2["count_input_sha256"] != cin_sha:
        counters.n_failure += 1
        counters.events.append({"event": "COUNT_REQUEST_MISMATCH"})
        return CountResult(False, PRECALL_TOKEN_COUNT_REQUEST_MISMATCH, None,
                           ireq_sha, cin_sha, detail="request changed after count")

    counters.n_success += 1
    counters.events.append({"event": "COUNT_OK", "input_tokens": tokens,
                            "inference_request_sha256": ireq_sha,
                            "count_input_sha256": cin_sha})
    return CountResult(True, PRECALL_TOKEN_COUNT_OK, tokens, ireq_sha, cin_sha,
                       detail="provider counted")


def version_stamp() -> Dict[str, Any]:
    return {
        "token_counter_version": TOKEN_COUNTER_VERSION,
        "provider_token_count_precall": True,
        "count_tokens_matches_actual_request": True,
        "count_tokens_is_inference_treatment": False,
        "count_tokens_consumes_generation_budget": False,
        "fails_closed_no_optimistic_fallback": True,
        "blocking_statuses": sorted(BLOCKING_STATUSES),
        "input_token_reservation_authority": "provider_count_tokens",
        "byte_ceiling_retained_independently": True,
    }
