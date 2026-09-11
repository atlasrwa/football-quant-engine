"""The research Telegram feed carries the expanded universe — safely.

Proves boundary claims G, H, I and J:

G. A valid ``PROSPECTIVE_SHADOW`` from a formerly non-Pilot-C league reaches the
   research Telegram renderer/feed when publication is explicitly enabled.
H. A subsequent shadow evaluation produces its research update.
I. Default configuration publishes nothing.
J. The research feed cannot fall back to consumer credentials.

Plus: a Telegram failure must never break prospective capture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.research.prospective import shadow_feed
from src.research.prospective.research_notify import (
    MessageType,
    assert_no_signal_content_research,
)

#: Deliberately not a Pilot-C competition.
NEW_LEAGUE_COMP = "comp_5840"   # Germany Bundesliga
KICKOFF = 1_789_500_000.0
CUTOFF = KICKOFF - 24 * 3600.0

#: Every Telegram env name the research feed must never read.
FOREIGN_CREDENTIAL_ENV = (
    "SIGNALS_TELEGRAM_BOT_TOKEN",
    "SIGNALS_TELEGRAM_CHAT_ID",
    "HEARTBEAT_TELEGRAM_BOT_TOKEN",
    "HEARTBEAT_TELEGRAM_CHAT_ID",
    "FORECAST_BROADCAST_TELEGRAM_BOT_TOKEN",
    "FORECAST_BROADCAST_TELEGRAM_CHAT_ID",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
)


def _shadow(shadow_id: str = "s" * 32, competition: str = NEW_LEAGUE_COMP) -> dict:
    """A publishable PROSPECTIVE_SHADOW record, as persisted."""
    return {
        "record_type": "SHADOW_RESIDUAL",
        "payload_contract_version": "shadow-residual-payload/v1",
        "provenance_kind": "PROSPECTIVE_SHADOW",
        "classification": ["RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE"],
        "fixture_id": "mt_new_1",
        "competition": competition,
        "kickoff_ts": KICKOFF,
        "information_cutoff": CUTOFF,
        "generated_at": CUTOFF - 3600.0,
        "market_observed_at": CUTOFF,
        "market_retrieved_at": CUTOFF,
        "provider": "thestatsapi",
        "bookmaker": "pinnacle",
        "market": "total_goals",
        "selection": "over",
        "line": 2.5,
        "p_model": 0.61,
        "raw_over_odds": 1.85,
        "raw_under_odds": 2.05,
        "raw_implied_probability": 0.5405,
        "p_market_devig": 0.5256,
        "devig_method": "multiplicative",
        "raw_probability_residual": 0.0844,
        "logit_residual": 0.35,
        "forecast_commitment_hash": "commit_new_1",
        "model_version": "model_champion_v2",
        "scope_version_hash": "research_scope_v1",
        "market_snapshot_hash": "snap_1",
        "shadow_id": shadow_id,
        "created_at": CUTOFF + 1.0,
        "shadow_payload_hash": "payload_1",
    }


def _evaluation(shadow_id: str = "s" * 32) -> dict:
    return {
        "record_type": "SHADOW_RESIDUAL_EVALUATION",
        "payload_contract_version": "shadow-residual-evaluation/v1",
        "classification": ["RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE"],
        "shadow_id": shadow_id,
        "shadow_payload_hash": "payload_1",
        "evaluation_id": "e" * 32,
        "fixture_id": "mt_new_1",
        "competition": NEW_LEAGUE_COMP,
        "kickoff_ts": KICKOFF,
        "bookmaker": "pinnacle",
        "market": "total_goals",
        "selection": "over",
        "line": 2.5,
        "p_model": 0.61,
        "p_market_earlier": 0.5256,
        "later_market_devig": 0.5601,
        "later_observed_at": KICKOFF - 3600.0,
        "later_market_snapshot_hash": "snap_2",
        "delta_probability": 0.0345,
        "delta_logit": 0.14,
        "movement_direction": "TOWARD_MODEL",
        "devig_method": "multiplicative",
        "created_at": KICKOFF - 3500.0,
    }


def _write_ledgers(root: Path, *, shadows=(), evaluations=()) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "shadow_residuals.jsonl", "w", encoding="utf-8") as handle:
        for rec in shadows:
            handle.write(json.dumps(rec) + "\n")
    with open(root / "shadow_evaluations.jsonl", "w", encoding="utf-8") as handle:
        for rec in evaluations:
            handle.write(json.dumps(rec) + "\n")


@pytest.fixture
def clean_env(monkeypatch):
    """Remove every Telegram-related env var, so tests start fail-closed."""
    for name in FOREIGN_CREDENTIAL_ENV + (
        "RESEARCH_SHADOW_FEED_PUBLISH",
        "RESEARCH_TELEGRAM_BOT_TOKEN",
        "RESEARCH_TELEGRAM_CHAT_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _enable(monkeypatch):
    monkeypatch.setenv("RESEARCH_SHADOW_FEED_PUBLISH", "1")
    monkeypatch.setenv("RESEARCH_TELEGRAM_BOT_TOKEN", "research-token")
    monkeypatch.setenv("RESEARCH_TELEGRAM_CHAT_ID", "-100999")


class RecordingTransport:
    """Captures sends instead of performing them."""

    def __init__(self, ok: bool = True):
        self.ok = ok
        self.sent: list[str] = []

    def send(self, text: str):
        self.sent.append(text)
        return (self.ok, "recorded" if self.ok else "forced failure")


# ── G. new-league shadow reaches the feed when explicitly enabled ────────────
def test_new_league_shadow_reaches_the_research_feed(tmp_path, clean_env):
    _enable(clean_env)
    root = tmp_path / "prospective"
    _write_ledgers(root, shadows=[_shadow()])
    transport = RecordingTransport()

    result = shadow_feed.publish_shadow_feed(shadow_root=root, transport=transport)

    assert result.shadows_seen == 1
    assert result.shadows_published == 1
    assert result.messages_sent == 1
    assert len(transport.sent) == 1

    body = transport.sent[0]
    # The card identifies the research observation, including its competition.
    assert NEW_LEAGUE_COMP in body
    assert "mt_new_1" in body
    assert "total_goals" in body and "2.5" in body
    assert "pinnacle" in body
    assert "61.0%" in body      # model probability
    assert "52.6%" in body      # market probability
    # A single shadow for a fixture renders through the grouped card, whose
    # footer states the same classification in sentence case.
    upper = body.upper()
    assert "NOT VALIDATED" in upper
    assert "NOT ACTIONABLE" in upper
    # Neutral gap presentation: no EV / ROI / edge / validation claims.
    assert_no_signal_content_research(body)


def test_new_league_card_is_the_shadow_research_message_type(tmp_path, clean_env):
    """The initial eligible shadow produces the SHADOW_RESEARCH equivalent."""
    _enable(clean_env)
    root = tmp_path / "prospective"
    _write_ledgers(root, shadows=[_shadow()])

    from src.research.prospective.research_notify import build_research_shadow_message

    card = shadow_feed.render_shadow_card(_shadow())
    message = build_research_shadow_message(
        MessageType.SHADOW_RESEARCH,
        f"shadow:{'s' * 32}",
        card,
        generated_at=CUTOFF + 1.0,
    )
    assert message.message_type is MessageType.SHADOW_RESEARCH


def test_shadows_from_several_new_leagues_all_publish(tmp_path, clean_env):
    _enable(clean_env)
    root = tmp_path / "prospective"
    shadows = []
    for index, comp in enumerate(("comp_5840", "comp_9799", "comp_4795")):
        rec = _shadow(shadow_id=f"{index}" * 32, competition=comp)
        rec["fixture_id"] = f"mt_new_{index}"
        rec["shadow_payload_hash"] = f"payload_{index}"
        shadows.append(rec)
    _write_ledgers(root, shadows=shadows)
    transport = RecordingTransport()

    result = shadow_feed.publish_shadow_feed(shadow_root=root, transport=transport)

    assert result.shadows_published == 3
    joined = "\n".join(transport.sent)
    for comp in ("comp_5840", "comp_9799", "comp_4795"):
        assert comp in joined


# ── H. the subsequent evaluation reaches the feed as an update ───────────────
def test_evaluation_from_new_league_produces_a_research_update(tmp_path, clean_env):
    _enable(clean_env)
    root = tmp_path / "prospective"
    _write_ledgers(root, shadows=[_shadow()], evaluations=[_evaluation()])
    transport = RecordingTransport()

    result = shadow_feed.publish_shadow_feed(shadow_root=root, transport=transport)

    assert result.evaluations_seen == 1
    assert result.evaluations_published == 1
    update = [t for t in transport.sent if "UPDATE" in t or "RESULT" in t]
    assert update, f"no update card among {transport.sent}"
    body = update[0]
    assert NEW_LEAGUE_COMP in body
    assert "TOWARD MODEL" in body
    assert_no_signal_content_research(body)


def test_update_card_is_the_shadow_research_update_message_type():
    from src.research.prospective.research_notify import build_research_shadow_message

    card = shadow_feed.render_evaluation_card(
        _evaluation(), shadow_lookup={"s" * 32: _shadow()}
    )
    message = build_research_shadow_message(
        MessageType.SHADOW_RESEARCH_UPDATE,
        f"shadow_eval:{'e' * 32}",
        card,
        generated_at=KICKOFF - 3500.0,
    )
    assert message.message_type is MessageType.SHADOW_RESEARCH_UPDATE


def test_orphan_evaluation_without_a_publishable_parent_does_not_publish(tmp_path, clean_env):
    """Parent linkage is still required; expansion does not relax it."""
    _enable(clean_env)
    root = tmp_path / "prospective"
    _write_ledgers(root, shadows=[], evaluations=[_evaluation()])
    transport = RecordingTransport()

    result = shadow_feed.publish_shadow_feed(shadow_root=root, transport=transport)
    assert result.evaluations_published == 0
    assert transport.sent == []


# ── I. default configuration publishes nothing ──────────────────────────────
def test_default_configuration_sends_nothing(tmp_path, clean_env):
    root = tmp_path / "prospective"
    _write_ledgers(root, shadows=[_shadow()], evaluations=[_evaluation()])

    result = shadow_feed.publish_shadow_feed(shadow_root=root)

    assert result.messages_sent == 0
    assert shadow_feed.shadow_feed_publication_enabled() is False
    assert shadow_feed.research_telegram_transport() is None


def test_publication_flag_off_yields_zero_sends(tmp_path, clean_env):
    clean_env.setenv("RESEARCH_SHADOW_FEED_PUBLISH", "0")
    clean_env.setenv("RESEARCH_TELEGRAM_BOT_TOKEN", "research-token")
    clean_env.setenv("RESEARCH_TELEGRAM_CHAT_ID", "-100999")
    root = tmp_path / "prospective"
    _write_ledgers(root, shadows=[_shadow()])

    result = shadow_feed.publish_shadow_feed(shadow_root=root)
    assert result.messages_sent == 0


def test_missing_dedicated_credentials_yields_zero_sends(tmp_path, clean_env):
    """Flag on, credentials absent -> fail closed."""
    clean_env.setenv("RESEARCH_SHADOW_FEED_PUBLISH", "1")
    root = tmp_path / "prospective"
    _write_ledgers(root, shadows=[_shadow()])

    result = shadow_feed.publish_shadow_feed(shadow_root=root)
    assert result.messages_sent == 0
    assert shadow_feed.research_telegram_transport() is None


@pytest.mark.parametrize("present", ["token_only", "chat_only"])
def test_partial_credentials_yield_zero_sends(tmp_path, clean_env, present):
    clean_env.setenv("RESEARCH_SHADOW_FEED_PUBLISH", "1")
    if present == "token_only":
        clean_env.setenv("RESEARCH_TELEGRAM_BOT_TOKEN", "research-token")
    else:
        clean_env.setenv("RESEARCH_TELEGRAM_CHAT_ID", "-100999")
    root = tmp_path / "prospective"
    _write_ledgers(root, shadows=[_shadow()])

    assert shadow_feed.research_telegram_transport() is None
    assert shadow_feed.publish_shadow_feed(shadow_root=root).messages_sent == 0


# ── J. no fallback to consumer / heartbeat / forecast credentials ────────────
def test_consumer_credentials_alone_yield_zero_research_sends(tmp_path, clean_env):
    """Every foreign Telegram credential present; research creds absent."""
    clean_env.setenv("RESEARCH_SHADOW_FEED_PUBLISH", "1")
    for name in FOREIGN_CREDENTIAL_ENV:
        clean_env.setenv(name, "foreign-value")
    root = tmp_path / "prospective"
    _write_ledgers(root, shadows=[_shadow()], evaluations=[_evaluation()])

    assert shadow_feed.research_telegram_transport() is None, (
        "the research feed must not resolve a transport from consumer, heartbeat, "
        "or forecast-broadcast credentials"
    )
    result = shadow_feed.publish_shadow_feed(shadow_root=root)
    assert result.messages_sent == 0


def test_research_transport_reads_only_the_dedicated_env_names(clean_env):
    _enable(clean_env)
    for name in FOREIGN_CREDENTIAL_ENV:
        clean_env.setenv(name, "foreign-value")

    transport = shadow_feed.research_telegram_transport()
    assert transport is not None
    assert transport.token_env == (shadow_feed.RESEARCH_TELEGRAM_TOKEN_ENV,)
    assert transport.chat_env == (shadow_feed.RESEARCH_TELEGRAM_CHAT_ENV,)


# ── failure isolation + delivery contract ───────────────────────────────────
def test_telegram_failure_does_not_break_prospective_capture(tmp_path, clean_env):
    """A transport failure is isolated; the ledgers are untouched."""
    _enable(clean_env)
    root = tmp_path / "prospective"
    _write_ledgers(root, shadows=[_shadow()])
    before = (root / "shadow_residuals.jsonl").read_text(encoding="utf-8")

    failing = RecordingTransport(ok=False)
    result = shadow_feed.publish_shadow_feed(shadow_root=root, transport=failing)

    assert result.messages_sent == 0
    assert failing.sent, "a send was attempted"
    # Capture/shadow state is unchanged by the delivery failure.
    assert (root / "shadow_residuals.jsonl").read_text(encoding="utf-8") == before


def test_capture_tick_survives_a_raising_shadow_feed(tmp_path, monkeypatch):
    """The capture-tick wrapper must swallow feed errors into its own ops log."""
    from src.research.prospective import cli as prospective_cli

    root = tmp_path / "prospective"
    root.mkdir(parents=True, exist_ok=True)

    def boom(**_kwargs):
        raise RuntimeError("telegram exploded")

    monkeypatch.setattr(shadow_feed, "publish_shadow_feed", boom)
    # Must not raise.
    prospective_cli._publish_shadow_feed_after_capture(capture_root=root)

    ops = (root / "shadow_feed_ops.jsonl").read_text(encoding="utf-8")
    assert "SHADOW_FEED_FAILED" in ops or "ERROR" in ops


def test_republication_is_suppressed_by_the_delivery_ledger(tmp_path, clean_env):
    """At-least-once with best-effort dedup: a second pass re-sends nothing."""
    _enable(clean_env)
    root = tmp_path / "prospective"
    _write_ledgers(root, shadows=[_shadow()])

    first = shadow_feed.publish_shadow_feed(
        shadow_root=root, transport=RecordingTransport()
    )
    second_transport = RecordingTransport()
    second = shadow_feed.publish_shadow_feed(
        shadow_root=root, transport=second_transport
    )

    assert first.messages_sent == 1
    assert second.messages_sent == 0
    assert second_transport.sent == []


def test_reconstructed_shadow_is_never_published(tmp_path, clean_env):
    """Historical evidence cannot reach the research feed, in any league."""
    _enable(clean_env)
    root = tmp_path / "prospective"
    rec = _shadow()
    rec["provenance_kind"] = "RECONSTRUCTED_SHADOW"
    _write_ledgers(root, shadows=[rec])
    transport = RecordingTransport()

    result = shadow_feed.publish_shadow_feed(shadow_root=root, transport=transport)
    assert result.shadows_published == 0
    assert transport.sent == []


def test_shadow_with_cutoff_at_or_after_kickoff_is_never_published(tmp_path, clean_env):
    _enable(clean_env)
    root = tmp_path / "prospective"
    rec = _shadow()
    rec["information_cutoff"] = rec["kickoff_ts"] + 1.0
    _write_ledgers(root, shadows=[rec])
    transport = RecordingTransport()

    result = shadow_feed.publish_shadow_feed(shadow_root=root, transport=transport)
    assert result.shadows_published == 0
    assert transport.sent == []


def test_feed_contains_no_league_allowlist():
    """Structural: the feed must have no competition predicate."""
    import inspect

    source = inspect.getsource(shadow_feed)
    for banned in ("comp_3039", "comp_8321", "comp_9777", "comp_0976"):
        assert banned not in source
