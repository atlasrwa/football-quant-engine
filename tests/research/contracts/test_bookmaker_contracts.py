"""Tests for bookmaker-specific settlement compatibility."""

from src.research.contracts.bookmaker import (
    BOOKMAKER_SETTLEMENT_REGISTRY_V1,
    Bookmaker,
    SettlementCompatibility,
)
from src.research.contracts.target import TARGET_REGISTRY_V1


def _target(target_id: str):
    return TARGET_REGISTRY_V1.contract(target_id)


def test_bet365_goal_targets_are_commercially_comparable() -> None:
    for target_id in (
        "goals_home_regulation",
        "goals_away_regulation",
        "goals_total_regulation",
    ):
        result = BOOKMAKER_SETTLEMENT_REGISTRY_V1.eligibility(
            bookmaker=Bookmaker.BET365,
            target=_target(target_id),
        )
        assert result.eligible is True
        assert result.status == SettlementCompatibility.VERIFIED


def test_pinnacle_goal_targets_are_commercially_comparable() -> None:
    assert set(
        BOOKMAKER_SETTLEMENT_REGISTRY_V1.eligible_target_ids(
            bookmaker="pinnacle",
            target_registry=TARGET_REGISTRY_V1,
        )
    ) == {
        "goals_home_regulation",
        "goals_away_regulation",
        "goals_total_regulation",
    }


def test_corners_are_not_commercially_promoted_before_count_semantics_audit() -> None:
    for book in ("bet365", "pinnacle"):
        result = BOOKMAKER_SETTLEMENT_REGISTRY_V1.eligibility(
            bookmaker=book,
            target=_target("corners_total_regulation"),
        )
        assert result.eligible is False
        assert (
            result.status
            == SettlementCompatibility.PERIOD_VERIFIED_COUNT_SEMANTICS_PENDING
        )
        assert "corner" in result.reason.lower()


def test_bookings_are_blocked_by_source_semantics_even_when_rules_are_known() -> None:
    for book in ("bet365", "pinnacle"):
        result = BOOKMAKER_SETTLEMENT_REGISTRY_V1.eligibility(
            bookmaker=book,
            target=_target("bookings_total_regulation"),
        )
        assert result.eligible is False
        assert result.status == SettlementCompatibility.BLOCKED_SOURCE_SEMANTICS
        assert "second" in result.reason.lower()


def test_unregistered_bookmaker_fails_closed() -> None:
    result = BOOKMAKER_SETTLEMENT_REGISTRY_V1.eligibility(
        bookmaker="unknown-book",
        target=_target("goals_total_regulation"),
    )
    assert result.eligible is False
    assert result.status == SettlementCompatibility.UNVERIFIED


def test_bookmaker_contract_market_key_must_equal_capture_contract() -> None:
    target = _target("goals_home_regulation")
    contract = BOOKMAKER_SETTLEMENT_REGISTRY_V1.contract(
        "bet365",
        target.target_id,
    )
    assert contract is not None
    assert contract.captured_market_key == target.captured_market_key
    assert contract.captured_market_key == "team_total_goals:home"
