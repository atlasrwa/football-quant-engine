"""The research forecast pass: expanded coverage, fail-closed stages, no delivery.

This is the layer that makes non-Pilot-C prospective shadows possible, because a
shadow candidate requires a committed forecast. Proves:

* a non-Pilot-C competition enters the forecast commitment stage;
* market abstention is per market, not per league;
* the research scope declaration reuses the consumer market cells verbatim (so no
  line, coefficient, or calibration decision is made here);
* the pass has no delivery capability at all.
"""

from __future__ import annotations

import inspect
import json

import pytest

from src.research.prediction_engine.broadcast.scope_config import MarketSpec
from src.research.prediction_engine.research_forecast import (
    DEFAULT_RESEARCH_HORIZON_HOURS,
    ResearchForecastResult,
    build_research_scope_config,
    build_research_scope_declaration,
    market_abstentions,
    record_research_scope_version,
    research_due_fixtures,
)
from src.research.scope.market_scope import build_research_scope

from tests.research.scope.conftest import (
    ALL_READY,
    coverage_row,
    league_entry,
    write_coverage_matrix,
    write_registry,
)

#: The champion market cells, as declared in consumer scope.
MARKET_SPECS = (
    MarketSpec(market="goals", line=2.5, over_label="over 2.5 goals",
               under_label="under 2.5 goals"),
    MarketSpec(market="corners", line=9.5, over_label="over 9.5 corners",
               under_label="under 9.5 corners"),
    MarketSpec(market="cards", line=4.5, over_label="over 4.5 cards",
               under_label="under 4.5 cards"),
    MarketSpec(market="btts", line=None, over_label="both teams to score - yes",
               under_label="both teams to score - no"),
)

NEW_COMP = "comp_5840"      # Germany Bundesliga — not Pilot C
KICKOFF = 1_789_600_000.0


def _scope(tmp_path, *, leagues, rows):
    registry = write_registry(tmp_path / "registry.json", leagues)
    matrix = write_coverage_matrix(tmp_path / "matrix.json", rows)
    return build_research_scope(registry_path=registry, coverage_matrix_path=matrix)


def _full_scope(tmp_path):
    return _scope(
        tmp_path,
        leagues=[league_entry(name="Germany Bundesliga", comp_ids=[NEW_COMP])],
        rows=[coverage_row(comp_id=NEW_COMP, canonical_name="Germany Bundesliga",
                           market_eligibility=ALL_READY)],
    )


# ── scope declaration ────────────────────────────────────────────────────────
def test_research_scope_includes_a_non_pilot_c_competition(tmp_path):
    config = build_research_scope_config(
        scope=_full_scope(tmp_path), market_specs=MARKET_SPECS
    )
    assert config.is_in_scope(NEW_COMP)
    assert NEW_COMP in config.comp_ids


def test_research_scope_reuses_consumer_market_cells_verbatim(tmp_path):
    """No new line is ever chosen for research — the cells are copied."""
    config = build_research_scope_config(
        scope=_full_scope(tmp_path), market_specs=MARKET_SPECS
    )
    assert [(m.market, m.line) for m in config.markets] == [
        (m.market, m.line) for m in MARKET_SPECS
    ]
    assert config.line_selection_rule == "FIXED_DECLARED_LINE"
    assert config.confidence_label_rule is None


def test_research_scope_hash_is_deterministic_and_distinct_from_consumer(tmp_path):
    scope = _full_scope(tmp_path)
    first = build_research_scope_config(scope=scope, market_specs=MARKET_SPECS)
    second = build_research_scope_config(scope=scope, market_specs=MARKET_SPECS)
    assert first.scope_version_hash == second.scope_version_hash

    from src.research.prediction_engine.broadcast.scope_config import load_scope_config

    consumer = load_scope_config(require_recorded_change=False)
    assert first.scope_version_hash != consumer.scope_version_hash, (
        "the research scope must be a distinct declared scope, not a mutation of "
        "the consumer scope"
    )


def test_research_scope_declaration_refuses_an_empty_universe():
    with pytest.raises(ValueError, match="at least one competition"):
        build_research_scope_declaration(competitions=[], market_specs=MARKET_SPECS)


