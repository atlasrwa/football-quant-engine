"""
Step 3 — sample-size / power ANALYSIS (zero requests).

NOTE: The Step-2 gate FAILED (35% usable), so scaling (Step 4) is NOT
proceeding. This analysis is advisory: it quantifies what a viable in-play
corpus would need IF reconciliation were fixed, and — more importantly —
addresses the within-match independence question, which governs effective
sample size regardless.

Uses only the already-cached, post-fix-usable matches. Reconstructs a simple
per-minute state series and measures:
  1. windows per match under a stated windowing scheme
  2. within-match autocorrelation of the state (are windows independent?)
  3. effective sample size implied, and matches needed vs FDR family 22,855

Windowing assumption (stated, not hidden):
  rolling horizon = 15 min, evaluated every 5 min, from minute 10 to 85
  -> candidate evaluation points at t = 10,15,20,...,85  (16 points)
  A 'prediction window' = state at t used to predict an event in (t, t+15].
"""
import json
import glob
import os
import math
from collections import defaultdict

import numpy as np

IP = "/home/ubuntu/data/thestatsapi/inplay"
CH = "/home/ubuntu/data/thestatsapi/championship"
OUT = f"{IP}/_recon_step3_power.json"
LEAGUE_PREFIX = {"Championship": "stats", "LaLiga2": "laliga2_stats", "Ligue2": "ligue2_stats"}

EVAL_POINTS = list(range(10, 86, 5))  # 10..85 step 5 -> 16 points
HORIZON = 15


def cumulative_series(events, side_of, var_types, upto):
    c = 0
    for e in events:
        if e.get("minute") is None or e["minute"] > upto:
            continue
        if e.get("type") in var_types and side_of.get((e.get("team") or {}).get("id")) is not None:
            c += 1
    return c


