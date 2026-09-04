"""PostgreSQL repository for immutable market-price observations."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from uuid import UUID

import asyncpg

from src.domain.market import compute_quote_hash, compute_raw_payload_hash


_PROVENANCE_COLUMNS = """
    id, match_id, market_type, line, selection, price_type, odds, observed_at,
    source, bookmaker, provider_source_time, retrieved_at, quote_status,
    kickoff_at, raw_payload, raw_payload_hash, quote_hash, capture_run_id,
    provider_quote_id, timestamp_semantics, ingested_at
"""


class PgMarketPriceRepository:
    """Append-only repository with transactional, idempotent capture writes."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    @staticmethod
    def _quote_hash(record: dict[str, Any]) -> str:
        computed = compute_quote_hash(
            match_id=record["match_id"],
            market_type=record["market_type"],
            line=record.get("line"),
            side=record["selection"],
            odds=record["odds"],
            timestamp=record["observed_at"],
            source=record["source"],
            bookmaker=record.get("bookmaker"),
            provider_source_time=record.get("provider_source_time"),
            provider_quote_id=record.get("provider_quote_id"),
        )
        supplied = record.get("quote_hash")
        if supplied is not None and supplied != computed:
            raise ValueError("quote_hash does not match quote identity")
        return computed

    @staticmethod
    def _enum_value(value: Any) -> Any:
        return value.value if isinstance(value, Enum) else value

    async def _insert_record(self, record: dict[str, Any]) -> tuple[int, bool]:
        raw_payload = record.get("raw_payload")
        raw_payload_hash = record.get("raw_payload_hash")
        if raw_payload_hash is None and raw_payload is not None:
            raw_payload_hash = compute_raw_payload_hash(raw_payload)
        quote_hash = self._quote_hash(record)
        bookmaker = record.get("bookmaker") or record["source"]
        retrieved_at = record.get("retrieved_at") or record["observed_at"]
        timestamp_semantics = self._enum_value(record.get("timestamp_semantics")) or (
            "PROVIDER_SOURCE_TIME"
            if record.get("provider_source_time") is not None
            else "RETRIEVAL_TIME"
        )
        quote_status = self._enum_value(record.get("quote_status", "ACTIVE"))

        row = await self._conn.fetchrow(
            """
            INSERT INTO market_prices (
                match_id, market_type, line, selection, price_type, odds,
                observed_at, source, raw_payload, bookmaker,
                provider_source_time, retrieved_at, quote_status, kickoff_at,
                raw_payload_hash, quote_hash, capture_run_id,
                provider_quote_id, timestamp_semantics
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19
            )
            ON CONFLICT (quote_hash) DO NOTHING
            RETURNING id
            """,
            record["match_id"], self._enum_value(record["market_type"]),
            record.get("line"), self._enum_value(record["selection"]),
            self._enum_value(record["price_type"]), record["odds"],
            record["observed_at"], record["source"],
            json.dumps(raw_payload) if raw_payload is not None else None,
            bookmaker, record.get("provider_source_time"), retrieved_at,
            quote_status, record.get("kickoff_at"), raw_payload_hash, quote_hash,
            record.get("capture_run_id"), record.get("provider_quote_id"),
            timestamp_semantics,
        )
        if row is not None:
            return row["id"], True

        # A separate statement gets a fresh READ COMMITTED snapshot after a
        # concurrent winner commits; the one-statement CTE pattern can miss it.
        row = await self._conn.fetchrow(
            "SELECT id FROM market_prices WHERE quote_hash = $1", quote_hash
        )
        if row is None:
            raise RuntimeError("Idempotent market price insert returned no identity")
        return row["id"], False

    async def insert(
        self,
        match_id: int,
        market_type: str,
        selection: str,
        price_type: str,
        odds: float,
        observed_at: datetime,
        source: str,
        line: Optional[float] = None,
        raw_payload: Optional[dict] = None,
        *,
        bookmaker: Optional[str] = None,
        provider_source_time: Optional[datetime] = None,
        retrieved_at: Optional[datetime] = None,
        quote_status: str = "ACTIVE",
        kickoff_at: Optional[datetime] = None,
        raw_payload_hash: Optional[str] = None,
        quote_hash: Optional[str] = None,
        capture_run_id: Optional[UUID] = None,
        provider_quote_id: Optional[str] = None,
        timestamp_semantics: Optional[str] = None,
    ) -> int:
        """Insert a quote idempotently and return its new or existing row ID."""
        row_id, _ = await self._insert_record(locals())
        return row_id

    async def insert_batch(self, records: List[dict]) -> int:
        """Atomically insert a batch, returning the number of new quote rows.

        Replaying an identical batch succeeds and returns zero. Any invalid row
        rolls back all new rows in the batch.
        """
        inserted = 0
        async with self._conn.transaction():
            for record in records:
                _, was_inserted = await self._insert_record(record)
                inserted += int(was_inserted)
        return inserted

    async def _create_capture_run(
        self,
        *,
        provider: str,
        source: str,
        started_at: datetime,
        completed_at: Optional[datetime] = None,
        status: str = "COMPLETED",
        request_id: Optional[str] = None,
        raw_payload_hash: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> tuple[dict, bool]:
        completed_at = completed_at or started_at
        row = await self._conn.fetchrow(
            """
            INSERT INTO market_price_capture_runs (
                provider, source, started_at, completed_at, status,
                request_id, raw_payload_hash, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            ON CONFLICT (provider, source, request_id)
                WHERE request_id IS NOT NULL DO NOTHING
            RETURNING *
            """,
            provider, source, started_at, completed_at, status, request_id,
            raw_payload_hash, json.dumps(metadata) if metadata is not None else None,
        )
        if row is not None:
            return dict(row), True
        row = await self._conn.fetchrow(
            """
            SELECT * FROM market_price_capture_runs
            WHERE provider = $1 AND source = $2 AND request_id = $3
            """,
            provider, source, request_id,
        )
        if row is None:
            raise RuntimeError("Capture run insert returned no row")
        return dict(row), False

    async def create_capture_run(
        self,
        *,
        provider: str,
        source: str,
        started_at: datetime,
        completed_at: Optional[datetime] = None,
        status: str = "COMPLETED",
        request_id: Optional[str] = None,
        raw_payload_hash: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Create or return an immutable, request-idempotent terminal run."""
        run, _ = await self._create_capture_run(
            provider=provider,
            source=source,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            request_id=request_id,
            raw_payload_hash=raw_payload_hash,
            metadata=metadata,
        )
        return run

    async def insert_capture_batch(
        self,
        records: List[dict],
        *,
        provider: str,
        source: str,
        started_at: datetime,
        completed_at: datetime,
        status: str = "COMPLETED",
        request_id: Optional[str] = None,
        raw_payload_hash: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> tuple[dict, int]:
        """Atomically persist a terminal run and freeze its quote membership."""
        async with self._conn.transaction():
            run, created = await self._create_capture_run(
                provider=provider,
                source=source,
                started_at=started_at,
                completed_at=completed_at,
                status=status,
                request_id=request_id,
                raw_payload_hash=raw_payload_hash,
                metadata=metadata,
            )
            expected_hashes = {self._quote_hash(record) for record in records}
            if not created:
                rows = await self._conn.fetch(
                    "SELECT quote_hash FROM market_prices WHERE capture_run_id = $1",
                    run["id"],
                )
                persisted_hashes = {row["quote_hash"] for row in rows}
                if persisted_hashes != expected_hashes:
                    raise ValueError(
                        "capture request replay does not match immutable run quotes"
                    )
                return run, 0

            inserted = 0
            for original in records:
                record = dict(original)
                supplied_run_id = record.get("capture_run_id")
                if supplied_run_id is not None and supplied_run_id != run["id"]:
                    raise ValueError("record capture_run_id does not match capture run")
                record["capture_run_id"] = run["id"]
                _, was_inserted = await self._insert_record(record)
                inserted += int(was_inserted)
        return run, inserted

    async def get_price_history(
        self,
        match_id: int,
        market_type: str,
        selection: str,
        *,
        line: Optional[float] = None,
        bookmaker: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[dict]:
        """Return chronological quote history with complete capture provenance."""
        query = f"""
            SELECT {_PROVENANCE_COLUMNS}
            FROM market_prices
            WHERE match_id = $1 AND market_type = $2 AND selection = $3
        """
        params: list[Any] = [match_id, market_type, selection]
        if line is not None:
            params.append(line)
            query += f" AND line = ${len(params)}"
        if bookmaker is not None:
            params.append(bookmaker)
            query += f" AND bookmaker = ${len(params)}"
        if source is not None:
            params.append(source)
            query += f" AND source = ${len(params)}"
        query += " ORDER BY observed_at ASC, id ASC"
        rows = await self._conn.fetch(query, *params)
        return [dict(row) for row in rows]

    async def get_last_quote_before_kickoff(
        self,
        match_id: int,
        market_type: str,
        selection: str,
        *,
        line: Optional[float],
        bookmaker: str,
        source: str,
        kickoff_at: datetime,
    ) -> Optional[dict]:
        """Return the exact-line/book/source last active quote before kickoff."""
        row = await self._conn.fetchrow(
            f"""
            SELECT {_PROVENANCE_COLUMNS}
            FROM market_prices
            WHERE match_id = $1
              AND market_type = $2
              AND selection = $3
              AND line IS NOT DISTINCT FROM $4
              AND bookmaker = $5
              AND source = $6
              AND observed_at < $7
              AND quote_status = 'ACTIVE'
              AND price_type <> 'LIVE'
            ORDER BY observed_at DESC, quote_hash DESC
            LIMIT 1
            """,
            match_id, market_type, selection, line, bookmaker, source, kickoff_at,
        )
        return dict(row) if row else None

    async def get_closing_price(
        self,
        match_id: int,
        market_type: str,
        selection: str,
        source: Optional[str] = None,
        *,
        line: Optional[float] = None,
        bookmaker: Optional[str] = None,
        kickoff_at: Optional[datetime] = None,
    ) -> Optional[float]:
        """Compatibility wrapper returning only odds.

        Supplying ``kickoff_at`` requires exact line/book/source filters and uses
        the hardened strictly-pre-kickoff selector. Without it, the legacy
        CLOSING lookup remains available with optional exact filters.
        """
        if kickoff_at is not None:
            if bookmaker is None or source is None:
                raise ValueError("bookmaker and source are required with kickoff_at")
            quote = await self.get_last_quote_before_kickoff(
                match_id, market_type, selection, line=line,
                bookmaker=bookmaker, source=source, kickoff_at=kickoff_at,
            )
            return quote["odds"] if quote else None

        query = """
            SELECT odds FROM market_prices
            WHERE match_id = $1 AND market_type = $2 AND selection = $3
              AND price_type = 'CLOSING'
        """
        params: list[Any] = [match_id, market_type, selection]
        if source is not None:
            params.append(source)
            query += f" AND source = ${len(params)}"
        if line is not None:
            params.append(line)
            query += f" AND line = ${len(params)}"
        if bookmaker is not None:
            params.append(bookmaker)
            query += f" AND bookmaker = ${len(params)}"
        query += " ORDER BY observed_at DESC, id DESC LIMIT 1"
        row = await self._conn.fetchrow(query, *params)
        return row["odds"] if row else None
