"""Generic panel-template compiler: instantiate a structured feature template on ANY historical
fixture using only matches strictly before that fixture's kickoff.

Style vs strength (frozen): similarity uses STYLE dimensions only (competition-relative robust
z of rolling means); strength (prior same-competition goal difference) is NEVER a similarity
dimension and enters the models as a separate covariate for both M0 and M1. The panel reports
the style-strength correlation of every similarity/profile dimension as a diagnostic.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

PANEL_VERSION = "target_aware_panel_compiler_v1"

MIN_WINDOW = {"W5": 5, "W10": 10, "SEASON_TO_DATE": 3, "VENUE_SEASON_TO_DATE": 3}
WINDOW_N = {"W5": 5, "W10": 10, "SEASON_TO_DATE": None, "VENUE_SEASON_TO_DATE": None}
MIN_REFERENCE_OBS = 200
MAD_TO_SD = 1.4826
PROFILE_WINDOW = 10            # opponent style profile: last 10 venue-matched matches
MIN_PROFILE_PER_DIM = 5
MIN_SIMILARITY_HISTORY = 15    # subject team prior matches needed for a similarity feature
NEIGHBOR_FRACTION = 1 / 3
MIN_NEIGHBORS = 5
SHRINKAGE_KAPPA = 5
RECENT_STATE_N = 5
MIN_LONG_RUN_STATE = 5
STRENGTH_WINDOW = 10
MIN_STRENGTH = 5


class PITViolation(RuntimeError):
    pass


@dataclass(frozen=True)
class Row:
    """One team's view of one completed match. values[(metric, period)] = (for, against)."""
    match_id: str
    kickoff: int
    competition_id: str
    season_id: str
    team_id: str
    opponent_id: str
    venue: str
    values: Tuple[Tuple[Tuple[str, str], Tuple[Optional[float], Optional[float]]], ...]

    def get(self, metric: str, perspective: str, period: str = "FULL_MATCH") -> Optional[float]:
        for (m, p), (f, a) in self.values:
            if m == metric and p == period:
                v = f if perspective == "FOR" else a
                return None if v is None else float(v)
        return None


class PanelHistory:
    def __init__(self, rows: Sequence[Row], panel_end_unix: int):
        self.end = int(panel_end_unix)
        self.rows = sorted((r for r in rows if r.kickoff <= self.end),
                           key=lambda r: (r.kickoff, r.match_id, r.team_id))
        self.by_team: Dict[str, List[Row]] = {}
        self.by_comp: Dict[str, List[Row]] = {}
        self._ref: Dict[tuple, Optional[Tuple[float, float]]] = {}
        for r in self.rows:
            self.by_team.setdefault(r.team_id, []).append(r)
            self.by_comp.setdefault(r.competition_id, []).append(r)

    def prior(self, team: str, before: int, venue: Optional[str] = None) -> List[Row]:
        if before > self.end + 1:
            raise PITViolation(f"query time {before} beyond the panel end {self.end}")
        return [r for r in self.by_team.get(team, []) if r.kickoff < before
                and (venue is None or r.venue == venue)]

    def reference(self, metric, period, comp, before) -> Optional[Tuple[float, float]]:
        key = (metric, period, comp, before)
        if key not in self._ref:
            self._ref[key] = self._reference(metric, period, comp, before)
        return self._ref[key]

    def _reference(self, metric, period, comp, before) -> Optional[Tuple[float, float]]:
        vals = np.array([v for r in self.by_comp.get(comp, []) if r.kickoff < before
                         for v in [r.get(metric, "FOR", period)] if v is not None], float)
        if len(vals) < MIN_REFERENCE_OBS:
            return None
        med = float(np.median(vals))
        sc = float(np.median(np.abs(vals - med))) * MAD_TO_SD
        if sc <= 0:
            q1, q3 = np.percentile(vals, [25, 75])
            sc = float(q3 - q1) / 1.349
        return (med, sc) if sc > 0 else None

    def strength(self, team: str, comp: str, before: int) -> Optional[float]:
        rows = [r for r in self.prior(team, before) if r.competition_id == comp][-STRENGTH_WINDOW:]
        gd = [r.get("goals", "FOR") - r.get("goals", "AGAINST") for r in rows
              if r.get("goals", "FOR") is not None and r.get("goals", "AGAINST") is not None]
        return float(np.mean(gd)) if len(gd) >= MIN_STRENGTH else None


