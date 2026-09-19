"""PIT-safe referee & league-environment context from the FootyStats corpus.

Referee data is NOT present in the TheStatsAPI rich corpus (would need the uncached
/matches/{id}/referee endpoint), but the FootyStats corpus carries `refereeID` at ~83%.
This module builds a shrunk, leakage-safe referee cards tendency and a league card
environment on the FootyStats corpus, for the cards-specific referee experiment.

Shrinkage: referee mean shrunk toward the competition mean by effective sample size.
Strictly PIT: for fixture F, only matches with date_unix < F.date_unix are used.
"""
from __future__ import annotations
import sys
from collections import defaultdict
from typing import Optional
import numpy as np
sys.path.insert(0, "/home/ubuntu/scripts")
import pilotC_stat_mixer as mix   # reuse load_corpus (FootyStats, status==complete)


def _total_cards(m):
    a = m.get("team_a_cards_num"); b = m.get("team_b_cards_num")
    if a in (None, -1) or b in (None, -1):
        ya, yb = m.get("team_a_yellow_cards"), m.get("team_b_yellow_cards")
        if ya in (None, -1) or yb in (None, -1):
            return None
        a = (ya or 0) + (m.get("team_a_red_cards") or 0)
        b = (yb or 0) + (m.get("team_b_red_cards") or 0)
    return a + b


class RefereeLeagueContext:
    """Incremental PIT context: for each match in time order, snapshot the referee's
    prior mean cards (shrunk to league prior) and the league prior itself."""
    def __init__(self, ms=None, shrink=5.0):
        self.shrink = shrink
        ms = ms if ms is not None else mix.load_corpus()
        self.ref_snap: dict = {}       # match_id -> shrunk referee cards tendency
        self.league_snap: dict = {}    # match_id -> league (competition) prior cards
        ref_sum = defaultdict(float); ref_cnt = defaultdict(int)
        comp_sum = defaultdict(float); comp_cnt = defaultdict(int)
        glob_sum = 0.0; glob_cnt = 0
        for m in ms:  # already sorted by date_unix in load_corpus
            tc = _total_cards(m)
            comp = str(m.get("competition_id"))
            ref = m.get("refereeID")
            mid = m.get("id")
            # SNAPSHOT before update
            league_prior = (comp_sum[comp] / comp_cnt[comp]) if comp_cnt[comp] > 0 else (
                (glob_sum / glob_cnt) if glob_cnt > 0 else None)
            self.league_snap[mid] = league_prior
            if ref not in (None, -1, 0) and ref_cnt[ref] > 0 and league_prior is not None:
                rmean = ref_sum[ref] / ref_cnt[ref]
                w = ref_cnt[ref] / (ref_cnt[ref] + shrink)
                self.ref_snap[mid] = w * rmean + (1 - w) * league_prior
            else:
                self.ref_snap[mid] = league_prior  # fall back to league prior
            # UPDATE
            if tc is not None:
                comp_sum[comp] += tc; comp_cnt[comp] += 1
                glob_sum += tc; glob_cnt += 1
                if ref not in (None, -1, 0):
                    ref_sum[ref] += tc; ref_cnt[ref] += 1

    def referee_tendency(self, match_id) -> Optional[float]:
        return self.ref_snap.get(match_id)

    def league_cards(self, match_id) -> Optional[float]:
        return self.league_snap.get(match_id)


if __name__ == "__main__":
    ctx = RefereeLeagueContext()
    vals = [v for v in ctx.ref_snap.values() if v is not None]
    print(f"referee tendency populated for {len(vals)} matches, mean={np.mean(vals):.2f}, "
          f"p05={np.percentile(vals,5):.2f} p95={np.percentile(vals,95):.2f}")
