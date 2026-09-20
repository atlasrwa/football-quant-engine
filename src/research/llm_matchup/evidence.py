"""fixture_evidence_packet_v1 — deterministic, PIT-safe evidence packet builder.

Builds the bounded factual universe handed to the LLM (brief §9, §10). Every value comes
from deterministic code and carries provenance: metric, value, sample_n, scope, provider,
source_field, cutoff, temporal_status. The LLM cannot invent fields outside this packet.

Half-split enrichment: the shared matchup `corpus.py` intentionally does not surface the
raw 1H/2H cells (they are dropped by the normalizer). We enrich records here WITHOUT
mutating that shared module, reading the raw TheStatsAPI /stats payload cache directly.

Formation is classified FORMATION_UNKNOWN for PIT purposes: cached lineups carry
`formation` + `confirmed:true` but NO announcement timestamp, so we cannot prove the
formation was known before kickoff (brief §17, §18, §25, §44). We therefore rely on
data-driven behavioral style clusters instead of formation labels.
"""
from __future__ import annotations
import os, sys, json, glob, hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional

from src._repo_paths import ensure_repo_importable
ensure_repo_importable()
from src.research.matchup.corpus import MatchRecord, load_corpus, season_of
from src.research.llm_matchup import cohorts as CH
from src.research.llm_matchup.versions import PACKET_SCHEMA_VERSION, COHORT_POLICY_VERSION

_RAW_CACHE = "/home/ubuntu/data/thestatsapi/championship"


# ---------- half-split enrichment (no mutation of shared corpus) ---------------
def _enrich_half_splits(recs: list[MatchRecord]) -> None:
    """Attach raw 1H/2H cells to rec.extra under keys '_half::group::stat'.
    Reads the raw stats_mt_<id>.json cache. Skips silently if absent (fail-closed:
    the metric simply becomes unavailable, never fabricated)."""
    needed = set(CH.HALF_METRICS.values())
    import multisrc_corpus as _msc  # authoritative stats-path resolver (already on sys.path)
    for r in recs:
        try:
            path = _msc.stats_path(r.competition, r.fixture_id)
        except Exception:
            path = None
        if not path or not os.path.exists(path):
            continue
        try:
            d = json.load(open(path)).get("data", {})
        except Exception:
            continue
        for grp, stat in needed:
            cell = (d.get(grp) or {}).get(stat)
            if isinstance(cell, dict) and ("first_half" in cell or "second_half" in cell):
                r.extra[f"_half::{grp}::{stat}"] = cell


# ---------- evidence item -------------------------------------------------------
@dataclass
class EvidenceItem:
    id: str
    metric: str
    value: Optional[float]
    sample_n: int
    scope: dict
    reliability: str
    shrinkage_level: str
    evidence_level: str
    source_provider: str
    source_field: str
    cutoff_unix: int
    temporal_status: str            # PIT_SAFE | UNAVAILABLE
    max_source_time_unix: Optional[int] = None


def _mk_id(prefix: str, metric: str, scope: dict, n: int) -> str:
    h = hashlib.sha1(f"{prefix}|{metric}|{sorted(scope.items())}".encode()).hexdigest()[:6]
    return f"{prefix}_{metric}_{h}"


# ---------- league environment (PIT, prior matches only) ------------------------
def _league_env(recs, target, metric):
    """Mean total (home+away) of a metric over prior matches in the same competition."""
    vals = []
    for r in recs:
        if r.kickoff_unix >= target.kickoff_unix:
            continue
        if r.competition != target.competition:
            continue
        h = CH.team_metric(r, r.home, metric, "for", "all")
        a = CH.team_metric(r, r.away, metric, "for", "all")
        if h is not None and a is not None:
            vals.append(h + a)
    if len(vals) < 20:
        return None
    return sum(vals) / len(vals)


