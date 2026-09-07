"""Tests for the market family registry, coverage audit and dispersion audit.

The coverage audit is what stops a first-half market being published for a league
where the provider does not populate the half-split fields. Zero-filling those would
turn "not recorded" into "no corners in the first half", so the audit excludes
instead.
"""

from __future__ import annotations

import pytest

from src.research.models.market_family import (
    ALL_FAMILY_NAMES,
    DERIVED_BTTS,
    FAMILY_CARDS,
    FAMILY_CORNERS,
    FAMILY_FIRST_HALF_CARDS,
    FAMILY_FIRST_HALF_CORNERS,
    FAMILY_FIRST_HALF_GOALS,
    FAMILY_GOALS,
    FAMILY_SHOTS_ON_TARGET,
    POOLED_LEAGUE_LABEL,
    SHOTS_ON_TARGET_LINES,
    FeatureBlock,
    MarketFamily,
    audit_dispersion,
    audit_family_coverage,
    buildable_leagues,
    default_market_families,
    family_by_name,
    numeric,
    required_stats,
    side_counts,
)

from tests.research.test_form_window import _match

CURRENT_SEASON = "9002"


# ─────────────────────────────────────────────────────────────────────────────
# The declared line set
# ─────────────────────────────────────────────────────────────────────────────
def test_every_required_market_family_is_declared() -> None:
    names = {family.name for family in default_market_families()}
    assert names == set(ALL_FAMILY_NAMES)
    assert names == {
        FAMILY_GOALS,
        FAMILY_CORNERS,
        FAMILY_CARDS,
        FAMILY_SHOTS_ON_TARGET,
        FAMILY_FIRST_HALF_GOALS,
        FAMILY_FIRST_HALF_CORNERS,
        FAMILY_FIRST_HALF_CARDS,
    }


@pytest.mark.parametrize(
    ("family_name", "expected"),
    [
        (FAMILY_GOALS, (2.5, 3.5)),
        (FAMILY_CORNERS, (7.5, 8.5, 9.5, 10.5)),
        (FAMILY_CARDS, (2.5, 3.5, 4.5)),
        (FAMILY_SHOTS_ON_TARGET, SHOTS_ON_TARGET_LINES),
        (FAMILY_FIRST_HALF_GOALS, (0.5, 1.5)),
    ],
)
def test_declared_lines_match_the_specification(family_name, expected) -> None:
    assert family_by_name(family_name).lines == expected


def test_shots_on_target_lines_state_why_they_were_chosen() -> None:
    family = family_by_name(FAMILY_SHOTS_ON_TARGET)
    rationale = family.line_rationale
    assert "median 9" in rationale
    assert "IQR" in rationale
    assert "rejected" in rationale


def test_lines_are_sorted_and_unique() -> None:
    for family in default_market_families():
        assert tuple(sorted(family.lines)) == family.lines
        assert len(set(family.lines)) == len(family.lines)


def test_btts_is_derived_and_is_not_a_family() -> None:
    assert DERIVED_BTTS not in ALL_FAMILY_NAMES
    assert sum(1 for f in default_market_families() if f.derives_btts) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Feature blocks stay compact
# ─────────────────────────────────────────────────────────────────────────────
def test_feature_blocks_are_compact() -> None:
    """No broad search. The 866-feature run added variance, not signal."""
    for family in default_market_families():
        assert len(family.feature_names) <= 10, (
            f"{family.name} declares {len(family.feature_names)} features; "
            "feature blocks must stay compact"
        )


def test_league_varying_slope_sets_are_tiny() -> None:
    for family in default_market_families():
        assert len(family.features.league_varying) <= 2
        assert set(family.features.league_varying) <= set(family.feature_names)


def test_unavailable_mechanisms_are_named_not_forgotten() -> None:
    """Mechanisms absent from this corpus are recorded, so proxies are visible."""
    corners = family_by_name(FAMILY_CORNERS)
    assert "final_third_entries" in corners.features.unavailable_mechanisms
    assert "accurate_crosses" in corners.features.unavailable_mechanisms
    goals = family_by_name(FAMILY_GOALS)
    assert "np_expected_goals" in goals.features.unavailable_mechanisms


def test_first_half_families_use_the_native_half_split_stat() -> None:
    assert "first_half_goals" in family_by_name(FAMILY_FIRST_HALF_GOALS).features.produce
    assert (
        "first_half_corners"
        in family_by_name(FAMILY_FIRST_HALF_CORNERS).features.produce
    )
    assert "first_half_cards" in family_by_name(FAMILY_FIRST_HALF_CARDS).features.produce


def test_a_block_naming_an_unmapped_stat_fails_closed() -> None:
    with pytest.raises(ValueError, match="no provider mapping"):
        FeatureBlock(produce=("teleportation",), concede=())


def test_a_block_cannot_vary_a_slope_it_does_not_declare() -> None:
    with pytest.raises(ValueError, match="league_varying names features"):
        FeatureBlock(produce=("corners",), concede=(), league_varying=("own_produce_xg",))


def test_family_requires_declared_side_fields() -> None:
    with pytest.raises(ValueError, match="no side target fields"):
        MarketFamily(
            name="not_a_family",
            lines=(1.5,),
            features=FeatureBlock(produce=("corners",), concede=()),
            line_rationale="x",
        )


