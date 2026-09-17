"""Targeted live probe of the SEARCH_BUDGET_EXHAUSTED -> forced-submit CONVERSATION-STRUCTURE
path, which the natural cap-canary run did not trigger (the model happened not to burst past
six searches in one response).

This is NOT a research fixture: it sends a tiny synthetic conversation (trivial tool schemas,
no evidence packet, no football content) whose prior user turn contains a tool result with
status SEARCH_BUDGET_EXHAUSTED, then forces submit_selections. It proves ONLY that the Bedrock
Converse API accepts a conversation containing a SEARCH_BUDGET_EXHAUSTED tool result and that
the model can proceed to the forced submit_selections tool on the next turn -- i.e. the
conversation structure the true cap produces is valid transport. No hypothesis quality is
inspected; no target outcome is read.
"""
from __future__ import annotations

import json
import sys

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT)


def main():
    from src.research.hypothesis_v8b1 import runner as RN

    model_config = json.load(open(f"{ROOT}/research/hypothesis_engine/V8B1_MODEL_CONFIG.json"))
    model_id = model_config["model_id"]
    region = model_config["region"]

    client = RN._bedrock_client(region)

    tools = [
        {"toolSpec": {"name": "search_hypotheses", "description": "search",
                      "inputSchema": {"json": {"type": "object", "properties": {
                          "q": {"type": "string"}}}}}},
        {"toolSpec": {"name": "submit_selections", "description": "submit final selections",
                      "inputSchema": {"json": {"type": "object", "properties": {
                          "final_selections": {"type": "array", "items": {"type": "object",
                              "properties": {"hypothesis_id": {"type": "string"}}}}},
                          "required": ["final_selections"]}}}},
    ]

    # Synthetic conversation: assistant asked to search; we answered with a
    # SEARCH_BUDGET_EXHAUSTED tool result (exactly what the true cap emits). Now force submit.
    messages = [
        {"role": "user", "content": [{"text": "Call search_hypotheses once."}]},
        {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "probe1", "name": "search_hypotheses",
                         "input": {"q": "x"}}}]},
        {"role": "user", "content": [
            {"toolResult": {"toolUseId": "probe1", "content": [{"json": {
                "status": "SEARCH_BUDGET_EXHAUSTED", "max_search_calls": 6,
                "search_calls_used": 6,
                "instruction": "search budget is exhausted; call submit_selections now with "
                               "the best hypotheses you currently support (zero is valid)"}}]}}]},
    ]

    print("probing forced submit_selections after a SEARCH_BUDGET_EXHAUSTED tool result...")
    try:
        resp = client.converse(
            modelId=model_id, messages=messages,
            system=[{"text": "You are validating transport. When told the search budget is "
                             "exhausted, call submit_selections. Zero selections is acceptable."}],
            inferenceConfig={"maxTokens": 1024, "temperature": 1.0},
            toolConfig={"tools": tools,
                        "toolChoice": {"tool": {"name": "submit_selections"}}},
        )
    except Exception as e:
        out = {"path_probe": "SEARCH_BUDGET_EXHAUSTED_forced_submit",
               "api_accepted_conversation": False, "error": f"{type(e).__name__}: {e}"}
        _write(out)
        print("FAILED:", out["error"])
        return

    msg = resp["output"]["message"]
    tool_uses = [b["toolUse"] for b in msg.get("content", []) if "toolUse" in b]
    submitted = any(tu["name"] == "submit_selections" for tu in tool_uses)
    usage = resp.get("usage", {})
    out = {
        "path_probe": "SEARCH_BUDGET_EXHAUSTED_forced_submit",
        "api_accepted_conversation": True,
        "stop_reason": resp.get("stopReason"),
        "model_emitted_submit_selections": submitted,
        "usage": usage,
        "model_id": model_id,
        "note": "synthetic transport/structure probe; no evidence packet, no football content, "
                "no target outcome. Validates only that a SEARCH_BUDGET_EXHAUSTED tool result "
                "yields a valid conversation and the forced submit_selections tool fires.",
    }
    _write(out)
    print(json.dumps(out, indent=1, default=str))


def _write(out):
    path = f"{ROOT}/research/hypothesis_engine/V8B1_CAP_PATHPROBE_RESULTS.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
