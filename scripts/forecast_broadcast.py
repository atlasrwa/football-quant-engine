#!/usr/bin/env python3
"""T-8h forecast broadcast — publish engine probabilities at a fixed horizon.

WHAT THIS RUN DOES
==================
Evaluated by the scheduler, never on demand. On each tick it:

1. Flushes any forecast queued by quiet hours, so a delayed message goes out at the
   first opportunity with its original ``generated_at_utc`` and hash intact.
2. Finds every fixture whose competition is in declared scope and whose horizon
   moment (kickoff minus the declared hours) has arrived, and which has not already
   fired. Each fixture fires exactly once, ever.
3. For each, computes the engine probability for every declared market cell, states
   both sides, hashes the payload, records the commitment append-only, gates the
   rendered message, and delivers it.
4. Independently captures available prices for the same markets into the CLV panel
   store, with the collection timestamp.

WHAT IT DELIBERATELY DOES NOT DO
================================
No fixture is filtered out by probability, confidence, price band, or expected
quality. The scope file decides what is broadcast; this script decides nothing. There
is no threshold constant anywhere in it, and no market or line outside the declared
scope is ever computed.

Nothing here touches the deprecated EV / edge / stake path. ``CryptoSignalExporter``,
``RiskUnitCalculator``, ``KellyCalculator``, and ``EVCalculator`` are not imported and
not reachable; ``devig``/edge helpers that happen to live alongside the reused model
functions are not called.

WHY IT REUSES PILOT C'S MODEL FUNCTIONS
=======================================
``fit_full`` and ``predict_one`` in ``pilotC_forward_predict`` are pure functions over
the frozen stat-mixer hyperparameters. Reusing them means the broadcast publishes the
same probability the engine produces elsewhere; reimplementing them would risk two
divergent numbers under one ``model_version``. Only those two functions are used —
Pilot C's ``main()``, its ledger, its commitments, and its pre-registration are never
invoked or written to.

TWO COST PROFILES, ONE COVERAGE RULE
====================================
Producing a forecast is local and free: it reads the corpus and the frozen model, so
forecast coverage is never rationed. Capturing prices calls a metered provider, so it
is bounded by a request cap. When the cap binds, the *price* capture is deferred and
recorded as a gap — the forecast still goes out. Coverage of the published record is
absolute; coverage of the price panel is best-effort and says so.

USAGE
=====
    python3 scripts/forecast_broadcast.py                    # scheduled run
    python3 scripts/forecast_broadcast.py --dry-run          # no send, no writes
    python3 scripts/forecast_broadcast.py --coverage         # audit declared vs record
    python3 scripts/forecast_broadcast.py --record-scope-change --reason "..."
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

from src.research.prediction_engine.broadcast import price_panel as pp
from src.research.prediction_engine.broadcast.delivery import (
    ForecastDeliverer,
    PendingQueue,
    QUEUE_NAME,
    RecordingTransport,
    TelegramTransport,
)
from src.research.prediction_engine.broadcast.payload import (
    ForecastContentError,
    build_forecast_payload,
    render_checked_message,
)
from src.research.prediction_engine.broadcast.record import (
    BroadcastLedger,
    DEFAULT_RECORD_ROOT,
    DeliveryStatus,
)
from src.research.prediction_engine.broadcast.scope_config import (
    DEFAULT_CHANGELOG_PATH,
    DEFAULT_CONFIG_PATH,
    ScopeChangeUnrecorded,
    ScopeConfig,
    ScopeConfigError,
    canonical_hash,
    load_scope_config,
    record_scope_change,
)

HOME = Path("/home/ubuntu")
ENV_PATH = HOME / ".env"
FIXTURE_LIST = HOME / "data/thestatsapi/championship/_pilotC_fixture_list.json"
STAT_MIXER_ARTIFACT = HOME / "data/discovery/pilotC_stat_mixer.json"
PRICE_CAPTURE_WORK_ROOT = HOME / "data/clv_panel/captures"
PRICE_GAP_LOG = pp.DEFAULT_PANEL_ROOT / "price_capture_gaps.jsonl"

#: Bounds the metered provider calls for price capture only. It never affects which
#: forecasts are published.
PRICE_REQUEST_CAP = int(os.environ.get("FORECAST_BROADCAST_PRICE_REQUEST_CAP", "45"))

#: Identifies the probability source inside the model_version hash.
PREDICTOR_IDENTITY = "pilotC_stat_mixer.elasticnet_logistic_full_corpus"
MODEL_VERSION_CONTRACT = "forecast-broadcast-model/v1"

logger = logging.getLogger("forecast_broadcast")


def load_env(path: Path = ENV_PATH) -> None:
    """Load KEY=VALUE lines into os.environ without overriding existing values."""
    if not path.exists():
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Fixture universe
# ─────────────────────────────────────────────────────────────────────────────
def load_fixture_universe(path: Path = FIXTURE_LIST) -> dict[str, dict[str, Any]]:
    """Read the shared discovered fixture universe, read-only.

    Kickoffs are the normalized ``ts`` UTC epoch produced by discovery; no local-time
    arithmetic happens anywhere on this path.
    """
    if not path.exists():
        logger.error("fixture universe not found: %s", path)
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("fixture universe is not valid JSON: %s", exc)
        return {}
    meta = raw.get("meta")
    return meta if isinstance(meta, dict) else {}


def due_fixtures(
    universe: dict[str, dict[str, Any]],
    config: ScopeConfig,
    *,
    now_unix: float,
    already_fired: frozenset[str],
) -> list[tuple[str, dict[str, Any]]]:
    """Every in-scope fixture whose horizon has arrived and which has not fired.

    A fixture becomes due at ``kickoff - horizon`` and stays due until it fires. It is
    never dropped for being late: if the scheduler was down, the fixture is still
    picked up on the next tick and either published (if still pre-kickoff) or recorded
    as a missed horizon. Silently forgetting a late fixture would leave a coverage gap
    indistinguishable from it never having been in scope.

    Ordered by kickoff so the most urgent fixtures are handled first if a run is
    interrupted.
    """
    due: list[tuple[str, dict[str, Any]]] = []
    for fixture_id, info in universe.items():
        if str(fixture_id) in already_fired:
            continue
        if not config.is_in_scope(info.get("comp")):
            continue
        try:
            kickoff = float(info["ts"])
        except (KeyError, TypeError, ValueError):
            logger.error("fixture %s has no usable kickoff; cannot place it on the "
                         "horizon", fixture_id)
            continue
        if now_unix >= kickoff - config.horizon_seconds:
            due.append((str(fixture_id), info))
    due.sort(key=lambda item: float(item[1]["ts"]))
    return due


# ─────────────────────────────────────────────────────────────────────────────
# Forecast source
# ─────────────────────────────────────────────────────────────────────────────
class ForecastEngine:
    """The declared market cells, fitted once per run, plus their provenance.

    Fitting is done once and reused for every fixture in the run so that every
    forecast published by a run carries the same ``model_version`` and the same
    ``data_cutoff_utc``.
    """

    def __init__(self, config: ScopeConfig) -> None:
        import pilotC_forward_predict as fp
        import pilotC_stat_mixer as mix

        self._fp = fp
        self._mix = mix
        self._config = config

        artifact = json.loads(STAT_MIXER_ARTIFACT.read_text(encoding="utf-8"))
        saved = {
            (row["market"], row.get("line")): (row["C"], row["l1_ratio"])
            for row in artifact["models"]
        }

        # Fail closed on a declared cell with no frozen model. Silently omitting it
        # would publish a narrower scope than the file declares.
        missing = [cell for cell in (m.cell for m in config.markets) if cell not in saved]
        if missing:
            raise ScopeConfigError(
                f"declared market cells have no frozen model: {missing}. Either the "
                "scope declares a market the engine cannot price, or the model "
                "artifact is stale."
            )

        matches = mix.load_corpus()
        self._hist = mix.build_histories(matches)
        cutoffs = [
            float(m["date_unix"]) for m in matches if m.get("date_unix")
        ]
        self._data_cutoff_unix = max(cutoffs) if cutoffs else 0.0
        self._n_matches = len(matches)

        logger.info(
            "fitting %d declared market cell(s) on %d corpus matches (cutoff %s)",
            len(config.markets), self._n_matches, self.data_cutoff_utc,
        )
        self._models: dict[tuple[str, Optional[float]], Any] = {}
        for spec in config.markets:
            C, l1r = saved[spec.cell]
            self._models[spec.cell] = fp.fit_full(
                matches, self._hist, spec.market, spec.line, C, l1r
            )

        self._model_version = canonical_hash(
            {
                "contract": MODEL_VERSION_CONTRACT,
                "predictor": PREDICTOR_IDENTITY,
                "cells": sorted(
                    [spec.market, spec.line] for spec in config.markets
                ),
                "hyperparameters": {
                    f"{spec.market}|{spec.line}": list(saved[spec.cell])
                    for spec in config.markets
                },
                "feature_pools": {
                    spec.market: mix.POOLS.get(spec.market, [])
                    for spec in config.markets
                },
                "windows": list(mix.WINDOWS),
                "corpus_n_matches": self._n_matches,
                "data_cutoff_unix": int(self._data_cutoff_unix),
            }
        )

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def data_cutoff_utc(self) -> str:
        return datetime.fromtimestamp(
            self._data_cutoff_unix, timezone.utc
        ).isoformat()

    def probabilities(
        self, *, home_team: str, away_team: str, kickoff_unix: float
    ) -> tuple[
        dict[tuple[str, Optional[float]], Optional[float]],
        dict[tuple[str, Optional[float]], str],
    ]:
        """Engine ``P(over line)`` for every declared cell, plus reasons for gaps.

        Only declared cells are computed — the loop iterates the config, so no market
        or line outside declared scope can enter a payload.

        Features are point-in-time by construction: ``match_features`` reads only
        history strictly before the fixture's kickoff.
        """
        missing_history = [
            team for team in (home_team, away_team) if team not in self._hist
        ]
        match = {
            "home_name": home_team,
            "away_name": away_team,
            "date_unix": kickoff_unix,
        }
        probs: dict[tuple[str, Optional[float]], Optional[float]] = {}
        reasons: dict[tuple[str, Optional[float]], str] = {}
        for spec in self._config.markets:
            if missing_history:
                probs[spec.cell] = None
                reasons[spec.cell] = (
                    "no match history in corpus for "
                    + ", ".join(missing_history)
                )
                continue
            try:
                p_over = self._fp.predict_one(
                    self._models[spec.cell], self._hist, match, spec.market
                )
            except Exception as exc:  # noqa: BLE001 - one cell must not sink a run
                logger.error(
                    "cell %s failed for %s vs %s: %s",
                    spec.cell, home_team, away_team, exc,
                )
                probs[spec.cell] = None
                reasons[spec.cell] = f"engine error: {type(exc).__name__}"
                continue
            if p_over is None:
                probs[spec.cell] = None
                reasons[spec.cell] = "no usable features at this kickoff"
                continue
            # No threshold, no confidence gate. Whatever the engine says is published.
            probs[spec.cell] = float(p_over)
        return probs, reasons


# ─────────────────────────────────────────────────────────────────────────────
# Price capture (separate layer)
# ─────────────────────────────────────────────────────────────────────────────
def capture_prices_for_fixture(
    *,
    fixture_id: str,
    kickoff_unix: float,
    config: ScopeConfig,
    store: pp.PriceCaptureStore,
    dry_run: bool,
) -> tuple[int, str]:
    """Capture available prices for the declared markets into the CLV panel store.

    Called after the forecast has already been built, hashed, and committed. Nothing
    it returns is fed back into the forecast, and it is invoked with no reference to
    the payload — a failure here can therefore change nothing about what was
    published.

    Returns:
        ``(rows_written, detail)``.
    """
    if dry_run:
        # A dry run must never reach the metered provider. Prices are only
        # observable live, so there is no way to "dry-run" a capture: fetching and
        # discarding would spend real budget and, worse, would consume the one
        # observation that belongs in the panel. Reporting the skip is the honest
        # behaviour. Guarded here as well as at the call site so no future caller
        # can reintroduce the spend.
        return 0, "dry-run: provider not called"

    import fixture_ev_engine as engine

    observed = datetime.now(timezone.utc)
    request_dir = (
        PRICE_CAPTURE_WORK_ROOT
        / str(fixture_id)
        / observed.strftime("%Y%m%dT%H%M%SZ")
    )
    try:
        raw, _meta = engine.capture_odds(
            str(fixture_id), request_dir, kickoff_unix=float(kickoff_unix)
        )
    except ValueError as exc:
        # ensure_pre_kickoff refused: a price that cannot be proven pre-kickoff is
        # not recorded at all rather than recorded with an optimistic label.
        return 0, f"refused: {exc}"
    except SystemExit as exc:
        # Do NOT report every abort as a budget stop. A missing THESTATS_API_KEY
        # (code 2) or an API auth rejection (code 6) is broken plumbing, not a quota
        # outcome, and recording it as one is precisely how Pilot C's outage stayed
        # invisible for 98.7 hours. The gap log states which it was, so a monitor can
        # tell "we chose to stop spending" from "we cannot authenticate".
        import thestatsapi_client as api_client

        code, clean, reason = api_client.describe_abort(exc)
        if clean:
            return 0, f"clean budget stop (SystemExit {code}): {reason}"
        return 0, f"PROVIDER FAILURE (SystemExit {code}): {reason}"
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {str(exc)[:200]}"

    books = engine.parse_books(raw)
    if not books:
        return 0, "no book payloads returned"

    quotes: list[pp.PriceQuote] = []
    for book, markets in books.items():
        for spec in config.markets:
            try:
                over, under = engine._market_prices(markets, spec.market, spec.line)
            except (KeyError, TypeError, AttributeError):
                continue
            for selection, odds in (
                (spec.over_label, over),
                (spec.under_label, under),
            ):
                if not isinstance(odds, (int, float)):
                    continue
                quotes.append(
                    pp.PriceQuote(
                        market=spec.market,
                        line=spec.line,
                        bookmaker=book,
                        selection=selection,
                        decimal_odds=float(odds),
                    )
                )

    if not quotes:
        return 0, "no priced selections for declared markets"

    records = pp.build_price_records(
        fixture_id=str(fixture_id),
        kickoff_unix=kickoff_unix,
        quotes=quotes,
        observed_at=observed,
        source="thestatsapi",
        horizon_hours=config.horizon_hours_before_kickoff,
    )
    return store.append(records), "ok"


def log_price_gap(
    *, fixture_id: str, kickoff_unix: float, reason: str, dry_run: bool
) -> None:
    """Record that a price capture did not happen, and why.

    The price panel is best-effort by design; saying so in an append-only log is what
    keeps it honest, because a missing panel row would otherwise look identical to a
    fixture that had no prices.
    """
    if dry_run:
        return
    _append_jsonl(
        PRICE_GAP_LOG,
        {
            "fixture_id": str(fixture_id),
            "kickoff_unix": int(float(kickoff_unix)),
            "reason": reason,
            "recorded_at_utc": _now_iso(),
            "capture_context": pp.CAPTURE_CONTEXT_HORIZON,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# The run
# ─────────────────────────────────────────────────────────────────────────────
def run(
    *,
    config: ScopeConfig,
    dry_run: bool = False,
    capture_prices: bool = True,
    record_root: Path = DEFAULT_RECORD_ROOT,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Execute one scheduler tick. Returns a summary dict."""
    summary: dict[str, Any] = {
        "started_at_utc": _now_iso(),
        "scope_version_hash": config.scope_version_hash,
        "horizon_hours": config.horizon_hours_before_kickoff,
        "dry_run": dry_run,
        "queue_flushed": 0,
        "due": 0,
        "committed": 0,
        "sent": 0,
        "queued_quiet_hours": 0,
        "delivery_failed": 0,
        "content_gate_blocked": 0,
        "not_published": 0,
        "missed_horizon_past_kickoff": 0,
        "price_rows_written": 0,
        "price_gaps": 0,
        "errors": [],
    }

    ledger = BroadcastLedger(record_root)
    queue = PendingQueue(Path(record_root) / QUEUE_NAME)
    transport = RecordingTransport() if dry_run else TelegramTransport()
    deliverer = ForecastDeliverer(
        ledger=ledger,
        queue=queue,
        transport=transport,
        quiet_start_hour=config.quiet_hours_start_hour,
        quiet_end_hour=config.quiet_hours_end_hour,
    )

    # 1. Delayed forecasts go out first, before anything new is generated.
    if not dry_run:
        flushed = deliverer.flush_queue()
        summary["queue_flushed"] = sum(
            1 for o in flushed if o.status is DeliveryStatus.SENT
        )
        summary["queue_pending"] = len(queue)

    # 2. Which fixtures have reached the horizon.
    universe = load_fixture_universe()
    now_unix = time.time()
    due = due_fixtures(
        universe, config, now_unix=now_unix, already_fired=ledger.fired_fixture_ids()
    )
    if limit is not None:
        due = due[:limit]
    summary["due"] = len(due)
    if not due:
        logger.info("no fixture has reached the T-%dh horizon this tick",
                    config.horizon_hours_before_kickoff)
        summary["finished_at_utc"] = _now_iso()
        return summary

    # 3. Fit once, so every forecast in this run shares one model_version.
    try:
        engine = ForecastEngine(config)
    except Exception as exc:  # noqa: BLE001
        logger.error("forecast engine unavailable: %s", exc)
        summary["errors"].append(f"engine_unavailable: {exc}")
        summary["finished_at_utc"] = _now_iso()
        return summary
    summary["model_version"] = engine.model_version
    summary["data_cutoff_utc"] = engine.data_cutoff_utc

    price_requests_used = 0
    store = pp.PriceCaptureStore()

    # A dry run never calls the metered odds provider. Reported as skipped rather
    # than counted as a price gap, because no capture was attempted.
    capture_prices_now = capture_prices and not dry_run
    summary["price_capture"] = (
        "enabled" if capture_prices_now
        else ("skipped: dry run" if capture_prices else "disabled: --no-price-capture")
    )

    for fixture_id, info in due:
        kickoff = float(info["ts"])
        home = str(info.get("home") or "")
        away = str(info.get("away") or "")

        # A forecast published after kickoff is not a pre-kickoff forecast. It is
        # recorded as a missed horizon and never backdated.
        if now_unix >= kickoff:
            reason = (
                "horizon missed: the fixture had already kicked off when the "
                "scheduler evaluated it; a pre-kickoff forecast cannot be "
                "backdated"
            )
            logger.error("fixture %s (%s vs %s): %s", fixture_id, home, away, reason)
            summary["missed_horizon_past_kickoff"] += 1
            summary["not_published"] += 1
            if not dry_run:
                ledger.append_not_published(
                    fixture_id=fixture_id, comp_id=info.get("comp"),
                    kickoff_unix=kickoff, reason=reason,
                    scope_version_hash=config.scope_version_hash,
                )
            continue

        generated_at = _now_iso()
        probs, reasons = engine.probabilities(
            home_team=home, away_team=away, kickoff_unix=kickoff
        )

        if not any(p is not None for p in probs.values()):
            reason = "no declared market could be priced: " + "; ".join(
                sorted(set(reasons.values()))
            )
            logger.warning("fixture %s (%s vs %s): %s", fixture_id, home, away, reason)
            summary["not_published"] += 1
            if not dry_run:
                ledger.append_not_published(
                    fixture_id=fixture_id, comp_id=info.get("comp"),
                    kickoff_unix=kickoff, reason=reason,
                    scope_version_hash=config.scope_version_hash,
                )
            continue

        payload = build_forecast_payload(
            config=config,
            fixture_id=fixture_id,
            comp_id=info.get("comp"),
            home_team=home,
            away_team=away,
            kickoff_unix=kickoff,
            probabilities=probs,
            unavailable_reasons=reasons,
            model_version=engine.model_version,
            data_cutoff_utc=engine.data_cutoff_utc,
            generated_at_utc=generated_at,
        )
        commitment = payload.commitment_hash()

        # 4. Hash and record BEFORE sending, so a crash mid-send cannot lose the
        #    commitment, and the message can always be checked against the record.
        if not dry_run:
            ledger.append_commitment(payload)
        summary["committed"] += 1

        # 5. The content gate. A message that fails it is not sent, and the refusal
        #    is recorded rather than swallowed.
        try:
            message = render_checked_message(payload, config)
        except ForecastContentError as exc:
            summary["content_gate_blocked"] += 1
            summary["errors"].append(f"{fixture_id}: content_gate: {exc}")
            if not dry_run:
                deliverer.log_content_gate_block(
                    commitment_hash=commitment, fixture_id=fixture_id,
                    reason=str(exc), generated_at_utc=generated_at,
                )
            continue

        if dry_run:
            print(message)
            print("-" * 70)
        else:
            outcome = deliverer.deliver(
                commitment_hash=commitment,
                fixture_id=fixture_id,
                generated_at_utc=payload.generated_at_utc,
                kickoff_unix=payload.kickoff_unix,
                message=message,
            )
            if outcome.status is DeliveryStatus.SENT:
                summary["sent"] += 1
            elif outcome.status is DeliveryStatus.QUEUED_QUIET_HOURS:
                summary["queued_quiet_hours"] += 1
            else:
                summary["delivery_failed"] += 1
                summary["errors"].append(f"{fixture_id}: delivery: {outcome.detail}")

        # 6. Price capture — separate store, separate timing record, no feedback into
        #    the forecast above (which is already hashed and committed).
        if not capture_prices_now:
            continue
        if price_requests_used >= PRICE_REQUEST_CAP:
            summary["price_gaps"] += 1
            log_price_gap(
                fixture_id=fixture_id, kickoff_unix=kickoff,
                reason=f"price request cap {PRICE_REQUEST_CAP} reached this run "
                       "(forecast was still published)",
                dry_run=dry_run,
            )
            continue
        price_requests_used += 1
        written, detail = capture_prices_for_fixture(
            fixture_id=fixture_id, kickoff_unix=kickoff, config=config,
            store=store, dry_run=dry_run,
        )
        summary["price_rows_written"] += written
        if written == 0:
            summary["price_gaps"] += 1
            log_price_gap(
                fixture_id=fixture_id, kickoff_unix=kickoff,
                reason=detail, dry_run=dry_run,
            )

    summary["finished_at_utc"] = _now_iso()
    return summary


