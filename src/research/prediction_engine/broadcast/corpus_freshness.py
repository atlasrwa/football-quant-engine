"""The freshness gate — refuse to publish forecasts from an out-of-date corpus.

WHAT THIS GUARDS
================
On 2026-09-05 the engine published 16 forecasts whose newest training observation
was 2026-05-31. Every rolling "recent form" window was last season's final matches:
different squads, in some cases different managers, and a different competitive
context. A five-match window that is actually last season's last five is not a stale
feature, it is a different feature measuring something else.

Nothing was broken in the sense of raising. The loader returned rows, the fit
converged, the payload carried ``data_cutoff_utc: 2026-05-31`` in plain text, and it
went out. The gap between "the record contained the evidence" and "anything checked
it" is what this module closes.

THE GATE BLOCKS; IT DOES NOT DEGRADE
====================================
:func:`evaluate_corpus_freshness` returns a verdict and :func:`require_fresh_corpus`
raises on it. There is deliberately no fallback path that publishes with a warning
attached, because that is the behaviour being fixed: the stale forecasts were, in
effect, a silent degradation. A blocked run leaves the fixture due on the next tick,
so the cost of a false block is a delay, while the cost of a false pass is a
published claim that cannot be withdrawn.

WHY THE THRESHOLD IS NOT JUST "48 HOURS OLD"
============================================
A fixed age limit is wrong twice a year. During an international break, off-season,
or winter shutdown there is legitimately no recent match, and a 48-hour rule would
alert every day for a fortnight — which trains operators to ignore it, reproducing
the silence it was meant to break. Disabling it for those weeks is worse: that is
precisely when a real ingestion break would slip through.

So the gate does not compare the corpus to the clock. It compares the corpus to
**what the fixture calendar says should already have been played**: the newest
in-scope fixture that has certainly finished. Concretely:

* Matches were played and we have them          -> ``FRESH``
* Matches were played and we do not have them   -> ``STALE``, publication refused
* No matches were due to be played              -> ``DORMANT``, publication allowed

Under that rule an international break is ``DORMANT`` or ``FRESH`` with a large lag
that is fully explained, and a broken ingestion job during a normal week is
``STALE`` on the first tick after the tolerance expires. The tolerance
(:data:`DEFAULT_MAX_LAG_HOURS`) exists only to absorb provider settlement delay, not
to excuse missing data.

``DORMANT`` is never silent. It is reported in the health report and carries its
reasoning, so "the gate did not fire" is always distinguishable from "the gate had
nothing to compare against".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional, Sequence

from src.research.prediction_engine.broadcast.corpus_snapshot import (
    MATCH_COMPLETION_SECONDS,
    CorpusFingerprint,
)

#: Contract for the verdict shape, so a persisted health report can be read later.
FRESHNESS_GATE_CONTRACT = "corpus-freshness-gate/v1"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


#: How far the corpus may lag behind the newest certainly-finished in-scope fixture
#: before publication is refused. Absorbs provider settlement delay and one missed
#: refresh tick; it is not an allowance for missing matches.
DEFAULT_MAX_LAG_HOURS = _env_float("FORECAST_CORPUS_MAX_LAG_HOURS", 48.0)

#: A fixture within this many days of now, in either direction, means the competition
#: is in season. Wide enough to span an international break (typically 8-12 days) plus
#: a winter break shoulder, so a break does not read as an off-season.
DEFAULT_SEASON_ACTIVE_WINDOW_DAYS = _env_float(
    "FORECAST_CORPUS_SEASON_WINDOW_DAYS", 28.0
)


class FreshnessState(str, Enum):
    """The three states the corpus can be in relative to the fixture calendar."""

    #: The corpus contains everything the calendar says has been played.
    FRESH = "FRESH"
    #: Matches have been played that the corpus does not contain. Blocks publication.
    STALE = "STALE"
    #: Nothing was due to be played. Publication allowed, and the reason is recorded.
    DORMANT = "DORMANT"


class CorpusFreshnessError(RuntimeError):
    """The corpus is too far behind the fixture calendar to publish from.

    Carries the verdict so the caller can put the metrics in the health report and
    the alert without re-deriving them from the message text.
    """

    def __init__(self, verdict: "FreshnessVerdict") -> None:
        super().__init__(verdict.detail)
        self.verdict = verdict


@dataclass(frozen=True, slots=True)
class FreshnessVerdict:
    """The gate's decision, with everything needed to explain or alert on it."""

    state: FreshnessState
    may_publish: bool
    detail: str
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def is_stale(self) -> bool:
        return self.state is FreshnessState.STALE

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_contract": FRESHNESS_GATE_CONTRACT,
            "state": self.state.value,
            "may_publish": self.may_publish,
            "detail": self.detail,
            "metrics": dict(self.metrics),
        }


