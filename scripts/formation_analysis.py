"""
FORMATION ANALYSIS (Steps 3-6) — descriptive, offline, zero API.

Joins cached lineups (data/thestatsapi/championship/lineups_<mid>.json) to cached
match outcomes (via multisrc_corpus adapted dicts) and runs:

  Step 3  Characterisation: per-league formation distribution & concentration;
          both-teams-formation-present rate; per-team formation stability (modal
          share) -> viability of a PRIOR-ONLY modal-formation proxy.

  Step 4  Descriptive formation-matchup analysis: for each (home_formation x
          away_formation) pairing, observed averages (with n and a MIN_PAIRING gate)
          for corners / fouls / cards / SOT / blocked shots / clearances / crosses,
          TOTAL and PER SIDE. Plus the more-robust MARGINAL per-formation averages.

  Step 5  Team-quality control: WITHIN-TEAM formation switches. When the SAME team
          plays formation A vs formation B, does its own per-match outcome change?
          Paired within-team contrast removes the team-quality confound.

  Step 6  Discipline: PER LEAGUE (never pooled-only); fresh BH FDR family across
          every (formation-contrast x outcome x league) cell actually tested;
          bootstrap CIs with a FIXED seed; small-n gate.

Outcomes are read PER SIDE from the adapted corpus dict:
  corners  = _rich['corner_kicks']            (home, away)
  sot      = _rich['shots_on_target']         (home, away)
  blocks   = _rich['blocked_shots']           (home, away)
  clear    = _rich['clearances']              (home, away)
  crosses  = _rich['accurate_crosses']        (home, away)
  fouls    = team_a_fouls / team_b_fouls
  cards    = team_a_yellow+red / team_b_yellow+red
"""
import sys, os, json, glob
from collections import defaultdict, Counter
import numpy as np

sys.path.insert(0, "/home/ubuntu/scripts")
import multisrc_corpus as corpus

SEED = 20260902
STABILITY_SEEDS = [1, 7, 42]   # separate seeds; a finding must hold across all
MIN_PAIRING = 30          # min matches for a pairing average to be shown (else "insufficient")
MIN_MARGINAL = 40         # min matches for a marginal per-formation average
MIN_SWITCH_TEAMS = 8      # min teams contributing to a within-team switch contrast
MIN_SWITCH_N = 30         # min matches per formation-arm within the switch contrast
BH_Q = 0.10
LINEUP_DIR = "/home/ubuntu/data/thestatsapi/championship"

# leagues used for the analysis (all six pulled; primary three flagged)
PRIMARY = ["champ", "laliga2", "ligue2"]
TOPFLIGHT = ["epl", "laliga", "ligue1"]
LEAGUES = PRIMARY + TOPFLIGHT

OUTCOMES = ["corners", "fouls", "cards", "sot", "blocked_shots", "clearances", "crosses"]


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f == -1 else f


def _pair(m, key):
    p = (m.get("_rich") or {}).get(key)
    if not p or p[0] is None or p[1] is None:
        return None
    a, b = _num(p[0]), _num(p[1])
    return None if (a is None or b is None) else (a, b)


def per_side_outcomes(m):
    """Return dict outcome -> (home_value, away_value) or None if unavailable."""
    out = {}
    out["corners"] = _pair(m, "corner_kicks")
    out["sot"] = _pair(m, "shots_on_target")
    out["blocked_shots"] = _pair(m, "blocked_shots")
    out["clearances"] = _pair(m, "clearances")
    out["crosses"] = _pair(m, "accurate_crosses")
    fa, fb = _num(m.get("team_a_fouls")), _num(m.get("team_b_fouls"))
    out["fouls"] = (fa, fb) if (fa is not None and fb is not None) else None
    ya, yb = _num(m.get("team_a_yellow_cards")), _num(m.get("team_b_yellow_cards"))
    ra = _num(m.get("team_a_red_cards")) or 0.0
    rb = _num(m.get("team_b_red_cards")) or 0.0
    out["cards"] = ((ya + ra, yb + rb) if (ya is not None and yb is not None) else None)
    return out


