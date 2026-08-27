"""Signal dispatch abstraction and channel adapters.

The core platform knows WHAT should be dispatched.
The core platform does NOT know HOW specific transports work.

Architecture:
    SignalDispatcher (protocol)
        ↓
    ChannelAdapter (abstract)
        ├── WebAdapter
        ├── MobileAdapter
        ├── TelegramAdapter
        ├── DiscordAdapter
        ├── EmailAdapter
        └── WebhookAdapter
"""

from src.services.dispatch.models import DispatchResult
from src.services.dispatch.dispatcher import SignalDispatcher
from src.services.dispatch.adapters import (
    ChannelAdapter,
    WebAdapter,
    MobileAdapter,
    TelegramAdapter,
    DiscordAdapter,
    EmailAdapter,
    WebhookAdapter,
    get_adapter,
    SUPPORTED_CHANNELS,
)

__all__ = [
    "SignalDispatcher",
    "DispatchResult",
    "ChannelAdapter",
    "WebAdapter",
    "MobileAdapter",
    "TelegramAdapter",
    "DiscordAdapter",
    "EmailAdapter",
    "WebhookAdapter",
    "get_adapter",
    "SUPPORTED_CHANNELS",
]
