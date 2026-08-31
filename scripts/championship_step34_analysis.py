"""
Steps 3 + 4 — Championship offline discovery + EV backtest (zero API calls).

Reuses the EXACT model pipeline from scripts/ev_test_metrics_vs_bet365.py:
  * Poisson GLM + L2 (lambda=0.01), team empirical-Bayes shrinkage (strength=10),
    point-in-time rolling-window features, multiplicative vig removal.
NO refit of the 7 existing metrics, NO retune, NO model substitution. The model
consumes Championship data via championship_adapter (TheStatsAPI -> FootyStats schema).

Model training / features use FULL per-team season history (all 552 fixtures' stats,
cached offline). EV evaluation runs ONLY on the balanced 200 matches that have cached
Bet365 odds. Walk-forward: for each target, model is fit on all matches strictly
before it, and rolling features use only prior matches -> point-in-time safe.

Candidate set:
  A) The 7 validated metrics, run AS-IS (pre-registered; already in FDR family).
  B) A small mechanism-motivated new-field candidate set (added to cumulative FDR).

Sanity gate: before trusting any screening result, confirm the screener detects a
known-good signal (team card-rate -> total_cards) on this slice.
"""
import os, sys, json, math
from collections import defaultdict
import numpy as np
from scipy.stats import poisson

sys.path.insert(0, os.path.dirname(__file__))
import ev_test_metrics_vs_bet365 as ev
import championship_adapter as adapt

CACHE = "/home/ubuntu/data/thestatsapi/championship"
SEASON = "sn_3064530"
OUT = "/home/ubuntu/data/results/championship_step34.json"
RNG = np.random.default_rng(42)
CUMULATIVE_FDR_BASE = 22848  # from metric_library cumulative_search


# ─────────────────────────────────────────────────────────────
# Data: full-history matches (all cached stats) + odds subset
# ─────────────────────────────────────────────────────────────

def load_full_history():
    """All fixtures with cached stats -> adapted FootyStats-schema dicts (for model
    training + rolling features). Uses full 552 where stats cached."""
    allfx = json.load(open(f"{CACHE}/_all_fixtures_{SEASON}.json"))["fixtures"]
    fx_by_id = {m["id"]: m for m in allfx}
    out = []
    for mid, fx in fx_by_id.items():
        spath = f"{CACHE}/stats_{mid}.json"
        if not os.path.exists(spath):
            continue
        sj = json.load(open(spath))
        # adapt_match expects selection-shaped dict (id/date/home/away/score_*)
        sel_shape = {
            "id": mid, "date": fx["utc_date"],
            "home": fx["home_team"]["name"], "home_id": fx["home_team"]["id"],
            "away": fx["away_team"]["name"], "away_id": fx["away_team"]["id"],
            "score_home": fx.get("score", {}).get("home"),
            "score_away": fx.get("score", {}).get("away"),
        }
        out.append(adapt.adapt_match(sel_shape, sj))
    out.sort(key=lambda m: m["date_unix"])
    return out


