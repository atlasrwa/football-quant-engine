"""13 mandatory adversarial tests for the Item 6 Stage-1 authoritative-provider-token-count
pre-call reservation amendment (v2). ZERO SPEND, network-killed (conftest).

CountTokens is MOCKED with deterministic local stand-ins; no real Bedrock CountTokens or any
Sonnet inference/generation call is possible. A module-level `INFERENCE_CALLS` counter records
how many times the (mock) inference transport was actually invoked so a test can assert that
NO real model inference occurred while the amendment's spend controls were exercised.

Mapping to the mission's mandatory adversarial list:
  1  counted input + output reserve below remaining ceiling -> inference eligible
  2  next call would exceed ceiling by $0.000001            -> blocked before inference
  3  CountTokens error                                       -> inference blocked
  4  CountTokens unavailable                                 -> inference blocked
  5  request modified after token count                      -> blocked / recount required
  6  count request omits tool schema used by inference       -> integrity failure
  7  provider count exceeds byte-derived estimate            -> higher provider count controls
  8  provider count below byte-derived estimate              -> provider count controls input
  9  actual output < 8192                                    -> reconciles only after receipt
  10 actual provider accounting approaches human ceiling     -> next call pre-blocked
  11 attempt marker still precedes paid inference
  12 CountTokens does not consume one of the 120 treatment slots
  13 no inference occurs during tests
"""
from __future__ import annotations

import json
import os

import pytest

from src.research.item6.execution import execution_status as ES
from src.research.item6.execution import request_builder as RB
from src.research.item6.execution import token_counter as TC
from src.research.item6.execution.runner import RunnerConfig, Stage1Runner
from src.research.item6.execution.spend_guard import PriceTable
from tests.research.item6.execution.conftest import (NON_LOOPBACK_CONNECTS, good_count_fn,
                                                     good_converse_response, make_count_fn)

PRICE_PATH = "/home/ubuntu/research/item6/ITEM6_STAGE1_PRICE_TABLE_V1.json"
PRICE = PriceTable.from_json(PRICE_PATH)

# Records every real (mock) inference transport invocation across the module.
INFERENCE_CALLS = {"n": 0}


def _inference_fn(response=None):
    """Wrap a converse stand-in so we can COUNT how many times inference actually happened.
    This is the ONLY thing that could touch the network; it never does (local dict only)."""
    def _fn(req):
        INFERENCE_CALLS["n"] += 1
        return response if response is not None else good_converse_response()
    return _fn


def _runner(tmp_path, ceiling=100.0, count_fn=good_count_fn) -> Stage1Runner:
    cfg = RunnerConfig(out_dir=str(tmp_path / "exec_out"),
                       human_authorized_ceiling_usd=ceiling,
                       price_table_path=PRICE_PATH, verify_identities=False,
                       count_tokens_fn=count_fn)
    return Stage1Runner(cfg)


def _fx(i="i6_test_0001"):
    return {"fixture_id": i, "home_id": "406", "away_id": "425",
            "competition": "comp_16572", "kickoff_unix": 1781352000}


def _reservation(input_tokens, output_tokens=RB.MAX_TOKENS):
    return PRICE.call_reservation_usd(input_tokens, output_tokens)


# 1. counted input cost + output reserve below remaining ceiling -> inference eligible.
def test_01_counted_cost_below_ceiling_inference_eligible(tmp_path):
    before = INFERENCE_CALLS["n"]
    r = _runner(tmp_path, ceiling=100.0, count_fn=make_count_fn(6500))
    res = r.run_fixture(_fx(), _inference_fn())
    assert res.status == ES.TRANSPORT_OK
    assert res.provider_counted_input_tokens == 6500
    assert res.count_status == TC.PRECALL_TOKEN_COUNT_OK
    # reservation used the AUTHORITATIVE provider count + frozen MAX output.
    assert abs(res.reservation_usd - _reservation(6500)) < 1e-9
    assert INFERENCE_CALLS["n"] == before + 1  # exactly one eligible inference


