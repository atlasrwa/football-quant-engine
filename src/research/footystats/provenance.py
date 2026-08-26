"""Data provenance tracking for FootyStats records.

Every real-data record must be traceable:
- source: FOOTYSTATS
- source_match_id: Original API match ID
- retrieved_at: When the data was fetched
- normalization_version: Version of normalization logic
- data_hash: Content hash of the normalized record

Distinguishes:
- EVENT TIME: When the match was played (date_unix)
- INFORMATION TIME: When stats became available (post-match, estimated)
- RETRIEVAL TIME: When we downloaded the data
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional


_NORMALIZATION_VERSION = "1.0.0"


@dataclass(frozen=True)
class DataProvenance:
    """Provenance record for a single research match.

    Attributes:
        source: Data source identifier.
        source_match_id: Original match ID from the source.
        source_season_id: Season/competition ID from the source.
        source_home_team_id: Home team ID from source (stable identity).
        source_away_team_id: Away team ID from source (stable identity).
        event_timestamp: When the match was played (kickoff).
        information_timestamp: Estimated time stats became available.
        retrieved_at: When we fetched the data (unix timestamp).
        normalization_version: Version of normalization logic applied.
        data_hash: SHA-256 hash of normalized record content.
    """

    source: str = "FOOTYSTATS"
    source_match_id: int = 0
    source_season_id: int = 0
    source_home_team_id: int = 0
    source_away_team_id: int = 0
    event_timestamp: int = 0
    information_timestamp: int = 0  # Estimated: event_timestamp + 2 hours
    retrieved_at: int = 0
    normalization_version: str = _NORMALIZATION_VERSION
    data_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_match_id": self.source_match_id,
            "source_season_id": self.source_season_id,
            "source_home_team_id": self.source_home_team_id,
            "source_away_team_id": self.source_away_team_id,
            "event_timestamp": self.event_timestamp,
            "information_timestamp": self.information_timestamp,
            "retrieved_at": self.retrieved_at,
            "normalization_version": self.normalization_version,
            "data_hash": self.data_hash,
        }


def create_provenance(
    raw_record: dict[str, Any],
    normalized_hash: str = "",
) -> DataProvenance:
    """Create provenance from a raw FootyStats record.

    The information_timestamp is estimated as event_timestamp + 2 hours.
    This is a conservative estimate — actual stats publication time is unknown.
    This limitation is documented.

    Args:
        raw_record: Raw API response dict.
        normalized_hash: Hash of the normalized ResearchMatch.

    Returns:
        DataProvenance record.
    """
    event_ts = int(raw_record.get("date_unix", 0))
    # Conservative estimate: stats available ~2 hours after kickoff
    # Actual publication time is unknown from the API
    info_ts = event_ts + 7200  # +2 hours

    return DataProvenance(
        source="FOOTYSTATS",
        source_match_id=int(raw_record.get("id", 0)),
        source_season_id=int(raw_record.get("competition_id", 0) or raw_record.get("league_id", 0)),
        source_home_team_id=int(raw_record.get("homeID", 0)),
        source_away_team_id=int(raw_record.get("awayID", 0)),
        event_timestamp=event_ts,
        information_timestamp=info_ts,
        retrieved_at=int(time.time()),
        normalization_version=_NORMALIZATION_VERSION,
        data_hash=normalized_hash,
    )


def compute_match_hash(match_dict: dict[str, Any]) -> str:
    """Compute deterministic content hash for a normalized match.

    Excludes retrieval time — only content matters.
    """
    # Use only stable content fields
    stable_fields = {
        k: v for k, v in sorted(match_dict.items())
        if k not in ("retrieved_at",)
    }
    canonical = json.dumps(stable_fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