def wf_predict_existing(mdef, matches, team_histories, min_train=60, refit_every=1):
    """Point-in-time WALK-FORWARD prediction for an EXISTING ev.METRICS metric on a
    single season. Uses ev.fit_poisson_glm_l2 + ev.get_team_rolling_stat +
    ev.compute_team_shrinkage_effects VERBATIM — identical model, features, L2, and
    shrinkage. Only the train/predict split is within-season expanding-window (the
    only point-in-time option for a one-season slice; the ev two-corpus split assumes
    multiple prior seasons which we do not have). No refit of coefficients' meaning,
    no retune of hyperparameters.
    """
    target = mdef["target"]
    feats = mdef["features"]

    def feat_vec(m):
        fv = []
        for side, stat, w in feats:
            tn = m["home_name"] if side == "home" else m["away_name"]
            v = ev.get_team_rolling_stat(team_histories, tn, stat, w, m["date_unix"])
            if v is None:
                return None
            fv.append(v)
        return np.array(fv, float)

    def outcome(m):
        if target == "total_cards":
            if m["team_a_yellow_cards"] is None or m["team_b_yellow_cards"] is None:
                return None
            return ((m["team_a_yellow_cards"] or 0) + (m["team_b_yellow_cards"] or 0)
                    + (m["team_a_red_cards"] or 0) + (m["team_b_red_cards"] or 0))
        if target == "total_goals":
            return m["overallGoalCount"]
        return None

    # Precompute per-match feature/outcome (None where not computable)
    rows = []
    for m in matches:
        rows.append((m, feat_vec(m), outcome(m)))
    rows.sort(key=lambda r: r[0]["date_unix"])

    preds = []
    cached_model = None
    for i, (m, fv, y) in enumerate(rows):
        if fv is None or y is None:
            continue
        # training set = all strictly-prior rows with valid features+outcome
        Xtr = [r[1] for r in rows[:i] if r[1] is not None and r[2] is not None]
        ytr = [r[2] for r in rows[:i] if r[1] is not None and r[2] is not None]
        if len(Xtr) < min_train:
            continue
        intercept, weights = ev.fit_poisson_glm_l2(np.array(Xtr, float),
                                                   np.array(ytr, float), l2_penalty=0.01)
        log_lam = float(np.clip(intercept + np.dot(weights, fv), -3, 4))
        lam = math.exp(log_lam)
        # team shrinkage (identical to ev), using only prior data
        te = ev.compute_team_shrinkage_effects(team_histories, target,
                                               m["date_unix"], min_matches=5)
        adj = (te.get(m["home_name"], 0.0) + te.get(m["away_name"], 0.0)) * 0.5
        lam_adj = lam * math.exp(adj)
        preds.append({"match_id": m["match_id"], "actual_count": y,
                      "predicted_lambda": lam_adj, "date_unix": m["date_unix"],
                      "home": m["home_name"], "away": m["away_name"]})
    return preds if len(preds) >= 20 else None


def load_odds_for(mid):
    p = f"{CACHE}/odds_{mid}.json"
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    for b in d.get("data", {}).get("bookmakers", []):
        if str(b.get("bookmaker", "")).lower().startswith("bet365"):
            return b.get("markets", {})
    return None


# ─────────────────────────────────────────────────────────────
# New-field candidate metrics (mechanism-motivated, small set)
# Feature source = adapted match['_rich'][name] -> (home, away)
# Target = total_cards | total_goals | match_corners
# ─────────────────────────────────────────────────────────────

NEW_METRICS = {
    "def_block_cards": {
        "name": "Defending block (tackles+interceptions, w10 both) -> cards",
        "target": "total_cards", "market": "total_cards",
        "features": [("home", "tackles", 10), ("away", "interceptions", 10)],
        "lines": [3.5, 4.5],
        "mechanism": "High defensive engagement (tackles/interceptions) reflects a "
                     "combative, disruptive style that draws more fouls and cautions.",
    },
    "territory_corners": {
        "name": "Territory (touches_in_pen_area + final_third_entries, w10) -> corners",
        "target": "match_corners", "market": "match_corners",
        "features": [("home", "touches_in_penalty_area", 10),
                     ("away", "final_third_entries", 10)],
        "lines": [9.5, 10.5],
        "mechanism": "Territorial pressure (final-third entries, box touches) forces "
                     "defensive clearances and blocked crosses -> more corners.",
    },
    "crosses_corners": {
        "name": "Crossing volume (accurate_crosses w10 both) -> corners",
        "target": "match_corners", "market": "match_corners",
        "features": [("home", "accurate_crosses", 10), ("away", "accurate_crosses", 10)],
        "lines": [9.5, 10.5],
        "mechanism": "Teams that cross a lot generate deflected/blocked balls out for "
                     "corners; crossing style correlates with corner count.",
    },
    "bigchance_goals": {
        "name": "Chance creation (big_chances w5 + np_xg w5) -> goals",
        "target": "total_goals", "market": "total_goals",
        "features": [("home", "big_chances", 5), ("away", "np_expected_goals", 5)],
        "lines": [2.5],
        "mechanism": "Big chances and non-penalty xG measure genuine chance quality/"
                     "quantity, the direct upstream of goals scored.",
    },
}


