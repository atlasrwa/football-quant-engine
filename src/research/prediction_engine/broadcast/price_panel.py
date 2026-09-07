"""CLV panel price capture — the price layer, kept separate from the forecast layer.

WHY THIS IS A SEPARATE MODULE
=============================
Prices are captured at the same horizon moment as the forecast, for the same
markets, and stored append-only for later closing-line analysis. They are *not* part
of the broadcast: no price appears in the message, and no price can reach the
forecast.

That separation is structural, not a convention:

* this module imports nothing from
  :mod:`~src.research.prediction_engine.broadcast.payload`, and that module imports
  nothing from here, so neither layer can read the other's state;
* the forecast builder has no price parameter at all, so there is no argument
  through which a price could influence a probability;
* the two write to different stores, so a failure to capture prices cannot alter a
  published forecast, and a forecast that could not be produced does not suppress a
  price capture.

WHAT IS RECORDED, AND HOW HONESTLY
==================================
The record mirrors the hardened quote contract already used in this repo (see
``migrations/0013_create_market_prices.sql`` and
``scripts/fixture_alert_watcher.py``): observation time, retrieval time, explicit
``timestamp_semantics``, and a content hash of the quote identity.

The providers used here do not supply a verified source timestamp, so
``provider_source_time`` is ``None`` and the semantics are recorded as
``RETRIEVAL_TIME``. A horizon capture is a snapshot taken 8 hours before kickoff — it
is emphatically not a closing line, and ``price_type`` says ``SNAPSHOT`` so nothing
downstream can mistake it for one. Relabelling a snapshot as a close is the single
easiest way to manufacture a flattering CLV number, so the label is fixed here and
never inferred.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

logger = logging.getLogger(__name__)

_HOME = Path("/home/ubuntu")

#: The CLV panel store for horizon price captures. Append-only.
DEFAULT_PANEL_ROOT = _HOME / "data" / "clv_panel"
PRICE_CAPTURE_NAME = "price_captures.jsonl"

#: Quote identity contract. Domain-separates these hashes from the watcher's
#: ``watcher-quote-v1`` quotes so the two producers can never collide.
QUOTE_CONTRACT = "clv-panel-quote/v1"

#: Marks why the capture happened, so panel rows from this producer are separable
#: from any other price collection in the store.
CAPTURE_CONTEXT_HORIZON = "FORECAST_HORIZON"

#: A horizon snapshot is never a closing line.
PRICE_TYPE_SNAPSHOT = "SNAPSHOT"

#: No provider here supplies a verified source timestamp; we record what is true.
TIMESTAMP_SEMANTICS_RETRIEVAL = "RETRIEVAL_TIME"


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _canonical_hash(obj: Any) -> str:
    return _sha256(_canonical_json(obj))


@dataclass(frozen=True, slots=True)
class PriceQuote:
    """One observed price for one side of one market at one bookmaker."""

    market: str
    line: Optional[float]
    bookmaker: str
    selection: str
    decimal_odds: float

    def identity(self, *, fixture_id: str, observed_at_utc: str) -> dict[str, Any]:
        return {
            "fixture_id": fixture_id,
            "market": self.market,
            "line": self.line,
            "bookmaker": self.bookmaker,
            "selection": self.selection,
            "decimal_odds": float(self.decimal_odds),
            "observed_at_utc": observed_at_utc,
        }


def build_price_records(
    *,
    fixture_id: str,
    kickoff_unix: float,
    quotes: Sequence[PriceQuote],
    observed_at: datetime,
    source: str,
    capture_context: str = CAPTURE_CONTEXT_HORIZON,
    horizon_hours: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Build append-only CLV panel rows for one fixture's observed prices.

    Args:
        fixture_id: provider fixture identifier, matching the forecast record's
            ``fixture_id`` so the two layers can be joined for analysis later
            without either one having read the other at capture time.
        kickoff_unix: kickoff as a UTC epoch.
        quotes: observed prices. Quotes with a non-numeric or non-positive price are
            dropped rather than stored as a fabricated number.
        observed_at: collection timestamp, timezone-aware UTC.
        source: provider identifier.
        capture_context: why this capture happened.
        horizon_hours: the declared horizon, recorded for auditability.

    Returns:
        The rows to append. Never partially fabricated: a quote either has a real
        price or is not recorded.
    """
    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware UTC")
    observed_at_utc = observed_at.astimezone(timezone.utc).isoformat()
    try:
        kickoff = int(float(kickoff_unix))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"kickoff_unix is not a timestamp: {kickoff_unix!r}") from exc

    capture_run_id = _canonical_hash(
        {
            "quote_contract": QUOTE_CONTRACT,
            "fixture_id": str(fixture_id),
            "observed_at_utc": observed_at_utc,
            "source": source,
            "capture_context": capture_context,
        }
    )

    records: list[dict[str, Any]] = []
    for quote in quotes:
        try:
            odds = float(quote.decimal_odds)
        except (TypeError, ValueError):
            continue
        if not odds > 1.0:
            continue
        identity = quote.identity(
            fixture_id=str(fixture_id), observed_at_utc=observed_at_utc
        )
        records.append(
            {
                **identity,
                "quote_contract": QUOTE_CONTRACT,
                "capture_context": capture_context,
                "horizon_hours_before_kickoff": horizon_hours,
                "capture_run_id": capture_run_id,
                "source": source,
                "provider_source_time": None,
                "retrieved_at_utc": observed_at_utc,
                "timestamp_semantics": TIMESTAMP_SEMANTICS_RETRIEVAL,
                "quote_status": "ACTIVE",
                "price_type": PRICE_TYPE_SNAPSHOT,
                "kickoff_unix": kickoff,
                "kickoff_utc": datetime.fromtimestamp(
                    kickoff, timezone.utc
                ).isoformat(),
                "clv_eligible": observed_at.timestamp() < kickoff,
                "raw_payload_hash": _canonical_hash(identity),
                "quote_hash": _canonical_hash(
                    {"quote_contract": QUOTE_CONTRACT, **identity}
                ),
            }
        )
    return records


class PriceCaptureStore:
    """Append-only CLV panel store for horizon price captures.

    Exposes append and read only. Like the broadcast ledger, a correction is a new
    observation rather than a rewrite of an old one — the convention documented for
    ``market_prices``.
    """

    def __init__(self, root: Path = DEFAULT_PANEL_ROOT) -> None:
        self.root = Path(root)
        self.path = self.root / PRICE_CAPTURE_NAME

    def append(self, records: Iterable[dict[str, Any]]) -> int:
        """Append rows, skipping any quote hash already present (idempotent).

        Idempotency matters because the scheduler may retry a run: a repeated capture
        of the identical quote at the identical observation time is the same
        observation, not a new one.
        """
        rows = list(records)
        if not rows:
            return 0
        existing = {str(r.get("quote_hash")) for r in self.read()}
        written = 0
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            for row in rows:
                if str(row.get("quote_hash")) in existing:
                    continue
                handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
                existing.add(str(row.get("quote_hash")))
                written += 1
        return written

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with open(self.path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
        return out

    def fixture_ids(self) -> frozenset[str]:
        return frozenset(str(r.get("fixture_id")) for r in self.read())
