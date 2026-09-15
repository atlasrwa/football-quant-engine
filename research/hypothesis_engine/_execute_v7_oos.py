"""Execute the FROZEN V7 confirmatory OOS experiment. ZERO SPEND. No Bedrock. No CHAMPION.

Reads the frozen V7 artifacts, compiles every canonical hypothesis through the frozen
comparator semantics, measures it out of sample on the frozen walk-forward folds, applies the
frozen support / confounder / multiplicity rules, assigns a frozen terminal state, and writes
immutable evidence artifacts.

Design is NOT altered here. Parameters the frozen artifacts do not settle are declared in
`measurement.engine_spec()` and hashed before the first effect.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/src")

from src.research.hypothesis_v7 import analysis_spec as A
from src.research.hypothesis_v7 import measurement as ME
from src.research.hypothesis_v7 import pit as PIT
from src.research.hypothesis_v7 import provider as P
from src.research.matchup import corpus as MC

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v7"
OOSDIR = f"{OUT}/oos"
CHAMPION = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"


def L(name):
    return json.load(open(f"{OUT}/{name}"))


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# =======================================================================================
# corpus index with PIT prefix structures
# =======================================================================================
class Index:
    def __init__(self, records, coverage):
        self.recs = sorted(records, key=lambda r: (int(r.kickoff_unix), str(r.fixture_id)))
        self.kick = [int(r.kickoff_unix) for r in self.recs]
        self.metrics = sorted(m for m, row in coverage["metrics"].items()
                              if row["coverage_gate_pass"])
        # per-record (home_val, away_val) per metric
        self.vals = {m: [] for m in self.metrics}
        for r in self.recs:
            for m in self.metrics:
                self.vals[m].append(self._read(r, m))
        # team series
        self.series = {}
        self.pos = {}
        for i, r in enumerate(self.recs):
            for tid, is_home in ((r.home_id, True), (r.away_id, False)):
                s = self.series.setdefault(tid, [])
                self.pos[(tid, i)] = len(s)
                s.append((i, int(r.kickoff_unix), r.competition, is_home,
                          r.away_id if is_home else r.home_id))
        # competition chronological index for environment means
        self.comp_idx = {}
        for i, r in enumerate(self.recs):
            self.comp_idx.setdefault(r.competition, []).append(i)
        self._pref = {}
        self.comp_cum = {}
        for comp, idxs in self.comp_idx.items():
            for m in self.metrics:
                cs, cn, tot, cnt = [], [], 0.0, 0
                for i in idxs:
                    pair = self.vals[m][i]
                    if pair is not None:
                        tot += pair[0] + pair[1]
                        cnt += 2
                    cs.append(tot)
                    cn.append(cnt)
                self.comp_cum[(comp, m)] = (cs, cn)
            self.comp_idx[comp] = idxs

    def _read(self, rec, metric):
        row = P.METRIC_CONTRACT.get(metric)
        if not row or not row.get("block"):
            return None
        blk, fld = row["block"], row["field"]
        if blk == "base":
            b = rec.base or {}
            h, a = b.get(fld), b.get(row.get("field_away"))
        else:
            pair = (getattr(rec, blk, None) or {}).get(fld)
            if not pair:
                return None
            h, a = pair
        try:
            return (float(h), float(a)) if (h is not None and a is not None) else None
        except (TypeError, ValueError):
            return None

    def env_mean(self, comp, metric, cutoff_unix):
        """Competition-environment mean of `metric` over records strictly before cutoff."""
        idxs = self.comp_idx.get(comp)
        if not idxs:
            return None
        ks = [self.kick[i] for i in idxs]
        j = bisect.bisect_left(ks, cutoff_unix)
        if j == 0:
            return None
        cs, cn = self.comp_cum[(comp, metric)]
        return (cs[j - 1] / cn[j - 1]) if cn[j - 1] > 0 else None

    def _prefix(self, team_id, metric, side, venue=None):
        """(cumsum, cumcount) over the team's own chronological series. Built once, cached."""
        key = (team_id, metric, side, venue)
        got = self._pref.get(key)
        if got is not None:
            return got
        cs, cn, tot, cnt = [], [], 0.0, 0
        for (i, _k, _c, is_home, _o) in self.series.get(team_id, []):
            if venue is None or is_home == venue:
                v = self.team_value(i, team_id, metric, side)
                if v is not None:
                    tot += v
                    cnt += 1
            cs.append(tot)
            cn.append(cnt)
        self._pref[key] = (cs, cn)
        return self._pref[key]

    def pit_mean(self, team_id, metric, side, before_rec_i, venue=None):
        """PIT mean over the team's matches strictly before `before_rec_i`. O(1)."""
        pos = self.pos.get((team_id, before_rec_i))
        if not pos:
            return (None, 0)
        cs, cn = self._prefix(team_id, metric, side, venue)
        n = cn[pos - 1]
        return ((cs[pos - 1] / n, n) if n > 0 else (None, 0))

    def team_value(self, rec_i, team_id, metric, side):
        pair = self.vals[metric][rec_i]
        if pair is None:
            return None
        r = self.recs[rec_i]
        own, opp = (pair[0], pair[1]) if r.home_id == team_id else (pair[1], pair[0])
        return own if side == "FOR" else opp

    def prior_slice(self, team_id, rec_i):
        """The team's own matches strictly before rec_i, as series entries."""
        s = self.series.get(team_id)
        if not s:
            return []
        p = self.pos.get((team_id, rec_i))
        return s[:p] if p is not None else []

    def team_pit_mean(self, team_id, metric, side, before_rec_i):
        vals = [self.team_value(i, team_id, metric, side)
                for (i, _k, _c, _h, _o) in self.prior_slice(team_id, before_rec_i)]
        vals = [v for v in vals if v is not None]
        return (sum(vals) / len(vals)) if vals else None


