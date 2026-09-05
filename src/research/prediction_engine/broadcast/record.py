"""Append-only broadcast record — what was said, when, and how it resolved.

THE RECORD IS THE POINT
=======================
A published forecast is only meaningful if it cannot be revised afterwards. This
module is the storage layer, and it is append-only by construction: there is no
update method, no delete method, and no code path that rewrites a line. A forecast
that turned out badly stays exactly as published, because a record that quietly
loses its worst entries measures nothing.

Later information is added as *new records that reference the original hash*, never
as edits:

* ``broadcasts.jsonl`` — the forecast commitments (payload + hash + timestamp), plus
  explicit ``NOT_PUBLISHED`` rows for in-scope fixtures that produced no forecast.
* ``delivery_log.jsonl`` — one row per delivery attempt (sent, queued, failed).
* ``outcomes.jsonl`` — resolved outcomes, joined to a forecast by commitment hash.

COVERAGE IS VERIFIABLE
======================
Every in-scope fixture reaching the horizon gets a row in ``broadcasts.jsonl`` —
either a commitment or a ``NOT_PUBLISHED`` row stating why. That is what makes
:meth:`BroadcastLedger.coverage_report` able to answer the question that matters:
was everything in declared scope actually broadcast? A fixture that simply vanished
would be indistinguishable from one that was never in scope, so nothing is allowed
to vanish.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from src.research.prediction_engine.broadcast.payload import (
    ForecastPayload,
    verify_commitment,
)

_HOME = Path("/home/ubuntu")
DEFAULT_RECORD_ROOT = _HOME / "data" / "forecast_broadcast"

BROADCAST_LEDGER_NAME = "broadcasts.jsonl"
DELIVERY_LOG_NAME = "delivery_log.jsonl"
OUTCOME_LEDGER_NAME = "outcomes.jsonl"

#: Contract for rows in the broadcast ledger.
BROADCAST_RECORD_CONTRACT = "forecast-broadcast-record/v1"


class RecordType(str, Enum):
    """What a broadcast-ledger row asserts."""

    #: A forecast was generated, hashed, and committed for publication.
    FORECAST_COMMITTED = "FORECAST_COMMITTED"
    #: An in-scope fixture reached the horizon but no forecast could be published.
    #: Recorded, never silently skipped, so coverage gaps stay visible.
    NOT_PUBLISHED = "NOT_PUBLISHED"


class DeliveryStatus(str, Enum):
    """Outcome of one delivery attempt."""

    SENT = "SENT"
    #: Held by quiet hours. A queued forecast is always sent later, with its
    #: original generated_at_utc and commitment hash intact.
    QUEUED_QUIET_HOURS = "QUEUED_QUIET_HOURS"
    #: Transport failed. Logged and retried; never silently dropped.
    FAILED = "FAILED"
    #: The content gate refused the message. Nothing was sent; visible for repair.
    BLOCKED_CONTENT_GATE = "BLOCKED_CONTENT_GATE"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Append one canonical JSON line. The only write primitive in this module."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # A malformed line is skipped for reading but never rewritten —
                # repairing the file in place would break append-only guarantees.
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Declared scope versus what the record actually contains."""

    scope_version_hash: str
    expected_fixture_ids: tuple[str, ...]
    committed_fixture_ids: tuple[str, ...]
    not_published_fixture_ids: tuple[str, ...]
    missing_fixture_ids: tuple[str, ...]
    undelivered_commitment_hashes: tuple[str, ...]
    not_published_reasons: tuple[tuple[str, str], ...]

    @property
    def is_complete(self) -> bool:
        """True iff every expected fixture has a row and every commitment was sent."""
        return not self.missing_fixture_ids and not self.undelivered_commitment_hashes

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_version_hash": self.scope_version_hash,
            "expected_n": len(self.expected_fixture_ids),
            "committed_n": len(self.committed_fixture_ids),
            "not_published_n": len(self.not_published_fixture_ids),
            "missing_n": len(self.missing_fixture_ids),
            "missing_fixture_ids": list(self.missing_fixture_ids),
            "undelivered_n": len(self.undelivered_commitment_hashes),
            "undelivered_commitment_hashes": list(self.undelivered_commitment_hashes),
            "not_published_reasons": [list(r) for r in self.not_published_reasons],
            "is_complete": self.is_complete,
        }


