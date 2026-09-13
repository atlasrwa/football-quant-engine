"""Deterministic stratified sampling for the hardening studies (patch §6).

Phase B's repeatability set was 10 fixtures. The patch requires a substantially larger,
STRATIFIED set (30-50) covering the difficulty dimensions that plausibly drive instability:

  strong evidence / weak evidence / conflicted evidence / formation-heavy / behavior-heavy /
  small-N / high shrinkage / large 2H shift / provider disagreement / different competitions /
  different tactical clusters (patch §6).

We derive each dimension DETERMINISTICALLY from the built packet (no randomness, no lookahead
to Phase-C outcomes). Selection is a deterministic stratified cover: we greedily pick fixtures
so that every stratum bucket is represented, spreading across competitions, capped at `n`.

The stratification is intentionally SEPARATE from the frozen B2 selection (patch §30). These
fixtures form the HARDENING_CONTROL_SET used for the repeatability / ablation / control studies.
They are NOT added to, and do not replace, the frozen B2 universe.
"""
from __future__ import annotations
import statistics
from dataclasses import dataclass

from src.research.llm_matchup import phaseb_harness as H


@dataclass
class StratifiedPick:
    candidate: object          # H.Candidate
    fixture_id: str
    competition: str
    strata: frozenset          # which difficulty buckets this fixture satisfies
    n_evidence: int
    n_formation_evidence: int


# --- deterministic per-packet difficulty signals --------------------------------
def _packet_strata(cand, packet) -> frozenset:
    ev = packet["evidence"]
    n = len(ev) or 1
    rels = [e.get("reliability") for e in ev]
    shr = [e.get("shrinkage_level") for e in ev]
    ns = [e.get("sample_n") or 0 for e in ev]
    provs = set(e.get("source_provider") for e in ev)
    metrics = [e.get("metric", "") for e in ev]
    n_formation = packet.get("data_quality", {}).get("n_formation_evidence", 0)

    frac_high = sum(1 for r in rels if r == "HIGH") / n
    frac_low = sum(1 for r in rels if r == "LOW") / n
    frac_shrunk = sum(1 for s in shr if s in ("SHRUNK", "HIERARCHICAL", "DERIVED")) / n
    median_n = statistics.median(ns) if ns else 0
    has_2h = any("2h_shift" in m for m in metrics)
    multi_provider = len({p for p in provs if p in ("thestatsapi", "footystats")}) >= 2
    form_diversity = len(cand.a_form.distribution or {}) + len(cand.b_form.distribution or {})

    strata = set()
    if frac_high >= 0.10:
        strata.add("STRONG_EVIDENCE")
    if frac_low >= 0.35:
        strata.add("WEAK_EVIDENCE")
    if frac_shrunk >= 0.55:
        strata.add("HIGH_SHRINKAGE")
    if median_n <= 4:
        strata.add("SMALL_N")
    if n_formation >= 30:
        strata.add("FORMATION_HEAVY")
    if (n - n_formation) >= 40:
        strata.add("BEHAVIOR_HEAVY")
    if has_2h:
        strata.add("LARGE_2H_SHIFT")
    if multi_provider:
        strata.add("PROVIDER_DISAGREEMENT")
    if form_diversity >= 5:
        strata.add("TACTICAL_CLUSTER_DIVERSE")
    # "conflicted" is not directly observable pre-call; we proxy it by simultaneous strong
    # FOR-behavior and strong AGAINST-suppression coverage (the setup that produces CONFLICTED).
    has_for = any(m.endswith("_for") for m in metrics)
    has_against = any(m.endswith("_against") or "_allowed" in m for m in metrics)
    if has_for and has_against and frac_high >= 0.05:
        strata.add("POTENTIALLY_CONFLICTED")
    return frozenset(strata)


