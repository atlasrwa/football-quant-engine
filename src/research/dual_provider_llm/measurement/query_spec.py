"""The six frozen ResearchQuerySpecs (declarative). Compiled, not executed.

Every numeric parameter is a support.c(<CONSTANT>) reference. Composites are structural ("mean"
or "contrast"), never weighted by hand. No number from the LLM hypotheses enters any spec.
"""
from __future__ import annotations

from typing import Any, Dict, List

from src.research.dual_provider_llm.measurement.support import c

HOME, AWAY = "HOME_TEAM", "AWAY_TEAM"

COMMON_CUTOFF = {
    "global": "only matches with kickoff strictly before the target fixture kickoff "
              "(packet cutoff_unix) exist in the measurement history; the target match and "
              "anything later are never loaded",
    "per_subject_match": "every covariate for a historical subject match (opponent profile, "
                         "scaling reference, strength) uses only matches strictly before that "
                         "match's kickoff",
    "query_point": "the target-fixture query profile/state is built with the identical rule at "
                   "the target kickoff",
}
COMMON_SCALING = {
    "method": "competition_relative_robust_z",
    "center": "median of the metric's team-match FOR values in the observation's competition, "
              "over matches strictly before the query time",
    "scale": {"mad_to_sd": c("MAD_TO_SD"), "iqr_fallback": c("IQR_TO_SD")},
    "min_reference_obs": c("MIN_REFERENCE_OBS"),
    "conceded_values": "an AGAINST value is scaled against the same metric's distribution (it "
                       "is the producing side's FOR value)",
    "unscaleable": "observation treated as missing",
}
COMMON_MISSINGNESS = {
    "null_is_zero": False,
    "observation": "a null provider cell is excluded, never imputed",
    "profile_dimension": {"min_non_null": c("MIN_PROFILE_MATCHES_PER_DIM"),
                          "of_window": c("PROFILE_WINDOW_MATCHES")},
    "profile": {"min_dimension_coverage": c("MIN_PROFILE_DIMENSION_COVERAGE"),
                "rule": "all dimensions required, else the subject match is ineligible"},
    "subject_output": "a subject match with any null output metric is ineligible",
    "metric_coverage": {"min": c("MIN_METRIC_COVERAGE"),
                        "else": "UNSUPPORTED_METRIC (fail closed)"},
}
COMMON_COMPETITION = {
    "policy": "B_COMPETITION_STANDARDIZED",
    "detail": "every observation is z-scored within its own competition using strictly prior "
              "data, so LaLiga and LaLiga 2 values are compared as 'relative to that league'; "
              "no raw pooling across competitions",
    "limitation": "this corrects league-level scale, NOT a team's own regime change on "
                  "promotion/relegation",
}
SIMILARITY = {
    "algorithm": "robust_standardized_euclidean_rms",
    "distance": "sqrt(mean_j (profile_j - query_j)^2) over the listed dimensions",
    "profile_window": c("PROFILE_WINDOW_MATCHES"),
    "neighbor_policy": {"rule": "nearest max(MIN_SIMILAR_MATCHES, ceil(n * NEIGHBOR_FRACTION)) "
                                "eligible subject matches; the rest form the comparison group",
                        "fraction": c("NEIGHBOR_FRACTION"), "min": c("MIN_SIMILAR_MATCHES"),
                        "tie_break": "(distance rounded to DISTANCE_ROUND_DECIMALS, kickoff, "
                                     "match_id)",
                        "round_decimals": c("DISTANCE_ROUND_DECIMALS")},
    "llm_similarity_score": False,
}
GROUP_SUPPORT = {"MIN_SUBJECT_MATCHES": c("MIN_SUBJECT_MATCHES"),
                 "MIN_SIMILAR_MATCHES": c("MIN_SIMILAR_MATCHES"),
                 "on_failure": "INSUFFICIENT_SUPPORT"}
STRENGTH = {"definition": "opponent mean goal difference over its last STRENGTH_WINDOW_MATCHES "
                          "same-competition matches strictly before the subject match",
            "window": c("STRENGTH_WINDOW_MATCHES"), "min": c("MIN_STRENGTH_MATCHES"),
            "gates_eligibility": False,
            "use": "balance diagnostic (neighbour vs comparison) and strength-adjusted secondary "
                   "on rows where it is available; missing strength is reported, not imputed"}
