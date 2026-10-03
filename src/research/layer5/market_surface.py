"""QFE V2 Layer 5 deterministic market-surface construction.

Outcome-blind. This module may consume timestamped bookmaker prices but never
football outcomes and never modifies the frozen Layer 4 p_model.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import mean
from typing import Iterable, Optional

from src.research.layer5.protocol import protocol_active
from src.research.reconciliation.devig import devig_multiplicative, devig_shin


@dataclass(frozen=True, slots=True)
class TwoWayQuote:
    fixture_id: str
    market_key: str
    bookmaker: str
    line: float
    over_odds: float
    under_odds: float
    observed_at: float
    bundle_id: str


@dataclass(frozen=True, slots=True)
class MarketPoint:
    line: float
    over_odds: float
    under_odds: float
    overround: float
    p_over_raw: float
    p_over_shin: float
    p_over_clean: float
    isotonic_adjustment: float


@dataclass(frozen=True, slots=True)
class MarketSurface:
    status: str
    reason: Optional[str]
    fixture_id: str
    market_key: str
    bookmaker: str
    prediction_cutoff: float
    observed_at_min: float
    observed_at_max: float
    bundle_id: str
    points: tuple[MarketPoint, ...]
    max_abs_repair: float
    mean_abs_repair: float

    @property
    def is_ok(self) -> bool:
        return self.status == "OK"


def _abstain(
    reason: str,
    *,
    fixture_id: str = "",
    market_key: str = "",
    bookmaker: str = "",
    prediction_cutoff: float = 0.0,
    observed_at_min: float = 0.0,
    observed_at_max: float = 0.0,
    bundle_id: str = "",
) -> MarketSurface:
    return MarketSurface(
        status="ABSTAIN",
        reason=reason,
        fixture_id=fixture_id,
        market_key=market_key,
        bookmaker=bookmaker,
        prediction_cutoff=prediction_cutoff,
        observed_at_min=observed_at_min,
        observed_at_max=observed_at_max,
        bundle_id=bundle_id,
        points=(),
        max_abs_repair=0.0,
        mean_abs_repair=0.0,
    )


def isotonic_nonincreasing(values: Iterable[float]) -> tuple[float, ...]:
    """Equal-weight PAV projection onto y[0] >= y[1] >= ... .

    Implemented locally to keep the market-surface contract deterministic and
    independent of optional ML packages.
    """
    raw = [float(v) for v in values]
    if any(not isfinite(v) for v in raw):
        raise ValueError("isotonic input must be finite")
    # Project -y onto the non-decreasing cone with classic pooled adjacent
    # violators, then negate.
    blocks: list[list[float | int]] = []
    for index, value in enumerate(raw):
        blocks.append([-value, 1, index, index])
        while len(blocks) >= 2:
            left, right = blocks[-2], blocks[-1]
            left_mean = float(left[0]) / int(left[1])
            right_mean = float(right[0]) / int(right[1])
            if left_mean <= right_mean:
                break
            merged = [
                float(left[0]) + float(right[0]),
                int(left[1]) + int(right[1]),
                int(left[2]),
                int(right[3]),
            ]
            blocks[-2:] = [merged]
    out = [0.0] * len(raw)
    for total, count, start, end in blocks:
        value = -(float(total) / int(count))
        for index in range(int(start), int(end) + 1):
            out[index] = value
    return tuple(out)


def _longest_adjacent_segment(points: list[MarketPoint]) -> list[MarketPoint]:
    if not points:
        return []
    points = sorted(points, key=lambda p: p.line)
    segments: list[list[MarketPoint]] = [[points[0]]]
    for point in points[1:]:
        if abs(point.line - segments[-1][-1].line - 1.0) <= 1e-9:
            segments[-1].append(point)
        else:
            segments.append([point])
    max_len = max(len(s) for s in segments)
    candidates = [s for s in segments if len(s) == max_len]

    def centrality(segment: list[MarketPoint]) -> tuple[float, float]:
        best = min(abs(p.p_over_raw - 0.5) for p in segment)
        return (best, segment[0].line)

    return min(candidates, key=centrality)


def devig_quote(quote: TwoWayQuote) -> MarketPoint:
    protocol = protocol_active()
    nv = protocol["no_vig"]
    if not (
        quote.over_odds > nv["decimal_odds_strictly_greater_than"]
        and quote.under_odds > nv["decimal_odds_strictly_greater_than"]
    ):
        raise ValueError("decimal odds outside preregistered bounds")
    primary = devig_multiplicative({"OVER": quote.over_odds, "UNDER": quote.under_odds})
    if not (
        nv["raw_two_way_implied_sum_min"]
        <= primary.overround
        <= nv["raw_two_way_implied_sum_max"]
    ):
        raise ValueError("overround outside preregistered bounds")
    shin = devig_shin({"OVER": quote.over_odds, "UNDER": quote.under_odds})
    return MarketPoint(
        line=float(quote.line),
        over_odds=float(quote.over_odds),
        under_odds=float(quote.under_odds),
        overround=float(primary.overround),
        p_over_raw=float(primary.fair_probabilities["OVER"]),
        p_over_shin=float(shin.fair_probabilities["OVER"]),
        p_over_clean=float(primary.fair_probabilities["OVER"]),
        isotonic_adjustment=0.0,
    )


def select_latest_complete_bundle(
    quotes: Iterable[TwoWayQuote],
    *,
    prediction_cutoff: float,
    bookmaker: str,
    market_key: str,
    minimum_adjacent_lines: int,
) -> tuple[TwoWayQuote, ...]:
    """Select the latest structurally complete preregistered bookmaker bundle.

    Future and stale bundles are ineligible. Among structurally complete
    in-window bundles, only recency decides. Price attractiveness, overround,
    model disagreement and outcomes never participate in bundle selection.
    Once selected, price/overround/coherence quality is evaluated by the
    surface builder; we do not fall back to an older bundle because the latest
    complete one produces an inconvenient disagreement.
    """
    h = protocol_active()["market_horizon"]
    eligible = [
        q for q in quotes
        if q.bookmaker == bookmaker
        and q.market_key == market_key
        and q.observed_at <= prediction_cutoff
        and prediction_cutoff - q.observed_at <= h["max_snapshot_age_seconds"]
    ]
    by_bundle: dict[str, list[TwoWayQuote]] = {}
    for quote in eligible:
        by_bundle.setdefault(quote.bundle_id, []).append(quote)

    candidates: list[tuple[float, str, tuple[TwoWayQuote, ...]]] = []
    for bundle_id, rows in by_bundle.items():
        if not rows:
            continue
        observed = [q.observed_at for q in rows]
        if max(observed) - min(observed) > h["max_intra_surface_skew_seconds"]:
            continue
        # Structural completeness only: unique lines and a sufficiently long
        # adjacent run. Do not inspect prices beyond their presence here.
        lines = sorted({float(q.line) for q in rows})
        if len(lines) != len(rows):
            continue
        longest = 0
        current = 0
        previous = None
        for line in lines:
            if previous is None or abs(line - previous - 1.0) <= 1e-9:
                current += 1
            else:
                current = 1
            longest = max(longest, current)
            previous = line
        if longest < minimum_adjacent_lines:
            continue
        candidates.append((max(observed), bundle_id, tuple(rows)))

    if not candidates:
        return ()
    # Latest observation wins; deterministic bundle-id tie break only.
    _, _, selected = max(candidates, key=lambda row: (row[0], row[1]))
    return tuple(sorted(selected, key=lambda q: q.line))


def select_benchmark_bundle(
    quotes: Iterable[TwoWayQuote],
    *,
    prediction_cutoff: float,
    market_key: str,
    minimum_adjacent_lines: int,
) -> tuple[TwoWayQuote, ...]:
    """Select bookmaker then bundle without inspecting price attractiveness.

    The first hierarchy bookmaker with a structurally complete in-window bundle
    wins. Once chosen, callers MUST evaluate that exact bundle and abstain on
    price/coherence failure; they may not fall through to another bookmaker.
    """
    hierarchy = tuple(protocol_active()["bookmaker_selection"]["hierarchy"])
    rows = list(quotes)
    for bookmaker in hierarchy:
        chosen = select_latest_complete_bundle(
            rows,
            prediction_cutoff=prediction_cutoff,
            bookmaker=bookmaker,
            market_key=market_key,
            minimum_adjacent_lines=minimum_adjacent_lines,
        )
        if chosen:
            return chosen
    return ()


def build_market_point(
    quote: TwoWayQuote,
    *,
    prediction_cutoff: float,
) -> MarketSurface:
    """Build a single-line market comparator (goals total 2.5 in V1)."""
    p = protocol_active()
    h = p["market_horizon"]
    if quote.observed_at > prediction_cutoff:
        return _abstain(
            "MARKET_HORIZON_MISSING",
            fixture_id=quote.fixture_id,
            market_key=quote.market_key,
            bookmaker=quote.bookmaker,
            prediction_cutoff=prediction_cutoff,
            observed_at_min=quote.observed_at,
            observed_at_max=quote.observed_at,
            bundle_id=quote.bundle_id,
        )
    if prediction_cutoff - quote.observed_at > h["max_snapshot_age_seconds"]:
        return _abstain(
            "MARKET_SNAPSHOT_TOO_OLD",
            fixture_id=quote.fixture_id,
            market_key=quote.market_key,
            bookmaker=quote.bookmaker,
            prediction_cutoff=prediction_cutoff,
            observed_at_min=quote.observed_at,
            observed_at_max=quote.observed_at,
            bundle_id=quote.bundle_id,
        )
    try:
        point = devig_quote(quote)
    except ValueError as exc:
        reason = (
            "OVERROUND_OUT_OF_BOUNDS"
            if "overround" in str(exc)
            else "TWO_SIDED_QUOTE_MISSING"
        )
        return _abstain(
            reason,
            fixture_id=quote.fixture_id,
            market_key=quote.market_key,
            bookmaker=quote.bookmaker,
            prediction_cutoff=prediction_cutoff,
            observed_at_min=quote.observed_at,
            observed_at_max=quote.observed_at,
            bundle_id=quote.bundle_id,
        )
    return MarketSurface(
        status="OK",
        reason=None,
        fixture_id=quote.fixture_id,
        market_key=quote.market_key,
        bookmaker=quote.bookmaker,
        prediction_cutoff=prediction_cutoff,
        observed_at_min=quote.observed_at,
        observed_at_max=quote.observed_at,
        bundle_id=quote.bundle_id,
        points=(point,),
        max_abs_repair=0.0,
        mean_abs_repair=0.0,
    )


def build_market_surface(
    quotes: Iterable[TwoWayQuote],
    *,
    prediction_cutoff: float,
) -> MarketSurface:
    """Build one same-bookmaker, same-bundle coherent multi-line market CDF."""
    protocol = protocol_active()
    h = protocol["market_horizon"]
    s = protocol["market_surface"]
    rows = list(quotes)
    if not rows:
        return _abstain("MARKET_HORIZON_MISSING", prediction_cutoff=prediction_cutoff)

    fixture_ids = {q.fixture_id for q in rows}
    markets = {q.market_key for q in rows}
    books = {q.bookmaker for q in rows}
    bundles = {q.bundle_id for q in rows}
    if len(fixture_ids) != 1 or len(markets) != 1:
        raise ValueError("surface rows must share fixture and market key")
    fixture_id = next(iter(fixture_ids))
    market_key = next(iter(markets))
    bookmaker = next(iter(books)) if len(books) == 1 else ""
    bundle_id = next(iter(bundles)) if len(bundles) == 1 else ""
    observed = [q.observed_at for q in rows]
    common = dict(
        fixture_id=fixture_id,
        market_key=market_key,
        bookmaker=bookmaker,
        prediction_cutoff=prediction_cutoff,
        observed_at_min=min(observed),
        observed_at_max=max(observed),
        bundle_id=bundle_id,
    )
    if len(books) != 1:
        return _abstain("CROSS_BOOK_BLEND_FORBIDDEN", **common)
    if len(bundles) != 1:
        return _abstain("MARKET_SURFACE_TIME_SKEW", **common)
    if any(ts > prediction_cutoff for ts in observed):
        return _abstain("MARKET_HORIZON_MISSING", **common)
    if prediction_cutoff - min(observed) > h["max_snapshot_age_seconds"]:
        return _abstain("MARKET_SNAPSHOT_TOO_OLD", **common)
    if max(observed) - min(observed) > h["max_intra_surface_skew_seconds"]:
        return _abstain("MARKET_SURFACE_TIME_SKEW", **common)

    line_seen: set[float] = set()
    points: list[MarketPoint] = []
    try:
        for q in rows:
            if q.line in line_seen:
                raise ValueError("duplicate line in market bundle")
            line_seen.add(q.line)
            points.append(devig_quote(q))
    except ValueError as exc:
        reason = (
            "OVERROUND_OUT_OF_BOUNDS"
            if "overround" in str(exc)
            else "TWO_SIDED_QUOTE_MISSING"
        )
        return _abstain(reason, **common)

    segment = _longest_adjacent_segment(points)
    if len(segment) < s["minimum_adjacent_lines"]:
        return _abstain("SURFACE_TOO_SPARSE", **common)
    segment = sorted(segment, key=lambda p: p.line)
    clean = isotonic_nonincreasing(p.p_over_raw for p in segment)
    rebuilt = tuple(
        MarketPoint(
            line=p.line,
            over_odds=p.over_odds,
            under_odds=p.under_odds,
            overround=p.overround,
            p_over_raw=p.p_over_raw,
            p_over_shin=p.p_over_shin,
            p_over_clean=float(c),
            isotonic_adjustment=float(c - p.p_over_raw),
        )
        for p, c in zip(segment, clean, strict=True)
    )
    abs_repairs = [abs(p.isotonic_adjustment) for p in rebuilt]
    max_repair = max(abs_repairs, default=0.0)
    mean_repair = mean(abs_repairs) if abs_repairs else 0.0
    if (
        max_repair > s["max_abs_isotonic_adjustment"] + 1e-12
        or mean_repair > s["max_mean_abs_isotonic_adjustment"] + 1e-12
    ):
        return _abstain("MARKET_SURFACE_INCOHERENT", **common)

    return MarketSurface(
        status="OK",
        reason=None,
        points=rebuilt,
        max_abs_repair=max_repair,
        mean_abs_repair=mean_repair,
        **common,
    )