def load_lineup(mid):
    p = f"{LINEUP_DIR}/lineups_{mid}.json"
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p)).get("data")
    except Exception:
        return None
    if not d:
        return None
    hf = (d.get("home") or {}).get("formation")
    af = (d.get("away") or {}).get("formation")
    return {"home_formation": hf, "away_formation": af,
            "confirmed": d.get("confirmed"),
            "home_id": (d.get("home") or {}).get("id"),
            "away_id": (d.get("away") or {}).get("id")}


def load_joined(tag):
    """Return list of joined records for a league: matches that have BOTH a cached
    lineup with both formations AND outcomes. Each record carries per-side outcomes,
    home/away formation, and team ids + date for the within-team analysis."""
    recs = []
    seen = set()
    for sid in corpus.LEAGUES[tag]["seasons"]:
        try:
            ms = corpus.load_season(tag, sid)
        except FileNotFoundError:
            continue
        for m in ms:
            mid = m.get("match_id")
            if mid in seen:
                continue
            lu = load_lineup(mid)
            if lu is None:
                continue
            recs.append({
                "match_id": mid, "date_unix": m.get("date_unix", 0),
                "home_id": m.get("home_id"), "away_id": m.get("away_id"),
                "home_formation": lu["home_formation"],
                "away_formation": lu["away_formation"],
                "confirmed": lu["confirmed"],
                "outcomes": per_side_outcomes(m),
            })
            seen.add(mid)
    return recs


# ────────────────────────────────────────────────────────────────────────────
# Step 3 — characterisation
# ────────────────────────────────────────────────────────────────────────────
def characterise(tag, recs):
    n = len(recs)
    both = sum(1 for r in recs if r["home_formation"] and r["away_formation"])
    formations = Counter()
    for r in recs:
        for side in ("home_formation", "away_formation"):
            if r[side]:
                formations[r[side]] += 1
    total_slots = sum(formations.values())
    # concentration: share of top-3 formations (HHI too)
    shares = np.array(sorted(formations.values(), reverse=True)) / total_slots if total_slots else np.array([])
    hhi = float(np.sum(shares ** 2)) if len(shares) else 0.0
    top3 = float(shares[:3].sum()) if len(shares) else 0.0

    # per-team stability: modal formation share over that team's matches (both sides)
    team_forms = defaultdict(list)
    for r in recs:
        if r["home_formation"]:
            team_forms[r["home_id"]].append(r["home_formation"])
        if r["away_formation"]:
            team_forms[r["away_id"]].append(r["away_formation"])
    modal_shares = []
    switch_teams = 0
    for tid, fl in team_forms.items():
        if len(fl) < 4:
            continue
        c = Counter(fl)
        modal = c.most_common(1)[0][1]
        modal_shares.append(modal / len(fl))
        if len(c) >= 2 and (len(fl) - modal) >= 3:  # switches enough to study within-team
            switch_teams += 1
    modal_shares = np.array(modal_shares) if modal_shares else np.array([0.0])
    return {
        "n_matches": n,
        "both_formations_present": both,
        "both_present_rate": round(both / n, 4) if n else 0.0,
        "n_distinct_formations": len(formations),
        "top3_share": round(top3, 4),
        "hhi": round(hhi, 4),
        "formation_counts": dict(formations.most_common()),
        "team_modal_share_median": round(float(np.median(modal_shares)), 4),
        "team_modal_share_mean": round(float(np.mean(modal_shares)), 4),
        "n_teams_ge4_matches": int(np.sum([1 for fl in team_forms.values() if len(fl) >= 4])),
        "n_teams_switch_enough": switch_teams,
    }


# ────────────────────────────────────────────────────────────────────────────
# Step 4 — pairing & marginal averages
# ────────────────────────────────────────────────────────────────────────────
def pairing_table(recs):
    """(home_formation, away_formation) -> per-outcome lists of (home,away,total)."""
    pair = defaultdict(lambda: defaultdict(list))  # (hf,af) -> outcome -> [(h,a,tot)]
    for r in recs:
        hf, af = r["home_formation"], r["away_formation"]
        if not hf or not af:
            continue
        for oc, val in r["outcomes"].items():
            if val is None:
                continue
            h, a = val
            pair[(hf, af)][oc].append((h, a, h + a))
    return pair


