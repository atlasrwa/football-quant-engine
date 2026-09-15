"""The frozen top-level scientific verdict (`v6_verdict_v1`). §21, §22, §25, §26.

    "The primary result must come from frozen gates. The exact numeric thresholds must be
     justified and frozen. Do not choose thresholds after observing results."

This module is the ONLY place a PASS/MIXED/FAIL is decided, and every threshold it reads is
frozen here, before spend, with the reason it takes the value it does. It consumes the
per-response scorecards `v6_scorecard` produced and the self-noise benchmark `v6_selfnoise`
computes, and it produces one verdict. It measures nothing itself -- a verdict that
recomputed a scorecard would be a second opinion on a number already decided.

THE ORDER OF THE GATES, AND WHY IT IS THIS ORDER
------------------------------------------------
    1  EVALUABILITY (§26).   Is there enough evidence to say anything at all? If not, the
                             answer is NON_EVALUABLE and NOTHING ELSE IS COMPUTED. §26 is
                             explicit that a mechanical partial score does not override
                             this: an under-covered run has no scientific verdict, full
                             stop. This is first because a discipline delta or a paired
                             difference on two fixtures is not a finding, and dressing it
                             as one is exactly the apparatus-confounded result §39 ranks
                             below a clean FAIL.

    2  DISCIPLINE (§25).     Did the research arm degrade discipline -- fabricate more,
                             violate the firewall more, break availability more, fail to
                             compile more -- beyond a frozen tolerance? A research arm that
                             asks better questions by breaking more rules has not asked
                             better questions. This gate can force FAIL on its own, before
                             the primary is even consulted, because §25 lists "no material
                             discipline degradation" as a REQUIREMENT, not a tiebreak.

    3  PRIMARY (§21, §22).   The paired Arm B - Arm A qualified-rate difference, compared
                             against the self-noise benchmark at the same aggregation
                             level. PASS only if it clears the benchmark AND discipline
                             held; MIXED if positive but within noise; FAIL if <= 0.

WHY THE EVALUABILITY MINIMUMS ARE WHAT THEY ARE
------------------------------------------------
    MIN_PAIRED_FIXTURES = 8        The battery schedules 10 (`v6_schedule`). Requiring 8
                                   leaves slack for two lost fixtures (a fatal response in
                                   one arm unpairs a fixture) while keeping the paired mean
                                   over enough blocks that one fixture cannot dominate it.
                                   Carried from V5A.2's MIN_PAIRED_FIXTURES unchanged.
    MIN_VALID_RESPONSES_PER_ARM=8  One valid response per paired fixture per arm, at the
                                   same 8. An arm with fewer valid responses than paired
                                   fixtures has holes the pairing cannot fill.
    MIN_REPEAT_GROUPS_PER_ARM = 3  §9's floor, and `v6_selfnoise.MIN_REPEAT_GROUPS_PER_ARM`.
                                   The self-noise benchmark IS the primary's denominator;
                                   an under-powered floor makes the primary unfalsifiable,
                                   which §37 bars from freeze. The schedule provides 4.
    MIN_QUALIFIED_DENOMINATOR = 20 The qualified RATE is n_qualified / n_nonabstaining. A
                                   rate on a tiny denominator is noise. 20 non-abstaining
                                   hypotheses across the run (2 per paired fixture at the
                                   floor) is the least on which a rate is a measurement.

None of these is reachable by tuning after the fact: they are floors on COVERAGE, not on
the result, and a run that meets them can still FAIL.

WHY THE DISCIPLINE TOLERANCE IS 0.05
-------------------------------------
`DISCIPLINE_TOLERANCE = 0.05` is carried from V5A.1/V5A.2 unchanged, where it was fixed
before any V5 call ran. A research arm may differ from the base arm on a discipline rate by
up to five percentage points before the difference is called material. It is applied to the
SIGNED delta (research minus base) so that the research arm doing BETTER on a discipline
axis never counts against it -- only degradation matters.

ZERO SPEND.
"""
from __future__ import annotations

import statistics

from src.research.hypothesis_oos import v6_selfnoise as SN

VERDICT_VERSION = "v6_verdict_v1"

