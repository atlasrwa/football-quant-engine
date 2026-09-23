"""GATED runner for the six compiled query specs. NOT executed in the design freeze.

`run_all(hist, ctx, specs)` computes every primary/secondary measurement on a PITHistory; the
CLI refuses to load real data unless HEAD == --authorized-head and the worktree is clean.
No LLM, no network, no model fit for prediction, no p_model.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.research.dual_provider_llm.measurement import measures as M
from src.research.dual_provider_llm.measurement import support as S
from src.research.dual_provider_llm.measurement.pit_history import PITHistory, TeamMatch
from src.research.dual_provider_llm.measurement.similarity import (nearest, profile,
                                                                    rms_distance, shrink,
                                                                    state_vector)

Dim = Tuple[str, str]


def _dims(xs) -> Tuple[Dim, ...]:
    return tuple((str(a), str(b)) for a, b in xs)


def output_value(hist: PITHistory, row: TeamMatch, outputs: Dict[str, Any], before: int,
                 by_venue: bool) -> Optional[float]:
    comb = outputs["combine"]
    if comb == "contrast":
        plus = [hist.z(row, m, p, before, by_venue) for m, p in outputs["contrast"]["plus"]]
        minus = [hist.z(row, m, p, before, by_venue)
                 for m, p in outputs["contrast"]["minus_mean_of"]]
        if any(v is None for v in plus + minus):
            return None
        return float(np.mean(plus) - np.mean(minus))
    zs = [hist.z(row, m, p, before, by_venue) for m, p in outputs["metrics"]]
    if any(v is None for v in zs):
        return None
    return float(np.mean(zs))


def _coverage(hist, rows, metrics, by_venue) -> Dict[str, Any]:
    out = {}
    for m, p in metrics:
        n = sum(1 for r in rows if hist.z(r, m, p, r.kickoff_unix, by_venue) is not None)
        st, why = S.metric_coverage(n, len(rows))
        out[f"{m}.{p}"] = {"n_non_null_scaled": n, "n_candidates": len(rows), "status": st}
    return out


def _strength_balance(hist, rows_a, rows_b) -> Dict[str, Any]:
    def s(rows):
        v = [hist.strength(r.opponent_id, r.competition_id, r.kickoff_unix) for r in rows]
        got = [x for x in v if x is not None]
        return {"n": len(rows), "n_with_strength": len(got),
                "mean": float(np.mean(got)) if got else None}
    return {"group_a": s(rows_a), "group_b": s(rows_b)}


def _composition(rows) -> Dict[str, Any]:
    comp, seas = {}, {}
    for r in rows:
        comp[r.competition_id] = comp.get(r.competition_id, 0) + 1
        seas[r.season_id] = seas.get(r.season_id, 0) + 1
    return {"competitions": dict(sorted(comp.items())), "seasons": dict(sorted(seas.items()))}


def run_neighbor_group(spec, hist: PITHistory, subject: str, query: str, T: int,
                       subj_venue: str, opp_venue: str) -> Dict[str, Any]:
    dims = _dims(spec["similarity_dimensions"])
    q, qmeta = profile(hist, query, T, opp_venue, dims)
    if q is None:
        return {"status": S.Status.NO_QUERY_PROFILE, "query_meta": qmeta}
    rows = hist.team_rows(subject, T, venue=subj_venue)
    cov = _coverage(hist, rows, spec["outputs"]["metrics"], False)
    if any(v["status"] != S.Status.OK for v in cov.values()):
        return {"status": S.Status.UNSUPPORTED_METRIC, "coverage": cov}
    cand = []
    for r in rows:
        y = output_value(hist, r, spec["outputs"], r.kickoff_unix, False)
        p, _ = profile(hist, r.opponent_id, r.kickoff_unix, opp_venue, dims)
        if y is not None and p is not None:
            cand.append((r, y, rms_distance(p, q, dims)))
    st, why = S.group_support(len(cand))
    res = {"status": st, "reason": why, "n_candidates": len(rows), "n_eligible": len(cand),
           "coverage": cov, "query_profile": {f"{m}.{p}": v for (m, p), v in q.items()}}
    if st != S.Status.OK:
        return res
    k = S.neighbor_count(len(cand))
    nn, rest = nearest([(r.match_id, d, r.kickoff_unix) for r, _, d in cand], k)
    by = {r.match_id: (r, y) for r, y, _ in cand}
    ya, yb = [by[i][1] for i in nn], [by[i][1] for i in rest]
    res["primary"] = M.group_difference(ya, yb)
    res["neighbor_match_ids"] = nn
    res["composition"] = {"neighbors": _composition([by[i][0] for i in nn]),
                          "comparison": _composition([by[i][0] for i in rest])}
    res["strength_balance"] = _strength_balance(hist, [by[i][0] for i in nn],
                                                [by[i][0] for i in rest])
    per = {}
    for m, p in spec["outputs"]["metrics"]:
        za = [hist.z(by[i][0], m, p, by[i][0].kickoff_unix, False) for i in nn]
        zb = [hist.z(by[i][0], m, p, by[i][0].kickoff_unix, False) for i in rest]
        per[f"{m}.{p}"] = float(np.mean(za) - np.mean(zb))
    res["secondary_per_channel_difference"] = per
    rows_s = [(1.0 if i in set(nn) else 0.0, by[i][1],
               hist.strength(by[i][0].opponent_id, by[i][0].competition_id,
                             by[i][0].kickoff_unix)) for i in nn + rest]
    rows_s = [t for t in rows_s if t[2] is not None]
    if len(rows_s) >= S.value("MIN_OBS_PER_PARAMETER") * 3:
        X = np.column_stack([np.ones(len(rows_s)), [t[0] for t in rows_s],
                             [t[2] for t in rows_s]])
        beta = np.linalg.lstsq(X, np.array([t[1] for t in rows_s]), rcond=None)[0]
        res["secondary_strength_adjusted_difference"] = {"coef": float(beta[1]),
                                                         "n": len(rows_s)}
    else:
        res["secondary_strength_adjusted_difference"] = {"status": S.Status.INSUFFICIENT_SUPPORT}
    return res


def run_interaction(spec, hist, subject, query, T) -> Dict[str, Any]:
    rows = hist.team_rows(subject, T, venue="HOME")
    need = [("accurate_crosses", "FOR"), ("touches_in_box", "FOR"), ("corners", "FOR")]
    cov = _coverage(hist, rows, need, False)
    if any(v["status"] != S.Status.OK for v in cov.values()):
        return {"status": S.Status.UNSUPPORTED_METRIC, "coverage": cov}
    data = []
    for r in rows:
        v = [hist.z(r, m, p, r.kickoff_unix, False) for m, p in need]
        if all(x is not None for x in v):
            data.append((r, *v))
    st, why = S.regression_support(len(data), 4)
    res = {"status": st, "reason": why, "n_eligible": len(data), "coverage": cov}
    if st != S.Status.OK:
        return res
    res["primary"] = M.interaction_coef([d[1] for d in data], [d[2] for d in data],
                                        [d[3] for d in data])
    dims = _dims(spec["similarity_dimensions"])
    q, _ = profile(hist, query, T, "AWAY", dims)
    sub = []
    if q is not None:
        cand = []
        for d in data:
            p, _ = profile(hist, d[0].opponent_id, d[0].kickoff_unix, "AWAY", dims)
            if p is not None:
                cand.append((d, rms_distance(p, q, dims)))
        nn, _ = nearest([(c[0][0].match_id, c[1], c[0][0].kickoff_unix) for c in cand],
                        S.neighbor_count(len(cand)))
        sub = [c[0] for c in cand if c[0][0].match_id in set(nn)]
    st2, why2 = S.regression_support(len(sub), 4)
    res["secondary_neighbor_subset"] = (
        {"status": st2, "reason": why2, "n": len(sub)} if st2 != S.Status.OK else
        {"status": st2, **M.interaction_coef([d[1] for d in sub], [d[2] for d in sub],
                                             [d[3] for d in sub])})
    return res


def run_conditional_rank(spec, hist, subject, query, T) -> Dict[str, Any]:
    rows = hist.team_rows(subject, T, venue="AWAY")
    need = [("possession", "FOR"), ("accurate_long_balls", "FOR"),
            ("final_third_entries", "FOR"), ("shots", "FOR"), ("corners", "FOR")]
    cov = _coverage(hist, rows, need, False)
    if any(v["status"] != S.Status.OK for v in cov.values()):
        return {"status": S.Status.UNSUPPORTED_METRIC, "coverage": cov}
    data = []
    for r in rows:
        v = {m: hist.z(r, m, p, r.kickoff_unix, False) for m, p in need}
        if any(x is None for x in v.values()) or v["possession"] >= 0:
            continue
        dpi = (v["accurate_long_balls"] + v["final_third_entries"]) / 2
        data.append((r, dpi, output_value(hist, r, spec["outputs"], r.kickoff_unix, False)))
    st = S.Status.OK if len(data) >= S.value("MIN_SUBJECT_MATCHES") else \
        S.Status.INSUFFICIENT_SUPPORT
    res = {"status": st, "n_low_possession_eligible": len(data), "coverage": cov}
    if st != S.Status.OK:
        res["reason"] = "low-possession away matches below MIN_SUBJECT_MATCHES"
        return res
    res["primary"] = M.rank_association([d[1] for d in data], [d[2] for d in data])
    dims = _dims(spec["similarity_dimensions"])
    q, _ = profile(hist, query, T, "HOME", dims)
    sub = []
    if q is not None:
        cand = [(d, p) for d in data
                for p in [profile(hist, d[0].opponent_id, d[0].kickoff_unix, "HOME", dims)[0]]
                if p is not None]
        nn, _ = nearest([(d[0].match_id, rms_distance(p, q, dims), d[0].kickoff_unix)
                         for d, p in cand], S.neighbor_count(len(cand)))
        sub = [d for d, _ in cand if d[0].match_id in set(nn)]
    res["secondary_neighbor_subset"] = (
        {"status": S.Status.INSUFFICIENT_SUPPORT, "n": len(sub)}
        if len(sub) < S.value("MIN_SUBJECT_MATCHES") else
        {"status": S.Status.OK, **M.rank_association([d[1] for d in sub], [d[2] for d in sub])})
    return res


def run_state_residual(spec, hist, subject, T) -> Dict[str, Any]:
    dims = _dims(spec["state_dimensions"])
    allv = hist.team_rows(subject, T, n=int(S.value("PROFILE_WINDOW_MATCHES")))
    ref_ids = {r.match_id for r in allv}
    st10 = [v for r in allv for v in [state_vector(hist, r, dims, T, True)] if v is not None]
    last5 = allv[-int(S.value("RECENT_BLOCK_MATCHES")):]
    st5 = [v for r in last5 for v in [state_vector(hist, r, dims, T, True)] if v is not None]
    if len(st10) < S.value("MIN_PROFILE_MATCHES_PER_DIM") or not st5:
        return {"status": S.Status.NO_QUERY_PROFILE, "n_r10": len(st10), "n_r5": len(st5)}
    R10 = {d: float(np.mean([v[d] for v in st10])) for d in dims}
    R5 = {d: float(np.mean([v[d] for v in st5])) for d in dims}
    Sst = shrink(R5, R10, len(st5))
    rows = [r for r in hist.team_rows(subject, T, venue="HOME") if r.match_id not in ref_ids]
    data = []
    for r in rows:
        v = state_vector(hist, r, dims, r.kickoff_unix, True)
        y = output_value(hist, r, spec["outputs"], r.kickoff_unix, True)
        if v is not None and y is not None:
            data.append((r, v, y, float(np.mean(list(v.values())))))
    st, why = S.group_support(len(data))
    res = {"status": st, "reason": why, "n_eligible": len(data),
           "n_reference_matches_excluded": len(ref_ids & {r.match_id for r in
                                                          hist.team_rows(subject, T,
                                                                         venue="HOME")}),
           "R5": {f"{a}.{b}": x for (a, b), x in R5.items()},
           "R10": {f"{a}.{b}": x for (a, b), x in R10.items()},
           "S": {f"{a}.{b}": x for (a, b), x in Sst.items()}}
    if st != S.Status.OK:
        return res
    resid = M.residualize([d[2] for d in data], [d[3] for d in data])
    rid = {d[0].match_id: e for d, e in zip(data, resid)}
    k = S.neighbor_count(len(data))
    g1, rest = nearest([(d[0].match_id, rms_distance(d[1], Sst, dims), d[0].kickoff_unix)
                        for d in data], k)
    rest_d = [d for d in data if d[0].match_id in set(rest)]
    g2, _ = nearest([(d[0].match_id, rms_distance(d[1], R10, dims), d[0].kickoff_unix)
                     for d in rest_d], min(k, len(rest_d)))
    res["primary"] = M.group_difference([rid[i] for i in g1], [rid[i] for i in g2])
    yid = {d[0].match_id: d[2] for d in data}
    res["secondary_raw_output_difference"] = float(np.mean([yid[i] for i in g1])
                                                   - np.mean([yid[i] for i in g2]))
    res["groups"] = {"near_recent_state": g1, "near_r10_state": g2}
    return res


def run_recent_block(spec, hist, subject, T) -> Dict[str, Any]:
    sdims = _dims(spec["state_dimensions"])
    adims = _dims(spec["similarity_dimensions"])
    rows = hist.team_rows(subject, T, venue="AWAY")
    vecs = []
    for r in rows:
        p, _ = profile(hist, r.opponent_id, r.kickoff_unix, "HOME", adims, by_venue=True)
        if p is None:
            continue
        v = {}
        for (m, persp) in sdims:
            z = hist.z(r, m, persp, r.kickoff_unix, True)
            if z is None:
                v = None
                break
            v[(m, persp)] = z - p[(m, "AGAINST")] if (m, "AGAINST") in p else z
        if v is not None:
            vecs.append((r, v))
    nb = int(S.value("RECENT_BLOCK_MATCHES"))
    if len(vecs) < nb + S.value("MIN_LONG_RUN_MATCHES"):
        return {"status": S.Status.INSUFFICIENT_SUPPORT, "n_valid_away": len(vecs)}

    def block_stat(block, prior):
        rec = {d: float(np.mean([v[d] for _, v in block])) for d in sdims}
        lr = {d: float(np.mean([v[d] for _, v in prior])) for d in sdims}
        s5 = shrink(rec, lr, len(block))
        diff = {d: s5[d] - lr[d] for d in sdims}
        return float(np.mean(list(diff.values()))), diff, rms_distance(s5, lr, sdims)

    comp, diff, dist = block_stat(vecs[-nb:], vecs[:-nb])
    hist_blocks, end = [], len(vecs) - nb
    while end - nb >= S.value("MIN_LONG_RUN_MATCHES"):
        hist_blocks.append(block_stat(vecs[end - nb:end], vecs[:end - nb])[0])
        end -= nb
    return {"status": S.Status.OK, "n_valid_away": len(vecs),
            "primary": M.block_percentile(comp, hist_blocks),
            "per_dimension_difference": {f"{a}.{b}": x for (a, b), x in diff.items()},
            "state_distance": dist, "recent_block_match_ids": [r.match_id for r, _ in
                                                               vecs[-nb:]]}


def run_all(hist: PITHistory, ctx: Dict[str, Any], specs: Sequence[Dict[str, Any]]
            ) -> Dict[str, Any]:
    H, A, T = ctx["home_team_id"], ctx["away_team_id"], int(ctx["cutoff_unix"])
    out = {}
    for s in specs:
        mid, d = s["mechanism_id"], s["design"]
        if d == "NEIGHBOR_GROUP_DIFFERENCE":
            out[mid] = run_neighbor_group(s, hist, H, A, T, "HOME", "AWAY")
        elif d == "INTERACTION_REGRESSION":
            out[mid] = run_interaction(s, hist, H, A, T)
        elif d == "CONDITIONAL_RANK_ASSOCIATION":
            out[mid] = run_conditional_rank(s, hist, A, H, T)
        elif d == "STATE_RESIDUAL_GROUP_DIFFERENCE":
            out[mid] = run_state_residual(s, hist, H, T)
        elif d == "RECENT_BLOCK_DESCRIPTIVE":
            out[mid] = run_recent_block(s, hist, A, T)
        else:
            raise ValueError(d)
    return {"results": out, **apply_fixed_family_bh(out)}


#: The preregistered inferential family (protocol section 6). It NEVER shrinks with runtime
#: support status. DP5 is descriptive and is never a member.
FROZEN_BH_FAMILY: Tuple[str, ...] = (
    "DP1_BOX_PRESSURE_MATCHUP",
    "DP2_WIDE_CENTRAL_INTERACTION",
    "DP3_ALBACETE_DIRECT_PROGRESSION",
    "DP4_GIRONA_CURRENT_TERRITORIAL_REGIME",
    "DP6_PRESSURE_RESOLUTION_CLEARANCE_PROFILE",
)
NON_EVALUABLE_STATUSES = (S.Status.INSUFFICIENT_SUPPORT, S.Status.UNSUPPORTED_METRIC,
                          S.Status.NO_QUERY_PROFILE)
#: PRE_EXECUTION_IMPLEMENTATION_AMENDMENT: a non-evaluable frozen family member enters BH with
#: this input solely for multiplicity bookkeeping, so the preregistered family size stays fixed.
#: It is NOT a measured p-value and is never written as one.
NON_EVALUABLE_BH_INPUT_P = 1.0


def apply_fixed_family_bh(results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Benjamini-Hochberg over exactly FROZEN_BH_FAMILY, whatever each member's status."""
    inputs, n_eval = [], 0
    for mid in FROZEN_BH_FAMILY:
        r = results[mid]                           # a missing member is a hard error
        st = r.get("status")
        if st == S.Status.OK:
            p = r["primary"]["p_two_sided"]        # an OK member must carry a real p-value
            if p is None:
                raise ValueError(f"{mid}: status OK without a p-value")
            inputs.append((mid, float(p), False))
            n_eval += 1
        elif st in NON_EVALUABLE_STATUSES:
            inputs.append((mid, NON_EVALUABLE_BH_INPUT_P, True))
        else:
            raise ValueError(f"{mid}: unknown status {st!r}")
    qs = M.bh_adjust([p for _, p, _ in inputs])
    for (mid, p, placeholder), q in zip(inputs, qs):
        results[mid]["multiplicity"] = {
            "primary_p_value": None if placeholder else p,
            "bh_input_p": p,
            "bh_q": q,
            "multiplicity_placeholder": placeholder,
            "evaluable": not placeholder,
            "interpretation": ("NOT EVALUABLE UNDER THE FROZEN SUPPORT RULE (bh_input_p is "
                               "bookkeeping only, not evidence for the null)") if placeholder
                              else "evaluated",
        }
    if "DP5_ALBACETE_RECENT_TERRITORIAL_EXPANSION" in results:
        results["DP5_ALBACETE_RECENT_TERRITORIAL_EXPANSION"]["multiplicity"] = {
            "in_bh_family": False, "descriptive_only": True}
    return {"BH_FAMILY_FROZEN": list(FROZEN_BH_FAMILY),
            "N_FROZEN_BH_TESTS": len(FROZEN_BH_FAMILY),
            "N_BH_EVALUABLE": n_eval, "N_BH_NON_EVALUABLE": len(FROZEN_BH_FAMILY) - n_eval,
            "NON_EVALUABLE_BH_INPUT_P": NON_EVALUABLE_BH_INPUT_P,
            "bh_q_level": S.value("BH_Q")}


