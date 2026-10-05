"""Certified QFE Prospective V1 probability writer.

This module reuses only frozen QFE V2/V3 components. It accepts no odds and no
outcomes for the target fixture. Historical football evidence is availability-
gated at T-6h with the frozen 6h result embargo.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.stats import poisson

from src.research.data_source import ResearchMatch
from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.pit import PITDatasetBuilder, PITDatasetSpec
from src.research.evaluation.similar_oof import (
    GOALS_FEATURES,
    SimilarContextConfig,
    _fit_scaler,
    _predict_one,
    _raw_matrix,
)
from src.research.layer4.calibrators import calibrator_from_spec
from src.research.layer5.disagreement import ModelMarketPoint
from src.research.layer5.prospective_manifest import validate_prospective_cohort_manifest
from src.research.models.dynamic_count_strength import (
    CORNERS_TARGET,
    GOALS_TARGET,
    DEFAULT_AVAILABILITY_EMBARGO_SECONDS,
    DEFAULT_DECISION_HORIZON_SECONDS,
    DynamicCountConfig,
    DynamicHierarchicalCountBaseline,
)
from src.research.models.structured_distributions import (
    nb2_cdf,
    nb2_total_under_probability_from_sides,
)

PREDICTION_BUNDLE_VERSION = "qfe-prospective-prediction-bundle-v1"
EXECUTION_PROTOCOL_HASH = "bf5b1ba2b15be8db74618754028a34c9568dc281e2fb26a9d0e174552681ca4c"
LAYER4_MODEL_FREEZE_HASH = "bce2cbdb6fd3ecf1d664439116d1666b9fc4b4172c2838bf29428d07d2713bd2"
LAYER5_PROTOCOL_HASH = "ae39008016b66f27c279bd2d47093e679ff46458fb44226d2b373983d42bb46a"
BASE_CORPUS_MANIFEST_HASH = "bde8a51688674f0ca5d7b17426327cc55d5d44ce4106443eb1a2f5b780419e22"
BASE_CORPUS_LAST_KICKOFF_TS = 1789412400
COMPETITION_UNIVERSE = (
    "comp_0256",
    "comp_0976",
    "comp_3039",
    "comp_8321",
    "comp_8814",
    "comp_9777",
)
GOAL_LINE = 2.5
SIDE_LINES = (2.5,3.5,4.5,5.5,6.5,7.5)
TOTAL_LINES = (7.5,8.5,9.5,10.5,11.5,12.5)

_IDENTITY_FIELDS = {
    "match_id","date_unix","league_id","season","home_team","away_team",
    "source_provider","source_match_ref","competition_ref","season_ref",
    "home_team_ref","away_team_ref","home_team_id","away_team_id",
}
_FORBIDDEN_ARTIFACT_KEY_TOKENS = ("outcome","score","settlement","p_market","price_decimal","odds")


@dataclass(frozen=True, slots=True)
class ProspectivePredictionRow:
    fixture_id: str
    stable_fixture_key: str
    event_time: int
    prediction_cutoff: int
    competition_ref: str
    group: str
    role: str | None
    line: float
    raw_probability_over: float
    p_model_over: float
    component_0_probability: float
    component_1_probability: float
    component_gap: float
    expected_count: float
    dynamic_effective_team_support: float
    dynamic_supported: bool
    prior_competition_match_count: int
    neighbor_count: int | None
    ood_flags: tuple[str,...]
    calibration_bin_index: int
    calibration_bin_unique_fixtures: int
    calibration_bin_supported: bool
    reliability_error_ci: tuple[float,float] | None

    def to_dict(self) -> dict[str,Any]:
        d=asdict(self)
        d["ood_flags"]=list(self.ood_flags)
        d["reliability_error_ci"]=list(self.reliability_error_ci) if self.reliability_error_ci is not None else None
        return d

    def to_layer5_model_point(self) -> ModelMarketPoint:
        return ModelMarketPoint(
            line=self.line,
            p_model_over=self.p_model_over,
            dynamic_supported=self.dynamic_supported,
            effective_support=self.dynamic_effective_team_support,
            calibration_unique_fixtures=self.calibration_bin_unique_fixtures,
            reliability_error_ci=self.reliability_error_ci,
            hard_ood_flags=tuple(x for x in self.ood_flags if x=="INTENSITY_OOD"),
            component_dispersion_ood="COMPONENT_GAP_OOD" in self.ood_flags,
        )


def _read_json(path: Path) -> dict[str,Any]:
    value=json.loads(Path(path).read_text())
    if not isinstance(value,dict):
        raise ValueError(path)
    return value


def _clip(p: float, lo: float, hi: float) -> float:
    return min(max(float(p),float(lo)),float(hi))


def _poisson_over(mu: float, line: float) -> float:
    return float(poisson.sf(int(line),float(mu)))


def _nb2_over(mu: float, line: float, alpha: float) -> float:
    return float(1.0-nb2_cdf(int(line),float(mu),float(alpha)))


def _identity_only_target(match: ResearchMatch) -> None:
    non_identity = []
    for f in fields(ResearchMatch):
        if f.name in _IDENTITY_FIELDS:
            continue
        if getattr(match,f.name) is not None:
            non_identity.append(f.name)
    if non_identity:
        raise ValueError("target fixture contains non-identity evidence: "+",".join(sorted(non_identity)))
    if match.source_provider.upper()!="THESTATSAPI":
        raise ValueError("prospective target provider must be THESTATSAPI")
    if not match.source_match_ref or not match.competition_ref or not match.season_ref:
        raise ValueError("prospective target stable identity incomplete")
    if not match.home_team_ref or not match.away_team_ref:
        raise ValueError("prospective target team identity incomplete")
    if match.competition_ref not in COMPETITION_UNIVERSE:
        raise ValueError("prospective target outside frozen competition universe")


def blank_target_from_match(match: ResearchMatch) -> ResearchMatch:
    return ResearchMatch(
        match_id=match.match_id,
        date_unix=match.date_unix,
        league_id=match.league_id,
        season=match.season,
        home_team=match.home_team,
        away_team=match.away_team,
        source_provider=match.source_provider,
        source_match_ref=match.source_match_ref,
        competition_ref=match.competition_ref,
        season_ref=match.season_ref,
        home_team_ref=match.home_team_ref,
        away_team_ref=match.away_team_ref,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
    )


def _validate_inputs(
    *,
    target: ResearchMatch,
    history: tuple[ResearchMatch,...],
    cohort_manifest: dict[str,Any],
    history_snapshot_hash: str,
    history_snapshot_captured_at: float,
    history_snapshot_competitions: Iterable[str],
) -> tuple[int,str]:
    _identity_only_target(target)
    fixtures=validate_prospective_cohort_manifest(cohort_manifest)
    by_id={x.fixture_id:x for x in fixtures}
    fixture_id=str(target.source_match_ref)
    if fixture_id not in by_id:
        raise ValueError("target fixture not present in frozen cohort")
    if abs(float(by_id[fixture_id].event_time)-float(target.date_unix))>1e-6:
        raise ValueError("target kickoff differs from frozen cohort")
    cutoff=int(target.date_unix)-DEFAULT_DECISION_HORIZON_SECONDS
    if float(history_snapshot_captured_at)>cutoff:
        raise ValueError("history snapshot captured after target T-6h cutoff")
    if set(history_snapshot_competitions)!=set(COMPETITION_UNIVERSE):
        raise ValueError("history snapshot does not cover complete frozen competition universe")
    if cutoff > BASE_CORPUS_LAST_KICKOFF_TS + DEFAULT_AVAILABILITY_EMBARGO_SECONDS:
        if history_snapshot_hash==BASE_CORPUS_MANIFEST_HASH:
            raise ValueError("stale canonical history requires incremental snapshot")
    keys=set()
    for m in history:
        if m.source_provider.upper()!="THESTATSAPI":
            raise ValueError("history provider mismatch")
        if m.competition_ref not in COMPETITION_UNIVERSE:
            raise ValueError("history row outside frozen competition universe")
        if int(m.date_unix)>=int(target.date_unix):
            raise ValueError("history contains target/future kickoff")
        key=m.stable_fixture_key
        if not key:
            raise ValueError("history stable fixture identity missing")
        if key in keys:
            raise ValueError("duplicate history fixture")
        keys.add(key)
    if target.stable_fixture_key in keys:
        raise ValueError("target leaked into historical rows")
    return cutoff,fixture_id


def _load_frozen_model(repo_root: Path):
    freeze=_read_json(repo_root/"evidence/layer4/QFE_LAYER4_MODEL_FREEZE_V3_BOUND.json")
    if freeze.get("model_freeze_hash")!=LAYER4_MODEL_FREEZE_HASH:
        raise ValueError("Layer4 V3 freeze binding mismatch")
    protocol=_read_json(repo_root/"evidence/prospective_v1/QFE_PROSPECTIVE_EXECUTION_PROTOCOL_V1.json")
    if protocol.get("protocol_hash")!=EXECUTION_PROTOCOL_HASH:
        raise ValueError("prospective execution protocol binding mismatch")
    layer5=_read_json(repo_root/"evidence/layer5/QFE_LAYER5_PROTOCOL_V1_2.json")
    if layer5.get("protocol_hash")!=LAYER5_PROTOCOL_HASH:
        raise ValueError("Layer5 V1.2 binding mismatch")

    structured=_read_json(repo_root/"evidence/layer3/STRUCTURED_DEVELOPMENT_OOF_V3_PIT.json")
    goal_cfg=DynamicCountConfig(**structured["goal_dynamic_config"])
    corner_cfg=DynamicCountConfig(**structured["corner_dynamic_config"])
    if goal_cfg.identity_hash!=freeze["goals_total_2_5"]["dynamic_config_hash"]:
        raise ValueError("goal dynamic config binding mismatch")
    if corner_cfg.identity_hash!=freeze["corners"]["dynamic_config_hash"]:
        raise ValueError("corner dynamic config binding mismatch")

    similar_source=_read_json(repo_root/"evidence/layer3/SIMILAR_CONTEXT_DEVELOPMENT_OOF.json")
    similar_cfg=SimilarContextConfig(**similar_source["config"])
    if similar_cfg.identity_hash!=freeze["goals_total_2_5"]["similar_context_config_hash"]:
        raise ValueError("similar-context config binding mismatch")
    return freeze,goal_cfg,corner_cfg,similar_cfg


def _similar_goal_prediction(
    pit_rows,
    target_row,
    config: SimilarContextConfig,
    cutoff: int,
) -> tuple[float,int,int]:
    training=[
        r for r in pit_rows
        if r.fixture_key!=target_row.fixture_key
        and r.competition_ref==target_row.competition_ref
        and r.targets.get("goals_total_regulation") is not None
        and int(r.kickoff_ts)+DEFAULT_AVAILABILITY_EMBARGO_SECONDS<=cutoff
    ]
    if not training:
        raise ValueError("no eligible similar-context history")
    tx=_raw_matrix(training,GOALS_FEATURES)
    ty=np.asarray([float(r.targets["goals_total_regulation"]) for r in training],float)
    vx=_raw_matrix([target_row],GOALS_FEATURES)[0]
    mu,sd=_fit_scaler(tx)
    prior=float(np.mean(ty))
    pred,k,nobs=_predict_one(tx,ty,vx,mu,sd,config,prior)
    return float(pred),int(k),int(nobs)


def _support_for(
    freeze: dict[str,Any],
    *,
    group: str,
    raw_probability: float,
    expected_count: float,
    component_gap: float,
) -> tuple[tuple[str,...],int,int,bool,tuple[float,float]|None]:
    ref=freeze["prediction_support"]["reference_thresholds"][group]
    flags=[]
    if expected_count<float(ref["intensity"]["low"]) or expected_count>float(ref["intensity"]["high"]):
        flags.append("INTENSITY_OOD")
    if component_gap>float(ref["gap_high"]):
        flags.append("COMPONENT_GAP_OOD")
    bins=list(freeze["prediction_support"]["probability_bins"])
    idx=int(np.searchsorted(np.asarray(bins),float(raw_probability),side="right")-1)
    idx=max(0,min(idx,len(bins)-2))
    support_rows=freeze["prediction_support"]["v3_diagnostics"][group]["support_bins"]
    sb=next(x for x in support_rows if int(x["bin_index"])==idx)
    ci=sb.get("reliability_error_ci")
    ci_pair=None if ci is None else (float(ci["ci_low"]),float(ci["ci_high"]))
    return tuple(flags),idx,int(sb["unique_fixtures"]),bool(sb["supported"]),ci_pair


def _calibrated(
    freeze: dict[str,Any],
    group: str,
    p: float,
    *,
    role: str|None,
    competition_ref: str,
) -> float:
    if group=="GOALS_TOTAL":
        spec=freeze["goals_total_2_5"]["calibrator_spec"]
    elif group=="CORNERS_SIDE":
        spec=freeze["corners"]["side"]["calibrator_spec"]
    elif group=="CORNERS_TOTAL":
        spec=freeze["corners"]["total"]["calibrator_spec"]
    else:
        raise ValueError(group)
    cal=calibrator_from_spec(spec)
    q=cal.transform(float(p),role=role,competition_ref=competition_ref)
    lo=float(freeze["output_probability_clip"]["lower"])
    hi=float(freeze["output_probability_clip"]["upper"])
    return _clip(q,lo,hi)


def build_prospective_prediction_bundle(
    *,
    repo_root: Path,
    history_matches: Iterable[ResearchMatch],
    target_match: ResearchMatch,
    cohort_manifest: dict[str,Any],
    history_snapshot_hash: str,
    history_snapshot_captured_at: float,
    history_snapshot_competitions: Iterable[str],
) -> dict[str,Any]:
    repo_root=Path(repo_root)
    history=tuple(sorted(tuple(history_matches),key=lambda m:(int(m.date_unix),m.stable_fixture_key or "")))
    cutoff,fixture_id=_validate_inputs(
        target=target_match,
        history=history,
        cohort_manifest=cohort_manifest,
        history_snapshot_hash=history_snapshot_hash,
        history_snapshot_captured_at=history_snapshot_captured_at,
        history_snapshot_competitions=history_snapshot_competitions,
    )
    freeze,goal_cfg,corner_cfg,similar_cfg=_load_frozen_model(repo_root)
    target=target_match
    all_matches=history+(target,)

    spec=PITDatasetSpec(
        decision_horizon_seconds=DEFAULT_DECISION_HORIZON_SECONDS,
        reconstructed_post_match_embargo_seconds=DEFAULT_AVAILABILITY_EMBARGO_SECONDS,
    )
    pit=PITDatasetBuilder(spec=spec).build(all_matches)
    target_row=next(r for r in pit.rows if r.fixture_key==target.stable_fixture_key)

    gf_map={f.fixture_key:f for f in DynamicHierarchicalCountBaseline(GOALS_TARGET,goal_cfg).walk_forward(all_matches)}
    cf_map={f.fixture_key:f for f in DynamicHierarchicalCountBaseline(CORNERS_TARGET,corner_cfg).walk_forward(all_matches)}
    gf=gf_map[target.stable_fixture_key]
    cf=cf_map[target.stable_fixture_key]
    sim_mu,neighbor_count,_=_similar_goal_prediction(pit.rows,target_row,similar_cfg,cutoff)

    comp_n=int(target_row.features.get("competition_history_matches") or 0)
    rows=[]

    gw=float(freeze["goals_total_2_5"]["similar_context_weight"])
    dyn_p=_poisson_over(gf.lambda_total,GOAL_LINE)
    sim_p=_poisson_over(sim_mu,GOAL_LINE)
    blend_mu=(1.0-gw)*gf.lambda_total+gw*sim_mu
    raw=_poisson_over(blend_mu,GOAL_LINE)
    gap=abs(dyn_p-sim_p)
    flags,bi,bn,bs,ci=_support_for(freeze,group="GOALS_TOTAL",raw_probability=raw,expected_count=blend_mu,component_gap=gap)
    rows.append(ProspectivePredictionRow(
        fixture_id, target.stable_fixture_key, int(target.date_unix), cutoff, target.competition_ref,
        "GOALS_TOTAL",None,GOAL_LINE,raw,_calibrated(freeze,"GOALS_TOTAL",raw,role=None,competition_ref=target.competition_ref),
        dyn_p,sim_p,gap,blend_mu,gf.effective_support,gf.supported,comp_n,neighbor_count,
        flags,bi,bn,bs,ci,
    ))

    cw=float(freeze["corners"]["nb2_joint_mixture_weight"])
    alpha=float(freeze["corners"]["common_nb2_alpha"])
    for role,mu in (("HOME",cf.lambda_home),("AWAY",cf.lambda_away)):
        for line in SIDE_LINES:
            p0=_poisson_over(mu,line)
            p1=_nb2_over(mu,line,alpha)
            raw=(1.0-cw)*p0+cw*p1
            gap=abs(p0-p1)
            flags,bi,bn,bs,ci=_support_for(freeze,group="CORNERS_SIDE",raw_probability=raw,expected_count=mu,component_gap=gap)
            rows.append(ProspectivePredictionRow(
                fixture_id,target.stable_fixture_key,int(target.date_unix),cutoff,target.competition_ref,
                "CORNERS_SIDE",role,float(line),raw,_calibrated(freeze,"CORNERS_SIDE",raw,role=role,competition_ref=target.competition_ref),
                p0,p1,gap,mu,cf.effective_support,cf.supported,comp_n,None,
                flags,bi,bn,bs,ci,
            ))
    mu=cf.lambda_total
    for line in TOTAL_LINES:
        p0=_poisson_over(mu,line)
        p1=1.0-nb2_total_under_probability_from_sides(line,cf.lambda_home,cf.lambda_away,alpha)
        raw=(1.0-cw)*p0+cw*p1
        gap=abs(p0-p1)
        flags,bi,bn,bs,ci=_support_for(freeze,group="CORNERS_TOTAL",raw_probability=raw,expected_count=mu,component_gap=gap)
        rows.append(ProspectivePredictionRow(
            fixture_id,target.stable_fixture_key,int(target.date_unix),cutoff,target.competition_ref,
            "CORNERS_TOTAL",None,float(line),raw,_calibrated(freeze,"CORNERS_TOTAL",raw,role=None,competition_ref=target.competition_ref),
            p0,p1,gap,mu,cf.effective_support,cf.supported,comp_n,None,
            flags,bi,bn,bs,ci,
        ))

    rows.sort(key=lambda r:(r.group,r.role or "",r.line))
    row_dicts=[r.to_dict() for r in rows]
    history_content_hash=sha256_json([m.to_dict() for m in history])
    bundle={
        "version":PREDICTION_BUNDLE_VERSION,
        "scientific_status":"FROZEN_OUTCOME_BLIND_ODDS_BLIND_PMODEL",
        "cohort_hash":cohort_manifest["cohort_hash"],
        "history_snapshot_hash":str(history_snapshot_hash),
        "history_snapshot_captured_at":float(history_snapshot_captured_at),
        "history_content_hash":history_content_hash,
        "history_match_count":len(history),
        "history_competitions":sorted(set(history_snapshot_competitions)),
        "execution_protocol_hash":EXECUTION_PROTOCOL_HASH,
        "layer4_model_freeze_hash":LAYER4_MODEL_FREEZE_HASH,
        "layer5_protocol_hash":LAYER5_PROTOCOL_HASH,
        "fixture":{
            "fixture_id":fixture_id,
            "stable_fixture_key":target.stable_fixture_key,
            "event_time":int(target.date_unix),
            "prediction_cutoff":cutoff,
            "competition_ref":target.competition_ref,
            "season_ref":target.season_ref,
            "home_team_ref":target.home_team_ref,
            "away_team_ref":target.away_team_ref,
            "home_team_name":target.home_team,
            "away_team_name":target.away_team,
        },
        "lineage":{
            "pit_target_row_hash":target_row.content_hash,
            "eligible_history_matches":target_row.lineage.eligible_history_matches,
            "max_source_kickoff_ts":target_row.lineage.max_source_kickoff_ts,
            "max_source_available_at":target_row.lineage.max_source_available_at,
            "source_chain_digest":target_row.lineage.source_chain_digest,
        },
        "dynamic":{
            "goals_config_hash":goal_cfg.identity_hash,
            "corners_config_hash":corner_cfg.identity_hash,
            "goals_lambda_home":gf.lambda_home,
            "goals_lambda_away":gf.lambda_away,
            "corners_lambda_home":cf.lambda_home,
            "corners_lambda_away":cf.lambda_away,
            "goals_effective_support":gf.effective_support,
            "corners_effective_support":cf.effective_support,
        },
        "similar_context":{
            "config_hash":similar_cfg.identity_hash,
            "expected_goals_total":sim_mu,
            "neighbor_count":neighbor_count,
        },
        "rows":row_dicts,
        "rows_hash":sha256_json(row_dicts),
    }
    for key in _walk_keys(bundle):
        low=key.lower()
        if any(tok in low for tok in _FORBIDDEN_ARTIFACT_KEY_TOKENS):
            raise ValueError(f"forbidden prediction artifact field: {key}")
    bundle["bundle_hash"]=sha256_json(bundle)
    return bundle


def _walk_keys(value: Any):
    if isinstance(value,dict):
        for k,v in value.items():
            yield str(k)
            yield from _walk_keys(v)
    elif isinstance(value,list):
        for v in value:
            yield from _walk_keys(v)


def write_prospective_prediction_bundle(path: Path, bundle: dict[str,Any]) -> Path:
    path=Path(path)
    payload=(canonical_json(bundle)+"\n").encode()
    if path.exists():
        if path.read_bytes()!=payload:
            raise FileExistsError(f"frozen prediction bundle differs: {path}")
        return path
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(payload)
    return path
