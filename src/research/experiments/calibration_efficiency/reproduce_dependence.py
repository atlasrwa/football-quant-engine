"""Reproduce the residual home/away corner dependence finding (Phase B1).

Independently re-derives the residual correlation between the two sides' corner
counts AFTER removing the champion's fitted per-side means, using a strictly
chronological walk-forward (never a full-sample fit). Reports raw and residual
correlation overall and stratified by league and season, with block-bootstrap
confidence intervals over match-week clusters (the same clustering the champion
harness uses), so the −0.209 figure can be confirmed or refuted and its
stability characterised.

Method (mirrors scripts/audit_calibration.py Candidate C, but walk-forward and
stratified):
- raw corr: corrcoef(home_obs, away_obs) — includes shared fixture effects.
- residual corr: Pearson residuals r = (obs - mu)/sqrt(mu) per side using the
  champion's OUT-OF-SAMPLE fitted means, then corrcoef(home_res, away_res).
Only fixtures predicted by a model trained strictly on earlier fixtures enter.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from src.research.models.hierarchical_market_model import (
    HierarchicalConfig,
    HierarchicalCountModel,
)
from src.research.models.market_family import family_by_name
from src.research.models.side_rows import build_fixture_rows, training_rows


@dataclass
class SideObservation:
    """One fixture's out-of-sample side means + observed counts (for residuals)."""
    league: str
    season: str
    kickoff_unix: int
    week_block: str
    home_obs: float
    away_obs: float
    home_mu: float
    away_mu: float

    @property
    def home_res(self) -> float:
        return (self.home_obs - self.home_mu) / np.sqrt(max(1e-9, self.home_mu))

    @property
    def away_res(self) -> float:
        return (self.away_obs - self.away_mu) / np.sqrt(max(1e-9, self.away_mu))


def capture_side_observations(
    fixtures,
    *,
    min_train: int = 1200,
    refit_every: int = 100,
    min_league: int = 60,
) -> list[SideObservation]:
    """Walk-forward: record OOS per-side means + observed counts for corners.

    Mirrors the champion walk-forward: batches by kickoff, refits the champion
    corners model on strictly-earlier labelled rows, predicts each fixture, and
    records the fitted home/away means alongside the realized counts.
    """
    family = family_by_name("corners")
    ordered = sorted(fixtures, key=lambda f: (f.kickoff_unix, f.fixture_id))
    # batch by shared kickoff
    batches: list[list] = []
    cursor = 0
    while cursor < len(ordered):
        k = ordered[cursor].kickoff_unix
        end = cursor + 1
        while end < len(ordered) and ordered[end].kickoff_unix == k:
            end += 1
        batches.append(ordered[cursor:end])
        cursor = end

    training: list = []
    league_counts: dict[str, int] = defaultdict(int)
    model: Optional[HierarchicalCountModel] = None
    since_refit = 0
    out: list[SideObservation] = []

    for batch in batches:
        labelled = training_rows(training)
        if len(labelled) >= min_train and (model is None or since_refit >= refit_every):
            candidate = HierarchicalCountModel(family, HierarchicalConfig())
            try:
                candidate.fit(labelled)
                model = candidate
                since_refit = 0
            except (ValueError, RuntimeError):
                pass
        if model is not None:
            for f in batch:
                if league_counts[f.league] < min_league or f.total_count is None:
                    continue
                if f.gate_reason is not None:
                    continue
                try:
                    dist = model.predict_match(f.home_row, f.away_row)
                except Exception:
                    continue
                out.append(SideObservation(
                    league=f.league, season=f.season, kickoff_unix=f.kickoff_unix,
                    week_block=f.league_week_block,
                    home_obs=float(f.home_count), away_obs=float(f.away_count),
                    home_mu=float(dist.home.mean), away_mu=float(dist.away.mean),
                ))
        training.extend(batch)
        for f in batch:
            league_counts[f.league] += 1
        since_refit += 1
    return out