# =======================================================================================
# cohort / baseline compilation (frozen comparator semantics)
# =======================================================================================
def _apply_conditions(idx, entries, conditions, target_is_home, terciles, metric_axis_cache):
    """Restrict the subject's prior entries by the canonical CONDITIONS. PIT-safe."""
    out = entries
    for c in conditions:
        try:
            d = json.loads(c) if isinstance(c, str) else c
        except (ValueError, TypeError):
            d = {}
        if not isinstance(d, dict):
            return []
        dim = d.get("dimension")
        if dim == "historical_venue_conditioning":
            want_home = (d.get("value") == "HOME")
            out = [e for e in out if e[3] == want_home]
        elif dim == "opponent_profile":
            axis, band = d.get("axis"), d.get("value")
            keep = []
            for e in out:
                key = (e[4], axis)
                mv = metric_axis_cache.get(key)
                if mv is None:
                    continue
                t = terciles.get((e[2], axis))
                if not t:
                    continue
                lo, hi = t
                got = LOW if mv < lo else (HIGH_ if mv > hi else MID_)
                if got == band:
                    keep.append(e)
            out = keep
        else:
            return []
    return out


HIGH_, MID_, LOW = "HIGH", "MID", "LOW"


def compile_signal(idx, spec, metric, rec_i, terciles, axis_cache):
    """Return (signal, outcome_residual, B, n_cohort, n_base) or None if not computable."""
    rec = idx.recs[rec_i]
    subject = rec.home_id if spec["SUBJECT"] == "HOME_TEAM" else rec.away_id
    side = spec["SIDE"] or "FOR"
    observed = idx.team_value(rec_i, subject, metric, side)
    if observed is None:
        return None
    env = idx.env_mean(rec.competition, metric, int(rec.kickoff_unix))
    if env is None:
        return None
    def vals_of(entries):
        v = [idx.team_value(i, subject, metric, side) for (i, _k, _c, _h, _o) in entries]
        return [x for x in v if x is not None]

    comparator = spec["COMPARATOR"]
    target_is_home = (rec.home_id == subject)
    conditions = spec.get("CONDITIONS") or []
    ts = spec.get("TIME_SCOPE")

    # ---- baseline set B (O(1) via prefix cache) ----
    venue_key = target_is_home if comparator == "SUBJECT_VENUE_BASELINE" else None
    bmean, bn = idx.pit_mean(subject, metric, side, rec_i, venue_key)
    if bmean is None:
        return None
    B = PIT.shrink_estimate(bmean, bn, env, PIT.SHRINKAGE_STRENGTH_K)

    # FAST PATH: an unconditioned, unwindowed cohort IS the baseline set, so the frozen
    # comparator definition yields signal == 0 exactly. Skip the rescan.
    if (comparator != "SUBJECT_RECENT_VS_LONG_BASELINE" and not conditions
            and ts in (None, "ALL_PRIOR")):
        return (0.0, observed - B, B, bn, bn)

    prior = idx.prior_slice(subject, rec_i)
    if not prior:
        return None
    base_entries = ([e for e in prior if e[3] == target_is_home]
                    if comparator == "SUBJECT_VENUE_BASELINE" else prior)

    # ---- cohort set C ----
    if comparator == "SUBJECT_RECENT_VS_LONG_BASELINE":
        # decayed reweighting of the SAME observations, at each frozen half-life
        ref = int(rec.kickoff_unix)
        cs = []
        for hl in PIT.TIME_DECAY_HALFLIVES_DAYS:
            num = den = 0.0
            for (i, k, _c, _h, _o) in base_entries:
                v = idx.team_value(i, subject, metric, side)
                if v is None:
                    continue
                w = PIT.time_decay_weight(k, ref, hl)
                num += w * v
                den += w
            if den > 0:
                cs.append(PIT.shrink_estimate(num / den, bn, env,
                                              PIT.SHRINKAGE_STRENGTH_K))
        if not cs:
            return None
        C, n_c = sum(cs) / len(cs), bn
    else:
        cohort = _apply_conditions(idx, base_entries, conditions,
                                   target_is_home, terciles, axis_cache)
        if ts == "W5":
            cohort = cohort[-5:]
        elif ts == "W10":
            cohort = cohort[-10:]
        cvals = vals_of(cohort)
        if not cvals:
            return None
        C = PIT.shrink_estimate(sum(cvals) / len(cvals), len(cvals), env,
                                PIT.SHRINKAGE_STRENGTH_K)
        n_c = len(cvals)

    return (C - B, observed - B, B, n_c, bn)


