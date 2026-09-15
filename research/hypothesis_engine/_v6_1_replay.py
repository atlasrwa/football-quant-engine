"""V6.1 POSTHOC CORRECTED-EVALUATOR REPLAY over the immutable 36 V6 raw scores. ZERO SPEND.

This runs the REPAIRED evaluator (`v6_1_verdict.final_verdict`) on V6's frozen
`execution/scores.json`. It is DIAGNOSTIC ONLY. Its purpose (Task 6) is to:
  * confirm the compiler_valid_rate repair (base rate no longer > 1);
  * measure how the repaired metric behaves;
  * validate evaluator mechanics end to end on real data;
  * expose any second-order evaluator defects (Task 7).

Its output is labelled, permanently, as:
    V6_POSTHOC_CORRECTED_EVALUATOR_REPLAY / NON_CONFIRMATORY / DIAGNOSTIC_ONLY.

It is NEVER a V6 verdict, NEVER a corrected official verdict, and its outcome MUST NOT be
used to choose any V6.1 threshold, fixture, model or score. It does not touch V6 artifacts;
it only reads scores.json and writes a new diagnostic file.
"""
from __future__ import annotations

import hashlib
import json
import sys

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_oos import v6_1_verdict as V61
from src.research.hypothesis_oos import v6_selfnoise as SN
from src.research.hypothesis_oos import v6_verdict as V6

OUT = "/home/ubuntu/research/hypothesis_oos/out/v6"
EXEC = f"{OUT}/execution"
V6_1_OUT = "/home/ubuntu/research/hypothesis_oos/out/v6_1"

# The immutable V6 scores this replay is allowed to read (verified before use).
SCORES_SHA = "4ba5f37b98aec2ad2a04cf62f3b40587786a907dd6abe19c6939d2f26cf5ec3c"


def _sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _self_noise_groups(scorecards: list) -> list:
    cells = {}
    for s in scorecards:
        if not (s and s.get("measured")):
            continue
        r = s.get("qualified_rate")
        if r is None:
            continue
        cells.setdefault((s.get("fixture_id"), s.get("arm")), []).append(r)
    return [{"fixture_id": f, "arm": a, "values": v} for (f, a), v in cells.items()]


def _old_compile_rate(scorecards, arm):
    """Reproduce the DEFECTIVE V6 compiler rate on one arm, for the before/after table."""
    sc = [s for s in scorecards if s and s.get("measured") and s.get("arm") == arm]
    num = sum(int(s.get("n_compiler_valid") or 0) for s in sc)
    den = sum(int(s.get("n_nonabstaining") or 0) for s in sc)
    return (num, den, (num / den) if den else None)


