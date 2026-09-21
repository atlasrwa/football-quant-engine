"""Build the FROZEN Item 6 Stage-1 offline request set (B4). ZERO SPEND, no network.

Constructs all 120 canonical Converse request SKELETONS (system=frozen prompt body,
tool schema from frozen mechanism schema, deterministic inference config, per-fixture
identity from the immutable cohort manifest, EMPTY evidence-packet placeholder), records
per-fixture request hash + UTF-8 byte count + reservation input-token bound, and produces:

  research/item6/out/execution/ITEM6_STAGE1_REQUEST_SET_V1.json
  STAGE1_REQUEST_SET_SHA256  (canonical hash of the whole set)

It also computes the spend authorization numbers under the frozen price table:
  EXPECTED / P90 / MAX_RESERVED generation spend, where MAX_RESERVED uses the frozen
  per-request byte-based input-token upper bound + frozen MAX_TOKENS output, at 120 calls.

The evidence packet is materialized by the live pipeline at run time; the frozen byte budget
(request_builder.MAX_REQUEST_UTF8_BYTES) bounds every admissible request, so MAX_RESERVED is
a true upper bound the runner enforces per call.
"""
from __future__ import annotations

import hashlib
import json
import os

from src.research.item6.execution import request_builder as RB
from src.research.item6.execution import execution_status as ES

ROOT = "/home/ubuntu"
COHORT = f"{ROOT}/research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json"
PRICE = f"{ROOT}/research/item6/ITEM6_STAGE1_PRICE_TABLE_V1.json"
OUT_DIR = f"{ROOT}/research/item6/out/execution"
OUT = f"{OUT_DIR}/ITEM6_STAGE1_REQUEST_SET_V1.json"

REQUEST_SET_VERSION = "item6_stage1_request_set_v1"

# Planning estimates for EXPECTED / P90 realized spend (NOT the enforced cap). These reuse
# the frozen power/cost artifact's per-call token expectations (input ~6500, output ~1800;
# P90 output ~ larger). MAX_RESERVED is the enforced worst case and does not depend on them.
EST_INPUT_TOKENS_PER_CALL = 6500
EST_OUTPUT_TOKENS_PER_CALL = 1800
P90_INPUT_TOKENS_PER_CALL = 9000
P90_OUTPUT_TOKENS_PER_CALL = 3500


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def main() -> None:
    cohort = json.load(open(COHORT))
    fixtures = cohort["fixtures"]
    assert len(fixtures) == 120, f"expected 120 fixtures, got {len(fixtures)}"
    price = json.load(open(PRICE))
    in_price_1k = float(price["input_price_usd_per_1k_tokens"])
    out_price_1k = float(price["output_price_usd_per_1k_tokens"])

    system_text = RB.load_frozen_system_text(ROOT)

    entries = []
    byte_lens = []
    for fx in fixtures:
        req = RB.canonical_request(fx, system_text, evidence_packet=None)
        blen = RB.request_byte_len(req)
        byte_lens.append(blen)
        entries.append({
            "fixture_id": fx["fixture_id"],
            "skeleton_request_sha256": RB.request_sha256(req),
            "skeleton_request_utf8_bytes": blen,
            "reservation_input_token_bound": RB.reservation_input_token_bound(req),
            "max_output_tokens": RB.MAX_TOKENS,
            "model_profile_id": RB.MODEL_PROFILE_ID,
            "within_byte_budget": RB.within_byte_budget(req),
        })

    byte_lens.sort()
    n = len(byte_lens)
    p50 = byte_lens[n // 2]
    p90 = byte_lens[min(n - 1, int(round(0.9 * (n - 1))))]

    # Per-call MAX reservation uses the frozen byte ceiling as the input-token upper bound.
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
        "n_fixtures": len(fixtures),
        "k_mechanisms_per_fixture": 5,
        "model_calls_per_fixture": ES.MODEL_CALLS_PER_FIXTURE,
        "planned_primary_model_calls": 120,
        "absolute_max_paid_calls": ES.ABSOLUTE_MAX_PAID_CALLS,
        "cohort_manifest_sha256": "f92cd6a23c1bc3a8e7f8fe5eabff9d1bf643802f42c6261ba069f128bfeaf54b",
        "request_builder_version": RB.REQUEST_BUILDER_VERSION,
        "prompt_sha256": RB.ITEM6_PROMPT_SHA256,
        "max_request_utf8_bytes": RB.MAX_REQUEST_UTF8_BYTES,
        "skeleton_note": ("Requests are SKELETONS with an empty evidence_packet placeholder; "
                          "the live pipeline materializes the point-in-time-safe packet at "
                          "run time and the runner refuses any request exceeding "
                          "max_request_utf8_bytes."),
        "request_bytes_min": byte_lens[0],
        "request_bytes_p50": p50,
        "request_bytes_p90": p90,
        "request_bytes_max": byte_lens[-1],
        "price_table_version": price["price_table_version"],
        "input_price_usd_per_mtok": price["input_price_usd_per_mtok"],
        "output_price_usd_per_mtok": price["output_price_usd_per_mtok"],
        "per_call_max_reservation_usd": round(max_call_reservation, 6),
        "reservation_input_token_bound_per_call": max_in_bound,
        "reservation_output_tokens_per_call": RB.MAX_TOKENS,
        "expected_stage1_generation_spend_usd": expected_total,
        "p90_stage1_generation_spend_usd": p90_total,
        "max_reserved_stage1_generation_spend_usd": max_reserved_total,
        "entries": entries,
    }
    # canonical hash EXCLUDING the self field
    set_hash = hashlib.sha256(_canon(doc)).hexdigest()
    doc["request_set_sha256"] = set_hash

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    print(f"[request-set] wrote {OUT}")
    print(f"[request-set] STAGE1_REQUEST_SET_SHA256={set_hash}")
    print(f"[request-set] bytes min/p50/p90/max = "
          f"{byte_lens[0]}/{p50}/{p90}/{byte_lens[-1]}")
    print(f"[request-set] per_call_max_reservation_usd={max_call_reservation:.6f}")
    print(f"[request-set] EXPECTED={expected_total} P90={p90_total} "
          f"MAX_RESERVED={max_reserved_total}")


if __name__ == "__main__":
    main()