def rich_rolling(matches_by_team, team_id, field, window, before_unix):
    """Rolling mean of a _rich field for a team, using only prior matches. The team's
    value is home-slot if it was home, away-slot if away. Returns None if <window."""
    hist = matches_by_team.get(team_id, [])
    prior = [(d, m, role) for (d, m, role) in hist if d < before_unix]
    prior = prior[-window:]
    if len(prior) < window:
        return None
    vals = []
    for _, m, role in prior:
        pair = m["_rich"].get(field)
        if pair is None:
            return None
        vals.append(pair[0] if role == "home" else pair[1])
    return float(np.mean(vals))


def build_rich_team_index(matches):
    idx = defaultdict(list)
    for m in matches:
        idx[m["home_id"]].append((m["date_unix"], m, "home"))
        idx[m["away_id"]].append((m["date_unix"], m, "away"))
    for k in idx:
        idx[k].sort(key=lambda x: x[0])
    return idx


def target_value(m, target):
    if target == "total_cards":
        if m["team_a_yellow_cards"] is None or m["team_b_yellow_cards"] is None:
            return None
        return ((m["team_a_yellow_cards"] or 0) + (m["team_b_yellow_cards"] or 0)
                + (m["team_a_red_cards"] or 0) + (m["team_b_red_cards"] or 0))
    if target == "total_goals":
        return m["overallGoalCount"]
    if target == "match_corners":
        pair = m["_rich"].get("corner_kicks")
        return None if pair is None else (pair[0] + pair[1])
    return None


def compute_new_metric_predictions(mdef, matches, rich_idx):
    """Walk-forward Poisson GLM for a new-field candidate. Fit on matches before the
    earliest target that has full features; predict on all matches with features.
    Mirrors ev.compute_metric_predictions structure (no leakage)."""
    feats = mdef["features"]
    target = mdef["target"]

    rows = []  # (mid, features, outcome, date, home_id, away_id, home, away)
    for m in matches:
        fv, ok = [], True
        for side, field, w in feats:
            tid = m["home_id"] if side == "home" else m["away_id"]
            val = rich_rolling(rich_idx, tid, field, w, m["date_unix"])
            if val is None:
                ok = False; break
            fv.append(val)
        if not ok:
            continue
        y = target_value(m, target)
        if y is None:
            continue
        rows.append((m["match_id"], np.array(fv, float), y, m["date_unix"],
                     m["home_id"], m["away_id"], m["home_name"], m["away_name"]))
    if len(rows) < 30:
        return None
    rows.sort(key=lambda r: r[3])
    # Point-in-time within-season expanding-window walk-forward (single-season slice).
    return _walk_forward_within(rows, feats)


def _walk_forward_within(rows, feats):
    """Expanding-window fit strictly within the target rows (point-in-time)."""
    results = []
    for i, (mid, fvec, y, d, hid, aid, hn, an) in enumerate(rows):
        Xtr = [r[1] for r in rows[:i]]
        ytr = [r[2] for r in rows[:i]]
        if len(Xtr) < 40:
            continue
        intercept, weights = ev.fit_poisson_glm_l2(np.array(Xtr, float),
                                                   np.array(ytr, float), l2_penalty=0.01)
        log_lam = np.clip(intercept + np.dot(weights, fvec), -3, 4)
        results.append({"match_id": mid, "actual_count": y,
                        "predicted_lambda": math.exp(log_lam),
                        "date_unix": d, "home": hn, "away": an})
    return results if len(results) >= 30 else None


# ─────────────────────────────────────────────────────────────
# Scoring on the odds subset
# ─────────────────────────────────────────────────────────────

