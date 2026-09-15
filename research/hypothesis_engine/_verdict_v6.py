"""Run the ONE frozen V6 verdict on the immutable execution scores. ZERO SPEND.

This does NOT compute a verdict itself. It assembles the inputs the frozen
`v6_verdict.final_verdict` requires from the immutable `execution/scores.json`, then calls
the frozen evaluator and the frozen self-noise estimator. It writes
`execution/V6_VERDICT.json`. It never edits a scientific artifact, never reruns a call, and
never touches Bedrock.

Inputs assembled (all from frozen scores):
  * scorecards            -- the per-response scorecards, tagged with arm by the driver.
  * self_noise            -- v6_selfnoise.pooled_sd over the within-(fixture,arm) repeat
                             groups of the primary statistic (qualified_rate).
  * repeat_groups_per_arm -- count of repeat groups with >= 2 measured values per arm,
                             taken from the SAME pooled_sd detail.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_oos import v6_selfnoise as SN
from src.research.hypothesis_oos import v6_verdict as VD

OUT = "/home/ubuntu/research/hypothesis_oos/out/v6"
EXEC = f"{OUT}/execution"


def _self_noise_groups(scorecards: list) -> list:
    """Within-(fixture, arm) groups of the primary statistic (qualified_rate), for the
    frozen pooled-SD estimator. A cell with >= 2 measured values is a repeat group; the
    estimator itself skips groups with < 2, so we hand it every cell and let it decide."""
    cells = {}
    for s in scorecards:
        if not (s and s.get("measured")):
            continue
        r = s.get("qualified_rate")
        if r is None:
            continue
        cells.setdefault((s.get("fixture_id"), s.get("arm")), []).append(r)
    return [{"fixture_id": f, "arm": a, "values": v} for (f, a), v in cells.items()]


def main() -> int:
    scores = json.load(open(f"{EXEC}/scores.json"))
    summary = json.load(open(f"{EXEC}/execution_summary.json"))
    scorecards = [s["scorecard"] for s in scores]        # each already tagged with arm

    # frozen self-noise estimator over V6's own repeat observations
    groups = _self_noise_groups(scorecards)
    self_noise = SN.pooled_sd(groups)
    repeat_groups_per_arm = self_noise["n_groups_by_arm"]

    # THE ONE FROZEN VERDICT
    verdict = VD.final_verdict(scorecards, repeat_groups_per_arm, self_noise)

    doc = {
        "verdict_source": "frozen v6_verdict.final_verdict on immutable execution scores",
        "execution_status": summary["execution_status"],
        "stop": summary["stop"],
        "self_noise": self_noise,
        "repeat_groups_per_arm": repeat_groups_per_arm,
        "verdict": verdict,
    }
    with open(f"{EXEC}/V6_VERDICT.json", "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True, default=str)

    v = verdict
    print("=== V6 FROZEN VERDICT ===")
    print("scientific_status :", v["scientific_status"])
    print("scientific_verdict:", v.get("scientific_verdict"))
    print("verdict_reason    :", v.get("verdict_reason"))
    ev = v["evaluability"]
    print("\n-- evaluability --")
    print("  paired fixtures        :", ev["n_paired_fixtures"], "(need",
          ev["minimums"]["paired_fixtures"], ")")
    print("  valid responses per arm:", ev["n_valid_responses_per_arm"])
    print("  repeat groups per arm  :", ev["repeat_groups_per_arm"], "(need",
          ev["minimums"]["repeat_groups_per_arm"], ")")
    print("  qualified denominator  :", ev["qualified_denominator"], "(need",
          ev["minimums"]["qualified_denominator"], ")")
    print("  unmet:", ev["unmet"] or "NONE")
    print("\n-- self-noise --")
    print("  pooled_sd:", self_noise["pooled_sd"], "sd_used:", self_noise["sd_used"],
          "floor_applied:", self_noise["min_floor_applied"])
    print("  n_groups_by_arm:", self_noise["n_groups_by_arm"])
    if "discipline" in v:
        d = v["discipline"]
        print("\n-- discipline (research - base, tol", d["tolerance"], ") --")
        for k, ax in d["axes"].items():
            print(f"  {k}: base={ax['base']} research={ax['research']} "
                  f"degraded={ax['degraded']}")
        print("  discipline_degraded:", d["discipline_degraded"])
    if "primary" in v:
        p = v["primary"]
        print("\n-- primary --")
        print("  n_paired_fixtures :", p["n_paired_fixtures"])
        print("  mean_paired_diff  :", p["mean_paired_diff"])
        print("  benchmark         :", p["benchmark"].get("benchmark"))
        print("  exceeds_self_noise:", p["exceeds_self_noise"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
