"""Self-noise as a first-class measurement (`v6_selfnoise_v1`). §9, §22.

THE NUMBER THIS MODULE HAS TO RESPECT
--------------------------------------
V5A.2, four byte-identical requests, `temperature = 0.0`, same
`serialized_request_sha256`. Re-scored under the V6 adjudicator, the base arm's
`qualified_rate` came back

    0.75, 0.00, 0.70, 0.00        pooled within-cell SD 0.363

Two of the four calls conditioned EVERY hypothesis on dimensions the base packet declares
unavailable; two conditioned none. That is not measurement jitter, it is a bimodal
generator, and any endpoint built without it in view will report generator variance as a
treatment effect.

WHY THE RAW SD IS THE WRONG BENCHMARK, AND WHAT REPLACES IT
-------------------------------------------------------------
V5A.2's gate was `mean_paired_diff > pooled_within_cell_SD`. That compares a quantity
averaged over TEN fixtures against the spread of a SINGLE call. The two live at different
aggregation levels, and the mismatch is conservative in a way that has nothing to do with
evidence: at SD 0.363 it demands a paired difference larger than any plausible effect, so
the experiment would return MIXED whatever the model did. §37 names that failure directly --
"self-noise design is underpowered BY CONSTRUCTION" -- and it is a reason not to freeze.

So V6 benchmarks the difference against self-noise AT THE LEVEL THE CLAIM IS MADE: the
standard error of the paired mean difference, under the null that the two arms differ only
by what the generator does to itself on identical input.

    Var(d_f)      = sd^2 * (1/r_f_base + 1/r_f_research)      per fixture
    Var(mean d)   = sum_f Var(d_f) / F^2
    benchmark     = Z * sqrt(Var(mean d))

`sd` is the POOLED within-(fixture, arm) SD measured from V6's own repeat groups. The
FORMULA is frozen here, before spend; the VALUE is measured in the run. That is what
preregistration means -- freezing the procedure, not the answer.

Z = 1.645 is the conventional one-sided 5% normal bound, fixed now and for the stated
reason. `r_f` weighting matters and is not cosmetic: a fixture measured three times
contributes a third of the variance of one measured once, so the four repeat fixtures do
real work in the denominator rather than only in the SD estimate.

    HONESTY ABOUT WHAT THIS IS. This is a NOISE-EXCEEDANCE criterion, not a hypothesis test
    with distributional guarantees. Ten fixtures, a bimodal generator and a bounded
    statistic do not satisfy normality, and calling the result a p-value would be a claim
    the design cannot support. It answers one question -- is the observed difference larger
    than same-input repeat variability plausibly produces at this aggregation level -- and
    `power_sketch()` states, before any spend, exactly how large a difference that requires.

MIN_SELF_NOISE_SD exists because three identical repeats are not evidence of zero
variance. Without it a group that happened to repeat itself exactly would drive the
benchmark to zero and auto-PASS any positive difference at all.

ZERO SPEND.
"""
from __future__ import annotations

import math
import statistics

SELFNOISE_VERSION = "v6_selfnoise_v1"

#: One-sided 5% normal bound. Frozen before spend, for the reason stated above.
Z_MULTIPLIER = 1.645

#: A floor on the pooled within-cell SD, on the [0, 1] qualified-rate scale. Five
#: percentage points: one twentieth of the statistic's range, and smaller than any
#: difference this experiment would call material. Its job is to stop an accidentally
#: clean repeat group from manufacturing a PASS, not to set the scale of the test.
MIN_SELF_NOISE_SD = 0.05

#: §9 requires MULTIPLE fixtures in BOTH arms. V5A.2 had one group per arm and correctly
#: refused to treat it as an estimate. Four are scheduled; three is the minimum at which
#: a pooled SD is an estimate rather than an anecdote, leaving one group of slack.
MIN_REPEAT_GROUPS_PER_ARM = 3


def pooled_sd(groups: list) -> dict:
    """Pooled within-(fixture, arm) SD of the primary statistic.

    `groups` is a list of {"fixture_id", "arm", "values"}. A group needs >= 2 values to
    contribute; groups with fewer are reported and excluded rather than silently dropped.
    """
    sds, detail, skipped = [], [], []
    for g in sorted(groups, key=lambda x: (x["arm"], x["fixture_id"])):
        vals = [v for v in g["values"] if v is not None]
        if len(vals) < 2:
            skipped.append({"fixture_id": g["fixture_id"], "arm": g["arm"],
                            "n": len(vals),
                            "reason": "fewer than 2 measured repeats"})
            continue
        sd = statistics.pstdev(vals)
        sds.append(sd)
        detail.append({"fixture_id": g["fixture_id"], "arm": g["arm"], "n": len(vals),
                       "values": [round(v, 6) for v in vals], "sd": round(sd, 6),
                       "mean": round(statistics.fmean(vals), 6)})
    pooled = math.sqrt(sum(s * s for s in sds) / len(sds)) if sds else 0.0
    used = max(pooled, MIN_SELF_NOISE_SD)
    return {"pooled_sd": round(pooled, 6),
            "sd_used": round(used, 6),
            "min_floor_applied": pooled < MIN_SELF_NOISE_SD,
            "min_self_noise_sd": MIN_SELF_NOISE_SD,
            "n_groups": len(detail),
            "n_groups_by_arm": {a: sum(1 for d in detail if d["arm"] == a)
                                for a in ("base", "research")},
            "groups": detail, "skipped_groups": skipped}


