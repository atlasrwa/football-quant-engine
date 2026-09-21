"""ITEM 6 stand-in rehearsal (ZERO paid calls).

Exercises the FULL Stage-1 apparatus end-to-end on synthetic stand-in mechanism outputs, so
the deterministic pipeline (schema -> formalize -> dedup -> registry -> endpoints -> gate)
is proven before any Sonnet spend. It also runs ARM G-D over the same fixtures for the
control comparison, and computes Pass-A / Pass-B(stub) quality agreement.

The stand-in generator fabricates responses deterministically from each fixture id, mixing:
  - baseline-equivalent mirrors / venue splits / profile splits (F1)
  - provider-unsafe and future-leakage traps (F2)
  - ungrounded (F0)
  - genuinely novel: cross-metric joint, threshold, half-state, two-axis, sequencing (F4)
  - occasional abstention

Two stand-in modes are produced:
  MODE_RICH  : a generator that DOES expand the space (should PASS the gate) — proves the
               apparatus can register a pass.
  MODE_POOR  : a generator that mostly rephrases baselines (should FAIL the gate) — proves
               the apparatus can register a fail (falsifiability of the instrument).
Neither mode is a claim about Sonnet; both are apparatus self-tests.
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, List

from src.research.item6 import control_generator as cg
from src.research.item6 import harness
from src.research.item6.formalizer import formalize
from src.research.item6.quality_protocol import agreement, pass_a_score, pass_b_stub
from src.research.item6.schema import ABSTENTION_TOKEN, K_MECHANISMS_PER_FIXTURE, validate_response

ROOT = "/home/ubuntu"
COHORT = f"{ROOT}/research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json"
OUT = f"{ROOT}/research/item6/out/STANDIN_REHEARSAL.json"

METRICS = ["corner_kicks", "shots_on_target", "possession", "fouls", "big_chances",
           "accurate_crosses", "tackles", "blocks"]


def _pick(fid: str, mod: int, options: list):
    h = int(hashlib.sha256(fid.encode()).hexdigest(), 16)
    return options[(h // (mod + 7)) % len(options)]


def _evrefs(fid: str) -> List[str]:
    return [f"ev_{fid}_a", f"ev_{fid}_b", f"ev_{fid}_c"]


def _mech(mid, stmt, vars_, cond, rel, why, refs, res="match", provreq=None):
    return {
        "mechanism_id_local": mid, "mechanism_statement": stmt,
        "observable_variables": vars_, "conditioning_logic": cond,
        "expected_relationship_to_test": rel, "why_not_baseline_equivalent": why,
        "evidence_refs": refs, "data_resolution_required": res,
        "provider_requirements": provreq or vars_, "self_overlap_with": [],
    }


def _rot(fid: str, salt: str, seq: list):
    h = int(hashlib.sha256((fid + salt).encode()).hexdigest(), 16)
    return seq[h % len(seq)]


def standin_response(fid: str, rich: bool) -> Dict:
    refs = _evrefs(fid)
    # draw a fixture-specific, well-spread metric triple so distinct family signatures
    # dominate across the corpus (a genuinely diverse generator, not a repetitive one).
    h = int(hashlib.sha256(fid.encode()).hexdigest(), 16)
    order = METRICS[(h % len(METRICS)):] + METRICS[:(h % len(METRICS))]
    m0, m1, m2 = order[0], order[1 + (h % 3)], order[2 + (h % 4)]
    m3 = order[3 + (h % 5)]

    # occasional abstention (deterministic, ~1 in 12)
    if int(hashlib.sha256((fid + "abst").encode()).hexdigest(), 16) % 12 == 0:
        return {"fixture_id": fid, "abstention": ABSTENTION_TOKEN, "mechanisms": []}

    if rich:
        axpair = _rot(fid, "ax", [
            ("goals_for", "shots_against"), ("possession_for", "goals_against"),
            ("shots_on_target_for", "shots_on_target_against"), ("goals_against", "possession_for"),
        ])
        mechs = [
            # F4 cross-metric joint (metrics vary per fixture -> distinct signatures)
            _mech(f"{fid}_x1",
                  f"Whether elevated {m0} together with suppressed {m1} jointly relates to {m2}",
                  [m0, m1, m2],
                  "Joint conditioning on two distinct metrics simultaneously",
                  f"Joint high-{m0}/low-{m1} state relates to elevated {m2}",
                  "Combines two distinct metrics in a genuine interaction beyond single-metric grammar",
                  refs),
            # F4 threshold (metric pair varies)
            _mech(f"{fid}_x2",
                  f"Whether {m1} above a threshold saturates and stops increasing {m3}",
                  [m1, m3],
                  "Threshold / nonlinear relationship on a continuous observable",
                  f"{m3} rises with {m1} then saturates beyond a cutoff",
                  "Threshold nonlinearity is not expressible by fixed tercile bands",
                  refs),
            # F4 half-state (metric varies)
            _mech(f"{fid}_x3",
                  f"Whether second-half {m2} rises when the subject was trailing at half-time",
                  [m2, "prior_match_scoreline"],
                  "Second half split conditioned on prior game state (trailing at half-time)",
                  f"Second-half {m2} is elevated in trailing game states",
                  "Half-state / game-state construction not expressible by the grammar",
                  refs, res="half"),
            # F1 baseline mirror (keeps baseline-eq rate realistic and non-zero)
            _mech(f"{fid}_b1",
                  f"Whether the subject's {m0} exceeds what the opponent concedes (mirror)",
                  [m0],
                  "No extra conditioning; for-versus-against on one metric",
                  f"Subject {m0} for exceeds opponent {m0} against",
                  "It is a same-metric mirror",
                  refs),
            # F4 two-axis profile intersection (axis pair + metric vary)
            _mech(f"{fid}_x4",
                  f"Whether {m3} shifts against opponents both high on {axpair[0]} and low on {axpair[1]} jointly",
                  [m3],
                  f"Intersection of two distinct opponent-profile axes ({axpair[0]} and {axpair[1]}) simultaneously",
                  f"{m3} shifts in the joint two-axis profile region",
                  "Two-axis opponent-profile intersection is excluded by the grammar",
                  refs),
        ]
    else:
        # MODE_POOR: mostly rephrased baselines + traps
        mechs = [
            _mech(f"{fid}_p1",
                  f"Whether the subject's {m0} exceeds the opponent's conceded {m0} (mirror)",
                  [m0], "for versus against on one metric", f"{m0} for vs against",
                  "mirror", refs),
            _mech(f"{fid}_p2",
                  f"Whether the subject's {m0} differs at home versus away",
                  [m0, "venue_home_away"], "venue split only", "home vs away differ",
                  "pure venue split", refs),
            _mech(f"{fid}_p3",
                  f"Whether recent {m0} deviates from long-run {m0}",
                  [m0], "recent window vs long run", "recent differs from long run",
                  "form / recent-vs-long", refs),
            # trap: provider unsafe
            _mech(f"{fid}_p4",
                  f"Whether expected lineup changes shift {m0}",
                  [m0], "condition on predicted xi injury news", "directional",
                  "lineup", refs),
            # trap: future leakage
            _mech(f"{fid}_p5",
                  f"Whether the closing line predicts {m0}",
                  [m0], "use closing odds settlement", "directional", "x", refs),
        ]
    return {"fixture_id": fid, "mechanisms": mechs}


def main():
    cohort = json.load(open(COHORT))
    fixtures = [f["fixture_id"] for f in cohort["fixtures"]]
    allowed = {f: _evrefs(f) for f in fixtures}

    results = {}
    for mode, rich in (("MODE_RICH", True), ("MODE_POOR", False)):
        responses = [standin_response(f, rich) for f in fixtures]
        res = harness.run_stage1(responses, allowed_evidence_refs_by_fixture=allowed)

        # quality Pass A / Pass B(stub) agreement over all mechanisms
        a_scores, b_scores = [], []
        for resp in responses:
            vr = validate_response(resp)
            for m in vr.mechanisms:
                f = formalize(m, allowed_evidence_refs=allowed[resp["fixture_id"]])
                a_scores.append(pass_a_score(m, f))
                b_scores.append(pass_b_stub(m, f))
        agr = agreement(a_scores, b_scores)

        results[mode] = {
            "gate_passed": res["gate"]["passed"],
            "failed_primary": res["gate"]["failed_primary"],
            "endpoints": res["endpoints"],
            "n_novel_families": res["novel_family_registry"]["n_families"],
            "quality_pass_agreement": agr,
            "validation_error_fixtures": len(res["validation_errors"]),
        }

    # ARM G-D control over the same fixtures (all should be baseline-equivalent)
    gd_responses = []
    for f in fixtures:
        mechs = cg.generate_families(f, METRICS, K_MECHANISMS_PER_FIXTURE)
        gd_responses.append({
            "fixture_id": f,
            "mechanisms": [m.to_dict() for m in mechs],
        })
    gd_allowed = {}
    for resp in gd_responses:
        gd_allowed[resp["fixture_id"]] = [
            r for m in resp["mechanisms"] for r in m["evidence_refs"]]
    gd_res = harness.run_stage1(gd_responses, allowed_evidence_refs_by_fixture=gd_allowed)
    results["ARM_GD_CONTROL"] = {
        "gate_passed": gd_res["gate"]["passed"],
        "endpoints": gd_res["endpoints"],
        "n_novel_families": gd_res["novel_family_registry"]["n_families"],
        "note": "Deterministic control draws only from baseline grammar; expected 0 novel "
                "families, gate FAIL by construction. Establishes the covered space G-L must exceed.",
    }

    summary = {
        "standin_rehearsal_version": "item6_standin_v1",
        "n_fixtures": len(fixtures),
        "k_mechanisms_per_fixture": K_MECHANISMS_PER_FIXTURE,
        "made_paid_call": False,
        "reads_outcomes": False,
        "results": results,
    }
    import os
    os.makedirs(f"{ROOT}/research/item6/out", exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(summary, fh, indent=1)

    print(f"[standin] wrote {OUT}")
    for mode in ("MODE_RICH", "MODE_POOR", "ARM_GD_CONTROL"):
        r = results[mode]
        print(f"  {mode}: gate_passed={r['gate_passed']} "
              f"novel_families={r['n_novel_families']} "
              f"novel_rate={r['endpoints']['novel_measurable_family_rate']} "
              f"be_rate={r['endpoints']['baseline_equivalent_rate']} "
              f"dup_rate={r['endpoints']['semantic_duplicate_rate']}")


if __name__ == "__main__":
    main()
