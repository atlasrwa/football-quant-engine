"""De-vigged pre-match corner market benchmark for Experiment B (Phase B10).

Reads FootyStats pre-match corner over/under odds from the champion corpus and
returns fair P(over) per (fixture_id, line) after multiplicative de-vig (reusing
the PR #4 devig module). These are PRE-MATCH prices used only as an external
benchmark; they are NEVER fed into either statistical arm. Genuine closing is
not available on this corpus and is not fabricated.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from src.research.experiments.provider_comparison.market import market_over_prob

# FootyStats corner odds keys per line present in the corpus.
_CORNER_ODDS_KEYS = {
    7.5: ("odds_corners_over_75", "odds_corners_under_75"),
    8.5: ("odds_corners_over_85", "odds_corners_under_85"),
    9.5: ("odds_corners_over_95", "odds_corners_under_95"),
    10.5: ("odds_corners_over_105", "odds_corners_under_105"),
}


def _fixture_id(match: Mapping[str, object]) -> str:
    for key in ("id", "match_id", "fixture_id"):
        v = match.get(key)
        if v is not None and str(v) != "":
            return str(v)
    return (
        f"{match.get('_league')}:{match.get('date_unix')}:"
        f"{match.get('homeID')}:{match.get('awayID')}"
    )


def build_corner_market(
    matches: Sequence[Mapping[str, object]],
) -> dict[tuple[str, float], float]:
    """Return {(fixture_id, line) -> fair P(over)} for available corner odds."""
    out: dict[tuple[str, float], float] = {}
    for m in matches:
        fid = _fixture_id(m)
        for line, (ok, uk) in _CORNER_ODDS_KEYS.items():
            p, _orr = market_over_prob(m.get(ok), m.get(uk))
            if p is not None:
                out[(fid, line)] = p
    return out
