"""Contract tests for the T-8h forecast broadcast.

WHY THIS FILE EXISTS
====================
This feature's entire value is a set of constraints. A broadcast is a two-sided
probability with provenance and *nothing else*: no stake sizing, no expected value or
edge, no recommended side, no confidence label unless the rule is declared in config,
and no language implying a bet should be placed. Those constraints are enforced in
code by ``assert_forecast_only``, and this file exists so that a future edit which
reintroduces EV or tipping framing fails here instead of shipping.

It also pins the delivery guarantees that make the published record trustworthy:
quiet hours may delay a send but never cancel it, a failed send is requeued and never
dropped, the ledger is append-only, and the commitment hash is tamper-evident.

The framing constraint is not cosmetic. The broadcast's probabilities come from the
pooled stat-mixer, whose per-league result did NOT replicate (41 of 189 cells
positive), and whose corners/cards predecessors were withdrawn for same-match feature
leakage (failure ledger F023). The probabilities are honest as predictions; nothing in
the output may imply validated skill or an edge. Do not weaken the content gate.

Promoted from an ad-hoc verification script on 2026-09-05 as part of Pilot C's
deprecation (F024), because a harness that lives in /tmp protects nothing.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.research.prediction_engine.broadcast import payload as P
from src.research.prediction_engine.broadcast import price_panel as PP
from src.research.prediction_engine.broadcast import scope_config as SC
from src.research.prediction_engine.broadcast.delivery import (
    ForecastDeliverer,
    PendingQueue,
    RecordingTransport,
    is_quiet_hours,
)
from src.research.prediction_engine.broadcast.record import BroadcastLedger, DeliveryStatus

REPO = Path("/home/ubuntu")

#: A self-contained declared scope. Deliberately NOT read from the live config file,
#: so these behavioural tests keep their meaning when declared scope legitimately
#: changes. The live file is validated separately in ``test_live_scope_config_parses``.
SCOPE_RAW: dict = {
    "config_contract": "forecast-broadcast-scope/v1",
    "horizon_hours_before_kickoff": 8,
    "leagues": [
        {"comp_id": "comp_8321", "label": "England Championship"},
        {"comp_id": "comp_3039", "label": "England Premier League"},
    ],
    "markets": [
        {"market": "goals", "line": 2.5,
         "over_label": "over 2.5 goals", "under_label": "under 2.5 goals"},
        {"market": "corners", "line": 9.5,
         "over_label": "over 9.5 corners", "under_label": "under 9.5 corners"},
        {"market": "cards", "line": 4.5,
         "over_label": "over 4.5 cards", "under_label": "under 4.5 cards"},
        {"market": "btts", "line": None,
         "over_label": "both teams to score - yes",
         "under_label": "both teams to score - no"},
    ],
    "line_selection_rule": {"rule": "FIXED_DECLARED_LINE"},
    "confidence_label_rule": None,
    "quiet_hours_utc": {"start_hour": 1, "end_hour": 6,
                        "policy": "DELAY_NEVER_CANCEL"},
}

CELLS = {("goals", 2.5): 0.4832, ("corners", 9.5): 0.5871,
         ("cards", 4.5): 0.3310, ("btts", None): 0.5402}
KICKOFF = 1788600000.0
GENERATED = "2026-09-05T03:59:16.336522+00:00"
MODEL_VERSION = "905303b401bb7611307de353739a4b515e5c43b04b6f861bf640b7d6a33a31ad"
DATA_CUTOFF = "2026-05-31T16:30:00+00:00"


# ── fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture()
def config() -> SC.ScopeConfig:
    return SC.parse_scope_config(SCOPE_RAW, source_path="<test>")


@pytest.fixture()
def make_payload(config):
    def _make(fixture_id="mt_test_0001", probs=None, reasons=None):
        return P.build_forecast_payload(
            config=config,
            fixture_id=fixture_id,
            comp_id="comp_8321",
            home_team="Stoke City",
            away_team="Charlton Athletic",
            kickoff_unix=KICKOFF,
            probabilities=CELLS if probs is None else probs,
            unavailable_reasons=reasons,
            model_version=MODEL_VERSION,
            data_cutoff_utc=DATA_CUTOFF,
            generated_at_utc=GENERATED,
        )
    return _make


@pytest.fixture()
def payload(make_payload):
    return make_payload()


@pytest.fixture()
def message(payload, config):
    return P.render_checked_message(payload, config)


class Clock:
    """Injectable UTC clock so quiet-hours behaviour is deterministic."""

    def __init__(self, dt: datetime) -> None:
        self.dt = dt

    def __call__(self) -> datetime:
        return self.dt


# ── the message is a probability with provenance, and nothing more ──────────
class TestMessageContent:
    def test_states_both_sides_of_every_market(self, message, config):
        for spec in config.markets:
            assert spec.over_label in message
            assert spec.under_label in message

    def test_every_displayed_pair_sums_to_one_hundred_percent(self, message):
        pairs = re.findall(r"(\d+)%\s+/\s+.*?(\d+)%", message)
        assert pairs, "no market rows rendered"
        for over, under in pairs:
            assert int(over) + int(under) == 100

    def test_carries_all_four_provenance_fields(self, message, payload):
        assert f"model_version: {MODEL_VERSION}" in message
        assert f"data_cutoff_utc: {DATA_CUTOFF}" in message
        assert f"generated_at_utc: {GENERATED}" in message
        assert payload.commitment_hash() in message

    def test_states_kickoff_in_utc(self, message, payload):
        assert f"Kick-off: {payload.kickoff_utc}" in message
        assert payload.kickoff_utc.endswith("+00:00")

    @pytest.mark.parametrize("word", [
        "stake", "unit", "units", "kelly", "bankroll", "EV", "edge", "value",
        "bet", "betting", "wager", "pick", "selection", "recommend", "advice",
        "confidence", "profit", "guaranteed", "lock", "sharp", "fair", "vig",
    ])
    def test_no_stake_ev_or_tipping_vocabulary(self, message, word):
        assert not re.search(rf"\b{word}\b", message, re.IGNORECASE), (
            f"forbidden word {word!r} appears in a published forecast"
        )

    def test_no_price_or_bookmaker_leaks_into_the_message(self, message):
        for token in ("odds", "bookmaker", "bet365", "betfair", "1.90", "2.10"):
            assert token.lower() not in message.lower()


# ── the content gate must fail closed. THIS IS THE INTEGRITY OF THE FEATURE ──
class TestContentGate:
    @pytest.mark.parametrize("addition", [
        "stake: 2 units",
        "Stake 1.5u",
        "EV +4.2%",
        "expected value +0.03",
        "edge vs market: 3%",
        "value bet",
        "+EV play",
        "Kelly fraction 0.03",
        "recommended bet: over 9.5 corners",
        "Recommended: over 9.5 corners",
        "our pick is the over",
        "worth backing",
        "best price 1.95",
        "get on this",
        "back the over",
        "guaranteed profit",
        "confidence: high",
        "ROI 6.1%",
        "bankroll 2%",
        "beats the market",
        # skill / edge-over-base-rate framing — the pooled BSS does not replicate
        # per-league, so skill claims must never reach a reader.
        "the model has genuine, modest skill over the base rate",
        "demonstrated skill in this league",
        "proven skill",
        "beats the base rate",
        "edge over the naive baseline",
        "this model outperforms the base rate",
        "validated: BSS +1.5%",
        "Brier skill score +1.67%",
        "the model beats naive here",
    ])
    def test_rejects_forbidden_framing(self, message, payload, addition):
        with pytest.raises(P.ForecastContentError):
            P.assert_forecast_only(f"{message}\n{addition}", payload)

    @pytest.mark.parametrize("skill_word", [
        "skill", "skilful", "outperform", "proven", "validated", "beats",
    ])
    def test_rejects_skill_claim_vocabulary(self, message, payload, skill_word):
        """A forecast is a calibrated probability, never a skill claim. The pooled
        BSS was contradicted by the per-league run, so any reintroduction of skill
        framing must fail the gate at send time (defence in depth for CI)."""
        with pytest.raises(P.ForecastContentError):
            P.assert_forecast_only(f"{message}\n{skill_word} demonstrated", payload)

    def test_rejects_a_message_that_drops_the_under_side(self, message, payload):
        one_sided = "\n".join(
            ln for ln in message.splitlines() if "under 9.5 corners" not in ln
        )
        with pytest.raises(P.ForecastContentError):
            P.assert_forecast_only(one_sided, payload)

    def test_rejects_a_message_missing_its_commitment_hash(self, message, payload):
        stripped = message.replace(payload.commitment_hash(), "")
        with pytest.raises(P.ForecastContentError):
            P.assert_forecast_only(stripped, payload)

    @pytest.mark.parametrize("field", ["model_version", "data_cutoff_utc",
                                       "generated_at_utc"])
    def test_rejects_a_message_missing_provenance(self, message, payload, field):
        stripped = "\n".join(
            ln for ln in message.splitlines() if not ln.startswith(f"{field}:")
        )
        with pytest.raises(P.ForecastContentError):
            P.assert_forecast_only(stripped, payload)

    def test_confidence_label_forbidden_unless_declared_in_config(
        self, message, payload, config
    ):
        assert not config.emits_confidence_label
        with pytest.raises(P.ForecastContentError):
            P.assert_forecast_only(
                f"{message}\nconfidence: high", payload,
                allow_confidence_label=False,
            )

    def test_confidence_label_permitted_only_when_rule_is_fixed_in_config(self):
        raw = dict(SCOPE_RAW)
        raw["confidence_label_rule"] = {
            "rule": "FIXED_BANDS",
            "bands": [[0.0, "low"], [0.6, "medium"], [0.8, "high"]],
        }
        cfg = SC.parse_scope_config(raw, source_path="<test>")
        assert cfg.emits_confidence_label
        # Applied identically to every fixture: same probability -> same label.
        assert cfg.confidence_label_rule.label_for(0.9) == "high"
        assert cfg.confidence_label_rule.label_for(0.1) == "low"

    def test_an_ad_hoc_confidence_rule_is_refused(self):
        raw = dict(SCOPE_RAW)
        raw["confidence_label_rule"] = {"rule": "PER_FIXTURE"}
        with pytest.raises(SC.ScopeConfigError):
            SC.parse_scope_config(raw)

    def test_render_checked_message_is_the_only_safe_path(self, payload, config):
        # render_checked_message gates in one step, so no caller can send ungated text.
        assert P.render_checked_message(payload, config) == P.render_message(payload)


# ── a market cannot be published one-sided, structurally ────────────────────
class TestTwoSidedByConstruction:
    def test_over_without_under_is_refused(self):
        with pytest.raises(P.ForecastContentError):
            P.MarketForecast(market="corners", line=9.5, over_label="o",
                             under_label="u", p_over=0.58, p_under=None)

    def test_non_complementary_sides_are_refused(self):
        with pytest.raises(P.ForecastContentError):
            P.MarketForecast(market="corners", line=9.5, over_label="o",
                             under_label="u", p_over=0.58, p_under=0.58)

    def test_unpriced_market_without_a_reason_is_refused(self):
        with pytest.raises(P.ForecastContentError):
            P.MarketForecast(market="corners", line=9.5, over_label="o",
                             under_label="u", p_over=None, p_under=None)

    def test_out_of_range_probability_is_refused(self):
        with pytest.raises(P.ForecastContentError):
            P.MarketForecast(market="corners", line=9.5, over_label="o",
                             under_label="u", p_over=1.4, p_under=-0.4)

    def test_under_is_derived_not_supplied(self, config):
        mf = P.build_market_forecast(config.markets[0], 0.4832)
        assert mf.p_over == pytest.approx(0.4832)
        assert mf.p_under == pytest.approx(0.5168)


# ── declared scope, not the model or the price, decides what is published ───
class TestScopeDrivesPublication:
    def test_unpriceable_market_is_published_as_an_explicit_gap(
        self, make_payload, config
    ):
        pay = make_payload(
            probs={("goals", 2.5): 0.48, ("corners", 9.5): None,
                   ("cards", 4.5): 0.33, ("btts", None): 0.54},
            reasons={("corners", 9.5): "no usable features at this kickoff"},
        )
        msg = P.render_checked_message(pay, config)
        assert len(pay.markets) == 4, "a declared market must never be dropped"
        assert "not published — no usable features at this kickoff" in msg

    def test_undeclared_cells_cannot_enter_the_payload(self, make_payload):
        pay = make_payload(probs={**CELLS, ("corners", 10.5): 0.99,
                                  ("goals", 1.5): 0.90})
        assert {(m.market, m.line) for m in pay.markets} == set(CELLS)
        rendered = P.render_message(pay)
        assert "10.5" not in rendered
        assert "1.5 goals" not in rendered

    def test_no_probability_threshold_filters_a_fixture(self, make_payload, config):
        # An unsure forecast is exactly as publishable as a confident one.
        for p in (0.01, 0.5, 0.99):
            pay = make_payload(probs={k: p for k in CELLS})
            msg = P.render_checked_message(pay, config)
            assert pay.priced_markets
            assert msg

    def test_runner_has_no_probability_threshold_constant(self):
        src = (REPO / "scripts" / "forecast_broadcast.py").read_text()
        assert not re.search(
            r"(MIN|MAX)_(PROB|CONFIDENCE|EDGE|EV)|PROB_THRESHOLD", src)


# ── the commitment hash ────────────────────────────────────────────────────
class TestCommitmentHash:
    def test_is_deterministic_and_sha256(self, payload, make_payload):
        assert payload.commitment_hash() == make_payload().commitment_hash()
        assert re.fullmatch(r"[0-9a-f]{64}", payload.commitment_hash())

    def test_stored_payload_reproduces_the_published_hash(self, payload):
        assert P.verify_commitment(payload.canonical_dict(),
                                   payload.commitment_hash())

    def test_altering_a_probability_breaks_the_hash(self, payload):
        tampered = payload.canonical_dict()
        tampered["markets"][1]["p_over"] = 0.99
        assert not P.verify_commitment(tampered, payload.commitment_hash())

    def test_redating_generated_at_breaks_the_hash(self, payload):
        redated = payload.canonical_dict()
        redated["generated_at_utc"] = "2026-09-05T09:00:00+00:00"
        assert not P.verify_commitment(redated, payload.commitment_hash())

    def test_rebuilt_payload_reproduces_the_hash(self, payload):
        rebuilt = P.payload_from_canonical_dict(payload.canonical_dict())
        assert rebuilt.commitment_hash() == payload.commitment_hash()


# ── quiet hours DELAY, never cancel ────────────────────────────────────────
class TestQuietHoursDelayNeverCancel:
    def _deliverer(self, tmp_path, clock, transport, config):
        ledger = BroadcastLedger(tmp_path)
        queue = PendingQueue(tmp_path / "pending_queue.jsonl")
        return ledger, queue, ForecastDeliverer(
            ledger=ledger, queue=queue, transport=transport,
            quiet_start_hour=config.quiet_hours_start_hour,
            quiet_end_hour=config.quiet_hours_end_hour, clock=clock,
        )

    def test_suppressed_forecast_is_queued_then_sent_unchanged(
        self, tmp_path, payload, message, config
    ):
        clock = Clock(datetime(2026, 9, 5, 2, 30, tzinfo=timezone.utc))  # inside 01-06
        transport = RecordingTransport()
        ledger, queue, deliverer = self._deliverer(tmp_path, clock, transport, config)
        ledger.append_commitment(payload, committed_at_utc=GENERATED)

        outcome = deliverer.deliver(
            commitment_hash=payload.commitment_hash(), fixture_id=payload.fixture_id,
            generated_at_utc=payload.generated_at_utc,
            kickoff_unix=payload.kickoff_unix, message=message,
        )
        assert outcome.status is DeliveryStatus.QUEUED_QUIET_HOURS
        assert transport.sent == [], "nothing may be transmitted during quiet hours"
        assert len(queue) == 1, "a suppressed forecast must be queued, never dropped"

        # A flush inside the window is a no-op and must not discard the envelope.
        assert deliverer.flush_queue() == []
        assert len(queue) == 1

        clock.dt = datetime(2026, 9, 5, 6, 5, tzinfo=timezone.utc)  # window closed
        outcomes = deliverer.flush_queue()
        assert len(outcomes) == 1
        assert outcomes[0].status is DeliveryStatus.SENT
        assert transport.sent == [message], "late send must be byte-identical"
        assert len(queue) == 0

        sent = [e for e in ledger.delivery_events() if e["status"] == "SENT"][0]
        assert sent["generated_at_utc"] == GENERATED, "original generation time kept"
        assert sent["commitment_hash"] == payload.commitment_hash()
        assert sent["event_at_utc"].startswith("2026-09-05T06:05")

    def test_queue_transition_is_recorded_on_the_permanent_ledger(
        self, tmp_path, payload, message, config
    ):
        clock = Clock(datetime(2026, 9, 5, 2, 0, tzinfo=timezone.utc))
        ledger, _q, deliverer = self._deliverer(
            tmp_path, clock, RecordingTransport(), config)
        deliverer.deliver(
            commitment_hash=payload.commitment_hash(), fixture_id=payload.fixture_id,
            generated_at_utc=GENERATED, kickoff_unix=payload.kickoff_unix,
            message=message,
        )
        assert any(e["status"] == "QUEUED_QUIET_HOURS"
                   for e in ledger.delivery_events())

    @pytest.mark.parametrize("hour,start,end,expected", [
        (3, 1, 6, True), (7, 1, 6, False),
        (1, 1, 6, True),        # start inclusive
        (6, 1, 6, False),       # end exclusive
        (23, 22, 6, True), (2, 22, 6, True), (12, 22, 6, False),  # wraps midnight
        (3, 0, 0, False),       # empty window suppresses nothing
    ])
    def test_quiet_window_arithmetic(self, hour, start, end, expected):
        assert is_quiet_hours(hour, start, end) is expected


# ── delivery failure is logged and requeued, never dropped ─────────────────
class TestDeliveryFailuresAreNeverDropped:
    def test_failure_requeues_and_survives_repeated_attempts(
        self, tmp_path, payload, message, config
    ):
        clock = Clock(datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc))  # not quiet
        ledger = BroadcastLedger(tmp_path)
        queue = PendingQueue(tmp_path / "pending_queue.jsonl")
        deliverer = ForecastDeliverer(
            ledger=ledger, queue=queue,
            transport=RecordingTransport(ok=False, detail="HTTP 502"),
            quiet_start_hour=1, quiet_end_hour=6, clock=clock,
        )
        outcome = deliverer.deliver(
            commitment_hash=payload.commitment_hash(), fixture_id=payload.fixture_id,
            generated_at_utc=GENERATED, kickoff_unix=payload.kickoff_unix,
            message=message,
        )
        assert outcome.status is DeliveryStatus.FAILED
        assert any(e["status"] == "FAILED" for e in ledger.delivery_events())
        assert len(queue) == 1

        for _ in range(7):
            deliverer.flush_queue()
        env = queue.load()[0]
        assert len(queue) == 1, "an envelope is never expired, however many failures"
        assert env.attempts >= 7
        assert env.message == message, "message preserved verbatim across retries"
        assert env.generated_at_utc == GENERATED


# ── the record is append-only ──────────────────────────────────────────────
class TestAppendOnlyRecord:
    def test_ledger_exposes_no_mutating_api(self, tmp_path):
        ledger = BroadcastLedger(tmp_path)
        assert not [m for m in dir(ledger) if re.search(
            r"update|delete|remove|edit|rewrite|truncate", m)]

    def test_attaching_an_outcome_does_not_touch_the_forecast_ledger(
        self, tmp_path, payload
    ):
        ledger = BroadcastLedger(tmp_path)
        ledger.append_commitment(payload, committed_at_utc=GENERATED)
        before = ledger.broadcast_path.read_text()
        ledger.append_outcome(
            commitment_hash=payload.commitment_hash(), fixture_id=payload.fixture_id,
            market="corners", line=9.5, settled_side="under", observed_value=8,
            source="test",
        )
        assert ledger.broadcast_path.read_text() == before
        assert ledger.outcomes()[0]["commitment_hash"] == payload.commitment_hash()

    def test_not_published_row_counts_as_fired_so_a_fixture_fires_once(
        self, tmp_path, payload, config
    ):
        ledger = BroadcastLedger(tmp_path)
        ledger.append_commitment(payload, committed_at_utc=GENERATED)
        ledger.append_not_published(
            fixture_id="mt_test_0002", comp_id="comp_3039", kickoff_unix=KICKOFF,
            reason="no match history in corpus",
            scope_version_hash=config.scope_version_hash,
        )
        assert ledger.fired_fixture_ids() == {payload.fixture_id, "mt_test_0002"}

    def test_stored_payloads_verify(self, tmp_path, payload):
        ledger = BroadcastLedger(tmp_path)
        ledger.append_commitment(payload, committed_at_utc=GENERATED)
        assert ledger.verify_commitment_hashes() == ()


# ── coverage is verifiable against declared scope ──────────────────────────
class TestCoverage:
    def test_a_fixture_with_no_row_is_reported_missing(
        self, tmp_path, payload, config
    ):
        ledger = BroadcastLedger(tmp_path)
        ledger.append_commitment(payload, committed_at_utc=GENERATED)
        ledger.append_not_published(
            fixture_id="mt_b", comp_id="comp_3039", kickoff_unix=KICKOFF,
            reason="no history", scope_version_hash=config.scope_version_hash,
        )
        rep = ledger.coverage_report(
            scope_version_hash=config.scope_version_hash,
            expected_fixture_ids=[payload.fixture_id, "mt_b", "mt_vanished"],
        )
        assert rep.missing_fixture_ids == ("mt_vanished",)
        assert not rep.is_complete
        assert len(rep.committed_fixture_ids) == 1
        assert len(rep.not_published_fixture_ids) == 1
        assert rep.not_published_reasons[0][1] == "no history"

    def test_a_committed_but_undelivered_forecast_is_not_complete(
        self, tmp_path, payload, config
    ):
        ledger = BroadcastLedger(tmp_path)
        ledger.append_commitment(payload, committed_at_utc=GENERATED)
        rep = ledger.coverage_report(
            scope_version_hash=config.scope_version_hash,
            expected_fixture_ids=[payload.fixture_id],
        )
        assert rep.undelivered_commitment_hashes == (payload.commitment_hash(),)
        assert not rep.is_complete


# ── the forecast layer and the price layer stay separate ───────────────────
class TestPriceLayerSeparation:
    def test_forecast_builder_has_no_price_parameter(self):
        params = list(inspect.signature(P.build_forecast_payload).parameters)
        assert not [p for p in params
                    if re.search(r"price|odds|book|market_price", p)]

    def test_layers_do_not_import_each_other(self):
        """Checked against import STATEMENTS, not prose.

        Both modules discuss the separation in their docstrings, and price_panel has a
        ``raw_payload_hash`` field, so a substring search would false-positive. What
        matters is that neither module actually imports the other.
        """
        base = REPO / "src" / "research" / "prediction_engine" / "broadcast"

        def imports(path: Path) -> list[str]:
            tree = ast.parse(path.read_text())
            names: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names += [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names.append(node.module or "")
                    names += [f"{node.module or ''}.{a.name}" for a in node.names]
            return names

        payload_imports = imports(base / "payload.py")
        panel_imports = imports(base / "price_panel.py")
        assert not [n for n in payload_imports if "price_panel" in n], payload_imports
        assert not [n for n in panel_imports if "payload" in n], panel_imports

    def test_no_price_field_reaches_the_payload(self, payload):
        blob = json.dumps(payload.canonical_dict()).lower()
        for key in ("odds", "price", "bookmaker", "bet365", "betfair"):
            assert key not in blob

    def test_price_capture_labels_are_honest(self, tmp_path):
        observed = datetime(2026, 9, 5, 3, 30, tzinfo=timezone.utc)
        rows = PP.build_price_records(
            fixture_id="mt_test_0001", kickoff_unix=KICKOFF,
            quotes=[
                PP.PriceQuote("corners", 9.5, "bet365", "over 9.5 corners", 1.90),
                PP.PriceQuote("corners", 9.5, "bet365", "under 9.5 corners", 1.95),
                PP.PriceQuote("corners", 9.5, "bet365", "bad", 0.0),
            ],
            observed_at=observed, source="test", horizon_hours=8,
        )
        assert len(rows) == 2, "a non-positive price is dropped, never fabricated"
        for r in rows:
            assert r["price_type"] == "SNAPSHOT", "a horizon snapshot is not a close"
            assert r["timestamp_semantics"] == "RETRIEVAL_TIME"
            assert r["provider_source_time"] is None
            assert r["capture_context"] == "FORECAST_HORIZON"
            assert r["retrieved_at_utc"] == observed.isoformat()

    def test_price_capture_is_idempotent(self, tmp_path):
        store = PP.PriceCaptureStore(tmp_path)
        rows = PP.build_price_records(
            fixture_id="mt_test_0001", kickoff_unix=KICKOFF,
            quotes=[PP.PriceQuote("corners", 9.5, "bet365", "over", 1.9)],
            observed_at=datetime(2026, 9, 5, 3, 30, tzinfo=timezone.utc),
            source="test", horizon_hours=8,
        )
        assert store.append(rows) == 1
        assert store.append(rows) == 0

    def test_price_capture_requires_timezone_aware_observation(self):
        with pytest.raises(ValueError):
            PP.build_price_records(
                fixture_id="x", kickoff_unix=KICKOFF, quotes=[],
                observed_at=datetime(2026, 9, 5, 3, 30), source="test",
            )


# ── the scope change gate is fail-closed ───────────────────────────────────
class TestScopeChangeGate:
    def test_unrecorded_scope_version_refuses_to_load(self, tmp_path):
        cfg = tmp_path / "scope.json"
        log = tmp_path / "changes.jsonl"
        cfg.write_text(json.dumps(SCOPE_RAW))
        with pytest.raises(SC.ScopeChangeUnrecorded):
            SC.load_scope_config(cfg, changelog_path=log)

    def test_a_change_needs_a_reason_and_a_timestamp(self, tmp_path):
        cfg = tmp_path / "scope.json"
        log = tmp_path / "changes.jsonl"
        cfg.write_text(json.dumps(SCOPE_RAW))
        cand = SC.load_scope_config(cfg, changelog_path=log,
                                    require_recorded_change=False)
        with pytest.raises(SC.ScopeConfigError):
            SC.record_scope_change(cand, "   ", changelog_path=log)
        rec = SC.record_scope_change(cand, "initial scope", changelog_path=log,
                                     now_iso="2026-09-05T03:55:00+00:00")
        assert rec["reason"] == "initial scope"
        assert rec["changed_at_utc"] == "2026-09-05T03:55:00+00:00"
        assert SC.load_scope_config(
            cfg, changelog_path=log).scope_version_hash == cand.scope_version_hash

    def test_a_version_is_recorded_exactly_once(self, tmp_path):
        cfg = tmp_path / "scope.json"
        log = tmp_path / "changes.jsonl"
        cfg.write_text(json.dumps(SCOPE_RAW))
        cand = SC.load_scope_config(cfg, changelog_path=log,
                                    require_recorded_change=False)
        SC.record_scope_change(cand, "first", changelog_path=log)
        with pytest.raises(SC.ScopeConfigError):
            SC.record_scope_change(cand, "again", changelog_path=log)

    def test_adding_a_market_takes_effect_only_after_it_is_logged(self, tmp_path):
        cfg = tmp_path / "scope.json"
        log = tmp_path / "changes.jsonl"
        cfg.write_text(json.dumps(SCOPE_RAW))
        cand = SC.load_scope_config(cfg, changelog_path=log,
                                    require_recorded_change=False)
        SC.record_scope_change(cand, "initial", changelog_path=log)

        widened = dict(SCOPE_RAW)
        widened["markets"] = SCOPE_RAW["markets"] + [
            {"market": "corners", "line": 10.5,
             "over_label": "over 10.5 corners", "under_label": "under 10.5 corners"}
        ]
        cfg.write_text(json.dumps(widened))
        with pytest.raises(SC.ScopeChangeUnrecorded):
            SC.load_scope_config(cfg, changelog_path=log)
        # The superseded version remains in the append-only log.
        assert [r["new_scope_version_hash"]
                for r in SC.read_scope_changes(log)] == [cand.scope_version_hash]

    @pytest.mark.parametrize("mutate,label", [
        (lambda c: {**c, "config_contract": "other/v2"}, "wrong contract"),
        (lambda c: {**c, "line_selection_rule": {"rule": "BEST_AVAILABLE_LINE"}},
         "per-fixture line rule"),
        (lambda c: {**c, "quiet_hours_utc": {"start_hour": 1, "end_hour": 6,
                                             "policy": "CANCEL"}},
         "quiet hours that cancel"),
        (lambda c: {**c, "markets": [{"market": "goals", "line": 2.5,
                                      "over_label": "over 2.5 goals",
                                      "under_label": ""}]},
         "market missing a side label"),
        (lambda c: {**c, "markets": c["markets"] + [c["markets"][0]]},
         "duplicate market cell"),
        (lambda c: {**c, "leagues": []}, "empty leagues"),
        (lambda c: {**c, "horizon_hours_before_kickoff": 0}, "zero horizon"),
        (lambda c: {**c, "leagues": c["leagues"] + [c["leagues"][0]]},
         "duplicate league"),
    ])
    def test_malformed_scope_is_refused_not_degraded(self, mutate, label):
        with pytest.raises(SC.ScopeConfigError):
            SC.parse_scope_config(mutate(SCOPE_RAW))

    def test_live_scope_config_parses_and_is_recorded(self):
        """The scope actually in force must be valid and change-logged."""
        cfg = SC.load_scope_config()  # fail-closed by default
        assert cfg.line_selection_rule == SC.FIXED_DECLARED_LINE
        assert cfg.quiet_hours_policy == SC.DELAY_NEVER_CANCEL
        assert cfg.markets and cfg.leagues
        for spec in cfg.markets:
            assert spec.over_label and spec.under_label


# ── the deprecated EV / stake path must stay unreachable ───────────────────
class TestDeprecatedEvPathUnreachable:
    TARGETS = [
        "src/research/prediction_engine/broadcast",
        "scripts/forecast_broadcast.py",
    ]

    def test_no_import_or_call_of_the_deprecated_classes(self):
        pattern = (
            r"^\s*(from|import)\s.*(crypto_signal|risk_unit|kelly|ev_calc)"
            r"|\b(CryptoSignalExporter|RiskUnitCalculator|KellyCalculator"
            r"|EVCalculator|devig)\s*\("
        )
        res = subprocess.run(
            ["grep", "-rn", "-E", pattern,
             *[str(REPO / t) for t in self.TARGETS], "--include=*.py"],
            capture_output=True, text=True,
        )
        assert not res.stdout.strip(), (
            f"deprecated EV/stake path is reachable:\n{res.stdout}"
        )

    def test_price_capture_happens_after_the_commitment_is_recorded(self):
        src = (REPO / "scripts" / "forecast_broadcast.py").read_text()
        body = src[src.index("\ndef run("):src.index("\ndef coverage(")]
        order = [body.index(tok) for tok in (
            "commitment = payload.commitment_hash()",
            "ledger.append_commitment(payload)",
            "render_checked_message(payload, config)",
            "deliverer.deliver(",
            "capture_prices_for_fixture(",
        )]
        assert order == sorted(order), (
            "run() must hash -> record -> gate -> send -> capture price"
        )
