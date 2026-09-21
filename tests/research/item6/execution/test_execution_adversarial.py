"""22 mandatory adversarial tests for the Item 6 Stage-1 execution/spend bindings (B1-B5).

All run under the non-loopback network kill-switch (conftest). The runner is exercised with
deterministic local stand-ins only; zero real Bedrock calls are possible. Tests assert the
frozen one-attempt / no-retry / call-cap / monetary-reservation / fail-closed semantics.
"""
from __future__ import annotations

import json
import os

import pytest

from src.research.item6.execution import execution_status as ES
from src.research.item6.execution import request_builder as RB
from src.research.item6.execution import runner as RUN
from src.research.item6.execution.runner import (RunnerConfig, RunnerFailClosed,
                                                 Stage1Runner, verify_frozen_identities)
from src.research.item6.execution.spend_guard import PriceTable, SpendGuard
from tests.research.item6.execution.conftest import (NON_LOOPBACK_CONNECTS,
                                                     good_converse_response, good_count_fn,
                                                     make_count_fn)

PRICE = "/home/ubuntu/research/item6/ITEM6_STAGE1_PRICE_TABLE_V1.json"


def _runner(tmp_path, ceiling=100.0, verify=False, count_fn=good_count_fn) -> Stage1Runner:
    cfg = RunnerConfig(out_dir=str(tmp_path / "exec_out"),
                       human_authorized_ceiling_usd=ceiling,
                       price_table_path=PRICE, verify_identities=verify,
                       count_tokens_fn=count_fn)
    return Stage1Runner(cfg)


def _fx(i="i6_test_0001"):
    return {"fixture_id": i, "home_id": "406", "away_id": "425",
            "competition": "comp_16572", "kickoff_unix": 1781352000}


# 1. one valid response -> a second invocation does NOT call again (idempotent resume).
def test_01_second_invocation_does_not_recall(tmp_path):
    r = _runner(tmp_path)
    calls = {"n": 0}

    def conv(req):
        calls["n"] += 1
        return good_converse_response()

    res1 = r.run_fixture(_fx(), conv)
    assert res1.status == ES.TRANSPORT_OK and calls["n"] == 1
    res2 = r.run_fixture(_fx(), conv)
    assert res2.status == ES.TRANSPORT_OK and calls["n"] == 1  # NOT re-called
    assert res2.detail == "resumed"


# 2. attempt marker exists, no receipt -> UNCERTAIN_ATTEMPT_NOT_RETRIED.
def test_02_marker_without_receipt_uncertain(tmp_path):
    r = _runner(tmp_path)
    # simulate: reserve + marker written, process died before receipt (no transport).
    res = r.run_fixture(_fx(), converse_fn=None)
    assert res.status == ES.UNCERTAIN_ATTEMPT_NOT_RETRIED
    # a resume must not retry it.
    res2 = r.run_fixture(_fx(), converse_fn=lambda q: good_converse_response())
    assert res2.status == ES.UNCERTAIN_ATTEMPT_NOT_RETRIED


# 3. transport failure -> no retry.
def test_03_transport_failure_no_retry(tmp_path):
    r = _runner(tmp_path)

    def conv(req):
        raise ConnectionError("boom")

    res = r.run_fixture(_fx(), conv)
    assert res.status == ES.MODEL_TRANSPORT_FAILURE
    assert not ES.is_retryable(res.status)
    # resume: not retried (attempt consumed).
    res2 = r.run_fixture(_fx(), lambda q: good_converse_response())
    assert res2.status == ES.UNCERTAIN_ATTEMPT_NOT_RETRIED


# 4. timeout -> no retry.
def test_04_timeout_no_retry(tmp_path):
    r = _runner(tmp_path)

    def conv(req):
        raise TimeoutError("slow")

    res = r.run_fixture(_fx(), conv)
    assert res.status == ES.MODEL_TIMEOUT
    assert not ES.is_retryable(res.status)


# 5. provider error -> no retry.
def test_05_provider_error_no_retry(tmp_path):
    r = _runner(tmp_path)

    def conv(req):
        raise ValueError("ThrottlingException")

    res = r.run_fixture(_fx(), conv)
    assert res.status == ES.MODEL_PROVIDER_ERROR
    assert not ES.is_retryable(res.status)


# 6. malformed received response (valid envelope, bad schema payload) -> treatment recorded,
#    no retry. A trustworthy envelope means the fixture received its treatment.
def test_06_malformed_payload_is_treatment_no_retry(tmp_path):
    r = _runner(tmp_path)
    resp = good_converse_response()
    # malformed *scientific* payload but a valid provider envelope + usage.
    resp["output"]["message"]["content"] = [{"text": "not the tool json at all"}]
    res = r.run_fixture(_fx(), lambda q: resp)
    assert res.status == ES.TRANSPORT_OK          # received == treatment
    assert res.receipt_present
    res2 = r.run_fixture(_fx(), lambda q: good_converse_response())
    assert res2.detail == "resumed"               # not re-called


