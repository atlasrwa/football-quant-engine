"""Coverage-bias funnel and analysis-support strata (mandatory diagnostics).

Reports what is filtered out at every stage from the full FootyStats universe
down to the eventual usable research sample, so we know whether the sample
represents football generally or merely high-liquidity European matches with
rich provider coverage. Either result is acceptable — it just must be explicit.

Also computes analysis-support strata to prevent the sample-size illusion:
2,000 captured fixtures is NOT N=2,000 for an analysis that needs same-book
same-line LATE->FINAL transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.research.prospective.coverage_matrix import CaptureClass, CoverageRow
from src.research.prospective.crosswalk import IdentityStatus
from src.research.prospective.storage import CaptureStore


@dataclass
class CoverageFunnel:
    """The identity/coverage funnel from the full universe to CAPTURE_READY."""

    footystats_supported: int
    identity_verified: int
    identity_ambiguous: int
    identity_unresolved: int
    api_unsupported: int
    capture_ready: int
    capture_partial: int
    market_insufficient: int

    def to_dict(self) -> dict:
        return {
            "footystats_supported": self.footystats_supported,
            "identity_verified": self.identity_verified,
            "identity_ambiguous": self.identity_ambiguous,
            "identity_unresolved": self.identity_unresolved,
            "api_unsupported": self.api_unsupported,
            "capture_ready": self.capture_ready,
            "capture_partial": self.capture_partial,
            "market_coverage_insufficient": self.market_insufficient,
        }


def competition_funnel(rows: list[CoverageRow]) -> CoverageFunnel:
    """Build the competition-level coverage funnel from classified rows."""
    def n_ident(s: IdentityStatus) -> int:
        return sum(1 for r in rows if r.entry.identity_status == s)

    def n_class(c: CaptureClass) -> int:
        return sum(1 for r in rows if r.capture_classification == c)

    return CoverageFunnel(
        footystats_supported=len(rows),
        identity_verified=n_ident(IdentityStatus.VERIFIED),
        identity_ambiguous=n_ident(IdentityStatus.AMBIGUOUS),
        identity_unresolved=n_ident(IdentityStatus.UNRESOLVED),
        api_unsupported=n_ident(IdentityStatus.API_UNSUPPORTED),
        capture_ready=n_class(CaptureClass.CAPTURE_READY),
        capture_partial=n_class(CaptureClass.CAPTURE_PARTIAL),
        market_insufficient=n_class(CaptureClass.MARKET_COVERAGE_INSUFFICIENT),
    )


@dataclass
class AnalysisSupport:
    """Fixture-level analysis-support strata from persisted captures.

    Each stratum is a STRICT subset of the one above; the usable N for a
    price-discovery analysis is the deepest relevant stratum, never the top.
    """

    all_captured_fixtures: int
    fixtures_with_odds: int
    fixtures_with_same_book_two_snapshots: int
    fixtures_with_confirmed_lineup: int
    fixtures_with_lineup_and_same_book_movement: int

    def to_dict(self) -> dict:
        return {
            "all_captured_fixtures": self.all_captured_fixtures,
            "fixtures_with_odds": self.fixtures_with_odds,
            "fixtures_with_same_book_two_snapshots": self.fixtures_with_same_book_two_snapshots,
            "fixtures_with_confirmed_lineup": self.fixtures_with_confirmed_lineup,
            "fixtures_with_lineup_and_same_book_movement": self.fixtures_with_lineup_and_same_book_movement,
        }


def analysis_support(store: CaptureStore) -> AnalysisSupport:
    """Compute analysis-support strata from the append-only capture store.

    Movement requires >=2 odds snapshots for the SAME (bookmaker, market,
    selection, line) key — the odds concept encodes bookmaker as its trailing
    segment (``odds:market:sel:line:bookmaker``).
    """
    fixtures: set = set()
    with_odds: set = set()
    with_lineup: set = set()
    # (fixture, full-odds-concept) -> count of distinct observed_at
    key_times: dict = {}

    for rec in store.read_all():
        fid = rec.canonical_entity_id
        fixtures.add(fid)
        if rec.concept.startswith("odds:"):
            with_odds.add(fid)
            k = (fid, rec.concept)  # concept already includes the bookmaker
            key_times.setdefault(k, set()).add(rec.observed_at)
        elif rec.concept.startswith("confirmed_lineup"):
            with_lineup.add(fid)

    same_book_move = {fid for (fid, _c), times in key_times.items() if len(times) >= 2}
    lineup_and_move = with_lineup & same_book_move

    return AnalysisSupport(
        all_captured_fixtures=len(fixtures),
        fixtures_with_odds=len(with_odds),
        fixtures_with_same_book_two_snapshots=len(same_book_move),
        fixtures_with_confirmed_lineup=len(with_lineup),
        fixtures_with_lineup_and_same_book_movement=len(lineup_and_move),
    )
