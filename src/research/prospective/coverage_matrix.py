"""Competition coverage matrix + capture classification.

Merges the identity crosswalk with live recon coverage into one machine-readable
matrix, then classifies each competition and derives market-specific
eligibility. UNKNOWN is preserved (never coerced to False).

Classification (per Part 11):
    CAPTURE_READY                - VERIFIED + enough data for price discovery
    CAPTURE_PARTIAL              - VERIFIED but a channel is missing/uncertain
    MARKET_COVERAGE_INSUFFICIENT - fixtures exist but market obs too weak
    IDENTITY_UNRESOLVED          - no safe provider mapping (incl. AMBIGUOUS)
    API_UNSUPPORTED              - provider genuinely lacks support

Market-specific eligibility avoids discarding a whole league for one absent
market, and lets the scheduler capture only useful markets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.research.prospective.crosswalk import CrosswalkEntry, IdentityStatus
from src.research.prospective.recon import CompetitionCoverage


class CaptureClass(str, Enum):
    CAPTURE_READY = "CAPTURE_READY"
    CAPTURE_PARTIAL = "CAPTURE_PARTIAL"
    MARKET_COVERAGE_INSUFFICIENT = "MARKET_COVERAGE_INSUFFICIENT"
    IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
    API_UNSUPPORTED = "API_UNSUPPORTED"


class MarketEligibility(str, Enum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


#: Champion-supported markets we track eligibility for.
CHAMPION_MARKETS = ("total_goals", "match_corners", "total_cards", "match_shots_on_target")


@dataclass
class CoverageRow:
    """One competition's full coverage-matrix row (identity + live coverage)."""

    entry: CrosswalkEntry
    coverage: Optional[CompetitionCoverage]
    capture_classification: CaptureClass
    capture_priority: int
    market_eligibility: dict[str, str]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        d = self.entry.to_dict()
        d.update({
            "thestatsapi_season_id": self.coverage.thestatsapi_season_id if self.coverage else None,
            "scheduled_fixtures_in_scan": self.coverage.scheduled_fixtures_in_scan if self.coverage else None,
            "nearest_kickoff": self.coverage.nearest_kickoff_iso if self.coverage else None,
            "odds_endpoint_verified": self.coverage.odds_endpoint_verified if self.coverage else None,
            "bookmakers_present": list(self.coverage.bookmakers_present) if self.coverage else [],
            "pinnacle_available": self.coverage.pinnacle_available if self.coverage else None,
            "bet365_available": self.coverage.bet365_available if self.coverage else None,
            "markets_present": list(self.coverage.markets_present) if self.coverage else [],
            "lineup_endpoint_verified": self.coverage.lineup_endpoint_verified if self.coverage else None,
            "injuries_endpoint_verified": self.coverage.injuries_endpoint_verified if self.coverage else None,
            "referee_available": self.coverage.referee_available if self.coverage else None,
            "capture_classification": self.capture_classification.value,
            "capture_priority": self.capture_priority,
            "market_eligibility": self.market_eligibility,
            "reason": self.reason,
        })
        return d


def _market_eligibility(cov: Optional[CompetitionCoverage], entry: CrosswalkEntry) -> dict[str, str]:
    """Per-market eligibility.

    - If the registry marks the competition odds_available and a live probe saw
      the market => READY.
    - odds_available true but market not seen in the (single) probe => PARTIAL
      (a single fixture may not price every market; not proof of UNSUPPORTED).
    - odds_available explicitly false => UNSUPPORTED.
    - No evidence either way => UNKNOWN (never False).
    """
    seen = set(cov.markets_present) if cov else set()
    out: dict[str, str] = {}
    for m in CHAMPION_MARKETS:
        if m in seen:
            out[m] = MarketEligibility.READY.value
        elif entry.odds_available is True:
            out[m] = MarketEligibility.PARTIAL.value
        elif entry.odds_available is False:
            out[m] = MarketEligibility.UNSUPPORTED.value
        else:
            out[m] = MarketEligibility.UNKNOWN.value
    return out


def classify(entry: CrosswalkEntry, cov: Optional[CompetitionCoverage]) -> CoverageRow:
    """Classify one competition deterministically.

    Priority tiers (1 highest): 1 = READY with Pinnacle+lineup potential;
    2 = READY without Pinnacle; 3 = PARTIAL; 4 = weak/none. Classification is
    NEVER based on predictive performance.
    """
    elig = _market_eligibility(cov, entry)

    # Identity gates first.
    if entry.identity_status == IdentityStatus.API_UNSUPPORTED:
        return CoverageRow(entry, cov, CaptureClass.API_UNSUPPORTED, 4, elig,
                           "registry BLOCKED / provider lacks competition")
    if entry.identity_status in (IdentityStatus.AMBIGUOUS, IdentityStatus.UNRESOLVED,
                                 IdentityStatus.PROBABLE):
        return CoverageRow(entry, cov, CaptureClass.IDENTITY_UNRESOLVED, 4, elig,
                           f"identity {entry.identity_status.value}; not auto-activated")

    # VERIFIED from here.
    if cov is None:
        return CoverageRow(entry, cov, CaptureClass.CAPTURE_PARTIAL, 3, elig,
                           "verified identity but no live recon evidence yet")

    has_odds_ep = cov.odds_endpoint_verified
    registry_odds = entry.odds_available is True
    any_market_ready = any(v == MarketEligibility.READY.value for v in elig.values())
    any_market_possible = registry_odds or any_market_ready

    # No fixtures in scan is NOT a disqualifier (off-matchday / far horizon):
    # rely on registry odds_available + endpoint evidence where present.
    if has_odds_ep is True and any_market_ready:
        # A real odds row with a champion market present.
        if cov.pinnacle_available:
            return CoverageRow(entry, cov, CaptureClass.CAPTURE_READY, 1, elig,
                               "verified; live odds with Pinnacle + champion market")
        return CoverageRow(entry, cov, CaptureClass.CAPTURE_READY, 2, elig,
                           "verified; live odds with a champion market (no Pinnacle seen)")

    if any_market_possible:
        # Registry says odds exist but we did not see a priced champion market
        # on the single probed fixture (or no fixture/odds row yet) — capture
        # partially; the scheduler will confirm markets per fixture at capture.
        return CoverageRow(entry, cov, CaptureClass.CAPTURE_PARTIAL, 3, elig,
                           "verified; odds expected but not confirmed on probe fixture")

    # odds explicitly unavailable and nothing priced => too weak.
    return CoverageRow(entry, cov, CaptureClass.MARKET_COVERAGE_INSUFFICIENT, 4, elig,
                       "verified; no usable market observations")


def build_coverage_matrix(
    entries: list[CrosswalkEntry],
    coverage: list[CompetitionCoverage],
) -> list[CoverageRow]:
    """Merge crosswalk + recon into classified rows (one per crosswalk entry)."""
    by_cid = {c.thestatsapi_competition_id: c for c in coverage if c.thestatsapi_competition_id}
    by_name = {c.canonical_name: c for c in coverage}
    rows: list[CoverageRow] = []
    for e in entries:
        cov = by_cid.get(e.thestatsapi_competition_id) or by_name.get(e.canonical_name)
        rows.append(classify(e, cov))
    return rows


def matrix_summary(rows: list[CoverageRow]) -> dict[str, int]:
    from collections import Counter

    c = Counter(r.capture_classification.value for r in rows)
    return {"total": len(rows), **dict(sorted(c.items()))}
