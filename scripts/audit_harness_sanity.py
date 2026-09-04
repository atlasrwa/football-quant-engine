"""
AUDIT 4 — Evaluation harness sanity (diagnose only, zero API).

Feeds known-answer inputs into the SHIPPED metric implementations and the
validation-script metric implementations, and checks each returns the answer we
already know. If a metric cannot detect skill we know is present (esp. a leaked
feature), the metric is broken and every negative result is suspect.

Metrics under test (all LIVE-tree implementations):
  A. src.research.prediction_engine.calibration_metrics.brier_skill_score  (shipped BSS)
  B. src.research.calibration.CalibrationEvaluator                          (shipped ECE/Brier)
  C. scripts.multisrc_step5_naive_baseline.brier_bss_ece                    (family-transfer BSS/ECE)
  D. run_robustness_check.brier_score + inline vs-naive                     (cross-league producer)
  E. run_benchmark.brier_score                                             (original producer)

Known-answer probes:
  1. Perfect predictor  -> BSS ~ +1.0, ECE ~ 0
  2. Base-rate predictor -> BSS ~ 0
  3. Random predictor    -> BSS clearly negative
  4. LEAKED feature      -> a model fed the outcome must show large, obvious skill
                            (decisive: if leakage is invisible, the harness is blind)
"""
import os, sys, math
import numpy as np

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

from src.research.prediction_engine.calibration_metrics import (
    brier_skill_score, calibration_report,
)
from src.research.calibration import CalibrationEvaluator

RNG = np.random.default_rng(20260902)
N = 2000

# A binary-outcome world with a real base rate.
base_rate = 0.55
outcomes = (RNG.random(N) < base_rate).astype(int)
outcomes_bool = [bool(o) for o in outcomes]


def line(s=""):
    print(s)


# ── Metric A/B: shipped BSS + CalibrationEvaluator ────────────────────────────
def probe_shipped():
    line("=" * 78)
    line("A/B. SHIPPED metrics: calibration_metrics.brier_skill_score + CalibrationEvaluator")
    line("=" * 78)

    # 1. Perfect predictor: predict 0.99 where outcome=1, 0.01 where 0
    perfect = np.where(outcomes == 1, 0.99, 0.01)
    r = brier_skill_score(perfect, outcomes_bool)
    ce = CalibrationEvaluator(n_bins=10, min_samples=50).evaluate(list(perfect), outcomes_bool)
    line(f"  1 perfect  : BSS={r.bss:+.4f}  (expect ~+1.0)   ECE={ce.ece:.4f} (expect ~0)")

    # 2. Base-rate predictor: predict the sample base rate everywhere
    br = float(outcomes.mean())
    baseline = np.full(N, br)
    r2 = brier_skill_score(baseline, outcomes_bool)
    line(f"  2 base-rate: BSS={r2.bss:+.4f}  (expect ~0.0)")

    # 3. Random predictor: uniform random probabilities
    rand = RNG.random(N)
    r3 = brier_skill_score(rand, outcomes_bool)
    line(f"  3 random   : BSS={r3.bss:+.4f}  (expect clearly negative)")

    # 4. LEAKED feature: probability = 0.5 + 0.4 * outcome (monotone in the truth)
    leaked = 0.5 + 0.4 * outcomes  # 0.5 for 0, 0.9 for 1
    r4 = brier_skill_score(leaked, outcomes_bool)
    line(f"  4 LEAKED   : BSS={r4.bss:+.4f}  (expect large positive — DECISIVE)")

    return {
        "perfect_bss": r.bss, "perfect_ece": ce.ece,
        "baserate_bss": r2.bss, "random_bss": r3.bss, "leaked_bss": r4.bss,
    }


# ── Metric C: multisrc_step5_naive_baseline.brier_bss_ece ─────────────────────
# This one is DIFFERENT: it takes preds as {predicted_lambda, actual_count,
# date_unix} and derives P(over line) via Poisson survival, with a POINT-IN-TIME
# EXPANDING base rate. We must feed it in that shape to test it honestly.
def probe_multisrc():
    line("")
    line("=" * 78)
    line("C. multisrc_step5_naive_baseline.brier_bss_ece (family-transfer BSS/ECE)")
    line("   NB: point-in-time expanding-base-rate naive; preds carry a Poisson lambda")
    line("=" * 78)
    from multisrc_step5_naive_baseline import brier_bss_ece

    line_val = 2.5
    # Build a synthetic season of counts with a known team-independent mean.
    lam_true = 2.7
    counts = RNG.poisson(lam_true, N)
    dates = np.arange(N) * 86400  # strictly increasing

    # 1. Perfect-ish: predicted_lambda = true generating lambda (best possible Poisson)
    perfect = [{"predicted_lambda": lam_true, "actual_count": int(c), "date_unix": int(d)}
               for c, d in zip(counts, dates)]
    rp = brier_bss_ece(perfect, line_val)
    line(f"  1 lambda=truth  : BSS={rp['bss_vs_naive_pct']:+.2f}%  ECE={rp['ece']:.4f}  n={rp['n']}")
    line("     (Poisson@true-lambda barely beats expanding base rate — small +BSS expected)")

    # 4. LEAKED: predicted_lambda set so P(over) is ~1 when count>line, ~0 else.
    #    lambda huge when actual>line, tiny when not -> survival ~1/0 = leaked.
    leaked = [{"predicted_lambda": (50.0 if c > line_val else 0.01),
               "actual_count": int(c), "date_unix": int(d)}
              for c, d in zip(counts, dates)]
    rl = brier_bss_ece(leaked, line_val)
    line(f"  4 LEAKED lambda : BSS={rl['bss_vs_naive_pct']:+.2f}%  ECE={rl['ece']:.4f}  n={rl['n']}  (expect near +100% — DECISIVE)")

    # 2. base-rate-ish: lambda = mean count -> should be ~0 vs expanding base rate
    lam_mean = float(counts.mean())
    base = [{"predicted_lambda": lam_mean, "actual_count": int(c), "date_unix": int(d)}
            for c, d in zip(counts, dates)]
    rb = brier_bss_ece(base, line_val)
    line(f"  2 lambda=mean   : BSS={rb['bss_vs_naive_pct']:+.2f}%  (expect ~0)")

    return {"perfect_bss_pct": rp["bss_vs_naive_pct"], "leaked_bss_pct": rl["bss_vs_naive_pct"],
            "base_bss_pct": rb["bss_vs_naive_pct"]}


