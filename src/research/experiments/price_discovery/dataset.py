"""Deterministic price-discovery dataset builder (leakage-safe).

Reads the append-only prospective capture store and produces market-movement
research rows. The pipeline is:

    CaptureStore odds records
        -> parse concept  odds:<market>:<selection>:<line>:<bookmaker>
        -> group by KEY = (fixture, bookmaker, market, selection, line)
        -> per snapshot: de-vig the over/under pair AT THAT observed_at
           into a fair probability
        -> assign each snapshot a vintage from its ACTUAL seconds-to-kickoff
        -> for each ordered vintage pair (EARLY->MID, MID->LATE, LATE->FINAL,
           EARLY->FINAL, PRE_LINEUP->POST_LINEUP, POST_LINEUP->FINAL) emit a
           Transition when BOTH endpoints exist for the SAME key
        -> the row's target is logit(p_later) - logit(p_earlier)

Hard safety properties (mirroring src/research/prospective/price_discovery.py):
- Movement requires the SAME bookmaker+market+selection+line. Cross-book and
  cross-line comparisons are refused (never fabricated).
- Line changes are recorded SEPARATELY (``line_changes``); a changed line does
  not produce a price transition.
- Predictor fields (fundamental disagreement, lineup surprise, availability,
  referee) may only reflect information available at the EARLIER endpoint.
  They are currently NULL/UNKNOWN because no fundamental/lineup capture is
  wired to the store yet; they are never fabricated to a value.
- De-vig uses the existing engine on the stored decimal odds; odds are never
  mutated. No best-price selection across books.
- Serialization is deterministic (rows sorted by a stable key), so re-running
  on the same store yields byte-identical output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

from src.research.observation.model import MISSING
from src.research.prospective.odds_capture import market_over_probability
from src.research.prospective.storage import CaptureStore
from src.research.prospective.vintages import ProspectiveVintage

_EPS = 1e-9


def _logit(p: Optional[float]) -> Optional[float]:
    if p is None or not (0.0 < p < 1.0):
        return None
    return math.log(p / (1.0 - p))


class DevigMethod(str, Enum):
    MULTIPLICATIVE = "multiplicative"
    SHIN = "shin"


# ---------------------------------------------------------------------------
# Preregistered sample gate (documented BEFORE inspecting predictive results).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReadinessGate:
    """Preregistered minimum support before ANY formal study is promoted.

    These thresholds are fixed in advance (mission section 20) and MUST NOT be
    lowered after seeing results. ``met`` is a pure function of the observed
    counts vs these thresholds.
    """

    min_captured_fixtures: int = 300
    min_same_book_late_final: int = 200
    min_confirmed_lineups: int = 150
    min_pre_post_lineup_pairs: int = 100

    def evaluate(
        self,
        *,
        captured_fixtures: int,
        same_book_late_final: int,
        confirmed_lineups: int,
        pre_post_lineup_pairs: int,
    ) -> dict:
        checks = {
            "captured_fixtures": (captured_fixtures, self.min_captured_fixtures),
            "same_book_late_final": (same_book_late_final, self.min_same_book_late_final),
            "confirmed_lineups": (confirmed_lineups, self.min_confirmed_lineups),
            "pre_post_lineup_pairs": (pre_post_lineup_pairs, self.min_pre_post_lineup_pairs),
        }
        detail = {k: {"observed": obs, "required": req, "met": obs >= req}
                  for k, (obs, req) in checks.items()}
        return {"met": all(d["met"] for d in detail.values()), "checks": detail}


#: The single canonical gate instance used by the study + reports.
PROSPECTIVE_GATE = ReadinessGate()


# ---------------------------------------------------------------------------
# Snapshot / transition rows
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DevigSnapshot:
    """A de-vigged fair probability for one KEY at one observed_at.

    ``p_fair`` is the no-vig probability of ``selection`` computed from the
    over/under pair present at this snapshot. ``vintage`` is derived from the
    ACTUAL seconds-to-kickoff (never fabricated); ``None`` when the age falls
    outside every vintage window.
    """

    fixture_id: str
    league: Optional[str]
    kickoff_ts: float
    bookmaker: str
    market: str
    selection: str
    line: Optional[float]
    observed_at: float
    seconds_to_kickoff: float
    p_fair: float
    vintage: Optional[ProspectiveVintage]


@dataclass(frozen=True)
class Transition:
    """A same-key market movement between two vintage endpoints.

    ``delta_market_logit`` = logit(p_later) - logit(p_earlier). Predictor
    fields are attached from the EARLIER endpoint only (currently NULL).
    """

    fixture_id: str
    league: Optional[str]
    kickoff_ts: float
    bookmaker: str
    market: str
    selection: str
    line: Optional[float]
    earlier_vintage: str
    later_vintage: str
    earlier_observed_at: float
    later_observed_at: float
    p_market_earlier: float
    p_market_later: float
    delta_market_logit: float
    # --- predictor placeholders (never fabricated; NULL until wired) ---
    p_fundamental_earlier: Optional[float] = None
    fundamental_market_disagreement: Optional[float] = None
    lineup_observed: bool = False
    lineup_surprise_features: dict = field(default_factory=dict)
    availability_features: dict = field(default_factory=dict)
    referee_available: bool = False
    outcome: Optional[bool] = None

    def to_dict(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "competition_id": self.league,
            "kickoff": self.kickoff_ts,
            "bookmaker": self.bookmaker,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "earlier_vintage": self.earlier_vintage,
            "later_vintage": self.later_vintage,
            "earlier_observed_at": self.earlier_observed_at,
            "later_observed_at": self.later_observed_at,
            "p_market_earlier": self.p_market_earlier,
            "p_market_later": self.p_market_later,
            "delta_market_logit": self.delta_market_logit,
            "p_fundamental_earlier": self.p_fundamental_earlier,
            "fundamental_market_disagreement": self.fundamental_market_disagreement,
            "lineup_observed": self.lineup_observed,
            "lineup_surprise_features": self.lineup_surprise_features,
            "availability_features": self.availability_features,
            "referee_available": self.referee_available,
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class LineChange:
    """A same-book/market/selection OFFERED-LINE change (kept out of movement)."""

    fixture_id: str
    bookmaker: str
    market: str
    selection: str
    earlier_line: Optional[float]
    later_line: Optional[float]
    earlier_observed_at: float
    later_observed_at: float

    def to_dict(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "bookmaker": self.bookmaker,
            "market": self.market,
            "selection": self.selection,
            "earlier_line": self.earlier_line,
            "later_line": self.later_line,
            "earlier_observed_at": self.earlier_observed_at,
            "later_observed_at": self.later_observed_at,
        }


#: Ordered vintage transitions the study evaluates (mission section 15).
VINTAGE_TRANSITIONS: tuple[tuple[ProspectiveVintage, ProspectiveVintage], ...] = (
    (ProspectiveVintage.EARLY, ProspectiveVintage.MID),
    (ProspectiveVintage.MID, ProspectiveVintage.LATE),
    (ProspectiveVintage.LATE, ProspectiveVintage.FINAL),
    (ProspectiveVintage.EARLY, ProspectiveVintage.FINAL),
)


@dataclass
class PriceDiscoveryDataset:
    """The built dataset + descriptive coverage counts (deterministic)."""

    transitions: list[Transition]
    line_changes: list[LineChange]
    n_snapshots: int
    n_fixtures: int
    n_keys: int
    devig_method: str
    #: per-vintage snapshot counts (from actual seconds-to-kickoff)
    vintage_snapshot_counts: dict
    #: transitions grouped "EARLY->MID" -> count
    transition_counts: dict

    def to_dict(self) -> dict:
        return {
            "devig_method": self.devig_method,
            "n_snapshots": self.n_snapshots,
            "n_fixtures": self.n_fixtures,
            "n_keys": self.n_keys,
            "vintage_snapshot_counts": self.vintage_snapshot_counts,
            "transition_counts": self.transition_counts,
            "n_transitions": len(self.transitions),
            "n_line_changes": len(self.line_changes),
        }


# ---------------------------------------------------------------------------
# Concept parsing
# ---------------------------------------------------------------------------


def _parse_concept(concept: str) -> Optional[tuple[str, str, Optional[float], str]]:
    """Parse ``odds:<market>:<selection>:<line>:<bookmaker>``.

    Returns (market, selection, line, bookmaker) or None if not an odds concept.
    ``line`` may be an empty segment (None) or a float-like string. The
    bookmaker is always the LAST segment; the line is the segment before it.
    """
    parts = concept.split(":")
    if len(parts) < 4 or parts[0] != "odds":
        return None
    bookmaker = parts[-1]
    market = parts[1]
    selection = parts[2]
    # Everything between selection and bookmaker is the (possibly empty) line.
    line_seg = ":".join(parts[3:-1]) if len(parts) > 4 else ""
    line: Optional[float]
    if line_seg == "":
        line = None
    else:
        try:
            line = float(line_seg)
        except ValueError:
            line = None
    return market, selection, line, bookmaker


def _assign_vintage(seconds_to_kickoff: float) -> Optional[ProspectiveVintage]:
    """Assign a vintage from actual age using the declared tolerances.

    Nearest target whose NEAR tolerance contains the age wins. Ages outside
    every window map to None (retained as a snapshot, but not a vintage anchor).
    Deterministic and pre-registered (uses vintage_quality tolerances).
    """
    from src.research.prospective.vintage_quality import DEFAULT_TOLERANCES

    if seconds_to_kickoff <= 0:
        return None  # post-kickoff never anchors a pre-match vintage
    best: Optional[ProspectiveVintage] = None
    best_err = float("inf")
    for v, tol in DEFAULT_TOLERANCES.items():
        err = abs(seconds_to_kickoff - v.offset_seconds)
        if err <= tol.near_target and err < best_err:
            best = v
            best_err = err
    return best


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _snapshots_from_store(
    store: CaptureStore, *, devig_method: str
) -> list[DevigSnapshot]:
    """Build de-vigged snapshots from the store's over/under odds records.

    Groups the two selections (over/under) at each (fixture, book, market,
    line, observed_at) so the pair can be de-vigged together. Selections
    without a matching opposite side at the same instant are skipped (a fair
    probability needs both sides; never fabricated).
    """
    # key: (fixture, book, market, line, observed_at) -> {selection: (odds, ko, league)}
    pairs: dict[tuple, dict] = {}
    for rec in store.read_all():
        if rec.value is MISSING or rec.value is None:
            continue
        parsed = _parse_concept(rec.concept)
        if parsed is None:
            continue
        market, selection, line, bookmaker = parsed
        if selection not in ("over", "under"):
            continue
        try:
            odds = float(rec.value)
        except (TypeError, ValueError):
            continue
        ko = rec.event_time
        if ko is None:
            continue  # cannot place on the pre-kickoff timeline
        k = (rec.canonical_entity_id, bookmaker, market, line, round(rec.observed_at, 3))
        slot = pairs.setdefault(k, {"kickoff": ko, "observed_at": rec.observed_at})
        slot[selection] = odds

    snapshots: list[DevigSnapshot] = []
    for (fixture, bookmaker, market, line, _obs_round), slot in pairs.items():
        over = slot.get("over")
        under = slot.get("under")
        if over is None or under is None:
            continue
        try:
            p_over = market_over_probability(over, under, method=devig_method)
        except Exception:
            continue
        ko = slot["kickoff"]
        observed_at = slot["observed_at"]
        stk = ko - observed_at
        vintage = _assign_vintage(stk)
        for selection, p_fair in (("over", p_over), ("under", 1.0 - p_over)):
            if not (0.0 < p_fair < 1.0):
                continue
            snapshots.append(
                DevigSnapshot(
                    fixture_id=fixture,
                    league=None,
                    kickoff_ts=float(ko),
                    bookmaker=bookmaker,
                    market=market,
                    selection=selection,
                    line=line,
                    observed_at=float(observed_at),
                    seconds_to_kickoff=float(stk),
                    p_fair=float(p_fair),
                    vintage=vintage,
                )
            )
    # Deterministic order.
    snapshots.sort(key=lambda s: (s.fixture_id, s.bookmaker, s.market, s.selection,
                                  _line_sort(s.line), s.observed_at))
    return snapshots


def _line_sort(line: Optional[float]) -> float:
    return float("-inf") if line is None else line


def _key(s: DevigSnapshot) -> tuple:
    return (s.fixture_id, s.bookmaker, s.market, s.selection, s.line)


def _nearest_to_vintage(
    snaps: list[DevigSnapshot], vintage: ProspectiveVintage
) -> Optional[DevigSnapshot]:
    """Pick the pre-kickoff snapshot whose age is nearest this vintage target,
    among snapshots actually assigned to that vintage window."""
    cand = [s for s in snaps if s.vintage == vintage]
    if not cand:
        return None
    target = vintage.offset_seconds
    return min(cand, key=lambda s: abs(s.seconds_to_kickoff - target))


def build_dataset(
    store: CaptureStore,
    *,
    devig_method: str = DevigMethod.MULTIPLICATIVE.value,
) -> PriceDiscoveryDataset:
    """Build the deterministic price-discovery dataset from a capture store.

    Only genuine same-key vintage transitions become rows. Line changes on the
    same book/market/selection are recorded separately and never turned into a
    price movement.
    """
    snapshots = _snapshots_from_store(store, devig_method=devig_method)

    # Group by KEY (book/market/selection/line) within a fixture.
    by_key: dict[tuple, list[DevigSnapshot]] = {}
    for s in snapshots:
        by_key.setdefault(_key(s), []).append(s)

    transitions: list[Transition] = []
    for key, snaps in by_key.items():
        snaps.sort(key=lambda s: s.observed_at)
        for earlier_v, later_v in VINTAGE_TRANSITIONS:
            e = _nearest_to_vintage(snaps, earlier_v)
            l = _nearest_to_vintage(snaps, later_v)
            if e is None or l is None:
                continue
            if e.observed_at >= l.observed_at:
                continue  # later endpoint must be strictly later in time
            le, ll = _logit(e.p_fair), _logit(l.p_fair)
            if le is None or ll is None:
                continue
            transitions.append(
                Transition(
                    fixture_id=e.fixture_id,
                    league=e.league,
                    kickoff_ts=e.kickoff_ts,
                    bookmaker=e.bookmaker,
                    market=e.market,
                    selection=e.selection,
                    line=e.line,
                    earlier_vintage=earlier_v.value,
                    later_vintage=later_v.value,
                    earlier_observed_at=e.observed_at,
                    later_observed_at=l.observed_at,
                    p_market_earlier=e.p_fair,
                    p_market_later=l.p_fair,
                    delta_market_logit=ll - le,
                )
            )

    # Line changes: same (fixture, book, market, selection), differing line
    # between consecutive-in-time snapshots. Kept SEPARATE from movement.
    line_changes = _detect_line_changes(snapshots)

    # Deterministic order.
    transitions.sort(key=lambda t: (t.fixture_id, t.bookmaker, t.market, t.selection,
                                    _line_sort(t.line), t.earlier_vintage, t.later_vintage))

    vintage_counts: dict[str, int] = {v.value: 0 for v in ProspectiveVintage}
    vintage_counts["UNASSIGNED"] = 0
    for s in snapshots:
        vintage_counts[s.vintage.value if s.vintage else "UNASSIGNED"] += 1

    transition_counts: dict[str, int] = {}
    for t in transitions:
        label = f"{t.earlier_vintage}->{t.later_vintage}"
        transition_counts[label] = transition_counts.get(label, 0) + 1

    return PriceDiscoveryDataset(
        transitions=transitions,
        line_changes=line_changes,
        n_snapshots=len(snapshots),
        n_fixtures=len({s.fixture_id for s in snapshots}),
        n_keys=len(by_key),
        devig_method=devig_method,
        vintage_snapshot_counts=vintage_counts,
        transition_counts=transition_counts,
    )


def _detect_line_changes(snapshots: list[DevigSnapshot]) -> list[LineChange]:
    """Detect offered-line changes per (fixture, book, market, selection) OVER TIME.

    A market offers MANY lines simultaneously (over 0.5, 1.5, 2.5, ...). Those
    coexisting lines are NOT a "line change". A genuine line change is when, at
    a LATER observed_at, the set of offered lines differs from the set offered
    at an EARLIER observed_at for the same book/market/selection. We therefore
    compare the offered-line SET between consecutive distinct snapshot times and
    record the symmetric difference. This never contributes to price movement
    (which requires identical lines at both endpoints).
    """
    # (fixture, book, market, selection) -> observed_at -> set(lines)
    grouped: dict[tuple, dict[float, set]] = {}
    for s in snapshots:
        g = grouped.setdefault((s.fixture_id, s.bookmaker, s.market, s.selection), {})
        g.setdefault(s.observed_at, set()).add(s.line)

    out: list[LineChange] = []
    for (fixture, book, market, selection), by_time in grouped.items():
        times = sorted(by_time)
        for earlier_t, later_t in zip(times, times[1:]):
            earlier_lines = by_time[earlier_t]
            later_lines = by_time[later_t]
            if earlier_lines == later_lines:
                continue
            for ln in sorted(later_lines - earlier_lines, key=_line_sort):
                out.append(LineChange(
                    fixture_id=fixture, bookmaker=book, market=market, selection=selection,
                    earlier_line=None, later_line=ln,
                    earlier_observed_at=earlier_t, later_observed_at=later_t,
                ))
            for ln in sorted(earlier_lines - later_lines, key=_line_sort):
                out.append(LineChange(
                    fixture_id=fixture, bookmaker=book, market=market, selection=selection,
                    earlier_line=ln, later_line=None,
                    earlier_observed_at=earlier_t, later_observed_at=later_t,
                ))
    out.sort(key=lambda c: (c.fixture_id, c.bookmaker, c.market, c.selection,
                            c.earlier_observed_at, _line_sort(c.earlier_line),
                            _line_sort(c.later_line)))
    return out


def load_default_store(capture_root: Path = Path("data/prospective")) -> CaptureStore:
    return CaptureStore(path=Path(capture_root) / "captures.jsonl.gz")
