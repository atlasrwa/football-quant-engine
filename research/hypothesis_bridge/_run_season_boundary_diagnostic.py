"""Real-corpus structural diagnostic for the season-boundary repair. ZERO SPEND.

The exposed-50 cohort contains no season-boundary fixture, so it does not exercise the
repair. This scans the whole local corpus for (fixture, team) pairs where

    current_season(team, kickoff)  !=  target_season(fixture)

i.e. the team's last-played season differs from the season the fixture belongs to, and
contrasts what the OLD semantic would have made available against what the CORRECTED
semantic does.

No outcome is evaluated and no performance is computed. Derived diagnostics only -- no raw
rows leave the machine.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.realpath(os.path.join(_HERE, os.pardir, os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src._repo_paths import ensure_repo_importable, ensure_scripts_importable
ensure_repo_importable()
ensure_scripts_importable()

from src.research.matchup.corpus import load_corpus
from src.research.llm_matchup import cohorts as CH

OUT = os.path.join(_HERE, "SEASON_BOUNDARY_REAL_CORPUS_DIAGNOSTIC_V1.json")
MIN = CH.MIN_HISTORY


def _anon(value: str) -> str:
    """Derived, stable identifier. Enough to audit a case without emitting a raw id."""
    return hashlib.sha256(str(value).encode()).hexdigest()[:12]


def main() -> int:
    recs = load_corpus()
    idx = CH.HistoryIndex(recs)

    n_pairs = n_boundary = 0
    n_old_stale = n_new_abstain = n_new_valid = 0
    samples, by_competition = [], Counter()

    for target in recs:
        target_season = CH.HistoryIndex.target_season(target)
        for team in (target.home_id, target.away_id):
            n_pairs += 1
            last_played = idx.current_season(team, target.kickoff_unix)
            if last_played is None or last_played == target_season:
                continue
            n_boundary += 1
            by_competition[target.competition] += 1

            # OLD semantic: history filtered by the season the team last played in.
            old_rows = idx.prior_records(team, target.kickoff_unix, last_played)
            # CORRECTED semantic: history filtered by the TARGET fixture's season.
            new_rows = idx.prior_records(team, target.kickoff_unix, target_season)

            old_supported = len(old_rows) >= MIN
            if old_supported:
                n_old_stale += 1
            if not new_rows:
                n_new_abstain += 1
            elif len(new_rows) >= MIN:
                n_new_valid += 1

            if len(samples) < 12 and old_supported:
                samples.append({
                    "fixture_ref": _anon(target.fixture_id),
                    "team_ref": _anon(team),
                    "competition": target.competition,
                    "target_season_ref": _anon(target_season),
                    "last_played_season_ref": _anon(last_played),
                    "old_semantic_prior_rows": len(old_rows),
                    "old_semantic_met_support_floor": old_supported,
                    "new_semantic_prior_rows": len(new_rows),
                    "new_semantic_outcome": ("ABSTAIN" if not new_rows else
                                             "VALID" if len(new_rows) >= MIN else
                                             "INSUFFICIENT_SUPPORT"),
                })

    report = {
        "artifact": "SEASON_BOUNDARY_REAL_CORPUS_DIAGNOSTIC_V1",
        "CLASSIFICATION": "DEVELOPMENT_REAL_CORPUS_STRUCTURAL_DIAGNOSTIC",
        "purpose": ("establish that the OLD semantic let prior-season history satisfy "
                    "current-season support, and that the CORRECTED semantic uses "
                    "target-season history only, abstaining when there is none"),
        "not_measured": ["outcomes", "performance", "effect size", "probability", "EV"],
        "support_floor_MIN_HISTORY": MIN,
        "N_CORPUS_FIXTURES": len(recs),
        "N_TEAM_TARGET_PAIRS": n_pairs,
        "N_SEASON_BOUNDARY_PAIRS": n_boundary,
        "N_OLD_SEMANTIC_STALE_SUPPORT": n_old_stale,
        "N_NEW_SEMANTIC_ABSTAIN": n_new_abstain,
        "N_NEW_SEMANTIC_VALID_TARGET_SEASON": n_new_valid,
        "boundary_pairs_by_competition": dict(sorted(by_competition.items())),
        "audit_samples_derived_only": samples,
        "RAW_CORPUS_EXPORTED": False,
        "LIVE_SONNET_CALLS": 0,
        "BEDROCK_PAID_CALLS": 0,
        "NEW_SONNET_SPEND_USD": 0,
    }
    json.dump(report, open(OUT, "w"), indent=2, default=str)
    print(json.dumps({k: v for k, v in report.items() if k != "audit_samples_derived_only"},
                     indent=2, default=str))
    print(f"\naudit samples (derived refs only): {len(samples)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
