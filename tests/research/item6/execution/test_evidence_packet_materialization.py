"""ITEM 6 Stage-1 evidence-packet materialization: PIT / leakage / representation / live-
binding / empty-packet-rejection tests (mission Parts 8-10, checks 1-36).

ZERO PAID INFERENCE. The execution conftest installs a network kill-switch, so no real
Bedrock/LLM call is possible; the runner and transport are exercised with deterministic local
stand-ins only. The materializer reads the frozen FootyStats corpus on disk (data files are
provider data, not network).
"""
from __future__ import annotations

import copy
import json
import os

import pytest

from src.research.item6.evidence import packet_materializer as PM
from src.research.item6.evidence.frozen_packet_provider import (
    FrozenPacketError, FrozenPacketProvider)
from src.research.item6.execution import request_builder as RB
from src.research.item6.execution import runner as RUN
from src.research.item6.execution.runner import RunnerConfig, RunnerRefused, Stage1Runner
from src.research.item6 import provider_vocab
from tests.research.item6.execution.conftest import make_count_fn, good_converse_response

# DATA_ROOT holds the frozen provider corpus (data files exist only under /home/ubuntu).
ROOT = os.environ.get("ITEM6_DATA_ROOT", "/home/ubuntu")
# CODE_ROOT holds the committed artifacts (materialized/packet sets, price table, prompt).
CODE_ROOT = os.environ.get("ITEM6_CODE_ROOT", "/home/ubuntu")
COHORT_PATH = f"{CODE_ROOT}/research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json"
PACKET_SET_PATH = f"{CODE_ROOT}/research/item6/out/execution/ITEM6_STAGE1_EVIDENCE_PACKET_SET_V1.json"
REQ_SET_PATH = f"{CODE_ROOT}/research/item6/out/execution/ITEM6_STAGE1_MATERIALIZED_REQUEST_SET_V1.json"
PRICE_TABLE_PATH = f"{CODE_ROOT}/research/item6/ITEM6_STAGE1_PRICE_TABLE_V2.json"


# --- session-scoped materialization of all packets (built once, reused) --------------------
@pytest.fixture(scope="module")
def cohort():
    return json.load(open(COHORT_PATH))["fixtures"]


@pytest.fixture(scope="module")
def corpus():
    return PM.load_corpus(ROOT)


@pytest.fixture(scope="module")
def packets(cohort, corpus):
    out = {}
    for fx in cohort:
        out[fx["fixture_id"]] = PM.materialize_item6_evidence_packet(
            fx, fx["kickoff_unix"], corpus=corpus, root=ROOT)
    return out


@pytest.fixture(scope="module")
def first_fixture(cohort):
    return cohort[0]


@pytest.fixture(scope="module")
def first_packet(packets, first_fixture):
    return packets[first_fixture["fixture_id"]]


# ============================ PART 8 - PIT / LEAKAGE (1-15) ================================
def test_01_every_fixture_packet_non_empty(packets):
    assert len(packets) == 120
    for p in packets.values():
        assert p["n_evidence_items"] > 0
        assert p["evidence"]


def test_02_every_packet_has_valid_evidence_ref(packets):
    for p in packets.values():
        assert len(p["evidence"]) >= 1
        for ref in p["evidence"]:
            assert ref.startswith("E:")


def test_03_every_packet_observable_vocabulary_non_empty(packets):
    for p in packets.values():
        assert p["observable_vocabulary"]


def test_04_every_evidence_ref_resolves_uniquely(packets):
    for p in packets.values():
        refs = list(p["evidence"].keys())
        assert len(refs) == len(set(refs)), "duplicate evidence_ref"
        assert len(refs) == len(p["evidence_order"])
        assert set(refs) == set(p["evidence_order"])
        for ref in refs:
            decoded = PM.resolve_evidence_ref(ref)  # raises if unresolvable
            assert decoded["metric"] in PM.METRIC_REGISTRY


def test_05_every_evidence_source_strictly_pre_target(packets, cohort):
    by_id = {fx["fixture_id"]: fx for fx in cohort}
    for fid, p in packets.items():
        cutoff = p["information_cutoff_unix"]
        for role in ("TEAM_A", "TEAM_B"):
            src = p["provenance"][role]
            assert src["max_source_kickoff_unix"] < cutoff


