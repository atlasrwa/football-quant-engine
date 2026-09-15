"""V5A.2 execution driver. RUNS NOTHING UNLESS EXPLICITLY AUTHORIZED.

`main()` refuses to start without `--i-have-authorization`, so importing, hashing or
reading this file costs nothing. It is written and hashed into the preregistration BEFORE
authorization precisely so the human is authorizing a known driver rather than one written
after the fact.

WHAT THIS DRIVER ASSERTS THAT V5A.1'S DID NOT
---------------------------------------------
S16  Transport preflight runs at spend == 0.0, before the first request is constructed.
     V5A.1 burned its authorization on three AttributeErrors because the environment
     requirement lived in the authorization prose and nothing checked it.
S17  `TransportAccounting` separates attempted / charged / transport-failed calls, so a
     failed call can never inflate the spend estimate and a stop rule can tell the two
     apart.
S15  Stop rules are evaluated by the FROZEN evaluator's `classify_stop`, which separates
     MODEL_SCHEMA_INVALID from INFRASTRUCTURE_CONTRACT_FAILURE. V5A.1's single rule fired
     on two apparatus failures and reported the run as a model discipline problem.
S31  Packet and module hashes are re-verified against the preregistration before the first
     paid call; any mismatch aborts at zero spend.

Every response is written to disk immutably BEFORE it is scored, so a scoring bug can never
destroy paid data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import schema_v3, validator_v4 as V4
from src.research.hypothesis_oos import v5a2_evaluator as EV
from src.research.hypothesis_oos import v5a2_prompt as PR
from src.research.hypothesis_oos import v5a2_transport as TRN

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v5a2"
EXEC_DIR = f"{OUT}/execution"
REGION = "us-east-1"


def _sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def reverify(prereg) -> list:
    """Task S31: nothing frozen may have moved. Returns problems; empty means proceed."""
    problems = []
    for rel, sha in sorted(prereg["module_hashes"].items()):
        if rel.endswith("_execute_v5a2.py"):
            continue
        got = _sha_file(f"{ROOT}/{rel}")
        if got != sha:
            problems.append(f"module {rel} changed since freeze ({got[:12]} != "
                            f"{sha[:12]})")
    for rel, sha in sorted(prereg["frozen_upstream_module_hashes"].items()):
        got = _sha_file(f"{ROOT}/{rel}")
        if got != sha:
            problems.append(f"FROZEN upstream module {rel} was modified ({got[:12]} != "
                            f"{sha[:12]})")
    if schema_v3.schema_content_hash() != \
            prereg["request_manifest"]["schema_content_hash"]:
        problems.append("schema_v3 content hash differs from the preregistered one")

    packets = {arm: json.load(open(f"{OUT}/packets_{arm}.json"))
               for arm in ("base", "research")}
    for call in prereg["request_manifest"]["calls"]:
        pk = packets[call["arm"]][call["fixture_id"]]
        if pk["packet_hash"] != call["packet_hash"]:
            problems.append(f"packet hash drift {call['arm']}/{call['fixture_id']}")
        if hashlib.sha256(PR.serialized_request(pk).encode()).hexdigest() != \
                call["serialized_request_sha256"]:
            problems.append(f"request bytes drift {call['arm']}/{call['fixture_id']}")

    champ = prereg["champion_protection"]
    if _sha_file(champ["artifact"]) != champ["frozen_sha256"]:
        problems.append("CHAMPION artifact changed")
    return problems


def build_client():
    import boto3
    return boto3.client("bedrock-runtime", region_name=REGION)


def call_once(client, prereg, packet, seq, log):
    """One Converse call with forced tool use. Returns (payload|None, in_tok, out_tok)."""
    rm = prereg["request_manifest"]
    tool = {"toolSpec": {"name": "emit_hypotheses",
                         "description": "Return the hypothesis set.",
                         "inputSchema": {"json": schema_v3.build_schema()}}}
    resp = client.converse(
        modelId=rm["model_id"],
        system=[{"text": PR.SYSTEM_PROMPT}],
        messages=[{"role": "user",
                   "content": [{"text": PR.build_user_payload(packet)}]}],
        inferenceConfig={"temperature": rm["temperature"],
                         "maxTokens": rm["max_tokens"]},
        toolConfig={"tools": [tool],
                    "toolChoice": {"tool": {"name": "emit_hypotheses"}}})
    usage = resp.get("usage") or {}
    in_tok = int(usage.get("inputTokens") or 0)
    out_tok = int(usage.get("outputTokens") or 0)
    payload = None
    for block in ((resp.get("output") or {}).get("message") or {}).get("content") or []:
        if "toolUse" in block:
            payload = block["toolUse"].get("input")
            break
    with open(f"{EXEC_DIR}/raw/{seq:03d}.json", "w") as fh:
        json.dump({"seq": seq, "response": resp, "payload": payload}, fh,
                  indent=1, sort_keys=True, default=str)
    return payload, in_tok, out_tok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--i-have-authorization", action="store_true")
    ap.add_argument("--ceiling", type=float, default=None,
                    help="hard ceiling in USD; defaults to the preregistered one")
    args = ap.parse_args()

    prereg = json.load(open(f"{OUT}/PREREGISTRATION.json"))
    ceiling = args.ceiling or prereg["cost_model"]["hard_ceiling_usd"]

    if not args.i_have_authorization:
        print("REFUSING TO RUN: no authorization flag. Zero spend.")
        print(f"  preregistered calls   : {prereg['cost_model']['n_calls_total']}")
        print(f"  expected / p90 / ceil : "
              f"${prereg['cost_model']['expected_cost_usd']} / "
              f"${prereg['cost_model']['p90_cost_usd']} / "
              f"${prereg['cost_model']['hard_ceiling_usd']}")
        return 0

    os.makedirs(f"{EXEC_DIR}/raw", exist_ok=True)

    # ---- S31 reverification, at zero spend -------------------------------------------
    problems = reverify(prereg)
    if problems:
        print("ABORT at $0.00 -- frozen artifacts moved since preregistration:")
        for p in problems:
            print("   ", p)
        return 2

    # ---- S16 transport preflight, at zero spend --------------------------------------
    client = build_client()
    try:
        env = TRN.preflight(client)
    except TRN.TransportPreflightFailure as exc:
        print("ABORT at $0.00 -- transport preflight failed (defect D4 class):")
        print("   ", exc)
        return 3
    print(f"preflight OK | {env['python_executable']} | boto3 {env['boto3_version']}")

    acct = TRN.TransportAccounting(prereg["cost_model"]["price_in_per_1k"],
                                   prereg["cost_model"]["price_out_per_1k"], ceiling)
    packets = {arm: json.load(open(f"{OUT}/packets_{arm}.json"))
               for arm in ("base", "research")}

    calls = []
    for c in prereg["request_manifest"]["calls"]:
        for rep in range(c["n_calls"]):
            calls.append({**c, "rep": rep})

    log_path = f"{EXEC_DIR}/execution_log.jsonl"
    log = open(log_path, "a")
    n_model_invalid = n_infra = 0
    max_observed_input = 0
    scores = []
    stop = None

    for seq, c in enumerate(calls, start=1):
        pk = packets[c["arm"]][c["fixture_id"]]
        # Worst case for THIS call, using the larger of the preregistered estimate and
        # the largest input actually observed so far. The estimate comes from a
        # calibration, and a calibration that runs low is exactly how a ceiling gets
        # crossed; taking the observed maximum makes the guard track reality rather than
        # the plan.
        worst_in = max(c["est_input_tokens"], max_observed_input)
        projected = (worst_in / 1000 * prereg["cost_model"]["price_in_per_1k"]
                     + prereg["request_manifest"]["max_tokens"] / 1000
                     * prereg["cost_model"]["price_out_per_1k"])
        # A TERMINAL guard, not the primary cost control. The preregistered ceiling
        # already prices every call at max_tokens of output, so this can only fire late in
        # the run and only if real usage outran the calibration. The primary control is
        # the post-call `classify_stop` cost rule; this exists so the run refuses to START
        # a call it could not afford at worst case.
        if acct.would_exceed_ceiling(projected):
            stop = [{"rule": "V5A2_STOP_COST_CEILING",
                     "detail": f"next call would exceed ${ceiling:.4f}",
                     "class": "APPARATUS"}]
            break
        try:
            payload, in_tok, out_tok = call_once(client, prereg, pk, seq, log)
            acct.record_call(seq, in_tok, out_tok)
            max_observed_input = max(max_observed_input, in_tok)
        except Exception as exc:                      # transport, not model
            acct.record_transport_failure(seq, f"{type(exc).__name__}: {exc}")
            log.write(json.dumps({"seq": seq, "outcome": "TRANSPORT_FAILURE",
                                  "error": f"{type(exc).__name__}: {exc}"}) + "\n")
            log.flush()
            fired = EV.classify_stop(acct.n_charged, n_model_invalid, n_infra,
                                     acct.n_consecutive_transport_failures,
                                     acct.spend_usd, ceiling)
            if fired:
                stop = fired
                break
            continue

        s = EV.score_response(payload, pk)
        scores.append({"seq": seq, "arm": c["arm"], "fixture_id": c["fixture_id"],
                       "rep": c["rep"], "score": s})
        if s["failure_class"] == V4.INFRASTRUCTURE_CONTRACT_FAILURE:
            n_infra += 1
        elif s["failure_class"] == V4.MODEL_SCHEMA_INVALID:
            n_model_invalid += 1

        log.write(json.dumps({"seq": seq, "arm": c["arm"],
                              "fixture_id": c["fixture_id"], "rep": c["rep"],
                              "input_tokens": in_tok, "output_tokens": out_tok,
                              "cumulative_usd": round(acct.spend_usd, 6),
                              "failure_class": s["failure_class"],
                              "grounded_accepted_n": s["grounded_accepted_n"],
                              "ts": int(time.time())}) + "\n")
        log.flush()
        print(f"  seq {seq:3d} {c['fixture_id']} {c['arm']:9s} rep{c['rep']} "
              f"in={in_tok:6d} out={out_tok:5d} "
              f"acc={s['grounded_accepted_n']:2d}/{s['n_hypotheses']:2d} "
              f"cum=${acct.spend_usd:.4f}")

        fired = EV.classify_stop(acct.n_charged, n_model_invalid, n_infra,
                                 acct.n_consecutive_transport_failures,
                                 acct.spend_usd, ceiling)
        if fired:
            stop = fired
            break

    log.close()
    summary = {"n_calls_planned": len(calls),
               "transport": acct.to_dict(),
               "n_model_schema_invalid": n_model_invalid,
               "n_infrastructure_contract_failures": n_infra,
               "stop": stop,
               "execution_status": "STOPPED" if stop else "COMPLETE",
               "environment": env}
    with open(f"{EXEC_DIR}/execution_summary.json", "w") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True, default=str)
    with open(f"{EXEC_DIR}/scores.json", "w") as fh:
        json.dump(scores, fh, indent=1, sort_keys=True, default=str)
    print(json.dumps({k: v for k, v in summary.items() if k != "environment"},
                     indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
