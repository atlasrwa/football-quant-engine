"""Tests for the research-only shadow-residual Telegram feed (shadow_feed.py).

Covers the mission's 25 required scenarios. Everything is consume-only over
persisted records; no provider, model, or residual recomputation is exercised
(and several tests assert that explicitly by monkeypatching those seams to
raise if touched).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.research._data_accumulation_mode import can_publish_validated_signals
from src.research.prospective import shadow_feed
from src.research.prospective.research_notify import (
    MessageType,
    ReservedMessageTypeError,
    SignalContentError,
    _FORBIDDEN_SUBSTRINGS,
    assert_no_signal_content,
    assert_no_signal_content_research,
    build_research_shadow_message,
)
from src.research.prospective.research_notify_delivery import NotifyLedger
from src.research.prospective.shadow_store import (
    SHADOW_CANDIDATES_FILE,
    SHADOW_EVALUATIONS_FILE,
)


# ---------------------------------------------------------------------------
# Record builders (plain persisted dicts, as read from the JSONL ledgers)
# ---------------------------------------------------------------------------


def _shadow(**over) -> dict:
    rec = {
        "record_type": "SHADOW_RESIDUAL",
        "provenance_kind": "PROSPECTIVE_SHADOW",
        "classification": ["RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE"],
        "fixture_id": "F123",
        "competition": "C1",
        "kickoff_ts": 1000.0 + 58 * 60,
        "information_cutoff": 1000.0,
        "provider": "prov",
        "bookmaker": "Pinnacle",
        "market": "Goals",
        "selection": "over",
        "line": 2.5,
        "p_model": 0.570,
        "p_market_devig": 0.512,
        "raw_probability_residual": 0.058,
        "shadow_id": "8f3a91c2deadbeef0000000000000001",
    }
    rec.update(over)
    return rec


def _evaluation(**over) -> dict:
    rec = {
        "record_type": "SHADOW_RESIDUAL_EVALUATION",
        "classification": ["RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE"],
        "evaluation_id": "e0000000000000000000000000000001",
        "shadow_id": "8f3a91c2deadbeef0000000000000001",
        "fixture_id": "F123",
        "bookmaker": "Pinnacle",
        "market": "Goals",
        "selection": "over",
        "line": 2.5,
        "p_market_earlier": 0.512,
        "later_market_devig": 0.534,
        "later_observed_at": 998000.0,
        "delta_probability": 0.022,
        "movement_direction": "TOWARD_MODEL",
    }
    rec.update(over)
    return rec


class _OkTransport:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)
        return True, "ok message_id=1"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _seed(root: Path, shadows=None, evaluations=None) -> None:
    _write_jsonl(root / SHADOW_CANDIDATES_FILE, shadows or [])
    _write_jsonl(root / SHADOW_EVALUATIONS_FILE, evaluations or [])


def _publish(root: Path, transport, **kw):
    ledger = kw.pop("ledger", None) or NotifyLedger(path=root / "notify_ledger.json")
    return shadow_feed.publish_shadow_feed(
        shadow_root=root, ledger=ledger, transport=transport,
        group_by_fixture_cards=kw.pop("group", False), **kw
    )


# ---------------------------------------------------------------------------
# 1. PROSPECTIVE_SHADOW publishes
# ---------------------------------------------------------------------------


def test_01_prospective_shadow_publishes(tmp_path):
    _seed(tmp_path, shadows=[_shadow()])
    t = _OkTransport()
    res = _publish(tmp_path, t)
    assert res.shadows_published == 1
    assert res.messages_sent == 1
    assert "SHADOW RESIDUAL" in t.sent[0]


# ---------------------------------------------------------------------------
# 2. RECONSTRUCTED_SHADOW never publishes
# ---------------------------------------------------------------------------


def test_02_reconstructed_shadow_never_publishes(tmp_path):
    _seed(tmp_path, shadows=[_shadow(provenance_kind="RECONSTRUCTED_SHADOW")])
    t = _OkTransport()
    res = _publish(tmp_path, t)
    assert res.shadows_seen == 0
    assert res.messages_sent == 0
    assert t.sent == []
    assert shadow_feed.is_publishable_shadow(_shadow(provenance_kind="RECONSTRUCTED_SHADOW")) is False


# ---------------------------------------------------------------------------
# 3. malformed classification fails closed
# ---------------------------------------------------------------------------


def test_03_malformed_classification_fails_closed(tmp_path):
    bad = [
        _shadow(classification=["RESEARCH_ONLY"]),                 # missing tokens
        _shadow(classification="RESEARCH_ONLY,NOT_VALIDATED"),     # wrong type (str)
        _shadow(classification=None),                              # missing
        _shadow(classification=["RESEARCH_ONLY", "NOT_VALIDATED", "ACTIONABLE"]),  # wrong token
    ]
    for rec in bad:
        assert shadow_feed.is_publishable_shadow(rec) is False
    _seed(tmp_path, shadows=bad)
    t = _OkTransport()
    res = _publish(tmp_path, t)
    assert res.messages_sent == 0 and t.sent == []


# ---------------------------------------------------------------------------
# 4. raw residual formatted as pp correctly
# ---------------------------------------------------------------------------


def test_04_positive_residual_pp(tmp_path):
    assert shadow_feed.format_pp(0.058) == "+5.8 pp"
    _seed(tmp_path, shadows=[_shadow(raw_probability_residual=0.058)])
    t = _OkTransport()
    _publish(tmp_path, t)
    assert "Residual: +5.8 pp" in t.sent[0]


# ---------------------------------------------------------------------------
# 5. negative residual formatted correctly
# ---------------------------------------------------------------------------


def test_05_negative_residual_pp(tmp_path):
    assert shadow_feed.format_pp(-0.031) == "-3.1 pp"
    _seed(tmp_path, shadows=[_shadow(raw_probability_residual=-0.031)])
    t = _OkTransport()
    _publish(tmp_path, t)
    assert "Residual: -3.1 pp" in t.sent[0]


# ---------------------------------------------------------------------------
# 6. exact bookmaker retained
# ---------------------------------------------------------------------------


def test_06_exact_bookmaker_retained(tmp_path):
    _seed(tmp_path, shadows=[_shadow(bookmaker="Bet365")])
    t = _OkTransport()
    _publish(tmp_path, t)
    assert "Bet365" in t.sent[0]


# ---------------------------------------------------------------------------
# 7. exact line retained
# ---------------------------------------------------------------------------


def test_07_exact_line_retained(tmp_path):
    _seed(tmp_path, shadows=[_shadow(market="Corners", selection="under", line=9.5)])
    t = _OkTransport()
    _publish(tmp_path, t)
    assert "9.5" in t.sent[0]
    assert "Corners - Under 9.5" in t.sent[0]


# ---------------------------------------------------------------------------
# 8. exact selection retained
# ---------------------------------------------------------------------------


def test_08_exact_selection_retained(tmp_path):
    _seed(tmp_path, shadows=[_shadow(selection="under")])
    t = _OkTransport()
    _publish(tmp_path, t)
    assert "Under" in t.sent[0]


# ---------------------------------------------------------------------------
# 9. T-minus uses information_cutoff (not send time)
# ---------------------------------------------------------------------------


def test_09_t_minus_uses_information_cutoff(tmp_path):
    # kickoff - cutoff = 58 minutes, regardless of "now" (send time) = huge.
    rec = _shadow(kickoff_ts=1000.0 + 58 * 60, information_cutoff=1000.0)
    _seed(tmp_path, shadows=[rec])
    t = _OkTransport()
    _publish(tmp_path, t, now=10_000_000.0)  # send time far from cutoff
    assert "T-58m" in t.sent[0]
    # And a longer gap renders hours+minutes.
    assert shadow_feed.format_t_minus(kickoff_ts=1000.0 + 102 * 60, information_cutoff=1000.0) == "T-1h 42m"


# ---------------------------------------------------------------------------
# 10. shadow dedup by shadow_id
# ---------------------------------------------------------------------------


def test_10_shadow_dedup_by_shadow_id(tmp_path):
    _seed(tmp_path, shadows=[_shadow()])
    t = _OkTransport()
    ledger = NotifyLedger(path=tmp_path / "notify_ledger.json")
    r1 = _publish(tmp_path, t, ledger=ledger)
    assert r1.messages_sent == 1
    # Re-run against same file + same ledger: dedup, nothing re-sent.
    r2 = _publish(tmp_path, t, ledger=ledger)
    assert r2.shadows_seen == 0
    assert r2.messages_sent == 0
    assert len(t.sent) == 1


# ---------------------------------------------------------------------------
# 11. evaluation dedup by evaluation_id
# ---------------------------------------------------------------------------


def test_11_evaluation_dedup_by_evaluation_id(tmp_path):
    _seed(tmp_path, shadows=[_shadow()], evaluations=[_evaluation()])
    t = _OkTransport()
    ledger = NotifyLedger(path=tmp_path / "notify_ledger.json")
    _publish(tmp_path, t, ledger=ledger)
    n_after_first = len(t.sent)
    r2 = _publish(tmp_path, t, ledger=ledger)
    assert r2.evaluations_seen == 0
    assert len(t.sent) == n_after_first  # evaluation not re-sent


# ---------------------------------------------------------------------------
# 12. restart does not replay history
# ---------------------------------------------------------------------------


def test_12_restart_does_not_replay_history(tmp_path):
    _seed(tmp_path, shadows=[_shadow(), _shadow(shadow_id="s2", fixture_id="F2")],
          evaluations=[_evaluation()])
    t = _OkTransport()
    ledger1 = NotifyLedger(path=tmp_path / "notify_ledger.json")
    _publish(tmp_path, t, ledger=ledger1)
    sent_first = len(t.sent)
    assert sent_first >= 1
    # Simulate a full restart: brand-new ledger object over the SAME file.
    ledger2 = NotifyLedger(path=tmp_path / "notify_ledger.json")
    r2 = _publish(tmp_path, t, ledger=ledger2)
    assert r2.messages_sent == 0
    assert len(t.sent) == sent_first  # nothing replayed


# ---------------------------------------------------------------------------
# 13-15. movement direction formatting
# ---------------------------------------------------------------------------


def test_13_toward_model_formatting(tmp_path):
    _seed(tmp_path, shadows=[_shadow()], evaluations=[_evaluation(movement_direction="TOWARD_MODEL")])
    t = _OkTransport()
    _publish(tmp_path, t)
    assert "Direction: TOWARD MODEL" in t.sent[-1]
    # Not celebrated as a win.
    assert "win" not in t.sent[-1].lower()


def test_14_away_from_model_formatting(tmp_path):
    _seed(tmp_path, shadows=[_shadow()], evaluations=[_evaluation(movement_direction="AWAY_FROM_MODEL")])
    t = _OkTransport()
    _publish(tmp_path, t)
    assert "Direction: AWAY FROM MODEL" in t.sent[-1]
    assert "loss" not in t.sent[-1].lower()


def test_15_flat_formatting(tmp_path):
    _seed(tmp_path, shadows=[_shadow()], evaluations=[_evaluation(movement_direction="FLAT")])
    t = _OkTransport()
    _publish(tmp_path, t)
    assert "Direction: FLAT" in t.sent[-1]


# ---------------------------------------------------------------------------
# 16. no residual recomputation in Telegram
# ---------------------------------------------------------------------------


def test_16_no_residual_recomputation(tmp_path, monkeypatch):
    # If the feed recomputed anything it would touch build_shadow_residual /
    # de-vig. Make those raise; the feed must still publish using the persisted
    # residual value verbatim.
    import src.research.prospective.shadow_residual as sr

    monkeypatch.setattr(sr, "build_shadow_residual", lambda *a, **k: (_ for _ in ()).throw(AssertionError("recomputed!")))
    monkeypatch.setattr(sr, "build_movement_evaluation", lambda *a, **k: (_ for _ in ()).throw(AssertionError("recomputed!")))
    monkeypatch.setattr(sr, "market_over_probability", lambda *a, **k: (_ for _ in ()).throw(AssertionError("devig!")))

    _seed(tmp_path, shadows=[_shadow(raw_probability_residual=0.1234)])
    t = _OkTransport()
    _publish(tmp_path, t)
    # Uses the stored value (12.3 pp), not any recomputation.
    assert "Residual: +12.3 pp" in t.sent[0]


# ---------------------------------------------------------------------------
# 17. no provider calls
# ---------------------------------------------------------------------------


def test_17_no_provider_calls(tmp_path, monkeypatch):
    # Guard the network primitive urlopen; the feed must never open a URL.
    import urllib.request

    def _boom(*a, **k):
        raise AssertionError("provider/network call attempted")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    _seed(tmp_path, shadows=[_shadow()])
    t = _OkTransport()  # in-process transport; no real network
    res = _publish(tmp_path, t)
    assert res.messages_sent == 1


# ---------------------------------------------------------------------------
# 18. no model calls
# ---------------------------------------------------------------------------


def test_18_no_model_calls(tmp_path):
    # The feed only imports formatting + store reading. Assert the module does
    # not import any model/fitting module at publish time by checking p_model is
    # taken verbatim from the record.
    _seed(tmp_path, shadows=[_shadow(p_model=0.7777)])
    t = _OkTransport()
    _publish(tmp_path, t)
    assert "Research model: 77.8%" in t.sent[0]


# ---------------------------------------------------------------------------
# 19. can_publish_validated_signals() remains False
# ---------------------------------------------------------------------------


def test_19_can_publish_validated_signals_false(monkeypatch):
    monkeypatch.delenv("DATA_ACCUMULATION_MODE", raising=False)
    monkeypatch.delenv("SIGNAL_PUBLICATION_STATE", raising=False)
    assert can_publish_validated_signals() is False


# ---------------------------------------------------------------------------
# 20. research-shadow messages still work while validated publication suppressed
# ---------------------------------------------------------------------------


def test_20_shadow_feed_works_while_validated_suppressed(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ACCUMULATION_MODE", "1")
    monkeypatch.delenv("SIGNAL_PUBLICATION_STATE", raising=False)
    assert can_publish_validated_signals() is False
    _seed(tmp_path, shadows=[_shadow()])
    t = _OkTransport()
    res = _publish(tmp_path, t)
    assert res.messages_sent == 1  # research feed independent of the validated gate


# ---------------------------------------------------------------------------
# 21. VALIDATED_SIGNAL remains impossible (on the shadow path)
# ---------------------------------------------------------------------------


def test_21_validated_signal_impossible():
    with pytest.raises(ReservedMessageTypeError):
        build_research_shadow_message(MessageType.VALIDATED_SIGNAL, "x", "hello", generated_at=1.0)


# ---------------------------------------------------------------------------
# 22. STRATEGY_ACTION remains impossible (on the shadow path)
# ---------------------------------------------------------------------------


def test_22_strategy_action_impossible():
    with pytest.raises(ReservedMessageTypeError):
        build_research_shadow_message(MessageType.STRATEGY_ACTION, "x", "hello", generated_at=1.0)


def test_22b_status_types_also_rejected_on_shadow_path():
    # The shadow builder only permits the two SHADOW_RESEARCH* types.
    with pytest.raises(ReservedMessageTypeError):
        build_research_shadow_message(MessageType.DATA_PROGRESS, "x", "hello", generated_at=1.0)


# ---------------------------------------------------------------------------
# 23. research gates unchanged (global content guard intact)
# ---------------------------------------------------------------------------


def test_23_global_content_guard_unchanged():
    # The global guard still rejects "actionable" (unchanged); only the research
    # path narrowly allows the "NOT ACTIONABLE" label.
    with pytest.raises(SignalContentError):
        assert_no_signal_content("this is actionable")
    # Research guard still rejects genuine betting vocabulary.
    for banned in ("value bet", "expected roi", "stake 2u", "profit", "+ev", "edge over"):
        with pytest.raises(SignalContentError):
            assert_no_signal_content_research(f"foo {banned} bar")
    # But allows the approved classification label.
    assert_no_signal_content_research("Research only. Not validated. Not actionable.")
    # "actionable" alone (not part of the allowed phrase) is still rejected.
    with pytest.raises(SignalContentError):
        assert_no_signal_content_research("this is actionable")


# ---------------------------------------------------------------------------
# 24. champion unchanged (no forbidden economic-action vocabulary in cards)
# ---------------------------------------------------------------------------


def test_24_cards_contain_no_action_vocabulary(tmp_path):
    _seed(
        tmp_path,
        shadows=[_shadow()],
        evaluations=[_evaluation()],
    )
    t = _OkTransport()
    _publish(tmp_path, t)
    # Economic-action vocabulary that must never appear. Note "NOT ACTIONABLE"
    # is the APPROVED research classification label, so we neutralise it before
    # scanning rather than banning the substring "action" outright.
    banned_words = ("wager", "buy", "sell", "profitable", "alpha", "strategy",
                    " bet ", "stake", "tipster")
    for text in t.sent:
        low = text.lower().replace("not actionable", " ").replace("actionable", " ")
        for w in banned_words:
            assert w not in low, f"card contains forbidden word {w!r}: {text}"


# ---------------------------------------------------------------------------
# 25. existing Telegram health/heartbeat tests still pass -> imported here to
#     assert the shared modules remain importable + unchanged in behaviour.
# ---------------------------------------------------------------------------


def test_25_existing_notify_surface_intact():
    from src.research.prospective.research_notify import (
        MILESTONES,
        RESERVED_TYPES,
        format_daily_heartbeat,
    )

    # Active + reserved types unchanged; new shadow types added but reserved set
    # is exactly the two signal/strategy types.
    assert {t.value for t in RESERVED_TYPES} == {"VALIDATED_SIGNAL", "STRATEGY_ACTION"}
    assert MessageType.SHADOW_RESEARCH not in RESERVED_TYPES
    assert MessageType.SHADOW_RESEARCH_UPDATE not in RESERVED_TYPES
    assert "captured_fixtures" in MILESTONES  # milestone gate untouched


# ---------------------------------------------------------------------------
# Extra: fixture-grouped batching + per-tick cap (neutral, magnitude-agnostic)
# ---------------------------------------------------------------------------


def test_batching_caps_messages_and_queues_rest_without_ranking(tmp_path):
    # Three fixtures, one shadow each; cap at 2 messages/tick.
    shadows = [
        _shadow(fixture_id="A", shadow_id="a1", raw_probability_residual=0.01),
        _shadow(fixture_id="B", shadow_id="b1", raw_probability_residual=0.09),  # largest
        _shadow(fixture_id="C", shadow_id="c1", raw_probability_residual=0.05),
    ]
    _seed(tmp_path, shadows=shadows)
    t = _OkTransport()
    ledger = NotifyLedger(path=tmp_path / "notify_ledger.json")
    res = shadow_feed.publish_shadow_feed(
        shadow_root=tmp_path, ledger=ledger, transport=t,
        group_by_fixture_cards=True, max_messages=2,
    )
    assert res.messages_sent == 2
    assert res.shadows_queued == 1
    # Order of appearance (A, B), NOT by residual magnitude (which would pick B, C).
    assert "fixture A" in t.sent[0]
    assert "fixture B" in t.sent[1]
    # Next tick delivers the remaining one (C) via the ledger.
    res2 = shadow_feed.publish_shadow_feed(
        shadow_root=tmp_path, ledger=ledger, transport=t,
        group_by_fixture_cards=True, max_messages=2,
    )
    assert res2.messages_sent == 1
    assert "fixture C" in t.sent[2]


def test_group_card_member_dedup_survives_new_sibling(tmp_path):
    # Fixture with one shadow, published as a group card; then a NEW sibling
    # shadow appears in the same fixture next tick. The already-published shadow
    # must not be re-sent (member-level dedup), only the new one.
    _seed(tmp_path, shadows=[_shadow(fixture_id="F", shadow_id="m1")])
    t = _OkTransport()
    ledger = NotifyLedger(path=tmp_path / "notify_ledger.json")
    shadow_feed.publish_shadow_feed(shadow_root=tmp_path, ledger=ledger, transport=t,
                                    group_by_fixture_cards=True)
    assert len(t.sent) == 1 and "m1"[:8] not in t.sent[0]  # ref uses shadow_id prefix

    # Add a sibling and re-run.
    _write_jsonl(
        tmp_path / SHADOW_CANDIDATES_FILE,
        [_shadow(fixture_id="F", shadow_id="m1"), _shadow(fixture_id="F", shadow_id="m2")],
    )
    res2 = shadow_feed.publish_shadow_feed(shadow_root=tmp_path, ledger=ledger, transport=t,
                                           group_by_fixture_cards=True)
    # Only m2 is unseen; m1 already delivered (member dedup).
    assert res2.shadows_seen == 1
    assert res2.shadows_published == 1


def test_absent_records_say_nothing(tmp_path):
    # No files at all -> nothing published, no error.
    t = _OkTransport()
    res = shadow_feed.publish_shadow_feed(shadow_root=tmp_path, transport=t)
    assert res.messages_sent == 0 and t.sent == []


def test_evaluation_malformed_classification_fails_closed(tmp_path):
    _seed(tmp_path, evaluations=[_evaluation(classification=["RESEARCH_ONLY"])])
    t = _OkTransport()
    res = _publish(tmp_path, t)
    assert res.messages_sent == 0 and t.sent == []



# ===========================================================================
# BLOCKER 1 — evaluation must prove its parent shadow is prospective
# ===========================================================================


def _lookup(*shadows: dict) -> dict:
    return {s["shadow_id"]: s for s in shadows}


def test_b1_1_evaluation_linked_to_prospective_publishes(tmp_path):
    parent = _shadow(shadow_id="p1", fixture_id="F1")
    ev = _evaluation(shadow_id="p1", fixture_id="F1", evaluation_id="ev_p1")
    assert shadow_feed.is_publishable_evaluation(ev, shadow_lookup=_lookup(parent)) is True
    _seed(tmp_path, shadows=[parent], evaluations=[ev])
    t = _OkTransport()
    res = _publish(tmp_path, t)
    assert res.evaluations_published == 1
    assert any("SHADOW UPDATE" in m for m in t.sent)


def test_b1_2_evaluation_linked_to_reconstructed_does_not_publish(tmp_path):
    parent = _shadow(shadow_id="r1", fixture_id="F1", provenance_kind="RECONSTRUCTED_SHADOW")
    ev = _evaluation(shadow_id="r1", fixture_id="F1", evaluation_id="ev_r1")
    # The evaluation itself is structurally valid, but its parent is reconstructed.
    assert shadow_feed.is_structurally_valid_evaluation(ev) is True
    assert shadow_feed.is_publishable_evaluation(ev, shadow_lookup=_lookup(parent)) is False
    _seed(tmp_path, shadows=[parent], evaluations=[ev])
    t = _OkTransport()
    res = _publish(tmp_path, t)
    assert res.evaluations_published == 0
    assert all("SHADOW UPDATE" not in m for m in t.sent)


def test_b1_3_evaluation_missing_parent_does_not_publish(tmp_path):
    ev = _evaluation(shadow_id="ghost", fixture_id="F1", evaluation_id="ev_ghost")
    assert shadow_feed.is_publishable_evaluation(ev, shadow_lookup={}) is False
    _seed(tmp_path, shadows=[], evaluations=[ev])  # no parent persisted
    t = _OkTransport()
    res = _publish(tmp_path, t)
    assert res.evaluations_published == 0 and t.sent == []


def test_b1_4_evaluation_malformed_parent_does_not_publish(tmp_path):
    # Parent present but malformed (bad p_model) -> not publishable-prospective.
    parent = _shadow(shadow_id="m1", fixture_id="F1", p_model=1.5)  # invalid probability
    ev = _evaluation(shadow_id="m1", fixture_id="F1", evaluation_id="ev_m1")
    assert shadow_feed.is_publishable_shadow(parent) is False
    assert shadow_feed.is_publishable_evaluation(ev, shadow_lookup=_lookup(parent)) is False
    _seed(tmp_path, shadows=[parent], evaluations=[ev])
    t = _OkTransport()
    res = _publish(tmp_path, t)
    assert res.evaluations_published == 0
    assert all("SHADOW UPDATE" not in m for m in t.sent)


def test_b1_5_evaluation_not_publishable_from_own_classification_alone(tmp_path):
    # Own classification is valid, but there is NO publishable parent. Provenance
    # must be proven by parent linkage, never inferred from classification.
    ev = _evaluation(shadow_id="orphan", evaluation_id="ev_orphan")
    assert shadow_feed._classification_ok(ev) is True
    assert shadow_feed.is_structurally_valid_evaluation(ev) is True
    assert shadow_feed.is_publishable_evaluation(ev, shadow_lookup={}) is False
    # Even with a reconstructed parent carrying the same valid classification.
    recon = _shadow(shadow_id="orphan", provenance_kind="RECONSTRUCTED_SHADOW")
    assert shadow_feed.is_publishable_evaluation(ev, shadow_lookup=_lookup(recon)) is False


# ===========================================================================
# BLOCKER 2 — scientific fields must fail closed, not default to zero
# ===========================================================================


def test_b2_1_valid_prospective_shadow_renders_unchanged(tmp_path):
    _seed(tmp_path, shadows=[_shadow()])
    t = _OkTransport()
    _publish(tmp_path, t)
    assert "Market: 51.2%" in t.sent[0]
    assert "Research model: 57.0%" in t.sent[0]
    assert "Residual: +5.8 pp" in t.sent[0]


@pytest.mark.parametrize("bad", [1.5, 0.0, 1.0, -0.1, "0.57", None])
def test_b2_2_malformed_p_model_rejected(bad):
    assert shadow_feed.is_publishable_shadow(_shadow(p_model=bad)) is False


@pytest.mark.parametrize("bad", [1.5, 0.0, 1.0, -0.1, "0.5", None])
def test_b2_3_malformed_p_market_rejected(bad):
    assert shadow_feed.is_publishable_shadow(_shadow(p_market_devig=bad)) is False


def test_b2_4_missing_residual_rejected():
    rec = _shadow()
    del rec["raw_probability_residual"]
    assert shadow_feed.is_publishable_shadow(rec) is False


def test_b2_5_nan_inf_rejected():
    assert shadow_feed.is_publishable_shadow(_shadow(raw_probability_residual=float("nan"))) is False
    assert shadow_feed.is_publishable_shadow(_shadow(raw_probability_residual=float("inf"))) is False
    assert shadow_feed.is_publishable_shadow(_shadow(p_model=float("nan"))) is False
    assert shadow_feed.is_publishable_shadow(_shadow(kickoff_ts=float("inf"))) is False


def test_b2_6_cutoff_ge_kickoff_rejected():
    assert shadow_feed.is_publishable_shadow(_shadow(information_cutoff=2000.0, kickoff_ts=2000.0)) is False
    assert shadow_feed.is_publishable_shadow(_shadow(information_cutoff=2001.0, kickoff_ts=2000.0)) is False


def test_b2_7_missing_bookmaker_market_selection_rejected():
    assert shadow_feed.is_publishable_shadow(_shadow(bookmaker="")) is False
    assert shadow_feed.is_publishable_shadow(_shadow(market="   ")) is False
    rec = _shadow(); del rec["selection"]
    assert shadow_feed.is_publishable_shadow(rec) is False
    assert shadow_feed.is_publishable_shadow(_shadow(fixture_id="")) is False


def test_b2_line_required_finite():
    assert shadow_feed.is_publishable_shadow(_shadow(line=None)) is False
    assert shadow_feed.is_publishable_shadow(_shadow(line="2.5")) is False
    assert shadow_feed.is_publishable_shadow(_shadow(line=float("nan"))) is False


def test_b2_8_malformed_evaluation_rejected():
    parent = _shadow(shadow_id="p1")
    lut = _lookup(parent)
    # missing later_market_devig
    ev = _evaluation(shadow_id="p1"); del ev["later_market_devig"]
    assert shadow_feed.is_publishable_evaluation(ev, shadow_lookup=lut) is False
    # non-finite delta
    ev2 = _evaluation(shadow_id="p1", delta_probability=float("inf"))
    assert shadow_feed.is_publishable_evaluation(ev2, shadow_lookup=lut) is False
    # bad earlier probability
    ev3 = _evaluation(shadow_id="p1", p_market_earlier=0.0)
    assert shadow_feed.is_publishable_evaluation(ev3, shadow_lookup=lut) is False


def test_b2_9_unknown_movement_direction_rejected():
    parent = _shadow(shadow_id="p1")
    ev = _evaluation(shadow_id="p1", movement_direction="MOON")
    assert shadow_feed.is_publishable_evaluation(ev, shadow_lookup=_lookup(parent)) is False
    ev2 = _evaluation(shadow_id="p1", movement_direction="")
    assert shadow_feed.is_publishable_evaluation(ev2, shadow_lookup=_lookup(parent)) is False


def test_b2_render_never_fabricates_zero(tmp_path):
    # A record that slips past would raise rather than print 0.0 — prove the
    # strict renderer refuses a missing scientific field.
    bad = _shadow()
    del bad["p_model"]
    with pytest.raises(shadow_feed.ShadowCardError):
        shadow_feed.render_shadow_card(bad)
    # And the feed as a whole never emits a fabricated 0.0 card for it.
    _seed(tmp_path, shadows=[bad])
    t = _OkTransport()
    res = _publish(tmp_path, t)
    assert res.messages_sent == 0 and t.sent == []


def test_b2_no_zero_percent_or_zero_pp_in_any_emitted_card(tmp_path):
    # Seed a mix of valid + corrupt; only valid publishes, and no emitted card
    # contains a fabricated 0.0% / +0.0 pp from a missing field.
    _seed(
        tmp_path,
        shadows=[_shadow(shadow_id="ok1"), _shadow(shadow_id="bad1", p_model=None)],
    )
    t = _OkTransport()
    _publish(tmp_path, t)
    for m in t.sent:
        assert "0.0%" not in m
        assert "+0.0 pp" not in m


# ===========================================================================
# Regression: dedup / batching / gates / champion still hold after the fixes
# ===========================================================================


def test_reg_dedup_unchanged(tmp_path):
    _seed(tmp_path, shadows=[_shadow()])
    t = _OkTransport()
    led = NotifyLedger(path=tmp_path / "notify_ledger.json")
    assert _publish(tmp_path, t, ledger=led).messages_sent == 1
    assert _publish(tmp_path, t, ledger=led).messages_sent == 0


def test_reg_batching_unchanged(tmp_path):
    shadows = [_shadow(fixture_id=f"F{i}", shadow_id=f"s{i}") for i in range(5)]
    _seed(tmp_path, shadows=shadows)
    t = _OkTransport()
    led = NotifyLedger(path=tmp_path / "notify_ledger.json")
    res = shadow_feed.publish_shadow_feed(shadow_root=tmp_path, ledger=led, transport=t,
                                          group_by_fixture_cards=True, max_messages=3)
    assert res.messages_sent == 3 and res.shadows_queued == 2


def test_reg_gates_remain_300_200_150_100():
    from src.research.prospective.research_notify import MILESTONES
    assert MILESTONES["captured_fixtures"][-1] == 300
    assert MILESTONES["same_book_late_final"][-1] == 200
    assert MILESTONES["confirmed_lineups"][-1] == 150
    assert MILESTONES["pre_post_lineup_pairs"][-1] == 100


def test_reg_no_provider_calls(tmp_path, monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    _seed(tmp_path, shadows=[_shadow()], evaluations=[_evaluation()])
    t = _OkTransport()
    res = _publish(tmp_path, t)
    assert res.messages_sent >= 1


def test_reg_no_model_calls(tmp_path, monkeypatch):
    import src.research.prospective.shadow_residual as sr
    monkeypatch.setattr(sr, "build_shadow_residual",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("model")))
    monkeypatch.setattr(sr, "market_over_probability",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("devig")))
    _seed(tmp_path, shadows=[_shadow()], evaluations=[_evaluation()])
    t = _OkTransport()
    res = _publish(tmp_path, t)
    assert res.messages_sent >= 1