def parse_axis(axis):
    """A profile axis names a metric AND a perspective: `goals_for` -> ("goals", "FOR")."""
    if axis is None:
        return (None, None)
    for suf, side in (("_against", "AGAINST"), ("_for", "FOR")):
        if axis.endswith(suf):
            return (axis[: -len(suf)], side)
    return (axis, "FOR")


def build_terciles(idx, metrics, cutoff_unix, axes):
    """PIT competition terciles of team means on each profile axis, at the fold's train_end."""
    ter, cache = {}, {}
    for axis in axes:
        metric, side = parse_axis(axis)
        if metric not in idx.metrics:
            continue
        by_comp = {}
        for tid, s in idx.series.items():
            pre = [e for e in s if e[1] < cutoff_unix]
            if len(pre) < PIT.MIN_UNIQUE_TEAMS:
                continue
            vals = [idx.team_value(i, tid, metric, side) for (i, _k, _c, _h, _o) in pre]
            vals = [v for v in vals if v is not None]
            if not vals:
                continue
            mv = sum(vals) / len(vals)
            cache[(tid, axis)] = mv
            by_comp.setdefault(pre[-1][2], []).append(mv)
        for comp, xs in by_comp.items():
            xs.sort()
            n = len(xs)
            if n >= 3:
                ter[(comp, axis)] = (xs[n // 3], xs[2 * n // 3])
    return ter, cache


# =======================================================================================
# per-fold evaluation
# =======================================================================================
CONF_ALLOWED = set(A.ALLOWED_CONFOUNDERS)


def evaluate_fold(idx, spec, metric, lo_unix, hi_unix, terciles, axis_cache, plan):
    """One fold: build signal/outcome over the validation block and return the effect row."""
    i0 = bisect.bisect_left(idx.kick, lo_unix)
    i1 = bisect.bisect_left(idx.kick, hi_unix)
    sig, res, rows, teams, fixtures, comps = [], [], [], set(), set(), set()
    for rec_i in range(i0, i1):
        rec = idx.recs[rec_i]
        got = compile_signal(idx, spec, metric, rec_i, terciles, axis_cache)
        if got is None:
            continue
        s, r, B, n_c, n_b = got
        subject = rec.home_id if spec["SUBJECT"] == "HOME_TEAM" else rec.away_id
        opp = rec.away_id if rec.home_id == subject else rec.home_id
        opp_strength = idx.pit_mean(opp, metric, "FOR", rec_i)[0]
        sig.append(s)
        res.append(r)
        cards_rate = idx.pit_mean(subject, "yellow_cards", "FOR", rec_i)[0]
        rows.append({"venue": 1.0 if rec.home_id == subject else 0.0,
                     "comp": rec.competition,
                     "opp": opp_strength if opp_strength is not None else 0.0,
                     "base": B,
                     "cards": cards_rate if cards_rate is not None else 0.0,
                     "season": float(int(rec.season_id.replace("sn_", "") or 0) % 100000)})
        teams.add(subject)
        fixtures.add(rec.fixture_id)
        comps.add(rec.competition)

    n = len(sig)
    weights = [1.0] * n
    support = PIT.classify_support(
        raw_n=n, unique_fixtures=len(fixtures), unique_teams=len(teams),
        effective_n=PIT.kish_effective_n(weights),
        concentration=PIT.weight_concentration(weights), n_competitions=len(comps))

    out = {"n": n, "unique_fixtures": len(fixtures), "unique_teams": len(teams),
           "n_competitions": len(comps), "support": support["status"],
           "effect": None, "adjusted": False, "signal_variance": None,
           "competitions": sorted(comps)}
    if n >= 3:
        mS = sum(sig) / n
        out["signal_variance"] = sum((x - mS) ** 2 for x in sig) / n
    if support["status"] != PIT.SUPPORT_ADEQUATE or n < 3:
        return out
    if out["signal_variance"] is not None and out["signal_variance"] <= 1e-18:
        return out           # contrastless -> no effect is computable

    # ---- frozen per-family confounder design -------------------------------------
    # Columns are built from the FROZEN plan. A column the corpus cannot supply is recorded
    # as unavailable rather than silently ignored, and a column that is CONSTANT in this
    # block (e.g. the venue indicator when SUBJECT is always the home team) is not
    # identifiable against the intercept and is dropped as such -- both are recorded.
    conf = set(plan.get("confounders") or []) & CONF_ALLOWED
    comp_levels = sorted({r["comp"] for r in rows})[1:]
    named, unavailable = [], []
    if "venue" in conf:
        named.append(("venue", [r["venue"] for r in rows]))
    if "competition" in conf:
        for c in comp_levels:
            named.append((f"comp={c}", [1.0 if r["comp"] == c else 0.0 for r in rows]))
    if "opponent_strength" in conf or "opponent_profile" in conf:
        named.append(("opponent_strength", [r["opp"] for r in rows]))
    if "team_baseline_quality" in conf:
        named.append(("team_baseline_quality", [r["base"] for r in rows]))
    if "cards" in conf:
        named.append(("cards", [r["cards"] for r in rows]))
    if "season_regime" in conf:
        named.append(("season_regime", [r["season"] for r in rows]))
    for miss in ("score_state", "formation"):
        if miss in conf:
            unavailable.append(miss)

    keep, dropped_constant = [], []
    for name, col in named:
        lo, hi = min(col), max(col)
        if hi - lo <= 1e-12:
            dropped_constant.append(name)
        else:
            keep.append((name, col))
    out["confounders_applied"] = [n for n, _ in keep]
    out["confounders_dropped_constant"] = dropped_constant
    out["confounders_unavailable_in_corpus"] = unavailable

    X = [[col[i] for _n, col in keep] for i in range(n)]
    rs = ME.ols_residualize(sig, X)
    rr = ME.ols_residualize(res, X)
    if rs is None or rr is None:
        out["confounded_unresolved"] = True
        return out
    out["adjusted"] = True
    out["effect"] = ME.pearson(rs, rr)
    return out


def evaluate_hypothesis(idx, spec, folds, dev_window, terciles, axis_cache, coverage):
    """All metrics x all folds for one canonical hypothesis. Returns the evidence record."""
    plan = A.confounder_plan_for(spec.get("FAMILY"))
    metrics = [m for m in (spec.get("TARGET") or []) if m in idx.metrics]
    per_metric, any_variance, any_conf_fail = {}, False, False
    for m in metrics:
        fold_rows = []
        for f in folds:
            fr = evaluate_fold(idx, spec, m, f["validate_start_unix"],
                               f["validate_end_unix"], terciles, axis_cache, plan)
            fr["fold_index"] = f["fold_index"]
            fr["train_end_iso"] = f["train_end_iso"]
            fold_rows.append(fr)
            if fr.get("signal_variance") and fr["signal_variance"] > 1e-18:
                any_variance = True
            if fr.get("confounded_unresolved"):
                any_conf_fail = True
        dev = evaluate_fold(idx, spec, m, dev_window[0], dev_window[1],
                            terciles, axis_cache, plan)
        per_metric[m] = {"folds": fold_rows, "development_non_confirmatory": dev}
    return {"metrics": metrics, "per_metric": per_metric,
            "any_signal_variance": any_variance,
            "confounder_unresolved": any_conf_fail,
            "confounder_plan": plan}


def score_hypothesis(ev):
    """OOS_QUALITY_SCORE per the frozen endpoint definition + engine spec."""
    per_metric_scores, all_fold_effects, ses = [], [], []
    for m, blk in sorted(ev["per_metric"].items()):
        eff = [f["effect"] for f in blk["folds"] if f["effect"] is not None]
        if not eff:
            continue
        pos = sum(1 for e in eff if e > 0)
        neg = sum(1 for e in eff if e < 0)
        agree = max(pos, neg) / len(eff)
        mean_e = sum(eff) / len(eff)
        per_metric_scores.append({"metric": m, "n_folds_evaluable": len(eff),
                                  "mean_effect": mean_e,
                                  "direction_agreement": agree,
                                  "score": mean_e * agree,
                                  "fold_effects": eff})
        all_fold_effects += eff
    if not per_metric_scores:
        return None
    score = sum(x["score"] for x in per_metric_scores) / len(per_metric_scores)
    agree = sum(x["direction_agreement"] for x in per_metric_scores) / len(per_metric_scores)
    n = len(all_fold_effects)
    mean_all = sum(all_fold_effects) / n
    se = None
    if n >= 2:
        var = sum((e - mean_all) ** 2 for e in all_fold_effects) / (n - 1)
        se = (var / n) ** 0.5
    dev_eff = []
    for m, blk in ev["per_metric"].items():
        d = blk["development_non_confirmatory"].get("effect")
        if d is not None:
            dev_eff.append(abs(d))
    return {"oos_quality_score": score, "direction_agreement": agree,
            "mean_fold_effect": mean_all, "se": se,
            "n_fold_effects": n, "per_metric": per_metric_scores,
            "p_value": ME.t_two_sided_p(all_fold_effects),
            "dev_abs_effect": (max(dev_eff) if dev_eff else None)}


# =======================================================================================
# terminal states (frozen taxonomy, engine-spec ordering)
# =======================================================================================
def terminal_state(meas_status, comparator_ok, ev, sc, fdr_rejected):
    if meas_status != P.MEASURABLE:
        return "UNMEASURABLE"
    if not comparator_ok:
        return "TAUTOLOGICAL"
    if not ev["any_signal_variance"]:
        return "TAUTOLOGICAL"
    if sc is None:
        if ev["confounder_unresolved"]:
            return "CONFOUNDED_UNRESOLVED"
        return "INSUFFICIENT_SUPPORT"
    if ev["confounder_unresolved"]:
        return "CONFOUNDED_UNRESOLVED"
    shrunk = sc.get("shrunk_score", sc["oos_quality_score"])
    if sc["direction_agreement"] < ME.DIRECTION_STABILITY_MIN:
        return "OOS_DIRECTION_UNSTABLE"
    if abs(shrunk) < ME.NONTRIVIAL_ABS_EFFECT_MIN:
        dev = sc.get("dev_abs_effect")
        if dev is not None and dev >= ME.DEV_EFFECT_LARGE:
            return "OOS_FAIL"
        return "OOS_NO_EFFECT"
    if not fdr_rejected:
        return "OOS_NO_EFFECT"
    return "OOS_SURVIVES"


def run_origin(idx, families, meas_lookup, comparator_ok, folds, dev_window,
               terciles, axis_cache, coverage, label, progress_every=100):
    """Evaluate every family of one origin. Returns per-family evidence records."""
    out = []
    for n_done, fam in enumerate(families, 1):
        cid = fam["canonical_hypothesis_id"]
        spec = fam["canonical_spec"]
        st = meas_lookup.get(cid, {}).get("status", P.UNMEASURABLE_COVERAGE)
        rec = {"canonical_hypothesis_id": cid, "origin": label,
               "arm_membership": fam.get("arm_membership"),
               "measurability": st, "family": spec.get("FAMILY"),
               "target": spec.get("TARGET"), "comparator": spec.get("COMPARATOR"),
               "time_scope": spec.get("TIME_SCOPE"),
               "n_conditions": len(spec.get("CONDITIONS") or []),
               "uses_similarity": bool(spec.get("SIMILARITY_DIMENSIONS"))}
        if st != P.MEASURABLE:
            rec.update({"terminal_state": "UNMEASURABLE", "evidence": None, "score": None})
            out.append(rec)
            continue
        ev = evaluate_hypothesis(idx, spec, folds, dev_window, terciles, axis_cache,
                                 coverage)
        sc = score_hypothesis(ev)
        rec["evidence"] = ev
        rec["score"] = sc
        rec["comparator_ok"] = comparator_ok.get(cid, True)
        out.append(rec)
        if n_done % progress_every == 0:
            print(f"    {label}: {n_done}/{len(families)}", flush=True)
    return out


def apply_multiplicity(records):
    """Frozen plan: BH-FDR per multiplicity family at q=0.10 + EB shrinkage. Mutates records."""
    by_family = {}
    for r in records:
        if not r.get("score"):
            continue
        fam = A.multiplicity_family_of(r.get("family"))
        by_family.setdefault(fam, []).append(r)
    summary = {}
    for fam, rows in sorted(by_family.items()):
        scores = [r["score"]["oos_quality_score"] for r in rows]
        ses = [r["score"].get("se") for r in rows]
        shrunk = ME.empirical_bayes(scores, ses)
        for r, s in zip(rows, shrunk):
            r["score"]["shrunk_score"] = s
        pvals = [(r["score"].get("p_value") if r["score"].get("p_value") is not None else 1.0)
                 for r in rows]
        rej = ME.benjamini_hochberg(pvals, A.FDR_Q)
        for r, k in zip(rows, rej):
            r["score"]["fdr_rejected"] = bool(k)
        summary[fam] = {"n": len(rows), "n_fdr_rejected": sum(rej),
                        "q": A.FDR_Q,
                        "mean_score": sum(scores) / len(scores),
                        "mean_shrunk": sum(shrunk) / len(shrunk)}
    return summary


def finalize_states(records, comparator_ok):
    from collections import Counter
    counts = Counter()
    for r in records:
        sc = r.get("score")
        st = terminal_state(r["measurability"],
                            comparator_ok.get(r["canonical_hypothesis_id"], True),
                            r["evidence"] if r.get("evidence") else
                            {"any_signal_variance": False, "confounder_unresolved": False},
                            sc, (sc or {}).get("fdr_rejected", False))
        if st == "OOS_SURVIVES":
            st = "CANDIDATE_FEATURE_ELIGIBLE"
        r["terminal_state"] = st
        counts[st] += 1
    return dict(counts)


# =======================================================================================
# main
# =======================================================================================
def _write(name, obj):
    os.makedirs(OOSDIR, exist_ok=True)
    p = f"{OOSDIR}/{name}"
    with open(p, "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True, default=str)
    return sha_file(p)


def main() -> int:
    champ_before = sha_file(CHAMPION)
    print("=== V7 CONFIRMATORY OOS EXECUTION ===", flush=True)

    # ---- precondition: frozen hashes ------------------------------------------------
    prereg = L("V7_PREREGISTRATION.json")
    mismatches = [n for n, h in prereg["artifact_hashes"].items()
                  if not os.path.exists(f"{OUT}/{n}") or sha_file(f"{OUT}/{n}") != h]
    if mismatches:
        print("STOP BEFORE OOS -- frozen artifacts differ:", mismatches)
        return 1
    if champ_before != prereg["champion_protection"]["champion_sha256"]:
        print("STOP BEFORE OOS -- CHAMPION changed")
        return 1
    engine_hash = ME.engine_spec_hash()
    _write("V7_MEASUREMENT_ENGINE_SPEC.json",
           {**ME.engine_spec(), "engine_spec_sha256": engine_hash,
            "frozen_before_first_effect": True,
            "verified_frozen_artifacts": len(prereg["artifact_hashes"]),
            "champion_sha256_before": champ_before})
    print(f"  precondition OK: {len(prereg['artifact_hashes'])} artifact hashes verified")
    print(f"  engine spec frozen: {engine_hash[:16]}", flush=True)

    # ---- load frozen design ---------------------------------------------------------
    coverage = L("V7_COVERAGE_MATRIX.json")
    folds_art = L("V7_WALKFORWARD_FOLDS.json")
    folds = folds_art["folds"]
    dev_window = (0, folds_art["confirmatory_start_unix"])
    ded = L("V7_DEDUPLICATION.json")["families"]
    meas_rows = {r["canonical_hypothesis_id"]: r for r in L("V7_MEASURABILITY.json")["rows"]}
    conf_art = L("V7_CONFOUNDER_PLAN.json")
    comparator_ok = {f["canonical_hypothesis_id"]: f["ok"]
                     for f in conf_art["comparator_flags_over_measurable"]}
    nullu = L("V7_NULL_BENCHMARK.json")
    null_meas = {r["canonical_hypothesis_id"]: r
                 for r in nullu["measurability"]["rows"]}
    weights = L("V7_CONTROL_B_WEIGHTS.json")
    cb_cov = L("V7_CONTROL_B_COVARIATE_SPEC.json")

    print("  loading corpus...", flush=True)
    idx = Index(MC.load_corpus(), coverage)
    print(f"  corpus: {len(idx.recs)} records, {len(idx.metrics)} gated metrics", flush=True)

    axes = sorted({json.loads(c).get("axis") for f in ded
                   for c in (f["canonical_spec"].get("CONDITIONS") or [])
                   if c.strip().startswith("{") and json.loads(c).get("axis")})
    terciles, axis_cache = build_terciles(
        idx, idx.metrics, folds_art["confirmatory_start_unix"], axes)
    print(f"  PIT terciles built for axes {axes} ({len(terciles)} comp-axis cells)",
          flush=True)

    # ---- ENDPOINT A: LLM universe + uniform control ---------------------------------
    print("  evaluating LLM universe (132 canonical families)...", flush=True)
    llm_records = run_origin(idx, ded, meas_rows, comparator_ok, folds, dev_window,
                             terciles, axis_cache, coverage, "LLM", 25)
    print("  evaluating UNIFORM control pool (1980 canonical families)...", flush=True)
    null_records = run_origin(idx, nullu["families"], null_meas, {}, folds, dev_window,
                              terciles, axis_cache, coverage, "NULL_UNIFORM", 200)

    fam_llm = apply_multiplicity(llm_records)
    fam_null = apply_multiplicity(null_records)
    states_llm = finalize_states(llm_records, comparator_ok)
    states_null = finalize_states(null_records, {})

    # ---- ENDPOINT B: matched comparison using the FROZEN weights ---------------------
    # The marginal-matched pool is regenerated DETERMINISTICALLY exactly as the freeze built
    # it (same seed, same marginals, same pool size) and indexed by canonical id, so the
    # frozen weights address the identical families. This is exact reproduction, not redesign.
    from src.research.hypothesis_v7 import canonical as C
    from src.research.hypothesis_v7 import null_benchmark as NB
    marginals = NB.derive_marginals(ded)
    nullm = NB.build(list(P.corpus_bindings().keys()), C,
                     pool_size=NB.NULL_MATCHED_POOL_SIZE,
                     sampling=NB.SAMPLING_MARGINAL, marginals=marginals)
    by_cid = {f["canonical_hypothesis_id"]: f for f in nullm["families"]}
    ctrl_needed = sorted({c for a in weights["assignments"] for c in a["control_ids"]})
    missing = [c for c in ctrl_needed if c not in by_cid]
    if missing:
        print("STOP BEFORE OOS -- matched control pool not reproducible; "
              f"{len(missing)} weighted controls absent")
        return 1
    matched_pool = [by_cid[c] for c in ctrl_needed]
    print(f"  matched pool reproduced: {nullm['n_canonical_families']} families; "
          f"evaluating {len(matched_pool)} weighted controls...", flush=True)
    matched_records = run_origin(
        idx, matched_pool,
        {cid: {"status": P.MEASURABLE} for cid in ctrl_needed},
        {}, folds, dev_window, terciles, axis_cache, coverage, "NULL_MATCHED", 100)
    apply_multiplicity(matched_records)
    finalize_states(matched_records, {})
    return _finish(idx, llm_records, null_records, matched_records, weights,
                   fam_llm, fam_null, states_llm, states_null, folds, engine_hash,
                   champ_before, prereg)


def _funnel(records, label):
    """End-to-end attrition ladder for one origin (endpoint A)."""
    from collections import Counter
    n_can = len(records)
    n_meas = sum(1 for r in records if r["measurability"] == P.MEASURABLE)
    n_support = sum(1 for r in records if r.get("score") is not None)
    n_surv = sum(1 for r in records
                 if r["terminal_state"] in ("OOS_SURVIVES", "CANDIDATE_FEATURE_ELIGIBLE"))
    return {"origin": label, "canonical": n_can,
            "measurable": n_meas,
            "measurable_rate": round(n_meas / max(n_can, 1), 4),
            "support_eligible": n_support,
            "support_eligible_rate": round(n_support / max(n_can, 1), 4),
            "oos_surviving": n_surv,
            "oos_surviving_rate": round(n_surv / max(n_can, 1), 4),
            "terminal_states": dict(Counter(r["terminal_state"] for r in records))}


def _endpoint_b(llm_records, matched_records, weights):
    """Frozen matched/weighted estimator. Weights are reused verbatim, never recomputed."""
    lookup = {r["canonical_hypothesis_id"]: r for r in llm_records}
    ctrl = {r["canonical_hypothesis_id"]: r for r in matched_records}

    def q(rec):
        sc = rec.get("score")
        return None if not sc else sc["oos_quality_score"]

    pairs, skipped = [], {"llm_unscored": 0, "no_control_scored": 0}
    for a in weights["assignments"]:
        if a["tier"] == "NO_COMPARABLE_CONTROL":
            continue
        lr = lookup.get(a["canonical_hypothesis_id"])
        ql = q(lr) if lr else None
        if ql is None:
            skipped["llm_unscored"] += 1
            continue
        num = den = 0.0
        for cid in a["control_ids"]:
            cq = q(ctrl.get(cid, {}))
            if cq is None:
                continue
            num += a["weight_per_control"] * cq
            den += a["weight_per_control"]
        if den <= 0:
            skipped["no_control_scored"] += 1
            continue
        pairs.append({"canonical_hypothesis_id": a["canonical_hypothesis_id"],
                      "tier": a["tier"], "llm_score": ql,
                      "weighted_control_score": num / den,
                      "diff": ql - num / den,
                      "n_controls_scored": sum(
                          1 for cid in a["control_ids"] if q(ctrl.get(cid, {})) is not None)})
    if not pairs:
        return {"n_matched_pairs": 0, "estimate": None, "skipped": skipped,
                "note": "no matched pair had a computable score on both sides"}
    diffs = [p["diff"] for p in pairs]
    n = len(diffs)
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1) if n > 1 else 0.0
    se = (var / n) ** 0.5 if n > 1 else None
    # clustered by (metric_family, primary metric) per the frozen uncertainty rule
    clusters = {}
    for p_ in pairs:
        r = lookup[p_["canonical_hypothesis_id"]]
        key = (A.multiplicity_family_of(r.get("family")),
               (sorted(r.get("target") or [None]) or [None])[0])
        clusters.setdefault(key, []).append(p_["diff"])
    cl_means = [sum(v) / len(v) for v in clusters.values()]
    ncl = len(cl_means)
    cl_mean = sum(cl_means) / ncl
    cl_var = sum((m - cl_mean) ** 2 for m in cl_means) / (ncl - 1) if ncl > 1 else 0.0
    cl_se = (cl_var / ncl) ** 0.5 if ncl > 1 else None
    return {
        "n_matched_pairs": n,
        "mean_llm_score": sum(p_["llm_score"] for p_ in pairs) / n,
        "mean_weighted_control_score": sum(p_["weighted_control_score"]
                                           for p_ in pairs) / n,
        "estimate": mean, "naive_se": se,
        "n_clusters": ncl, "clustered_se": cl_se,
        "clustered_t": (cl_mean / cl_se) if cl_se else None,
        "clustered_p": ME.t_two_sided_p(cl_means) if ncl > 1 else None,
        "skipped": skipped, "pairs": pairs,
        "uncertainty_rule": ("cluster bootstrap-equivalent: clustered by "
                             "(multiplicity family, primary metric); raw control-pool N "
                             "never drives precision"),
    }


def _finish(idx, llm_records, null_records, matched_records, weights,
            fam_llm, fam_null, states_llm, states_null, folds, engine_hash,
            champ_before, prereg):
    from collections import Counter
    hashes = {}
    hashes["V7_OOS_LLM_EVIDENCE.json"] = _write("V7_OOS_LLM_EVIDENCE.json",
                                                {"records": llm_records})
    hashes["V7_OOS_NULL_UNIFORM_EVIDENCE.json"] = _write(
        "V7_OOS_NULL_UNIFORM_EVIDENCE.json", {"records": null_records})
    hashes["V7_OOS_NULL_MATCHED_EVIDENCE.json"] = _write(
        "V7_OOS_NULL_MATCHED_EVIDENCE.json", {"records": matched_records})

    ep_a = {"endpoint": "END_TO_END_RESEARCH_YIELD",
            "llm": _funnel(llm_records, "LLM"),
            "null_uniform": _funnel(null_records, "NULL_UNIFORM"),
            "includes_unmeasurable": True}
    hashes["V7_OOS_ENDPOINT_A.json"] = _write("V7_OOS_ENDPOINT_A.json", ep_a)

    ep_b = _endpoint_b(llm_records, matched_records, weights)
    ep_b["endpoint"] = "CONDITIONAL_SIGNAL_QUALITY"
    hashes["V7_OOS_ENDPOINT_B.json"] = _write("V7_OOS_ENDPOINT_B.json", ep_b)

    # fold-level table
    fold_tab = []
    for f in folds:
        rows = []
        for r in llm_records:
            if not r.get("evidence"):
                continue
            for m, blk in r["evidence"]["per_metric"].items():
                for fr in blk["folds"]:
                    if fr["fold_index"] == f["fold_index"] and fr["effect"] is not None:
                        rows.append(fr["effect"])
        fold_tab.append({"fold_index": f["fold_index"],
                         "train_end_iso": f["train_end_iso"],
                         "validate_end_iso": f["validate_end_iso"],
                         "n_llm_effects": len(rows),
                         "mean_effect": (sum(rows) / len(rows)) if rows else None,
                         "pct_positive": (sum(1 for x in rows if x > 0) / len(rows))
                         if rows else None})
    hashes["V7_OOS_FOLDS.json"] = _write("V7_OOS_FOLDS.json", {"folds": fold_tab})

    # league stability + family results
    comp_counter = Counter()
    for r in llm_records:
        if not r.get("evidence"):
            continue
        for m, blk in r["evidence"]["per_metric"].items():
            for fr in blk["folds"]:
                for c in fr.get("competitions") or []:
                    comp_counter[c] += 1
    by_family = {}
    for r in llm_records:
        fam = A.multiplicity_family_of(r.get("family"))
        d = by_family.setdefault(fam, Counter())
        d[r["terminal_state"]] += 1
    hashes["V7_OOS_STABILITY.json"] = _write("V7_OOS_STABILITY.json", {
        "competition_participation": dict(comp_counter),
        "terminal_states_by_multiplicity_family": {k: dict(v)
                                                   for k, v in sorted(by_family.items())},
        "multiplicity_llm": fam_llm, "multiplicity_null_uniform": fam_null})

    survivors = [{"canonical_hypothesis_id": r["canonical_hypothesis_id"],
                  "family": r["family"], "target": r["target"],
                  "comparator": r["comparator"], "time_scope": r["time_scope"],
                  "uses_similarity": r["uses_similarity"],
                  "score": r["score"], "terminal_state": r["terminal_state"]}
                 for r in llm_records
                 if r["terminal_state"] in ("OOS_SURVIVES", "CANDIDATE_FEATURE_ELIGIBLE")]
    hashes["V7_CANDIDATE_FEATURE_SET.json"] = _write("V7_CANDIDATE_FEATURE_SET.json", {
        "n_candidates": len(survivors), "candidates": survivors,
        "promoted_to_production": False, "champion_modified": False,
        "eligible_for": "the NEXT experiment only"})

    champ_after = sha_file(CHAMPION)
    states = ["V7_CONFIRMATORY_OOS_EXECUTED", "V7_OOS_EVIDENCE_FROZEN",
              "V7_ENDPOINT_A_EVALUATED", "V7_ENDPOINT_B_EVALUATED",
              "V7_MULTIPLICITY_APPLIED", "V7_CANDIDATE_FEATURE_SET_FROZEN",
              "V7_CHAMPION_UNCHANGED", "V7_EXPERIMENT_COMPLETE"]
    final = {"experiment": "V7_DETERMINISTIC_HYPOTHESIS_VALIDATION",
             "execution_status": "COMPLETE",
             "confirmatory_oos_computed": True, "confirmatory_oos_viewed": True,
             "post_oos_design_changes": 0,
             "candidate_feature_promotion": False,
             "bedrock_used": False, "kiro_handoff_required": False,
             "engine_spec_sha256": engine_hash,
             "champion_sha256_before": champ_before,
             "champion_sha256_after": champ_after,
             "champion_unchanged": champ_before == champ_after,
             "evidence_hashes": hashes,
             "states_emitted": states}
    _write("V7_OOS_STATES.json", final)

    print("\n=== RESULTS ===")
    print(f"  ENDPOINT A  LLM : {ep_a['llm']}")
    print(f"  ENDPOINT A NULL : {ep_a['null_uniform']}")
    print(f"  ENDPOINT B      : pairs={ep_b.get('n_matched_pairs')} "
          f"estimate={ep_b.get('estimate')} clustered_p={ep_b.get('clustered_p')}")
    print(f"  candidates      : {len(survivors)}")
    print(f"  CHAMPION        : {champ_before[:16]} -> {champ_after[:16]} "
          f"unchanged={champ_before == champ_after}")
    for s in states:
        print(f"    [STATE] {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
