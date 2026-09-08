"""Tests for the shrinking current-season form window.

The central assertion is negative: the window must never contain a prior-season
match. That was the bug that invalidated every forecast published before the corpus
fix, so it is tested directly rather than inferred from the absence of complaints.
"""

from __future__ import annotations

import pytest

from src.research.models.market_family import default_market_families, required_stats
from src.research.models.side_rows import (
    assert_no_same_match_leakage,
    build_fixture_rows,
)
from src.research.prediction_engine.form_window import (
    DEFAULT_WINDOW,
    MIN_CURRENT_SEASON_MATCHES,
    STATUS_FULL,
    STATUS_SHRUNK,
    STATUS_UNAVAILABLE,
    FormWindowBuilder,
    gate_reason,
    window_provenance,
    window_sufficient,
)

LEAGUE = "Test League"
PRIOR_SEASON = "9001"
CURRENT_SEASON = "9002"


def _match(
    *,
    season: str,
    kickoff: int,
    home: str,
    away: str,
    home_corners: float,
    away_corners: float,
) -> dict:
    return {
        "id": f"{season}-{kickoff}-{home}-{away}",
        "status": "complete",
        "_league": LEAGUE,
        "_season": season,
        "competition_id": season,
        "date_unix": kickoff,
        "homeID": home,
        "awayID": away,
        "home_name": f"Team {home}",
        "away_name": f"Team {away}",
        "team_a_corners": home_corners,
        "team_b_corners": away_corners,
        "team_a_dangerous_attacks": 40.0,
        "team_b_dangerous_attacks": 35.0,
        "team_a_shotsOffTarget": 5.0,
        "team_b_shotsOffTarget": 4.0,
        "homeGoalCount": 1,
        "awayGoalCount": 1,
        "team_a_shotsOnTarget": 5,
        "team_b_shotsOnTarget": 4,
        "team_a_shots": 12,
        "team_b_shots": 10,
        "team_a_xg": 1.2,
        "team_b_xg": 1.0,
        "team_a_fouls": 11,
        "team_b_fouls": 12,
        "team_a_yellow_cards": 2,
        "team_b_yellow_cards": 1,
        "team_a_red_cards": 0,
        "team_b_red_cards": 0,
        "ht_goals_team_a": 1,
        "ht_goals_team_b": 0,
        "team_a_fh_corners": 3,
        "team_b_fh_corners": 2,
        "team_a_fh_cards": 1,
        "team_b_fh_cards": 0,
        "game_week": kickoff // 100,
    }


def _builder(stats=("corners",)) -> FormWindowBuilder:
    return FormWindowBuilder(stats, window=DEFAULT_WINDOW)


def test_window_shrinks_rather_than_backfilling_from_the_prior_season() -> None:
    """Three current-season matches give a three-match window, not five."""
    builder = _builder()
    # Ten prior-season matches with a deliberately extreme corner count.
    for index in range(10):
        builder.observe(
            _match(
                season=PRIOR_SEASON,
                kickoff=1000 + index,
                home="A",
                away="B",
                home_corners=20.0,
                away_corners=20.0,
            )
        )
    # Three current-season matches with a very different count.
    for index in range(3):
        builder.observe(
            _match(
                season=CURRENT_SEASON,
                kickoff=5000 + index,
                home="A",
                away="B",
                home_corners=2.0,
                away_corners=2.0,
            )
        )
    state = builder.window_state(LEAGUE, "A", 9000)
    assert state.used == 3, "the window must shrink to the matches that exist"
    assert state.requested == DEFAULT_WINDOW
    assert state.deficit == 2
    assert state.status == STATUS_SHRUNK
    assert state.current_season_matches == 3
    assert state.season == CURRENT_SEASON

    form = builder.team_form(LEAGUE, "A", 9000)
    # If the prior season had leaked in, the mean would be pulled toward 20.
    assert form.produced["corners"] == pytest.approx(2.0, abs=1e-9)


def test_a_full_window_reports_full_status() -> None:
    builder = _builder()
    for index in range(7):
        builder.observe(
            _match(
                season=CURRENT_SEASON,
                kickoff=5000 + index,
                home="A",
                away="B",
                home_corners=6.0,
                away_corners=4.0,
            )
        )
    state = builder.window_state(LEAGUE, "A", 9000)
    assert state.status == STATUS_FULL
    assert state.used == DEFAULT_WINDOW
    assert state.deficit == 0
    assert state.current_season_matches == 7


def test_window_uses_only_the_most_recent_five_of_a_long_season() -> None:
    builder = _builder()
    for index in range(10):
        builder.observe(
            _match(
                season=CURRENT_SEASON,
                kickoff=5000 + index,
                home="A",
                away="B",
                home_corners=0.0 if index < 5 else 10.0,
                away_corners=5.0,
            )
        )
    form = builder.team_form(LEAGUE, "A", 9000)
    # The last five are all 10.0; the first five must not enter.
    assert form.produced["corners"] == pytest.approx(10.0, abs=1e-9)