def _current_season(rows: List[Row]) -> List[Row]:
    if not rows:
        return []
    key = (rows[-1].competition_id, rows[-1].season_id)
    return [r for r in rows if (r.competition_id, r.season_id) == key]


def rolling(h: PanelHistory, team: str, venue_now: str, c: Dict[str, Any], before: int
            ) -> Optional[float]:
    rows = _current_season(h.prior(team, before))
    if c["window"] == "VENUE_SEASON_TO_DATE":
        rows = [r for r in rows if r.venue == venue_now]
    n = WINDOW_N[c["window"]]
    rows = rows[-n:] if n else rows
    if len(rows) < MIN_WINDOW[c["window"]]:
        return None
    vals = [r.get(c["metric"], c["perspective"], c.get("period", "FULL_MATCH")) for r in rows]
    if any(v is None for v in vals):
        vals = [v for v in vals if v is not None]
        if len(vals) < MIN_WINDOW[c["window"]]:
            return None
    return float(np.mean(vals))


def _z(h, value, metric, period, comp, before):
    if value is None:
        return None
    ref = h.reference(metric, period, comp, before)
    return None if ref is None else (value - ref[0]) / ref[1]


def _team(fx, side):
    return fx["home_team_id"] if side == "HOME" else fx["away_team_id"]


def _venue(side):
    return "HOME" if side == "HOME" else "AWAY"


def comp_z(h, fx, c):
    v = rolling(h, _team(fx, c["side"]), _venue(c["side"]), c, fx["kickoff"])
    return _z(h, v, c["metric"], c.get("period", "FULL_MATCH"), fx["competition_id"],
              fx["kickoff"])


def style_profile(h, team, venue, dims, before, comp) -> Optional[Dict[Tuple[str, str], float]]:
    rows = h.prior(team, before, venue=venue)[-PROFILE_WINDOW:]
    out = {}
    for d in dims:
        key = (d["metric"], d["perspective"])
        zs = [z for r in rows for z in [_z(h, r.get(*key), d["metric"], "FULL_MATCH",
                                           r.competition_id, before)] if z is not None]
        if len(zs) < MIN_PROFILE_PER_DIM:
            return None
        out[key] = float(np.mean(zs))
    return out


def instantiate(template: Dict[str, Any], h: PanelHistory, fx: Dict[str, Any]
                ) -> Optional[float]:
    """Feature value for historical fixture fx = {match_id, kickoff, competition_id,
    home_team_id, away_team_id}. Reads only rows with kickoff < fx['kickoff']."""
    tt, comb = template["template_type"], template["combine"]
    comps = template.get("components", [])
    if tt == "ROLLING_PROFILE":
        return comp_z(h, fx, comps[0])
    if tt == "PAIRWISE_COMBINATION":
        a, b = comp_z(h, fx, comps[0]), comp_z(h, fx, comps[1])
        if a is None or b is None:
            return None
        return {"SUM": a + b, "DIFFERENCE": a - b, "PRODUCT": a * b,
                "RATIO": (a / b if abs(b) > 1e-9 else None)}[comb]
    if tt == "MULTI_DIMENSION_MATCHUP":
        prods = []
        for a, b in zip(comps[::2], comps[1::2]):
            za, zb = comp_z(h, fx, a), comp_z(h, fx, b)
            if za is None or zb is None:
                return None
            prods.append(za * zb)
        return float(np.mean(prods))
    if tt == "OPPONENT_SIMILARITY_CONDITIONAL":
        d = similarity_detail(template, h, fx)
        return None if d is None else d["value"]
    if tt == "STATE_DEVIATION":
        return _state_deviation(template, h, fx)
    raise ValueError(f"unknown template {tt}")


