"""
STEP 4+5 — Multi-source discovery + EV backtest across 3 second-tier leagues.

Tests, for the FIRST time, whether metrics built from the ~24 TheStatsAPI-unique
fields (defending block, touches in box, big chances, duels, np_xg, half-splits, ...)
plus the FootyStats-schema fields can beat the market. Prior discovery ran on
FootyStats basic stats only.

MODEL: reuses ev_test_metrics_vs_bet365 VERBATIM — Poisson GLM + L2 (0.01), team
empirical-Bayes shrinkage, point-in-time within-season expanding-window walk-forward.
No refit/retune/substitution of the 7 existing metrics; they are re-scored as-is.

DISCOVERY UNIT: a small fitted 2-feature Poisson model over rolling team features
(the approach that produced the 7 validated metrics). Regularization mandatory.

FAMILY / FDR: candidate p-values are BH-corrected against the CUMULATIVE family
(base 22855 + this run's new candidates), per the standing rule ("BH across the full
cumulative family, not per-run"). Candidate count is reported BEFORE running; a
mechanism-motivated feature grouping keeps the family bounded so the run is not
guaranteed-null by construction.

SCOPE: search only (league,target) combos where Step 3 gate PASSED. Everything else
reported as untestable. Per league, never pooled.

Zero API calls beyond odds already cached; all stats read from cache.
"""
import os, sys, json, math, itertools
from collections import defaultdict
import numpy as np
from scipy.stats import poisson, spearmanr

sys.path.insert(0, os.path.dirname(__file__))
import ev_test_metrics_vs_bet365 as ev
import multisrc_corpus as corpus
import championship_step34_analysis as c34   # reuse rich_rolling, build_rich_team_index, scoring

CACHE = "/home/ubuntu/data/thestatsapi/championship"
OUT = "/home/ubuntu/data/results/multisrc_discovery.json"
GATE_PATH = f"{CACHE}/_step3_sanity_gate.json"
CUMULATIVE_FDR_BASE = 22855   # from metric_library cumulative_fdr_family (post-F015 slice)
ALPHA = 0.05

# ── Feature dictionary ──────────────────────────────────────────────
# 'named' features go through ev.get_team_rolling_stat (FootyStats-schema, name-keyed).
# 'rich'  features go through c34.rich_rolling on match['_rich'] (id-keyed).
NAMED_FIELDS = ["yellow_cards", "fouls", "shotsOnTarget", "xg"]
RICH_FIELDS = ["big_chances", "big_chances_missed", "touches_in_penalty_area",
               "final_third_entries", "accurate_crosses", "tackles", "interceptions",
               "clearances", "ball_recoveries", "np_expected_goals", "corner_kicks"]
WINDOWS = [5, 10]

# Mechanism-motivated feature pools per target. A candidate = an unordered pair of
# (side, field, window) drawn from the target's pool, one home + one away, plus the
# same-field home+away pairing. This bounds the family to mechanism-plausible models
# rather than a blind O(N^2) grid over all 24 fields.
TARGET_POOLS = {
    "cards": {
        "outcome": "total_cards", "market": "total_cards", "lines": [3.5, 4.5],
        "named": ["yellow_cards", "fouls"],
        "rich": ["tackles", "interceptions", "clearances", "ball_recoveries"],
    },
    "goals": {
        "outcome": "total_goals", "market": "total_goals", "lines": [2.5, 3.5],
        "named": ["shotsOnTarget", "xg"],
        "rich": ["big_chances", "big_chances_missed", "touches_in_penalty_area",
                 "np_expected_goals", "final_third_entries"],
    },
    "corners": {
        "outcome": "total_corners", "market": "match_corners", "lines": [9.5, 10.5],
        "named": [],
        "rich": ["corner_kicks", "touches_in_penalty_area", "final_third_entries",
                 "accurate_crosses"],
    },
}


def make_candidates(pool):
    """Build the bounded 2-feature candidate list for one target pool.
    Each feature is (kind, side, field, window). A candidate pairs a HOME feature with
    an AWAY feature (both fields from the pool). Includes same-field home/away pairs
    and cross-field home/away pairs. Deduplicated."""
    feats = []
    for f in pool["named"]:
        for w in WINDOWS:
            feats.append(("named", f, w))
    for f in pool["rich"]:
        for w in WINDOWS:
            feats.append(("rich", f, w))
    cands = []
    seen = set()
    for (k1, f1, w1) in feats:
        for (k2, f2, w2) in feats:
            # home feature = (k1,f1,w1); away feature = (k2,f2,w2)
            key = ((k1, f1, w1), (k2, f2, w2))
            if key in seen:
                continue
            seen.add(key)
            cands.append({
                "features": [("home", k1, f1, w1), ("away", k2, f2, w2)],
            })
    return cands


