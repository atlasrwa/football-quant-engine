"""Enrich canonical model theses with thesis-relative close + preferred-side
settlement, and build read-only reconciliation reports.

All inputs are canonical persisted evidence read READ-ONLY:
  * theses           -> projected from shadow_residuals (model_thesis.py)
  * genuine close     -> resolve_genuine_close over the capture store
  * settlement outcome-> shadow_settlements.jsonl, PREFERRED side only

Never mutates any ledger. Close direction and settlement are attached AFTER the
frozen preferred side is chosen, so hindsight never influences side selection.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Optional

from src.research.prospective.model_thesis import (
    CloseDirection,
    ModelThesis,
    NEUTRAL_EPS,
    ThesisResult,
)
from src.research.prospective.odds_capture import (
    CapturedPrice,
    CloseStatus,
    market_over_probability,
    resolve_genuine_close,
)


def build_close_direction(
    thesis: ModelThesis,
    *,
    keyed_snapshots: dict,
    key_kickoff: dict,
    devig_method: str = "multiplicative",
) -> ModelThesis:
    """Attach thesis-relative genuine-close direction (canonical resolver).

    Uses the genuine close of BOTH sides at the preferred side's exact key to
    compute the de-vigged close probability of the preferred side, then compares
    it to the frozen ``p_market_preferred``:

      close_pref - frozen_pref  > 0  -> market moved toward the model's side
                                        (FINAL_TOWARD_MODEL)
                                 < 0  -> FINAL_AWAY_FROM_MODEL
                            ~ 0        -> FINAL_FLAT
      no genuine close for either leg -> NO_CLOSE

    Never uses intermediate movement ticks; the genuine close is the primary
    market verdict.
    """
    fx, book, market, line = thesis.fixture_id, thesis.bookmaker, thesis.market, thesis.line
    over_key = (fx, book, market, "over", line)
    under_key = (fx, book, market, "under", line)
    over_snaps = keyed_snapshots.get(over_key)
    under_snaps = keyed_snapshots.get(under_key)
    if not over_snaps or not under_snaps:
        return replace(thesis, close_direction=CloseDirection.NO_CLOSE.value)
    ro = resolve_genuine_close(
        over_snaps, kickoff_ts=key_kickoff.get(over_key), bookmaker=book,
        market=market, selection="over", line=line,
    )
    ru = resolve_genuine_close(
        under_snaps, kickoff_ts=key_kickoff.get(under_key), bookmaker=book,
        market=market, selection="under", line=line,
    )
    if ro.status != CloseStatus.GENUINE_CLOSE or ru.status != CloseStatus.GENUINE_CLOSE:
        return replace(thesis, close_direction=CloseDirection.NO_CLOSE.value)
    p_over_close = market_over_probability(
        ro.close.price.decimal_odds, ru.close.price.decimal_odds, method=devig_method
    )
    close_pref = p_over_close if thesis.preferred_selection == "over" else 1.0 - p_over_close
    delta = close_pref - thesis.p_market_preferred
    if abs(delta) <= NEUTRAL_EPS:
        direction = CloseDirection.FINAL_FLAT
    elif delta > 0:
        direction = CloseDirection.FINAL_TOWARD_MODEL
    else:
        direction = CloseDirection.FINAL_AWAY_FROM_MODEL
    return replace(
        thesis,
        close_p_market_preferred=float(close_pref),
        close_delta_pp=float(delta * 100.0),
        close_direction=direction.value,
    )


def attach_settlement(thesis: ModelThesis, *, settlement_by_shadow: dict) -> ModelThesis:
    """Attach the PREFERRED side's settlement outcome only.

    Looks up the settlement keyed by the PREFERRED shadow id. The opposite
    side's settlement is never consulted — a thesis has at most one preferred
    outcome (WIN/LOSS/PUSH/VOID) or PENDING.
    """
    st = settlement_by_shadow.get(thesis.preferred_shadow_id)
    if not st:
        return replace(thesis, settlement_outcome="PENDING")
    return replace(
        thesis,
        settlement_outcome=st.get("settlement_outcome", "PENDING"),
        result_statistic_value=st.get("result_statistic_value"),
    )


def build_capture_index(store) -> tuple[dict, dict]:
    """Group capture-store odds snapshots by exact key for close resolution."""
    from src.research.observation.model import MISSING
    from src.research.prospective.genuine_close_metrics import (
        _parse_odds_concept,
        _semantics_from_raw_status,
    )

    keyed: dict = defaultdict(list)
    kickoff: dict = {}
    for rec in store.read_all():
        concept = getattr(rec, "concept", None)
        if not isinstance(concept, str):
            continue
        parsed = _parse_odds_concept(concept)
        if parsed is None:
            continue
        market, selection, line, bookmaker = parsed
        v = rec.value
        if v is MISSING or v is None:
            continue
        try:
            od = float(v)
        except (TypeError, ValueError):
            continue
        key = (rec.canonical_entity_id, bookmaker, market, selection, line)
        kickoff.setdefault(key, rec.event_time)
        keyed[key].append(
            CapturedPrice(
                bookmaker=bookmaker, market=market, selection=selection, line=line,
                decimal_odds=od, semantics=_semantics_from_raw_status(rec.raw_status),
                observed_at=rec.observed_at, provider_payload_hash=getattr(rec, "raw_payload_hash", ""),
            )
        )
    return keyed, kickoff


def enrich_theses(
    theses: Iterable[ModelThesis],
    *,
    capture_store,
    settlement_by_shadow: dict,
) -> list[ModelThesis]:
    """Attach close direction + preferred-side settlement to each thesis."""
    keyed, kickoff = build_capture_index(capture_store)
    out = []
    for t in theses:
        t = build_close_direction(t, keyed_snapshots=keyed, key_kickoff=kickoff)
        t = attach_settlement(t, settlement_by_shadow=settlement_by_shadow)
        out.append(t)
    return out


# ── edge buckets (descriptive; never called profitable/significant) ─────────
EDGE_BUCKETS = (
    ("0-1pp", 0.0, 1.0),
    ("1-2.5pp", 1.0, 2.5),
    ("2.5-5pp", 2.5, 5.0),
    ("5-10pp", 5.0, 10.0),
    (">10pp", 10.0, float("inf")),
)


def edge_bucket(edge_pp: float) -> str:
    a = abs(edge_pp)
    for name, lo, hi in EDGE_BUCKETS:
        if lo <= a < hi:
            return name
    return ">10pp"


HORIZON_BUCKETS = (
    ("<1h", 0, 3600),
    ("1-3h", 3600, 3 * 3600),
    ("3-6h", 3 * 3600, 6 * 3600),
    ("6-12h", 6 * 3600, 12 * 3600),
    (">12h", 12 * 3600, float("inf")),
)


def horizon_bucket(thesis: ModelThesis) -> str:
    if thesis.kickoff_ts is None:
        return "unknown"
    d = thesis.kickoff_ts - thesis.information_cutoff
    for name, lo, hi in HORIZON_BUCKETS:
        if lo <= d < hi:
            return name
    return ">12h"


def unique_fixture_market_key(t: ModelThesis) -> tuple:
    """Aggregation key for the deduplicated fixture-market-line view.

    Drops bookmaker and cutoff so several bookmakers observing the same
    fixture-market-line count the football outcome ONCE.
    """
    return (t.fixture_id, t.market, t.line)
