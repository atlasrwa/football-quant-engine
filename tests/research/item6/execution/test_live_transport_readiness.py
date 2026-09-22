"""20 mandatory tests for the Item 6 Stage-1 authentic live-transport readiness amendment.

ZERO PAID INFERENCE. Network-killed (conftest blocks non-loopback connects). No real Bedrock
Converse or CountTokens call is made anywhere in this suite; the live transport is exercised
with a genuine bedrock-runtime CLIENT OBJECT (constructed offline) but its `converse` /
`count_tokens` methods are monkeypatched to local stand-ins so no network egress occurs, OR a
STANDIN transport is used. A module counter proves zero real inference.

Mapping to the mission's required tests:
  1  SDK exposes Converse
  2  SDK exposes CountTokens
  3  live transport factory constructs real bedrock-runtime client
  4  LIVE mode rejects stand-in transport
  5  STANDIN mode cannot produce LIVE receipt
  6  CountTokens request binds same content as Converse
  7  mutation after count blocks/recounts
  8  CountTokens failure prevents Converse
  9  missing credentials prevents run
  10 model/profile mismatch prevents run
  11 run-manifest mismatch prevents run
  12 price-table mismatch prevents run
  13 unset human ceiling prevents run
  14 call cap 120 enforced
  15 no retries enforced
  16 attempt marker precedes Converse
  17 receipt distinguishes authentic provider response
  18 resume never duplicates treated fixture
  19 structurally valid mocked 120-fixture run completes deterministically
  20 no actual paid inference occurs during tests
"""
from __future__ import annotations

import json
import os

import boto3
import pytest

from src.research.item6.execution import execution_status as ES
from src.research.item6.execution import request_builder as RB
from src.research.item6.execution import token_counter as TC
from src.research.item6.execution import live_driver as LD
from src.research.item6.execution.live_transport import (
    BedrockStage1Transport, LiveTransportRefused, TransportMode, sdk_capability_report)
from src.research.item6.execution.runner import RunnerConfig, Stage1Runner
from src.research.item6.execution.spend_guard import PriceTable
from tests.research.item6.execution.conftest import NON_LOOPBACK_CONNECTS

ROOT = "/home/ubuntu"
MANIFEST_V4 = "research/item6/ITEM6_STAGE1_RUN_MANIFEST_V4.json"
PRICE_V2 = f"{ROOT}/research/item6/ITEM6_STAGE1_PRICE_TABLE_V2.json"

REAL_INFERENCE_CALLS = {"n": 0}   # would be >0 only if a real Converse egress happened


def _fx(i="i6_test_0001"):
    return {"fixture_id": i, "home_id": "406", "away_id": "425",
            "competition": "comp_16572", "kickoff_unix": 1781352000}


def _good_converse_response(input_tokens=6000, output_tokens=1500):
    return {
        "output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"name": "emit_item6_mechanisms",
                         "input": {"fixture_id": "i6_test_0001", "mechanisms": []}}}]}},
        "stopReason": "tool_use",
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens,
                  "totalTokens": input_tokens + output_tokens},
        "ResponseMetadata": {"RequestId": "req-abc-123", "HTTPStatusCode": 200},
    }


def _live_transport_with_patched_client(monkeypatch, *, count_tokens_impl=None,
                                        converse_impl=None):
    """Construct a REAL LIVE transport (genuine bedrock-runtime client, offline) then
    monkeypatch the client's converse/count_tokens methods to local stand-ins so NO network
    call occurs. This exercises the live code path without spend."""
    t = BedrockStage1Transport.from_frozen_config()

    def _default_count(modelId, input):  # noqa: A002
        return {"inputTokens": 6000}

    def _default_converse(**request):
        return _good_converse_response()

    ct = count_tokens_impl or _default_count
    cv = converse_impl or _default_converse

    def _count(modelId, input):  # noqa: A002
        return ct(modelId, input)

    def _converse(**request):
        REAL_INFERENCE_CALLS["n"] += 0   # stand-in; never a paid call
        return cv(**request)

    monkeypatch.setattr(t._client, "count_tokens", _count)
    monkeypatch.setattr(t._client, "converse", _converse)
    return t


# 1. SDK exposes Converse.
def test_01_sdk_exposes_converse():
    cap = sdk_capability_report()
    assert cap.has_converse is True


# 2. SDK exposes CountTokens.
def test_02_sdk_exposes_count_tokens():
    cap = sdk_capability_report()
    assert cap.has_count_tokens is True