def _second_order_audit(scorecards, verdict) -> dict:
    """Task 7. Scan the corrected replay for further evaluator defects, over real data."""
    valid = [s for s in scorecards if s and s.get("measured")]
    findings = []

    # 1. every per-response rate must be in [0,1] or None
    rate_keys = ["qualified_rate", "evidence_specific_qualified_rate",
                 "valid_evidence_reference_rate", "fabricated_evidence_rate",
                 "abstention_rate", "grounded_abstention_rate",
                 "meaningful_interaction_rate", "redundancy_rate",
                 "discipline_violation_rate"]
    for s in valid:
        for k in rate_keys:
            v = s.get(k)
            if v is not None and not (0.0 <= v <= 1.0):
                findings.append(f"per_response rate {k}={v} out of [0,1] "
                                f"(fixture {s.get('fixture_id')}, arm {s.get('arm')})")

    # 2. numerator<=denominator on every response's compiler count (repaired numerator)
    for s in valid:
        nb = int(s.get("n_nonabstaining") or 0)
        na_cv = sum(1 for h in (s.get("per_hypothesis") or [])
                    if (not h.get("abstaining")) and h.get("compiler_valid") is True)
        if na_cv > nb:
            findings.append(f"repaired compiler numerator {na_cv} > denominator {nb} "
                            f"(fixture {s.get('fixture_id')}, arm {s.get('arm')})")

    # 3. arm-asymmetric eligibility: are the two arms measured on the same fixtures?
    by_arm = {"base": set(), "research": set()}
    for s in valid:
        by_arm.setdefault(s.get("arm"), set()).add(s.get("fixture_id"))
    only_base = sorted(by_arm["base"] - by_arm["research"])
    only_res = sorted(by_arm["research"] - by_arm["base"])
    arm_asymmetry = {"fixtures_only_in_base": only_base,
                     "fixtures_only_in_research": only_res}

    # 4. Simpson-like check on the DECISIVE compiler axis: does the pooled (hypothesis-
    #    weighted) sign agree with the fixture-balanced (per-fixture mean) sign?
    disc = verdict.get("discipline", {})
    cv = disc.get("axes", {}).get("compiler_valid_rate", {})
    pooled_delta = cv.get("degradation_delta_base_minus_research")
    fb = _fixture_balanced_compile_delta(valid)
    simpson = {
        "pooled_hypothesis_weighted_delta_base_minus_research": pooled_delta,
        "fixture_balanced_delta_base_minus_research": fb["delta"],
        "signs_agree": (pooled_delta is None or fb["delta"] is None
                        or (pooled_delta >= 0) == (fb["delta"] >= 0)),
        "note": "diagnostic only; the frozen decisive gate is hypothesis-pooled (unchanged)."}

    # 5. abstention asymmetry between arms (the driver of the original defect)
    def _abst(arm):
        sc = [s for s in valid if s.get("arm") == arm]
        na = sum(int(s.get("n_abstentions") or 0) for s in sc)
        rec = sum(int(s.get("n_recoverable") or 0) for s in sc)
        return {"abstentions": na, "recoverable": rec,
                "abstention_rate": (na / rec) if rec else None}
    abst = {a: _abst(a) for a in ("base", "research")}

    # 6. null-treated-as-zero: any rate that is 0.0 where denominator was actually empty?
    #    (the scorecard already returns None on empty denominator; verify none are 0.0-with
    #     -empty-denominator by checking the count fields)
    null_as_zero = []
    for s in valid:
        if s.get("n_nonabstaining") == 0 and s.get("qualified_rate") == 0.0:
            null_as_zero.append(s.get("fixture_id"))

    # 7. duplicate scorecards (same fixture+arm+rep+seq appearing twice). Self-noise
    #    repeats share (fixture, arm) legitimately, so the observation identity includes the
    #    repeat index and the frozen execution sequence number.
    seen, dups = set(), []
    for s in valid:
        key = (s.get("fixture_id"), s.get("arm"), s.get("rep"), s.get("_seq"))
        if key in seen:
            dups.append(key)
        seen.add(key)

    return {
        "n_findings": len(findings),
        "findings": findings,
        "arm_asymmetric_eligibility": arm_asymmetry,
        "simpson_check_compiler_axis": simpson,
        "abstention_by_arm": abst,
        "null_treated_as_zero_fixtures": null_as_zero,
        "duplicate_scorecards": [list(d) for d in dups],
        "material_second_order_defect_found": bool(findings) or bool(null_as_zero)
        or bool(dups),
    }


def _fixture_balanced_compile_delta(valid) -> dict:
    """Diagnostic fixture-balanced version of the hypothesis-pooled compiler axis.

    For each fixture, compute the corrected compiler rate per arm (non-abstaining valid /
    non-abstaining), average over the arm's responses for that fixture, take base-minus-
    research per fixture, then average over fixtures. Reported for the Simpson check only;
    the frozen decisive gate stays hypothesis-pooled and is NOT replaced.
    """
    import statistics
    by_cell = {}
    for s in valid:
        nb = int(s.get("n_nonabstaining") or 0)
        na_cv = sum(1 for h in (s.get("per_hypothesis") or [])
                    if (not h.get("abstaining")) and h.get("compiler_valid") is True)
        if nb == 0:
            continue
        by_cell.setdefault((s.get("fixture_id"), s.get("arm")), []).append(na_cv / nb)
    fixtures = sorted({f for (f, a) in by_cell})
    per_fix = []
    for f in fixtures:
        b = by_cell.get((f, "base"))
        r = by_cell.get((f, "research"))
        if b and r:
            per_fix.append(statistics.fmean(b) - statistics.fmean(r))
    return {"delta": (statistics.fmean(per_fix) if per_fix else None),
            "n_fixtures": len(per_fix)}