def test_a_team_with_no_current_season_match_has_no_window() -> None:
    builder = _builder()
    for index in range(10):
        builder.observe(
            _match(
                season=PRIOR_SEASON,
                kickoff=1000 + index,
                home="A",
                away="B",
                home_corners=9.0,
                away_corners=9.0,
            )
        )
    # 'C' has never played.
    state = builder.window_state(LEAGUE, "C", 9000)
    assert state.status == STATUS_UNAVAILABLE
    assert state.used == 0
    assert not state.available


def test_one_current_season_match_forms_a_window_but_fails_the_history_gate() -> None:
    """Available and sufficient are different questions, and both are asked."""
    builder = _builder()
    builder.observe(
        _match(
            season=CURRENT_SEASON,
            kickoff=5000,
            home="A",
            away="B",
            home_corners=7.0,
            away_corners=3.0,
        )
    )
    state = builder.window_state(LEAGUE, "A", 9000)
    assert state.available is True
    assert state.used == 1
    assert window_sufficient(state) is False


def test_the_gate_keys_on_window_availability_and_the_minimum_count() -> None:
    """A team clearing 'min 3' with a live window passes; either failure blocks."""
    builder = _builder()
    for index in range(MIN_CURRENT_SEASON_MATCHES):
        builder.observe(
            _match(
                season=CURRENT_SEASON,
                kickoff=5000 + index,
                home="A",
                away="B",
                home_corners=6.0,
                away_corners=4.0,
            )
        )
    home = builder.team_form(LEAGUE, "A", 9000)
    away = builder.team_form(LEAGUE, "B", 9000)
    assert gate_reason(home, away) is None
    assert window_sufficient(home.window) is True

    unseen = builder.team_form(LEAGUE, "Z", 9000)
    reason = gate_reason(home, unseen)
    assert reason is not None
    assert "never backfilled from the prior season" in reason


def test_window_provenance_records_the_actual_match_count_used() -> None:
    builder = _builder()
    for index in range(4):
        builder.observe(
            _match(
                season=CURRENT_SEASON,
                kickoff=5000 + index,
                home="A",
                away="B",
                home_corners=6.0,
                away_corners=4.0,
            )
        )
    builder.observe(
        _match(
            season=CURRENT_SEASON,
            kickoff=5100,
            home="A",
            away="C",
            home_corners=6.0,
            away_corners=4.0,
        )
    )
    provenance = window_provenance(
        builder.team_form(LEAGUE, "A", 9000), builder.team_form(LEAGUE, "B", 9000)
    )
    assert provenance["home"]["used"] == 5
    assert provenance["away"]["used"] == 4
    assert provenance["home"]["deficit"] == 0
    assert provenance["away"]["deficit"] == 1
    assert provenance["away"]["status"] == STATUS_SHRUNK
    assert provenance["sufficient"] is True
    assert provenance["gate_keys_on"] == (
        "window_availability_and_min_current_season_matches"
    )
    assert "shrinks" in provenance["window_policy"]
    assert "backfilling" in provenance["window_policy"]


def test_season_boundary_resets_the_window_completely() -> None:
    """The first match of a new season yields a one-match window."""
    builder = _builder()
    for index in range(10):
        builder.observe(
            _match(
                season=PRIOR_SEASON,
                kickoff=1000 + index,
                home="A",
                away="B",
                home_corners=8.0,
                away_corners=8.0,
            )
        )
    builder.observe(
        _match(
            season=CURRENT_SEASON,
            kickoff=5000,
            home="A",
            away="B",
            home_corners=1.0,
            away_corners=1.0,
        )
    )
    state = builder.window_state(LEAGUE, "A", 9000)
    assert state.used == 1
    assert state.current_season_matches == 1
    assert state.season == CURRENT_SEASON
    form = builder.team_form(LEAGUE, "A", 9000)
    assert form.produced["corners"] == pytest.approx(1.0, abs=1e-9)


def test_recency_weighting_favours_the_most_recent_match() -> None:
    builder = _builder()
    for index, corners in enumerate([0.0, 0.0, 0.0, 0.0, 10.0]):
        builder.observe(
            _match(
                season=CURRENT_SEASON,
                kickoff=5000 + index,
                home="A",
                away="B",
                home_corners=corners,
                away_corners=5.0,
            )
        )
    form = builder.team_form(LEAGUE, "A", 9000)
    unweighted = 10.0 / 5.0
    assert form.produced["corners"] > unweighted


def test_unknown_stat_is_refused_rather_than_zero_filled() -> None:
    with pytest.raises(ValueError, match="no provider mapping"):
        FormWindowBuilder(("not_a_real_stat",))


# ─────────────────────────────────────────────────────────────────────────────
# Row building and leakage
# ─────────────────────────────────────────────────────────────────────────────
def _season_fixtures(n_matches: int = 40) -> list[dict]:
    matches: list[dict] = []
    teams = [f"T{index}" for index in range(8)]
    kickoff = 5000
    for round_index in range(n_matches):
        home = teams[round_index % len(teams)]
        away = teams[(round_index + 3) % len(teams)]
        if home == away:
            continue
        kickoff += 100
        matches.append(
            _match(
                season=CURRENT_SEASON,
                kickoff=kickoff,
                home=home,
                away=away,
                home_corners=5.0 + (round_index % 4),
                away_corners=4.0 + (round_index % 3),
            )
        )
    return matches


