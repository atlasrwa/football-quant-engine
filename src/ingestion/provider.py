"""DataProvider protocol and MockProvider implementation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Protocol, runtime_checkable

from src.models.match import Match

logger = logging.getLogger(__name__)

# Default fixture directory
_FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"


@runtime_checkable
class DataProvider(Protocol):
    """Interface for match data sourcing.

    All providers must implement fetch_matches to return a list of
    validated Match objects for a given league and season.
    """

    def fetch_matches(self, league_id: int, season: str) -> List[Match]:
        """Fetch match data for a league season.

        Args:
            league_id: The FootyStats league identifier.
            season: The season string (e.g., "2023").

        Returns:
            List of Match objects.
        """
        ...


class MockProvider:
    """Test provider that loads match data from local JSON fixture files.

    Fixture files should follow the FootyStats response schema and be
    located at: tests/fixtures/{league_id}_{season}.json

    When use_live_example=True, fetches from the public FootyStats
    key=example endpoint instead (not implemented in mock — raises).
    """

    EXAMPLE_ENDPOINT = (
        "https://api.football-data-api.com/league-matches"
        "?key=example&league_id=4759"
    )

    def __init__(
        self,
        fixtures_dir: Path | None = None,
        use_live_example: bool = False,
    ) -> None:
        """Initialize MockProvider.

        Args:
            fixtures_dir: Path to fixture JSON files. Defaults to tests/fixtures/.
            use_live_example: If True, would fetch from live example endpoint
                              (raises NotImplementedError in mock).
        """
        self._fixtures_dir = fixtures_dir or _FIXTURES_DIR
        self._use_live_example = use_live_example

    def fetch_matches(self, league_id: int, season: str) -> List[Match]:
        """Load matches from a local fixture file.

        Season strings are sanitized (slashes → underscores) for safe
        filesystem paths (e.g., "2018/2019" → "2018_2019").

        Args:
            league_id: The FootyStats league identifier.
            season: The season string.

        Returns:
            List of Match objects parsed from the fixture.

        Raises:
            FileNotFoundError: If the fixture file does not exist.
            NotImplementedError: If use_live_example is True.
        """
        if self._use_live_example:
            raise NotImplementedError(
                "Live example fetching not available in MockProvider. "
                "Use FootyStatsClient with key='example' instead."
            )

        safe_season = season.replace("/", "_")
        fixture_path = self._fixtures_dir / f"{league_id}_{safe_season}.json"
        if not fixture_path.exists():
            raise FileNotFoundError(
                f"Fixture file not found: {fixture_path}"
            )

        logger.info("Loading fixture: %s", fixture_path)
        with open(fixture_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        return self._parse_response(raw_data)

    def _parse_response(self, raw_data: Dict[str, Any]) -> List[Match]:
        """Parse a FootyStats-format JSON response into Match objects.

        Args:
            raw_data: The full JSON response dict with a "data" key.

        Returns:
            List of successfully parsed Match objects. Skips invalid records.
        """
        matches: List[Match] = []
        records = raw_data.get("data", [])

        for record in records:
            try:
                match = self._record_to_match(record)
                matches.append(match)
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(
                    "Skipping record id=%s: %s",
                    record.get("id", "unknown"),
                    e,
                )

        logger.info("Parsed %d/%d records successfully", len(matches), len(records))
        return matches

    @staticmethod
    def _record_to_match(record: Dict[str, Any]) -> Match:
        """Convert a single raw JSON record to a Match dataclass.

        Args:
            record: A single match dict from the FootyStats response.

        Returns:
            A validated Match instance.
        """
        home_goals = int(record["homeGoalCount"])
        away_goals = int(record["awayGoalCount"])

        return Match(
            id=int(record["id"]),
            date_unix=int(record["date_unix"]),
            league_id=int(record["league_id"]),
            season=str(record["season"]),
            home_team=str(record["home_name"]),
            away_team=str(record["away_name"]),
            home_goals=home_goals,
            away_goals=away_goals,
            total_goals=home_goals + away_goals,
            home_xg=float(record.get("team_a_xg") or 0.0),
            away_xg=float(record.get("team_b_xg") or 0.0),
            referee=record.get("referee_name") or None,
            over_under_line=2.5,  # Default line; override if present
            over_odds=float(record["o25_potential"]) if record.get("o25_potential") else None,
            under_odds=float(record["u25_potential"]) if record.get("u25_potential") else None,
        )
