"""V7.1 PIT-safe corpus index (`v71_index_v1`).

Loads the frozen TheStatsAPI corpus and exposes exactly the reads the compiler needs, with
point-in-time safety enforced STRUCTURALLY rather than by convention: every accessor takes a
reference record position and can only see strictly-earlier observations.

It also loads the V7.1 FRESH seasons (tags `f27_*`) alongside the historical corpus, so a
2026/27 fixture can be measured against genuine prior history without the historical corpus
identity changing. Which fixtures are HISTORY and which are CONFIRMATORY is not a property of
this index -- it is decided by the frozen fresh-sample manifest.

ZERO SPEND. Cache-only. No network.
"""
from __future__ import annotations

import bisect
import os
import sys

sys.path.insert(0, "/home/ubuntu/scripts")

INDEX_VERSION = "v71_index_v1"

#: The V7.1 fresh seasons: (tag, competition tag used in the index, season id).
#: `competition` deliberately reuses the SAME six competition labels as the historical corpus
#: so a team's history spans the season boundary; the season id is what makes a fixture fresh.
FRESH_SEASONS = (
    ("f27_champ", "champ", "sn_3014533"),
    ("f27_epl", "epl", "sn_8406098"),
    ("f27_laliga", "laliga", "sn_8407970"),
    ("f27_laliga2", "laliga2", "sn_1368511"),
    ("f27_ligue1", "ligue1", "sn_3011424"),
    ("f27_ligue2", "ligue2", "sn_7255696"),
)


def load_records(*, include_fresh: bool = True):
    """Historical corpus records, plus the fresh 2026/27 season records when asked.

    The historical half is `src.research.matchup.corpus.load_corpus()` unchanged, so the
    corpus V7 measured is byte-identically the corpus V7.1 uses for history.
    """
    from src.research.matchup import corpus as MC

    recs = list(MC.load_corpus())
    if not include_fresh:
        return recs

    import json

    import championship_adapter as adapt          # noqa: E402
    import multisrc_corpus as msc                 # noqa: E402

    # The mapping is NOT re-derived here: every step below calls the same helper the frozen
    # historical loader calls, in the same order, with the same admission filters. A fresh
    # record is therefore byte-shaped identically to a historical one.
    for tag, competition, season in FRESH_SEASONS:
        fp = f"{msc.CACHE}/_all_fixtures_{tag}_{season}.json"
        if not os.path.exists(fp):
            continue
        for fx in json.load(open(fp))["fixtures"]:
            status = str(fx.get("status", "")).lower()
            score = fx.get("score") or {}
            if status not in ("finished", "complete", "played"):
                continue
            if score.get("home") is None or score.get("away") is None:
                continue
            spath = f"{msc.CACHE}/{tag}_stats_{fx['id']}.json"
            if not os.path.exists(spath):
                continue
            sj = json.load(open(spath))
            adapted = adapt.adapt_match(msc._to_adapter_shape(fx), sj)
            recs.append(MC.MatchRecord(
                fixture_id=str(fx["id"]), competition=competition,
                competition_id=str(fx.get("competition_id") or ""), season_id=str(season),
                kickoff_unix=int(adapted["date_unix"]),
                home=adapted["home_name"], away=adapted["away_name"],
                home_id=str(adapted.get("home_id")), away_id=str(adapted.get("away_id")),
                base=adapted, rich=adapted.get("_rich") or {},
                extra=MC._extra_pairs((sj or {}).get("data", {}))))
    recs.sort(key=lambda r: (int(r.kickoff_unix), str(r.fixture_id)))
    return recs


