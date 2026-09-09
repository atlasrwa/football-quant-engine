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
3. Refreshes the training corpus with completed current-season matches, then checks it
   against the fixture calendar. A corpus that lags what has actually been played
   blocks the whole run — see ``corpus_freshness``. The refresh is a phase here rather
   than a separate cron entry so it cannot fall behind the run that depends on it.
4. For each fixture, computes the engine probability for every declared market cell,
   states both sides, hashes the payload, records the commitment append-only, gates the
   rendered message, and delivers it.
5. Independently captures available prices for the same markets into the CLV panel
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
from typing import Any, Optional, Sequence

warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

from src.research.prediction_engine.broadcast import price_panel as pp
from src.research.prediction_engine.broadcast.corpus_freshness import (
    CorpusFreshnessError,
    FreshnessState,
    FreshnessVerdict,
    in_scope_kickoffs,
    require_fresh_corpus,
)
from src.research.prediction_engine.broadcast.corpus_snapshot import (
    CorpusFingerprint,
    CorpusIntegrityError,
    SameMatchLeakageError,
    assert_fixture_absent_from_history,
    build_snapshot,
    newest_observation_per_team,
    observations_per_season,
)
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
from src.research.prediction_engine.evaluation_window import (
    EvaluationWindowError,
    open_window,
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
MODEL_VERSION_CONTRACT = "forecast-broadcast-model/v2"

#: Where the run states what the freshness gate decided. Written on every run,
#: including clean ones, because a health report that only appears on failure cannot
#: be distinguished from a monitor that stopped running — the F024 lesson.
HEALTH_REPORT = DEFAULT_RECORD_ROOT / "health_report.json"

#: Minimum gap between corpus refreshes attempted by the broadcast run. The run ticks
#: every 15 minutes; refreshing on every tick would spend provider quota to re-fetch
#: seasons that gain matches a few times a week. A stale-corpus verdict overrides this
#: interval, so the throttle can delay a routine refresh but can never suppress the
#: one that a blocked run needs.
CORPUS_REFRESH_MIN_INTERVAL_MINUTES = float(
    os.environ.get("FORECAST_CORPUS_REFRESH_INTERVAL_MINUTES", "180")
)

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
def _evaluate_freshness_only(
    fingerprint: CorpusFingerprint,
    reference_kickoffs: Sequence[float],
    now_unix: float,
) -> FreshnessVerdict:
    """Evaluate the gate without enforcing it, for research callers.

    Kept as a named function rather than a boolean branch inside the engine so that
    the non-enforcing path is grep-able. A silent way to switch the gate off is how
    gates die.
    """
    from src.research.prediction_engine.broadcast.corpus_freshness import (
        evaluate_corpus_freshness,
    )

    return evaluate_corpus_freshness(
        fingerprint=fingerprint,
        reference_kickoffs=reference_kickoffs,
        now_unix=now_unix,
    )


def emit_health_report(
    report: dict[str, Any], *, path: Path = HEALTH_REPORT, dry_run: bool = False
) -> None:
    """Write the run's health report, overwriting the previous one.

    Overwrite rather than append: this file answers "what is the state right now",
    and the durable history lives in the append-only ledger. The heartbeat reads it
    and alerts on both its content and its age, so a run that stops writing it is
    itself an alertable condition.
    """
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def alert_operator(title: str, detail: str, *, dry_run: bool = False) -> bool:
    """Send an operational alert to the monitoring channel.

    Used for conditions that block publication. A blocked run that alerted nobody is
    the failure mode this whole change exists to remove, so the send is attempted
    even though the health report and the log already carry the same information —
    three independent surfaces, because each has failed alone before.

    Returns:
        ``True`` if the alert was delivered.
    """
    if dry_run:
        return False
    token = os.environ.get("HEARTBEAT_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("HEARTBEAT_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.error(
            "cannot alert: HEARTBEAT_TELEGRAM_BOT_TOKEN/CHAT_ID not configured. "
            "Alert was: %s — %s", title, detail,
        )
        return False
    import urllib.error
    import urllib.parse
    import urllib.request

    body = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": f"\u26d4 {title}\n\n{detail}",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        # The alert transport failing must not mask the condition being alerted on.
        logger.error("alert delivery failed (%s). Alert was: %s — %s",
                     exc, title, detail)
        return False


def ensure_corpus_current(
    *,
    config: ScopeConfig,
    universe: dict[str, dict[str, Any]],
    now_unix: float,
    dry_run: bool,
) -> dict[str, Any]:
    """Bring the training corpus up to date before anything is fitted or published.

    This runs as a phase of the broadcast rather than on its own schedule. An
    independently scheduled refresh can lag the thing it feeds — if the refresh cron
    slips, is disabled, or simply runs after the broadcast on a given day, the
    broadcast fits on yesterday's corpus and nothing says so. Making it a phase makes
    the ordering a property of the code instead of a property of two crontab lines
    that have to stay in the right order forever.

    Refresh is attempted when either:

    * the last refresh is older than :data:`CORPUS_REFRESH_MIN_INTERVAL_MINUTES`, or
    * the corpus is currently stale against the fixture calendar.

    The second condition is what makes the throttle safe. A time-based interval alone
    would mean a blocked run waits out the interval before it may even try to fix
    itself; here a stale verdict always earns an immediate attempt.

    Returns:
        A phase report for the run summary. Never raises: a refresh failure must not
        stop the run, because the freshness gate downstream is what decides whether
        the resulting corpus may be published from. Letting an exception escape here
        would conflate "could not fetch" with "must not publish".
    """
    import pilotC_stat_mixer as mix
    from src.research.prediction_engine.broadcast.corpus_freshness import (
        evaluate_corpus_freshness,
    )
    from src.research.prediction_engine.broadcast.corpus_snapshot import (
        fingerprint_matches,
    )

    phase: dict[str, Any] = {"attempted": False, "reason": "", "api_requests": 0}

    try:
        import refresh_corpus
    except Exception as exc:  # noqa: BLE001
        phase["reason"] = f"refresh module unavailable: {type(exc).__name__}: {exc}"
        logger.error("corpus refresh unavailable: %s", exc)
        return phase

    before = fingerprint_matches(mix.load_corpus())
    verdict = evaluate_corpus_freshness(
        fingerprint=before,
        reference_kickoffs=in_scope_kickoffs(universe, config.is_in_scope),
        now_unix=now_unix,
    )
    phase["freshness_before"] = verdict.state.value

    last_refresh_age_minutes: Optional[float] = None
    report_path = refresh_corpus.REFRESH_REPORT
    if report_path.exists():
        try:
            previous = json.loads(report_path.read_text(encoding="utf-8"))
            finished = datetime.fromisoformat(str(previous["finished_at_utc"]))
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=timezone.utc)
            last_refresh_age_minutes = (
                now_unix - finished.timestamp()
            ) / 60.0
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            # An unreadable previous report is treated as no report: refresh.
            last_refresh_age_minutes = None
    phase["last_refresh_age_minutes"] = (
        round(last_refresh_age_minutes, 1)
        if last_refresh_age_minutes is not None else None
    )

    due_by_interval = (
        last_refresh_age_minutes is None
        or last_refresh_age_minutes >= CORPUS_REFRESH_MIN_INTERVAL_MINUTES
    )
    if verdict.is_stale:
        phase["reason"] = f"corpus is {verdict.state.value}; refresh forced"
    elif due_by_interval:
        phase["reason"] = (
            f"last refresh {phase['last_refresh_age_minutes']}min ago, interval "
            f"{CORPUS_REFRESH_MIN_INTERVAL_MINUTES:.0f}min"
        )
    else:
        phase["reason"] = (
            f"corpus {verdict.state.value} and refreshed "
            f"{phase['last_refresh_age_minutes']}min ago; skipped"
        )
        return phase

    if dry_run:
        phase["reason"] += " (dry run: no fetch)"
        return phase

    phase["attempted"] = True
    try:
        report = refresh_corpus.refresh(all_leagues=False)
    except Exception as exc:  # noqa: BLE001
        phase["error"] = f"{type(exc).__name__}: {exc}"
        logger.error("corpus refresh failed: %s", exc)
        return phase

    phase["api_requests"] = report.get("api_requests", 0)
    phase["matches_added"] = report.get("matches_added")
    phase["corpus_changed"] = report.get("corpus_changed")
    phase["refresh_errors"] = report.get("errors") or []
    if phase["refresh_errors"]:
        # Surfaced, not swallowed. The gate still decides publication, but a partial
        # refresh has to be visible in the run summary and the health report.
        logger.error("corpus refresh reported errors: %s", phase["refresh_errors"])
    logger.info(
        "corpus refresh: %s match(es) added, %d API request(s), changed=%s",
        phase.get("matches_added"), phase["api_requests"], phase.get("corpus_changed"),
    )
    return phase


class ForecastEngine:
    """The declared market cells, fitted once per run, plus their provenance.

    Fitting is done once and reused for every fixture in the run so that every
    forecast published by a run carries the same ``model_version`` and the same
    ``data_cutoff_utc``.

    Construction order is deliberate and load-bearing:

    1. Freeze the corpus at an explicit cutoff and fingerprint it.
    2. Run the freshness gate.
    3. Only then fit.

    The gate precedes the fit so that a stale corpus never produces a fitted model at
    all. If fitting came first there would be a usable model sitting in memory next to
    a failed gate, and the next edit to this file could plausibly publish from it.
    """

    def __init__(
        self,
        config: ScopeConfig,
        *,
        reference_kickoffs: Sequence[float] = (),
        snapshot_cutoff_unix: Optional[float] = None,
        enforce_freshness: bool = True,
    ) -> None:
        """Fit the declared cells on a frozen, freshness-checked corpus snapshot.

        Args:
            config: the declared scope in force.
            reference_kickoffs: in-scope fixture kick-offs from the discovered
                universe. The freshness gate's independent benchmark.
            snapshot_cutoff_unix: the corpus boundary. Defaults to now. Only matches
                that had certainly finished before it enter the snapshot.
            enforce_freshness: when ``False`` the gate is evaluated and reported but
                does not raise. Reserved for research and backtest callers that are
                deliberately reconstructing a historical corpus state; the scheduled
                path never sets it.

        Raises:
            CorpusFreshnessError: the corpus is stale relative to the calendar.
            CorpusIntegrityError: the snapshot contains a match that had not finished.
            ScopeConfigError: a declared cell has no frozen model.
        """
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

        # 1. Freeze. The cutoff is recorded rather than implied by when the directory
        #    happened to be read, and the snapshot is immutable so nothing can be
        #    appended to the training set after it was fingerprinted.
        self._snapshot_cutoff_unix = (
            float(snapshot_cutoff_unix) if snapshot_cutoff_unix is not None
            else time.time()
        )
        snapshot, fingerprint = build_snapshot(
            mix.load_corpus(), cutoff_unix=self._snapshot_cutoff_unix
        )
        self._fingerprint = fingerprint
        self._season_coverage = observations_per_season(snapshot)
        self._data_cutoff_unix = float(fingerprint.latest_observation_unix)
        self._n_matches = fingerprint.match_count

        # 2. Gate. Raises before any model exists.
        self._freshness = require_fresh_corpus(
            fingerprint=fingerprint,
            reference_kickoffs=reference_kickoffs,
            now_unix=self._snapshot_cutoff_unix,
        ) if enforce_freshness else _evaluate_freshness_only(
            fingerprint, reference_kickoffs, self._snapshot_cutoff_unix
        )
        if self._freshness.state is FreshnessState.DORMANT:
            logger.warning(
                "corpus freshness could not be positively confirmed: %s",
                self._freshness.detail,
            )
        else:
            logger.info("corpus freshness: %s", self._freshness.detail)

        self._hist = mix.build_histories(list(snapshot))

        # 3. Fit.
        logger.info(
            "fitting %d declared market cell(s) on %d corpus matches "
            "(cutoff %s, content %s)",
            len(config.markets), self._n_matches, self.data_cutoff_utc,
            fingerprint.content_hash[:12],
        )
        self._models: dict[tuple[str, Optional[float]], Any] = {}
        for spec in config.markets:
            C, l1r = saved[spec.cell]
            self._models[spec.cell] = fp.fit_full(
                list(snapshot), self._hist, spec.market, spec.line, C, l1r
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
                # The corpus is identified by the observations it contains, not by how
                # many there were and when they stopped. A count-and-cutoff pair
                # cannot distinguish two corpora that swapped one match for another
                # of the same date; the content hash can.
                "corpus_content_hash": fingerprint.content_hash,
                "corpus_n_matches": self._n_matches,
                "data_cutoff_unix": int(self._data_cutoff_unix),
            }
        )

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def fingerprint(self) -> CorpusFingerprint:
        return self._fingerprint

    @property
    def freshness(self) -> FreshnessVerdict:
        return self._freshness

    @property
    def season_coverage(self) -> dict[str, dict[str, Any]]:
        return self._season_coverage

    @property
    def snapshot_cutoff_utc(self) -> str:
        return datetime.fromtimestamp(
            self._snapshot_cutoff_unix, timezone.utc
        ).isoformat()

    @property
    def data_cutoff_utc(self) -> str:
        return datetime.fromtimestamp(
            self._data_cutoff_unix, timezone.utc
        ).isoformat()

    def corpus_provenance(self) -> dict[str, Any]:
        """The corpus provenance block published with every forecast."""
        return self._fingerprint.provenance_dict()

    def newest_observations(self, *teams: str) -> dict[str, Optional[dict[str, Any]]]:
        """The newest corpus match for each named team.

        Lets an operator or a verification run answer "what is the engine treating as
        this team's recent form" directly, instead of inferring it from the aggregate
        cutoff. The stale corpus was invisible partly because that question had no
        cheap answer.
        """
        return newest_observation_per_team(self._hist, teams)

    def probabilities(
        self, *, home_team: str, away_team: str, kickoff_unix: float
    ) -> tuple[
        dict[tuple[str, Optional[float]], Optional[float]],
        dict[tuple[str, Optional[float]], str],
        dict[str, Any],
    ]:
        """Engine ``P(over line)`` for every declared cell, the reasons for gaps, and
        the per-fixture history provenance.

        Only declared cells are computed — the loop iterates the config, so no market
        or line outside declared scope can enter a payload.

        Features are point-in-time by construction: ``match_features`` reads only
        history strictly before the fixture's kickoff. That inequality is asserted
        here rather than assumed, because it is the one convention in this pipeline
        whose violation is both invisible in the output and fatal to the claim.

        The minimum-history gate runs before any cell is priced: a team below
        ``pilotC_stat_mixer.MIN_CURRENT_SEASON_MATCHES`` completed current-season
        matches has no trustworthy current-season form, so every cell abstains and the
        reason names the thin side. This is the interim protection for early-season
        fixtures — the rolling windows themselves already refuse to backfill from a
        prior season, so a thin team yields ``None`` per window rather than a form
        figure that is mostly last season. The history provenance is returned either
        way, so a forecast built on three matches is distinguishable in the record
        from one built on ten.
        """
        # Structural refusal, not a filter: if this fixture's own result is already
        # in the corpus, no probability is produced for it at all.
        assert_fixture_absent_from_history(
            self._hist,
            home_team=home_team,
            away_team=away_team,
            kickoff_unix=kickoff_unix,
        )
        history = self._mix.history_provenance(
            self._hist, home_team, away_team, kickoff_unix
        )
        probs: dict[tuple[str, Optional[float]], Optional[float]] = {}
        reasons: dict[tuple[str, Optional[float]], str] = {}

        # Minimum-history gate. Below the floor for either team, the fixture is not
        # priced: an early-season side with too few completed matches has no
        # current-season form to estimate, and borrowing last season's is the failure
        # this whole change exists to prevent.
        if not history["sufficient"]:
            thin = [
                f"{team} ({side['current_season_matches']} completed "
                f"current-season match(es))"
                for team, side in (("home", history["home"]), ("away", history["away"]))
                if not side["meets_min_history"]
            ]
            reason = (
                "insufficient current-season history (minimum "
                f"{history['min_current_season_matches']} per team): "
                + "; ".join(thin)
                + ". Rolling form would otherwise rest on a prior season."
            )
            for spec in self._config.markets:
                probs[spec.cell] = None
                reasons[spec.cell] = reason
            return probs, reasons, history

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
        return probs, reasons, history


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
def _health_report(
    summary: dict[str, Any],
    config: ScopeConfig,
    *,
    engine: Optional["ForecastEngine"],
    verdict: Optional[FreshnessVerdict],
) -> dict[str, Any]:
    """Assemble the machine-readable health report for one run.

    Includes the freshness verdict on success as well as failure. A report that only
    carries the gate's decision when it fails cannot distinguish "the gate passed"
    from "the gate was removed", and that distinction is the entire point.
    """
    gate = None
    if verdict is not None:
        gate = verdict.to_dict()
    elif engine is not None:
        gate = engine.freshness.to_dict()
    report: dict[str, Any] = {
        "report_contract": "forecast-broadcast-health/v1",
        "generated_at_utc": _now_iso(),
        "scope_version_hash": config.scope_version_hash,
        "freshness_gate": gate,
        "publication_blocked": bool(gate and not gate.get("may_publish", True)),
        "run_summary": {
            key: summary.get(key)
            for key in (
                "started_at_utc", "finished_at_utc", "due", "committed", "sent",
                "not_published", "blocked_by_freshness_gate",
                "same_match_leakage_refused", "insufficient_current_season_history",
                "content_gate_blocked",
                "delivery_failed", "queued_quiet_hours", "model_version",
                "data_cutoff_utc",
            )
        },
        "errors": list(summary.get("errors") or []),
        "corpus_refresh": summary.get("corpus_refresh"),
    }
    if engine is not None:
        report["corpus_provenance"] = engine.corpus_provenance()
        report["corpus_season_coverage"] = engine.season_coverage
        report["snapshot_cutoff_utc"] = engine.snapshot_cutoff_utc
    return report


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
        "blocked_by_freshness_gate": 0,
        "same_match_leakage_refused": 0,
        "insufficient_current_season_history": 0,
        "missed_horizon_past_kickoff": 0,
        "price_rows_written": 0,
        "price_gaps": 0,
        "errors": [],
    }

    ledger = BroadcastLedger(record_root)
    queue = PendingQueue(Path(record_root) / QUEUE_NAME)
    # DATA ACCUMULATION MODE: still compute + commit + record forecasts, but do
    # NOT transmit them to the public channel. Routing delivery to a recording
    # transport preserves the append-only forecast record and the full capability
    # while withholding external publication (SUPPRESSED_RESEARCH_ONLY). Reversible
    # via the DATA_ACCUMULATION_MODE env var at a future promotion decision.
    from src.research._data_accumulation_mode import (
        SUPPRESSED_RESEARCH_ONLY,
        is_data_accumulation_mode,
    )

    suppressed = is_data_accumulation_mode()
    if dry_run:
        transport = RecordingTransport()
    elif suppressed:
        transport = RecordingTransport(ok=True, detail=SUPPRESSED_RESEARCH_ONLY)
        logger.warning(
            "DATA_ACCUMULATION_MODE active: forecasts are computed and committed "
            "to the ledger but NOT transmitted (routed to %s). Set "
            "DATA_ACCUMULATION_MODE=0 to re-enable publication after a promotion "
            "decision.", SUPPRESSED_RESEARCH_ONLY,
        )
    else:
        transport = TelegramTransport()
    summary["publication_suppressed"] = bool(suppressed and not dry_run)
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

    # 3. Refresh the corpus, then fit once so every forecast in this run shares one
    #    model_version. The freshness gate runs inside the engine, before the fit, and
    #    blocks the entire run rather than degrading to stale features per fixture.
    summary["corpus_refresh"] = ensure_corpus_current(
        config=config, universe=universe, now_unix=now_unix, dry_run=dry_run
    )
    reference_kickoffs = in_scope_kickoffs(universe, config.is_in_scope)
    try:
        engine = ForecastEngine(
            config,
            reference_kickoffs=reference_kickoffs,
            snapshot_cutoff_unix=now_unix,
        )
    except CorpusFreshnessError as exc:
        verdict = exc.verdict
        logger.error("FRESHNESS GATE: %s", verdict.detail)
        summary["errors"].append(f"corpus_freshness_gate: {verdict.detail}")
        summary["freshness_gate"] = verdict.to_dict()
        summary["blocked_by_freshness_gate"] = len(due)
        summary["not_published"] += len(due)
        summary["finished_at_utc"] = _now_iso()
        # Every due fixture is recorded as not published with the gate's reasoning.
        # Without this the run would leave a coverage hole indistinguishable from
        # fixtures that were never in scope — the ambiguity that let the stale
        # corpus go unnoticed.
        if not dry_run:
            for fixture_id, info in due:
                ledger.append_not_published(
                    fixture_id=fixture_id,
                    comp_id=info.get("comp"),
                    kickoff_unix=_kickoff_or_none(info) or 0.0,
                    reason=f"corpus freshness gate refused publication: "
                           f"{verdict.detail}",
                    scope_version_hash=config.scope_version_hash,
                )
        emit_health_report(
            _health_report(summary, config, engine=None, verdict=verdict),
            dry_run=dry_run,
        )
        summary["alert_sent"] = alert_operator(
            "Forecast broadcast BLOCKED — corpus freshness gate",
            f"{verdict.detail}\n\n"
            f"{len(due)} due fixture(s) were not published and remain due.\n"
            f"corpus newest observation: "
            f"{verdict.metrics.get('corpus_latest_observation_utc')}\n"
            f"lag: {verdict.metrics.get('corpus_lag_hours')}h",
            dry_run=dry_run,
        )
        return summary
    except CorpusIntegrityError as exc:
        logger.error("CORPUS INTEGRITY: %s", exc)
        summary["errors"].append(f"corpus_integrity: {exc}")
        summary["finished_at_utc"] = _now_iso()
        emit_health_report(
            _health_report(summary, config, engine=None, verdict=None),
            dry_run=dry_run,
        )
        summary["alert_sent"] = alert_operator(
            "Forecast broadcast BLOCKED — corpus integrity", str(exc),
            dry_run=dry_run,
        )
        return summary
    except Exception as exc:  # noqa: BLE001
        logger.error("forecast engine unavailable: %s", exc)
        summary["errors"].append(f"engine_unavailable: {exc}")
        summary["finished_at_utc"] = _now_iso()
        emit_health_report(
            _health_report(summary, config, engine=None, verdict=None),
            dry_run=dry_run,
        )
        return summary
    summary["model_version"] = engine.model_version
    summary["data_cutoff_utc"] = engine.data_cutoff_utc
    summary["freshness_gate"] = engine.freshness.to_dict()
    summary["corpus_provenance"] = engine.corpus_provenance()

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
        try:
            probs, reasons, history = engine.probabilities(
                home_team=home, away_team=away, kickoff_unix=kickoff
            )
        except SameMatchLeakageError as exc:
            # The fixture's own result is already in the corpus. This is not a
            # "no features" case to be recorded and moved past quietly: it means the
            # corpus and the fixture universe disagree about whether this match has
            # been played, and a probability produced here would be a postdiction.
            logger.error("fixture %s: %s", fixture_id, exc)
            summary["same_match_leakage_refused"] += 1
            summary["not_published"] += 1
            summary["errors"].append(f"{fixture_id}: same_match_leakage: {exc}")
            if not dry_run:
                ledger.append_not_published(
                    fixture_id=fixture_id, comp_id=info.get("comp"),
                    kickoff_unix=kickoff, reason=f"same-match leakage refused: {exc}",
                    scope_version_hash=config.scope_version_hash,
                )
            continue

        if not any(p is not None for p in probs.values()):
            reason = "no declared market could be priced: " + "; ".join(
                sorted(set(reasons.values()))
            )
            logger.warning("fixture %s (%s vs %s): %s", fixture_id, home, away, reason)
            summary["not_published"] += 1
            if not history.get("sufficient", True):
                # Distinguished from a generic "no features" outcome: this fixture was
                # withheld specifically because a team is too early in its season for a
                # trustworthy current-season form, which is the early-season protection
                # working, not a data gap.
                summary["insufficient_current_season_history"] += 1
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
            corpus_provenance=engine.corpus_provenance(),
            history_provenance=history,
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
                # The 30-day evaluation window opens on the first forecast
                # actually delivered on the corrected corpus, and never moves
                # afterwards. Everything published before that instant was built
                # on the stale corpus and is excluded from the record. This is
                # idempotent and deliberately non-fatal: failing to mark the epoch
                # must not stop a forecast going out, but it must be visible.
                try:
                    window = open_window(
                        commitment_hash=commitment,
                        generated_at_utc=payload.generated_at_utc,
                        generated_at_unix=int(
                            datetime.fromisoformat(
                                payload.generated_at_utc
                            ).timestamp()
                        ),
                        model_version=payload.model_version,
                        corpus_content_hash=(
                            payload.corpus_provenance or {}
                        ).get("corpus_content_hash"),
                    )
                    summary["evaluation_window_epoch"] = window.epoch_commitment_hash
                    summary["evaluation_window_closes_utc"] = window.closes_at_utc
                except (EvaluationWindowError, OSError, ValueError) as exc:
                    summary["errors"].append(f"{fixture_id}: evaluation_window: {exc}")
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
    emit_health_report(
        _health_report(summary, config, engine=engine, verdict=None), dry_run=dry_run
    )
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
