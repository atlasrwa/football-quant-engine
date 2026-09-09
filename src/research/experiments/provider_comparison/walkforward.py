"""Chronological walk-forward forecasting per provider policy (Phases 7-9).

Runs the UNCHANGED champion (build_prior_only_features + LeagueCountModel) over
the paired fixtures, producing one probability per fixture per O/U line, for the
markets the champion supports as count processes: CORNERS_TOTAL and CARDS_TOTAL.
Goals-based markets (goals totals, BTTS) are provider-invariant here because the
providers agree on goals (Phase 3 corr=1.0); they are reported as such rather
than re-run per provider.

Strict PIT walk-forward:
- Features for fixture i come only from fixtures strictly before i (guaranteed by
  build_prior_only_features' batch-by-timestamp rolling means).
- The model is fit on rows strictly before an expanding-window cutoff and used to
  predict the next block; train window always precedes the predicted fixtures.
- The SAME fixture set, chronology, cutoffs, window, and model hyperparameters are
  used for every provider arm; only the provider-sourced feature values differ.

Every prediction is keyed by (fs_match_id, market, line) so arms can be compared
paired on identical keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.research.experiments.provider_comparison.bridge import build_provider_matches
from src.research.experiments.provider_comparison.dataset import PairedFixture
from src.research.models.hierarchical_count import (
    HIERARCHICAL_ARM,
    POOLED_ARM,
    CountMarketSpec,
    LeagueCountModel,
)
from src.research.models.prior_only_features import build_prior_only_features

# Champion overlapping feature set (provider-sourced). These are the rolling
# feature names build_prior_only_features emits for the overlapping stats.
_OVERLAP_FEATURES = (
    "shots_home", "shots_away",
    "possession_home", "possession_away",
    "fouls_home", "fouls_away",
)

# FootyStats-only extra features (no TheStatsAPI equivalent). Included ONLY in
# the additional-feature ablation, never in the provider-quality head-to-head.
_FS_ONLY_FEATURES = (
    "dangerous_attacks_home", "dangerous_attacks_away",
    "attacks_home", "attacks_away",
)


def _feature_fields(include_fs_only_features: bool) -> tuple[str, ...]:
    """Model feature set. Overlap-only for provider-quality; +FS-only for the
    additional-feature ablation so the ablation actually changes the model."""
    if include_fs_only_features:
        return _OVERLAP_FEATURES + _FS_ONLY_FEATURES
    return _OVERLAP_FEATURES

# Markets evaluated as count processes (champion-supported). Lines chosen at the
# common O/U ladder points for each market.
MARKET_SPECS = {
    "CORNERS_TOTAL": dict(target_field="total_corners", lines=(9.5, 10.5, 11.5)),
    "CARDS_TOTAL": dict(target_field="total_cards", lines=(3.5, 4.5)),
}


@dataclass(frozen=True)
class Prediction:
    """One forecast for one fixture/market/line, with the realized outcome."""
    fixture_key: int          # fs_match_id (identical across arms)
    kickoff_unix: int
    market: str
    line: float
    prob_over: float
    outcome_over: bool        # realized: total > line
    league: str
    season: str

    @property
    def pair_key(self) -> tuple:
        return (self.fixture_key, self.market, self.line)


@dataclass
class WalkForwardResult:
    policy: str
    arm: str
    include_fs_only_features: bool
    predictions: list[Prediction] = field(default_factory=list)


def _league_of(fx: PairedFixture) -> str:
    return f"{fx.league}:{fx.season_fs}"


def run_walk_forward(
    fixtures: list[PairedFixture],
    *,
    policy: str,
    market: str,
    arm: str = POOLED_ARM,
    window: int = 10,
    min_prior: int = 3,
    min_train: int = 80,
    refit_every: int = 40,
    include_fs_only_features: bool = False,
) -> WalkForwardResult:
    """Expanding-window walk-forward for one provider policy and market.

    Args:
        fixtures: paired fixtures (chronological).
        policy: provider policy name (bridge._POLICY_MAP keys).
        market: 'CORNERS_TOTAL' | 'CARDS_TOTAL'.
        arm: model arm (pooled/hierarchical/independent).
        window/min_prior: champion feature hyperparameters (held constant).
        min_train: minimum prior rows before the first prediction.
        refit_every: refit cadence (rows) to bound compute; train always precedes test.
        include_fs_only_features: additional-feature ablation toggle.

    Returns:
        WalkForwardResult with one Prediction per predictable fixture.
    """
    spec_cfg = MARKET_SPECS[market]
    ordered = sorted(fixtures, key=lambda f: f.kickoff_unix)

    # Build champion match dicts under the policy, then champion feature rows.
    matches = build_provider_matches(
        ordered, policy, include_fs_only_features=include_fs_only_features
    )
    feats = build_prior_only_features(
        matches, target_field=spec_cfg["target_field"], window=window, min_prior=min_prior
    )
    # Attach league + realized outcome; align to fixtures by index (same order).
    # build_prior_only_features preserves order and count of input matches.
    assert len(feats) == len(ordered), "feature/fixture alignment broken"

    rows = []
    for fx, ft in zip(ordered, feats):
        r = dict(ft)
        r["_league"] = _league_of(fx)
        r["_fixture_key"] = fx.fs_match_id
        r["_kickoff"] = fx.kickoff_unix
        r["_season"] = fx.season_fs
        rows.append(r)

    spec = CountMarketSpec(
        name=market,
        target_field=spec_cfg["target_field"],
        lines=tuple(spec_cfg["lines"]),
        feature_fields=_feature_fields(include_fs_only_features),
    )

    result = WalkForwardResult(policy=policy, arm=arm,
                               include_fs_only_features=include_fs_only_features)

    # Only rows with a realized target are usable for train/eval.
    def has_target(r) -> bool:
        v = r.get(spec_cfg["target_field"])
        return v is not None

    usable = [r for r in rows if has_target(r)]
    n = len(usable)
    if n <= min_train:
        return result  # not enough data to walk forward

    model: Optional[LeagueCountModel] = None
    last_fit_at = -1
    for i in range(min_train, n):
        train = usable[:i]  # strictly before the i-th fixture (chronological)
        # (Re)fit periodically; train window always precedes the test row.
        if model is None or (i - last_fit_at) >= refit_every:
            try:
                m = LeagueCountModel(spec)
                m.fit(train)
                model = m
                last_fit_at = i
            except (ValueError, KeyError):
                # insufficient/degenerate training -> skip until next cadence
                continue
        row = usable[i]
        try:
            dist = model.predict_distribution(row, arm=arm)
        except (KeyError, RuntimeError):
            # e.g. a season/league unseen in training under this arm -> skip
            continue
        target_val = float(row[spec_cfg["target_field"]])
        for line in spec_cfg["lines"]:
            result.predictions.append(Prediction(
                fixture_key=int(row["_fixture_key"]),
                kickoff_unix=int(row["_kickoff"]),
                market=market,
                line=line,
                prob_over=float(dist.p_over(line)),
                outcome_over=bool(target_val > line),
                league=str(row["_league"]),
                season=str(row["_season"]),
            ))
    return result
