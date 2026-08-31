"""
Step 1b — Gate decision: does correlation vary MATERIALLY by profile?

Reads the Step 1 result and applies an explicit, pre-stated gate:

  The hypothesis requires POSITIVE outcome correlation that is materially
  larger in some identifiable profile than a blanket adjustment assumes.

Gate criteria (all model-free, within-league-season controlled):
  (A) Is the overall correlation positive and non-trivial? (|rho| >= 0.05 and > 0)
  (B) Does any profile bucket show a within-control Spearman that is
      (i) positive, (ii) material (>= +0.10), and (iii) survives a
      Bonferroni/BH correction over the full profile×pair family?

Also reports the multiple-testing family size explicitly and applies
Benjamini-Hochberg across every profile-bucket×pair correlation examined.
"""

import json
import numpy as np


def bh_correct(pvals, alpha=0.05):
    """Benjamini-Hochberg FDR. Returns (reject list, adjusted p list) in input order."""
    m = len(pvals)
    if m == 0:
        return [], []
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    prev = 1.0
    # step-up: iterate from largest p to smallest
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        val = pvals[i] * m / rank
        prev = min(prev, val)
        adj[i] = min(prev, 1.0)
    reject = [adj[i] <= alpha for i in range(m)]
    return reject, adj

BASE = "/home/ubuntu"
IN = f"{BASE}/data/results/samegame_step1_correlation.json"
OUT = f"{BASE}/data/results/samegame_step1b_gate.json"


def collect_bucket_tests(res):
    """Collect every within-league-season bucket×pair correlation with its p and n."""
    tests = []
    for pk, prof in res["profiles"].items():
        buckets = prof["buckets"]
        for lab, b in buckets.items():
            corr = b.get("corr")
            if not corr:
                continue
            for pair, c in corr.items():
                w = c["within_league_season"]
                if w["spearman"] is None:
                    continue
                tests.append({
                    "profile": pk, "bucket": lab, "pair": pair,
                    "spearman": w["spearman"], "p": w["spearman_p"], "n": w["n"],
                })
    return tests


def main():
    res = json.load(open(IN))
    tests = collect_bucket_tests(res)
    family_size = len(tests)

    pvals = [t["p"] for t in tests]
    rej, p_adj = bh_correct(pvals, alpha=0.05)
    for t, r, pa in zip(tests, rej, p_adj):
        t["bh_reject"] = bool(r)
        t["p_adj_bh"] = float(pa)

    # Overall
    overall = res["overall"]
    overall_summary = {}
    for pair, c in overall.items():
        w = c["within_league_season"]
        p = c["pooled"]
        overall_summary[pair] = {
            "pooled_spearman": p["spearman"],
            "within_spearman": w["spearman"],
            "within_n": w["n"],
        }

    # Criterion A
    A = any((s["within_spearman"] is not None and s["within_spearman"] > 0 and abs(s["within_spearman"]) >= 0.05)
            for s in overall_summary.values())

    # Criterion B: positive, material, survives BH
    material_positive = [t for t in tests if t["spearman"] >= 0.10 and t["bh_reject"]]
    B = len(material_positive) > 0

    # Also: any positive-and-BH-significant at all (weaker)
    positive_significant = [t for t in tests if t["spearman"] > 0 and t["bh_reject"]]
    # negative-and-significant (informative: the coupling is negative)
    negative_significant = [t for t in tests if t["spearman"] < 0 and t["bh_reject"]]

    gate_pass = bool(A or B)

    out = {
        "family_size_profile_bucket_pair_tests": family_size,
        "overall": overall_summary,
        "criterion_A_overall_positive_nontrivial": A,
        "criterion_B_any_bucket_positive_material_bh": B,
        "material_positive_buckets": material_positive,
        "positive_and_bh_significant": positive_significant,
        "negative_and_bh_significant_count": len(negative_significant),
        "negative_and_bh_significant_examples": negative_significant[:8],
        "gate_pass": gate_pass,
        "max_within_bucket_spearman": max((t["spearman"] for t in tests), default=None),
        "min_within_bucket_spearman": min((t["spearman"] for t in tests), default=None),
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)

    print("=" * 78)
    print("STEP 1b — GATE DECISION")
    print("=" * 78)
    print(f"Multiple-testing family (profile-bucket x pair correlations): {family_size}")
    print("\nOverall within-league-season Spearman:")
    for pair, s in overall_summary.items():
        print(f"  {pair:18s} within={s['within_spearman']:+.4f} (n={s['within_n']}) "
              f"pooled={s['pooled_spearman']:+.4f}")
    print(f"\nCriterion A (overall positive & |rho|>=0.05): {A}")
    print(f"Criterion B (a bucket positive, >=+0.10, BH-significant): {B}")
    print(f"  material positive buckets: {len(material_positive)}")
    print(f"  positive & BH-significant (any size): {len(positive_significant)}")
    print(f"  negative & BH-significant: {len(negative_significant)}")
    print(f"  max within-bucket Spearman = {out['max_within_bucket_spearman']:+.4f}")
    print(f"  min within-bucket Spearman = {out['min_within_bucket_spearman']:+.4f}")
    print(f"\n>>> GATE {'PASSES' if gate_pass else 'FAILS'} <<<")
    if positive_significant:
        print("\nPositive & BH-significant buckets:")
        for t in positive_significant:
            print(f"  {t['profile']}/{t['bucket']}/{t['pair']}: rho={t['spearman']:+.3f} "
                  f"n={t['n']} p_adj={t['p_adj_bh']:.4f}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
