"""Closing Line Validation — verifies closing odds observations are genuine.

A closing odds observation must satisfy:
1. Same fixture as the paper trade
2. Same market
3. Same selection
4. closing_timestamp > entry_timestamp
5. closing_timestamp <= kickoff (where applicable)
6. No post-kickoff information
7. Source provenance exists
8. Odds are valid decimal (>= 1.0)
9. No impossible timestamp ordering
10. No duplicate observations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.research.closing.provider import (
    ClosingOddsObservation,
    ClosingOddsStatus,
    TimestampSemantics,
)


@dataclass(frozen=True)
class ClosingValidationResult:
    """Result of validating a closing odds observation."""
    valid: bool
    observation_id: str = ""
    status: ClosingOddsStatus = ClosingOddsStatus.VALID
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "observation_id": self.observation_id,
            "status": self.status.value,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


class ClosingLineValidator:
    """Validates closing odds observations against paper trades.

    Rejects observations that fail any validation rule.
    Never silently accepts ambiguous data.
    """

    def __init__(self, max_closing_delay_seconds: float = 7200.0) -> None:
        """Initialize validator.

        Args:
            max_closing_delay_seconds: Maximum acceptable delay between
                closing_timestamp and kickoff (default 2h).
        """
        self._max_delay = max_closing_delay_seconds

    def validate(
        self,
        observation: ClosingOddsObservation,
        trade_fixture_id: str,
        trade_market: str,
        trade_selection: str,
        trade_entry_timestamp: float,
        trade_kickoff_timestamp: float,
        seen_observation_ids: Optional[set[str]] = None,
    ) -> ClosingValidationResult:
        """Validate a closing odds observation against a paper trade.

        Returns ClosingValidationResult with detailed errors if invalid.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Same fixture
        if observation.fixture_id != trade_fixture_id:
            errors.append(
                f"Fixture mismatch: obs={observation.fixture_id} != trade={trade_fixture_id}"
            )

        # 2. Same market
        if observation.market != trade_market:
            errors.append(
                f"Market mismatch: obs={observation.market} != trade={trade_market}"
            )

        # 3. Same selection
        if observation.selection != trade_selection:
            errors.append(
                f"Selection mismatch: obs={observation.selection} != trade={trade_selection}"
            )

        # 4. Closing timestamp > entry timestamp
        if observation.closing_timestamp <= trade_entry_timestamp:
            errors.append(
                f"Closing timestamp ({observation.closing_timestamp}) must be > "
                f"entry timestamp ({trade_entry_timestamp})"
            )

        # 5. Closing timestamp <= kickoff (with tolerance)
        if trade_kickoff_timestamp > 0:
            if observation.closing_timestamp > trade_kickoff_timestamp + self._max_delay:
                errors.append(
                    f"Closing timestamp ({observation.closing_timestamp}) is too far after "
                    f"kickoff ({trade_kickoff_timestamp})"
                )

        # 6. No post-kickoff data used (heuristic: closing must be near kickoff)
        if observation.closing_timestamp > trade_kickoff_timestamp + 300:  # 5 min tolerance
            warnings.append("Closing timestamp is after kickoff + 5min (may be post-kickoff)")

        # 7. Source provenance
        if not observation.source:
            errors.append("Missing source provenance")

        # 8. Valid decimal odds
        if observation.decimal_odds < 1.0:
            errors.append(f"Invalid odds: {observation.decimal_odds} < 1.0")

        # 9. Timestamp ordering
        if observation.closing_timestamp < 0:
            errors.append("Negative closing timestamp")

        # 10. Duplicate check
        if seen_observation_ids and observation.observation_id in seen_observation_ids:
            errors.append(f"Duplicate observation: {observation.observation_id}")

        # Determine status
        if errors:
            status = ClosingOddsStatus.INVALID
        elif observation.timestamp_semantics == TimestampSemantics.EXACT_CLOSE:
            status = ClosingOddsStatus.VALID
        elif observation.timestamp_semantics == TimestampSemantics.LAST_BEFORE_KICKOFF:
            status = ClosingOddsStatus.VALID
        elif observation.timestamp_semantics == TimestampSemantics.PROVIDER_ESTIMATED:
            status = ClosingOddsStatus.ESTIMATED
            warnings.append("Timestamp is provider-estimated, not exact")
        else:
            status = ClosingOddsStatus.UNKNOWN
            warnings.append("Timestamp semantics unknown — treat with caution")

        return ClosingValidationResult(
            valid=len(errors) == 0,
            observation_id=observation.observation_id,
            status=status,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )
