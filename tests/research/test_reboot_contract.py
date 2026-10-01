"""Hard architectural guards for the QFE V2 reboot."""

from dataclasses import fields

from src.research.data_source import ResearchMatch
from src.research.forward.odds import OddsSelection
from src.research.prospective.api_contract import OVER_UNDER_MARKET_KEYS
from src.research.prospective.vintages import (
    ProspectiveVintage,
    compute_cutoff,
    is_consultable,
)


def test_target_market_contract_is_goals_corners_bookings_only() -> None:
    assert OVER_UNDER_MARKET_KEYS == (
        "total_goals",
        "match_corners",
        "total_cards",
    )


def test_independent_match_schema_contains_no_bookmaker_prices() -> None:
    names = {f.name for f in fields(ResearchMatch)}
    assert not any(name.startswith("odds_") for name in names)
    assert not any(name.startswith("line_") for name in names)


def test_target_selection_layer_is_over_under_only() -> None:
    assert {item.value for item in OddsSelection} == {"OVER", "UNDER"}


def test_point_in_time_cutoff_rejects_future_observation() -> None:
    kickoff = 1_800_000_000.0
    cutoff = compute_cutoff("fixture-1", kickoff, ProspectiveVintage.EARLY)
    assert is_consultable(
        concept="team_strength",
        observed_at=cutoff.cutoff_ts,
        cutoff=cutoff,
    )
    assert not is_consultable(
        concept="team_strength",
        observed_at=cutoff.cutoff_ts + 1,
        cutoff=cutoff,
    )


def test_early_vintage_cannot_consult_confirmed_lineup() -> None:
    kickoff = 1_800_000_000.0
    early = compute_cutoff("fixture-1", kickoff, ProspectiveVintage.EARLY)
    assert not is_consultable(
        concept="confirmed_lineup",
        observed_at=early.cutoff_ts - 1,
        cutoff=early,
    )