def _corr(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3:
        return None
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _block_bootstrap_corr(
    obs: Sequence[SideObservation], residual: bool, *, n_boot: int = 1000, seed: int = 20260909
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Block-bootstrap CI for the (residual) correlation, resampling week blocks."""
    if len(obs) < 5:
        return (None, None, None)
    by_block: dict[str, list[SideObservation]] = defaultdict(list)
    for o in obs:
        by_block[o.week_block].append(o)
    blocks = list(by_block.values())
    rng = np.random.default_rng(seed)

    def corr_of(sample_obs):
        if residual:
            xs = [o.home_res for o in sample_obs]
            ys = [o.away_res for o in sample_obs]
        else:
            xs = [o.home_obs for o in sample_obs]
            ys = [o.away_obs for o in sample_obs]
        return _corr(xs, ys)

    point = corr_of(obs)
    boots = []
    n_blocks = len(blocks)
    for _ in range(n_boot):
        picked = rng.integers(0, n_blocks, size=n_blocks)
        sample = [o for idx in picked for o in blocks[idx]]
        c = corr_of(sample)
        if c is not None:
            boots.append(c)
    if not boots:
        return (point, None, None)
    lo = float(np.quantile(boots, 0.025))
    hi = float(np.quantile(boots, 0.975))
    return (point, lo, hi)


@dataclass
class DependenceReproduction:
    overall: dict = field(default_factory=dict)
    by_league: dict = field(default_factory=dict)
    by_season: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"overall": self.overall, "by_league": self.by_league, "by_season": self.by_season}


def _summary(obs: list[SideObservation], *, n_boot: int, seed: int) -> dict:
    raw = _corr([o.home_obs for o in obs], [o.away_obs for o in obs])
    res_point, res_lo, res_hi = _block_bootstrap_corr(obs, residual=True, n_boot=n_boot, seed=seed)
    # variance ratio: observed total var vs convolution-implied (sum of side vars)
    total_obs = np.array([o.home_obs + o.away_obs for o in obs], dtype=float)
    exp_total = np.array([o.home_mu + o.away_mu for o in obs], dtype=float)
    observed_var = float(np.mean((total_obs - exp_total) ** 2)) if obs else None
    # Reference variance if the two sides were independent Poissons with the
    # fitted means (Var = mean). This is a LOWER BOUND on the champion's actual
    # convolution-implied variance (which uses NB2 + uncertainty widening, so is
    # larger); the observed/this-ratio therefore UNDERSTATES how much the champion
    # already over-widens the total. Labelled explicitly to avoid confusion.
    poisson_ref_var = float(np.mean([o.home_mu + o.away_mu for o in obs])) if obs else None
    return {
        "n_fixtures": len(obs),
        "raw_corr": None if raw is None else round(raw, 4),
        "residual_corr": None if res_point is None else round(res_point, 4),
        "residual_corr_ci95": [None if res_lo is None else round(res_lo, 4),
                               None if res_hi is None else round(res_hi, 4)],
        "observed_total_variance": None if observed_var is None else round(observed_var, 4),
        "poisson_reference_variance_lower_bound": None if poisson_ref_var is None else round(poisson_ref_var, 4),
        "variance_ratio_obs_over_poisson_ref": (
            round(observed_var / poisson_ref_var, 4) if observed_var and poisson_ref_var else None
        ),
    }


def reproduce(
    fixtures,
    *,
    min_train: int = 1200,
    refit_every: int = 100,
    min_league: int = 60,
    n_boot: int = 1000,
    seed: int = 20260909,
    min_cell: int = 100,
) -> DependenceReproduction:
    """Full B1 reproduction: overall + per-league + per-season residual dependence."""
    obs = capture_side_observations(
        fixtures, min_train=min_train, refit_every=refit_every, min_league=min_league
    )
    rep = DependenceReproduction()
    rep.overall = _summary(obs, n_boot=n_boot, seed=seed)

    by_league: dict[str, list[SideObservation]] = defaultdict(list)
    by_season: dict[str, list[SideObservation]] = defaultdict(list)
    for o in obs:
        by_league[o.league].append(o)
        by_season[o.season].append(o)
    rep.by_league = {
        lg: _summary(v, n_boot=n_boot, seed=seed)
        for lg, v in sorted(by_league.items()) if len(v) >= min_cell
    }
    rep.by_season = {
        sn: _summary(v, n_boot=n_boot, seed=seed)
        for sn, v in sorted(by_season.items()) if len(v) >= min_cell
    }
    return rep
