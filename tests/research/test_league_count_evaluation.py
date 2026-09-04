from __future__ import annotations

import json
import math

import pytest

from src.research.evaluation.league_count import (
    DEFAULT_CONTRASTS,
    LeagueCountEvaluationConfig,
    LeagueCountEvaluator,
    GOALS_FEATURES,
    VERDICT_ARTIFACT,
    build_broad_count_rows,
    default_count_markets,
)
from src.research.models.hierarchical_count import (
    HIERARCHICAL_ARM,
    POOLED_ARM,
    CountMarketSpec,
    LeagueCountModel,
)


def _spec() -> CountMarketSpec:
    return CountMarketSpec(
        name="goals",
        target_field="total_goals",
        lines=(1.5,),
        feature_fields=(),
        use_team_effects=False,
    )


def test_empirical_bayes_arm_is_partial_pool_and_supports_arbitrary_lines() -> None:
    spec = _spec()
    rows = []
    for league, count in (("low", 1.0), ("high", 9.0)):
        for index in range(16):
            rows.append({"_league": league, "total_goals": count, "date_unix": index})

    model = LeagueCountModel(spec)
    model.fit(rows)
    effect = model.league_effects["high"]
    assert 0.0 < effect.shrinkage_weight < 1.0
    assert 0.0 < effect.posterior_log_offset < effect.raw_log_offset

    row = {"_league": "high"}
    pooled = model.predict_distribution(row, arm=POOLED_ARM)
    hierarchical = model.predict_distribution(row, arm=HIERARCHICAL_ARM)
    assert pooled.mean < hierarchical.mean < pooled.mean * math.exp(effect.raw_log_offset)
    assert hierarchical.p_over(1.5) > hierarchical.p_over(4.5)
    assert sum(hierarchical.pmf(20)) == pytest.approx(1.0)


def test_broad_adapter_updates_only_after_complete_equal_kickoff_batch() -> None:
    spec = CountMarketSpec(
        name="corners",
        target_field="total_corners",
        lines=(9.5,),
        feature_fields=("shots_home", "shots_away"),
        use_team_effects=False,
    )
    fixtures = [
        _fixture(1, 100, 1, 2, 10, 4),
        _fixture(2, 100, 3, 4, 20, 8),
        _fixture(3, 200, 1, 3, 30, 12),
    ]
    rows = build_broad_count_rows(fixtures, (spec,), min_prior=1)["corners"]
    assert rows[0]["shots_home"] == 0.0
    assert rows[1]["shots_home"] == 0.0
    # Fixture 3 sees fixtures 1 and 2 only after their whole kickoff batch closes.
    assert rows[2]["shots_home"] == 10.0
    assert rows[2]["shots_away"] == 20.0


def test_evaluator_emits_complete_aligned_family_and_monotone_bh_q_values() -> None:
    spec = _spec()
    rows = []
    for week in range(36):
        kickoff = 1_700_000_000 + week * 604_800
        for league_index, league in enumerate(("A", "B")):
            count = float((week + league_index) % 5)
            rows.append(
                {
                    "_fixture_id": f"{league}-{week}",
                    "_league": league,
                    "_season": "s1",
                    "date_unix": kickoff,
                    "_date_block": f"d{week}",
                    "_league_week_block": f"{league}:w{week}",
                    "home_team_id": league_index * 100 + 1,
                    "away_team_id": league_index * 100 + 2,
                    "total_goals": count,
                }
            )
    config = LeagueCountEvaluationConfig(
        min_global_train=8,
        min_league_train=3,
        refit_every_kickoff_batches=4,
        min_cell_predictions=8,
        min_bootstrap_blocks=3,
        bootstrap_draws=40,
        seed=7,
    )
    report = LeagueCountEvaluator(config).evaluate(
        {"goals": rows}, (spec,), preregistered_leagues=("A", "B", "MISSING")
    )

    assert len(report.cells) == 3 * len(DEFAULT_CONTRASTS)
    assert report.governance["preregistered_cell_count"] == len(report.cells)
    assert report.governance["valid_family_size"] == 2 * len(DEFAULT_CONTRASTS)
    serialized = json.dumps(report.to_dict())
    assert "league-count-evaluation/v1" in serialized
    for cell in report.cells:
        if cell["league"] == "MISSING":
            assert cell["status"] == "insufficient"
            assert cell["insufficient_reasons"] == ["no_walk_forward_predictions"]
            assert cell["fdr"]["raw_p"] is None
            assert cell["fdr"]["family_size"] == 2 * len(DEFAULT_CONTRASTS)
            continue
        assert cell["status"] == "tested"
        assert cell["identical_fixture_ids_across_arms"] is True
        assert set(cell["effects"]) == {"brier", "log_loss", "ece"}
        assert cell["fdr"]["raw_p"] is not None
        assert cell["fdr"]["threshold"] is not None
        assert cell["fdr"]["rank"] is not None
        assert cell["fdr"]["q_value"] is not None

    ranked = sorted(
        (cell for cell in report.cells if cell["status"] == "tested"),
        key=lambda cell: cell["fdr"]["rank"],
    )
    q_values = [cell["fdr"]["q_value"] for cell in ranked]
    assert q_values == sorted(q_values)


