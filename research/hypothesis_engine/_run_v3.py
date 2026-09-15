"""Execute the frozen SONNET46_HYPOTHESIS_V3 battery.

Lives OUTSIDE `src/research/hypothesis_engine/` on purpose: that package must never import
Bedrock (enforced by tests/research/hypothesis_engine/test_architecture_isolation.py).

This runner is TRANSPORT + PROVENANCE ONLY. It makes no scientific choice. Every packet,
prompt, schema, parameter, threshold and stop rule is read from the frozen V3 manifest and
the frozen V3 modules. After the first paid call nothing here repairs, retries, salvages or
reinterprets a response: a failed response is recorded verbatim and never overwritten.

STOP RULE (frozen, applied exactly as preregistered in verdict_v3.STOP_RULE)
---------------------------------------------------------------------------
  numerator   completed calls whose WHOLE-RESPONSE failure is EXACTLY SCHEMA_INVALID,
              as decided by the frozen `validator_v2.validate`. Numerical-authority
              violations, latent-grading violations, per-hypothesis rejections and
              compiler failures are explicitly NOT counted.
  denominator completed calls so far, in frozen seq order. An INFRASTRUCTURE_CENSORED
              call never reached the model, so it is in neither numerator nor denominator.
  checkpoints after 12 / 24 / 36 / 48 / 56 completed calls, minimum N 12
  threshold   >= 0.25  ->  stop immediately, preserve everything, no salvage, no resume

SPEND CEILING
-------------
$10.37, enforced BEFORE each request using the frozen calibrated methodology
(chars/4 x 1.5938, floored by the observed actual/estimate ratio once one exists, and
charging the full maxTokens for the pending call's output). If the next call could cross
the ceiling the run stops before issuing it.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src")

from research.hypothesis_engine import (capability, prompt_v2 as PROMPT, schema_v2 as SCH,
                                        lifecycle, validator_v2, verdict_v3)

OUT = f"{ROOT}/research/hypothesis_engine/out"
MAN_PATH = f"{OUT}/PRESPEND_MANIFEST_sonnet46_v3.json"
PKT_PATH = f"{OUT}/MATERIALIZED_PACKETS_sonnet46_v3.json"
RUN_DIR = f"{OUT}/hypothesis_v3_sonnet46"
CACHE = f"{RUN_DIR}/cache"
STATES = f"{RUN_DIR}/hypothesis_states.jsonl"
LEDGER = f"{RUN_DIR}/execution_ledger.json"
CALLCSV = f"{RUN_DIR}/call_manifest.csv"

FROZEN_MANIFEST_HASH = (
    "cfd9244067c9dc0ca18140f1d02460e9833b1df820cff7070713df6f6f8cce3f")

CEILING_USD = 10.3694
PRICE_IN_1K = 0.003
PRICE_OUT_1K = 0.015
REGION = "us-east-1"
TOOL_NAME = "submit_hypotheses"

#: Frozen calibration from the preregistration: chars/4 understates the real tokeniser by
#: this factor (measured on V2's actual billing). Used as the FLOOR of the spend guard so
#: the projection can never under-predict.
CALIBRATION = 1.5938

STOP = verdict_v3.STOP_RULE
STOP_CHECKPOINTS = set(STOP["checkpoints_after_call_number"])
STOP_MIN_N = STOP["minimum_n_before_evaluation"]
STOP_THRESHOLD = STOP["threshold"]


def cache_key(model_id, packet_hash, seq, control, prompt_hash, schema_hash) -> str:
    """Discriminates on seq: `reference::X` and `repeatability::X` are the SAME packet with
    the SAME hash by design, so a packet-hash-only key would serve the reference response
    to the repeatability call and make the stability measurement vacuously 1.0."""
    return hashlib.sha256("|".join(
        [model_id, prompt_hash, schema_hash, packet_hash, str(seq), control]
    ).encode()).hexdigest()


def extract_tool_input(resp: dict):
    for block in resp.get("output", {}).get("message", {}).get("content", []):
        if "toolUse" in block:
            return block["toolUse"]["input"]
    return None


def manifest_of(packet: dict):
    cm = packet["capability_manifest"]
    return capability.FixtureCapabilityManifest(
        fixture_id=cm["fixture_id"],
        available_metrics=tuple(cm["available_metrics"]),
        available_dimensions=tuple(cm["available_dimensions"]),
        unsupported_context=dict(cm.get("unsupported_context") or {}),
        coverage=dict(cm.get("coverage") or {}),
        notes=tuple(cm.get("notes") or ()))


def whole_response_failure(raw, packet):
    """The frozen validator's whole-response verdict. No local logic, no reinterpretation."""
    res = validator_v2.validate(
        raw, packet=packet, manifest=manifest_of(packet),
        expected_packet_hash=packet.get("packet_hash"),
        expected_fixture_id=packet.get("fixture_id"))
    return res.failure


