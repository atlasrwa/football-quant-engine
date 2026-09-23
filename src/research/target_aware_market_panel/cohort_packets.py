"""Fresh cohort selection and rich PIT-safe per-family packets for the Sol requests.

Reuses the verified pilot packet machinery (src.research.dual_provider_llm.packet) for field
mapping, FOR/AGAINST orientation, NULL != ZERO and the independent leakage re-derivation, then
adds genuine half-level aggregates and slices by frozen family context.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.research.dual_provider_llm import packet as P
from src.research.target_aware_market_panel import policy as POL
from src.research.thestatsapi.normalizer import _cell, parse_iso_to_unix

COHORT_VERSION = "target_aware_cohort_v1"
COHORT_SIZE = 12
EXCLUDED_FIXTURES = ("mt_022075291",)       # Girona v Albacete (used by earlier pilots)


def _load(p):
    try:
        return json.load(open(p))
    except (OSError, json.JSONDecodeError):
        return None


def fsha(p) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load_history(cache: str, include_gap_fetches: bool) -> Tuple[Dict[str, Any], Dict]:
    """Finished fixtures + unambiguous stats. Gap fetches (dpl_/tamp_) are packet-only."""
    versions: Dict[str, Dict] = {}
    for f in sorted(glob.glob(os.path.join(cache, "_all_fixtures*.json"))):
        for x in (_load(f) or {}).get("fixtures", []):
            if isinstance(x, dict) and str(x.get("status")).lower() == "finished":
                versions.setdefault(x["id"], {}).setdefault(P.fixture_identity(x), x)
    gap_files = []
    if include_gap_fetches:
        for f in sorted(glob.glob(os.path.join(cache, "dpl_match_mt_*.json"))
                        + glob.glob(os.path.join(cache, "tamp_match_mt_*.json"))):
            x = (_load(f) or {}).get("data")
            if isinstance(x, dict) and str(x.get("status")).lower() == "finished":
                versions.setdefault(x["id"], {}).setdefault(P.fixture_identity(x), x)
                gap_files.append(f)
    fixtures = {i: next(iter(v.values())) for i, v in versions.items() if len(v) == 1}
    names = []
    for f in sorted(glob.glob(os.path.join(cache, "*stats_mt_*.json"))):
        b = os.path.basename(f)
        if not include_gap_fetches and b.startswith(("dpl_", "tamp_")):
            continue
        names.append(f)
    ok, conf = P.build_stats_map((os.path.basename(f), _load(f)) for f in names)
    gap_hashes = {os.path.basename(f): fsha(f) for f in gap_files}
    for f in names:
        if os.path.basename(f).startswith(("dpl_", "tamp_")):
            gap_hashes[os.path.basename(f)] = fsha(f)
    return P.normalize_history(fixtures, ok, conf), {"n_fixtures": len(fixtures),
                                                      "n_stats_conflicts": len(conf),
                                                      "gap_fetch_files": gap_hashes}


def latest_scheduled(cache: str) -> Tuple[str, Dict[str, Dict], Dict[str, str]]:
    snaps = sorted(glob.glob(os.path.join(cache, "discovery_comp_*_scheduled_*_p*.json")))
    latest = max(re.search(r"_(20\d{6})_p", s).group(1) for s in snaps)
    files = [s for s in snaps if f"_{latest}_p" in s]
    up: Dict[str, Dict] = {}
    for s in files:
        for x in (_load(s) or {}).get("data", []):
            up.setdefault(x["id"], x)
    return latest, up, {os.path.basename(s): fsha(s) for s in files}


def select_cohort(history, scheduled: Dict[str, Dict], as_of_unix: int,
                  n: int = COHORT_SIZE) -> Tuple[List[Dict], Dict[str, Any]]:
    """Mechanical: future scheduled fixtures, both teams >= MIN_RICH_PRIOR_MATCHES rich prior
    matches (panel cache only), excluding earlier-pilot fixtures; per competition sorted by
    (kickoff, id); round-robin over competitions sorted by id until n."""
    by: Dict[str, List] = {}
    for x in scheduled.values():
        k = parse_iso_to_unix(x.get("utc_date"))
        if str(x.get("status")) != "scheduled" or k is None or k <= as_of_unix \
                or x["id"] in EXCLUDED_FIXTURES:
            continue
        rich = [sum(1 for h in P.team_history(history, (x.get(s) or {}).get("id"), k)
                    if h.has_rich) for s in ("home_team", "away_team")]
        if min(rich) >= P.MIN_RICH_PRIOR_MATCHES:
            by.setdefault(x["competition_id"], []).append((k, x["id"], x, rich))
    for c in by:
        by[c].sort(key=lambda t: (t[0], t[1]))
    comps, sel, i = sorted(by), [], 0
    while len(sel) < n and any(by[c] for c in comps):
        c = comps[i % len(comps)]
        i += 1
        if by[c]:
            sel.append(by[c].pop(0))
    return ([{"fixture_id": f"thestatsapi:{x['id']}", "provider_fixture_id": x["id"],
              "kickoff_unix": k, "kickoff_utc": x["utc_date"],
              "competition_id": x["competition_id"], "season_id": x.get("season_id"),
              "home_team": {"provider_team_id": x["home_team"]["id"],
                            "name": x["home_team"]["name"]},
              "away_team": {"provider_team_id": x["away_team"]["id"],
                            "name": x["away_team"]["name"]},
              "rich_prior_matches_home": r[0], "rich_prior_matches_away": r[1]}
             for k, _, x, r in sel],
            {"eligible_per_competition_before_selection": {c: len(v) for c, v in by.items()}})


def _half_aggregates(history, team_id, role, cutoff, metrics) -> List[Dict[str, Any]]:
    rows = P.team_history(history, team_id, cutoff)
    out = []
    for m in metrics:
        grp, key = POL.HALF_PROVIDER_FIELDS[m]
        for period, pk in (("FIRST_HALF", "first_half"), ("SECOND_HALF", "second_half")):
            for w, subset in (("ALL_PRIOR", rows), ("RECENT_10", rows[-10:])):
                for persp in ("FOR", "AGAINST"):
                    vals, used = [], []
                    for h in subset:
                        _, fs, ag, _ = P.perspective(h, team_id)
                        v = _cell((h.stats or {}).get("data") or {}, grp, key, pk,
                                  fs if persp == "FOR" else ag)
                        if v is not None:
                            vals.append(float(v))
                            used.append(h)
                    if not vals:
                        continue
                    out.append({"evidence_ref": P.ref(role, m, persp, w, "ALL", period),
                                "provider": P.PROVIDER, "canonical_concept": m,
                                "provider_field": f"stats.{grp}.{key}.{pk}", "team_role": role,
                                "perspective": persp, "period": period, "window": w,
                                "venue_scope": "ALL", "value": round(sum(vals) / len(vals), 4),
                                "sample_n": len(vals),
                                "coverage": round(len(vals) / len(subset), 4),
                                "cutoff_unix": cutoff,
                                "observed_at_max": max(h.kickoff_unix for h in used)})
    return out


def build_fixture_packet(history, fx: Dict[str, Any], as_of: int, norm_ver: str
                         ) -> Dict[str, Any]:
    """Full (all-concept) PIT packet for one cohort fixture, leakage-checked."""
    T = int(fx["kickoff_unix"])
    tid = fx["provider_fixture_id"]
    if tid in history:
        raise ValueError("target fixture present in history")
    blocks = {r: P.build_team_block(history, fx[k]["provider_team_id"], r, T, norm_ver)
              for r, k in (("HOME_TEAM", "home_team"), ("AWAY_TEAM", "away_team"))}
    pk = {"contract_version": P.CONTRACT_VERSION, "fixture": {
              "fixture_id": fx["fixture_id"], "provider_fixture_id": tid,
              "kickoff_unix": T, "kickoff_utc": fx["kickoff_utc"],
              "competition": fx["competition_id"], "season_id": fx["season_id"],
              "home_team": fx["home_team"], "away_team": fx["away_team"],
              "target_outcome_included": False},
          "cutoff_unix": T, "data_cutoff_unix": as_of, "selection_rule": {},
          "target_outcome_included": False, "market_data_included": False,
          "p_model_included": False,
          "raw_recent_matches": {r: b["raw_recent_matches"] for r, b in blocks.items()},
          "aggregate_evidence": [x for b in blocks.values() for x in b["aggregate_evidence"]],
          "windows": {r: b["windows"] for r, b in blocks.items()},
          "coverage": {r: {k: v for k, v in b["coverage"].items() if k != "per_metric_FOR"}
                       for r, b in blocks.items()}}
    checks = P.leakage_checks(pk, history, tid)
    if not P.leakage_ok(checks):
        raise ValueError(f"leakage check failed for {tid}: {checks}")
    pk["leakage_checks"] = checks
    pk["_blocks"] = blocks
    return pk


def family_slice(pk: Dict[str, Any], history, family: str) -> Dict[str, Any]:
    """Deterministic slice to the family's frozen metric list (+ genuine half aggregates)."""
    keep = set(POL.FAMILY_CONTEXT[family])
    agg = [a for a in pk["aggregate_evidence"] if a["canonical_concept"] in keep]
    raw = {}
    for r, rows in pk["raw_recent_matches"].items():
        raw[r] = [{**{k: v for k, v in row.items() if k != "values"},
                   "values": {ref: v for ref, v in row["values"].items()
                              if ref.split(".")[4] in keep}} for row in rows]
    T = pk["cutoff_unix"]
    half = []
    for r, k in (("HOME_TEAM", "home_team"), ("AWAY_TEAM", "away_team")):
        half += _half_aggregates(history, pk["fixture"][k]["provider_team_id"], r, T,
                                 POL.HALF_CONTEXT.get(family, []))
    refs = [a["evidence_ref"] for a in agg] + [h["evidence_ref"] for h in half] + [
        ref for rows in raw.values() for row in rows for ref in row["values"]]
    if len(refs) != len(set(refs)):
        raise ValueError("duplicate evidence refs in slice")
    return {"family": family, "fixture": pk["fixture"], "cutoff_unix": T,
            "data_cutoff_unix": pk["data_cutoff_unix"],
            "providers_used": [P.PROVIDER], "metrics_in_slice": sorted(keep),
            "field_semantics": {c: s for c, s in P.concept_semantics().items() if c in keep},
            "aggregate_evidence": agg, "half_level_evidence": half,
            "raw_recent_matches": raw, "windows": pk["windows"],
            "coverage": pk["coverage"],
            "evidence_ref_index": sorted(refs), "n_evidence_refs": len(refs),
            "target_outcome_included": False, "market_data_included": False,
            "p_model_included": False}


def verify_half_evidence(slice_: Dict[str, Any], rows_by_team: Dict[str, list]) -> int:
    """Independent re-derivation of every half-level aggregate through the panel-row path
    (panel.rows_from_history), not the packet's own cell reads. Returns the mismatch count."""
    T = slice_["cutoff_unix"]
    team_of = {"HOME_TEAM": slice_["fixture"]["home_team"]["provider_team_id"],
               "AWAY_TEAM": slice_["fixture"]["away_team"]["provider_team_id"]}
    bad = 0
    for a in slice_["half_level_evidence"]:
        rows = [r for r in rows_by_team.get(team_of[a["team_role"]], []) if r.kickoff < T]
        rows.sort(key=lambda r: (r.kickoff, r.match_id))
        if a["window"] == "RECENT_10":
            rows = rows[-10:]
        vals = [v for r in rows for v in [r.get(a["canonical_concept"], a["perspective"],
                                                a["period"])] if v is not None]
        if not vals or round(sum(vals) / len(vals), 4) != a["value"] or \
                len(vals) != a["sample_n"]:
            bad += 1
    return bad
