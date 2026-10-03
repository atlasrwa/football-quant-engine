"""QFE V2 Layer 3.1 preregistered multi-line corner OOF evaluation."""
from __future__ import annotations

import hashlib
import gzip
import json
from dataclasses import asdict, dataclass
from math import floor
from pathlib import Path
from statistics import mean
from typing import Any

from scipy.stats import poisson

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.multiseason import MultiSeasonPITCorpus
from src.research.evaluation.chronology import CALIBRATION_START_TS, DEVELOPMENT_OOF_FOLDS
from src.research.evaluation.layer31_protocol import Layer31Protocol, protocol_v1
from src.research.evaluation.paired_uncertainty import PairedBlockResult, paired_block_bootstrap
from src.research.models.dynamic_count_strength import (
    CORNERS_TARGET,
    DynamicCountConfig,
    DynamicHierarchicalCountBaseline,
)
from src.research.models.structured_distributions import (
    binary_log_loss,
    brier_score,
    fit_nb2_dispersion,
    nb2_cdf,
    nb2_total_under_probability_from_sides,
)

LAYER31_OOF_VERSION = "qfe-layer3.1-corners-multiline-oof-v1"


@dataclass(frozen=True, slots=True)
class MarketEventRow:
    fixture_key: str
    fold_id: str
    kickoff_ts: int
    competition_ref: str
    market_scope: str  # SIDE or TOTAL
    role: str | None
    line: float
    candidate: str
    observed_count: int
    outcome_over: bool
    probability_over: float
    log_loss: float
    brier: float
    lambda_home: float
    lambda_away: float
    alpha: float | None

    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True, slots=True)
class ComparisonSlice:
    scope: str
    role: str | None
    line: float | None
    competition_ref: str | None
    n_pairs: int
    log_loss: dict[str, Any]
    brier: dict[str, Any]

    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True, slots=True)
class Layer31Artifact:
    version: str
    protocol: dict[str, Any]
    protocol_hash: str
    corpus_manifest_hash: str
    corner_config: dict[str, Any]
    corner_config_hash: str
    source_structured_oof_hash: str
    fold_parameters: tuple[dict[str, Any], ...]
    rows: tuple[MarketEventRow, ...]
    primary_comparisons: tuple[ComparisonSlice, ...]
    diagnostic_comparisons: tuple[ComparisonSlice, ...]
    side_decision: str
    total_decision: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "protocol": self.protocol,
            "protocol_hash": self.protocol_hash,
            "corpus_manifest_hash": self.corpus_manifest_hash,
            "corner_config": self.corner_config,
            "corner_config_hash": self.corner_config_hash,
            "source_structured_oof_hash": self.source_structured_oof_hash,
            "fold_parameters": list(self.fold_parameters),
            "rows": [r.to_dict() for r in self.rows],
            "primary_comparisons": [r.to_dict() for r in self.primary_comparisons],
            "diagnostic_comparisons": [r.to_dict() for r in self.diagnostic_comparisons],
            "side_decision": self.side_decision,
            "total_decision": self.total_decision,
        }

    @property
    def artifact_hash(self) -> str: return sha256_json(self.to_dict())


def _poisson_over(mu: float, line: float) -> float:
    return float(poisson.sf(int(floor(line)), mu))


def _nb2_over(mu: float, line: float, alpha: float) -> float:
    return float(1.0 - nb2_cdf(int(floor(line)), mu, alpha))


def _dynamic_forecasts(matches, config):
    model=DynamicHierarchicalCountBaseline(CORNERS_TARGET,config)
    return {f.fixture_key:f for f in model.walk_forward(matches)}


def _paired(rows: list[MarketEventRow], protocol: Layer31Protocol, scope: str, *, role=None, line=None, competition_ref=None) -> ComparisonSlice:
    selected=[r for r in rows if r.market_scope==scope and (role is None or r.role==role) and (line is None or r.line==line) and (competition_ref is None or r.competition_ref==competition_ref)]
    by={}
    for r in selected:
        key=(r.fixture_key,r.role,r.line)
        by.setdefault(key,{})[r.candidate]=r
    pairs=[]
    for key,cands in by.items():
        if set(cands) >= {"dynamic_poisson","dynamic_side_nb2"}:
            pairs.append((cands["dynamic_poisson"],cands["dynamic_side_nb2"]))
    if len(pairs)<30: raise ValueError(f"insufficient paired rows for {scope}/{role}/{line}/{competition_ref}: {len(pairs)}")
    ll=paired_block_bootstrap(
        [(a.kickoff_ts,a.log_loss,b.log_loss) for a,b in pairs],
        metric="binary_log_loss",bootstrap_replicates=protocol.bootstrap_replicates,seed=protocol.bootstrap_seed,
    )
    br=paired_block_bootstrap(
        [(a.kickoff_ts,a.brier,b.brier) for a,b in pairs],
        metric="brier",bootstrap_replicates=protocol.bootstrap_replicates,seed=protocol.bootstrap_seed,
    )
    return ComparisonSlice(scope,role,line,competition_ref,len(pairs),ll.to_dict(),br.to_dict())


