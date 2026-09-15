"""V6 execution driver. RUNS NOTHING UNLESS EXPLICITLY AUTHORIZED. ZERO SPEND ON IMPORT.

`main()` refuses to start without `--i-have-authorization`, so importing, hashing or reading
this file costs nothing. It is written and hashed into the preregistration BEFORE
authorization precisely so the human authorizes a KNOWN driver, not one written after the
fact. This module is on the frozen `MODULES` list in `_freeze_v6.py`.

WHAT THIS DRIVER GUARANTEES THAT A DEFAULT ONE WOULD NOT (amendment 1)
----------------------------------------------------------------------
The client is built by `v6_transport.build_client()`, which disables retries. Preflight then
`assert_no_retries` on the CONSTRUCTED client at zero spend, so a client that could bill a
call more than once aborts the run before the first request. That is the mechanism that
makes the preregistered `hard_ceiling_usd` a true worst-case BILLABLE bound rather than an
estimate of the no-retry case. Without it, a Converse call the server billed but whose
response was lost to a read timeout would be retried and re-billed, and the ceiling would
understate spend.

WHAT ELSE IT ASSERTS (inherited from the V5A.2 driver reasoning)
----------------------------------------------------------------
  * S31  every frozen module / packet / request hash is re-verified against the
         preregistration before the first paid call; any drift aborts at zero spend.
  * S16  transport preflight runs at spend == 0.0, before the first request is constructed.
  * S17  `TransportAccounting` separates attempted / charged / transport-failed calls, so a
         failed call can never inflate the spend estimate.
  * schedule is CONSUMED VERBATIM from the frozen flat call list -- there is no `n_calls`
         field to expand, which is the seam that put V5A.2's stop rule on one fixture.
  * every raw response is written to disk immutably BEFORE it is scored, so a scoring bug
         can never destroy paid data.
  * stop rules are the FROZEN `v6_stop.classify_stop`; the terminal cost guard refuses to
         START a call whose worst-case charge would breach the ceiling.

The scientific verdict (`v6_verdict.final_verdict`) is intentionally NOT computed here at
run time in a way that could vary: this driver records scores and lets the frozen evaluator
be run once, afterwards, on the immutable scores. EXECUTION_STATUS and SCIENTIFIC_VERDICT
are kept separate (§26).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import validator_v5 as V
from src.research.hypothesis_oos import v6_classes as K
from src.research.hypothesis_oos import v6_prompt as PR
from src.research.hypothesis_oos import v6_scorecard as SC
from src.research.hypothesis_oos import v6_stop as STOP
from src.research.hypothesis_oos import v6_token_count as TC
from src.research.hypothesis_oos import v6_transport as TRN

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v6"
EXEC_DIR = f"{OUT}/execution"


def _sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def reverify(prereg) -> list:
    """Nothing frozen may have moved. Returns problems; empty means proceed. Zero spend."""
    problems = []
    for rel, sha in sorted(prereg["module_hashes"].items()):
        if rel.endswith("_execute_v6.py"):
            continue
        got = _sha_file(f"{ROOT}/{rel}")
        if got != sha:
            problems.append(f"module {rel} changed since freeze ({got[:12]} != {sha[:12]})")
    for rel, sha in sorted(prereg["frozen_upstream_module_hashes"].items()):
        got = _sha_file(f"{ROOT}/{rel}")
        if got != sha:
            problems.append(f"FROZEN upstream module {rel} was modified ({got[:12]} != "
                            f"{sha[:12]})")
    packets = {arm: json.load(open(f"{OUT}/packets_{arm}.json"))
               for arm in ("base", "research")}
    shared = prereg["shared_stack"]
    # token manifest hash + per-request canonical request hash coverage (Audit 3/4)
    tm_path = f"{OUT}/INPUT_TOKEN_MANIFEST.json"
    if _sha_file(tm_path) != prereg["artifact_hashes"].get("INPUT_TOKEN_MANIFEST.json"):
        problems.append("INPUT_TOKEN_MANIFEST.json hash differs from the preregistered one")
    token_manifest = json.load(open(tm_path))
    by_seq = {e["seq"]: e for e in token_manifest["entries"]}
    for call in prereg["call_sequence"]:
        pk = packets[call["arm"]][call["fixture_id"]]
        if pk["packet_hash"] != call["packet_hash"]:
            problems.append(f"packet hash drift {call['arm']}/{call['fixture_id']}")
        if hashlib.sha256(PR.serialized_request(pk).encode()).hexdigest() != \
                call["serialized_request_sha256"]:
            problems.append(f"request bytes drift {call['arm']}/{call['fixture_id']}")
        # Audit 4: the canonical executable request must match its frozen manifest hash.
        me = by_seq.get(call["seq"])
        if me is None:
            problems.append(f"seq {call['seq']} missing from token manifest")
            continue
        req = TC.canonical_converse_request(
            pk, model_id=shared["model_id"], temperature=shared["temperature"],
            max_tokens=shared["max_tokens"])
        if TC.request_sha256(req) != me["request_sha256"]:
            problems.append(f"canonical request hash drift {call['arm']}/"
                            f"{call['fixture_id']} seq {call['seq']}")
        if me["converse_model_id"] != shared["model_id"]:
            problems.append(f"seq {call['seq']} manifest model id != shared_stack model id")
    champ = prereg["champion_protection"]
    if _sha_file(champ["artifact"]) != champ["frozen_sha256"]:
        problems.append("CHAMPION artifact changed")
    return problems


def call_once(client, prereg, packet, seq):
    """One Converse call with forced tool use. Returns (payload|None, in_tok, out_tok)."""
class RequestHashMismatch(TRN.TransportPreflightFailure):
    """The canonical request does not match its frozen token-manifest hash. No inference."""


def call_once(client, prereg, packet, seq, manifest_entry):
    """One Converse call from the ONE canonical request. Verifies the request hash against
    the frozen token manifest BEFORE invoking; a mismatch aborts before any inference.

    Returns (payload|None, in_tok, out_tok). The request the token count was taken over and
    the request sent to Converse are the SAME structure (`canonical_converse_request`), so a
    correct count can never be applied to a silently-rebuilt request.
    """
    shared = prereg["shared_stack"]
    request = TC.canonical_converse_request(
        packet, model_id=shared["model_id"], temperature=shared["temperature"],
        max_tokens=shared["max_tokens"])

    # Audit 4: rebuild -> canonicalize -> hash -> compare -> abort before inference on drift.
    rhash = TC.request_sha256(request)
    if rhash != manifest_entry["request_sha256"]:
        raise RequestHashMismatch(
            f"seq {seq}: canonical request hash {rhash[:12]} != frozen manifest "
            f"{manifest_entry['request_sha256'][:12]}; the executable request content "
            f"changed since freeze. No Bedrock call is made; spend is unchanged.")

    resp = client.converse(**request)
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
    ap.add_argument("--ceiling", type=float, default=None)
    args = ap.parse_args()

    prereg = json.load(open(f"{OUT}/PREREGISTRATION.json"))
    cm = prereg["cost_model"]
    ceiling = args.ceiling or cm["hard_ceiling_usd"]

    if not args.i_have_authorization:
        print("REFUSING TO RUN: no authorization flag. Zero spend.")
        print(f"  preregistered calls   : {cm['n_calls_total']}")
        print(f"  max billable attempts : {cm['max_billable_attempts_total']} "
              f"({cm['max_billable_attempts_per_call']}/call, retries disabled)")
        print(f"  expected / p90 / ceil : ${cm['expected_cost_usd']} / "
              f"${cm['p90_cost_usd']} / ${cm['hard_ceiling_usd']}")
        return 0

    os.makedirs(f"{EXEC_DIR}/raw", exist_ok=True)

    problems = reverify(prereg)
    if problems:
        print("ABORT at $0.00 -- frozen artifacts moved since preregistration:")
        for p in problems:
            print("   ", p)
        return 2

    client = TRN.build_client()
    try:
        env = TRN.preflight(client)     # raises on no-converse OR retries-enabled
    except TRN.TransportPreflightFailure as exc:
        print("ABORT at $0.00 -- transport preflight failed:")
        print("   ", exc)
        return 3
    print(f"preflight OK | {env['python_executable']} | boto3 {env['boto3_version']} | "
          f"retries disabled: {env['retry_policy']['retries_disabled_on_client']}")

    acct = TRN.TransportAccounting(cm["price_in_per_1k"], cm["price_out_per_1k"], ceiling)
    packets = {arm: json.load(open(f"{OUT}/packets_{arm}.json"))
               for arm in ("base", "research")}
    calls = sorted(prereg["call_sequence"], key=lambda c: c["seq"])

    # Audit 4/7/8: the frozen token manifest, indexed by seq. Every executable call must have
    # an entry; a missing entry blocks execution. The guard uses the frozen per-request
    # maximum cost, never an estimate.
    token_manifest = json.load(open(f"{OUT}/INPUT_TOKEN_MANIFEST.json"))
    by_seq = {e["seq"]: e for e in token_manifest["entries"]}

    log = open(f"{EXEC_DIR}/execution_log.jsonl", "a")
    scores, stop = [], None
    cost_violations = []
    class_counts = {c: 0 for c in K.HYPOTHESIS_CLASSES}
    n_resp_fatal = n_infra = 0
    fixtures_seen, valid_per_arm = set(), {"base": 0, "research": 0}

    for c in calls:
        seq = c["seq"]
        pk = packets[c["arm"]][c["fixture_id"]]
        me = by_seq.get(seq)
        if me is None:                                  # Audit 11: missing manifest entry
            stop = [{"rule": "V6_STOP_TOKEN_MANIFEST_MISSING", "class": "APPARATUS",
                     "detail": f"no token-manifest entry for seq {seq}; cannot bound cost"}]
            break
        # Audit 7: pre-call affordability uses the FROZEN per-request maximum cost.
        projected = me["max_request_cost_usd"]
        if acct.would_exceed_ceiling(projected):
            stop = [{"rule": "V6_STOP_COST_CEILING", "class": "APPARATUS",
                     "detail": f"next call max cost ${projected:.4f} + spent "
                               f"${acct.spend_usd:.4f} would exceed ${ceiling:.4f}"}]
            break
        try:
            payload, in_tok, out_tok = call_once(client, prereg, pk, seq, me)
            acct.record_call(seq, in_tok, out_tok)
            # Audit 8: reconcile observed input usage against the frozen hard bound.
            if in_tok > me["input_tokens"]:
                cost_violations.append(
                    {"seq": seq, "observed_input_tokens": in_tok,
                     "frozen_bound": me["input_tokens"]})
                stop = [{"rule": "V6_STOP_COST_BOUND_VIOLATION", "class": "APPARATUS",
                         "detail": f"seq {seq}: observed input {in_tok} exceeds frozen "
                                   f"bound {me['input_tokens']}; the hard-bound guarantee "
                                   f"can no longer be trusted. Aborting further spend."}]
                break
        except Exception as exc:
            acct.record_transport_failure(seq, f"{type(exc).__name__}: {exc}")
            log.write(json.dumps({"seq": seq, "outcome": "TRANSPORT_FAILURE",
                                  "error": f"{type(exc).__name__}: {exc}"}) + "\n")
            log.flush()
            res = STOP.classify_stop(
                n_calls_charged=acct.n_charged, fixtures_observed=sorted(fixtures_seen),
                valid_calls_per_arm=valid_per_arm, class_counts=class_counts,
                n_hypotheses_adjudicated=sum(class_counts.values()),
                n_responses_fatal=n_resp_fatal, n_infrastructure_failures=n_infra,
                n_consecutive_transport_failures=acct.n_consecutive_transport_failures,
                spend_usd=acct.spend_usd, ceiling_usd=ceiling)
            if res["stop"]:
                stop = res["fired"]
                break
            continue

        adj = V.adjudicate(payload, packet=pk, expected_packet_hash=pk["packet_hash"],
                           expected_fixture_id=pk["fixture_id"])
        sc = SC.score_response(adj, pk)
        sc["arm"] = c["arm"]
        scores.append({"seq": seq, "arm": c["arm"], "fixture_id": c["fixture_id"],
                       "rep": c["rep"], "scorecard": sc})
        fixtures_seen.add(c["fixture_id"])
        if adj.fatal:
            n_resp_fatal += 1
        else:
            valid_per_arm[c["arm"]] = valid_per_arm.get(c["arm"], 0) + 1
            for a in adj.hypotheses:
                class_counts[a.outcome_class] = class_counts.get(a.outcome_class, 0) + 1
                if a.outcome_class == K.INFRASTRUCTURE_FAILURE:
                    n_infra += 1

        log.write(json.dumps({"seq": seq, "arm": c["arm"],
                              "fixture_id": c["fixture_id"], "rep": c["rep"],
                              "input_tokens": in_tok, "output_tokens": out_tok,
                              "cumulative_usd": round(acct.spend_usd, 6),
                              "response_class": adj.response_class,
                              "n_qualified": sc.get("n_qualified"),
                              "ts": int(time.time())}) + "\n")
        log.flush()

        res = STOP.classify_stop(
            n_calls_charged=acct.n_charged, fixtures_observed=sorted(fixtures_seen),
            valid_calls_per_arm=valid_per_arm, class_counts=class_counts,
            n_hypotheses_adjudicated=sum(class_counts.values()),
            n_responses_fatal=n_resp_fatal, n_infrastructure_failures=n_infra,
            n_consecutive_transport_failures=acct.n_consecutive_transport_failures,
            spend_usd=acct.spend_usd, ceiling_usd=ceiling)
        if res["stop"]:
            stop = res["fired"]
            break

    log.close()
    summary = {"n_calls_planned": len(calls),
               "transport": acct.to_dict(),
               "class_counts": class_counts,
               "n_responses_fatal": n_resp_fatal,
               "n_infrastructure_failures": n_infra,
               "fixtures_observed": sorted(fixtures_seen),
               "valid_calls_per_arm": valid_per_arm,
               "cost_bound_violations": cost_violations,
               "hard_ceiling_usd": ceiling,
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
