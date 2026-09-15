"""Execute the frozen SONNET46_HYPOTHESIS_V2 battery.

Lives OUTSIDE `src/research/hypothesis_engine/` on purpose: that package must never
import Bedrock (enforced by tests/research/hypothesis_engine/test_architecture_isolation.py).
This runner is transport + provenance only. It makes NO scientific choice: every packet,
prompt, schema and parameter is read from the frozen V2 manifest or the frozen
FREEZE_LLM_MATCHUP_V3_SONNET46 inference config.

Frozen-design rule: after the first paid call nothing here repairs, retries, salvages or
reinterprets a response. A failed response is recorded verbatim and never overwritten.
"""
from __future__ import annotations

import csv, hashlib, json, os, sys, time

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src")

from research.hypothesis_engine import prompt as PROMPT

OUT      = f"{ROOT}/research/hypothesis_engine/out"
MAN_PATH = f"{OUT}/PRESPEND_MANIFEST_sonnet46_v2.json"
PKT_PATH = f"{OUT}/MATERIALIZED_PACKETS_sonnet46_v2.json"
RUN_DIR  = f"{OUT}/hypothesis_v1_sonnet46_v2"
CACHE    = f"{RUN_DIR}/cache"
STATES   = f"{RUN_DIR}/hypothesis_states.jsonl"
LEDGER   = f"{RUN_DIR}/execution_ledger.json"
CALLCSV  = f"{RUN_DIR}/call_manifest.csv"

CEILING_USD   = 9.15
PRICE_IN_1K   = 0.003
PRICE_OUT_1K  = 0.015
REGION        = "us-east-1"
# Frozen in research/llm_matchup/out/FREEZE_LLM_MATCHUP_V3_SONNET46.json, which the V2
# manifest names as its identity source: {"temperature":0.0,"topP":1.0,"maxTokens":8192}.
# topP is omitted from the wire call exactly as the frozen 4.6 adapter path does (some
# Sonnet models reject temperature+topP together); topP=1.0 is the API default and a
# no-op under temperature=0.0, so the sampling distribution is identical.
INFERENCE = {"temperature": 0.0, "maxTokens": 8192}
TOOL_NAME = "submit_hypotheses"
RATIO_FLOOR = 1.7   # conservative floor for actual-tokens / (chars/4) estimate


def cache_key(model_id: str, packet_hash: str, seq: int, control: str,
              prompt_hash: str, schema_hash: str) -> str:
    """Discriminates on seq. `reference::X` and `repeatability::X` are the SAME packet with
    the SAME hash by design; a packet-hash-only key (the legacy llm_matchup convention)
    would serve the reference response to the repeatability call and make the stability
    measurement vacuously 1.0. The manifest preregisters 64 paid calls / 0 cache hits, so
    each seq must be its own key."""
    return hashlib.sha256("|".join(
        [model_id, prompt_hash, schema_hash, packet_hash, str(seq), control]
    ).encode()).hexdigest()


def extract_tool_input(resp: dict):
    for block in resp.get("output", {}).get("message", {}).get("content", []):
        if "toolUse" in block:
            return block["toolUse"]["input"]
    return None


