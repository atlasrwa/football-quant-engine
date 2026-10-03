"""Leakage-safe nonlinear tabular OOF benchmark for QFE V2 Layer 3."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from scipy.stats import poisson

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.multiseason import MultiSeasonPITCorpus
from src.research.models.structured_distributions import binary_log_loss, brier_score
from src.research.evaluation.chronology import (
    CALIBRATION_START_TS,
    DEVELOPMENT_OOF_FOLDS,
    development_fold_manifest,
)

TABULAR_OOF_VERSION = "qfe-layer3-tabular-oof-v1"


@dataclass(frozen=True, slots=True)
class TabularConfig:
    learning_rate: float = 0.05
    max_iter: int = 160
    max_leaf_nodes: int = 15
    min_samples_leaf: int = 30
    l2_regularization: float = 2.0
    max_features: float = 0.75
    random_state: int = 1729

    @property
    def identity_hash(self) -> str:
        return sha256_json(asdict(self))


@dataclass(frozen=True, slots=True)
class TabularOOFRow:
    fixture_key: str
    fold_id: str
    target: str
    kickoff_ts: int
    competition_ref: str
    line: float
    observed_total: int
    lambda_home: float
    lambda_away: float
    probability_over: float
    count_log_probability: float
    binary_log_loss: float
    brier: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TabularSummary:
    target: str
    n: int
    mean_count_nll: float
    mean_binary_log_loss: float
    mean_brier: float

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TabularOOFArtifact:
    version: str
    corpus_manifest_hash: str
    development_fold_manifest: dict[str, Any]
    config: dict[str, Any]
    config_hash: str
    feature_names: tuple[str, ...]
    competition_refs: tuple[str, ...]
    rows: tuple[TabularOOFRow, ...]
    summaries: tuple[TabularSummary, ...]

    def to_dict(self):
        return {
            "version": self.version,
            "corpus_manifest_hash": self.corpus_manifest_hash,
            "development_fold_manifest": self.development_fold_manifest,
            "config": self.config,
            "config_hash": self.config_hash,
            "feature_names": list(self.feature_names),
            "competition_refs": list(self.competition_refs),
            "rows": [r.to_dict() for r in self.rows],
            "summaries": [s.to_dict() for s in self.summaries],
        }

    @property
    def artifact_hash(self) -> str:
        return sha256_json(self.to_dict())


def _feature_schema(corpus: MultiSeasonPITCorpus) -> tuple[str, ...]:
    # Schema is derived only from pre-calibration rows. No protected values are
    # consulted even for column discovery.
    names = {
        name
        for row in corpus.pit.rows
        if row.kickoff_ts < CALIBRATION_START_TS
        for name in row.features
    }
    forbidden = ("odds", "price", "market", "target", "outcome")
    safe = [
        name for name in names
        if not any(token in name.lower() for token in forbidden)
    ]
    return tuple(sorted(safe))


def _matrix(rows, feature_names, competition_refs):
    comp_index = {c:i for i,c in enumerate(competition_refs)}
    x = np.full((len(rows), len(feature_names)+len(competition_refs)), np.nan, dtype=float)
    for i,row in enumerate(rows):
        for j,name in enumerate(feature_names):
            value=row.features.get(name)
            if value is not None:
                x[i,j]=float(value)
        if row.competition_ref in comp_index:
            x[i,len(feature_names)+comp_index[row.competition_ref]]=1.0
        # Missing dummy positions represent zero, not unknown.
        for j in range(len(competition_refs)):
            idx=len(feature_names)+j
            if np.isnan(x[i,idx]): x[i,idx]=0.0
    return x


def _model(config: TabularConfig) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="poisson",
        learning_rate=config.learning_rate,
        max_iter=config.max_iter,
        max_leaf_nodes=config.max_leaf_nodes,
        min_samples_leaf=config.min_samples_leaf,
        l2_regularization=config.l2_regularization,
        max_features=config.max_features,
        random_state=config.random_state,
        early_stopping=False,
    )


def _summary(rows: list[TabularOOFRow], target: str) -> TabularSummary:
    rr=[r for r in rows if r.target==target]
    return TabularSummary(
        target=target,
        n=len(rr),
        mean_count_nll=mean(-r.count_log_probability for r in rr),
        mean_binary_log_loss=mean(r.binary_log_loss for r in rr),
        mean_brier=mean(r.brier for r in rr),
    )


def build_tabular_oof(
    *,
    corpus: MultiSeasonPITCorpus,
    config: TabularConfig = TabularConfig(),
) -> TabularOOFArtifact:
    feature_names=_feature_schema(corpus)
    competition_refs=tuple(sorted({
        row.competition_ref for row in corpus.pit.rows
        if row.kickoff_ts < CALIBRATION_START_TS
    }))
    pit_by_key={row.fixture_key:row for row in corpus.pit.rows}
    match_by_key={m.stable_fixture_key:m for m in corpus.matches}
    all_precal=[row for row in corpus.pit.rows if row.kickoff_ts < CALIBRATION_START_TS]
    out: list[TabularOOFRow]=[]

    specs=(
        ("goals","goals_home_regulation","goals_away_regulation",2.5),
        ("corners","corners_home_regulation","corners_away_regulation",9.5),
    )
    for fold in DEVELOPMENT_OOF_FOLDS:
        train_rows=[r for r in all_precal if r.kickoff_ts < fold.validation_start_ts]
        valid_rows=[r for r in all_precal if fold.contains_validation(int(r.kickoff_ts))]
        for target,home_target,away_target,line in specs:
            train=[r for r in train_rows if r.targets.get(home_target) is not None and r.targets.get(away_target) is not None]
            valid=[r for r in valid_rows if r.targets.get(home_target) is not None and r.targets.get(away_target) is not None]
            x_train=_matrix(train,feature_names,competition_refs)
            x_valid=_matrix(valid,feature_names,competition_refs)
            yh=np.asarray([r.targets[home_target] for r in train],dtype=float)
            ya=np.asarray([r.targets[away_target] for r in train],dtype=float)
            home_model=_model(config); away_model=_model(config)
            home_model.fit(x_train,yh); away_model.fit(x_train,ya)
            lh=np.maximum(home_model.predict(x_valid),1e-6)
            la=np.maximum(away_model.predict(x_valid),1e-6)
            for row,mu_h,mu_a in zip(valid,lh,la,strict=True):
                total=int(row.targets[home_target]+row.targets[away_target])
                mu=float(mu_h+mu_a)
                p_over=float(1.0-poisson.cdf(int(line),mu))
                outcome=total>line
                out.append(TabularOOFRow(
                    fixture_key=row.fixture_key,
                    fold_id=fold.fold_id,
                    target=target,
                    kickoff_ts=int(row.kickoff_ts),
                    competition_ref=row.competition_ref,
                    line=line,
                    observed_total=total,
                    lambda_home=float(mu_h),
                    lambda_away=float(mu_a),
                    probability_over=p_over,
                    count_log_probability=float(poisson.logpmf(total,mu)),
                    binary_log_loss=binary_log_loss(p_over,outcome),
                    brier=brier_score(p_over,outcome),
                ))
    out.sort(key=lambda r:(r.kickoff_ts,r.fixture_key,r.target))
    return TabularOOFArtifact(
        version=TABULAR_OOF_VERSION,
        corpus_manifest_hash=corpus.manifest.manifest_hash,
        development_fold_manifest=development_fold_manifest(
            tuple(m for m in corpus.matches if m.date_unix<CALIBRATION_START_TS)
        ),
        config=asdict(config),
        config_hash=config.identity_hash,
        feature_names=feature_names,
        competition_refs=competition_refs,
        rows=tuple(out),
        summaries=tuple(_summary(out,t) for t in ("goals","corners")),
    )


def write_tabular_oof(path, artifact: TabularOOFArtifact) -> None:
    from pathlib import Path
    output = Path(path)
    payload = canonical_json(artifact.to_dict()) + "\n"
    if output.exists():
        if output.read_text() != payload:
            raise FileExistsError(f"OOF artifact exists with different content: {output}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload)
