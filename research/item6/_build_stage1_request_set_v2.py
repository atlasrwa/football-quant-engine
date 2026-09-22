"""Build the successor Item 6 Stage-1 request set V2 (US-geo price rebinding). ZERO SPEND.

WHY V2 EXISTS
The narrow US-geo price-freeze amendment corrects the execution PRICE BASIS only
(3.00/15.00 global -> 3.30/16.50 US-geo conservative). The request-set identity embeds the
price-table version and the cost-planning annotations, so a SUCCESSOR request-set version is
created rather than overwriting V1. The request BYTES themselves are SCIENTIFICALLY and
BYTE-IDENTICALLY UNCHANGED: every per-fixture skeleton_request_sha256 and
skeleton_request_utf8_bytes is carried over verbatim from V1 (asserted here). No scientific
packet content is regenerated.

WHAT CHANGES vs V1
  * price_table_version -> item6_stage1_price_table_v2;
  * input/output price annotations -> 3.30 / 16.50;
  * per_call_max_reservation_usd and max_reserved_stage1_generation_spend_usd -> recomputed
    at the corrected US-geo prices (byte-ceiling worst case);
  * explicit request_bytes_unchanged_vs_v1 = true provenance.

WHAT IS IDENTICAL vs V1
  * n_fixtures, cohort hash, prompt hash, request builder version, byte ceiling;
  * EVERY per-fixture skeleton request hash + byte length (byte-identical requests).

Produces research/item6/out/execution/ITEM6_STAGE1_REQUEST_SET_V2.json and prints
STAGE1_REQUEST_SET_V2_SHA256. Re-running is byte-idempotent.
"""
from __future__ import annotations

import hashlib
import json
import os

from src.research.item6.execution import request_builder as RB
from src.research.item6.execution import execution_status as ES

ROOT = "/home/ubuntu"
V1 = f"{ROOT}/research/item6/out/execution/ITEM6_STAGE1_REQUEST_SET_V1.json"
PRICE_V2 = f"{ROOT}/research/item6/ITEM6_STAGE1_PRICE_TABLE_V2.json"
OUT_DIR = f"{ROOT}/research/item6/out/execution"
OUT = f"{OUT_DIR}/ITEM6_STAGE1_REQUEST_SET_V2.json"

REQUEST_SET_VERSION = "item6_stage1_request_set_v2"

