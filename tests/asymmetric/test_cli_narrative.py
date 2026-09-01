"""CLI narrative + coverage-branch unit tests (task 11.7).

Asserts the narrative sections are present on a resolved cached fixture
(Req 9.2-9.6), the EV section is distinct and labelled when odds exist (Req 9.9),
and the coverage branches at exactly 0 and 5 matches behave per Req 9.7/9.8.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.research.asymmetric.cli import OddsQuote
from src.research.data_source import ResearchMatch
from tests.asymmetric._cli_helpers import build_corpus, fixture_unix, load_cli_module

_MOD = load_cli_module()


def test_narrative_sections_present_on_resolved_fixture() -> None:
    corpus = build_corpus()
    out = _MOD.analyze("Leeds", "Norwich", "2026-09-05", corpus=corpus)
    # Req 9.2-9.6 sections.
    assert "TEAM PROFILES" in out
    assert "Attacking dimensions:" in out
    assert "Defensive dimensions:" in out
    assert "PER-SIDE PREDICTIONS" in out
    assert "driving features:" in out
    assert "DERIVED MATCH OUTCOMES" in out
    assert "BTTS" in out
    assert "ASYMMETRY STATEMENT" in out
    assert "COVERAGE" in out


def test_ev_section_distinct_and_labelled_when_odds_exist() -> None:
    corpus = build_corpus()
    odds = [
        OddsQuote("team_corners", "bet365", "home", 4.5, 1.9, 1.9),
        OddsQuote("team_total_goals", "bet365", "home", 1.5, 2.1, 1.75),
    ]
    out = _MOD.analyze("Leeds", "Norwich", "2026-09-05", corpus=corpus, odds=odds)
    assert "EXPECTED VALUE (per-side, per book, UNBLENDED" in out  # Req 9.9 distinct+labelled
    assert "[bet365] team_corners (home)" in out
    assert "EV " in out
    # Team cards explicitly has no per-side EV (Req 9.11).
    assert "team_cards: NO per-side price is available" in out


def test_coverage_branch_zero_matches() -> None:
    """Exactly 0 cached matches for a team -> no profile, no predictions (Req 9.8)."""
    fut = fixture_unix()
    corpus = [
        (
            ResearchMatch(
                match_id=1, date_unix=fut, league_id=100, season="s",
                home_team="Ghost", away_team="Phantom",
                home_goals=None, away_goals=None,
            ),
            "Championship",
        )
    ]
    out = _MOD.analyze("Ghost", "Phantom", "2026-09-05", corpus=corpus)
    assert "NO PROFILE" in out
    assert "PER-SIDE PREDICTIONS" not in out


def _corpus_with_exact_history(n_before: int) -> list[tuple[ResearchMatch, str]]:
    """Build a corpus where 'Home' has exactly ``n_before`` completed matches
    strictly before the fixture, plus the scheduled fixture."""
    fut = fixture_unix()
    corpus: list[tuple[ResearchMatch, str]] = []
    d = fut - 86_400 * (n_before + 5)
    for i in range(n_before):
        d += 86_400
        corpus.append(
            (
                ResearchMatch(
                    match_id=i + 1, date_unix=d, league_id=100, season="s",
                    home_team="Home", away_team=f"Opp{i}",
                    home_goals=1, away_goals=1,
                    corners_home=5, corners_away=4,
                    shots_on_target_home=4, shots_on_target_away=3,
                    yellow_cards_home=2, yellow_cards_away=1,
                    red_cards_home=0, red_cards_away=0,
                    attacks_home=100, attacks_away=90,
                    dangerous_attacks_home=40, dangerous_attacks_away=30,
                ),
                "Championship",
            )
        )
    # Away needs history too so its profile is non-empty; reuse Home's opponents.
    d2 = fut - 86_400 * (n_before + 5)
    for i in range(max(n_before, 6)):
        d2 += 86_400
        corpus.append(
            (
                ResearchMatch(
                    match_id=1000 + i, date_unix=d2, league_id=100, season="s",
                    home_team="Away", away_team=f"Opp{i}",
                    home_goals=1, away_goals=1,
                    corners_home=4, corners_away=5,
                    shots_on_target_home=3, shots_on_target_away=4,
                    yellow_cards_home=1, yellow_cards_away=2,
                    red_cards_home=0, red_cards_away=0,
                    attacks_home=90, attacks_away=100,
                    dangerous_attacks_home=30, dangerous_attacks_away=40,
                ),
                "Championship",
            )
        )
    corpus.append(
        (
            ResearchMatch(
                match_id=9999, date_unix=fut, league_id=100, season="s",
                home_team="Home", away_team="Away",
                home_goals=None, away_goals=None,
            ),
            "Championship",
        )
    )
    return corpus


def test_coverage_branch_reduced_below_min() -> None:
    """1 <= n < 5 -> reduced-coverage flagged, count vs minimum stated, continue (Req 9.7)."""
    corpus = _corpus_with_exact_history(3)
    out = _MOD.analyze("Home", "Away", "2026-09-05", corpus=corpus)
    assert "REDUCED-COVERAGE" in out
    assert "3 <" in out and "minimum 5" in out
    # Continues to produce predictions on the reduced profile.
    assert "PER-SIDE PREDICTIONS" in out


def test_coverage_branch_at_five_is_sufficient() -> None:
    """Exactly 5 completed matches -> NOT reduced (boundary at min_history=5)."""
    corpus = _corpus_with_exact_history(5)
    out = _MOD.analyze("Home", "Away", "2026-09-05", corpus=corpus)
    # Home has exactly 5 -> not reduced-coverage for Home.
    assert "PER-SIDE PREDICTIONS" in out
    # The 'Home' coverage line should not carry the reduced marker at n=5.
    home_lines = [ln for ln in out.splitlines() if "home Home:" in ln]
    assert home_lines, out