# ── Metric D/E: run_robustness_check + run_benchmark brier/vs-naive ───────────
def probe_producers():
    line("")
    line("=" * 78)
    line("D/E. Cross-league producer (run_robustness_check) + original (run_benchmark) BSS")
    line("=" * 78)
    import importlib.util

    def load(modpath, name):
        spec = importlib.util.spec_from_file_location(name, modpath)
        m = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(m)
        except SystemExit:
            pass
        return m

    results = {}
    # NB: run_benchmark.py performs a FootyStats fetch at IMPORT time (lines 44-45),
    # so it cannot be imported under the zero-API rule. Its brier_score is textually
    # identical to run_robustness_check's (np.mean((p-a)^2)); testing the latter
    # covers the identical metric math. We therefore probe run_robustness_check only.
    for label, path in (("run_robustness_check", "/home/ubuntu/run_robustness_check.py"),):
        if not os.path.exists(path):
            line(f"  {label}: FILE NOT FOUND at {path}")
            continue
        m = load(path, label.replace(".", "_"))
        bs = getattr(m, "brier_score", None)
        ece_fn = getattr(m, "compute_ece", None)
        if bs is None:
            line(f"  {label}: no brier_score() function found")
            continue
        # perfect vs base vs leaked using their brier_score(probs, outcomes)
        probs_perfect = np.where(outcomes == 1, 0.99, 0.01)
        probs_base = np.full(N, float(outcomes.mean()))
        probs_leak = 0.5 + 0.4 * outcomes
        try:
            b_perfect = bs(probs_perfect, outcomes)
            b_base = bs(probs_base, outcomes)
            b_leak = bs(probs_leak, outcomes)
            # vs-naive percent as the producers compute it: (naive - model)/naive*100
            naive = b_base
            def vs_naive(bm):
                return (naive - bm) / naive * 100 if naive > 0 else None
            line(f"  {label}.brier_score: perfect={b_perfect:.4f} (vs-naive {vs_naive(b_perfect):+.1f}%)  "
                 f"base={b_base:.4f}  leaked={b_leak:.4f} (vs-naive {vs_naive(b_leak):+.1f}%)")
            results[label] = {"perfect_vs_naive_pct": vs_naive(b_perfect),
                              "leaked_vs_naive_pct": vs_naive(b_leak)}
        except Exception as e:
            line(f"  {label}.brier_score raised: {e!r}")
        if ece_fn is not None:
            try:
                e_perfect = ece_fn(probs_perfect, outcomes)
                line(f"  {label}.compute_ece: perfect ECE={e_perfect:.4f} (expect ~0)")
            except Exception as e:
                line(f"  {label}.compute_ece raised: {e!r}")
    return results


def main():
    line("AUDIT 4 — EVALUATION HARNESS SANITY (known-answer probes, seed 20260902)")
    line(f"world: N={N}, base_rate={base_rate}, realised mean={outcomes.mean():.4f}")
    a = probe_shipped()
    c = probe_multisrc()
    d = probe_producers()

    line("")
    line("=" * 78)
    line("VERDICT (harness)")
    line("=" * 78)
    ok_perfect = a["perfect_bss"] > 0.9
    ok_base = abs(a["baserate_bss"]) < 0.02
    ok_random = a["random_bss"] < -0.05
    ok_leaked = a["leaked_bss"] > 0.3
    ok_multi_leak = c["leaked_bss_pct"] > 50
    line(f"  shipped perfect BSS>0.9 : {ok_perfect} ({a['perfect_bss']:+.4f})")
    line(f"  shipped base-rate ~0    : {ok_base} ({a['baserate_bss']:+.4f})")
    line(f"  shipped random <0       : {ok_random} ({a['random_bss']:+.4f})")
    line(f"  shipped LEAKED big +    : {ok_leaked} ({a['leaked_bss']:+.4f})")
    line(f"  multisrc LEAKED >+50%   : {ok_multi_leak} ({c['leaked_bss_pct']:+.2f}%)")
    all_ok = all([ok_perfect, ok_base, ok_random, ok_leaked, ok_multi_leak])
    line(f"\n  HARNESS DETECTS SKILL WHEN PRESENT: {all_ok}")
    if not all_ok:
        line("  *** HARNESS FAULT — a known signal was not detected; negative results suspect ***")


if __name__ == "__main__":
    main()
