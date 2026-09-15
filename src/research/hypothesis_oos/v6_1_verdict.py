"""V6.1 corrected verdict (`v6_1_verdict_v1`). Evaluator REPAIR only.

This is a NEW module. It does NOT edit the frozen `v6_verdict` (which stays exactly as V6
executed it). It reuses every frozen threshold, gate order, evaluability rule, self-noise
estimator and primary-endpoint definition VERBATIM from `v6_verdict`, and changes exactly
one thing plus adds one safety layer:

  1. REPAIR: `compiler_valid_rate` numerator is restricted to NON-ABSTAINING compiler-valid
     hypotheses, so it can never exceed its non-abstaining denominator and can never be > 1.
     (V6 counted compilable abstentions in the numerator against a non-abstaining
     denominator, producing 1.153 for the higher-abstaining base arm and a spurious FAIL.)

  2. CONTRACTS: every rate consumed by the discipline gate and every per-response rate is
     checked against `v6_1_metrics` contracts IN THE PRODUCTION PATH. An impossible metric
     raises `MetricContractViolation`, which this module maps to EVALUATOR_INVALID -- an
     apparatus state -- never a scientific PASS/MIXED/FAIL.

Nothing else changes: thresholds, tolerance (0.05), Z, floors, minimum coverage, gate order
(EVALUABILITY -> DISCIPLINE -> PRIMARY) and PASS/MIXED/FAIL semantics are the frozen ones,
imported from `v6_verdict`. This module is the repaired evaluator V6.1 will freeze.

ZERO SPEND.
"""
from __future__ import annotations

from src.research.hypothesis_oos import v6_1_metrics as MC
from src.research.hypothesis_oos import v6_selfnoise as SN
from src.research.hypothesis_oos import v6_verdict as V6

VERDICT_VERSION = "v6_1_verdict_v1"

# Reused VERBATIM from the frozen evaluator -- one source of truth, no re-tuning.
MIN_PAIRED_FIXTURES = V6.MIN_PAIRED_FIXTURES
MIN_VALID_RESPONSES_PER_ARM = V6.MIN_VALID_RESPONSES_PER_ARM
MIN_REPEAT_GROUPS_PER_ARM = V6.MIN_REPEAT_GROUPS_PER_ARM
MIN_QUALIFIED_DENOMINATOR = V6.MIN_QUALIFIED_DENOMINATOR
DISCIPLINE_TOLERANCE = V6.DISCIPLINE_TOLERANCE
DISCIPLINE_AXES = V6.DISCIPLINE_AXES
COMPILE_AXIS = V6.COMPILE_AXIS

EVALUATOR_INVALID = "EVALUATOR_INVALID"


def _nonabstaining_compiler_valid(scorecard: dict) -> int:
    """The CORRECTED compiler numerator for one response: hypotheses that are BOTH
    non-abstaining AND compiler-valid. Read off the per-hypothesis rows the frozen scorecard
    already records, so no frozen module is edited and the count is auditable."""
    n = 0
    for h in scorecard.get("per_hypothesis") or []:
        if (not h.get("abstaining")) and h.get("compiler_valid") is True:
            n += 1
    return n


def compile_rate(scorecards: list):
    """Pooled non-abstaining compilability per arm, REPAIRED and contract-checked.

    numerator   = sum of non-abstaining compiler-valid hypotheses
    denominator = sum of non-abstaining hypotheses (n_nonabstaining)
    Enforces 0 <= num <= den and returns None on an empty denominator.
    """
    num = den = 0
    for s in scorecards:
        den += int(s.get("n_nonabstaining") or 0)
        num += _nonabstaining_compiler_valid(s)
    return MC.check_rate("compiler_valid_rate", num, den)


def _pooled_rate_checked(scorecards: list, key: str):
    """The frozen denominator-weighted pooled rate, with a contract check on the result."""
    val = V6._pooled_rate(scorecards, key)
    return MC.check_value_in_unit_interval(key, val)


def discipline(scorecards: list) -> dict:
    """§25 discipline, with the REPAIRED compiler axis and contract enforcement.

    Identical structure and tolerance to the frozen `v6_verdict.discipline`; the only change
    is that `compile_rate` uses the corrected non-abstaining numerator. Every rate is
    contract-checked; an impossible rate raises MetricContractViolation (caught by
    `final_verdict` and mapped to EVALUATOR_INVALID).
    """
    base = V6._arm(scorecards, "base")
    res = V6._arm(scorecards, "research")
    axes = {}
    degraded = False
    for key in DISCIPLINE_AXES:
        b, r = _pooled_rate_checked(base, key), _pooled_rate_checked(res, key)
        delta = (r - b) if (b is not None and r is not None) else None
        MC.check_signed_rate_delta(key + "_delta", delta)
        ax_degraded = delta is not None and delta > DISCIPLINE_TOLERANCE
        degraded = degraded or ax_degraded
        axes[key] = {"base": b, "research": r, "delta": delta,
                     "degraded": ax_degraded, "higher_is_worse": True}
    # compilability, REPAIRED numerator, sign-flipped: degradation = research compiles LESS
    b, r = compile_rate(base), compile_rate(res)
    delta = (b - r) if (b is not None and r is not None) else None
    MC.check_signed_rate_delta(COMPILE_AXIS + "_delta", delta)
    ax_degraded = delta is not None and delta > DISCIPLINE_TOLERANCE
    degraded = degraded or ax_degraded
    axes[COMPILE_AXIS] = {"base": b, "research": r,
                          "degradation_delta_base_minus_research": delta,
                          "degraded": ax_degraded, "higher_is_worse": False}
    return {"tolerance": DISCIPLINE_TOLERANCE, "axes": axes,
            "discipline_degraded": degraded,
            "degraded_axes": sorted(k for k, v in axes.items() if v["degraded"])}


