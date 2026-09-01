"""Unit tests for the cached corpus loaders (task 2.2).

These tests assert the behaviours required by task 2.2:

* both loaders read from **cache** (no network), returning ``ResearchMatch``
  records paired with a per-match league identity;
* absent fields surface as ``None`` while genuine zeros are preserved
  (NULL != ZERO), and the FootyStats ``-1`` "unplayed" sentinel is surfaced as
  not-populated (``None``);
* every match exposes its league identity (both a machine ``league_id`` on the
  :class:`ResearchMatch` and a readable ``league`` label on the
  :class:`LoadedMatch`).

Fixtures are tiny synthesized cache directories under ``tmp_path`` so the tests
are fast and do not depend on the (large) real cache. A single smoke test
against the real Rich cache is included but skips gracefully if it is absent.

Requirements: 4.1, 4.2.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.research.asymmetric.corpus import (
    BroadCorpusLoader,
    CacheOnlyFootyStatsSource,
    LoadedMatch,
    RichCorpusLoader,
    RICH_CACHE_DIR,
    _adapted_to_research_match,
)
from src.research.data_source import ResearchMatch


# --------------------------------------------------------------------------- #
# Broad corpus: tiny synthesized cache
# --------------------------------------------------------------------------- #
def _write_broad_cache(tmp_path: Path) -> str:
    """Write a minimal FootyStats league-matches cache file and return its dir.

    Two records:
      * a *complete* match with a genuine 0 (corners_home=0) and a populated
        positive value (corners_away=5) — exercises NULL != ZERO;
      * an *incomplete* match with -1 sentinels — must be excluded, and if it
        were admitted its -1 must surface as None (never -1).
    """
    data = [
        {
            "id": 1001,
            "date_unix": 1_700_000_000,
            "status": "complete",
            "home_name": "Alpha",
            "away_name": "Beta",
            "competition_id": 42,
            "season": "2025/2026",
            "homeGoalCount": 1,
            "awayGoalCount": 0,
            "team_a_corners": 0,     # genuine zero -> must stay 0
            "team_b_corners": 5,     # populated -> 5
            "team_a_yellow_cards": 2,
            "team_b_yellow_cards": 1,
            "team_a_shotsOnTarget": 4,
            "team_b_shotsOnTarget": 3,
            "refereeID": None,       # null pre/post -> referee None
        },
        {
            "id": 1002,
            "date_unix": 1_700_100_000,
            "status": "incomplete",  # unplayed -> excluded entirely
            "home_name": "Gamma",
            "away_name": "Delta",
            "competition_id": 42,
            "season": "2025/2026",
            "homeGoalCount": 0,
            "awayGoalCount": 0,
            "team_a_corners": -1,    # sentinel -> not populated
            "team_b_corners": -1,
        },
    ]
    payload = {"success": True, "data": data, "pager": {"current_page": 1, "max_page": 1}}
    cache_dir = tmp_path / "footystats"
    cache_dir.mkdir()
    with open(cache_dir / "league-matches_season_id_42.json", "w") as fh:
        json.dump(payload, fh)
    return str(cache_dir)


def test_broad_loader_reads_from_cache_and_excludes_unplayed(tmp_path: Path) -> None:
    cache_dir = _write_broad_cache(tmp_path)
    loader = BroadCorpusLoader(cache_dir=cache_dir)
    loaded = loader.load()

    # Only the completed match is admitted; the incomplete (-1 sentinel) is not.
    assert len(loaded) == 1
    lm = loaded[0]
    assert isinstance(lm, LoadedMatch)
    assert isinstance(lm.match, ResearchMatch)
    assert lm.match.home_team == "Alpha"


def test_broad_loader_preserves_null_not_zero(tmp_path: Path) -> None:
    cache_dir = _write_broad_cache(tmp_path)
    match = BroadCorpusLoader(cache_dir=cache_dir).load()[0].match

    # Genuine zero stays 0; populated value stays; nothing becomes -1.
    assert match.corners_home == 0
    assert match.corners_away == 5
    assert match.corners_home is not None
    # A field never present in the raw record stays None (not fabricated).
    assert match.possession_home is None
    # refereeID null -> None (not the string "None" or a sentinel).
    assert match.referee is None


def test_broad_loader_exposes_league_identity(tmp_path: Path) -> None:
    cache_dir = _write_broad_cache(tmp_path)
    lm = BroadCorpusLoader(cache_dir=cache_dir).load()[0]
    assert lm.match.league_id == 42          # machine id preserved
    assert lm.league == "league_42"          # readable per-match label


def test_broad_loader_uses_injected_source(tmp_path: Path) -> None:
    """An injected source that yields records is used verbatim (cache-only)."""

    class InMemorySource:
        def iter_raw_records(self):
            yield {
                "id": 7,
                "date_unix": 1,
                "status": "complete",
                "home_name": "H",
                "away_name": "A",
                "competition_id": 9,
                "season": "s",
                "homeGoalCount": 2,
                "awayGoalCount": 2,
            }

    loaded = BroadCorpusLoader(source=InMemorySource()).load()
    assert len(loaded) == 1
    assert loaded[0].match.total_goals == 4
    assert loaded[0].league == "league_9"


# --------------------------------------------------------------------------- #
# Rich corpus: mapping unit tests (no large cache needed)
# --------------------------------------------------------------------------- #
def test_rich_mapping_preserves_null_not_zero() -> None:
    """The adapter->ResearchMatch mapping keeps None as None and 0 as 0."""
    adapted = {
        "match_id": "mt_000000123",
        "home_name": "Alpha",
        "away_name": "Beta",
        "date_unix": 1_700_000_000,
        "team_a_yellow_cards": 0,      # genuine zero
        "team_b_yellow_cards": None,   # absent -> None
        "team_a_red_cards": 0,
        "team_b_red_cards": 0,
        "team_a_shotsOnTarget": None,  # absent -> None
        "team_b_shotsOnTarget": 5,
        "team_a_fouls": 11,
        "team_b_fouls": None,
        "team_a_xg": 0.0,              # genuine zero xG
        "team_b_xg": 1.2,
        "homeGoalCount": 0,
        "awayGoalCount": 2,
        "overallGoalCount": 2,
        "_rich": {
            "corner_kicks": (0, 6),    # genuine zero home corners, 6 away
        },
    }
    rm = _adapted_to_research_match(adapted, league_id=555, season="sn_x")

    assert rm.league_id == 555
    assert rm.match_id == 123               # numeric suffix extracted
    assert rm.corners_home == 0             # zero preserved
    assert rm.corners_away == 6
    assert rm.total_corners == 6
    assert rm.shots_on_target_home is None  # absent stays None
    assert rm.shots_on_target_away == 5
    assert rm.yellow_cards_home == 0        # zero preserved
    assert rm.yellow_cards_away is None     # absent stays None
    assert rm.home_xg == 0.0                # zero xG preserved (not None)
    assert rm.fouls_away is None


def test_rich_mapping_absent_rich_block_yields_none_corners() -> None:
    adapted = {
        "match_id": 999,
        "home_name": "X",
        "away_name": "Y",
        "date_unix": 1,
        "team_a_red_cards": 0,
        "team_b_red_cards": 0,
        "homeGoalCount": 1,
        "awayGoalCount": 1,
        "overallGoalCount": 2,
        # no "_rich" -> corners cannot be populated
    }
    rm = _adapted_to_research_match(adapted, league_id=1, season="s")
    assert rm.corners_home is None
    assert rm.corners_away is None
    assert rm.total_corners is None


@pytest.mark.skipif(
    not os.path.isdir(RICH_CACHE_DIR)
    or not os.path.exists(os.path.join(RICH_CACHE_DIR, "_all_fixtures_sn_3064530.json")),
    reason="real Rich cache not present",
)
def test_rich_loader_reads_real_cache_and_exposes_leagues() -> None:
    """Smoke test against the real cached Rich corpus (fast: reads cache only)."""
    loaded = RichCorpusLoader().load()
    assert len(loaded) > 100
    labels = {lm.league for lm in loaded}
    # The rich registry covers Championship + Ligue 2 + La Liga 2.
    assert "Championship" in labels
    # Every match carries a league identity (machine id + readable label).
    assert all(lm.league for lm in loaded)
    assert all(isinstance(lm.match.league_id, int) for lm in loaded)
