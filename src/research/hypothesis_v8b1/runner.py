"""V8B.1 Bedrock runner -- the multi-turn Converse tool-use loop for ONE fixture.

Follows the fail-closed, cache-keyed, no-fabrication discipline already audited in
src/research/llm_matchup/bedrock_adapter.py, extended for TWO tools (search_hypotheses,
submit_selections) across multiple conversation turns rather than one tool in one turn.

Loop: model may call search_hypotheses any number of times; each call is answered locally
(zero network, zero marginal cost -- src.research.hypothesis_v8b1.search.search()) and fed
back as a toolResult; the loop ends when the model calls submit_selections or a turn budget
is exhausted. Every submitted hypothesis_id is validated against the set of ids the search
tool actually returned THIS session (search.resolve() plus a live-session registry) before
being accepted -- an id Sonnet invents rather than receives is rejected, not silently kept.

ZERO SILENT MODEL SUBSTITUTION. Model id, resolved model id, and every usage/latency figure
are recorded per call, exactly as bedrock_adapter.py already does.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from src.research.hypothesis_v8b1 import prompt as PR
from src.research.hypothesis_v8b1 import search as SE

CACHE_DIR = "/home/ubuntu/research/hypothesis_engine/out/v8b1_cache"
MAX_TOOL_TURNS = 12   # generous ceiling on search_hypotheses calls before forcing a stop


class RunnerUnavailable(Exception):
    pass


class CacheModelIdentityError(Exception):
    """A cached response's model_id does not match the requested one -- refuses to serve it,
    mirroring hardening/adapter_v4.py's own cross-model cache-poisoning guard."""


@dataclass
class RunResult:
    status: str   # OK | INVALID_NO_SUBMISSION | INVALID_SCHEMA | INVALID_UNKNOWN_HYPOTHESIS_ID | LLM_STATE_UNAVAILABLE
    research_trace: Optional[dict]
    final_selections: list
    manifest: dict


def _cache_key(model_id: str, config_stamp: dict, prompt_hash: str, packet_hash: str) -> str:
    raw = f"{model_id}|{json.dumps(config_stamp, sort_keys=True)}|{prompt_hash}|{packet_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def _load_cache(key: str, expect_model_id: str) -> Optional[dict]:
    p = _cache_path(key)
    if not os.path.exists(p):
        return None
    try:
        payload = json.load(open(p))
    except Exception:
        return None
    cached_model = (payload.get("manifest") or {}).get("model_id")
    if cached_model is not None and cached_model != expect_model_id:
        raise CacheModelIdentityError(
            f"cache key {key} bound to model {cached_model!r}, requested {expect_model_id!r}")
    return payload


def _save_cache(key: str, payload: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = _cache_path(key) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=1, default=str)
    os.replace(tmp, _cache_path(key))


# --- TRANSPORT CONFIG (V8B.1 canary attempt-1 repair; PRE_RESEARCH_TRANSPORT_TIMEOUT_REPAIR) ---
# Root cause of canary attempt 1 (all 3 fixtures LLM_STATE_UNAVAILABLE = "Read timeout on
# endpoint .../converse"): read_timeout=90 was below the latency tail of ONE heavy Sonnet-4.6
# Converse turn. Empirical basis: the working golden_v3 single-call baseline for the SAME model
# and SAME maxTokens=8192 (but WITHOUT extended thinking) already showed median 55.8s and max
# 118.8s PER CALL; each runner turn is strictly heavier (extended thinking budget 4096 +
# temperature 1.0 emits thinking tokens on top of output) and there are up to MAX_TOOL_TURNS
# turns per fixture. This is a transport-only change: it does NOT alter the prompt, the evidence
# packet, the fixture scorer, reasoning depth (thinking budget unchanged), max output
# (maxTokens unchanged), the research task, or the fixtures. It only makes the SDK wait long
# enough for one legitimate heavy turn to return, and applies a bounded transport retry.
READ_TIMEOUT_S = 300      # per single Converse turn; comfortably above the observed heavy-call tail
CONNECT_TIMEOUT_S = 15
RETRY_MAX_ATTEMPTS = 3    # botocore 'standard' mode: bounded retries for transient transport faults
RETRY_MODE = "standard"