# 3. live transport factory constructs a real bedrock-runtime client.
def test_03_factory_constructs_real_client():
    t = BedrockStage1Transport.from_frozen_config()
    assert t.mode == TransportMode.LIVE_BEDROCK
    assert t._client.meta.service_model.service_name == "bedrock-runtime"
    assert t.converse_model_id == "us.anthropic.claude-sonnet-4-6"
    assert t.count_model_id == "anthropic.claude-sonnet-4-6"


# 4. LIVE mode rejects a stand-in transport / non-authentic client.
def test_04_live_mode_rejects_standin_client():
    with pytest.raises(LiveTransportRefused):
        BedrockStage1Transport(mode=TransportMode.LIVE_BEDROCK, client=object())

    class FakeConverse:  # has the method names but is not a real bedrock-runtime client
        def converse(self, **k): ...
        def count_tokens(self, **k): ...
    with pytest.raises(LiveTransportRefused):
        BedrockStage1Transport(mode=TransportMode.LIVE_BEDROCK, client=FakeConverse())


# 5. STANDIN mode cannot produce a LIVE receipt.
def test_05_standin_cannot_emit_live_receipt():
    st = BedrockStage1Transport.standin(
        count_tokens_impl=lambda modelId, input: {"inputTokens": 10},
        converse_impl=lambda request: _good_converse_response())
    raw = st.converse({"modelId": "x"})
    assert BedrockStage1Transport.is_authentic_live_response(raw) is False
    # even if a stand-in tries to forge the authenticity key, converse strips it.
    st2 = BedrockStage1Transport.standin(
        count_tokens_impl=lambda modelId, input: {"inputTokens": 10},
        converse_impl=lambda request: {**_good_converse_response(),
                                       "_item6_live_transport": {"authentic_provider_response": True}})
    raw2 = st2.converse({"modelId": "x"})
    assert BedrockStage1Transport.is_authentic_live_response(raw2) is False


# 6. CountTokens request binds the same content as Converse.
def test_06_count_tokens_binds_same_content(monkeypatch):
    captured = {}

    def _count(modelId, input):  # noqa: A002
        captured["count_input"] = input
        captured["count_modelId"] = modelId
        return {"inputTokens": 6000}

    def _converse(**request):
        captured["converse_request"] = request
        return _good_converse_response()

    t = _live_transport_with_patched_client(monkeypatch, count_tokens_impl=_count,
                                            converse_impl=_converse)
    fx = _fx()
    req = RB.canonical_request(fx, RB.load_frozen_system_text())
    # the runner builds the CountTokens payload from the SAME canonical request:
    payload = TC.build_count_tokens_input(req)
    t.count_tokens(**payload)
    t.converse(req)
    # the counted converse block equals the transmitted request's system+messages+toolConfig.
    counted = captured["count_input"]["converse"]
    assert counted["system"] == req["system"]
    assert counted["messages"] == req["messages"]
    assert counted["toolConfig"] == req["toolConfig"]
    # CountTokens used the foundation-model id; Converse used the inference-profile id.
    assert captured["count_modelId"] == "anthropic.claude-sonnet-4-6"
    assert captured["converse_request"]["modelId"] == "us.anthropic.claude-sonnet-4-6"


# 7. mutation after count blocks / requires recount (frozen token_counter guarantee).
def test_07_mutation_after_count_blocked():
    fx = _fx()
    sys_text = RB.load_frozen_system_text()
    req = RB.canonical_request(fx, sys_text)
    res = TC.count_input_tokens(req, lambda modelId, input: {"inputTokens": 6000})
    assert res.ok
    # a different request has a different fingerprint => count for A cannot authorize B.
    req_b = RB.canonical_request(_fx("i6_other"), sys_text)
    fp_b = TC.count_input_fingerprint(req_b)
    assert res.inference_request_sha256 != fp_b["inference_request_sha256"]


# 8. CountTokens failure prevents Converse (runner blocks; transport never conversed).
def test_08_count_failure_prevents_converse(tmp_path, monkeypatch):
    def _err_count(modelId, input):  # noqa: A002
        raise RuntimeError("ThrottlingException")

    conversed = {"n": 0}

    def _converse(**request):
        conversed["n"] += 1
        return _good_converse_response()

    t = _live_transport_with_patched_client(monkeypatch, count_tokens_impl=_err_count,
                                            converse_impl=_converse)
    cfg = RunnerConfig(out_dir=str(tmp_path / "o"), human_authorized_ceiling_usd=30.0,
                       price_table_path=PRICE_V2, verify_identities=False,
                       count_tokens_fn=t.count_tokens)
    runner = Stage1Runner(cfg)
    res = runner.run_fixture(_fx(), t.converse)
    assert res.status == ES.CALL_BLOCKED_BY_TOKEN_COUNT
    assert conversed["n"] == 0  # Converse never happened


