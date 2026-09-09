"""xG/shots ablation walk-forward for the champion goals family (Experiment A).

xG and total shots are ALREADY champion features for the GOALS and
SHOTS_ON_TARGET families (Phase 0 audit). The defensible, leakage-safe test is
therefore a FEATURE ABLATION on the champion's own goals model: does removing
xG (and/or shots) from the goals family change out-of-sample goals-total
forecasting? Every arm uses the SAME fixtures, chronology, model, hyperparameters
and walk-forward window; only the feature SET varies. Paired predictions per
(fixture, line) let arms be compared paired on identical keys.

This isolates the *value of the xG/shots signal* the champion already ingests.
Provider-of-xG (FootyStats vs TheStatsAPI) is a separate question already
answered non-credible by PR #4 on the single-total arm; here we work on the
champion goals family, whose corpus is FootyStats, and vary the feature presence,
not the provider.

We build a family variant with a reduced ``produce``/``concede`` feature set by
copying the champion goals MarketFamily and dropping the ablated stats. The
marginal engine and everything else is the champion's, unchanged.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Optional, Sequence

from src.research.models.hierarchical_market_model import (
    HierarchicalConfig,
    HierarchicalCountModel,
)
from src.research.models.market_family import family_by_name
from src.research.models.side_rows import build_fixture_rows, training_rows

GOALS_LINES = (1.5, 2.5, 3.5)  # standard goals O/U ladder present on the goals family


def _ablated_goals_family(drop: tuple[str, ...]):
    """Return a goals MarketFamily variant with ``drop`` stats removed.

    Preserves everything about the champion goals family except the named
    produce/concede stats and any league_varying slope referencing them.
    """
    base = family_by_name("goals")
    feats = base.features
    new_produce = tuple(s for s in feats.produce if s not in drop)
    new_concede = tuple(s for s in feats.concede if s not in drop)
    dropped_varying = {f"own_produce_{s}" for s in drop} | {f"opp_concede_{s}" for s in drop}
    new_varying = tuple(v for v in feats.league_varying if v not in dropped_varying)
    new_features = replace(
        feats, produce=new_produce, concede=new_concede, league_varying=new_varying
    )
    return replace(base, features=new_features)


# Ablation arms. A0 is the champion goals family as-is.
ABLATIONS = {
    "A0_champion_goals": (),
    "A1_drop_xg": ("xg",),
    "A2_drop_shots": ("shots",),
    "A3_drop_xg_and_shots": ("xg", "shots"),
}


@dataclass(frozen=True)
class GoalsPred:
    fixture_key: str
    kickoff_unix: int
    league: str
    season: str
    week_block: str
    line: float
    prob_over: float
    outcome_over: bool

    @property
    def pair_key(self) -> tuple:
        return (self.fixture_key, self.line)


def _lines_for(family) -> tuple[float, ...]:
    # Use the family's declared lines intersected with the standard goals ladder
    # actually present; fall back to the family lines.
    declared = tuple(family.lines)
    return declared or GOALS_LINES


def run_goals_ablation(
    fixtures_by_family: dict,
    matches,
    drop: tuple[str, ...],
    *,
    min_train: int = 1200,
    refit_every: int = 150,
    min_league: int = 60,
) -> list[GoalsPred]:
    """Walk-forward goals predictions for one ablation arm.

    ``fixtures_by_family`` must contain the fixtures for the ablated family name
    (built with the ablated family so features match). We rebuild side rows per
    arm so the feature set is exactly the arm's.
    """
    family = _ablated_goals_family(drop)
    # Rebuild fixtures with THIS family so its feature rows carry only its features.
    built = build_fixture_rows(matches, [family])
    fixtures = built[family.name]
    lines = _lines_for(family)

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
    preds: list[GoalsPred] = []

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
                total = float(f.total_count)
                for line in lines:
                    preds.append(GoalsPred(
                        fixture_key=f.fixture_id, kickoff_unix=int(f.kickoff_unix),
                        league=f.league, season=f.season, week_block=f.league_week_block,
                        line=line, prob_over=float(dist.p_over(line)),
                        outcome_over=bool(total > line),
                    ))
        training.extend(batch)
        for f in batch:
            league_counts[f.league] += 1
        since_refit += 1
    return preds