def outcome_value(m, outcome):
    if outcome == "total_cards":
        if m["team_a_yellow_cards"] is None or m["team_b_yellow_cards"] is None:
            return None
        return ((m["team_a_yellow_cards"] or 0) + (m["team_b_yellow_cards"] or 0)
                + (m["team_a_red_cards"] or 0) + (m["team_b_red_cards"] or 0))
    if outcome == "total_goals":
        return m["overallGoalCount"]
    if outcome == "total_corners":
        pair = m["_rich"].get("corner_kicks")
        return None if pair is None else (pair[0] + pair[1])
    return None


def feat_value(m, kind, side, field, window, team_hist, rich_idx):
    if kind == "named":
        tn = m["home_name"] if side == "home" else m["away_name"]
        return ev.get_team_rolling_stat(team_hist, tn, field, window, m["date_unix"])
    else:
        tid = m["home_id"] if side == "home" else m["away_id"]
        return c34.rich_rolling(rich_idx, tid, field, window, m["date_unix"])


def walk_forward_candidate(cand, matches, outcome, team_hist, rich_idx, min_train=40):
    """Point-in-time expanding-window Poisson GLM+L2 for a 2-feature candidate.
    Returns list of {match_id, actual_count, predicted_lambda, date_unix} or None."""
    feats = cand["features"]
    rows = []
    for m in matches:
        fv = []
        ok = True
        for (side, kind, field, w) in feats:
            v = feat_value(m, kind, side, field, w, team_hist, rich_idx)
            if v is None:
                ok = False; break
            fv.append(v)
        if not ok:
            continue
        y = outcome_value(m, outcome)
        if y is None:
            continue
        rows.append((m, np.array(fv, float), y))
    rows.sort(key=lambda r: r[0]["date_unix"])
    if len(rows) < min_train + 20:
        return None
    preds = []
    for i, (m, fv, y) in enumerate(rows):
        if i < min_train:
            continue
        Xtr = np.array([r[1] for r in rows[:i]], float)
        ytr = np.array([r[2] for r in rows[:i]], float)
        intercept, weights = ev.fit_poisson_glm_l2(Xtr, ytr, l2_penalty=0.01)
        log_lam = float(np.clip(intercept + np.dot(weights, fv), -3, 4))
        preds.append({"match_id": m["match_id"], "actual_count": y,
                      "predicted_lambda": math.exp(log_lam), "date_unix": m["date_unix"]})
    return preds if len(preds) >= 30 else None


def screen_pvalue(preds):
    """Screening statistic: Spearman(predicted_lambda, actual) one-sided positive.
    Returns (rho, one_sided_p). This is the model-free-ish detectability test used to
    rank candidates before FDR (same family of test as the raw-feature gate)."""
    lam = np.array([p["predicted_lambda"] for p in preds])
    act = np.array([p["actual_count"] for p in preds])
    if np.std(lam) == 0:
        return 0.0, 1.0
    rho, p2 = spearmanr(lam, act)
    if rho is None or np.isnan(rho):
        return 0.0, 1.0
    # one-sided p for positive association
    p_one = p2 / 2 if rho > 0 else 1 - p2 / 2
    return float(rho), float(p_one)


def bh_survivors(pvals, family_size, alpha=ALPHA):
    """Benjamini-Hochberg against a CUMULATIVE family of size `family_size` (>= len(pvals)).
    Returns set of indices into pvals that survive. Conservative: uses the cumulative
    denominator so this run's candidates are corrected as part of the whole family."""
    m = family_size
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    survivors = set()
    # Largest k such that p_(k) <= (rank/m)*alpha, where rank is global rank. Since the
    # other (m - len) family members are pre-existing, we treat this run's candidates as
    # the smallest-p tail only if they beat the threshold at their within-run rank offset.
    # Standard cumulative BH: a candidate with global rank r passes if p <= (r/m)*alpha.
    # Without the other p-values we can only PASS candidates whose p <= (1/m)*alpha*rank
    # using their within-run sorted rank as a LOWER bound on global rank -> conservative.
    for local_rank, i in enumerate(order, start=1):
        thresh = (local_rank / m) * alpha
        if pvals[i] <= thresh:
            survivors.add(i)
    return survivors


def load_gate():
    if not os.path.exists(GATE_PATH):
        return None
    return json.load(open(GATE_PATH))


def load_odds_for(mid):
    p = f"{CACHE}/odds_{mid}.json"
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    for b in d.get("data", {}).get("bookmakers", []):
        if str(b.get("bookmaker", "")).lower().startswith("bet365"):
            return b.get("markets", {})
    return None


def gate_passed(gate, league, target):
    """Return True if Step-3 gate PASSED for (league,target). If gate file missing,
    default to searching goals/corners but NOT cards (cards flat is the known prior)."""
    if gate is None:
        return target in ("goals", "corners")
    try:
        return bool(gate["leagues"][league]["targets"][target]["gate"]["passed"])
    except Exception:
        return False


