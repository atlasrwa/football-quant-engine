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

# --- DETERMINISTIC TERMINATION CONTRACT (V8B.1 orchestration amendment) ---
# BOUNDED_SEARCH_THEN_FORCED_SUBMIT. Canary attempt 2 showed the auto-tool loop could search
# indefinitely (2/3 fixtures hit the old turn ceiling without ever calling submit_selections,
# with unbounded input-token growth). This is an interface/termination rule, NOT a football-
# content change: the frozen research prompt, evidence packet, reasoning budget, hypothesis
# universe, scorer, and controls are untouched.
#
#   * The model may call search_hypotheses up to MAX_SEARCH_CALLS times (auto tool choice,
#     extended thinking ON exactly as frozen). MAX_SEARCH_CALLS is a TRUE EXECUTION CAP: if a
#     single response contains more search calls than the remaining budget, only the remaining
#     allowed searches are executed and each excess call gets a deterministic
#     SEARCH_BUDGET_EXHAUSTED tool result (every toolUseId answered => valid conversation).
#   * If it calls submit_selections at any point BEFORE the budget is exhausted, that is
#     accepted immediately (the budget is a maximum, not a mandatory quota).
#   * Once MAX_SEARCH_CALLS is reached without a submission, the runner issues EXACTLY ONE more
#     Converse turn with toolChoice FORCED to submit_selections. On this model, forced tool
#     choice is incompatible with extended thinking ("Thinking may not be enabled when
#     tool_choice forces tool use"), so the forced turn disables thinking. Temperature is left
#     at the frozen 1.0 (thinking-off permits any temperature; nothing about the reasoning
#     content changes -- the forced turn asks only for the terminal action, not new research).
#   * Forced submission means "report the best selections you currently support, including
#     ZERO if none are justified" -- it NEVER means invent hypotheses. 0-8 selections valid.
MAX_SEARCH_CALLS = 6
FINAL_FORCED_SUBMIT_CALLS = 1
# MAX_TOOL_TURNS is DERIVED mechanically, not chosen arbitrarily: worst case is one
# search_hypotheses call per turn (MAX_SEARCH_CALLS turns) followed by the single forced-submit
# turn. It is a defensive hard ceiling only; normal termination is by search budget or early
# submit, never by hitting this.
MAX_TOOL_TURNS = MAX_SEARCH_CALLS + FINAL_FORCED_SUBMIT_CALLS


class RunnerUnavailable(Exception):
    pass


class CacheModelIdentityError(Exception):
    """A cached response's model_id does not match the requested one -- refuses to serve it,
    mirroring hardening/adapter_v4.py's own cross-model cache-poisoning guard."""


