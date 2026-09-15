"""V5A full-fidelity fixture research view builder (`full_fidelity_view_v1`).

Corrects the V3 architectural weakness the forensic audit found: V3 exposed only
unconditional shrunk scalar means (venue=ALL, window=ALL_PRIOR). V5A exposes the actual
PIT-safe MATCH-LEVEL canonical record for both teams, plus deterministic DERIVED_SUMMARY
aids that supplement -- never replace -- the raw rows.

INVARIANTS (enforced by tests, not asserted):
  * No hidden aggregate-only stage: every admitted historical match becomes a canonical row.
  * Serialized cell == canonical cell (no shrinkage/banding/label substitution/imputation).
  * PIT: only matches with kickoff strictly < target cutoff; target and future excluded.
  * The LLM is the question layer only; this module supplies data, computes no probability.

This module is DOWNSTREAM research infrastructure. It reuses the frozen V3 corpus_adapter,
similarity, vocabulary, schema, compiler and firewall UNCHANGED. It writes no artifact and
imports no Bedrock client and no production-prediction / p_model path.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Sequence

from src.research.hypothesis_engine import corpus_adapter as CA
from src.research.hypothesis_engine import capability, similarity, vocabulary
from src.research.matchup import corpus as MC

FULL_FIDELITY_VIEW_VERSION = "full_fidelity_view_v1"

# ----------------------------------------------------------------------------------------
# Canonical metric inventory exposed as MATCH-LEVEL columns (Phase 1-2, 5).
# Reuses corpus_adapter._METRIC_SOURCE provenance verbatim, PLUS xg and red_cards, which
# V3 did not expose (audit finding). Each entry: canonical -> (block, key[, key2]).
# `xg` and `red_cards` read the base block. `dangerous_attacks` is DELIBERATELY EXCLUDED:
# the corpus only carries a proxy (touches_in_penalty_area), a documented semantic conflict.
# ----------------------------------------------------------------------------------------
CANONICAL_MATCH_METRICS = tuple(sorted(set(CA._METRIC_SOURCE) | {"xg", "red_cards"}))

_EXTRA_SOURCE = {
    "xg": ("base", "team_a_xg", "team_b_xg"),
    "red_cards": ("base", "team_a_red_cards", "team_b_red_cards"),
}

#: Metrics excluded by provider semantic ambiguity, recorded so the exclusion is explicit.
SEMANTIC_EXCLUSIONS = {
    "dangerous_attacks": "corpus carries only a proxy (touches_in_penalty_area); "
                         "no validated canonical mapping -> DO_NOT_MERGE, excluded",
}

#: Half-time state: measured 0% coverage in the TheStatsAPI corpus -> UNAVAILABLE.
HALF_STATE_STATUS = "UNAVAILABLE"

#: Deterministic similarity axes for opponent-profile context (Phase 7). Structurally
#: justified behavioral axes, frozen BEFORE any outcome; NOT chosen from V4 performance.
PROFILE_SIMILARITY_AXES = ("shots_on_target_for", "shots_on_target_against",
                           "corners_for", "corners_against", "possession_for",
                           "accurate_crosses_for", "goals_for", "goals_against")


def _metric_pair(rec: MC.MatchRecord, metric: str):
    if metric in _EXTRA_SOURCE:
        _, hk, ak = _EXTRA_SOURCE[metric]
        h, a = rec.base.get(hk), rec.base.get(ak)
        return (h, a) if (h is not None and a is not None) else None
    return CA._pair(rec, metric)


def _team_value(rec: MC.MatchRecord, team: str, metric: str, side: str):
    if metric in _EXTRA_SOURCE:
        pair = _metric_pair(rec, metric)
        if not pair:
            return None
        own, opp = (pair[0], pair[1]) if rec.home == team else (pair[1], pair[0])
        v = own if side == "FOR" else opp
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return CA.team_value(rec, team, metric, side)


# ----------------------------------------------------------------------------------------
# History policy (Phase 4) -- frozen deterministic rule, identical across fixtures.
# ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class HistoryPolicy:
    version: str = "history_policy_v1"
    #: The largest useful history that preserves context feasibility. Chosen from the
    #: feasibility study (see _freeze script): last-N matches per team, current+prior
    #: seasons allowed, no cross-competition restriction. NOT a function of any outcome.
    max_matches_per_team: int = 30
    min_matches_per_team: int = 6
    include_all_competitions: bool = True

    def to_dict(self) -> dict:
        return {"version": self.version,
                "max_matches_per_team": self.max_matches_per_team,
                "min_matches_per_team": self.min_matches_per_team,
                "include_all_competitions": self.include_all_competitions,
                "rule": "most recent N prior matches strictly before cutoff, all "
                        "competitions, N frozen before spend and identical per fixture"}


DEFAULT_POLICY = HistoryPolicy()


# ----------------------------------------------------------------------------------------
# Match-level row (Phase 5) -- actual canonical observations, aliased identities only.
# ----------------------------------------------------------------------------------------
def _alias_map(index: CA.HistoryIndex, target: MC.MatchRecord, policy: HistoryPolicy) -> dict:
    """Deterministic opponent alias: OPP_001.. in first-seen chronological order across
    both teams' admitted windows. Identity-neutral, stable, no club names."""
    seen: dict[str, str] = {}
    for team in (target.home, target.away):
        hist = _admitted(index, target, team, policy)
        for r in hist:
            opp = r.away if r.home == team else r.home
            if opp not in seen:
                seen[opp] = f"OPP_{len(seen) + 1:03d}"
    return seen


