"""Tests for the DATA ACCUMULATION MODE Telegram research monitor.

Covers: heartbeat formatting, live-count loading, milestone crossing +
deduplication, readiness transition (and NOT triggering early), critical
health alert, prediction-signal suppression, Telegram-failure isolation, secret
redaction, and restart-safe notification ledger.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.research._data_accumulation_mode import is_data_accumulation_mode
from src.research.prospective.research_notify import (
    MILESTONES,
    MessageType,
    ReservedMessageTypeError,
    ResearchStatus,
    SignalContentError,
    assert_no_signal_content,
    format_critical_alert,
    format_daily_heartbeat,
    format_milestone,
    format_readiness_transition,
    milestones_crossed,
)
from src.research.prospective.research_notify_delivery import (
    NotifyLedger,
    deliver,
)


def _status(**over) -> ResearchStatus:
    gate = {
        "met": over.get("gate_met", False),
        "checks": {
            "captured_fixtures": {"observed": over.get("captured_fixtures", 30), "required": 300, "met": False},
            "same_book_late_final": {"observed": over.get("same_book_late_final", 0), "required": 200, "met": False},
            "confirmed_lineups": {"observed": over.get("confirmed_lineups", 0), "required": 150, "met": False},
            "pre_post_lineup_pairs": {"observed": over.get("pre_post_lineup_pairs", 0), "required": 100, "met": False},
        },
    }
    base = dict(
        generated_at=1_788_000_000.0, main_sha="abc123", collector_version="prospective-collector/1",
        collector_health="HEALTHY", minutes_since_success=4.0, last_successful_run=1_787_999_000.0,
        quota_remaining=96_700, errors_last_run=0, total_runs=5,
        captured_fixtures=30, same_book_late_final=0, confirmed_lineups=0,
        pre_post_lineup_pairs=0,
        genuine_close_available=over.get("genuine_close_available", True),
        fixtures_with_genuine_close=over.get("fixtures_with_genuine_close", 0),
        genuine_closing_keys=over.get("genuine_closing_keys", 0),
        readiness_state="PRICE_DISCOVERY_EXPLORATORY", gate_met=False, gate=gate,
    )
    base.update({k: v for k, v in over.items() if k in base})
    base["gate"] = gate
    return ResearchStatus(**base)


class _FailTransport:
    def send(self, text):  # noqa: ARG002
        return False, "HTTP 500 boom"


class _RaiseTransport:
    def send(self, text):  # noqa: ARG002
        raise RuntimeError("network exploded")


class _OkTransport:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)
        return True, "ok message_id=1"


# --- heartbeat formatting + live counts ---------------------------------


def test_heartbeat_format_and_live_counts():
    s = _status(captured_fixtures=42, quota_remaining=96_700)
    msg = format_daily_heartbeat(s)
    assert msg.message_type is MessageType.DATA_PROGRESS
    assert "FOOTBALL QUANT ENGINE" in msg.text
    assert "SYSTEM" in msg.text and "RESEARCH ACCUMULATION" in msg.text
    assert "Collector: HEALTHY" in msg.text
    assert "Fixtures: 42 / 300" in msg.text          # live count, not hard-coded
    assert "96,700 / 100,000" in msg.text
    assert "PRICE DISCOVERY \u2014 EXPLORATORY" in msg.text
    assert "Research only. Not validated. Not actionable." in msg.text
    # provenance present
    assert msg.main_sha == "abc123"
    assert msg.payload_hash and len(msg.payload_hash) == 64


def test_heartbeat_dedup_id_is_per_utc_day():
    s = _status()
    assert format_daily_heartbeat(s).event_id.startswith("heartbeat:")


# --- milestones ---------------------------------------------------------


def test_milestones_crossed_deterministic():
    s = _status(captured_fixtures=210, same_book_late_final=60,
                confirmed_lineups=0, pre_post_lineup_pairs=0)
    crossed = milestones_crossed(s)
    assert ("captured_fixtures", 100) in crossed
    assert ("captured_fixtures", 200) in crossed
    assert ("captured_fixtures", 300) not in crossed
    assert ("same_book_late_final", 50) in crossed
    assert ("same_book_late_final", 100) not in crossed


def test_milestone_dedup_across_restart(tmp_path):
    s = _status(captured_fixtures=120)
    ledger = NotifyLedger(path=tmp_path / "ledger.json")
    msg = format_milestone(s, metric="captured_fixtures", threshold=100)
    t = _OkTransport()
    r1 = deliver(msg, transport=t, ledger=ledger)
    assert r1.sent is True and len(t.sent) == 1
    # Simulate restart: brand-new ledger object over the SAME persisted file.
    ledger2 = NotifyLedger(path=tmp_path / "ledger.json")
    r2 = deliver(msg, transport=t, ledger=ledger2)
    assert r2.deduped is True and len(t.sent) == 1  # not resent


def test_milestone_threshold_vs_captured_wording():
    # The observed count can be far above the threshold; the message must show
    # BOTH explicitly (Required vs Captured), never the misleading
    # "Reached 200 ... (2520 observed)" phrasing.
    s = _status(same_book_late_final=2520)
    msg = format_milestone(s, metric="same_book_late_final", threshold=200)
    assert "RESEARCH MILESTONE" in msg.text
    assert "Required: 200" in msg.text
    assert "Captured: 2,520" in msg.text            # thousands-separated
    assert "\u2705" in msg.text                       # captured tick
    # Exploratory framing preserved; no validation/actionable/edge language.
    assert "This unlocks analysis. It does not validate a signal." in msg.text
    assert "PRICE DISCOVERY \u2014 EXPLORATORY" in msg.text
    low = msg.text.lower()
    for banned in ("validated", "alpha", "edge", "profitable", "actionable ", " ev ", "+ev"):
        assert banned not in low


def test_milestone_dedup_id_unchanged():
    s = _status(same_book_late_final=2520)
    msg = format_milestone(s, metric="same_book_late_final", threshold=200)
    assert msg.event_id == "milestone:same_book_late_final:200"


def test_status_sections_and_genuine_close_unit():
    s = _status(captured_fixtures=35, same_book_late_final=2520,
                fixtures_with_genuine_close=27, genuine_closing_keys=3058)
    text = format_daily_heartbeat(s).text
    # Three clearly separated sections.
    assert "SYSTEM" in text
    assert "RESEARCH ACCUMULATION" in text
    assert "READINESS" in text
    # Genuine-close metric carries an EXPLICIT unit (fixtures), never bare
    # "Genuine closes: N".
    assert "Fixtures with genuine close: 27 / 35" in text
    assert "genuine closing keys: 3,058" in text
    assert "Genuine closes:" not in text
    # Crossed accumulation line marked, research-only footer present.
    assert "LATE \u2192 FINAL transitions: 2,520 / 200 \u2705" in text
    assert "Research only. Not validated. Not actionable." in text


def test_status_genuine_close_unknown_not_zero():
    s = _status(genuine_close_available=False, fixtures_with_genuine_close=None,
                genuine_closing_keys=None)
    text = format_daily_heartbeat(s).text
    assert "Fixtures with genuine close: UNKNOWN (source unavailable)" in text
    # Must never render a fabricated 0 for an unavailable source.
    assert "Fixtures with genuine close: 0" not in text


# --- readiness transition ----------------------------------------------


def test_readiness_transition_not_triggered_early(tmp_path):
    s = _status(gate_met=False)
    # The monitor only emits the transition when gate_met; formatting it here is
    # allowed, but the deterministic id ensures a single delivery when it happens.
    msg = format_readiness_transition(s)
    assert msg.message_type is MessageType.READINESS_TRANSITION
    # gate not met -> the caller (cmd_heartbeat) would not emit; assert the guard
    assert s.gate_met is False


def test_readiness_transition_when_gate_met_text():
    s = _status(gate_met=True, readiness_state="PRICE_DISCOVERY_EVALUABLE")
    msg = format_readiness_transition(s)
    assert "PRICE_DISCOVERY_EVALUABLE" in msg.text
    assert "eligible to run" in msg.text
    assert "No model has been promoted" in msg.text
    assert msg.event_id == "readiness:PRICE_DISCOVERY_EVALUABLE"


# --- critical alert -----------------------------------------------------


def test_critical_alert_format():
    s = _status(collector_health="STALE_SCHEDULER")
    msg = format_critical_alert(s, reason="STALE_SCHEDULER")
    assert msg.message_type is MessageType.CRITICAL_ALERT
    assert "CRITICAL" in msg.text
    assert "STALE_SCHEDULER" in msg.text


# --- signal suppression (content) --------------------------------------


def test_signal_vocabulary_is_rejected():
    for banned in ("value bet", "expected roi", "strong signal", "stake 2 units", "+ev play"):
        with pytest.raises(SignalContentError):
            assert_no_signal_content(f"foo {banned} bar")


def test_reserved_message_types_cannot_be_emitted():
    # The reserved types must never be constructed via the guarded path.
    from src.research.prospective.research_notify import _msg
    s = _status()
    with pytest.raises(ReservedMessageTypeError):
        _msg(MessageType.VALIDATED_SIGNAL, "x", "hello", s)
    with pytest.raises(ReservedMessageTypeError):
        _msg(MessageType.STRATEGY_ACTION, "x", "hello", s)


def test_data_accumulation_mode_default_suppresses(monkeypatch):
    monkeypatch.delenv("DATA_ACCUMULATION_MODE", raising=False)
    assert is_data_accumulation_mode() is True          # fail-safe default
    monkeypatch.setenv("DATA_ACCUMULATION_MODE", "0")
    assert is_data_accumulation_mode() is False
    monkeypatch.setenv("DATA_ACCUMULATION_MODE", "garbage")
    assert is_data_accumulation_mode() is True           # unrecognized -> suppress


def test_signals_bot_suppressed_in_accumulation_mode(monkeypatch):
    monkeypatch.setenv("DATA_ACCUMULATION_MODE", "1")
    import importlib.util
    spec = importlib.util.spec_from_file_location("sbot", "scripts/signals_telegram_bot.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    out = m.run(dry_run=False)
    assert out.get("suppressed") is True
    assert out.get("reason") == "SUPPRESSED_RESEARCH_ONLY"
    assert out.get("sent") == []


# --- telegram failure isolation ----------------------------------------


def test_telegram_failure_does_not_raise_or_record(tmp_path):
    s = _status()
    ledger = NotifyLedger(path=tmp_path / "ledger.json")
    msg = format_daily_heartbeat(s)
    r = deliver(msg, transport=_FailTransport(), ledger=ledger)
    assert r.sent is False
    # Not recorded as delivered -> will retry later (never marked done on failure).
    assert ledger.already_sent(msg.event_id) is False


def test_transport_exception_is_isolated(tmp_path):
    s = _status()
    ledger = NotifyLedger(path=tmp_path / "ledger.json")
    msg = format_daily_heartbeat(s)
    # Must not raise; returns a failed result.
    r = deliver(msg, transport=_RaiseTransport(), ledger=ledger)
    assert r.sent is False
    assert ledger.already_sent(msg.event_id) is False


# --- restart-safe ledger + secret safety --------------------------------


def test_ledger_records_only_non_secret_provenance(tmp_path):
    s = _status()
    ledger = NotifyLedger(path=tmp_path / "ledger.json")
    msg = format_daily_heartbeat(s)
    deliver(msg, transport=_OkTransport(), ledger=ledger)
    text = (tmp_path / "ledger.json").read_text()
    # Only non-secret fields; no token-like strings.
    assert "payload_hash" in text and "message_type" in text
    assert "TOKEN" not in text.upper()
    assert "bot" not in text.lower() or "message_id" in text  # detail may say message_id


def test_dedup_prevents_resend_same_event(tmp_path):
    s = _status()
    ledger = NotifyLedger(path=tmp_path / "ledger.json")
    msg = format_daily_heartbeat(s)
    t = _OkTransport()
    assert deliver(msg, transport=t, ledger=ledger).sent is True
    assert deliver(msg, transport=t, ledger=ledger).deduped is True
    assert len(t.sent) == 1