def _iso(unix: float) -> str:
    return datetime.fromtimestamp(float(unix), timezone.utc).isoformat()


def in_scope_kickoffs(
    universe: dict[str, dict[str, Any]],
    is_in_scope,
) -> tuple[float, ...]:
    """Kick-offs of every in-scope fixture in the discovered universe.

    The gate's benchmark comes from here rather than from the corpus, which is the
    whole point: the fixture universe is refreshed on its own schedule by discovery,
    so it is an *independent* statement about what has been played. Checking the
    corpus against itself could never have detected this failure.

    Args:
        universe: the ``meta`` mapping from the discovered fixture list.
        is_in_scope: predicate over a competition id, normally
            ``ScopeConfig.is_in_scope``.

    Returns:
        Kick-offs as UTC epochs, ascending.
    """
    kickoffs: list[float] = []
    for info in universe.values():
        if not is_in_scope(info.get("comp")):
            continue
        try:
            kickoffs.append(float(info["ts"]))
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(sorted(kickoffs))


def evaluate_corpus_freshness(
    *,
    fingerprint: CorpusFingerprint,
    reference_kickoffs: Sequence[float],
    now_unix: float,
    max_lag_hours: float = DEFAULT_MAX_LAG_HOURS,
    season_active_window_days: float = DEFAULT_SEASON_ACTIVE_WINDOW_DAYS,
    completion_seconds: int = MATCH_COMPLETION_SECONDS,
) -> FreshnessVerdict:
    """Decide whether the corpus is current enough to publish forecasts from.

    Args:
        fingerprint: content identity and coverage of the snapshot about to be used.
        reference_kickoffs: in-scope fixture kick-offs from the discovered universe,
            past and future. This is the independent calendar the corpus is judged
            against.
        now_unix: the moment being evaluated.
        max_lag_hours: tolerated lag behind the newest finished in-scope fixture.
        season_active_window_days: a fixture this close, either side of now, means
            the competition is in season.
        completion_seconds: how long after kick-off a match is certainly finished.

    Returns:
        The verdict. ``may_publish`` is ``False`` only for
        :attr:`FreshnessState.STALE`.
    """
    now = float(now_unix)
    max_lag_seconds = float(max_lag_hours) * 3600.0
    active_window_seconds = float(season_active_window_days) * 86400.0
    settled_before = now - float(completion_seconds)

    metrics: dict[str, Any] = {
        "evaluated_at_utc": _iso(now),
        "corpus_content_hash": fingerprint.content_hash,
        "corpus_match_count": fingerprint.match_count,
        "corpus_latest_observation_utc": fingerprint.latest_observation_utc,
        "corpus_seasons": list(fingerprint.seasons),
        "max_lag_hours": float(max_lag_hours),
        "season_active_window_days": float(season_active_window_days),
        "in_scope_fixtures_known": len(reference_kickoffs),
    }

    # An empty corpus is unconditionally refused. There is no calendar comparison to
    # make and no defensible forecast to publish from nothing.
    if fingerprint.match_count == 0:
        metrics["corpus_lag_hours"] = None
        return FreshnessVerdict(
            state=FreshnessState.STALE,
            may_publish=False,
            detail=(
                "corpus is empty: no completed match observations are available, so "
                "no forecast can be published"
            ),
            metrics=metrics,
        )

    latest = float(fingerprint.latest_observation_unix)
    metrics["corpus_age_hours"] = round((now - latest) / 3600.0, 2)

    in_season = [
        k
        for k in reference_kickoffs
        if now - active_window_seconds <= k <= now + active_window_seconds
    ]
    metrics["in_scope_fixtures_in_season_window"] = len(in_season)

    # No fixture anywhere near now: off-season, or the competition is not playing.
    # Nothing recent could have been ingested, so an old corpus is expected rather
    # than symptomatic. Reported, never silent.
    if not in_season:
        metrics["corpus_lag_hours"] = None
        metrics["benchmark"] = None
        return FreshnessVerdict(
            state=FreshnessState.DORMANT,
            may_publish=True,
            detail=(
                "no in-scope fixture within "
                f"{season_active_window_days:.0f} days of now, so no recent match "
                "could have been ingested; corpus newest observation "
                f"{fingerprint.latest_observation_utc} "
                f"({metrics['corpus_age_hours']}h old) is not evidence of an "
                "ingestion failure. Freshness could not be positively confirmed."
            ),
            metrics=metrics,
        )

    settled_past = [k for k in reference_kickoffs if k <= settled_before]
    if settled_past:
        benchmark = max(settled_past)
        benchmark_kind = "newest_finished_in_scope_fixture"
    else:
        # In season, but the known calendar contains nothing that has finished yet
        # (e.g. discovery only holds upcoming fixtures). Fall back to the clock so
        # this cannot become a hole the gate declines to look through.
        benchmark = settled_before
        benchmark_kind = "clock_fallback_no_finished_fixture_in_universe"

    lag_seconds = benchmark - latest
    metrics["benchmark"] = {
        "kind": benchmark_kind,
        "unix": int(benchmark),
        "utc": _iso(benchmark),
    }
    metrics["corpus_lag_hours"] = round(lag_seconds / 3600.0, 2)

    if lag_seconds <= max_lag_seconds:
        return FreshnessVerdict(
            state=FreshnessState.FRESH,
            may_publish=True,
            detail=(
                f"corpus newest observation {fingerprint.latest_observation_utc} is "
                f"{metrics['corpus_lag_hours']}h behind the newest finished in-scope "
                f"fixture ({_iso(benchmark)}), within the {max_lag_hours:.0f}h "
                "tolerance"
            ),
            metrics=metrics,
        )

    return FreshnessVerdict(
        state=FreshnessState.STALE,
        may_publish=False,
        detail=(
            "CORPUS IS STALE: newest training observation is "
            f"{fingerprint.latest_observation_utc} but in-scope fixtures have been "
            f"played as recently as {_iso(benchmark)} — a lag of "
            f"{metrics['corpus_lag_hours']}h against a {max_lag_hours:.0f}h "
            "tolerance. Rolling form features would describe a period that has "
            "already been superseded, so publication is refused. Run the corpus "
            "refresh (scripts/refresh_corpus.py) and retry; the fixtures stay due."
        ),
        metrics=metrics,
    )


def require_fresh_corpus(
    *,
    fingerprint: CorpusFingerprint,
    reference_kickoffs: Sequence[float],
    now_unix: float,
    max_lag_hours: float = DEFAULT_MAX_LAG_HOURS,
    season_active_window_days: float = DEFAULT_SEASON_ACTIVE_WINDOW_DAYS,
) -> FreshnessVerdict:
    """Evaluate the gate and raise if the corpus is stale.

    Returns:
        The verdict, when publication is permitted. ``DORMANT`` is returned rather
        than raised so the caller can surface the unconfirmed state.

    Raises:
        CorpusFreshnessError: when the verdict is :attr:`FreshnessState.STALE`.
    """
    verdict = evaluate_corpus_freshness(
        fingerprint=fingerprint,
        reference_kickoffs=reference_kickoffs,
        now_unix=now_unix,
        max_lag_hours=max_lag_hours,
        season_active_window_days=season_active_window_days,
    )
    if not verdict.may_publish:
        raise CorpusFreshnessError(verdict)
    return verdict
