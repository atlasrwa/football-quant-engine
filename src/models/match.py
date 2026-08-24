"""Core Match dataclass representing a validated match record from FootyStats."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class Match:
    """Validated match record from FootyStats ingestion.

    All fields are guaranteed present after schema validation,
    except optional fields (referee, odds) which may be None.
    """

    id: int
    date_unix: int
    league_id: int
    season: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    total_goals: int
    home_xg: float
    away_xg: float
    referee: Optional[str]
    over_under_line: float  # e.g., 2.5
    over_odds: Optional[float]  # decimal odds for Over
    under_odds: Optional[float]  # decimal odds for Under

    def __post_init__(self) -> None:
        """Validate invariants after construction."""
        if self.total_goals != self.home_goals + self.away_goals:
            raise ValueError(
                f"total_goals ({self.total_goals}) must equal "
                f"home_goals ({self.home_goals}) + away_goals ({self.away_goals})"
            )
        if self.home_xg < 0 or self.away_xg < 0:
            raise ValueError("xG values must be non-negative")
        if self.over_under_line <= 0:
            raise ValueError("over_under_line must be positive")
