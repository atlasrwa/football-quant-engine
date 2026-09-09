"""Data-quality reporting, collector health states, and schema-drift checks.

Produces a lightweight machine-readable (JSON) + Markdown quality report from
the persisted capture store, plus explicit collector health states so the
system fails visibly rather than silently emitting a partial dataset that looks
complete.

Schema-drift validation guards the critical fields we rely on: if a required
field disappears or changes type in a live payload, we raise
API_SCHEMA_DRIFT rather than normalizing garbage. Noncritical new fields are
ignored safely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from src.research.prospective.storage import CaptureStore
from src.research.prospective.vintage_quality import (
    VintageQuality,
    best_capture_for_vintage,
)
from src.research.prospective.vintages import ProspectiveVintage


class HealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    QUOTA_LIMITED = "QUOTA_LIMITED"
    AUTH_FAILED = "AUTH_FAILED"
    IDENTITY_FAILURE = "IDENTITY_FAILURE"
    API_SCHEMA_DRIFT = "API_SCHEMA_DRIFT"
    NO_UPCOMING_FIXTURES = "NO_UPCOMING_FIXTURES"


class SchemaDriftError(RuntimeError):
    """Raised when a critical field is missing or the wrong type."""


# Critical fields per endpoint we normalize. (field_path, expected_types).
_CRITICAL_MATCH_FIELDS = (
    ("id", (str,)),
    ("utc_date", (str,)),
    ("home_team", (dict,)),
    ("away_team", (dict,)),
)
_CRITICAL_ODDS_FIELDS = (("bookmakers", (list,)),)
_CRITICAL_LINEUP_FIELDS = (("home", (dict,)), ("away", (dict,)))


def _check(data: Mapping[str, Any], fields: tuple, *, context: str) -> None:
    for name, types in fields:
        if name not in data:
            raise SchemaDriftError(f"{context}: required field '{name}' missing")
        if not isinstance(data[name], types):
            got = type(data[name]).__name__
            raise SchemaDriftError(f"{context}: field '{name}' wrong type ({got})")


def validate_match_schema(payload: Mapping[str, Any]) -> None:
    """Validate a match/detail payload's critical fields (else SchemaDriftError)."""
    data = payload.get("data", payload)
    if isinstance(data, list):
        for item in data:
            if isinstance(item, Mapping):
                _check(item, _CRITICAL_MATCH_FIELDS, context="match")
        return
    if not isinstance(data, Mapping):
        raise SchemaDriftError("match: payload data is not an object")
    _check(data, _CRITICAL_MATCH_FIELDS, context="match")


def validate_odds_schema(payload: Mapping[str, Any]) -> None:
    data = payload.get("data", payload)
    if not isinstance(data, Mapping):
        raise SchemaDriftError("odds: payload data is not an object")
    _check(data, _CRITICAL_ODDS_FIELDS, context="odds")


def validate_lineup_schema(payload: Mapping[str, Any]) -> None:
    data = payload.get("data", payload)
    if not isinstance(data, Mapping):
        raise SchemaDriftError("lineups: payload data is not an object")
    _check(data, _CRITICAL_LINEUP_FIELDS, context="lineups")


# ---------------------------------------------------------------------------
# Quality report
# ---------------------------------------------------------------------------


@dataclass
class FixtureCoverage:
    """Per-fixture coverage derived from persisted captures."""

    fixture_id: str
    kickoff_ts: Optional[float]
    league: Optional[str]
    vintages_captured: dict[str, str] = field(default_factory=dict)  # vintage -> quality
    pinnacle_seen: bool = False
    bet365_seen: bool = False
    lineup_first_observed_at: Optional[float] = None
    genuine_close: bool = False
    referee_seen: bool = False
    injury_seen: bool = False


@dataclass
class QualityReport:
    """Aggregate data-quality report over the persisted store."""

    generated_at: float
    fixtures_discovered: int
    fixtures_mapped: int
    early_pct: float
    mid_pct: float
    late_pct: float
    final_pct: float
    pinnacle_pct: float
    bet365_pct: float
    lineup_pct: float
    median_first_lineup_stk: Optional[float]
    genuine_close_pct: float
    referee_pct: float
    injury_pct: float
    health: HealthState
    n_multi_vintage: int
    n_confirmed_lineup: int
    n_genuine_close: int

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "fixtures_discovered": self.fixtures_discovered,
            "fixtures_mapped": self.fixtures_mapped,
            "coverage_pct": {
                "EARLY": self.early_pct, "MID": self.mid_pct,
                "LATE": self.late_pct, "FINAL": self.final_pct,
            },
            "bookmaker_pct": {"pinnacle": self.pinnacle_pct, "bet365": self.bet365_pct},
            "lineup_pct": self.lineup_pct,
            "median_first_lineup_seconds_to_kickoff": self.median_first_lineup_stk,
            "genuine_close_pct": self.genuine_close_pct,
            "referee_pct": self.referee_pct,
            "injury_pct": self.injury_pct,
            "health": self.health.value,
            "readiness_counts": {
                "multi_vintage": self.n_multi_vintage,
                "confirmed_lineup": self.n_confirmed_lineup,
                "genuine_close": self.n_genuine_close,
            },
        }

    def to_markdown(self) -> str:
        d = self.to_dict()
        cov = d["coverage_pct"]
        return (
            f"# Prospective capture quality report\n\n"
            f"- Health: **{self.health.value}**\n"
            f"- Fixtures discovered / mapped: {self.fixtures_discovered} / {self.fixtures_mapped}\n"
            f"- Vintage coverage: EARLY {cov['EARLY']:.0%}, MID {cov['MID']:.0%}, "
            f"LATE {cov['LATE']:.0%}, FINAL {cov['FINAL']:.0%}\n"
            f"- Bookmaker: Pinnacle {self.pinnacle_pct:.0%}, Bet365 {self.bet365_pct:.0%}\n"
            f"- Lineup captured: {self.lineup_pct:.0%} "
            f"(median first-lineup STK: {self.median_first_lineup_stk})\n"
            f"- Genuine close: {self.genuine_close_pct:.0%}\n"
            f"- Referee: {self.referee_pct:.0%} · Injury: {self.injury_pct:.0%}\n"
            f"- Readiness: multi_vintage={self.n_multi_vintage}, "
            f"confirmed_lineup={self.n_confirmed_lineup}, "
            f"genuine_close={self.n_genuine_close}\n"
        )


