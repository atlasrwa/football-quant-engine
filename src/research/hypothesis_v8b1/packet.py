"""V8B.1 evidence packet builder (`v8b1_packet_v1`). See research/hypothesis_engine/
V8B1_EVIDENCE_PACKET_SPEC.md for the full design rationale.

RAW PIT-SAFE HISTORICAL ROWS + DETERMINISTIC NAVIGATION SUMMARIES + CAPABILITY ENVELOPE.
Assembles ALREADY-AUDITED primitives (PITIndex, SimilarityEngine, CapabilityContract.envelope,
Recency.shrink) -- no new PIT, shrinkage, or similarity logic is written here.

NEVER includes: the target fixture's own observed statistics, any later fixture, market/odds
data, any historical hypothesis's effect/p-value/terminal-state, any numeric similarity score
(membership only), or the target fixture's own formation (always FORMATION_UNKNOWN).

ZERO SPEND. No network. No CHAMPION.
"""
from __future__ import annotations

import hashlib
import json

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import recency as REC
from src.research.hypothesis_v7 import pit as V7PIT

PACKET_VERSION = "v8b1_packet_v1"

PROFILE_AXES = ("goals_for", "goals_against", "shots_on_target_for",
               "shots_on_target_against", "possession_for", "shots_against")

THIN_COVERAGE_THRESHOLD = V7PIT.MIN_RAW_N


def _metric_row(index, team_id, metric, terciles=None, axis_cache=None):
    """One metric's navigation summary for one team, both perspectives. Reuses PITIndex
    accessors exactly; adds no new statistic."""
    out = {"metric": metric}
    for perspective in ("FOR", "AGAINST"):
        mean_all, n_all = index.pit_mean(team_id, metric, perspective, _REF_POS[0])
        mean_home, n_home = index.pit_mean(team_id, metric, perspective, _REF_POS[0],
                                           venue=True)
        mean_away, n_away = index.pit_mean(team_id, metric, perspective, _REF_POS[0],
                                           venue=False)
        thin = n_all < THIN_COVERAGE_THRESHOLD
        out[perspective.lower()] = {
            "long_run_mean": (round(mean_all, 4) if mean_all is not None else None),
            "long_run_n": n_all,
            "home_mean": (round(mean_home, 4) if mean_home is not None else None),
            "home_n": n_home,
            "away_mean": (round(mean_away, 4) if mean_away is not None else None),
            "away_n": n_away,
            "coverage": "THIN" if thin else "ADEQUATE",
        }
    return out


# `_REF_POS` is a one-element mutable cell threaded through `_metric_row` so the function
# signature stays a clean (index, team_id, metric) call per the spec's own description; set by
# `build_packet` before use and never read outside a single packet build (no cross-call state).
_REF_POS = [None]


def _recent_vs_long(index, team_id, metric, rec_i, recency_family):
    """Recent (time-decay shrunk) vs long-run (uniform, un-decayed) for one team/metric/FOR,
    reusing recency.Recency.shrink exactly as engine.py::_estimates already does."""
    long_mean, long_n = index.pit_mean(team_id, metric, "FOR", rec_i)
    if long_mean is None:
        return {"recent_shrunk": None, "long_run": None, "coverage": "THIN"}
    recent_vals = []
    for w in recency_family:
        if w.halflife_days is None:
            continue
        entries = index.prior_entries(team_id, rec_i)
        ref = index.kick[rec_i]
        vals, wts = [], []
        for (pos, kick, _comp, _home, _opp) in entries:
            v = index.team_value(pos, team_id, metric, "FOR")
            if v is not None:
                vals.append(v)
                wts.append(w.weight(kick, ref))
        if not vals or sum(wts) <= 0:
            continue
        wmean = sum(v * wt for v, wt in zip(vals, wts)) / sum(wts)
        recent_vals.append(w.shrink(wmean, long_n, long_mean))
    recent_shrunk = (sum(recent_vals) / len(recent_vals)) if recent_vals else None
    return {"recent_shrunk": (round(recent_shrunk, 4) if recent_shrunk is not None else None),
           "long_run": round(long_mean, 4), "coverage": "ADEQUATE" if long_n >=
           THIN_COVERAGE_THRESHOLD else "THIN"}


