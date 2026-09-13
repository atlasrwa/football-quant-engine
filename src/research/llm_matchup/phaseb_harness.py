"""Shared Phase-B harness utilities (B0 / B1 / B2).

Deterministic, research-only. Provides:
  * corpus loading (cache-only);
  * PIT-safe formation PROJECTION for a target (mode of the team's prior resolved
    formations — never the target's own resolved formation);
  * v2 packet construction with formation dimensions;
  * a uniform call record for phase_b_calls.csv;
  * candidate fixture discovery (fixtures whose two teams have enough prior history AND
    prior resolved-formation coverage).

Writes nothing on import. All file writes go through the individual gate harnesses into
research/llm_matchup/out/.
"""
from __future__ import annotations
import os, csv, json, time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from src.research.matchup.corpus import load_corpus, MatchRecord, season_of
from src.research.llm_matchup import formation as FM
from src.research.llm_matchup import cohorts as CH
from src.research.llm_matchup.evidence_v2 import EvidencePacketBuilderV2
from src.research.llm_matchup import versions as V

OUT = "/home/ubuntu/research/llm_matchup/out"

CALLS_HEADER = [
    "phase", "fixture_id", "competition", "home", "away", "packet_hash",
    "model_id", "resolved_model_id", "region", "status",
    "ontology_version", "schema_version", "prompt_version", "packet_schema_version",
    "formation_policy_version", "formation_family_version",
    "cache_hit", "latency_s", "input_tokens", "output_tokens",
    "reject_field", "reject_reason", "n_evidence", "n_formation_evidence",
    "resolution_status", "prematch_status", "created_unix",
]


# ---------------------------------------------------------------------------
# PIT-safe formation projection (Scenario 2 baseline; NOT productionised)
# ---------------------------------------------------------------------------
def project_formation(recs, coverage_idx, team: str, before_unix: int,
                      season: Optional[str]) -> FM.FormationInput:
    """Project a PROJECTED FormationInput for `team` at the target using ONLY prior matches.

    Baseline projector: mode of the team's prior resolved formations this season, with a
    distribution over the observed prior formations. Uses the RESOLVED formation of the
    team's OWN PRIOR matches (legitimate — those are completed source matches). NEVER reads
    the target fixture's resolved formation.
    """
    counts: Counter = Counter()
    for r in recs:
        if r.kickoff_unix >= before_unix:
            continue
        if season is not None and season_of(r) != season:
            continue
        if r.fixture_id not in coverage_idx:
            continue
        if r.home == team or r.home_id == team:
            f = coverage_idx[r.fixture_id]["home"]
        elif r.away == team or r.away_id == team:
            f = coverage_idx[r.fixture_id]["away"]
        else:
            continue
        if f:
            counts[f] += 1
    if not counts:
        return FM.FormationInput.unknown(source_version="phase_b_projector_v0")
    total = sum(counts.values())
    dist = {k: round(v / total, 4) for k, v in counts.items()}
    top = counts.most_common(1)[0][0]
    # confidence scales with concentration and sample size
    conc = counts[top] / total
    if total >= 6 and conc >= 0.6:
        conf = FM.FormationConfidence.MEDIUM.value
    else:
        conf = FM.FormationConfidence.LOW.value
    return FM.FormationInput.projected(top, "phase_b_projector_v0", confidence=conf,
                                       distribution=dist)


# ---------------------------------------------------------------------------
# candidate discovery
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    target: MatchRecord
    a_form: FM.FormationInput
    b_form: FM.FormationInput
    n_prior_a: int
    n_prior_b: int
    a_prior_form_cov: int
    b_prior_form_cov: int


class HarnessContext:
    """Loads corpus + formation coverage once; builds packets on demand."""

    def __init__(self, enrich_halves: bool = False):
        self.recs = load_corpus()
        self.coverage = FM.resolved_coverage_index()
        self.builder = EvidencePacketBuilderV2(self.recs, enrich_halves=enrich_halves)
        self._hidx = CH.HistoryIndex(self.recs)

    def _prior_form_cov(self, team, before_unix, season) -> int:
        n = 0
        for r in self.recs:
            if r.kickoff_unix >= before_unix:
                continue
            if season is not None and season_of(r) != season:
                continue
            if r.fixture_id not in self.coverage:
                continue
            if (r.home == team or r.home_id == team) and self.coverage[r.fixture_id]["home"]:
                n += 1
            elif (r.away == team or r.away_id == team) and self.coverage[r.fixture_id]["away"]:
                n += 1
        return n

    def candidates(self, min_prior=6, min_form_cov=1, require_target_lineup=True):
        """Yield Candidate objects for fixtures usable in the pilot.

        require_target_lineup: only used for reporting resolution status; the target's
        resolved formation is NEVER injected into the packet.
        """
        out = []
        for target in self.recs:
            if require_target_lineup and target.fixture_id not in self.coverage:
                continue
            sA = self._hidx.current_season(target.home, target.kickoff_unix)
            sB = self._hidx.current_season(target.away, target.kickoff_unix)
            nA = len(self._hidx.prior_records(target.home, target.kickoff_unix, sA))
            nB = len(self._hidx.prior_records(target.away, target.kickoff_unix, sB))
            if nA < min_prior or nB < min_prior:
                continue
            fca = self._prior_form_cov(target.home, target.kickoff_unix, sA)
            fcb = self._prior_form_cov(target.away, target.kickoff_unix, sB)
            if fca < min_form_cov or fcb < min_form_cov:
                continue
            a_form = project_formation(self.recs, self.coverage, target.home, target.kickoff_unix, sA)
            b_form = project_formation(self.recs, self.coverage, target.away, target.kickoff_unix, sB)
            out.append(Candidate(target, a_form, b_form, nA, nB, fca, fcb))
        return out

    def build_packet(self, cand: Candidate, include_formation=True,
                     formation_override=None, projected=True):
        pf = None
        if projected:
            pf = {"home": cand.a_form, "away": cand.b_form}
        return self.builder.build(cand.target, prematch_formations=pf,
                                  include_formation=include_formation,
                                  formation_override=formation_override)


def call_record(phase: str, cand: Candidate, packet: dict, result) -> dict:
    m = result.manifest or {}
    fc = packet.get("formation_context", {})
    return {
        "phase": phase, "fixture_id": cand.target.fixture_id,
        "competition": cand.target.competition, "home": cand.target.home,
        "away": cand.target.away, "packet_hash": packet.get("packet_hash"),
        "model_id": m.get("model_id"), "resolved_model_id": m.get("resolved_model_id"),
        "region": m.get("region"), "status": result.status,
        "ontology_version": m.get("ontology_version"), "schema_version": m.get("schema_version"),
        "prompt_version": m.get("prompt_version"), "packet_schema_version": m.get("packet_schema_version"),
        "formation_policy_version": m.get("formation_policy_version"),
        "formation_family_version": m.get("formation_family_version"),
        "cache_hit": m.get("cache_hit"), "latency_s": m.get("latency_s"),
        "input_tokens": m.get("input_tokens"), "output_tokens": m.get("output_tokens"),
        "reject_field": m.get("reject_field"), "reject_reason": m.get("reject_reason"),
        "n_evidence": packet.get("data_quality", {}).get("n_evidence"),
        "n_formation_evidence": packet.get("data_quality", {}).get("n_formation_evidence"),
        "resolution_status": fc.get("resolution_status"), "prematch_status": fc.get("prematch_status"),
        "created_unix": int(time.time()),
    }


def append_calls_csv(path: str, rows: list[dict]):
    exists = os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CALLS_HEADER)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in CALLS_HEADER})
