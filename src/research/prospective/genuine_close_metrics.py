"""Canonical genuine-close counting over the append-only capture store.

This module answers ONE operational observability question for the research
Telegram monitor: how many of our captured fixtures actually have at least one
GENUINE closing observation, using the repository's EXISTING scientific
definition of a genuine close. It does NOT invent a new definition.

Canonical predicate reused
--------------------------
The single source of truth for "is this a genuine close?" is
:func:`src.research.prospective.odds_capture.resolve_genuine_close` (with its
helper :func:`genuine_close`). That predicate is strictly fail-closed and:

- requires a KNOWN kickoff (unknown kickoff -> NO_GENUINE_CLOSE);
- derives the close ONLY from our own timestamped snapshots with
  ``observed_at`` strictly before kickoff (``observed_at`` implies a real,
  positive observation time — the ``closing_timestamp > 0`` discipline);
- NEVER falls back to the provider ``last_seen`` sighting;
- returns an explicit :class:`CloseResult` rather than a bare ``None``.

This module simply groups the persisted capture records into the exact market
keys that predicate expects and counts the GENUINE_CLOSE outcomes. No genuine
close is fabricated; no threshold is invented.

Fail-closed reporting
---------------------
If the canonical capture source is missing, unreadable, or malformed, the count
is reported as :data:`UNKNOWN` (``None``) rather than a fake ``0``. A real
zero (the store is readable but contains no genuine close yet) is distinct from
UNKNOWN (we could not trust the source) and the monitor renders them
differently.

Two distinct, explicitly-named concepts are computed (never mixed under one
ambiguous label):

- ``fixtures_with_genuine_close`` — number of distinct fixtures that have at
  least one genuine close (the operationally useful headline);
- ``genuine_closing_keys`` — number of distinct (fixture, bookmaker, market,
  selection, line) keys that resolve to a genuine close (a finer, key-level
  count).

No provider call, no model, no network. Pure read over persisted state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.research.observation.model import MISSING
from src.research.prospective.odds_capture import (
    CapturedPrice,
    CloseStatus,
    OddsSemantics,
    resolve_genuine_close,
)
from src.research.prospective.storage import CaptureStore

#: Sentinel for "source unavailable / malformed / unreadable" — NOT zero.
UNKNOWN: None = None


def _semantics_from_raw_status(raw_status: Optional[str]) -> OddsSemantics:
    """Map a persisted ``raw_status`` string to :class:`OddsSemantics`.

    Only our own prospective snapshots can ever contribute to a genuine close
    (that is enforced downstream by :func:`resolve_genuine_close`). An unknown
    or missing status maps to the provider ``last_seen`` semantics, which the
    canonical predicate refuses to treat as a genuine close — so a malformed
    status can never masquerade as a genuine close.
    """
    try:
        return OddsSemantics(str(raw_status))
    except (ValueError, TypeError):
        # Unknown status is treated as a non-genuine sighting (fail closed):
        # resolve_genuine_close only accepts PROSPECTIVE_SNAPSHOT /
        # PROSPECTIVE_LAST_BEFORE_KICKOFF, so this can never count.
        return OddsSemantics.API_LAST_SEEN


def _parse_odds_concept(
    concept: str,
) -> Optional[tuple[str, str, Optional[float], str]]:
    """Parse ``odds:<market>:<selection>:<line>:<bookmaker>``.

    Returns (market, selection, line, bookmaker) or None if not an odds concept.
    Mirrors the parsing already used by the price-discovery dataset builder so
    the market-key semantics are identical (bookmaker is the LAST segment; the
    line is the segment before it and may be empty -> None).
    """
    parts = concept.split(":")
    if len(parts) < 4 or parts[0] != "odds":
        return None
    bookmaker = parts[-1]
    market = parts[1]
    selection = parts[2]
    line_seg = ":".join(parts[3:-1]) if len(parts) > 4 else ""
    line: Optional[float]
    if line_seg == "":
        line = None
    else:
        try:
            line = float(line_seg)
        except ValueError:
            line = None
    return market, selection, line, bookmaker


@dataclass(frozen=True)
class GenuineCloseCounts:
    """Explicitly-named genuine-close counts (never an ambiguous single label).

    ``available`` is False ONLY when the canonical source could not be trusted
    (missing / unreadable / malformed). When ``available`` is False, both counts
    are ``None`` (UNKNOWN) — never a fabricated 0.
    """

    available: bool
    fixtures_with_genuine_close: Optional[int]
    genuine_closing_keys: Optional[int]

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "fixtures_with_genuine_close": self.fixtures_with_genuine_close,
            "genuine_closing_keys": self.genuine_closing_keys,
        }


def _unknown_counts() -> GenuineCloseCounts:
    return GenuineCloseCounts(
        available=False,
        fixtures_with_genuine_close=UNKNOWN,
        genuine_closing_keys=UNKNOWN,
    )


def count_genuine_closes(store: CaptureStore) -> GenuineCloseCounts:
    """Count genuine closes in the capture store using the canonical predicate.

    Groups odds records into exact (fixture, bookmaker, market, selection, line)
    keys, reconstructs the :class:`CapturedPrice` snapshots for each key, and
    asks :func:`resolve_genuine_close` (the canonical, fail-closed predicate)
    whether that key has a genuine close. Counts distinct fixtures and distinct
    keys that resolve to ``GENUINE_CLOSE``.

    Fails closed to UNKNOWN (``available=False``) if the store cannot be read or
    a record is malformed — a broken source never presents as ``0``. A capture
    file that does not exist yet is also treated as UNKNOWN (the canonical
    source is unavailable), never a fabricated ``0``.
    """
    # Unavailable source (file absent) -> UNKNOWN, not 0.
    if not Path(store.path).exists():
        return _unknown_counts()

    # key -> list[CapturedPrice]; also remember the key's kickoff (event_time).
    keyed_snapshots: dict[tuple, list[CapturedPrice]] = {}
    key_kickoff: dict[tuple, Optional[float]] = {}

    try:
        for rec in store.read_all():
            concept = getattr(rec, "concept", None)
            if not isinstance(concept, str):
                # A record with no concept is malformed for this purpose.
                raise ValueError("capture record missing a string concept")
            parsed = _parse_odds_concept(concept)
            if parsed is None:
                continue  # not an odds record; irrelevant to genuine closes
            market, selection, line, bookmaker = parsed

            value = rec.value
            if value is MISSING or value is None:
                continue  # observed-but-absent; cannot be a priced close
            try:
                decimal_odds = float(value)
            except (TypeError, ValueError):
                continue  # non-numeric odds value: skip (never fabricate)

            fixture_id = rec.canonical_entity_id
            key = (fixture_id, bookmaker, market, selection, line)
            kickoff = rec.event_time  # unix kickoff, or None if unknown
            # Record the key's kickoff once (records for one key share kickoff).
            key_kickoff.setdefault(key, kickoff)

            keyed_snapshots.setdefault(key, []).append(
                CapturedPrice(
                    bookmaker=bookmaker,
                    market=market,
                    selection=selection,
                    line=line,
                    decimal_odds=decimal_odds,
                    semantics=_semantics_from_raw_status(rec.raw_status),
                    observed_at=rec.observed_at,
                    provider_payload_hash=getattr(rec, "raw_payload_hash", ""),
                )
            )
    except (OSError, ValueError, KeyError, TypeError, EOFError):
        # Missing / unreadable / malformed canonical source -> UNKNOWN, not 0.
        # EOFError covers a truncated/partial gzip stream (zlib raises EOFError,
        # NOT OSError, when the compressed data ends before the end-of-stream
        # marker); gzip.BadGzipFile is already an OSError subclass.
        return _unknown_counts()

    fixtures_with_close: set = set()
    genuine_keys = 0
    for key, snapshots in keyed_snapshots.items():
        fixture_id, bookmaker, market, selection, line = key
        result = resolve_genuine_close(
            snapshots,
            kickoff_ts=key_kickoff.get(key),
            bookmaker=bookmaker,
            market=market,
            selection=selection,
            line=line,
        )
        if result.status == CloseStatus.GENUINE_CLOSE:
            genuine_keys += 1
            fixtures_with_close.add(fixture_id)

    return GenuineCloseCounts(
        available=True,
        fixtures_with_genuine_close=len(fixtures_with_close),
        genuine_closing_keys=genuine_keys,
    )


def genuine_close_counts_from_root(
    capture_root: Path = Path("data/prospective"),
) -> GenuineCloseCounts:
    """Convenience: build the canonical store from the capture root and count.

    If the store itself cannot even be constructed (e.g. an unreadable root, or
    a truncated/partial gzip that fails while the store primes its idempotency
    set), fail closed to UNKNOWN rather than raising into the monitor. A
    truncated gzip raises ``EOFError`` (not ``OSError``) at construction, so it
    is caught explicitly here too.
    """
    try:
        store = CaptureStore(path=Path(capture_root) / "captures.jsonl.gz")
    except (OSError, EOFError):
        return _unknown_counts()
    return count_genuine_closes(store)
