"""Build the paired comparable-observations dataset (Phase 1).

Joins FootyStats corpus matches to TheStatsAPI fixtures+stats using ONLY
high-confidence canonical team maps, keyed on (mapped_home_tm, mapped_away_tm,
date within tolerance). Ambiguous joins fail closed (skipped). The join is
validated by final-score agreement.

Each output PairedFixture carries canonical identity, kickoff, both providers'
per-concept values (NULL != ZERO preserved, no imputation), and provenance
timestamps. Provider disagreement is directly observable from the two values.

IMPORTANT provenance honesty:
- FootyStats corpus values and TheStatsAPI /stats values are POST-MATCH. Their
  genuine publication time is unknown (TSA stats files carry no capture time).
  We therefore set observed_at = None for stat observations and record the
  fixture kickoff as event_time. The walk-forward evaluation never uses a
  match's own post-match stats as a feature for that match; it uses prior
  matches' stats, for which "known before a later fixture" is established by
  date ordering (event_time), exactly as the champion already does.
- retrieved_at is left None (we did not capture fetch times for the corpus).
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.research.experiments.provider_comparison.fields import (
    CONCEPTS_BY_NAME,
    OVERLAPPING_CONCEPTS,
    ConceptField,
)

_DAY = 86400
_JOIN_TOLERANCE = 2 * _DAY

FS_CORPUS_GLOB = "data/discovery/corpus/league-matches*"
TSA_DIR = "data/thestatsapi/championship"


# ---------------------------------------------------------------------------
# NULL-safe coercion (NULL != ZERO)
# ---------------------------------------------------------------------------

def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tsa_cell(sd: dict, group: str, stat: str, side: str) -> Any:
    node = (sd.get(group) or {}).get(stat) or {}
    per = node.get("all")
    if not isinstance(per, dict):
        return None
    return per.get(side)


def _tsa_concept_value(sd: dict, score: dict, cf: ConceptField) -> Optional[float]:
    """Extract a TheStatsAPI value for a concept (both-sides total / home)."""
    if cf.concept == "total_goals":
        gh, ga = score.get("home"), score.get("away")
        gh, ga = _num(gh), _num(ga)
        return None if gh is None or ga is None else gh + ga
    if cf.concept == "total_cards":
        yh = _num(_tsa_cell(sd, "overview", "yellow_cards", "home"))
        ya = _num(_tsa_cell(sd, "overview", "yellow_cards", "away"))
        if yh is None or ya is None:
            return None  # require both yellow sides (NULL != ZERO)
        total = yh + ya
        rh = _num(_tsa_cell(sd, "overview", "red_cards", "home"))
        ra = _num(_tsa_cell(sd, "overview", "red_cards", "away"))
        if rh is not None:
            total += rh
        if ra is not None:
            total += ra
        return total
    if cf.concept == "possession":
        return _num(_tsa_cell(sd, "overview", "ball_possession", "home"))
    # generic home+away sum
    h = _num(_tsa_cell(sd, cf.tsa_group, cf.tsa_stat, "home"))
    a = _num(_tsa_cell(sd, cf.tsa_group, cf.tsa_stat, "away"))
    if h is None or a is None:
        return None
    return h + a


def _fs_concept_value(m: dict, cf: ConceptField) -> Optional[float]:
    """Extract a FootyStats value for a concept (both-sides total / home)."""
    if cf.concept == "total_cards":
        yh = _num(m.get("team_a_yellow_cards"))
        ya = _num(m.get("team_b_yellow_cards"))
        if yh is None or ya is None:
            return None
        total = yh + ya
        rh = _num(m.get("team_a_red_cards"))
        ra = _num(m.get("team_b_red_cards"))
        if rh is not None:
            total += rh
        if ra is not None:
            total += ra
        return total
    if cf.concept == "possession":
        v = _num(m.get("team_a_possession"))
        if v is None or v < 0 or v > 100:
            return None
        return v
    h = _num(m.get(cf.fs_home))
    a = _num(m.get(cf.fs_away))
    if h is None or a is None:
        return None
    return h + a


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConceptObservation:
    """One provider's observation of one concept for one fixture."""
    concept: str
    footystats: Optional[float]
    thestatsapi: Optional[float]

    @property
    def both_present(self) -> bool:
        return self.footystats is not None and self.thestatsapi is not None


@dataclass(frozen=True)
class PairedFixture:
    """A canonically-joined FootyStats+TheStatsAPI fixture."""
    canonical_home_tm: str
    canonical_away_tm: str
    league: str
    season_fs: str
    season_tsa: str
    kickoff_unix: int
    fs_match_id: int
    tsa_match_ref: str
    concepts: dict[str, ConceptObservation]
    # provenance
    fs_observed_at: Optional[int] = None   # unknown for corpus
    tsa_observed_at: Optional[int] = None  # unknown: TSA stats carry no capture time
    fs_retrieved_at: Optional[int] = None
    tsa_retrieved_at: Optional[int] = None
    score_agreement: bool = False

    def value(self, provider: str, concept: str) -> Optional[float]:
        obs = self.concepts.get(concept)
        if obs is None:
            return None
        return obs.footystats if provider == "footystats" else obs.thestatsapi


