"""Deterministic similar-context OOF benchmark for QFE V2 Layer 3."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any

import numpy as np
from scipy.stats import poisson

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.multiseason import MultiSeasonPITCorpus
from src.research.models.structured_distributions import binary_log_loss, brier_score
from src.research.evaluation.chronology import (
    CALIBRATION_START_TS,
    DEVELOPMENT_OOF_FOLDS,
    development_fold_manifest,
)

SIMILAR_OOF_VERSION = "qfe-layer3-similar-context-oof-v1"

GOALS_FEATURES = (
    "home_comp_goals_for_mean", "home_comp_goals_against_mean",
    "away_comp_goals_for_mean", "away_comp_goals_against_mean",
    "home_comp_shots_for_mean", "home_comp_shots_against_mean",
    "away_comp_shots_for_mean", "away_comp_shots_against_mean",
    "home_comp_shots_on_target_for_mean", "home_comp_shots_on_target_against_mean",
    "away_comp_shots_on_target_for_mean", "away_comp_shots_on_target_against_mean",
    "home_venue_goals_for_mean", "home_venue_goals_against_mean",
    "away_venue_goals_for_mean", "away_venue_goals_against_mean",
)
CORNERS_FEATURES = (
    "home_comp_corners_for_mean", "home_comp_corners_against_mean",
    "away_comp_corners_for_mean", "away_comp_corners_against_mean",
    "home_comp_shots_for_mean", "home_comp_shots_against_mean",
    "away_comp_shots_for_mean", "away_comp_shots_against_mean",
    "home_comp_shots_on_target_for_mean", "home_comp_shots_on_target_against_mean",
    "away_comp_shots_on_target_for_mean", "away_comp_shots_on_target_against_mean",
    "home_comp_possession_for_mean", "home_comp_possession_against_mean",
    "away_comp_possession_for_mean", "away_comp_possession_against_mean",
)


@dataclass(frozen=True, slots=True)
class SimilarContextConfig:
    k_neighbors: int = 75
    distance_floor: float = 0.25
    prior_weight: float = 25.0
    min_observed_dimensions: int = 8

    @property
    def identity_hash(self) -> str:
        return sha256_json(asdict(self))


@dataclass(frozen=True, slots=True)
class SimilarOOFRow:
    fixture_key: str
    fold_id: str
    target: str
    kickoff_ts: int
    competition_ref: str
    line: float
    observed_total: int
    expected_total: float
    probability_over: float
    count_log_probability: float
    binary_log_loss: float
    brier: float
    neighbor_count: int
    observed_dimensions: int

    def to_dict(self): return asdict(self)


@dataclass(frozen=True, slots=True)
class SimilarSummary:
    target: str
    n: int
    mean_count_nll: float
    mean_binary_log_loss: float
    mean_brier: float

    def to_dict(self): return asdict(self)


@dataclass(frozen=True, slots=True)
class SimilarOOFArtifact:
    version: str
    corpus_manifest_hash: str
    development_fold_manifest: dict[str, Any]
    config: dict[str, Any]
    config_hash: str
    feature_sets: dict[str, tuple[str, ...]]
    rows: tuple[SimilarOOFRow, ...]
    summaries: tuple[SimilarSummary, ...]

    def to_dict(self):
        return {
            "version": self.version,
            "corpus_manifest_hash": self.corpus_manifest_hash,
            "development_fold_manifest": self.development_fold_manifest,
            "config": self.config,
            "config_hash": self.config_hash,
            "feature_sets": {k:list(v) for k,v in self.feature_sets.items()},
            "rows": [r.to_dict() for r in self.rows],
            "summaries": [s.to_dict() for s in self.summaries],
        }

    @property
    def artifact_hash(self): return sha256_json(self.to_dict())


def _raw_matrix(rows, names):
    x=np.full((len(rows),len(names)),np.nan,float)
    for i,row in enumerate(rows):
        for j,name in enumerate(names):
            v=row.features.get(name)
            if v is not None: x[i,j]=float(v)
    return x


def _fit_scaler(x):
    with np.errstate(all="ignore"):
        mu=np.nanmean(x,axis=0)
        sd=np.nanstd(x,axis=0)
    mu=np.where(np.isfinite(mu),mu,0.0)
    sd=np.where(np.isfinite(sd)&(sd>1e-8),sd,1.0)
    return mu,sd


def _predict_one(train_x, train_y, valid_x, mu, sd, config, prior_mean):
    train_obs=np.isfinite(train_x)
    valid_obs=np.isfinite(valid_x)
    common=train_obs & valid_obs[None,:]
    n_common=common.sum(axis=1)
    z_train=(np.where(train_obs,train_x,mu)-mu)/sd
    z_valid=(np.where(valid_obs,valid_x,mu)-mu)/sd
    delta=(z_train-z_valid[None,:])**2
    delta=np.where(common,delta,0.0)
    dist=np.sqrt(delta.sum(axis=1)/np.maximum(n_common,1))
    eligible=np.where(n_common>=config.min_observed_dimensions)[0]
    if len(eligible)==0:
        return prior_mean,0,int(valid_obs.sum())
    order=eligible[np.argsort(dist[eligible],kind="mergesort")]
    chosen=order[:min(config.k_neighbors,len(order))]
    weights=1.0/(dist[chosen]+config.distance_floor)
    weighted=float(np.dot(weights,train_y[chosen])/weights.sum())
    neighbor_weight=float(weights.sum())
    estimate=(neighbor_weight*weighted+config.prior_weight*prior_mean)/(neighbor_weight+config.prior_weight)
    return max(estimate,1e-6),len(chosen),int(valid_obs.sum())


def _summary(rows,target):
    rr=[r for r in rows if r.target==target]
    return SimilarSummary(
        target=target,n=len(rr),
        mean_count_nll=mean(-r.count_log_probability for r in rr),
        mean_binary_log_loss=mean(r.binary_log_loss for r in rr),
        mean_brier=mean(r.brier for r in rr),
    )


def build_similar_oof(*,corpus: MultiSeasonPITCorpus,config: SimilarContextConfig=SimilarContextConfig()):
    all_rows=[r for r in corpus.pit.rows if r.kickoff_ts<CALIBRATION_START_TS]
    out=[]
    specs=(
        ("goals",GOALS_FEATURES,"goals_total_regulation",2.5),
        ("corners",CORNERS_FEATURES,"corners_total_regulation",9.5),
    )
    for fold in DEVELOPMENT_OOF_FOLDS:
        for target,names,target_id,line in specs:
            training=[r for r in all_rows if r.kickoff_ts<fold.validation_start_ts and r.targets.get(target_id) is not None]
            valid=[r for r in all_rows if fold.contains_validation(int(r.kickoff_ts)) and r.targets.get(target_id) is not None]
            for comp in sorted({r.competition_ref for r in valid}):
                tr=[r for r in training if r.competition_ref==comp]
                va=[r for r in valid if r.competition_ref==comp]
                if not tr: continue
                tx=_raw_matrix(tr,names); vx=_raw_matrix(va,names)
                ty=np.asarray([r.targets[target_id] for r in tr],float)
                mu,sd=_fit_scaler(tx); prior=float(np.mean(ty))
                for row,x in zip(va,vx,strict=True):
                    pred,k,nobs=_predict_one(tx,ty,x,mu,sd,config,prior)
                    total=int(row.targets[target_id]); outcome=total>line
                    p_over=float(1.0-poisson.cdf(int(line),pred))
                    out.append(SimilarOOFRow(
                        fixture_key=row.fixture_key,fold_id=fold.fold_id,target=target,
                        kickoff_ts=int(row.kickoff_ts),competition_ref=comp,line=line,
                        observed_total=total,expected_total=pred,probability_over=p_over,
                        count_log_probability=float(poisson.logpmf(total,pred)),
                        binary_log_loss=binary_log_loss(p_over,outcome),
                        brier=brier_score(p_over,outcome),neighbor_count=k,
                        observed_dimensions=nobs,
                    ))
    out.sort(key=lambda r:(r.kickoff_ts,r.fixture_key,r.target))
    return SimilarOOFArtifact(
        version=SIMILAR_OOF_VERSION,
        corpus_manifest_hash=corpus.manifest.manifest_hash,
        development_fold_manifest=development_fold_manifest(tuple(m for m in corpus.matches if m.date_unix<CALIBRATION_START_TS)),
        config=asdict(config),config_hash=config.identity_hash,
        feature_sets={"goals":GOALS_FEATURES,"corners":CORNERS_FEATURES},
        rows=tuple(out),summaries=tuple(_summary(out,t) for t in ("goals","corners")),
    )


def write_similar_oof(path, artifact: SimilarOOFArtifact) -> None:
    from pathlib import Path
    output = Path(path)
    payload = canonical_json(artifact.to_dict()) + "\n"
    if output.exists():
        if output.read_text() != payload:
            raise FileExistsError(f"OOF artifact exists with different content: {output}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload)