def test_pooled_only_positive_is_classified_as_artifact() -> None:
    evaluator = LeagueCountEvaluator(
        LeagueCountEvaluationConfig(bootstrap_draws=5)
    )
    cell = {
        "status": "tested",
        "effects": {"brier": {"point": 0.01, "ci95": [-0.01, 0.03]}},
        "fdr": {"reject": False},
    }
    pooled = {
        "status": "tested",
        "effects": {
            "brier": {"point": 0.02, "ci95": [0.01, 0.03], "p_one_sided": 0.01}
        },
    }
    assert evaluator._classify(cell, pooled) == VERDICT_ARTIFACT
    assert (
        evaluator._classify(cell, pooled, any_league_finding=True)
        != VERDICT_ARTIFACT
    )


def test_default_goal_market_uses_theory_appropriate_strictly_prior_features() -> None:
    goal_market = next(market for market in default_count_markets() if market.name == "goals")
    assert goal_market.feature_fields == GOALS_FEATURES
    assert "attacks_home" not in goal_market.feature_fields
    assert "possession_home" not in goal_market.feature_fields
    assert {
        "shots_home",
        "shots_on_target_home",
        "xg_home",
        "dangerous_attacks_home",
    }.issubset(goal_market.feature_fields)

    first = _fixture(1, 100, 1, 2, 10, 7)
    first.update(
        {
            "team_a_shotsOnTarget": 4,
            "team_b_shotsOnTarget": 2,
            "team_a_xg": 1.25,
            "team_b_xg": 0.75,
            "team_a_dangerous_attacks": 30,
            "team_b_dangerous_attacks": 20,
            "totalGoalCount": 2,
        }
    )
    second = _fixture(2, 200, 1, 3, 99, 88)
    second.update(
        {
            "team_a_shotsOnTarget": 40,
            "team_b_shotsOnTarget": 30,
            "team_a_xg": 9.0,
            "team_b_xg": 8.0,
            "team_a_dangerous_attacks": 90,
            "team_b_dangerous_attacks": 80,
            "totalGoalCount": 3,
        }
    )
    rows = build_broad_count_rows((first, second), (goal_market,), min_prior=1)["goals"]
    assert rows[1]["shots_home"] == 10.0
    assert rows[1]["shots_on_target_home"] == 4.0
    assert rows[1]["xg_home"] == 1.25
    assert rows[1]["dangerous_attacks_home"] == 30.0


def test_broad_adapter_rejects_features_without_declared_provenance() -> None:
    unsupported = CountMarketSpec(
        name="custom",
        target_field="total_goals",
        lines=(2.5,),
        feature_fields=("custom_prior",),
        use_team_effects=False,
    )
    with pytest.raises(ValueError, match="provenance is not defined.*custom_prior"):
        build_broad_count_rows([], (unsupported,))


def _fixture(
    fixture_id: int,
    kickoff: int,
    home_id: int,
    away_id: int,
    home_shots: int,
    away_shots: int,
) -> dict[str, object]:
    return {
        "id": fixture_id,
        "status": "complete",
        "date_unix": kickoff,
        "_league": "L",
        "_season": "S",
        "homeID": home_id,
        "awayID": away_id,
        "team_a_shots": home_shots,
        "team_b_shots": away_shots,
        "totalCornerCount": 10,
    }
