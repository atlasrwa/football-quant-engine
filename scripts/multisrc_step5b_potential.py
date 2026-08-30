"""
STEP 5b reference bar — FootyStats *_potential public projections vs naive.

The brief asks to report FootyStats's own *_potential projections "as a reference
point where available — beating a freely-available public estimate is a concrete bar."

*_potential fields are FootyStats-only. Rather than depend on the cross-source join
(which only covers the Championship 24/25 overlap season), we evaluate the public
projection AS A STANDALONE PREDICTOR on the FootyStats corpus itself: does
o25_potential (goals over 2.5) / cards_potential / corners_o95_potential beat a naive
base-rate baseline on the same over/under outcome? That is the concrete public bar the
new-field candidates would have to clear.

These projections are pre-match values present in the fixture row (look-ahead-free by
construction — FootyStats publishes them before kickoff). BSS vs naive + Brier + ECE,
per league where the FootyStats corpus has the field. Zero API requests (reads the
cached FootyStats discovery corpus).
"""
import glob, json, math
import numpy as np

CORPUS = "/home/ubuntu/data/discovery/corpus"
OUT = "/home/ubuntu/data/results/multisrc_potential_baseline.json"


def load_corpus():
    rows = []
    for f in sorted(glob.glob(f"{CORPUS}/league-matches_*.json")):
        d = json.load(open(f))
        for m in d.get("data", d):
            if m.get("status") == "complete":
                rows.append(m)
    return rows


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# projection field -> (outcome builder, line, prob-interpretation)
def total_goals(m):
    g = num(m.get("overallGoalCount"))
    return g


def total_cards(m):
    ya, yb = num(m.get("team_a_yellow_cards")), num(m.get("team_b_yellow_cards"))
    if ya is None or yb is None:
        return None
    return ya + yb + (num(m.get("team_a_red_cards")) or 0) + (num(m.get("team_b_red_cards")) or 0)


def total_corners(m):
    c = num(m.get("totalCornerCount"))
    return c if (c is not None and m.get("corner_timings_recorded", 0) != 0) else None


# *_potential in FootyStats are AVERAGE projected counts (e.g. cards_potential ~ expected
# total cards), NOT probabilities — o25_potential IS a probability-like 0-100 for over 2.5.
# Handle both: o*_potential are % over that line; cards_potential/corners_potential are
# expected counts -> convert to P(over line) via Poisson survival.
PROJECTIONS = {
    "goals_o25": {"field": "o25_potential", "outcome": total_goals, "line": 2.5, "kind": "pct"},
    "goals_o35": {"field": "o35_potential", "outcome": total_goals, "line": 3.5, "kind": "pct"},
    "cards_pot": {"field": "cards_potential", "outcome": total_cards, "line": 3.5, "kind": "count"},
    "corners_o95": {"field": "corners_o95_potential", "outcome": total_corners, "line": 9.5, "kind": "pct"},
    "corners_pot": {"field": "corners_potential", "outcome": total_corners, "line": 9.5, "kind": "count"},
}


def p_over_from(kind, val, line):
    if val is None:
        return None
    if kind == "pct":
        p = float(val) / 100.0 if val > 1 else float(val)
        return min(max(p, 1e-6), 1 - 1e-6)
    # count -> Poisson survival
    from scipy.stats import poisson
    k = int(math.floor(line))
    return float(1.0 - poisson.cdf(k, float(val)))


def brier_bss_ece(ps, ys):
    ps = np.array(ps); ys = np.array(ys)
    # naive = overall over-rate (single constant; a public projection should beat this)
    naive = ys.mean()
    brier = float(np.mean((ps - ys) ** 2))
    brier_naive = float(np.mean((naive - ys) ** 2))
    bss = float(1 - brier / brier_naive) if brier_naive > 0 else None
    bins = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(ps, bins) - 1, 0, 9)
    ece = 0.0
    for b in range(10):
        m = idx == b
        if m.sum():
            ece += (m.sum() / len(ps)) * abs(ps[m].mean() - ys[m].mean())
    return {"n": int(len(ys)), "over_rate": round(float(naive), 3),
            "brier": round(brier, 4), "bss_vs_naive_pct": round(bss * 100, 2) if bss is not None else None,
            "ece": round(float(ece), 4)}


def main():
    rows = load_corpus()
    print(f"FootyStats corpus complete matches: {len(rows)}")
    out = {}
    for name, cfg in PROJECTIONS.items():
        ps, ys = [], []
        for m in rows:
            v = num(m.get(cfg["field"]))
            y = cfg["outcome"](m)
            if v is None or y is None:
                continue
            p = p_over_from(cfg["kind"], v, cfg["line"])
            if p is None:
                continue
            ps.append(p); ys.append(1 if y > cfg["line"] else 0)
        if len(ys) < 100:
            out[name] = {"status": f"insufficient (n={len(ys)})"}
            continue
        out[name] = {"field": cfg["field"], "line": cfg["line"], **brier_bss_ece(ps, ys)}

    json.dump(out, open(OUT, "w"), indent=2)
    print("\n" + "=" * 70)
    print("FootyStats *_potential public projections vs naive (reference bar)")
    print("=" * 70)
    for name, r in out.items():
        if "bss_vs_naive_pct" in r:
            print(f"  {name:12s} ({r['field']:22s} @{r['line']}): "
                  f"BSS={r['bss_vs_naive_pct']}%  Brier={r['brier']} ECE={r['ece']} n={r['n']}")
        else:
            print(f"  {name:12s}: {r.get('status')}")
    print(f"\nsaved: {OUT}")


if __name__ == "__main__":
    main()