def test_unsorted_lines_are_refused() -> None:
    with pytest.raises(ValueError, match="sorted ascending"):
        MarketFamily(
            name=FAMILY_CORNERS,
            lines=(9.5, 7.5),
            features=FeatureBlock(produce=("corners",), concede=()),
            line_rationale="x",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Reading raw values
# ─────────────────────────────────────────────────────────────────────────────
def test_the_missing_sentinel_is_not_confused_with_zero() -> None:
    """``-1`` means not recorded; ``0`` means genuinely none. Never collapsed."""
    assert numeric(-1) is None
    assert numeric("-1") is None
    assert numeric(0) == 0.0
    assert numeric(None) is None
    assert numeric("nonsense") is None
    assert numeric(True) is None


def test_side_counts_returns_none_when_a_half_split_field_is_absent() -> None:
    match = _match(
        season=CURRENT_SEASON,
        kickoff=1,
        home="A",
        away="B",
        home_corners=6.0,
        away_corners=4.0,
    )
    match["team_a_fh_corners"] = -1
    assert side_counts(match, FAMILY_FIRST_HALF_CORNERS) is None
    # The full-match family is unaffected.
    assert side_counts(match, FAMILY_CORNERS) == (6.0, 4.0)


def test_cards_fall_back_to_yellows_plus_reds() -> None:
    match = _match(
        season=CURRENT_SEASON, kickoff=1, home="A", away="B", home_corners=1, away_corners=1
    )
    match.pop("team_a_cards_num", None)
    match["team_a_yellow_cards"] = 3
    match["team_a_red_cards"] = 1
    match["team_b_yellow_cards"] = 2
    match["team_b_red_cards"] = 0
    assert side_counts(match, FAMILY_CARDS) == (4.0, 2.0)


def test_required_stats_is_deduplicated_and_ordered() -> None:
    stats = required_stats(default_market_families())
    assert len(stats) == len(set(stats))


# ─────────────────────────────────────────────────────────────────────────────
# Coverage audit
# ─────────────────────────────────────────────────────────────────────────────
def _corpus(n: int = 200, *, break_first_half: bool = False) -> list[dict]:
    matches = []
    for index in range(n):
        match = _match(
            season=CURRENT_SEASON,
            kickoff=1000 + index,
            home=f"T{index % 8}",
            away=f"T{(index + 4) % 8}",
            home_corners=5.0,
            away_corners=4.0,
        )
        if break_first_half and index % 2 == 0:
            match["team_a_fh_corners"] = -1
            match["team_b_fh_corners"] = -1
        matches.append(match)
    return matches


def test_full_coverage_marks_every_family_buildable() -> None:
    coverage = audit_family_coverage(_corpus())
    assert coverage
    for report in coverage:
        assert report.buildable is True
        assert report.coverage == pytest.approx(1.0)


def test_a_league_missing_half_split_fields_is_excluded_not_zero_filled() -> None:
    coverage = audit_family_coverage(_corpus(break_first_half=True))
    first_half_corners = [
        report for report in coverage if report.family == FAMILY_FIRST_HALF_CORNERS
    ]
    assert first_half_corners
    for report in first_half_corners:
        assert report.buildable is False
        assert "zero-filled" in report.reason
    # Other families are untouched.
    corners = [report for report in coverage if report.family == FAMILY_CORNERS]
    assert all(report.buildable for report in corners)


def test_a_league_with_too_few_fixtures_is_excluded() -> None:
    coverage = audit_family_coverage(_corpus(n=30))
    assert coverage
    for report in coverage:
        assert report.buildable is False
        assert "minimum" in report.reason


def test_buildable_leagues_filters_by_family() -> None:
    coverage = audit_family_coverage(_corpus(break_first_half=True))
    assert buildable_leagues(coverage, FAMILY_CORNERS)
    assert buildable_leagues(coverage, FAMILY_FIRST_HALF_CORNERS) == ()


def test_coverage_report_serialises() -> None:
    report = audit_family_coverage(_corpus())[0].to_dict()
    for key in ("league", "family", "n_fixtures", "n_buildable", "coverage", "buildable", "reason"):
        assert key in report


# ─────────────────────────────────────────────────────────────────────────────
# Dispersion audit
# ─────────────────────────────────────────────────────────────────────────────
def test_dispersion_audit_reports_per_league_and_pooled() -> None:
    reports = audit_dispersion(_corpus(), min_observations=10)
    assert reports
    leagues = {report.league for report in reports}
    assert POOLED_LEAGUE_LABEL in leagues
    assert len(leagues) >= 2
    for report in reports:
        assert report.n_observations >= 10
        assert report.variance_mean_ratio >= 0.0
        assert isinstance(report.overdispersed, bool)


def test_dispersion_audit_flags_a_genuinely_overdispersed_family() -> None:
    matches = []
    for index in range(300):
        # Alternating extremes give variance far above the mean.
        corners = 1.0 if index % 2 == 0 else 19.0
        matches.append(
            _match(
                season=CURRENT_SEASON,
                kickoff=1000 + index,
                home=f"T{index % 8}",
                away=f"T{(index + 4) % 8}",
                home_corners=corners,
                away_corners=corners,
            )
        )
    reports = audit_dispersion(matches, min_observations=10)
    corners = [
        report
        for report in reports
        if report.family == FAMILY_CORNERS and report.league == POOLED_LEAGUE_LABEL
    ]
    assert corners and corners[0].overdispersed is True
    assert corners[0].variance_mean_ratio > 1.2


def test_dispersion_report_serialises() -> None:
    report = audit_dispersion(_corpus(), min_observations=10)[0].to_dict()
    for key in ("league", "family", "n_observations", "mean", "variance", "variance_mean_ratio", "overdispersed"):
        assert key in report