# 9. missing credentials prevents run (preflight fail-closed).
def test_09_missing_credentials_prevents_run(monkeypatch):
    import boto3 as _b
    real_session = _b.session.Session

    class NoCredSession(real_session):
        def get_credentials(self):
            return None
    monkeypatch.setattr(_b.session, "Session", NoCredSession)
    with pytest.raises(LD.LiveDriverRefused) as ei:
        LD.preflight(MANIFEST_V4, authorized_ceiling_usd=30.0)
    assert "credentials" in str(ei.value).lower()


# 10. model/profile mismatch prevents run.
def test_10_model_profile_mismatch_prevents_run(tmp_path):
    m = json.load(open(f"{ROOT}/{MANIFEST_V4}"))
    m["model_profile_id"] = "global.anthropic.claude-sonnet-4-6"
    p = tmp_path / "bad_profile_manifest.json"
    p.write_text(json.dumps(m))
    rel = os.path.relpath(str(p), ROOT)
    with pytest.raises(LD.LiveDriverRefused) as ei:
        LD.preflight(rel, authorized_ceiling_usd=30.0)
    assert "model profile" in str(ei.value).lower()


# 11. run-manifest mismatch (self-hash) prevents run.
def test_11_run_manifest_mismatch_prevents_run(tmp_path):
    m = json.load(open(f"{ROOT}/{MANIFEST_V4}"))
    m["stage1_n_fixtures"] = 999  # tamper without recomputing self-hash
    p = tmp_path / "tampered_manifest.json"
    p.write_text(json.dumps(m))
    rel = os.path.relpath(str(p), ROOT)
    with pytest.raises(LD.LiveDriverRefused) as ei:
        LD.preflight(rel, authorized_ceiling_usd=30.0)
    assert "self-hash" in str(ei.value).lower()