def _assert_monotone(rows: list[MarketEventRow]) -> None:
    groups={}
    for r in rows:
        key=(r.fixture_key,r.market_scope,r.role,r.candidate)
        groups.setdefault(key,[]).append(r)
    for key,vals in groups.items():
        vals=sorted(vals,key=lambda x:x.line)
        probs=[x.probability_over for x in vals]
        if any(probs[i+1] > probs[i] + 1e-12 for i in range(len(probs)-1)):
            raise ValueError(f"non-monotone over ladder: {key}")


def _primary_decision(primary: ComparisonSlice, *, role_slices: tuple[ComparisonSlice,...]=()) -> str:
    ll=primary.log_loss; br=primary.brier
    primary_pass=ll["mean_improvement"]>0 and ll["ci_low"]>0 and br["mean_improvement"]>0 and br["ci_low"]>0
    if role_slices:
        role_guard=all(x.log_loss["ci_high"] >= 0 for x in role_slices)
    else:
        role_guard=True
    if primary_pass and role_guard: return "NB2_DEVELOPMENT_CANDIDATE"
    if ll["ci_high"]<0 and br["ci_high"]<0: return "NB2_REJECT_MATERIALLY_WORSE"
    if ll["mean_improvement"]>0 and br["mean_improvement"]>0: return "NB2_WEAK_OR_INCONCLUSIVE"
    return "NB2_NOT_SUPPORTED_OR_MIXED"


def build_layer31_oof(*, corpus: MultiSeasonPITCorpus, corner_config: DynamicCountConfig, frozen_fold_alphas: dict[str,float], source_structured_oof_hash: str, protocol: Layer31Protocol | None=None) -> Layer31Artifact:
    protocol=protocol or protocol_v1()
    if protocol.market_odds_allowed or protocol.calibration_outcomes_allowed or protocol.protected_outcomes_allowed:
        raise ValueError("Layer3.1 protocol boundary violated")
    dev=tuple(m for m in corpus.matches if m.date_unix<CALIBRATION_START_TS)
    forecasts=_dynamic_forecasts(dev,corner_config)
    rows=[]; fold_params=[]
    for fold in DEVELOPMENT_OOF_FOLDS:
        train=[m for m in dev if m.date_unix<fold.validation_start_ts]
        valid=[m for m in dev if fold.contains_validation(m.date_unix)]
        fit_rows=[]
        for m in train:
            obs=CORNERS_TARGET.observed_counts(m); f=forecasts.get(m.stable_fixture_key)
            if obs is None or f is None: continue
            fit_rows.extend(((f.lambda_home,obs[0]),(f.lambda_away,obs[1])))
        nb=fit_nb2_dispersion(fit_rows)
        expected=frozen_fold_alphas.get(fold.fold_id)
        if expected is None or abs(nb.alpha-expected)>1e-10:
            raise ValueError(f"NB2 fold alpha drift {fold.fold_id}: {nb.alpha} != {expected}")
        fold_params.append({"fold_id":fold.fold_id,"alpha":nb.alpha,"n_training":nb.n_observations})
        for m in valid:
            obs=CORNERS_TARGET.observed_counts(m); f=forecasts.get(m.stable_fixture_key)
            if obs is None or f is None or not m.stable_fixture_key or not m.competition_ref: continue
            for role,count,mu in (("home",obs[0],f.lambda_home),("away",obs[1],f.lambda_away)):
                for line in protocol.side_lines:
                    outcome=count>line
                    for cand,p,alpha in (
                        ("dynamic_poisson",_poisson_over(mu,line),None),
                        ("dynamic_side_nb2",_nb2_over(mu,line,nb.alpha),nb.alpha),
                    ):
                        rows.append(MarketEventRow(m.stable_fixture_key,fold.fold_id,m.date_unix,m.competition_ref,"SIDE",role,line,cand,count,outcome,p,binary_log_loss(p,outcome),brier_score(p,outcome),f.lambda_home,f.lambda_away,alpha))
            total=obs[0]+obs[1]
            for line in protocol.total_lines:
                outcome=total>line
                p_pois=_poisson_over(f.lambda_total,line)
                p_nb=1.0-nb2_total_under_probability_from_sides(line,f.lambda_home,f.lambda_away,nb.alpha)
                for cand,p,alpha in (("dynamic_poisson",p_pois,None),("dynamic_side_nb2",p_nb,nb.alpha)):
                    rows.append(MarketEventRow(m.stable_fixture_key,fold.fold_id,m.date_unix,m.competition_ref,"TOTAL",None,line,cand,total,outcome,p,binary_log_loss(p,outcome),brier_score(p,outcome),f.lambda_home,f.lambda_away,alpha))
    _assert_monotone(rows)
    side=_paired(rows,protocol,"SIDE")
    home=_paired(rows,protocol,"SIDE",role="home"); away=_paired(rows,protocol,"SIDE",role="away")
    total=_paired(rows,protocol,"TOTAL")
    diagnostics=[home,away]
    diagnostics += [_paired(rows,protocol,"SIDE",role=role,line=line) for role in protocol.side_roles for line in protocol.side_lines]
    diagnostics += [_paired(rows,protocol,"TOTAL",line=line) for line in protocol.total_lines]
    competitions=sorted({r.competition_ref for r in rows})
    diagnostics += [_paired(rows,protocol,"SIDE",competition_ref=c) for c in competitions]
    diagnostics += [_paired(rows,protocol,"TOTAL",competition_ref=c) for c in competitions]
    return Layer31Artifact(
        version=LAYER31_OOF_VERSION,protocol=protocol.to_dict(),protocol_hash=protocol.protocol_hash,
        corpus_manifest_hash=corpus.manifest.manifest_hash,corner_config=asdict(corner_config),corner_config_hash=corner_config.identity_hash,
        source_structured_oof_hash=source_structured_oof_hash,fold_parameters=tuple(fold_params),rows=tuple(rows),
        primary_comparisons=(side,total),diagnostic_comparisons=tuple(diagnostics),
        side_decision=_primary_decision(side,role_slices=(home,away)),total_decision=_primary_decision(total),
    )


