"""
Step 1 — Model-free correlation structure of same-game outcomes.

Measures realized pairwise correlation between match-level count outcomes
(cards, corners, goals) across the full FootyStats corpus, then breaks it
down by match profile to test the core hypothesis: does the outcome
correlation vary materially by identifiable match profile?

NO MODEL. NO ODDS. Realized outcomes only. Zero API calls.

Outputs data/results/samegame_step1_correlation.json and prints a report.

Definitions (consistent with the validated marginal models):
- total_cards  = team_a_yellow + team_b_yellow + team_a_red + team_b_red
- total_corners= totalCornerCount (requires corner_timings_recorded != 0)
- total_goals  = overallGoalCount

Profiles:
- referee card tendency: expanding-window (strictly-prior) mean total_cards
  for the referee (look-ahead free); split at within-corpus terciles.
- tempo: total dangerous attacks (a+b); terciles.
- competitive balance: |home_ppg - away_ppg| (pre-match season PPG); close vs mismatched by median.
- league (competition_id) and league tier (derived from league_mapping if available).

Because pooling leagues can manufacture correlation via differing league
means (a Simpson-type artifact), every pooled correlation is reported
alongside a WITHIN-league-season version that z-scores each outcome within
its league-season before pooling. If a profile effect survives the
within-league-season control, it is not a league-mix artifact.
"""

import json
import glob
import math
from collections import defaultdict

import numpy as np
from scipy.stats import pearsonr, spearmanr

BASE = "/home/ubuntu"
CORPUS = f"{BASE}/data/discovery/corpus"
OUT = f"{BASE}/data/results/samegame_step1_correlation.json"


def load_corpus():
    rows = []
    for f in sorted(glob.glob(f"{CORPUS}/league-matches_*.json")):
        d = json.load(open(f))
        data = d.get("data", d)
        for m in data:
            if m.get("status") != "complete":
                continue
            rows.append(m)
    return rows


def _num(x):
    try:
        v = float(x)
        return v
    except (TypeError, ValueError):
        return None


def extract(m):
    """Extract outcomes + profile fields for one match, or None if invalid."""
    ya = _num(m.get("team_a_yellow_cards"))
    yb = _num(m.get("team_b_yellow_cards"))
    ra = _num(m.get("team_a_red_cards")) or 0.0
    rb = _num(m.get("team_b_red_cards")) or 0.0
    if ya is None or yb is None or ya < 0 or yb < 0:
        return None
    cards = ya + yb + ra + rb

    corners = _num(m.get("totalCornerCount"))
    corner_ok = corners is not None and corners >= 0 and m.get("corner_timings_recorded", 0) != 0

    goals = _num(m.get("overallGoalCount"))
    if goals is None or goals < 0:
        return None

    da = (_num(m.get("team_a_dangerous_attacks")) or 0.0) + (_num(m.get("team_b_dangerous_attacks")) or 0.0)
    shots = (_num(m.get("team_a_shots")) or 0.0) + (_num(m.get("team_b_shots")) or 0.0)
    hppg = _num(m.get("home_ppg")) or 0.0
    appg = _num(m.get("away_ppg")) or 0.0
    ref = m.get("refereeID", -1)
    if ref in (None, -1):
        ref = None
    ls = (m.get("competition_id"), m.get("season"))

    return {
        "cards": cards,
        "corners": corners if corner_ok else None,
        "goals": goals,
        "tempo_da": da if da > 0 else None,
        "shots": shots if shots > 0 else None,
        "ppg_gap": abs(hppg - appg) if (hppg > 0 and appg > 0) else None,
        "ref": ref,
        "comp": m.get("competition_id"),
        "season": m.get("season"),
        "ls": ls,
        "date_unix": m.get("date_unix", 0),
    }


