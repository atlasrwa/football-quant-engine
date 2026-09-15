"""V6.1 provider-native EXACT input-token accounting via AWS Bedrock CountTokens.

`v6_1_count_tokens_driver_v1`. ZERO INFERENCE. ZERO SPEND. CountTokens is a non-generative,
zero-charge accounting operation, allowed as pure infrastructure validation AFTER the V6.1
requests are frozen. This driver NEVER calls Converse/InvokeModel: it reuses the V6
`_NoConverseClient` wrapper, which structurally forbids any generative method, and the frozen
no-retry client.

It rebuilds each frozen V6.1 canonical request, verifies its SHA-256 against the frozen
`INPUT_TOKEN_MANIFEST.json`, calls CountTokens on the foundation-model id the profile
resolves to, asserts the exact count never exceeds the conservative byte bound, and writes a
deterministic `EXACT_INPUT_TOKEN_MANIFEST.json` (+ a separate operational audit log). It then
lets `_freeze_v6_1.py` re-run to fold the exact counts into a tighter hard ceiling.

Any failure before all 36 requests are counted is a PRE-SPEND APPARATUS failure, never a
scientific verdict, and no exact manifest is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from decimal import ROUND_CEILING, Decimal

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/research/hypothesis_engine")

# Reuse the V6 driver's safety machinery verbatim (no-converse client, failure classes).
from _count_tokens_v6 import (
    CountTokensApparatusFailure, COUNT_TOKENS_INCOMPLETE_MANIFEST,
    COUNT_TOKENS_INVALID_RESPONSE, COUNT_TOKENS_MODEL_MAPPING_FAILURE,
    COUNT_TOKENS_REQUEST_HASH_MISMATCH, COUNT_TOKENS_TRANSPORT_FAILURE,
    build_count_client, count_one)
from src.research.hypothesis_oos import v6_token_count as TC
from src.research.hypothesis_oos import v6_transport as TRN

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v6_1"

COUNT_DRIVER_VERSION = "v6_1_count_tokens_driver_v1"
EXACT_MANIFEST_VERSION = "v6_1_exact_input_token_manifest_v1"
COUNTING_METHOD = "aws_bedrock_count_tokens"


def _sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def _price_per_token(p) -> Decimal:
    return Decimal(str(p)) / Decimal(1000)


def _usd(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    prereg = json.load(open(f"{OUT}/PREREGISTRATION.json"))
    shared = prereg["shared_stack"]
    frozen = json.load(open(f"{OUT}/INPUT_TOKEN_MANIFEST.json"))
    pricing = frozen["pricing"]
    price_in = _price_per_token(pricing["input_price_per_1k_usd"])
    price_out = _price_per_token(pricing["output_price_per_1k_usd"])

    frozen_by_seq = {e["seq"]: e for e in frozen["entries"]}
    calls = sorted(prereg["call_sequence"], key=lambda c: c["seq"])
    packets = {arm: json.load(open(f"{OUT}/packets_{arm}.json"))
               for arm in ("base", "research")}

    client = build_count_client()
    if client.max_attempts() > TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL:
        raise CountTokensApparatusFailure(COUNT_TOKENS_TRANSPORT_FAILURE,
                                          "count client is not no-retry")

    entries, audit = [], []
    total_in = total_out = 0
    sum_in_cost = sum_out_cost = sum_req_ceil = Decimal(0)

    for c in calls:
        seq, arm, fid = c["seq"], c["arm"], c["fixture_id"]
        me = frozen_by_seq.get(seq)
        if me is None:
            raise CountTokensApparatusFailure(
                COUNT_TOKENS_INCOMPLETE_MANIFEST, f"seq {seq} missing from frozen manifest")
        pk = packets[arm][fid]
        req = TC.canonical_converse_request(pk, model_id=shared["model_id"],
                                            temperature=shared["temperature"],
                                            max_tokens=shared["max_tokens"])
        rhash = TC.request_sha256(req)
        if rhash != me["request_sha256"]:
            raise CountTokensApparatusFailure(
                COUNT_TOKENS_REQUEST_HASH_MISMATCH,
                f"seq {seq} {arm}/{fid}: rebuilt {rhash[:12]} != frozen "
                f"{me['request_sha256'][:12]}")
        count_model_id = TC.foundation_model_id(shared["model_id"])
        if count_model_id != me["count_model_id"]:
            raise CountTokensApparatusFailure(
                COUNT_TOKENS_MODEL_MAPPING_FAILURE,
                f"seq {seq}: {count_model_id} != frozen {me['count_model_id']}")

        # CountTokens is free and non-generative; a transient provider-side error
        # (InternalServerException/Throttling) may be retried WITHOUT any billing or
        # inference risk. Bounded transient retries here never touch the billable Converse
        # path (that path stays no-retry, total_max_attempts=1).
        exact = op_meta = None
        last_exc = None
        for attempt in range(6):
            try:
                exact, op_meta = count_one(client, pk, count_model_id=count_model_id)
                break
            except CountTokensApparatusFailure as exc:
                if exc.klass != COUNT_TOKENS_TRANSPORT_FAILURE:
                    raise
                last_exc = exc
                time.sleep(2 * (attempt + 1))
        if exact is None:
            raise last_exc
        if exact > me["conservative_byte_upper_bound"]:
            raise CountTokensApparatusFailure(
                COUNT_TOKENS_INVALID_RESPONSE,
                f"seq {seq}: exact {exact} > byte bound "
                f"{me['conservative_byte_upper_bound']}")

        max_out = int(me["max_output_tokens"])
        in_cost = Decimal(exact) * price_in
        out_cost = Decimal(max_out) * price_out
        req_ceil = _usd(in_cost + out_cost)
        total_in += exact; total_out += max_out
        sum_in_cost += in_cost; sum_out_cost += out_cost; sum_req_ceil += req_ceil

        entries.append({
            "seq": seq, "execution_index": seq, "fixture_id": fid, "arm": arm,
            "rep": c["rep"], "role": c.get("role"),
            "request_sha256": rhash, "execution_model_id": shared["model_id"],
            "count_tokens_model_id": count_model_id, "mapping_verified": True,
            "exact_input_tokens": exact,
            "conservative_byte_upper_bound": me["conservative_byte_upper_bound"],
            "max_output_tokens": max_out,
            "max_billable_attempts": TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL,
            "max_request_cost_usd_ceil": str(req_ceil),
            "counting_method": COUNTING_METHOD})
        audit.append({"seq": seq, "fixture_id": fid, "arm": arm,
                      "exact_input_tokens": exact, **op_meta,
                      "counting_timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                              time.gmtime())})

    if len(entries) != len(calls):
        raise CountTokensApparatusFailure(
            COUNT_TOKENS_INCOMPLETE_MANIFEST,
            f"counted {len(entries)}/{len(calls)}; partial manifest blocks freeze")

    hard_ceiling = sum_req_ceil
    manifest = {
        "manifest_version": EXACT_MANIFEST_VERSION,
        "count_driver_version": COUNT_DRIVER_VERSION,
        "experiment_id": prereg["experiment"],
        "counting_method": COUNTING_METHOD,
        "execution_model_id": shared["model_id"],
        "count_tokens_model_id": TC.foundation_model_id(shared["model_id"]),
        "mapping_verified": True, "region": pricing["region"], "pricing_contract": pricing,
        "n_requests": len(entries),
        "total_exact_input_tokens": total_in,
        "total_max_output_tokens": total_out,
        "total_max_billable_attempts": len(entries) * TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL,
        "min_input_tokens": min(e["exact_input_tokens"] for e in entries),
        "max_input_tokens": max(e["exact_input_tokens"] for e in entries),
        "max_token_cost_usd_exact_global_roundup": str(_usd(sum_in_cost + sum_out_cost)),
        "hard_max_cost_usd": str(hard_ceiling),
        "previous_utf8_total_input_tokens": frozen["total_input_tokens_hard_bound"],
        "previous_hard_ceiling_usd": str(prereg["cost_model"]["hard_ceiling_usd"]),
        "entries": sorted(entries, key=lambda e: e["seq"])}

    print(f"requests counted         : {len(entries)}/{len(calls)}")
    print(f"total exact input tokens : {total_in}  (UTF-8 byte bound was "
          f"{frozen['total_input_tokens_hard_bound']})")
    print(f"min/max input tokens     : {manifest['min_input_tokens']} / "
          f"{manifest['max_input_tokens']}")
    print(f"HARD_MAX_COST (per-req sum): ${hard_ceiling}  (byte-bound was "
          f"${prereg['cost_model']['hard_ceiling_usd']})")

    if args.write:
        path = f"{OUT}/EXACT_INPUT_TOKEN_MANIFEST.json"
        with open(path, "w") as fh:
            json.dump(manifest, fh, indent=1, sort_keys=True, default=str)
        with open(f"{OUT}/count_tokens_audit_log.jsonl", "w") as fh:
            for a in sorted(audit, key=lambda x: x["seq"]):
                fh.write(json.dumps(a, sort_keys=True, default=str) + "\n")
        print(f"wrote {path}")
        print(f"EXACT manifest sha256    : {_sha_file(path)}")
    else:
        print("(dry run; pass --write to freeze the EXACT manifest)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CountTokensApparatusFailure as exc:
        print(f"APPARATUS STOP [{exc.klass}] {exc.detail}")
        print("No EXACT manifest written. Zero inference. Zero spend.")
        raise SystemExit(4)