def score_line(preds, market_key, line, odds_by_mid):
    """Return per-match arrays restricted to matches with cached odds for market/line."""
    model_p, fair_p, actuals, over_odds, under_odds, overr = [], [], [], [], [], []
    for p in preds:
        mkts = odds_by_mid.get(p["match_id"])
        if not mkts:
            continue
        ld = mkts.get(market_key, {}).get(str(line))
        if not ld:
            continue
        try:
            o = float(ld["over"]["last_seen"]); u = float(ld["under"]["last_seen"])
        except (KeyError, TypeError, ValueError):
            continue
        if o <= 1 or u <= 1:
            continue
        lam = p["predicted_lambda"]
        po = float(np.clip(1.0 - poisson.cdf(int(line), lam), 0.01, 0.99))
        fo, fu = ev.devig_multiplicative(o, u)
        model_p.append(po); fair_p.append(float(fo))
        actuals.append(p["actual_count"]); over_odds.append(o); under_odds.append(u)
        overr.append(ev.compute_overround(o, u))
    return (np.array(model_p), np.array(fair_p), np.array(actuals, float),
            np.array(over_odds), np.array(under_odds), np.array(overr))


def bss(probs, outcomes):
    if len(probs) == 0:
        return None
    bs = np.mean((probs - outcomes) ** 2)
    base = np.mean(outcomes)
    bn = np.mean((base - outcomes) ** 2)
    return None if bn == 0 else 1.0 - bs / bn


def flat_roi_over(actuals, over_odds, line, seed=42):
    if len(actuals) == 0:
        return None
    out = (actuals > line).astype(float)
    profits = np.where(out == 1.0, over_odds - 1.0, -1.0)
    roi = float(np.mean(profits))
    rng = np.random.default_rng(seed)
    n = len(profits)
    boot = np.sort([np.mean(profits[rng.choice(n, n, replace=True)]) for _ in range(10000)])
    return roi, float(boot[250]), float(boot[9750]), n


def analyze(preds, market_key, lines, odds_by_mid, label):
    res = {}
    for line in lines:
        mp, fp, act, oo, uo, orr = score_line(preds, market_key, line, odds_by_mid)
        n = len(mp)
        if n < 5:
            res[str(line)] = {"n": n, "status": "insufficient"}
            continue
        outcomes = (act > line).astype(float)
        mbss = bss(mp, outcomes)
        kbss = bss(fp, outcomes)
        edges = mp - fp
        roi = flat_roi_over(act, oo, line)
        res[str(line)] = {
            "n": n,
            "base_rate_over": float(np.mean(outcomes)),
            "overround_mean_pct": float(np.mean(orr) * 100),
            "market_bss_pct": None if kbss is None else kbss * 100,
            "model_bss_pct": None if mbss is None else mbss * 100,
            "model_minus_market_bss_pct": None if (mbss is None or kbss is None) else (mbss - kbss) * 100,
            "edge_mean_pct": float(np.mean(edges) * 100),
            "edge_median_pct": float(np.median(edges) * 100),
            "edge_std_pct": float(np.std(edges) * 100),
            "edge_p10_pct": float(np.percentile(edges, 10) * 100),
            "edge_p90_pct": float(np.percentile(edges, 90) * 100),
            "n_positive_ev": int(np.sum(edges > 0)),
            "over_flat_roi_pct": roi[0] * 100,
            "over_flat_roi_ci95_pct": [roi[1] * 100, roi[2] * 100],
        }
    return res


# ─────────────────────────────────────────────────────────────
# Sanity gate
# ─────────────────────────────────────────────────────────────