NULL_PERM = {"resamples": c("N_RESAMPLES"), "seed": c("RNG_SEED")}
REGIME_LIMIT = ("Girona's history is predominantly LaLiga while the query opponent and target "
                "are LaLiga 2; competition z-scoring fixes league scale but the measurement "
                "still describes LaLiga-era Girona queried with a LaLiga 2 opponent.")
SAME_MATCH_LIMIT = ("Covariates and outputs are observed in the same match: this is a "
                    "historical association, not a pre-match predictor and not causal.")


def _base(mid: str) -> Dict[str, Any]:
    return {"mechanism_id": mid, "provider": "thestatsapi",
            "historical_cutoff_policy": COMMON_CUTOFF, "scaling_policy": COMMON_SCALING,
            "missingness_policy": COMMON_MISSINGNESS, "competition_condition": COMMON_COMPETITION,
            "point_in_time_requirements": COMMON_CUTOFF,
            "numeric_llm_input_used": False,
            "determinism_notes": "pure functions of the frozen cache snapshot and constants; "
                                 "sorted iteration; seeded permutations; no wall-clock values"}


def specs() -> List[Dict[str, Any]]:
    out = []

    s = _base("DP1_BOX_PRESSURE_MATCHUP")
    s.update({
        "design": "NEIGHBOR_GROUP_DIFFERENCE",
        "subject_team_definition": {"role": HOME, "team": "target home team (Girona FC)"},
        "population_definition": "subject team's HOME matches strictly before the target "
                                 "kickoff (all competitions, competition-standardized)",
        "venue_condition": {"subject_venue": "HOME", "opponent_profile_venue": "AWAY"},
        "opponent_population_definition": "the away opponent in each subject match; profile "
                                          "from its own prior AWAY matches",
        "input_metrics": ["possession", "touches_in_box", "shots_inside_box", "corners", "shots",
                          "shots_on_target"],
        "similarity_dimensions": [["possession", "AGAINST"], ["touches_in_box", "AGAINST"],
                                  ["shots_inside_box", "AGAINST"], ["corners", "AGAINST"]],
        "query_point": {"team": "target away team (Albacete)", "venue": "AWAY",
                        "profile": "same last-10 rule at the target kickoff"},
        "similarity_algorithm": SIMILARITY,
        "outputs": {"metrics": [["corners", "FOR"], ["shots", "FOR"],
                                ["shots_on_target", "FOR"]], "combine": "mean_of_z"},
        "derived_metrics": ["pressure_composite = mean z(corners, shots, shots_on_target) FOR"],
        "metrics_named_in_prose_only": [{"metric": "shots",
                                         "quote": "distribution of corners, shots and shots on "
                                                  "target"}],
        "primary_measurement": {"statistic": "mean(pressure_composite | neighbours) - "
                                             "mean(pressure_composite | comparison)",
                                "null": "group_label_permutation", **NULL_PERM,
                                "in_bh_family": True},
        "secondary_measurements": ["per-channel differences (corners, shots, shots_on_target)",
                                   "strength-adjusted difference (OLS composite ~ neighbour + "
                                   "strength, rows with strength)"],
        "support_policy": GROUP_SUPPORT, "minimum_sample_requirements": GROUP_SUPPORT,
        "recent_window_policy": "not used", "long_run_policy": "all prior home matches in cache",
        "confounders": {"handled": ["competition (z-scoring)", "venue (home only)",
                                    "opponent strength (diagnostic + adjusted secondary)",
                                    "season (reported per group)"],
                        "unhandled": ["Girona regime change", "score state (no half data)",
                                      "lineups/injuries (not available)"]},
        "opponent_strength_control": STRENGTH,
        "comparison_groups": ["neighbours (nearest tercile to the query profile)",
                              "comparison (remaining eligible home matches)"],
        "failure_conditions": ["INSUFFICIENT_SUPPORT", "NO_QUERY_PROFILE", "UNSUPPORTED_METRIC"],
        "interpretation_limits": [REGIME_LIMIT, "describes Girona's historical home output vs "
                                  "profile-similar visitors; not a forecast of the target"],
        "evidence_ref_window_note": "frozen refs cite ALL_PRIOR.AWAY/HOME; profiles use the last "
                                    "10 venue-matched matches for both the query point and every "
                                    "historical profile, because ALL_PRIOR length depends on the "
                                    "corpus start date",
    })
    out.append(s)

    s = _base("DP2_WIDE_CENTRAL_INTERACTION")
    s.update({
        "design": "INTERACTION_REGRESSION",
        "subject_team_definition": {"role": HOME, "team": "Girona FC"},
        "population_definition": "Girona HOME matches strictly before the target kickoff",
        "venue_condition": {"subject_venue": "HOME", "opponent_profile_venue": "AWAY"},
        "opponent_population_definition": "away opponents; secondary conditioning on their prior "
                                          "AWAY concession of crosses and box touches",
        "input_metrics": ["accurate_crosses", "touches_in_box", "corners"],
        "derived_metrics": ["x1 = z(accurate_crosses FOR)", "x2 = z(touches_in_box FOR)",
                            "x1*x2 continuous standardized product (no threshold)"],
        "similarity_dimensions": [["accurate_crosses", "AGAINST"], ["touches_in_box", "AGAINST"]],
        "query_point": {"team": "Albacete", "venue": "AWAY", "profile": "last-10 rule"},
        "similarity_algorithm": SIMILARITY,
        "outputs": {"metrics": [["corners", "FOR"]], "combine": "z"},
        "primary_measurement": {"statistic": "coefficient of x1*x2 in z(corners) ~ 1 + x1 + x2 + "
                                             "x1*x2 over all eligible Girona home matches",
                                "null": "freedman_lane_residual_permutation", **NULL_PERM,
                                "parameters": ["intercept", "x1", "x2", "x1*x2"],
                                "in_bh_family": True},
        "secondary_measurements": ["same model within the neighbour tercile of opponents near "
                                   "Albacete's away concession profile (only if it meets the "
                                   "regression support rule)",
                                   "main-effect coefficients reported alongside"],
        "support_policy": {"regression": {"min_obs_per_parameter": c("MIN_OBS_PER_PARAMETER"),
                                          "parameters": ["intercept", "x1", "x2", "x1*x2"]},
                           "on_failure": "INSUFFICIENT_SUPPORT"},
        "minimum_sample_requirements": {"min_obs_per_parameter": c("MIN_OBS_PER_PARAMETER")},
        "recent_window_policy": "not used", "long_run_policy": "all prior home matches",
        "confounders": {"handled": ["competition (z-scoring)", "venue (home only)"],
                        "unhandled": ["opponent possession/defensive strength in the primary "
                                      "(conditioned only in the secondary)",
                                      "recent-vs-long-run regime", "Girona regime change"]},
        "opponent_strength_control": STRENGTH,
        "comparison_groups": ["continuous interaction; no groups in the primary"],
        "failure_conditions": ["INSUFFICIENT_SUPPORT", "UNSUPPORTED_METRIC"],
        "interpretation_limits": [REGIME_LIMIT, SAME_MATCH_LIMIT,
                                  "provider semantics: accurate_crosses may include corner "
                                  "deliveries and touches_in_box may include set-piece touches, "
                                  "so part of the association may be mechanical or reversed"],
        "multivariate": True,
    })
    out.append(s)

    s = _base("DP3_ALBACETE_DIRECT_PROGRESSION")
    s.update({
        "design": "CONDITIONAL_RANK_ASSOCIATION",
        "subject_team_definition": {"role": AWAY, "team": "Albacete Balompié"},
        "population_definition": "Albacete AWAY matches strictly before the target kickoff in "
                                 "which its own possession z < 0 (below its competition's "
                                 "median; the median is the scaling centre, not an LLM number)",
        "venue_condition": {"subject_venue": "AWAY", "opponent_profile_venue": "HOME"},
        "opponent_population_definition": "home opponents; secondary conditioning on their prior "
                                          "HOME defensive profile",
        "input_metrics": ["possession", "accurate_long_balls", "final_third_entries", "shots",
                          "corners"],
        "derived_metrics": ["direct_progression_index = mean z(accurate_long_balls, "
                            "final_third_entries) FOR (observational label only; no tactical "
                            "intent inferred)",
                            "output_composite = mean z(shots, corners) FOR"],
        "similarity_dimensions": [["possession", "AGAINST"], ["final_third_entries", "AGAINST"],
                                  ["shots", "AGAINST"], ["corners", "AGAINST"]],
        "query_point": {"team": "Girona FC", "venue": "HOME", "profile": "last-10 rule"},
        "similarity_algorithm": SIMILARITY,
        "outputs": {"metrics": [["shots", "FOR"], ["corners", "FOR"]], "combine": "mean_of_z"},
        "primary_measurement": {"statistic": "Spearman rho(direct_progression_index, "
                                             "output_composite) over low-possession away matches",
                                "null": "outcome_permutation", **NULL_PERM,
                                "in_bh_family": True},
        "secondary_measurements": ["same within the neighbour tercile of home opponents near "
                                   "Girona's home defensive profile (if supported)",
                                   "per-output rho (shots, corners)"],
        "support_policy": GROUP_SUPPORT, "minimum_sample_requirements": GROUP_SUPPORT,
        "recent_window_policy": "not used", "long_run_policy": "all prior away matches",
        "confounders": {"handled": ["competition (z-scoring)", "venue (away only)",
                                    "opponent profile (secondary)"],
                        "unhandled": ["score state (a trailing team concedes possession; no half "
                                      "data)", "opponent strength (diagnostic only)", "season"]},
        "opponent_strength_control": STRENGTH,
        "comparison_groups": ["continuous association; no groups in the primary"],
        "failure_conditions": ["INSUFFICIENT_SUPPORT", "UNSUPPORTED_METRIC"],
        "interpretation_limits": [SAME_MATCH_LIMIT,
                                  "final_third_entries mechanically feed shots, so part of the "
                                  "association is definitional"],
    })
    out.append(s)

    s = _base("DP4_GIRONA_CURRENT_TERRITORIAL_REGIME")
    s.update({
        "design": "STATE_RESIDUAL_GROUP_DIFFERENCE",
        "subject_team_definition": {"role": HOME, "team": "Girona FC"},
        "population_definition": "Girona HOME matches strictly before the target kickoff, "
                                 "EXCLUDING every match used to define the recent-5 or recent-10 "
                                 "reference states (no circularity)",
        "venue_condition": {"subject_venue": "HOME",
                            "state_standardization": "competition x venue"},
        "opponent_population_definition": "not profiled (strength diagnostic only)",
        "input_metrics": ["possession", "final_third_entries", "touches_in_box",
                          "accurate_crosses", "corners", "shots"],
        "state_dimensions": [["possession", "FOR"], ["final_third_entries", "FOR"],
                             ["touches_in_box", "FOR"], ["accurate_crosses", "FOR"]],
        "similarity_dimensions": [["possession", "FOR"], ["final_third_entries", "FOR"],
                                  ["touches_in_box", "FOR"], ["accurate_crosses", "FOR"]],
        "derived_metrics": [
            "state_i = z(each state dim) within competition x venue at the subject kickoff",
            "R5 = mean state over Girona's last RECENT_BLOCK_MATCHES all-venue matches before "
            "the target; R10 = mean over the last PROFILE_WINDOW_MATCHES",
            "S = R10 + n5/(n5 + SHRINKAGE_KAPPA) x (R5 - R10)  (recent state shrunk to R10)",
            "territory_i = mean(state_i); output_i = mean z(corners, shots) FOR",
            "resid_i = output_i - OLS fit of output on territory over the eligible pool"],
        "metrics_named_in_prose_only": [{"metric": "shots", "quote": "corner/shot behavior"}],
        "recent_window_policy": {"recent": c("RECENT_BLOCK_MATCHES"),
                                 "shrinkage_kappa": c("SHRINKAGE_KAPPA"),
                                 "recent_5_is_not_ground_truth": True},
        "long_run_policy": {"reference": c("PROFILE_WINDOW_MATCHES")},
        "similarity_algorithm": SIMILARITY,
        "outputs": {"metrics": [["corners", "FOR"], ["shots", "FOR"]], "combine": "mean_of_z"},
        "primary_measurement": {"statistic": "mean(resid | k nearest to S) - mean(resid | k "
                                             "nearest to R10 among the rest)",
                                "k": "neighbor_count(n_eligible)",
                                "null": "group_label_permutation", **NULL_PERM,
                                "in_bh_family": True,
                                "meaning": "does the territory->output relationship differ in "
                                           "matches resembling the recent state vs the broader "
                                           "recent-10 state"},
        "secondary_measurements": ["raw output difference between the two groups (descriptive)",
                                   "all-venue version with competition x venue standardization"],
        "support_policy": GROUP_SUPPORT, "minimum_sample_requirements": GROUP_SUPPORT,
        "confounders": {"handled": ["competition and venue (z within competition x venue)",
                                    "circularity (reference matches excluded)"],
                        "unhandled": ["competition change inside the recent windows (regime)",
                                      "opponent strength (diagnostic)", "small RECENT_5"]},
        "opponent_strength_control": STRENGTH,
        "comparison_groups": ["nearest to shrunk recent state S", "nearest to R10 (disjoint)"],
        "failure_conditions": ["INSUFFICIENT_SUPPORT", "NO_QUERY_PROFILE"],
        "interpretation_limits": [REGIME_LIMIT, SAME_MATCH_LIMIT,
                                  "R5/R10 are all-venue states compared with home matches; "
                                  "competition x venue z-scoring is the mitigation"],
    })
    out.append(s)

    s = _base("DP5_ALBACETE_RECENT_TERRITORIAL_EXPANSION")
    s.update({
        "design": "RECENT_BLOCK_DESCRIPTIVE",
        "subject_team_definition": {"role": AWAY, "team": "Albacete Balompié"},
        "population_definition": "Albacete AWAY matches strictly before the target kickoff",
        "venue_condition": {"subject_venue": "AWAY", "opponent_profile_venue": "HOME",
                            "state_standardization": "competition x venue"},
        "opponent_population_definition": "home opponents; adjustment profile from their prior "
                                          "HOME matches (what they concede at home)",
        "input_metrics": ["possession", "final_third_entries", "touches_in_box", "corners"],
        "state_dimensions": [["possession", "FOR"], ["final_third_entries", "FOR"],
                             ["touches_in_box", "FOR"], ["corners", "FOR"]],
        "similarity_dimensions": [["possession", "AGAINST"], ["final_third_entries", "AGAINST"],
                                  ["touches_in_box", "AGAINST"]],
        "derived_metrics": [
            "adjusted_i[d] = z(Albacete d FOR in match i) - opponent's prior HOME profile of d "
            "AGAINST, for d in the three similarity dims; corners unadjusted (not a frozen "
            "similarity dimension)",
            "recent block = last RECENT_BLOCK_MATCHES away matches; long run = away matches "
            "before it",
            "S5 = long_run + n/(n + SHRINKAGE_KAPPA) x (recent - long_run)",
            "composite = mean over state dims of (S5 - long_run)",
            "state distance = RMS(S5 - long_run)"],
        "recent_window_policy": {"recent": c("RECENT_BLOCK_MATCHES"),
                                 "shrinkage_kappa": c("SHRINKAGE_KAPPA")},
        "long_run_policy": {"min_long_run": c("MIN_LONG_RUN_MATCHES")},
        "similarity_algorithm": {"note": "opponent adjustment by profile subtraction, no "
                                         "neighbour selection", "profile_window":
                                         c("PROFILE_WINDOW_MATCHES")},
        "outputs": {"metrics": [["corners", "FOR"]], "combine": "part of the state vector"},
        "primary_measurement": {"statistic": "composite (shrunk recent-block minus long-run "
                                             "adjusted territorial state)",
                                "reference": "percentile among DISJOINT historical "
                                             "RECENT_BLOCK_MATCHES-match away blocks tiled "
                                             "backwards from the recent block (none overlapping "
                                             "it)",
                                "inferential": False, "in_bh_family": False,
                                "why": "blocks of one team's sequence are not exchangeable; the "
                                       "percentile is descriptive, not a p-value"},
        "secondary_measurements": ["venue-mix decomposition: packet RECENT_5 (all venues) vs "
                                   "away-only recent block", "per-dimension differences",
                                   "state distance"],
        "support_policy": {"recent": c("RECENT_BLOCK_MATCHES"),
                           "min_long_run": c("MIN_LONG_RUN_MATCHES"),
                           "on_failure": "INSUFFICIENT_SUPPORT"},
        "minimum_sample_requirements": {"min_long_run": c("MIN_LONG_RUN_MATCHES")},
        "confounders": {"handled": ["venue (away only)", "opponent concession (profile "
                                    "subtraction)", "competition (z; Albacete stays in LaLiga 2)"],
                        "unhandled": ["season boundary: the recent away block spans the summer "
                                      "break", "opponent strength (diagnostic)"]},
        "opponent_strength_control": STRENGTH,
        "comparison_groups": ["recent away block", "long-run away state"],
        "failure_conditions": ["INSUFFICIENT_SUPPORT"],
        "interpretation_limits": ["descriptive only; excluded from the BH family",
                                  "a 5-match block is small; shrinkage is the mitigation"],
    })
    out.append(s)

    s = _base("DP6_PRESSURE_RESOLUTION_CLEARANCE_PROFILE")
    s.update({
        "design": "NEIGHBOR_GROUP_DIFFERENCE",
        "subject_team_definition": {"role": HOME, "team": "Girona FC"},
        "population_definition": "Girona HOME matches strictly before the target kickoff",
        "venue_condition": {"subject_venue": "HOME", "opponent_profile_venue": "AWAY"},
        "opponent_population_definition": "away opponents; pressure-absorption profile from "
                                          "their prior AWAY matches",
        "input_metrics": ["clearances", "touches_in_box", "shots", "shots_inside_box", "corners",
                          "shots_on_target", "big_chances"],
        "similarity_dimensions": [["clearances", "FOR"], ["touches_in_box", "AGAINST"],
                                  ["shots", "AGAINST"], ["shots_inside_box", "AGAINST"]],
        "query_point": {"team": "Albacete", "venue": "AWAY", "profile": "last-10 rule"},
        "similarity_algorithm": SIMILARITY,
        "outputs": {"metrics": [["corners", "FOR"], ["shots_on_target", "FOR"],
                                ["big_chances", "FOR"]],
                    "combine": "contrast",
                    "contrast": {"plus": [["corners", "FOR"]],
                                 "minus_mean_of": [["shots_on_target", "FOR"],
                                                   ["big_chances", "FOR"]]}},
        "derived_metrics": ["resolution_contrast = z(corners) - mean z(shots_on_target, "
                            "big_chances) FOR (continuous; no bins)"],
        "primary_measurement": {"statistic": "mean(resolution_contrast | neighbours) - "
                                             "mean(resolution_contrast | comparison)",
                                "null": "group_label_permutation", **NULL_PERM,
                                "in_bh_family": True},
        "secondary_measurements": ["per-channel differences", "strength-adjusted difference"],
        "support_policy": GROUP_SUPPORT, "minimum_sample_requirements": GROUP_SUPPORT,
        "recent_window_policy": "not used", "long_run_policy": "all prior home matches",
        "confounders": {"handled": ["competition (z)", "venue (home only)",
                                    "opponent strength (diagnostic + adjusted secondary)"],
                        "unhandled": ["possession (not a frozen DP6 dimension)", "score state",
                                      "Girona regime change"]},
        "opponent_strength_control": STRENGTH,
        "comparison_groups": ["neighbours", "comparison"],
        "failure_conditions": ["INSUFFICIENT_SUPPORT", "NO_QUERY_PROFILE", "UNSUPPORTED_METRIC"],
        "interpretation_limits": [REGIME_LIMIT,
                                  "shots_on_target and big_chances are not disjoint events; the "
                                  "contrast compares standardized channel levels, not shares",
                                  "blocked_shots deliberately unused (provider semantics "
                                  "unresolved)"],
        "multivariate": True,
    })
    out.append(s)
    for s in out:
        s.setdefault("state_dimensions", [])
        s.setdefault("metrics_named_in_prose_only", [])
        s["control_metrics"] = [{"metric": "goals", "use": "opponent strength control only "
                                 "(prior matches' goal difference); never an output"}]
    return out
