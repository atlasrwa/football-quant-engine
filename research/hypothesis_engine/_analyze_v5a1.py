"""Run the FROZEN V5A.1 evaluator exactly once over the completed immutable response set.

ZERO SPEND. This is a driver: every scoring rule, threshold, classifier and gate lives in
`v5a1_evaluator.py`, which was hashed and frozen BEFORE the first paid call. Nothing here
defines or adjusts a metric.
"""
from __future__ import annotations

import hashlib, json, os, statistics, sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_oos import v5a1_evaluator as EV

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v5a1"
RUN = f"{OUT}/execution"

RATE_KEYS = ["grounded_acceptance_rate", "valid_evidence_reference_rate",
             "fabricated_evidence_rate", "compilability", "unsupported_dimension_rate",
             "firewall_clean_rate", "meaningful_conditionality",
             "meaningful_interaction_rate", "redundancy_rate", "baseline_diversity",
             "metric_family_diversity", "evidence_specificity", "abstention_rate"]
USE_KEYS = ["venue_use", "recent_vs_long_use", "opponent_profile_use", "formation_use"]


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    frz = json.load(open(f"{OUT}/EVALUATOR_FREEZE.json"))
    cur = _sha(f"{ROOT}/src/research/hypothesis_oos/v5a1_evaluator.py")
    if cur != frz["evaluator_sha256"]:
        print("EVALUATOR DRIFT: refusing to score.", cur, "!=", frz["evaluator_sha256"])
        return 2

    packets = {"base": json.load(open(f"{OUT}/packets_base.json")),
               "research": json.load(open(f"{OUT}/packets_research.json"))}
    recs = [json.loads(l) for l in open(f"{RUN}/execution_log.jsonl")]
    completed = [r for r in recs if r.get("outcome") in ("COMPLETED", "MODEL_NO_TOOL_USE")]
    infra = [r for r in recs if r.get("outcome") == "INFRASTRUCTURE_CENSORED"]

    scored = []
    for r in completed:
        pk = packets[r["arm_internal"]][r["fixture_id"]]
        s = EV.score_response(r.get("raw_response"), pk)
        for k in USE_KEYS:
            s.setdefault(k, 0)
            s.setdefault(f"{k}_available", False)
        row = {"seq": r["seq"], "fixture_id": r["fixture_id"], "arm": r["arm_internal"],
               "replicate": r["replicate"], "is_repeat": r["is_repeat"],
               "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
               "stop_reason": r.get("stop_reason"), **s, **EV.rates(s)}
        scored.append(row)

    # ---- primary calls only (replicate 0) for the paired comparison -------------------
    primary = {(x["fixture_id"], x["arm"]): x for x in scored if x["replicate"] == 0}
    fixtures = sorted({f for f, _ in primary})
    paired = []
    for f in fixtures:
        a, b = primary.get((f, "base")), primary.get((f, "research"))
        if not a or not b:
            continue
        row = {"fixture_id": f,
               "base": a[EV.PRIMARY_METRIC], "research": b[EV.PRIMARY_METRIC],
               "diff": b[EV.PRIMARY_METRIC] - a[EV.PRIMARY_METRIC]}
        for k in RATE_KEYS:
            row[f"{k}__base"] = round(a[k], 4)
            row[f"{k}__research"] = round(b[k], 4)
            row[f"{k}__delta"] = round(b[k] - a[k], 4)
        # A whole-response failure (schema-invalid, firewall block) returns early from
        # score_response and never reaches the availability-use pass, so these keys are
        # absent. 0 / False is the only meaningful value for a response that produced no
        # usable hypotheses. Defaulting here keeps the FROZEN evaluator byte-identical.
        for k in USE_KEYS:
            row[f"{k}__base"] = a.get(k, 0)
            row[f"{k}__base_available"] = a.get(f"{k}_available", False)
            row[f"{k}__research"] = b.get(k, 0)
            row[f"{k}__research_available"] = b.get(f"{k}_available", False)
        paired.append(row)

    # ---- self-noise from the preregistered repeats -----------------------------------
    groups = {}
    for x in scored:
        groups.setdefault((x["fixture_id"], x["arm"]), []).append(x)
    repeat_groups = [{"fixture_id": f, "arm": a,
                      "values": [y[EV.PRIMARY_METRIC]
                                 for y in sorted(v, key=lambda z: z["replicate"])]}
                     for (f, a), v in sorted(groups.items()) if len(v) > 1]
    noise = EV.self_noise_floor(repeat_groups)

    # ---- discipline deltas (pooled over primary calls) --------------------------------
    def pooled(arm, key):
        vals = [x[key] for x in scored if x["arm"] == arm and x["replicate"] == 0]
        return statistics.fmean(vals) if vals else 0.0

    disc = {
        "compilability_delta": round(pooled("research", "compilability")
                                     - pooled("base", "compilability"), 4),
        "firewall_clean_delta": round(pooled("research", "firewall_clean_rate")
                                      - pooled("base", "firewall_clean_rate"), 4),
        "fabricated_evidence_delta": round(pooled("research", "fabricated_evidence_rate")
                                           - pooled("base", "fabricated_evidence_rate"), 4),
        "unsupported_dimension_delta": round(pooled("research", "unsupported_dimension_rate")
                                             - pooled("base", "unsupported_dimension_rate"), 4),
    }

    verdict = EV.verdict(paired, noise["floor_used"], disc)

    pooled_rates = {arm: {k: round(pooled(arm, k), 4) for k in RATE_KEYS}
                    for arm in ("base", "research")}

    summary = json.load(open(f"{RUN}/execution_summary.json"))
    results = {
        "evaluator": EV.version_stamp(),
        "evaluator_sha256": cur,
        "evaluator_frozen_before_first_paid_call": True,
        "n_completed_calls": len(completed),
        "n_infrastructure_failures": len(infra),
        "infrastructure_failures": [{"seq": r["seq"], "error": r.get("error")}
                                    for r in infra],
        "actual_cost_usd": summary.get("actual_cost_usd"),
        "per_call": scored,
        "paired_by_fixture": paired,
        "pooled_rates": pooled_rates,
        "discipline_deltas": disc,
        "self_noise": noise,
        "verdict": verdict,
    }
    json.dump(results, open(f"{RUN}/evaluation_results.json", "w"), indent=1,
              sort_keys=False, default=str)

    print(f"completed={len(completed)} infra={len(infra)} cost=${summary.get('actual_cost_usd')}")
    print(f"self-noise pooled_sd={noise['pooled_sd']} floor={noise['floor_used']}")
    print(f"discipline deltas: {disc}")
    print(f"\n{'FIXTURE':14}{'base':>6}{'res':>6}{'diff':>6}")
    for p in paired:
        print(f"{p['fixture_id']:14}{p['base']:6}{p['research']:6}{p['diff']:+6}")
    print(f"\nVERDICT: {verdict['verdict']}  ({verdict['reason']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