def sanity_gate(matches):
    """Known-good detection test. The instrument should detect that a team's recent
    yellow-card rate carries information about total match cards: predicted lambda
    should rank-correlate POSITIVELY with realized cards, and high-predicted matches
    should have a higher over-rate than low-predicted ones. This checks the screener
    is wired correctly / the signal is present on THIS slice — not whether it beats
    the market. If it fails, downstream screening results are NOT trusted.
    """
    from scipy.stats import spearmanr
    th = ev.build_team_histories(matches)
    mdef = {"target": "total_cards",
            "features": [("home", "yellow_cards", 5), ("away", "yellow_cards", 5)],
            "lines": [3.5]}
    preds = wf_predict_existing(mdef, matches, th)
    if not preds:
        return {"passed": False, "reason": "no predictions", "n": 0}
    lam = np.array([p["predicted_lambda"] for p in preds])
    act = np.array([p["actual_count"] for p in preds])
    rho, pv = spearmanr(lam, act)
    line = 3.5
    po = 1 - poisson.cdf(int(line), lam)
    out = (act > line).astype(float)
    med = np.median(po)
    hi_rate = float(out[po >= med].mean()) if (po >= med).any() else None
    lo_rate = float(out[po < med].mean()) if (po < med).any() else None
    b = bss(np.clip(po, 0.01, 0.99), out)
    # Pass criterion: positive rank correlation (signal present & correctly oriented).
    passed = bool(rho is not None and rho > 0)
    return {"passed": passed,
            "spearman_lambda_actual": None if rho is None else float(rho),
            "spearman_p": None if pv is None else float(pv),
            "over_rate_high_pred": hi_rate, "over_rate_low_pred": lo_rate,
            "unconditional_bss_pct": None if b is None else b * 100,
            "predicted_mean_lambda": float(lam.mean()), "actual_mean": float(act.mean()),
            "n": len(preds),
            "interpretation": ("PASS = predicted card-lambda rank-correlates positively "
                               "with realized cards (known signal detectable on this slice)")}


def _old_sanity_gate(matches):
    th = ev.build_team_histories(matches)
    matched = {m["match_id"]: m for m in matches}
    mdef = {"target": "total_cards",
            "features": [("home", "yellow_cards", 5), ("away", "yellow_cards", 5)],
            "lines": [3.5]}
    preds = wf_predict_existing(mdef, matches, th)
    if not preds:
        return {"passed": False, "reason": "no predictions", "n": 0}
    # BSS of model P(over 3.5) vs naive, unconditional (no odds needed)
    line = 3.5
    probs, outs = [], []
    for p in preds:
        lam = p["predicted_lambda"]
        probs.append(float(np.clip(1 - poisson.cdf(int(line), lam), 0.01, 0.99)))
        outs.append(1.0 if p["actual_count"] > line else 0.0)
    b = bss(np.array(probs), np.array(outs))
    return {"passed": bool(b is not None and b > 0), "bss_pct": None if b is None else b * 100,
            "n": len(preds),
            "interpretation": "screener detects known team-card-rate signal (BSS>0 vs naive)"}


