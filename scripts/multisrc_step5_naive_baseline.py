"""
STEP 5 (naive-baseline variant) — do the ~24 new fields contain signal vs a NAIVE
baseline? ODDS OUT OF SCOPE (market comparison already answered in F013/F018; this
run isolates the signal-vs-naive question the brief specifies).

Zero API requests — reuses cached stats + the SAME walk-forward machinery/models as
the discovery run (ev_test_metrics_vs_bet365 + championship_step34_analysis). NO
refit/retune/substitution of the 7 metrics; they are re-scored as-is.

For each scored predictor (the 7 existing metrics + the notable new-field candidates,
i.e. the discovery near-misses), on its over/under line(s):
  - convert Poisson predicted_lambda -> P(count > line)  [survival]
  - binary outcome = (actual_count > line)
  - Brier, BSS vs naive (naive = point-in-time expanding base rate of the over),
    ECE (10-bin)
Reported per (league, target, line). Then Step-5b:
  - best NEW-FIELD candidate vs best FOOTYSTATS-derived metric on the same
    (league,target) by naive-BSS
  - vs FootyStats *_potential public projection where the FS join exists
    (Championship overlap season only) as a reference bar.

Everything is a screening/desirability readout: 0 candidates survived cumulative FDR
(Step 4), so NONE of this is a validated finding — it quantifies whether the new
fields even move BSS above naive.
"""
import os, sys, json, math
from collections import defaultdict
import numpy as np
from scipy.stats import poisson

sys.path.insert(0, os.path.dirname(__file__))
import ev_test_metrics_vs_bet365 as ev
import multisrc_corpus as corpus
import championship_step34_analysis as c34
import multisrc_step4_discovery as disc

CACHE = "/home/ubuntu/data/thestatsapi/championship"
OUT = "/home/ubuntu/data/results/multisrc_naive_baseline.json"

# Lines per target (same as discovery)
TARGET_LINES = {"total_cards": [3.5, 4.5], "total_goals": [2.5, 3.5], "total_corners": [9.5, 10.5]}


def p_over(lmbda, line):
    """P(count > line) for integer line x.5 under Poisson(lambda)."""
    k = int(math.floor(line))
    return float(1.0 - poisson.cdf(k, lmbda))


def brier_bss_ece(preds, line):
    """Given preds [{predicted_lambda, actual_count, date_unix}], compute Brier, naive
    baseline Brier (expanding point-in-time over-rate), BSS, and ECE for the over@line."""
    preds = sorted(preds, key=lambda p: p["date_unix"])
    ps, ys = [], []
    naive_ps = []
    over_running = 0
    n_running = 0
    for p in preds:
        y = 1 if p["actual_count"] > line else 0
        # naive = expanding base rate BEFORE this match (point-in-time); seed 0.5
        naive = (over_running / n_running) if n_running >= 20 else 0.5
        ps.append(p_over(p["predicted_lambda"], line))
        ys.append(y)
        naive_ps.append(naive)
        over_running += y
        n_running += 1
    ps = np.array(ps); ys = np.array(ys); naive_ps = np.array(naive_ps)
    # only evaluate where naive is defined by real base rate (drop seed region)
    mask = np.arange(len(ys)) >= 20
    if mask.sum() < 30:
        return None
    ps, ys, naive_ps = ps[mask], ys[mask], naive_ps[mask]
    brier = float(np.mean((ps - ys) ** 2))
    brier_naive = float(np.mean((naive_ps - ys) ** 2))
    bss = float(1 - brier / brier_naive) if brier_naive > 0 else None
    # ECE 10-bin
    bins = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(ps, bins) - 1, 0, 9)
    ece = 0.0
    for b in range(10):
        m = idx == b
        if m.sum() == 0:
            continue
        conf = ps[m].mean(); acc = ys[m].mean()
        ece += (m.sum() / len(ps)) * abs(conf - acc)
    return {"n": int(len(ys)), "over_rate": float(ys.mean()),
            "brier": round(brier, 4), "brier_naive": round(brier_naive, 4),
            "bss_vs_naive_pct": round(bss * 100, 2) if bss is not None else None,
            "ece": round(float(ece), 4)}


