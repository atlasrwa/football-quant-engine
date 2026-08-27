"""Integration tests for users table and UserRepository."""

import pytest
import asyncpg
from uuid import uuid4

from src.persistence.pg_user_repository import PgUserRepository
from src.persistence.repositories import UserRecord


pytestmark = pytest.mark.asyncio


class TestUserCreation:
    """Test user registration and uniqueness constraints."""

    async def test_create_user(self, db_conn):
        """Basic user creation succeeds."""
        repo = PgUserRepository(db_conn)
        user = UserRecord(
            id=uuid4(),
            username="testuser1",
            email="test@example.com",
            display_name="Test User",
            password_hash="$2b$12$fakehash",
            role="user",
            status="active",
        )
        created = await repo.create(user)
        assert created.id == user.id
        assert created.username == "testuser1"
        assert created.email == "test@example.com"
        assert created.role == "user"
        assert created.status == "active"
        assert created.created_at is not None

    async def test_duplicate_username_rejected(self, db_conn):
        """Duplicate username (case-insensitive) raises UniqueViolation."""
        repo = PgUserRepository(db_conn)
        user1 = UserRecord(
            id=uuid4(), username="UniqueUser", email="a@x.com",
            display_name="A", password_hash=None, role="user", status="active",
        )
        await repo.create(user1)

        user2 = UserRecord(
            id=uuid4(), username="uniqueuser",  # same, different case
            email="b@x.com", display_name="B",
            password_hash=None, role="user", status="active",
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await repo.create(user2)

    async def test_duplicate_email_rejected(self, db_conn):
        """Duplicate email (case-insensitive) raises UniqueViolation."""
        repo = PgUserRepository(db_conn)
        user1 = UserRecord(
            id=uuid4(), username="user_a", email="Same@Email.com",
            display_name="A", password_hash=None, role="user", status="active",
        )
        await repo.create(user1)

        user2 = UserRecord(
            id=uuid4(), username="user_b", email="same@email.com",
            display_name="B", password_hash=None, role="user", status="active",
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await repo.create(user2)

    async def test_null_email_allowed_multiple(self, db_conn):
        """Multiple users with NULL email are allowed."""
        repo = PgUserRepository(db_conn)
        user1 = UserRecord(
            id=uuid4(), username="wallet_user_1", email=None,
            display_name="W1", password_hash=None, role="user", status="active",
        )
        user2 = UserRecord(
            id=uuid4(), username="wallet_user_2", email=None,
            display_name="W2", password_hash=None, role="user", status="active",
        )
        await repo.create(user1)
        await repo.create(user2)  # Should not raise

    async def test_get_by_username_case_insensitive(self, db_conn):
        """Username lookup is case-insensitive."""
        repo = PgUserRepository(db_conn)
        user = UserRecord(
            id=uuid4(), username="CaseSensitive", email="cs@x.com",
            display_name="CS", password_hash=None, role="user", status="active",
        )
        await repo.create(user)
        found = await repo.get_by_username("casesensitive")
        assert found is not None
        assert found.id == user.id

    async def test_get_nonexistent_returns_none(self, db_conn):
        """Looking up a nonexistent user returns None."""
        repo = PgUserRepository(db_conn)
        assert await repo.get_by_id(uuid4()) is None
        assert await repo.get_by_username("nobody") is None
        assert await repo.get_by_email("nobody@nowhere.com") is None


class TestUserDisabling:
    """Test soft-deactivation behavior."""

    async def test_disable_user(self, db_conn):
        """User status can be set to disabled."""
        repo = PgUserRepository(db_conn)
        user = UserRecord(
            id=uuid4(), username="to_disable", email="d@x.com",
            display_name="D", password_hash=None, role="user", status="active",
        )
        await repo.create(user)
        updated = await repo.update(user.id, status="disabled")
        assert updated.status == "disabled"

    async def test_invalid_status_rejected(self, db_conn):
        """Invalid status value is rejected by CHECK constraint."""
        repo = PgUserRepository(db_conn)
        user = UserRecord(
            id=uuid4(), username="bad_status", email="bs@x.com",
            display_name="BS", password_hash=None, role="user", status="active",
        )
        await repo.create(user)
        with pytest.raises(asyncpg.CheckViolationError):
            await repo.update(user.id, status="deleted")


class TestSystemUser:
    """Test the system user exists and has expected properties."""

    async def test_system_user_exists(self, db_conn, system_user_id):
        """The deterministic system user exists after migration."""
        repo = PgUserRepository(db_conn)
        user = await repo.get_by_id(system_user_id)
        assert user is not None
        assert user.username == "_system"
        assert user.role == "system"
        assert user.status == "active"
