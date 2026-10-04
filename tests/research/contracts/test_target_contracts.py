"""Tests for QFE V2 target and settlement contracts."""

from src.research.contracts.target import (
    TARGET_REGISTRY_V1,
    ProviderMarketStatus,
    SettlementOutcome,
    TargetStatus,
    binary_event_outcome,
    is_binary_scoring_line,
    settle_count_market,
)
from src.research.data_source import ResearchMatch
from src.research.forward.odds import OddsSelection


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
        home_goals=2,
        away_goals=1,
        total_goals=3,
        corners_home=6,
        corners_away=4,
        total_corners=10,
        yellow_cards_home=2,
        yellow_cards_away=1,
        total_cards=3,
    )
    values.update(overrides)
    return ResearchMatch(**values)


def test_goals_and_corners_have_model_contracts() -> None:
    ids = set(TARGET_REGISTRY_V1.model_eligible_ids())
    assert {
        "goals_home_regulation",
        "goals_away_regulation",
        "goals_total_regulation",
        "corners_home_regulation",
        "corners_away_regulation",
        "corners_total_regulation",
    } <= ids


def test_goals_are_market_comparison_eligible_but_corners_fail_closed() -> None:
    comparison_ids = set(TARGET_REGISTRY_V1.market_comparison_eligible_ids())
    assert {
        "goals_home_regulation",
        "goals_away_regulation",
        "goals_total_regulation",
    } <= comparison_ids
    assert {
        "corners_home_regulation",
        "corners_away_regulation",
        "corners_total_regulation",
    }.isdisjoint(comparison_ids)

    goals = TARGET_REGISTRY_V1.contract("goals_home_regulation")
    assert goals.provider_market_available is True
    assert goals.market_comparison_eligible is True
    assert goals.provider_market_key == "team_total_goals"

    corners = TARGET_REGISTRY_V1.contract("corners_away_regulation")
    assert corners.model_eligible is True
    assert corners.provider_market_status == ProviderMarketStatus.UNVERIFIED
    assert corners.provider_market_available is False
    assert corners.market_comparison_eligible is False
    assert corners.provider_market_side_key == "away"


def test_bookings_remain_fail_closed() -> None:
    obs = TARGET_REGISTRY_V1.contract("bookings_total_regulation").observe(_match())
    assert obs.status == TargetStatus.CONTRACT_UNRESOLVED
    assert obs.count is None
    contract = TARGET_REGISTRY_V1.contract("bookings_total_regulation")
    # TheStatsAPI exposes total_cards, but provider market availability is not
    # the same thing as an accepted QFE model-vs-market comparison contract.
    assert contract.provider_market_status == ProviderMarketStatus.VERIFIED
    assert contract.provider_market_available is True
    assert contract.provider_market_mapped is True  # compatibility alias
    assert contract.model_eligible is False
    assert contract.market_comparison_eligible is False
    assert "bookings_total_regulation" not in set(
        TARGET_REGISTRY_V1.market_comparison_eligible_ids()
    )


def test_extra_time_metadata_blocks_regulation_targets() -> None:
    match = _match(extra_time_home_goals=1, extra_time_away_goals=0)
    for target_id in (
        "goals_total_regulation",
        "corners_total_regulation",
    ):
        obs = TARGET_REGISTRY_V1.contract(target_id).observe(match)
        assert obs.status == TargetStatus.EXTRA_TIME_UNSAFE
        assert obs.count is None


def test_missing_required_target_is_explicit() -> None:
    obs = TARGET_REGISTRY_V1.contract("corners_total_regulation").observe(
        _match(corners_home=None, total_corners=None)
    )
    assert obs.status == TargetStatus.SOURCE_MISSING


def test_half_line_is_binary() -> None:
    assert is_binary_scoring_line(2.5)
    assert not is_binary_scoring_line(2.0)
    assert not is_binary_scoring_line(2.25)


def test_integer_line_push_is_preserved() -> None:
    assert (
        settle_count_market(2, 2.0, OddsSelection.OVER)
        == SettlementOutcome.PUSH
    )


def test_quarter_line_half_loss_and_half_win() -> None:
    assert (
        settle_count_market(2, 2.25, OddsSelection.OVER)
        == SettlementOutcome.HALF_LOSS
    )
    assert (
        settle_count_market(3, 2.75, OddsSelection.OVER)
        == SettlementOutcome.HALF_WIN
    )
    assert (
        settle_count_market(2, 2.25, OddsSelection.UNDER)
        == SettlementOutcome.HALF_WIN
    )


def test_binary_event_rejects_non_binary_line() -> None:
    try:
        binary_event_outcome(2, 2.0, OddsSelection.UNDER)
    except ValueError as exc:
        assert "half-line" in str(exc)
    else:
        raise AssertionError("integer line must not be coerced into Bernoulli label")


def test_binary_event_half_line() -> None:
    assert binary_event_outcome(3, 2.5, OddsSelection.OVER) is True
    assert binary_event_outcome(2, 2.5, OddsSelection.OVER) is False
