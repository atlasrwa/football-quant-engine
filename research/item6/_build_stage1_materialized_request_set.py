"""Build the Item 6 Stage-1 EVIDENCE PACKET SET + MATERIALIZED REQUEST SET V1.

ZERO PAID INFERENCE. Importing/running this builder makes NO Bedrock call and NO LLM call.
It deterministically materializes the PIT evidence packet for every frozen cohort fixture,
binds each packet into the exact canonical Converse request (via the frozen request_builder),
and writes two successor artifacts (it does NOT overwrite the skeleton request sets V1/V2):

  research/item6/out/execution/ITEM6_STAGE1_EVIDENCE_PACKET_SET_V1.json
  research/item6/out/execution/ITEM6_STAGE1_MATERIALIZED_REQUEST_SET_V1.json

For each fixture it binds: fixture_id, information_cutoff (== frozen kickoff), packet_sha256,
canonical request sha256, request UTF-8 bytes, model-visible prompt identity, schema identity,
n_evidence_items, observable vocabulary, provider provenance summary. Also emits set-level
hashes ITEM6_STAGE1_EVIDENCE_PACKET_SET_SHA256 and STAGE1_MATERIALIZED_REQUEST_SET_SHA256 and
cost diagnostics computed from the REAL materialized request byte sizes.

Re-running is byte-idempotent (pure function of frozen cohort + frozen corpus + frozen code).
"""
from __future__ import annotations

import hashlib
import json
import os

from src.research.item6.evidence import packet_materializer as PM
from src.research.item6.execution import request_builder as RB

ROOT = os.environ.get("ITEM6_CODE_ROOT", "/home/ubuntu")          # code + artifacts to hash
DATA_ROOT = os.environ.get("ITEM6_DATA_ROOT", "/home/ubuntu")     # frozen provider corpus
COHORT = f"{ROOT}/research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json"
OUT_DIR = f"{ROOT}/research/item6/out/execution"
PACKET_SET_OUT = f"{OUT_DIR}/ITEM6_STAGE1_EVIDENCE_PACKET_SET_V1.json"
REQ_SET_OUT = f"{OUT_DIR}/ITEM6_STAGE1_MATERIALIZED_REQUEST_SET_V1.json"

PROMPT_PATH = "research/item6/ITEM6_MECHANISM_PROMPT_V1.md"
SCHEMA_PATH = "research/item6/ITEM6_MECHANISM_SCHEMA_V1.md"
CONTRACT_PATH = "research/item6/ITEM6_STAGE1_EVIDENCE_PACKET_CONTRACT_V1.json"
MATERIALIZER_SRC = "src/research/item6/evidence/packet_materializer.py"

# US-geo conservative price bounds (frozen price table v2), for cost diagnostics only.
INPUT_PRICE_USD_PER_MTOK = 3.30
OUTPUT_PRICE_USD_PER_MTOK = 16.50
MAX_OUTPUT_TOKENS = 8192
MAX_REQUEST_UTF8_BYTES = 32768
ABSOLUTE_MAX_PAID_CALLS = 120