def load_matches(lg):
    ms = []
    for sid in corpus.LEAGUES[lg]["seasons"]:
        try:
            ms.extend(corpus.load_season(lg, sid))
        except Exception:
            pass
    ms = [m for m in ms if m.get("date_unix")]
    ms.sort(key=lambda m: m["date_unix"])
    return ms


def parse_candidate_features(fname):
    """'home:tacklesw10+away:foulsw10' -> [('home', field, w), ('away', field, w)]
    with kind inferred (named vs rich) from disc.NAMED_FIELDS."""
    feats = []
    for part in fname.split("+"):
        side, rest = part.split(":")
        # rest like 'tacklesw10' -> field 'tackles', window 10
        import re
        m = re.match(r"(.+?)w(\d+)$", rest)
        field, w = m.group(1), int(m.group(2))
        kind = "named" if field in disc.NAMED_FIELDS else "rich"
        feats.append((side, kind, field, w))
    return feats


def score_candidate(fname, target, matches, team_hist, rich_idx):
    cand = {"features": parse_candidate_features(fname)}
    return disc.walk_forward_candidate(cand, matches, target, team_hist, rich_idx)


def main():
    disc_res = json.load(open("/home/ubuntu/data/results/multisrc_discovery.json"))
    gate = disc.load_gate()

    out = {"scope": "naive-baseline only; odds out of scope (market answered in F013/F018)",
           "note": "0 candidates survived cumulative FDR (Step 4); these are signal-vs-naive "
                   "readouts, NOT validated findings.",
           "per_metric": {}, "per_candidate": {}, "step5b": {}}

    TARGET_OUTCOME = {"cards": "total_cards", "goals": "total_goals", "corners": "total_corners"}

    for lg in corpus.LEAGUES:
        matches = load_matches(lg)
        th = ev.build_team_histories(matches)
        rich = c34.build_rich_team_index(matches)
        out["per_metric"][lg] = {}
        out["per_candidate"][lg] = {}

        # ---- the 7 existing metrics (no refit) ----
        for mid, mdef in ev.METRICS.items():
            preds = c34.wf_predict_existing(mdef, matches, th)
            if not preds:
                out["per_metric"][lg][mid] = {"status": "insufficient"}
                continue
            target = mdef["target"]
            per_line = {}
            for line in TARGET_LINES.get(target, []):
                r = brier_bss_ece(preds, line)
                if r:
                    per_line[str(line)] = r
            out["per_metric"][lg][mid] = {"target": target, "by_line": per_line}

        # ---- notable new-field candidates: the discovery near-misses in this league ----
        near = [nm for nm in disc_res.get("near_misses", []) if nm["league"] == disc_league(lg)]
        # also include the best candidate per gate-passing target from the full cell list
        for lg_key, cell_lg in disc_res.get("leagues", {}).items():
            if lg_key != disc_league(lg):
                continue
            for t, cell in cell_lg.get("targets", {}).items():
                if not cell.get("searched"):
                    continue
                for c in cell.get("candidates", [])[:3]:  # top-3 by screen p
                    near.append({"league": lg_key, "target": t, "features": c["features"]})
        seen = set()
        for nm in near:
            key = (nm["target"], nm["features"])
            if key in seen:
                continue
            seen.add(key)
            target = TARGET_OUTCOME[nm["target"]]
            preds = score_candidate(nm["features"], target, matches, th, rich)
            if not preds:
                continue
            per_line = {}
            for line in TARGET_LINES.get(target, []):
                r = brier_bss_ece(preds, line)
                if r:
                    per_line[str(line)] = r
            out["per_candidate"][lg].setdefault(nm["target"], {})[nm["features"]] = {"by_line": per_line}

    # ---- Step 5b: new-field vs best FootyStats metric, per gate-passing cell ----
    # FootyStats-derived metrics among the 7: those using named FootyStats-schema fields
    # (yellow_cards/fouls/shotsOnTarget/xg). New-field = rich TheStatsAPI fields.
    step5b = {}
    for lg in corpus.LEAGUES:
        for t in ("cards", "goals", "corners"):
            if not disc.gate_passed(gate, disc_league(lg), t):
                continue
            target = TARGET_OUTCOME[t]
            # best existing (FootyStats-derived) metric on this target/league by BSS@first line
            line0 = TARGET_LINES[target][0]
            best_fs = None
            for mid, r in out["per_metric"][lg].items():
                if r.get("target") != target:
                    continue
                bl = r.get("by_line", {}).get(str(line0))
                if bl and bl["bss_vs_naive_pct"] is not None:
                    if best_fs is None or bl["bss_vs_naive_pct"] > best_fs[1]:
                        best_fs = (mid, bl["bss_vs_naive_pct"])
            # best new-field candidate on same target/league by BSS@first line
            best_new = None
            for feats, r in out["per_candidate"][lg].get(t, {}).items():
                bl = r.get("by_line", {}).get(str(line0))
                if bl and bl["bss_vs_naive_pct"] is not None:
                    # new-field = uses a rich field
                    is_new = any(f not in disc.NAMED_FIELDS for (_, k, f, w) in parse_candidate_features(feats))
                    if is_new and (best_new is None or bl["bss_vs_naive_pct"] > best_new[1]):
                        best_new = (feats, bl["bss_vs_naive_pct"])
            step5b[f"{lg}/{t}@{line0}"] = {
                "best_footystats_metric": best_fs,
                "best_newfield_candidate": best_new,
                "newfield_beats_footystats": (best_new is not None and best_fs is not None
                                              and best_new[1] > best_fs[1]),
            }
    out["step5b"] = step5b

    json.dump(out, open(OUT, "w"), indent=2, default=str)

    # ---- print ----
    print("=" * 78)
    print("STEP 5 (NAIVE BASELINE) — signal-vs-naive readout, odds out of scope")
    print("=" * 78)
    for lg in corpus.LEAGUES:
        print(f"\n### {lg} — 7 existing metrics (BSS vs naive %, first line):")
        for mid, r in out["per_metric"][lg].items():
            if "by_line" not in r:
                print(f"   {mid}: {r.get('status')}"); continue
            line0 = TARGET_LINES[r["target"]][0]
            bl = r["by_line"].get(str(line0), {})
            print(f"   {mid:22s} @{line0}: BSS={bl.get('bss_vs_naive_pct')}%  "
                  f"Brier={bl.get('brier')} ECE={bl.get('ece')} n={bl.get('n')}")
        print(f"### {lg} — notable NEW-FIELD candidates:")
        for t, cs in out["per_candidate"][lg].items():
            line0 = TARGET_LINES[TARGET_OUTCOME[t]][0]
            for feats, r in list(cs.items())[:4]:
                bl = r["by_line"].get(str(line0), {})
                print(f"   [{t}] {feats[:42]:42s} @{line0}: BSS={bl.get('bss_vs_naive_pct')}% "
                      f"Brier={bl.get('brier')} n={bl.get('n')}")
    print("\n### STEP 5b — new-field vs best FootyStats metric (BSS vs naive):")
    for cell, r in step5b.items():
        print(f"   {cell}: FS={r['best_footystats_metric']}  NEW={r['best_newfield_candidate']}  "
              f"new_beats_FS={r['newfield_beats_footystats']}")
    print(f"\nsaved: {OUT}")


def disc_league(lg):
    # corpus.LEAGUES keys are champ/ligue2/laliga2 — same as discovery JSON keys
    return lg


if __name__ == "__main__":
    main()
