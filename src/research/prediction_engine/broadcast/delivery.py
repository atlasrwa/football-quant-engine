"""Delivery — quiet hours may delay a forecast, never cancel it.

THE DELIVERY GUARANTEE
======================
Once a forecast is committed it *will* be delivered. Two things can get in the way,
and neither is allowed to discard it:

* **Quiet hours.** The message is queued and sent when quiet hours end. It goes out
  byte-identical, carrying its original ``generated_at_utc`` and commitment hash, so
  a late delivery is still attributable to the horizon moment it was generated at.
  It is never regenerated at send time — regenerating would silently re-date the
  forecast and break its hash.
* **Transport failure.** Logged and re-queued. The queue never discards an envelope,
  no matter how many attempts have failed; a forecast that could not be sent stays
  pending and visible rather than disappearing.

This contrasts deliberately with the deprecated ``CommunityBroadcaster``, whose
quiet-hours branch drops signals outright. Dropping is acceptable for a signal and
unacceptable for a published forecast record.

THE QUEUE IS OPERATIONAL STATE, NOT THE RECORD
==============================================
``pending_queue.jsonl`` is working state and is rewritten as envelopes drain. The
permanent record lives in the append-only ledger in
:mod:`~src.research.prediction_engine.broadcast.record`, which is never rewritten.
Every queue transition is logged there, so the queue file could be lost entirely
without losing the history of what was committed or sent.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from src.research.prediction_engine.broadcast.record import (
    BroadcastLedger,
    DeliveryStatus,
)

logger = logging.getLogger(__name__)

#: Matches the timeout used by the other Telegram senders in this repo.
TELEGRAM_TIMEOUT = 15

QUEUE_NAME = "pending_queue.jsonl"

#: Attempts after which a stuck envelope is logged at ERROR every run. It is still
#: never dropped — escalation is about visibility, not expiry.
ESCALATE_AFTER_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_quiet_hours(hour_utc: int, start_hour: int, end_hour: int) -> bool:
    """Whether ``hour_utc`` falls in the quiet window, handling midnight wrap.

    Args:
        hour_utc: hour of day in UTC, 0-23.
        start_hour: first quiet hour, inclusive.
        end_hour: first non-quiet hour, exclusive.
    """
    if start_hour == end_hour:
        return False
    if start_hour <= end_hour:
        return start_hour <= hour_utc < end_hour
    # Wraps midnight (e.g. 22 to 6).
    return hour_utc >= start_hour or hour_utc < end_hour


# ─────────────────────────────────────────────────────────────────────────────
# Transports
# ─────────────────────────────────────────────────────────────────────────────
class Transport(Protocol):
    """Outbound message transport. Returns ``(ok, detail)`` and never raises."""

    def send(self, text: str) -> tuple[bool, str]:
        ...


@dataclass
class TelegramTransport:
    """Telegram Bot API sender, standard library only.

    Follows the transport convention already used by ``scripts/signals_telegram_bot.py``
    and ``scripts/pilotC_heartbeat.py``: urlencoded form POST, plain text with no
    ``parse_mode`` (so no markup escaping can corrupt a team name), a ``(bool, str)``
    return, truncated error bodies, and no exception escaping to the caller.

    A failure returns ``False`` rather than raising, because the caller's job on
    failure is to queue and log — not to abort the run and leave other fixtures
    unbroadcast.

    Credentials are resolved from the first environment variable present in each
    tuple, preferring the dedicated ``FORECAST_BROADCAST_*`` pair. The names that
    actually resolved are logged once per process and recorded in the delivery
    detail, so the record shows which channel received a forecast. That matters
    because the fallback names belong to the deprecated signals channel: a silent
    fallback would publish forecasts to a signal audience with nothing in the record
    saying so.
    """

    token_env: tuple[str, ...] = (
        "FORECAST_BROADCAST_TELEGRAM_BOT_TOKEN",
        "SIGNALS_TELEGRAM_BOT_TOKEN",
    )
    chat_env: tuple[str, ...] = (
        "FORECAST_BROADCAST_TELEGRAM_CHAT_ID",
        "SIGNALS_TELEGRAM_CHAT_ID",
        "HEARTBEAT_TELEGRAM_CHAT_ID",
    )
    timeout: int = TELEGRAM_TIMEOUT
    _announced: bool = field(default=False, repr=False)

    def _first_env(
        self, names: tuple[str, ...]
    ) -> tuple[Optional[str], Optional[str]]:
        """The first present ``(name, value)`` pair, or ``(None, None)``."""
        for name in names:
            value = os.environ.get(name)
            if value:
                return name, value
        return None, None

    def send(self, text: str) -> tuple[bool, str]:
        token_name, token = self._first_env(self.token_env)
        chat_name, chat_id = self._first_env(self.chat_env)
        if not token or not chat_id:
            return False, (
                f"missing credentials: set one of {self.token_env} and "
                f"one of {self.chat_env}"
            )
        route = f"{token_name}+{chat_name}"
        if not self._announced:
            if not token_name.startswith("FORECAST_BROADCAST_"):
                logger.warning(
                    "no dedicated forecast credentials set; falling back to %s. "
                    "Forecasts will be delivered to the %s channel — set "
                    "FORECAST_BROADCAST_TELEGRAM_BOT_TOKEN and "
                    "FORECAST_BROADCAST_TELEGRAM_CHAT_ID to publish to a dedicated "
                    "forecast channel instead.", route, chat_name,
                )
            else:
                logger.info("forecast delivery route: %s", route)
            self._announced = True
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            }
        ).encode()
        request = urllib.request.Request(url, data=payload, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(body)
            if obj.get("ok"):
                message_id = obj.get("result", {}).get("message_id")
                return True, f"ok message_id={message_id} via {route}"
            return False, f"telegram not ok via {route}: {body[:200]}"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            return False, f"HTTP {exc.code} via {route}: {detail}"
        except Exception as exc:  # noqa: BLE001 - transport must never raise
            return False, f"{type(exc).__name__} via {route}: {str(exc)[:200]}"


@dataclass
class RecordingTransport:
    """Transport that records messages instead of sending. For dry runs and tests."""

    ok: bool = True
    detail: str = "dry-run"
    sent: list[str] = field(default_factory=list)

    def send(self, text: str) -> tuple[bool, str]:
        self.sent.append(text)
        return self.ok, self.detail


# ─────────────────────────────────────────────────────────────────────────────
# Pending queue
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class QueuedForecast:
    """A committed forecast awaiting delivery, stored verbatim.

    ``message`` is the exact rendered text and ``commitment_hash`` the exact
    published hash. Nothing here is recomputed on the way out.
    """

    commitment_hash: str
    fixture_id: str
    generated_at_utc: str
    kickoff_unix: int
    message: str
    enqueued_at_utc: str
    attempts: int = 0
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "commitment_hash": self.commitment_hash,
            "fixture_id": self.fixture_id,
            "generated_at_utc": self.generated_at_utc,
            "kickoff_unix": self.kickoff_unix,
            "message": self.message,
            "enqueued_at_utc": self.enqueued_at_utc,
            "attempts": self.attempts,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "QueuedForecast":
        return cls(
            commitment_hash=str(obj["commitment_hash"]),
            fixture_id=str(obj["fixture_id"]),
            generated_at_utc=str(obj["generated_at_utc"]),
            kickoff_unix=int(obj.get("kickoff_unix") or 0),
            message=str(obj["message"]),
            enqueued_at_utc=str(obj.get("enqueued_at_utc") or ""),
            attempts=int(obj.get("attempts") or 0),
            last_error=str(obj.get("last_error") or ""),
        )

    def with_failure(self, error: str) -> "QueuedForecast":
        """A copy with the attempt counter advanced. Never expires the envelope."""
        return QueuedForecast(
            commitment_hash=self.commitment_hash,
            fixture_id=self.fixture_id,
            generated_at_utc=self.generated_at_utc,
            kickoff_unix=self.kickoff_unix,
            message=self.message,
            enqueued_at_utc=self.enqueued_at_utc,
            attempts=self.attempts + 1,
            last_error=error[:300],
        )


class PendingQueue:
    """Durable pending-delivery queue. Drains, but never discards on failure."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> list[QueuedForecast]:
        if not self.path.exists():
            return []
        out: list[QueuedForecast] = []
        with open(self.path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(QueuedForecast.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
        return out

    def _write(self, envelopes: list[QueuedForecast]) -> None:
        """Atomically replace the queue file with ``envelopes``."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            for env in envelopes:
                handle.write(json.dumps(env.to_dict(), sort_keys=True) + "\n")
        os.replace(tmp, self.path)

    def add(self, envelope: QueuedForecast) -> None:
        """Enqueue, unless this commitment is already queued (idempotent)."""
        current = self.load()
        if any(e.commitment_hash == envelope.commitment_hash for e in current):
            return
        current.append(envelope)
        self._write(current)

    def replace_all(self, envelopes: list[QueuedForecast]) -> None:
        self._write(envelopes)

    def contains(self, commitment_hash: str) -> bool:
        return any(e.commitment_hash == commitment_hash for e in self.load())

    def __len__(self) -> int:
        return len(self.load())


# ─────────────────────────────────────────────────────────────────────────────
# Deliverer
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    """Result of trying to deliver one committed forecast."""

    status: DeliveryStatus
    detail: str


class ForecastDeliverer:
    """Sends committed forecasts, queueing rather than cancelling when suppressed.

    Args:
        ledger: append-only record every transition is logged to.
        queue: durable pending queue.
        transport: outbound transport.
        quiet_start_hour: first quiet UTC hour, inclusive.
        quiet_end_hour: first non-quiet UTC hour, exclusive.
        clock: injectable UTC clock, so quiet-hours behaviour is deterministic in
            tests rather than dependent on when the suite happens to run.
    """

    def __init__(
        self,
        *,
        ledger: BroadcastLedger,
        queue: PendingQueue,
        transport: Transport,
        quiet_start_hour: int,
        quiet_end_hour: int,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._ledger = ledger
        self._queue = queue
        self._transport = transport
        self._quiet_start = quiet_start_hour
        self._quiet_end = quiet_end_hour
        self._clock = clock or _now

    def in_quiet_hours(self) -> bool:
        return is_quiet_hours(self._clock().hour, self._quiet_start, self._quiet_end)

    def deliver(
        self,
        *,
        commitment_hash: str,
        fixture_id: str,
        generated_at_utc: str,
        kickoff_unix: int,
        message: str,
    ) -> DeliveryOutcome:
        """Deliver a committed forecast now, or queue it for later.

        Queueing is not a cancellation and not a decision about whether the forecast
        deserves to go out. It is a deferral of transport only.
        """
        envelope = QueuedForecast(
            commitment_hash=commitment_hash,
            fixture_id=fixture_id,
            generated_at_utc=generated_at_utc,
            kickoff_unix=int(kickoff_unix),
            message=message,
            enqueued_at_utc=self._clock().isoformat(),
        )

        if self.in_quiet_hours():
            self._queue.add(envelope)
            detail = (
                f"quiet hours {self._quiet_start:02d}:00-{self._quiet_end:02d}:00 UTC — "
                "queued for delivery when quiet hours end; original "
                "generated_at_utc and commitment hash preserved"
            )
            logger.info("forecast %s queued: %s", commitment_hash[:16], detail)
            self._ledger.append_delivery(
                commitment_hash=commitment_hash,
                fixture_id=fixture_id,
                status=DeliveryStatus.QUEUED_QUIET_HOURS,
                detail=detail,
                generated_at_utc=generated_at_utc,
                event_at_utc=self._clock().isoformat(),
            )
            return DeliveryOutcome(DeliveryStatus.QUEUED_QUIET_HOURS, detail)

        return self._attempt(envelope, attempt=1)

    def flush_queue(self) -> list[DeliveryOutcome]:
        """Attempt every pending envelope, oldest first.

        Called at the start of every scheduler run so a forecast suppressed by quiet
        hours goes out at the first opportunity afterwards. During quiet hours this
        is a no-op and the queue is left untouched.
        """
        pending = self._queue.load()
        if not pending:
            return []
        if self.in_quiet_hours():
            logger.info(
                "quiet hours active — %d forecast(s) remain queued (delayed, not "
                "cancelled)", len(pending),
            )
            return []

        outcomes: list[DeliveryOutcome] = []
        remaining: list[QueuedForecast] = []
        for envelope in pending:
            outcome = self._attempt(envelope, attempt=envelope.attempts + 1)
            outcomes.append(outcome)
            if outcome.status is not DeliveryStatus.SENT:
                failed = envelope.with_failure(outcome.detail)
                if failed.attempts >= ESCALATE_AFTER_ATTEMPTS:
                    logger.error(
                        "forecast %s has failed delivery %d times and is STILL "
                        "queued (never dropped): %s",
                        failed.commitment_hash[:16], failed.attempts,
                        failed.last_error,
                    )
                remaining.append(failed)
        self._queue.replace_all(remaining)
        return outcomes

    def _attempt(self, envelope: QueuedForecast, *, attempt: int) -> DeliveryOutcome:
        """Send once and log the result. The message is sent exactly as stored."""
        ok, detail = self._transport.send(envelope.message)
        status = DeliveryStatus.SENT if ok else DeliveryStatus.FAILED
        if not ok:
            logger.error(
                "forecast %s delivery FAILED (attempt %d): %s",
                envelope.commitment_hash[:16], attempt, detail,
            )
        self._ledger.append_delivery(
            commitment_hash=envelope.commitment_hash,
            fixture_id=envelope.fixture_id,
            status=status,
            detail=detail,
            attempt=attempt,
            generated_at_utc=envelope.generated_at_utc,
            event_at_utc=self._clock().isoformat(),
        )
        if not ok:
            # Ensure a failed direct send becomes pending work rather than a
            # forecast that was committed and then quietly never sent.
            self._queue.add(envelope.with_failure(detail))
        return DeliveryOutcome(status, detail)

    def log_content_gate_block(
        self, *, commitment_hash: str, fixture_id: str, reason: str,
        generated_at_utc: str,
    ) -> DeliveryOutcome:
        """Record that the content gate refused a message. Nothing was sent."""
        logger.error(
            "forecast %s BLOCKED by content gate, not sent: %s",
            commitment_hash[:16], reason,
        )
        self._ledger.append_delivery(
            commitment_hash=commitment_hash,
            fixture_id=fixture_id,
            status=DeliveryStatus.BLOCKED_CONTENT_GATE,
            detail=reason[:500],
            generated_at_utc=generated_at_utc,
            event_at_utc=self._clock().isoformat(),
        )
        return DeliveryOutcome(DeliveryStatus.BLOCKED_CONTENT_GATE, reason[:500])