def main(limit: int | None = None) -> int:
    man = json.load(open(MAN_PATH))
    packets = json.load(open(PKT_PATH))
    model_id = man["model_id"]
    p_hash, s_hash = man["prompt_content_hash"], man["schema_content_hash"]

    # ---- hard preflight: refuse to spend if anything drifted -------------------------
    assert PROMPT.prompt_content_hash() == p_hash, "PROMPT DRIFT"
    from research.hypothesis_engine import schema as SCH
    assert SCH.schema_content_hash() == s_hash, "SCHEMA DRIFT"
    assert man["manifest_hash"] == \
        "59964d676af37292b9784d8477dada6a4ba3f982963f42e87ad7feff207421d0", "MANIFEST DRIFT"
    specs = sorted(man["call_specs"], key=lambda c: c["seq"])
    assert len(specs) == 64 and {c["seq"] for c in specs} == set(range(64)), "CALL PLAN DRIFT"

    os.makedirs(CACHE, exist_ok=True)
    done = set()
    if os.path.exists(STATES):                      # resume-safe; never re-call a done seq
        for line in open(STATES):
            if line.strip():
                done.add(json.loads(line)["seq"])
    print(f"already recorded: {len(done)} / 64")

    def _est(pk: dict) -> int:
        return len(PROMPT.system_prompt() + PROMPT.build_user_message(pk)
                   + json.dumps(PROMPT.tool_spec(), sort_keys=True)) // 4


    import boto3
    client = boto3.client("bedrock-runtime", region_name=REGION)
    system, tool = PROMPT.system_prompt(), PROMPT.tool_spec()
    tool_cfg = {"tools": [{"toolSpec": tool}],
                "toolChoice": {"tool": {"name": TOOL_NAME}}}

    tot_in = tot_out = 0
    est_in_seen = 0
    n_attempt = n_complete = n_infra = n_model_reject = 0
    if os.path.exists(LEDGER):
        prev = json.load(open(LEDGER))
        tot_in, tot_out = prev.get("input_tokens", 0), prev.get("output_tokens", 0)
        n_infra = prev.get("infrastructure_censored_calls", 0)
        n_model_reject = prev.get("model_rejected_calls", 0)
        n_complete = prev.get("completed_calls", 0)
    # backfill the chars/4 estimate for every already-recorded call so the
    # actual/estimate ratio stays correct across resumes
    for c in specs:
        if c["seq"] in done:
            est_in_seen += _est(packets[c["packet_key"]])


    ceiling_hit = False
    for spec in specs:
        seq = spec["seq"]
        if seq in done:
            continue
        if limit is not None and n_attempt >= limit:
            break
        pkt = packets[spec["packet_key"]]
        assert pkt["packet_hash"] == spec["resulting_packet_hash"], f"PACKET DRIFT seq={seq}"

        # ---- projected spend gate BEFORE the request ---------------------------------
        est_in = len(PROMPT.system_prompt() + PROMPT.build_user_message(pkt)
                     + json.dumps(tool, sort_keys=True)) // 4
        # The manifest's chars/4 convention UNDERSTATES the real tokeniser (measured ~1.6x
        # on seq 0). The ceiling guard must never under-predict, so scale by the observed
        # actual/estimate ratio once we have one, floored at a conservative 1.7. This is
        # spend-safety arithmetic only: it changes no packet, prompt, schema or score.
        ratio = max(RATIO_FLOOR, (tot_in / est_in_seen) if est_in_seen else RATIO_FLOOR)
        proj_in = int(est_in * ratio)
        projected = ((tot_in + proj_in) / 1000 * PRICE_IN_1K
                     + (tot_out + INFERENCE["maxTokens"]) / 1000 * PRICE_OUT_1K)
        if projected > CEILING_USD:
            print(f"\nSONNET46_V2_SPEND_CEILING_REACHED before seq={seq} "
                  f"(projected ${projected:.4f} > ${CEILING_USD})")
            ceiling_hit = True
            break

        user = PROMPT.build_user_message(pkt)
        key = cache_key(model_id, pkt["packet_hash"], seq, spec["control"], p_hash, s_hash)
        n_attempt += 1
        t0 = time.time()
        rec = {"seq": seq, "control": spec["control"], "fixture_id": spec["source_fixture"],
               "packet_key": spec["packet_key"], "packet_hash": pkt["packet_hash"],
               "source_packet_hash": spec["source_packet_hash"],
               "transformation": spec.get("transformation"),
               "transformation_version": spec.get("transformation_version"),
               "model_id": model_id, "cache_key": key,
               "prompt_content_hash": p_hash, "schema_content_hash": s_hash,
               "inference_config": dict(INFERENCE), "cache_hit": False}
        try:
            resp = client.converse(modelId=model_id, system=[{"text": system}],
                                   messages=[{"role": "user", "content": [{"text": user}]}],
                                   toolConfig=tool_cfg, inferenceConfig=INFERENCE)
        except Exception as e:                      # INFRASTRUCTURE failure. Zero retries:
            n_infra += 1                            # retry semantics were not frozen in V2.
            rec.update(outcome="INFRASTRUCTURE_CENSORED", error=f"{type(e).__name__}: {e}",
                       latency_s=round(time.time() - t0, 3))
            _append(STATES, rec); print(f"  seq {seq:>2} {spec['control']:<22} INFRA_FAIL")
            continue

        usage = resp.get("usage", {})
        ti, to = usage.get("inputTokens", 0), usage.get("outputTokens", 0)
        tot_in += ti; tot_out += to; est_in_seen += est_in
        raw = extract_tool_input(resp)
        rec.update(latency_s=round(time.time() - t0, 3), input_tokens=ti, output_tokens=to,
                   stop_reason=resp.get("stopReason"),
                   resolved_model_id=resp.get("ResponseMetadata", {}).get("HTTPHeaders", {})
                       .get("x-amzn-bedrock-invocation-model-id", model_id),
                   raw_response=raw)
        if raw is None:
            n_model_reject += 1
            rec["outcome"] = "MODEL_NO_TOOL_USE"
        else:
            n_complete += 1
            rec["outcome"] = "COMPLETED"
        # write-once raw cache; a failed response is preserved, never overwritten
        cp = f"{CACHE}/{key}.json"
        if not os.path.exists(cp):
            json.dump({"seq": seq, "raw": raw, "usage": usage,
                       "stop_reason": resp.get("stopReason")},
                      open(cp, "w"), indent=1, sort_keys=True)
        _append(STATES, rec)
        cost = tot_in / 1000 * PRICE_IN_1K + tot_out / 1000 * PRICE_OUT_1K
        print(f"  seq {seq:>2} {spec['control']:<22} {rec['outcome']:<18} "
              f"in={ti:>6} out={to:>5} stop={rec['stop_reason']:<12} ${cost:.3f}")

    cost = tot_in / 1000 * PRICE_IN_1K + tot_out / 1000 * PRICE_OUT_1K
    ledger = {
        "experiment_id": "SONNET46_HYPOTHESIS_V2", "model_id": model_id,
        "manifest_hash": man["manifest_hash"], "battery_hash": man["battery_hash"],
        "prompt_content_hash": p_hash, "schema_content_hash": s_hash,
        "inference_config_frozen": {"temperature": 0.0, "topP": 1.0, "maxTokens": 8192},
        "inference_config_sent": dict(INFERENCE),
        "retry_policy": "ZERO retries: retry semantics were not frozen in V2.",
        "planned_calls": 64, "attempted_calls_this_process": n_attempt,
        "completed_calls": n_complete, "cache_hits": 0, "retries": 0,
        "infrastructure_censored_calls": n_infra, "model_rejected_calls": n_model_reject,
        "input_tokens": tot_in, "output_tokens": tot_out,
        "estimated_input_tokens_chars4": est_in_seen,
        "actual_to_chars4_ratio": round(tot_in / est_in_seen, 4) if est_in_seen else None,
        "total_tokens": tot_in + tot_out,
        "cost_usd_from_actual_tokens": round(cost, 4),
        "price_per_1k_input_usd": PRICE_IN_1K, "price_per_1k_output_usd": PRICE_OUT_1K,
        "ceiling_usd": CEILING_USD, "remaining_under_ceiling_usd": round(CEILING_USD - cost, 4),
        "spend_ceiling_reached": ceiling_hit,
    }
    json.dump(ledger, open(LEDGER, "w"), indent=2, sort_keys=True)

    rows = [json.loads(l) for l in open(STATES) if l.strip()]
    with open(CALLCSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["seq", "control", "fixture_id", "packet_hash", "outcome",
                    "input_tokens", "output_tokens", "stop_reason", "cache_key"])
        for r in sorted(rows, key=lambda r: r["seq"]):
            w.writerow([r["seq"], r["control"], r["fixture_id"], r["packet_hash"],
                        r["outcome"], r.get("input_tokens"), r.get("output_tokens"),
                        r.get("stop_reason"), r["cache_key"]])
    print(f"\nrecorded {len(rows)}/64  cost ${cost:.4f}  remaining ${CEILING_USD-cost:.4f}")
    return 0


def _append(path: str, rec: dict) -> None:
    """Append + flush + fsync immediately: a mid-run death must never lose paid spend."""
    with open(path, "a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
        fh.flush(); os.fsync(fh.fileno())


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else None))
