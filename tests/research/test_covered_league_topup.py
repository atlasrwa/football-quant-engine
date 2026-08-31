"""Tests for the covered-league top-up bias."""

from src.research.forward.covered_league_topup import (
    team_coverage,
    covered_competitions,
    build_topup_plan,
    project_settleable_sample,
)


def _meta():
    # comp A: has a both-covered fixture -> covered. comp B: no coverage -> new league.
    return {
        "m1": {"comp": "A", "home": "TeamX", "away": "TeamY", "ts": 2000, "status": "scheduled"},
        "m2": {"comp": "A", "home": "TeamX", "away": "Stranger", "ts": 2500, "status": "scheduled"},
        "m3": {"comp": "A", "home": "TeamX", "away": "TeamY", "ts": 500, "status": "finished"},
        "m4": {"comp": "B", "home": "New1", "away": "New2", "ts": 3000, "status": "scheduled"},
        "m5": {"comp": "A", "home": "Stranger", "away": "Nobody", "ts": 4000, "status": "scheduled"},
    }


CORPUS = {"TeamX", "TeamY"}
NOW = 1000


def test_team_coverage():
    assert team_coverage({"home": "TeamX", "away": "TeamY"}, CORPUS) == 2
    assert team_coverage({"home": "TeamX", "away": "Z"}, CORPUS) == 1
    assert team_coverage({"home": "A", "away": "B"}, CORPUS) == 0


def test_covered_competitions_excludes_uncovered():
    covered = covered_competitions(_meta(), CORPUS)
    assert "A" in covered
    assert "B" not in covered  # no both-covered fixture in B


def test_plan_prioritises_upcoming_both_covered_and_excludes_new_leagues():
    plan = build_topup_plan(_meta(), list(_meta().keys()), CORPUS, now_ts=NOW)
    # m1 is upcoming both-covered -> tier0, first
    assert plan.ordered_match_ids[0] == "m1"
    # m4 (comp B, new league) excluded entirely
    assert "m4" not in plan.ordered_match_ids
    assert plan.n_excluded_new_league >= 1
    # m3 is finished both-covered -> included (settle backlog) but after upcoming
    assert "m3" in plan.ordered_match_ids
    assert plan.ordered_match_ids.index("m1") < plan.ordered_match_ids.index("m3")
    # m2 upcoming one-covered -> tier1 (between tier0 and tier2)
    assert "m2" in plan.ordered_match_ids
    assert plan.ordered_match_ids.index("m2") < plan.ordered_match_ids.index("m3")
    # m5 in covered comp but 0 coverage & upcoming -> excluded as past/uncovered bucket
    assert "m5" not in plan.ordered_match_ids


def test_plan_can_drop_partial_cover():
    plan = build_topup_plan(_meta(), list(_meta().keys()), CORPUS, now_ts=NOW,
                            include_partial_cover=False)
    assert "m2" not in plan.ordered_match_ids


def test_projection_weeks_to_power():
    plan = build_topup_plan(_meta(), list(_meta().keys()), CORPUS, now_ts=NOW)
    # tier0 has 1 fixture (m1)
    proj = project_settleable_sample(plan, markets_per_fixture=4,
                                     weekly_covered_upcoming=10, target_n=385)
    assert proj["projected_weekly_settleable_predictions"] == 40
    assert proj["projected_weekly_settleable_per_market_line"] == 10
    assert proj["estimated_weeks_to_power_per_market_line"] == 38.5


def test_projection_handles_zero_rate():
    plan = build_topup_plan({}, [], CORPUS, now_ts=NOW)
    proj = project_settleable_sample(plan, markets_per_fixture=4,
                                     weekly_covered_upcoming=0)
    assert proj["estimated_weeks_to_power_per_market_line"] is None
