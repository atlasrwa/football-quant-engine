"""Score the rebuilt prior-only EPL 2023/24 (season 9660) predictions (Task 3).

Reads the fixture-keyed predictions persisted by rebuild_prior_only_9660.py and computes,
on the identical saved fixtures:
  - model Brier, naive Brier, and vs-naive % for corners O/U 9.5 and cards O/U 3.5
  - 5-bin ECE for the model

It does NOT recompute predictions — it scores exactly what was saved to disk, so the
numbers correspond to the persisted, leak-free artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

PRED_PATH = Path("/home/ubuntu/data/results/prior_only_9660_predictions.json")


def brier(preds, actuals):
    return float(np.mean([(p - a) ** 2 for p, a in zip(preds, actuals)]))


def ece(preds, actuals, n_bins=5):
    preds = np.asarray(preds)
    actuals = np.asarray(actuals)
    edges = np.linspace(0, 1, n_bins + 1)
    tot_gap = 0.0
    tot_n = 0
    for i in range(n_bins):
        if i == n_bins - 1:
            mask = (preds >= edges[i]) & (preds <= edges[i + 1])
        else:
            mask = (preds >= edges[i]) & (preds < edges[i + 1])
        if mask.sum() >= 3:
            gap = abs(preds[mask].mean() - actuals[mask].mean())
            tot_gap += gap * mask.sum()
            tot_n += int(mask.sum())
    return tot_gap / tot_n if tot_n else None


def score(preds, market_key):
    model = [p[f"model_p_{market_key}_over"] for p in preds]
    naive = [p[f"naive_p_{market_key}_over"] for p in preds]
    actual = [p[f"actual_{market_key}_over"] for p in preds]
    mb = brier(model, actual)
    nb = brier(naive, actual)
    vs = (nb - mb) / nb * 100 if nb else float("nan")
    return {
        "n": len(preds),
        "model_brier": mb,
        "naive_brier": nb,
        "vs_naive_pct": vs,
        "model_ece": ece(model, actual),
        "base_rate_over": float(np.mean(actual)),
    }


def main():
    data = json.load(open(PRED_PATH))
    preds = [p for p in data["predictions"] if p["actual_corners_over"] is not None]
    preds_k = [p for p in data["predictions"] if p["actual_cards_over"] is not None]

    c = score(preds, "corners")
    k = score(preds_k, "cards")

    # Old contaminated figures (for side-by-side). Sources:
    #   - run_benchmark.py reported +9.6% corners (headline, EPL, mislabeled 2023/24 = actually 2020/21).
    #   - Task brief quoted corners +6.8%, cards +6.1% as the "genuinely predictive" markets.
    #   - robustness_results.json EPL 2023/24-labeled row: corners +9.98%, cards +13.80%.
    # These all share the leaking pipeline (Task 1). We present the brief's headline pair.
    old = {
        "corners_vs_naive_pct": 6.8,
        "cards_vs_naive_pct": 6.1,
        "note": "contaminated: same-match realized stats leaked into features; "
                "corners benchmark also ran on season 4759 (2020/21) mislabeled 2023/24",
    }

    print("=" * 78)
    print("TASK 3 — PRIOR-ONLY (LEAK-FREE) RE-RUN vs CONTAMINATED — EPL 2023/24 (9660)")
    print("=" * 78)
    print(f"Identical fixtures scored: corners n={c['n']}, cards n={k['n']} "
          f"(walk-forward, MIN_TRAIN=150, expanding window)")
    print()
    print(f"{'Market':<18}{'Old (contam.)':<16}{'New (prior-only)':<18}{'Model Brier':<13}{'Naive Brier':<13}")
    print("-" * 78)
    print(f"{'Corners O/U 9.5':<18}{old['corners_vs_naive_pct']:>+7.1f}%{'':<8}"
          f"{c['vs_naive_pct']:>+8.2f}%{'':<8}{c['model_brier']:<13.4f}{c['naive_brier']:<13.4f}")
    print(f"{'Cards O/U 3.5':<18}{old['cards_vs_naive_pct']:>+7.1f}%{'':<8}"
          f"{k['vs_naive_pct']:>+8.2f}%{'':<8}{k['model_brier']:<13.4f}{k['naive_brier']:<13.4f}")
    print()
    print(f"Model ECE (5-bin):  corners={c['model_ece']:.4f}   cards={k['model_ece']:.4f}")
    print(f"Over base rate:     corners={c['base_rate_over']:.3f}   cards={k['base_rate_over']:.3f}")
    print()

    # Honest summary line.
    def verdict(name, v):
        if v <= 0:
            return f"{name}: edge GONE — prior-only model does NOT beat naive ({v:+.2f}%)."
        if v < 1.0:
            return f"{name}: edge essentially gone — {v:+.2f}% vs naive (within noise)."
        return f"{name}: {v:+.2f}% vs naive after removing the leak."

    print("SUMMARY:")
    print("  " + verdict("Corners", c["vs_naive_pct"]))
    print("  " + verdict("Cards", k["vs_naive_pct"]))
    print()
    print("  Cards: leak-free, beats climatology on EPL 2023/24 in this single sample "
          f"({k['vs_naive_pct']:+.2f}% vs the rolling prior-rate baseline); market-relative "
          "performance unknown because cards closing-line prices are unavailable.")
    print("  This one-season result is not a general cross-league skill claim and does not "
          "establish that the model beats market prices.")

    # Persist scored summary next to predictions.
    out = {
        "season_id": data["meta"]["season_id"],
        "season_label": data["meta"]["season_label"],
        "corners": c,
        "cards": k,
        "old_contaminated": old,
        "cards_claim": (
            "leak-free, beats climatology on EPL 2023/24, market-relative performance unknown"
        ),
        "hypothesis_result": {
            "corners": "contaminated edge removed by prior-only reconstruction",
            "cards": "single EPL 2023/24 leak-free result beats climatology; cross-league and market-relative performance unknown",
        },
    }
    Path("/home/ubuntu/data/results/prior_only_9660_scores.json").write_text(
        json.dumps(out, indent=2)
    )
    print()
    print("Wrote data/results/prior_only_9660_scores.json")


if __name__ == "__main__":
    main()