def _admitted(index, target, team, policy) -> list:
    cutoff = int(target.kickoff_unix)
    prior = [r for r in index.prior(team, cutoff) if r.fixture_id != target.fixture_id]
    prior.sort(key=lambda r: r.kickoff_unix)
    return prior[-policy.max_matches_per_team:]


def _comp_alias_map(index, target, policy) -> dict:
    """Deterministic competition alias: the target's own competition -> 'COMPETITION'
    (parity with the fixture-level alias), others -> COMP_002.. in first-seen order.
    Identity-neutral: no real league tag ever reaches the packet."""
    out = {target.competition: "COMPETITION"}
    for team in (target.home, target.away):
        for r in _admitted(index, target, team, policy):
            if r.competition not in out:
                out[r.competition] = f"COMP_{len(out) + 1:03d}"
    return out


def build_match_rows(index, target, team, policy, aliases, comp_aliases) -> list[dict]:
    rows = []
    for r in _admitted(index, target, team, policy):
        opp = r.away if r.home == team else r.home
        row = {
            "match_alias": f"m_{r.fixture_id}",
            "kickoff_unix": int(r.kickoff_unix),
            "competition": comp_aliases.get(r.competition, "COMP_OTHER"),
            "venue": "HOME" if r.home == team else "AWAY",
            "opponent_alias": aliases.get(opp, "OPP_UNK"),
            "own_formation_family": CA.team_formation_family(r, team),
            "opponent_formation_family": CA.team_formation_family(r, team, opponent=True),
        }
        for metric in CANONICAL_MATCH_METRICS:
            row[f"{metric}_for"] = _team_value(r, team, metric, "FOR")
            row[f"{metric}_against"] = _team_value(r, team, metric, "AGAINST")
        rows.append(row)
    return rows


# ----------------------------------------------------------------------------------------
# Derived summaries (Phase 6, 8, 9) -- marked DERIVED_SUMMARY, supplement not substitute.
# ----------------------------------------------------------------------------------------
def _mean(vals):
    u = [v for v in vals if v is not None]
    return (round(sum(u) / len(u), 4), len(u)) if u else (None, 0)


def build_derived_summaries(rows: list[dict], cutoff: int) -> list[dict]:
    out = []
    windows = {"ALL_PRIOR": rows, "W5": rows[-5:], "W10": rows[-10:]}
    venues = {"HOME": [r for r in rows if r["venue"] == "HOME"],
              "AWAY": [r for r in rows if r["venue"] == "AWAY"]}
    for metric in CANONICAL_MATCH_METRICS:
        for side in ("for", "against"):
            col = f"{metric}_{side}"
            for wname, wrows in windows.items():
                val, n = _mean([r[col] for r in wrows])
                if val is None:
                    continue
                out.append({"type": "DERIVED_SUMMARY", "metric": metric, "side": side.upper(),
                            "window": wname, "venue": "ALL", "value": val, "sample_n": n,
                            "cutoff_unix": cutoff, "reliability": _rel(n),
                            "provenance": "mean of serialized match rows"})
            for vname, vrows in venues.items():
                val, n = _mean([r[col] for r in vrows])
                if val is None or n < 3:
                    continue
                out.append({"type": "DERIVED_SUMMARY", "metric": metric, "side": side.upper(),
                            "window": "ALL_PRIOR", "venue": vname, "value": val, "sample_n": n,
                            "cutoff_unix": cutoff, "reliability": _rel(n),
                            "provenance": "venue-conditioned mean of serialized match rows"})
    return out


def _rel(n):
    return "HIGH" if n >= 20 else ("MEDIUM" if n >= 8 else "LOW")


