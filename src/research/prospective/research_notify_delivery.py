"""Delivery + deterministic dedup ledger for research-status notifications.

Separation of concerns (mission section 13): capture success and operational
state are persisted by the collector INDEPENDENTLY of notifications. This
module only attempts a send and records whether it succeeded. A Telegram
failure never affects the collector and never blocks a future send of a
DIFFERENT event; it simply is not marked delivered, so a later run retries.

Delivery guarantee (explicit): at-least-once, deduplicated best-effort. The
same event (by deterministic ``event_id``) is normally delivered once and, once
recorded, is never re-sent across restart / reboot / scheduler retry / Telegram
timeout. It is NOT true exactly-once: Telegram delivery and the local ledger
write cannot be committed atomically, so there is a narrow crash window — if the
process dies AFTER Telegram accepts the message but BEFORE
:meth:`NotifyLedger.record_sent` persists — in which the next run will resend
that one event (a duplicate). We deliberately do not add an in-flight/2-phase
protocol: for research-only cards a rare duplicate after a crash is acceptable,
and the alternative failure (recording before a confirmed send, which could drop
a message entirely) is worse. Ordering of the two steps is therefore fixed:
send first, record only on confirmed success, so the failure mode is a duplicate
(safe) rather than a silent drop.

Deduplication ledger: the ledger is a small gitignored JSON file under the
capture root. Concurrent writers (the capture collector and the research monitor
run as separate processes under different flocks and share this ledger) are
serialized by an exclusive advisory lock (``fcntl.flock`` on a sidecar
``<ledger>.lock``) held across the whole read-modify-write, so a racing writer
can never clobber another's delivered marker.

Secret safety (mission section 14): credentials are read from the environment
by :class:`TelegramTransport`; this module never reads, stores, prints, or logs
the token/chat id. Provenance stored in the ledger contains only non-secret
fields (event id, type, hash, timestamps, outcome).
"""

from __future__ import annotations

import fcntl
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from src.research.prediction_engine.broadcast.delivery import (
    RecordingTransport,
    TelegramTransport,
    Transport,
)
from src.research.prospective.research_notify import NotifyMessage

#: Gitignored dedup + delivery-state ledger (under the capture root).
DEFAULT_LEDGER = Path("data/prospective/notify_ledger.json")