def marginal_table(recs):
    """formation -> outcome -> list of that team's OWN value when playing that shape
    (home side uses home value, away side uses away value)."""
    marg = defaultdict(lambda: defaultdict(list))
    for r in recs:
        hf, af = r["home_formation"], r["away_formation"]
        for oc, val in r["outcomes"].items():
            if val is None:
                continue
            h, a = val
            if hf:
                marg[hf][oc].append(h)
            if af:
                marg[af][oc].append(a)
    return marg


def summarise_pairings(pair):
    rows = []
    for (hf, af), ocs in pair.items():
        # n for the pairing = max matches across outcomes (corners usually present)
        n = max((len(v) for v in ocs.values()), default=0)
        row = {"home_formation": hf, "away_formation": af, "n": n,
               "sufficient": n >= MIN_PAIRING, "outcomes": {}}
        for oc in OUTCOMES:
            vals = ocs.get(oc, [])
            if len(vals) >= MIN_PAIRING:
                arr = np.array(vals, float)
                row["outcomes"][oc] = {
                    "n": len(vals),
                    "home_mean": round(float(arr[:, 0].mean()), 3),
                    "away_mean": round(float(arr[:, 1].mean()), 3),
                    "total_mean": round(float(arr[:, 2].mean()), 3),
                }
            else:
                row["outcomes"][oc] = {"n": len(vals), "insufficient": True}
        rows.append(row)
    rows.sort(key=lambda r: r["n"], reverse=True)
    return rows


def summarise_marginals(marg):
    rows = []
    for f, ocs in marg.items():
        n = max((len(v) for v in ocs.values()), default=0)
        row = {"formation": f, "n": n, "sufficient": n >= MIN_MARGINAL, "outcomes": {}}
        for oc in OUTCOMES:
            vals = ocs.get(oc, [])
            if len(vals) >= MIN_MARGINAL:
                arr = np.array(vals, float)
                row["outcomes"][oc] = {"n": len(vals),
                                       "own_mean": round(float(arr.mean()), 3),
                                       "own_sd": round(float(arr.std()), 3)}
            else:
                row["outcomes"][oc] = {"n": len(vals), "insufficient": True}
        rows.append(row)
    rows.sort(key=lambda r: r["n"], reverse=True)
    return rows


# ────────────────────────────────────────────────────────────────────────────
# Step 5 — within-team formation-switch control (team quality removed)
# ────────────────────────────────────────────────────────────────────────────
def within_team_contrast(recs, formation_a, formation_b, outcome, rng, n_boot=10000):
    """Paired within-team contrast: for each team that played BOTH formation_a and
    formation_b (as home or away, using its OWN value), compute the team's mean
    outcome under A minus under B, then average over teams (each team weighted
    equally). Bootstrap CI over teams. This removes cross-team quality differences
    because every difference is within one team."""
    team_vals = defaultdict(lambda: {"a": [], "b": []})
    for r in recs:
        for side, own_idx in (("home_formation", 0), ("away_formation", 1)):
            f = r[side]
            if f not in (formation_a, formation_b):
                continue
            val = r["outcomes"].get(outcome)
            if val is None:
                continue
            tid = r["home_id"] if side == "home_formation" else r["away_id"]
            own = val[own_idx]
            team_vals[tid]["a" if f == formation_a else "b"].append(own)
    # teams with enough of BOTH arms
    diffs = []
    na = nb = 0
    used_teams = 0
    for tid, d in team_vals.items():
        if len(d["a"]) >= 2 and len(d["b"]) >= 2:
            diffs.append(np.mean(d["a"]) - np.mean(d["b"]))
            na += len(d["a"]); nb += len(d["b"])
            used_teams += 1
    if used_teams < MIN_SWITCH_TEAMS or na < MIN_SWITCH_N or nb < MIN_SWITCH_N:
        return None
    diffs = np.array(diffs, float)
    point = float(diffs.mean())
    boot = []
    for _ in range(n_boot):
        s = rng.choice(len(diffs), len(diffs), replace=True)
        boot.append(diffs[s].mean())
    boot = np.sort(np.array(boot))
    lo = float(boot[int(0.025 * len(boot))]); hi = float(boot[int(0.975 * len(boot))])
    p_two = 2 * min((boot <= 0).mean(), (boot >= 0).mean())
    return {"formation_a": formation_a, "formation_b": formation_b, "outcome": outcome,
            "n_teams": used_teams, "n_a": na, "n_b": nb,
            "within_team_diff": round(point, 4),
            "ci95": [round(lo, 4), round(hi, 4)], "p": round(float(p_two), 4)}


