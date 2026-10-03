"""Immutable expanding-window OOF evaluation for Layer 3 structured candidates."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import log
from pathlib import Path
from statistics import mean
from typing import Any

from scipy.stats import poisson

from src.research.data_source import ResearchMatch
from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.multiseason import MultiSeasonPITCorpus
from src.research.models.dixon_coles import DixonColesModel
from src.research.models.dynamic_count_strength import (
    CORNERS_TARGET,
    GOALS_TARGET,
    CountTargetSpec,
    DynamicCountConfig,
    DynamicHierarchicalCountBaseline,
)
from src.research.models.structured_distributions import (
    binary_log_loss,
    brier_score,
    dixon_coles_total_pmf,
    dixon_coles_under_probability,
    independent_btts_probability,
    dixon_coles_btts_probability,
    fit_dixon_coles_rho,
    fit_nb2_dispersion,
    nb2_cdf,
    nb2_logpmf,
    nb2_total_pmf_from_sides,
    nb2_total_under_probability_from_sides,
)
from src.research.evaluation.chronology import (
    CALIBRATION_START_TS,
    DEVELOPMENT_OOF_FOLDS,
    development_fold_manifest,
)

STRUCTURED_OOF_VERSION = "qfe-layer3-structured-oof-v2"


@dataclass(frozen=True, slots=True)
class OOFRow:
    fixture_key: str
    fold_id: str
    target: str
    candidate: str
    kickoff_ts: int
    competition_ref: str
    line: float
    observed_total: int
    probability_over: float
    count_log_probability: float
    binary_log_loss: float
    brier: float
    expected_total: float
    fitted_parameter_name: str | None
    fitted_parameter_value: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BinaryOOFRow:
    fixture_key: str
    fold_id: str
    market: str
    candidate: str
    kickoff_ts: int
    competition_ref: str
    outcome: bool
    probability: float
    log_loss: float
    brier: float
    fitted_parameter_name: str | None
    fitted_parameter_value: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BinarySummary:
    market: str
    candidate: str
    n: int
    mean_log_loss: float
    mean_brier: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CandidateSummary:
    target: str
    candidate: str
    n: int
    mean_count_nll: float
    mean_binary_log_loss: float
    mean_brier: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StructuredOOFArtifact:
    version: str
    corpus_manifest_hash: str
    development_fold_manifest: dict[str, Any]
    goal_dynamic_config: dict[str, Any]
    goal_dynamic_config_hash: str
    corner_dynamic_config: dict[str, Any]
    corner_dynamic_config_hash: str
    rows: tuple[OOFRow, ...]
    summaries: tuple[CandidateSummary, ...]
    binary_rows: tuple[BinaryOOFRow, ...]
    binary_summaries: tuple[BinarySummary, ...]
    fitted_fold_parameters: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "corpus_manifest_hash": self.corpus_manifest_hash,
            "development_fold_manifest": self.development_fold_manifest,
            "goal_dynamic_config": self.goal_dynamic_config,
            "goal_dynamic_config_hash": self.goal_dynamic_config_hash,
            "corner_dynamic_config": self.corner_dynamic_config,
            "corner_dynamic_config_hash": self.corner_dynamic_config_hash,
            "rows": [r.to_dict() for r in self.rows],
            "summaries": [s.to_dict() for s in self.summaries],
            "binary_rows": [r.to_dict() for r in self.binary_rows],
            "binary_summaries": [s.to_dict() for s in self.binary_summaries],
            "fitted_fold_parameters": list(self.fitted_fold_parameters),
        }

    @property
    def artifact_hash(self) -> str:
        return sha256_json(self.to_dict())


def _poisson_total_probability_over(mean_total: float, line: float) -> float:
    return float(1.0 - poisson.cdf(int(line), mean_total))


def _candidate_summary(rows: list[OOFRow], target: str, candidate: str) -> CandidateSummary:
    subset = [r for r in rows if r.target == target and r.candidate == candidate]
    if not subset:
        raise ValueError(f"no OOF rows for {target}/{candidate}")
    return CandidateSummary(
        target=target,
        candidate=candidate,
        n=len(subset),
        mean_count_nll=mean(-r.count_log_probability for r in subset),
        mean_binary_log_loss=mean(r.binary_log_loss for r in subset),
        mean_brier=mean(r.brier for r in subset),
    )


def _binary_summary(rows: list[BinaryOOFRow], market: str, candidate: str) -> BinarySummary:
    subset = [r for r in rows if r.market == market and r.candidate == candidate]
    if not subset:
        raise ValueError(f"no binary OOF rows for {market}/{candidate}")
    return BinarySummary(
        market=market,
        candidate=candidate,
        n=len(subset),
        mean_log_loss=mean(r.log_loss for r in subset),
        mean_brier=mean(r.brier for r in subset),
    )


def _dynamic_forecasts(
    matches: tuple[ResearchMatch, ...],
    target: CountTargetSpec,
    config: DynamicCountConfig,
):
    model = DynamicHierarchicalCountBaseline(target, config)
    return {f.fixture_key: f for f in model.walk_forward(matches)}


def build_structured_oof(
    *,
    corpus: MultiSeasonPITCorpus,
    goal_config: DynamicCountConfig,
    corner_config: DynamicCountConfig,
) -> StructuredOOFArtifact:
    # Explicitly stop before calibration. Protected/calibration outcomes cannot
    # enter state, parameter fitting, candidate comparison, or diagnostics here.
    dev_history = tuple(
        m for m in corpus.matches if m.date_unix < CALIBRATION_START_TS
    )
    by_key = {m.stable_fixture_key: m for m in dev_history}
    goal_forecasts = _dynamic_forecasts(dev_history, GOALS_TARGET, goal_config)
    corner_forecasts = _dynamic_forecasts(dev_history, CORNERS_TARGET, corner_config)

    rows: list[OOFRow] = []
    binary_rows: list[BinaryOOFRow] = []
    fitted: list[dict[str, Any]] = []

    for fold in DEVELOPMENT_OOF_FOLDS:
        train = [m for m in dev_history if m.date_unix < fold.validation_start_ts]
        valid = [m for m in dev_history if fold.contains_validation(m.date_unix)]

        # Goals: fit only the dependence parameter on earlier dynamic forecasts.
        dc_training = []
        for m in train:
            obs = GOALS_TARGET.observed_counts(m)
            f = goal_forecasts.get(m.stable_fixture_key)
            if obs is None or f is None:
                continue
            dc_training.append((f.lambda_home, f.lambda_away, obs[0], obs[1]))
        dc_fit = fit_dixon_coles_rho(dc_training)
        fitted.append({
            "fold_id": fold.fold_id,
            "target": "goals",
            "candidate": "dynamic_dixon_coles",
            "parameter": "rho",
            "value": dc_fit.rho,
            "n_training": dc_fit.n_observations,
        })

        goal_nb_training = []
        for m in train:
            obs = GOALS_TARGET.observed_counts(m)
            f = goal_forecasts.get(m.stable_fixture_key)
            if obs is None or f is None:
                continue
            goal_nb_training.append((f.lambda_total, obs[0] + obs[1]))
        goal_nb_fit = fit_nb2_dispersion(goal_nb_training)
        fitted.append({
            "fold_id": fold.fold_id,
            "target": "goals",
            "candidate": "dynamic_nb2",
            "parameter": "alpha",
            "value": goal_nb_fit.alpha,
            "n_training": goal_nb_fit.n_observations,
        })

        competition_dc: dict[str, DixonColesModel] = {}
        competitions = sorted({m.competition_ref for m in valid if m.competition_ref})
        for competition_ref in competitions:
            comp_train = []
            for m in train:
                if m.competition_ref != competition_ref:
                    continue
                obs = GOALS_TARGET.observed_counts(m)
                if obs is None or not m.home_team_ref or not m.away_team_ref:
                    continue
                comp_train.append({
                    "home_team": m.home_team_ref,
                    "away_team": m.away_team_ref,
                    "home_goals": obs[0],
                    "away_goals": obs[1],
                    "date_unix": m.date_unix,
                })
            model = DixonColesModel(
                line=2.5,
                time_decay_days=365.0,
                min_team_matches=3,
                max_goals=12,
                shrinkage_factor=12.0,
            )
            model.fit(
                comp_train,
                [False] * len(comp_train),
                training_start=min((r["date_unix"] for r in comp_train), default=None),
                training_end=fold.validation_start_ts - 1,
            )
            competition_dc[competition_ref] = model
            params = model.params
            fitted.append({
                "fold_id": fold.fold_id,
                "target": "goals",
                "candidate": "competition_dixon_coles",
                "competition_ref": competition_ref,
                "parameter": "rho",
                "value": params.rho if params is not None else None,
                "n_training": len(comp_train),
            })

        # Corners: fit one common NB2 side-dispersion parameter using only
        # earlier home/away side observations. The total-market distribution is
        # then obtained by convolving the two side distributions.
        nb_training = []
        for m in train:
            obs = CORNERS_TARGET.observed_counts(m)
            f = corner_forecasts.get(m.stable_fixture_key)
            if obs is None or f is None:
                continue
            nb_training.append((f.lambda_home, obs[0]))
            nb_training.append((f.lambda_away, obs[1]))
        nb_fit = fit_nb2_dispersion(nb_training)
        fitted.append({
            "fold_id": fold.fold_id,
            "target": "corners",
            "candidate": "dynamic_side_nb2",
            "parameter": "alpha",
            "value": nb_fit.alpha,
            "n_training": nb_fit.n_observations,
        })

        for m in valid:
            assert m.stable_fixture_key and m.competition_ref

            # GOALS candidates at 2.5
            gobs = GOALS_TARGET.observed_counts(m)
            gf = goal_forecasts[m.stable_fixture_key]
            if gobs is not None:
                total = gobs[0] + gobs[1]
                outcome_over = total > 2.5
                p_over_pois = _poisson_total_probability_over(gf.lambda_total, 2.5)
                lp_pois = float(poisson.logpmf(total, gf.lambda_total))
                rows.append(OOFRow(
                    fixture_key=m.stable_fixture_key,
                    fold_id=fold.fold_id,
                    target="goals",
                    candidate="dynamic_poisson",
                    kickoff_ts=m.date_unix,
                    competition_ref=m.competition_ref,
                    line=2.5,
                    observed_total=total,
                    probability_over=p_over_pois,
                    count_log_probability=lp_pois,
                    binary_log_loss=binary_log_loss(p_over_pois, outcome_over),
                    brier=brier_score(p_over_pois, outcome_over),
                    expected_total=gf.lambda_total,
                    fitted_parameter_name=None,
                    fitted_parameter_value=None,
                ))
                p_under_dc = dixon_coles_under_probability(
                    2.5, gf.lambda_home, gf.lambda_away, dc_fit.rho
                )
                p_over_dc = 1.0 - p_under_dc
                pmf_dc = max(
                    dixon_coles_total_pmf(
                        total, gf.lambda_home, gf.lambda_away, dc_fit.rho
                    ),
                    1e-300,
                )
                rows.append(OOFRow(
                    fixture_key=m.stable_fixture_key,
                    fold_id=fold.fold_id,
                    target="goals",
                    candidate="dynamic_dixon_coles",
                    kickoff_ts=m.date_unix,
                    competition_ref=m.competition_ref,
                    line=2.5,
                    observed_total=total,
                    probability_over=p_over_dc,
                    count_log_probability=log(pmf_dc),
                    binary_log_loss=binary_log_loss(p_over_dc, outcome_over),
                    brier=brier_score(p_over_dc, outcome_over),
                    expected_total=gf.lambda_total,
                    fitted_parameter_name="rho",
                    fitted_parameter_value=dc_fit.rho,
                ))
                p_over_gnb = 1.0 - nb2_cdf(2, gf.lambda_total, goal_nb_fit.alpha)
                lp_gnb = nb2_logpmf(total, gf.lambda_total, goal_nb_fit.alpha)
                rows.append(OOFRow(
                    fixture_key=m.stable_fixture_key,
                    fold_id=fold.fold_id,
                    target="goals",
                    candidate="dynamic_nb2",
                    kickoff_ts=m.date_unix,
                    competition_ref=m.competition_ref,
                    line=2.5,
                    observed_total=total,
                    probability_over=p_over_gnb,
                    count_log_probability=lp_gnb,
                    binary_log_loss=binary_log_loss(p_over_gnb, outcome_over),
                    brier=brier_score(p_over_gnb, outcome_over),
                    expected_total=gf.lambda_total,
                    fitted_parameter_name="alpha",
                    fitted_parameter_value=goal_nb_fit.alpha,
                ))
                dc_model = competition_dc[m.competition_ref]
                dc_features = {
                    "home_team": m.home_team_ref,
                    "away_team": m.away_team_ref,
                }
                dc_lh, dc_la = dc_model.get_expected_goals(dc_features)
                dc_over, _ = dc_model.predict_over_under(dc_features, 2.5)
                grid = dc_model.predict_scoreline(dc_features)
                pmf_total = sum(
                    grid[i, total - i]
                    for i in range(grid.shape[0])
                    if 0 <= total - i < grid.shape[1]
                )
                pmf_total = max(float(pmf_total), 1e-300)
                rho = dc_model.params.rho if dc_model.params is not None else None
                rows.append(OOFRow(
                    fixture_key=m.stable_fixture_key,
                    fold_id=fold.fold_id,
                    target="goals",
                    candidate="competition_dixon_coles",
                    kickoff_ts=m.date_unix,
                    competition_ref=m.competition_ref,
                    line=2.5,
                    observed_total=total,
                    probability_over=float(dc_over),
                    count_log_probability=log(pmf_total),
                    binary_log_loss=binary_log_loss(float(dc_over), outcome_over),
                    brier=brier_score(float(dc_over), outcome_over),
                    expected_total=dc_lh + dc_la,
                    fitted_parameter_name="rho",
                    fitted_parameter_value=rho,
                ))

                btts_outcome = gobs[0] > 0 and gobs[1] > 0
                p_btts_ind = independent_btts_probability(gf.lambda_home, gf.lambda_away)
                binary_rows.append(BinaryOOFRow(
                    fixture_key=m.stable_fixture_key, fold_id=fold.fold_id,
                    market="btts", candidate="dynamic_independent_poisson",
                    kickoff_ts=m.date_unix, competition_ref=m.competition_ref,
                    outcome=btts_outcome, probability=p_btts_ind,
                    log_loss=binary_log_loss(p_btts_ind,btts_outcome),
                    brier=brier_score(p_btts_ind,btts_outcome),
                    fitted_parameter_name=None, fitted_parameter_value=None,
                ))
                p_btts_dc = dixon_coles_btts_probability(
                    gf.lambda_home, gf.lambda_away, dc_fit.rho
                )
                binary_rows.append(BinaryOOFRow(
                    fixture_key=m.stable_fixture_key, fold_id=fold.fold_id,
                    market="btts", candidate="dynamic_dixon_coles",
                    kickoff_ts=m.date_unix, competition_ref=m.competition_ref,
                    outcome=btts_outcome, probability=p_btts_dc,
                    log_loss=binary_log_loss(p_btts_dc,btts_outcome),
                    brier=brier_score(p_btts_dc,btts_outcome),
                    fitted_parameter_name="rho", fitted_parameter_value=dc_fit.rho,
                ))
                p_btts_comp = float(grid[1:,1:].sum())
                binary_rows.append(BinaryOOFRow(
                    fixture_key=m.stable_fixture_key, fold_id=fold.fold_id,
                    market="btts", candidate="competition_dixon_coles",
                    kickoff_ts=m.date_unix, competition_ref=m.competition_ref,
                    outcome=btts_outcome, probability=p_btts_comp,
                    log_loss=binary_log_loss(p_btts_comp,btts_outcome),
                    brier=brier_score(p_btts_comp,btts_outcome),
                    fitted_parameter_name="rho", fitted_parameter_value=rho,
                ))

            # CORNERS candidates at 9.5
            cobs = CORNERS_TARGET.observed_counts(m)
            cf = corner_forecasts[m.stable_fixture_key]
            if cobs is not None:
                total = cobs[0] + cobs[1]
                outcome_over = total > 9.5
                p_over_pois = _poisson_total_probability_over(cf.lambda_total, 9.5)
                lp_pois = float(poisson.logpmf(total, cf.lambda_total))
                rows.append(OOFRow(
                    fixture_key=m.stable_fixture_key,
                    fold_id=fold.fold_id,
                    target="corners",
                    candidate="dynamic_poisson",
                    kickoff_ts=m.date_unix,
                    competition_ref=m.competition_ref,
                    line=9.5,
                    observed_total=total,
                    probability_over=p_over_pois,
                    count_log_probability=lp_pois,
                    binary_log_loss=binary_log_loss(p_over_pois, outcome_over),
                    brier=brier_score(p_over_pois, outcome_over),
                    expected_total=cf.lambda_total,
                    fitted_parameter_name=None,
                    fitted_parameter_value=None,
                ))
                p_over_nb = 1.0 - nb2_total_under_probability_from_sides(
                    9.5, cf.lambda_home, cf.lambda_away, nb_fit.alpha
                )
                pmf_nb = max(
                    nb2_total_pmf_from_sides(
                        total, cf.lambda_home, cf.lambda_away, nb_fit.alpha
                    ),
                    1e-300,
                )
                lp_nb = log(pmf_nb)
                rows.append(OOFRow(
                    fixture_key=m.stable_fixture_key,
                    fold_id=fold.fold_id,
                    target="corners",
                    candidate="dynamic_side_nb2",
                    kickoff_ts=m.date_unix,
                    competition_ref=m.competition_ref,
                    line=9.5,
                    observed_total=total,
                    probability_over=p_over_nb,
                    count_log_probability=lp_nb,
                    binary_log_loss=binary_log_loss(p_over_nb, outcome_over),
                    brier=brier_score(p_over_nb, outcome_over),
                    expected_total=cf.lambda_total,
                    fitted_parameter_name="alpha",
                    fitted_parameter_value=nb_fit.alpha,
                ))

    rows.sort(key=lambda r: (r.kickoff_ts, r.fixture_key, r.target, r.candidate))
    binary_rows.sort(key=lambda r: (r.kickoff_ts, r.fixture_key, r.market, r.candidate))
    summaries = tuple(
        _candidate_summary(rows, target, candidate)
        for target, candidate in (
            ("goals", "dynamic_poisson"),
            ("goals", "dynamic_dixon_coles"),
            ("goals", "dynamic_nb2"),
            ("goals", "competition_dixon_coles"),
            ("corners", "dynamic_poisson"),
            ("corners", "dynamic_side_nb2"),
        )
    )
    binary_summaries = tuple(
        _binary_summary(binary_rows, "btts", candidate)
        for candidate in (
            "dynamic_independent_poisson",
            "dynamic_dixon_coles",
            "competition_dixon_coles",
        )
    )
    return StructuredOOFArtifact(
        version=STRUCTURED_OOF_VERSION,
        corpus_manifest_hash=corpus.manifest.manifest_hash,
        development_fold_manifest=development_fold_manifest(dev_history),
        goal_dynamic_config=asdict(goal_config),
        goal_dynamic_config_hash=goal_config.identity_hash,
        corner_dynamic_config=asdict(corner_config),
        corner_dynamic_config_hash=corner_config.identity_hash,
        rows=tuple(rows),
        summaries=summaries,
        binary_rows=tuple(binary_rows),
        binary_summaries=binary_summaries,
        fitted_fold_parameters=tuple(fitted),
    )


def write_structured_oof(path: Path, artifact: StructuredOOFArtifact) -> None:
    payload = canonical_json(artifact.to_dict()) + "\n"
    path = Path(path)
    if path.exists():
        if path.read_text() != payload:
            raise FileExistsError(f"OOF artifact exists with different content: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)