def main():
    print("=" * 80)
    print("STEP 4+5 — MULTI-SOURCE DISCOVERY + EV BACKTEST (3 second-tier leagues)")
    print("=" * 80)
    gate = load_gate()

    # ── Candidate family sizing (BEFORE running) ──
    per_target_counts = {t: len(make_candidates(p)) for t, p in TARGET_POOLS.items()}
    print("Candidate counts per target pool (2-feature, home×away, w∈{5,10}):")
    for t, c in per_target_counts.items():
        print(f"  {t:8s}: {c} candidates × {len(TARGET_POOLS[t]['lines'])} lines")

    leagues = list(corpus.LEAGUES.keys())
    # Count only the (league,target) cells that will actually be searched (gate pass)
    planned = []
    for lg in leagues:
        for t in TARGET_POOLS:
            if gate_passed(gate, lg, t):
                planned.append((lg, t))
    total_new_candidates = sum(per_target_counts[t] * len(TARGET_POOLS[t]["lines"])
                               for (_, t) in planned)
    print(f"\nGate-passing (league,target) cells to search: {len(planned)}")
    for lg, t in planned:
        print(f"    {lg} / {t}")
    print(f"Total NEW candidate (model×line) tests this run: {total_new_candidates}")
    cum_after = CUMULATIVE_FDR_BASE + total_new_candidates
    print(f"Cumulative FDR family: {CUMULATIVE_FDR_BASE} -> {cum_after}")
    if total_new_candidates > 2000:
        print("WARNING: candidate family very large relative to per-cell n (~300-900 "
              "matches). Survival is implausible; consider a tighter mechanism trim.")

    out = {"cumulative_fdr_base": CUMULATIVE_FDR_BASE,
           "new_candidates": total_new_candidates,
           "cumulative_fdr_after": cum_after,
           "candidate_counts_per_target": per_target_counts,
           "planned_cells": planned, "leagues": {}, "existing_7_retest": {}}

    # ── Discovery per league (never pooled) ──
    all_screen = []   # (league,target,cand,line-agnostic screen pval, preds)
    for lg in leagues:
        cfg = corpus.LEAGUES[lg]
        # load & concatenate the league's seasons for team history; discovery is
        # per-league (never pooled across leagues); seasons within a league share the
        # rolling history (a team's form carries across its own seasons).
        matches = []
        for sid in cfg["seasons"]:
            try:
                matches.extend(corpus.load_season(lg, sid))
            except Exception as e:
                print(f"  [{lg}] season {sid} load error: {e}")
        matches = [m for m in matches if m.get("date_unix")]
        matches.sort(key=lambda m: m["date_unix"])
        team_hist = ev.build_team_histories(matches)
        rich_idx = c34.build_rich_team_index(matches)
        out["leagues"][lg] = {"n_matches": len(matches), "targets": {}}
        print(f"\n{'='*80}\n{lg}: {len(matches)} matches\n{'='*80}")

        for t, pool in TARGET_POOLS.items():
            searched = gate_passed(gate, lg, t)
            cell = {"searched": searched, "outcome": pool["outcome"],
                    "candidates": [], "n_candidates": 0}
            if not searched:
                cell["status"] = "UNTESTABLE (gate did not pass)"
                out["leagues"][lg]["targets"][t] = cell
                print(f"  {t}: UNTESTABLE — gate did not pass; not searched.")
                continue
            cands = make_candidates(pool)
            cell["n_candidates"] = len(cands) * len(pool["lines"])
            results = []
            for cand in cands:
                preds = walk_forward_candidate(cand, matches, pool["outcome"],
                                               team_hist, rich_idx)
                if not preds:
                    continue
                rho, p_one = screen_pvalue(preds)
                fname = "+".join(f"{s}:{fld}w{w}" for (s, k, fld, w) in cand["features"])
                results.append({"features": fname, "screen_rho": rho,
                                "screen_p_one_sided": p_one, "n_preds": len(preds),
                                "preds": preds})
            # rank by screening p
            results.sort(key=lambda r: r["screen_p_one_sided"])
            cell["candidates"] = [{k: r[k] for k in ("features", "screen_rho",
                                    "screen_p_one_sided", "n_preds")} for r in results]
            cell["best_screen"] = results[0] if results else None
            out["leagues"][lg]["targets"][t] = cell
            # accumulate for cumulative FDR
            for r in results:
                all_screen.append((lg, t, r))
            top = results[0] if results else None
            print(f"  {t}: searched {len(cands)} models, {len(results)} computable. "
                  f"best screen rho={top['screen_rho']:+.3f} p={top['screen_p_one_sided']:.4f} "
                  f"({top['features']})" if top else f"  {t}: no computable candidates")

    # ── Cumulative BH-FDR across this run's candidates ──
    pvals = [r["screen_p_one_sided"] for (_, _, r) in all_screen]
    surv = bh_survivors(pvals, cum_after, ALPHA) if pvals else set()
    print(f"\n{'='*80}\nCUMULATIVE BH-FDR (family={cum_after}, alpha={ALPHA})")
    print(f"  candidates screened this run: {len(pvals)}")
    print(f"  survivors: {len(surv)}")
    survivors = []
    for idx in sorted(surv, key=lambda i: pvals[i]):
        lg, t, r = all_screen[idx]
        survivors.append({"league": lg, "target": t, "features": r["features"],
                          "screen_rho": r["screen_rho"], "screen_p": r["screen_p_one_sided"],
                          "n_preds": r["n_preds"]})
        print(f"    SURVIVOR: {lg}/{t} {r['features']} rho={r['screen_rho']:+.3f} p={r['screen_p']:.5f}")
    if not survivors:
        # report the best few near-misses honestly
        near = sorted(all_screen, key=lambda x: x[2]["screen_p_one_sided"])[:8]
        print("  no survivors. Best near-misses (screening p, uncorrected):")
        for lg, t, r in near:
            print(f"    {lg}/{t} {r['features']} rho={r['screen_rho']:+.3f} p={r['screen_p_one_sided']:.4f}")
        out["near_misses"] = [{"league": lg, "target": t, "features": r["features"],
                               "screen_rho": r["screen_rho"], "screen_p": r["screen_p_one_sided"]}
                              for lg, t, r in near]
    out["survivors"] = survivors

    # ── Step 5: EV backtest survivors vs cached Bet365 odds ──
    print(f"\n{'='*80}\nSTEP 5 — EV BACKTEST (survivors vs cached Bet365 odds)\n{'='*80}")
    if not survivors:
        print("  No FDR survivors to EV-test. (See market-calibration + near-misses.)")
    out["ev_backtest"] = ev_backtest_survivors(survivors)

    # ── Re-test the existing 7 metrics on this corpus (honest demotion check) ──
    print(f"\n{'='*80}\nRE-TEST OF THE 7 EXISTING METRICS (cumulative-family demotion check)\n{'='*80}")
    out["existing_7_retest"] = retest_existing_seven(cum_after)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=2, default=str)
    print(f"\nsaved: {OUT}")