def similarity_detail(template, h: PanelHistory, fx) -> Optional[Dict[str, Any]]:
    """Opponent-similarity feature plus its style-strength diagnostic: mean prior strength of
    the neighbour opponents vs all prior opponents (strength never enters the distance)."""
    s = template["similarity"]
    subj, other = _team(fx, s["subject_side"]), _team(fx, s["profile_side"])
    q = style_profile(h, other, _venue(s["profile_side"]), s["profile_dimensions"],
                      fx["kickoff"], fx["competition_id"])
    if q is None:
        return None
    past = h.prior(subj, fx["kickoff"], venue=_venue(s["subject_side"]))
    cand = []
    for r in past:
        p = style_profile(h, r.opponent_id, "AWAY" if r.venue == "HOME" else "HOME",
                          s["profile_dimensions"], r.kickoff, r.competition_id)
        y = _z(h, r.get(s["subject_metric"], s["subject_perspective"]), s["subject_metric"],
               "FULL_MATCH", r.competition_id, r.kickoff)
        if p is not None and y is not None:
            d = math.sqrt(sum((p[k] - q[k]) ** 2 for k in q) / len(q))
            cand.append((round(d, 12), r.kickoff, r.match_id, y))
    if len(cand) < MIN_SIMILARITY_HISTORY:
        return None
    cand.sort()
    k = max(MIN_NEIGHBORS, int(math.ceil(len(cand) * NEIGHBOR_FRACTION)))
    near = [c[3] for c in cand[:k]]
    base = float(np.mean([c[3] for c in cand]))
    w = len(near) / (len(near) + SHRINKAGE_KAPPA)
    by_id = {r.match_id: r for r in past}

    def mean_strength(ids):
        v = [h.strength(by_id[i].opponent_id, by_id[i].competition_id, by_id[i].kickoff)
             for i in ids]
        v = [x for x in v if x is not None]
        return float(np.mean(v)) if v else None
    return {"value": w * (float(np.mean(near)) - base), "n_neighbors": len(near),
            "n_history": len(cand), "neighbor_ids": [c[2] for c in cand[:k]],
            "diagnostic": {"neighbor_opponent_strength_mean":
                           mean_strength([c[2] for c in cand[:k]]),
                           "all_opponent_strength_mean": mean_strength([c[2] for c in cand])}}


def _state_deviation(template, h: PanelHistory, fx) -> Optional[float]:
    st = template["state"]
    team = _team(fx, st["side"])
    rows = _current_season(h.prior(team, fx["kickoff"]))
    recent, longrun = rows[-RECENT_STATE_N:], rows[:-RECENT_STATE_N]
    if len(recent) < RECENT_STATE_N or len(longrun) < MIN_LONG_RUN_STATE:
        return None
    devs = []
    for d in st["dimensions"]:
        def zmean(rs):
            zs = [z for r in rs for z in [_z(h, r.get(d["metric"], d["perspective"]),
                                             d["metric"], "FULL_MATCH", r.competition_id,
                                             fx["kickoff"])] if z is not None]
            return float(np.mean(zs)) if zs else None
        a, b = zmean(recent), zmean(longrun)
        if a is None or b is None:
            return None
        devs.append(a - b)
    return float(np.mean(devs))


def style_strength_correlation(h: PanelHistory, fixtures: Sequence[Dict[str, Any]],
                               dims: Sequence[Dict[str, str]], side: str) -> Dict[str, Any]:
    """Diagnostic: Pearson correlation of each style dimension with prior strength across the
    given fixtures (all PIT). Reported, never used to select anything."""
    out = {}
    for d in dims:
        xs, ys = [], []
        for fx in fixtures:
            team = _team(fx, side)
            p = style_profile(h, team, _venue(side), [d], fx["kickoff"], fx["competition_id"])
            st = h.strength(team, fx["competition_id"], fx["kickoff"])
            if p is not None and st is not None:
                xs.append(list(p.values())[0])
                ys.append(st)
        out[f"{d['metric']}.{d['perspective']}"] = (
            {"n": len(xs), "pearson_r": float(np.corrcoef(xs, ys)[0, 1])} if len(xs) >= 10
            else {"n": len(xs), "pearson_r": None})
    return out


