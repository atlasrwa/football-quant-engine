"""Walk-forward evaluation of the corners dependence correction (Phases B7-B10).

Reuses the champion corners model UNCHANGED for the side marginals. At each
walk-forward step it produces, for every eligible fixture and every corner line,
TWO paired probabilities keyed identically:
- baseline: the champion independence convolution (dist.p_over(line)).
- dependence: the same two side PMFs coupled by a Gaussian copula at a
  walk-forward-estimated rho, then p_over(line) off the resulting total PMF.

rho ESTIMATION IS STRICTLY PRIOR-ONLY (Phase B7): at each refit, rho is the
residual home/away corner correlation computed ONLY from fixtures already folded
into the training history (out-of-sample side means from the current model on
prior fixtures). Insufficient support -> rho = 0 (safe fallback = the champion).
No full-sample correlation is ever used for a historical prediction.

Only fixtures with a model trained strictly on earlier data are scored, and each
(fixture, line) prediction is emitted for both arms so they can be compared
paired on identical keys.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from src.research.experiments.calibration_efficiency.dependence import build_joint
from src.research.models.hierarchical_market_model import (
    HierarchicalConfig,
    HierarchicalCountModel,
)
from src.research.models.market_family import family_by_name
from src.research.models.side_rows import training_rows

CORNER_LINES = (7.5, 8.5, 9.5, 10.5)
_MAX_SIDE = 30


@dataclass(frozen=True)
class Pred:
    fixture_key: str
    kickoff_unix: int
    league: str
    season: str
    week_block: str
    line: float
    p_baseline: float
    p_dependence: float
    outcome_over: bool

    @property
    def pair_key(self) -> tuple:
        return (self.fixture_key, self.line)


@dataclass
class RhoState:
    """Rolling residual-correlation estimator over PRIOR fixtures only."""
    min_support: int = 300
    rho_cap: float = 0.6
    # accumulate residual pairs from prior scored fixtures
    _home_res: list = field(default_factory=list)
    _away_res: list = field(default_factory=list)

    def observe(self, home_obs, away_obs, home_mu, away_mu) -> None:
        self._home_res.append((home_obs - home_mu) / np.sqrt(max(1e-9, home_mu)))
        self._away_res.append((away_obs - away_mu) / np.sqrt(max(1e-9, away_mu)))

    def current_rho(self) -> float:
        n = len(self._home_res)
        if n < self.min_support:
            return 0.0  # safe fallback = champion independence
        hr = np.asarray(self._home_res, dtype=float)
        ar = np.asarray(self._away_res, dtype=float)
        if hr.std() == 0 or ar.std() == 0:
            return 0.0
        rho = float(np.corrcoef(hr, ar)[0, 1])
        if not np.isfinite(rho):
            return 0.0
        return float(max(-self.rho_cap, min(self.rho_cap, rho)))


@dataclass
class DependenceEvalResult:
    predictions: list[Pred] = field(default_factory=list)
    rho_trace: list[tuple[int, float, int]] = field(default_factory=list)  # (kickoff, rho, support)


def run_dependence_walk_forward(
    fixtures,
    *,
    min_train: int = 1200,
    refit_every: int = 150,
    min_league: int = 60,
    rho_min_support: int = 300,
    rho_cap: float = 0.6,
    global_rho: bool = True,
) -> DependenceEvalResult:
    """Walk-forward producing paired baseline/dependence corner predictions.

    global_rho=True estimates ONE rho over all prior fixtures (Phase B4 simplest
    hierarchy). Per-league rho is a later refinement, only if global is supported.
    """
    family = family_by_name("corners")
    ordered = sorted(fixtures, key=lambda f: (f.kickoff_unix, f.fixture_id))
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
    rho_state = RhoState(min_support=rho_min_support, rho_cap=rho_cap)
    result = DependenceEvalResult()

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
            rho = rho_state.current_rho()  # prior-only
            result.rho_trace.append((int(batch[0].kickoff_unix), rho, len(rho_state._home_res)))
            for f in batch:
                if league_counts[f.league] < min_league or f.total_count is None:
                    continue
                if f.gate_reason is not None:
                    continue
                try:
                    dist = model.predict_match(f.home_row, f.away_row)
                except Exception:
                    continue
                home_pmf = np.asarray(dist.home.pmf(_MAX_SIDE), dtype=float)
                away_pmf = np.asarray(dist.away.pmf(_MAX_SIDE), dtype=float)
                joint = build_joint(home_pmf, away_pmf, rho)
                total = float(f.total_count)
                for line in CORNER_LINES:
                    result.predictions.append(Pred(
                        fixture_key=f.fixture_id,
                        kickoff_unix=int(f.kickoff_unix),
                        league=f.league,
                        season=f.season,
                        week_block=f.league_week_block,
                        line=line,
                        p_baseline=float(dist.p_over(line)),
                        p_dependence=float(joint.p_over(line)),
                        outcome_over=bool(total > line),
                    ))
                # fold this fixture's realized residual into the prior-only rho
                # estimator AFTER it has been scored (so it never informs its own rho).
                rho_state.observe(
                    float(f.home_count), float(f.away_count),
                    float(dist.home.mean), float(dist.away.mean),
                )

        training.extend(batch)
        for f in batch:
            league_counts[f.league] += 1
        since_refit += 1
    return result