# ---- evaluability minimums (§26). Floors on COVERAGE, frozen before spend. -------------
MIN_PAIRED_FIXTURES = 8
MIN_VALID_RESPONSES_PER_ARM = 8
MIN_REPEAT_GROUPS_PER_ARM = SN.MIN_REPEAT_GROUPS_PER_ARM      # = 3, one source of truth
MIN_QUALIFIED_DENOMINATOR = 20

# ---- discipline (§25). Signed delta tolerance, carried from V5A.1/V5A.2 unchanged. -----
DISCIPLINE_TOLERANCE = 0.05

#: The discipline axes §25 names, each a per-response RATE `v6_scorecard` already produced.
#: All are "lower is better", so a POSITIVE research-minus-base delta is degradation.
DISCIPLINE_AXES = (
    "fabricated_evidence_rate",
    "discipline_violation_rate",
    "redundancy_rate",
)
#: Compilability is "higher is better", so it is handled with its sign flipped: a research
#: arm that compiles LESS often has degraded, which is a positive degradation delta.
COMPILE_AXIS = "compiler_valid_rate"

SCIENTIFIC_STATUSES = ("EVALUABLE", "NON_EVALUABLE")
VERDICTS = ("PASS", "MIXED", "FAIL")


def _valid_scorecards(scorecards: list) -> list:
    """Only responses that were actually measured. A fatal response is not a measurement
    and must never be pooled -- §20's whole reason for the `measured` flag."""
    return [s for s in scorecards if s and s.get("measured")]


def _arm(scorecards: list, arm: str) -> list:
    return [s for s in _valid_scorecards(scorecards)
            if _arm_of(s) == arm]


def _arm_of(scorecard: dict) -> str:
    """A scorecard does not carry its arm (the packet does not serialize it, M-6); the
    driver tags it. Read the tag the driver attached, never infer it."""
    return scorecard.get("arm")


def evaluability(scorecards: list, repeat_groups_per_arm: dict) -> dict:
    """§26. Is the run EVALUABLE? Returns the status AND every unmet minimum, always.

    A run is evaluable only if EVERY minimum holds. `repeat_groups_per_arm` is
    {"base": n, "research": n} counting groups with >= 2 measured repeats.
    """
    valid = _valid_scorecards(scorecards)
    per_arm = {a: _arm(scorecards, a) for a in ("base", "research")}

    # paired fixtures: a fixture is paired iff BOTH arms have a measured response for it
    by_fixture = {}
    for s in valid:
        by_fixture.setdefault(s.get("fixture_id"), set()).add(_arm_of(s))
    paired = sorted(f for f, arms in by_fixture.items()
                    if {"base", "research"} <= arms)

    # qualified denominator: non-abstaining recovered hypotheses across all valid responses
    denom = sum(s.get("n_nonabstaining") or 0 for s in valid)

    unmet = []
    if len(paired) < MIN_PAIRED_FIXTURES:
        unmet.append(f"{len(paired)} paired fixture(s) with a measured response in BOTH "
                     f"arms; need {MIN_PAIRED_FIXTURES}")
    for a in ("base", "research"):
        if len(per_arm[a]) < MIN_VALID_RESPONSES_PER_ARM:
            unmet.append(f"{a} arm has {len(per_arm[a])} valid response(s); "
                         f"need {MIN_VALID_RESPONSES_PER_ARM}")
        rg = int((repeat_groups_per_arm or {}).get(a, 0))
        if rg < MIN_REPEAT_GROUPS_PER_ARM:
            unmet.append(f"{a} arm has {rg} repeat group(s) of size >= 2; "
                         f"need {MIN_REPEAT_GROUPS_PER_ARM}")
    if denom < MIN_QUALIFIED_DENOMINATOR:
        unmet.append(f"qualified-rate denominator is {denom} non-abstaining "
                     f"hypotheses; need {MIN_QUALIFIED_DENOMINATOR}")

    status = "EVALUABLE" if not unmet else "NON_EVALUABLE"
    return {"scientific_status": status, "evaluable": not unmet, "unmet": unmet,
            "n_paired_fixtures": len(paired), "paired_fixtures": paired,
            "n_valid_responses_per_arm": {a: len(per_arm[a]) for a in per_arm},
            "repeat_groups_per_arm": dict(repeat_groups_per_arm or {}),
            "qualified_denominator": denom,
            "minimums": {"paired_fixtures": MIN_PAIRED_FIXTURES,
                         "valid_responses_per_arm": MIN_VALID_RESPONSES_PER_ARM,
                         "repeat_groups_per_arm": MIN_REPEAT_GROUPS_PER_ARM,
                         "qualified_denominator": MIN_QUALIFIED_DENOMINATOR}}


