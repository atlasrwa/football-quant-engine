"""Delivery + deterministic dedup ledger for research-status notifications.

Separation of concerns (mission section 13): capture success and operational
state are persisted by the collector INDEPENDENTLY of notifications. This
module only attempts a send and records whether it succeeded. A Telegram
failure never affects the collector and never blocks a future send of a
DIFFERENT event; it simply is not marked delivered, so a later run retries.

Deduplication (mission section 12): the same event (by deterministic
``event_id``) is delivered at most once, surviving process restart / reboot /
scheduler retry / Telegram timeout. The ledger is a small gitignored JSON file
under the capture root.

Secret safety (mission section 14): credentials are read from the environment
by :class:`TelegramTransport`; this module never reads, stores, prints, or logs
the token/chat id. Provenance stored in the ledger contains only non-secret
fields (event id, type, hash, timestamps, outcome).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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
    delivered-at timestamp. Only SUCCESSFUL deliveries are recorded, so a failed
    send is naturally retried on the next run (at-least-once attempt,
    exactly-once success).
    """

    path: Path = DEFAULT_LEDGER

    def _load(self) -> dict:
        p = Path(self.path)
        if not p.exists():
            return {}
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def already_sent(self, event_id: str) -> bool:
        return event_id in self._load().get("delivered", {})

    def record_sent(self, msg: NotifyMessage, *, detail: str = "") -> None:
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = self._load()
        delivered = data.setdefault("delivered", {})
        delivered[msg.event_id] = {
            "message_type": msg.message_type.value,
            "payload_hash": msg.payload_hash,
            "delivered_at": time.time(),
            # detail may contain a telegram message_id; never a credential.
            "detail": detail[:200],
        }
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)

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
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
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
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)


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
        ledger.record_sent(msg, detail=detail)
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