class EvidencePacketBuilder:
    """Deterministic builder. Feed it the full loaded corpus once; build per fixture."""

    def __init__(self, recs: list[MatchRecord], enrich_halves: bool = True):
        if enrich_halves:
            _enrich_half_splits(recs)
        self.idx = CH.HistoryIndex(recs)
        self.recs = self.idx.recs

    # -- one team's conditional state for a set of metrics --
    def _team_block(self, team: str, opp: str, target: MatchRecord, venue: str,
                    metrics: list[tuple[str, str]], prefix: str) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        # TARGET fixture's own season-instance (A3): one key filters BOTH sides, so
        # neither team can drift into a different season, and a team with no prior
        # matches in it abstains instead of falling back to the previous season.
        season = CH.HistoryIndex.target_season(target)
        for metric, side in metrics:
            # tier hierarchy: venue-conditioned -> overall -> None(prior)
            venue_vals = self.idx.prior_values(team, metric, side, target.kickoff_unix, season, venue=venue)
            overall_vals = self.idx.prior_values(team, metric, side, target.kickoff_unix, season)
            parent = (sum(overall_vals) / len(overall_vals)) if len(overall_vals) >= CH.MIN_HISTORY else None
            est = CH.shrink(venue_vals, parent)
            if est is None and len(overall_vals) >= CH.MIN_HISTORY:
                est, venue_vals = parent, overall_vals
                lvl = "VENUE_OVERALL"
            else:
                lvl = "VENUE_OVERALL" if len(venue_vals) >= CH.MIN_HISTORY else "ALL_VENUES"
            n = len(venue_vals) if lvl == "VENUE_OVERALL" else len(overall_vals)
            scope = {"team": team, "opponent": opp, "venue": venue, "side": side,
                     "competition": target.competition, "season": season}
            status = "PIT_SAFE" if est is not None else "UNAVAILABLE"
            items.append(EvidenceItem(
                id=_mk_id(prefix, f"{metric}_{side}", scope, n),
                metric=f"{metric}_{side}", value=(round(est, 4) if est is not None else None),
                sample_n=n, scope=scope, reliability=CH._reliability(n),
                shrinkage_level=("SHRUNK" if 0 < len(venue_vals) < 15 else "DIRECT"),
                evidence_level=lvl,
                source_provider="thestatsapi", source_field=metric,
                cutoff_unix=target.kickoff_unix, temporal_status=status,
                max_source_time_unix=None,
            ))
            # half-split escalation evidence (2H shift) for select metrics
            if metric in ("crosses", "total_shots", "corners", "possession"):
                fh = self.idx.prior_values(team, metric, side, target.kickoff_unix, season, period="first_half")
                sh = self.idx.prior_values(team, metric, side, target.kickoff_unix, season, period="second_half")
                if len(fh) >= CH.MIN_HISTORY and len(sh) >= CH.MIN_HISTORY:
                    shift = (sum(sh) / len(sh)) - (sum(fh) / len(fh))
                    sc = dict(scope); sc["period"] = "2h_minus_1h"
                    items.append(EvidenceItem(
                        id=_mk_id(prefix, f"{metric}_2h_shift", sc, len(sh)),
                        metric=f"{metric}_2h_shift", value=round(shift, 4), sample_n=len(sh),
                        scope=sc, reliability=CH._reliability(len(sh)), shrinkage_level="DIRECT",
                        evidence_level="VENUE_OVERALL", source_provider="thestatsapi",
                        source_field=f"{metric}.first_half/second_half", cutoff_unix=target.kickoff_unix,
                        temporal_status="PIT_SAFE",
                    ))
        return items

    def build(self, target: MatchRecord) -> dict:
        A, B = target.home, target.away
        # attack metrics (for) + defense metrics (against) per side
        atk = [("crosses", "for"), ("total_shots", "for"), ("shots_on_target", "for"),
               ("shots_inside_box", "for"), ("touches_in_box", "for"), ("corners", "for"),
               ("possession", "for"), ("throw_ins", "for"), ("final_third_entries", "for")]
        dfn = [("crosses", "against"), ("total_shots", "against"), ("shots_inside_box", "against"),
               ("touches_in_box", "against"), ("corners", "against"), ("blocked_shots", "for"),
               ("clearances", "for"), ("interceptions", "for")]
        disc = [("fouls", "for"), ("tackles", "for"), ("yellow_cards", "for"), ("fouls", "against")]

        a_items = (self._team_block(A, B, target, "home", atk, "A_ATK")
                   + self._team_block(A, B, target, "home", dfn, "A_DEF")
                   + self._team_block(A, B, target, "home", disc, "A_DIS"))
        b_items = (self._team_block(B, A, target, "away", atk, "B_ATK")
                   + self._team_block(B, A, target, "away", dfn, "B_DEF")
                   + self._team_block(B, A, target, "away", disc, "B_DIS"))

        # league env
        env_items = []
        for m in ("corners", "total_shots", "fouls", "yellow_cards"):
            v = _league_env(self.recs, target, m)
            env_items.append(EvidenceItem(
                id=_mk_id("ENV", m, {"comp": target.competition}, 0),
                metric=f"league_{m}_env", value=(round(v, 4) if v is not None else None),
                sample_n=0, scope={"competition": target.competition}, reliability=("HIGH" if v else "LOW"),
                shrinkage_level="DIRECT", evidence_level="COMPETITION_PRIOR", source_provider="derived",
                source_field=f"prior-match {m} totals", cutoff_unix=target.kickoff_unix,
                temporal_status=("PIT_SAFE" if v is not None else "UNAVAILABLE"),
            ))

        # style clusters (data-driven)
        # TARGET fixture's own season-instance (A3): one key filters BOTH sides, so
        # neither team can drift into a different season, and a team with no prior
        # matches in it abstains instead of falling back to the previous season.
        seasonA = seasonB = CH.HistoryIndex.target_season(target)
        league_ref = {}
        for m in CH._STYLE_METRICS:
            vv = []
            for r in self.recs:
                if r.kickoff_unix >= target.kickoff_unix or r.competition != target.competition:
                    continue
                h = CH.team_metric(r, r.home, m, "for", "all")
                if h is not None:
                    vv.append(h)
            if len(vv) >= 20:
                league_ref[m] = sum(vv) / len(vv)
        profA = CH._team_style_vector(self.idx, A, target.kickoff_unix, seasonA)
        profB = CH._team_style_vector(self.idx, B, target.kickoff_unix, seasonB)

        all_items = a_items + b_items + env_items
        packet = {
            "packet_schema_version": PACKET_SCHEMA_VERSION,
            "cohort_policy_version": COHORT_POLICY_VERSION,
            "fixture": {"fixture_id": target.fixture_id, "home": A, "away": B,
                         "competition": target.competition, "season": target.season_id,
                         "kickoff_unix": target.kickoff_unix},
            "information_cutoff_unix": target.kickoff_unix,
            "competition_context": {"tags": []},
            "team_a": {"name": A, "venue": "home", "style_tags": CH.style_tags(profA, league_ref),
                        "evidence_ids": [i.id for i in a_items]},
            "team_b": {"name": B, "venue": "away", "style_tags": CH.style_tags(profB, league_ref),
                        "evidence_ids": [i.id for i in b_items]},
            "league_environment": {"evidence_ids": [i.id for i in env_items]},
            "evidence": [asdict(i) for i in all_items],
            "unsupported_context": {
                "formation_status": "FORMATION_UNKNOWN",
                "formation_reason": "cached lineups lack announcement timestamp; cannot prove pre-kickoff",
                "injury_status": "INJURY_STATUS_UNKNOWN",
                "neutral_venue": "UNKNOWN",
            },
            "data_quality": {
                "n_evidence": len(all_items),
                "n_pit_safe": sum(1 for i in all_items if i.temporal_status == "PIT_SAFE"),
                "n_unavailable": sum(1 for i in all_items if i.temporal_status == "UNAVAILABLE"),
            },
            "provider_provenance": {"primary": "thestatsapi", "half_splits": "thestatsapi_raw_stats"},
        }
        packet["packet_hash"] = packet_hash(packet)
        return packet


def packet_hash(packet: dict) -> str:
    core = {k: v for k, v in packet.items() if k != "packet_hash"}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def valid_evidence_ids(packet: dict) -> set[str]:
    return {e["id"] for e in packet["evidence"]}