def benchmark(sd_used: float, per_fixture_reps: list) -> dict:
    """The §22 self-noise benchmark for the paired mean difference.

    `per_fixture_reps` is one {"fixture_id", "n_base", "n_research"} per PAIRED fixture --
    how many measured repeats each cell mean rests on. A fixture with more repeats has a
    better-estimated cell mean and contributes proportionally less variance.
    """
    terms = []
    for r in sorted(per_fixture_reps, key=lambda x: x["fixture_id"]):
        nb, nr = max(int(r.get("n_base", 0)), 0), max(int(r.get("n_research", 0)), 0)
        if nb < 1 or nr < 1:
            continue
        v = sd_used ** 2 * (1.0 / nb + 1.0 / nr)
        terms.append({"fixture_id": r["fixture_id"], "n_base": nb, "n_research": nr,
                      "var_diff": round(v, 8)})
    f = len(terms)
    if not f:
        return {"n_paired_fixtures": 0, "se_paired_mean_diff": None,
                "benchmark": None, "z": Z_MULTIPLIER, "terms": []}
    var_mean = sum(t["var_diff"] for t in terms) / (f * f)
    se = math.sqrt(var_mean)
    return {"n_paired_fixtures": f,
            "sd_used": round(sd_used, 6),
            "se_paired_mean_diff": round(se, 6),
            "z": Z_MULTIPLIER,
            "benchmark": round(Z_MULTIPLIER * se, 6),
            "terms": terms,
            "formula": "benchmark = Z * sqrt( sum_f sd^2 (1/n_base_f + 1/n_research_f) "
                       "/ F^2 )"}


def power_sketch(sd: float, n_fixtures: int, n_repeat_fixtures: int,
                 repeats_per_group: int) -> dict:
    """What paired difference would this battery need in order to clear the benchmark?

    Written and frozen BEFORE spend so §25's "the exact numeric thresholds must be
    justified" is answered with a number rather than a paragraph, and so a reader can see
    in advance whether the design could have detected anything at all.
    """
    reps = []
    fixtures = [f"f{i:02d}" for i in range(n_fixtures)]
    for i, fid in enumerate(fixtures):
        n = repeats_per_group if i < n_repeat_fixtures else 1
        reps.append({"fixture_id": fid, "n_base": n, "n_research": n})
    b = benchmark(max(sd, MIN_SELF_NOISE_SD), reps)
    return {"assumed_within_cell_sd": sd,
            "n_fixtures": n_fixtures,
            "n_repeat_fixtures": n_repeat_fixtures,
            "repeats_per_group": repeats_per_group,
            "se_paired_mean_diff": b["se_paired_mean_diff"],
            "minimum_detectable_paired_difference": b["benchmark"],
            "interpretation":
                f"with a within-cell SD of {sd:.3f} on the qualified rate, this battery "
                f"declares PASS only for a mean paired Arm B - Arm A difference above "
                f"{b['benchmark']}. A true difference smaller than that returns MIXED, "
                f"which is the honest answer for a difference this design cannot separate "
                f"from generator self-noise."}


def paired_differences(cells: dict) -> list:
    """Per-fixture paired differences from cell means. `cells[(fixture, arm)] = [values]`.

    A fixture contributes ONLY when both arms have at least one measured value. §21: the
    primary inference is paired, and an unpaired fixture is not a paired observation.
    """
    fixtures = sorted({f for f, _ in cells})
    out = []
    for f in fixtures:
        b = [v for v in cells.get((f, "base"), []) if v is not None]
        r = [v for v in cells.get((f, "research"), []) if v is not None]
        if not b or not r:
            continue
        mb, mr = statistics.fmean(b), statistics.fmean(r)
        out.append({"fixture_id": f, "n_base": len(b), "n_research": len(r),
                    "base_mean": round(mb, 6), "research_mean": round(mr, 6),
                    "diff": round(mr - mb, 6)})
    return out


def version_stamp() -> dict:
    return {"selfnoise_version": SELFNOISE_VERSION,
            "z_multiplier": Z_MULTIPLIER,
            "min_self_noise_sd": MIN_SELF_NOISE_SD,
            "min_repeat_groups_per_arm": MIN_REPEAT_GROUPS_PER_ARM,
            "benchmark_level": "standard error of the PAIRED MEAN difference, not the "
                               "spread of a single call",
            "is_a_hypothesis_test": False,
            "is_a_noise_exceedance_criterion": True}