@dataclass
class RunResult:
    status: str   # OK | OK_ABSTAIN | INVALID_UNKNOWN_HYPOTHESIS_ID | INVALID_NO_SUBMISSION
                  # | ORCHESTRATION_FORCED_SUBMIT_FAILED | ORCHESTRATION_TURN_CEILING
                  # | LLM_STATE_UNAVAILABLE
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
    search_calls = 0          # total search_hypotheses invocations across all turns
    converse_calls = 0        # total Converse round trips (accounting)
    t0 = time.time()

    def _acct(**extra):
        """Deterministic operational accounting block (no scientific score)."""
        return {"converse_calls": converse_calls, "search_calls": search_calls,
                "usage": dict(total_usage), "latency_s": round(time.time() - t0, 3),
                "cache_hit": False,
                "max_search_calls": MAX_SEARCH_CALLS,
                "max_tool_turns": MAX_TOOL_TURNS, **extra}

    def _finalize_submission(submitted, termination_reason):
        """Validate ids, persist, and return a terminal RunResult. 0 selections => OK_ABSTAIN.
        NEVER fabricates: only ids the search tool actually returned this session are accepted."""
        sels = submitted.get("final_selections", []) or []
        problems = _validate_selection_ids(sels, returned_ids, capability)
        if problems:
            payload = {"status": "INVALID_UNKNOWN_HYPOTHESIS_ID",
                       "research_trace": submitted.get("research_trace"),
                       "final_selections": [],
                       "manifest": {**base_manifest,
                                    **_acct(termination_reason=termination_reason,
                                            validation_problems=problems)}}
            _save_cache(key, payload)
            return RunResult(payload["status"], payload["research_trace"], [],
                             payload["manifest"])
        status = "OK_ABSTAIN" if len(sels) == 0 else "OK"
        payload = {"status": status, "research_trace": submitted.get("research_trace"),
                   "final_selections": sels,
                   "manifest": {**base_manifest,
                                **_acct(termination_reason=termination_reason)}}
        _save_cache(key, payload)
        return RunResult(status, payload["research_trace"], sels, payload["manifest"])

    for turn in range(max_tool_turns):
        # Deterministic termination contract: once the search budget is spent without a
        # submission, force exactly one final submit_selections turn (thinking OFF, since this
        # model forbids forced tool choice while thinking is enabled).
        force_submit = search_calls >= MAX_SEARCH_CALLS
        if force_submit:
            tool_choice = {"tool": {"name": "submit_selections"}}
            extra_fields = {}          # thinking disabled on the forced turn (API constraint)
        else:
            tool_choice = {"auto": {}}
            extra_fields = {"thinking": config_stamp["thinking"]}

        print(f"    [runner] turn {turn}: converse() force_submit={force_submit} "
              f"search_calls={search_calls}...", flush=True)
        try:
            converse_calls += 1
            resp = client.converse(
                modelId=model_id, system=[{"text": system}], messages=messages,
                inferenceConfig={"maxTokens": config_stamp["max_tokens"],
                                 "temperature": config_stamp["temperature"]},
                additionalModelRequestFields=extra_fields,
                toolConfig={"tools": tools, "toolChoice": tool_choice},
            )
        except Exception as e:
            # Persist accounting accumulated on PRIOR turns before this turn raised (e.g. read
            # timeout). Transport failure per frozen accounting semantics.
            return RunResult("LLM_STATE_UNAVAILABLE", None, [],
                             {**base_manifest,
                              **_acct(error=f"invoke_failed: {e}", turn=turn,
                                      termination_reason="TRANSPORT_FAILURE",
                                      call_state="UNKNOWN_AFTER_SEND")})
        print(f"    [runner] turn {turn}: returned stopReason={resp.get('stopReason')}", flush=True)
        usage = resp.get("usage", {}) or {}
        for k in total_usage:
            total_usage[k] += usage.get(k, 0) or 0

        message = resp["output"]["message"]
        messages.append(message)
        tool_uses = [b["toolUse"] for b in message["content"] if "toolUse" in b]

        # A submit_selections anywhere in the turn's tool calls terminates (search or forced).
        submitted = next((tu["input"] for tu in tool_uses
                          if tu["name"] == "submit_selections"), None)
        if submitted is not None:
            reason = "FORCED_SUBMIT" if force_submit else "EARLY_SUBMIT"
            # answer any sibling tool calls in this turn is unnecessary once submitted; the
            # loop terminates here.
            return _finalize_submission(submitted, reason)

        if force_submit:
            # We forced submit_selections but the model did not produce it. Explicit
            # orchestration failure -- never fabricate a selection.
            return RunResult("ORCHESTRATION_FORCED_SUBMIT_FAILED", None, [],
                             {**base_manifest,
                              **_acct(turn=turn, stop_reason=resp.get("stopReason"),
                                      termination_reason="FORCED_SUBMIT_NOT_PRODUCED",
                                      error="forced toolChoice=submit_selections but model "
                                            "did not emit that tool call")})

        if not tool_uses:
            # No tool call and not forcing yet: only terminal if the model explicitly ended.
            if resp.get("stopReason") == "end_turn":
                return RunResult("INVALID_NO_SUBMISSION", None, [],
                                 {**base_manifest,
                                  **_acct(turn=turn, termination_reason="ENDED_WITHOUT_TOOL",
                                          reason="model ended turn without calling any tool")})
            continue

        # Answer every tool call locally (zero network, zero marginal cost), but enforce
        # MAX_SEARCH_CALLS as a TRUE EXECUTION CAP -- not merely a between-turn threshold. A
        # single Sonnet response may contain several search_hypotheses tool calls; we execute
        # only as many as remain within the budget and return a deterministic
        # SEARCH_BUDGET_EXHAUSTED result for every excess call (search or otherwise). Every
        # toolUseId is still answered exactly once, so the conversation structure stays valid;
        # the next turn will be force_submit because search_calls has reached the cap.
        tool_results = []
        for tu in tool_uses:
            remaining = MAX_SEARCH_CALLS - search_calls
            if tu["name"] == "search_hypotheses" and remaining > 0:
                search_calls += 1
                q = SE.SearchQuery(**{k: v for k, v in tu["input"].items()
                                      if k in SE.SearchQuery.__dataclass_fields__})
                results = SE.search(q, capability)
                print(f"    [runner] turn {turn}: search #{search_calls} -> "
                      f"{len(results)} results", flush=True)
                for r in results:
                    returned_ids.add(r["hypothesis_id"])
                tool_results.append({"toolResult": {"toolUseId": tu["toolUseId"],
                                     "content": [{"json": {"results": results}}]}})
            elif tu["name"] == "search_hypotheses":
                # Over the six-search execution cap: do NOT run search; return a deterministic
                # budget-exhausted tool result so the toolUseId is answered and the model is
                # told to submit.
                print(f"    [runner] turn {turn}: SEARCH_BUDGET_EXHAUSTED "
                      f"(cap={MAX_SEARCH_CALLS}) -- excess search not executed", flush=True)
                tool_results.append({"toolResult": {"toolUseId": tu["toolUseId"],
                                     "content": [{"json": {
                                         "status": "SEARCH_BUDGET_EXHAUSTED",
                                         "max_search_calls": MAX_SEARCH_CALLS,
                                         "search_calls_used": search_calls,
                                         "instruction": "search budget is exhausted; call "
                                                        "submit_selections now with the best "
                                                        "hypotheses you currently support "
                                                        "(zero is valid)"}}]}})
            else:
                tool_results.append({"toolResult": {"toolUseId": tu["toolUseId"],
                                     "content": [{"json": {"error": "unknown tool"}}],
                                     "status": "error"}})
        messages.append({"role": "user", "content": tool_results})

    # Reaching here means the mechanically-derived hard ceiling was hit without the forced
    # submit turn resolving -- treated as an explicit orchestration failure, never fabrication.
    return RunResult("ORCHESTRATION_TURN_CEILING", None, [],
                     {**base_manifest,
                      **_acct(termination_reason="HARD_TURN_CEILING",
                              error=f"exceeded mechanically-derived MAX_TOOL_TURNS="
                                    f"{max_tool_turns} without terminal submission")})


def version_stamp() -> dict:
    return {"runner_version": "v8b1_runner_v3_true_search_cap",
            "max_search_calls": MAX_SEARCH_CALLS,
            "search_budget_is_true_execution_cap": True,
            "excess_search_tool_result": "SEARCH_BUDGET_EXHAUSTED",
            "final_forced_submit_calls": FINAL_FORCED_SUBMIT_CALLS,
            "max_tool_turns": MAX_TOOL_TURNS,
            "termination_contract": "BOUNDED_SEARCH_THEN_FORCED_SUBMIT",
            "forced_submit_disables_thinking": True,
            "cache_dir": CACHE_DIR, "cross_model_cache_poisoning_guard": True,
            "unknown_hypothesis_id_rejected": True,
            "abstain_is_valid": True, "never_fabricates": True}
