"""1-Click bet deep-link generator for crypto betting platforms.

Translates Signal objects into actionable direct links for Stake,
Rollbit, and Polymarket, with affiliate tag injection and Telegram
inline keyboard button generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List
from urllib.parse import quote, urlencode

from src.engine.analysis.evaluator import Signal

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeepLink:
    """A platform-specific betting deep-link."""

    platform: str  # "stake" | "rollbit" | "polymarket"
    url: str
    label: str
    affiliate_tag: str | None = None


@dataclass(frozen=True, slots=True)
class DeepLinkConfig:
    """Configuration for deep-link generation."""

    stake_base_url: str = "https://stake.com/sports/football"
    rollbit_base_url: str = "https://rollbit.com/sports/soccer"
    polymarket_base_url: str = "https://polymarket.com/event"
    affiliate_stake: str | None = None
    affiliate_rollbit: str | None = None


class DeepLinker:
    """Generates platform-specific deep-links from Signal objects.

    Supports Stake, Rollbit, and Polymarket with optional affiliate
    tag injection for monetization.
    """

    def __init__(self, config: DeepLinkConfig | None = None) -> None:
        self.config = config or DeepLinkConfig()

    def generate_links(
        self, signal: Signal, match_info: dict
    ) -> List[DeepLink]:
        """Generate deep-links for all supported platforms.

        Args:
            signal: The betting signal.
            match_info: Dict with home_team, away_team, league, market.

        Returns:
            List of DeepLink objects for each platform.
        """
        market = match_info.get("market", signal.direction.lower())
        links: List[DeepLink] = []

        links.append(DeepLink(
            platform="stake",
            url=self.generate_stake_url(match_info, market),
            label="Place Bet on Stake",
            affiliate_tag=self.config.affiliate_stake,
        ))

        links.append(DeepLink(
            platform="rollbit",
            url=self.generate_rollbit_url(match_info, market),
            label="Place Bet on Rollbit",
            affiliate_tag=self.config.affiliate_rollbit,
        ))

        links.append(DeepLink(
            platform="polymarket",
            url=self.generate_polymarket_url(match_info, market),
            label="View on Polymarket",
            affiliate_tag=None,
        ))

        return links

    def generate_stake_url(self, match_info: dict, market: str) -> str:
        """Generate Stake.com deep-link URL.

        Args:
            match_info: Match details dict.
            market: Market type string.

        Returns:
            Formatted URL string.
        """
        home = match_info.get("home_team", "home")
        away = match_info.get("away_team", "away")
        event = f"{home}-vs-{away}".lower().replace(" ", "-")
        event = quote(event, safe="-")

        url = f"{self.config.stake_base_url}/{event}"

        params = {"market": market}
        if self.config.affiliate_stake:
            params["ref"] = self.config.affiliate_stake

        return f"{url}?{urlencode(params)}"

    def generate_rollbit_url(self, match_info: dict, market: str) -> str:
        """Generate Rollbit deep-link URL.

        Args:
            match_info: Match details dict.
            market: Market type string.

        Returns:
            Formatted URL string.
        """
        home = match_info.get("home_team", "home")
        away = match_info.get("away_team", "away")
        event = f"{home}-vs-{away}".lower().replace(" ", "-")
        event = quote(event, safe="-")

        url = f"{self.config.rollbit_base_url}/{event}"

        params = {"market": market}
        if self.config.affiliate_rollbit:
            params["aff"] = self.config.affiliate_rollbit

        return f"{url}?{urlencode(params)}"

    def generate_polymarket_url(self, match_info: dict, market: str) -> str:
        """Generate Polymarket deep-link URL.

        Args:
            match_info: Match details dict.
            market: Market type string.

        Returns:
            Formatted URL string.
        """
        home = match_info.get("home_team", "home")
        away = match_info.get("away_team", "away")
        slug = f"{home}-{away}-{market}".lower().replace(" ", "-")
        slug = quote(slug, safe="-")

        return f"{self.config.polymarket_base_url}/{slug}"

    def generate_telegram_buttons(
        self, links: List[DeepLink], proof_hash: str
    ) -> List[dict]:
        """Generate Telegram inline keyboard button definitions.

        Args:
            links: Generated deep-links.
            proof_hash: Proof-of-Alpha hash for verification button.

        Returns:
            List of Telegram inline keyboard button dicts.
        """
        buttons: List[dict] = []

        for link in links:
            buttons.append({
                "text": link.label,
                "url": link.url,
            })

        # Add proof verification button
        buttons.append({
            "text": "View Proof-of-Alpha Hash",
            "callback_data": f"proof:{proof_hash[:32]}",
        })

        return buttons

    def generate_telegram_keyboard(
        self, links: List[DeepLink], proof_hash: str
    ) -> dict:
        """Generate full Telegram inline keyboard markup.

        Args:
            links: Generated deep-links.
            proof_hash: Proof-of-Alpha hash.

        Returns:
            Telegram InlineKeyboardMarkup dict.
        """
        buttons = self.generate_telegram_buttons(links, proof_hash)
        # Arrange as rows: one button per row
        rows = [[btn] for btn in buttons]
        return {"inline_keyboard": rows}
