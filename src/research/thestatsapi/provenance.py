"""Data provenance for TheStatsAPI records.

Parallel to ``src/research/footystats/provenance.py`` but for
source="THESTATSAPI". The provenance record preserves BOTH the numeric ids
used on the canonical ``ResearchMatch`` and the ORIGINAL provider string ids
(mt_/tm_/sn_) so identity can never be silently lost or conflated with
FootyStats numeric ids.

Timestamp distinctions (unchanged philosophy from FootyStats):
- event_timestamp: kickoff (from fixture utc_date)
- information_timestamp: estimated time post-match stats became available
  (conservative: event + 2h). This is an ESTIMATE and is documented as such.
- retrieved_at: when we fetched the data.

``compute_match_hash`` excludes retrieval time so the hash is content
deterministic.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Optional

_NORMALIZATION_VERSION = "1.0.0"
_SOURCE = "THESTATSAPI"

# Conservative estimate: post-match stats available ~2h after kickoff.
# Actual publication time is unknown from the provider. Documented limitation.
_INFO_DELAY_SECONDS = 7200


@dataclass(frozen=True)
class TheStatsAPIProvenance:
    """Provenance record for a single TheStatsAPI match.

    Attributes:
        source: Always "THESTATSAPI".
        source_match_id: Numeric match id (suffix of mt_...).
        source_match_ref: Original prefixed match id ("mt_...").
        source_season_id: Numeric season id (suffix of sn_...).
        source_season_ref: Original prefixed season id ("sn_...").
        source_home_team_id: Numeric home team id (suffix of tm_...).
        source_home_team_ref: Original prefixed home team id ("tm_...").
        source_away_team_id: Numeric away team id.
        source_away_team_ref: Original prefixed away team id.
        event_timestamp: Kickoff (unix).
        information_timestamp: Estimated stats-available time (unix).
        retrieved_at: Fetch time (unix).
        normalization_version: Version of normalization logic.
        data_hash: Content hash of the normalized record.
    """

    source: str = _SOURCE
    source_match_id: int = 0
    source_match_ref: str = ""
    source_season_id: int = 0
    source_season_ref: str = ""
    source_home_team_id: int = 0
    source_home_team_ref: str = ""
    source_away_team_id: int = 0
    source_away_team_ref: str = ""
    event_timestamp: int = 0
    information_timestamp: int = 0
    retrieved_at: int = 0
    normalization_version: str = _NORMALIZATION_VERSION
    data_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_match_id": self.source_match_id,
            "source_match_ref": self.source_match_ref,
            "source_season_id": self.source_season_id,
            "source_season_ref": self.source_season_ref,
            "source_home_team_id": self.source_home_team_id,
            "source_home_team_ref": self.source_home_team_ref,
            "source_away_team_id": self.source_away_team_id,
            "source_away_team_ref": self.source_away_team_ref,
            "event_timestamp": self.event_timestamp,
            "information_timestamp": self.information_timestamp,
            "retrieved_at": self.retrieved_at,
            "normalization_version": self.normalization_version,
            "data_hash": self.data_hash,
        }


def create_provenance(
    *,
    match_ref: str,
    season_ref: str,
    home_team_ref: str,
    away_team_ref: str,
    event_timestamp: int,
    normalized_hash: str = "",
    retrieved_at: Optional[int] = None,
) -> TheStatsAPIProvenance:
    """Create provenance from parsed TheStatsAPI identity fields.

    Uses the ``ids`` module for numeric parsing, keeping the original prefixed
    refs alongside. ``information_timestamp`` is a conservative estimate.
    """
    from src.research.thestatsapi import ids

    def _num(ref: str, parser: Any) -> int:
        try:
            return parser(ref)
        except ids.ProviderIdError:
            return 0

    return TheStatsAPIProvenance(
        source=_SOURCE,
        source_match_id=_num(match_ref, ids.parse_match_id),
        source_match_ref=match_ref,
        source_season_id=_num(season_ref, ids.parse_season_id),
        source_season_ref=season_ref,
        source_home_team_id=_num(home_team_ref, ids.parse_team_id),
        source_home_team_ref=home_team_ref,
        source_away_team_id=_num(away_team_ref, ids.parse_team_id),
        source_away_team_ref=away_team_ref,
        event_timestamp=int(event_timestamp),
        information_timestamp=int(event_timestamp) + _INFO_DELAY_SECONDS,
        retrieved_at=int(retrieved_at if retrieved_at is not None else time.time()),
        normalization_version=_NORMALIZATION_VERSION,
        data_hash=normalized_hash,
    )


def compute_match_hash(match_dict: dict[str, Any]) -> str:
    """Deterministic content hash for a normalized match (excludes retrieval)."""
    stable = {k: v for k, v in sorted(match_dict.items()) if k not in ("retrieved_at",)}
    canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