def _append(path: str, rec: dict) -> None:
    """Append + flush + fsync immediately: a mid-run death must never lose paid spend."""
    with open(path, "a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def main(limit=None, dry=False) -> int:
    man = json.load(open(MAN_PATH))
    packets = json.load(open(PKT_PATH))
    model_id = man["bedrock_identity"]["requested_model_id"]
    p_hash, s_hash = man["prompt_content_hash"], man["schema_content_hash"]
    inference = dict(man["bedrock_identity"]["inference_config"])

    # ---- hard preflight: refuse to spend if anything drifted -------------------------
    assert PROMPT.prompt_content_hash() == p_hash, "PROMPT DRIFT"
    assert SCH.schema_content_hash() == s_hash, "SCHEMA DRIFT"
    assert man["manifest_hash"] == FROZEN_MANIFEST_HASH, "MANIFEST DRIFT"
    recomputed = hashlib.sha256(json.dumps(
        {k: v for k, v in man.items() if k != "manifest_hash"},
        sort_keys=True, default=str).encode()).hexdigest()
    assert recomputed == FROZEN_MANIFEST_HASH, "MANIFEST SELF-HASH DRIFT"
    specs = sorted(man["call_specs"], key=lambda c: c["seq"])
    assert len(specs) == 56 and {c["seq"] for c in specs} == set(range(56)), \
        "CALL PLAN DRIFT"
    for c in specs:
        pk = packets[c["packet_key"]]
        assert pk["packet_hash"] == c["resulting_packet_hash"], f"PACKET DRIFT {c['seq']}"
        req = (PROMPT.system_prompt() + PROMPT.build_user_message(pk)
               + json.dumps(PROMPT.tool_spec(), sort_keys=True))
        assert hashlib.sha256(req.encode()).hexdigest() == c["serialized_request_sha256"],\
            f"SERIALIZED REQUEST DRIFT {c['seq']}"
    print("PREFLIGHT CLEAN: manifest, prompt, schema, 56 packets and 56 serialized "
          "requests all match their frozen hashes")
    if dry:
        print("DRY RUN: no Bedrock call issued")
        return 0

    os.makedirs(CACHE, exist_ok=True)

    # ---- resume-safe state ------------------------------------------------------------
    done, prior = set(), []
    if os.path.exists(STATES):
        for line in open(STATES):
            if line.strip():
                r = json.loads(line)
                done.add(r["seq"])
                prior.append(r)
    print(f"already recorded: {len(done)} / 56")

    tot_in = sum(r.get("input_tokens") or 0 for r in prior)
    tot_out = sum(r.get("output_tokens") or 0 for r in prior)
    # Only calls that ACTUALLY BILLED may contribute to the chars/4 baseline. An
    # INFRASTRUCTURE_CENSORED row is in `done` but contributed zero input tokens, so
    # including it would inflate `est_in_seen` relative to `tot_in`, depress the observed
    # ratio, and make the spend guard under-predict on a resume -- the exact direction the
    # CALIBRATION floor exists to prevent.
    billed_seqs = {r["seq"] for r in prior if r.get("input_tokens")}
    est_in_seen = 0
    for c in specs:
        if c["seq"] in billed_seqs:
            est_in_seen += c["input_tokens"]
    n_complete = sum(1 for r in prior if r.get("outcome") in
                     ("COMPLETED", "MODEL_NO_TOOL_USE"))
    n_infra = sum(1 for r in prior if r.get("outcome") == "INFRASTRUCTURE_CENSORED")
    n_schema_invalid = sum(1 for r in prior
                           if r.get("whole_response_failure") == lifecycle.SCHEMA_INVALID)

    import boto3
    client = boto3.client("bedrock-runtime", region_name=REGION)
    system, tool = PROMPT.system_prompt(), PROMPT.tool_spec()
    tool_cfg = {"tools": [{"toolSpec": tool}],
                "toolChoice": {"tool": {"name": TOOL_NAME}}}

    n_attempt = 0
    ceiling_hit = False
    stop_triggered = False
    stop_detail = None

    for spec in specs:
        seq = spec["seq"]
        if seq in done:
            continue
        if limit is not None and n_attempt >= limit:
            break
        pkt = packets[spec["packet_key"]]

        # ---- frozen spend gate BEFORE the request ------------------------------------
        est_in = spec["input_tokens"]
        ratio = max(CALIBRATION, (tot_in / est_in_seen) if est_in_seen else CALIBRATION)
        proj_in = int(est_in * ratio)
        projected = ((tot_in + proj_in) / 1000 * PRICE_IN_1K
                     + (tot_out + inference["maxTokens"]) / 1000 * PRICE_OUT_1K)
        if projected > CEILING_USD:
            print(f"\nSONNET46_V3_SPEND_CEILING_REACHED before seq={seq} "
                  f"(projected ${projected:.4f} > ${CEILING_USD})")
            ceiling_hit = True
            break

        user = PROMPT.build_user_message(pkt)
        key = cache_key(model_id, pkt["packet_hash"], seq, spec["control"], p_hash, s_hash)
        n_attempt += 1
        t0 = time.time()
        rec = {"seq": seq, "control": spec["control"],
               "fixture_id": spec["source_fixture"], "packet_key": spec["packet_key"],
               "packet_hash": pkt["packet_hash"],
               "source_packet_hash": spec["source_packet_hash"],
               "transformation": spec.get("transformation"),
               "transformation_version": spec.get("transformation_version"),
               "transformation_params": spec.get("transformation_params"),
               "serialized_request_sha256": spec["serialized_request_sha256"],
               "model_id": model_id, "cache_key": key,
               "prompt_content_hash": p_hash, "schema_content_hash": s_hash,
               "manifest_hash": FROZEN_MANIFEST_HASH,
               "inference_config": dict(inference), "cache_hit": False}

        try:
            resp = client.converse(
                modelId=model_id, system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                toolConfig=tool_cfg, inferenceConfig=inference)
        except Exception as e:
            # INFRASTRUCTURE failure: never reached the model. Zero retries -- retry
            # semantics were not frozen. Excluded from the stop rule's numerator AND
            # denominator, because it is not a completed call.
            n_infra += 1
            rec.update(outcome="INFRASTRUCTURE_CENSORED",
                       error=f"{type(e).__name__}: {e}",
                       latency_s=round(time.time() - t0, 3))
            _append(STATES, rec)
            print(f"  seq {seq:>2} {spec['control']:<26} INFRA_FAIL  {type(e).__name__}")
            continue

        usage = resp.get("usage", {})
        ti, to = usage.get("inputTokens", 0), usage.get("outputTokens", 0)
        tot_in += ti
        tot_out += to
        est_in_seen += est_in
        raw = extract_tool_input(resp)

        # Frozen validator decides the whole-response verdict. Recorded alongside the RAW
        # response; the raw output is never replaced by it.
        failure = whole_response_failure(raw, pkt)

        rec.update(latency_s=round(time.time() - t0, 3), input_tokens=ti,
                   output_tokens=to, stop_reason=resp.get("stopReason"),
                   resolved_model_id=resp.get("ResponseMetadata", {})
                   .get("HTTPHeaders", {})
                   .get("x-amzn-bedrock-invocation-model-id", model_id),
                   raw_response=raw,
                   whole_response_failure=failure)
        rec["outcome"] = "COMPLETED" if raw is not None else "MODEL_NO_TOOL_USE"
        n_complete += 1
        if failure == lifecycle.SCHEMA_INVALID:
            n_schema_invalid += 1

        # write-once raw cache; a failed response is preserved, never overwritten
        cp = f"{CACHE}/{key}.json"
        if not os.path.exists(cp):
            json.dump({"seq": seq, "raw": raw, "usage": usage,
                       "stop_reason": resp.get("stopReason")},
                      open(cp, "w"), indent=1, sort_keys=True)
        _append(STATES, rec)

        cost = tot_in / 1000 * PRICE_IN_1K + tot_out / 1000 * PRICE_OUT_1K
        print(f"  seq {seq:>2} {spec['control']:<26} {rec['outcome']:<17} "
              f"in={ti:>6} out={to:>5} fail={str(failure):<28} ${cost:.3f}")

        # ---- FROZEN STOP RULE, evaluated only at the frozen checkpoints --------------
        if n_complete in STOP_CHECKPOINTS and n_complete >= STOP_MIN_N:
            rate = n_schema_invalid / n_complete
            print(f"    [checkpoint {n_complete}] SCHEMA_INVALID "
                  f"{n_schema_invalid}/{n_complete} = {rate:.4f} "
                  f"(threshold >= {STOP_THRESHOLD})")
            if rate >= STOP_THRESHOLD:
                stop_triggered = True
                stop_detail = {"checkpoint_completed_calls": n_complete,
                               "n_schema_invalid": n_schema_invalid,
                               "rate": round(rate, 4),
                               "threshold": STOP_THRESHOLD}
                print(f"\nFROZEN STOP RULE TRIGGERED at checkpoint {n_complete}: "
                      f"{rate:.4f} >= {STOP_THRESHOLD}")
                break

    cost = tot_in / 1000 * PRICE_IN_1K + tot_out / 1000 * PRICE_OUT_1K
    ledger = {
        "experiment_id": man["experiment_id"],
        "model_id": model_id,
        "manifest_hash": man["manifest_hash"],
        "battery_hash": man["battery_hash"],
        "prompt_content_hash": p_hash,
        "schema_content_hash": s_hash,
        "inference_config_sent": dict(inference),
        "retry_policy": "ZERO retries; retry semantics were not frozen.",
        "planned_calls": 56,
        "attempted_calls_this_process": n_attempt,
        "completed_calls": n_complete,
        "cache_hits": 0,
        "retries": 0,
        "infrastructure_censored_calls": n_infra,
        "schema_invalid_calls": n_schema_invalid,
        "schema_invalid_rate": (round(n_schema_invalid / n_complete, 4)
                                if n_complete else None),
        "input_tokens": tot_in,
        "output_tokens": tot_out,
        "total_tokens": tot_in + tot_out,
        "estimated_input_tokens_chars4": est_in_seen,
        "actual_to_chars4_ratio": (round(tot_in / est_in_seen, 4)
                                   if est_in_seen else None),
        "frozen_calibration_factor": CALIBRATION,
        "cost_usd_from_actual_tokens": round(cost, 4),
        "price_per_1k_input_usd": PRICE_IN_1K,
        "price_per_1k_output_usd": PRICE_OUT_1K,
        "ceiling_usd": CEILING_USD,
        "remaining_under_ceiling_usd": round(CEILING_USD - cost, 4),
        "spend_ceiling_reached": ceiling_hit,
        "stop_rule": dict(STOP),
        "stop_rule_triggered": stop_triggered,
        "stop_rule_detail": stop_detail,
    }
    json.dump(ledger, open(LEDGER, "w"), indent=2, sort_keys=True)

    rows = [json.loads(l) for l in open(STATES) if l.strip()]
    with open(CALLCSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["seq", "control", "fixture_id", "packet_hash", "outcome",
                    "whole_response_failure", "input_tokens", "output_tokens",
                    "stop_reason", "cache_key"])
        for r in sorted(rows, key=lambda r: r["seq"]):
            w.writerow([r["seq"], r["control"], r["fixture_id"], r["packet_hash"],
                        r["outcome"], r.get("whole_response_failure"),
                        r.get("input_tokens"), r.get("output_tokens"),
                        r.get("stop_reason"), r["cache_key"]])

    print(f"\nrecorded {len(rows)}/56   cost ${cost:.4f}   "
          f"remaining ${CEILING_USD - cost:.4f}")
    if stop_triggered:
        print("STOP RULE TRIGGERED -- no further calls; no verdict from a partial battery")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    dry = "--dry" in args
    lim = next((int(a) for a in args if a.isdigit()), None)
    sys.exit(main(lim, dry))
