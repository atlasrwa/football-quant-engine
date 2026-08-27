"""Signal dispatcher — generic dispatch abstraction.

Receives an authoritative broadcast payload and dispatches it to a
channel adapter, returning a normalized delivery result.

The dispatcher is transport-agnostic: it delegates actual delivery
to the appropriate ChannelAdapter implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.services.dispatch.models import DispatchResult
from src.services.dispatch.adapters import get_adapter


class SignalDispatcher:
    """Generic signal dispatcher.

    Dispatches a broadcast payload to a specific channel using the
    appropriate adapter. Returns a normalized DispatchResult.

    Usage:
        dispatcher = SignalDispatcher()
        result = await dispatcher.dispatch(
            channel="telegram",
            payload=canonical_payload,
            destination="@channel_name",
        )
    """

    async def dispatch(
        self,
        channel: str,
        payload: dict,
        destination: Optional[str] = None,
    ) -> DispatchResult:
        """Dispatch a payload to a channel.

        Args:
            channel: Target channel (web, mobile, telegram, etc.).
            payload: Canonical broadcast payload dict.
            destination: Channel-specific destination address.

        Returns:
            DispatchResult with delivery outcome.
        """
        adapter = get_adapter(channel)
        if adapter is None:
            return DispatchResult(
                success=False,
                status="FAILED",
                error_code="UNSUPPORTED_CHANNEL",
                error_message=f"Channel '{channel}' is not supported",
            )

        try:
            result = await adapter.send(payload, destination)
            return result
        except Exception as e:
            return DispatchResult(
                success=False,
                status="FAILED",
                dispatched_at=datetime.now(timezone.utc),
                error_code="DISPATCH_ERROR",
                error_message=str(e)[:500],
            )
