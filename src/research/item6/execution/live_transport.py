"""ITEM 6 Stage-1 authentic live Bedrock transport adapter (`item6_bedrock_transport_v1`).

Closes blocker B1: the Item 6 runner accepts a `converse_fn` and a `count_tokens_fn` but the
frozen commit shipped NO committed authentic transport binding them to a real
`bedrock-runtime` client -- only test stand-ins ever drove the runner. This module is that
committed binding. It REUSES the already-frozen, already-paid-tested transport primitives
from the V5A.2 / V6 experiments unchanged (imported, never edited) and wraps them in a narrow
Item 6 adapter that satisfies the runner's exact callable contracts:

    count_tokens(modelId=..., input=...) -> {"inputTokens": int}      (runner count_tokens_fn)
    converse(request) -> raw_provider_response                        (runner converse_fn)

WHY REUSE, NOT REIMPLEMENT
`v6_transport.build_client()` already constructs a `bedrock-runtime` client with retries
DISABLED (total_max_attempts == 1) so one logical call bills at most once; `v5a2_transport`
and `v6_transport.preflight()` already assert the Converse capability on the CLIENT OBJECT
(not a version string, the mistake that burned an earlier authorization); and
`v6_token_count.foundation_model_id()` already encodes the CountTokens model-identifier
semantics. Duplicating that AWS logic would create a second thing to keep in step. Those
modules are frozen and hash-bound in their own preregistrations; this adapter imports them.

COUNT-TOKENS MODEL IDENTIFIER (verified, not guessed)
The AWS CountTokens API takes `modelId` = the FOUNDATION-MODEL id and an `input.converse`
block compatible with that model; its returned count matches what Converse would charge for
the same input. Converse itself takes the INFERENCE-PROFILE id. So this adapter counts with
`anthropic.claude-sonnet-4-6` and converses with `us.anthropic.claude-sonnet-4-6`. Claude
tokenization is a model-family property, identical across the regional routes the US profile
fans out to, so the count is valid for the frozen live path.

LIVE vs STANDIN -- FAIL CLOSED
Execution mode is explicit (`TransportMode.LIVE_BEDROCK` or `TransportMode.STANDIN`). In LIVE
mode a stand-in client, a mock, or any object not carrying the real bedrock-runtime service
model is REFUSED at construction; and every live receipt is stamped with an authenticity
block (`provider`, `model/profile`, botocore response metadata / requestId, envelope hash)
that a stand-in cannot fabricate. In STANDIN mode the adapter refuses to emit that live
authenticity stamp, so a stand-in response can never masquerade as an authentic live one.

ZERO SPEND on import and construction: importing this module and building the transport make
NO network call. Only `converse(...)` performs a paid generation, and only the frozen Item 6
live driver calls it, under the human-authorized ceiling and one-treatment rules.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

from src.research.hypothesis_oos import v5a2_transport as V5A2
from src.research.hypothesis_oos import v6_transport as V6
from src.research.hypothesis_oos.v6_token_count import foundation_model_id

LIVE_TRANSPORT_VERSION = "item6_bedrock_transport_v1"

MODEL_PROVIDER = "aws_bedrock"
MODEL_PROFILE_ID = "us.anthropic.claude-sonnet-4-6"       # Converse identifier
MODEL_ID = "anthropic.claude-sonnet-4-6"                  # CountTokens identifier
AWS_REGION = "us-east-1"

# The authenticity stamp key a LIVE receipt carries and a STANDIN one is forbidden to carry.
LIVE_AUTHENTICITY_KEY = "_item6_live_transport"


class TransportMode(str, Enum):
    LIVE_BEDROCK = "LIVE_BEDROCK"
    STANDIN = "STANDIN"


class LiveTransportRefused(RuntimeError):
    """Raised at construction / call time when LIVE mode cannot be honored authentically."""


def _sha256_canon(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _looks_like_real_bedrock_runtime_client(client: Any) -> bool:
    """True only for a genuine botocore bedrock-runtime client exposing the operations we
    depend on. Checks the CLIENT OBJECT's own service model (not a version string, not the
    class name), so a hand-rolled stand-in with `converse`/`count_tokens` attributes still
    fails unless it is actually the bedrock-runtime service. This is the property the runner
    depends on, asserted directly."""
    if client is None:
        return False
    if not (hasattr(client, "converse") and hasattr(client, "count_tokens")):
        return False
    try:
        sm = client.meta.service_model
        if sm.service_name not in ("bedrock-runtime",):
            return False
        ops = set(sm.operation_names)
        return "Converse" in ops and "CountTokens" in ops
    except Exception:
        return False


@dataclass
class CapabilityReport:
    boto3_version: str
    botocore_version: str
    has_converse: bool
    has_count_tokens: bool
    region: str
    client_service: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "boto3_version": self.boto3_version,
            "botocore_version": self.botocore_version,
            "bedrock_runtime_has_converse": self.has_converse,
            "bedrock_runtime_has_count_tokens": self.has_count_tokens,
            "aws_region": self.region,
            "client_service": self.client_service,
        }


def sdk_capability_report(region: str = AWS_REGION) -> CapabilityReport:
    """Programmatic capability assertion from the constructed client's service model. NO
    network call (building a client and reading its service model is offline)."""
    import boto3
    import botocore
    client = boto3.client("bedrock-runtime", region_name=region)
    sm = client.meta.service_model
    ops = set(sm.operation_names)
    return CapabilityReport(
        boto3_version=boto3.__version__,
        botocore_version=botocore.__version__,
        has_converse="Converse" in ops,
        has_count_tokens="CountTokens" in ops,
        region=region,
        client_service=sm.service_name,
    )


class BedrockStage1Transport:
    """Authentic Item 6 Stage-1 transport. Construct via `from_frozen_config(...)` for LIVE
    mode. Exposes `count_tokens(**payload)` and `converse(request)` matching the runner's
    injected-callable contracts, so `RunnerConfig(count_tokens_fn=t.count_tokens,
    converse_fn=t.converse)` wires the real provider in with no generic operator callable."""

    def __init__(self, *, mode: TransportMode, client: Any,
                 converse_model_id: str = MODEL_PROFILE_ID,
                 count_model_id: str = MODEL_ID, region: str = AWS_REGION):
        self.mode = mode
        self.converse_model_id = converse_model_id
        self.count_model_id = count_model_id
        self.region = region
        self._client = client
        self.n_converse_calls = 0
        self.n_count_tokens_calls = 0

        if mode == TransportMode.LIVE_BEDROCK:
            # Fail closed: a stand-in / mock cannot be bound in LIVE mode.
            if not _looks_like_real_bedrock_runtime_client(client):
                raise LiveTransportRefused(
                    "LIVE_BEDROCK requires a genuine bedrock-runtime client exposing "
                    "Converse + CountTokens on its service model; refusing a non-authentic "
                    "client (possible stand-in/mock). Aborted before any call.")
            # Reuse the frozen V6/V5A.2 capability + no-retry preflight on THIS client.
            V6.preflight(client, require_converse=True, model_id=converse_model_id)
            # CountTokens capability is additionally required for Item 6 (V6 only needed
            # Converse); assert it directly on the client object.
            if not hasattr(client, "count_tokens"):
                raise LiveTransportRefused(
                    "LIVE_BEDROCK requires the client to expose `count_tokens`; absent.")

    # ---- factory ----------------------------------------------------------------------
    @classmethod
    def from_frozen_config(cls, *, converse_model_id: str = MODEL_PROFILE_ID,
                           count_model_id: Optional[str] = None,
                           region: str = AWS_REGION) -> "BedrockStage1Transport":
        """Deterministically construct a LIVE transport from frozen configuration.

        Builds the retries-DISABLED bedrock-runtime client via the frozen
        `v6_transport.build_client()`, derives the CountTokens foundation-model id from the
        Converse inference-profile id (unless explicitly supplied), and runs the fail-closed
        preflight. Makes no network call (client construction is offline)."""
        client = V6.build_client(region_name=region)
        cmid = count_model_id or foundation_model_id(converse_model_id)
        return cls(mode=TransportMode.LIVE_BEDROCK, client=client,
                   converse_model_id=converse_model_id, count_model_id=cmid, region=region)

    @classmethod
    def standin(cls, *, count_tokens_impl: Callable[..., Dict[str, Any]],
                converse_impl: Callable[[Dict[str, Any]], Dict[str, Any]]
                ) -> "BedrockStage1Transport":
        """A STANDIN transport for tests/rehearsal. It can NEVER emit the LIVE authenticity
        stamp (enforced in `converse`), so a stand-in response cannot masquerade as live."""
        obj = cls(mode=TransportMode.STANDIN, client=None)
        obj._standin_count = count_tokens_impl
        obj._standin_converse = converse_impl
        return obj

    # ---- CountTokens ------------------------------------------------------------------
    def count_tokens(self, *, modelId: str, input: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A002,N803
        """Provider CountTokens (execution-control; non-generative, zero-charge). The runner
        passes the CountTokens payload it built from the EXACT canonical Converse request; we
        override its `modelId` to the FOUNDATION-MODEL id CountTokens requires, but the
        `input.converse` content (system + messages + toolConfig) is passed through verbatim,
        so the counted content is byte-identical to what Converse will see."""
        self.n_count_tokens_calls += 1
        if self.mode == TransportMode.STANDIN:
            return self._standin_count(modelId=self.count_model_id, input=input)
        # LIVE: force the foundation-model id for counting; forward the converse input as-is.
        resp = self._client.count_tokens(modelId=self.count_model_id, input=input)
        return resp

    # ---- Converse ---------------------------------------------------------------------
    def converse(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """One paid Converse generation. `request` is the runner's canonical request
        ({modelId, system, messages, inferenceConfig, toolConfig}); we splat it into
        `client.converse(**request)`. On success we attach a LIVE authenticity stamp derived
        from botocore ResponseMetadata (requestId, http status) plus a raw-envelope hash --
        material a stand-in cannot fabricate. In STANDIN mode we NEVER attach that stamp."""
        self.n_converse_calls += 1
        if self.mode == TransportMode.STANDIN:
            raw = self._standin_converse(request)
            # Defensive: strip any forged authenticity key a stand-in response might carry.
            if isinstance(raw, dict) and LIVE_AUTHENTICITY_KEY in raw:
                raw = {k: v for k, v in raw.items() if k != LIVE_AUTHENTICITY_KEY}
            return raw

        # LIVE path: the request already carries the inference-profile modelId. Transmit.
        raw = self._client.converse(**request)
        meta = raw.get("ResponseMetadata", {}) if isinstance(raw, dict) else {}
        stamp = {
            "provider": MODEL_PROVIDER,
            "transport_version": LIVE_TRANSPORT_VERSION,
            "converse_model_id": self.converse_model_id,
            "count_model_id": self.count_model_id,
            "aws_request_id": meta.get("RequestId"),
            "http_status": meta.get("HTTPStatusCode"),
            "authentic_provider_response": True,
        }
        # Bind the stamp to the exact envelope so it cannot be lifted onto another response.
        envelope_hash = _sha256_canon({k: v for k, v in raw.items()
                                       if k != "ResponseMetadata"})
        stamp["envelope_sha256"] = envelope_hash
        raw = dict(raw)
        raw[LIVE_AUTHENTICITY_KEY] = stamp
        return raw

    # ---- receipt authenticity ---------------------------------------------------------
    @staticmethod
    def is_authentic_live_response(raw: Dict[str, Any]) -> bool:
        """True only for a response carrying a well-formed LIVE authenticity stamp bound to
        its own envelope. Used by tests / receipt verification to distinguish a real provider
        response from a stand-in one."""
        if not isinstance(raw, dict):
            return False
        stamp = raw.get(LIVE_AUTHENTICITY_KEY)
        if not isinstance(stamp, dict) or not stamp.get("authentic_provider_response"):
            return False
        expect = _sha256_canon({k: v for k, v in raw.items()
                                if k not in ("ResponseMetadata", LIVE_AUTHENTICITY_KEY)})
        return stamp.get("envelope_sha256") == expect

    def version_stamp(self) -> Dict[str, Any]:
        return {
            "live_transport_version": LIVE_TRANSPORT_VERSION,
            "mode": self.mode.value,
            "model_provider": MODEL_PROVIDER,
            "converse_model_id": self.converse_model_id,
            "count_model_id": self.count_model_id,
            "aws_region": self.region,
            "reuses_transport": [V5A2.TRANSPORT_VERSION, V6.TRANSPORT_VERSION],
            "count_tokens_model_identifier": "foundation_model_id",
            "converse_model_identifier": "inference_profile_id",
        }


def version_stamp() -> Dict[str, Any]:
    return {
        "live_transport_version": LIVE_TRANSPORT_VERSION,
        "model_provider": MODEL_PROVIDER,
        "model_profile_id": MODEL_PROFILE_ID,
        "model_id": MODEL_ID,
        "aws_region": AWS_REGION,
        "reuses_v5a2_transport": V5A2.TRANSPORT_VERSION,
        "reuses_v6_transport": V6.TRANSPORT_VERSION,
        "count_tokens_uses_foundation_model_id": True,
        "converse_uses_inference_profile_id": True,
        "live_mode_rejects_standin": True,
        "standin_cannot_emit_live_receipt": True,
    }
