"""Strict closing-line validation with no post-kickoff tolerance."""

from __future__ import annotations

from dataclasses import dataclass
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
    """Fail-closed validation of a closing quote against one trade."""

    def __init__(self, max_closing_delay_seconds: float = 7200.0) -> None:
        # Kept for constructor compatibility. Post-kickoff tolerance is no longer
        # applied because closing quotes must be strictly pre-kickoff.
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
        *,
        expected_line: Optional[float] = None,
        expected_bookmaker: Optional[str] = None,
        require_same_book: bool = False,
    ) -> ClosingValidationResult:
        """Validate identity, exact market, provenance, and strict timing."""
        errors: list[str] = []
        warnings: list[str] = []

        if observation.fixture_id != trade_fixture_id:
            errors.append(
                f"Fixture mismatch: obs={observation.fixture_id} != trade={trade_fixture_id}"
            )
        if observation.market != trade_market:
            errors.append(
                f"Market mismatch: obs={observation.market} != trade={trade_market}"
            )
        if observation.selection != trade_selection:
            errors.append(
                f"Selection mismatch: obs={observation.selection} != trade={trade_selection}"
            )
        if expected_line is not None and observation.line != expected_line:
            errors.append(f"Line mismatch: obs={observation.line} != expected={expected_line}")
        if require_same_book:
            if not expected_bookmaker:
                errors.append("Same-book validation requires expected_bookmaker")
            elif observation.bookmaker.casefold() != expected_bookmaker.casefold():
                errors.append(
                    f"Bookmaker mismatch: obs={observation.bookmaker} "
                    f"!= expected={expected_bookmaker}"
                )

        if observation.closing_timestamp <= trade_entry_timestamp:
            errors.append(
                f"Closing timestamp ({observation.closing_timestamp}) must be > "
                f"entry timestamp ({trade_entry_timestamp})"
            )
        if trade_kickoff_timestamp <= 0:
            errors.append("Missing or invalid kickoff timestamp")
        elif observation.closing_timestamp >= trade_kickoff_timestamp:
            errors.append(
                f"Closing timestamp ({observation.closing_timestamp}) must be strictly "
                f"before kickoff ({trade_kickoff_timestamp})"
            )
            warnings.append("Closing timestamp is at or after kickoff (post-kickoff ineligible)")

        if not observation.source:
            errors.append("Missing source provenance")
        if observation.decimal_odds <= 1.0:
            errors.append(f"Invalid odds: {observation.decimal_odds} <= 1.0")
        if observation.closing_timestamp < 0:
            errors.append("Negative closing timestamp")
        if seen_observation_ids and observation.observation_id in seen_observation_ids:
            errors.append(f"Duplicate observation: {observation.observation_id}")

        if errors:
            status = ClosingOddsStatus.INVALID
        elif observation.timestamp_semantics in (
            TimestampSemantics.EXACT_CLOSE,
            TimestampSemantics.LAST_BEFORE_KICKOFF,
        ):
            status = ClosingOddsStatus.VALID
        elif observation.timestamp_semantics == TimestampSemantics.PROVIDER_ESTIMATED:
            status = ClosingOddsStatus.ESTIMATED
            warnings.append("Timestamp is provider-estimated, not exact")
        else:
            status = ClosingOddsStatus.UNKNOWN
            warnings.append("Timestamp semantics unknown — treat with caution")

        return ClosingValidationResult(
            valid=not errors,
            observation_id=observation.observation_id,
            status=status,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )
