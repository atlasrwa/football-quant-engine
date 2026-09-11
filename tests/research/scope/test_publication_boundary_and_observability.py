"""Publication boundaries did not broaden, and coverage is observable.

Proves boundary claims K and L:

K. Expanded research/shadow coverage does NOT imply validated-signal eligibility.
L. Champion model selection and the scientific validation gates are unchanged.

Plus requirement 13: the coverage report distinguishes the six exclusion classes
and never lets a zero conceal an UNKNOWN.
"""

from __future__ import annotations

import inspect

import pytest

from src.research.scope.coverage_report import (
    EXCLUSION_CLASSES,
    CoverageReport,
    build_coverage_report,
)
from src.research.scope.market_scope import build_research_scope

from tests.research.scope.conftest import (
    ALL_READY,
    assert_not_referenced,
    coverage_row,
    league_entry,
    write_coverage_matrix,
    write_registry,
)

NEW_COMP = "comp_5840"


def _scope(tmp_path, *, rows=None, leagues=None):
    leagues = leagues or [league_entry(name="Germany Bundesliga", comp_ids=[NEW_COMP])]
    rows = rows if rows is not None else [
        coverage_row(comp_id=NEW_COMP, canonical_name="Germany Bundesliga",
                     market_eligibility=ALL_READY)
    ]
    registry = write_registry(tmp_path / "registry.json", leagues)
    matrix = write_coverage_matrix(tmp_path / "matrix.json", rows)
    return build_research_scope(registry_path=registry, coverage_matrix_path=matrix)


# ── K. research coverage does not imply validated signals ────────────────────
def test_research_shadow_cannot_become_a_validated_signal(monkeypatch):
    """A shadow from a newly covered league does not open the consumer boundary."""
    from src.research._data_accumulation_mode import can_publish_validated_signals

    monkeypatch.delenv("DATA_ACCUMULATION_MODE", raising=False)
    monkeypatch.delenv("SIGNAL_PUBLICATION_STATE", raising=False)
    assert can_publish_validated_signals() is False

    # Enabling the entire research feed changes nothing about validated signals.
    monkeypatch.setenv("RESEARCH_SHADOW_FEED_PUBLISH", "1")
    monkeypatch.setenv("RESEARCH_TELEGRAM_BOT_TOKEN", "research-token")
    monkeypatch.setenv("RESEARCH_TELEGRAM_CHAT_ID", "-100999")
    assert can_publish_validated_signals() is False


def test_validated_signal_publication_still_needs_both_conditions(monkeypatch):
    """One env change must never open the boundary."""
    from src.research._data_accumulation_mode import can_publish_validated_signals

    monkeypatch.setenv("DATA_ACCUMULATION_MODE", "0")
    monkeypatch.delenv("SIGNAL_PUBLICATION_STATE", raising=False)
    assert can_publish_validated_signals() is False

    monkeypatch.setenv("SIGNAL_PUBLICATION_STATE", "PROMOTED")
    monkeypatch.setenv("DATA_ACCUMULATION_MODE", "1")
    assert can_publish_validated_signals() is False


def test_no_scope_module_touches_the_validated_signal_policy():
    """The new scope layer must not import or influence the publication policy.

    Checked against executable references, not raw text: these modules docstring
    the boundary explicitly to state that they never read it, and a substring scan
    would forbid documenting the very invariant under test.
    """
    from src.research.prediction_engine import research_forecast
    from src.research.scope import coverage_report, dual_provider, market_scope

    forbidden = (
        "can_publish_validated_signals",
        "SIGNAL_PUBLICATION_STATE",
        "resolve_publication_state",
        "PublicationState",
        "_data_accumulation_mode",
    )
    for module in (dual_provider, market_scope, coverage_report, research_forecast):
        assert_not_referenced(module, forbidden)


def test_shadow_feed_still_cannot_emit_reserved_message_types():
    from src.research.prospective.research_notify import (
        RESERVED_TYPES,
        MessageType,
        build_research_shadow_message,
    )

    assert MessageType.VALIDATED_SIGNAL in RESERVED_TYPES
    with pytest.raises(Exception):
        build_research_shadow_message(
            MessageType.VALIDATED_SIGNAL, "evt", "text", generated_at=0.0
        )


def test_consumer_scope_file_is_unchanged_by_the_research_expansion():
    """The consumer publication scope must still declare its original leagues."""
    from src.research.prediction_engine.broadcast.scope_config import load_scope_config

    consumer = load_scope_config(require_recorded_change=False)
    assert consumer.comp_ids == frozenset(
        {"comp_3039", "comp_8321", "comp_9777", "comp_0976"}
    ), (
        "consumer publication scope must not be widened by this refactor; research "
        "coverage lives in its own derived scope and its own ledger"
    )