# ----------------------------------------------------------------------------------------
# Opponent-profile research context (Phase 7) -- deterministic cohorts, no LLM similarity.
# ----------------------------------------------------------------------------------------
def build_opponent_profile_context(index, target, policy, aliases) -> dict:
    """For each similarity axis, band the UPCOMING opponent and report the subject's
    response cohort vs its overall baseline. Deterministic (RANK_BAND), PIT-safe."""
    cutoff = int(target.kickoff_unix)
    ctx = {"similarity_version": similarity.SIMILARITY_VERSION, "axes": {}}
    for axis in PROFILE_SIMILARITY_AXES:
        ms = _axis_to_metric_side(axis)
        if ms is None:
            continue
        metric, side = ms
        # candidate pool: teams in target competition before cutoff
        cands = sorted({t for r in index.records
                        if r.competition == target.competition and r.kickoff_unix < cutoff
                        for t in (r.home, r.away)})

        def value_fn(team, cut, _m=metric, _s=side):
            vals = [_team_value(r, team, _m, _s) for r in index.prior(team, cut)
                    if r.fixture_id != target.fixture_id]
            u = [v for v in vals if v is not None]
            return (sum(u) / len(u), len(u)) if u else None

        # band the two upcoming opponents (home's opponent = away team, and vice versa)
        axis_report = {}
        for subj_label, subj, opp in (("HOME", target.home, target.away),
                                      ("AWAY", target.away, target.home)):
            got = value_fn(opp, cutoff)
            if got is None:
                axis_report[subj_label] = {"status": "MISSING_PROVIDER_EVIDENCE"}
                continue
            res = similarity.resolve_band(
                axis=axis, requested_band="HIGH", cutoff_unix=cutoff,
                candidates=cands, axis_value_fn=value_fn)
            # which band the actual upcoming opponent falls in (from the full assignment set)
            opp_band = next((a.band for a in res.assignments if a.opponent == opp), None)
            axis_report[subj_label] = {
                "status": "AVAILABLE" if opp_band else "LOW_COVERAGE",
                "upcoming_opponent_band": opp_band,
                "candidate_n": res.candidate_n, "bandable_n": res.usable_n,
                "coverage_rate": round(res.coverage_rate, 4)}
        ctx["axes"][axis] = axis_report
    return ctx


def _axis_to_metric_side(axis: str):
    for suf, side in (("_for", "FOR"), ("_against", "AGAINST")):
        if axis.endswith(suf):
            m = axis[: -len(suf)]
            if m in CANONICAL_MATCH_METRICS:
                return m, side
    return None


# ----------------------------------------------------------------------------------------
# Availability map (Phase 12)
# ----------------------------------------------------------------------------------------
def build_availability_map(index, target, policy, rows_home, rows_away, prof_ctx) -> dict:
    def venue_ok(rows):
        h = sum(1 for r in rows if r["venue"] == "HOME")
        a = sum(1 for r in rows if r["venue"] == "AWAY")
        return h >= 4 and a >= 4
    def form_cov(rows):
        n = sum(1 for r in rows if r["own_formation_family"])
        return round(n / len(rows), 4) if rows else 0.0
    fc = max(form_cov(rows_home), form_cov(rows_away))
    prof_avail = any(v.get(s, {}).get("status") == "AVAILABLE"
                     for v in prof_ctx["axes"].values() for s in ("HOME", "AWAY"))
    return {
        "venue": "AVAILABLE" if (venue_ok(rows_home) and venue_ok(rows_away)) else "LOW_COVERAGE",
        "recent_vs_long": "AVAILABLE" if (len(rows_home) >= 10 and len(rows_away) >= 10)
        else "LOW_COVERAGE",
        "opponent_profile": "AVAILABLE" if prof_avail else "LOW_COVERAGE",
        "formation": ("AVAILABLE" if fc >= 0.5 else
                      ("LOW_COVERAGE" if fc > 0 else "UNAVAILABLE")),
        "half_time_state": HALF_STATE_STATUS,        # 0% coverage measured
        "lineup": "PIT_UNSAFE",                       # announcement timestamp unproven
        "injuries": "UNAVAILABLE",
        "expected_formation": "UNAVAILABLE",
        "temporal_event_state": "UNAVAILABLE",        # only goal minutes; no general events
        "xg": "AVAILABLE",                            # 78.8% corpus coverage
        "red_cards": "AVAILABLE",
    }


