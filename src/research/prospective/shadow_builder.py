"""Build eligible SHADOW_RESIDUAL candidates from ALREADY-PERSISTED state.

This is the integration core. It performs ZERO provider calls and does NOT run
any model: it joins

    * committed forecasts   (BroadcastLedger.records() -> FORECAST_COMMITTED), and
    * own market snapshots   (CaptureStore odds captures),

into frozen shadow candidates via
:func:`src.research.prospective.shadow_residual.build_shadow_residual`.

Only the legitimate intersection is used: a candidate is produced solely for a
fixture that has BOTH a committed forecast and prospective odds captures, with
matching canonical identity (never a display-name join).

PIT cutoff ``T`` per (fixture, market, selection, line, bookmaker) key:
    T = the observed_at of the LATEST own paired snapshot with
        observed_at <= horizon AND observed_at >= forecast.generated_at
        AND observed_at < kickoff.
The horizon defaults to kickoff (all pre-kickoff snapshots eligible); callers
may pass an earlier ``as_of`` to freeze a strictly earlier vintage. The market
snapshot used is the latest eligible OWN snapshot at/before T — consistent with
existing PIT semantics; provider ``last_seen`` is never used as timing evidence.

Model market keys map to captured odds market keys:
    goals   -> total_goals
    corners -> match_corners
    cards   -> total_cards
(These mirror the FORECAST payload markets that have an over/under line; ``btts``
has no line and no paired over/under total in the capture concept space, so it
is skipped rather than guessed.)
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from src.research.observation.model import MISSING
from src.research.prospective.shadow_residual import (
    ForecastLeg,
    MarketLeg,
    ShadowJoinError,
    ShadowProvenanceKind,
    ShadowResidualRecord,
    build_shadow_residual,
)
from src.research.prospective.storage import CaptureStore

#: Model market key -> captured odds market key. Only over/under markets with a
#: line are joinable in the capture concept space.
MODEL_TO_ODDS_MARKET: dict[str, str] = {
    "goals": "total_goals",
    "corners": "match_corners",
    "cards": "total_cards",
}


def _parse_iso(ts: str) -> float:
    return datetime.datetime.fromisoformat(ts).timestamp()


@dataclass(frozen=True)
class _PairedSnapshot:
    """A paired over/under snapshot for one exact key at one observed_at."""

    fixture_id: str
    provider: str
    bookmaker: str
    market: str
    line: Optional[float]
    over_odds: float
    under_odds: float
    observed_at: float
    retrieved_at: float
    raw_payload_hash: str
    kickoff_ts: Optional[float]


def _paired_snapshots(store: CaptureStore) -> dict[tuple, list[_PairedSnapshot]]:
    """Group odds captures into paired over/under snapshots per exact key.

    Key = (fixture, bookmaker, market, line). Each value is the list of paired
    snapshots (both sides present at the same observed_at), sorted by time.
    A side without its opposite at the same instant is skipped (a fair
    probability needs both sides; never fabricated).
    """
    # (fixture, book, market, line, observed_at) -> slot
    slots: dict[tuple, dict] = {}
    for rec in store.read_all():
        if rec.value is MISSING or rec.value is None:
            continue
        if not rec.concept.startswith("odds:"):
            continue
        parts = rec.concept.split(":")
        if len(parts) != 5:
            continue
        _, market, selection, line_seg, bookmaker = parts
        if selection not in ("over", "under"):
            continue
        try:
            odds = float(rec.value)
        except (TypeError, ValueError):
            continue
        try:
            line: Optional[float] = float(line_seg)
        except ValueError:
            line = None
        k = (rec.canonical_entity_id, bookmaker, market, line, round(rec.observed_at, 3))
        slot = slots.setdefault(
            k,
            {
                "fixture_id": rec.canonical_entity_id,
                "provider": rec.provider,
                "bookmaker": bookmaker,
                "market": market,
                "line": line,
                "observed_at": rec.observed_at,
                "retrieved_at": rec.retrieved_at,
                "raw_payload_hash": rec.raw_payload_hash,
                "kickoff_ts": rec.event_time,
            },
        )
        slot[selection] = odds

    out: dict[tuple, list[_PairedSnapshot]] = {}
    for (fixture, book, market, line, _obs), slot in slots.items():
        if "over" not in slot or "under" not in slot:
            continue
        ps = _PairedSnapshot(
            fixture_id=slot["fixture_id"],
            provider=slot["provider"],
            bookmaker=book,
            market=market,
            line=line,
            over_odds=slot["over"],
            under_odds=slot["under"],
            observed_at=slot["observed_at"],
            retrieved_at=slot["retrieved_at"],
            raw_payload_hash=slot["raw_payload_hash"],
            kickoff_ts=slot["kickoff_ts"],
        )
        out.setdefault((fixture, book, market, line), []).append(ps)
    for key in out:
        out[key].sort(key=lambda s: s.observed_at)
    return out


def _forecast_legs(records: Iterable[dict]) -> dict[str, list[ForecastLeg]]:
    """Extract per-fixture forecast legs from committed broadcast records.

    Only FORECAST_COMMITTED rows with over/under markets that map to a captured
    odds market are used. Each priced market yields BOTH over and under legs so
    either selection can be joined.
    """
    by_fixture: dict[str, list[ForecastLeg]] = {}
    for r in records:
        if r.get("record_type") != "FORECAST_COMMITTED":
            continue
        payload = r.get("payload") or {}
        fixture_id = r.get("fixture_id") or payload.get("fixture_id")
        if not fixture_id:
            continue
        try:
            generated_at = _parse_iso(payload["generated_at_utc"])
        except (KeyError, ValueError):
            continue
        kickoff_ts = r.get("kickoff_unix") or payload.get("kickoff_unix")
        competition = r.get("comp_id") or payload.get("comp_id")
        commitment_hash = r.get("commitment_hash", "")
        model_version = payload.get("model_version", "")
        scope_version_hash = r.get("scope_version_hash") or payload.get("scope_version_hash", "")
        for m in payload.get("markets", []):
            odds_market = MODEL_TO_ODDS_MARKET.get(m.get("market"))
            if odds_market is None:
                continue
            line = m.get("line")
            p_over = m.get("p_over")
            p_under = m.get("p_under")
            if p_over is None or p_under is None or line is None:
                continue
            for selection, p_model in (("over", p_over), ("under", p_under)):
                by_fixture.setdefault(fixture_id, []).append(
                    ForecastLeg(
                        fixture_id=fixture_id,
                        competition=competition,
                        kickoff_ts=float(kickoff_ts) if kickoff_ts is not None else None,
                        market=odds_market,
                        selection=selection,
                        line=float(line),
                        p_model=float(p_model),
                        generated_at=generated_at,
                        forecast_commitment_hash=commitment_hash,
                        model_version=model_version,
                        scope_version_hash=scope_version_hash,
                    )
                )
    return by_fixture


def _leg_to_market(ps: _PairedSnapshot, selection: str) -> MarketLeg:
    return MarketLeg(
        fixture_id=ps.fixture_id,
        provider=ps.provider,
        bookmaker=ps.bookmaker,
        market=ps.market,
        selection=selection,
        line=ps.line,
        over_odds=ps.over_odds,
        under_odds=ps.under_odds,
        observed_at=ps.observed_at,
        retrieved_at=ps.retrieved_at,
        raw_payload_hash=ps.raw_payload_hash,
    )


def build_candidates(
    *,
    broadcast_records: Iterable[dict],
    capture_store: CaptureStore,
    provenance_kind: ShadowProvenanceKind,
    as_of: Optional[float] = None,
    devig_method: str = "multiplicative",
    created_at: Optional[float] = None,
) -> list[ShadowResidualRecord]:
    """Produce all eligible frozen shadow candidates from persisted state.

    For each fixture in the legitimate intersection, and each (bookmaker, market,
    selection, line) key, pick the latest OWN paired snapshot with
        generated_at <= observed_at <= min(as_of or +inf, kickoff-epsilon)
    and freeze one candidate at T = that snapshot's observed_at.

    Deterministic: candidates are returned sorted by shadow_id.
    """
    legs_by_fixture = _forecast_legs(broadcast_records)
    paired = _paired_snapshots(capture_store)

    out: list[ShadowResidualRecord] = []
    for fixture_id, legs in legs_by_fixture.items():
        for leg in legs:
            # candidate snapshots for this exact key
            key = (fixture_id, None, leg.market, leg.line)  # bookmaker varies
            # iterate over every bookmaker present for this fixture/market/line
            for (fx, book, market, line), snaps in paired.items():
                if fx != fixture_id or market != leg.market or line != leg.line:
                    continue
                # eligible snapshots: at/after generated_at, at/before horizon, pre-kickoff
                horizon = as_of if as_of is not None else float("inf")
                eligible = [
                    s
                    for s in snaps
                    if s.observed_at >= leg.generated_at
                    and s.observed_at <= horizon
                    and (leg.kickoff_ts is None or s.observed_at < leg.kickoff_ts)
                ]
                if not eligible:
                    continue
                chosen = max(eligible, key=lambda s: s.observed_at)
                market_leg = _leg_to_market(chosen, leg.selection)
                try:
                    rec = build_shadow_residual(
                        forecast=leg,
                        market=market_leg,
                        information_cutoff=chosen.observed_at,
                        provenance_kind=provenance_kind,
                        devig_method=devig_method,
                        created_at=created_at,
                    )
                except ShadowJoinError:
                    continue
                out.append(rec)
    out.sort(key=lambda r: r.shadow_id)
    return out


def default_capture_store(root: Path = Path("data/prospective")) -> CaptureStore:
    return CaptureStore(path=Path(root) / "captures.jsonl.gz")



# ---------------------------------------------------------------------------
# Later-movement evaluation from persisted state (append-only; no mutation)
# ---------------------------------------------------------------------------

from src.research.prospective.shadow_residual import (  # noqa: E402
    ShadowMovementEvaluation,
    build_movement_evaluation,
)


def build_evaluations(
    *,
    candidates: Iterable[ShadowResidualRecord],
    capture_store: CaptureStore,
    as_of: Optional[float] = None,
    created_at: Optional[float] = None,
) -> list[ShadowMovementEvaluation]:
    """Derive later same-key movement evaluations for frozen candidates.

    For each candidate, find the LATEST own paired snapshot for the SAME
    (fixture, bookmaker, market, selection, line) key with
        candidate.market_observed_at < observed_at <= min(as_of, kickoff-eps)
    and build a separate evaluation record referencing the candidate. The
    candidate is never mutated. Candidates with no later same-key snapshot
    simply produce no evaluation (never fabricated).

    Deterministic: evaluations returned sorted by evaluation_id.
    """
    paired = _paired_snapshots(capture_store)
    out: list[ShadowMovementEvaluation] = []
    for cand in candidates:
        key = (cand.fixture_id, cand.bookmaker, cand.market, cand.line)
        snaps = paired.get(key)
        if not snaps:
            continue
        horizon = as_of if as_of is not None else float("inf")
        later = [
            s
            for s in snaps
            if s.observed_at > cand.market_observed_at
            and s.observed_at <= horizon
            and (cand.kickoff_ts is None or s.observed_at < cand.kickoff_ts)
        ]
        if not later:
            continue
        chosen = max(later, key=lambda s: s.observed_at)
        later_leg = _leg_to_market(chosen, cand.selection)
        try:
            ev = build_movement_evaluation(
                shadow=cand,
                later_market=later_leg,
                created_at=created_at,
            )
        except ShadowJoinError:
            continue
        out.append(ev)
    out.sort(key=lambda e: e.evaluation_id)
    return out
