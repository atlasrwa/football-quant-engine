"""Hardened Bedrock call path (adapter_v3) — the LLM_MATCHUP_V2 instrument (patch §28).

This is a NEW call path; the frozen `bedrock_adapter.py` is untouched. It reuses the frozen
adapter's Bedrock plumbing (client creation, converse invocation, tool-input extraction) but
swaps in the hardened components:

  * system prompt      -> hardening.prompt_v3.SYSTEM_PROMPT_V3   (two-pass adversarial)
  * output schema      -> hardening.schema_v3.build_schema()     (+ counter_evidence_search)
  * validator          -> hardening.validator_v3.validate_v3     (fail-closed, stronger)
  * version stamp      -> hardening.versions_v2.version_stamp()  (LLM_MATCHUP_V2)
  * cache namespace    -> out/hardening/cache/                   (separate from Phase-B)

Design invariants preserved from the frozen adapter (patch §2, §43):
  * fail-closed: any Bedrock error -> LLM_STATE_UNAVAILABLE, never fabricate;
  * any validation failure -> LLM_STATE_REJECTED (no salvage);
  * the resolved model id is recorded per call (no silent model drift, patch §28);
  * output cached by (model, V2 versions, packet_hash, call_index).

k-CALL SUPPORT (patch §6, §31): analyze_k() runs the SAME packet through N independent calls
(cache disabled OR cache keyed by call index) so the repeatability + aggregation studies can
observe genuine call-to-call variation at temperature 0. Each raw response is persisted.
"""
from __future__ import annotations
import os, json, hashlib, time
from dataclasses import dataclass
from typing import Optional

from src.research.llm_matchup import ontology as ONT
from src.research.llm_matchup.bedrock_adapter import (
    _bedrock_client, _invoke_converse, _extract_tool_input, BedrockUnavailable, LLMResult,
)
from src.research.llm_matchup.validator import ValidationError
from src.research.llm_matchup.hardening import prompt_v3 as PR3
from src.research.llm_matchup.hardening import schema_v3 as SCH3
from src.research.llm_matchup.hardening import validator_v3 as VV3
from src.research.llm_matchup.hardening import versions_v2 as V2

CACHE_DIR = "/home/ubuntu/research/llm_matchup/out/hardening/cache"


def _cache_key(model_id: str, packet_hash: str, call_index: int) -> str:
    stamp = V2.version_stamp()
    # Include the actual prompt + schema CONTENT hashes so any edit to the prompt/schema text
    # (even without a version-string bump) busts the cache — no stale responses (patch §28
    # "no silent change"). This keeps cached responses honest during hardening iteration.
    content = f"{PR3.prompt_content_hash()}|{SCH3.schema_content_hash()}"
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


def analyze_matchup_v3(packet: dict,
                       model_id: Optional[str] = None,
                       region: Optional[str] = None,
                       use_cache: bool = True,
                       call_index: int = 0) -> LLMResult:
    """Single hardened call. `call_index` distinguishes repeated identical calls in the cache
    so a k-call repeatability study can be re-run deterministically from cache."""
    model_id = model_id or os.environ.get("BEDROCK_MODEL_ID", V2.DEFAULT_BEDROCK_MODEL_ID)
    region = region or os.environ.get("AWS_REGION", V2.DEFAULT_BEDROCK_REGION)
    ph = packet["packet_hash"]
    key = _cache_key(model_id, ph, call_index)
    stamp = V2.version_stamp()
    base_manifest = {
        "generation_id": V2.GENERATION_ID,
        "fixture_id": packet["fixture"]["fixture_id"], "packet_hash": ph,
        "model_id": model_id, "region": region, "call_index": call_index, **stamp,
        "created_unix": int(time.time()),
    }

    if use_cache:
        cached = _load_cache(key)
        if cached is not None:
            return LLMResult(cached["status"], cached.get("state"),
                             {**base_manifest, **cached.get("manifest", {}), "cache_hit": True})

    tool_schema = SCH3.build_schema()
    system = PR3.SYSTEM_PROMPT_V3
    user = PR3.user_message(packet, ONT.to_dict(), tool_schema)

    try:
        client = _bedrock_client(region)
    except BedrockUnavailable as e:
        return LLMResult("LLM_STATE_UNAVAILABLE", None, {**base_manifest, "error": str(e)})

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
    """Run the SAME packet through k independent calls (patch §6 repeatability, §31 aggregate).
    Returns a list of LLMResult, one per call index. temperature is 0 but inference is NOT
    deterministic — that variation is exactly what the repeatability study measures."""
    k = k or V2.REPEATABILITY_CALLS
    return [analyze_matchup_v3(packet, model_id=model_id, region=region,
                               use_cache=use_cache, call_index=i) for i in range(k)]


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Rough per-call cost estimate for the cost-discipline report (patch §34). Uses public
    Claude Sonnet 4.5 on-demand Bedrock pricing (USD per 1K tokens): input 0.003, output 0.015.
    This is an ESTIMATE for operating-economics reporting only, not a billing figure."""
    return round((input_tokens or 0) / 1000.0 * 0.003 + (output_tokens or 0) / 1000.0 * 0.015, 6)
