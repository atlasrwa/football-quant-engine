"""Identity-neutral Bedrock call path (adapter_v4) — the LLM_MATCHUP_V3 instrument.

This is a NEW call path; adapter_v3 (LLM_MATCHUP_V2, preserved as the failed
identity-sensitive generation) is untouched. It reuses the frozen adapter's Bedrock plumbing
(client creation, converse invocation, tool-input extraction) and V3's validator/output
schema (unchanged — see versions_v3.py's docstring for why), but swaps in:

  * system prompt      -> hardening.prompt_v4.SYSTEM_PROMPT_V4   (identity-neutral contract)
  * version stamp      -> hardening.versions_v3.version_stamp()  (LLM_MATCHUP_V3)
  * cache namespace     -> out/hardening_v3/cache/               (separate from V2)

HARD INTERFACE GUARD (V3 patch SS22-SS23): this module NEVER sends a raw/source evidence
packet to Bedrock. `analyze_matchup_v4` refuses (raises `NonNeutralPacketError`, before any
network call or cache lookup) any packet that is not `neutralize_v3.is_neutralized(...)`.
This makes the closed-world contract structural rather than a matter of caller discipline
(patch SS22: "Do not rely on developer discipline.").
"""
from __future__ import annotations
import os, json, hashlib
from typing import Optional

from src.research.llm_matchup.bedrock_adapter import (
    _bedrock_client, _invoke_converse, _extract_tool_input, BedrockUnavailable, LLMResult,
)
from src.research.llm_matchup.validator import ValidationError
from src.research.llm_matchup.hardening import prompt_v4 as PR4
from src.research.llm_matchup.hardening import schema_v3 as SCH3          # output schema, reused
from src.research.llm_matchup.hardening import validator_v3 as VV3        # reused, unchanged
from src.research.llm_matchup.hardening import versions_v3 as V3
from src.research.llm_matchup.hardening import neutralize_v3 as NZ3
from src.research.llm_matchup import ontology as ONT

CACHE_DIR = "/home/ubuntu/research/llm_matchup/out/hardening_v3/cache"


class NonNeutralPacketError(Exception):
    """Raised when code attempts to send a non-neutralized packet to Bedrock (SS22)."""


def _cache_key(model_id: str, packet_hash: str, call_index: int) -> str:
    stamp = V3.version_stamp()
    content = f"{PR4.prompt_content_hash()}|{SCH3.schema_content_hash()}"
    raw = f"{model_id}|{json.dumps(stamp, sort_keys=True)}|{content}|{packet_hash}|call{call_index}"
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


def analyze_matchup_v4(packet: dict,
                       model_id: Optional[str] = None,
                       region: Optional[str] = None,
                       use_cache: bool = True,
                       call_index: int = 0) -> LLMResult:
    """Single hardened, identity-neutral call. Refuses non-neutralized input (SS22)."""
    if not NZ3.is_neutralized(packet):
        raise NonNeutralPacketError(
            "adapter_v4 only accepts NEUTRALIZED_LLM_EVIDENCE_PACKET "
            f"(packet_schema_version={V3.PACKET_SCHEMA_VERSION!r}); got "
            f"packet_kind={packet.get('packet_kind')!r}, "
            f"packet_schema_version={packet.get('packet_schema_version')!r}. "
            "Call neutralize_v3.neutralize_for_llm_v2(source_packet) first.")

    model_id = model_id or os.environ.get("BEDROCK_MODEL_ID", V3.DEFAULT_BEDROCK_MODEL_ID)
    region = region or os.environ.get("AWS_REGION", V3.DEFAULT_BEDROCK_REGION)
    ph = packet["packet_hash"]
    key = _cache_key(model_id, ph, call_index)
    stamp = V3.version_stamp()
    base_manifest = {
        "generation_id": V3.GENERATION_ID,
        "fixture_id": packet["fixture"]["fixture_id"], "packet_hash": ph,
        "source_evidence_packet_hash": packet.get("source_evidence_packet_hash"),
        "model_id": model_id, "region": region, "call_index": call_index, **stamp,
        "inference_config": V3.INFERENCE_CONFIG,
        "created_unix": __import__("time").time().__int__(),
    }

    if use_cache:
        cached = _load_cache(key)
        if cached is not None:
            return LLMResult(cached["status"], cached.get("state"),
                             {**base_manifest, **cached.get("manifest", {}), "cache_hit": True})

    tool_schema = SCH3.build_schema()
    system = PR4.SYSTEM_PROMPT_V4
    user = PR4.user_message(packet, ONT.to_dict(), tool_schema)

    try:
        client = _bedrock_client(region)
    except BedrockUnavailable as e:
        return LLMResult("LLM_STATE_UNAVAILABLE", None, {**base_manifest, "error": str(e)})

    import time
    t0 = time.time()
    try:
        resp = _invoke_converse(client, model_id, system, user, tool_schema)
    except Exception as e:
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
        state = VV3.validate_v3(raw_state, packet, stamp)
    except ValidationError as e:
        payload = {"status": "LLM_STATE_REJECTED", "state": None,
                   "manifest": {**manifest, "reject_field": e.field_path, "reject_reason": e.reason}}
        _save_cache(key, payload)
        return LLMResult(payload["status"], None, payload["manifest"])

    state = dict(state)
    state["_provenance"] = manifest
    payload = {"status": "OK", "state": state, "manifest": manifest}
    _save_cache(key, payload)
    return LLMResult("OK", state, manifest)


def analyze_k(packet: dict, k: int = None, use_cache: bool = True,
              model_id: Optional[str] = None, region: Optional[str] = None) -> list[LLMResult]:
    """Run the SAME neutralized packet through k independent calls (repeatability/aggregate)."""
    k = k or V3.REPEATABILITY_CALLS
    return [analyze_matchup_v4(packet, model_id=model_id, region=region,
                               use_cache=use_cache, call_index=i) for i in range(k)]


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Same public Bedrock on-demand Sonnet pricing used for V2 (patch §34): $0.003/1K input,
    $0.015/1K output. Estimate for operating-economics reporting only, not a billing figure."""
    return round((input_tokens or 0) / 1000.0 * 0.003 + (output_tokens or 0) / 1000.0 * 0.015, 6)
