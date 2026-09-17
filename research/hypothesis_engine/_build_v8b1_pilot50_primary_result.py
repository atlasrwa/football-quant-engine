"""Freeze the V8B.1 PILOT-50 PRIMARY RESULT, computed ONLY from the frozen scorer output
(V8B1_PILOT50_OOS_RESULTS.json). Written BEFORE any qualitative research-trace review, so the
numeric result can never be reinterpreted in light of the traces.

The pilot's measured result is a NULL-EVALUABILITY outcome: under the frozen scorer exactly as
committed, 0 selections in any arm reach SCORE_OK, so both primary endpoints have 0 evaluable
paired fixtures. The documented root cause is a pre-existing latent defect in the frozen
scorer's support gate (unique_teams hardcoded to 1 vs a gate requiring >=6). This freeze does
NOT modify the scorer; it records the result as-measured.
"""
from __future__ import annotations

import hashlib
import json

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
OOS = f"{ENG}/V8B1_PILOT50_OOS_RESULTS.json"
OUT = f"{ENG}/V8B1_PILOT50_PRIMARY_RESULT.json"

CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def _sha_obj(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _sha_file(p):
    with open(f"{ROOT}/{p}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    d = json.load(open(OOS))
    e1 = d["endpoint1_research_yield_sonnet"]
    e2 = d["endpoint2_sonnet_vs_blind"]
    e3 = d["endpoint3_sonnet_vs_heuristic"]

    champ_ok = _sha_file("data/discovery/pilotC_stat_mixer.json") == CHAMPION_EXPECTED

    result = {
        "result_version": "v8b1_pilot50_primary_result_v1",
        "frozen_before_trace_review": True,
        "cohort": "OUTCOME_EXPOSED_PILOT",
        "n_target_fixtures": 50,
        "oos_results_source": "research/hypothesis_engine/V8B1_PILOT50_OOS_RESULTS.json",
        "oos_results_sha256": _sha_file("research/hypothesis_engine/V8B1_PILOT50_OOS_RESULTS.json"),
        "selection_freeze_self_hash": d["freeze_self_hash"],
        "scorer_version": d["scorer_version"],

        "primary_finding": "NULL_EVALUABILITY_UNDER_FROZEN_SCORER",
        "primary_finding_plain": "Under the frozen V8B.1 fixture-level scorer exactly as "
            "committed, zero selections in ANY arm (Sonnet, matched-blind R, heuristic H) reach "
            "SCORE_OK, so neither primary endpoint has a single evaluable paired fixture. The "
            "pilot therefore cannot measure Sonnet vs either control at the fixture level.",

        # ---- Endpoint 1: Sonnet research yield (attrition funnel) ----
        "endpoint1_research_yield": {
            "selected": e1["selected"],
            "canonical_resolved": e1["canonical_resolved"],
            "measurable_named_status": e1["canonical_resolved"],
            "non_ok_measured": e1["non_ok_measured"],
            "score_ok": e1["score_ok"],
            "note": "all 249 valid Sonnet selections resolved to canonical IRs and reached a "
                    "named terminal scorer status (no exceptions); 0 were SCORE_OK.",
        },

        # ---- Endpoint 2: Sonnet vs matched blind ----
        "endpoint2_sonnet_vs_blind": {
            "evaluable_paired_fixtures": e2["n_paired_fixtures"],
            "point_estimate": e2.get("point_estimate"),
            "primary_p_value": e2.get("primary_p_value"),
            "inference_status": e2.get("inference_status"),
        },
        # ---- Endpoint 3: Sonnet vs heuristic ----
        "endpoint3_sonnet_vs_heuristic": {
            "evaluable_paired_fixtures": e3["n_paired_fixtures"],
            "point_estimate": e3.get("point_estimate"),
            "primary_p_value": e3.get("primary_p_value"),
            "inference_status": e3.get("inference_status"),
        },

        "evaluable_sonnet_vs_blind": e2["n_paired_fixtures"],
        "evaluable_sonnet_vs_heuristic": e3["n_paired_fixtures"],
        "sonnet_vs_blind": "UNDEFINED_NO_EVALUABLE_FIXTURES",
        "sonnet_vs_heuristic": "UNDEFINED_NO_EVALUABLE_FIXTURES",

        # ---- Root cause (diagnosed, factual, code-level) ----
        "root_cause": {
            "classification": "PRE_EXISTING_LATENT_DEFECT_IN_FROZEN_SCORER",
            "mechanism": "scorer.score_fixture (src/research/hypothesis_v8b1/scorer.py:141-144) "
                "calls V7PIT.classify_support(..., unique_teams=1, ...) with unique_teams "
                "HARDCODED to 1 (correct for a single-team fixture-level cohort). The reused "
                "frozen support gate (src/research/hypothesis_v7/pit.py:96-98) sets SUPPORT_LOW "
                "whenever raw_n<20 OR unique_fixtures<15 OR unique_teams<MIN_UNIQUE_TEAMS(=6). "
                "Because unique_teams==1 < 6 ALWAYS, classify_support can never return "
                "ADEQUATE_SUPPORT, so score_fixture can never return SCORE_OK at the fixture "
                "level -- independent of history depth or which arm selected the hypothesis.",
            "independent_confirmation": [
                "0 SCORE_OK across ALL three arms including the deterministic heuristic that "
                "selects the highest-coverage/simplest hypotheses.",
                "the frozen scorer test battery (tests/research/hypothesis_v8b1/test_scorer.py) "
                "never asserts a real SCORE_OK is produced -- only that status is one of the four "
                "named terminal statuses -- so SCORE_OK reachability was never proven pre-freeze.",
                "target observed values WERE read (only 2 'observed unavailable' refusals across "
                "all arms), so the seal opened real data and the evaluation driver is correct.",
            ],
            "not_caused_by": [
                "the evaluation driver (it reproduces the frozen apparatus call-for-call)",
                "thin unconditional team history (pilot home/away prior_n min 20 / median 27 / "
                "max 36, satisfying the manifest's >=20 guarantee)",
                "the Sonnet selections themselves (the defect is arm-independent)",
                "the pilot cohort choice",
            ],
        },

        "interpretation_inputs": {
            "direction": "N/A -- no evaluable comparison exists",
            "magnitude": "N/A -- point estimates undefined (0 paired fixtures)",
            "uncertainty": "total -- the apparatus cannot produce a measurement",
            "evaluable_N_blind": e2["n_paired_fixtures"],
            "evaluable_N_heuristic": e3["n_paired_fixtures"],
        },

        "champion_unchanged": champ_ok,
        "champion_sha256": CHAMPION_EXPECTED,
        "no_scorer_change_made": True,
        "no_trace_reviewed_before_this_freeze": True,
        "target_outcomes_opened_fixture_count": d["outcome_seal_crossed_count"],
    }
    result["primary_result_self_hash"] = _sha_obj(result)
    with open(OUT, "w") as f:
        json.dump(result, f, indent=1, default=str)

    print(f"[primary] wrote {OUT}")
    print(f"[primary] self_hash={result['primary_result_self_hash']}")
    print(f"[primary] finding={result['primary_finding']}")
    print(f"[primary] E1 yield: selected={result['endpoint1_research_yield']['selected']} "
          f"score_ok={result['endpoint1_research_yield']['score_ok']}")
    print(f"[primary] E2 evaluable={result['evaluable_sonnet_vs_blind']} "
          f"E3 evaluable={result['evaluable_sonnet_vs_heuristic']}")
    print(f"[primary] champion_unchanged={champ_ok}")


if __name__ == "__main__":
    main()
