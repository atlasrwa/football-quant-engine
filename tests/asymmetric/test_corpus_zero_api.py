"""Property 23: Zero API during build and backtest (task 2.3).

# Feature: asymmetric-matchup-engine, Property 23: Zero API during build and backtest

*For any* build or backtest execution over the cached corpora, the live API
client is never invoked.

**Validates: Requirements 12.1, 12.2**

NOTE: ``hypothesis`` is not yet a project dependency (it is added in task 12.1).
This test is therefore written as a deterministic ``pytest`` test that injects a
client/source stub raising on ANY network call and asserts the loaders never
invoke it. It will be converted to a ``hypothesis`` property test with
``from hypothesis import settings`` and ``@settings(max_examples=100)`` in task
12.1 once the dependency lands.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.research.asymmetric.corpus import (
    BroadCorpusLoader,
    NetworkAccessError,
    RichCorpusLoader,
)


class _ExplodingClient:
    """A stub 'live' client that raises on ANY attribute access / call.

    If either loader ever touches a network client, one of these methods fires
    and the test fails. Because the loaders only read cached files and never
    import ``live_fetch``, this client is never invoked.
    """

    def __getattr__(self, name: str):  # noqa: ANN001 - any attribute is a trap
        def _boom(*args, **kwargs):
            raise NetworkAccessError(
                f"network call attempted via .{name}() during build/backtest"
            )
        return _boom


class _ExplodingBroadSource:
    """A cache 'source' whose network path explodes but whose cache path works.

    ``iter_raw_records`` reads only from the provided in-memory list (cache), so
    the loader completes without ever calling the network method.
    """

    def __init__(self, records):
        self._records = records
        self.client = _ExplodingClient()

    def fetch(self, *args, **kwargs):  # any 'network' method is a trap
        raise NetworkAccessError("network fetch attempted")

    def iter_raw_records(self):
        return iter(self._records)


def _complete_record(mid: int) -> dict:
    return {
        "id": mid,
        "date_unix": 1_700_000_000 + mid,
        "status": "complete",
        "home_name": f"H{mid}",
        "away_name": f"A{mid}",
        "competition_id": 42,
        "season": "2025/2026",
        "homeGoalCount": 1,
        "awayGoalCount": 1,
        "team_a_corners": 0,
        "team_b_corners": 4,
    }


def test_broad_loader_never_invokes_network_client() -> None:
    records = [_complete_record(i) for i in range(1, 6)]
    source = _ExplodingBroadSource(records)

    loaded = BroadCorpusLoader(source=source).load()

    # Loader produced results purely from the injected cache records ...
    assert len(loaded) == 5
    # ... and touching the network client would have raised NetworkAccessError.
    with pytest.raises(NetworkAccessError):
        source.client.fetch_season_matches(42)
    with pytest.raises(NetworkAccessError):
        source.fetch()


class _ExplodingRichSource:
    """A Rich source exposing the multisrc_corpus surface but no network.

    ``load_season`` / ``fixture_path`` / ``LEAGUES`` return synthesized cached
    data; any other attribute (a would-be network call) raises.
    """

    LEAGUES = {
        "champ": {
            "display": "Championship",
            "comp": "championship",
            "seasons": ["sn_test"],
            "fixture_prefix": "",
        }
    }
    CACHE = "/nonexistent"

    def __init__(self, fixture_exists: bool = True):
        self._fixture_exists = fixture_exists

    def fixture_path(self, tag, season_id):
        # Return a path our loader will os.path.exists() check. We monkeypatch
        # existence in the test via a real temp file.
        return self._fixture_file

    def load_season(self, tag, season_id):
        return [
            {
                "match_id": "mt_000000001",
                "home_name": "Alpha",
                "away_name": "Beta",
                "date_unix": 1_700_000_000,
                "team_a_red_cards": 0,
                "team_b_red_cards": 0,
                "team_a_shotsOnTarget": 4,
                "team_b_shotsOnTarget": 3,
                "homeGoalCount": 1,
                "awayGoalCount": 0,
                "overallGoalCount": 1,
                "_rich": {"corner_kicks": (2, 3)},
            }
        ]

    def __getattr__(self, name):  # any other attr is a network trap
        def _boom(*args, **kwargs):
            raise NetworkAccessError(f"network call via .{name}()")
        return _boom


def test_rich_loader_never_invokes_network_client(tmp_path: Path) -> None:
    # Create a real fixture file so the loader's cache-existence check passes.
    fx = tmp_path / "_all_fixtures_sn_test.json"
    fx.write_text(json.dumps({"fixtures": []}))

    source = _ExplodingRichSource()
    source._fixture_file = str(fx)

    loaded = RichCorpusLoader(cache_dir=str(tmp_path), source=source).load()

    assert len(loaded) == 1
    assert loaded[0].league == "Championship"
    assert loaded[0].match.corners_home == 2
    assert loaded[0].match.corners_away == 3
    # A genuine network method on the source raises.
    with pytest.raises(NetworkAccessError):
        source.fetch_live_fixture()
