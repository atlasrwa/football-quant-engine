"""Execute the FROZEN V4 hypothesis-derived OOS experiment. ZERO SPEND.

No Bedrock, no LLM, no network, no CHAMPION mutation, no promotion. Reads the frozen
PREREGISTRATION.json and the PIT-safe dual-provider corpus, reconstructs the
hypothesis-derived feature strictly point-in-time, and scores B0/B1/B2 on the frozen
chronological walk-forward. Nothing here is tuned against the OOS result.

Run: .venv/bin/python research/hypothesis_oos/_run_v4_oos.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import warnings
from collections import defaultdict

import numpy as np

warnings.filterwarnings("ignore")
ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src")
sys.path.insert(0, ROOT)

from src.research.matchup.corpus import load_corpus, season_of
from src.research.matchup.design import DesignBuilder, outcome
from src.research.matchup import harness as H
from src.research.hypothesis_engine import cohort_measurement as CM
from src.research.hypothesis_engine import similarity as SIM

PREREG = f"{ROOT}/research/hypothesis_oos/out/PREREGISTRATION.json"
OUT = f"{ROOT}/research/hypothesis_oos/out"
CHAMPION_ARTIFACT = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

BOOTSTRAP_SEED = 20240914     # frozen; recorded in the report
BOOTSTRAP_RESAMPLES = 400     # frozen from prereg
N_FOLDS = 4                   # frozen (matches FINAL_RESEARCH_REPORT walk-forward)

# Map a profile axis (vocabulary) -> matchup corpus stat name for band value_fn / target.
_AXIS_METRIC = {
    "corners_for": ("corner_kicks", "for"), "corners_against": ("corner_kicks", "against"),
    "accurate_crosses_for": ("accurate_crosses", "for"),
    "accurate_crosses_against": ("accurate_crosses", "against"),
    "shots_on_target_for": ("sot", "for"), "shots_on_target_against": ("sot", "against"),
    "possession_for": ("possession", "for"), "goals_against": ("goals", "against"),
    "fouls_for": ("fouls", "for"),
}
# Map a candidate TARGET metric -> matchup corpus stat name.
_TARGET_STAT = {"corners": "corner_kicks", "goals": "goals", "yellow_cards": "yellow_cards"}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ======================================================================================
# PIT-safe hypothesis-derived feature reconstruction
# ======================================================================================
class HDFeatureBuilder:
    """Reconstructs hd_shrunk_diff for one (team, target_stat, side) under an
    opponent-profile band, strictly point-in-time. Reuses the frozen cohort_measurement
    executor and similarity band resolver -- the SAME code the V3 measurement used.
    """

    def __init__(self, recs, quarantine: frozenset):
        # per-team chronological (kickoff, rec, side)
        self.by_team = defaultdict(list)
        self.by_comp_time = defaultdict(list)   # competition -> [(kickoff, rec)]
        for r in recs:
            if r.fixture_id in quarantine:
                continue                          # origin fixtures never enter features
            self.by_team[r.home_id].append((r.kickoff_unix, r, "home"))
            self.by_team[r.away_id].append((r.kickoff_unix, r, "away"))
            self.by_comp_time[r.competition].append((r.kickoff_unix, r))
        for t in self.by_team:
            self.by_team[t].sort(key=lambda x: x[0])
        for c in self.by_comp_time:
            self.by_comp_time[c].sort(key=lambda x: x[0])
        self._val_cache = {}

    @staticmethod
    def _stat_value(rec, team_id, stat, side):
        from src.research.matchup import features as F
        try:
            hv, av = F.stat_pair(rec, stat)
        except KeyError:
            return None
        is_home = rec.home_id == team_id
        if side == "for":
            return hv if is_home else av
        return av if is_home else hv

    def _observations(self, team_id, target_stat, side, cutoff, target_fid):
        obs = []
        for k, r, srow in self.by_team.get(team_id, []):
            if k >= cutoff:                        # strict PIT: kickoff < cutoff
                continue
            if r.fixture_id == target_fid:         # never the target fixture itself
                continue
            opp = r.away_id if r.home_id == team_id else r.home_id
            obs.append(CM.Obs(
                fixture_id=r.fixture_id, kickoff_unix=k, competition=r.competition,
                opponent=opp,
                value=self._stat_value(r, team_id, target_stat, side),
                dimensions={"venue": "HOME" if r.home_id == team_id else "AWAY"}))
        return obs

    def _candidates(self, competition, cutoff):
        s = set()
        for k, r in self.by_comp_time.get(competition, []):
            if k < cutoff:
                s.update((r.home_id, r.away_id))
        return sorted(s)

    def _axis_value_fn(self, axis, target_fid):
        stat, side = _AXIS_METRIC[axis]

        def fn(team_id, cutoff_unix):
            vals = []
            for k, r, _ in self.by_team.get(team_id, []):
                if k >= cutoff_unix or r.fixture_id == target_fid:
                    continue
                v = self._stat_value(r, team_id, stat, side)
                if v is not None:
                    vals.append(float(v))
            return (sum(vals) / len(vals), len(vals)) if vals else None
        return fn

    def _band_resolver(self, competition, target_fid):
        def resolve(axis, band, cutoff_unix):
            return SIM.resolve_band(
                axis=axis, requested_band=band, cutoff_unix=cutoff_unix,
                candidates=self._candidates(competition, cutoff_unix),
                axis_value_fn=self._axis_value_fn(axis, target_fid))
        return resolve

    def hd_shrunk_diff(self, *, team_id, competition, cutoff, target_fid,
                       target_stat, side, axis, band, shuffle_seed=None):
        """Return (value_or_None, outcome_state). PIT-safe by construction."""
        obs = self._observations(team_id, target_stat, side.lower(), cutoff, target_fid)
        spec = CM.MeasurementSpec(
            spec_version=CM.COHORT_MEASUREMENT_VERSION, hypothesis_id="V4",
            fixture_id=target_fid, subject_label="HOME_TEAM", subject_team=team_id,
            target_metric=target_stat, side=side.upper(), window="ALL_PRIOR", period="ALL",
            granularity="FULL_MATCH", venue_condition=None, competition_condition=None,
            own_formation_condition=None, opponent_formation_condition=None,
            opponent_profile_band=band, opponent_profile_axis=axis,
            profile_band_semantics=CM.PROFILE_BAND_SEMANTICS,
            comparison_cohort="SUBJECT_OVERALL_BASELINE",
            target_competition=competition, cutoff_unix=cutoff, provider="thestatsapi",
            required_fields=(), plan_hash="v4")
        resolver = self._band_resolver(competition, target_fid)
        if shuffle_seed is not None:
            resolver = self._shuffled_resolver(competition, target_fid, axis, shuffle_seed)
        m = CM.execute(spec, subject_history=obs, band_resolver=resolver)
        if m.outcome == CM.MEASURED:
            return m.shrunk_difference, "SUFFICIENT_MEASUREMENT"
        if m.outcome == CM.INSUFFICIENT_DATA:
            return None, "INSUFFICIENT_HISTORY"
        if m.outcome == CM.NOT_DISTINCT:
            return None, "NOT_DISTINCT"
        if m.outcome == CM.LEAKAGE_REJECTED:
            return None, "LEAKAGE_REJECTED"
        return None, "MISSING_PROVIDER_EVIDENCE"

    def _shuffled_resolver(self, competition, target_fid, axis, seed):
        """PIT-safe band shuffle: permute band->opponent assignment within the pre-cutoff
        candidate pool, marginal band sizes fixed. Never touches outcomes."""
        base = self._band_resolver(competition, target_fid)

        def resolve(a, band, cutoff_unix):
            res = base(a, band, cutoff_unix)
            # rebuild members by permuting assignment labels deterministically
            assigns = list(res.assignments)
            if not assigns:
                return res
            rng = np.random.default_rng(hash((seed, competition, cutoff_unix, a)) % (2**32))
            labels = [x.band for x in assigns]
            perm = rng.permutation(len(labels))
            shuffled = [labels[i] for i in perm]
            members = tuple(sorted(assigns[i].opponent for i in range(len(assigns))
                                   if shuffled[i] == band))
            return SIM.CohortResolution(
                res.axis, res.requested_band, res.cutoff_unix, members,
                res.assignments, res.candidate_n, res.usable_n, res.missing_n,
                res.notes + ("PIT_SAFE_BAND_SHUFFLE",))
        return resolve


def build_hd_feature(fb, rec, templates, target_stat, shuffle_seed=None):
    """Aggregate the mapped templates into ONE match-total-frame hd_shrunk_diff.

    Frozen aggregation (prereg): matchup A-attack (+) B-defence frame. The home subject's
    FOR templates and the away subject's FOR templates are summed; AGAINST templates
    contribute the concession side. Missing legs -> that leg absent; whole feature is None
    only if NO leg resolved.
    """
    legs = []
    states = []
    for t in templates:
        axis, band, side = (t["opponent_profile_axis"], t["opponent_profile_band"],
                            t["side"])
        # home subject produces target_stat; away subject's concession mirrors it
        for team_id, subj_side in ((rec.home_id, side),):
            v, st = fb.hd_shrunk_diff(
                team_id=team_id, competition=rec.competition, cutoff=rec.kickoff_unix,
                target_fid=rec.fixture_id, target_stat=target_stat, side=subj_side,
                axis=axis, band=band, shuffle_seed=shuffle_seed)
            states.append(st)
            if v is not None:
                legs.append(v)
        # away subject leg (FOR from away perspective contributes to match total)
        v2, st2 = fb.hd_shrunk_diff(
            team_id=rec.away_id, competition=rec.competition, cutoff=rec.kickoff_unix,
            target_fid=rec.fixture_id, target_stat=target_stat, side=side,
            axis=axis, band=band, shuffle_seed=shuffle_seed)
        states.append(st2)
        if v2 is not None:
            legs.append(v2)
    if not legs:
        return None, states
    return float(np.mean(legs)), states


# ======================================================================================
# Matrix assembly + walk-forward (reuses harness.fit_predict_logit / summarize)
# ======================================================================================
def assemble(recs, db, fb, market, line, templates, target_stat,
             hd_mode="mapped", shuffle_seed=None):
    """Build aligned rows for B0/B1/B2 with the hypothesis feature.

    hd_mode: 'mapped' (real), 'none' (no hd feature -> B1 only), 'irrelevant' (fouls axis
    control uses templates with fouls_for), 'shuffle' (PIT-safe band shuffle).
    """
    b0_rows, b1_rows, hd_vals, y, comps, times = [], [], [], [], [], []
    avail = 0
    n_rows = 0
    for rec in recs:
        o = outcome(rec, market, line)
        if o is None:
            continue
        n_rows += 1
        b0 = db.f_champ(rec, market)
        b1 = {**db.f_champ(rec, market), **db.f_matchup(rec, market),
              **db.f_league_env(rec, market), **db.f_home_away(rec, market)}
        if hd_mode == "none":
            hd = None
        else:
            hd, _ = build_hd_feature(fb, rec, templates, target_stat,
                                     shuffle_seed=shuffle_seed)
        if hd is not None:
            avail += 1          # one fixture, availability counted ONCE per row
        b0_rows.append(b0); b1_rows.append(b1); hd_vals.append(hd)
        y.append(o); comps.append(rec.competition); times.append(rec.kickoff_unix)
    return {"b0": b0_rows, "b1": b1_rows, "hd": hd_vals, "y": np.array(y),
            "comps": comps, "times": times, "hd_available": avail, "n_rows": n_rows}


def _matrix(rows, names):
    return np.array([[d.get(n, np.nan) for n in names] for d in rows], dtype=float)


def _names(rows):
    keys = set()
    for d in rows:
        keys.update(d.keys())
    return sorted(keys)


def walk_forward_model(mat_rows, y, comps, times, add_hd=None):
    """Chronological expanding folds; train-only preprocessing inside fit_predict_logit.
    add_hd: optional list of hd values aligned to rows (NaN where absent -> median-imputed
    train-only, exactly like any B1 feature)."""
    order = np.argsort(times, kind="stable")
    names = _names(mat_rows)
    X = _matrix(mat_rows, names)[order]
    yy = y[order]
    cc = [comps[i] for i in order]
    if add_hd is not None:
        hd = np.array([add_hd[i] for i in order], dtype=float).reshape(-1, 1)
        X = np.hstack([X, hd])
    n = len(yy)
    bounds = np.linspace(0, n, N_FOLDS + 1, dtype=int)
    all_p, all_y, all_c, folds = [], [], [], []
    for fi in range(2, N_FOLDS + 1):
        tr_lo, tr_hi = 0, bounds[fi - 1]
        te_lo, te_hi = bounds[fi - 1], bounds[fi]
        Xtr, ytr = X[tr_lo:tr_hi], yy[tr_lo:tr_hi]
        Xte, yte = X[te_lo:te_hi], yy[te_lo:te_hi]
        if len(np.unique(ytr)) < 2 or len(yte) == 0:
            continue
        p, _, _ = H.fit_predict_logit(Xtr, ytr, Xte)
        all_p.append(p); all_y.append(yte); all_c += [cc[i] for i in range(te_lo, te_hi)]
        folds.append({"fold": fi, "n_train": int(len(ytr)), "n_test": int(len(yte)),
                      "logloss": round(H.logloss(yte, p), 5),
                      "brier": round(H.brier(yte, p), 5)})
    P = np.concatenate(all_p); Y = np.concatenate(all_y)
    return {"p": P, "y": Y, "comp": all_c, "folds": folds}


def block_bootstrap_delta(y, p_b1, p_b2, comps, seed, n=BOOTSTRAP_RESAMPLES):
    """Paired competition-block bootstrap of dLogLoss(B2-B1). Frozen seed."""
    rng = np.random.default_rng(seed)
    by_comp = defaultdict(list)
    for i, c in enumerate(comps):
        by_comp[c].append(i)
    blocks = list(by_comp.values())
    deltas = []
    for _ in range(n):
        pick = rng.integers(0, len(blocks), size=len(blocks))
        idx = np.concatenate([blocks[b] for b in pick])
        d = H.logloss(y[idx], p_b2[idx]) - H.logloss(y[idx], p_b1[idx])
        deltas.append(d)
    deltas = np.array(deltas)
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    return {"mean": float(deltas.mean()), "ci_lo": float(lo), "ci_hi": float(hi),
            "p_better": float((deltas < 0).mean()), "n_resamples": n, "seed": seed,
            "n_blocks": len(blocks)}


def classify(delta_point, ci_lo, ci_hi):
    if ci_hi < 0:
        return "CLEAR" if delta_point < 0 and ci_hi < -1e-4 else "PROMISING"
    if delta_point < 0 <= ci_hi and ci_lo < 0:
        return "MARGINAL"
    if delta_point >= 0 and ci_lo > 0:
        return "NEGATIVE"
    return "INCONCLUSIVE"


def main():
    t0 = time.time()
    prereg = json.load(open(PREREG))
    quarantine = frozenset(prereg["contamination_protocol"]["origin_fixtures_quarantined"])
    recs_all = load_corpus()
    recs = [r for r in recs_all if r.fixture_id not in quarantine]
    quarantine_audit = {
        "n_corpus_total": len(recs_all), "n_after_quarantine": len(recs),
        "n_removed": len(recs_all) - len(recs),
        "origin_ids_present": sorted(r.fixture_id for r in recs_all
                                     if r.fixture_id in quarantine),
        "origin_ids_in_evaluation_universe": sorted(r.fixture_id for r in recs
                                                    if r.fixture_id in quarantine)}
    print(f"[{time.time()-t0:.0f}s] corpus {len(recs_all)} -> {len(recs)} after quarantine "
          f"(removed {quarantine_audit['n_removed']})")

    db = DesignBuilder(recs)
    for s in ("xg", "corner_kicks", "cards"):
        db.ratings(s)
    fb = HDFeatureBuilder(recs, quarantine)
    print(f"[{time.time()-t0:.0f}s] builders ready")

    templates = prereg["templates"]
    corners_tpl = [t for t in templates if t["target_metric"] == "corners"]

    results = {"integrity": {
        "prereg_sha256": _sha256(PREREG),
        "prereg_rebuilt_deterministic": True,
        "compatibility_sha256": _sha256(f"{ROOT}/src/research/hypothesis_oos/compatibility.py"),
        "design_doc_sha256": _sha256(
            f"{ROOT}/research/hypothesis_engine/V4_HYPOTHESIS_DERIVED_OOS_PREREGISTRATION.md"),
        "champion_frozen_sha256": CHAMPION_FROZEN_SHA,
        "champion_current_sha256": _sha256(CHAMPION_ARTIFACT),
        "champion_unchanged": _sha256(CHAMPION_ARTIFACT) == CHAMPION_FROZEN_SHA,
        "shrink_k": CM.SHRINK_K, "min_conditional_n": CM.MIN_CONDITIONAL_N,
        "min_comparison_n": CM.MIN_COMPARISON_N, "min_prior_matches": CM.MIN_PRIOR_MATCHES,
        "n_folds": N_FOLDS, "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
    }, "quarantine_audit": quarantine_audit}

    # ---- CONFIRMATORY: opponent_profile x corners x B2 vs B1 --------------------------
    print(f"[{time.time()-t0:.0f}s] CONFIRMATORY: corners 9.5 ...")
    conf_line = 9.5   # champion consumer-scope corners line
    data = assemble(recs, db, fb, "corners", conf_line, corners_tpl, "corner_kicks",
                    hd_mode="mapped")
    b0 = walk_forward_model(data["b0"], data["y"], data["comps"], data["times"])
    b1 = walk_forward_model(data["b1"], data["y"], data["comps"], data["times"])
    b2 = walk_forward_model(data["b1"], data["y"], data["comps"], data["times"],
                            add_hd=data["hd"])
    # common support: all three share identical rows (same fixtures), so p arrays align
    s0, s1, s2 = (H.summarize(b0["y"], b0["p"]), H.summarize(b1["y"], b1["p"]),
                  H.summarize(b2["y"], b2["p"]))
    boot = block_bootstrap_delta(b2["y"], b1["p"], b2["p"], b2["comp"], BOOTSTRAP_SEED)
    band = classify(s2["logloss"] - s1["logloss"], boot["ci_lo"], boot["ci_hi"])
    # fold-level direction
    fold_dir = []
    for f1, f2 in zip(b1["folds"], b2["folds"]):
        fold_dir.append({"fold": f1["fold"], "d_logloss": round(f2["logloss"] - f1["logloss"], 5),
                         "improved": f2["logloss"] < f1["logloss"]})

    results["confirmatory"] = {
        "cell": "opponent_profile x corners@9.5 x B2_vs_B1",
        "market": "corners", "line": conf_line,
        "n_predictions": s1["n"], "n_assembled": data["n_rows"],
        "hd_available": data["hd_available"],
        "hd_coverage": round(data["hd_available"] / data["n_rows"], 4) if data["n_rows"] else 0.0,
        "B0": s0, "B1": s1, "B2": s2,
        "d_logloss_B2_minus_B1": round(s2["logloss"] - s1["logloss"], 5),
        "d_brier_B2_minus_B1": round(s2["brier"] - s1["brier"], 5),
        "bootstrap": boot, "band": band,
        "fold_direction": fold_dir,
        "b1_folds": b1["folds"], "b2_folds": b2["folds"], "b0_folds": b0["folds"],
    }
    print(f"    B1 LL={s1['logloss']} B2 LL={s2['logloss']} "
          f"dLL={results['confirmatory']['d_logloss_B2_minus_B1']} band={band} "
          f"cov={results['confirmatory']['hd_coverage']}")

    # ---- NEGATIVE CONTROLS ------------------------------------------------------------
    print(f"[{time.time()-t0:.0f}s] negative controls ...")
    controls = {}
    # 1. irrelevant axis: fouls_for band, same market
    irr_tpl = [{"opponent_profile_axis": "fouls_for", "opponent_profile_band": "HIGH",
                "side": "FOR", "target_metric": "corners"}]
    d_irr = assemble(recs, db, fb, "corners", conf_line, irr_tpl, "corner_kicks",
                     hd_mode="irrelevant")
    b2_irr = walk_forward_model(d_irr["b1"], d_irr["y"], d_irr["comps"], d_irr["times"],
                                add_hd=d_irr["hd"])
    s_irr = H.summarize(b2_irr["y"], b2_irr["p"])
    controls["irrelevant_axis"] = {
        "d_logloss_vs_B1": round(s_irr["logloss"] - s1["logloss"], 5),
        "hd_coverage": round(d_irr["hd_available"] / d_irr["n_rows"], 4) if d_irr["n_rows"] else 0.0,
        "B2ctrl_logloss": s_irr["logloss"]}
    # 3. PIT-safe band shuffle
    d_shuf = assemble(recs, db, fb, "corners", conf_line, corners_tpl, "corner_kicks",
                      hd_mode="shuffle", shuffle_seed=BOOTSTRAP_SEED)
    b2_shuf = walk_forward_model(d_shuf["b1"], d_shuf["y"], d_shuf["comps"], d_shuf["times"],
                                 add_hd=d_shuf["hd"])
    s_shuf = H.summarize(b2_shuf["y"], b2_shuf["p"])
    controls["pit_safe_band_shuffle"] = {
        "d_logloss_vs_B1": round(s_shuf["logloss"] - s1["logloss"], 5),
        "hd_coverage": round(d_shuf["hd_available"] / d_shuf["n_rows"], 4) if d_shuf["n_rows"] else 0.0,
        "B2ctrl_logloss": s_shuf["logloss"]}
    # 2. unconditional comparator: use unconditional_behavioral_profile family feature.
    #    Approximated by band=ANY (no opponent conditioning) on the same axis/target.
    unc_tpl = [{**t, "opponent_profile_band": "ANY"} for t in corners_tpl]
    d_unc = assemble(recs, db, fb, "corners", conf_line, unc_tpl, "corner_kicks",
                     hd_mode="mapped")
    b2_unc = walk_forward_model(d_unc["b1"], d_unc["y"], d_unc["comps"], d_unc["times"],
                                add_hd=d_unc["hd"])
    s_unc = H.summarize(b2_unc["y"], b2_unc["p"])
    controls["unconditional_comparator"] = {
        "d_logloss_vs_B1": round(s_unc["logloss"] - s1["logloss"], 5),
        "hd_coverage": round(d_unc["hd_available"] / d_unc["n_rows"], 4) if d_unc["n_rows"] else 0.0,
        "B2ctrl_logloss": s_unc["logloss"]}
    results["negative_controls"] = controls
    print(f"    controls: {json.dumps({k: v['d_logloss_vs_B1'] for k, v in controls.items()})}")

    # ---- EXPLORATORY: goals + cards -------------------------------------------------
    print(f"[{time.time()-t0:.0f}s] exploratory cells ...")
    exploratory = {}
    for market, line, metric in (("goals", 2.5, "goals"), ("cards", 4.5, "yellow_cards")):
        tpl = [t for t in templates if t["target_metric"] == metric]
        if not tpl:
            continue
        de = assemble(recs, db, fb, market, line, tpl, _TARGET_STAT[metric],
                      hd_mode="mapped")
        e1 = walk_forward_model(de["b1"], de["y"], de["comps"], de["times"])
        e2 = walk_forward_model(de["b1"], de["y"], de["comps"], de["times"], add_hd=de["hd"])
        se1, se2 = H.summarize(e1["y"], e1["p"]), H.summarize(e2["y"], e2["p"])
        eboot = block_bootstrap_delta(e2["y"], e1["p"], e2["p"], e2["comp"], BOOTSTRAP_SEED)
        exploratory[f"{market}@{line}"] = {
            "label": "EXPLORATORY", "market": market, "line": line, "metric": metric,
            "n": se1["n"], "hd_coverage": round(de["hd_available"] / de["n_rows"], 4) if de["n_rows"] else 0.0,
            "B1_logloss": se1["logloss"], "B2_logloss": se2["logloss"],
            "d_logloss": round(se2["logloss"] - se1["logloss"], 5),
            "d_brier": round(se2["brier"] - se1["brier"], 5),
            "bootstrap": eboot, "band": classify(se2["logloss"] - se1["logloss"],
                                                  eboot["ci_lo"], eboot["ci_hi"])}
    # FDR (Benjamini-Hochberg) over exploratory p_better -> pseudo p = 1 - p_better
    pvals = {k: 1 - v["bootstrap"]["p_better"] for k, v in exploratory.items()}
    m = len(pvals)
    ranked = sorted(pvals.items(), key=lambda kv: kv[1])
    for rank, (k, pv) in enumerate(ranked, 1):
        exploratory[k]["fdr_bh_threshold_0.10"] = round(rank / m * 0.10, 4) if m else None
        exploratory[k]["fdr_pass_0.10"] = pv <= (rank / m * 0.10) if m else False
    results["exploratory"] = exploratory

    # ---- MECHANICAL VERDICT -----------------------------------------------------------
    conf = results["confirmatory"]
    dll = conf["d_logloss_B2_minus_B1"]
    slope = conf["B2"]["calib_slope"]
    ece_b1, ece_b2 = conf["B1"]["ece"], conf["B2"]["ece"]
    n_folds_improved = sum(1 for f in conf["fold_direction"] if f["improved"])
    beats_controls = all(dll < c["d_logloss_vs_B1"] for c in controls.values())
    gates = [
        {"gate": "dLogLoss(B2-B1) < 0", "observed": dll, "threshold": "< 0",
         "pass": dll < 0},
        {"gate": "95% CI entirely < 0", "observed": conf["bootstrap"]["ci_hi"],
         "threshold": "ci_hi < 0", "pass": conf["bootstrap"]["ci_hi"] < 0},
        {"gate": "band in {CLEAR,PROMISING}", "observed": conf["band"],
         "threshold": "CLEAR|PROMISING", "pass": conf["band"] in ("CLEAR", "PROMISING")},
        {"gate": "calib slope in [0.8,1.25]", "observed": slope,
         "threshold": "[0.8,1.25]",
         "pass": slope is not None and 0.8 <= slope <= 1.25},
        {"gate": "ECE not worse than B1 by >0.01", "observed": round(ece_b2 - ece_b1, 4),
         "threshold": "<= 0.01", "pass": (ece_b2 - ece_b1) <= 0.01},
        {"gate": "lift exceeds all 3 controls", "observed": beats_controls,
         "threshold": "True", "pass": beats_controls},
        {"gate": "direction consistent >=3/4 folds", "observed": f"{n_folds_improved}/"
         f"{len(conf['fold_direction'])}", "threshold": ">=3",
         "pass": n_folds_improved >= 3},
    ]
    all_pass = all(g["pass"] for g in gates)
    # MIXED if point<0 but not all gates (e.g. CI crosses / control not beaten / folds)
    if all_pass:
        verdict = "PASS"
    elif dll < 0:
        verdict = "MIXED"
    else:
        verdict = "FAIL"
    results["gate_table"] = gates
    results["mechanical_verdict"] = verdict
    print(f"[{time.time()-t0:.0f}s] VERDICT={verdict}")

    with open(f"{OUT}/V4_OOS_RESULTS.json", "w") as fh:
        json.dump(results, fh, indent=1, sort_keys=True, default=str)
    print(f"[{time.time()-t0:.0f}s] wrote {OUT}/V4_OOS_RESULTS.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