def test_research_scope_declaration_notes_state_the_boundary():
    declaration = build_research_scope_declaration(
        competitions=[(NEW_COMP, "Germany Bundesliga")], market_specs=MARKET_SPECS
    )
    notes = " ".join(declaration["notes"]).lower()
    assert "never delivered" in notes
    assert "pilot c membership is not an input" in notes
    assert "observability, not validation" in notes


def test_default_research_horizon_precedes_the_early_capture_vintage():
    """T-30h must sit before the EARLY (~T-24h) vintage so snapshots are joinable."""
    from src.research.prospective.vintages import ProspectiveVintage

    early_seconds = ProspectiveVintage.EARLY.offset_seconds
    assert DEFAULT_RESEARCH_HORIZON_HOURS * 3600 > early_seconds, (
        "the research commitment horizon must precede the EARLY capture vintage, or "
        "the EARLY snapshot would be older than the forecast and could not be joined"
    )
    # And it must precede every other vintage too, so all four are joinable.
    for vintage in ProspectiveVintage:
        assert DEFAULT_RESEARCH_HORIZON_HOURS * 3600 > vintage.offset_seconds


def test_scope_version_log_is_append_only_and_idempotent(tmp_path):
    scope = _full_scope(tmp_path)
    config = build_research_scope_config(scope=scope, market_specs=MARKET_SPECS)
    root = tmp_path / "research_forecast"

    first = record_research_scope_version(config, scope=scope, root=root)
    second = record_research_scope_version(config, scope=scope, root=root)

    assert first is not None
    assert second is None, "recording the same version twice must be a no-op"
    lines = (root / "scope_versions.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["scope_version_hash"] == config.scope_version_hash
    assert row["derivation"]["rule"] == "dual_provider_intersection"
    assert row["pilot_c_is_behavioral_input"] is False


# ── market-stage abstention (claim D at the forecast layer) ──────────────────
def test_unsupported_market_abstains_without_removing_the_league(tmp_path):
    scope = _scope(
        tmp_path,
        leagues=[league_entry(name="Germany Bundesliga", comp_ids=[NEW_COMP])],
        rows=[
            coverage_row(
                comp_id=NEW_COMP, canonical_name="Germany Bundesliga",
                market_eligibility={
                    "total_goals": "READY",
                    "match_corners": "READY",
                    "total_cards": "UNSUPPORTED",
                    "match_shots_on_target": "UNKNOWN",
                },
            )
        ],
    )
    config = build_research_scope_config(scope=scope, market_specs=MARKET_SPECS)
    assert config.is_in_scope(NEW_COMP), "league survives the unsupported market"

    abstain = market_abstentions(
        scope=scope, competition_id=NEW_COMP, market_specs=MARKET_SPECS
    )
    abstained = {market for market, _line in abstain}
    assert abstained == {"cards", "btts"}
    assert "goals" not in abstained and "corners" not in abstained
    # Each abstention states a reason; none is silent.
    assert all(reason for reason in abstain.values())
    assert "UNSUPPORTED" in abstain[("cards", 4.5)]
    assert "no captured odds counterpart" in abstain[("btts", None)]


def test_btts_always_abstains_because_it_can_never_be_joined(tmp_path):
    scope = _full_scope(tmp_path)
    abstain = market_abstentions(
        scope=scope, competition_id=NEW_COMP, market_specs=MARKET_SPECS
    )
    assert ("btts", None) in abstain


def test_competition_outside_scope_abstains_on_every_market(tmp_path):
    scope = _full_scope(tmp_path)
    abstain = market_abstentions(
        scope=scope, competition_id="comp_unknown", market_specs=MARKET_SPECS
    )
    assert len(abstain) == len(MARKET_SPECS)


# ── due selection ────────────────────────────────────────────────────────────
def _universe():
    return {
        "mt_in_scope": {"ts": KICKOFF, "comp": NEW_COMP, "home": "A", "away": "B"},
        "mt_out_of_scope": {"ts": KICKOFF, "comp": "comp_elsewhere",
                            "home": "C", "away": "D"},
        "mt_no_kickoff": {"comp": NEW_COMP, "home": "E", "away": "F"},
    }


def test_due_selection_covers_the_new_league_and_counts_every_exclusion(tmp_path):
    config = build_research_scope_config(
        scope=_full_scope(tmp_path), market_specs=MARKET_SPECS
    )
    due, counts = research_due_fixtures(
        _universe(),
        config=config,
        now_unix=KICKOFF - 10 * 3600.0,  # inside the T-30h horizon
        already_fired=frozenset(),
    )

    assert [f.fixture_id for f in due] == ["mt_in_scope"]
    assert counts["not_in_research_scope"] == 1
    assert counts["unusable_kickoff"] == 1
    assert counts["already_committed"] == 0
    # Every reason key is always present, so a zero-due tick is never ambiguous.
    assert set(counts) == {
        "not_in_research_scope", "already_committed", "unusable_kickoff",
        "before_horizon", "past_kickoff",
    }


def test_fixture_before_its_horizon_is_counted_not_dropped(tmp_path):
    config = build_research_scope_config(
        scope=_full_scope(tmp_path), market_specs=MARKET_SPECS
    )
    due, counts = research_due_fixtures(
        _universe(), config=config,
        now_unix=KICKOFF - 100 * 3600.0, already_fired=frozenset(),
    )
    assert due == []
    assert counts["before_horizon"] == 1


def test_fixture_past_kickoff_is_never_committed(tmp_path):
    """A forecast committed after kickoff is not a pre-kickoff forecast."""
    config = build_research_scope_config(
        scope=_full_scope(tmp_path), market_specs=MARKET_SPECS
    )
    due, counts = research_due_fixtures(
        _universe(), config=config,
        now_unix=KICKOFF + 3600.0, already_fired=frozenset(),
    )
    assert due == []
    assert counts["past_kickoff"] == 1


def test_already_committed_fixture_fires_only_once(tmp_path):
    config = build_research_scope_config(
        scope=_full_scope(tmp_path), market_specs=MARKET_SPECS
    )
    due, counts = research_due_fixtures(
        _universe(), config=config, now_unix=KICKOFF - 10 * 3600.0,
        already_fired=frozenset({"mt_in_scope"}),
    )
    assert due == []
    assert counts["already_committed"] == 1


# ── no delivery capability ───────────────────────────────────────────────────
def test_research_forecast_module_has_no_transport_or_delivery(tmp_path):
    """Structural proof that this pass cannot publish anything."""
    from src.research.prediction_engine import research_forecast

    source = inspect.getsource(research_forecast)
    for banned in (
        "TelegramTransport", "ForecastDeliverer", "PendingQueue",
        "append_delivery", "render_message", "sendMessage",
    ):
        assert banned not in source, (
            f"research_forecast references {banned}; the research pass must have no "
            "delivery capability"
        )


def test_runner_never_constructs_a_telegram_transport():
    import importlib.util

    spec = importlib.util.find_spec("scripts.research_forecast_commit")
    path = spec.origin if spec else "scripts/research_forecast_commit.py"
    source = open(path, encoding="utf-8").read() if spec else open(path).read()
    for banned in ("TelegramTransport(", "ForecastDeliverer(", "PendingQueue("):
        assert banned not in source


def test_result_reports_zero_delivery_explicitly():
    result = ResearchForecastResult()
    published = result.to_dict()["publication"]
    assert published["delivered"] == 0
    assert published["delivery_attempted"] is False
    assert "never delivered" in published["note"]


def test_result_separates_league_market_and_model_stage_exclusions():
    """The report must distinguish the stages, per requirement 13."""
    result = ResearchForecastResult()
    result.league_exclusion_reasons = {"THESTATSAPI_UNSUPPORTED": 1}
    result.fixture_exclusions = {"not_in_research_scope": 5}
    result.model_stage_exclusions = {"insufficient_history": 2}
    result.market_stage_abstentions = {"cards:comp_5840": 3}

    payload = result.to_dict()
    assert payload["league_universe"]["league_exclusion_reasons"]
    assert payload["fixtures"]["exclusions"]
    assert payload["commitments"]["model_stage_exclusions"]
    assert payload["commitments"]["market_stage_abstentions"]
