"""10 mandatory tests for the Item 6 Stage-1 US-geo conservative price freeze (V2 price table
/ V3 run manifest). ZERO SPEND, network-killed (conftest). CountTokens is MOCKED with
deterministic local stand-ins; no real Bedrock CountTokens or any Sonnet inference/generation
call is possible.

This amendment corrects the EXECUTION PRICE BASIS only: the frozen US geographic inference
profile us.anthropic.claude-sonnet-4-6 is priced at the conservative US-only Sonnet 4.6
standard-rate basis 3.30 / 16.50 per MTok (was global 3.00 / 15.00). No scientific treatment
changes; no logic redesign.

Mapping to the mission's mandatory test list:
  1  US geo price table = 3.30 / 16.50
  2  worst-case per-call reserve = 0.2433024
  3  worst-case 120-call reserve = 29.196288
  4  CountTokens input reservation uses 3.30/MTok
  5  output reservation uses 16.50/MTok
  6  human ceiling $30 permits the mathematical worst-case run
  7  human ceiling below required next-call reservation blocks before inference
  8  old $3/$15 table cannot be loaded as current Stage-1 execution pricing
  9  no scientific hash changes
  10 no inference/model call occurs
"""
from __future__ import annotations

import hashlib
import json

from src.research.item6.execution import execution_status as ES
from src.research.item6.execution import request_builder as RB
from src.research.item6.execution import token_counter as TC
from src.research.item6.execution.runner import RunnerConfig, Stage1Runner
from src.research.item6.execution.spend_guard import PriceTable
from tests.research.item6.execution.conftest import (NON_LOOPBACK_CONNECTS, make_count_fn)

ROOT = "/home/ubuntu"
PRICE_V1 = f"{ROOT}/research/item6/ITEM6_STAGE1_PRICE_TABLE_V1.json"
PRICE_V2 = f"{ROOT}/research/item6/ITEM6_STAGE1_PRICE_TABLE_V2.json"
RUN_MANIFEST_V3 = f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V3.json"

PRICE = PriceTable.from_json(PRICE_V2)

# Records every real (mock) inference transport invocation across the module.
INFERENCE_CALLS = {"n": 0}


def _inference_fn(response=None):
    def _fn(req):
        INFERENCE_CALLS["n"] += 1
        return response if response is not None else _good_resp()
    return _fn


def _good_resp(input_tokens=6500, output_tokens=1500):
    return {
        "output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"name": "emit_item6_mechanisms",
                         "input": {"fixture_id": "i6_test_0001", "mechanisms": []}}}]}},
        "stopReason": "tool_use",
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens,
                  "totalTokens": input_tokens + output_tokens},
        "modelId": "us.anthropic.claude-sonnet-4-6",
        "_resolved_model_id": "anthropic.claude-sonnet-4-6",
    }


def _runner(tmp_path, ceiling, count_fn) -> Stage1Runner:
    cfg = RunnerConfig(out_dir=str(tmp_path / "exec_out"),
                       human_authorized_ceiling_usd=ceiling,
                       price_table_path=PRICE_V2, verify_identities=False,
                       count_tokens_fn=count_fn)
    return Stage1Runner(cfg)


def _fx(i="i6_test_0001"):
    return {"fixture_id": i, "home_id": "406", "away_id": "425",
            "competition": "comp_16572", "kickoff_unix": 1781352000}


# 1. US geo price table = 3.30 / 16.50.
def test_01_us_geo_price_table_values():
    d = json.load(open(PRICE_V2))
    assert d["price_table_version"] == "item6_stage1_price_table_v2"
    assert d["model_profile_scope"] == "US_GEO"
    assert d["price_bound_type"] == "CONSERVATIVE_US_ONLY_STANDARD_RATE"
    assert d["input_price_usd_per_mtok"] == 3.30
    assert d["output_price_usd_per_mtok"] == 16.50
    assert d["input_price_usd_per_1k_tokens"] == 0.0033
    assert d["output_price_usd_per_1k_tokens"] == 0.0165
    # model/profile preserved, NOT switched to global.
    assert d["model_profile_id"] == "us.anthropic.claude-sonnet-4-6"
    assert d["model_profile_id"] != "global.anthropic.claude-sonnet-4-6"
    assert d["model_profile_unchanged"] is True
    assert d["does_not_switch_to_global_profile"] is True


# 2. worst-case per-call reserve = 0.2433024.
def test_02_worst_case_per_call_reserve():
    per_call = PRICE.call_reservation_usd(RB.MAX_REQUEST_UTF8_BYTES, RB.MAX_TOKENS)
    assert abs(per_call - 0.2433024) < 1e-12