def _opponent_profile_terciles(opponent_id, terciles, axis_cache, competition):
    """Which PIT tercile the fixture opponent falls into per profile axis -- reuses the SAME
    tercile construction execution.py::build_context already computes; no new profiling."""
    out = {}
    for axis in PROFILE_AXES:
        mv = axis_cache.get((str(opponent_id), axis))
        bounds = terciles.get((competition, axis))
        if mv is None or bounds is None:
            out[axis] = None
            continue
        lo, hi = bounds
        out[axis] = "LOW" if mv < lo else ("HIGH" if mv > hi else "MID")
    return out


def _similar_opponents(similarity_engine, index, opponent_id, rec, rec_i):
    """Membership only -- team IDENTITIES, never a distance score. Refuses (returns None with
    a named reason) rather than guessing, exactly like the compiler's own SIMILAR_OPPONENT
    handling."""
    try:
        ids = similarity_engine.similar_opponent_ids(index, opponent_id, rec, rec_i)
        return {"status": "OK", "similar_opponent_ids": sorted(ids)}
    except Exception as e:  # SimilarityRefused, caught by name to avoid a hard import cycle
        return {"status": "REFUSED", "reason": str(e), "similar_opponent_ids": []}


def build_packet(index, rec_i, capability, terciles, axis_cache, similarity_engine,
                 recency_family) -> dict:
    """The full V8B.1 evidence packet for target fixture at position `rec_i`. Symmetric
    Team A (home) / Team B (away) construction: THE SAME function calls, subject swapped."""
    rec = index.recs[rec_i]
    _REF_POS[0] = rec_i
    metrics = sorted(m for m in CAP.METRIC_SEMANTICS
                     if capability.classify_metric(m)[0] in (CAP.SUPPORTED, CAP.RESTRICTED))

    def team_block(team_id, opponent_id):
        rows = [_metric_row(index, team_id, m) for m in metrics]
        recent = {m: _recent_vs_long(index, team_id, m, rec_i, recency_family) for m in metrics}
        env = {m: (round(v, 4) if (v := index.env_mean(rec.competition, m,
                                                         int(rec.kickoff_unix))) is not None
                   else None) for m in metrics}
        return {
            "raw_rows": rows,
            "recent_vs_long": recent,
            "competition_environment_mean": env,
            "opponent_profile_of_fixture_opponent": _opponent_profile_terciles(
                opponent_id, terciles, axis_cache, rec.competition),
            "similar_to_fixture_opponent": _similar_opponents(
                similarity_engine, index, opponent_id, rec, rec_i),
        }

    packet = {
        "packet_version": PACKET_VERSION,
        "fixture": {"fixture_id": str(rec.fixture_id), "competition": rec.competition,
                   "kickoff_unix": int(rec.kickoff_unix)},
        "information_cutoff_unix": int(rec.kickoff_unix),
        "team_a": {"role": "HOME_TEAM", **team_block(str(rec.home_id), str(rec.away_id))},
        "team_b": {"role": "AWAY_TEAM", **team_block(str(rec.away_id), str(rec.home_id))},
        "target_formation": "FORMATION_UNKNOWN",
        "capability_envelope": capability.envelope(),
        "reads_target_outcome": False,
        "reads_historical_hypothesis_effects": False,
        "reads_similarity_scores": False,
    }
    packet["packet_hash"] = _packet_hash(packet)
    return packet


def _packet_hash(packet: dict) -> str:
    core = {k: v for k, v in packet.items() if k != "packet_hash"}
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def version_stamp() -> dict:
    return {"packet_version": PACKET_VERSION,
            "thin_coverage_threshold": THIN_COVERAGE_THRESHOLD,
            "thin_coverage_threshold_source": V7PIT.PIT_VERSION,
            "reads_target_outcome": False,
            "reads_historical_hypothesis_effects": False,
            "reads_similarity_scores": False,
            "target_formation_always_unknown": True,
            "symmetric_team_construction": True}
