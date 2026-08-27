"""Channel adapters for signal dispatch.

Each adapter implements transport-specific delivery logic.
Phase 3.4 provides stub implementations that simulate successful delivery.
Real provider integrations can be implemented without modifying the
core dispatch architecture.

No external provider dependency is required.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from src.services.dispatch.models import DispatchResult


# Supported channels
SUPPORTED_CHANNELS = frozenset({"web", "mobile", "telegram", "discord", "email", "webhook"})


class ChannelAdapter(ABC):
    """Abstract base for channel-specific delivery adapters.

    Each implementation handles the actual transport mechanism
    for a specific channel (e.g., Telegram bot API, webhook POST, etc.).
    """

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """The channel identifier this adapter handles."""
        ...

    @abstractmethod
    async def send(
        self,
        payload: dict,
        destination: Optional[str] = None,
    ) -> DispatchResult:
        """Send a payload to the channel destination.

        Args:
            payload: Canonical broadcast payload.
            destination: Channel-specific address (optional).

        Returns:
            DispatchResult with delivery outcome.
        """
        ...


class WebAdapter(ChannelAdapter):
    """Web channel adapter — delivers via web notification/feed."""

    @property
    def channel_name(self) -> str:
        return "web"

    async def send(self, payload: dict, destination: Optional[str] = None) -> DispatchResult:
        # Stub: web delivery is instant (stored in DB, available via API)
        return DispatchResult(
            success=True,
            status="DELIVERED",
            dispatched_at=datetime.now(timezone.utc),
        )


class MobileAdapter(ChannelAdapter):
    """Mobile push notification adapter."""

    @property
    def channel_name(self) -> str:
        return "mobile"

    async def send(self, payload: dict, destination: Optional[str] = None) -> DispatchResult:
        # Stub: simulates push notification dispatch
        return DispatchResult(
            success=True,
            status="DISPATCHED",
            dispatched_at=datetime.now(timezone.utc),
        )


class TelegramAdapter(ChannelAdapter):
    """Telegram bot API adapter."""

    @property
    def channel_name(self) -> str:
        return "telegram"

    async def send(self, payload: dict, destination: Optional[str] = None) -> DispatchResult:
        # Stub: simulates Telegram API call
        if not destination:
            return DispatchResult(
                success=False,
                status="FAILED",
                error_code="MISSING_DESTINATION",
                error_message="Telegram requires a chat_id or channel destination",
            )
        return DispatchResult(
            success=True,
            status="DISPATCHED",
            dispatched_at=datetime.now(timezone.utc),
        )


class DiscordAdapter(ChannelAdapter):
    """Discord webhook/bot adapter."""

    @property
    def channel_name(self) -> str:
        return "discord"

    async def send(self, payload: dict, destination: Optional[str] = None) -> DispatchResult:
        # Stub: simulates Discord webhook POST
        if not destination:
            return DispatchResult(
                success=False,
                status="FAILED",
                error_code="MISSING_DESTINATION",
                error_message="Discord requires a webhook URL or channel destination",
            )
        return DispatchResult(
            success=True,
            status="DISPATCHED",
            dispatched_at=datetime.now(timezone.utc),
        )


class EmailAdapter(ChannelAdapter):
    """Email delivery adapter."""

    @property
    def channel_name(self) -> str:
        return "email"

    async def send(self, payload: dict, destination: Optional[str] = None) -> DispatchResult:
        # Stub: simulates email send
        if not destination:
            return DispatchResult(
                success=False,
                status="FAILED",
                error_code="MISSING_DESTINATION",
                error_message="Email requires a recipient address",
            )
        return DispatchResult(
            success=True,
            status="DISPATCHED",
            dispatched_at=datetime.now(timezone.utc),
        )


class WebhookAdapter(ChannelAdapter):
    """Generic webhook adapter."""

    @property
    def channel_name(self) -> str:
        return "webhook"

    async def send(self, payload: dict, destination: Optional[str] = None) -> DispatchResult:
        # Stub: simulates HTTP POST to webhook URL
        if not destination:
            return DispatchResult(
                success=False,
                status="FAILED",
                error_code="MISSING_DESTINATION",
                error_message="Webhook requires a target URL",
            )
        return DispatchResult(
            success=True,
            status="DISPATCHED",
            dispatched_at=datetime.now(timezone.utc),
        )


# ═══════════════════════════════════════════════════════════════════
# ADAPTER REGISTRY
# ═══════════════════════════════════════════════════════════════════

_ADAPTERS: dict[str, ChannelAdapter] = {
    "web": WebAdapter(),
    "mobile": MobileAdapter(),
    "telegram": TelegramAdapter(),
    "discord": DiscordAdapter(),
    "email": EmailAdapter(),
    "webhook": WebhookAdapter(),
}


def get_adapter(channel: str) -> Optional[ChannelAdapter]:
    """Get the adapter for a channel. Returns None if unsupported."""
    return _ADAPTERS.get(channel)
