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


class CacheModelIdentityError(Exception):
    """Raised when a cache entry's recorded model identity contradicts the requested model.

    Defence in depth for the multi-model-generation era (Sonnet 4.5 arm vs Sonnet 4.6 arm):
    the cache KEY already binds the model id, so a cross-model collision is not reachable by
    construction, but a corrupted/hand-edited/misplaced cache file must never be silently
    served as if it came from the requested model. Reusing one model's LLM response as
    another model's observation would invalidate the experiment.
    """


def _cache_key(model_id: str, packet_hash: str, call_index: int, gen=V3) -> str:
    """Cache key binds MODEL IDENTITY + full generation version stamp + prompt/schema content
    + packet hash + call index. `model_id` is part of the key, so the Sonnet 4.5 and Sonnet
    4.6 arms can never collide even for a byte-identical neutralized packet."""
    stamp = gen.version_stamp()
    content = f"{PR4.prompt_content_hash()}|{SCH3.schema_content_hash()}"
    raw = f"{model_id}|{json.dumps(stamp, sort_keys=True)}|{content}|{packet_hash}|call{call_index}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_path(key: str, cache_dir: str = CACHE_DIR) -> str:
    return os.path.join(cache_dir, f"{key}.json")


def _load_cache(key: str, cache_dir: str = CACHE_DIR,
                expect_model_id: Optional[str] = None) -> Optional[dict]:
    p = _cache_path(key, cache_dir)
    if os.path.exists(p):
        try:
            payload = json.load(open(p))
        except Exception:
            return None
        if expect_model_id is not None:
            cached_model = (payload.get("manifest") or {}).get("model_id")
            if cached_model is not None and cached_model != expect_model_id:
                raise CacheModelIdentityError(
                    f"cache entry {key} records model_id={cached_model!r} but "
                    f"{expect_model_id!r} was requested; refusing to serve another model's "
                    "response as this model's observation")
        return payload
    return None


def _save_cache(key: str, payload: dict, cache_dir: str = CACHE_DIR) -> None:
    os.makedirs(cache_dir, exist_ok=True)
    tmp = _cache_path(key, cache_dir) + ".tmp"
    json.dump(payload, open(tmp, "w"), indent=2, default=str)
    os.replace(tmp, _cache_path(key, cache_dir))


def analyze_matchup_v4(packet: dict,
                       model_id: Optional[str] = None,
                       region: Optional[str] = None,
                       use_cache: bool = True,
                       call_index: int = 0,
                       gen=V3,
                       cache_dir: Optional[str] = None,
                       capture_rejected_raw: bool = False) -> LLMResult:
    """Single hardened, identity-neutral call. Refuses non-neutralized input (SS22).

    `gen` selects the scientific generation module (default `versions_v3` = the Sonnet 4.5
    arm; pass `versions_v3_sonnet46` for the Sonnet 4.6 arm). `cache_dir` selects the response
    cache namespace and defaults to the generation-appropriate directory. Both default to the
    original 4.5 behavior, so existing callers are unaffected.

    `capture_rejected_raw` (default False = original behavior) additionally records the RAW
    model output alongside a validator rejection, under the manifest key `rejected_raw_state`.
    Without it a rejection is a black box: the state is discarded, so diagnosing WHY a model
    failed the contract requires re-spending tokens on an identical call. Validator rejection
    rate is a primary measured quantity in the multi-model comparison, so the rejected payload
    is scientific data. It is safe to persist because it is the model's OWN output about an
    already-neutralized packet -- it contains no real identifiers by construction (and the
    pre-spend audit proves the input carried none). NEVER enable this for the 4.5 arm
    mid-experiment: it would change what the 4.5 cache files contain.
    """
    if not NZ3.is_neutralized(packet):
        raise NonNeutralPacketError(
            "adapter_v4 only accepts NEUTRALIZED_LLM_EVIDENCE_PACKET "
            f"(packet_schema_version={V3.PACKET_SCHEMA_VERSION!r}); got "
            f"packet_kind={packet.get('packet_kind')!r}, "
            f"packet_schema_version={packet.get('packet_schema_version')!r}. "
            "Call neutralize_v3.neutralize_for_llm_v2(source_packet) first.")

    model_id = model_id or os.environ.get("BEDROCK_MODEL_ID", gen.DEFAULT_BEDROCK_MODEL_ID)
    region = region or os.environ.get("AWS_REGION", gen.DEFAULT_BEDROCK_REGION)
    cache_dir = cache_dir or CACHE_DIR
    ph = packet["packet_hash"]
    key = _cache_key(model_id, ph, call_index, gen=gen)
    stamp = gen.version_stamp()
    base_manifest = {
        "generation_id": gen.GENERATION_ID,
        "fixture_id": packet["fixture"]["fixture_id"], "packet_hash": ph,
        "source_evidence_packet_hash": packet.get("source_evidence_packet_hash"),
        "model_id": model_id, "region": region, "call_index": call_index, **stamp,
        "inference_config": gen.INFERENCE_CONFIG,
        "created_unix": __import__("time").time().__int__(),
    }

    if use_cache:
        cached = _load_cache(key, cache_dir, expect_model_id=model_id)
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

    raw_state = None
    try:
        raw_state = _extract_tool_input(resp)
        state = VV3.validate_v3(raw_state, packet, stamp)
    except ValidationError as e:
        reject_manifest = {**manifest, "reject_field": e.field_path, "reject_reason": e.reason}
        if capture_rejected_raw:
            reject_manifest["rejected_raw_state"] = raw_state
        payload = {"status": "LLM_STATE_REJECTED", "state": None,
                   "manifest": reject_manifest}
        _save_cache(key, payload, cache_dir)
        return LLMResult(payload["status"], None, payload["manifest"])

    state = dict(state)
    state["_provenance"] = manifest
    payload = {"status": "OK", "state": state, "manifest": manifest}
    _save_cache(key, payload, cache_dir)
    return LLMResult("OK", state, manifest)


def analyze_k(packet: dict, k: int = None, use_cache: bool = True,
              model_id: Optional[str] = None, region: Optional[str] = None,
              gen=V3, cache_dir: Optional[str] = None) -> list[LLMResult]:
    """Run the SAME neutralized packet through k independent calls (repeatability/aggregate)."""
    k = k or gen.REPEATABILITY_CALLS
    return [analyze_matchup_v4(packet, model_id=model_id, region=region,
                               use_cache=use_cache, call_index=i,
                               gen=gen, cache_dir=cache_dir) for i in range(k)]


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Same public Bedrock on-demand Sonnet pricing used for V2 (patch §34): $0.003/1K input,
    $0.015/1K output. Estimate for operating-economics reporting only, not a billing figure."""
    return round((input_tokens or 0) / 1000.0 * 0.003 + (output_tokens or 0) / 1000.0 * 0.015, 6)