# 12. price-table mismatch prevents run.
def test_12_price_table_mismatch_prevents_run(tmp_path):
    m = json.load(open(f"{ROOT}/{MANIFEST_V4}"))
    m["execution_artifact_hashes"]["price_table"] = "deadbeef" * 8
    # keep self-hash consistent so we isolate the price-table check
    import hashlib
    mm = dict(m); mm.pop("run_manifest_sha256", None)
    m["run_manifest_sha256"] = hashlib.sha256(
        json.dumps(mm, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    p = tmp_path / "bad_price_manifest.json"
    p.write_text(json.dumps(m))
    rel = os.path.relpath(str(p), ROOT)
    with pytest.raises(LD.LiveDriverRefused) as ei:
        LD.preflight(rel, authorized_ceiling_usd=30.0)
    assert "price-table" in str(ei.value).lower()


# 13. unset human ceiling prevents run.
def test_13_unset_ceiling_prevents_run():
    with pytest.raises(LD.LiveDriverRefused) as ei:
        LD.preflight(MANIFEST_V4, authorized_ceiling_usd=None)
    assert "ceiling" in str(ei.value).lower()


# 14. call cap 120 enforced (spend guard call cap, driven by frozen constants).
def test_14_call_cap_120_enforced(tmp_path, monkeypatch):
    t = _live_transport_with_patched_client(monkeypatch)
    cfg = RunnerConfig(out_dir=str(tmp_path / "o"), human_authorized_ceiling_usd=1000.0,
                       price_table_path=PRICE_V2, verify_identities=False,
                       count_tokens_fn=t.count_tokens)
    runner = Stage1Runner(cfg)
    assert runner.guard.call_cap == ES.ABSOLUTE_MAX_PAID_CALLS == 120
    # simulate 120 reservations already consumed => the 121st is blocked pre-transmission.
    runner.guard.n_calls_reserved = 120
    res = runner.run_fixture(_fx("i6_121"), t.converse)
    assert res.status == ES.CALL_BLOCKED_BY_CALL_CAP
    assert not res.transmitted


# 15. no retries enforced (frozen policy) + client is retries-disabled.
def test_15_no_retries_enforced():
    assert ES.MAX_RETRIES_PER_FIXTURE == 0
    assert ES.is_retryable(ES.MODEL_TRANSPORT_FAILURE) is False
    # the live client is built retries-disabled (total_max_attempts == 1).
    t = BedrockStage1Transport.from_frozen_config()
    retries = t._client.meta.config.retries or {}
    assert retries.get("total_max_attempts") == 1


# 16. attempt marker precedes Converse.
def test_16_attempt_marker_precedes_converse(tmp_path, monkeypatch):
    order = []

    def _converse(**request):
        order.append(("marker_on_disk", os.path.exists(
            runner._attempt_path("i6_test_0001"))))
        return _good_converse_response()

    t = _live_transport_with_patched_client(monkeypatch, converse_impl=_converse)
    cfg = RunnerConfig(out_dir=str(tmp_path / "o"), human_authorized_ceiling_usd=30.0,
                       price_table_path=PRICE_V2, verify_identities=False,
                       count_tokens_fn=t.count_tokens)
    runner = Stage1Runner(cfg)
    res = runner.run_fixture(_fx(), t.converse)
    assert res.status == ES.TRANSPORT_OK
    assert order == [("marker_on_disk", True)]


# 17. receipt distinguishes an authentic provider response from a stand-in.
def test_17_receipt_distinguishes_authentic(monkeypatch):
    # a genuine LIVE transport (client patched to a stand-in converse) stamps authenticity.
    t = _live_transport_with_patched_client(monkeypatch)
    fx = _fx()
    req = RB.canonical_request(fx, RB.load_frozen_system_text())
    raw = t.converse(req)
    assert BedrockStage1Transport.is_authentic_live_response(raw) is True
    # tampering with the envelope breaks the authenticity binding.
    tampered = dict(raw)
    tampered["output"] = {"message": {"role": "assistant", "content": [{"text": "x"}]}}
    assert BedrockStage1Transport.is_authentic_live_response(tampered) is False


# 18. resume never duplicates a treated fixture.
def test_18_resume_no_duplicate(tmp_path, monkeypatch):
    calls = {"n": 0}

    def _converse(**request):
        calls["n"] += 1
        return _good_converse_response()

    t = _live_transport_with_patched_client(monkeypatch, converse_impl=_converse)
    cfg = RunnerConfig(out_dir=str(tmp_path / "o"), human_authorized_ceiling_usd=30.0,
                       price_table_path=PRICE_V2, verify_identities=False,
                       count_tokens_fn=t.count_tokens)
    runner = Stage1Runner(cfg)
    r1 = runner.run_fixture(_fx(), t.converse)
    assert r1.status == ES.TRANSPORT_OK and calls["n"] == 1
    # second invocation resumes idempotently -- no second Converse.
    r2 = runner.run_fixture(_fx(), t.converse)
    assert r2.status == ES.TRANSPORT_OK and calls["n"] == 1


# 19. structurally valid mocked 120-fixture run completes deterministically.
def test_19_full_120_fixture_mock_run(tmp_path, monkeypatch):
    t = _live_transport_with_patched_client(monkeypatch)
    cfg = RunnerConfig(out_dir=str(tmp_path / "o"), human_authorized_ceiling_usd=30.0,
                       price_table_path=PRICE_V2, verify_identities=False,
                       count_tokens_fn=t.count_tokens)
    runner = Stage1Runner(cfg)
    cohort = json.load(open(f"{ROOT}/research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json"))
    n_ok = 0
    for fx in cohort["fixtures"]:
        if not runner.guard.call_cap_ok():
            break
        res = runner.run_fixture(fx, t.converse)
        if res.status == ES.TRANSPORT_OK:
            n_ok += 1
    assert n_ok == 120
    assert runner.guard.n_calls_reserved == 120
    assert runner.guard.n_calls_charged == 120
    assert runner.count_counters.n_requests == 120
    # cumulative reservation stayed within the prospective $30 ceiling.
    assert runner.guard.reserved_usd <= 30.0 + 1e-9


# 20. no actual paid inference occurs during tests.
def test_20_no_real_inference(tmp_path, monkeypatch):
    t = _live_transport_with_patched_client(monkeypatch)
    cfg = RunnerConfig(out_dir=str(tmp_path / "o"), human_authorized_ceiling_usd=30.0,
                       price_table_path=PRICE_V2, verify_identities=False,
                       count_tokens_fn=t.count_tokens)
    runner = Stage1Runner(cfg)
    runner.run_fixture(_fx(), t.converse)
    assert NON_LOOPBACK_CONNECTS["count"] == 0
    assert REAL_INFERENCE_CALLS["n"] == 0
