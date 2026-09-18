"""V8C evidence packet (`v8c_packet_v1`) -- repairs P1 PACKET-RAW.

TWO DEFECTS IN THE V8B.1 PACKET
------------------------------
1. `raw_rows` were not raw. Each entry was a per-metric NAVIGATION SUMMARY -- long-run mean,
   home mean, away mean and their counts. A model asked to reason about football was handed
   aggregates and told they were the raw evidence, so it could not see form, opponent quality,
   venue sequence or dispersion; it could only re-read means the deterministic engine had
   already computed.
2. `_REF_POS` was a MUTABLE MODULE-LEVEL GLOBAL, set by `build_packet` and read inside
   `_metric_row`. Two packet builds in one process -- concurrent, or simply interleaved --
   race on it, and the second build can silently stamp the first build's reference position.
   That is a correctness bug in any parallel preflight and a reproducibility bug everywhere.

WHAT V8C EMITS
--------------
    raw_rows                 DETERMINISTIC, BOUNDED, match-level PIT-safe rows: one row per
                             prior match, each carrying kickoff, competition, venue, the
                             opponent's identity, and the audited raw metric values for BOTH
                             perspectives. Ordered most-recent-first, capped at
                             MAX_RAW_ROWS_PER_TEAM.
    navigation_summaries     the V8B.1 aggregates, RETAINED but kept in their own block and
                             named for what they are.
    recent_vs_long           now for BOTH `FOR` and `AGAINST` (V8B.1 computed FOR only, so
                             every defensive question was answered from attacking form).

PURITY
------
`build_packet` is a pure function of its arguments. No module-level mutable state, no global
reference position; the reference is threaded explicitly. Safe to call concurrently, and
`test_packet.py::test_serial_and_parallel_builds_are_identical` proves it.

NEVER INCLUDES the target fixture's own statistics, any later fixture, odds/market data, any
historical hypothesis's effect or terminal state, any numeric similarity score (membership
only), or the target's formation.

ZERO SPEND. No network. No CHAMPION.
"""
from __future__ import annotations

import hashlib
import json

from src.research.hypothesis_v7 import pit as V7PIT
from src.research.hypothesis_v71 import capability as CAP

PACKET_VERSION = "v8c_packet_v1"

#: Deterministic bound on the raw history handed over per team. Chosen as a round multiple of
#: the frozen MIN_RAW_N support floor (20) so a model can always see at least a supportable
#: cohort's worth of matches, and fixed so packet size is a function of the contract rather
#: than of how much history a team happens to have.
MAX_RAW_ROWS_PER_TEAM = 40

THIN_COVERAGE_THRESHOLD = V7PIT.MIN_RAW_N

PROFILE_AXES = ("goals_for", "goals_against", "shots_on_target_for",
                "shots_on_target_against", "possession_for", "shots_against")


def _raw_rows(index, team_id, rec_i, metrics) -> list:
    """MATCH-LEVEL PIT-safe rows. Every value comes from `prior_entries`, which is strictly
    before the target by construction, so no row here can be the target or later."""
    entries = index.prior_entries(team_id, rec_i)
    rows = []
    for (pos, kick, comp, is_home, opponent_id) in entries[-MAX_RAW_ROWS_PER_TEAM:]:
        row = {"kickoff_unix": int(kick), "competition": comp,
               "venue": "HOME" if is_home else "AWAY",
               "opponent_id": (str(opponent_id) if opponent_id is not None else None),
               "metrics": {}}
        for m in metrics:
            row["metrics"][m] = {
                "for": index.team_value(pos, team_id, m, "FOR"),
                "against": index.team_value(pos, team_id, m, "AGAINST"),
            }
        rows.append(row)
    rows.sort(key=lambda r: (-r["kickoff_unix"], str(r["opponent_id"])))
    return rows


def _navigation_summary(index, team_id, rec_i, metric) -> dict:
    """The V8B.1 aggregate, retained and correctly named. `rec_i` is threaded EXPLICITLY --
    there is no module-level reference cell to race on."""
    out = {"metric": metric}
    for perspective in ("FOR", "AGAINST"):
        mean_all, n_all = index.pit_mean(team_id, metric, perspective, rec_i)
        mean_home, n_home = index.pit_mean(team_id, metric, perspective, rec_i, venue=True)
        mean_away, n_away = index.pit_mean(team_id, metric, perspective, rec_i, venue=False)
        out[perspective.lower()] = {
            "long_run_mean": (round(mean_all, 4) if mean_all is not None else None),
            "long_run_n": n_all,
            "home_mean": (round(mean_home, 4) if mean_home is not None else None),
            "home_n": n_home,
            "away_mean": (round(mean_away, 4) if mean_away is not None else None),
            "away_n": n_away,
            "coverage": "THIN" if n_all < THIN_COVERAGE_THRESHOLD else "ADEQUATE",
        }
    return out


