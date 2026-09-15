"""PIT-safe dual-provider match corpus for matchup research (cache-only, no network).

Loads TheStatsAPI rich adapted matches (via scripts/multisrc_corpus + championship_adapter)
across the 6 covered leagues and exposes each match as a flat provenance-carrying record.

Every match record carries:
  fixture_id, competition (tag), competition_id, season_id, kickoff_unix,
  home, away, provider fields (home/away), and a `_rich` block (TheStatsAPI extras).

Temporal rule enforced downstream by feature builders: a feature for fixture F may
read ONLY matches with kickoff_unix strictly < F.kickoff_unix (same-season) — never F
itself, never the future. This module only LOADS; it does not compute features.
"""
from __future__ import annotations
import os, sys, json, glob
from dataclasses import dataclass, field
from typing import Any, Optional

_SCRIPTS = "/home/ubuntu/scripts"
sys.path.insert(0, _SCRIPTS)
import multisrc_corpus as msc          # noqa: E402
import championship_adapter as adapt   # noqa: E402

CACHE = "/home/ubuntu/data/thestatsapi/championship"

# Extra raw stats the stock adapter does NOT surface but which we need for research
# (throw_ins, free_kicks, goal_kicks, offsides, possession, total_shots, corners full).
# Read directly from the raw /stats payload here, all-period, home/away, NULL!=ZERO.
_EXTRA_STATS = {
    "throw_ins": ("passes", "throw_ins"),
    "free_kicks": ("overview", "free_kicks"),
    "goal_kicks": ("goalkeeping", "goal_kicks"),
    "offsides": ("attack", "offsides"),
    "possession": ("overview", "ball_possession"),
    "total_shots": ("overview", "total_shots"),
    "shots_off_target": ("shots", "shots_off_target"),
    "hit_woodwork": ("shots", "hit_woodwork"),
    "dangerous_attacks_proxy": ("attack", "touches_in_penalty_area"),  # FS-only concept absent in TSA; proxy noted
}


@dataclass
class MatchRecord:
    fixture_id: str
    competition: str          # league tag (champ, epl, ...)
    competition_id: str
    season_id: str
    kickoff_unix: int
    home: str
    away: str
    home_id: str
    away_id: str
    base: dict[str, Any]      # FootyStats-schema fields from adapter
    rich: dict[str, Any]      # (home, away) pairs from adapter._rich
    extra: dict[str, Any]     # extra raw stats not in adapter


def _cell(sd, group, stat, side, period="all"):
    return adapt._cell(sd, group, stat, period, side)


def _extra_pairs(sd) -> dict[str, Any]:
    out = {}
    for name, (grp, stat) in _EXTRA_STATS.items():
        h = _cell(sd, grp, stat, "home")
        a = _cell(sd, grp, stat, "away")
        out[name] = (h, a) if (h is not None and a is not None) else None
    return out


def load_corpus(leagues: Optional[list[str]] = None) -> list[MatchRecord]:
    """Load all finished, stats-backed matches across covered leagues, sorted by kickoff."""
    leagues = leagues or list(msc.LEAGUES.keys())
    recs: list[MatchRecord] = []
    for tag in leagues:
        meta = msc.LEAGUES[tag]
        for sn in meta["seasons"]:
            fp = msc.fixture_path(tag, sn)
            if not os.path.exists(fp):
                continue
            fixtures = json.load(open(fp))["fixtures"]
            for fx in fixtures:
                status = str(fx.get("status", "")).lower()
                score = fx.get("score") or {}
                if status not in ("finished", "complete", "played"):
                    continue
                if score.get("home") is None or score.get("away") is None:
                    continue
                spath = msc.stats_path(tag, fx["id"])
                if not os.path.exists(spath):
                    continue
                sj = json.load(open(spath))
                shape = msc._to_adapter_shape(fx)
                adapted = adapt.adapt_match(shape, sj)
                sd = (sj or {}).get("data", {})
                recs.append(MatchRecord(
                    fixture_id=str(fx["id"]),
                    competition=tag,
                    competition_id=str(fx.get("competition_id") or meta["comp"]),
                    season_id=str(sn),
                    kickoff_unix=int(adapted["date_unix"]),
                    home=adapted["home_name"], away=adapted["away_name"],
                    home_id=str(adapted.get("home_id")), away_id=str(adapted.get("away_id")),
                    base=adapted,
                    rich=adapted.get("_rich") or {},
                    extra=_extra_pairs(sd),
                ))
    recs.sort(key=lambda r: r.kickoff_unix)
    return recs


def season_of(rec: MatchRecord) -> str:
    """Season-instance key = (competition tag, season_id). Windows never span this."""
    return f"{rec.competition}:{rec.season_id}"


if __name__ == "__main__":
    recs = load_corpus()
    from collections import Counter
    print(f"loaded {len(recs)} rich dual-provider matches")
    print("by league:", dict(Counter(r.competition for r in recs)))
    r = recs[len(recs)//2]
    print("sample:", r.competition, r.home, "vs", r.away)
    print("  base keys:", sorted(r.base.keys())[:8])
    print("  rich populated:", [k for k, v in r.rich.items() if v is not None][:12])
    print("  extra populated:", [k for k, v in r.extra.items() if v is not None])
