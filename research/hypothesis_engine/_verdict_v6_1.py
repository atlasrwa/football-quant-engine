"""Run the ONE frozen V6.1 verdict on the immutable execution scores. ZERO SPEND.

Mirrors `_verdict_v6.py` exactly, but for V6.1: it assembles the inputs the frozen
`v6_1_verdict.final_verdict` requires from the immutable `execution/scores.json`, computes
self-noise with the frozen `v6_selfnoise` over V6.1's OWN NEW repeat observations, then calls
the frozen repaired evaluator and writes `execution/V6_1_VERDICT.json`. It computes no
verdict itself, edits no scientific artifact, reruns no call, and never touches Bedrock.

It never injects V6's historical +0.1134 / 0.1281 or the corrected replay -- self-noise is
estimated only from V6.1's new within-(fixture,arm) repeat groups.
"""
from __future__ import annotations

import hashlib
import json
import sys

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_oos import v6_1_verdict as V61
from src.research.hypothesis_oos import v6_selfnoise as SN

OUT = "/home/ubuntu/research/hypothesis_oos/out/v6_1"
EXEC = f"{OUT}/execution"


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _self_noise_groups(scorecards):
    """Within-(fixture, arm) groups of the primary statistic (qualified_rate), for the
    frozen pooled-SD estimator -- V6.1's own repeats only."""
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

    groups = _self_noise_groups(scorecards)
    self_noise = SN.pooled_sd(groups)
    repeat_groups_per_arm = self_noise["n_groups_by_arm"]

    # THE ONE FROZEN V6.1 VERDICT (repaired evaluator + metric contracts)
    verdict = V61.final_verdict(scorecards, repeat_groups_per_arm, self_noise)

    doc = {
        "verdict_source": "frozen v6_1_verdict.final_verdict on immutable V6.1 execution scores",
        "scores_sha256": _sha(f"{EXEC}/scores.json"),
        "execution_status": summary["execution_status"],
        "execution_state": summary["execution_state"],
        "stop": summary["stop"],
        "self_noise": self_noise,
        "repeat_groups_per_arm": repeat_groups_per_arm,
        "verdict": verdict,
    }
    with open(f"{EXEC}/V6_1_VERDICT.json", "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True, default=str)

    v = verdict
    print("=== V6.1 FROZEN VERDICT ===")
    print("verdict_version   :", v["verdict_version"])
    print("scientific_status :", v["scientific_status"])
    print("scientific_verdict:", v.get("scientific_verdict"))
    print("verdict_reason    :", v.get("verdict_reason"))
    if v.get("evaluator_invalid"):
        print("metric_contract_violation:", v.get("metric_contract_violation"))
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
    print("\n-- self-noise (V6.1 own repeats) --")
    print("  pooled_sd:", self_noise["pooled_sd"], "sd_used:", self_noise["sd_used"],
          "floor_applied:", self_noise["min_floor_applied"])
    print("  n_groups_by_arm:", self_noise["n_groups_by_arm"])
    if "discipline" in v:
        d = v["discipline"]
        print("\n-- discipline (tol", d["tolerance"], ") --")
        for k, ax in d["axes"].items():
            print(f"  {k}: base={ax['base']} research={ax['research']} "
                  f"degraded={ax['degraded']}")
        print("  discipline_degraded:", d["discipline_degraded"],
              "degraded_axes:", d["degraded_axes"])
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