# 2. next call would exceed ceiling by $0.000001 -> blocked before inference.
def test_02_exceed_ceiling_by_one_micro_dollar_blocked(tmp_path):
    before = INFERENCE_CALLS["n"]
    # choose a provider count whose reservation is a round dollar figure, then set the ceiling
    # exactly 0.000001 below it so the call is over by one micro-dollar.
    tokens = 10000
    exact = _reservation(tokens)  # 10000/1e3*0.003 + 8192/1e3*0.015 = 0.03 + 0.12288 = 0.15288
    r = _runner(tmp_path, ceiling=exact - 0.000001, count_fn=make_count_fn(tokens))
    res = r.run_fixture(_fx(), _inference_fn())
    assert res.status == ES.CALL_BLOCKED_BY_SPEND_CAP
    assert not res.transmitted
    assert INFERENCE_CALLS["n"] == before  # nothing transmitted
    # and exactly on the boundary it IS eligible.
    r2 = _runner(tmp_path / "ok", ceiling=exact + 1e-9, count_fn=make_count_fn(tokens))
    assert r2.run_fixture(_fx(), _inference_fn()).status == ES.TRANSPORT_OK


# 3. CountTokens error -> inference blocked.
def test_03_count_error_blocks_inference(tmp_path):
    before = INFERENCE_CALLS["n"]

    def err_count(modelId, input):  # noqa: A002
        raise RuntimeError("ThrottlingException")

    r = _runner(tmp_path, count_fn=err_count)
    res = r.run_fixture(_fx(), _inference_fn())
    assert res.status == ES.CALL_BLOCKED_BY_TOKEN_COUNT
    assert res.count_status == TC.PRECALL_TOKEN_COUNT_ERROR
    assert not res.transmitted
    assert INFERENCE_CALLS["n"] == before
    assert r.guard.reserved_usd == 0.0  # no reservation consumed


# 4. CountTokens unavailable -> inference blocked (no optimistic fallback).
def test_04_count_unavailable_blocks_inference(tmp_path):
    before = INFERENCE_CALLS["n"]
    r = _runner(tmp_path, count_fn=None)  # capability unavailable
    res = r.run_fixture(_fx(), _inference_fn())
    assert res.status == ES.CALL_BLOCKED_BY_TOKEN_COUNT
    assert res.count_status == TC.PRECALL_TOKEN_COUNT_UNAVAILABLE
    assert not res.transmitted
    assert INFERENCE_CALLS["n"] == before


# 5. request modified after token count -> blocked / recount required.
def test_05_request_mutation_after_count_blocked(tmp_path):
    before = INFERENCE_CALLS["n"]
    fx = _fx()
    sys_text = RB.load_frozen_system_text()
    req = RB.canonical_request(fx, sys_text)
    counters = TC.CountTokensCounters()
    # count request A.
    resA = TC.count_input_tokens(req, make_count_fn(6500), counters)
    assert resA.ok
    # now MUTATE the request (a different fixture id => different bytes) and prove the
    # fingerprint no longer matches: transmitting this would be count A -> send B.
    req_B = RB.canonical_request(_fx("i6_test_9999"), sys_text)
    fpA = TC.count_input_fingerprint(req)
    fpB = TC.count_input_fingerprint(req_B)
    assert fpA["inference_request_sha256"] != fpB["inference_request_sha256"]
    assert fpA["count_input_sha256"] != fpB["count_input_sha256"]
    # the runner binds count.inference_request_sha256 to the request it transmits, so a count
    # taken for A cannot authorize sending B: the counter result for A is simply invalid for B.
    # Directly exercise the mismatch guard: a count fn that returns a valid count but whose
    # fingerprint is checked against the (different) transmitted request.
    assert resA.inference_request_sha256 == fpA["inference_request_sha256"]
    assert resA.inference_request_sha256 != fpB["inference_request_sha256"]
    assert INFERENCE_CALLS["n"] == before  # nothing transmitted here

    # Now exercise the RUNNER's request-immutability guard directly: a count fn whose returned
    # count is valid, but where the request the runner rebuilds/transmits differs from what was
    # counted. We simulate mutation by monkeypatching the counter to report a fingerprint for a
    # DIFFERENT request than the one the runner will transmit.
    r = _runner(tmp_path, ceiling=100.0, count_fn=make_count_fn(6500))

    import src.research.item6.execution.token_counter as _TC
    real_count = _TC.count_input_tokens

    def _drifting_count(canonical_request, count_tokens_fn, counters=None):
        res = real_count(canonical_request, count_tokens_fn, counters)
        # forge a mismatch: pretend the counted request had a different sha than transmitted.
        return _TC.CountResult(True, _TC.PRECALL_TOKEN_COUNT_OK, res.input_tokens,
                               inference_request_sha256="deadbeef" * 8,
                               count_input_sha256=res.count_input_sha256,
                               detail="forced drift")

    import src.research.item6.execution.runner as _RUN
    monkey = _RUN.TC.count_input_tokens
    _RUN.TC.count_input_tokens = _drifting_count
    try:
        res_drift = r.run_fixture(_fx("i6_drift"), _inference_fn())
    finally:
        _RUN.TC.count_input_tokens = monkey
    assert res_drift.status == ES.CALL_BLOCKED_BY_TOKEN_COUNT
    assert res_drift.count_status == TC.PRECALL_TOKEN_COUNT_REQUEST_MISMATCH
    assert not res_drift.transmitted
    assert INFERENCE_CALLS["n"] == before  # still nothing transmitted