# 3. worst-case 120-call reserve = 29.196288.
def test_03_worst_case_120_call_reserve():
    per_call = PRICE.call_reservation_usd(RB.MAX_REQUEST_UTF8_BYTES, RB.MAX_TOKENS)
    run = per_call * ES.ABSOLUTE_MAX_PAID_CALLS
    assert ES.ABSOLUTE_MAX_PAID_CALLS == 120
    assert abs(run - 29.196288) < 1e-9
    # the V3 run manifest records exactly this.
    m = json.load(open(RUN_MANIFEST_V3))
    wc = m["worst_case_reservation"]
    assert wc["max_reserved_stage1_generation_spend_usd"] == 29.196288
    assert wc["max_total_reserve_per_call_usd"] == 0.2433024


# 4. CountTokens input reservation uses 3.30/MTok.
def test_04_input_reservation_uses_330_per_mtok(tmp_path):
    tokens = 6500
    r = _runner(tmp_path, ceiling=100.0, count_fn=make_count_fn(tokens))
    res = r.run_fixture(_fx(), _inference_fn())
    assert res.status == ES.TRANSPORT_OK
    assert res.provider_counted_input_tokens == tokens
    # isolate the input component of the reservation and confirm the 3.30/MTok basis.
    input_component = PRICE.call_reservation_usd(tokens, 0)
    assert abs(input_component - (tokens * 3.30 / 1_000_000)) < 1e-12
    # and the total reservation = provider-count input @3.30 + frozen MAX output @16.50.
    assert abs(res.reservation_usd
               - PRICE.call_reservation_usd(tokens, RB.MAX_TOKENS)) < 1e-12


# 5. output reservation uses 16.50/MTok.
def test_05_output_reservation_uses_1650_per_mtok(tmp_path):
    tokens = 6500
    r = _runner(tmp_path, ceiling=100.0, count_fn=make_count_fn(tokens))
    res = r.run_fixture(_fx(), _inference_fn())
    assert res.status == ES.TRANSPORT_OK
    output_component = PRICE.call_reservation_usd(0, RB.MAX_TOKENS)
    assert abs(output_component - (RB.MAX_TOKENS * 16.50 / 1_000_000)) < 1e-12
    assert abs(output_component - 0.135168) < 1e-12
    # output is reserved at the frozen MAX_TOKENS (8192), never expected output.
    assert RB.MAX_TOKENS == 8192


# 6. human ceiling $30 permits the mathematical worst-case run.
def test_06_thirty_dollar_ceiling_permits_worst_case(tmp_path):
    # a $30 ceiling admits 120 worst-case (byte-ceiling) reservations without a spend block.
    r = _runner(tmp_path, ceiling=30.00,
                count_fn=make_count_fn(RB.MAX_REQUEST_UTF8_BYTES))  # provider == byte ceiling
    n_ok = 0
    for i in range(ES.ABSOLUTE_MAX_PAID_CALLS):
        res = r.run_fixture(_fx(f"i6_wc_{i}"), _inference_fn())
        assert res.status == ES.TRANSPORT_OK, f"call {i} blocked: {res.status}"
        n_ok += 1
    assert n_ok == 120
    # cumulative reserved is exactly the worst-case run total and within $30.
    assert abs(r.guard.reserved_usd - 29.196288) < 1e-6
    assert r.guard.reserved_usd <= 30.00 + 1e-9
    assert INFERENCE_CALLS["n"] >= 120


# 7. human ceiling below required next-call reservation blocks before inference.
def test_07_ceiling_below_reserve_blocks_before_inference(tmp_path):
    before = INFERENCE_CALLS["n"]
    tokens = RB.MAX_REQUEST_UTF8_BYTES
    one = PRICE.call_reservation_usd(tokens, RB.MAX_TOKENS)  # 0.2433024
    # ceiling one micro-dollar below a single worst-case reservation -> first call blocks.
    r = _runner(tmp_path, ceiling=one - 0.000001, count_fn=make_count_fn(tokens))
    res = r.run_fixture(_fx(), _inference_fn())
    assert res.status == ES.CALL_BLOCKED_BY_SPEND_CAP
    assert not res.transmitted
    assert r.guard.reserved_usd == 0.0
    assert INFERENCE_CALLS["n"] == before  # nothing transmitted


