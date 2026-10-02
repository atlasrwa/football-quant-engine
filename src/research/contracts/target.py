"""Target and settlement contracts for QFE V2.

The contract layer separates three questions that are easy to conflate:

1. Can the provider supply a trustworthy realized count?
2. Is that count a valid modeling target for the registered period/side?
3. Does a sportsbook market use settlement semantics compatible with that count?

A target can be modelable while its market comparator is still unverified.
Bookings are intentionally blocked until provider and bookmaker card semantics
are reconciled.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional

from src.research.data_source import ResearchMatch
from src.research.forward.odds import OddsSelection


class TargetFamily(str, Enum):
    GOALS = "GOALS"
    CORNERS = "CORNERS"
    BOOKINGS = "BOOKINGS"


class TargetSide(str, Enum):
    HOME = "HOME"
    AWAY = "AWAY"
    TOTAL = "TOTAL"


class TargetPeriod(str, Enum):
    REGULATION = "REGULATION"


class TargetStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    SOURCE_MISSING = "SOURCE_MISSING"
    EXTRA_TIME_UNSAFE = "EXTRA_TIME_UNSAFE"
    CONTRACT_UNRESOLVED = "CONTRACT_UNRESOLVED"


class ProviderMarketStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    BLOCKED_SEMANTICS = "BLOCKED_SEMANTICS"


class SettlementOutcome(str, Enum):
    WIN = "WIN"
    HALF_WIN = "HALF_WIN"
    PUSH = "PUSH"
    HALF_LOSS = "HALF_LOSS"
    LOSS = "LOSS"


@dataclass(frozen=True, slots=True)
class TargetObservation:
    target_id: str
    status: TargetStatus
    count: Optional[int]
    reason: str = ""

    @property
    def available(self) -> bool:
        return self.status == TargetStatus.AVAILABLE and self.count is not None


@dataclass(frozen=True, slots=True)
class TargetContract:
    target_id: str
    family: TargetFamily
    side: TargetSide
    period: TargetPeriod
    source_fields: tuple[str, ...]
    provider_count_semantics: str
    model_eligible: bool
    provider_market_status: ProviderMarketStatus
    provider_market_key: Optional[str] = None
    provider_market_side_key: Optional[str] = None
    requires_no_extra_time: bool = True
    notes: str = ""

    @property
    def provider_market_mapped(self) -> bool:
        return (
            self.provider_market_status == ProviderMarketStatus.VERIFIED
            and self.provider_market_key is not None
        )

    @property
    def captured_market_key(self) -> Optional[str]:
        """Canonical capture key matching prospective odds storage."""
        if self.provider_market_key is None:
            return None
        if self.provider_market_side_key is None:
            return self.provider_market_key
        return f"{self.provider_market_key}:{self.provider_market_side_key}"

    def observe(self, match: ResearchMatch) -> TargetObservation:
        if not self.model_eligible:
            return TargetObservation(
                self.target_id,
                TargetStatus.CONTRACT_UNRESOLVED,
                None,
                self.notes or "Target semantics are not yet accepted for modeling.",
            )

        if self.requires_no_extra_time and match.has_extra_time_or_shootout_metadata:
            return TargetObservation(
                self.target_id,
                TargetStatus.EXTRA_TIME_UNSAFE,
                None,
                "Regulation-time target rejected because ET/shootout metadata is present.",
            )

        value = _extract_count(match, self.family, self.side)
        if value is None:
            return TargetObservation(
                self.target_id,
                TargetStatus.SOURCE_MISSING,
                None,
                "Required provider count is missing.",
            )
        if value < 0:
            return TargetObservation(
                self.target_id,
                TargetStatus.SOURCE_MISSING,
                None,
                "Provider count is negative and therefore invalid.",
            )
        return TargetObservation(self.target_id, TargetStatus.AVAILABLE, int(value))


@dataclass(frozen=True, slots=True)
class TargetRegistry:
    version: str
    contracts: tuple[TargetContract, ...]

    def __post_init__(self) -> None:
        ids = [contract.target_id for contract in self.contracts]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate target_id")

    def contract(self, target_id: str) -> TargetContract:
        for contract in self.contracts:
            if contract.target_id == target_id:
                return contract
        raise KeyError(target_id)

    def observations(self, match: ResearchMatch) -> dict[str, TargetObservation]:
        return {
            contract.target_id: contract.observe(match)
            for contract in self.contracts
        }

    def model_eligible_ids(self) -> tuple[str, ...]:
        return tuple(c.target_id for c in self.contracts if c.model_eligible)

    def provider_market_mapped_ids(self) -> tuple[str, ...]:
        return tuple(
            c.target_id for c in self.contracts if c.provider_market_mapped
        )


def _extract_count(
    match: ResearchMatch,
    family: TargetFamily,
    side: TargetSide,
) -> Optional[int]:
    if family == TargetFamily.GOALS:
        home = match.home_goals
        away = match.away_goals
    elif family == TargetFamily.CORNERS:
        home = match.corners_home
        away = match.corners_away
    else:
        # Bookings remain deliberately blocked at the contract level.
        return None

    if side == TargetSide.HOME:
        return home
    if side == TargetSide.AWAY:
        return away
    if home is None or away is None:
        return None
    return home + away


def _decimal_line(line: float | int | str | Decimal) -> Decimal:
    try:
        value = Decimal(str(line))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid line {line!r}") from exc
    if value < 0:
        raise ValueError("Line must be non-negative")
    quarters = value * Decimal(4)
    if quarters != quarters.to_integral_value():
        raise ValueError("Only integer, half and quarter lines are supported")
    return value


def is_binary_scoring_line(line: float | int | str | Decimal) -> bool:
    """Whether the line has no push/split state and is safe for binary LL/Brier."""
    value = _decimal_line(line)
    return (value * Decimal(2)) == (value * Decimal(2)).to_integral_value() and (
        value != value.to_integral_value()
    )


def _settle_single(
    count: int,
    line: Decimal,
    selection: OddsSelection,
) -> SettlementOutcome:
    count_d = Decimal(count)
    if selection == OddsSelection.OVER:
        if count_d > line:
            return SettlementOutcome.WIN
        if count_d == line:
            return SettlementOutcome.PUSH
        return SettlementOutcome.LOSS

    if selection == OddsSelection.UNDER:
        if count_d < line:
            return SettlementOutcome.WIN
        if count_d == line:
            return SettlementOutcome.PUSH
        return SettlementOutcome.LOSS

    raise ValueError(f"Unsupported selection {selection}")


def _combine_split(
    a: SettlementOutcome,
    b: SettlementOutcome,
) -> SettlementOutcome:
    pair = {a, b}
    if pair == {SettlementOutcome.WIN}:
        return SettlementOutcome.WIN
    if pair == {SettlementOutcome.LOSS}:
        return SettlementOutcome.LOSS
    if pair == {SettlementOutcome.PUSH}:
        return SettlementOutcome.PUSH
    if pair == {SettlementOutcome.WIN, SettlementOutcome.PUSH}:
        return SettlementOutcome.HALF_WIN
    if pair == {SettlementOutcome.LOSS, SettlementOutcome.PUSH}:
        return SettlementOutcome.HALF_LOSS
    # A properly formed quarter-line split cannot create WIN+LOSS from an
    # integer count, but fail visibly if assumptions change.
    raise ValueError(f"Incoherent split settlement: {a.value}/{b.value}")


def settle_count_market(
    count: int,
    line: float | int | str | Decimal,
    selection: OddsSelection,
) -> SettlementOutcome:
    """Settle an O/U count market for integer, half or Asian quarter lines.

    Quarter lines are split into adjacent integer/half stakes:
    - x.25 -> x.0 and x.5
    - x.75 -> x.5 and x+1.0

    This produces explicit HALF_WIN/HALF_LOSS states instead of forcing a
    binary label. Binary proper scoring should use half-lines only.
    """
    if isinstance(count, bool) or int(count) != count or count < 0:
        raise ValueError("Count must be a non-negative integer")
    value = _decimal_line(line)
    quarter_units = int(value * Decimal(4))
    remainder = quarter_units % 4

    if remainder in (0, 2):
        return _settle_single(int(count), value, selection)

    floor_int = value.to_integral_value(rounding="ROUND_FLOOR")
    if remainder == 1:
        lower = floor_int
        upper = floor_int + Decimal("0.5")
    else:  # x.75
        lower = floor_int + Decimal("0.5")
        upper = floor_int + Decimal("1.0")

    return _combine_split(
        _settle_single(int(count), lower, selection),
        _settle_single(int(count), upper, selection),
    )


def binary_event_outcome(
    count: int,
    line: float | int | str | Decimal,
    selection: OddsSelection,
) -> bool:
    """Return a binary outcome only for true half-lines.

    Integer or quarter lines are rejected because PUSH/HALF states make a
    Bernoulli label scientifically incorrect.
    """
    if not is_binary_scoring_line(line):
        raise ValueError("Binary scoring requires a half-line with no push state")
    outcome = settle_count_market(count, line, selection)
    if outcome == SettlementOutcome.WIN:
        return True
    if outcome == SettlementOutcome.LOSS:
        return False
    raise AssertionError(f"Unexpected non-binary outcome {outcome}")


def _contract(
    family: TargetFamily,
    side: TargetSide,
    source_fields: tuple[str, ...],
    semantics: str,
    *,
    model_eligible: bool,
    market_status: ProviderMarketStatus,
    market_key: Optional[str] = None,
    market_side_key: Optional[str] = None,
    notes: str = "",
) -> TargetContract:
    return TargetContract(
        target_id=f"{family.value.lower()}_{side.value.lower()}_regulation",
        family=family,
        side=side,
        period=TargetPeriod.REGULATION,
        source_fields=source_fields,
        provider_count_semantics=semantics,
        model_eligible=model_eligible,
        provider_market_status=market_status,
        provider_market_key=market_key,
        provider_market_side_key=market_side_key,
        notes=notes,
    )


TARGET_REGISTRY_V1 = TargetRegistry(
    version="qfe-target-contracts-v1",
    contracts=(
        _contract(
            TargetFamily.GOALS,
            TargetSide.HOME,
            ("home_goals",),
            "Home final-score count, accepted only when no ET/shootout metadata exists.",
            model_eligible=True,
            market_status=ProviderMarketStatus.VERIFIED,
            market_key="team_total_goals",
            market_side_key="home",
        ),
        _contract(
            TargetFamily.GOALS,
            TargetSide.AWAY,
            ("away_goals",),
            "Away final-score count, accepted only when no ET/shootout metadata exists.",
            model_eligible=True,
            market_status=ProviderMarketStatus.VERIFIED,
            market_key="team_total_goals",
            market_side_key="away",
        ),
        _contract(
            TargetFamily.GOALS,
            TargetSide.TOTAL,
            ("home_goals", "away_goals"),
            "Sum of both final scores, accepted only when no ET/shootout metadata exists.",
            model_eligible=True,
            market_status=ProviderMarketStatus.VERIFIED,
            market_key="total_goals",
        ),
        _contract(
            TargetFamily.CORNERS,
            TargetSide.HOME,
            ("corners_home",),
            "Home provider all-period corner count; ET matches rejected.",
            model_eligible=True,
            market_status=ProviderMarketStatus.VERIFIED,
            market_key="team_corners",
            market_side_key="home",
        ),
        _contract(
            TargetFamily.CORNERS,
            TargetSide.AWAY,
            ("corners_away",),
            "Away provider all-period corner count; ET matches rejected.",
            model_eligible=True,
            market_status=ProviderMarketStatus.VERIFIED,
            market_key="team_corners",
            market_side_key="away",
        ),
        _contract(
            TargetFamily.CORNERS,
            TargetSide.TOTAL,
            ("corners_home", "corners_away"),
            "Sum of provider all-period corner counts; ET matches rejected.",
            model_eligible=True,
            market_status=ProviderMarketStatus.VERIFIED,
            market_key="match_corners",
        ),
        _contract(
            TargetFamily.BOOKINGS,
            TargetSide.HOME,
            ("yellow_cards_home", "red_cards_home"),
            "Provider raw card counts are not yet reconciled to bookmaker bookings rules.",
            model_eligible=False,
            market_status=ProviderMarketStatus.BLOCKED_SEMANTICS,
            notes="Blocked until red/second-yellow/bookings-point settlement semantics are reconciled.",
        ),
        _contract(
            TargetFamily.BOOKINGS,
            TargetSide.AWAY,
            ("yellow_cards_away", "red_cards_away"),
            "Provider raw card counts are not yet reconciled to bookmaker bookings rules.",
            model_eligible=False,
            market_status=ProviderMarketStatus.BLOCKED_SEMANTICS,
            notes="Blocked until red/second-yellow/bookings-point settlement semantics are reconciled.",
        ),
        _contract(
            TargetFamily.BOOKINGS,
            TargetSide.TOTAL,
            ("yellow_cards_home", "yellow_cards_away", "red_cards_home", "red_cards_away"),
            "Provider raw card counts are not yet reconciled to bookmaker bookings rules.",
            model_eligible=False,
            market_status=ProviderMarketStatus.VERIFIED,
            market_key="total_cards",
            notes="Provider market exists, but target settlement semantics are blocked.",
        ),
    ),
)