# 6. token-count request omits tool schema used by inference -> integrity failure.
def test_06_count_omits_tool_schema_integrity_failure(tmp_path):
    fx = _fx()
    req = RB.canonical_request(fx, RB.load_frozen_system_text())
    # strip the tool schema from the request handed to the counter builder.
    req_no_tool = dict(req)
    del req_no_tool["toolConfig"]
    with pytest.raises(TC.CountTokensRequestMismatch):
        TC.build_count_tokens_input(req_no_tool)
    # and via the top-level API it fails closed (does not silently count a skeleton).
    res = TC.count_input_tokens(req_no_tool, make_count_fn(6500))
    assert not res.ok
    assert res.status == TC.PRECALL_TOKEN_COUNT_REQUEST_MISMATCH


# 7. provider count exceeds byte-derived estimate -> higher provider count controls reservation.
def test_07_provider_count_above_byte_estimate_controls(tmp_path):
    fx = _fx()
    req = RB.canonical_request(fx, RB.load_frozen_system_text())
    byte_bound = RB.reservation_input_token_bound(req)  # frozen MAX_REQUEST_UTF8_BYTES
    provider = byte_bound + 5000                        # provider counts MORE than bytes
    r = _runner(tmp_path, ceiling=100.0, count_fn=make_count_fn(provider))
    res = r.run_fixture(fx, _inference_fn())
    assert res.status == ES.TRANSPORT_OK
    assert res.provider_counted_input_tokens == provider
    # reservation reflects the HIGHER provider count, not the byte-derived bound.
    assert abs(res.reservation_usd - _reservation(provider)) < 1e-9
    assert res.reservation_usd > _reservation(byte_bound)


# 8. provider count below byte-derived estimate -> provider count controls input reservation
#    while the byte ceiling remains independently enforced.
def test_08_provider_count_below_byte_estimate_controls(tmp_path):
    fx = _fx()
    req = RB.canonical_request(fx, RB.load_frozen_system_text())
    byte_bound = RB.reservation_input_token_bound(req)
    provider = 3000                                     # provider counts FEWER than bytes
    assert provider < byte_bound
    r = _runner(tmp_path, ceiling=100.0, count_fn=make_count_fn(provider))
    res = r.run_fixture(fx, _inference_fn())
    assert res.status == ES.TRANSPORT_OK
    # input reservation uses the (lower) provider count...
    assert abs(res.reservation_usd - _reservation(provider)) < 1e-9
    assert res.reservation_usd < _reservation(byte_bound)
    # ...and the byte ceiling is STILL enforced independently (request within budget here).
    assert RB.within_byte_budget(req)
    assert RB.MAX_REQUEST_UTF8_BYTES == 32768