def corr_block(x, y):
    """Return dict of Pearson/Spearman with n for paired arrays (drop NaN)."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = int(len(x))
    if n < 30 or np.std(x) == 0 or np.std(y) == 0:
        return {"n": n, "pearson": None, "pearson_p": None, "spearman": None, "spearman_p": None}
    pr, pp = pearsonr(x, y)
    sr, sp = spearmanr(x, y)
    return {
        "n": n,
        "pearson": round(float(pr), 4),
        "pearson_p": float(pp),
        "spearman": round(float(sr), 4),
        "spearman_p": float(sp),
    }


def zscore_within_ls(recs, field):
    """Return a dict match-index -> z-scored value within its league-season."""
    groups = defaultdict(list)
    for i, r in enumerate(recs):
        v = r[field]
        if v is not None:
            groups[r["ls"]].append((i, v))
    z = {}
    for ls, items in groups.items():
        vals = np.array([v for _, v in items], float)
        mu, sd = vals.mean(), vals.std()
        if sd == 0:
            for i, _ in items:
                z[i] = 0.0
        else:
            for (i, v) in items:
                z[i] = (v - mu) / sd
    return z


PAIRS = [("cards", "corners"), ("cards", "goals"), ("corners", "goals")]


def pooled_and_within(recs):
    """Overall pooled correlation and within-league-season correlation per pair."""
    out = {}
    zc = {f: zscore_within_ls(recs, f) for f in ("cards", "corners", "goals")}
    for a, b in PAIRS:
        xa = [r[a] if r[a] is not None else np.nan for r in recs]
        xb = [r[b] if r[b] is not None else np.nan for r in recs]
        pooled = corr_block(xa, xb)
        za = [zc[a].get(i, np.nan) for i in range(len(recs))]
        zb = [zc[b].get(i, np.nan) for i in range(len(recs))]
        within = corr_block(za, zb)
        out[f"{a}_x_{b}"] = {"pooled": pooled, "within_league_season": within}
    return out


def build_referee_prior(recs):
    """Expanding-window (strictly prior) referee mean total_cards, look-ahead free.

    Returns a dict match-index -> prior mean cards for that referee (or None
    if the referee has no prior matches). Uses chronological order.
    """
    order = sorted(range(len(recs)), key=lambda i: recs[i]["date_unix"])
    running_sum = defaultdict(float)
    running_n = defaultdict(int)
    prior = {}
    for i in order:
        r = recs[i]
        ref = r["ref"]
        if ref is None:
            prior[i] = None
        else:
            n = running_n[ref]
            prior[i] = (running_sum[ref] / n) if n >= 5 else None
            running_sum[ref] += r["cards"]
            running_n[ref] += 1
    return prior


def tercile_labels(values):
    """Return (labels list aligned to input, edges). None values -> None label."""
    v = np.array([x for x in values if x is not None], float)
    if len(v) < 30:
        return [None] * len(values), None
    q1, q2 = np.quantile(v, [1 / 3, 2 / 3])
    labels = []
    for x in values:
        if x is None:
            labels.append(None)
        elif x <= q1:
            labels.append("low")
        elif x <= q2:
            labels.append("mid")
        else:
            labels.append("high")
    return labels, (float(q1), float(q2))


def subset_corr(recs, idxs):
    sub = [recs[i] for i in idxs]
    if len(sub) < 30:
        return None
    return pooled_and_within(sub)


def profile_split(recs, labels, name):
    """Compute per-bucket correlations for a labelled profile split."""
    buckets = defaultdict(list)
    for i, lab in enumerate(labels):
        if lab is not None:
            buckets[lab].append(i)
    res = {}
    for lab, idxs in sorted(buckets.items()):
        res[lab] = {"n_matches": len(idxs), "corr": subset_corr(recs, idxs)}
    return {"profile": name, "buckets": res}


def main():
    recs = load_corpus()
    print(f"Loaded {len(recs)} complete matches (pre-extract)")
    recs = [r for r in (extract(m) for m in recs) if r is not None]
    print(f"Usable matches: {len(recs)}")

    n_corners = sum(1 for r in recs if r["corners"] is not None)
    print(f"  with valid corners: {n_corners}")

    result = {
        "n_matches": len(recs),
        "n_with_corners": n_corners,
        "n_league_seasons": len({r["ls"] for r in recs}),
        "definitions": {
            "total_cards": "team_a_yellow+team_b_yellow+team_a_red+team_b_red",
            "total_corners": "totalCornerCount (corner_timings_recorded!=0)",
            "total_goals": "overallGoalCount",
        },
    }

    # ── Overall ──
    result["overall"] = pooled_and_within(recs)

    # ── Profiles ──
    profiles = {}

    # Referee card tendency (look-ahead-free expanding prior), terciles
    ref_prior = build_referee_prior(recs)
    ref_vals = [ref_prior.get(i) for i in range(len(recs))]
    ref_labels, ref_edges = tercile_labels(ref_vals)
    profiles["referee_card_tendency"] = profile_split(recs, ref_labels, "referee_card_tendency")
    profiles["referee_card_tendency"]["tercile_edges"] = ref_edges
    profiles["referee_card_tendency"]["n_with_prior"] = sum(1 for v in ref_vals if v is not None)

    # Tempo (total dangerous attacks), terciles
    tempo_vals = [r["tempo_da"] for r in recs]
    tempo_labels, tempo_edges = tercile_labels(tempo_vals)
    profiles["tempo_dangerous_attacks"] = profile_split(recs, tempo_labels, "tempo_dangerous_attacks")
    profiles["tempo_dangerous_attacks"]["tercile_edges"] = tempo_edges

    # Competitive balance |ppg gap|, median split (close vs mismatched)
    gap_vals = [r["ppg_gap"] for r in recs]
    gv = np.array([x for x in gap_vals if x is not None], float)
    med = float(np.median(gv)) if len(gv) else None
    bal_labels = [None if x is None else ("close" if x <= med else "mismatched") for x in gap_vals]
    profiles["competitive_balance"] = profile_split(recs, bal_labels, "competitive_balance")
    profiles["competitive_balance"]["median_ppg_gap"] = med

    # League (top leagues by n) — pooled only meaningful within-league anyway
    comp_counts = defaultdict(int)
    for r in recs:
        comp_counts[r["comp"]] += 1
    top_comps = sorted(comp_counts, key=comp_counts.get, reverse=True)[:12]
    league_res = {}
    for c in top_comps:
        idxs = [i for i, r in enumerate(recs) if r["comp"] == c]
        league_res[str(c)] = {"n_matches": len(idxs), "corr": subset_corr(recs, idxs)}
    profiles["league"] = {"profile": "league", "buckets": league_res}

    result["profiles"] = profiles

    # ── Variation summary (Spearman spread across buckets, WITHIN control) ──
    def spread(profkey):
        buckets = profiles[profkey]["buckets"]
        summ = {}
        for pair in ["cards_x_corners", "cards_x_goals", "corners_x_goals"]:
            vals = []
            for lab, b in buckets.items():
                c = b.get("corr")
                if c and c[pair]["within_league_season"]["spearman"] is not None:
                    vals.append((lab, c[pair]["within_league_season"]["spearman"], c[pair]["within_league_season"]["n"]))
            if len(vals) >= 2:
                s = [v for _, v, _ in vals]
                summ[pair] = {
                    "buckets": vals,
                    "range": round(max(s) - min(s), 4),
                    "min": round(min(s), 4),
                    "max": round(max(s), 4),
                }
        return summ

    result["variation_within_control"] = {
        k: spread(k) for k in ["referee_card_tendency", "tempo_dangerous_attacks", "competitive_balance", "league"]
    }

    import os
    os.makedirs(f"{BASE}/data/results", exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2)

    # ── Print report ──
    print("\n" + "=" * 78)
    print("STEP 1 — MODEL-FREE OUTCOME CORRELATION STRUCTURE")
    print("=" * 78)
    print(f"n matches = {result['n_matches']}  (corners valid on {n_corners});  "
          f"{result['n_league_seasons']} league-seasons")
    print("\nOVERALL (pooled | within-league-season):")
    for pair, c in result["overall"].items():
        p, w = c["pooled"], c["within_league_season"]
        print(f"  {pair:18s}  Pearson pooled={p['pearson']} within={w['pearson']} | "
              f"Spearman pooled={p['spearman']} within={w['spearman']}  (n={p['n']})")

    for pk in ["referee_card_tendency", "tempo_dangerous_attacks", "competitive_balance", "league"]:
        print(f"\n{pk.upper()} — within-league-season Spearman by bucket:")
        for pair, s in result["variation_within_control"].get(pk, {}).items():
            bs = ", ".join(f"{lab}:{v:+.3f}(n={n})" for lab, v, n in s["buckets"])
            print(f"  {pair:18s} range={s['range']:+.3f}  [{bs}]")

    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
