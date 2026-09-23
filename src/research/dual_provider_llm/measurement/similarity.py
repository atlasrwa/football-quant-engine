"""Deterministic opponent/state profiles, distance and neighbour selection.

Similarity method (frozen): robust-standardized Euclidean distance.
  * each observation -> competition-relative robust z (median / 1.4826 x MAD of that
    competition's team-match values strictly before the query time);
  * profile = per-dimension mean of z over the last PROFILE_WINDOW_MATCHES venue-matched prior
    matches, each dimension needing >= MIN_PROFILE_MATCHES_PER_DIM non-null values, ALL
    dimensions required (no partial profiles, no imputation);
  * distance = sqrt(mean_j (p_j - q_j)^2)  (RMS over dimensions, so it is comparable across
    hypotheses with different dimension counts);
  * neighbours = the nearest max(MIN_SIMILAR_MATCHES, ceil(n / 3)) subject matches, ties broken
    by (kickoff, match_id).
No LLM similarity score; no outcome participates.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from src.research.dual_provider_llm.measurement import support as S
from src.research.dual_provider_llm.measurement.pit_history import PITHistory, TeamMatch

Dim = Tuple[str, str]           # (metric, FOR|AGAINST)


def profile(hist: PITHistory, team_id: str, before: int, venue: Optional[str],
            dims: Sequence[Dim], by_venue: bool = False
            ) -> Tuple[Optional[Dict[Dim, float]], Dict[str, object]]:
    rows = hist.team_rows(team_id, before, venue=venue,
                          n=int(S.value("PROFILE_WINDOW_MATCHES")))
    out: Dict[Dim, float] = {}
    meta: Dict[str, object] = {"n_window_matches": len(rows),
                               "window_match_ids": [r.match_id for r in rows]}
    for d in dims:
        zs = [z for r in rows for z in [hist.z(r, d[0], d[1], before, by_venue)] if z is not None]
        meta[f"n_{d[0]}_{d[1]}"] = len(zs)
        if len(zs) < S.value("MIN_PROFILE_MATCHES_PER_DIM"):
            meta["missing_dim"] = f"{d[0]}.{d[1]}"
            return None, meta
        out[d] = sum(zs) / len(zs)
    return out, meta


def rms_distance(p: Dict[Dim, float], q: Dict[Dim, float], dims: Sequence[Dim]) -> float:
    return math.sqrt(sum((p[d] - q[d]) ** 2 for d in dims) / len(dims))


def nearest(items: Sequence[Tuple[str, float, int]], k: int) -> Tuple[List[str], List[str]]:
    """items = (key, distance, kickoff); returns (k nearest keys, rest) deterministically."""
    nd = int(S.value("DISTANCE_ROUND_DECIMALS"))
    ordered = sorted(items, key=lambda t: (round(t[1], nd), t[2], t[0]))
    keys = [t[0] for t in ordered]
    return keys[:k], keys[k:]


def state_vector(hist: PITHistory, row: TeamMatch, dims: Sequence[Dim], before: int,
                 by_venue: bool) -> Optional[Dict[Dim, float]]:
    """In-match state of one team-match (all dims required)."""
    out = {}
    for d in dims:
        z = hist.z(row, d[0], d[1], before, by_venue)
        if z is None:
            return None
        out[d] = z
    return out


def shrink(recent: Dict[Dim, float], reference: Dict[Dim, float], n_recent: int
           ) -> Dict[Dim, float]:
    k = S.value("SHRINKAGE_KAPPA")
    w = n_recent / (n_recent + k)
    return {d: w * recent[d] + (1 - w) * reference[d] for d in recent}