def _recent_vs_long(index, team_id, metric, rec_i, recency_family, perspective) -> dict:
    """Recent (time-decay shrunk) vs long-run, for the GIVEN perspective.

    V8B.1 hard-coded `FOR`, so every defensive question was answered from attacking form.
    """
    long_mean, long_n = index.pit_mean(team_id, metric, perspective, rec_i)
    if long_mean is None:
        return {"recent_shrunk": None, "long_run": None, "coverage": "THIN"}
    entries = index.prior_entries(team_id, rec_i)
    ref = index.kick[rec_i]
    recent_vals = []
    for w in recency_family:
        if w.halflife_days is None:
            continue
        vals, wts = [], []
        for (pos, kick, _c, _h, _o) in entries:
            v = index.team_value(pos, team_id, metric, perspective)
            if v is not None:
                vals.append(v)
                wts.append(w.weight(kick, ref))
        if not vals or sum(wts) <= 0:
            continue
        wmean = sum(v * wt for v, wt in zip(vals, wts)) / sum(wts)
        recent_vals.append(w.shrink(wmean, long_n, long_mean))
    recent = (sum(recent_vals) / len(recent_vals)) if recent_vals else None
    return {"recent_shrunk": (round(recent, 4) if recent is not None else None),
            "long_run": round(long_mean, 4),
            "coverage": "ADEQUATE" if long_n >= THIN_COVERAGE_THRESHOLD else "THIN"}


def _opponent_profile_bands(opponent_id, ctx, competition) -> dict:
    """The fixture opponent's band per axis, under the V8C (team, competition, axis, T)
    semantic. `None` where the cell has no profile -- never imputed to MID."""
    out = {}
    for axis in PROFILE_AXES:
        mv = ctx.axis_cache.get((str(opponent_id), competition, axis))
        bounds = ctx.terciles.get((competition, axis))
        if mv is None or bounds is None:
            out[axis] = None
            continue
        lo, hi = bounds
        out[axis] = "LOW" if mv < lo else ("HIGH" if mv > hi else "MID")
    return out


def _similar_opponents(ctx, index, opponent_id, rec, rec_i) -> dict:
    """Membership only -- team IDENTITIES, never a distance score."""
    try:
        ids = ctx.similarity.similar_opponent_ids(index, opponent_id, rec, rec_i)
        return {"status": "OK", "similar_opponent_ids": sorted(ids)}
    except Exception as e:
        return {"status": "REFUSED", "reason": str(e), "similar_opponent_ids": []}


def build_packet(index, rec_i, capability, ctx, recency_family) -> dict:
    """The V8C evidence packet. PURE: no module-level state, reentrant, thread-safe."""
    rec = index.recs[rec_i]
    metrics = sorted(m for m in CAP.METRIC_SEMANTICS
                     if capability.classify_metric(m)[0] in (CAP.SUPPORTED, CAP.RESTRICTED)
                     and m in index.metrics)

    def team_block(team_id, opponent_id):
        return {
            "raw_rows": _raw_rows(index, team_id, rec_i, metrics),
            "navigation_summaries": [_navigation_summary(index, team_id, rec_i, m)
                                     for m in metrics],
            "recent_vs_long": {
                m: {"for": _recent_vs_long(index, team_id, m, rec_i, recency_family, "FOR"),
                    "against": _recent_vs_long(index, team_id, m, rec_i, recency_family,
                                               "AGAINST")}
                for m in metrics},
            "competition_environment_mean": {
                m: (round(v, 4)
                    if (v := index.env_mean(rec.competition, m, int(rec.kickoff_unix)))
                    is not None else None)
                for m in metrics},
            "opponent_profile_of_fixture_opponent": _opponent_profile_bands(
                opponent_id, ctx, rec.competition),
            "similar_to_fixture_opponent": _similar_opponents(
                ctx, index, opponent_id, rec, rec_i),
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
        "max_raw_rows_per_team": MAX_RAW_ROWS_PER_TEAM,
        "environment_mean_semantic": ("competition environment mean, PIT-safe, pooled over "
                                      "ALL prior seasons of the competition -- NOT "
                                      "season-specific"),
        "reads_target_outcome": False,
        "reads_historical_hypothesis_effects": False,
        "reads_similarity_scores": False,
    }
    packet["packet_hash"] = packet_hash(packet)
    return packet


def packet_hash(packet: dict) -> str:
    core = {k: v for k, v in packet.items() if k != "packet_hash"}
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def assert_no_target_leak(packet: dict, target_fixture_id: str, target_kickoff: int) -> None:
    """Structural audit: no raw row may be the target or later."""
    for side in ("team_a", "team_b"):
        for row in packet[side]["raw_rows"]:
            assert row["kickoff_unix"] < target_kickoff, (
                f"raw row at/after the target kickoff in {side}")


def version_stamp() -> dict:
    return {"packet_version": PACKET_VERSION,
            "successor_to": "v8b1_packet_v1",
            "repairs": ["P1-PACKET-RAW"],
            "raw_rows_are_match_level": True,
            "v8b1_raw_rows_were": "per-metric navigation summaries, not raw rows",
            "max_raw_rows_per_team": MAX_RAW_ROWS_PER_TEAM,
            "navigation_summaries_retained_separately": True,
            "recent_vs_long_perspectives": ["FOR", "AGAINST"],
            "v8b1_recent_vs_long_perspectives": ["FOR"],
            "mutable_module_global": False,
            "ref_pos_global_removed": True,
            "pure_reentrant_thread_safe": True,
            "profile_semantic": "(team, competition, axis, T)",
            "reads_target_outcome": False}