def _bedrock_client(region: str):
    try:
        import boto3
        from botocore.config import Config
    except Exception as e:
        raise RunnerUnavailable(f"boto3 not installed: {e}")
    try:
        cfg = Config(read_timeout=READ_TIMEOUT_S, connect_timeout=CONNECT_TIMEOUT_S,
                     retries={"max_attempts": RETRY_MAX_ATTEMPTS, "mode": RETRY_MODE})
        return boto3.client("bedrock-runtime", region_name=region, config=cfg)
    except Exception as e:
        raise RunnerUnavailable(f"cannot create bedrock client: {e}")


def _validate_selection_ids(final_selections, returned_ids: set, capability) -> list[str]:
    """Every problems -- unknown or unresolvable hypothesis_id -- collected, never silently
    dropped. Returns the list of problems (empty if all valid)."""
    problems = []
    for sel in final_selections:
        hid = sel.get("hypothesis_id")
        if hid not in returned_ids:
            problems.append(f"hypothesis_id {hid!r} was not returned by search_hypotheses "
                            "this session")
            continue
        if SE.resolve(hid, capability) is None:
            problems.append(f"hypothesis_id {hid!r} does not resolve to a real canonical IR")
    return problems


def run_fixture(packet: dict, capability, *, model_id: str, region: str,
                config_stamp: dict, use_cache: bool = True,
                max_tool_turns: int = MAX_TOOL_TURNS) -> RunResult:
    """The full multi-turn loop for ONE fixture's evidence packet. Deterministic-first: serves
    cache if present and model-identity-matched, else calls Bedrock."""
    packet_hash = packet["packet_hash"]
    prompt_hash = PR.prompt_content_hash()
    key = _cache_key(model_id, config_stamp, prompt_hash, packet_hash)
    base_manifest = {
        "fixture_id": packet["fixture"]["fixture_id"], "packet_hash": packet_hash,
        "model_id": model_id, "region": region, "prompt_content_hash": prompt_hash,
        "config_stamp": config_stamp, "created_unix": int(time.time()),
    }

    if use_cache:
        cached = _load_cache(key, model_id)
        if cached is not None:
            m = {**base_manifest, **cached.get("manifest", {}), "cache_hit": True}
            return RunResult(cached["status"], cached.get("research_trace"),
                             cached.get("final_selections", []), m)

    try:
        client = _bedrock_client(region)
    except RunnerUnavailable as e:
        return RunResult("LLM_STATE_UNAVAILABLE", None, [],
                         {**base_manifest, "error": str(e)})

    system = PR.system_prompt()
    tools = [{"toolSpec": {"name": t["name"], "description": t["description"],
                           "inputSchema": t["inputSchema"]}} for t in PR.tool_specs()]
    packet_text = json.dumps({k: v for k, v in packet.items()}, sort_keys=True, default=str)
    messages = [{"role": "user", "content": [
        {"text": "=== BEGIN UNTRUSTED EVIDENCE PACKET ===\n" + packet_text +
                 "\n=== END UNTRUSTED EVIDENCE PACKET ==="}]}]

    returned_ids: set[str] = set()
    total_usage = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
    t0 = time.time()

    for turn in range(max_tool_turns):
        print(f"    [runner] turn {turn}: calling converse()...", flush=True)
        try:
            resp = client.converse(
                modelId=model_id, system=[{"text": system}], messages=messages,
                inferenceConfig={"maxTokens": config_stamp["max_tokens"],
                                 "temperature": config_stamp["temperature"]},
                additionalModelRequestFields={"thinking": config_stamp["thinking"]},
                toolConfig={"tools": tools, "toolChoice": {"auto": {}}},
            )
        except Exception as e:
            # Persist whatever call accounting we accumulated on PRIOR turns before this turn
            # raised (e.g. a read timeout). Without this the manifest reported usage=None even
            # though earlier turns in the loop had already returned and been billed -- which is
            # exactly why canary attempt 1 could not be accounted precisely (UNKNOWN_AFTER_SEND).
            return RunResult("LLM_STATE_UNAVAILABLE", None, [],
                             {**base_manifest, "error": f"invoke_failed: {e}",
                              "turn": turn, "usage_before_failure": dict(total_usage),
                              "latency_s": round(time.time() - t0, 3),
                              "call_state": "UNKNOWN_AFTER_SEND"})
        print(f"    [runner] turn {turn}: converse() returned, stopReason={resp.get('stopReason')}", flush=True)
        usage = resp.get("usage", {}) or {}
        for k in total_usage:
            total_usage[k] += usage.get(k, 0) or 0

        message = resp["output"]["message"]
        messages.append(message)
        tool_uses = [b["toolUse"] for b in message["content"] if "toolUse" in b]

        if not tool_uses:
            if resp.get("stopReason") == "end_turn":
                return RunResult("INVALID_NO_SUBMISSION", None, [],
                                 {**base_manifest, "cache_hit": False,
                                  "latency_s": round(time.time() - t0, 3),
                                  "usage": total_usage, "turns": turn + 1,
                                  "reason": "model ended turn without calling any tool"})
            continue

        tool_results = []
        submitted = None
        for tu in tool_uses:
            if tu["name"] == "search_hypotheses":
                print(f"    [runner] turn {turn}: search_hypotheses({tu['input']})", flush=True)
                q = SE.SearchQuery(**{k: v for k, v in tu["input"].items()
                                      if k in SE.SearchQuery.__dataclass_fields__})
                results = SE.search(q, capability)
                print(f"    [runner] turn {turn}: search returned {len(results)} results", flush=True)
                for r in results:
                    returned_ids.add(r["hypothesis_id"])
                tool_results.append({"toolResult": {"toolUseId": tu["toolUseId"],
                                     "content": [{"json": {"results": results}}]}})
            elif tu["name"] == "submit_selections":
                submitted = tu["input"]
                tool_results.append({"toolResult": {"toolUseId": tu["toolUseId"],
                                     "content": [{"json": {"received": True}}]}})
            else:
                tool_results.append({"toolResult": {"toolUseId": tu["toolUseId"],
                                     "content": [{"json": {"error": "unknown tool"}}],
                                     "status": "error"}})

        if submitted is not None:
            manifest = {**base_manifest, "cache_hit": False,
                       "latency_s": round(time.time() - t0, 3), "usage": total_usage,
                       "turns": turn + 1, "n_search_calls": len(returned_ids) and
                       sum(1 for tu in tool_uses if tu["name"] == "search_hypotheses")}
            problems = _validate_selection_ids(
                submitted.get("final_selections", []), returned_ids, capability)
            if problems:
                payload = {"status": "INVALID_UNKNOWN_HYPOTHESIS_ID",
                          "research_trace": submitted.get("research_trace"),
                          "final_selections": [], "manifest": {**manifest,
                          "validation_problems": problems}}
                _save_cache(key, payload)
                return RunResult(payload["status"], payload["research_trace"], [],
                                 payload["manifest"])
            payload = {"status": "OK", "research_trace": submitted.get("research_trace"),
                      "final_selections": submitted.get("final_selections", []),
                      "manifest": manifest}
            _save_cache(key, payload)
            return RunResult("OK", payload["research_trace"], payload["final_selections"],
                             manifest)

        messages.append({"role": "user", "content": tool_results})

    return RunResult("LLM_STATE_UNAVAILABLE", None, [],
                     {**base_manifest, "error": f"exceeded max_tool_turns={max_tool_turns} "
                     "without a submit_selections call", "usage": total_usage})


def version_stamp() -> dict:
    return {"runner_version": "v8b1_runner_v1", "max_tool_turns": MAX_TOOL_TURNS,
            "cache_dir": CACHE_DIR, "cross_model_cache_poisoning_guard": True,
            "unknown_hypothesis_id_rejected": True}