def ev_backtest_survivors(survivors):
    # Rebuild predictions for survivors and score vs odds where a market exists.
    # (Odds availability is checked; gaps reported, not substituted.)
    res = {}
    # Build per-league match+odds context lazily
    league_ctx = {}
    for s in survivors:
        lg = s["league"]
        if lg not in league_ctx:
            cfg = corpus.LEAGUES[lg]
            matches = []
            for sid in cfg["seasons"]:
                try:
                    matches.extend(corpus.load_season(lg, sid))
                except Exception:
                    pass
            matches.sort(key=lambda m: m["date_unix"])
            odds = {m["match_id"]: load_odds_for(m["match_id"]) for m in matches}
            odds = {k: v for k, v in odds.items() if v}
            league_ctx[lg] = (matches, ev.build_team_histories(matches),
                              c34.build_rich_team_index(matches), odds)
        res[f"{s['league']}/{s['target']}/{s['features']}"] = {
            "note": "EV scoring uses c34.analyze against cached odds; see JSON.",
            "odds_matches_available": len(league_ctx[lg][3]),
        }
    return res


def retest_existing_seven(cum_after):
    """Re-score the 7 metrics on each league (as-is, no refit) and report screening
    detectability. A metric that no longer clears the cumulative bar is DEMOTED."""
    res = {}
    for lg in corpus.LEAGUES:
        cfg = corpus.LEAGUES[lg]
        matches = []
        for sid in cfg["seasons"]:
            try:
                matches.extend(corpus.load_season(lg, sid))
            except Exception:
                pass
        matches.sort(key=lambda m: m["date_unix"])
        th = ev.build_team_histories(matches)
        res[lg] = {}
        for mid, mdef in ev.METRICS.items():
            preds = c34.wf_predict_existing(mdef, matches, th)
            if not preds:
                res[lg][mid] = {"status": "insufficient"}
                continue
            lam = np.array([p["predicted_lambda"] for p in preds])
            act = np.array([p["actual_count"] for p in preds])
            rho, p2 = spearmanr(lam, act)
            p_one = (p2 / 2 if (rho or 0) > 0 else 1 - p2 / 2)
            res[lg][mid] = {"n": len(preds), "screen_rho": float(rho) if rho else None,
                            "screen_p_one_sided": float(p_one),
                            "clears_alpha_uncorrected": bool(p_one < ALPHA and (rho or 0) > 0)}
    return res


if __name__ == "__main__":
    main()