# ----------------------------------------------------------------------------------------
# Full packet assembly (Arm B)
# ----------------------------------------------------------------------------------------
@dataclass
class FullFidelityPacket:
    fixture_id: str
    cutoff_unix: int
    policy: HistoryPolicy
    home_rows: list
    away_rows: list
    home_summaries: list
    away_summaries: list
    opponent_profile: dict
    availability: dict
    manifest_dict: dict
    notes: list = field(default_factory=list)

    def to_dict(self, include_hash=True, compact_rows=True) -> dict:
        """Serialize the packet.

        compact_rows=True packs match rows as parallel column arrays (columns + a values
        matrix) instead of repeating column names per row. This is a LOSSLESS deterministic
        re-encoding -- every cell value is preserved exactly, only the key repetition is
        removed -- and it materially reduces token cost. A test verifies the compact matrix
        reproduces the canonical cells exactly.
        """
        def pack(rows):
            cols = _row_columns()
            return {"columns": cols, "n_rows": len(rows),
                    "values": [[r.get(c) for c in cols] for r in rows]}
        home_block = (pack(self.home_rows) if compact_rows
                      else {"columns": _row_columns(), "rows": self.home_rows,
                            "n_rows": len(self.home_rows)})
        away_block = (pack(self.away_rows) if compact_rows
                      else {"columns": _row_columns(), "rows": self.away_rows,
                            "n_rows": len(self.away_rows)})
        body = {
            "packet_schema_version": FULL_FIDELITY_VIEW_VERSION,
            "arm": "B_full_fidelity",
            "row_encoding": "COLUMNAR_LOSSLESS" if compact_rows else "PER_ROW_DICT",
            "fixture_id": self.fixture_id,
            "information_cutoff_unix": self.cutoff_unix,
            "fixture": {"home": "HOME_TEAM", "away": "AWAY_TEAM",
                        "competition": "COMPETITION"},
            "history_policy": self.policy.to_dict(),
            "vocabulary": vocabulary.snapshot(),
            "capability_manifest": self.manifest_dict,
            "availability_map": self.availability,
            "match_level_history": {"HOME_TEAM": home_block, "AWAY_TEAM": away_block},
            "derived_summaries": {"HOME_TEAM": self.home_summaries,
                                  "AWAY_TEAM": self.away_summaries},
            "opponent_profile_context": self.opponent_profile,
            "notes": list(self.notes),
        }
        if include_hash:
            body["packet_hash"] = _hash(body)
        return body


def _row_columns() -> list:
    base = ["match_alias", "kickoff_unix", "competition", "venue", "opponent_alias",
            "own_formation_family", "opponent_formation_family"]
    for m in CANONICAL_MATCH_METRICS:
        base += [f"{m}_for", f"{m}_against"]
    return base


def _hash(body: dict) -> str:
    clean = {k: v for k, v in body.items() if k != "packet_hash"}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def build_full_fidelity_packet(target, index, policy=DEFAULT_POLICY) -> Optional[FullFidelityPacket]:
    cutoff = int(target.kickoff_unix)
    aliases = _alias_map(index, target, policy)
    comp_aliases = _comp_alias_map(index, target, policy)
    home_rows = build_match_rows(index, target, target.home, policy, aliases, comp_aliases)
    away_rows = build_match_rows(index, target, target.away, policy, aliases, comp_aliases)
    if len(home_rows) < policy.min_matches_per_team or len(away_rows) < policy.min_matches_per_team:
        return None
    home_sum = build_derived_summaries(home_rows, cutoff)
    away_sum = build_derived_summaries(away_rows, cutoff)
    prof = build_opponent_profile_context(index, target, policy, aliases)
    avail = build_availability_map(index, target, policy, home_rows, away_rows, prof)

    # reuse the frozen capability manifest builder for parity with Arm A
    from src.research.hypothesis_engine import context_packet as CP
    available_metrics = sorted({m for m in CANONICAL_MATCH_METRICS
                                if capability.is_supported_metric(m)})
    recorded = [CA.recorded_formations(r["match_alias"][2:]) for r in home_rows + away_rows]
    cov = CP.formation_coverage([f[0] if f else None for f in recorded])
    manifest = CP.build_capability_manifest(
        fixture_id=target.fixture_id, available_metrics=available_metrics,
        formation_coverage_report=cov, half_level_available=False,
        referee_available=False)
    return FullFidelityPacket(
        fixture_id=target.fixture_id, cutoff_unix=cutoff, policy=policy,
        home_rows=home_rows, away_rows=away_rows, home_summaries=home_sum,
        away_summaries=away_sum, opponent_profile=prof, availability=avail,
        manifest_dict=manifest.to_dict(),
        notes=[f"builder={FULL_FIDELITY_VIEW_VERSION}",
               f"home_rows={len(home_rows)}", f"away_rows={len(away_rows)}",
               "match-level rows are actual canonical observations; DERIVED_SUMMARY blocks "
               "supplement but do not replace them"])
