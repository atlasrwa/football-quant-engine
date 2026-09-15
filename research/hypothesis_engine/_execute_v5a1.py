"""Execute the frozen V5A.1 38-call battery. PAID. Authorized ceiling $7.69.

Executes EXACTLY the preregistered manifest. No retries (none were preregistered), no
fixture replacement, no prompt alteration, no response filtering. Every call is verified
against its frozen request hash and scanned for treatment labels BEFORE it is sent.

Append-only, write-once: `execution_log.jsonl` is the immutable record. A record is never
rewritten, and a raw model response is never modified.
"""
from __future__ import annotations

import hashlib, json, os, sys, time, datetime

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import lifecycle, schema_v2, validator_v3, firewall_v3
from src.research.hypothesis_engine import query_plan as QP
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a1_prompt as P

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v5a1"
RUN = f"{OUT}/execution"
LOG = f"{RUN}/execution_log.jsonl"
RAW = f"{RUN}/raw"

REGION = "us-east-1"
TOOL_NAME = "submit_hypotheses"
CEILING_USD = 7.6947                # frozen hard ceiling; never raised
PRICE_IN_1K = 0.003
PRICE_OUT_1K = 0.015
MAX_CONSECUTIVE_INFRA = 3           # frozen stop rule
SCHEMA_INVALID_RATE_STOP = 0.30     # frozen stop rule


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _append(rec):
    with open(LOG, "a") as fh:
        fh.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def tool_spec():
    return {"name": TOOL_NAME,
            "description": ("Submit grounded, falsifiable football research questions for "
                            "this fixture. Questions only: no probabilities, odds, edges, "
                            "predictions, strength grades or observed values as numbers."),
            "inputSchema": {"json": schema_v2.build_schema()}}


def extract_tool_input(resp):
    for block in resp.get("output", {}).get("message", {}).get("content", []):
        if "toolUse" in block:
            return block["toolUse"]["input"]
    return None


def call_specs(prereg):
    """Expand the frozen manifest into exactly 38 ordered call specs."""
    specs, seq = [], 0
    for c in prereg["request_manifest"]["calls"]:
        for rep in range(c["n_calls"]):
            seq += 1
            specs.append({"seq": seq, "fixture_id": c["fixture_id"],
                          "arm_internal": c["arm_internal"], "replicate": rep,
                          "is_repeat": rep > 0,
                          "serialized_request_sha256": c["serialized_request_sha256"],
                          "packet_hash": c["packet_hash"],
                          "est_input_tokens": c["est_input_tokens"]})
    return specs


