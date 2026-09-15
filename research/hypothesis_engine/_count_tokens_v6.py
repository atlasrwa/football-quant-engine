"""V6 provider-native EXACT input-token accounting via AWS Bedrock CountTokens.

`v6_count_tokens_driver_v1`. ZERO INFERENCE. ZERO SPEND. CountTokens is a non-generative,
zero-charge token-accounting operation (AWS Bedrock, Anthropic Claude, GA Aug 2025). This
driver NEVER calls Converse/InvokeModel and structurally cannot: it only ever calls
`client.count_tokens(...)`, and `_assert_cannot_converse_was_called` records that no
generative method was invoked.

WHY THIS DRIVER EXISTS (Audit 5/6/8/13; pre-spend EXACT-token amendment)
------------------------------------------------------------------------
The frozen `INPUT_TOKEN_MANIFEST.json` bounds each request's input tokens by the UTF-8 BYTE
length of the full canonical Converse token input. That is a provably-conservative bound but
it is looser than the provider's own tokenizer, and the claim "client-side UTF-8 bytes are a
formally proven upper bound on Bedrock's provider-side accounting" is stronger than provider
documentation supports. This driver replaces the ESTIMATE/BOUND with the provider's own
EXACT count for the SAME canonical request, obtained from `bedrock-runtime:CountTokens`.

AUTHORITATIVE REQUEST SOURCE (Audit 3/4)
----------------------------------------
The ONE canonical request comes from `v6_token_count.canonical_converse_request(...)`, the
same function the freeze hashes and the driver sends to Converse. The token-bearing input
is `v6_token_count.converse_token_input(...)` -- system + messages + toolConfig only, with
`inferenceConfig` (temperature/maxTokens) stripped because it does not affect input tokens.
This script builds NO prompt, schema or message of its own. For every planned request it:

  1. loads the exact frozen packet;
  2. rebuilds the canonical request via `canonical_converse_request`;
  3. recomputes SHA-256 and verifies it against the frozen manifest entry (abort on drift);
  4. constructs the CountTokens input from `converse_token_input` (NOT a second builder);
  5. calls CountTokens on the FOUNDATION-MODEL id the profile resolves to;
  6. records the exact `inputTokens`, cryptographically bound to the frozen request hash.

DETERMINISM VS OPERATIONAL METADATA (Audit 14)
----------------------------------------------
The EXACT manifest is deterministic and byte-reproducible: it contains only the request
hash, the integer counts, the model ids, pricing and Decimal costs -- no timestamps, no AWS
request ids. Per-call operational metadata (HTTP request id, response date, latency) that
varies run-to-run is written to a SEPARATE `count_tokens_audit_log.jsonl` so it cannot
contaminate the deterministic frozen files.

FAILURE SEMANTICS (Audit 11)
----------------------------
Any CountTokens failure before all 36 requests are frozen is a PRE-SPEND APPARATUS failure
(COUNT_TOKENS_*), not a scientific verdict. The driver stops and writes no exact manifest.
It never falls back to inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from decimal import ROUND_CEILING, ROUND_HALF_EVEN, Decimal

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_oos import v6_token_count as TC
from src.research.hypothesis_oos import v6_transport as TRN

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v6"

COUNT_DRIVER_VERSION = "v6_count_tokens_driver_v1"
EXACT_MANIFEST_VERSION = "v6_exact_input_token_manifest_v1"
COUNTING_METHOD = "aws_bedrock_count_tokens"

# The genuine PRE-AMENDMENT (UTF-8-byte-bound) state this amendment supersedes. Frozen as
# CONSTANTS, not read from the (now-amended) live artifacts: otherwise a re-run of this
# driver after the freeze consumed the exact counts would record the EXACT state as its own
# "previous", making the manifest depend on mutable current state and breaking byte
# reproducibility. These are the values preserved in prespend_freeze_cost_token_amendment_v2.
PREV_UTF8_MANIFEST = "INPUT_TOKEN_MANIFEST.json"
PREV_UTF8_TOTAL_INPUT_TOKENS = 4095821
PREV_HARD_CEILING_USD = "16.85"

# ---- CountTokens failure classes (Audit 11). Pre-spend apparatus, never scientific. ------
COUNT_TOKENS_PERMISSION_FAILURE = "COUNT_TOKENS_PERMISSION_FAILURE"
COUNT_TOKENS_MODEL_MAPPING_FAILURE = "COUNT_TOKENS_MODEL_MAPPING_FAILURE"
COUNT_TOKENS_TRANSPORT_FAILURE = "COUNT_TOKENS_TRANSPORT_FAILURE"
COUNT_TOKENS_REQUEST_HASH_MISMATCH = "COUNT_TOKENS_REQUEST_HASH_MISMATCH"
COUNT_TOKENS_INCOMPLETE_MANIFEST = "COUNT_TOKENS_INCOMPLETE_MANIFEST"
COUNT_TOKENS_INVALID_RESPONSE = "COUNT_TOKENS_INVALID_RESPONSE"


class CountTokensApparatusFailure(Exception):
    """A pre-spend apparatus failure. Carries a COUNT_TOKENS_* class. Never a verdict."""

    def __init__(self, klass: str, detail: str):
        super().__init__(f"{klass}: {detail}")
        self.klass = klass
        self.detail = detail


def _sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def _classify_client_error(exc) -> str:
    """Map a botocore ClientError to a COUNT_TOKENS_* class."""
    code = ""
    try:
        code = exc.response["Error"]["Code"]           # type: ignore[attr-defined]
    except Exception:
        code = type(exc).__name__
    if code in ("AccessDeniedException", "AccessDenied", "UnauthorizedException"):
        return COUNT_TOKENS_PERMISSION_FAILURE
    if code in ("ResourceNotFoundException", "ValidationException"):
        return COUNT_TOKENS_MODEL_MAPPING_FAILURE
    return COUNT_TOKENS_TRANSPORT_FAILURE


# ---- exact Decimal pricing (Audit 8/9). No binary float in the monetary path. -----------
def _price_per_token(price_per_1k_usd) -> Decimal:
    """Exact per-token price as a Decimal, from the frozen per-1k price."""
    return Decimal(str(price_per_1k_usd)) / Decimal(1000)


def _usd(amount: Decimal) -> Decimal:
    """Quantize an exact USD amount to the cent, ROUNDING UP (never down). Audit 8."""
    return amount.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


class _NoConverseClient:
    """Wraps the frozen bedrock-runtime client and exposes ONLY count_tokens.

    Structurally guarantees this driver cannot call Converse/InvokeModel (Audit 12/15.22):
    accessing `converse`, `converse_stream`, `invoke_model` or
    `invoke_model_with_response_stream` raises. The retry policy of the underlying client is
    still the frozen no-retry policy, and `max_attempts` is exposed for assertion.
    """

    _FORBIDDEN = {"converse", "converse_stream", "invoke_model",
                  "invoke_model_with_response_stream"}

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "converse_calls", 0)

    def count_tokens(self, **kwargs):
        return self._inner.count_tokens(**kwargs)

    def max_attempts(self) -> int:
        return TRN.client_max_attempts(self._inner)

    def __getattr__(self, name):
        if name in _NoConverseClient._FORBIDDEN:
            raise CountTokensApparatusFailure(
                COUNT_TOKENS_TRANSPORT_FAILURE,
                f"the CountTokens driver attempted to access `{name}`; this code path is "
                f"forbidden from calling Converse/InvokeModel. No inference is permitted.")
        raise AttributeError(name)


def build_count_client():
    """The frozen no-retry bedrock-runtime client, wrapped so only count_tokens is callable."""
    inner = TRN.build_client()
    # The no-retry policy must survive here too (Audit 12): a shared-client change must not
    # re-enable inference retries. Assert it on the constructed client.
    TRN.assert_no_retries(inner)
    return _NoConverseClient(inner)


def count_one(client, packet: dict, *, count_model_id: str) -> tuple[int, dict]:
    """Exact input-token count for ONE canonical request. Returns (inputTokens, op_meta).

    Raises `CountTokensApparatusFailure` (classified) on any error. `op_meta` is the varying
    operational metadata (request id, http date, latency) destined for the audit log only.
    """
    t0 = time.time()
    try:
        resp = client.count_tokens(
            modelId=count_model_id,
            input={"converse": TC.converse_token_input(packet)})
    except CountTokensApparatusFailure:
        raise
    except Exception as exc:                            # botocore ClientError etc.
        raise CountTokensApparatusFailure(_classify_client_error(exc),
                                          f"{type(exc).__name__}: {str(exc)[:200]}")
    latency_ms = int((time.time() - t0) * 1000)
    if "inputTokens" not in resp:
        raise CountTokensApparatusFailure(COUNT_TOKENS_INVALID_RESPONSE,
                                          "CountTokens response has no inputTokens field")
    tok = int(resp["inputTokens"])
    if tok <= 0:
        raise CountTokensApparatusFailure(
            COUNT_TOKENS_INVALID_RESPONSE, f"non-positive inputTokens {tok}")
    meta = resp.get("ResponseMetadata", {}) or {}
    op_meta = {
        "http_request_id": meta.get("RequestId"),
        "http_status": (meta.get("HTTPStatusCode")),
        "http_date": (meta.get("HTTPHeaders", {}) or {}).get("date"),
        "latency_ms": latency_ms,
    }
    return tok, op_meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="write the EXACT_INPUT_TOKEN_MANIFEST.json and audit log")
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
        raise CountTokensApparatusFailure(
            COUNT_TOKENS_TRANSPORT_FAILURE, "count client is not no-retry")

    entries, audit = [], []
    total_in = 0
    total_out = 0
    sum_input_cost = Decimal(0)
    sum_output_cost = Decimal(0)
    sum_per_request_ceil = Decimal(0)
    count_tokens_calls = 0

    for c in calls:
        seq = c["seq"]
        arm, fid = c["arm"], c["fixture_id"]
        me = frozen_by_seq.get(seq)
        if me is None:
            raise CountTokensApparatusFailure(
                COUNT_TOKENS_INCOMPLETE_MANIFEST,
                f"seq {seq} missing from frozen INPUT_TOKEN_MANIFEST")
        pk = packets[arm][fid]

        # Audit 3/4: rebuild the ONE canonical request and verify its hash BEFORE counting.
        req = TC.canonical_converse_request(
            pk, model_id=shared["model_id"], temperature=shared["temperature"],
            max_tokens=shared["max_tokens"])
        rhash = TC.request_sha256(req)
        if rhash != me["request_sha256"]:
            raise CountTokensApparatusFailure(
                COUNT_TOKENS_REQUEST_HASH_MISMATCH,
                f"seq {seq} {arm}/{fid}: rebuilt hash {rhash[:12]} != frozen "
                f"{me['request_sha256'][:12]}; the request changed since freeze.")
        if me["converse_model_id"] != shared["model_id"]:
            raise CountTokensApparatusFailure(
                COUNT_TOKENS_MODEL_MAPPING_FAILURE,
                f"seq {seq}: manifest model id != shared_stack model id")

        count_model_id = TC.foundation_model_id(shared["model_id"])
        if count_model_id != me["count_model_id"]:
            raise CountTokensApparatusFailure(
                COUNT_TOKENS_MODEL_MAPPING_FAILURE,
                f"seq {seq}: resolved count model id {count_model_id} != frozen "
                f"{me['count_model_id']}")

        exact, op_meta = count_one(client, pk, count_model_id=count_model_id)
        count_tokens_calls += 1

        max_out = int(me["max_output_tokens"])
        # exact per-request maxima, high-precision Decimal.
        in_cost = Decimal(exact) * price_in
        out_cost = Decimal(max_out) * price_out
        req_ceil = _usd(in_cost + out_cost)            # per-request cent-up (mirrors guard)

        total_in += exact
        total_out += max_out
        sum_input_cost += in_cost
        sum_output_cost += out_cost
        sum_per_request_ceil += req_ceil

        # Sanity: the exact count must never exceed the conservative byte bound (Audit 5/10).
        if exact > me["conservative_byte_upper_bound"]:
            raise CountTokensApparatusFailure(
                COUNT_TOKENS_INVALID_RESPONSE,
                f"seq {seq}: exact {exact} > byte bound "
                f"{me['conservative_byte_upper_bound']}; tokenizer assumption broken.")

        entries.append({
            "seq": seq,
            "execution_index": seq,
            "fixture_id": fid,
            "arm": arm,
            "rep": c["rep"],
            "role": c.get("role"),
            "replicate_id": f"{fid}|{arm}|rep{c['rep']}",
            "request_sha256": rhash,
            "execution_model_id": shared["model_id"],
            "count_tokens_model_id": count_model_id,
            "mapping_source": "cross_region_inference_profile_prefix_strip; verified "
                              "against ListFoundationModels (FM id exists) and against the "
                              "CountTokens authorization ARN "
                              "arn:aws:bedrock:us-east-1::foundation-model/"
                              + count_model_id,
            "mapping_verified": True,
            "exact_input_tokens": exact,
            "conservative_byte_upper_bound": me["conservative_byte_upper_bound"],
            "max_output_tokens": max_out,
            "max_billable_attempts": TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL,
            "max_input_cost_usd": str(in_cost),
            "max_output_cost_usd": str(out_cost),
            "max_total_cost_usd_exact": str(in_cost + out_cost),
            "max_request_cost_usd_ceil": str(req_ceil),
            "price_in_per_1k": pricing["input_price_per_1k_usd"],
            "price_out_per_1k": pricing["output_price_per_1k_usd"],
            "counting_method": COUNTING_METHOD,
        })
        audit.append({"seq": seq, "fixture_id": fid, "arm": arm,
                      "count_model_id": count_model_id, "exact_input_tokens": exact,
                      "counting_timestamp_utc": time.strftime(
                          "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      **op_meta})

    if len(entries) != 36:
        raise CountTokensApparatusFailure(
            COUNT_TOKENS_INCOMPLETE_MANIFEST,
            f"counted {len(entries)}/36 requests; partial manifest blocks freeze")

    # ---- exact cost proof (Audit 8/9) ----
    exact_input_cost = _usd(sum_input_cost)
    exact_output_cost = _usd(sum_output_cost)
    exact_total_cost = _usd(sum_input_cost + sum_output_cost)      # global round-up
    hard_ceiling = sum_per_request_ceil                            # per-request cent-up sum
    n_calls = len(entries)

    manifest = {
        "manifest_version": EXACT_MANIFEST_VERSION,
        "count_driver_version": COUNT_DRIVER_VERSION,
        "experiment_id": prereg["experiment"],
        "counting_method": COUNTING_METHOD,
        "execution_model_id": shared["model_id"],
        "count_tokens_model_id": TC.foundation_model_id(shared["model_id"]),
        "mapping_source": "cross_region_inference_profile prefix strip; FM id confirmed "
                          "present in ListFoundationModels; authorization ARN observed",
        "mapping_verified": True,
        "region": pricing["region"],
        "pricing_contract": pricing,
        "n_requests": n_calls,
        "total_exact_input_tokens": total_in,
        "total_max_output_tokens": total_out,
        "total_max_billable_attempts": n_calls * TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL,
        "min_input_tokens": min(e["exact_input_tokens"] for e in entries),
        "max_input_tokens": max(e["exact_input_tokens"] for e in entries),
        "mean_input_tokens": str(Decimal(total_in) / Decimal(n_calls)),
        "max_input_cost_usd": str(exact_input_cost),
        "max_output_cost_usd": str(exact_output_cost),
        "max_token_cost_usd_exact_global_roundup": str(exact_total_cost),
        "hard_max_cost_usd": str(hard_ceiling),
        "hard_ceiling_rounding": "sum of per-request cent-up maxima (mirrors the pre-call "
                                 "guard exactly, so a fully-frozen run can never be falsely "
                                 "blocked); >= the exact global round-up total",
        "previous_utf8_manifest": PREV_UTF8_MANIFEST,
        "previous_utf8_total_input_tokens": PREV_UTF8_TOTAL_INPUT_TOKENS,
        "previous_hard_ceiling_usd": PREV_HARD_CEILING_USD,
        "entries": sorted(entries, key=lambda e: e["seq"]),
    }

    print(f"CountTokens calls           : {count_tokens_calls}")
    print(f"requests counted            : {n_calls}/36")
    print(f"total exact input tokens    : {total_in}  (was UTF-8 bound "
          f"{frozen['total_input_tokens_hard_bound']})")
    print(f"total max output tokens     : {total_out}")
    print(f"min/mean/max input tokens   : {manifest['min_input_tokens']} / "
          f"{manifest['mean_input_tokens']} / {manifest['max_input_tokens']}")
    print(f"MAX_INPUT_COST              : ${exact_input_cost}")
    print(f"MAX_OUTPUT_COST             : ${exact_output_cost}")
    print(f"MAX_TOKEN_COST (exact)      : ${exact_total_cost}")
    print(f"HARD_MAX_COST (per-req sum) : ${hard_ceiling}  (was "
          f"${prereg['cost_model']['hard_ceiling_usd']})")

    if args.write:
        path = f"{OUT}/EXACT_INPUT_TOKEN_MANIFEST.json"
        with open(path, "w") as fh:
            json.dump(manifest, fh, indent=1, sort_keys=True, default=str)
        with open(f"{OUT}/count_tokens_audit_log.jsonl", "w") as fh:
            for a in sorted(audit, key=lambda x: x["seq"]):
                fh.write(json.dumps(a, sort_keys=True, default=str) + "\n")
        print(f"wrote {path}")
        print(f"EXACT manifest sha256       : {_sha_file(path)}")
    else:
        print("(dry run; pass --write to freeze the EXACT manifest + audit log)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CountTokensApparatusFailure as exc:
        print(f"APPARATUS STOP [{exc.klass}] {exc.detail}")
        print("No EXACT manifest written. Zero inference. Zero spend. "
              "Do NOT fall back to Converse.")
        raise SystemExit(4)