def test_built_rows_contain_nothing_from_the_fixture_they_describe() -> None:
    families = default_market_families()
    matches = _season_fixtures()
    built = build_fixture_rows(matches, families)
    for family in families:
        assert_no_same_match_leakage(matches, built[family.name], [family])


def test_simultaneous_fixtures_cannot_inform_each_other() -> None:
    """Two fixtures at the same kickoff must see identical prior history."""
    families = [default_market_families()[1]]  # corners
    matches = _season_fixtures()
    # Force two fixtures onto exactly the same kickoff.
    matches.append(
        _match(
            season=CURRENT_SEASON,
            kickoff=99000,
            home="T0",
            away="T1",
            home_corners=11.0,
            away_corners=1.0,
        )
    )
    matches.append(
        _match(
            season=CURRENT_SEASON,
            kickoff=99000,
            home="T2",
            away="T3",
            home_corners=1.0,
            away_corners=11.0,
        )
    )
    built = build_fixture_rows(matches, families)
    assert_no_same_match_leakage(matches, built[families[0].name], families)


def test_every_fixture_yields_two_side_rows_with_opposed_orientation() -> None:
    families = [default_market_families()[0]]
    built = build_fixture_rows(_season_fixtures(), families)
    fixtures = built[families[0].name]
    assert fixtures
    for fixture in fixtures:
        assert fixture.home_row.is_home is True
        assert fixture.away_row.is_home is False
        assert fixture.home_row.counting_team == fixture.away_row.opposing_team
        assert fixture.away_row.counting_team == fixture.home_row.opposing_team
        if fixture.total_count is not None:
            assert fixture.total_count == pytest.approx(
                (fixture.home_count or 0) + (fixture.away_count or 0)
            )


def test_required_stats_covers_every_family_feature() -> None:
    families = default_market_families()
    stats = set(required_stats(families))
    for family in families:
        assert set(family.features.produce) <= stats
        assert set(family.features.concede) <= stats



# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap block identity
# ─────────────────────────────────────────────────────────────────────────────
def test_a_zero_provider_week_falls_back_to_the_iso_week() -> None:
    """``game_week = 0`` is a "not set" sentinel for several leagues, not week 0.

    MLS carries ``game_week = 0`` on 78% of its fixtures. Accepting it collapsed
    the whole league into two bootstrap blocks, which destroys the bootstrap: a
    resample over two clusters estimates nothing, and every MLS cell was reported
    insufficient for a reason that was really a provider quirk.
    """
    families = [default_market_families()[1]]
    matches = []
    for index in range(60):
        match = _match(
            season=CURRENT_SEASON,
            kickoff=1_600_000_000 + index * 86_400 * 3,
            home=f"T{index % 8}",
            away=f"T{(index + 4) % 8}",
            home_corners=5.0,
            away_corners=4.0,
        )
        match["game_week"] = 0  # the provider's unset value
        match["roundID"] = None
        matches.append(match)
    built = build_fixture_rows(matches, families)
    blocks = {fixture.league_week_block for fixture in built[families[0].name]}
    assert len(blocks) > 2, "a zero week must not collapse the league into one block"
    assert all("iso-week" in block for block in blocks)
    assert not any("provider-week:0" in block for block in blocks)


def test_a_real_provider_week_is_used_when_present() -> None:
    families = [default_market_families()[1]]
    matches = []
    for index in range(20):
        match = _match(
            season=CURRENT_SEASON,
            kickoff=1_600_000_000 + index * 3600,
            home=f"T{index % 8}",
            away=f"T{(index + 4) % 8}",
            home_corners=5.0,
            away_corners=4.0,
        )
        match["game_week"] = 1 + index // 4
        matches.append(match)
    built = build_fixture_rows(matches, families)
    blocks = {fixture.league_week_block for fixture in built[families[0].name]}
    assert all("provider-week:" in block for block in blocks)
    assert len(blocks) == 5


def test_blocks_are_namespaced_by_league_and_season() -> None:
    """Two leagues in the same calendar week must never share a block."""
    families = [default_market_families()[1]]
    matches = []
    for index in range(12):
        for league_suffix in ("A", "B"):
            match = _match(
                season=CURRENT_SEASON,
                kickoff=1_600_000_000 + index * 86_400 * 3,
                home=f"T{index % 4}",
                away=f"T{(index + 2) % 4}",
                home_corners=5.0,
                away_corners=4.0,
            )
            match["_league"] = f"League {league_suffix}"
            match["id"] = f"{league_suffix}-{index}"
            match["game_week"] = 0
            match["roundID"] = None
            matches.append(match)
    built = build_fixture_rows(matches, families)
    blocks = {fixture.league_week_block for fixture in built[families[0].name]}
    assert any(block.startswith("League A:") for block in blocks)
    assert any(block.startswith("League B:") for block in blocks)
    for block in blocks:
        assert CURRENT_SEASON in block