@dataclass
class DatasetBuildReport:
    league: str
    fs_seasons: list[str] = field(default_factory=list)
    tsa_seasons: list[str] = field(default_factory=list)
    n_joined: int = 0
    n_ambiguous_skipped: int = 0
    n_score_agree: int = 0
    date_range: tuple[Optional[int], Optional[int]] = (None, None)

    def to_dict(self) -> dict:
        return {
            "league": self.league,
            "fs_seasons": sorted(self.fs_seasons),
            "tsa_seasons": sorted(self.tsa_seasons),
            "n_joined": self.n_joined,
            "n_ambiguous_skipped": self.n_ambiguous_skipped,
            "n_score_agreement": self.n_score_agree,
            "score_agreement_rate": round(self.n_score_agree / self.n_joined, 4) if self.n_joined else None,
            "date_range_unix": list(self.date_range),
        }


def _iso_to_unix(iso: str) -> Optional[int]:
    if not iso:
        return None
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def build_epl_paired_dataset(
    name_to_tm: dict[str, str],
    *,
    league: str = "England Premier League",
    fs_corpus_glob: str = FS_CORPUS_GLOB,
    tsa_dir: str = TSA_DIR,
    tsa_fixtures_glob: str = "_all_fixtures_epl_*.json",
    tsa_stats_prefix: str = "epl_stats_",
    root: str | Path = ".",
) -> tuple[list[PairedFixture], DatasetBuildReport]:
    """Build the paired dataset for one league (EPL by default).

    Args:
        name_to_tm: high-confidence {footystats_name -> tm_id} for this league.
        Other args locate the corpus/fixtures/stats on disk.

    Returns:
        (paired_fixtures, report). Fixtures are chronological by kickoff.
    """
    root = Path(root)
    report = DatasetBuildReport(league=league)

    # Index TheStatsAPI fixtures by (home_tm, away_tm) -> list of candidates.
    from collections import defaultdict
    tsa_idx: dict[tuple[str, str], list[dict]] = defaultdict(list)
    tsa_seasons: set[str] = set()
    for ff in glob.glob(str(root / tsa_dir / tsa_fixtures_glob)):
        d = json.loads(Path(ff).read_text())
        for fx in d.get("fixtures", []):
            h = (fx.get("home_team") or {}).get("id")
            a = (fx.get("away_team") or {}).get("id")
            du = _iso_to_unix(fx.get("utc_date", ""))
            if not (h and a and du):
                continue
            tsa_idx[(h, a)].append({
                "mt": fx["id"], "date_unix": du, "score": fx.get("score", {}),
                "season": fx.get("season_id", ""),
            })
            tsa_seasons.add(str(fx.get("season_id", "")))

    stats_available = {
        os.path.basename(p)[len(tsa_stats_prefix):-5]
        for p in glob.glob(str(root / tsa_dir / f"{tsa_stats_prefix}mt_*.json"))
    }

    def load_stats(mt: str) -> dict:
        p = root / tsa_dir / f"{tsa_stats_prefix}{mt}.json"
        if not p.exists():
            return {}
        try:
            return (json.loads(p.read_text()).get("data") or {})
        except (OSError, json.JSONDecodeError):
            return {}

    fs_seasons: set[str] = set()
    dates: list[int] = []
    paired: list[PairedFixture] = []

    for cf_path in glob.glob(str(root / fs_corpus_glob)):
        d = json.loads(Path(cf_path).read_text())
        recs = d.get("data", d) if isinstance(d, dict) else d
        if not isinstance(recs, list):
            continue
        for m in recs:
            hn, an = m.get("home_name"), m.get("away_name")
            if hn not in name_to_tm or an not in name_to_tm or m.get("status") != "complete":
                continue
            key = (name_to_tm[hn], name_to_tm[an])
            fsdu = int(m.get("date_unix", 0))
            cands = [
                c for c in tsa_idx.get(key, [])
                if abs(c["date_unix"] - fsdu) <= _JOIN_TOLERANCE and c["mt"] in stats_available
            ]
            if not cands:
                continue
            if len(cands) > 1:
                report.n_ambiguous_skipped += 1
                continue  # fail closed on ambiguity
            c = cands[0]
            sd = load_stats(c["mt"])
            score = c["score"]

            concepts: dict[str, ConceptObservation] = {}
            for cfld in OVERLAPPING_CONCEPTS:
                concepts[cfld.concept] = ConceptObservation(
                    concept=cfld.concept,
                    footystats=_fs_concept_value(m, cfld),
                    thestatsapi=_tsa_concept_value(sd, score, cfld),
                )

            fs_gh, fs_ga = _num(m.get("homeGoalCount")), _num(m.get("awayGoalCount"))
            score_ok = (fs_gh == _num(score.get("home")) and fs_ga == _num(score.get("away")))

            fs_seasons.add(str(m.get("season", "")))
            dates.append(fsdu)
            paired.append(PairedFixture(
                canonical_home_tm=key[0],
                canonical_away_tm=key[1],
                league=league,
                season_fs=str(m.get("season", "")),
                season_tsa=str(c.get("season", "")),
                kickoff_unix=fsdu,
                fs_match_id=int(m.get("id", 0)),
                tsa_match_ref=c["mt"],
                concepts=concepts,
                fs_observed_at=None,
                tsa_observed_at=None,
                score_agreement=bool(score_ok),
            ))
            if score_ok:
                report.n_score_agree += 1

    paired.sort(key=lambda p: p.kickoff_unix)
    report.n_joined = len(paired)
    report.fs_seasons = sorted(fs_seasons)
    report.tsa_seasons = sorted(tsa_seasons)
    report.date_range = (min(dates), max(dates)) if dates else (None, None)
    return paired, report