@dataclass
class NotifyLedger:
    """Restart-safe delivery ledger keyed by deterministic event_id.

    Stores, per delivered event: the message type, payload hash, and the
    delivered-at timestamp. Only CONFIRMED-SUCCESSFUL deliveries are recorded,
    so a failed send is naturally retried on the next run. The resulting
    contract is at-least-once, deduplicated best-effort: after a confirmed send
    the event is never resent, except in the narrow crash window between a
    successful Telegram send and this ledger write (see the module docstring),
    where the next run resends that one event. It is NOT exactly-once.
    """

    path: Path = DEFAULT_LEDGER

    def _lock_path(self) -> Path:
        p = Path(self.path)
        return p.with_name(f"{p.name}.lock")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Serialize a full read-modify-write across processes with an exclusive
        advisory lock.

        Uses a sidecar ``<ledger>.lock`` file and ``fcntl.flock(LOCK_EX)`` (the
        same discipline as :mod:`src.research.forward.attestation_ledger`). The
        capture collector and the research monitor run as SEPARATE processes
        under DIFFERENT flocks, so without this the two could interleave their
        read-modify-write on the shared ledger and silently drop a delivered
        marker (causing a duplicate resend). Holding this lock across load +
        write + atomic replace makes concurrent writers safe.
        """
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._lock_path()
        with open(lock_path, "a+") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def _load(self) -> dict:
        p = Path(self.path)
        if not p.exists():
            return {}
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _atomic_write(self, data: dict) -> None:
        """Write the ledger atomically. Caller MUST hold :meth:`_locked`."""
        p = Path(self.path)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)

    def already_sent(self, event_id: str) -> bool:
        return event_id in self._load().get("delivered", {})

    def record_sent(self, msg: NotifyMessage, *, detail: str = "") -> None:
        with self._locked():
            data = self._load()
            delivered = data.setdefault("delivered", {})
            delivered[msg.event_id] = {
                "message_type": msg.message_type.value,
                "payload_hash": msg.payload_hash,
                "delivered_at": time.time(),
                # detail may contain a telegram message_id; never a credential.
                "detail": detail[:200],
            }
            self._atomic_write(data)

    def record_member(self, member_event_id: str, *, parent: NotifyMessage, detail: str = "") -> None:
        """Mark an additional (member) event id delivered under a parent message.

        Used when ONE delivered message covers several logical events (e.g. a
        fixture-grouped research-shadow card that contains several individual
        shadows). Each member gets its own durable dedup key so it is never
        re-published on a later tick, even if a future card would re-include it.
        Stores only non-secret provenance; keyed by the member id.
        """
        if not member_event_id:
            return
        with self._locked():
            data = self._load()
            delivered = data.setdefault("delivered", {})
            if member_event_id in delivered:
                return
            delivered[member_event_id] = {
                "message_type": parent.message_type.value,
                "payload_hash": parent.payload_hash,
                "delivered_at": time.time(),
                "detail": (f"member of {parent.event_id}: {detail}")[:200],
            }
            self._atomic_write(data)


@dataclass(frozen=True)
class DeliveryResult:
    event_id: str
    message_type: str
    sent: bool
    deduped: bool
    detail: str


def deliver(
    msg: NotifyMessage,
    *,
    transport: Optional[Transport] = None,
    ledger: Optional[NotifyLedger] = None,
    dry_run: bool = False,
) -> DeliveryResult:
    """Send one research-status message unless already delivered (dedup).

    Delivery guarantee: at-least-once, deduplicated best-effort (see the module
    docstring). Steps are ordered send-then-record so the only crash-window
    failure mode is a duplicate resend, never a silent drop:

      1. if the ledger already has ``event_id`` -> skip (dedup);
      2. attempt the send;
      3. record the event as delivered ONLY on a confirmed ``ok`` result.

    If the process dies between step 2 (Telegram accepted) and step 3 (ledger
    persisted), the next run repeats the send for this one event (a tolerated
    duplicate for research-only cards); exactly-once is not attempted. A
    ledger-write EXCEPTION at step 3 is likewise isolated (never raised to the
    caller): the event stays unrecorded and is resent next run.

    Telegram failure isolation: a send failure returns ``sent=False`` and does
    NOT record the event as delivered (so it retries later). It never raises to
    the caller, so a notification problem cannot break a capture pipeline that
    calls this after persisting its own state.
    """
    ledger = ledger or NotifyLedger()
    if ledger.already_sent(msg.event_id):
        return DeliveryResult(msg.event_id, msg.message_type.value, sent=False,
                              deduped=True, detail="already delivered")

    if dry_run:
        # Dry run neither sends nor records; used for inspection/tests.
        return DeliveryResult(msg.event_id, msg.message_type.value, sent=False,
                              deduped=False, detail="dry-run (not sent, not recorded)")

    transport = transport or TelegramTransport()
    try:
        ok, detail = transport.send(msg.text)
    except Exception as exc:  # noqa: BLE001 - transport must never break the caller
        return DeliveryResult(msg.event_id, msg.message_type.value, sent=False,
                              deduped=False, detail=f"transport error: {type(exc).__name__}")

    if ok:
        try:
            ledger.record_sent(msg, detail=detail)
        except Exception as exc:  # noqa: BLE001 - a ledger-write failure must not break the caller
            # The send SUCCEEDED but we could not durably record it. Isolate the
            # failure (never raise into the capture pipeline) and leave the event
            # unrecorded, so the next run resends it. This is the documented
            # at-least-once crash window: a tolerated duplicate, never a drop.
            return DeliveryResult(
                msg.event_id, msg.message_type.value, sent=ok, deduped=False,
                detail=f"{detail}; WARNING ledger not recorded ({type(exc).__name__}); will resend",
            )
    return DeliveryResult(msg.event_id, msg.message_type.value, sent=ok, deduped=False,
                          detail=detail)


def deliver_all(
    messages: list[NotifyMessage],
    *,
    transport: Optional[Transport] = None,
    ledger: Optional[NotifyLedger] = None,
    dry_run: bool = False,
) -> list[DeliveryResult]:
    """Deliver a batch, each independently deduped. Order preserved."""
    ledger = ledger or NotifyLedger()
    transport = transport or (RecordingTransport() if dry_run else TelegramTransport())
    out: list[DeliveryResult] = []
    for m in messages:
        out.append(deliver(m, transport=transport, ledger=ledger, dry_run=dry_run))
    return out