def _pooled_rate(scorecards: list, key: str):
    """Denominator-weighted pooled rate across responses, or None if never measured.

    Weighted by non-abstaining count (the rate's own denominator) rather than a plain mean
    of per-response rates, so a response that adjudicated twelve hypotheses is not given the
    same weight as one that adjudicated two.
    """
    num = den = 0.0
    for s in scorecards:
        r = s.get(key)
        w = s.get("n_nonabstaining") or 0
        if key == "fabricated_evidence_rate":
            w = s.get("n_refs") or 0
        elif key in ("redundancy_rate", "discipline_violation_rate"):
            w = s.get("n_recoverable") or 0
        elif key == COMPILE_AXIS:
            w = s.get("n_nonabstaining") or 0
        if r is None or not w:
            continue
        num += r * w
        den += w
    return (num / den) if den else None


def _compile_rate(scorecards: list):
    """Per-arm compilability = compiler-valid / non-abstaining, pooled. Higher is better."""
    num = den = 0
    for s in scorecards:
        nb = s.get("n_nonabstaining") or 0
        cv = s.get("n_compiler_valid") or 0
        num += cv
        den += nb
    return (num / den) if den else None


def discipline(scorecards: list) -> dict:
    """§25. Signed research-minus-base deltas on every discipline axis, vs tolerance.

    `degraded` is True iff ANY axis degraded by more than the tolerance. The research arm
    doing better on an axis produces a negative delta and never triggers degradation.
    """
    base = _arm(scorecards, "base")
    res = _arm(scorecards, "research")
    axes = {}
    degraded = False
    for key in DISCIPLINE_AXES:
        b, r = _pooled_rate(base, key), _pooled_rate(res, key)
        delta = (r - b) if (b is not None and r is not None) else None
        ax_degraded = delta is not None and delta > DISCIPLINE_TOLERANCE
        degraded = degraded or ax_degraded
        axes[key] = {"base": b, "research": r, "delta": delta,
                     "degraded": ax_degraded, "higher_is_worse": True}
    # compilability, sign-flipped: degradation = research compiles LESS
    b, r = _compile_rate(base), _compile_rate(res)
    delta = (b - r) if (b is not None and r is not None) else None   # positive = worse
    ax_degraded = delta is not None and delta > DISCIPLINE_TOLERANCE
    degraded = degraded or ax_degraded
    axes[COMPILE_AXIS] = {"base": b, "research": r,
                          "degradation_delta_base_minus_research": delta,
                          "degraded": ax_degraded, "higher_is_worse": False}
    return {"tolerance": DISCIPLINE_TOLERANCE, "axes": axes,
            "discipline_degraded": degraded,
            "degraded_axes": sorted(k for k, v in axes.items() if v["degraded"])}


def _cells(scorecards: list) -> dict:
    """(fixture, arm) -> [qualified_rate, ...] over the measured responses of that cell."""
    cells = {}
    for s in _valid_scorecards(scorecards):
        r = s.get("qualified_rate")
        if r is None:
            continue
        cells.setdefault((s.get("fixture_id"), _arm_of(s)), []).append(r)
    return cells


def primary(scorecards: list, self_noise: dict) -> dict:
    """§21/§22. The paired qualified-rate difference vs the self-noise benchmark.

    `self_noise` is `v6_selfnoise.pooled_sd(...)` output. The benchmark is rebuilt here from
    the SAME per-fixture repeat counts the paired differences rest on, so the noise floor
    and the estimate it gates are measured at one aggregation level.
    """
    cells = _cells(scorecards)
    diffs = SN.paired_differences(cells)
    per_fixture_reps = [{"fixture_id": d["fixture_id"],
                         "n_base": d["n_base"], "n_research": d["n_research"]}
                        for d in diffs]
    sd_used = (self_noise or {}).get("sd_used", SN.MIN_SELF_NOISE_SD)
    bench = SN.benchmark(sd_used, per_fixture_reps)
    mean_diff = statistics.fmean([d["diff"] for d in diffs]) if diffs else None
    return {"n_paired_fixtures": len(diffs),
            "paired_differences": diffs,
            "mean_paired_diff": round(mean_diff, 6) if mean_diff is not None else None,
            "self_noise_sd_used": sd_used,
            "benchmark": bench,
            "exceeds_self_noise": (mean_diff is not None and bench.get("benchmark")
                                   is not None and mean_diff > bench["benchmark"])}


