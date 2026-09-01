"""Team-name resolution and fixture lookup for the Analysis_CLI (Req 9.13-9.15).

Responsibility:
    Resolve supplied home/away team names and a date to a recognised team and a
    scheduled fixture, WITHOUT producing any predictions on failure:

    * unrecognised name  -> reject and identify the offending name (Req 9.13);
    * ambiguous name      -> reject and list the candidate matches (Req 9.14);
    * no scheduled fixture on the date -> report no matching fixture (Req 9.15).

Design decisions:
    * **Pure over an injected index.** Resolution is a pure function over a
      :class:`TeamIndex` (the set of known team names) and a
      :class:`FixtureIndex` (known scheduled fixtures). The CLI builds these from
      the cached corpus (and any capped live fetch); this module performs no I/O
      and imports no live-fetch path, so it is trivially testable and cannot
      trigger a network call.
    * **Deterministic matching.** A name resolves by (1) exact case-insensitive
      match, else (2) unique case-insensitive substring/alias match. Zero
      candidates -> unrecognised; more than one candidate -> ambiguous. This is
      the minimal, explainable rule the design's error table calls for.
    * **Resolution never predicts.** Every failure path returns a typed result
      whose ``ok`` is ``False`` and whose ``message`` names the offending input;
      the caller is responsible for emitting the mandatory caveat and stopping.

This module imports nothing from Prior_Efforts (isolation, Req 13.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional

from src.research.data_source import ResearchMatch


# ─────────────────────────────────────────────────────────────────────────────
# Date parsing (ISO 8601 YYYY-MM-DD, Req 9.1)
# ─────────────────────────────────────────────────────────────────────────────
class DateParseError(ValueError):
    """Raised when a date string is not ISO 8601 ``YYYY-MM-DD``."""


def parse_iso_date(text: str) -> _date:
    """Parse an ISO 8601 ``YYYY-MM-DD`` date, rejecting anything else (Req 9.1).

    Raises:
        DateParseError: if ``text`` is not a valid ``YYYY-MM-DD`` date.
    """
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError) as exc:  # pragma: no cover - message path
        raise DateParseError(
            f"date {text!r} is not ISO 8601 YYYY-MM-DD"
        ) from exc


def day_bounds_unix(day: _date) -> tuple[int, int]:
    """Return the ``[start, end)`` unix-second bounds of a UTC calendar day."""
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    start_unix = int(start.timestamp())
    return start_unix, start_unix + 86_400


# ─────────────────────────────────────────────────────────────────────────────
# Resolution outcomes
# ─────────────────────────────────────────────────────────────────────────────
class ResolutionStatus(Enum):
    """Why a team-name or fixture resolution succeeded or failed."""

    RESOLVED = "RESOLVED"
    UNRECOGNISED = "UNRECOGNISED"   # Req 9.13
    AMBIGUOUS = "AMBIGUOUS"         # Req 9.14
    NO_FIXTURE = "NO_FIXTURE"       # Req 9.15


@dataclass(frozen=True)
class TeamResolution:
    """Result of resolving a single team name (Req 9.13, 9.14).

    ``ok`` is True only when exactly one canonical team matched. On failure the
    ``message`` names the offending input and ``candidates`` lists the ambiguous
    matches (empty for unrecognised). No prediction is ever produced from a
    non-ok resolution.
    """

    status: ResolutionStatus
    query: str
    canonical: Optional[str] = None
    candidates: tuple[str, ...] = ()
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == ResolutionStatus.RESOLVED


@dataclass(frozen=True)
class FixtureResolution:
    """Result of resolving a fixture between two teams on a date (Req 9.15).

    ``ok`` is True only when both teams resolved AND a scheduled fixture exists
    between them on the date. On any failure the appropriate sub-result / message
    identifies the offending input and no prediction is produced.
    """

    status: ResolutionStatus
    home: TeamResolution
    away: TeamResolution
    fixture: Optional[ResearchMatch] = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == ResolutionStatus.RESOLVED and self.fixture is not None


# ─────────────────────────────────────────────────────────────────────────────
# TeamIndex — known team names (Req 9.13, 9.14)
# ─────────────────────────────────────────────────────────────────────────────
class TeamIndex:
    """A case-insensitive index of recognised canonical team names.

    Resolution rule (deterministic):
        1. exact case-insensitive match -> resolved;
        2. else unique case-insensitive substring match -> resolved;
        3. else zero matches -> unrecognised; >1 matches -> ambiguous.
    """

    def __init__(self, teams: Iterable[str]) -> None:
        # Preserve a canonical spelling per lowercased key (first seen wins).
        self._canonical: dict[str, str] = {}
        for t in teams:
            key = t.strip().lower()
            if key and key not in self._canonical:
                self._canonical[key] = t.strip()

    @property
    def teams(self) -> tuple[str, ...]:
        return tuple(sorted(self._canonical.values()))

    def resolve(self, query: str) -> TeamResolution:
        """Resolve one team name (Req 9.13, 9.14)."""
        q = (query or "").strip()
        qlow = q.lower()
        if not qlow:
            return TeamResolution(
                status=ResolutionStatus.UNRECOGNISED,
                query=query,
                message="empty team name is not recognised",
            )

        # 1. exact case-insensitive match.
        if qlow in self._canonical:
            return TeamResolution(
                status=ResolutionStatus.RESOLVED,
                query=query,
                canonical=self._canonical[qlow],
            )

        # 2. substring match across canonical names.
        candidates = sorted(
            name for key, name in self._canonical.items() if qlow in key
        )
        if len(candidates) == 1:
            return TeamResolution(
                status=ResolutionStatus.RESOLVED,
                query=query,
                canonical=candidates[0],
            )
        if len(candidates) > 1:
            return TeamResolution(
                status=ResolutionStatus.AMBIGUOUS,
                query=query,
                candidates=tuple(candidates),
                message=(
                    f"team name {query!r} is ambiguous; candidates: "
                    + ", ".join(candidates)
                ),
            )

        # 3. no match at all.
        return TeamResolution(
            status=ResolutionStatus.UNRECOGNISED,
            query=query,
            message=f"team name {query!r} is not recognised",
        )


# ─────────────────────────────────────────────────────────────────────────────
# FixtureIndex — scheduled fixtures (Req 9.15)
# ─────────────────────────────────────────────────────────────────────────────
class FixtureIndex:
    """An index of scheduled fixtures, resolvable by (home, away, date).

    Built from a list of :class:`ResearchMatch` (cached fixtures, and any
    scheduled/future fixtures a capped live fetch supplied). A "fixture on the
    date" is a match whose kickoff falls within the supplied UTC calendar day and
    whose two teams equal the resolved canonical names (in either home/away
    orientation, since a scheduled fixture between the two teams is what the user
    asked about).
    """

    def __init__(self, matches: Iterable[ResearchMatch]) -> None:
        self._matches: list[ResearchMatch] = list(matches)
        self._team_index = TeamIndex(
            [m.home_team for m in self._matches]
            + [m.away_team for m in self._matches]
        )

    @property
    def team_index(self) -> TeamIndex:
        return self._team_index

    @property
    def matches(self) -> tuple[ResearchMatch, ...]:
        return tuple(self._matches)

    def fixture_on(
        self, home: str, away: str, day: _date
    ) -> Optional[ResearchMatch]:
        """Return the scheduled fixture between ``home`` and ``away`` on ``day``.

        Matching is by canonical team names on the given UTC calendar day. The
        home/away orientation supplied by the user is honoured first; if only the
        reversed orientation is scheduled that is returned too (a fixture between
        the two teams still exists), so the CLI can proceed and note orientation.
        """
        start, end = day_bounds_unix(day)
        # Prefer exact orientation, then reversed.
        for want_home, want_away in ((home, away), (away, home)):
            for m in self._matches:
                if (
                    start <= m.date_unix < end
                    and m.home_team == want_home
                    and m.away_team == want_away
                ):
                    return m
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Top-level resolution (Req 9.13-9.15)
# ─────────────────────────────────────────────────────────────────────────────
def resolve_fixture(
    home_query: str,
    away_query: str,
    day: _date,
    fixture_index: FixtureIndex,
) -> FixtureResolution:
    """Resolve both team names and the scheduled fixture (Req 9.13-9.15).

    Returns a :class:`FixtureResolution` whose ``ok`` is True only when both
    teams resolve to a single canonical name AND a scheduled fixture between them
    exists on ``day``. Every failure path names the offending input and yields no
    fixture (so the caller produces no predictions).
    """
    ti = fixture_index.team_index
    home = ti.resolve(home_query)
    away = ti.resolve(away_query)

    if not home.ok or not away.ok:
        # Surface the first offending input's status/message.
        offending = home if not home.ok else away
        return FixtureResolution(
            status=offending.status,
            home=home,
            away=away,
            message=offending.message,
        )

    fixture = fixture_index.fixture_on(home.canonical, away.canonical, day)
    if fixture is None:
        return FixtureResolution(
            status=ResolutionStatus.NO_FIXTURE,
            home=home,
            away=away,
            message=(
                f"no scheduled fixture between {home.canonical!r} and "
                f"{away.canonical!r} on {day.isoformat()}"
            ),
        )

    return FixtureResolution(
        status=ResolutionStatus.RESOLVED,
        home=home,
        away=away,
        fixture=fixture,
    )
