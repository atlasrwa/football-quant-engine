"""Tests for the append-only prospective-shadow FINAL settlement layer.

Covers: parent integrity, reconstructed rejection, final-state gate, result
provenance fail-closed, goals/corners/cards grading (WIN/LOSS/PUSH/VOID),
idempotency, parent immutability, movement-vs-settlement separation, Telegram
render + safety, and consumer isolation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.research.prospective import shadow_feed
from src.research.prospective import shadow_settle_process as ssp
from src.research.prospective.research_notify import MessageType
from src.research.prospective.shadow_settlement import (
    FixtureResult,
    MARKET_RESULT_STATISTIC,
    SettlementOutcome,
    SettlementRefusal,
    SettlementRefusalError,
    build_settlement,
    check_parent_eligible,
    grade_over_under,
)
from src.research.prospective.shadow_settlement_store import (
    ShadowSettlementStore,
    default_settlement_store,
)
from src.research.prospective.shadow_store import (
    SHADOW_CANDIDATES_FILE,
    default_candidate_store,
)

VALID_HASH = "commit_hash_abc"


def _shadow(**over) -> dict:
    rec = {
        "record_type": "SHADOW_RESIDUAL",
        "provenance_kind": "PROSPECTIVE_SHADOW",
        "classification": ["RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE"],
        "fixture_id": "F1",
        "competition": "comp_9788",
        "kickoff_ts": 1000.0,
        "information_cutoff": 400.0,
        "provider": "thestatsapi",
        "bookmaker": "pinnacle",
        "market": "total_goals",
        "selection": "over",
        "line": 2.5,
        "p_model": 0.57,
        "p_market_devig": 0.51,
        "raw_probability_residual": 0.06,
        "forecast_commitment_hash": VALID_HASH,
        "model_version": "mv1",
        "shadow_id": "sid_0000000000000000000000000001",
        "shadow_payload_hash": "ph_0001",
    }
    rec.update(over)
    return rec


def _result(**over) -> FixtureResult:
    base = dict(
        fixture_id="F1",
        status="finished",
        statistics={"total_goals": 3.0, "total_corners": 10.0, "total_cards": 4.0},
        observed_at=2000.0,
        source="test",
    )
    base.update(over)
    return FixtureResult(**base)


# ── grading: goals / corners / cards WIN/LOSS/PUSH/VOID ─────────────────────
@pytest.mark.parametrize(
    "selection,line,actual,expected",
    [
        ("over", 2.5, 3, SettlementOutcome.WIN),
        ("under", 2.5, 3, SettlementOutcome.LOSS),
        ("over", 2.5, 2, SettlementOutcome.LOSS),
        ("under", 2.5, 2, SettlementOutcome.WIN),
        ("over", 3.0, 3, SettlementOutcome.PUSH),   # integer line, exact tie
        ("under", 3.0, 3, SettlementOutcome.PUSH),
        ("over", None, 3, SettlementOutcome.VOID),  # no line
        ("weird", 2.5, 3, SettlementOutcome.VOID),  # unknown selection
    ],
)
def test_grade_over_under(selection, line, actual, expected):
    assert grade_over_under(selection, line, actual) is expected


def test_goals_grading_end_to_end_win():
    rec = build_settlement(_shadow(), _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0)
    assert rec.settlement_outcome == "WIN"
    assert rec.result_statistic_key == "total_goals"
    assert rec.result_statistic_value == 3.0


def test_corners_grading_push_on_integer_line():
    sh = _shadow(market="match_corners", selection="over", line=10.0)
    rec = build_settlement(sh, _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0)
    assert rec.result_statistic_key == "total_corners"
    assert rec.settlement_outcome == "PUSH"  # 10 corners on line 10.0


def test_cards_grading_uses_total_cards_concept():
    sh = _shadow(market="total_cards", selection="under", line=4.5)
    rec = build_settlement(sh, _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0)
    assert rec.result_statistic_key == "total_cards"
    assert rec.settlement_outcome == "WIN"  # 4 cards < 4.5


def test_market_result_binding_is_exactly_the_three_supported_markets():
    assert set(MARKET_RESULT_STATISTIC) == {"total_goals", "match_corners", "total_cards"}


# ── parent integrity ────────────────────────────────────────────────────────
def test_requires_genuine_prospective_parent_commitment_link():
    with pytest.raises(SettlementRefusalError) as e:
        build_settlement(_shadow(forecast_commitment_hash="unknown"), _result(),
                         valid_commitment_hashes=frozenset({VALID_HASH}))
    assert e.value.reason is SettlementRefusal.COMMITMENT_LINK_UNVERIFIED


def test_reconstructed_parent_is_rejected():
    with pytest.raises(SettlementRefusalError) as e:
        build_settlement(_shadow(provenance_kind="RECONSTRUCTED_SHADOW"), _result(),
                         valid_commitment_hashes=frozenset({VALID_HASH}))
    assert e.value.reason is SettlementRefusal.PARENT_NOT_PROSPECTIVE


def test_non_shadow_record_type_rejected():
    with pytest.raises(SettlementRefusalError) as e:
        build_settlement(_shadow(record_type="SOMETHING_ELSE"), _result(),
                         valid_commitment_hashes=frozenset({VALID_HASH}))
    assert e.value.reason is SettlementRefusal.PARENT_NOT_SHADOW_RESIDUAL


def test_unsupported_market_fails_closed():
    with pytest.raises(SettlementRefusalError) as e:
        build_settlement(_shadow(market="match_shots_on_target"), _result(),
                         valid_commitment_hashes=frozenset({VALID_HASH}))
    assert e.value.reason is SettlementRefusal.UNSUPPORTED_MARKET


# ── final-state gate + result provenance ────────────────────────────────────
def test_unfinished_fixture_cannot_settle():
    with pytest.raises(SettlementRefusalError) as e:
        build_settlement(_shadow(), _result(status="in_progress"),
                         valid_commitment_hashes=frozenset({VALID_HASH}))
    assert e.value.reason is SettlementRefusal.FIXTURE_NOT_FINAL


def test_missing_result_statistic_fails_closed_not_zero():
    # cards market but no cards statistic reported (NULL != ZERO)
    sh = _shadow(market="total_cards", line=4.5)
    res = _result(statistics={"total_goals": 3.0})  # no total_cards key
    with pytest.raises(SettlementRefusalError) as e:
        build_settlement(sh, res, valid_commitment_hashes=frozenset({VALID_HASH}))
    assert e.value.reason is SettlementRefusal.RESULT_STATISTIC_MISSING


def test_result_fixture_mismatch_fails_closed():
    with pytest.raises(SettlementRefusalError) as e:
        build_settlement(_shadow(fixture_id="F1"), _result(fixture_id="F2"),
                         valid_commitment_hashes=frozenset({VALID_HASH}))
    assert e.value.reason is SettlementRefusal.INVALID_FIXTURE_IDENTITY


# ── idempotency + parent immutability ───────────────────────────────────────
def test_settlement_id_is_deterministic_idempotent():
    r1 = build_settlement(_shadow(), _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                          created_at=1.0)
    r2 = build_settlement(_shadow(), _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                          created_at=999.0)  # different wall clock
    assert r1.settlement_id == r2.settlement_id  # created_at excluded from identity


def test_store_dedup_same_result_run_twice(tmp_path):
    store = ShadowSettlementStore(path=tmp_path / "shadow_settlements.jsonl")
    rec = build_settlement(_shadow(), _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0)
    assert store.append(rec) is True
    assert store.append(rec) is False  # idempotent
    assert store.count() == 1


def test_settlement_does_not_mutate_parent_shadow():
    sh = _shadow()
    frozen = json.dumps(sh, sort_keys=True)
    build_settlement(sh, _result(), valid_commitment_hashes=frozenset({VALID_HASH}))
    assert json.dumps(sh, sort_keys=True) == frozen  # unchanged


# ── movement vs settlement separation ───────────────────────────────────────
def test_settlement_carries_no_movement_direction_field():
    rec = build_settlement(_shadow(), _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0).to_dict()
    assert "movement_direction" not in rec        # separate axis
    assert rec["settlement_outcome"] in {"WIN", "LOSS", "PUSH", "VOID"}


# ── process: idempotency, pending kickoff, resolver fail-closed ──────────────
def _seed_shadow_ledger(root: Path, shadows: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with open(root / SHADOW_CANDIDATES_FILE, "w", encoding="utf-8") as fh:
        for s in shadows:
            fh.write(json.dumps(s) + "\n")


def test_process_settles_finished_and_skips_pending(tmp_path):
    _seed_shadow_ledger(tmp_path, [
        _shadow(shadow_id="sid_finished", fixture_id="F1", kickoff_ts=500.0),
        _shadow(shadow_id="sid_pending", fixture_id="F2", kickoff_ts=5000.0),
    ])
    def resolver(fid, ko):
        return _result(fixture_id=fid) if fid == "F1" else None
    res = ssp.run(result_resolver=resolver, shadow_root=tmp_path,
                  broadcast_root=tmp_path / "no_consumer",
                  research_broadcast_root=None, now=1000.0, created_at=1.0)
    # No commitment ledgers present -> valid_hashes empty -> linkage unverified.
    # This proves the linkage gate fails closed when no ledger backs the hash.
    assert res.settlements_new == 0
    assert res.fixtures_pending_kickoff == 1
    assert res.refusals.get("COMMITMENT_LINK_UNVERIFIED", 0) == 1


def test_process_idempotent_second_run_no_new(tmp_path, monkeypatch):
    _seed_shadow_ledger(tmp_path, [_shadow(shadow_id="sid_finished", fixture_id="F1",
                                           kickoff_ts=500.0)])
    # Bypass commitment-ledger linkage by pointing the process at an empty set is
    # not enough; instead settle directly through the store to prove dedup.
    store = default_settlement_store(root=tmp_path)
    rec = build_settlement(_shadow(shadow_id="sid_finished", fixture_id="F1", kickoff_ts=500.0),
                           _result(fixture_id="F1"),
                           valid_commitment_hashes=frozenset({VALID_HASH}), created_at=1.0)
    assert store.append(rec) is True
    assert "sid_finished" in store.settled_shadow_ids()
    # A process run now sees it already settled.
    def resolver(fid, ko):
        return _result(fixture_id=fid)
    res = ssp.run(result_resolver=resolver, shadow_root=tmp_path,
                  broadcast_root=tmp_path / "x", research_broadcast_root=None,
                  now=1000.0, created_at=2.0)
    assert res.shadows_already_settled == 1
    assert res.settlements_new == 0


def test_process_one_bad_fixture_does_not_stop_others(tmp_path):
    _seed_shadow_ledger(tmp_path, [
        _shadow(shadow_id="sid_ok", fixture_id="F1", kickoff_ts=500.0),
        _shadow(shadow_id="sid_bad", fixture_id="F2", kickoff_ts=500.0),
    ])
    def resolver(fid, ko):
        if fid == "F2":
            raise RuntimeError("provider blew up")
        return _result(fixture_id=fid)
    # Provide the commitment hash via monkeypatched valid set by writing a ledger:
    (tmp_path / "cl").mkdir(parents=True, exist_ok=True)
    with open(tmp_path / "cl" / "broadcasts.jsonl", "w") as fh:
        fh.write(json.dumps({"record_type": "FORECAST_COMMITTED",
                             "commitment_hash": VALID_HASH}) + "\n")
    res = ssp.run(result_resolver=resolver, shadow_root=tmp_path,
                  broadcast_root=tmp_path / "cl", research_broadcast_root=None,
                  now=1000.0, created_at=1.0)
    assert res.settlements_new == 1                     # F1 settled
    assert res.settlements_by_outcome.get("WIN") == 1
    assert any("F2" in e for e in res.errors)           # F2 error recorded, not fatal


# ── Telegram: render + safety + consumer isolation ──────────────────────────
def _settlement_dict(**over) -> dict:
    rec = build_settlement(_shadow(**{k: v for k, v in over.items()
                                      if k in _shadow()}),
                           _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0).to_dict()
    rec.update({k: v for k, v in over.items() if k not in _shadow()})
    return rec


def test_settlement_card_renders_required_fields():
    rec = build_settlement(_shadow(), _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0).to_dict()
    lookup = {rec["shadow_id"]: _shadow()}
    text = shadow_feed.render_settlement_card(rec, shadow_lookup=lookup,
                                              final_direction="TOWARD_MODEL")
    assert "SETTLED" in text
    assert "comp_9788" in text
    assert "total_goals" in text.lower() or "Total_goals" in text
    assert "Settlement: WIN" in text
    assert "Final market movement: TOWARD_MODEL" in text  # separate axis line
    assert "NOT VALIDATED" in text and "NOT ACTIONABLE" in text
    # neutral: no betting-signal vocabulary
    from src.research.prospective.research_notify import assert_no_signal_content_research
    assert_no_signal_content_research(text)


def test_settlement_message_is_shadow_research_update_type():
    rec = build_settlement(_shadow(), _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0).to_dict()
    lookup = {rec["shadow_id"]: _shadow()}
    msg = shadow_feed.build_settlement_message(rec, now=0.0, shadow_lookup=lookup)
    assert msg.message_type is MessageType.SHADOW_RESEARCH_UPDATE


def test_publishable_settlement_requires_publishable_parent():
    rec = build_settlement(_shadow(), _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0).to_dict()
    # publishable parent
    assert shadow_feed.is_publishable_settlement(rec, shadow_lookup={rec["shadow_id"]: _shadow()})
    # reconstructed parent -> not publishable
    recon = _shadow(provenance_kind="RECONSTRUCTED_SHADOW")
    assert not shadow_feed.is_publishable_settlement(rec, shadow_lookup={rec["shadow_id"]: recon})
    # missing parent -> not publishable
    assert not shadow_feed.is_publishable_settlement(rec, shadow_lookup={})


def _seed_settlements(root: Path, settlements: list[dict], shadows: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "shadow_settlements.jsonl", "w") as fh:
        for s in settlements:
            fh.write(json.dumps(s) + "\n")
    with open(root / SHADOW_CANDIDATES_FILE, "w") as fh:
        for s in shadows:
            fh.write(json.dumps(s) + "\n")


def test_settlement_feed_default_off_sends_nothing(tmp_path, monkeypatch):
    for k in ("RESEARCH_SHADOW_FEED_PUBLISH", "RESEARCH_TELEGRAM_BOT_TOKEN",
              "RESEARCH_TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(k, raising=False)
    rec = build_settlement(_shadow(), _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0).to_dict()
    _seed_settlements(tmp_path, [rec], [_shadow()])
    res = shadow_feed.publish_settlement_feed(shadow_root=tmp_path)
    assert res.shadows_seen == 1 and res.messages_sent == 0  # publishable but not sent


def test_settlement_feed_optin_without_creds_sends_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_SHADOW_FEED_PUBLISH", "1")
    monkeypatch.delenv("RESEARCH_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("RESEARCH_TELEGRAM_CHAT_ID", raising=False)
    rec = build_settlement(_shadow(), _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0).to_dict()
    _seed_settlements(tmp_path, [rec], [_shadow()])
    res = shadow_feed.publish_settlement_feed(shadow_root=tmp_path)
    assert res.messages_sent == 0


def test_settlement_feed_consumer_creds_only_sends_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_SHADOW_FEED_PUBLISH", "1")
    monkeypatch.delenv("RESEARCH_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("RESEARCH_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("SIGNALS_TELEGRAM_BOT_TOKEN", "consumer_tok")
    monkeypatch.setenv("SIGNALS_TELEGRAM_CHAT_ID", "consumer_chat")
    rec = build_settlement(_shadow(), _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0).to_dict()
    _seed_settlements(tmp_path, [rec], [_shadow()])
    res = shadow_feed.publish_settlement_feed(shadow_root=tmp_path)
    assert res.messages_sent == 0  # no fallback to consumer channel


def test_settlement_feed_enabled_with_injected_transport_sends(tmp_path, monkeypatch):
    class _T:
        def __init__(self):
            self.sent = []
        def send(self, text):
            self.sent.append(text)
            return True, "ok"
    t = _T()
    rec = build_settlement(_shadow(), _result(), valid_commitment_hashes=frozenset({VALID_HASH}),
                           created_at=1.0).to_dict()
    _seed_settlements(tmp_path, [rec], [_shadow()])
    res = shadow_feed.publish_settlement_feed(shadow_root=tmp_path, transport=t)
    assert res.messages_sent == 1
    assert "SETTLED" in t.sent[0]


def test_settlement_cannot_be_validated_signal():
    # The message type used is a research type, never a reserved signal type.
    from src.research.prospective.research_notify import (
        MessageType, build_research_shadow_message, ReservedMessageTypeError,
    )
    with pytest.raises(ReservedMessageTypeError):
        build_research_shadow_message(MessageType.VALIDATED_SIGNAL, "e", "t", generated_at=0.0)