class GateError(RuntimeError):
    pass


def gate(root: Path, authorized_head: str) -> str:
    g = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True,  # noqa: E731
                                  capture_output=True, text=True).stdout.strip()
    head = g("rev-parse", "HEAD")
    if head != authorized_head:
        raise GateError(f"HEAD {head} != authorized {authorized_head}")
    if g("status", "--porcelain"):
        raise GateError("worktree not clean")
    return head


def load_real_history(cache: Path, packet_path: Path) -> Tuple[PITHistory, Dict[str, Any]]:
    """Mirror of the packet builder's loading rules (same sources, same conflict exclusions).
    Only called after the gate. The target fixture id and anything at/after its kickoff are
    excluded; the fetched gap files must match the packet's recorded hashes."""
    import hashlib
    from src.research.dual_provider_llm import packet as P
    from src.research.dual_provider_llm.measurement.pit_history import team_matches_from_history
    pk = json.loads(packet_path.read_text())
    T, tid = int(pk["cutoff_unix"]), pk["fixture"]["provider_fixture_id"]
    for name, h in pk["provenance"]["fetched_gap_files"].items():
        if hashlib.sha256((cache / name).read_bytes()).hexdigest() != h:
            raise GateError(f"fetched gap file {name} differs from the packet provenance")

    def load(f):
        try:
            return json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            return None
    versions: Dict[str, Dict] = {}
    files = (sorted(cache.glob("_all_fixtures*.json"))
             + sorted(cache.glob("fixtures_sn_*_finished_*.json"))
             + sorted(cache.glob("*_matches_sn_*.json")))
    for f in files:
        d = load(f) or {}
        for x in (d.get("fixtures") or d.get("data") or []):
            if isinstance(x, dict) and str(x.get("status")).lower() == "finished" and x.get("id"):
                versions.setdefault(x["id"], {}).setdefault(P.fixture_identity(x), x)
    for f in sorted(cache.glob("dpl_match_mt_*.json")):
        x = (load(f) or {}).get("data")
        if isinstance(x, dict) and str(x.get("status")).lower() == "finished":
            versions.setdefault(x["id"], {}).setdefault(P.fixture_identity(x), x)
    fixtures = {i: next(iter(v.values())) for i, v in versions.items()
                if len(v) == 1 and i != tid}
    ok, conf = P.build_stats_map((f.name, load(f)) for f in sorted(cache.glob("*stats_mt_*.json")))
    ok.pop(tid, None)
    hist = PITHistory(team_matches_from_history(P.normalize_history(fixtures, ok, conf)), T,
                      excluded_match_ids=[tid])
    ctx = {"cutoff_unix": T, "target_fixture_id": tid,
           "home_team_id": pk["fixture"]["home_team"]["provider_team_id"],
           "away_team_id": pk["fixture"]["away_team"]["provider_team_id"]}
    return hist, ctx


def main(argv=None) -> None:
    """GATED: python -m src.research.dual_provider_llm.measurement.executor --authorized-head H"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--authorized-head", required=True)
    ap.add_argument("--cache", default="/home/ubuntu/data/thestatsapi/championship")
    a = ap.parse_args(argv)
    root = Path(__file__).resolve().parents[4]
    head = gate(root, a.authorized_head)
    specs = json.loads((root / "research/dual_provider_llm/measurement/"
                               "DIRECT_HYPOTHESIS_QUERY_SPECS_V1.json").read_text())["specs"]
    hist, ctx = load_real_history(
        Path(a.cache), root / "research/dual_provider_llm/out/direct_pilot/"
                              "PILOT_FIXTURE_PACKET_V1.json")
    res = run_all(hist, ctx, specs)
    res.update({"authorized_head": head, "context": ctx, "outcomes_of_target_read": False,
                "p_model_produced": False})
    out = root / "research/dual_provider_llm/measurement/out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "DIRECT_HYPOTHESIS_MEASUREMENT_RESULTS_V1.json").write_text(
        json.dumps(res, indent=1, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
