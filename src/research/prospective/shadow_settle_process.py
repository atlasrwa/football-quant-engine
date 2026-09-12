"""Settle genuine prospective shadows against canonical final results.

CONSUMES PERSISTED STATE; writes only the append-only settlement ledger.

Reads:
  * ``data/prospective/shadow_residuals.jsonl``  (frozen prospective shadows)
  * both commitment ledgers (to verify parent commitment linkage)
Resolves a canonical FINAL result per fixture via an INJECTED resolver
(default: provider + TheStatsAPINormalizer, cache-first and bounded), grades
each eligible shadow into WIN/LOSS/PUSH/VOID, and appends a settlement record.

DESIGN
======
* The core is I/O-free and deterministic given the resolver. The resolver is
  the only seam that may touch the provider, so grading is fully testable with
  no network and the process cannot mutate any historical record.
* Downstream + append-only: never touches shadows, evaluations, commitments,
  the frontier, or the capture store.
* Fail closed per shadow (bad parent, non-final fixture, missing statistic,
  unsupported market -> that shadow is skipped with a reason; other shadows
  proceed). One malformed fixture never stops the run.
* Bounded provider usage: results are resolved ONCE per fixture (memoised),
  only for fixtures whose kickoff is already in the past, and only for shadows
  not already settled. There is no per-market or per-shadow provider call.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from src.research.prediction_engine.broadcast.record import BroadcastLedger
from src.research.prospective.shadow_settlement import (
    FixtureResult,
    SettlementRefusal,
    SettlementRefusalError,
    build_settlement,
)
from src.research.prospective.shadow_settlement_store import default_settlement_store
from src.research.prospective.shadow_store import default_candidate_store

DEFAULT_SHADOW_ROOT = Path("data/prospective")
DEFAULT_BROADCAST_ROOT = Path("data/forecast_broadcast")
DEFAULT_RESEARCH_BROADCAST_ROOT = Path("data/research_forecast")

#: A resolver maps (fixture_id, kickoff_ts) -> a canonical FixtureResult, or
#: None when no canonical final result is available yet. It must NEVER fabricate
#: a result; returning None fails the fixture closed (its shadows are skipped).
ResultResolver = Callable[[str, Optional[float]], Optional[FixtureResult]]


@dataclass
class SettleRunResult:
    """Observability for one settlement run (never a promotion metric)."""

    shadows_considered: int = 0
    shadows_already_settled: int = 0
    fixtures_pending_kickoff: int = 0
    fixtures_resolved: int = 0
    fixtures_unresolved: int = 0
    settlements_new: int = 0
    settlements_by_outcome: dict = field(default_factory=dict)
    refusals: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "shadows_considered": self.shadows_considered,
            "shadows_already_settled": self.shadows_already_settled,
            "fixtures_pending_kickoff": self.fixtures_pending_kickoff,
            "fixtures_resolved": self.fixtures_resolved,
            "fixtures_unresolved": self.fixtures_unresolved,
            "settlements_new": self.settlements_new,
            "settlements_by_outcome": dict(sorted(self.settlements_by_outcome.items())),
            "refusals": dict(sorted(self.refusals.items())),
            "errors": list(self.errors),
        }


def _valid_commitment_hashes(roots) -> frozenset[str]:
    """Forecast commitment hashes present across the canonical commitment ledgers."""
    hashes: set[str] = set()
    for root in roots:
        try:
            led = BroadcastLedger(root=Path(root))
        except Exception:  # noqa: BLE001 - a missing ledger contributes nothing
            continue
        for rec in led.records():
            if rec.get("record_type") == "FORECAST_COMMITTED":
                h = rec.get("commitment_hash")
                if h:
                    hashes.add(str(h))
    return frozenset(hashes)


def run(
    *,
    result_resolver: ResultResolver,
    shadow_root: Path = DEFAULT_SHADOW_ROOT,
    broadcast_root: Path = DEFAULT_BROADCAST_ROOT,
    research_broadcast_root: Optional[Path] = DEFAULT_RESEARCH_BROADCAST_ROOT,
    now: Optional[float] = None,
    created_at: Optional[float] = None,
) -> SettleRunResult:
    """Settle every eligible, not-yet-settled prospective shadow.

    Args:
        result_resolver: canonical final-result provider (required; injected so
            the process itself performs no I/O and is fully testable).
        shadow_root: prospective ledger root.
        broadcast_root / research_broadcast_root: commitment ledgers (for parent
            linkage verification).
        now: wall clock (unix); only fixtures with kickoff < now are resolved.
        created_at: settlement created_at (tests pin it).

    Returns:
        A machine-readable :class:`SettleRunResult`. Never raises for a single
        bad shadow/fixture; per-shadow refusals are counted by reason.
    """
    wall = time.time() if now is None else float(now)
    result = SettleRunResult()

    roots = [broadcast_root]
    if research_broadcast_root is not None:
        roots.append(research_broadcast_root)
    valid_hashes = _valid_commitment_hashes(roots)

    cand_store = default_candidate_store(root=shadow_root)
    settle_store = default_settlement_store(root=shadow_root)
    already = settle_store.settled_shadow_ids()

    shadows = list(cand_store.read_all_dicts())
    result.shadows_considered = len(shadows)

    # Resolve each fixture's final result at most once (bounded provider usage).
    fixture_cache: dict[str, Optional[FixtureResult]] = {}

    def resolve(fixture_id: str, kickoff_ts: Optional[float]) -> Optional[FixtureResult]:
        if fixture_id in fixture_cache:
            return fixture_cache[fixture_id]
        try:
            res = result_resolver(fixture_id, kickoff_ts)
        except Exception as exc:  # noqa: BLE001 - resolver failure is fail-closed
            result.errors.append(f"resolver error for {fixture_id}: {type(exc).__name__}: {exc}")
            res = None
        fixture_cache[fixture_id] = res
        if res is None:
            result.fixtures_unresolved += 1
        else:
            result.fixtures_resolved += 1
        return res

    new_records = []
    for shadow in shadows:
        sid = shadow.get("shadow_id")
        if sid in already:
            result.shadows_already_settled += 1
            continue

        kickoff = shadow.get("kickoff_ts")
        # Only settle after kickoff has passed (no post-event evidence before it).
        if kickoff is not None and float(kickoff) >= wall:
            result.fixtures_pending_kickoff += 1
            continue

        res = resolve(shadow.get("fixture_id"), kickoff)
        if res is None:
            result.refusals[SettlementRefusal.FIXTURE_NOT_FINAL.value] = (
                result.refusals.get(SettlementRefusal.FIXTURE_NOT_FINAL.value, 0) + 1
            )
            continue

        try:
            rec = build_settlement(
                shadow, res, valid_commitment_hashes=valid_hashes, created_at=created_at
            )
        except SettlementRefusalError as refusal:
            result.refusals[refusal.reason.value] = (
                result.refusals.get(refusal.reason.value, 0) + 1
            )
            continue
        except Exception as exc:  # noqa: BLE001 - one bad shadow never stops the run
            result.errors.append(
                f"settle error for shadow {sid}: {type(exc).__name__}: {exc}"
            )
            continue
        new_records.append(rec)

    # Persist (idempotent append). Count only genuinely-new settlements.
    for rec in new_records:
        if settle_store.append(rec):
            result.settlements_new += 1
            result.settlements_by_outcome[rec.settlement_outcome] = (
                result.settlements_by_outcome.get(rec.settlement_outcome, 0) + 1
            )

    return result


# ---------------------------------------------------------------------------
# Default provider-backed result resolver (cache-first, bounded, fail-closed)
# ---------------------------------------------------------------------------
def provider_result_resolver(
    *, client=None, now: Optional[float] = None
) -> ResultResolver:
    """Build the default resolver using the provider + canonical normalizer.

    Uses ``ProspectiveApiClient`` to fetch the match detail (score) and stats
    (corners/cards) and the canonical ``_FINISHED``/normalizer semantics to
    build a :class:`FixtureResult`. Fails closed (returns None) on any missing
    key, non-final status, or client abort — never fabricates a result. The
    process memoises per fixture, so this is called at most once per fixture.

    Kept intentionally thin and defensive (mirrors scripts/pilotC_settle
    parsing) so the settlement CORE stays provider-agnostic and unit-testable.
    """
    from src.research.prospective.api_contract import Endpoint
    from src.research.prospective.capture import ProspectiveApiClient
    from src.research.prospective.shadow_settlement import FINAL_FIXTURE_STATES

    api = client or ProspectiveApiClient()

    def _num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    def _score(dd):
        if not isinstance(dd, dict):
            return None, None
        sc = dd.get("score")
        if isinstance(sc, dict):
            h, a = _num(sc.get("home")), _num(sc.get("away"))
            if h is not None and a is not None:
                return h, a
            for k in ("fulltime", "full_time", "ft", "current", "total"):
                node = sc.get(k)
                if isinstance(node, dict):
                    h, a = _num(node.get("home")), _num(node.get("away"))
                    if h is not None and a is not None:
                        return h, a
        for hk, ak in (("homeGoalCount", "awayGoalCount"), ("home_goals", "away_goals"),
                       ("home_score", "away_score"), ("goals_home", "goals_away")):
            h, a = _num(dd.get(hk)), _num(dd.get(ak))
            if h is not None and a is not None:
                return h, a
        return None, None

    def _status(dd):
        if not isinstance(dd, dict):
            return ""
        for k in ("status", "match_status", "state"):
            v = dd.get(k)
            if isinstance(v, str):
                return v.strip().lower()
        return ""

    def _pair_total(overview, key):
        node = (overview or {}).get(key)
        if not isinstance(node, dict):
            return None
        allv = node.get("all", node)
        if not isinstance(allv, dict):
            return None
        h, a = _num(allv.get("home")), _num(allv.get("away"))
        if h is None or a is None:
            return None
        return h + a

    def resolver(fixture_id: str, kickoff_ts: Optional[float]) -> Optional[FixtureResult]:
        try:
            detail = api.get(Endpoint.MATCH_DETAIL, match_id=fixture_id)
        except SystemExit:
            return None  # client abort (missing key / cap / network): fail closed
        except Exception:  # noqa: BLE001
            return None
        dd = (detail or {}).get("data", detail) if isinstance(detail, dict) else None
        status = _status(dd)
        if status not in FINAL_FIXTURE_STATES:
            return None
        home, away = _score(dd)
        stats: dict[str, Optional[float]] = {}
        if home is not None and away is not None:
            stats["total_goals"] = home + away
        # corners + cards from /stats (best-effort; missing -> that market fails closed)
        try:
            sresp = api.get(Endpoint.MATCH_DETAIL, match_id=f"{fixture_id}/stats")
        except Exception:  # noqa: BLE001
            sresp = None
        overview = None
        if isinstance(sresp, dict):
            data = sresp.get("data", sresp)
            if isinstance(data, dict):
                overview = data.get("overview", data)
        stats["total_corners"] = _pair_total(overview, "corner_kicks")
        yh = _pair_total(overview, "yellow_cards")
        rh = _pair_total(overview, "red_cards")
        stats["total_cards"] = None if yh is None else (yh + (rh or 0.0))
        return FixtureResult(
            fixture_id=fixture_id,
            status=status,
            statistics=stats,
            observed_at=(time.time() if now is None else now),
            source="thestatsapi:match_detail+stats",
        )

    return resolver



def main(argv=None) -> int:  # pragma: no cover - thin CLI wrapper
    """Standalone settlement run: python -m src.research.prospective.shadow_settle_process run"""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Prospective shadow settlement processor")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="settle finished prospective shadows")
    run_p.add_argument("--shadow-root", default=str(DEFAULT_SHADOW_ROOT))
    run_p.add_argument("--broadcast-root", default=str(DEFAULT_BROADCAST_ROOT))
    run_p.add_argument("--research-broadcast-root", default=str(DEFAULT_RESEARCH_BROADCAST_ROOT))
    args = parser.parse_args(argv)

    if args.cmd == "run":
        res = run(
            result_resolver=provider_result_resolver(),
            shadow_root=Path(args.shadow_root),
            broadcast_root=Path(args.broadcast_root),
            research_broadcast_root=Path(args.research_broadcast_root),
        )
        print(json.dumps(res.to_dict(), indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