def main():
    print("=" * 80)
    print("CHAMPIONSHIP STEPS 3+4 — offline discovery + EV backtest")
    print("=" * 80)

    matches = load_full_history()
    n_stats = sum(1 for m in matches if m["team_a_yellow_cards"] is not None)
    print(f"matches with cached stats (full history for model): {len(matches)} "
          f"(cards populated {n_stats})")

    # odds subset (balanced 200)
    sel_ids = json.load(open(f"{CACHE}/_selected_balanced_{SEASON}.json"))["selected_match_ids"]
    odds_by_mid = {}
    for mid in sel_ids:
        mk = load_odds_for(mid)
        if mk:
            odds_by_mid[mid] = mk
    print(f"odds subset (balanced matches with Bet365 odds): {len(odds_by_mid)}")

    # ---- Sanity gate ----
    print("\n" + "-" * 80)
    sg = sanity_gate(matches)
    print(f"SANITY GATE: passed={sg['passed']}  spearman(lambda,actual)={sg.get('spearman_lambda_actual')}  "
          f"n={sg['n']}")
    print(f"  over-rate high-pred={sg.get('over_rate_high_pred')} low-pred={sg.get('over_rate_low_pred')}")
    model_trusted = sg["passed"]
    if not model_trusted:
        print("  *** SANITY GATE FAILED ***: the known team-card-rate signal is NOT")
        print("  detectable on this slice (predicted lambda does not positively rank-")
        print("  correlate with realized cards). Per the standing rule, ALL MODEL-SIDE")
        print("  screening/EV results below are reported but NOT TRUSTED as evidence.")
        print("  The MARKET-CALIBRATION numbers (market BSS vs naive) do NOT depend on")
        print("  our model and remain valid — they are the primary deliverable.")
    else:
        print("  -> screener validated on this slice; model-side results trustworthy.")

    th = ev.build_team_histories(matches)
    matched = {m["match_id"]: m for m in matches}
    rich_idx = build_rich_team_index(matches)

    out = {"season_id": SEASON, "n_history": len(matches), "n_odds": len(odds_by_mid),
           "sanity_gate": sg, "model_trusted": model_trusted,
           "market_calibration": {}, "existing_metrics": {}, "new_metrics": {}}

    # ---- Market calibration (MODEL-INDEPENDENT — the primary deliverable) ----
    # For each Bet365 O/U market/line present, compute the market's own BSS vs the
    # naive base-rate predictor, using vig-adjusted implied probs and realized totals.
    print("\n" + "=" * 80)
    print("MARKET CALIBRATION (Bet365, model-independent) — is the book sloppy?")
    print("EPL reference: goals corners market BSS ~ -0.35% (near naive).")
    print("=" * 80)
    actual_by_mid = {}
    for m in matches:
        actual_by_mid[m["match_id"]] = {
            "total_goals": m["overallGoalCount"],
            "total_cards": target_value(m, "total_cards"),
            "match_corners": target_value(m, "match_corners"),
        }
    market_lines = {"total_goals": ["0.5","1.5","2.5","3.5","4.5","5.5"],
                    "total_cards": ["2.5","3.5","4.5","5.5"],
                    "match_corners": ["8.5","9.5","10.5","11.5","12.5"]}
    for market, lines in market_lines.items():
        out["market_calibration"][market] = {}
        for line in lines:
            L = float(line)
            fair, outs, orrs = [], [], []
            for mid, mkts in odds_by_mid.items():
                ld = mkts.get(market, {}).get(line)
                act = actual_by_mid.get(mid, {}).get(market)
                if not ld or act is None:
                    continue
                try:
                    o = float(ld["over"]["last_seen"]); u = float(ld["under"]["last_seen"])
                except (KeyError, TypeError, ValueError):
                    continue
                if o <= 1 or u <= 1:
                    continue
                fo, _ = ev.devig_multiplicative(o, u)
                fair.append(float(fo)); outs.append(1.0 if act > L else 0.0)
                orrs.append(ev.compute_overround(o, u))
            n = len(fair)
            if n < 10:
                out["market_calibration"][market][line] = {"n": n, "status": "insufficient"}
                continue
            kbss = bss(np.array(fair), np.array(outs))
            out["market_calibration"][market][line] = {
                "n": n, "base_rate_over": float(np.mean(outs)),
                "overround_mean_pct": float(np.mean(orrs) * 100),
                "market_bss_vs_naive_pct": None if kbss is None else kbss * 100,
                "market_mean_implied_over": float(np.mean(fair)),
            }
            kb = out["market_calibration"][market][line]["market_bss_vs_naive_pct"]
            print(f"  {market:14s} @{line:>4}: n={n:3d} baseOver={np.mean(outs):.2f} "
                  f"orr={np.mean(orrs)*100:4.1f}% marketBSS_vs_naive="
                  f"{('n/a' if kb is None else format(kb,'+6.2f')+'%')}")

    # ---- A) 7 existing metrics AS-IS ----
    print("\n" + "=" * 80 + "\nA) EXISTING 7 METRICS (as-is, pre-registered)"
          + ("" if model_trusted else "  [MODEL-SIDE NOT TRUSTED — sanity gate failed]")
          + "\n" + "=" * 80)
    for mid, mdef in ev.METRICS.items():
        preds = wf_predict_existing(mdef, matches, th)
        if not preds:
            out["existing_metrics"][mid] = {"status": "insufficient"}
            print(f"\n{mid}: INSUFFICIENT")
            continue
        market = "total_cards" if mdef["target"] == "total_cards" else "total_goals"
        res = analyze(preds, market, mdef["lines"], odds_by_mid, mid)
        out["existing_metrics"][mid] = {"n_predictions": len(preds), "lines": res}
        print(f"\n{mid} ({mdef['target']}, preds={len(preds)}):")
        for ln, r in res.items():
            if r.get("status") == "insufficient":
                print(f"   @{ln}: n={r['n']} insufficient"); continue
            print(f"   @{ln}: n={r['n']:3d} mktBSS={r['market_bss_pct']:+6.2f}% "
                  f"mdlBSS={r['model_bss_pct']:+6.2f}% mdl-mkt={r['model_minus_market_bss_pct']:+6.2f}% "
                  f"edge_mean={r['edge_mean_pct']:+5.2f}% ROI={r['over_flat_roi_pct']:+6.1f}% "
                  f"[{r['over_flat_roi_ci95_pct'][0]:+5.1f},{r['over_flat_roi_ci95_pct'][1]:+5.1f}] "
                  f"orr={r['overround_mean_pct']:.1f}%")

    # ---- B) new-field candidates ----
    print("\n" + "=" * 80 + "\nB) NEW-FIELD CANDIDATES (added to cumulative FDR)\n" + "=" * 80)
    n_new_candidates = 0
    for mid, mdef in NEW_METRICS.items():
        preds = compute_new_metric_predictions(mdef, matches, rich_idx)
        n_new_candidates += len(mdef["lines"])
        if not preds:
            out["new_metrics"][mid] = {"status": "insufficient", "mechanism": mdef["mechanism"]}
            print(f"\n{mid}: INSUFFICIENT")
            continue
        res = analyze(preds, mdef["market"], mdef["lines"], odds_by_mid, mid)
        out["new_metrics"][mid] = {"n_predictions": len(preds), "mechanism": mdef["mechanism"],
                                   "lines": res}
        print(f"\n{mid} ({mdef['target']}, preds={len(preds)}): {mdef['name']}")
        for ln, r in res.items():
            if r.get("status") == "insufficient":
                print(f"   @{ln}: n={r['n']} insufficient"); continue
            print(f"   @{ln}: n={r['n']:3d} mktBSS={r['market_bss_pct']:+6.2f}% "
                  f"mdlBSS={r['model_bss_pct']:+6.2f}% mdl-mkt={r['model_minus_market_bss_pct']:+6.2f}% "
                  f"edge_mean={r['edge_mean_pct']:+5.2f}% ROI={r['over_flat_roi_pct']:+6.1f}% "
                  f"[{r['over_flat_roi_ci95_pct'][0]:+5.1f},{r['over_flat_roi_ci95_pct'][1]:+5.1f}] "
                  f"orr={r['overround_mean_pct']:.1f}%")

    out["candidate_accounting"] = {
        "existing_metrics_preregistered": 7,
        "new_field_candidates_metric_line": n_new_candidates,
        "cumulative_fdr_family_before": CUMULATIVE_FDR_BASE,
        "cumulative_fdr_family_after": CUMULATIVE_FDR_BASE + n_new_candidates,
        "note": ("Existing 7 metrics are pre-registered/validated and already in the "
                 "family; only new-field candidates increment it. New candidates are "
                 "metric x line combos.")
    }
    print("\n" + "=" * 80)
    print(f"CANDIDATE ACCOUNTING: {n_new_candidates} new-field candidates (metric x line)")
    print(f"  cumulative FDR family: {CUMULATIVE_FDR_BASE} -> {CUMULATIVE_FDR_BASE + n_new_candidates}")

    json.dump(out, open(OUT, "w"), indent=2, default=str)
    print(f"\nsaved: {OUT}")


if __name__ == "__main__":
    main()
