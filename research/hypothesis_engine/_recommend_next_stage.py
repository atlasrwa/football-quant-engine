"""Technical eligibility of each hypothesis family for the NEXT preregistered stage.

Every criterion below is STRUCTURAL. None of them reads a difference, a sign, a magnitude
or any significance quantity: a family qualifies because the corpus can measure it
cleanly, never because the numbers came out convenient. That is mandate deliverable 15's
explicit requirement, and it is also why this file can be read before the results.

DISCLOSURE: these criteria were written AFTER the measurement run, not before it. What
protects the conclusion is not the ordering but the construction -- there is no term in
any criterion that could respond to an observed effect. The thresholds themselves are the
project's existing canonical values (see cohort_measurement.CANONICAL_CONVENTION_SOURCES),
not new numbers chosen to fit this corpus.
"""
from __future__ import annotations

import json
import sys

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src")

from research.hypothesis_engine import cohort_measurement as CM   # noqa: E402

OUT = f"{ROOT}/research/hypothesis_engine/out/v3_hypothesis_measurement"

#: Structural gates. Only the first is a new number; it is a rate, not a threshold on any
#: measured football quantity, and it is set at the conventional 80%.
MIN_MEASURABLE_RATE = 0.80
#: The canonical MEDIUM reliability floor (context_packet.reliability_for): below 8 usable
#: matches the project already declines to call a cohort estimate reliable.
MIN_MEDIAN_CONDITIONAL_N = 8
#: A family needs enough distinct comparisons to preregister anything at all.
MIN_DISTINCT_MEASURED_COMPARISONS = 10

CRITERIA_CONTAIN_NO_EFFECT_TERM = True


def main() -> int:
    fam = json.load(open(f"{OUT}/family_diagnostics.json"))["condition_family"]
    pit = json.load(open(f"{OUT}/pit_audit.json"))
    dup = json.load(open(f"{OUT}/duplicate_analysis.json"))
    meas = json.load(open(f"{OUT}/cohort_measurements.json"))

    providers = {m["spec"]["provider"] for m in meas}
    provider_consistent = len(providers) == 1

    rows = {}
    for name, d in sorted(fam.items()):
        checks = {
            "measurable_query": d["measurable_rate"] >= MIN_MEASURABLE_RATE,
            "sufficient_coverage": (d["mean_conditional_coverage"] or 0) >= 0.80,
            "reasonable_sample_n": (d["conditional_n"].get("median", 0)
                                    >= MIN_MEDIAN_CONDITIONAL_N),
            "distinct_non_duplicate_information": (
                d["n_measured"] >= MIN_DISTINCT_MEASURED_COMPARISONS
                and dup["duplicate_rate"] == 0.0),
            "provider_consistency": provider_consistent and d["n_unsupported"] == 0,
            "pit_safety": pit["clean"],
        }
        rows[name] = {
            "checks": checks,
            "eligible": all(checks.values()),
            "n_hypotheses_generated": d["n_hypotheses_generated"],
            "n_query_plans": d["n_query_plans"],
            "n_measured": d["n_measured"],
            "measurable_rate": d["measurable_rate"],
            "median_conditional_n": d["conditional_n"].get("median"),
            "blocking_reasons": sorted(k for k, v in checks.items() if not v),
        }

    out = {
        "recommendation_version": "v3_next_stage_eligibility_v1",
        "criteria_contain_no_effect_term": CRITERIA_CONTAIN_NO_EFFECT_TERM,
        "criteria_written_before_results": False,
        "criteria": {
            "MIN_MEASURABLE_RATE": MIN_MEASURABLE_RATE,
            "MIN_MEDIAN_CONDITIONAL_N": MIN_MEDIAN_CONDITIONAL_N,
            "MIN_DISTINCT_MEASURED_COMPARISONS": MIN_DISTINCT_MEASURED_COMPARISONS,
            "canonical_sources": CM.CANONICAL_CONVENTION_SOURCES,
        },
        "families": rows,
        "eligible_families": sorted(k for k, v in rows.items() if v["eligible"]),
        "ineligible_families": sorted(k for k, v in rows.items() if not v["eligible"]),
        "screening_note": (
            "If a later stage screens hypotheses on effect magnitude or sign, that "
            "screening rule must itself be preregistered and validated on data disjoint "
            "from the walk-forward evaluation window, or it contaminates the OOS test. "
            "No such screening is applied here."),
    }
    with open(f"{OUT}/next_stage_recommendation.json", "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)

    for k, v in sorted(rows.items()):
        mark = "ELIGIBLE " if v["eligible"] else "NOT ELIG."
        print(f"{mark} {k:34s} plans={v['n_query_plans']:3d} measured={v['n_measured']:3d} "
              f"rate={v['measurable_rate']:.3f} medN={v['median_conditional_n']} "
              f"{'' if v['eligible'] else '<- ' + ','.join(v['blocking_reasons'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
