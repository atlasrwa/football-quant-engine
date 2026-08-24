"""Schema validation for raw FootyStats match records."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default errors directory
_DEFAULT_ERRORS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "errors"

# Required fields that must be present and non-null for a valid record
REQUIRED_FIELDS = [
    "id",
    "homeGoalCount",
    "awayGoalCount",
    "date_unix",
    "home_name",
    "away_name",
    "league_id",
    "season",
]

# Fields that should be numeric (int or float) when present
NUMERIC_FIELDS = [
    "id",
    "homeGoalCount",
    "awayGoalCount",
    "date_unix",
    "league_id",
]


class SchemaValidator:
    """Validates raw FootyStats JSON records against the minimum required schema.

    Invalid records are logged to an error file in JSONL format for debugging.
    """

    def __init__(self, errors_dir: Optional[Path] = None) -> None:
        """Initialize SchemaValidator.

        Args:
            errors_dir: Directory for validation error logs.
                        Defaults to data/errors/.
        """
        self._errors_dir = errors_dir or _DEFAULT_ERRORS_DIR
        self._errors_dir.mkdir(parents=True, exist_ok=True)
        self._error_log_path = self._errors_dir / "validation_errors.jsonl"
        self._error_count = 0

    @property
    def error_count(self) -> int:
        """Total validation errors since initialization."""
        return self._error_count

    @property
    def error_log_path(self) -> Path:
        """Path to the validation errors log file."""
        return self._error_log_path

    def validate_batch(
        self, records: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Validate a batch of raw records.

        Args:
            records: List of raw JSON dicts from the API response.

        Returns:
            Tuple of (valid_records, error_count).
        """
        valid: List[Dict[str, Any]] = []
        errors = 0

        for record in records:
            validation_errors = self._validate_record(record)
            if validation_errors:
                errors += 1
                self._error_count += 1
                self._log_error(record, validation_errors)
            else:
                valid.append(record)

        logger.info(
            "Validation complete: %d valid, %d invalid out of %d total",
            len(valid), errors, len(records),
        )
        return valid, errors

    def validate_single(self, record: Dict[str, Any]) -> Optional[List[str]]:
        """Validate a single record.

        Args:
            record: A raw JSON dict.

        Returns:
            List of error messages if invalid, None if valid.
        """
        errors = self._validate_record(record)
        if errors:
            self._error_count += 1
            self._log_error(record, errors)
        return errors or None

    def _validate_record(self, record: Dict[str, Any]) -> List[str]:
        """Check a single record against the schema.

        Args:
            record: Raw match dict.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: List[str] = []

        # Check required fields exist and are not None
        for field in REQUIRED_FIELDS:
            if field not in record:
                errors.append(f"Missing required field: '{field}'")
            elif record[field] is None:
                errors.append(f"Required field is null: '{field}'")

        # If we have basic fields, check numeric types
        if not errors:
            for field in NUMERIC_FIELDS:
                value = record.get(field)
                if value is not None and not isinstance(value, (int, float)):
                    errors.append(
                        f"Field '{field}' must be numeric, got {type(value).__name__}"
                    )

            # Check goal counts are non-negative
            home_goals = record.get("homeGoalCount")
            away_goals = record.get("awayGoalCount")
            if isinstance(home_goals, (int, float)) and home_goals < 0:
                errors.append(f"homeGoalCount must be non-negative, got {home_goals}")
            if isinstance(away_goals, (int, float)) and away_goals < 0:
                errors.append(f"awayGoalCount must be non-negative, got {away_goals}")

            # Check xG values if present are non-negative
            for xg_field in ("team_a_xg", "team_b_xg"):
                xg_val = record.get(xg_field)
                if xg_val is not None and isinstance(xg_val, (int, float)) and xg_val < 0:
                    errors.append(f"{xg_field} must be non-negative, got {xg_val}")

        return errors

    def _log_error(
        self, record: Dict[str, Any], errors: List[str]
    ) -> None:
        """Append a validation error to the JSONL error log.

        Args:
            record: The invalid raw record.
            errors: List of validation error descriptions.
        """
        error_entry = {
            "timestamp": int(time.time()),
            "record_id": record.get("id", "unknown"),
            "errors": errors,
            "record": record,
        }
        with open(self._error_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(error_entry) + "\n")
        logger.warning(
            "Validation error for record id=%s: %s",
            record.get("id", "unknown"),
            "; ".join(errors),
        )

    def clear_error_log(self) -> None:
        """Clear the validation error log file."""
        if self._error_log_path.exists():
            self._error_log_path.unlink()
        self._error_count = 0