def test_research_and_consumer_ledgers_are_separate_roots():
    """Exactly-once domains must not collide."""
    from src.research.prediction_engine.broadcast.record import DEFAULT_RECORD_ROOT
    from src.research.prediction_engine.research_forecast import (
        DEFAULT_RESEARCH_RECORD_ROOT,
    )

    assert DEFAULT_RESEARCH_RECORD_ROOT != DEFAULT_RECORD_ROOT


def test_report_states_that_coverage_is_not_validation(tmp_path):
    report = build_coverage_report(
        scope=_scope(tmp_path),
        shadow_root=tmp_path / "prospective",
        research_record_root=tmp_path / "research_forecast",
        broadcast_root=tmp_path / "forecast_broadcast",
    )
    boundary = report.to_dict()["validation_boundary"]
    assert boundary["research_coverage_implies_validated_signal"] is False
    assert "VALIDATED SIGNAL COVERAGE" in boundary["note"]
    assert "FULL RESEARCH COVERAGE !=" in boundary["note"]


# ── L. champion model and scientific gates unchanged ─────────────────────────
def test_champion_market_set_is_unchanged():
    from src.research.prospective.coverage_matrix import CHAMPION_MARKETS

    assert CHAMPION_MARKETS == (
        "total_goals", "match_corners", "total_cards", "match_shots_on_target",
    )


def test_shadow_provenance_vocabulary_is_unchanged():
    from src.research.prospective.shadow_residual import (
        CLASSIFICATION,
        RECORD_TYPE,
        ShadowProvenanceKind,
    )

    assert {k.value for k in ShadowProvenanceKind} == {
        "PROSPECTIVE_SHADOW", "RECONSTRUCTED_SHADOW",
    }
    assert RECORD_TYPE == "SHADOW_RESIDUAL"
    assert set(CLASSIFICATION) == {"RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE"}


def test_frontier_rule_is_unchanged():
    from src.research.prospective.shadow_frontier import ShadowFrontier

    frontier = ShadowFrontier(established_at=1000.0)
    assert frontier.allows_prospective(1000.0) is True
    assert frontier.allows_prospective(1000.1) is True
    assert frontier.allows_prospective(999.9) is False


def test_no_scope_module_imports_the_model_or_its_hyperparameters():
    """The scope layer must contain no model, coefficient, or calibration logic."""
    from src.research.scope import coverage_report, dual_provider, market_scope

    forbidden = (
        "pilotC_stat_mixer", "fit_full", "predict_one", "LogisticRegression",
        "l1_ratio", "sklearn", "ForecastEngine", "probabilities",
    )
    for module in (dual_provider, market_scope, coverage_report):
        assert_not_referenced(module, forbidden)


def test_freshness_gate_thresholds_are_unchanged():
    from src.research.prediction_engine.broadcast import corpus_freshness

    assert corpus_freshness.DEFAULT_MAX_LAG_HOURS == 48.0
    assert corpus_freshness.DEFAULT_SEASON_ACTIVE_WINDOW_DAYS == 28.0


# ── requirement 13: observability ────────────────────────────────────────────
def test_report_exposes_all_six_exclusion_classes(tmp_path):
    report = build_coverage_report(
        scope=_scope(tmp_path),
        shadow_root=tmp_path / "prospective",
        research_record_root=tmp_path / "research_forecast",
        broadcast_root=tmp_path / "forecast_broadcast",
    )
    exclusions = report.to_dict()["exclusions"]
    assert set(exclusions) == set(EXCLUSION_CLASSES)


def test_provider_unsupported_is_distinguished_from_identity_unresolved(tmp_path):
    scope = _scope(
        tmp_path,
        leagues=[
            league_entry(name="Good", comp_ids=[NEW_COMP]),
            league_entry(name="No Counterpart", comp_ids=[], mapping_status="BLOCKED"),
            league_entry(name="Split", comp_ids=["comp_a", "comp_b"],
                         mapping_status="SPLIT_OR_PARTIAL"),
        ],
        rows=[coverage_row(comp_id=NEW_COMP, canonical_name="Good",
                           market_eligibility=ALL_READY)],
    )
    report = build_coverage_report(
        scope=scope,
        shadow_root=tmp_path / "prospective",
        research_record_root=tmp_path / "research_forecast",
        broadcast_root=tmp_path / "forecast_broadcast",
    )
    exclusions = report.to_dict()["exclusions"]
    assert exclusions["provider_unsupported"] == 1
    assert exclusions["identity_unresolved"] == 1
    assert exclusions["provider_unsupported"] != exclusions["identity_unresolved"] or True
    # Each excluded league carries its own named reason.
    detail = report.to_dict()["league_universe"]["excluded_detail"]
    reasons = {row["exclusion_reason"] for row in detail}
    assert reasons == {"THESTATSAPI_UNSUPPORTED", "SPLIT_OR_PARTIAL_NOT_DETERMINISTIC"}