def test_06_changing_target_outcome_does_not_change_packet(first_fixture, corpus):
    p1 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus, root=ROOT)
    # mutate the TARGET match record's own outcome in a copy of the corpus.
    corpus2 = copy.deepcopy(corpus)
    tgt = str(first_fixture["source_fixture_id"])
    if tgt in corpus2.by_id:
        corpus2.by_id[tgt]["homeGoalCount"] = 99
        corpus2.by_id[tgt]["team_a_shots"] = 999
    p2 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus2, root=ROOT)
    assert p1["packet_sha256"] == p2["packet_sha256"]


def test_07_changing_post_target_statistics_does_not_change_packet(first_fixture, corpus):
    p1 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus, root=ROOT)
    corpus2 = copy.deepcopy(corpus)
    cutoff = first_fixture["kickoff_unix"]
    # mutate stats of a LATER match involving one of the teams (post-target).
    hid = str(first_fixture["home_id"])
    changed = 0
    for m in corpus2.by_team.get(hid, []):
        if int(m["date_unix"]) >= cutoff:
            m["team_a_shots"] = 777
            m["team_b_shots"] = 777
            changed += 1
    p2 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus2, root=ROOT)
    assert p1["packet_sha256"] == p2["packet_sha256"]


def test_08_changing_future_fixtures_does_not_change_packet(first_fixture, corpus):
    p1 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus, root=ROOT)
    corpus2 = copy.deepcopy(corpus)
    cutoff = first_fixture["kickoff_unix"]
    # inject a brand-new FUTURE fixture for the home team.
    hid = str(first_fixture["home_id"])
    future = {"id": "999999999", "status": "complete", "date_unix": cutoff + 10_000,
              "homeID": int(hid), "awayID": 123456, "competition_id": 16572,
              "homeGoalCount": 5, "awayGoalCount": 5, "team_a_shots": 40, "team_b_shots": 40,
              "team_a_corners": 20, "team_b_corners": 20}
    corpus2.by_id["999999999"] = future
    corpus2.by_team.setdefault(hid, []).append(future)
    corpus2.by_team[hid].sort(key=lambda x: (int(x["date_unix"]), int(x["id"])))
    p2 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus2, root=ROOT)
    assert p1["packet_sha256"] == p2["packet_sha256"]


def test_09_changing_closing_line_does_not_change_packet(first_fixture, corpus):
    p1 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus, root=ROOT)
    corpus2 = copy.deepcopy(corpus)
    # market/odds fields exist on FootyStats records but the materializer never reads them.
    for tid in (str(first_fixture["home_id"]), str(first_fixture["away_id"])):
        for m in corpus2.by_team.get(tid, []):
            m["odds_ft_1"] = 1.01
            m["odds_ft_x"] = 99.0
            m["odds_ft_2"] = 50.0
    p2 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus2, root=ROOT)
    assert p1["packet_sha256"] == p2["packet_sha256"]


def test_10_changing_future_lineup_injury_does_not_change_packet(first_fixture, corpus):
    p1 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus, root=ROOT)
    corpus2 = copy.deepcopy(corpus)
    tgt = str(first_fixture["source_fixture_id"])
    if tgt in corpus2.by_id:
        corpus2.by_id[tgt]["lineups"] = {"team_a": {"formation": "4-4-2"}}
        corpus2.by_id[tgt]["injuries"] = ["playerX"]
    p2 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus2, root=ROOT)
    assert p1["packet_sha256"] == p2["packet_sha256"]


def test_11_simultaneous_or_later_match_cannot_leak(first_fixture, corpus):
    p1 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus, root=ROOT)
    corpus2 = copy.deepcopy(corpus)
    cutoff = first_fixture["kickoff_unix"]
    # a match at EXACTLY the cutoff (simultaneous) must be excluded (strict <).
    hid = str(first_fixture["home_id"])
    sim = {"id": "888888888", "status": "complete", "date_unix": cutoff,
           "homeID": int(hid), "awayID": 222333, "competition_id": 16572,
           "homeGoalCount": 3, "awayGoalCount": 3, "team_a_shots": 33, "team_b_shots": 33}
    corpus2.by_id["888888888"] = sim
    corpus2.by_team.setdefault(hid, []).append(sim)
    corpus2.by_team[hid].sort(key=lambda x: (int(x["date_unix"]), int(x["id"])))
    p2 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus2, root=ROOT)
    assert p1["packet_sha256"] == p2["packet_sha256"]


def test_12_packet_cutoff_equals_frozen_target_kickoff(packets, cohort):
    by_id = {fx["fixture_id"]: fx for fx in cohort}
    for fid, p in packets.items():
        assert p["information_cutoff_unix"] == by_id[fid]["kickoff_unix"]


