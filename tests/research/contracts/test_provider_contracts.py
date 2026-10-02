"""Tests for provider-scoped capability contracts."""

from src.research.contracts.provider import (
    SemanticStatus,
    THESTATSAPI_CAPABILITIES_V1,
)
from src.research.data_source import ResearchMatch


def _match(**overrides) -> ResearchMatch:
    values = dict(
        match_id=1,
        date_unix=1_700_000_000,
        league_id=3039,
        season="sn_1",
        home_team="Alpha",
        away_team="Beta",
        source_provider="THESTATSAPI",
        source_match_ref="mt_1",
        competition_ref="comp_3039",
        season_ref="sn_1",
        home_team_ref="tm_1",
        away_team_ref="tm_2",
        home_team_id=1,
        away_team_id=2,
        home_goals=0,
        away_goals=0,
        corners_home=0,
        corners_away=3,
        shots_home=10,
        shots_away=None,
    )
    values.update(overrides)
    return ResearchMatch(**values)


def test_zero_is_counted_as_available_not_missing() -> None:
    audit = THESTATSAPI_CAPABILITIES_V1.audit([_match()])
    by_field = audit.by_field()
    assert by_field["home_goals"].available == 1
    assert by_field["corners_home"].available == 1
    assert by_field["shots_away"].missing == 1


def test_unverified_semantics_are_not_promoted_to_default_history() -> None:
    assert (
        THESTATSAPI_CAPABILITIES_V1.contract("npxg_home").semantic_status
        == SemanticStatus.NEEDS_AUDIT
    )
    assert "npxg_home" not in set(
        THESTATSAPI_CAPABILITIES_V1.eligible_historical_fields()
    )


def test_core_history_fields_are_explicitly_eligible() -> None:
    eligible = set(THESTATSAPI_CAPABILITIES_V1.eligible_historical_fields())
    assert {
        "home_goals",
        "away_goals",
        "corners_home",
        "corners_away",
        "shots_home",
        "shots_away",
        "shots_on_target_home",
        "shots_on_target_away",
        "yellow_cards_home",
        "yellow_cards_away",
        "home_xg",
        "away_xg",
    } <= eligible


def test_registry_is_pinned_to_verified_provider_document() -> None:
    assert THESTATSAPI_CAPABILITIES_V1.contract_source_url.endswith("/llms.txt")
    assert len(THESTATSAPI_CAPABILITIES_V1.contract_source_sha256) == 64
    assert THESTATSAPI_CAPABILITIES_V1.contract_verified_on == "2026-10-01"
