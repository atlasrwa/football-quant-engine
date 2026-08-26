"""Data quality validation for FootyStats records.

Validates normalized research matches and tracks quality metrics.
Invalid records are quarantined, not silently discarded.

Quality statuses:
- VALID: All required fields present, values in valid ranges
- MISSING_REQUIRED_FIELDS: Core identity/result fields absent
- INVALID_STATISTIC: Values outside valid ranges
- DUPLICATE: Same source match_id seen before
- TIMESTAMP_ERROR: Invalid or out-of-range timestamp
- SCHEMA_ERROR: Record structure is broken
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.research.data_source import ResearchMatch

logger = logging.getLogger(__name__)


class DataQualityStatus(Enum):
    """Data quality classification for a record."""

    VALID = "VALID"
    MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
    INVALID_STATISTIC = "INVALID_STATISTIC"
    DUPLICATE = "DUPLICATE"
    TIMESTAMP_ERROR = "TIMESTAMP_ERROR"
    SCHEMA_ERROR = "SCHEMA_ERROR"


@dataclass
class QualityReport:
    """Aggregated quality report for a batch of records."""

    total_records: int = 0
    valid_count: int = 0
    missing_fields_count: int = 0
    invalid_stats_count: int = 0
    duplicate_count: int = 0
    timestamp_error_count: int = 0
    schema_error_count: int = 0
    issues: list[dict[str, Any]] = field(default_factory=list)

    @property
    def valid_rate(self) -> float:
        if self.total_records == 0:
            return 0.0
        return self.valid_count / self.total_records

    @property
    def invalid_count(self) -> int:
        return self.total_records - self.valid_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "valid_count": self.valid_count,
            "valid_rate": round(self.valid_rate, 4),
            "missing_fields_count": self.missing_fields_count,
            "invalid_stats_count": self.invalid_stats_count,
            "duplicate_count": self.duplicate_count,
            "timestamp_error_count": self.timestamp_error_count,
            "schema_error_count": self.schema_error_count,
        }


class RecordValidator:
    """Validates research match records for data quality.

    Tracks seen match IDs for deduplication.
    Reports issues without silently repairing them.
    """

    # Reasonable timestamp bounds (year 2000 to year 2030)
    _MIN_TIMESTAMP = 946684800   # 2000-01-01
    _MAX_TIMESTAMP = 1893456000  # 2030-01-01

    def __init__(self) -> None:
        self._seen_ids: set[int] = set()
        self._report = QualityReport()

    @property
    def report(self) -> QualityReport:
        return self._report

    def reset(self) -> None:
        """Reset validator state."""
        self._seen_ids.clear()
        self._report = QualityReport()

    def validate(self, match: ResearchMatch) -> DataQualityStatus:
        """Validate a single ResearchMatch.

        Args:
            match: Normalized research match.

        Returns:
            DataQualityStatus classification.
        """
        self._report.total_records += 1

        # Deduplication check
        if match.match_id in self._seen_ids:
            self._report.duplicate_count += 1
            self._report.issues.append({
                "match_id": match.match_id,
                "status": DataQualityStatus.DUPLICATE.value,
                "detail": "Duplicate match_id",
            })
            return DataQualityStatus.DUPLICATE
        self._seen_ids.add(match.match_id)

        # Timestamp validation
        if not self._MIN_TIMESTAMP <= match.date_unix <= self._MAX_TIMESTAMP:
            self._report.timestamp_error_count += 1
            self._report.issues.append({
                "match_id": match.match_id,
                "status": DataQualityStatus.TIMESTAMP_ERROR.value,
                "detail": f"date_unix={match.date_unix} out of range",
            })
            return DataQualityStatus.TIMESTAMP_ERROR

        # Required fields
        if match.home_goals is None or match.away_goals is None:
            self._report.missing_fields_count += 1
            self._report.issues.append({
                "match_id": match.match_id,
                "status": DataQualityStatus.MISSING_REQUIRED_FIELDS.value,
                "detail": "Missing goals",
            })
            return DataQualityStatus.MISSING_REQUIRED_FIELDS

        if not match.home_team or not match.away_team:
            self._report.missing_fields_count += 1
            return DataQualityStatus.MISSING_REQUIRED_FIELDS

        # Statistical range validation (only for non-null values)
        issues = self._validate_ranges(match)
        if issues:
            self._report.invalid_stats_count += 1
            self._report.issues.append({
                "match_id": match.match_id,
                "status": DataQualityStatus.INVALID_STATISTIC.value,
                "detail": "; ".join(issues),
            })
            return DataQualityStatus.INVALID_STATISTIC

        # Home team != away team
        if match.home_team == match.away_team:
            self._report.schema_error_count += 1
            return DataQualityStatus.SCHEMA_ERROR

        self._report.valid_count += 1
        return DataQualityStatus.VALID

    def validate_batch(
        self, matches: list[ResearchMatch]
    ) -> tuple[list[ResearchMatch], list[tuple[ResearchMatch, DataQualityStatus]]]:
        """Validate a batch of matches.

        Args:
            matches: List of normalized matches.

        Returns:
            Tuple of (valid_matches, rejected_matches_with_status).
        """
        valid: list[ResearchMatch] = []
        rejected: list[tuple[ResearchMatch, DataQualityStatus]] = []

        for match in matches:
            status = self.validate(match)
            if status == DataQualityStatus.VALID:
                valid.append(match)
            else:
                rejected.append((match, status))

        return valid, rejected

    def _validate_ranges(self, match: ResearchMatch) -> list[str]:
        """Validate statistical ranges. Returns list of issues."""
        issues: list[str] = []

        # Goals non-negative
        if match.home_goals is not None and match.home_goals < 0:
            issues.append(f"home_goals={match.home_goals} < 0")
        if match.away_goals is not None and match.away_goals < 0:
            issues.append(f"away_goals={match.away_goals} < 0")

        # Corners non-negative
        if match.corners_home is not None and match.corners_home < 0:
            issues.append(f"corners_home={match.corners_home} < 0")
        if match.corners_away is not None and match.corners_away < 0:
            issues.append(f"corners_away={match.corners_away} < 0")

        # Shots non-negative
        if match.shots_home is not None and match.shots_home < 0:
            issues.append(f"shots_home={match.shots_home} < 0")
        if match.shots_away is not None and match.shots_away < 0:
            issues.append(f"shots_away={match.shots_away} < 0")

        # Possession 0-100
        if match.possession_home is not None and not (0 <= match.possession_home <= 100):
            issues.append(f"possession_home={match.possession_home} out of [0,100]")
        if match.possession_away is not None and not (0 <= match.possession_away <= 100):
            issues.append(f"possession_away={match.possession_away} out of [0,100]")

        # xG non-negative
        if match.home_xg is not None and match.home_xg < 0:
            issues.append(f"home_xg={match.home_xg} < 0")
        if match.away_xg is not None and match.away_xg < 0:
            issues.append(f"away_xg={match.away_xg} < 0")

        return issues
