"""Build strictly-prior side observations for the hierarchical count models.

Each completed fixture becomes **two** rows — one per side — because the models
forecast a side count and convolve the two into the match total. The features on a
row describe the counting side's recent production and the opposing side's recent
record of conceding, both read from shrinking current-season windows that close
strictly before kickoff.

Two leakage disciplines are enforced structurally rather than by review:

1. **Nothing from the fixture being predicted.** Features are read from
   :class:`~src.research.prediction_engine.form_window.FormWindowBuilder` before
   the fixture is folded into history, and the fixture's own statistics are never
   among the feature names. :func:`assert_no_same_match_leakage` re-derives every
   row from an independently rebuilt history and asserts equality, so a future
   refactor that reorders read and write is caught by a test rather than by a
   published forecast.
2. **Nothing from a simultaneous fixture.** Fixtures sharing a kickoff are emitted
   as a complete batch before any of them updates history, so two teams playing at
   the same time cannot inform each other's features.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Optional, Sequence

from src.research.models.hierarchical_market_model import SideRow
from src.research.models.market_family import (
    MarketFamily,
    numeric,
    required_stats,
    side_counts,
)
from src.research.prediction_engine.form_window import (
    DEFAULT_HALF_LIFE_MATCHES,
    DEFAULT_WINDOW,
    FormWindowBuilder,
    TeamForm,
    gate_reason,
    season_key,
    window_provenance,
)


@dataclass(frozen=True, slots=True)
class FixtureRows:
    """The two side rows for one fixture, plus what a reader needs about it."""

    fixture_id: str
    league: str
    season: str
    kickoff_unix: int
    date_block: str
    league_week_block: str
    home_row: SideRow
    away_row: SideRow
    home_form: TeamForm
    away_form: TeamForm
    total_count: Optional[float]
    home_count: Optional[float]
    away_count: Optional[float]

    @property
    def gate_reason(self) -> Optional[str]:
        return gate_reason(self.home_form, self.away_form)

    @property
    def window_provenance(self) -> dict[str, object]:
        return window_provenance(self.home_form, self.away_form)

    def both_scored(self) -> Optional[float]:
        if self.home_count is None or self.away_count is None:
            return None
        return 1.0 if self.home_count >= 1.0 and self.away_count >= 1.0 else 0.0


def side_features(
    family: MarketFamily, counting: TeamForm, opposing: TeamForm, *, is_home: bool
) -> dict[str, float]:
    """Assemble one side's feature row from two teams' windows.

    ``support_n`` is the shared uncertainty feature: how many matches actually
    stood behind the thinner of the two windows. It is an input to the fit, so a
    thin row is down-weighted by the model rather than filtered out by a rule.
    """
    features: dict[str, float] = {}
    for stat in family.features.produce:
        features[f"own_produce_{stat}"] = float(counting.produced.get(stat, 0.0))
    for stat in family.features.concede:
        features[f"opp_concede_{stat}"] = float(opposing.conceded.get(stat, 0.0))
    features["is_home"] = 1.0 if is_home else 0.0
    features["support_n"] = float(min(counting.window.used, opposing.window.used))
    return features


def build_fixture_rows(
    matches: Sequence[Mapping[str, object]],
    families: Sequence[MarketFamily],
    *,
    window: int = DEFAULT_WINDOW,
    half_life_matches: float = DEFAULT_HALF_LIFE_MATCHES,
) -> dict[str, list[FixtureRows]]:
    """Convert completed fixtures into per-family side rows, chronologically.

    Returns one list per family name, in kickoff order. Fixtures whose target the
    provider does not populate are omitted for that family and kept for others, so
    a league missing first-half corners still contributes to corners.
    """
    if not families:
        raise ValueError("at least one market family is required")
    names = [family.name for family in families]
    if len(set(names)) != len(names):
        raise ValueError("market family names must be unique")

    ordered = _chronological(matches)
    builder = FormWindowBuilder(
        required_stats(families),
        window=window,
        half_life_matches=half_life_matches,
    )
    result: dict[str, list[FixtureRows]] = {family.name: [] for family in families}

    for batch in _equal_kickoff_batches(ordered):
        for match in batch:
            league = str(match.get("_league") or match.get("league") or "")
            season = season_key(match)
            kickoff = numeric(match.get("date_unix"))
            home = _team_id(match, home=True)
            away = _team_id(match, home=False)
            if not league or season is None or kickoff is None:
                continue
            if home is None or away is None:
                continue
            kickoff_unix = int(kickoff)
            home_name = _team_name(match, home=True) or home
            away_name = _team_name(match, home=False) or away
            home_form = builder.team_form(league, home, kickoff_unix)
            away_form = builder.team_form(league, away, kickoff_unix)
            fixture_id = _fixture_id(match)
            date_block = (
                datetime.fromtimestamp(kickoff_unix, tz=timezone.utc).date().isoformat()
            )
            week_block = _league_week_block(match, league, season, kickoff_unix)

            for family in families:
                counts = side_counts(match, family.name)
                home_count, away_count = counts if counts else (None, None)
                home_row = SideRow(
                    fixture_id=fixture_id,
                    league=league,
                    season=season,
                    kickoff_unix=kickoff_unix,
                    counting_team=home,
                    opposing_team=away,
                    is_home=True,
                    features=side_features(family, home_form, away_form, is_home=True),
                    count=home_count,
                    counting_team_name=home_name,
                    opposing_team_name=away_name,
                )
                away_row = SideRow(
                    fixture_id=fixture_id,
                    league=league,
                    season=season,
                    kickoff_unix=kickoff_unix,
                    counting_team=away,
                    opposing_team=home,
                    is_home=False,
                    features=side_features(family, away_form, home_form, is_home=False),
                    count=away_count,
                    counting_team_name=away_name,
                    opposing_team_name=home_name,
                )
                result[family.name].append(
                    FixtureRows(
                        fixture_id=fixture_id,
                        league=league,
                        season=season,
                        kickoff_unix=kickoff_unix,
                        date_block=date_block,
                        league_week_block=week_block,
                        home_row=home_row,
                        away_row=away_row,
                        home_form=home_form,
                        away_form=away_form,
                        total_count=(
                            None
                            if home_count is None or away_count is None
                            else home_count + away_count
                        ),
                        home_count=home_count,
                        away_count=away_count,
                    )
                )
        # Compute-before-update: the batch enters history only now.
        builder.observe_batch(batch)

    return result


def training_rows(fixtures: Iterable[FixtureRows]) -> list[SideRow]:
    """Flatten fixtures into the labelled side rows a model fit consumes."""
    rows: list[SideRow] = []
    for fixture in fixtures:
        for row in (fixture.home_row, fixture.away_row):
            if row.count is not None:
                rows.append(row)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Leakage assertion
# ─────────────────────────────────────────────────────────────────────────────
def assert_no_same_match_leakage(
    matches: Sequence[Mapping[str, object]],
    fixtures: Sequence[FixtureRows],
    families: Sequence[MarketFamily],
    *,
    window: int = DEFAULT_WINDOW,
    half_life_matches: float = DEFAULT_HALF_LIFE_MATCHES,
    tolerance: float = 1e-9,
) -> None:
    """Re-derive every feature from an independent history and assert equality.

    This is deliberately a second implementation of the read order rather than a
    re-run of the first: the builder is rebuilt from scratch and every fixture's
    features are recomputed from a history that provably excludes both the fixture
    and its kickoff-mates. Agreement means the emitted rows contain nothing from
    the fixture they describe.
    """
    if not fixtures:
        return
    ordered = _chronological(matches)
    builder = FormWindowBuilder(
        required_stats(families), window=window, half_life_matches=half_life_matches
    )
    by_family: dict[str, dict[str, FixtureRows]] = {}
    for fixture in fixtures:
        by_family.setdefault(_family_of(fixture, families), {})[
            fixture.fixture_id
        ] = fixture

    violations: list[str] = []
    for batch in _equal_kickoff_batches(ordered):
        for match in batch:
            league = str(match.get("_league") or match.get("league") or "")
            kickoff = numeric(match.get("date_unix"))
            home = _team_id(match, home=True)
            away = _team_id(match, home=False)
            if not league or kickoff is None or home is None or away is None:
                continue
            home_form = builder.team_form(league, home, int(kickoff))
            away_form = builder.team_form(league, away, int(kickoff))
            fixture_id = _fixture_id(match)
            for family in families:
                emitted = by_family.get(family.name, {}).get(fixture_id)
                if emitted is None:
                    continue
                expected_home = side_features(
                    family, home_form, away_form, is_home=True
                )
                expected_away = side_features(
                    family, away_form, home_form, is_home=False
                )
                for label, expected, actual in (
                    ("home", expected_home, emitted.home_row.features),
                    ("away", expected_away, emitted.away_row.features),
                ):
                    for name, value in expected.items():
                        got = float(actual.get(name, math.nan))
                        if not math.isclose(
                            got, value, rel_tol=0.0, abs_tol=tolerance
                        ):
                            violations.append(
                                f"{family.name}/{fixture_id}/{label}/{name}: "
                                f"emitted {got!r} != prior-only {value!r}"
                            )
                            if len(violations) >= 5:
                                raise AssertionError(
                                    "same-match leakage in side rows: "
                                    + "; ".join(violations)
                                )
        builder.observe_batch(batch)

    if violations:
        raise AssertionError(
            "same-match leakage in side rows: " + "; ".join(violations)
        )

    # No raw same-fixture statistic may appear among the feature names.
    raw_keys = {"team_a_corners", "team_b_corners", "homeGoalCount", "awayGoalCount"}
    for fixture in fixtures:
        offending = raw_keys & set(fixture.home_row.features)
        if offending:
            raise AssertionError(
                f"feature row carries raw same-match keys: {sorted(offending)}"
            )


def _family_of(fixture: FixtureRows, families: Sequence[MarketFamily]) -> str:
    """Recover which family a fixture row set belongs to from its feature names."""
    names = set(fixture.home_row.features)
    for family in families:
        if set(family.feature_names) == names:
            return family.name
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _fixture_id(match: Mapping[str, object]) -> str:
    for key in ("id", "match_id", "fixture_id"):
        value = match.get(key)
        if value is not None and str(value) != "":
            return str(value)
    return (
        f"{match.get('_league')}:{match.get('date_unix')}:"
        f"{_team_id(match, home=True)}:{_team_id(match, home=False)}"
    )


def _team_id(match: Mapping[str, object], *, home: bool) -> Optional[str]:
    keys = ("homeID", "home_id", "home_name") if home else ("awayID", "away_id", "away_name")
    for key in keys:
        value = match.get(key)
        if value is not None and str(value) != "":
            return str(value)
    return None


def _team_name(match: Mapping[str, object], *, home: bool) -> Optional[str]:
    """Display label for a team. Never used as a model key."""
    keys = ("home_name", "homeName") if home else ("away_name", "awayName")
    for key in keys:
        value = match.get(key)
        if value is not None and str(value) != "":
            return str(value)
    return None


def _league_week_block(
    match: Mapping[str, object], league: str, season: str, kickoff: int
) -> str:
    """Bootstrap block id: a provider match-week where available, else ISO week.

    Fixtures inside a match-week are not independent — the same weather, the same
    congestion, the same referee appointments — so the bootstrap resamples whole
    weeks rather than individual fixtures.

    ``0`` is rejected alongside ``None`` and ``-1`` because for several leagues it
    is the provider's "not set" value rather than a real match-week: MLS carries
    ``game_week = 0`` on 78% of its fixtures. Accepting it collapsed an entire
    league into two blocks, which silently destroys the bootstrap — a resample of
    two clusters cannot estimate anything, and the cells were correctly but
    uninformatively reported as insufficient. Falling back to the ISO week gives a
    real cluster structure instead.
    """
    for key in ("game_week", "gameWeek", "week", "round", "roundID"):
        value = match.get(key)
        if value in (None, "", -1, "-1", 0, "0"):
            continue
        return f"{league}:{season}:provider-week:{value}"
    iso = datetime.fromtimestamp(kickoff, tz=timezone.utc).isocalendar()
    return f"{league}:{season}:iso-week:{iso.year}-{iso.week:02d}"


def _chronological(
    matches: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    deduplicated: dict[str, Mapping[str, object]] = {}
    for match in matches:
        if str(match.get("status") or "").casefold() != "complete":
            continue
        kickoff = numeric(match.get("date_unix"))
        if kickoff is None or kickoff <= 0:
            continue
        deduplicated.setdefault(_fixture_id(match), match)
    return sorted(
        deduplicated.values(),
        key=lambda m: (int(numeric(m.get("date_unix")) or 0), _fixture_id(m)),
    )


def _equal_kickoff_batches(
    ordered: Sequence[Mapping[str, object]],
) -> Iterable[list[Mapping[str, object]]]:
    cursor = 0
    while cursor < len(ordered):
        kickoff = int(numeric(ordered[cursor].get("date_unix")) or 0)
        end = cursor + 1
        while end < len(ordered) and int(
            numeric(ordered[end].get("date_unix")) or 0
        ) == kickoff:
            end += 1
        yield list(ordered[cursor:end])
        cursor = end
