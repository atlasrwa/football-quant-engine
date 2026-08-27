"""PostgreSQL implementation of UserRepository."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

import asyncpg

from src.persistence.repositories import UserRecord


class PgUserRepository:
    """PostgreSQL-backed user repository.

    Operates on the `users` table. Expects a connection with
    appropriate RLS context already set.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(self, user: UserRecord) -> UserRecord:
        """Insert a new user and return the full record."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO users (id, username, email, display_name, password_hash, role, status, avatar_url, bio, primary_wallet_address)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING *
            """,
            user.id,
            user.username,
            user.email,
            user.display_name,
            user.password_hash,
            user.role,
            user.status,
            user.avatar_url,
            user.bio,
            user.primary_wallet_address,
        )
        return self._row_to_record(row)

    async def get_by_id(self, user_id: UUID) -> Optional[UserRecord]:
        """Find user by UUID."""
        row = await self._conn.fetchrow(
            "SELECT * FROM users WHERE id = $1", user_id
        )
        return self._row_to_record(row) if row else None

    async def get_by_username(self, username: str) -> Optional[UserRecord]:
        """Find user by username (case-insensitive)."""
        row = await self._conn.fetchrow(
            "SELECT * FROM users WHERE LOWER(username) = LOWER($1)", username
        )
        return self._row_to_record(row) if row else None

    async def get_by_email(self, email: str) -> Optional[UserRecord]:
        """Find user by email (case-insensitive)."""
        row = await self._conn.fetchrow(
            "SELECT * FROM users WHERE LOWER(email) = LOWER($1)", email
        )
        return self._row_to_record(row) if row else None

    async def update(self, user_id: UUID, **fields) -> Optional[UserRecord]:
        """Update specific fields on a user."""
        if not fields:
            return await self.get_by_id(user_id)

        # Build SET clause dynamically
        set_parts = []
        values = []
        for i, (key, value) in enumerate(fields.items(), start=1):
            set_parts.append(f"{key} = ${i}")
            values.append(value)

        values.append(user_id)
        query = f"UPDATE users SET {', '.join(set_parts)} WHERE id = ${len(values)} RETURNING *"
        row = await self._conn.fetchrow(query, *values)
        return self._row_to_record(row) if row else None

    async def update_last_login(self, user_id: UUID) -> None:
        """Update last_login_at to current timestamp."""
        await self._conn.execute(
            "UPDATE users SET last_login_at = NOW() WHERE id = $1", user_id
        )

    @staticmethod
    def _row_to_record(row: asyncpg.Record) -> UserRecord:
        """Convert a database row to a UserRecord."""
        return UserRecord(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            display_name=row["display_name"],
            password_hash=row["password_hash"],
            role=row["role"],
            status=row["status"],
            avatar_url=row["avatar_url"],
            bio=row["bio"],
            primary_wallet_address=row["primary_wallet_address"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_login_at=row["last_login_at"],
        )
