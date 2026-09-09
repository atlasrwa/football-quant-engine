"""Dynamic operational-universe activation policy.

The operational universe is DERIVED from the coverage matrix, not hard-coded.
Activation is deterministic and testable:

    ACTIVE  <=>  identity == VERIFIED
                 AND capture_classification in {CAPTURE_READY,
                                                approved CAPTURE_PARTIAL}

By default only CAPTURE_READY auto-activates; CAPTURE_PARTIAL activates only
when ``include_partial`` is explicitly set (an approved, documented choice).
IDENTITY_UNRESOLVED / API_UNSUPPORTED / MARKET_COVERAGE_INSUFFICIENT never
activate. Lowering the threshold to inflate the league count is refused by
construction: activation keys off classification, never off league prestige or
predictive performance.

Each active competition carries the markets it is eligible to capture, so the
scheduler never requests markets a league does not price.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.research.prospective.coverage_matrix import (
    CaptureClass,
    CoverageRow,
    MarketEligibility,
)
from src.research.prospective.crosswalk import IdentityStatus


@dataclass(frozen=True)
class ActiveCompetition:
    """An activated competition + the markets the scheduler may capture."""

    canonical_name: str
    country: Optional[str]
    thestatsapi_competition_id: str
    thestatsapi_season_id: Optional[str]
    capture_priority: int
    eligible_markets: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "canonical_name": self.canonical_name,
            "country": self.country,
            "thestatsapi_competition_id": self.thestatsapi_competition_id,
            "thestatsapi_season_id": self.thestatsapi_season_id,
            "capture_priority": self.capture_priority,
            "eligible_markets": list(self.eligible_markets),
        }


def _eligible_markets(row: CoverageRow) -> tuple[str, ...]:
    """Markets worth capturing: READY or PARTIAL (skip UNSUPPORTED/UNKNOWN)."""
    return tuple(
        m for m, status in sorted(row.market_eligibility.items())
        if status in (MarketEligibility.READY.value, MarketEligibility.PARTIAL.value)
    )


def active_universe(
    rows: list[CoverageRow],
    *,
    include_partial: bool = False,
) -> list[ActiveCompetition]:
    """Derive the deterministic active universe from coverage rows.

    Sorted by (priority asc, name) so activation order is stable.
    """
    allowed = {CaptureClass.CAPTURE_READY}
    if include_partial:
        allowed.add(CaptureClass.CAPTURE_PARTIAL)

    active: list[ActiveCompetition] = []
    for row in rows:
        if row.entry.identity_status != IdentityStatus.VERIFIED:
            continue
        if row.capture_classification not in allowed:
            continue
        cid = row.entry.thestatsapi_competition_id
        if not cid:  # fail closed: never activate without a stable id
            continue
        markets = _eligible_markets(row)
        if not markets:
            continue  # nothing worth capturing
        season = row.coverage.thestatsapi_season_id if row.coverage else None
        active.append(
            ActiveCompetition(
                canonical_name=row.entry.canonical_name,
                country=row.entry.country,
                thestatsapi_competition_id=cid,
                thestatsapi_season_id=season,
                capture_priority=row.capture_priority,
                eligible_markets=markets,
            )
        )
    active.sort(key=lambda a: (a.capture_priority, a.canonical_name))
    return active


def active_competition_ids(rows: list[CoverageRow], *, include_partial: bool = False) -> tuple[str, ...]:
    """Just the TheStatsAPI competition ids of the active universe."""
    return tuple(a.thestatsapi_competition_id for a in active_universe(rows, include_partial=include_partial))