def select_stratified(ctx: H.HarnessContext, n: int = 40, enrich_halves: bool = True,
                      min_prior: int = 8, min_form_cov: int = 1,
                      max_scan: int = 220) -> list[StratifiedPick]:
    """Deterministic stratified cover of `n` fixtures across difficulty buckets + competitions.

    Deterministic ordering: sort CANDIDATES (cheap metadata, no packet build) by
    (competition, kickoff_unix, fixture_id) so the selection is reproducible and independent of
    corpus iteration order. We then build packets only for a bounded, round-robin-by-competition
    prefix of at most `max_scan` candidates (building all ~726 packets is unnecessary and slow).
    Greedy set-cover over that scanned pool: repeatedly add the fixture that introduces the most
    not-yet-covered strata, breaking ties by the deterministic order, round-robining competitions
    to avoid a single-league sample.
    """
    cands = ctx.candidates(min_prior=min_prior, min_form_cov=min_form_cov)
    # deterministic order on cheap metadata first
    cands.sort(key=lambda c: (c.target.competition, c.target.kickoff_unix, c.target.fixture_id))
    # round-robin across competitions so the scanned pool spans all leagues even under the cap
    by_comp: dict[str, list] = {}
    for c in cands:
        by_comp.setdefault(c.target.competition, []).append(c)
    comps = sorted(by_comp)
    scan_order: list = []
    idx = {k: 0 for k in comps}
    while len(scan_order) < min(max_scan, len(cands)):
        progressed = False
        for comp in comps:
            i = idx[comp]
            if i < len(by_comp[comp]):
                scan_order.append(by_comp[comp][i])
                idx[comp] += 1
                progressed = True
                if len(scan_order) >= min(max_scan, len(cands)):
                    break
        if not progressed:
            break

    picks_all: list[StratifiedPick] = []
    for c in scan_order:
        pk = ctx.build_packet(c, include_formation=True, projected=True)
        strata = _packet_strata(c, pk)
        picks_all.append(StratifiedPick(
            candidate=c, fixture_id=c.target.fixture_id, competition=c.target.competition,
            strata=strata, n_evidence=len(pk["evidence"]),
            n_formation_evidence=pk.get("data_quality", {}).get("n_formation_evidence", 0)))

    picks_all.sort(key=lambda p: (p.competition, p.candidate.target.kickoff_unix, p.fixture_id))

    # greedy stratum cover with competition round-robin
    all_strata = set().union(*[p.strata for p in picks_all]) if picks_all else set()
    covered: set = set()
    chosen: list[StratifiedPick] = []
    seen_pairs: set = set()
    remaining = list(picks_all)

    def _key(p, covered):
        new = len(p.strata - covered)
        return (-new, p.competition, p.candidate.target.kickoff_unix, p.fixture_id)

    # phase 1: cover every stratum at least once
    while remaining and covered != all_strata and len(chosen) < n:
        remaining.sort(key=lambda p: _key(p, covered))
        p = remaining.pop(0)
        pair = (p.candidate.target.home, p.candidate.target.away)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        chosen.append(p)
        covered |= p.strata

    # phase 2: fill remaining slots spreading across competitions deterministically
    if len(chosen) < n:
        by_comp: dict[str, list] = {}
        for p in remaining:
            pair = (p.candidate.target.home, p.candidate.target.away)
            if pair in seen_pairs:
                continue
            by_comp.setdefault(p.competition, []).append(p)
        comps = sorted(by_comp)
        i = 0
        while len(chosen) < n and any(by_comp.values()):
            comp = comps[i % len(comps)]
            i += 1
            bucket = by_comp.get(comp)
            if bucket:
                p = bucket.pop(0)
                pair = (p.candidate.target.home, p.candidate.target.away)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                chosen.append(p)

    return chosen[:n]


def strata_coverage(picks: list[StratifiedPick]) -> dict:
    from collections import Counter
    c = Counter()
    for p in picks:
        for s in p.strata:
            c[s] += 1
    comps = Counter(p.competition for p in picks)
    return {"n_picks": len(picks), "strata_counts": dict(c), "competition_counts": dict(comps)}