def main() -> int:
    assert _sha(f"{EXEC}/scores.json") == SCORES_SHA, \
        "scores.json hash mismatch -- refusing to replay against a changed artifact"

    scores = json.load(open(f"{EXEC}/scores.json"))
    # Carry the outer identity (rep/seq) onto the scorecard so the duplicate check keys on
    # the true observation identity, not just (fixture, arm) -- self-noise repeats share
    # (fixture, arm) legitimately and must NOT be flagged as duplicates.
    scorecards = []
    for s in scores:
        sc = dict(s["scorecard"])
        sc.setdefault("rep", s.get("rep"))
        sc["_seq"] = s.get("seq")
        scorecards.append(sc)

    groups = _self_noise_groups(scorecards)
    self_noise = SN.pooled_sd(groups)
    repeat_groups_per_arm = self_noise["n_groups_by_arm"]

    # The frozen (defective) verdict, recomputed here ONLY to show the before/after, read
    # from the immutable stored verdict for the authoritative value.
    frozen = json.load(open(f"{EXEC}/V6_VERDICT.json"))["verdict"]

    # THE REPAIRED EVALUATOR on the same immutable scores.
    corrected = V61.final_verdict(scorecards, repeat_groups_per_arm, self_noise)

    old = {a: _old_compile_rate(scorecards, a) for a in ("base", "research")}
    audit = _second_order_audit(scorecards, corrected)

    doc = {
        "label": "V6_POSTHOC_CORRECTED_EVALUATOR_REPLAY",
        "status_tags": ["NON_CONFIRMATORY", "DIAGNOSTIC_ONLY"],
        "is_v6_scientific_verdict": False,
        "is_v6_1_confirmatory_evidence": False,
        "must_not_tune_v6_1": True,
        "scores_source": f"{EXEC}/scores.json",
        "scores_sha256": SCORES_SHA,
        "frozen_evaluator": {
            "version": "v6_verdict_v1",
            "scientific_status": frozen["scientific_status"],
            "scientific_verdict": frozen["scientific_verdict"],
            "compiler_valid_rate_base": frozen["discipline"]["axes"][
                "compiler_valid_rate"]["base"],
            "compiler_valid_rate_research": frozen["discipline"]["axes"][
                "compiler_valid_rate"]["research"],
            "compiler_degradation_delta": frozen["discipline"]["axes"][
                "compiler_valid_rate"]["degradation_delta_base_minus_research"],
            "note": "IMMUTABLE. This is V6's real, permanent mechanical verdict."},
        "old_defective_compiler_rate": {
            a: {"numerator_all_compilable": old[a][0],
                "denominator_nonabstaining": old[a][1], "rate": old[a][2]}
            for a in old},
        "corrected_evaluator": {
            "version": corrected["verdict_version"],
            "scientific_status": corrected["scientific_status"],
            "scientific_verdict": corrected.get("scientific_verdict"),
            "verdict_reason": corrected.get("verdict_reason"),
            "discipline": corrected.get("discipline"),
            "primary": corrected.get("primary"),
            "evaluator_invalid": corrected.get("evaluator_invalid", False)},
        "second_order_audit": audit,
        "interpretation": (
            "DIAGNOSTIC ONLY. The repair removes the compiler_valid_rate>1 defect: the "
            "corrected base compiler rate is <=1 and the decisive spurious FAIL gate no "
            "longer fires from that axis. This replay is NOT a verdict on V6 and is NOT "
            "confirmatory evidence for V6.1. V6's mechanical verdict remains FAIL; V6's "
            "scientific interpretability remains COMPROMISED; V6.1 requires fresh model "
            "observations."),
    }
    import os
    os.makedirs(V6_1_OUT, exist_ok=True)
    outpath = f"{V6_1_OUT}/V6_POSTHOC_CORRECTED_REPLAY.json"
    with open(outpath, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True, default=str)

    print("=== V6 POSTHOC CORRECTED EVALUATOR REPLAY (DIAGNOSTIC ONLY, NON_CONFIRMATORY) ===")
    print("frozen (IMMUTABLE) verdict :", frozen["scientific_verdict"],
          "| compiler base", round(frozen["discipline"]["axes"]["compiler_valid_rate"][
              "base"], 4), "research", frozen["discipline"]["axes"][
              "compiler_valid_rate"]["research"])
    print("OLD defective compiler rate: base", old["base"], "research", old["research"])
    cc = corrected["discipline"]["axes"]["compiler_valid_rate"]
    print("corrected compiler rate    : base", cc["base"], "research", cc["research"],
          "delta(b-r)", cc["degradation_delta_base_minus_research"])
    print("corrected status/verdict   :", corrected["scientific_status"], "/",
          corrected.get("scientific_verdict"))
    print("corrected verdict reason   :", corrected.get("verdict_reason"))
    print("second-order material defect found:",
          audit["material_second_order_defect_found"], "| findings:", audit["n_findings"])
    print("simpson signs agree        :",
          audit["simpson_check_compiler_axis"]["signs_agree"])
    print("wrote", outpath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