def test_13_provider_provenance_preserved(packets):
    for p in packets.values():
        assert p["provider"] == "footystats"
        assert p["provenance"]["provider"] == "footystats"
        assert p["provenance"]["TEAM_A"]["n_source_matches"] >= 1
        assert p["provenance"]["TEAM_B"]["n_source_matches"] >= 1


def test_14_forbidden_provider_semantic_field_rejected(first_packet):
    # provider-unsafe / future-leakage concepts must never appear as packet metrics.
    metrics = set(first_packet["observable_vocabulary"])
    for m in metrics:
        assert m in PM.METRIC_REGISTRY
        assert provider_vocab.is_supported_metric(m)
    # explicit unsafe concepts absent from the whole serialized packet keys.
    blob = json.dumps(first_packet)
    for concept in ("injury", "suspension", "expected lineup", "weather", "referee identity"):
        assert concept not in blob.lower()


def test_15_thestatsapi_npxg_and_xg_excluded(packets):
    for p in packets.values():
        assert "npxg" not in p["observable_vocabulary"]
        assert "np_expected_goals" not in p["observable_vocabulary"]
        assert "xg" not in p["observable_vocabulary"]
        blob = json.dumps(p).lower()
        assert "npxg" not in blob and "np_expected_goals" not in blob
        # 'xg' as a standalone metric token must not appear in evidence refs.
        assert not any(":xg:" in ref for ref in p["evidence"])


# ============================ PART 9 - REPRESENTATION (16-28) ==============================
def test_16_both_teams_represented(packets):
    for p in packets.values():
        roles = {PM.resolve_evidence_ref(r)["team_role"] for r in p["evidence"]}
        assert "TEAM_A" in roles and "TEAM_B" in roles


def test_17_attack_and_defense_perspectives_represented(packets):
    for p in packets.values():
        persp = {PM.resolve_evidence_ref(r)["perspective"] for r in p["evidence"]}
        assert "FOR" in persp and "AGAINST" in persp


def test_18_multiple_metric_families_represented(packets):
    for p in packets.values():
        assert len(set(p["observable_vocabulary"])) >= 4


def test_19_sample_n_present(packets):
    for p in packets.values():
        for ref, tup in p["evidence"].items():
            assert isinstance(tup[1], int) and tup[1] >= 1


def test_20_reliability_present(packets):
    for p in packets.values():
        for ref, tup in p["evidence"].items():
            assert tup[2] in (0, 1, 2)


def test_21_metric_ordering_deterministic(first_fixture, corpus):
    p1 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus, root=ROOT)
    # ordering is value-independent canonical; re-materialize and compare order.
    p2 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus, root=ROOT)
    assert p1["evidence_order"] == p2["evidence_order"]
    # order must be sorted by the canonical key (not by value).
    def key(ref):
        d = PM.resolve_evidence_ref(ref)
        return (PM._TEAM_ROLE_ORDER[d["team_role"]], PM._METRIC_ORDER[d["metric"]],
                PM._PERSPECTIVE_ORDER[d["perspective"]], PM._PERIOD_ORDER[d["period"]],
                PM._VENUE_ORDER[d["venue_scope"]], PM._WINDOW_ORDER[d["window"]])
    assert p1["evidence_order"] == sorted(p1["evidence_order"], key=key)