def main():
    v2 = json.load(open(f"{IP}/_recon_step2_result_v2.json"))["results"]
    batch = {b["mid"]: b for b in json.load(open(f"{IP}/_recon_batch.json"))}
    usable = [r for r in v2 if not r.get("quarantined_postfix")]
    print(f"usable (post-fix) matches available for analysis: {len(usable)}")

    # Build per-match minute series of a representative in-play state variable:
    # cumulative shots (attacking intensity proxy) and whether a goal occurs in
    # the next HORIZON minutes (the label for a 'goal in next 15' style target).
    GOAL_TYPES = {"goal", "penalty_scored", "own_goal"}
    per_match_windows = []
    intensity_series = []  # list of arrays: cumulative total shots at eval points
    label_series = []      # list of arrays: goal-in-next-15 (0/1) at eval points
    for r in usable:
        mid = r["mid"]; b = batch[mid]
        tl = json.load(open(f"{IP}/recon_timeline_{mid}.json")).get("data", {})
        events = tl.get("events", [])
        side_of = {b["home_id"]: "home", b["away_id"]: "away"}
        goal_minutes = sorted(e["minute"] for e in events if e.get("type") in GOAL_TYPES and e.get("minute") is not None)
        # cumulative shots (both sides) at each eval point
        SHOT_T = {"shot_on_target", "shot_off_target", "shot_blocked", "goal", "penalty_scored"}
        cum = []
        lab = []
        for t in EVAL_POINTS:
            cum.append(sum(1 for e in events if e.get("type") in SHOT_T and e.get("minute") is not None and e["minute"] <= t))
            lab.append(1 if any(t < gm <= t + HORIZON for gm in goal_minutes) else 0)
        intensity_series.append(np.array(cum, float))
        label_series.append(np.array(lab, float))
        per_match_windows.append(len(EVAL_POINTS))

    n_matches = len(usable)
    windows_per_match = float(np.mean(per_match_windows)) if per_match_windows else 0
    total_windows = int(np.sum(per_match_windows))

    # ── within-match autocorrelation of the state variable (intensity) ──
    # lag-1 autocorr of the per-minute increments; high autocorr => windows not independent
    lag1 = []
    for s in intensity_series:
        d = np.diff(s)  # increments between eval points
        if d.std() > 0 and len(d) > 2:
            a = np.corrcoef(d[:-1], d[1:])[0, 1]
            if np.isfinite(a):
                lag1.append(a)
    mean_lag1_increment = float(np.mean(lag1)) if lag1 else None

    # autocorrelation of the LABEL within match (goal-in-next-15 is highly
    # persistent across adjacent 5-min points because horizons overlap 10/15)
    lab_ac = []
    for s in label_series:
        if s.std() > 0 and len(s) > 2:
            a = np.corrcoef(s[:-1], s[1:])[0, 1]
            if np.isfinite(a):
                lab_ac.append(a)
    mean_label_ac = float(np.mean(lab_ac)) if lab_ac else None

    # ── effective sample size ──
    # Overlapping 15-min horizons stepped by 5 min share 2/3 of their window,
    # so adjacent labels are mechanically correlated. A standard design-effect
    # correction for correlated repeated measures:
    #   n_eff = n_raw / (1 + (m-1)*rho)   [cluster of size m=windows/match]
    m = windows_per_match
    rho = mean_label_ac if (mean_label_ac is not None and mean_label_ac > 0) else 0.5
    design_effect = 1 + (m - 1) * rho
    n_eff_per_match = m / design_effect if design_effect > 0 else 1
    total_n_eff = n_matches * n_eff_per_match

    # ── matches needed vs FDR family 22,855 ──
    # For a two-proportion / logistic effect to survive Bonferroni-ish control
    # at family F, need per-test alpha ~ 0.05/F. Approx required effective-n for a
    # small effect (Cohen's h ~ 0.1) at that alpha, power 0.8:
    F = 22855
    alpha = 0.05 / F
    from math import sqrt
    # z-based approximation
    def z(p):
        # inverse normal via rational approx (Acklam) — adequate here
        import scipy.stats as st
        return float(st.norm.ppf(p))
    z_alpha = z(1 - alpha / 2)
    z_beta = z(0.8)
    for h in (0.1, 0.15, 0.2):
        n_required_eff = ((z_alpha + z_beta) / h) ** 2
        matches_needed = n_required_eff / max(n_eff_per_match, 1e-9)
        print(f"  effect h={h}: required n_eff≈{n_required_eff:.0f} -> matches needed≈{matches_needed:.0f} "
              f"(raw windows≈{matches_needed*m:.0f})")

    result = {
        "note": "ADVISORY ONLY — Step 2 gate failed; not scaling. Answers the "
                "windows-per-match and within-match-independence questions.",
        "windowing_assumption": f"rolling {HORIZON}min horizon, eval every 5min, t=10..85 -> {len(EVAL_POINTS)} points/match",
        "usable_matches_analyzed": n_matches,
        "windows_per_match": windows_per_match,
        "total_raw_windows": total_windows,
        "within_match_label_autocorr_lag1": mean_label_ac,
        "within_match_intensity_increment_autocorr_lag1": mean_lag1_increment,
        "design_effect": design_effect,
        "effective_windows_per_match": round(n_eff_per_match, 2),
        "interpretation": (
            "Overlapping horizons make adjacent windows strongly positively "
            "correlated (label lag-1 autocorr measured). Effective independent "
            "observations per match are FAR fewer than the raw 16 windows: "
            f"~{n_eff_per_match:.1f} effective vs {m:.0f} raw. Treating raw "
            "windows as independent would overstate significance by roughly the "
            f"design effect ({design_effect:.1f}x)."
        ),
        "fdr_family": F,
    }
    json.dump(result, open(OUT, "w"), indent=2)

    print("\n" + "=" * 70)
    print("STEP 3 — SAMPLE-SIZE / INDEPENDENCE ANALYSIS (advisory)")
    print("=" * 70)
    print(f"windows/match (raw): {windows_per_match:.0f}   total raw windows: {total_windows}")
    print(f"within-match label lag-1 autocorr: {mean_label_ac}")
    print(f"within-match intensity-increment lag-1 autocorr: {mean_lag1_increment}")
    print(f"design effect: {design_effect:.2f}  -> effective windows/match: {n_eff_per_match:.2f}")
    print(f"(raw windows overstate independent n by ~{design_effect:.1f}x)")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
