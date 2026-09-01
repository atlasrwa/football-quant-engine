"""Shared helpers for the Analysis_CLI tests.

Builds a small synthetic cached corpus with a scheduled future fixture, and
imports the CLI script module by path (``scripts`` is not an importable package).
"""

from __future__ import annotations

import importlib.util
import random
from datetime import datetime, timezone
from pathlib import Path

from src.research.data_source import ResearchMatch

_REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DATE_ISO = "2026-09-05"


def load_cli_module():
    """Import ``scripts/asymmetric_analyze.py`` by path."""
    path = _REPO_ROOT / "scripts" / "asymmetric_analyze.py"
    spec = importlib.util.spec_from_file_location("asymmetric_analyze", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fixture_unix(iso: str = FIXTURE_DATE_ISO) -> int:
    y, m, d = (int(x) for x in iso.split("-"))
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())


def build_corpus(
    *,
    league_id: int = 100,
    league_label: str = "Championship",
    n_history: int = 90,
    home: str = "Leeds",
    away: str = "Norwich",
    schedule_fixture: bool = True,
    seed: int = 3,
) -> list[tuple[ResearchMatch, str]]:
    """A completed history over a small team pool + one scheduled future fixture."""
    rng = random.Random(seed)
    teams = [home, away, "Watford", "Hull", "Stoke", "Luton"]
    corpus: list[tuple[ResearchMatch, str]] = []
    d = 1_600_000_000
    for i in range(n_history):
        h = rng.choice(teams)
        a = rng.choice([t for t in teams if t != h])
        d += 86_400 * 3
        corpus.append(
            (
                ResearchMatch(
                    match_id=i + 1,
                    date_unix=d,
                    league_id=league_id,
                    season="s",
                    home_team=h,
                    away_team=a,
                    home_goals=rng.randint(0, 4),
                    away_goals=rng.randint(0, 3),
                    corners_home=rng.randint(2, 9),
                    corners_away=rng.randint(2, 9),
                    shots_on_target_home=rng.randint(1, 8),
                    shots_on_target_away=rng.randint(1, 8),
                    fouls_home=rng.randint(6, 16),
                    fouls_away=rng.randint(6, 16),
                    yellow_cards_home=rng.randint(0, 4),
                    yellow_cards_away=rng.randint(0, 4),
                    red_cards_home=0,
                    red_cards_away=0,
                    attacks_home=rng.randint(60, 140),
                    attacks_away=rng.randint(60, 140),
                    dangerous_attacks_home=rng.randint(20, 70),
                    dangerous_attacks_away=rng.randint(20, 70),
                ),
                league_label,
            )
        )
    if schedule_fixture:
        corpus.append(
            (
                ResearchMatch(
                    match_id=9_999,
                    date_unix=fixture_unix(),
                    league_id=league_id,
                    season="s",
                    home_team=home,
                    away_team=away,
                    home_goals=None,
                    away_goals=None,
                ),
                league_label,
            )
        )
    return corpus