def main():
    os.makedirs(RAW, exist_ok=True)
    prereg = json.load(open(f"{OUT}/PREREGISTRATION.json"))
    packets = {"base": json.load(open(f"{OUT}/packets_base.json")),
               "research": json.load(open(f"{OUT}/packets_research.json"))}
    man = prereg["request_manifest"]
    model_id = man["model_id"]
    inference = {"temperature": man["temperature"], "maxTokens": man["max_tokens"]}

    # ---- resume: never re-send a completed sequence -----------------------------------
    done = {}
    if os.path.exists(LOG):
        for line in open(LOG):
            r = json.loads(line)
            if r.get("outcome") in ("COMPLETED", "MODEL_NO_TOOL_USE"):
                done[r["seq"]] = r
    tot_in = sum(r.get("input_tokens", 0) for r in done.values())
    tot_out = sum(r.get("output_tokens", 0) for r in done.values())

    specs = call_specs(prereg)
    assert len(specs) == 38, f"expected 38 calls, manifest expands to {len(specs)}"

    import boto3
    client = boto3.client("bedrock-runtime", region_name=REGION)
    tool_cfg = {"tools": [{"toolSpec": tool_spec()}],
                "toolChoice": {"tool": {"name": TOOL_NAME}}}

    consec_infra = 0
    n_complete = len(done)
    n_schema_invalid = 0
    stop = None

    print(f"V5A.1 execution | model={model_id} | ceiling ${CEILING_USD} | "
          f"{len(specs) - len(done)} calls to run")

    for spec in specs:
        seq = spec["seq"]
        if seq in done:
            continue
        pk = packets[spec["arm_internal"]][spec["fixture_id"]]

        # ---- pre-send integrity: hash + blinding -------------------------------------
        req = P.serialized_request(pk)
        rh = _sha(req)
        if rh != spec["serialized_request_sha256"]:
            stop = ("V5A1_EXECUTION_ABORTED_HASH_DRIFT",
                    f"seq {seq}: request hash {rh} != frozen "
                    f"{spec['serialized_request_sha256']}")
            break
        if E.packet_hash(pk) != spec["packet_hash"]:
            stop = ("V5A1_EXECUTION_ABORTED_HASH_DRIFT",
                    f"seq {seq}: packet hash drift")
            break
        low = req.lower()
        leaked = [t for t in ("arm_a", "arm_b", "full_fidelity", "b_full_fidelity",
                              "condition_a", "condition_b", "experiment_arm",
                              "treatment_arm", "baseline_arm") if t in low]
        if leaked:
            stop = ("V5A1_EXECUTION_ABORTED_TREATMENT_LABEL_LEAK",
                    f"seq {seq}: {leaked}")
            break

        # ---- frozen spend gate BEFORE the request ------------------------------------
        projected = ((tot_in + spec["est_input_tokens"]) / 1000 * PRICE_IN_1K
                     + (tot_out + inference["maxTokens"]) / 1000 * PRICE_OUT_1K)
        if projected > CEILING_USD:
            stop = ("V5A1_EXECUTION_STOPPED_COST_CEILING",
                    f"projected ${projected:.4f} > ${CEILING_USD} before seq {seq}")
            break

        rec = {"seq": seq, "fixture_id": spec["fixture_id"],
               "arm_internal": spec["arm_internal"], "replicate": spec["replicate"],
               "is_repeat": spec["is_repeat"],
               "serialized_request_sha256": rh,
               "request_bytes": len(req),
               "packet_hash": pk["packet_hash"],
               "model_id": model_id, "region": REGION,
               "inference_config": dict(inference),
               "prompt_version": P.V5A1_PROMPT_VERSION,
               "schema_version": schema_v2.SCHEMA_VERSION,
               "schema_content_hash": schema_v2.schema_content_hash(),
               "retry_count": 0,
               "start_utc": _now()}
        t0 = time.time()
        try:
            resp = client.converse(
                modelId=model_id, system=[{"text": P.SYSTEM_PROMPT}],
                messages=[{"role": "user", "content": [{"text": P.build_user_payload(pk)}]}],
                toolConfig=tool_cfg, inferenceConfig=inference)
        except Exception as e:
            consec_infra += 1
            rec.update(outcome="INFRASTRUCTURE_CENSORED", end_utc=_now(),
                       latency_s=round(time.time() - t0, 3),
                       error=f"{type(e).__name__}: {str(e)[:400]}",
                       infrastructure_state="TRANSPORT_FAILURE")
            _append(rec)
            print(f"  seq {seq:>2} {spec['fixture_id']} {spec['arm_internal']:<8} "
                  f"INFRA_FAIL {type(e).__name__}")
            if consec_infra >= MAX_CONSECUTIVE_INFRA:
                stop = ("V5A1_EXECUTION_STOPPED_INFRASTRUCTURE",
                        f"{consec_infra} consecutive transport failures")
                break
            continue

        consec_infra = 0
        usage = resp.get("usage", {}) or {}
        ti, to = usage.get("inputTokens", 0), usage.get("outputTokens", 0)
        tot_in += ti
        tot_out += to
        raw = extract_tool_input(resp)
        cost = tot_in / 1000 * PRICE_IN_1K + tot_out / 1000 * PRICE_OUT_1K

        # frozen validator/firewall verdict, recorded ALONGSIDE the raw response
        vres = validator_v3.validate(raw, packet=pk,
                                     expected_packet_hash=pk["packet_hash"],
                                     expected_fixture_id=pk["fixture_id"]) if raw else None

        rec.update(
            outcome="COMPLETED" if raw is not None else "MODEL_NO_TOOL_USE",
            end_utc=_now(), latency_s=round(time.time() - t0, 3),
            input_tokens=ti, output_tokens=to,
            stop_reason=resp.get("stopReason"),
            bedrock_request_id=resp.get("ResponseMetadata", {}).get("RequestId"),
            bedrock_http_status=resp.get("ResponseMetadata", {}).get("HTTPStatusCode"),
            resolved_model_id=resp.get("ResponseMetadata", {}).get("HTTPHeaders", {})
            .get("x-amzn-bedrock-invocation-model-id", model_id),
            infrastructure_state="OK",
            raw_response=raw,
            call_cost_usd=round(ti / 1000 * PRICE_IN_1K + to / 1000 * PRICE_OUT_1K, 6),
            cumulative_cost_usd=round(cost, 6),
            validation_accepted=(vres.accepted if vres else None),
            validation_failure=(vres.failure if vres else "NO_TOOL_USE"),
            validation_reasons=(list(vres.reasons) if vres else []),
            accepted_hypotheses=([h.get("hypothesis_id")
                                  for h in vres.accepted_hypotheses] if vres else []),
            rejected_hypotheses=([{"hypothesis_id": v.hypothesis_id,
                                   "failure": v.failure, "reasons": list(v.reasons)}
                                  for v in vres.verdicts if not v.accepted]
                                 if vres else []),
            firewall_findings=([f.to_dict() for f in vres.firewall_findings]
                               if vres else []))
        if vres and vres.failure == lifecycle.SCHEMA_INVALID:
            n_schema_invalid += 1
        n_complete += 1

        # write-once raw cache
        cp = f"{RAW}/seq_{seq:02d}_{spec['fixture_id']}_{spec['arm_internal']}.json"
        if not os.path.exists(cp):
            json.dump({"seq": seq, "raw": raw, "usage": usage,
                       "stop_reason": resp.get("stopReason")},
                      open(cp, "w"), indent=1, sort_keys=True, default=str)
        _append(rec)
        print(f"  seq {seq:>2} {spec['fixture_id']} {spec['arm_internal']:<8} "
              f"rep{spec['replicate']} in={ti:>6} out={to:>5} "
              f"acc={len(rec['accepted_hypotheses']):>2}/"
              f"{len((raw or {}).get('hypotheses') or []):<2} "
              f"cum=${cost:.4f}")

        if n_complete >= 5 and (n_schema_invalid / n_complete) > SCHEMA_INVALID_RATE_STOP:
            stop = ("V5A1_EXECUTION_STOPPED_SCHEMA_INVALID_RATE",
                    f"{n_schema_invalid}/{n_complete} > {SCHEMA_INVALID_RATE_STOP}")
            break

    final = {"completed": n_complete, "total_input_tokens": tot_in,
             "total_output_tokens": tot_out,
             "actual_cost_usd": round(tot_in / 1000 * PRICE_IN_1K
                                      + tot_out / 1000 * PRICE_OUT_1K, 6),
             "ceiling_usd": CEILING_USD, "stop": stop,
             "schema_invalid": n_schema_invalid}
    json.dump(final, open(f"{RUN}/execution_summary.json", "w"), indent=1, sort_keys=True)
    print(json.dumps(final, indent=1))
    return 0 if stop is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
