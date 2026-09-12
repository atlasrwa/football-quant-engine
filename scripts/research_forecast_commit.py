#!/usr/bin/env python3
"""Commit research forecasts across the full dual-provider league universe.

WHAT THIS RUN DOES
==================
For every competition in the safe FootyStats x TheStatsAPI intersection, and every
market that competition's provider actually prices, compute the champion engine's
probability for each fixture that has reached the research horizon and write an
append-only forecast commitment to ``data/research_forecast/``.

That commitment is the missing prerequisite for prospective shadow residuals
outside Pilot C: ``shadow_builder`` joins ``FORECAST_COMMITTED`` rows against our
own pre-kickoff market snapshots, and capture already spans the whole eligible
universe.

WHAT THIS RUN CANNOT DO
=======================
Publish. There is no transport, no queue, no renderer and no delivery ledger on
this path. It writes commitments and nothing else. Consumer publication scope
(``config/forecast_broadcast_scope.json``) is read only for its *market cell
declarations* — the lines and side labels are copied verbatim so a research
forecast for a market is the identical computation to a consumer forecast for that
market — and is never widened.

The champion model is reused as-is via ``forecast_broadcast.ForecastEngine``:
same corpus snapshot, same frozen hyperparameters, same fitted cells, same
``predict_one``. No coefficient, calibration, line or model-selection decision is
made here.

FAIL CLOSED PER STAGE
=====================
* competition outside the intersection    -> excluded, reason recorded
* market the provider does not price      -> that market abstains, league continues
* team history missing / below the floor  -> that fixture abstains, others continue
* corpus stale                            -> model stage refused for the run, every
                                             due fixture recorded NOT_PUBLISHED

USAGE
=====
    python3 scripts/research_forecast_commit.py                 # scheduled run
    python3 scripts/research_forecast_commit.py --dry-run       # no writes
    python3 scripts/research_forecast_commit.py --coverage      # report only
    python3 scripts/research_forecast_commit.py --limit 25      # bound one tick
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Optional, Sequence

warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

from src.research.prediction_engine.broadcast.corpus_freshness import (
    CorpusFreshnessError,
)
from src.research.prediction_engine.broadcast.corpus_snapshot import (
    CorpusIntegrityError,
    SameMatchLeakageError,
)
from src.research.prediction_engine.broadcast.payload import (
    ForecastContentError,
    build_forecast_payload,
)
from src.research.prediction_engine.broadcast.record import BroadcastLedger
from src.research.prediction_engine.broadcast.scope_config import (
    ScopeConfig,
    load_scope_config,
)
from src.research.prediction_engine.research_forecast import (
    DEFAULT_RESEARCH_HORIZON_HOURS,
    DEFAULT_RESEARCH_RECORD_ROOT,
    ResearchForecastResult,
    build_research_scope_config,
    market_abstentions,
    record_research_scope_version,
    research_due_fixtures,
)
from src.research.scope.dual_provider import corpus_covered_competition_ids
from src.research.scope.market_scope import build_research_scope

HOME = Path("/home/ubuntu")

#: The research fixture universe, written by ``scripts/research_fixture_discovery.py``
#: across the full dual-provider intersection.
RESEARCH_FIXTURE_LIST = HOME / "data/research/research_fixture_universe.json"

#: Where the run states what it covered this tick. Overwritten each run; the
#: durable history is the append-only commitment ledger.
COVERAGE_REPORT = DEFAULT_RESEARCH_RECORD_ROOT / "research_coverage_report.json"

logger = logging.getLogger("research_forecast_commit")


def load_research_universe(
    *, research_path: Path = RESEARCH_FIXTURE_LIST
) -> dict[str, dict[str, Any]]:
    """The union of the research fixture universe and Pilot C's shared universe.

    Two sources, read-only, because they are refreshed by different runs:

    * the research universe covers every dual-provider competition;
    * Pilot C's universe covers its four pre-registered competitions and is
      refreshed on its own cadence.

    Reading the union means research forecasting covers the whole eligible universe
    without this pass having to write — and therefore without any risk of altering —
    Pilot C's pre-registered fixture sample. The research file wins on conflict
    because it is the one this pipeline maintains; the merge is by fixture id, so a
    fixture present in both appears exactly once.
    """
    import forecast_broadcast as fb

    merged: dict[str, dict[str, Any]] = dict(fb.load_fixture_universe())

    path = Path(research_path)
    if not path.exists():
        logger.warning(
            "research fixture universe not found at %s; falling back to the shared "
            "universe only. Run scripts/research_fixture_discovery.py to cover the "
            "full dual-provider league set.", path,
        )
        return merged
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("research fixture universe is unreadable (%s): %s", path, exc)
        return merged

    meta = raw.get("meta")
    if isinstance(meta, dict):
        for fixture_id, info in meta.items():
            if isinstance(info, dict):
                merged[str(fixture_id)] = info
    return merged


def _consumer_market_specs() -> tuple[Any, ...]:
    """The declared champion market cells, taken verbatim from consumer scope.

    ``require_recorded_change=False`` is correct and safe here: this call is
    read-only and inspects the declaration for its *market cells only*. Nothing
    on this path can publish, so the consumer change-log gate — which exists to
    stop an unlogged scope change taking effect on a send path — has nothing to
    protect against. The consumer send path continues to load its scope with the
    gate enforced.
    """
    consumer = load_scope_config(require_recorded_change=False)
    return consumer.markets


def _research_reference_kickoffs(
    universe: dict[str, dict[str, Any]], corpus_comp_ids: frozenset[str]
) -> tuple[float, ...]:
    """Kick-offs used as the corpus-freshness benchmark.

    Restricted to competitions the training corpus actually covers. The gate asks
    "have matches been played that we should already have ingested?" — a finished
    fixture in a competition the corpus has never contained is not evidence of an
    ingestion failure, and letting it set the benchmark would make every newly
    covered league read as staleness and block the entire run. Widening coverage
    must not be able to manufacture an outage.
    """
    out: list[float] = []
    for info in universe.values():
        if str(info.get("comp") or "") not in corpus_comp_ids:
            continue
        try:
            out.append(float(info["ts"]))
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(sorted(out))


def run(
    *,
    dry_run: bool = False,
    limit: Optional[int] = None,
    record_root: Path = DEFAULT_RESEARCH_RECORD_ROOT,
    horizon_hours: int = DEFAULT_RESEARCH_HORIZON_HOURS,
    now_unix: Optional[float] = None,
) -> ResearchForecastResult:
    """Execute one research forecast pass. Returns the machine-readable result."""
    import forecast_broadcast as fb  # champion engine + fixture universe loader

    result = ResearchForecastResult(dry_run=dry_run, horizon_hours=horizon_hours)
    now = now_unix if now_unix is not None else time.time()

    # 1. Universe: the dual-provider intersection x per-market eligibility.
    scope = build_research_scope()
    result.registry_leagues_total = len(scope.universe.leagues)
    result.dual_provider_eligible = len(scope.universe.eligible)
    result.leagues_excluded = len(scope.universe.excluded)
    result.league_exclusion_reasons = scope.universe.exclusion_summary()
    result.competitions_in_research_scope = len(scope.forecastable_competition_ids)

    if not scope.forecastable_competition_ids:
        result.errors.append(
            "no competition is both dual-provider eligible and has a forecastable "
            "market; nothing to do (this is an explicit empty universe, not a skip)"
        )
        result.finished_at_utc = fb._now_iso()
        return result

    market_specs = _consumer_market_specs()
    config: ScopeConfig = build_research_scope_config(
        scope=scope, market_specs=market_specs, horizon_hours=horizon_hours
    )
    result.scope_version_hash = config.scope_version_hash
    if not dry_run:
        record_research_scope_version(config, scope=scope, root=record_root)

    # 2. Fixtures due at the research horizon.
    ledger = BroadcastLedger(record_root)
    universe = load_research_universe()
    result.fixtures_in_universe = len(universe)
    due, exclusions = research_due_fixtures(
        universe,
        config=config,
        now_unix=now,
        already_fired=ledger.fired_fixture_ids(),
    )
    result.fixture_exclusions = exclusions
    result.competitions_with_fixtures_in_horizon = len(
        {f.competition_id for f in due if f.competition_id}
    )
    if limit is not None:
        due = due[:limit]
    result.fixtures_due = len(due)

    if not due:
        logger.info(
            "no fixture reached the research T-%dh horizon this tick "
            "(%d competitions in scope)", horizon_hours,
            result.competitions_in_research_scope,
        )
        result.finished_at_utc = fb._now_iso()
        return result

    # 3. Fit once, so every commitment in this run shares one model_version.
    #    The freshness gate runs inside the engine, before the fit, and refuses the
    #    model stage for the whole run rather than degrading per fixture.
    corpus_comps = corpus_covered_competition_ids(scope.universe)
    reference_kickoffs = _research_reference_kickoffs(universe, corpus_comps)
    try:
        engine = fb.ForecastEngine(
            config,
            reference_kickoffs=reference_kickoffs,
            snapshot_cutoff_unix=now,
        )
    except CorpusFreshnessError as exc:
        verdict = exc.verdict
        logger.error("RESEARCH FRESHNESS GATE: %s", verdict.detail)
        result.errors.append(f"corpus_freshness_gate: {verdict.detail}")
        result.freshness_state = verdict.state.value
        result.model_stage_exclusions["corpus_stale"] = len(due)
        if not dry_run:
            for fixture in due:
                ledger.append_not_published(
                    fixture_id=fixture.fixture_id,
                    comp_id=fixture.competition_id,
                    kickoff_unix=fixture.kickoff_unix,
                    reason=(
                        "model stage refused: corpus freshness gate — "
                        f"{verdict.detail}"
                    ),
                    scope_version_hash=config.scope_version_hash,
                )
                result.not_published_written += 1
        result.finished_at_utc = fb._now_iso()
        return result
    except CorpusIntegrityError as exc:
        logger.error("RESEARCH CORPUS INTEGRITY: %s", exc)
        result.errors.append(f"corpus_integrity: {exc}")
        result.finished_at_utc = fb._now_iso()
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("research forecast engine unavailable: %s", exc)
        result.errors.append(f"engine_unavailable: {type(exc).__name__}: {exc}")
        result.finished_at_utc = fb._now_iso()
        return result

    result.model_version = engine.model_version
    result.data_cutoff_utc = engine.data_cutoff_utc
    result.freshness_state = engine.freshness.state.value

    # 4. Commit per fixture. A failure at one fixture never sinks the run.
    for fixture in due:
        comp_id = fixture.competition_id
        abstain = market_abstentions(
            scope=scope, competition_id=comp_id, market_specs=market_specs
        )
        for spec in market_specs:
            if spec.cell in abstain:
                key = f"{spec.market}:{comp_id}"
                result.market_stage_abstentions[key] = (
                    result.market_stage_abstentions.get(key, 0) + 1
                )

        try:
            probs, reasons, history = engine.probabilities(
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                kickoff_unix=fixture.kickoff_unix,
            )
        except SameMatchLeakageError as exc:
            # The fixture's own result is already in the corpus. Structural
            # refusal: no probability is produced for it at all.
            result.model_stage_exclusions["same_match_leakage"] = (
                result.model_stage_exclusions.get("same_match_leakage", 0) + 1
            )
            if not dry_run:
                ledger.append_not_published(
                    fixture_id=fixture.fixture_id,
                    comp_id=comp_id,
                    kickoff_unix=fixture.kickoff_unix,
                    reason=f"model stage refused: same-match leakage — {exc}",
                    scope_version_hash=config.scope_version_hash,
                )
                result.not_published_written += 1
            continue
        except Exception as exc:  # noqa: BLE001
            result.errors.append(
                f"fixture {fixture.fixture_id}: {type(exc).__name__}: {exc}"
            )
            result.model_stage_exclusions["engine_error"] = (
                result.model_stage_exclusions.get("engine_error", 0) + 1
            )
            continue

        # Market-stage abstention overrides any probability the engine produced:
        # a market the provider does not price must not be committed as research
        # evidence, because it could never be joined to a market observation.
        final_probs: dict[tuple[str, Optional[float]], Optional[float]] = {}
        final_reasons: dict[tuple[str, Optional[float]], str] = {}
        for spec in market_specs:
            cell = spec.cell
            if cell in abstain:
                final_probs[cell] = None
                final_reasons[cell] = abstain[cell]
                continue
            value = probs.get(cell)
            final_probs[cell] = value
            if value is None:
                final_reasons[cell] = reasons.get(
                    cell, "engine produced no probability"
                )

        n_priced = sum(1 for v in final_probs.values() if v is not None)
        n_abstained = len(market_specs) - n_priced
        result.priced_cells += n_priced
        result.abstained_cells += n_abstained

        if n_priced == 0:
            # Every declared cell abstained. Record why, permanently and visibly:
            # a fixture that simply vanished would be indistinguishable from one
            # that was never in scope.
            detail = "; ".join(
                sorted({str(r) for r in final_reasons.values()})
            )[:600]
            if not history.get("sufficient", True):
                result.model_stage_exclusions["insufficient_history"] = (
                    result.model_stage_exclusions.get("insufficient_history", 0) + 1
                )
            else:
                result.model_stage_exclusions["no_priced_market"] = (
                    result.model_stage_exclusions.get("no_priced_market", 0) + 1
                )
            if not dry_run:
                ledger.append_not_published(
                    fixture_id=fixture.fixture_id,
                    comp_id=comp_id,
                    kickoff_unix=fixture.kickoff_unix,
                    reason=f"no declared market could be priced: {detail}",
                    scope_version_hash=config.scope_version_hash,
                )
                result.not_published_written += 1
            continue

        try:
            payload = build_forecast_payload(
                config=config,
                fixture_id=fixture.fixture_id,
                comp_id=comp_id,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                kickoff_unix=fixture.kickoff_unix,
                probabilities=final_probs,
                unavailable_reasons=final_reasons,
                model_version=engine.model_version,
                data_cutoff_utc=engine.data_cutoff_utc,
                corpus_provenance=engine.corpus_provenance(),
                history_provenance=history,
                generated_at_utc=fb._now_iso(),
            )
        except ForecastContentError as exc:
            result.errors.append(f"fixture {fixture.fixture_id}: payload refused: {exc}")
            continue

        if not dry_run:
            ledger.append_commitment(payload)
        result.commitments_written += 1
        if comp_id:
            result.committed_by_competition[comp_id] = (
                result.committed_by_competition.get(comp_id, 0) + 1
            )

    result.competitions_committed = len(result.committed_by_competition)
    result.finished_at_utc = fb._now_iso()
    return result


def emit_coverage_report(
    result: ResearchForecastResult, *, path: Path = COVERAGE_REPORT, dry_run: bool = False
) -> None:
    """Write the run's machine-readable coverage report, overwriting the previous."""
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def emit_engine_coverage_report(
    result: ResearchForecastResult, *, dry_run: bool = False
) -> Optional[Path]:
    """Write the end-to-end engine coverage report for this tick.

    Separate from the run report above: that one describes what *this* pass did,
    this one stitches the whole path together (provider discovery through research
    Telegram delivery) by reading persisted artifacts. Passing this run's summary in
    is what lets it populate the fixtures-in-horizon and model-prerequisite fields,
    which no persisted artifact can supply on its own — without it those stay
    UNKNOWN, which is correct but less useful.
    """
    if dry_run:
        return None
    try:
        from src.research.scope.coverage_report import (
            build_coverage_report,
            emit_coverage_report as write_report,
        )

        report = build_coverage_report(research_run=result.to_dict())
        return write_report(report)
    except Exception as exc:  # noqa: BLE001 - observability must never fail the run
        logger.error("engine coverage report not written: %s: %s", type(exc).__name__, exc)
        return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Commit research forecasts across the dual-provider universe"
    )
    parser.add_argument("--dry-run", action="store_true", help="compute, write nothing")
    parser.add_argument(
        "--coverage", action="store_true",
        help="report the scope/coverage matrix without running the model",
    )
    parser.add_argument("--limit", type=int, default=None, help="cap fixtures this tick")
    parser.add_argument(
        "--horizon-hours", type=int, default=DEFAULT_RESEARCH_HORIZON_HOURS,
        help=f"research commitment horizon (default {DEFAULT_RESEARCH_HORIZON_HOURS})",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    import forecast_broadcast as fb

    fb.load_env()

    if args.coverage:
        scope = build_research_scope()
        print(json.dumps(scope.to_dict(), indent=2, sort_keys=True))
        return 0

    result = run(
        dry_run=args.dry_run, limit=args.limit, horizon_hours=args.horizon_hours
    )
    emit_coverage_report(result, dry_run=args.dry_run)
    emit_engine_coverage_report(result, dry_run=args.dry_run)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