# Planning estimates reused verbatim from the V1 builder (NOT the enforced cap).
EST_INPUT_TOKENS_PER_CALL = 6500
EST_OUTPUT_TOKENS_PER_CALL = 1800
P90_INPUT_TOKENS_PER_CALL = 9000
P90_OUTPUT_TOKENS_PER_CALL = 3500


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def main() -> None:
    v1 = json.load(open(V1))
    price = json.load(open(PRICE_V2))
    in_price_1k = float(price["input_price_usd_per_1k_tokens"])
    out_price_1k = float(price["output_price_usd_per_1k_tokens"])

    # Carry the V1 skeleton entries VERBATIM (request bytes are price-independent and unchanged).
    entries = v1["entries"]
    # HARD INVARIANT: request bytes byte-identical vs V1 -- re-derive from the frozen builder
    # and confirm each skeleton hash/byte-length matches V1 exactly.
    system_text = RB.load_frozen_system_text(ROOT)
    cohort = json.load(open(f"{ROOT}/research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json"))
    by_id = {fx["fixture_id"]: fx for fx in cohort["fixtures"]}
    for e in entries:
        fx = by_id[e["fixture_id"]]
        req = RB.canonical_request(fx, system_text, evidence_packet=None)
        assert RB.request_sha256(req) == e["skeleton_request_sha256"], (
            f"REQUEST BYTE DRIFT vs V1 for {e['fixture_id']}")
        assert RB.request_byte_len(req) == e["skeleton_request_utf8_bytes"], (
            f"REQUEST BYTE-LEN DRIFT vs V1 for {e['fixture_id']}")

    # Recompute worst-case reservation at the CORRECTED US-geo prices.
    max_in_bound = RB.MAX_REQUEST_UTF8_BYTES
    max_call_reservation = (max_in_bound / 1000.0 * in_price_1k
                            + RB.MAX_TOKENS / 1000.0 * out_price_1k)
    max_reserved_total = round(max_call_reservation * ES.ABSOLUTE_MAX_PAID_CALLS, 6)

    expected_total = round(
        (EST_INPUT_TOKENS_PER_CALL / 1000.0 * in_price_1k
         + EST_OUTPUT_TOKENS_PER_CALL / 1000.0 * out_price_1k) * 120, 6)
    p90_total = round(
        (P90_INPUT_TOKENS_PER_CALL / 1000.0 * in_price_1k
         + P90_OUTPUT_TOKENS_PER_CALL / 1000.0 * out_price_1k) * 120, 6)

    doc = {
        "request_set_version": REQUEST_SET_VERSION,
        "supersedes_request_set_version": v1["request_set_version"],
        "predecessor_request_set_sha256": v1["request_set_sha256"],
        "amendment": "ITEM6_STAGE1_US_GEO_CONSERVATIVE_PRICE_FREEZE",
        "amendment_scope": "SPEND_CONTROL_ACCOUNTING_ONLY_NO_SCIENTIFIC_CHANGE",
        "request_bytes_unchanged_vs_v1": True,
        "request_bytes_unchanged_note": ("Request bytes are scientifically and byte-identically "
                                         "unchanged vs V1: every per-fixture skeleton request "
                                         "hash and UTF-8 byte length is carried over verbatim "
                                         "and re-verified from the frozen request builder. Only "
                                         "the price-table binding and cost-planning annotations "
                                         "changed."),
        "n_fixtures": v1["n_fixtures"],
        "k_mechanisms_per_fixture": v1["k_mechanisms_per_fixture"],
        "model_calls_per_fixture": v1["model_calls_per_fixture"],
        "planned_primary_model_calls": v1["planned_primary_model_calls"],
        "absolute_max_paid_calls": v1["absolute_max_paid_calls"],
        "cohort_manifest_sha256": v1["cohort_manifest_sha256"],
        "request_builder_version": v1["request_builder_version"],
        "prompt_sha256": v1["prompt_sha256"],
        "max_request_utf8_bytes": v1["max_request_utf8_bytes"],
        "skeleton_note": v1["skeleton_note"],
        "request_bytes_min": v1["request_bytes_min"],
        "request_bytes_p50": v1["request_bytes_p50"],
        "request_bytes_p90": v1["request_bytes_p90"],
        "request_bytes_max": v1["request_bytes_max"],
        # corrected price binding
        "price_table_version": price["price_table_version"],
        "model_profile_scope": price["model_profile_scope"],
        "price_bound_type": price["price_bound_type"],
        "input_price_usd_per_mtok": price["input_price_usd_per_mtok"],
        "output_price_usd_per_mtok": price["output_price_usd_per_mtok"],
        "per_call_max_reservation_usd": round(max_call_reservation, 7),
        "reservation_input_token_bound_per_call": max_in_bound,
        "reservation_output_tokens_per_call": RB.MAX_TOKENS,
        "expected_stage1_generation_spend_usd": expected_total,
        "p90_stage1_generation_spend_usd": p90_total,
        "max_reserved_stage1_generation_spend_usd": max_reserved_total,
        "entries": entries,
    }
    set_hash = hashlib.sha256(_canon(doc)).hexdigest()
    doc["request_set_sha256"] = set_hash

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    print(f"[request-set-v2] wrote {OUT}")
    print(f"[request-set-v2] STAGE1_REQUEST_SET_V2_SHA256={set_hash}")
    print(f"[request-set-v2] per_call_max_reservation_usd={max_call_reservation!r}")
    print(f"[request-set-v2] MAX_RESERVED={max_reserved_total}")
    print(f"[request-set-v2] request_bytes_unchanged_vs_v1=True")


if __name__ == "__main__":
    main()