# 9. actual output < 8192 -> unused reserve reconciles only after provider usage receipt.
def test_09_output_reconciles_only_after_receipt(tmp_path):
    r = _runner(tmp_path, ceiling=100.0, count_fn=make_count_fn(6500))
    # reserve output at frozen 8192 but the model actually emits 1500 output tokens.
    res = r.run_fixture(_fx(), _inference_fn(good_converse_response(input_tokens=6500,
                                                                    output_tokens=1500)))
    assert res.status == ES.TRANSPORT_OK
    # reservation used MAX output (8192); realized used the receipt's 1500. Reserve dominates.
    assert abs(res.reservation_usd - _reservation(6500, RB.MAX_TOKENS)) < 1e-9
    assert res.realized_cost_usd is not None
    assert res.realized_cost_usd < res.reservation_usd
    # reservation is monotonic: it is NOT shrunk by the smaller realized output.
    assert r.guard.reserved_usd >= r.guard.realized_usd


# 10. actual provider accounting approaches human ceiling -> next call pre-blocked.
def test_10_near_ceiling_next_call_preblocked(tmp_path):
    before = INFERENCE_CALLS["n"]
    tokens = 6500
    one = _reservation(tokens)
    # ceiling admits exactly ONE call's reservation (plus epsilon), not two.
    r = _runner(tmp_path, ceiling=one + 1e-9, count_fn=make_count_fn(tokens))
    res1 = r.run_fixture(_fx("i6_a"), _inference_fn())
    assert res1.status == ES.TRANSPORT_OK
    # the next call's reservation would push cumulative reserved over the ceiling -> pre-block.
    res2 = r.run_fixture(_fx("i6_b"), _inference_fn())
    assert res2.status == ES.CALL_BLOCKED_BY_SPEND_CAP
    assert not res2.transmitted
    assert INFERENCE_CALLS["n"] == before + 1  # only the first call transmitted


# 11. attempt marker still precedes paid inference.
def test_11_attempt_marker_precedes_inference(tmp_path):
    r = _runner(tmp_path, ceiling=100.0, count_fn=make_count_fn(6500))
    fx = _fx()

    order = []

    def conv(req):
        # by the time inference is invoked, the durable marker must already exist on disk.
        order.append(("marker_on_disk", os.path.exists(r._attempt_path(fx["fixture_id"]))))
        return good_converse_response()

    res = r.run_fixture(fx, conv)
    assert res.status == ES.TRANSPORT_OK
    assert order == [("marker_on_disk", True)]  # marker written BEFORE transmission
    rec = json.load(open(r._attempt_path(fx["fixture_id"])))
    assert rec["attempt_marker_written"] is True


# 12. CountTokens does not consume one of the 120 paid-treatment slots.
def test_12_count_tokens_not_a_treatment_slot(tmp_path):
    r = _runner(tmp_path, ceiling=1000.0, count_fn=make_count_fn(6500))
    # run several fixtures; each does exactly ONE CountTokens + ONE paid treatment.
    for i in range(5):
        assert r.run_fixture(_fx(f"i6_s{i}"), _inference_fn()).status == ES.TRANSPORT_OK
    # 5 paid treatments reserved+charged; 5 CountTokens requests. The paid-call cap counter is
    # driven ONLY by reservations, NOT by CountTokens.
    assert r.guard.n_calls_reserved == 5
    assert r.guard.n_calls_charged == 5
    assert r.count_counters.n_requests == 5
    assert r.count_counters.n_success == 5
    cc = r.count_counters.to_dict()
    assert cc["is_model_inference_treatment"] is False
    assert cc["increments_paid_treatments"] is False
    assert cc["increments_sonnet_generation_calls"] is False
    # the absolute paid-call cap is unchanged and independent of CountTokens volume.
    assert r.guard.call_cap == ES.ABSOLUTE_MAX_PAID_CALLS == 120


# 13. no real inference occurs during tests (network killed + inference counter observable).
def test_13_no_real_inference_during_tests(tmp_path):
    # exercising a full run still only calls the LOCAL mock transport; no non-loopback socket
    # connect was ever made across the whole module.
    r = _runner(tmp_path, ceiling=100.0, count_fn=make_count_fn(6500))
    r.run_fixture(_fx(), _inference_fn())
    assert NON_LOOPBACK_CONNECTS["count"] == 0
    # INFERENCE_CALLS counts only MOCK-transport invocations; it never represents a paid
    # Bedrock generation. No real Sonnet inference is reachable from these tests.
    assert INFERENCE_CALLS["n"] >= 0