def rows_from_history(history: Dict[str, Any]) -> List[Row]:
    """Panel rows from normalized pilot HistoryMatch objects (+ verified half-level cells)."""
    from src.research.target_aware_market_panel.policy import HALF_PROVIDER_FIELDS
    from src.research.thestatsapi.normalizer import _cell
    out = []
    for hm in history.values():
        home, away = hm.fixture.get("home_team") or {}, hm.fixture.get("away_team") or {}
        sd = (hm.stats or {}).get("data") or {}
        for team, opp, fs, ag, venue in ((home, away, "home", "away", "HOME"),
                                         (away, home, "away", "home", "AWAY")):
            if hm.fixture.get("is_neutral"):
                venue = "NEUTRAL"
            vals = [((c, "FULL_MATCH"), (hm.values[c][fs], hm.values[c][ag]))
                    for c in sorted(hm.values)]
            for m, (grp, key) in sorted(HALF_PROVIDER_FIELDS.items()):
                for per, pk in (("FIRST_HALF", "first_half"), ("SECOND_HALF", "second_half")):
                    vals.append(((m, per), (_cell(sd, grp, key, pk, fs),
                                            _cell(sd, grp, key, pk, ag))))
            out.append(Row(hm.match_id, int(hm.kickoff_unix),
                           str(hm.fixture.get("competition_id")),
                           str(hm.fixture.get("season_id")), str(team.get("id")),
                           str(opp.get("id")), venue, tuple(vals)))
    return out


def build_fold_manifest(fixtures: Sequence[Dict[str, Any]], cohort_team_ids: Sequence[str]
                        ) -> Dict[str, Any]:
    """Frozen walk-forward folds over panel fixtures (ids, kickoffs, teams only; no outcome).
    Reuses Item 6's expanding match-count-quantile fold rule by import (not modified)."""
    import hashlib
    import json
    from src.research.item6.stage2.folds import MIN_TRAIN_FRAC, N_FOLDS, make_folds
    fx = sorted(fixtures, key=lambda f: (f["kickoff"], f["match_id"]))
    folds = make_folds([f["kickoff"] for f in fx], n_folds=N_FOLDS, min_train_frac=MIN_TRAIN_FRAC)
    cohort = set(cohort_team_ids)
    rows = []
    for f in fx:
        fold = next((d.fold_index for d in folds
                     if d.test_start_unix <= f["kickoff"] < d.test_end_unix), None)
        rows.append({"match_id": f["match_id"], "kickoff": f["kickoff"],
                     "competition_id": f["competition_id"],
                     "fold": fold, "designation": "TEST" if fold is not None else "TRAIN_ONLY",
                     "involves_cohort_team": bool({f["home_team_id"], f["away_team_id"]}
                                                  & cohort)})
    per = {}
    for d in folds:
        test = [r for r in rows if r["fold"] == d.fold_index]
        per[str(d.fold_index)] = {"train_end": d.train_end_unix, "test_start": d.test_start_unix,
                                  "test_end": d.test_end_unix,
                                  "n_train": sum(1 for r in rows if r["kickoff"] <
                                                 d.test_start_unix),
                                  "n_test_all": len(test),
                                  "n_test_primary": sum(1 for r in test
                                                        if not r["involves_cohort_team"])}
    doc = {"fold_manifest_version": "target_aware_folds_v1", "n_panel_rows": len(rows),
           "n_oos_all": sum(v["n_test_all"] for v in per.values()),
           "n_oos_primary_excluding_cohort_teams": sum(v["n_test_primary"] for v in per.values()),
           "folds": per, "rows": rows, "retrain": "once per fold",
           "primary_scoring_set": "OOS rows with involves_cohort_team == false",
           "reads_outcomes": False}
    doc["rows_sha256"] = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    return doc