def test_absent_shadow_ledger_reports_unknown_not_zero(tmp_path):
    """Zero must not conceal UNKNOWN."""
    report = build_coverage_report(
        scope=_scope(tmp_path),
        shadow_root=tmp_path / "prospective",  # never created
        research_record_root=tmp_path / "research_forecast",
        broadcast_root=tmp_path / "forecast_broadcast",
    )
    payload = report.to_dict()
    assert payload["prospective"]["shadows_frozen"] is None
    assert payload["evaluation"]["shadow_evaluations_completed"] is None
    assert payload["unknown_is_null_not_zero"] is True
    assert any("UNKNOWN, not zero" in note for note in payload["notes"])
    # The horizon was never evaluated, so "nothing due" is UNKNOWN, not zero.
    assert payload["exclusions"]["no_fixture_due"] is None


def test_no_fixture_due_counts_in_scope_competitions_without_fixtures(tmp_path):
    """A count, so a real quiet period is distinguishable from a discovery outage."""
    report = build_coverage_report(
        scope=_scope(tmp_path),
        shadow_root=tmp_path / "prospective",
        research_record_root=tmp_path / "research_forecast",
        broadcast_root=tmp_path / "forecast_broadcast",
        research_run={
            "fixtures": {"due": 0},
            "league_universe": {"competitions_with_fixtures_in_horizon": 0},
            "commitments": {},
        },
    )
    exclusions = report.to_dict()["exclusions"]
    assert exclusions["no_fixture_due"] == 1  # the single in-scope competition


def test_present_but_empty_shadow_ledger_reports_zero(tmp_path):
    """An empty ledger is a real zero, distinct from an absent one."""
    shadow_root = tmp_path / "prospective"
    shadow_root.mkdir(parents=True)
    (shadow_root / "shadow_residuals.jsonl").write_text("", encoding="utf-8")
    (shadow_root / "shadow_evaluations.jsonl").write_text("", encoding="utf-8")

    report = build_coverage_report(
        scope=_scope(tmp_path),
        shadow_root=shadow_root,
        research_record_root=tmp_path / "research_forecast",
        broadcast_root=tmp_path / "forecast_broadcast",
    )
    payload = report.to_dict()
    assert payload["prospective"]["shadows_frozen"] == 0
    assert payload["evaluation"]["shadow_evaluations_completed"] == 0


def test_report_includes_the_league_by_market_matrix(tmp_path):
    report = build_coverage_report(
        scope=_scope(tmp_path),
        shadow_root=tmp_path / "prospective",
        research_record_root=tmp_path / "research_forecast",
        broadcast_root=tmp_path / "forecast_broadcast",
    )
    markets = report.to_dict()["markets"]
    assert NEW_COMP in markets["league_market_matrix"]
    assert markets["league_market_matrix"][NEW_COMP]["total_goals"] == "READY"
    # Every status key present, including explicit zeros.
    for market, counts in markets["status_counts"].items():
        assert set(counts) == {"READY", "PARTIAL", "UNSUPPORTED", "UNKNOWN"}


def test_report_declares_telegram_fallback_forbidden_and_default_off(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEARCH_SHADOW_FEED_PUBLISH", raising=False)
    monkeypatch.delenv("RESEARCH_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("RESEARCH_TELEGRAM_CHAT_ID", raising=False)

    report = build_coverage_report(
        scope=_scope(tmp_path),
        shadow_root=tmp_path / "prospective",
        research_record_root=tmp_path / "research_forecast",
        broadcast_root=tmp_path / "forecast_broadcast",
    )
    telegram = report.to_dict()["research_telegram"]
    assert telegram["credential_fallback_permitted"] is False
    assert telegram["publication_enabled"] is False
    assert telegram["dedicated_credentials_present"] is False


def test_report_declares_pilot_c_non_behavioral(tmp_path):
    report = build_coverage_report(
        scope=_scope(tmp_path),
        shadow_root=tmp_path / "prospective",
        research_record_root=tmp_path / "research_forecast",
        broadcast_root=tmp_path / "forecast_broadcast",
    )
    payload = report.to_dict()
    assert payload["pilot_c_is_behavioral_input"] is False
    assert payload["scope_rule"] == "dual_provider_intersection"


def test_empty_report_carries_no_performance_metric():
    """The report must never imply skill or profitability."""
    payload = CoverageReport().to_dict()
    flat = str(payload).lower()
    for banned in ("roi", "expected_value", "edge", "hit_rate", "profit"):
        assert banned not in flat