def _median(vals: list[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def build_quality_report(
    store: CaptureStore,
    *,
    now: float,
    mapped_fixture_ids: Optional[set] = None,
    health: HealthState = HealthState.HEALTHY,
) -> QualityReport:
    """Aggregate a quality report from persisted captures.

    Coverage percentages are over discovered fixtures (fixtures that appear in
    the store). ``mapped_fixture_ids`` optionally marks which discovered
    fixtures resolved to a canonical identity.
    """
    by_fixture: dict[str, FixtureCoverage] = {}
    odds_ts: dict[str, list[float]] = {}
    kickoffs: dict[str, float] = {}

    for rec in store.read_all():
        fid = rec.canonical_entity_id
        fc = by_fixture.setdefault(fid, FixtureCoverage(fid, rec.event_time, rec.vintage))
        if rec.event_time is not None:
            kickoffs[fid] = float(rec.event_time)
            fc.kickoff_ts = float(rec.event_time)
        concept = rec.concept
        if concept.startswith("odds:"):
            odds_ts.setdefault(fid, []).append(float(rec.observed_at))
            # Odds concept is "odds:market:selection:line:bookmaker".
            book = concept.rsplit(":", 1)[-1].lower()
            if book == "pinnacle":
                fc.pinnacle_seen = True
            elif book == "bet365":
                fc.bet365_seen = True
        if concept.startswith("confirmed_lineup"):
            t = float(rec.observed_at)
            fc.lineup_first_observed_at = (
                t if fc.lineup_first_observed_at is None else min(fc.lineup_first_observed_at, t)
            )
        if concept.startswith("referee"):
            fc.referee_seen = True
        if concept.startswith("injury") or concept.startswith("availability"):
            fc.injury_seen = True

    # Vintage coverage per fixture from odds observation times.
    for fid, fc in by_fixture.items():
        ko = kickoffs.get(fid)
        times = odds_ts.get(fid, [])
        if ko is None or not times:
            continue
        for v in ProspectiveVintage:
            q = best_capture_for_vintage(vintage=v, observed_ats=times, kickoff_ts=ko)
            if q.quality in (VintageQuality.ON_TARGET, VintageQuality.NEAR_TARGET):
                fc.vintages_captured[v.value] = q.quality.value

    n = len(by_fixture) or 1
    def pct(pred) -> float:
        return sum(1 for fc in by_fixture.values() if pred(fc)) / n

    early = pct(lambda fc: "EARLY" in fc.vintages_captured)
    mid = pct(lambda fc: "MID" in fc.vintages_captured)
    late = pct(lambda fc: "LATE" in fc.vintages_captured)
    final = pct(lambda fc: "FINAL" in fc.vintages_captured)
    lineup = pct(lambda fc: fc.lineup_first_observed_at is not None)
    referee = pct(lambda fc: fc.referee_seen)
    injury = pct(lambda fc: fc.injury_seen)
    pinnacle = pct(lambda fc: fc.pinnacle_seen)
    bet365 = pct(lambda fc: fc.bet365_seen)

    first_lineup_stks = [
        (kickoffs[fid] - fc.lineup_first_observed_at)
        for fid, fc in by_fixture.items()
        if fc.lineup_first_observed_at is not None and fid in kickoffs
    ]

    n_multi = sum(1 for fc in by_fixture.values() if len(fc.vintages_captured) >= 2)
    n_lineup = sum(1 for fc in by_fixture.values() if fc.lineup_first_observed_at is not None)

    if not by_fixture:
        health = HealthState.NO_UPCOMING_FIXTURES

    mapped = len(mapped_fixture_ids) if mapped_fixture_ids is not None else len(by_fixture)

    return QualityReport(
        generated_at=now,
        fixtures_discovered=len(by_fixture),
        fixtures_mapped=mapped,
        early_pct=early, mid_pct=mid, late_pct=late, final_pct=final,
        pinnacle_pct=pinnacle, bet365_pct=bet365,
        lineup_pct=lineup,
        median_first_lineup_stk=_median(first_lineup_stks),
        genuine_close_pct=0.0,
        referee_pct=referee, injury_pct=injury,
        health=health,
        n_multi_vintage=n_multi, n_confirmed_lineup=n_lineup, n_genuine_close=0,
    )
