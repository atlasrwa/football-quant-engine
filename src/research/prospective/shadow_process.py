"""Shadow-residual processing entrypoint (consumes persisted state only).

This is the integration point. It performs NO provider request and runs NO
model. It reads:

    * committed forecasts, from BOTH commitment ledgers:
        - data/forecast_broadcast/broadcasts.jsonl   (consumer scope)
        - data/research_forecast/broadcasts.jsonl    (dual-provider research
          universe — every safely mapped FootyStats x TheStatsAPI competition)
    * own market snapshots  (data/prospective/captures.jsonl.gz),

joins them into eligible frozen SHADOW_RESIDUAL candidates, appends new ones to
the append-only ledger (idempotent), and derives later-movement evaluations for
candidates that already have a later same-key snapshot.

There is NO league allowlist on this path. Which competitions can produce a
shadow is decided entirely by which competitions have a committed forecast and a
paired pre-kickoff snapshot — never by league identity, and never by Pilot-C
membership.

Intended to be invoked by an EXISTING scheduled run (e.g. right after the
prospective capture run or the forecast-broadcast tick). It adds no new timer
and no scheduler-cadence change. Re-running against unchanged state is a no-op.

    python -m src.research.prospective.shadow_process run
    python -m src.research.prospective.shadow_process run --as-of 2026-09-09T13:00:00Z

By default it emits PROSPECTIVE_SHADOW records, but ONLY for candidates that
froze at/after the persisted live PROSPECTIVE FRONTIER (see
:mod:`src.research.prospective.shadow_frontier`). The frontier — not the CLI
flag — is what authorizes prospective provenance: a default run over historical
pre-frontier state produces NO prospective records (those candidates are
excluded, never relabeled). Use --reconstructed for RECONSTRUCTED_SHADOW
diagnostics over historical state; those must never be claimed prospective.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from src.research.prediction_engine.broadcast.record import BroadcastLedger
from src.research.prospective.shadow_builder import (
    build_candidates,
    build_evaluations,
    default_capture_store,
)
from src.research.prospective.shadow_frontier import (
    ShadowFrontier,
    establish_frontier,
)
from src.research.prospective.shadow_residual import ShadowProvenanceKind
from src.research.prospective.shadow_store import (
    default_candidate_store,
    default_evaluation_store,
)

DEFAULT_SHADOW_ROOT = Path("data/prospective")
DEFAULT_BROADCAST_ROOT = Path("data/forecast_broadcast")

#: Additional append-only commitment ledgers joined alongside the consumer
#: broadcast ledger.
#:
#: The research ledger (written by ``scripts/research_forecast_commit.py``) carries
#: forecast commitments for the full dual-provider league universe. Reading both
#: roots is what lets a competition outside the historical Pilot-C four produce a
#: prospective shadow at all: a shadow candidate requires a FORECAST_COMMITTED row,
#: and before this the only such rows were the four consumer-scope leagues.
#:
#: Every integrity control is unchanged by widening the *input* set. Each candidate
#: still has to clear the same joins, the same strictly-pre-kickoff rule, and the
#: same live frontier, and ``shadow_id`` is derived from the forecast commitment
#: hash, so a record's provenance stays traceable to the exact ledger row that
#: produced it.
DEFAULT_RESEARCH_BROADCAST_ROOT = Path("data/research_forecast")


@dataclass(frozen=True)
class ShadowRunResult:
    """What one processing run did (observability only; not a promotion metric)."""

    candidates_considered: int
    candidates_new: int
    evaluations_considered: int
    evaluations_new: int
    provenance_kind: str
    #: Frontier timestamp used to gate prospectivity (None for reconstructed).
    frontier_established_at: Optional[float] = None
    #: Candidates the join produced but which were EXCLUDED because they froze
    #: before the live frontier (pre-deployment history; never made prospective).
    candidates_pre_frontier_excluded: int = 0
    #: Commitment ledger roots that were actually read this run, in order.
    #: Recorded so a run that produced nothing can be distinguished from a run
    #: that silently never looked at the research ledger.
    broadcast_roots_read: tuple[str, ...] = ()
    #: FORECAST_COMMITTED rows found per ledger root.
    forecast_records_by_root: dict[str, int] = field(default_factory=dict)
    #: Distinct competitions represented among the new candidates. Observability
    #: only; never a promotion metric and never a filter.
    candidate_competitions: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "candidates_considered": self.candidates_considered,
            "candidates_new": self.candidates_new,
            "candidates_pre_frontier_excluded": self.candidates_pre_frontier_excluded,
            "evaluations_considered": self.evaluations_considered,
            "evaluations_new": self.evaluations_new,
            "provenance_kind": self.provenance_kind,
            "frontier_established_at": self.frontier_established_at,
            "broadcast_roots_read": list(self.broadcast_roots_read),
            "forecast_records_by_root": dict(sorted(self.forecast_records_by_root.items())),
            "candidate_competitions": list(self.candidate_competitions),
        }


def _parse_utc(value: str) -> float:
    v = value.strip().replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(v).timestamp()


def _commitment_roots(
    broadcast_root: Path,
    research_broadcast_root: Optional[Path],
    extra_broadcast_roots: Sequence[Path],
) -> tuple[Path, ...]:
    """Ordered, de-duplicated commitment ledger roots to read.

    Order is stable (consumer first, then research, then extras) so a fixture
    committed in more than one ledger deterministically resolves to the same
    record every run — which matters because ``shadow_id`` incorporates the
    forecast commitment hash.
    """
    ordered: list[Path] = [Path(broadcast_root)]
    if research_broadcast_root is not None:
        ordered.append(Path(research_broadcast_root))
    ordered.extend(Path(r) for r in extra_broadcast_roots)

    seen: set[str] = set()
    out: list[Path] = []
    for root in ordered:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return tuple(out)


def _load_commitment_records(
    roots: Sequence[Path],
) -> tuple[list[dict], dict[str, int]]:
    """Read and merge FORECAST_COMMITTED-bearing rows from every ledger root.

    Deduplicated by ``commitment_hash``. Two ledgers holding the same commitment
    is legitimate (a fixture can be in both consumer and research scope), but it
    must not produce two shadow candidates for one forecast, so the first
    occurrence wins under the stable root ordering.

    Returns:
        ``(records, forecast_rows_per_root)``. The per-root count is of
        FORECAST_COMMITTED rows specifically, so an empty research ledger is
        visibly zero rather than absent.
    """
    merged: list[dict] = []
    per_root: dict[str, int] = {}
    seen_hashes: set[str] = set()
    for root in roots:
        ledger = BroadcastLedger(root=Path(root))
        committed = 0
        for rec in ledger.records():
            if rec.get("record_type") == "FORECAST_COMMITTED":
                committed += 1
                digest = str(rec.get("commitment_hash") or "")
                if digest and digest in seen_hashes:
                    continue
                if digest:
                    seen_hashes.add(digest)
            merged.append(rec)
        per_root[str(root)] = committed
    return merged, per_root


def run(
    *,
    shadow_root: Path = DEFAULT_SHADOW_ROOT,
    broadcast_root: Path = DEFAULT_BROADCAST_ROOT,
    research_broadcast_root: Optional[Path] = DEFAULT_RESEARCH_BROADCAST_ROOT,
    extra_broadcast_roots: Sequence[Path] = (),
    reconstructed: bool = False,
    as_of: Optional[float] = None,
    now: Optional[float] = None,
) -> ShadowRunResult:
    """Process eligible shadow candidates + evaluations from persisted state.

    ``now`` (unix) bounds "live" prospectivity: for PROSPECTIVE_SHADOW the
    effective horizon is ``min(as_of or now, ...)`` so a live run never freezes
    a candidate using a snapshot from the future relative to the wall clock.

    Commitment ledgers (dual-provider coverage):
      Forecast commitments are read from ``broadcast_root`` (consumer scope) AND
      ``research_broadcast_root`` (the full dual-provider research universe), plus
      any ``extra_broadcast_roots``. Reading more than one ledger widens the set of
      competitions that can produce a shadow; it changes no rule about what a
      shadow *is*. Records are concatenated and deduplicated by commitment hash,
      so a fixture present in both ledgers cannot yield two shadows for the same
      forecast. A root that does not exist contributes nothing and is not an error
      — but it is reported in ``forecast_records_by_root``, so "the research ledger
      is empty" is never confused with "the research ledger was not read".

      There is no league filter here and there never was: this function has no
      allowlist, and competition is carried as metadata only.

    Provenance & the live frontier (BLOCKER 1):
      A live (``reconstructed=False``) run establishes/loads the persisted
      PROSPECTIVE FRONTIER ``F`` (see :mod:`shadow_frontier`). A candidate frozen
      at information cutoff ``T`` is emitted as PROSPECTIVE_SHADOW ONLY when
      ``T >= F`` — i.e. it was frozen while the instrumentation was live.
      Candidates that froze before ``F`` are pre-deployment history: they are
      EXCLUDED here (never relabeled prospective). They can only ever be
      produced explicitly via ``reconstructed=True`` (RECONSTRUCTED_SHADOW).
      A corrupt/tampered frontier raises and fails closed (no candidate is made
      prospective). A restart reuses the same immutable ``F``, so the
      prospective/reconstructed partition of history is preserved across
      reboots. ``reconstructed=True`` never consults or mutates the frontier.
    """
    kind = (
        ShadowProvenanceKind.RECONSTRUCTED_SHADOW
        if reconstructed
        else ShadowProvenanceKind.PROSPECTIVE_SHADOW
    )
    wall = now if now is not None else datetime.datetime.now(datetime.timezone.utc).timestamp()

    # Establish/load the immutable live frontier for a prospective run. This is
    # the ONLY thing that authorizes prospective provenance; CLI intent alone is
    # never sufficient. Fails closed on corrupt state (raises ShadowFrontierError).
    frontier: Optional[ShadowFrontier] = None
    if not reconstructed:
        frontier = establish_frontier(shadow_root, now=wall)

    # For a live prospective run, the horizon must not exceed the current time.
    if not reconstructed:
        horizon = wall if as_of is None else min(as_of, wall)
    else:
        horizon = as_of

    roots = _commitment_roots(
        broadcast_root, research_broadcast_root, extra_broadcast_roots
    )
    records, per_root = _load_commitment_records(roots)
    capture_store = default_capture_store(root=shadow_root)

    candidates = build_candidates(
        broadcast_records=records,
        capture_store=capture_store,
        provenance_kind=kind,
        as_of=horizon,
    )

    # Frontier gate: a live candidate may only be PROSPECTIVE_SHADOW if it froze
    # at/after the frontier. Pre-frontier candidates are dropped here — never
    # persisted as prospective, never relabeled. (Historical candidates remain
    # available as RECONSTRUCTED_SHADOW via a --reconstructed run.)
    pre_frontier_excluded = 0
    if not reconstructed and frontier is not None:
        eligible: list = []
        for c in candidates:
            if frontier.allows_prospective(c.information_cutoff):
                eligible.append(c)
            else:
                pre_frontier_excluded += 1
        candidates = eligible

    cand_store = default_candidate_store(root=shadow_root)
    new_cands = cand_store.extend(candidates)

    # Evaluate later movement for ALL known candidates (from the ledger), so
    # evaluations accrue as later snapshots arrive on subsequent runs.
    known = list(_load_candidates(cand_store))
    # Evaluation horizon is the CURRENT observation frontier, not the (possibly
    # earlier) candidate-freezing cutoff: later snapshots accrue over time up to
    # kickoff. For a live run that frontier is the wall clock; for reconstructed
    # diagnostics it is unbounded (kickoff still gates each candidate).
    if reconstructed:
        eval_horizon = None
    else:
        eval_horizon = wall
    evaluations = build_evaluations(
        candidates=known,
        capture_store=capture_store,
        as_of=eval_horizon,
    )
    eval_store = default_evaluation_store(root=shadow_root)
    new_evals = eval_store.extend(evaluations)

    return ShadowRunResult(
        candidates_considered=len(candidates),
        candidates_new=new_cands,
        evaluations_considered=len(evaluations),
        evaluations_new=new_evals,
        provenance_kind=kind.value,
        frontier_established_at=(frontier.established_at if frontier is not None else None),
        candidates_pre_frontier_excluded=pre_frontier_excluded,
        broadcast_roots_read=tuple(str(r) for r in roots),
        forecast_records_by_root=per_root,
        candidate_competitions=tuple(
            sorted({str(c.competition) for c in candidates if c.competition})
        ),
    )


def _load_candidates(cand_store):
    """Rehydrate minimal candidate views needed for evaluation from the ledger."""
    from src.research.prospective.shadow_residual import ShadowResidualRecord
    from dataclasses import fields

    valid = {f.name for f in fields(ShadowResidualRecord)}
    for d in cand_store.read_all_dicts():
        kw = {k: v for k, v in d.items() if k in valid}
        if "classification" in kw and isinstance(kw["classification"], list):
            kw["classification"] = tuple(kw["classification"])
        try:
            yield ShadowResidualRecord(**kw)
        except TypeError:
            continue


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Prospective shadow-residual processor")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="process eligible shadow candidates + evaluations")
    run_p.add_argument("--shadow-root", default=str(DEFAULT_SHADOW_ROOT))
    run_p.add_argument("--broadcast-root", default=str(DEFAULT_BROADCAST_ROOT))
    run_p.add_argument(
        "--research-broadcast-root", default=str(DEFAULT_RESEARCH_BROADCAST_ROOT),
        help="research commitment ledger (dual-provider universe); "
             "pass an empty string to read the consumer ledger only",
    )
    run_p.add_argument("--reconstructed", action="store_true",
                       help="emit RECONSTRUCTED_SHADOW (diagnostics; never prospective)")
    run_p.add_argument("--as-of", default=None, help="ISO-8601 UTC cutoff horizon")
    args = parser.parse_args(argv)

    if args.cmd == "run":
        as_of = _parse_utc(args.as_of) if args.as_of else None
        research_root = (
            Path(args.research_broadcast_root)
            if str(args.research_broadcast_root).strip()
            else None
        )
        result = run(
            shadow_root=Path(args.shadow_root),
            broadcast_root=Path(args.broadcast_root),
            research_broadcast_root=research_root,
            reconstructed=args.reconstructed,
            as_of=as_of,
        )
        import json
        print(json.dumps(result.to_dict()))
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