class PITIndex:
    """Chronological corpus index with O(1) point-in-time team means.

    Structural PIT guarantee: every read is keyed by a record POSITION in the chronological
    order, and a team's prefix caches are cumulative over that order, so an accessor
    physically cannot reach an observation at or after the reference position.
    """

    def __init__(self, records, metrics, metric_contract):
        self.recs = sorted(records, key=lambda r: (int(r.kickoff_unix), str(r.fixture_id)))
        self.kick = [int(r.kickoff_unix) for r in self.recs]
        self.pos_of_fixture = {str(r.fixture_id): i for i, r in enumerate(self.recs)}
        self.metrics = tuple(sorted(metrics))
        self._contract = metric_contract
        self.vals = {m: [self._read(r, m) for r in self.recs] for m in self.metrics}
        self.series, self.pos = {}, {}
        for i, r in enumerate(self.recs):
            for tid, is_home in ((str(r.home_id), True), (str(r.away_id), False)):
                s = self.series.setdefault(tid, [])
                self.pos[(tid, i)] = len(s)
                s.append((i, int(r.kickoff_unix), r.competition, is_home,
                          str(r.away_id) if is_home else str(r.home_id)))
        self.comp_idx = {}
        for i, r in enumerate(self.recs):
            self.comp_idx.setdefault(r.competition, []).append(i)
        self._pref = {}
        self.comp_cum = {}
        for comp, idxs in self.comp_idx.items():
            for m in self.metrics:
                cs, cn, tot, cnt = [], [], 0.0, 0
                for i in idxs:
                    pair = self.vals[m][i]
                    if pair is not None:
                        tot += pair[0] + pair[1]
                        cnt += 2
                    cs.append(tot)
                    cn.append(cnt)
                self.comp_cum[(comp, m)] = (cs, cn)

    # ---- raw reads ---------------------------------------------------------------------
    def _read(self, rec, metric):
        row = self._contract.get(metric)
        if not row or not row.get("block"):
            return None
        blk, fld = row["block"], row["field"]
        if blk == "base":
            b = rec.base or {}
            h, a = b.get(fld), b.get(row.get("field_away"))
        else:
            pair = (getattr(rec, blk, None) or {}).get(fld)
            if not pair:
                return None
            h, a = pair
        try:
            return (float(h), float(a)) if (h is not None and a is not None) else None
        except (TypeError, ValueError):
            return None

    def team_value(self, rec_i, team_id, metric, perspective):
        """The team's own (`FOR`) or conceded (`AGAINST`) value in that match."""
        pair = self.vals[metric][rec_i]
        if pair is None:
            return None
        r = self.recs[rec_i]
        own, opp = (pair[0], pair[1]) if str(r.home_id) == str(team_id) else (pair[1],
                                                                             pair[0])
        return own if perspective == "FOR" else opp

    # ---- PIT accessors ------------------------------------------------------------------
    def prior_entries(self, team_id, before_rec_i):
        """The team's own series entries STRICTLY before `before_rec_i`."""
        s = self.series.get(str(team_id))
        if not s:
            return []
        p = self.pos.get((str(team_id), before_rec_i))
        if p is None:
            # the team does not appear in the reference fixture: fall back to a timestamp cut
            ref = self.kick[before_rec_i]
            return [e for e in s if e[1] < ref]
        return s[:p]

    def _prefix(self, team_id, metric, perspective, venue=None):
        key = (str(team_id), metric, perspective, venue)
        got = self._pref.get(key)
        if got is not None:
            return got
        cs, cn, tot, cnt = [], [], 0.0, 0
        for (i, _k, _c, is_home, _o) in self.series.get(str(team_id), []):
            if venue is None or is_home == venue:
                v = self.team_value(i, team_id, metric, perspective)
                if v is not None:
                    tot += v
                    cnt += 1
            cs.append(tot)
            cn.append(cnt)
        self._pref[key] = (cs, cn)
        return self._pref[key]

    def pit_mean(self, team_id, metric, perspective, before_rec_i, venue=None):
        """(mean, n) over the team's matches strictly before `before_rec_i`. O(1)."""
        p = self.pos.get((str(team_id), before_rec_i))
        if not p:
            return (None, 0)
        cs, cn = self._prefix(team_id, metric, perspective, venue)
        n = cn[p - 1]
        return ((cs[p - 1] / n, n) if n > 0 else (None, 0))

    def env_mean(self, competition, metric, cutoff_unix):
        """Competition-season environment mean strictly before `cutoff_unix`."""
        idxs = self.comp_idx.get(competition)
        if not idxs:
            return None
        ks = [self.kick[i] for i in idxs]
        j = bisect.bisect_left(ks, cutoff_unix)
        if j == 0:
            return None
        cs, cn = self.comp_cum[(competition, metric)]
        return (cs[j - 1] / cn[j - 1]) if cn[j - 1] > 0 else None

    def range_positions(self, lo_unix, hi_unix):
        return range(bisect.bisect_left(self.kick, lo_unix),
                     bisect.bisect_left(self.kick, hi_unix))


def version_stamp() -> dict:
    return {"index_version": INDEX_VERSION,
            "fresh_seasons": [{"tag": t, "competition": c, "season_id": s}
                              for t, c, s in FRESH_SEASONS],
            "pit_guarantee": ("every accessor is keyed by chronological record position; a "
                              "prefix cache cannot reach an observation at or after the "
                              "reference position"),
            "network": False}