def final_verdict(scorecards: list, repeat_groups_per_arm: dict,
                  self_noise: dict) -> dict:
    """The one frozen verdict. EVALUABILITY, then DISCIPLINE, then PRIMARY.

    Returns `scientific_status` (EVALUABLE / NON_EVALUABLE) and, only when EVALUABLE, a
    `scientific_verdict` (PASS / MIXED / FAIL). The two are never collapsed: a run can be
    mechanically scored and still have no scientific verdict, which is §26's whole point.
    """
    elig = evaluability(scorecards, repeat_groups_per_arm)
    out = {"verdict_version": VERDICT_VERSION,
           "scientific_status": elig["scientific_status"],
           "evaluability": elig}

    if not elig["evaluable"]:
        out["scientific_verdict"] = None
        out["verdict_reason"] = ("NON_EVALUABLE: coverage minimums not met, so no "
                                 "PASS/MIXED/FAIL is issued regardless of any partial "
                                 "mechanical score. " + "; ".join(elig["unmet"]))
        return out

    disc = discipline(scorecards)
    prim = primary(scorecards, self_noise)
    out["discipline"] = disc
    out["primary"] = prim

    if disc["discipline_degraded"]:
        out["scientific_verdict"] = "FAIL"
        out["verdict_reason"] = (
            f"FAIL: the research arm degraded discipline beyond tolerance "
            f"{DISCIPLINE_TOLERANCE} on {disc['degraded_axes']}. §25 requires no material "
            f"discipline degradation; a research arm that breaks more rules has not asked "
            f"better questions.")
        return out

    md = prim["mean_paired_diff"]
    bench = prim["benchmark"].get("benchmark")
    if md is None or bench is None:
        out["scientific_verdict"] = "FAIL"
        out["verdict_reason"] = ("FAIL: no paired difference or no benchmark could be "
                                 "computed on evaluable coverage -- an apparatus state, "
                                 "reported as FAIL rather than hidden.")
    elif md <= 0:
        out["scientific_verdict"] = "FAIL"
        out["verdict_reason"] = (
            f"FAIL: mean paired Arm B - Arm A qualified-rate difference is {md} <= 0. "
            f"Richer evidence did not improve the research-question layer.")
    elif prim["exceeds_self_noise"]:
        out["scientific_verdict"] = "PASS"
        out["verdict_reason"] = (
            f"PASS: mean paired difference {md} exceeds the self-noise benchmark {bench}, "
            f"and discipline held. Richer football evidence improved the LLM "
            f"research-question layer beyond what the generator does to itself on "
            f"identical input. This does NOT establish predictive value (§40).")
    else:
        out["scientific_verdict"] = "MIXED"
        out["verdict_reason"] = (
            f"MIXED: mean paired difference {md} is positive but within the self-noise "
            f"benchmark {bench}. The difference cannot be separated from generator "
            f"self-noise at this design's aggregation level -- the honest answer, not a "
            f"failure of the model.")
    return out


def version_stamp() -> dict:
    return {"verdict_version": VERDICT_VERSION,
            "min_paired_fixtures": MIN_PAIRED_FIXTURES,
            "min_valid_responses_per_arm": MIN_VALID_RESPONSES_PER_ARM,
            "min_repeat_groups_per_arm": MIN_REPEAT_GROUPS_PER_ARM,
            "min_qualified_denominator": MIN_QUALIFIED_DENOMINATOR,
            "discipline_tolerance": DISCIPLINE_TOLERANCE,
            "discipline_axes": list(DISCIPLINE_AXES) + [COMPILE_AXIS],
            "gate_order": ["EVALUABILITY (§26)", "DISCIPLINE (§25)", "PRIMARY (§21,§22)"],
            "scientific_statuses": list(SCIENTIFIC_STATUSES),
            "verdicts": list(VERDICTS),
            "primary_endpoint": "paired per-fixture Arm B - Arm A qualified-rate "
                                "difference vs self-noise benchmark",
            "thresholds_frozen_before_spend": True,
            **SN.version_stamp()}