def _check_per_response_rates(scorecards: list):
    """Contract-check every per-response rate in the registry that a scorecard carries.
    An out-of-range rate is an evaluator/apparatus invalidity, caught by final_verdict."""
    rate_keys = [k for k, v in MC.REGISTRY.items()
                 if v["type"] == MC.TYPE_RATE and k != COMPILE_AXIS]
    for s in scorecards:
        if not (s and s.get("measured")):
            continue
        for k in rate_keys:
            if k in s:
                MC.check_value_in_unit_interval(k, s.get(k))


def final_verdict(scorecards: list, repeat_groups_per_arm: dict,
                  self_noise: dict) -> dict:
    """The repaired verdict. Same gates and order as frozen; corrected compiler axis;
    contract-enforced. Returns EVALUATOR_INVALID (apparatus) if any metric contract breaks,
    NEVER a scientific verdict built on an impossible metric.
    """
    try:
        _check_per_response_rates(scorecards)

        elig = V6.evaluability(scorecards, repeat_groups_per_arm)
        out = {"verdict_version": VERDICT_VERSION,
               "scientific_status": elig["scientific_status"],
               "evaluability": elig}
        if not elig["evaluable"]:
            out["scientific_verdict"] = None
            out["verdict_reason"] = ("NON_EVALUABLE: coverage minimums not met. "
                                     + "; ".join(elig["unmet"]))
            return out

        disc = discipline(scorecards)                 # REPAIRED + contract-checked
        prim = V6.primary(scorecards, self_noise)      # frozen primary, unchanged
        MC.check_value_in_unit_interval("primary_mean_paired_diff_abs_guard",
                                        abs(prim["mean_paired_diff"])
                                        if prim["mean_paired_diff"] is not None else None)
        out["discipline"] = disc
        out["primary"] = prim

        if disc["discipline_degraded"]:
            out["scientific_verdict"] = "FAIL"
            out["verdict_reason"] = (
                f"FAIL: research arm degraded discipline beyond tolerance "
                f"{DISCIPLINE_TOLERANCE} on {disc['degraded_axes']}.")
            return out

        md = prim["mean_paired_diff"]
        bench = prim["benchmark"].get("benchmark")
        if md is None or bench is None:
            out["scientific_verdict"] = "FAIL"
            out["verdict_reason"] = ("FAIL: no paired difference or benchmark on evaluable "
                                     "coverage (apparatus state, reported as FAIL).")
        elif md <= 0:
            out["scientific_verdict"] = "FAIL"
            out["verdict_reason"] = (f"FAIL: mean paired B-A qualified-rate diff {md} <= 0.")
        elif prim["exceeds_self_noise"]:
            out["scientific_verdict"] = "PASS"
            out["verdict_reason"] = (
                f"PASS: mean paired difference {md} exceeds the self-noise benchmark "
                f"{bench}, and discipline held.")
        else:
            out["scientific_verdict"] = "MIXED"
            out["verdict_reason"] = (
                f"MIXED: mean paired difference {md} is positive but within the self-noise "
                f"benchmark {bench}.")
        return out
    except MC.MetricContractViolation as exc:
        return {"verdict_version": VERDICT_VERSION,
                "scientific_status": EVALUATOR_INVALID,
                "scientific_verdict": None,
                "evaluator_invalid": True,
                "metric_contract_violation": {"metric": exc.metric_name,
                                              "detail": exc.detail},
                "verdict_reason": (f"EVALUATOR_INVALID: metric contract violated "
                                   f"({exc.metric_name}). No scientific verdict is issued on "
                                   f"an impossible metric.")}


def version_stamp() -> dict:
    return {"verdict_version": VERDICT_VERSION,
            "reuses_frozen": V6.VERDICT_VERSION,
            "repair": "compiler_valid_rate numerator = non-abstaining AND compiler_valid",
            "contracts_enforced_in_production_path": True,
            "evaluator_invalid_status": EVALUATOR_INVALID,
            "thresholds_unchanged": True,
            "min_paired_fixtures": MIN_PAIRED_FIXTURES,
            "min_valid_responses_per_arm": MIN_VALID_RESPONSES_PER_ARM,
            "min_repeat_groups_per_arm": MIN_REPEAT_GROUPS_PER_ARM,
            "min_qualified_denominator": MIN_QUALIFIED_DENOMINATOR,
            "discipline_tolerance": DISCIPLINE_TOLERANCE,
            "gate_order": ["EVALUABILITY", "DISCIPLINE", "PRIMARY"],
            **MC.version_stamp(),
            **SN.version_stamp()}
