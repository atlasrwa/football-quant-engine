"""Request authentication context.

Provides the authenticated user context for API requests.
Extracts and validates JWT from Authorization header.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Authenticated request context.

    Derived from the verified JWT token. Never from client-supplied body fields.

    Attributes:
        user_id: The authenticated user's UUID.
        role: The user's role (user, creator, admin, system).
    """
    user_id: UUID
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role in ("admin", "system")

    @property
    def is_system(self) -> bool:
        return self.role == "system"


# System context used for CLI operations and background jobs
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

SYSTEM_CONTEXT = AuthContext(
    user_id=SYSTEM_USER_ID,
    role="system",
)
