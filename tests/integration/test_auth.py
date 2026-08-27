"""Integration tests for authentication tokens and password hashing."""

import pytest
from datetime import timedelta
from uuid import uuid4

from src.auth.passwords import hash_password, verify_password
from src.auth.tokens import create_access_token, decode_access_token, TokenError
from src.auth.context import AuthContext, SYSTEM_CONTEXT, SYSTEM_USER_ID


class TestPasswordHashing:
    """Test bcrypt password operations."""

    def test_hash_and_verify(self):
        """Password can be hashed and verified."""
        plain = "my-secure-password-123!"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_wrong_password_fails(self):
        """Wrong password does not verify."""
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_hash_is_not_plaintext(self):
        """Hash output is not the plaintext password."""
        plain = "secret"
        hashed = hash_password(plain)
        assert hashed != plain
        assert hashed.startswith("$2b$")  # bcrypt prefix


class TestJWTTokens:
    """Test JWT creation and validation."""

    def test_create_and_decode(self):
        """Token roundtrips successfully."""
        user_id = uuid4()
        token = create_access_token(user_id, "user")
        payload = decode_access_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["role"] == "user"

    def test_expired_token_rejected(self):
        """Expired token raises TokenError."""
        user_id = uuid4()
        token = create_access_token(
            user_id, "user", expires_delta=timedelta(seconds=-1)
        )
        with pytest.raises(TokenError, match="expired"):
            decode_access_token(token)

    def test_invalid_token_rejected(self):
        """Garbage token raises TokenError."""
        with pytest.raises(TokenError):
            decode_access_token("not.a.valid.token")

    def test_tampered_token_rejected(self):
        """Modified token fails signature verification."""
        user_id = uuid4()
        token = create_access_token(user_id, "user")
        # Tamper with payload
        parts = token.split(".")
        parts[1] = parts[1][:-2] + "XX"
        tampered = ".".join(parts)
        with pytest.raises(TokenError):
            decode_access_token(tampered)

    def test_admin_role_in_token(self):
        """Admin role is correctly encoded."""
        user_id = uuid4()
        token = create_access_token(user_id, "admin")
        payload = decode_access_token(token)
        assert payload["role"] == "admin"


class TestAuthContext:
    """Test the AuthContext dataclass."""

    def test_system_context(self):
        """System context has expected values."""
        assert SYSTEM_CONTEXT.user_id == SYSTEM_USER_ID
        assert SYSTEM_CONTEXT.role == "system"
        assert SYSTEM_CONTEXT.is_admin is True
        assert SYSTEM_CONTEXT.is_system is True

    def test_user_context(self):
        """Regular user context is not admin."""
        ctx = AuthContext(user_id=uuid4(), role="user")
        assert ctx.is_admin is False
        assert ctx.is_system is False

    def test_context_is_immutable(self):
        """AuthContext is frozen."""
        ctx = AuthContext(user_id=uuid4(), role="user")
        with pytest.raises(AttributeError):
            ctx.role = "admin"  # type: ignore