class BroadcastLedger:
    """Append-only store for forecast commitments, deliveries, and outcomes.

    Deliberately exposes no mutating operation. Corrections and later knowledge are
    expressed as additional rows referencing an existing commitment hash, mirroring
    the INSERT-only convention documented for ``market_prices`` in
    ``migrations/0013_create_market_prices.sql``.
    """

    def __init__(self, root: Path = DEFAULT_RECORD_ROOT) -> None:
        self.root = Path(root)
        self.broadcast_path = self.root / BROADCAST_LEDGER_NAME
        self.delivery_path = self.root / DELIVERY_LOG_NAME
        self.outcome_path = self.root / OUTCOME_LEDGER_NAME

    # ── writes (append only) ────────────────────────────────────────────────
    def append_commitment(
        self,
        payload: ForecastPayload,
        *,
        committed_at_utc: Optional[str] = None,
    ) -> dict[str, Any]:
        """Persist a forecast commitment before it is delivered.

        Written before the send attempt so that a crash mid-send cannot lose the
        record of what was committed. Delivery outcome is a separate row.
        """
        record = {
            "record_contract": BROADCAST_RECORD_CONTRACT,
            "record_type": RecordType.FORECAST_COMMITTED.value,
            "fixture_id": payload.fixture_id,
            "comp_id": payload.comp_id,
            "league_label": payload.league_label,
            "kickoff_unix": int(payload.kickoff_unix),
            "kickoff_utc": payload.kickoff_utc,
            "scope_version_hash": payload.scope_version_hash,
            "commitment_hash": payload.commitment_hash(),
            "committed_at_utc": committed_at_utc or _now_iso(),
            "payload": payload.canonical_dict(),
        }
        _append_jsonl(self.broadcast_path, record)
        return record

    def append_not_published(
        self,
        *,
        fixture_id: str,
        comp_id: Optional[str],
        kickoff_unix: float,
        reason: str,
        scope_version_hash: str,
        recorded_at_utc: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record an in-scope fixture that reached the horizon without a forecast.

        This is not a skip. It is a permanent, visible statement that a declared
        fixture produced no publishable forecast and why — which is what allows a
        coverage check to distinguish a genuine gap from a silent omission.
        """
        record = {
            "record_contract": BROADCAST_RECORD_CONTRACT,
            "record_type": RecordType.NOT_PUBLISHED.value,
            "fixture_id": str(fixture_id),
            "comp_id": comp_id,
            "kickoff_unix": int(float(kickoff_unix)),
            "kickoff_utc": datetime.fromtimestamp(
                float(kickoff_unix), timezone.utc
            ).isoformat(),
            "scope_version_hash": scope_version_hash,
            "reason": reason,
            "recorded_at_utc": recorded_at_utc or _now_iso(),
        }
        _append_jsonl(self.broadcast_path, record)
        return record

    def append_delivery(
        self,
        *,
        commitment_hash: str,
        fixture_id: str,
        status: DeliveryStatus,
        detail: str = "",
        attempt: int = 1,
        generated_at_utc: Optional[str] = None,
        event_at_utc: Optional[str] = None,
    ) -> dict[str, Any]:
        """Log one delivery attempt.

        ``generated_at_utc`` is carried through unchanged so a late send stays
        attributable to the moment the forecast was generated, not the moment the
        transport happened to succeed.
        """
        record = {
            "record_contract": BROADCAST_RECORD_CONTRACT,
            "commitment_hash": commitment_hash,
            "fixture_id": str(fixture_id),
            "status": status.value,
            "detail": detail,
            "attempt": int(attempt),
            "generated_at_utc": generated_at_utc,
            "event_at_utc": event_at_utc or _now_iso(),
        }
        _append_jsonl(self.delivery_path, record)
        return record

    def append_outcome(
        self,
        *,
        commitment_hash: str,
        fixture_id: str,
        market: str,
        line: Optional[float],
        settled_side: str,
        observed_value: Optional[float] = None,
        resolved_at_utc: Optional[str] = None,
        source: str = "",
    ) -> dict[str, Any]:
        """Attach a resolved outcome to an existing forecast, as a new row.

        The forecast itself is never touched. Joining on ``commitment_hash`` means an
        outcome can only ever be attached to the exact payload that was published.
        """
        record = {
            "record_contract": BROADCAST_RECORD_CONTRACT,
            "commitment_hash": commitment_hash,
            "fixture_id": str(fixture_id),
            "market": market,
            "line": line,
            "settled_side": settled_side,
            "observed_value": observed_value,
            "source": source,
            "resolved_at_utc": resolved_at_utc or _now_iso(),
        }
        _append_jsonl(self.outcome_path, record)
        return record

    # ── reads ───────────────────────────────────────────────────────────────
    def records(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.broadcast_path)

    def delivery_events(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.delivery_path)

    def outcomes(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.outcome_path)

    def commitments(self) -> Iterator[dict[str, Any]]:
        for rec in self.records():
            if rec.get("record_type") == RecordType.FORECAST_COMMITTED.value:
                yield rec

    def fired_fixture_ids(self) -> frozenset[str]:
        """Fixtures the horizon has already fired for.

        Exactly-once is enforced against this set: a fixture with any row — a
        commitment or a ``NOT_PUBLISHED`` row — has had its horizon moment and is
        never evaluated again. Re-firing on a later scheduler tick would publish a
        second, differently-timed forecast for the same fixture.
        """
        return frozenset(str(rec.get("fixture_id")) for rec in self.records())

    def commitment_for_fixture(self, fixture_id: str) -> Optional[dict[str, Any]]:
        for rec in self.commitments():
            if str(rec.get("fixture_id")) == str(fixture_id):
                return rec
        return None

    def delivered_commitment_hashes(self) -> frozenset[str]:
        return frozenset(
            str(ev.get("commitment_hash"))
            for ev in self.delivery_events()
            if ev.get("status") == DeliveryStatus.SENT.value
        )

    # ── verification ────────────────────────────────────────────────────────
    def verify_commitment_hashes(self) -> tuple[str, ...]:
        """Re-hash every stored payload; return the hashes that do not reproduce.

        An empty result means every stored payload still hashes to the value
        published with it, i.e. no record has been altered since it was written.
        """
        bad: list[str] = []
        for rec in self.commitments():
            stored = str(rec.get("commitment_hash"))
            if not verify_commitment(rec.get("payload") or {}, stored):
                bad.append(stored)
        return tuple(bad)

    def coverage_report(
        self,
        *,
        scope_version_hash: str,
        expected_fixture_ids: Iterable[str],
    ) -> CoverageReport:
        """Compare declared scope against the record.

        Args:
            scope_version_hash: the scope version being audited.
            expected_fixture_ids: every in-scope fixture whose horizon has passed.

        Returns:
            A :class:`CoverageReport`. ``missing_fixture_ids`` is the number that
            matters — a fixture in declared scope with no row at all.
        """
        expected = tuple(str(f) for f in expected_fixture_ids)
        committed: list[str] = []
        not_published: list[str] = []
        reasons: list[tuple[str, str]] = []
        for rec in self.records():
            fid = str(rec.get("fixture_id"))
            if rec.get("record_type") == RecordType.FORECAST_COMMITTED.value:
                committed.append(fid)
            elif rec.get("record_type") == RecordType.NOT_PUBLISHED.value:
                not_published.append(fid)
                reasons.append((fid, str(rec.get("reason", ""))))

        present = set(committed) | set(not_published)
        missing = tuple(f for f in expected if f not in present)

        delivered = self.delivered_commitment_hashes()
        undelivered = tuple(
            str(rec.get("commitment_hash"))
            for rec in self.commitments()
            if str(rec.get("commitment_hash")) not in delivered
        )

        return CoverageReport(
            scope_version_hash=scope_version_hash,
            expected_fixture_ids=expected,
            committed_fixture_ids=tuple(committed),
            not_published_fixture_ids=tuple(not_published),
            missing_fixture_ids=missing,
            undelivered_commitment_hashes=undelivered,
            not_published_reasons=tuple(reasons),
        )
