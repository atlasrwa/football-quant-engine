"""Bedrock adapter — narrow interface analyze_matchup() (brief §21, §23, §60, §61).

Design constraints enforced here:
  - single narrow function; no hidden filesystem mutation beyond the explicit cache dir;
  - no global mutable state; no silent fallback to a different LLM;
  - temperature≈0; strict tool-input schema (structured output);
  - output cache keyed by (model_id, prompt/ontology/schema versions, packet_hash);
  - fail-closed: on any Bedrock error -> LLM_STATE_UNAVAILABLE (never fabricate);
  - the exact resolved model id is recorded per call (no silent model drift);
  - OFFLINE RESEARCH MODE: if boto3/creds are absent, analyze_matchup raises
    BedrockUnavailable so the pilot harness records LLM_STATE_UNAVAILABLE and the quant
    pipeline degrades gracefully. A separate deterministic `stub_analyze` exists ONLY for
    golden tests (never used to manufacture research features).
"""
from __future__ import annotations
import os, json, hashlib, time
from dataclasses import dataclass
from typing import Optional

from src.research.llm_matchup import ontology as ONT
from src.research.llm_matchup import schema as SCH
from src.research.llm_matchup import prompt as PR
from src.research.llm_matchup import versions as V
from src.research.llm_matchup.validator import validate, ValidationError

CACHE_DIR = "/home/ubuntu/research/llm_matchup/out/cache"


class BedrockUnavailable(Exception):
    pass


@dataclass
class LLMResult:
    status: str                     # OK | LLM_STATE_REJECTED | LLM_STATE_UNAVAILABLE
    state: Optional[dict]
    manifest: dict                  # provenance: model, versions, tokens, latency, hash


def _cache_key(model_id: str, packet_hash: str) -> str:
    stamp = V.version_stamp()
    raw = f"{model_id}|{stamp}|{packet_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def _load_cache(key: str) -> Optional[dict]:
    p = _cache_path(key)
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            return None
    return None


def _save_cache(key: str, payload: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = _cache_path(key) + ".tmp"
    json.dump(payload, open(tmp, "w"), indent=2, default=str)
    os.replace(tmp, _cache_path(key))


def _bedrock_client(region: str):
    try:
        import boto3  # noqa
    except Exception as e:
        raise BedrockUnavailable(f"boto3 not installed: {e}")
    try:
        return __import__("boto3").client("bedrock-runtime", region_name=region)
    except Exception as e:
        raise BedrockUnavailable(f"cannot create bedrock client: {e}")


def _invoke_converse(client, model_id: str, system: str, user: str, tool_schema: dict) -> dict:
    """Bedrock Runtime Converse call with a strict tool input schema (structured output)."""
    tool = {
        "toolSpec": {
            "name": "emit_football_state",
            "description": "Return the structured football state for the fixture.",
            "inputSchema": {"json": tool_schema},
        }
    }
    resp = client.converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        toolConfig={"tools": [tool], "toolChoice": {"tool": {"name": "emit_football_state"}}},
        inferenceConfig={
            # Some Sonnet models reject temperature+topP together; we pin temperature only
            # for low-stochasticity analytical use and omit topP (brief §21).
            "temperature": V.INFERENCE_CONFIG["temperature"],
            "maxTokens": V.INFERENCE_CONFIG["maxTokens"],
        },
    )
    return resp


def _extract_tool_input(resp: dict) -> dict:
    for block in resp.get("output", {}).get("message", {}).get("content", []):
        if "toolUse" in block:
            return block["toolUse"]["input"]
    raise ValidationError("<response>", "no toolUse block returned")


def analyze_matchup(packet: dict,
                    model_id: Optional[str] = None,
                    region: Optional[str] = None,
                    use_cache: bool = True) -> LLMResult:
    """Narrow public interface. Deterministic-first: serves cache if present, else calls
    Bedrock. Always validates before returning. Never fabricates on failure."""
    model_id = model_id or os.environ.get("BEDROCK_MODEL_ID", V.DEFAULT_BEDROCK_MODEL_ID)
    region = region or os.environ.get("AWS_REGION", V.DEFAULT_BEDROCK_REGION)
    ph = packet["packet_hash"]
    key = _cache_key(model_id, ph)
    stamp = V.version_stamp()
    base_manifest = {
        "fixture_id": packet["fixture"]["fixture_id"], "packet_hash": ph,
        "model_id": model_id, "region": region, **stamp,
        "created_unix": int(time.time()),
    }

    if use_cache:
        cached = _load_cache(key)
        if cached is not None:
            return LLMResult(cached["status"], cached.get("state"),
                             {**base_manifest, **cached.get("manifest", {}), "cache_hit": True})

    tool_schema = SCH.build_schema()
    system = PR.SYSTEM_PROMPT
    user = PR.user_message(packet, ONT.to_dict(), tool_schema)

    try:
        client = _bedrock_client(region)
    except BedrockUnavailable as e:
        return LLMResult("LLM_STATE_UNAVAILABLE", None,
                         {**base_manifest, "error": str(e)})

    t0 = time.time()
    try:
        resp = _invoke_converse(client, model_id, system, user, tool_schema)
    except Exception as e:  # network/timeout/throttle -> fail closed
        return LLMResult("LLM_STATE_UNAVAILABLE", None,
                         {**base_manifest, "error": f"invoke_failed: {e}"})
    latency = time.time() - t0

    usage = resp.get("usage", {})
    manifest = {**base_manifest, "cache_hit": False, "latency_s": round(latency, 3),
                "input_tokens": usage.get("inputTokens"), "output_tokens": usage.get("outputTokens"),
                "resolved_model_id": resp.get("ResponseMetadata", {}).get("HTTPHeaders", {})
                    .get("x-amzn-bedrock-invocation-model-id", model_id)}

    try:
        raw_state = _extract_tool_input(resp)
        state = validate(raw_state, packet, stamp)
    except ValidationError as e:
        payload = {"status": "LLM_STATE_REJECTED", "state": None,
                   "manifest": {**manifest, "reject_field": e.field_path, "reject_reason": e.reason}}
        _save_cache(key, payload)
        return LLMResult(payload["status"], None, payload["manifest"])

    # stamp the validated state immutably
    state = dict(state)
    state["_provenance"] = manifest
    payload = {"status": "OK", "state": state, "manifest": manifest}
    _save_cache(key, payload)
    return LLMResult("OK", state, manifest)
