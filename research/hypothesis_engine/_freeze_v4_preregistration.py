"""Emit the FROZEN V4 preregistration artifact. ZERO SPEND.

Reads only the immutable V3 outputs and projects them into a machine-readable
preregistration. Writes nothing but research/hypothesis_oos/out/PREREGISTRATION.json.
No Bedrock, no network, no CHAMPION mutation, no final OOS scoring, no effect-based
selection: every eligibility field here is structural.

Run: .venv/bin/python research/hypothesis_engine/_freeze_v4_preregistration.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src")
sys.path.insert(0, ROOT)

from research.hypothesis_oos import compatibility as COMPAT
from research.hypothesis_oos import HYPOTHESIS_OOS_VERSION

V3_OUT = f"{ROOT}/research/hypothesis_engine/out/v3_hypothesis_measurement"
OUT = f"{ROOT}/research/hypothesis_oos/out"

CHAMPION_ARTIFACT = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

#: Betting targets the project already validates (matchup/design.py::outcome). No new
#: outcome semantics are invented.
VALIDATED_MARKETS = {
    "goals": [1.5, 2.5, 3.5],
    "corners": [8.5, 9.5, 10.5],
    "cards": [3.5, 4.5],
    "btts": [None],
}
#: Which candidate target metric maps (via side aggregation) to which validated market.
METRIC_TO_MARKET = {"corners": "corners", "goals": "goals", "yellow_cards": "cards"}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _template_of(spec: dict) -> dict:
    """Identity-blind structural template: NO fixture id, club, date, or observed effect."""
    return {
        "condition_dimension": "opponent_profile" if spec.get("opponent_profile_band")
        not in (None, "ANY") else ("venue" if spec.get("venue") not in (None, "ANY")
                                   else "unconditional"),
        "opponent_profile_axis": spec.get("opponent_profile_axis"),
        "opponent_profile_band": spec.get("opponent_profile_band"),
        "target_metric": spec.get("target_metric"),
        "side": spec.get("side"),
        "comparison_cohort": spec.get("comparison_cohort"),
        "window": spec.get("window"),
        "period": spec.get("period"),
    }


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    corpus = json.load(open(f"{V3_OUT}/frozen_hypothesis_corpus.json"))
    meas = json.load(open(f"{V3_OUT}/cohort_measurements.json"))
    reco = json.load(open(f"{V3_OUT}/next_stage_recommendation.json"))

    origin_fixtures = sorted({r["fixture_id"] for r in corpus["included"]})

    # ---- identity-blind templates from the MEASURED opponent_profile candidates ---------
    op_measured = [m for m in meas
                   if m.get("spec", {}).get("opponent_profile_axis")
                   and m["outcome"] == "MEASURED"]
    templates, seen = [], set()
    for m in op_measured:
        t = _template_of(m["spec"])
        key = json.dumps(t, sort_keys=True)
        if key not in seen:
            seen.add(key)
            templates.append(t)

    # ---- target mapping ----------------------------------------------------------------
    mapping = {}
    for m in op_measured:
        metric = m["spec"]["target_metric"]
        if metric in METRIC_TO_MARKET:
            mapping.setdefault(metric, {
                "classification": "MAPS_TO_VALIDATED_TARGET_VIA_SIDE_AGGREGATION",
                "market": METRIC_TO_MARKET[metric], "n_candidates": 0})
            mapping[metric]["n_candidates"] += 1
        else:
            mapping.setdefault(metric, {
                "classification": "NO_VALIDATED_PREDICTIVE_TARGET",
                "market": None, "n_candidates": 0})
            mapping[metric]["n_candidates"] += 1

    predictive_metrics = sorted(k for k, v in mapping.items()
                                if v["classification"].startswith("MAPS"))
    set_aside = sorted(k for k, v in mapping.items()
                       if v["classification"] == "NO_VALIDATED_PREDICTIVE_TARGET")

    # ---- compatibility sweep over ALL measured specs (venue tautology exclusion) --------
    compat_excluded = []
    for m in meas:
        v = COMPAT.check_spec(m["spec"])
        if not v.eligible:
            compat_excluded.append({"hypothesis_id": m.get("hypothesis_id"),
                                    "fixture_id": m["spec"].get("fixture_id"),
                                    **v.to_dict()})

    prereg = {
        "preregistration_version": "hypothesis_derived_oos_v4_prereg_v1",
        "hypothesis_oos_version": HYPOTHESIS_OOS_VERSION,
        "spend_usd": 0.0,
        "scientific_question": (
            "Do deterministic measurements derived from the frozen LLM hypotheses provide "
            "stable incremental predictive information in walk-forward OOS football "
            "forecasting beyond appropriate existing quantitative baselines?"),

        # ---- §0 anti-selection ----------------------------------------------------------
        "anti_selection_rule": {
            "eligibility": "STRUCTURAL_ONLY",
            "forbidden_selectors": ["conditional_minus_comparison_difference", "sign",
                                    "magnitude", "abs_diff_over_se", "significance",
                                    "story_success"],
            "families_inherited_unchanged_from": "v3_next_stage_eligibility_v1",
            "criteria_contain_no_effect_term": True,
        },

        # ---- §1 families ----------------------------------------------------------------
        "families": {
            "primary_research_target": "opponent_profile",
            "behavioral_comparator_control": "unconditional_behavioral_profile",
            "secondary": "venue",
            "excluded": {"formation": "corpus coverage",
                         "meaningful_multi_condition": "n=1 generator limit"},
            "eligible_from_v3": reco["eligible_families"],
        },

        # ---- §2 contamination -----------------------------------------------------------
        "contamination_protocol": {
            "design": "B_templates_walk_forward",
            "origin_fixtures_quarantined": origin_fixtures,
            "templates_identity_blind": True,
            "band_semantics": "AS_OF_TARGET_CUTOFF",
        },
        "templates": templates,
        "n_templates": len(templates),

        # ---- §3/§4 baselines excluded by construction -----------------------------------
        "venue_tautology_rule": {
            "version": COMPAT.COMPATIBILITY_VERSION,
            "absorption_map": COMPAT._BASELINE_ABSORBS,
            "excluded_candidates": compat_excluded,
            "n_excluded": len(compat_excluded),
        },
        "excluded_baselines": {
            "SUBJECT_COMPETITION_BASELINE": (
                "zero real-data exercise in the eligible corpus; not required by any "
                "eligible V4 candidate; readiness smoke provided but not included"),
        },

        # ---- §5 feature representation --------------------------------------------------
        "feature_representation": {
            "primary": {"name": "hd_shrunk_diff",
                        "definition": "shrunk (conditional_mean - comparison_mean), n/(n+6)"},
            "ablation_only": [
                {"name": "hd_shrunk_cond_mean", "definition": "shrunk conditional mean"},
                {"name": "hd_cond_n", "definition": "conditional usable N (raw count)"},
                {"name": "hd_available", "definition": "1 if MEASURED else 0"},
            ],
            "excluded_transforms": ["cond_over_comp_ratio", "raw_band_one_hot",
                                    "any_interaction"],
            "computed_as_of_cutoff": True,
        },

        # ---- §6 shrinkage ---------------------------------------------------------------
        "shrinkage": {
            "SHRINK_K": 6.0, "MIN_PRIOR_MATCHES": 4, "MIN_CONDITIONAL_N": 4,
            "MIN_COMPARISON_N": 8, "tuned_against_oos": False,
            "canonical_sources": reco["criteria"]["canonical_sources"],
        },

        # ---- §7 PIT ---------------------------------------------------------------------
        "pit": {"rule": "feature_history_kickoff < prediction_fixture_cutoff (strict)",
                "target_fixture_excluded_from_own_feature": True,
                "reconstructed_not_reused": True},

        # ---- §8 target mapping ----------------------------------------------------------
        "target_mapping": {
            "validated_markets": {k: v for k, v in VALIDATED_MARKETS.items()},
            "metric_to_market": METRIC_TO_MARKET,
            "per_metric": mapping,
            "predictive_metrics": predictive_metrics,
            "set_aside_no_validated_target": set_aside,
            "aggregation_frame": "matchup A-attack (+) B-defence -> match-total frame",
        },

        # ---- §9 baselines ---------------------------------------------------------------
        "baselines": {
            "B0": "f_champ (champion-parity, F0)",
            "B1": "f_champ + f_matchup + f_league_env + f_home_away (no LLM measurement)",
            "B2": "B1 + hd_shrunk_diff (mapped opponent_profile template)",
            "key_comparison": "B2 vs B1",
            "harness": "src/research/matchup/harness.py (existing walk-forward OOS)",
        },

        # ---- §10 champion protection ----------------------------------------------------
        "champion_protection": {
            "artifact": CHAMPION_ARTIFACT,
            "frozen_sha256": CHAMPION_FROZEN_SHA,
            "current_sha256": _sha256(CHAMPION_ARTIFACT)
            if os.path.exists(CHAMPION_ARTIFACT) else None,
            "read_only": True, "auto_promotion": False,
        },

        # ---- §11 confounders ------------------------------------------------------------
        "confounders": {
            "opponent_profile": ["team strength", "opponent strength", "venue",
                                 "competition", "historical sample size", "score state",
                                 "band drift", "profile-selection effects"],
            "adjustment": "B2 - B1 (B1 already carries strength/venue/competition context)",
            "causality_claimed": False,
        },

        # ---- §12 missingness ------------------------------------------------------------
        "missingness_policy": {
            "states": ["SUFFICIENT_MEASUREMENT", "INSUFFICIENT_HISTORY", "NOT_DISTINCT",
                       "UNSUPPORTED", "MISSING_PROVIDER_EVIDENCE"],
            "absent_feature": "NaN -> train-only median impute (B1 convention) + hd_available",
            "favorable_imputation_forbidden": True,
            "indicator_preregistered": "hd_available",
        },

        # ---- §13 multiplicity -----------------------------------------------------------
        "multiplicity": {
            "families": 3, "markets": ["corners", "goals", "cards"],
            "primary_transform": "hd_shrunk_diff",
            "confirmatory": {
                "family": "opponent_profile", "market": "corners",
                "feature": "hd_shrunk_diff", "comparison": "B2_vs_B1",
                "selection_basis": "structural: most-populated mapped opponent_profile "
                                   "target metric (corners FOR/AGAINST=6); NOT any observed "
                                   "effect",
            },
            "exploratory": ["goals", "cards", "unconditional_behavioral_profile", "venue",
                            "all ablation transforms", "per-league", "per-fold"],
            "fdr": "Benjamini-Hochberg over the exploratory family (src/research/fdr/)",
        },

        # ---- §14 negative controls ------------------------------------------------------
        "negative_controls": [
            {"name": "irrelevant_axis",
             "definition": "hd_shrunk_diff from an axis structurally unrelated to the "
                           "market (e.g. fouls_for band for corners)"},
            {"name": "unconditional_comparator",
             "definition": "unconditional_behavioral_profile feature in place of "
                           "opponent_profile"},
            {"name": "pit_safe_band_shuffle",
             "definition": "seeded permutation of band->opponent within the pre-cutoff "
                           "candidate pool, marginal band sizes fixed; never touches "
                           "outcomes"},
        ],

        # ---- §15 uncertainty ------------------------------------------------------------
        "uncertainty": {
            "method": "paired block bootstrap of dLogLoss(B2-B1) over competition blocks",
            "resamples": 400, "frozen_before_evaluation": True,
            "bands": ["CLEAR", "PROMISING", "MARGINAL", "INCONCLUSIVE", "NEGATIVE"],
        },

        # ---- §16 metrics ----------------------------------------------------------------
        "metrics": {
            "primary": ["log_loss", "brier"],
            "also": ["ece", "calib_slope", "calib_intercept", "auc", "p_std",
                     "coverage", "fold_level", "per_league"],
            "primary_comparison": "incremental dLogLoss B2 - B1 (pooled + fold-level)",
            "hit_rate_is_primary": False,
        },

        # ---- §18 decision rules ---------------------------------------------------------
        "decision_rules": {
            "scope": "confirmatory contrast only (opponent_profile.corners.hd_shrunk_diff.B2_vs_B1)",
            "PASS": ("dLogLoss(B2-B1)<0 AND 95% block-bootstrap CI entirely<0 "
                     "(CLEAR|PROMISING) AND calibration preserved (slope in [0.8,1.25], "
                     "ECE not worse than B1 by >0.01) AND mapped-axis lift exceeds ALL "
                     "three negative controls AND direction consistent >=3/4 folds"),
            "MIXED": ("point<0 but CI crosses zero (MARGINAL), OR a control not cleanly "
                      "beaten, OR fold direction inconsistent"),
            "FAIL": ("dLogLoss(B2-B1)>=0 pooled, OR calibration degraded, OR a negative "
                     "control matches/exceeds the mapped axis"),
            "pass_is_historical_oos_candidate_only": True,
        },

        # ---- §19 prospective ------------------------------------------------------------
        "prospective_followup": [
            "historical OOS candidate (V4 PASS)", "frozen challenger",
            "prospective shadow predictions", "timestamped market comparison",
            "genuine closing line", "settlement", "possible later promotion"],
        "oos_and_prospective_are_separate_claims": True,

        # ---- §18b identifiability -------------------------------------------------------
        "identifiability": {
            "verdict": "IDENTIFIABLE_FOR_SINGLE_CONFIRMATORY_CONTRAST",
            "confirmatory_cell_identifiable": True,
            "threats": ["target-mapping loss (~40/53 candidates have no validated target)",
                        "origin-fixture scarcity (11 clean origin fixtures)",
                        "single-side vs match-total estimand gap"],
            "scope": "opponent_profile.corners confirmatory; everything else exploratory",
        },
    }

    with open(f"{OUT}/PREREGISTRATION.json", "w") as fh:
        json.dump(prereg, fh, indent=1, sort_keys=True)

    print(f"templates={len(templates)} predictive_metrics={predictive_metrics} "
          f"set_aside={len(set_aside)} venue_tautology_excluded={len(compat_excluded)}")
    print(f"champion sha match: "
          f"{prereg['champion_protection']['current_sha256'] == CHAMPION_FROZEN_SHA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