# 8. old $3/$15 table cannot be loaded as current Stage-1 execution pricing.
def test_08_old_global_table_not_current_pricing():
    v1 = json.load(open(PRICE_V1))
    v2 = json.load(open(PRICE_V2))
    # the V1 (global) table is explicitly the PREDECESSOR, not the operative bound.
    assert v1["input_price_usd_per_mtok"] == 3.0
    assert v1["output_price_usd_per_mtok"] == 15.0
    assert v2["supersedes_price_table_version"] == v1["price_table_version"]
    assert v2["predecessor_input_price_usd_per_mtok"] == 3.0
    assert v2["predecessor_output_price_usd_per_mtok"] == 15.0
    # the operative Stage-1 run manifest (V3) binds the V2 table, NOT V1.
    m = json.load(open(RUN_MANIFEST_V3))
    assert m["price_table_version"] == "item6_stage1_price_table_v2"
    assert m["input_price_usd_per_mtok"] == 3.30
    assert m["output_price_usd_per_mtok"] == 16.50
    assert m["execution_artifact_paths"]["price_table"] \
        == "research/item6/ITEM6_STAGE1_PRICE_TABLE_V2.json"
    # loading the V1 global table yields the non-operative 3.00/15.00 basis; the operative
    # reservation math must NOT match it (proves the old table isn't the current pricing).
    old = PriceTable.from_json(PRICE_V1)
    old_per_call = old.call_reservation_usd(RB.MAX_REQUEST_UTF8_BYTES, RB.MAX_TOKENS)
    new_per_call = PRICE.call_reservation_usd(RB.MAX_REQUEST_UTF8_BYTES, RB.MAX_TOKENS)
    assert abs(old_per_call - 0.221184) < 1e-12       # the OLD worst case
    assert abs(new_per_call - 0.2433024) < 1e-12      # the CURRENT worst case
    assert new_per_call > old_per_call                # US-geo basis is conservatively higher


# 9. no scientific hash changes (V3 binds byte-identical scientific hashes vs V1/V2).
def test_09_no_scientific_hash_changes():
    m3 = json.load(open(RUN_MANIFEST_V3))
    m2 = json.load(open(f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V2.json"))
    assert m3["scientific_artifact_hashes"] == m2["scientific_artifact_hashes"]
    assert m3["scientific_artifacts_unchanged_vs_v2"] is True
    # and each recorded scientific hash matches the current on-disk file.
    for key, rel in m3["scientific_artifact_paths"].items():
        got = hashlib.sha256(open(f"{ROOT}/{rel}", "rb").read()).hexdigest()
        assert got == m3["scientific_artifact_hashes"][key], f"scientific drift {key}"
    # CHAMPION unchanged.
    assert m3["champion_sha256"] == m2["champion_sha256"]
    ch = hashlib.sha256(open(f"{ROOT}/{m3['champion_path']}", "rb").read()).hexdigest()
    assert ch == m3["champion_sha256"]
    # the CountTokens implementation is unchanged vs V2 (no logic redesign).
    assert m3["token_counter_code_sha256"] == m2["token_counter_code_sha256"]
    for k in ("spend_guard_code", "runner_code", "execution_status_code",
              "request_builder_code", "token_counter_code"):
        assert m3["execution_artifact_hashes"][k] == m2["execution_artifact_hashes"][k]
    # spend-control invariants preserved.
    assert m3["spend_model"]["provider_token_count_precall"] is True
    assert m3["spend_model"]["count_tokens_failure_blocks_inference"] is True
    assert m3["spend_model"]["request_immutable_after_count"] is True
    assert m3["spend_model"]["byte_ceiling_retained_independently"] is True
    assert m3["spend_model"]["hard_monetary_stop"] is True
    assert m3["max_output_tokens_reserved"] == 8192
    assert m3["max_request_utf8_bytes"] == 32768
    # human ceiling still NOT authorized in this amendment.
    assert m3["spend_model"]["human_authorized_monetary_ceiling_usd"] is None


# 10. no inference/model call occurs (network killed; only mock transport ever invoked).
def test_10_no_real_inference_during_tests(tmp_path):
    r = _runner(tmp_path, ceiling=100.0, count_fn=make_count_fn(6500))
    r.run_fixture(_fx(), _inference_fn())
    assert NON_LOOPBACK_CONNECTS["count"] == 0
    # CountTokens is an execution-control call, not a treatment; and INFERENCE_CALLS only ever
    # counts the LOCAL mock transport, never a paid Bedrock generation.
    assert r.count_counters.n_requests >= 1
    cc = r.count_counters.to_dict()
    assert cc["is_model_inference_treatment"] is False
    assert cc["increments_paid_treatments"] is False