def coverage(config: ScopeConfig, *, record_root: Path = DEFAULT_RECORD_ROOT) -> dict:
    """Audit the record against declared scope for every past horizon moment."""
    ledger = BroadcastLedger(record_root)
    universe = load_fixture_universe()
    now_unix = time.time()
    expected = [
        fid for fid, info in universe.items()
        if config.is_in_scope(info.get("comp"))
        and _kickoff_or_none(info) is not None
        and now_unix >= float(info["ts"]) - config.horizon_seconds
    ]
    report = ledger.coverage_report(
        scope_version_hash=config.scope_version_hash,
        expected_fixture_ids=expected,
    )
    out = report.to_dict()
    out["altered_commitment_hashes"] = list(ledger.verify_commitment_hashes())
    out["queue_pending"] = len(PendingQueue(Path(record_root) / QUEUE_NAME))
    return out


def _kickoff_or_none(info: dict) -> Optional[float]:
    try:
        return float(info["ts"])
    except (KeyError, TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="render and print messages; send nothing, write nothing")
    parser.add_argument("--coverage", action="store_true",
                        help="audit the record against declared scope and exit")
    parser.add_argument("--record-scope-change", action="store_true",
                        help="bring the current scope file into effect")
    parser.add_argument("--reason", default="",
                        help="why scope changed (required with --record-scope-change)")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap fixtures processed this run (operational recovery "
                             "only; leaves the rest due next tick, never skipped)")
    parser.add_argument("--no-price-capture", action="store_true",
                        help="skip the separate CLV panel price capture")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="forecast_broadcast: %(levelname)s %(message)s",
    )
    load_env()

    config_path = Path(args.config)

    if args.record_scope_change:
        try:
            candidate = load_scope_config(
                config_path, require_recorded_change=False
            )
            record = record_scope_change(candidate, args.reason)
        except ScopeConfigError as exc:
            print(f"scope change refused: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(record, indent=2, sort_keys=True, default=str))
        return 0

    try:
        config = load_scope_config(config_path)
    except ScopeChangeUnrecorded as exc:
        print(f"REFUSING TO RUN: {exc}", file=sys.stderr)
        return 3
    except ScopeConfigError as exc:
        print(f"REFUSING TO RUN: invalid scope config: {exc}", file=sys.stderr)
        return 2

    if args.coverage:
        report = coverage(config)
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 0 if report["is_complete"] else 1

    summary = run(
        config=config,
        dry_run=args.dry_run,
        capture_prices=not args.no_price_capture,
        limit=args.limit,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