def render_layer31_markdown(a: Layer31Artifact) -> str:
    lines=["# QFE V2 Layer 3.1 — Multi-line Corner Market-Event Coverage","",f"Protocol hash: `{a.protocol_hash}`",f"Artifact hash: `{a.artifact_hash}`","","> DEVELOPMENT OOF ONLY. No bookmaker odds, calibration outcomes, or protected outcomes were used.",""]
    for x in a.primary_comparisons:
        lines += [f"## {x.scope}","",f"- Pairs: **{x.n_pairs}**",f"- Log Loss improvement: **{x.log_loss['mean_improvement']:+.6f}** (95% CI {x.log_loss['ci_low']:+.6f} to {x.log_loss['ci_high']:+.6f})",f"- Brier improvement: **{x.brier['mean_improvement']:+.6f}** (95% CI {x.brier['ci_low']:+.6f} to {x.brier['ci_high']:+.6f})",""]
    lines += ["## Decisions","",f"- Side corners: **{a.side_decision}**",f"- Total corners: **{a.total_decision}**","","Per-line, role and competition slices are diagnostic only and cannot promote a candidate by themselves.",""]
    return "\n".join(lines)


def write_layer31_artifact(json_path: Path, markdown_path: Path, rows_gz_path: Path, artifact: Layer31Artifact) -> None:
    full=artifact.to_dict()
    rows=full.pop("rows")
    rows_text="".join(canonical_json(row)+"\n" for row in rows).encode("utf-8")
    rows_gz=gzip.compress(rows_text,compresslevel=9,mtime=0)
    summary={**full,"artifact_hash":artifact.artifact_hash,"row_count":len(rows),"rows_hash":sha256_json(rows),"rows_file":Path(rows_gz_path).name,"rows_encoding":"canonical-jsonl+gzip(mtime=0)"}
    text_payloads=((Path(json_path),canonical_json(summary)+'\n'),(Path(markdown_path),render_layer31_markdown(artifact)))
    for path,payload in text_payloads:
        if path.exists():
            if path.read_text()!=payload: raise FileExistsError(f"Layer3.1 artifact differs: {path}")
        else:
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text(payload)
    rp=Path(rows_gz_path)
    if rp.exists():
        if rp.read_bytes()!=rows_gz: raise FileExistsError(f"Layer3.1 rows artifact differs: {rp}")
    else:
        rp.parent.mkdir(parents=True,exist_ok=True); rp.write_bytes(rows_gz)


def verify_layer31_artifact(json_path: Path, rows_gz_path: Path) -> str:
    """Verify compact evidence reconstructs the exact full scientific artifact."""
    summary=json.loads(Path(json_path).read_text())
    compressed=Path(rows_gz_path).read_bytes()
    raw=gzip.decompress(compressed)
    rows=[json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(rows)!=summary.get("row_count"):
        raise ValueError("Layer3.1 row_count mismatch")
    if sha256_json(rows)!=summary.get("rows_hash"):
        raise ValueError("Layer3.1 rows_hash mismatch")
    canonical_rows="".join(canonical_json(row)+"\n" for row in rows).encode("utf-8")
    if canonical_rows!=raw:
        raise ValueError("Layer3.1 rows are not canonical JSONL")
    if gzip.compress(canonical_rows,compresslevel=9,mtime=0)!=compressed:
        raise ValueError("Layer3.1 gzip encoding is not deterministic")
    extras={"artifact_hash","row_count","rows_hash","rows_file","rows_encoding"}
    full={k:v for k,v in summary.items() if k not in extras}
    full["rows"]=rows
    digest=sha256_json(full)
    if digest!=summary.get("artifact_hash"):
        raise ValueError("Layer3.1 full scientific artifact hash mismatch")
    return digest