# 7. fewer than K mechanisms -> no retry (scientific observation).
def test_07_fewer_than_k_no_retry(tmp_path):
    r = _runner(tmp_path)
    resp = good_converse_response()
    resp["output"]["message"]["content"] = [{"toolUse": {"name": "emit_item6_mechanisms",
        "input": {"fixture_id": "i6_test_0001", "mechanisms": [{"mechanism_id_local": "m1"}]}}}]
    res = r.run_fixture(_fx(), lambda q: resp)
    assert res.status == ES.TRANSPORT_OK
    assert ES.consumed_paid_attempt(res.status)


# 8. valid abstention -> no retry.
def test_08_abstention_no_retry(tmp_path):
    from src.research.item6.schema import ABSTENTION_TOKEN
    r = _runner(tmp_path)
    resp = good_converse_response()
    resp["output"]["message"]["content"] = [{"toolUse": {"name": "emit_item6_mechanisms",
        "input": {"fixture_id": "i6_test_0001",
                  "abstention": ABSTENTION_TOKEN,
                  "mechanisms": []}}}]
    res = r.run_fixture(_fx(), lambda q: resp)
    assert res.status == ES.TRANSPORT_OK
    assert ES.ABSTENTION_IS_VALID_TREATMENT and not ES.ABSTENTION_TRIGGERS_RETRY


# 9. duplicate mechanisms in response -> no retry.
def test_09_duplicates_no_retry(tmp_path):
    r = _runner(tmp_path)
    dup = {"mechanism_id_local": "m1"}
    resp = good_converse_response()
    resp["output"]["message"]["content"] = [{"toolUse": {"name": "emit_item6_mechanisms",
        "input": {"fixture_id": "i6_test_0001", "mechanisms": [dup, dup, dup, dup, dup]}}}]
    res = r.run_fixture(_fx(), lambda q: resp)
    assert res.status == ES.TRANSPORT_OK


# 10. call #121 attempted -> blocked before transport.
def test_10_call_121_blocked_before_transport(tmp_path):
    r = _runner(tmp_path, ceiling=1000.0)
    calls = {"n": 0}

    def conv(req):
        calls["n"] += 1
        return good_converse_response(input_tokens=10, output_tokens=10)

    for i in range(ES.ABSOLUTE_MAX_PAID_CALLS):
        assert r.run_fixture(_fx(f"i6_f{i:04d}"), conv).status == ES.TRANSPORT_OK
    assert calls["n"] == 120
    res = r.run_fixture(_fx("i6_f0120"), conv)
    assert res.status == ES.CALL_BLOCKED_BY_CALL_CAP
    assert calls["n"] == 120  # 121st never transmitted


# 11. next call reservation would exceed monetary ceiling -> blocked before transport.
def test_11_spend_cap_blocks_before_transport(tmp_path):
    # ceiling below one call's max reservation ($0.221184) -> first call blocked.
    r = _runner(tmp_path, ceiling=0.10)
    calls = {"n": 0}

    def conv(req):
        calls["n"] += 1
        return good_converse_response()

    res = r.run_fixture(_fx(), conv)
    assert res.status == ES.CALL_BLOCKED_BY_SPEND_CAP
    assert calls["n"] == 0  # never transmitted


# 12. actual request larger than expected -> reservation increases automatically (byte bound).
def test_12_reservation_tracks_request_size():
    price = PriceTable.from_json(PRICE)
    small = price.call_reservation_usd(1000, RB.MAX_TOKENS)
    big = price.call_reservation_usd(RB.MAX_REQUEST_UTF8_BYTES, RB.MAX_TOKENS)
    assert big > small
    # runner reserves against the frozen ceiling bound (the max), so bigger requests cannot
    # under-reserve.
    req = RB.canonical_request(_fx(), RB.load_frozen_system_text())
    assert RB.reservation_input_token_bound(req) == RB.MAX_REQUEST_UTF8_BYTES


# 13. v2: the reservation uses the AUTHORITATIVE provider count, which matches what is
#     billed. When the provider count reflects the true input, realized <= reserved holds.
def test_13_provider_count_reservation_dominates_realized(tmp_path):
    r = _runner(tmp_path, ceiling=100.0, count_fn=make_count_fn(20000))
    # provider counts 20000 input tokens => reservation covers 20000 in + 8192 out. Realized
    # input equals the counted 20000 and realized output (8000) <= the 8192 reserve.
    res = r.run_fixture(_fx(), lambda q: good_converse_response(input_tokens=20000,
                                                               output_tokens=8000))
    assert res.status == ES.TRANSPORT_OK
    assert res.provider_counted_input_tokens == 20000
    assert r.guard.realized_usd <= r.guard.reserved_usd  # reservation dominated realized
    assert r.integrity_ok()


