"""
Family-transfer test — consolidated report + BH multiple-testing correction.

Reads the six per-league result JSONs (data/results/family_transfer_<tag>.json),
assembles the side-by-side family comparison, applies Benjamini-Hochberg to the
PRE-REGISTERED family of primary validation tests, and answers the three patterns
(tier / country / neither). Zero API calls.

Pre-registered family (stated before running): for the 3 NEW top-flight leagues
x {corners, cards} primary BSS-vs-naive tests = 6 hypotheses. BH at q=0.10.
Bootstrap seed 20260902 (in the per-league runs). Within-league only; the 2nd-tier
partners are reported alongside for the family comparison but the NEW-league family
is the 6 top-flight cells (the second tiers were already validated in prior work).
"""
import json
import numpy as np

RES = "/home/ubuntu/data/results"
FAMILIES = [
    ("England", "epl", "champ"),
    ("Spain", "laliga", "laliga2"),
    ("France", "ligue1", "ligue2"),
]
TIER = {"epl": 1, "champ": 2, "laliga": 1, "laliga2": 2, "ligue1": 1, "ligue2": 2}
DISPLAY = {"epl": "EPL", "champ": "Championship", "laliga": "La Liga",
           "laliga2": "La Liga 2", "ligue1": "Ligue 1", "ligue2": "Ligue 2"}


def load(tag):
    with open(f"{RES}/family_transfer_{tag}.json") as f:
        return json.load(f)


def bss_ci_p(cell_line):
    """Approximate a two-sided p for BSS>0 from the bootstrap CI (normal approx on
    the 95% CI half-width). Returns (bss, ci_lo, ci_hi, p_approx)."""
    bss = cell_line["bss_vs_naive_pct"]
    ci = cell_line.get("bss_ci95_pct") or {}
    lo, hi = ci.get("ci_low_pct"), ci.get("ci_high_pct")
    if bss is None or lo is None or hi is None:
        return bss, lo, hi, None
    se = (hi - lo) / (2 * 1.96) if hi > lo else 1e-9
    from math import erf, sqrt
    z = bss / se if se > 0 else 0.0
    p = 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))
    return bss, lo, hi, p


def benjamini_hochberg(pvals, q=0.10):
    """Return boolean reject list in original order (BH step-up)."""
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx)
    order = sorted(idx, key=lambda i: pvals[i])
    reject = [False] * len(pvals)
    kmax = 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= (rank / m) * q:
            kmax = rank
    for rank, i in enumerate(order, start=1):
        if rank <= kmax:
            reject[i] = True
    return reject


