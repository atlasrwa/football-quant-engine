"""Bookmaker-specific settlement compatibility for QFE V2.

Provider market availability and bookmaker settlement compatibility are separate
contracts. TheStatsAPI can expose a market even when QFE cannot yet prove that
its historical realized count is settled identically by a given bookmaker.

This registry therefore answers a narrow question:

    May target T be compared to bookmaker B's market using QFE's current
    historical target definition?

A VERIFIED result is required before commercial market-relative evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.research.contracts.target import TargetContract, TargetRegistry


class Bookmaker(str, Enum):
    BET365 = "bet365"
    PINNACLE = "pinnacle"


class SettlementCompatibility(str, Enum):
    VERIFIED = "VERIFIED"
    PERIOD_VERIFIED_COUNT_SEMANTICS_PENDING = (
        "PERIOD_VERIFIED_COUNT_SEMANTICS_PENDING"
    )
    BLOCKED_SOURCE_SEMANTICS = "BLOCKED_SOURCE_SEMANTICS"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True, slots=True)
class BookmakerTargetSettlementContract:
    bookmaker: Bookmaker
    target_id: str
    captured_market_key: str
    status: SettlementCompatibility
    settlement_period: str
    source_urls: tuple[str, ...]
    verified_on: str
    rule_summary: str
    unresolved_reason: str = ""

    @property
    def market_comparison_eligible(self) -> bool:
        return self.status == SettlementCompatibility.VERIFIED


@dataclass(frozen=True, slots=True)
class SettlementEligibility:
    bookmaker: str
    target_id: str
    status: SettlementCompatibility
    eligible: bool
    reason: str
    contract: Optional[BookmakerTargetSettlementContract]


@dataclass(frozen=True, slots=True)
class BookmakerSettlementRegistry:
    version: str
    contracts: tuple[BookmakerTargetSettlementContract, ...]

    def __post_init__(self) -> None:
        keys = [(c.bookmaker.value, c.target_id) for c in self.contracts]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate bookmaker/target settlement contract")

    @staticmethod
    def normalize_bookmaker(bookmaker: str | Bookmaker) -> str:
        if isinstance(bookmaker, Bookmaker):
            return bookmaker.value
        return str(bookmaker).strip().lower().replace(" ", "-")

    def contract(
        self,
        bookmaker: str | Bookmaker,
        target_id: str,
    ) -> Optional[BookmakerTargetSettlementContract]:
        slug = self.normalize_bookmaker(bookmaker)
        for contract in self.contracts:
            if (
                contract.bookmaker.value == slug
                and contract.target_id == target_id
            ):
                return contract
        return None

    def eligibility(
        self,
        *,
        bookmaker: str | Bookmaker,
        target: TargetContract,
    ) -> SettlementEligibility:
        slug = self.normalize_bookmaker(bookmaker)

        contract = self.contract(slug, target.target_id)
        if not target.model_eligible:
            status = (
                contract.status
                if contract is not None
                else SettlementCompatibility.BLOCKED_SOURCE_SEMANTICS
            )
            return SettlementEligibility(
                bookmaker=slug,
                target_id=target.target_id,
                status=status,
                eligible=False,
                reason=(
                    contract.unresolved_reason
                    if contract is not None and contract.unresolved_reason
                    else "QFE target source semantics are not accepted for modeling."
                ),
                contract=contract,
            )

        if not target.provider_market_mapped:
            return SettlementEligibility(
                bookmaker=slug,
                target_id=target.target_id,
                status=SettlementCompatibility.UNVERIFIED,
                eligible=False,
                reason="Target has no verified provider market mapping.",
                contract=contract,
            )

        if contract is None:
            return SettlementEligibility(
                bookmaker=slug,
                target_id=target.target_id,
                status=SettlementCompatibility.UNVERIFIED,
                eligible=False,
                reason="No bookmaker-specific settlement contract is registered.",
                contract=None,
            )

        if contract.captured_market_key != target.captured_market_key:
            return SettlementEligibility(
                bookmaker=slug,
                target_id=target.target_id,
                status=SettlementCompatibility.UNVERIFIED,
                eligible=False,
                reason=(
                    "Bookmaker contract market key does not match provider "
                    "target-market mapping."
                ),
                contract=contract,
            )

        reason = (
            "Settlement semantics verified for current QFE target definition."
            if contract.market_comparison_eligible
            else contract.unresolved_reason
            or "Settlement compatibility has not been fully verified."
        )
        return SettlementEligibility(
            bookmaker=slug,
            target_id=target.target_id,
            status=contract.status,
            eligible=contract.market_comparison_eligible,
            reason=reason,
            contract=contract,
        )

    def eligible_target_ids(
        self,
        *,
        bookmaker: str | Bookmaker,
        target_registry: TargetRegistry,
    ) -> tuple[str, ...]:
        return tuple(
            target.target_id
            for target in target_registry.contracts
            if self.eligibility(bookmaker=bookmaker, target=target).eligible
        )


BET365_GENERAL_90_URL = (
    "https://help.bet365.com/s/en-ca/sportsrules/soccer/result-event-half-time"
)
BET365_GOALS_URL = (
    "https://help.bet365.com/s/en-us/sportsrules/soccer/goalscoring-markets"
)
BET365_TEAM_GOALS_URL = (
    "https://help.bet365.com/s/en-us/sportsrules/soccer/team-markets"
)
BET365_CORNERS_URL = (
    "https://help.bet365.com/s/en-ca/sportsrules/soccer/corner-markets"
)
BET365_CARDS_URL = (
    "https://help.bet365.com/s/en-us/sportsrules/soccer/card-markets"
)
PINNACLE_RULES_URL = "https://www.pinnacle.com/en/future/betting-rules/"

_VERIFIED_ON = "2026-10-01"
_PERIOD = "SCHEDULED_90_MINUTES_PLUS_STOPPAGE_EXCLUDES_EXTRA_TIME_SHOOTOUT"


def _contract(
    bookmaker: Bookmaker,
    target_id: str,
    captured_market_key: str,
    status: SettlementCompatibility,
    source_urls: tuple[str, ...],
    rule_summary: str,
    unresolved_reason: str = "",
) -> BookmakerTargetSettlementContract:
    return BookmakerTargetSettlementContract(
        bookmaker=bookmaker,
        target_id=target_id,
        captured_market_key=captured_market_key,
        status=status,
        settlement_period=_PERIOD,
        source_urls=source_urls,
        verified_on=_VERIFIED_ON,
        rule_summary=rule_summary,
        unresolved_reason=unresolved_reason,
    )


_GOAL_BINDINGS = (
    ("goals_home_regulation", "team_total_goals:home"),
    ("goals_away_regulation", "team_total_goals:away"),
    ("goals_total_regulation", "total_goals"),
)
_CORNER_BINDINGS = (
    ("corners_home_regulation", "team_corners:home"),
    ("corners_away_regulation", "team_corners:away"),
    ("corners_total_regulation", "match_corners"),
)
_BOOKING_BINDINGS = (
    ("bookings_home_regulation", "total_cards:home"),
    ("bookings_away_regulation", "total_cards:away"),
    ("bookings_total_regulation", "total_cards"),
)


BOOKMAKER_SETTLEMENT_REGISTRY_V1 = BookmakerSettlementRegistry(
    version="qfe-bookmaker-settlement-v1",
    contracts=(
        # Bet365 goals: general 90-minute match rule plus explicit team-goals
        # rule for side markets.
        *tuple(
            _contract(
                Bookmaker.BET365,
                target_id,
                market_key,
                SettlementCompatibility.VERIFIED,
                (
                    BET365_GENERAL_90_URL,
                    BET365_TEAM_GOALS_URL
                    if ":home" in market_key or ":away" in market_key
                    else BET365_GOALS_URL,
                ),
                (
                    "Goals settled on scheduled 90 minutes; team-goals rule "
                    "explicitly excludes extra time and penalties."
                ),
            )
            for target_id, market_key in _GOAL_BINDINGS
        ),
        # Bet365 corners: 90-minute period is verified, but QFE has not yet
        # proven that provider 'corner_kicks' uses the bookmaker's exact
        # taken-vs-awarded convention on every source match.
        *tuple(
            _contract(
                Bookmaker.BET365,
                target_id,
                market_key,
                SettlementCompatibility.PERIOD_VERIFIED_COUNT_SEMANTICS_PENDING,
                (BET365_GENERAL_90_URL, BET365_CORNERS_URL),
                (
                    "Corners are 90-minute markets and Bet365 counts corners "
                    "taken rather than merely awarded."
                ),
                (
                    "TheStatsAPI corner_kicks must be empirically/provider-"
                    "semantically reconciled to Bet365's corners-taken rule."
                ),
            )
            for target_id, market_key in _CORNER_BINDINGS
        ),
        # Pinnacle's default soccer rule is scheduled 90 minutes plus stoppage,
        # excluding ET/shootouts. This is enough for goals after QFE's ET guard.
        *tuple(
            _contract(
                Bookmaker.PINNACLE,
                target_id,
                market_key,
                SettlementCompatibility.VERIFIED,
                (PINNACLE_RULES_URL,),
                (
                    "Pinnacle soccer match markets default to scheduled "
                    "90 minutes plus stoppage, excluding extra time/shootouts."
                ),
            )
            for target_id, market_key in _GOAL_BINDINGS
        ),
        # For corners the period is covered by Pinnacle's generic soccer rule,
        # but provider-vs-bookmaker corner event semantics still need proof.
        *tuple(
            _contract(
                Bookmaker.PINNACLE,
                target_id,
                market_key,
                SettlementCompatibility.PERIOD_VERIFIED_COUNT_SEMANTICS_PENDING,
                (PINNACLE_RULES_URL,),
                "Scheduled 90-minute period is verified for match markets.",
                (
                    "Exact provider corner_kicks settlement equivalence is not "
                    "yet proven."
                ),
            )
            for target_id, market_key in _CORNER_BINDINGS
        ),
        # Bookmaker card rules are known, but aggregate provider yellow/red
        # counts cannot reconstruct second-yellow and participant eligibility.
        *tuple(
            _contract(
                Bookmaker.BET365,
                target_id,
                market_key,
                SettlementCompatibility.BLOCKED_SOURCE_SEMANTICS,
                (BET365_CARDS_URL,),
                (
                    "Yellow=1, red=2; second yellows ignored; non-participants "
                    "excluded; scheduled 90 minutes."
                ),
                (
                    "Aggregate provider card counts cannot reconstruct second "
                    "yellow or participant/on-pitch eligibility."
                ),
            )
            for target_id, market_key in _BOOKING_BINDINGS
        ),
        *tuple(
            _contract(
                Bookmaker.PINNACLE,
                target_id,
                market_key,
                SettlementCompatibility.BLOCKED_SOURCE_SEMANTICS,
                (PINNACLE_RULES_URL,),
                (
                    "Yellow=1, red=2; second yellows ignored; non-competitors "
                    "excluded; post-regulation cards excluded."
                ),
                (
                    "Aggregate provider card counts cannot reconstruct second "
                    "yellow or competitor eligibility."
                ),
            )
            for target_id, market_key in _BOOKING_BINDINGS
        ),
    ),
)
