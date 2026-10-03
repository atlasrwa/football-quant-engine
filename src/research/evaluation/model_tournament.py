"""Development-only model tournament for QFE V2 Layer 3.

The tournament is constrained by the frozen chronology:

- WARMUP updates state but is not scored.
- DEVELOPMENT is the only partition available to candidate/hyperparameter
  selection.
- CALIBRATION and PROTECTED are never passed to the candidate models here.

Two stages are deliberately separated:

1. intensity tournament: select the dynamic hierarchy hyperparameters using
   side-count Poisson NLL;
2. observation-distribution tournament: holding the selected intensity path
   fixed, compare goals Poisson vs Dixon-Coles and corners Poisson vs NB2.

Every prediction is one-step-ahead and same-kickoff batched.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Sequence

import numpy as np
from scipy.stats import poisson

from src.research.data_source import ResearchMatch
from src.research.dataset.manifest import canonical_json, rows_digest, sha256_json
from src.research.evaluation.chronology import (
    DEVELOPMENT_END_TS,
    WARMUP_END_TS,
    ChronologyManifest,
    EvaluationPartition,
    assert_selection_partition_allowed,
    partition_for_kickoff,
)
from src.research.models.distribution_candidates import (
    OnlineGridSelector,
    binary_log_loss,
    dixon_coles_btts_probability,
    dixon_coles_joint_nll,
    dixon_coles_total_over_probability,
    nb2_side_nll,
    nb2_side_over_probability,
    nb2_total_over_probability,
    poisson_joint_nll,
)
from src.research.models.dynamic_count_strength import (
    CORNERS_TARGET,
    GOALS_TARGET,
    CountTargetSpec,
    DynamicCountConfig,
    DynamicHierarchicalCountBaseline,
    HierarchicalCountForecast,
)


TOURNAMENT_VERSION = "qfe-layer3-development-tournament-v1"
BOOTSTRAP_SEED = 20261002
BOOTSTRAP_REPS = 5000

GOALS_RHO_GRID: tuple[float, ...] = (
    0.0,
    -0.05,
    -0.10,
    -0.15,
    0.05,
)
CORNERS_ALPHA_GRID: tuple[float, ...] = (
    0.0,
    0.05,
    0.10,
    0.20,
    0.35,
    0.50,
    0.75,
)


@dataclass(frozen=True, slots=True)
class PairedBlockInterval:
    mean_delta: float
    lower_95: float
    upper_95: float
    n_rows: int
    n_time_blocks: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class IntensityCandidateResult:
    candidate_id: str
    config: dict[str, Any]
    config_hash: str
    n_scored: int
    mean_poisson_nll: float
    mean_mae: float
    improvement_vs_anchor: PairedBlockInterval | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "config": self.config,
            "config_hash": self.config_hash,
            "n_scored": self.n_scored,
            "mean_poisson_nll": self.mean_poisson_nll,
            "mean_mae": self.mean_mae,
            "improvement_vs_anchor": (
                self.improvement_vs_anchor.to_dict()
                if self.improvement_vs_anchor is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class IntensityTournamentResult:
    target: str
    anchor_candidate_id: str
    selected_candidate_id: str
    selected_config_hash: str
    selected_config: dict[str, Any]
    candidates: tuple[IntensityCandidateResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "anchor_candidate_id": self.anchor_candidate_id,
            "selected_candidate_id": self.selected_candidate_id,
            "selected_config_hash": self.selected_config_hash,
            "selected_config": self.selected_config,
            "candidates": [row.to_dict() for row in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class DevelopmentOOFRow:
    fixture_key: str
    kickoff_ts: int
    month_block: str
    competition_ref: str
    season_ref: str
    target: str
    lambda_home: float
    lambda_away: float
    observed_home: int
    observed_away: int
    effective_support: float
    supported: bool
    structured_parameter: float
    poisson_joint_nll: float
    structured_joint_nll: float
    poisson_event_log_loss: float
    structured_event_log_loss: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DistributionTournamentResult:
    target: str
    structured_family: str
    parameter_grid: tuple[float, ...]
    selected_parameter_frequency: dict[str, int]
    n_scored: int
    poisson_joint_nll: float
    structured_joint_nll: float
    joint_nll_improvement: PairedBlockInterval
    poisson_event_log_loss: float
    structured_event_log_loss: float
    event_log_loss_improvement: PairedBlockInterval
    by_competition_joint_nll_delta: dict[str, float]
    by_competition_event_log_loss_delta: dict[str, float]
    oof_rows_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "structured_family": self.structured_family,
            "parameter_grid": list(self.parameter_grid),
            "selected_parameter_frequency": dict(
                sorted(self.selected_parameter_frequency.items())
            ),
            "n_scored": self.n_scored,
            "poisson_joint_nll": self.poisson_joint_nll,
            "structured_joint_nll": self.structured_joint_nll,
            "joint_nll_improvement": self.joint_nll_improvement.to_dict(),
            "poisson_event_log_loss": self.poisson_event_log_loss,
            "structured_event_log_loss": self.structured_event_log_loss,
            "event_log_loss_improvement": (
                self.event_log_loss_improvement.to_dict()
            ),
            "by_competition_joint_nll_delta": dict(
                sorted(self.by_competition_joint_nll_delta.items())
            ),
            "by_competition_event_log_loss_delta": dict(
                sorted(self.by_competition_event_log_loss_delta.items())
            ),
            "oof_rows_hash": self.oof_rows_hash,
        }


@dataclass(frozen=True, slots=True)
class Layer3DevelopmentTournament:
    version: str
    chronology_manifest_hash: str
    corpus_manifest_hash: str
    calibration_rows_scored: int
    protected_rows_scored: int
    intensity_results: tuple[IntensityTournamentResult, ...]
    distribution_results: tuple[DistributionTournamentResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "chronology_manifest_hash": self.chronology_manifest_hash,
            "corpus_manifest_hash": self.corpus_manifest_hash,
            "calibration_rows_scored": self.calibration_rows_scored,
            "protected_rows_scored": self.protected_rows_scored,
            "intensity_results": [
                row.to_dict() for row in self.intensity_results
            ],
            "distribution_results": [
                row.to_dict() for row in self.distribution_results
            ],
        }

    @property
    def tournament_hash(self) -> str:
        return sha256_json(self.to_dict())


def predefined_intensity_grid() -> tuple[tuple[str, DynamicCountConfig], ...]:
    """Bounded grid frozen before development scoring."""
    rows: list[tuple[str, DynamicCountConfig]] = []
    for half_life in (90.0, 180.0, 360.0):
        for influence in (0.50, 0.75, 1.00):
            for team_comp_prior in (4.0, 8.0, 16.0):
                candidate_id = (
                    f"hl{int(half_life):03d}_"
                    f"inf{int(round(influence * 100)):03d}_"
                    f"tcp{int(team_comp_prior):02d}"
                )
                rows.append(
                    (
                        candidate_id,
                        DynamicCountConfig(
                            half_life_days=half_life,
                            team_influence=influence,
                            team_comp_prior_weight=team_comp_prior,
                        ),
                    )
                )
    return tuple(rows)


ANCHOR_CANDIDATE_ID = "hl180_inf075_tcp08"


def _development_stream(
    matches: Iterable[ResearchMatch],
) -> tuple[ResearchMatch, ...]:
    """Return only warmup+development rows without inspecting later outcomes."""
    rows = tuple(
        sorted(
            (
                match
                for match in matches
                if match.date_unix < DEVELOPMENT_END_TS
            ),
            key=lambda match: (
                match.date_unix,
                match.stable_fixture_key or "",
            ),
        )
    )
    if rows and rows[-1].date_unix >= DEVELOPMENT_END_TS:
        raise AssertionError("selection stream crossed development boundary")
    return rows


def _month_block(timestamp: int) -> str:
    dt = datetime.fromtimestamp(timestamp, timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


def _paired_block_interval(
    rows: Sequence[tuple[str, float]],
) -> PairedBlockInterval:
    """Block bootstrap mean paired delta; positive means candidate is better."""
    if not rows:
        raise ValueError("paired interval requires rows")

    by_block: dict[str, list[float]] = defaultdict(list)
    for block, delta in rows:
        by_block[block].append(float(delta))

    blocks = sorted(by_block)
    block_sums = np.array(
        [sum(by_block[block]) for block in blocks],
        dtype=float,
    )
    block_counts = np.array(
        [len(by_block[block]) for block in blocks],
        dtype=float,
    )
    observed = float(block_sums.sum() / block_counts.sum())

    if len(blocks) == 1:
        return PairedBlockInterval(
            mean_delta=observed,
            lower_95=observed,
            upper_95=observed,
            n_rows=len(rows),
            n_time_blocks=1,
        )

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    indices = rng.integers(
        0,
        len(blocks),
        size=(BOOTSTRAP_REPS, len(blocks)),
    )
    sampled_sums = block_sums[indices].sum(axis=1)
    sampled_counts = block_counts[indices].sum(axis=1)
    sampled = sampled_sums / sampled_counts
    lower, upper = np.quantile(sampled, (0.025, 0.975))
    return PairedBlockInterval(
        mean_delta=observed,
        lower_95=float(lower),
        upper_95=float(upper),
        n_rows=len(rows),
        n_time_blocks=len(blocks),
    )


def _score_intensity_candidate(
    *,
    stream: Sequence[ResearchMatch],
    target: CountTargetSpec,
    config: DynamicCountConfig,
) -> tuple[
    list[tuple[str, float, float]],
    dict[str, HierarchicalCountForecast],
]:
    model = DynamicHierarchicalCountBaseline(target, config)
    predictions = model.walk_forward(stream)
    by_match = {
        match.stable_fixture_key: match
        for match in stream
    }
    scored: list[tuple[str, float, float]] = []
    prediction_map: dict[str, HierarchicalCountForecast] = {}

    for prediction in predictions:
        prediction_map[prediction.fixture_key] = prediction
        match = by_match[prediction.fixture_key]
        if partition_for_kickoff(match.date_unix) != EvaluationPartition.DEVELOPMENT:
            continue
        assert_selection_partition_allowed(EvaluationPartition.DEVELOPMENT)
        observed = target.observed_counts(match)
        if observed is None:
            continue
        home, away = observed
        nll = poisson_joint_nll(
            home,
            away,
            prediction.lambda_home,
            prediction.lambda_away,
        ) / 2.0
        mae = (
            abs(home - prediction.lambda_home)
            + abs(away - prediction.lambda_away)
        ) / 2.0
        scored.append((_month_block(match.date_unix), nll, mae))

    return scored, prediction_map


def run_intensity_tournament(
    *,
    matches: Sequence[ResearchMatch],
    target: CountTargetSpec,
) -> IntensityTournamentResult:
    stream = _development_stream(matches)
    grid = predefined_intensity_grid()
    candidate_scores: dict[str, list[tuple[str, float, float]]] = {}
    configs = dict(grid)

    for candidate_id, config in grid:
        scored, _ = _score_intensity_candidate(
            stream=stream,
            target=target,
            config=config,
        )
        candidate_scores[candidate_id] = scored

    if ANCHOR_CANDIDATE_ID not in candidate_scores:
        raise AssertionError("anchor config missing from frozen grid")
    anchor = candidate_scores[ANCHOR_CANDIDATE_ID]
    anchor_nll_by_index = [row[1] for row in anchor]

    results: list[IntensityCandidateResult] = []
    for candidate_id, config in grid:
        scored = candidate_scores[candidate_id]
        if len(scored) != len(anchor):
            raise AssertionError("candidate scoring support mismatch")
        nll = mean(row[1] for row in scored)
        mae = mean(row[2] for row in scored)

        if candidate_id == ANCHOR_CANDIDATE_ID:
            interval = None
        else:
            paired = [
                (
                    scored[index][0],
                    anchor_nll_by_index[index] - scored[index][1],
                )
                for index in range(len(scored))
            ]
            interval = _paired_block_interval(paired)

        results.append(
            IntensityCandidateResult(
                candidate_id=candidate_id,
                config=asdict(config),
                config_hash=config.identity_hash,
                n_scored=len(scored),
                mean_poisson_nll=nll,
                mean_mae=mae,
                improvement_vs_anchor=interval,
            )
        )

    selected = min(
        results,
        key=lambda row: (
            row.mean_poisson_nll,
            row.candidate_id,
        ),
    )
    return IntensityTournamentResult(
        target=target.name,
        anchor_candidate_id=ANCHOR_CANDIDATE_ID,
        selected_candidate_id=selected.candidate_id,
        selected_config_hash=selected.config_hash,
        selected_config=selected.config,
        candidates=tuple(
            sorted(
                results,
                key=lambda row: (
                    row.mean_poisson_nll,
                    row.candidate_id,
                ),
            )
        ),
    )


def _poisson_goal_event_loss(
    *,
    home: int,
    away: int,
    forecast: HierarchicalCountForecast,
) -> float:
    total = home + away
    losses = []
    for line in (1.5, 2.5, 3.5):
        probability = float(
            poisson.sf(int(line // 1), forecast.lambda_total)
        )
        losses.append(binary_log_loss(probability, total > line))
    btts_probability = (
        (1.0 - np.exp(-forecast.lambda_home))
        * (1.0 - np.exp(-forecast.lambda_away))
    )
    losses.append(
        binary_log_loss(
            float(btts_probability),
            home > 0 and away > 0,
        )
    )
    return mean(losses)


def _dc_goal_event_loss(
    *,
    home: int,
    away: int,
    forecast: HierarchicalCountForecast,
    rho: float,
) -> float:
    total = home + away
    losses = [
        binary_log_loss(
            dixon_coles_total_over_probability(
                forecast.lambda_home,
                forecast.lambda_away,
                line,
                rho,
            ),
            total > line,
        )
        for line in (1.5, 2.5, 3.5)
    ]
    losses.append(
        binary_log_loss(
            dixon_coles_btts_probability(
                forecast.lambda_home,
                forecast.lambda_away,
                rho,
            ),
            home > 0 and away > 0,
        )
    )
    return mean(losses)


def _poisson_corner_event_loss(
    *,
    home: int,
    away: int,
    forecast: HierarchicalCountForecast,
) -> float:
    return _nb_corner_event_loss(
        home=home,
        away=away,
        forecast=forecast,
        alpha=0.0,
    )


def _nb_corner_event_loss(
    *,
    home: int,
    away: int,
    forecast: HierarchicalCountForecast,
    alpha: float,
) -> float:
    losses: list[float] = []
    total = home + away
    for line in (7.5, 8.5, 9.5, 10.5, 11.5):
        losses.append(
            binary_log_loss(
                nb2_total_over_probability(
                    forecast.lambda_home,
                    forecast.lambda_away,
                    line,
                    alpha,
                ),
                total > line,
            )
        )
    for line in (3.5, 4.5, 5.5, 6.5):
        losses.append(
            binary_log_loss(
                nb2_side_over_probability(
                    forecast.lambda_home,
                    line,
                    alpha,
                ),
                home > line,
            )
        )
        losses.append(
            binary_log_loss(
                nb2_side_over_probability(
                    forecast.lambda_away,
                    line,
                    alpha,
                ),
                away > line,
            )
        )
    return mean(losses)


def _config_from_dict(value: dict[str, Any]) -> DynamicCountConfig:
    return DynamicCountConfig(**value)


def run_distribution_tournament(
    *,
    matches: Sequence[ResearchMatch],
    target: CountTargetSpec,
    selected_config: DynamicCountConfig,
) -> tuple[DistributionTournamentResult, tuple[DevelopmentOOFRow, ...]]:
    stream = _development_stream(matches)
    model = DynamicHierarchicalCountBaseline(target, selected_config)

    if target.name == "goals":
        selector = OnlineGridSelector(GOALS_RHO_GRID, min_observations=100)
        family = "DIXON_COLES_LOW_SCORE"
    elif target.name == "corners":
        selector = OnlineGridSelector(CORNERS_ALPHA_GRID, min_observations=100)
        family = "NB2_OVERDISPERSION"
    else:
        raise ValueError(f"unsupported tournament target {target.name}")

    rows: list[DevelopmentOOFRow] = []
    parameter_frequency: Counter[str] = Counter()
    by_comp_joint: dict[str, list[float]] = defaultdict(list)
    by_comp_event: dict[str, list[float]] = defaultdict(list)

    batch: list[ResearchMatch] = []
    current_kickoff: int | None = None

    def process_batch(items: Sequence[ResearchMatch]) -> None:
        if not items:
            return
        selected_parameter = selector.selected
        forecasts = model.process_batch(items)

        pending_selector_updates: list[
            tuple[HierarchicalCountForecast, int, int]
        ] = []

        for match, forecast in zip(items, forecasts, strict=True):
            observed = target.observed_counts(match)
            if observed is None:
                continue
            home, away = observed
            partition = partition_for_kickoff(match.date_unix)

            if target.name == "goals":
                structured_nll = dixon_coles_joint_nll(
                    home,
                    away,
                    forecast.lambda_home,
                    forecast.lambda_away,
                    selected_parameter,
                )
                poisson_event = _poisson_goal_event_loss(
                    home=home,
                    away=away,
                    forecast=forecast,
                )
                structured_event = _dc_goal_event_loss(
                    home=home,
                    away=away,
                    forecast=forecast,
                    rho=selected_parameter,
                )
            else:
                structured_nll = nb2_side_nll(
                    home,
                    away,
                    forecast.lambda_home,
                    forecast.lambda_away,
                    selected_parameter,
                )
                poisson_event = _poisson_corner_event_loss(
                    home=home,
                    away=away,
                    forecast=forecast,
                )
                structured_event = _nb_corner_event_loss(
                    home=home,
                    away=away,
                    forecast=forecast,
                    alpha=selected_parameter,
                )

            poisson_nll = poisson_joint_nll(
                home,
                away,
                forecast.lambda_home,
                forecast.lambda_away,
            )

            if partition == EvaluationPartition.DEVELOPMENT:
                assert_selection_partition_allowed(partition)
                parameter_frequency[f"{selected_parameter:g}"] += 1
                row = DevelopmentOOFRow(
                    fixture_key=forecast.fixture_key,
                    kickoff_ts=forecast.kickoff_ts,
                    month_block=_month_block(forecast.kickoff_ts),
                    competition_ref=forecast.competition_ref,
                    season_ref=match.season_ref or "<missing>",
                    target=target.name,
                    lambda_home=forecast.lambda_home,
                    lambda_away=forecast.lambda_away,
                    observed_home=home,
                    observed_away=away,
                    effective_support=forecast.effective_support,
                    supported=forecast.supported,
                    structured_parameter=selected_parameter,
                    poisson_joint_nll=poisson_nll,
                    structured_joint_nll=structured_nll,
                    poisson_event_log_loss=poisson_event,
                    structured_event_log_loss=structured_event,
                )
                rows.append(row)
                by_comp_joint[row.competition_ref].append(
                    poisson_nll - structured_nll
                )
                by_comp_event[row.competition_ref].append(
                    poisson_event - structured_event
                )
            elif partition not in (
                EvaluationPartition.WARMUP,
                EvaluationPartition.DEVELOPMENT,
            ):
                raise AssertionError(
                    "distribution tournament accessed non-development outcome"
                )

            pending_selector_updates.append((forecast, home, away))

        # Update all parameter scores only after the same-kickoff predictions
        # were emitted. Thus no fixture at the same kickoff can affect another.
        for forecast, home, away in pending_selector_updates:
            if target.name == "goals":
                selector.update(
                    lambda rho, f=forecast, h=home, a=away: (
                        dixon_coles_joint_nll(
                            h,
                            a,
                            f.lambda_home,
                            f.lambda_away,
                            rho,
                        )
                    )
                )
            else:
                selector.update(
                    lambda alpha, f=forecast, h=home, a=away: (
                        nb2_side_nll(
                            h,
                            a,
                            f.lambda_home,
                            f.lambda_away,
                            alpha,
                        )
                    )
                )

    for match in stream:
        if current_kickoff is None:
            current_kickoff = match.date_unix
        if match.date_unix != current_kickoff:
            process_batch(batch)
            batch = []
            current_kickoff = match.date_unix
        batch.append(match)
    process_batch(batch)

    if not rows:
        raise ValueError("distribution tournament produced no development rows")

    joint_paired = [
        (
            row.month_block,
            row.poisson_joint_nll - row.structured_joint_nll,
        )
        for row in rows
    ]
    event_paired = [
        (
            row.month_block,
            row.poisson_event_log_loss - row.structured_event_log_loss,
        )
        for row in rows
    ]

    report = DistributionTournamentResult(
        target=target.name,
        structured_family=family,
        parameter_grid=selector.grid,
        selected_parameter_frequency=dict(parameter_frequency),
        n_scored=len(rows),
        poisson_joint_nll=mean(row.poisson_joint_nll for row in rows),
        structured_joint_nll=mean(
            row.structured_joint_nll for row in rows
        ),
        joint_nll_improvement=_paired_block_interval(joint_paired),
        poisson_event_log_loss=mean(
            row.poisson_event_log_loss for row in rows
        ),
        structured_event_log_loss=mean(
            row.structured_event_log_loss for row in rows
        ),
        event_log_loss_improvement=_paired_block_interval(event_paired),
        by_competition_joint_nll_delta={
            competition: mean(values)
            for competition, values in sorted(by_comp_joint.items())
        },
        by_competition_event_log_loss_delta={
            competition: mean(values)
            for competition, values in sorted(by_comp_event.items())
        },
        oof_rows_hash=rows_digest([row.to_dict() for row in rows]),
    )
    return report, tuple(rows)


def run_layer3_development_tournament(
    *,
    matches: Sequence[ResearchMatch],
    corpus_manifest_hash: str,
    chronology: ChronologyManifest,
) -> tuple[
    Layer3DevelopmentTournament,
    dict[str, tuple[DevelopmentOOFRow, ...]],
]:
    if chronology.corpus_manifest_hash != corpus_manifest_hash:
        raise ValueError("chronology/corpus manifest mismatch")

    intensity_results: list[IntensityTournamentResult] = []
    distribution_results: list[DistributionTournamentResult] = []
    oof: dict[str, tuple[DevelopmentOOFRow, ...]] = {}

    for target in (GOALS_TARGET, CORNERS_TARGET):
        intensity = run_intensity_tournament(
            matches=matches,
            target=target,
        )
        intensity_results.append(intensity)
        selected_config = _config_from_dict(intensity.selected_config)
        distribution, rows = run_distribution_tournament(
            matches=matches,
            target=target,
            selected_config=selected_config,
        )
        distribution_results.append(distribution)
        oof[target.name] = rows

    # These counters are constants by construction: selection code only receives
    # the warmup+development stream. They are explicit in the artifact so a
    # future implementation cannot quietly broaden the selection window.
    result = Layer3DevelopmentTournament(
        version=TOURNAMENT_VERSION,
        chronology_manifest_hash=chronology.manifest_hash,
        corpus_manifest_hash=corpus_manifest_hash,
        calibration_rows_scored=0,
        protected_rows_scored=0,
        intensity_results=tuple(intensity_results),
        distribution_results=tuple(distribution_results),
    )
    return result, oof


def write_oof_rows(
    *,
    path: Path,
    rows: Sequence[DevelopmentOOFRow],
) -> None:
    payload = "".join(
        canonical_json(row.to_dict()) + "\n"
        for row in rows
    )
    if path.exists():
        if path.read_text() != payload:
            raise FileExistsError(
                f"OOF artifact exists with different content: {path}"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)


def write_tournament_report(
    *,
    path: Path,
    tournament: Layer3DevelopmentTournament,
) -> None:
    payload = canonical_json(tournament.to_dict()) + "\n"
    if path.exists():
        if path.read_text() != payload:
            raise FileExistsError(
                f"tournament report exists with different content: {path}"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)