def _sha_file(rel: str) -> str:
    with open(f"{ROOT}/{rel}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha_obj(obj) -> str:
    return hashlib.sha256(_canon(obj)).hexdigest()


def _pct(xs, q):
    import math
    s = sorted(xs)
    i = min(len(s) - 1, int(math.ceil(q / 100 * len(s)) - 1))
    return s[max(0, i)]


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    cohort = json.load(open(COHORT))
    fixtures = cohort["fixtures"]
    corpus = PM.load_corpus(DATA_ROOT)
    system_text = RB.load_frozen_system_text(ROOT)

    prompt_sha = _sha_file(PROMPT_PATH)
    schema_sha = _sha_file(SCHEMA_PATH)
    contract_sha = _sha_file(CONTRACT_PATH)
    materializer_sha = _sha_file(MATERIALIZER_SRC)

    packets = []
    req_entries = []
    n_fail = 0
    req_bytes_list = []
    est_input_bytes_list = []

    for fx in fixtures:
        try:
            packet = PM.materialize_item6_evidence_packet(
                fx, fx["kickoff_unix"], corpus=corpus, root=ROOT)
        except PM.MaterializationError as e:
            n_fail += 1
            print(f"[materialize] FAIL {fx['fixture_id']}: {e}")
            continue

        req = RB.canonical_request(fx, system_text, evidence_packet=packet)
        rsha = RB.request_sha256(req)
        rbytes = RB.request_byte_len(req)
        req_bytes_list.append(rbytes)
        est_input_bytes_list.append(rbytes)
        within = RB.within_byte_budget(req)

        packets.append({
            "fixture_id": fx["fixture_id"],
            "source_fixture_id": fx["source_fixture_id"],
            "information_cutoff_unix": packet["information_cutoff_unix"],
            "packet_sha256": packet["packet_sha256"],
            "n_evidence_items": packet["n_evidence_items"],
            "observable_vocabulary": packet["observable_vocabulary"],
            "provider": packet["provider"],
            "provenance_summary": {
                "TEAM_A": packet["provenance"]["TEAM_A"],
                "TEAM_B": packet["provenance"]["TEAM_B"],
            },
            "packet": packet,
        })
        req_entries.append({
            "fixture_id": fx["fixture_id"],
            "source_fixture_id": fx["source_fixture_id"],
            "information_cutoff_unix": packet["information_cutoff_unix"],
            "packet_sha256": packet["packet_sha256"],
            "canonical_request_sha256": rsha,
            "request_utf8_bytes": rbytes,
            "within_byte_budget": within,
            "n_evidence_items": packet["n_evidence_items"],
            "observable_vocabulary": packet["observable_vocabulary"],
            "model_profile_id": RB.MODEL_PROFILE_ID,
            "prompt_sha256": prompt_sha,
            "schema_md_sha256": schema_sha,
        })

    if n_fail != 0:
        raise SystemExit(f"FATAL: {n_fail} packet materialization failures; refusing to freeze.")
    if len(req_entries) != len(fixtures):
        raise SystemExit("FATAL: materialized count != cohort count.")

    # cost diagnostics from REAL request bytes. Input tokens <= request UTF-8 bytes (byte-level
    # BPE upper bound); the runner's authoritative reservation still uses provider CountTokens
    # at live time. These are conservative BYTE-UPPER-BOUND diagnostics, not the hard cap.
    def _byte_bound_input_cost(b):
        return b * INPUT_PRICE_USD_PER_MTOK / 1_000_000.0
    output_cost = MAX_OUTPUT_TOKENS * OUTPUT_PRICE_USD_PER_MTOK / 1_000_000.0
    per_call_byte_bound = [(_byte_bound_input_cost(b) + output_cost) for b in req_bytes_list]
    expected_spend = round(sum(per_call_byte_bound), 6)   # byte-upper-bound sum over 120
    p90_per_call = _pct(per_call_byte_bound, 90)
    # worst-case hard reservation is unchanged (byte ceiling based), NOT lowered here.
    max_reserved = round(ABSOLUTE_MAX_PAID_CALLS
                         * (MAX_REQUEST_UTF8_BYTES * INPUT_PRICE_USD_PER_MTOK / 1_000_000.0
                            + output_cost), 6)

    packet_set = {
        "artifact_version": "item6_stage1_evidence_packet_set_v1",
        "contract_version": "item6_stage1_evidence_packet_contract_v1",
        "contract_sha256": contract_sha,
        "materializer_source_sha256": materializer_sha,
        "materializer_version": PM.MATERIALIZER_VERSION,
        "cohort_manifest_sha256": _sha_file("research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json"),
        "n_fixtures": len(packets),
        "n_packet_materialization_failures": n_fail,
        "provider": PM.PROVIDER,
        "packets": packets,
    }
    packet_set["evidence_packet_set_sha256"] = _sha_obj(
        {k: v for k, v in packet_set.items() if k != "evidence_packet_set_sha256"})

    req_set = {
        "artifact_version": "item6_stage1_materialized_request_set_v1",
        "supersedes_skeleton_request_set_version": "item6_stage1_request_set_v2",
        "does_not_overwrite_skeleton_sets": True,
        "contract_version": "item6_stage1_evidence_packet_contract_v1",
        "contract_sha256": contract_sha,
        "materializer_source_sha256": materializer_sha,
        "materializer_version": PM.MATERIALIZER_VERSION,
        "evidence_packet_set_sha256": packet_set["evidence_packet_set_sha256"],
        "cohort_manifest_sha256": packet_set["cohort_manifest_sha256"],
        "prompt_sha256": prompt_sha,
        "schema_md_sha256": schema_sha,
        "model_profile_id": RB.MODEL_PROFILE_ID,
        "model_id": RB.BASE_MODEL_ID,
        "max_request_utf8_bytes": MAX_REQUEST_UTF8_BYTES,
        "n_fixtures": len(req_entries),
        "all_within_byte_budget": all(e["within_byte_budget"] for e in req_entries),
        "request_bytes_min": min(req_bytes_list),
        "request_bytes_p50": _pct(req_bytes_list, 50),
        "request_bytes_p90": _pct(req_bytes_list, 90),
        "request_bytes_max": max(req_bytes_list),
        "cost_diagnostics_byte_upper_bound": {
            "input_price_usd_per_mtok": INPUT_PRICE_USD_PER_MTOK,
            "output_price_usd_per_mtok": OUTPUT_PRICE_USD_PER_MTOK,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "expected_stage1_spend_usd_byte_upper_bound": expected_spend,
            "p90_per_call_usd_byte_upper_bound": round(p90_per_call, 6),
            "max_reserved_stage1_spend_usd_byte_ceiling": max_reserved,
            "note": ("Byte-upper-bound diagnostics only (input tokens <= request UTF-8 bytes). "
                     "The hard worst-case reservation (max_reserved) is the frozen byte-ceiling "
                     "figure and is NOT lowered. Live reservation uses authoritative provider "
                     "CountTokens per call."),
        },
        "entries": req_entries,
    }
    req_set["materialized_request_set_sha256"] = _sha_obj(
        {k: v for k, v in req_set.items() if k != "materialized_request_set_sha256"})

    with open(PACKET_SET_OUT, "w") as f:
        json.dump(packet_set, f, indent=1, sort_keys=True)
    with open(REQ_SET_OUT, "w") as f:
        json.dump(req_set, f, indent=1, sort_keys=True)

    print(f"[build] wrote {PACKET_SET_OUT}")
    print(f"[build] wrote {REQ_SET_OUT}")
    print(f"[build] n_fixtures={len(req_entries)} fails={n_fail}")
    print(f"[build] ITEM6_STAGE1_EVIDENCE_PACKET_SET_SHA256={packet_set['evidence_packet_set_sha256']}")
    print(f"[build] STAGE1_MATERIALIZED_REQUEST_SET_SHA256={req_set['materialized_request_set_sha256']}")
    print(f"[build] request_bytes max={max(req_bytes_list)} all_within_budget="
          f"{req_set['all_within_byte_budget']}")
    print(f"[build] expected_spend_byte_upper_bound=${expected_spend} "
          f"max_reserved_byte_ceiling=${max_reserved}")


if __name__ == "__main__":
    main()
