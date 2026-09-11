"""Research-status Telegram notifications for DATA ACCUMULATION MODE.

During data accumulation the Telegram channel is an OPERATIONAL / RESEARCH
observability interface, NOT a betting-tip feed. This module composes compact
status messages from ALREADY-PERSISTED operational and research state
(scheduler-health ops log, the price-discovery dataset, analysis-support
strata, the coverage-matrix artifact). It never calls TheStatsAPI — populating
Telegram must not consume provider quota.

What it may communicate:
    what the engine has observed, whether the pipeline is healthy, how close
    research is to being evaluable, and when a legitimate study may begin.

What it must NEVER communicate (enforced by ``assert_no_signal_content``):
    bet recommendations, value bets, stakes, ROI, "strong signal", "lock",
    raw champion probabilities framed as tips, or fundamental-vs-market
    disagreement framed as alpha.

Message types (active): ENGINE_HEALTH, DATA_PROGRESS, RESEARCH_MILESTONE,
READINESS_TRANSITION, CRITICAL_ALERT, WEEKLY_SUMMARY.
Reserved (NOT activated — require a future promotion gate): VALIDATED_SIGNAL,
STRATEGY_ACTION. Emitting either raises.

Transport reuses :class:`TelegramTransport` from the forecast-broadcast path.
Telegram failure is isolated: capture/ops state is persisted independently and
a send failure only records a failed notification, never affects the collector.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------


class MessageType(str, Enum):
    # active during data accumulation
    ENGINE_HEALTH = "ENGINE_HEALTH"
    DATA_PROGRESS = "DATA_PROGRESS"
    RESEARCH_MILESTONE = "RESEARCH_MILESTONE"
    READINESS_TRANSITION = "READINESS_TRANSITION"
    CRITICAL_ALERT = "CRITICAL_ALERT"
    WEEKLY_SUMMARY = "WEEKLY_SUMMARY"
    # research-only shadow-residual feed (see shadow_feed.py). These are NOT
    # betting signals: they publish an already-persisted, immutable
    # PROSPECTIVE_SHADOW model-vs-market disagreement (and its later market
    # movement) purely as evidence. They are distinct from — and can never be
    # emitted as — the reserved VALIDATED_SIGNAL / STRATEGY_ACTION types.
    SHADOW_RESEARCH = "SHADOW_RESEARCH"
    SHADOW_RESEARCH_UPDATE = "SHADOW_RESEARCH_UPDATE"
    # reserved — require a future explicit promotion gate; NOT activated
    VALIDATED_SIGNAL = "VALIDATED_SIGNAL"
    STRATEGY_ACTION = "STRATEGY_ACTION"


#: Message types that may NOT be emitted during DATA ACCUMULATION MODE.
RESERVED_TYPES: frozenset[MessageType] = frozenset(
    {MessageType.VALIDATED_SIGNAL, MessageType.STRATEGY_ACTION}
)


class ReservedMessageTypeError(RuntimeError):
    """Raised if a reserved (signal/strategy) message type is emitted."""


class SignalContentError(ValueError):
    """Raised if a research status message contains betting-signal vocabulary."""


#: Vocabulary forbidden in a research-status message (defence in depth; the
#: formatters emit none of it). Matched case-insensitively as substrings on the
#: lowered text; the research formatters never produce football team names, so a
#: coarse substring check is safe here and stricter than needed.
_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "value bet", "bet recommendation", "recommended bet", "strong signal",
    "lock of the", " lock ", "expected roi", "roi:", "stake", "kelly",
    "+ev", "-ev", "expected value", "edge over", "worth backing", "best price",
    "back the", "lay the", "tip:", "tipster", "guaranteed", "profit",
    "alpha:", "actionable", "place a bet",
)


def assert_no_signal_content(text: str) -> None:
    """Fail closed if a research message drifts toward betting-signal framing."""
    low = f" {text.lower()} "
    hits = [s for s in _FORBIDDEN_SUBSTRINGS if s in low]
    if hits:
        raise SignalContentError(
            "research status message contains forbidden signal vocabulary: "
            f"{sorted(set(hits))}. During DATA ACCUMULATION MODE Telegram reports "
            "collector/research status only — never bets, stakes, ROI, or tips."
        )


#: The ONLY additional phrases permitted specifically on the research-shadow
#: message path (mission section 11: "update only the research-message
#: validation path narrowly enough to allow the approved research
#: terminology"). Nothing here relaxes the global ``assert_no_signal_content``
#: used by every other message type.
#:
#: Only ``actionable`` needs an exception: the frozen research classification
#: label "NOT ACTIONABLE" / "NOT_ACTIONABLE" (carried verbatim from the shadow
#: record) contains the forbidden substring ``actionable``. We allow it ONLY as
#: part of that explicit negative-classification phrase, so the message can
#: state the record is not actionable without being able to reintroduce any
#: other use of the word.
_RESEARCH_ALLOWED_PHRASES: tuple[str, ...] = (
    "not actionable",
    "not_actionable",
)


def assert_no_signal_content_research(text: str) -> None:
    """Content guard for the research-shadow feed only (narrowly widened).

    Identical to :func:`assert_no_signal_content` EXCEPT that the explicit
    approved research phrases in :data:`_RESEARCH_ALLOWED_PHRASES` (currently
    only the "NOT ACTIONABLE" classification label) are neutralised before the
    forbidden-substring scan. Every other betting-signal term — stake, ROI,
    +EV, edge over, profit, alpha:, tip:, value bet, etc. — is STILL rejected,
    so this cannot be used to smuggle a signal. The global guard is unchanged.
    """
    low = f" {text.lower()} "
    for allowed in _RESEARCH_ALLOWED_PHRASES:
        low = low.replace(allowed, " ")
    hits = [s for s in _FORBIDDEN_SUBSTRINGS if s in low]
    if hits:
        raise SignalContentError(
            "research-shadow message contains forbidden signal vocabulary: "
            f"{sorted(set(hits))}. The research-shadow feed publishes a persisted "
            "model-vs-market residual as evidence only — never bets, stakes, "
            "ROI, edges, or tips."
        )


# ---------------------------------------------------------------------------
# Frozen milestones (mirrors the preregistered gate; do NOT change thresholds)
# ---------------------------------------------------------------------------

#: (metric_key, threshold) milestone points. Milestones are DETERMINISTIC and
#: deduplicated by (metric, threshold). Thresholds here are checkpoints toward
#: the frozen gate in price_discovery.dataset.ReadinessGate; the gate itself is
#: never modified by this module.
MILESTONES: dict[str, tuple[int, ...]] = {
    "captured_fixtures": (100, 200, 300),
    "same_book_late_final": (50, 100, 150, 200),
    "confirmed_lineups": (50, 100, 150),
    "pre_post_lineup_pairs": (50, 100),
}


# ---------------------------------------------------------------------------
# Research status snapshot (read-only over persisted state)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResearchStatus:
    """A point-in-time snapshot of collector + research state (no network)."""

    generated_at: float
    main_sha: str
    collector_version: str
    # scheduler / ops
    collector_health: str
    minutes_since_success: Optional[float]
    last_successful_run: Optional[float]
    quota_remaining: Optional[int]
    errors_last_run: Optional[int]
    total_runs: int
    # research counts
    captured_fixtures: int
    same_book_late_final: int
    confirmed_lineups: int
    pre_post_lineup_pairs: int
    # Genuine-close telemetry (explicitly named units; never an ambiguous
    # "genuine_closes" scalar). ``genuine_close_available`` is False ONLY when
    # the canonical closing/odds source was missing / unreadable / malformed;
    # in that case the two counts are None (UNKNOWN), never a fabricated 0.
    #   * fixtures_with_genuine_close: distinct fixtures with >=1 genuine close
    #   * genuine_closing_keys:        distinct (fixture,book,market,sel,line)
    #                                  keys resolving to a genuine close
    genuine_close_available: bool
    fixtures_with_genuine_close: Optional[int]
    genuine_closing_keys: Optional[int]
    readiness_state: str
    gate_met: bool
    # frozen gate thresholds (for display; never mutated here)
    gate: dict

    def counts(self) -> dict:
        return {
            "captured_fixtures": self.captured_fixtures,
            "same_book_late_final": self.same_book_late_final,
            "confirmed_lineups": self.confirmed_lineups,
            "pre_post_lineup_pairs": self.pre_post_lineup_pairs,
        }

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "main_sha": self.main_sha,
            "collector_version": self.collector_version,
            "collector_health": self.collector_health,
            "minutes_since_success": self.minutes_since_success,
            "last_successful_run": self.last_successful_run,
            "quota_remaining": self.quota_remaining,
            "errors_last_run": self.errors_last_run,
            "total_runs": self.total_runs,
            "captured_fixtures": self.captured_fixtures,
            "same_book_late_final": self.same_book_late_final,
            "confirmed_lineups": self.confirmed_lineups,
            "pre_post_lineup_pairs": self.pre_post_lineup_pairs,
            "genuine_close_available": self.genuine_close_available,
            "fixtures_with_genuine_close": self.fixtures_with_genuine_close,
            "genuine_closing_keys": self.genuine_closing_keys,
            "readiness_state": self.readiness_state,
            "gate_met": self.gate_met,
        }


COLLECTOR_VERSION = "prospective-collector/1"


def _read_main_sha() -> str:
    """Best-effort current commit SHA for provenance (never a secret)."""
    head = Path(".git/HEAD")
    try:
        content = head.read_text(encoding="utf-8").strip()
        if content.startswith("ref:"):
            ref = content.split(" ", 1)[1].strip()
            sha = Path(".git") / ref
            return sha.read_text(encoding="utf-8").strip()[:40]
        return content[:40]
    except OSError:
        return "unknown"


def collect_status(
    *,
    now: Optional[float] = None,
    capture_root: Path = Path("data/prospective"),
    coverage_matrix_path: Path = Path("research/evaluation/prospective_coverage_matrix.json"),
) -> ResearchStatus:
    """Build a ResearchStatus from persisted state only. No network calls.

    Reads: the ops run log (scheduler health), the append-only capture store
    (analysis-support strata), and the price-discovery dataset builder
    (same-book LATE->FINAL count + readiness gate).
    """
    from src.research.experiments.price_discovery.dataset import build_dataset
    from src.research.experiments.price_discovery.report import assess_readiness
    from src.research.prospective.coverage_funnel import analysis_support
    from src.research.prospective.genuine_close_metrics import count_genuine_closes
    from src.research.prospective.ops_log import DEFAULT_OPS_LOG
    from src.research.prospective.scheduler_health import assess_health
    from src.research.prospective.storage import CaptureStore

    now = time.time() if now is None else now
    ops_path = Path(capture_root) / DEFAULT_OPS_LOG.name
    health = assess_health(now=now, path=ops_path)

    store = CaptureStore(path=Path(capture_root) / "captures.jsonl.gz")
    support = analysis_support(store)
    dataset = build_dataset(store)
    readiness = assess_readiness(
        dataset,
        confirmed_lineups=support.fixtures_with_confirmed_lineup,
        pre_post_lineup_pairs=0,  # PRE->POST pairing needs lineup captures (none yet)
    )
    # Genuine-close telemetry is derived from the SAME canonical capture store
    # using the repository's existing genuine-close predicate
    # (resolve_genuine_close). It fails closed to UNKNOWN if the source is
    # missing/unreadable/malformed — it is never a hard-coded 0.
    gc = count_genuine_closes(store)

    return ResearchStatus(
        generated_at=now,
        main_sha=_read_main_sha(),
        collector_version=COLLECTOR_VERSION,
        collector_health=health.health,
        minutes_since_success=health.minutes_since_success,
        last_successful_run=health.last_successful_run,
        quota_remaining=health.latest_quota_remaining,
        errors_last_run=health.latest_error_count,
        total_runs=health.total_runs_observed,
        captured_fixtures=readiness.captured_fixtures,
        same_book_late_final=readiness.same_book_late_final,
        confirmed_lineups=readiness.confirmed_lineups,
        pre_post_lineup_pairs=readiness.pre_post_lineup_pairs,
        genuine_close_available=gc.available,
        fixtures_with_genuine_close=gc.fixtures_with_genuine_close,
        genuine_closing_keys=gc.genuine_closing_keys,
        readiness_state=readiness.readiness_state,
        gate_met=readiness.gate["met"],
        gate=readiness.gate,
    )


# ---------------------------------------------------------------------------
# Message envelope + provenance
# ---------------------------------------------------------------------------


def _payload_hash(obj: dict) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NotifyMessage:
    """A research-status message + provenance, ready to (dedup and) send."""

    message_type: MessageType
    event_id: str          # deterministic dedup id
    text: str
    generated_at: float
    main_sha: str
    collector_version: str
    readiness_state: str
    source_version: str
    payload_hash: str = ""

    def with_hash(self) -> "NotifyMessage":
        h = _payload_hash({
            "message_type": self.message_type.value,
            "event_id": self.event_id,
            "text": self.text,
            "main_sha": self.main_sha,
            "readiness_state": self.readiness_state,
            "source_version": self.source_version,
        })
        return NotifyMessage(
            message_type=self.message_type, event_id=self.event_id, text=self.text,
            generated_at=self.generated_at, main_sha=self.main_sha,
            collector_version=self.collector_version, readiness_state=self.readiness_state,
            source_version=self.source_version, payload_hash=h,
        )

    def provenance(self) -> dict:
        return {
            "message_type": self.message_type.value,
            "event_id": self.event_id,
            "generated_at": self.generated_at,
            "main_sha": self.main_sha,
            "collector_version": self.collector_version,
            "readiness_state": self.readiness_state,
            "source_version": self.source_version,
            "payload_hash": self.payload_hash,
        }


SOURCE_VERSION = "research-notify/1"


def _msg(mtype: MessageType, event_id: str, text: str, status: ResearchStatus) -> NotifyMessage:
    if mtype in RESERVED_TYPES:
        raise ReservedMessageTypeError(
            f"{mtype.value} is reserved and must not be emitted during DATA "
            "ACCUMULATION MODE; it requires a future promotion gate."
        )
    # Research/operational monitor messages may carry the explicit negative
    # classification label "NOT ACTIONABLE" (e.g. the status footer "Research
    # only. Not validated. Not actionable."). We use the narrowly-widened guard
    # that neutralises ONLY that approved phrase before scanning; every other
    # betting-signal term (stake, ROI, +EV, edge, profit, tip, value bet, ...)
    # is STILL rejected, so this cannot be used to smuggle a signal.
    assert_no_signal_content_research(text)
    return NotifyMessage(
        message_type=mtype, event_id=event_id, text=text,
        generated_at=status.generated_at, main_sha=status.main_sha,
        collector_version=status.collector_version, readiness_state=status.readiness_state,
        source_version=SOURCE_VERSION,
    ).with_hash()


#: Message types the research-shadow feed is allowed to emit. Deliberately a
#: subset that EXCLUDES the reserved signal/strategy types, so the feed can
#: never publish a validated signal even by mistake.
_SHADOW_RESEARCH_TYPES: frozenset[MessageType] = frozenset(
    {MessageType.SHADOW_RESEARCH, MessageType.SHADOW_RESEARCH_UPDATE}
)


def build_research_shadow_message(
    mtype: MessageType,
    event_id: str,
    text: str,
    *,
    generated_at: float,
    main_sha: str = "",
    readiness_state: str = "RESEARCH_ONLY",
    collector_version: str = COLLECTOR_VERSION,
) -> NotifyMessage:
    """Construct a research-shadow ``NotifyMessage`` through the guarded path.

    This is the shadow-feed analogue of :func:`_msg`. It enforces THREE things:
      1. ``mtype`` must be one of :data:`_SHADOW_RESEARCH_TYPES` — the reserved
         VALIDATED_SIGNAL / STRATEGY_ACTION types (and any status type) are
         rejected here, so the shadow feed can never emit a signal.
      2. the text passes :func:`assert_no_signal_content_research` (all betting
         vocabulary rejected; only the "NOT ACTIONABLE" label is allowed).
      3. a deterministic ``payload_hash`` is attached for provenance/audit.

    It does not require a full :class:`ResearchStatus` (the shadow feed reads
    persisted shadow records, not the collector snapshot), so provenance fields
    are passed explicitly.
    """
    if mtype not in _SHADOW_RESEARCH_TYPES:
        raise ReservedMessageTypeError(
            f"{mtype.value} may not be emitted by the research-shadow feed; "
            f"only {sorted(t.value for t in _SHADOW_RESEARCH_TYPES)} are permitted."
        )
    assert_no_signal_content_research(text)
    return NotifyMessage(
        message_type=mtype, event_id=event_id, text=text,
        generated_at=generated_at, main_sha=main_sha,
        collector_version=collector_version, readiness_state=readiness_state,
        source_version=SOURCE_VERSION,
    ).with_hash()


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _iso(ts: Optional[float]) -> str:
    if ts is None:
        return "n/a"
    import datetime as _dt
    return _dt.datetime.fromtimestamp(float(ts), _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _quota_str(status: ResearchStatus) -> str:
    q = status.quota_remaining
    return f"{q:,} / 100,000" if isinstance(q, int) else "unknown"


def _fmt_int(value: int) -> str:
    """Thousands-separated integer, e.g. 2520 -> '2,520'."""
    return f"{int(value):,}"


def _gate_line(g: dict, key: str, label: str) -> str:
    """Render an 'observed / required' accumulation line with a ✅ when met.

    A crossed accumulation checkpoint is marked ✅ to make progress legible; it
    signals ONLY that this single input threshold is satisfied — never that the
    overall experiment has passed or that any signal is validated.
    """
    obs = g[key]["observed"]
    req = g[key]["required"]
    tick = " \u2705" if obs >= req else ""
    return f"{label}: {_fmt_int(obs)} / {_fmt_int(req)}{tick}"


def _genuine_close_line(status: ResearchStatus) -> str:
    """Render the genuine-close metric with an EXPLICIT, unambiguous unit.

    The headline is fixture-based (operationally the most useful): the number of
    distinct fixtures that have at least one genuine close, out of the fixtures
    captured so far. If the canonical source could not be trusted, we render
    UNKNOWN rather than a fabricated 0 (missing truth stays missing). We never
    print a bare "Genuine closes: N" whose unit is ambiguous.
    """
    if not status.genuine_close_available or status.fixtures_with_genuine_close is None:
        return "Fixtures with genuine close: UNKNOWN (source unavailable)"
    fixtures = _fmt_int(status.fixtures_with_genuine_close)
    total = _fmt_int(status.captured_fixtures)
    line = f"Fixtures with genuine close: {fixtures} / {total}"
    # Also surface the finer key-level count, explicitly named so the fixture
    # count and the market-key count are never conflated under one label.
    if status.genuine_closing_keys is not None:
        line += f" (genuine closing keys: {_fmt_int(status.genuine_closing_keys)})"
    return line


def _readiness_label(readiness_state: str) -> str:
    """Human-facing readiness label, kept explicitly exploratory.

    The machine token (e.g. PRICE_DISCOVERY_EXPLORATORY) is mapped to spaced
    words for the consumer-ish research surface without losing its meaning. The
    exploratory nature is preserved verbatim.
    """
    return readiness_state.replace("PRICE_DISCOVERY_", "PRICE DISCOVERY \u2014 ").replace("_", " ")


def format_daily_heartbeat(status: ResearchStatus) -> NotifyMessage:
    # NOTE ON STATISTICAL N: the "LATE -> FINAL transitions" figure below is a
    # RAW transition count. Many transitions can belong to the SAME fixture,
    # bookmaker, market and line (a single fixture priced by several books
    # across several vintages produces many transitions). Raw transition N is
    # therefore NOT the effective statistical N / number of independent
    # experiments, fixtures, picks, or samples. It is a data-accumulation
    # counter only. No independence claim is made or implied here, and no new
    # statistical estimator is introduced.
    g = status.gate["checks"]
    text = "\n".join([
        "\u2699\ufe0f FOOTBALL QUANT ENGINE \u2014 RESEARCH STATUS",
        "",
        "SYSTEM",
        f"Collector: {status.collector_health}",
        f"Quota: {_quota_str(status)}",
        f"Last capture: {_iso(status.last_successful_run)}",
        f"Errors last run: {status.errors_last_run if status.errors_last_run is not None else 'n/a'}",
        "",
        "RESEARCH ACCUMULATION",
        _gate_line(g, "captured_fixtures", "Fixtures"),
        _gate_line(g, "same_book_late_final", "LATE \u2192 FINAL transitions"),
        _gate_line(g, "confirmed_lineups", "Confirmed lineups"),
        _gate_line(g, "pre_post_lineup_pairs", "PRE \u2192 POST lineup pairs"),
        _genuine_close_line(status),
        "",
        "READINESS",
        _readiness_label(status.readiness_state),
        "",
        "Research only. Not validated. Not actionable.",
    ])
    # Daily heartbeat dedups per UTC day so a re-run same day is not resent.
    day = _iso(status.generated_at)[:10]
    return _msg(MessageType.DATA_PROGRESS, f"heartbeat:{day}", text, status)


def format_critical_alert(status: ResearchStatus, *, reason: str, detail: str = "") -> NotifyMessage:
    text = "\n".join([
        "Football Quant Engine \u2014 CRITICAL",
        "",
        f"Condition: {reason}",
        f"Collector: {status.collector_health}",
        f"Last successful capture: {_iso(status.last_successful_run)}",
        f"Quota: {_quota_str(status)}",
        (f"Detail: {detail}" if detail else ""),
    ]).rstrip()
    # Dedup a critical condition per (reason, last_successful_run-bucket) so the
    # same standing condition is not re-alerted every check.
    bucket = int((status.last_successful_run or 0) // 3600)
    return _msg(MessageType.CRITICAL_ALERT, f"critical:{reason}:{bucket}", text, status)


def format_milestone(status: ResearchStatus, *, metric: str, threshold: int) -> NotifyMessage:
    # Explicit Required-vs-Captured wording. The threshold (Required) is the
    # frozen data gate; the observed (Captured) count is what we have actually
    # accumulated so far and is often FAR above the threshold. Showing both
    # avoids the misleading "Reached 200 ... (2520 observed)" phrasing.
    #
    # NOTE ON STATISTICAL N: for transition-based metrics the Captured figure is
    # a RAW count. Many transitions/observations can share the same fixture,
    # bookmaker, market and line, so this is NOT the effective statistical N /
    # number of independent experiments, picks, fixtures, or samples. Crossing
    # this data gate unlocks ANALYSIS only; it does not validate any signal and
    # does not mean the overall experiment has passed.
    label = {
        "captured_fixtures": "Captured fixtures",
        "same_book_late_final": "Same-book LATE \u2192 FINAL transitions",
        "confirmed_lineups": "Confirmed lineups",
        "pre_post_lineup_pairs": "PRE \u2192 POST lineup pairs",
    }[metric]
    observed = status.counts()[metric]
    text = "\n".join([
        "\U0001f52c RESEARCH MILESTONE",
        "",
        "Price-discovery data gate reached",
        "",
        label,
        f"Required: {_fmt_int(threshold)}",
        f"Captured: {_fmt_int(observed)} \u2705",
        "",
        "Research stage unlocked:",
        _readiness_label(status.readiness_state),
        "",
        "This unlocks analysis. It does not validate a signal.",
    ])
    # Dedup key unchanged: one milestone message per (metric, threshold), so an
    # already-crossed gate is never re-sent (preserved via the NotifyLedger).
    return _msg(MessageType.RESEARCH_MILESTONE, f"milestone:{metric}:{threshold}", text, status)


def format_readiness_transition(status: ResearchStatus) -> NotifyMessage:
    text = "\n".join([
        "Football Quant Engine \u2014 PRICE_DISCOVERY_EVALUABLE",
        "",
        "Prospective research gate reached.",
        "Formal M0-M4 experiment is now eligible to run.",
        "",
        "No model has been promoted.",
        "No production signal has been enabled.",
    ])
    # One-time transition; dedup by the fixed event id.
    return _msg(MessageType.READINESS_TRANSITION, "readiness:PRICE_DISCOVERY_EVALUABLE", text, status)


def format_engine_health(status: ResearchStatus) -> NotifyMessage:
    text = "\n".join([
        "Football Quant Engine \u2014 Engine Health",
        "",
        f"Collector: {status.collector_health}",
        f"Runs observed: {status.total_runs}",
        f"Minutes since last success: {round(status.minutes_since_success, 1) if status.minutes_since_success is not None else 'n/a'}",
        f"Quota: {_quota_str(status)}",
        f"Errors last run: {status.errors_last_run if status.errors_last_run is not None else 'n/a'}",
    ])
    bucket = int(status.generated_at // 3600)
    return _msg(MessageType.ENGINE_HEALTH, f"health:{bucket}", text, status)


def milestones_crossed(status: ResearchStatus) -> list[tuple[str, int]]:
    """All (metric, threshold) milestones currently satisfied. Deterministic."""
    out: list[tuple[str, int]] = []
    counts = status.counts()
    for metric, thresholds in MILESTONES.items():
        observed = counts.get(metric, 0)
        for t in thresholds:
            if observed >= t:
                out.append((metric, t))
    return out