# 14. attempt ledger / reception counter inconsistent -> fail closed.
def test_14_ledger_inconsistency_fails_closed(tmp_path):
    r = _runner(tmp_path)
    r.run_fixture(_fx(), lambda q: good_converse_response())
    # forge an extra receipt with no corresponding charge.
    with open(f"{r.receipts_dir}/i6_bogus.json", "w") as f:
        json.dump({"fixture_id": "i6_bogus"}, f)
    assert not r.integrity_ok()
    with pytest.raises(RunnerFailClosed):
        r.assert_integrity()


# 15. unknown execution status -> fail closed.
def test_15_unknown_status_fails_closed():
    assert ES.normalize("SOMETHING_WEIRD") == ES.UNKNOWN_EXECUTION_STATUS
    assert ES.fail_closed(ES.UNKNOWN_EXECUTION_STATUS)
    assert ES.fail_closed(ES.REQUEST_INTEGRITY_FAILURE)


# 16. Pass B invocation through the primary runner -> blocked (no such capability exists).
def test_16_pass_b_not_reachable_through_runner():
    # The runner exposes no Pass B / semantic-rater entry point at all.
    assert not hasattr(Stage1Runner, "run_pass_b")
    assert not hasattr(Stage1Runner, "semantic_rate")
    pol = json.load(open("/home/ubuntu/research/item6/ITEM6_STAGE1_PASS_B_POLICY_V1.json"))
    assert pol["pass_b_included_in_stage1_generation_budget"] is False
    assert pol["pass_b_requires_separate_human_spend_authorization"] is True


# 17. Pass B absence -> primary Stage-1 gate remains computable.
def test_17_primary_gate_computable_without_pass_b():
    import importlib
    gate = importlib.import_module("src.research.item6.stage1_gate")
    metrics = importlib.import_module("src.research.item6.stage1_metrics")
    src_gate = open("/home/ubuntu/src/research/item6/stage1_gate.py").read()
    src_metrics = open("/home/ubuntu/src/research/item6/stage1_metrics.py").read()
    assert "quality_protocol" not in src_gate
    assert "quality_protocol" not in src_metrics
    # evaluate_gate consumes only Stage1Endpoints (deterministic), proving no Pass B needed.
    ep = metrics.Stage1Endpoints(
        n_fixtures=120, n_fixtures_abstained=10, n_mechanisms_total=550,
        baseline_equivalent_rate=0.2, semantic_duplicate_rate=0.1,
        novel_measurable_family_rate=0.9, novel_measurable_family_rate_mech=0.8,
        multivariable_interaction_rate=0.5, new_family_count=40,
        grounding_pass_rate=1.0, falsifiability_pass_rate=1.0,
        formalization_survival_rate=1.0, abstention_rate=0.08,
        f_class_counts={}, extension_family_ids=[])
    assert gate.evaluate_gate(ep).passed is True


# 18. scientific artifact hash changed -> runner refuses execution.
def test_18_scientific_drift_refused(tmp_path, monkeypatch):
    bad = dict(RUN.SCIENTIFIC_HASHES)
    # corrupt one expected hash so the on-disk file no longer matches.
    k = next(iter(bad))
    bad[k] = "0" * 64
    monkeypatch.setattr(RUN, "SCIENTIFIC_HASHES", bad)
    with pytest.raises(RUN.RunnerRefused):
        verify_frozen_identities()


# 19. cohort hash changed -> runner refuses execution.
def test_19_cohort_drift_refused(monkeypatch):
    monkeypatch.setattr(RUN, "COHORT_SHA256", "0" * 64)
    with pytest.raises(RUN.RunnerRefused):
        verify_frozen_identities()


# 20. CHAMPION hash changed -> runner refuses execution.
def test_20_champion_drift_refused(monkeypatch):
    monkeypatch.setattr(RUN, "CHAMPION_SHA256", "0" * 64)
    with pytest.raises(RUN.RunnerRefused):
        verify_frozen_identities()


# 21. request-set regeneration -> byte-identical hashes.
def test_21_request_set_regeneration_byte_identical():
    import hashlib
    p = "/home/ubuntu/research/item6/out/execution/ITEM6_STAGE1_REQUEST_SET_V1.json"
    before = hashlib.sha256(open(p, "rb").read()).hexdigest()
    import runpy
    runpy.run_path("/home/ubuntu/research/item6/_build_stage1_request_set.py",
                   run_name="__main__")
    after = hashlib.sha256(open(p, "rb").read()).hexdigest()
    assert before == after


# 22. network kill-switch -> zero non-loopback connects.
def test_22_zero_non_loopback_connects(tmp_path):
    r = _runner(tmp_path)
    r.run_fixture(_fx(), lambda q: good_converse_response())
    assert NON_LOOPBACK_CONNECTS["count"] == 0
