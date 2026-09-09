"""Truth-table tests for the centralized external-publication policy.

The boundary requires BOTH DATA_ACCUMULATION_MODE=0 AND
SIGNAL_PUBLICATION_STATE=PROMOTED. A single env change must never open it, and
everything fails closed. Both legacy publication paths must consult the same
policy, the research monitor must be unaffected, and the reserved Telegram
types must remain impossible regardless of accumulation mode.
"""

from __future__ import annotations

import importlib.util

import pytest

from src.research._data_accumulation_mode import (
    PublicationState,
    can_publish_validated_signals,
    is_data_accumulation_mode,
    publication_suppressed,
    resolve_publication_state,
)


def _set(monkeypatch, accumulation, state):
    if accumulation is None:
        monkeypatch.delenv("DATA_ACCUMULATION_MODE", raising=False)
    else:
        monkeypatch.setenv("DATA_ACCUMULATION_MODE", accumulation)
    if state is None:
        monkeypatch.delenv("SIGNAL_PUBLICATION_STATE", raising=False)
    else:
        monkeypatch.setenv("SIGNAL_PUBLICATION_STATE", state)


# --- truth table --------------------------------------------------------


def test_default_env_suppresses(monkeypatch):
    _set(monkeypatch, None, None)
    assert can_publish_validated_signals() is False
    assert publication_suppressed() is True


def test_accumulation_on_research_only_suppress(monkeypatch):
    _set(monkeypatch, "1", "RESEARCH_ONLY")
    assert can_publish_validated_signals() is False


def test_accumulation_on_promoted_suppress(monkeypatch):
    # accumulation ON dominates: PROMOTED alone is not enough.
    _set(monkeypatch, "1", "PROMOTED")
    assert can_publish_validated_signals() is False


def test_accumulation_off_research_only_suppress(monkeypatch):
    # accumulation OFF alone is not enough.
    _set(monkeypatch, "0", "RESEARCH_ONLY")
    assert can_publish_validated_signals() is False


def test_both_conditions_allow(monkeypatch):
    _set(monkeypatch, "0", "PROMOTED")
    assert can_publish_validated_signals() is True
    assert publication_suppressed() is False


def test_promoted_alone_without_state_var_suppress(monkeypatch):
    # accumulation off but state unset -> RESEARCH_ONLY -> suppress.
    _set(monkeypatch, "0", None)
    assert can_publish_validated_signals() is False


# --- fail-closed on malformed inputs ------------------------------------


def test_malformed_accumulation_suppresses(monkeypatch):
    _set(monkeypatch, "garbage", "PROMOTED")
    # malformed accumulation -> treated as ON -> suppress
    assert is_data_accumulation_mode() is True
    assert can_publish_validated_signals() is False


def test_malformed_state_resolves_research_only(monkeypatch):
    _set(monkeypatch, "0", "garbage")
    assert resolve_publication_state() is PublicationState.RESEARCH_ONLY
    assert can_publish_validated_signals() is False


def test_empty_state_resolves_research_only(monkeypatch):
    _set(monkeypatch, "0", "")
    assert resolve_publication_state() is PublicationState.RESEARCH_ONLY
    assert can_publish_validated_signals() is False


def test_promoted_is_case_and_space_insensitive(monkeypatch):
    _set(monkeypatch, "0", "  promoted  ")
    assert resolve_publication_state() is PublicationState.PROMOTED
    assert can_publish_validated_signals() is True


# --- both legacy publication paths use the SAME policy ------------------


def _load_signals_bot():
    spec = importlib.util.spec_from_file_location("sbot", "scripts/signals_telegram_bot.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_signals_bot_follows_policy_suppress_when_off_only(monkeypatch):
    # accumulation off but not promoted -> still suppressed.
    _set(monkeypatch, "0", "RESEARCH_ONLY")
    m = _load_signals_bot()
    out = m.run(dry_run=False)
    assert out.get("suppressed") is True
    assert out.get("reason") == "SUPPRESSED_RESEARCH_ONLY"


def test_signals_bot_not_suppressed_when_promoted(monkeypatch):
    # Both conditions met -> the suppression early-return does NOT fire. The bot
    # then proceeds to its normal (empty, no signals file) path — the key point
    # is that the policy gate no longer blocks it.
    _set(monkeypatch, "0", "PROMOTED")
    m = _load_signals_bot()
    out = m.run(dry_run=False)
    assert out.get("suppressed") is not True


def test_forecast_broadcast_uses_policy(monkeypatch):
    # The forecast path uses the centralized policy; verify via source that it
    # depends on the shared symbol and has no duplicated direct-gate call.
    src = open("scripts/forecast_broadcast.py", encoding="utf-8").read()
    assert "can_publish_validated_signals" in src
    assert "is_data_accumulation_mode(" not in src  # no direct/duplicated gate


def test_signals_bot_uses_policy_symbol():
    src = open("scripts/signals_telegram_bot.py", encoding="utf-8").read()
    assert "can_publish_validated_signals" in src


# --- reserved Telegram types remain impossible --------------------------


def test_reserved_types_impossible_even_with_accumulation_off(monkeypatch):
    _set(monkeypatch, "0", "PROMOTED")  # most permissive possible env
    from src.research.prospective.research_notify import (
        MessageType,
        ReservedMessageTypeError,
        _msg,
    )
    from tests.research.prospective.test_research_notify import _status

    s = _status()
    for reserved in (MessageType.VALIDATED_SIGNAL, MessageType.STRATEGY_ACTION):
        with pytest.raises(ReservedMessageTypeError):
            _msg(reserved, "x", "hello", s)


# --- research monitor unaffected by publication policy ------------------


def test_research_monitor_status_unaffected(monkeypatch):
    # The observability monitor reports status regardless of publication policy;
    # it never publishes signals, so the gate does not apply to it.
    _set(monkeypatch, "1", "RESEARCH_ONLY")
    from src.research.prospective.research_notify import format_daily_heartbeat
    from tests.research.prospective.test_research_notify import _status

    msg = format_daily_heartbeat(_status())
    assert "Research Status" in msg.text
    # And with the most permissive env, the heartbeat is still just status.
    _set(monkeypatch, "0", "PROMOTED")
    msg2 = format_daily_heartbeat(_status())
    assert msg2.message_type.value == "DATA_PROGRESS"