def main():
    data = {tag: load(tag) for _, top, bot in FAMILIES for tag in (top, bot)}

    # ---- Assemble primary family: 3 NEW top flights x {corners@9.5, cards@3.5} ----
    primary = []  # (label, tag, market, bss, lo, hi, p)
    for _, top, _ in FAMILIES:
        d = data[top]
        for market, key, line in (("corners", "corners_validation", "9.5"),
                                   ("cards", "cards_validation", "3.5")):
            cell = d.get(key, {}).get("by_line", {}).get(line, {})
            if cell.get("status") == "insufficient" or "bss_vs_naive_pct" not in cell:
                primary.append((DISPLAY[top], top, market, None, None, None, None))
                continue
            bss, lo, hi, p = bss_ci_p(cell)
            primary.append((DISPLAY[top], top, market, bss, lo, hi, p))

    pvals = [row[6] for row in primary]
    rej = benjamini_hochberg(pvals, q=0.10)

    print("=" * 92)
    print("LEAGUE-FAMILY TRANSFER — CONSOLIDATED REPORT")
    print("=" * 92)
    print("Pre-registered family = 3 new top flights x {corners@9.5, cards@3.5} = 6 primary")
    print("BSS-vs-naive tests. BH at q=0.10. Bootstrap seed 20260902. Within-league only.")
    print()

    # ---- Full side-by-side table (both tiers) ----
    hdr = f"{'League':13s} {'Tier':4s} {'Market':7s} {'BSS%':>7s} {'CI95%':>16s} {'ECE':>6s} {'DirAcc':>7s} {'Home':>6s} {'n':>5s}  Verdict"
    print(hdr); print("-" * len(hdr))
    for fam, top, bot in FAMILIES:
        for tag in (top, bot):
            d = data[tag]
            marginal = d.get("features_marginal")
            stopped = d.get("stopped")
            for market, key, line in (("corners", "corners_validation", "9.5"),
                                      ("cards", "cards_validation", "3.5")):
                if stopped:
                    print(f"{DISPLAY[tag]:13s} {TIER[tag]:<4d} {market:7s} {'--':>7s} {'(stopped)':>16s} "
                          f"{'--':>6s} {'--':>7s} {'--':>6s} {'--':>5s}  feature-check hard fail")
                    continue
                cell = d.get(key, {}).get("by_line", {}).get(line, {})
                dirc = d.get("directional", {}).get(market, {})
                if cell.get("status") == "insufficient" or "bss_vs_naive_pct" not in cell:
                    print(f"{DISPLAY[tag]:13s} {TIER[tag]:<4d} {market:7s} insufficient")
                    continue
                bss = cell["bss_vs_naive_pct"]
                ci = cell.get("bss_ci95_pct") or {}
                lo, hi = ci.get("ci_low_pct"), ci.get("ci_high_pct")
                ece = cell["ece"]
                acc = dirc.get("model_accuracy"); home = dirc.get("home_baseline"); nn = cell["n"]
                skill = (lo is not None and lo > 0)
                verdict = "SKILL (CI>0)" if skill else "no skill (CI spans 0)"
                if marginal:
                    verdict += " [features marginal]"
                cistr = f"[{lo:+.2f},{hi:+.2f}]" if lo is not None else "n/a"
                print(f"{DISPLAY[tag]:13s} {TIER[tag]:<4d} {market:7s} {bss:>7.2f} {cistr:>16s} "
                      f"{ece:>6.3f} {(acc if acc is not None else 0):>7.3f} {(home if home is not None else 0):>6.3f} {nn:>5d}  {verdict}")
        print()

    # ---- BH result on the primary family ----
    print("=" * 92)
    print("BH MULTIPLE-TESTING (primary family of 6, q=0.10) — top-flight BSS>0 tests")
    print("=" * 92)
    for (label, tag, market, bss, lo, hi, p), r in zip(primary, rej):
        ps = "n/a" if p is None else f"{p:.4f}"
        print(f"  {label:10s} {market:7s}: BSS={('n/a' if bss is None else format(bss,'+.2f')+'%'):>8s} "
              f"CI[{('n/a' if lo is None else format(lo,'+.2f'))},{('n/a' if hi is None else format(hi,'+.2f'))}] "
              f"p={ps}  BH_reject={r}")
    print()

    # ---- Cards persistence + field coverage summary ----
    print("=" * 92)
    print("CARDS PERSISTENCE (built-in check) + xG COVERAGE per league")
    print("=" * 92)
    for fam, top, bot in FAMILIES:
        for tag in (top, bot):
            d = data[tag]
            c2 = d["feature_checks"]["check2_known_signal"]
            fp = d["field_population"]
            xg_pops = [fp[s]["fields"]["expected_goals"]["pct"] for s in fp
                       if fp[s]["fields"]["expected_goals"]["pct"] is not None]
            xg_pop = round(np.mean(xg_pops), 1) if xg_pops else None
            print(f"  {DISPLAY[tag]:13s} (tier {TIER[tag]}): cards_persistence={c2['cards_persistence']:+.3f}  "
                  f"anchor={c2['known_signal_anchor']}  xg_coverage={xg_pop}%")
    print()


if __name__ == "__main__":
    main()
