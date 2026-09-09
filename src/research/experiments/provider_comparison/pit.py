"""Point-in-time determination and gating for the provider comparison (Phase 2).

This module records, in code, the honest PIT determination made during the
Phase 0 audit and enforces the fail-closed behavior the task requires.

Findings that constrain what is supportable on the available historical data:

1. STAT-LEVEL VINTAGES (EARLY ~T-24h / LATE ~T-60m) ARE UNSUPPORTED for provider
   statistics. TheStatsAPI /stats payloads carry NO capture/observation
   timestamp, and the FootyStats corpus records carry none either. We cannot
   prove *when* a given match's box-score became available, so we cannot honestly
   assign a stat observation to a T-24h vs T-60m cutoff. Per the task
   ("unknown timestamps fail closed"), stat observations are NOT admitted to a
   vintage-timestamped comparison.

2. WHAT IS SUPPORTED: a fixture-date walk-forward. A prediction for fixture F at
   kickoff K may use ONLY prior completed matches (event_time < K). This is the
   exact discipline the champion already enforces (date_unix < cutoff), and it is
   PIT-safe because a prior match's outcome is unambiguously known before a later
   fixture regardless of the exact publication minute. The "forecast cutoff" for
   the walk-forward is the fixture kickoff; features are built strictly from
   earlier fixtures.

3. GENUINE CLOSING / CLV IS UNSUPPORTED on this dataset: the only
   genuinely-timestamped odds (research_odds captures, 82 matches) do NOT overlap
   the fixtures that have stats. Closing/CLV comparisons are marked UNSUPPORTED,
   not fabricated. Pre-match odds are used only as a market benchmark with the
   explicit caveat that ``last_seen`` is not a genuine close.

The helpers below make the "prior fixtures only" rule explicit and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PITSupport(Enum):
    """Whether a requested comparison mode is supportable on the data."""
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class VintageSupport:
    early_stats: PITSupport = PITSupport.UNSUPPORTED
    late_stats: PITSupport = PITSupport.UNSUPPORTED
    fixture_date_walk_forward: PITSupport = PITSupport.SUPPORTED
    genuine_closing_odds: PITSupport = PITSupport.UNSUPPORTED
    reason_stats_vintage: str = (
        "Provider stat payloads carry no capture/observation timestamp; a T-24h "
        "vs T-60m assignment cannot be proven, so stat vintages fail closed."
    )
    reason_closing: str = (
        "Genuinely-timestamped odds captures do not overlap fixtures with stats; "
        "no genuine LAST_BEFORE_KICKOFF close is available for the evaluated set."
    )

    def to_dict(self) -> dict:
        return {
            "early_stats": self.early_stats.value,
            "late_stats": self.late_stats.value,
            "fixture_date_walk_forward": self.fixture_date_walk_forward.value,
            "genuine_closing_odds": self.genuine_closing_odds.value,
            "reason_stats_vintage": self.reason_stats_vintage,
            "reason_closing": self.reason_closing,
        }


VINTAGE_SUPPORT = VintageSupport()


def is_prior_fixture(candidate_kickoff: int, target_kickoff: int, *, strict: bool = True) -> bool:
    """Whether a candidate fixture may contribute to a target fixture's features.

    PIT rule: only STRICTLY-earlier fixtures contribute. Equal kickoffs are
    excluded in strict mode (same-kickoff fixtures cannot see each other), which
    matches the champion's batch-by-timestamp discipline.
    """
    if strict:
        return candidate_kickoff < target_kickoff
    return candidate_kickoff <= target_kickoff


def forecast_cutoff_for(kickoff_unix: int) -> int:
    """The as-of cutoff used by the supported walk-forward: the kickoff itself.

    Features must come from fixtures strictly before this cutoff.
    """
    return int(kickoff_unix)