def bh_reject(pvals, q=BH_Q):
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx)
    if m == 0:
        return [False] * len(pvals)
    order = sorted(idx, key=lambda i: pvals[i]); kmax = 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= (rank / m) * q:
            kmax = rank
    rej = [False] * len(pvals)
    for rank, i in enumerate(order, 1):
        if rank <= kmax:
            rej[i] = True
    return rej


def main():
    rng = np.random.default_rng(SEED)
    print("=" * 80)
    print("FORMATION ANALYSIS — descriptive, offline (Steps 3-6)")
    print(f"seed={SEED}; MIN_PAIRING={MIN_PAIRING}; MIN_MARGINAL={MIN_MARGINAL}; "
          f"switch: >={MIN_SWITCH_TEAMS} teams & >={MIN_SWITCH_N}/arm; BH q={BH_Q}")
    print("=" * 80)

    report = {"seed": SEED, "min_pairing": MIN_PAIRING, "min_marginal": MIN_MARGINAL,
              "leagues": {}}
    league_recs = {}
    for tag in LEAGUES:
        recs = load_joined(tag)
        league_recs[tag] = recs
        disp = corpus.LEAGUES[tag]["display"]
        ch = characterise(tag, recs)
        report["leagues"][tag] = {"display": disp, "characterisation": ch}
        print(f"\n=== {disp} ({tag}) — joined matches with lineups: {ch['n_matches']} ===")
        print(f"  both formations present: {ch['both_formations_present']} "
              f"({ch['both_present_rate']*100:.1f}%)")
        print(f"  distinct formations: {ch['n_distinct_formations']}  "
              f"top3 share: {ch['top3_share']*100:.1f}%  HHI: {ch['hhi']:.3f}")
        top = list(ch["formation_counts"].items())[:6]
        print("  most common:", ", ".join(f"{f}={c}" for f, c in top))
        print(f"  team modal-formation share: median {ch['team_modal_share_median']*100:.1f}%  "
              f"mean {ch['team_modal_share_mean']*100:.1f}%  "
              f"(teams>=4 matches: {ch['n_teams_ge4_matches']}, "
              f"switch-enough: {ch['n_teams_switch_enough']})")

    # Step 4 — pairings & marginals per league
    for tag in LEAGUES:
        recs = league_recs[tag]
        disp = corpus.LEAGUES[tag]["display"]
        pair_rows = summarise_pairings(pairing_table(recs))
        marg_rows = summarise_marginals(marginal_table(recs))
        report["leagues"][tag]["pairings"] = pair_rows
        report["leagues"][tag]["marginals"] = marg_rows
        suff_pairs = [r for r in pair_rows if r["sufficient"]]
        print(f"\n--- {disp}: {len(pair_rows)} distinct pairings, "
              f"{len(suff_pairs)} with n>={MIN_PAIRING} ---")
        for r in suff_pairs[:6]:
            c = r["outcomes"].get("corners", {})
            cd = r["outcomes"].get("cards", {})
            print(f"    {r['home_formation']} vs {r['away_formation']} n={r['n']}: "
                  f"corners tot={c.get('total_mean')} (H{c.get('home_mean')}/A{c.get('away_mean')}) "
                  f"cards tot={cd.get('total_mean')}")

    # Step 5 & 6 — within-team switch contrasts, per league, with a shared BH family
    print("\n" + "=" * 80)
    print("STEP 5 — WITHIN-TEAM formation-switch contrasts (team quality controlled)")
    print("=" * 80)
    family = []  # (tag, contrast, outcome, result)
    for tag in LEAGUES:
        recs = league_recs[tag]
        ch = report["leagues"][tag]["characterisation"]
        # candidate formations: the top-K most common in this league (>= a floor)
        fc = ch["formation_counts"]
        common = [f for f, c in list(fc.items()) if c >= 60][:5]
        contrasts = [(common[i], common[j]) for i in range(len(common))
                     for j in range(i + 1, len(common))]
        for (fa, fb) in contrasts:
            for oc in OUTCOMES:
                res = within_team_contrast(recs, fa, fb, oc, rng)
                if res is not None:
                    family.append((tag, f"{fa}_vs_{fb}", oc, res))
    # BH across the whole family actually tested
    pvals = [res["p"] for (_, _, _, res) in family]
    rej = bh_reject(pvals, q=BH_Q)
    fam_size = len(family)
    survivors = []
    for (tag, contrast, oc, res), r in zip(family, rej):
        res["bh_reject"] = bool(r)
        ci = res["ci95"]
        res["significant_after_bh"] = bool(r and (ci[0] > 0 or ci[1] < 0))
        if res["significant_after_bh"]:
            survivors.append((tag, contrast, oc, res))
    report["within_team_family_size"] = fam_size
    report["within_team_family"] = [
        {"league": t, "contrast": c, "outcome": o, **res} for (t, c, o, res) in family]
    report["within_team_survivors"] = [
        {"league": t, "contrast": c, "outcome": o, **res} for (t, c, o, res) in survivors]

    print(f"  within-team contrasts tested (FDR family): {fam_size}")
    print(f"  BH-significant (CI excludes 0 after BH q={BH_Q}): {len(survivors)}")
    for (tag, contrast, oc, res) in family:
        disp = corpus.LEAGUES[tag]["display"]
        star = " *SURVIVES-BH*" if res["significant_after_bh"] else ""
        print(f"    {disp:12s} {contrast:20s} {oc:14s} "
              f"diff={res['within_team_diff']:+.3f} CI[{res['ci95'][0]:+.3f},{res['ci95'][1]:+.3f}] "
              f"p={res['p']} teams={res['n_teams']}{star}")

    verdict = ("SIGNAL: >=1 within-team formation contrast survives BH"
               if survivors else
               "NULL: no within-team formation contrast survives BH — formation "
               "effects do not persist once team identity is controlled for")
    report["verdict_within_team"] = verdict
    print("\nVERDICT (within-team, team-quality controlled):", verdict)

    # ── seed stability for survivors (prior runs produced seed-fragile findings) ──
    if survivors:
        print("\n" + "-" * 80)
        print("SEED STABILITY of BH survivors (must hold across all stability seeds)")
        print("-" * 80)
        stab_report = {}
        for (tag, contrast, oc, res) in survivors:
            fa, fb = contrast.split("_vs_")
            recs = league_recs[tag]
            per_seed = []
            for sd in STABILITY_SEEDS:
                r2 = within_team_contrast(recs, fa, fb, oc, np.random.default_rng(sd))
                if r2 is None:
                    per_seed.append(None); continue
                ci = r2["ci95"]
                per_seed.append({"seed": sd, "diff": r2["within_team_diff"],
                                 "ci95": ci, "p": r2["p"],
                                 "excludes_0": bool(ci[0] > 0 or ci[1] < 0)})
            n_hold = sum(1 for s in per_seed if s and s["excludes_0"])
            disp = corpus.LEAGUES[tag]["display"]
            key = f"{tag}/{contrast}/{oc}"
            stab_report[key] = {"primary_seed": SEED, "stability_seeds": STABILITY_SEEDS,
                                "n_stability_seeds_ci_excludes_0": n_hold,
                                "per_seed": per_seed}
            print(f"  {disp} {contrast} {oc}: CI-excludes-0 at "
                  f"{n_hold}/{len(STABILITY_SEEDS)} stability seeds "
                  f"(+ primary) -> {'STABLE' if n_hold == len(STABILITY_SEEDS) else 'SEED-FRAGILE'}")
        report["within_team_seed_stability"] = stab_report

    json.dump(report, open("/home/ubuntu/data/results/formation_analysis.json", "w"), indent=2)
    print("\nsaved -> data/results/formation_analysis.json")


if __name__ == "__main__":
    main()