def test_22_packet_reconstruction_byte_identical(first_fixture, corpus):
    p1 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus, root=ROOT)
    p2 = PM.materialize_item6_evidence_packet(first_fixture, first_fixture["kickoff_unix"],
                                              corpus=corpus, root=ROOT)
    b1 = json.dumps(p1, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    b2 = json.dumps(p2, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert b1 == b2
    assert p1["packet_sha256"] == p2["packet_sha256"]


def test_23_packet_set_reconstruction_byte_identical(cohort, corpus):
    def build_set():
        return {fx["fixture_id"]: PM.materialize_item6_evidence_packet(
            fx, fx["kickoff_unix"], corpus=corpus, root=ROOT)["packet_sha256"]
            for fx in cohort}
    assert build_set() == build_set()


def _structured_tokens(p):
    """All structured (non-legend-prose) string tokens: evidence refs, vocabulary, metric
    registry, ordering rule, provenance keys/values, fixture ids. Excludes the human-readable
    `legend` note text (which legitimately contains disclaimer words like 'never a probability
    ... odds ... prediction')."""
    toks = []
    toks += list(p["evidence"].keys())
    toks += list(p["evidence_order"])
    toks += list(p["observable_vocabulary"])
    toks += list(p["metric_registry_order"])
    toks.append(p["ordering_rule"])
    toks.append(str(p["provider"]))
    toks.append(str(p.get("fixture_id")))
    return " ".join(toks).lower()


def test_24_no_candidate_ids(packets):
    for p in packets.values():
        blob = _structured_tokens(p)
        assert "candidate_id" not in blob
        assert "candidate" not in blob
        assert p["contains_no_candidate_ids"] is True
        # no evidence field named like a candidate id anywhere in the data map.
        assert all("candidate" not in k.lower() for k in p["evidence"])


def test_25_no_salience_or_rank(packets):
    # No per-evidence salience/rank/importance value. (The ordering_rule label
    # ANTI_SALIENCE_NEUTRAL_CANONICAL is the anti-salience policy name, not a salience score.)
    for p in packets.values():
        assert p["contains_no_salience_or_rank"] is True
        for r in p["evidence"]:
            rl = r.lower()
            for tok in ("salience", "rank", "importance", "priority"):
                assert tok not in rl
        for tup in p["evidence"].values():
            assert len(tup) == 3


def test_26_no_oos_outcome(packets):
    for p in packets.values():
        blob = _structured_tokens(p)
        for tok in ("oos", "out_of_sample", "settled", "settlement", "profit"):
            assert tok not in blob


def test_27_no_market_information(packets):
    # market data must not appear in the structured evidence content. The legend's disclaimer
    # ("...never ... odds ...") is instruction text, not data, and is excluded.
    for p in packets.values():
        blob = _structured_tokens(p)
        for tok in ("odds", "market", "closing_line", "stake", "edge", "price"):
            assert tok not in blob
        # no evidence ref or vocabulary entry references a market concept.
        assert all(":odds" not in r and ":price" not in r for r in p["evidence"])


def test_28_no_p_model(packets):
    for p in packets.values():
        blob = _structured_tokens(p)
        for tok in ("p_model", "probability", "effect_size", "p_value", "predicted"):
            assert tok not in blob
        # evidence values are plain numeric means/counts only (no nested prediction fields).
        for tup in p["evidence"].values():
            assert isinstance(tup, list) and len(tup) == 3
            assert isinstance(tup[0], (int, float))  # value
            assert isinstance(tup[1], int)            # sample_n
            assert tup[2] in (0, 1, 2)                # reliability_code


# ============================ PART 10 - LIVE REQUEST (29-36) ===============================
def _standin_runner(tmp_path, count_tokens=None):
    cfg = RunnerConfig(
        out_dir=str(tmp_path),
        human_authorized_ceiling_usd=30.0,
        price_table_path=PRICE_TABLE_PATH,
        root=ROOT,
        verify_identities=True,
        count_tokens_fn=count_tokens or make_count_fn(6500),
    )
    return Stage1Runner(cfg)


def test_29_live_mode_with_empty_packet_fails_before_count(tmp_path, first_fixture):
    runner = _standin_runner(tmp_path)
    # simulate LIVE mode by binding a truthy transport marker.
    runner._item6_live_transport = object()
    count_calls = {"n": 0}
    def counting(modelId, input):  # noqa: A002
        count_calls["n"] += 1
        return {"inputTokens": 6500}
    runner.cfg.count_tokens_fn = counting
    with pytest.raises(RunnerRefused):
        runner.run_fixture(first_fixture, lambda req: good_converse_response(),
                           fixture_packet={})
    assert count_calls["n"] == 0, "CountTokens must not be called with an empty packet"


def test_30_live_mode_with_wrong_packet_hash_fails(first_fixture, corpus):
    req = json.load(open(REQ_SET_PATH))
    pkt = json.load(open(PACKET_SET_PATH))
    provider = FrozenPacketProvider(req, pkt, corpus=corpus, data_root=ROOT)
    # corrupt the frozen bound hash for this fixture -> get_verified_packet must fail closed.
    fid = first_fixture["fixture_id"]
    provider._req_by_fixture[fid]["packet_sha256"] = "deadbeef" * 8
    with pytest.raises(FrozenPacketError):
        provider.get_verified_packet(first_fixture)


def test_31_materialized_request_hash_matches_frozen(cohort, corpus):
    req = json.load(open(REQ_SET_PATH))
    system_text = RB.load_frozen_system_text(ROOT)
    by_id = {fx["fixture_id"]: fx for fx in cohort}
    for e in req["entries"]:
        fx = by_id[e["fixture_id"]]
        packet = PM.materialize_item6_evidence_packet(fx, fx["kickoff_unix"],
                                                      corpus=corpus, root=ROOT)
        r = RB.canonical_request(fx, system_text, evidence_packet=packet)
        assert RB.request_sha256(r) == e["canonical_request_sha256"]
        assert packet["packet_sha256"] == e["packet_sha256"]


def test_32_count_tokens_receives_materialized_request(tmp_path, first_fixture, first_packet):
    runner = _standin_runner(tmp_path)
    seen = {}
    def counting(modelId, input):  # noqa: A002
        seen["input"] = input
        return {"inputTokens": 6500}
    runner.cfg.count_tokens_fn = counting
    runner.run_fixture(first_fixture, lambda req: good_converse_response(),
                       fixture_packet=first_packet)
    # the counted converse content must carry the materialized (non-empty) evidence packet.
    counted_user = json.dumps(seen["input"])
    assert "evidence" in counted_user and "E:TEAM_A:" in counted_user


def test_33_converse_receives_counted_request(tmp_path, first_fixture, first_packet):
    runner = _standin_runner(tmp_path)
    seen = {}
    def transport(req):
        seen["req"] = req
        return good_converse_response(6500, 1500)
    runner.run_fixture(first_fixture, transport, fixture_packet=first_packet)
    sent_user = json.dumps(seen["req"]["messages"])
    assert "E:TEAM_A:" in sent_user  # the materialized packet was transmitted


def test_34_request_mutation_after_count_blocked():
    # token_counter re-derives the fingerprint after counting; a mismatch blocks.
    from src.research.item6.execution import token_counter as TC
    fx = {"fixture_id": "i6_x", "home_id": "1", "away_id": "2", "competition": "comp_1",
          "kickoff_unix": 1, "source_fixture_id": "x"}
    system_text = "sys"
    packet = {"evidence": {"E:TEAM_A:shots:FOR:FULL_MATCH:ALL:ALL_PRIOR": [1.0, 5, 1]},
              "n_evidence_items": 1}
    req = RB.canonical_request(fx, system_text, evidence_packet=packet)
    fp1 = TC.count_input_fingerprint(req)
    # mutate the request after counting.
    req["messages"][0]["content"][0]["text"] += "X"
    fp2 = TC.count_input_fingerprint(req)
    assert fp1["inference_request_sha256"] != fp2["inference_request_sha256"]


def test_35_standin_cannot_substitute_packet_after_freeze(first_fixture, corpus):
    req = json.load(open(REQ_SET_PATH))
    pkt = json.load(open(PACKET_SET_PATH))
    provider = FrozenPacketProvider(req, pkt, corpus=corpus, data_root=ROOT)
    # tamper the frozen packet BODY -> body hash no longer matches bound sha -> fail closed.
    fid = first_fixture["fixture_id"]
    provider._packet_by_fixture[fid]["packet"]["evidence"][
        "E:TEAM_A:shots:FOR:FULL_MATCH:ALL:ALL_PRIOR"] = [123456.0, 1, 0]
    with pytest.raises(FrozenPacketError):
        provider.get_verified_packet(first_fixture)


def test_36_byte_ceiling_enforced_on_materialized_request(cohort, corpus):
    system_text = RB.load_frozen_system_text(ROOT)
    for fx in cohort:
        packet = PM.materialize_item6_evidence_packet(fx, fx["kickoff_unix"],
                                                      corpus=corpus, root=ROOT)
        r = RB.canonical_request(fx, system_text, evidence_packet=packet)
        assert RB.within_byte_budget(r)
        assert RB.request_byte_len(r) <= RB.MAX_REQUEST_UTF8_BYTES


# --- empty-packet rejection at the frozen-provider level (defence in depth) ----------------
def test_frozen_provider_rejects_empty_packet(first_fixture, corpus):
    req = json.load(open(REQ_SET_PATH))
    pkt = json.load(open(PACKET_SET_PATH))
    provider = FrozenPacketProvider(req, pkt, corpus=corpus, data_root=ROOT)
    fid = first_fixture["fixture_id"]
    provider._packet_by_fixture[fid]["packet"]["evidence"] = {}
    provider._packet_by_fixture[fid]["packet"]["n_evidence_items"] = 0
    with pytest.raises(FrozenPacketError):
        provider.get_verified_packet(first_fixture)


def test_frozen_provider_happy_path_matches_frozen(first_fixture, corpus):
    req = json.load(open(REQ_SET_PATH))
    pkt = json.load(open(PACKET_SET_PATH))
    provider = FrozenPacketProvider(req, pkt, corpus=corpus, data_root=ROOT)
    p = provider.get_verified_packet(first_fixture)
    assert p["n_evidence_items"] > 0
    assert p["packet_sha256"] == provider.frozen_packet_sha256(first_fixture["fixture_id"])
