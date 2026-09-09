"""Market benchmark (Phase 11).

Builds a de-vigged pre-match probability benchmark from FootyStats bookmaker
odds embedded in each corpus match. Used ONLY as an external benchmark; these
odds are NEVER fed into the statistical model.

Temporal honesty:
- These are PRE-MATCH prices (available before kickoff), used as the
  forecast-time market benchmark. FootyStats provides no capture timestamp and
  no genuine close, so the benchmark is labelled MARKET_PRE_MATCH.
- GENUINE closing / LAST_BEFORE_KICKOFF is UNSUPPORTED on this dataset (the
  timestamped odds captures do not overlap the fixtures with stats). We do NOT
  fabricate a close from any "last_seen"-type value. Closing/CLV is reported as
  UNSUPPORTED.

De-vig uses the merged PR #3 module (reconciliation.devig), multiplicative by
default, so the two-way over/under fair probabilities sum to 1.
"""

from __future__ import annotations

import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.research.reconciliation.devig import devig

# FootyStats odds keys per market/line.
_MARKET_ODDS_KEYS = {
    ("GOALS_TOTAL", 2.5): ("odds_ft_over25", "odds_ft_under25"),
    ("CORNERS_TOTAL", 9.5): ("odds_corners_over_95", "odds_corners_under_95"),
    ("CORNERS_TOTAL", 10.5): ("odds_corners_over_105", "odds_corners_under_105"),
    ("CORNERS_TOTAL", 11.5): ("odds_corners_over_115", "odds_corners_under_115"),
}
_BTTS_KEYS = ("odds_btts_yes", "odds_btts_no")


def _valid_odds(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 1.0 else None  # 0/<=1.0 = NULL (market not available)


@dataclass(frozen=True)
class MarketBenchmark:
    """De-vigged pre-match market probability for one fixture/market/line."""
    fixture_key: int
    market: str
    line: Optional[float]
    prob_over: Optional[float]     # fair P(over) after de-vig
    overround: Optional[float]
    semantics: str = "MARKET_PRE_MATCH"  # never CLOSING on this dataset


def market_over_prob(over_odds, under_odds) -> tuple[Optional[float], Optional[float]]:
    """De-vig a two-way over/under market -> (fair P(over), overround)."""
    o = _valid_odds(over_odds)
    u = _valid_odds(under_odds)
    if o is None or u is None:
        return None, None
    res = devig({"OVER": o, "UNDER": u})  # multiplicative
    return res.fair_probabilities["OVER"], res.overround


def build_market_benchmarks_by_fs_id(
    fs_match_ids: set[int],
    *,
    fs_corpus_glob: str = "data/discovery/corpus/league-matches*",
    root: str | Path = ".",
) -> dict[tuple[int, str, Optional[float]], MarketBenchmark]:
    """Load de-vigged pre-match benchmarks for the given FootyStats match ids.

    Returns {(fixture_key, market, line) -> MarketBenchmark}. Only fixtures with
    valid odds are included (NULL != ZERO; missing markets are simply absent).
    """
    root = Path(root)
    out: dict[tuple[int, str, Optional[float]], MarketBenchmark] = {}
    for cf in glob.glob(str(root / fs_corpus_glob)):
        d = json.loads(Path(cf).read_text())
        recs = d.get("data", d) if isinstance(d, dict) else d
        if not isinstance(recs, list):
            continue
        for m in recs:
            fid = int(m.get("id", 0))
            if fid not in fs_match_ids:
                continue
            for (market, line), (ok, uk) in _MARKET_ODDS_KEYS.items():
                p, orr = market_over_prob(m.get(ok), m.get(uk))
                if p is not None:
                    out[(fid, market, line)] = MarketBenchmark(fid, market, line, p, orr)
            # BTTS (yes/no) -> treat "over" as YES
            y = _valid_odds(m.get(_BTTS_KEYS[0]))
            n = _valid_odds(m.get(_BTTS_KEYS[1]))
            if y is not None and n is not None:
                res = devig({"YES": y, "NO": n})
                out[(fid, "BTTS", None)] = MarketBenchmark(
                    fid, "BTTS", None, res.fair_probabilities["YES"], res.overround
                )
    return out
