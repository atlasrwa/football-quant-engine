"""Password hashing utilities using passlib + bcrypt."""

from __future__ import annotations

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt.

    Args:
        plain: The plaintext password.

    Returns:
        The bcrypt hash string.
    """
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored hash.

    Args:
        plain: The plaintext password attempt.
        hashed: The stored bcrypt hash.

    Returns:
        True if the password matches.
    """
    return _pwd_context.verify(plain, hashed)
