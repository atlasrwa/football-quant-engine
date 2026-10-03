"""Preregistered QFE V2 Layer 4 ensemble/calibration protocol.

This file is frozen before any CALIBRATION outcome is scored. Candidate model
families were fixed by Layer 3/3.1 DEVELOPMENT OOF evidence. PROTECTED outcomes
are forbidden throughout Layer 4.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from src.research.dataset.manifest import sha256_json

LAYER4_PROTOCOL_VERSION="qfe-layer4-ensemble-calibration-v1"
FROZEN_ON="2026-10-02"


def _ts(y,m,d): return int(datetime(y,m,d,tzinfo=timezone.utc).timestamp())

CALIBRATION_START_TS=_ts(2026,2,1)
CALIBRATION_FIT_END_TS=_ts(2026,5,1)
CALIBRATION_END_TS=_ts(2026,8,1)

GOALS_SIMILAR_WEIGHT_GRID=(0.0,0.05,0.10,0.20)
GOALS_EQUAL_WEIGHT_DIAGNOSTIC=0.50
CORNERS_NB2_WEIGHT_GRID=(0.0,0.25,0.50,0.75,1.0)
CORNERS_SCOPE_WEIGHTS={"SIDE":0.5,"TOTAL":0.5}

GOALS_LINES=(2.5,)
CORNERS_SIDE_LINES=(2.5,3.5,4.5,5.5,6.5,7.5)
CORNERS_TOTAL_LINES=(7.5,8.5,9.5,10.5,11.5,12.5)

CALIBRATOR_CANDIDATES=(
    "IDENTITY",
    "PLATT_GLOBAL",
    "BETA_GLOBAL",
    "ISOTONIC_GLOBAL",
    "PLATT_ROLE_COMP_RIDGE_L1",
    "PLATT_ROLE_COMP_RIDGE_L10",
    "PLATT_ROLE_COMP_RIDGE_L100",
)
RIDGE_LAMBDAS=(1.0,10.0,100.0)
CALIBRATION_GROUPS=("GOALS_TOTAL","CORNERS_SIDE","CORNERS_TOTAL")
PROBABILITY_BINS=(0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0)
PROBABILITY_CLIP=1e-6
CALIBRATOR_LL_TIE_TOLERANCE=0.0005
BRIER_NONINFERIORITY_TOLERANCE=0.001
ISOTONIC_MIN_UNIQUE_FIXTURES=250
ISOTONIC_MIN_EVENT_CELLS=500
ISOTONIC_MIN_CLASS_CELLS=100
RELIABILITY_MIN_UNIQUE_FIXTURES=30
OOD_QUANTILES=(0.005,0.995)
COMPONENT_GAP_OOD_QUANTILE=0.99
BOOTSTRAP_REPLICATES=4000
BOOTSTRAP_SEED=20261002


@dataclass(frozen=True,slots=True)
class Layer4Protocol:
    version: str=LAYER4_PROTOCOL_VERSION
    frozen_on: str=FROZEN_ON

    def to_dict(self)->dict[str,Any]:
        return {
            "version":self.version,"frozen_on":self.frozen_on,
            "scientific_boundary":{
                "development_outcomes":"ensemble-weight selection only",
                "calibration_fit_window":{"start_ts":CALIBRATION_START_TS,"end_exclusive_ts":CALIBRATION_FIT_END_TS},
                "calibration_select_window":{"start_ts":CALIBRATION_FIT_END_TS,"end_exclusive_ts":CALIBRATION_END_TS},
                "final_calibrator_refit":"selected method refit on all CALIBRATION after selection; resulting fit metrics are descriptive only",
                "protected_outcomes_allowed":False,
                "market_odds_allowed":False,
                "post_result_redesign":"forbidden; material design change requires Layer4 protocol v2 and no reuse of v1 result as confirmatory evidence",
            },
            "goals":{
                "raw_distribution":"dynamic hierarchical independent Poisson",
                "diversifier":"deterministic similar-context expected_total",
                "diversifier_weight_grid":list(GOALS_SIMILAR_WEIGHT_GRID),
                "equal_weight_0_5":"diagnostic_only_not_eligible",
                "blend_contract":"blend expected_total; if nonzero diversifier weight is selected, rescale dynamic lambda_home/lambda_away by blended_total/dynamic_total, preserving home/away ratio and a coherent Poisson count distribution",
                "selection_market_lines":list(GOALS_LINES),
                "nonzero_weight_gate":"paired weekly-block DEVELOPMENT improvement vs w=0 must have 95% CI lower bound >0 for BOTH binary Log Loss and Brier; otherwise select w=0",
                "selection_rule":"among eligible weights choose lowest mean binary Log Loss; tie chooses smaller diversifier weight",
            },
            "corners":{
                "component_0":"independent Poisson home/away count joint distribution",
                "component_1":"independent side-NB2 home/away joint distribution with common DEVELOPMENT-fitted alpha",
                "nb2_weight_grid":list(CORNERS_NB2_WEIGHT_GRID),
                "coherent_mixture":"one fixture-level convex mixture weight is applied to the two complete joint count distributions; all side and total event probabilities are marginals of that same joint mixture",
                "side_lines":list(CORNERS_SIDE_LINES),"total_lines":list(CORNERS_TOTAL_LINES),
                "selection_objective":"per-fixture composite proper score: 50% mean SIDE ladder loss + 50% mean TOTAL ladder loss; SIDE itself gives HOME and AWAY equal weight and lines equal weight",
                "scope_weights":CORNERS_SCOPE_WEIGHTS,
                "nonzero_weight_gate":"paired weekly-block composite improvement vs w=0 must have 95% CI lower bound >0 for BOTH Log Loss and Brier; HOME and AWAY role Log Loss must not have 95% CI upper bound <0",
                "selection_rule":"among eligible weights choose lowest mean composite Log Loss; tie chooses smaller NB2 weight",
            },
            "calibration":{
                "groups":list(CALIBRATION_GROUPS),
                "cell_weighting":{
                    "GOALS_TOTAL":"one event per fixture",
                    "CORNERS_SIDE":"each fixture equal; HOME/AWAY each 50%; lines equal within role",
                    "CORNERS_TOTAL":"each fixture equal; total lines equal",
                },
                "candidate_methods":list(CALIBRATOR_CANDIDATES),
                "ridge_lambdas":list(RIDGE_LAMBDAS),
                "PLATT_GLOBAL":"logit(q)=a+b*logit(p), constrained b>0",
                "BETA_GLOBAL":"logit(q)=c+a*log(p)-b*log(1-p), constrained a>=0,b>=0",
                "ISOTONIC_GLOBAL":"one monotone map per calibration group; eligible only if preregistered support thresholds are met",
                "PLATT_ROLE_COMP_RIDGE":"logit(q)=a+b*logit(p)+role_intercept+competition_intercept; b>0; role/competition deviations L2-shrunk toward zero. CORNERS_SIDE uses HOME/AWAY role; other groups have no role deviation.",
                "fit_window":"CALIBRATION_FIT only",
                "selection_window":"CALIBRATION_SELECT only",
                "selection_primary":"fixture-balanced binary Log Loss",
                "brier_noninferiority_tolerance":BRIER_NONINFERIORITY_TOLERANCE,
                "selection_rule":"candidate must improve Log Loss vs IDENTITY and have Brier <= IDENTITY + tolerance; select minimum Log Loss. If candidates are within LL tie tolerance, select lower-complexity order IDENTITY < PLATT_GLOBAL < BETA_GLOBAL < ISOTONIC_GLOBAL < role/competition ridge.",
                "ll_tie_tolerance":CALIBRATOR_LL_TIE_TOLERANCE,
                "probability_clip":PROBABILITY_CLIP,
                "isotonic_support":{"min_unique_fixtures":ISOTONIC_MIN_UNIQUE_FIXTURES,"min_event_cells":ISOTONIC_MIN_EVENT_CELLS,"min_each_class_cells":ISOTONIC_MIN_CLASS_CELLS},
                "coherence":"no line-specific calibrators. Every mapping must be monotone; one selected mapping is applied consistently within a calibration group. Calibrated ladders must be checked monotone after transformation. Raw coherent count distribution is retained separately from calibrated market-event surface.",
            },
            "prediction_support_metadata":{
                "required":["dynamic_effective_team_support","prior_competition_match_count","component_probabilities","component_dispersion","raw_probability_bin","calibration_bin_event_cells","calibration_bin_unique_fixtures","calibration_bin_mean_prediction","calibration_bin_observed_rate","calibration_bin_reliability_error_ci","model_space_intensity_percentile","component_gap_percentile","ood_flags"],
                "probability_bins":list(PROBABILITY_BINS),
                "reliability_min_unique_fixtures":RELIABILITY_MIN_UNIQUE_FIXTURES,
                "reliability_band":"weekly-block bootstrap of observed_rate - mean_prediction within fixed raw-probability bin; this is an empirical reliability band, NOT an individual-fixture probability confidence interval",
                "ood_intensity_quantiles":list(OOD_QUANTILES),
                "component_gap_ood_quantile":COMPONENT_GAP_OOD_QUANTILE,
                "ood_policy":"diagnostic metadata only in Layer4; it must not silently filter calibration or protected rows. Layer5 may preregister an eligibility policy later.",
            },
            "bootstrap":{"block":"UTC_CALENDAR_WEEK","replicates":BOOTSTRAP_REPLICATES,"seed":BOOTSTRAP_SEED},
            "promotion_boundary":"Layer4 freezes a standalone odds-blind p_model stack. No market disagreement or profitability claim is allowed. PROTECTED remains sealed until Layer5 market/disagreement policy is also frozen.",
        }

    @property
    def protocol_hash(self)->str: return sha256_json(self.to_dict())


def protocol_v1()->Layer4Protocol: return Layer4Protocol()
