"""TheStatsAPI contract, verified against the live reference.

Source of truth: ``https://api.thestatsapi.com/llms.txt`` (fetched and
cross-checked while building this package). This module does NOT invent
endpoints or fields. Every endpoint / field referenced by the prospective
capture layer is declared here and traced to the live docs.

Where the repository's existing client
(``src/research/thestatsapi/client.py``) disagrees with the live docs, the
discrepancy is documented in :data:`KNOWN_DISCREPANCIES`, backward
compatibility is preserved (the legacy client is untouched), and the
prospective plane fails closed rather than guessing.

Nothing here performs I/O. It is a declarative contract plus a small
read-only, key-redacting request helper used by the collector.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Optional

# ---------------------------------------------------------------------------
# Verified base URL / auth (live docs)
# ---------------------------------------------------------------------------

#: Live docs "Base URL": ``https://api.thestatsapi.com/api``.
LIVE_BASE_URL: Final = "https://api.thestatsapi.com/api"

#: Live docs "Authentication": Bearer token in the ``Authorization`` header.
LIVE_AUTH_SCHEME: Final = "bearer_header"

#: Environment variable holding the API key (never logged / committed).
#: The documented / preferred name is ``THESTATSAPI_API_KEY``. Some deploys
#: (cron, .env) store it under the shorter ``THESTATS_API_KEY`` — accepted as an
#: alias so an available key is used rather than failing closed on a name gap.
ENV_API_KEY: Final = "THESTATSAPI_API_KEY"
ENV_API_KEY_ALIASES: Final = ("THESTATSAPI_API_KEY", "THESTATS_API_KEY")


def resolve_api_key() -> str:
    """Return the API key from the environment, or "" if none is set.

    Checks names in ``ENV_API_KEY_ALIASES`` order (documented name first). The
    value is returned to the caller for header construction only; it is never
    logged, hashed, or serialized by this module.
    """
    import os

    for name in ENV_API_KEY_ALIASES:
        val = os.environ.get(name, "")
        if val:
            return val
    return ""


def api_key_available() -> bool:
    """Whether a non-empty API key is available under any accepted name."""
    return bool(resolve_api_key())

#: Optional base-url override for tests / self-hosted mirrors.
ENV_BASE_URL: Final = "THESTATSAPI_BASE_URL"


# ---------------------------------------------------------------------------
# Verified endpoints (only those this package relies on)
# ---------------------------------------------------------------------------


class Endpoint(str, Enum):
    """Endpoints verified present in the live ``llms.txt``.

    Path templates use ``{match_id}`` etc. placeholders. All are GET.
    All are relative to :data:`LIVE_BASE_URL`.
    """

    # --- discovery -------------------------------------------------------
    MATCHES = "/football/matches"
    MATCH_DETAIL = "/football/matches/{match_id}"
    COVERAGE_LEAGUES = "/coverage/leagues"
    COMPETITION_SEASONS = "/football/competitions/{competition_id}/seasons"

    # --- context ---------------------------------------------------------
    MATCH_REFEREE = "/football/matches/{match_id}/referee"

    # --- odds (prospective capture core) ---------------------------------
    MATCH_ODDS = "/football/matches/{match_id}/odds"
    MATCH_ODDS_LIVE = "/football/matches/{match_id}/odds/live"

    # --- lineups / player state ------------------------------------------
    MATCH_LINEUPS = "/football/matches/{match_id}/lineups"
    MATCH_PLAYER_STATS = "/football/matches/{match_id}/player-stats"
    PLAYER_STATS = "/football/players/{player_id}/stats"
    TEAM_PLAYERS = "/football/teams/{team_id}/players"

    # --- explicit availability (NOT inferred from absence) ---------------
    # Live docs expose these; used only to attach an EXPLICIT reason when the
    # provider states one. Never used to fabricate an injury from a non-start.
    TEAM_INJURIES = "/football/teams/{team_id}/injuries-suspensions"
    PLAYER_INJURIES = "/football/players/{player_id}/injuries-suspensions"


#: Bookmaker slugs the live ``/odds`` endpoint accepts (verified enum).
BOOKMAKER_SLUGS: Final = (
    "bet365",
    "paddy-power",
    "betmgm-uk",
    "pinnacle",
    "betfair-exchange",
)

#: Canonical over/under market keys used on ``MatchOddsMarkets`` (verified).
#: These are the keys that carry a ``Map<line, OverUnderOdds>`` shape.
OVER_UNDER_MARKET_KEYS: Final = (
    "total_goals",
    "match_corners",
    "total_cards",
    "match_shots",
    "match_shots_on_target",
    "first_half_total_goals",
)

#: Two-way (yes/no) market keys (verified).
YES_NO_MARKET_KEYS: Final = ("btts", "btts_first_half", "btts_second_half")

#: Three-way market keys (verified).
THREE_WAY_MARKET_KEYS: Final = ("match_odds", "first_half_result", "second_half_result")


# ---------------------------------------------------------------------------
# Field-level semantics we DEPEND ON (verified quotes paraphrased from docs)
# ---------------------------------------------------------------------------

#: OddsValue.opening — "Decimal odds when the bookmaker first listed the
#: selection (first pre-match sighting). null when no opening price recorded."
#: => usable AS AN OPENING PRICE ONLY. Not a snapshot at a chosen time.
ODDS_OPENING_FIELD: Final = "opening"

#: OddsValue.last_seen — most recent sighting; the docs carry NO timestamp on
#: it. It is therefore NOT a genuine closing line and MUST NOT be treated as
#: one. See src/research/prospective/odds_capture.py OddsSemantics.
ODDS_LAST_SEEN_FIELD: Final = "last_seen"

#: Lineups endpoint semantics (verified): for UPCOMING matches the confirmed
#: XI is exposed "once the official team sheet has been announced (~1h before
#: kickoff); speculative pre-announcement predictions are NOT exposed"; 404
#: until announced. For finished matches it returns the actual XI sourced from
#: the post-match record. CRITICAL: the response carries NO capture timestamp,
#: so a *historical* lineup cannot prove it was available before any given
#: forecast cutoff. Historical PIT lineup use is UNSUPPORTED without our own
#: timestamped prospective capture.
LINEUP_HAS_CAPTURE_TIMESTAMP: Final = False

#: MatchStatItem / MatchStats semantics (verified): missing period rows are
#: returned as ``null`` "so clients never see a fabricated 0". Reinforces
#: NULL != ZERO.
STATS_NULL_IS_MISSING_NOT_ZERO: Final = True


# ---------------------------------------------------------------------------
# Discrepancies vs the repository's legacy client
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Discrepancy:
    """A single documented gap between the legacy client and the live docs."""

    topic: str
    live_docs: str
    repo_impl: str
    resolution: str


#: Discrepancies discovered by cross-checking ``llms.txt`` against
#: ``src/research/thestatsapi/client.py``. The legacy client is preserved for
#: backward compatibility (its cached-data flows still work); the prospective
#: plane uses the corrected, live-accurate settings in this module.
KNOWN_DISCREPANCIES: Final = (
    Discrepancy(
        topic="base_url",
        live_docs="https://api.thestatsapi.com/api",
        repo_impl='client._DEFAULT_BASE_URL = "https://api.thestatsapi.com" (no /api)',
        resolution=(
            "Prospective plane uses LIVE_BASE_URL (with /api). Legacy client "
            "untouched to preserve backward compat with existing cache keys."
        ),
    ),
    Discrepancy(
        topic="authentication",
        live_docs="Authorization: Bearer <key> header",
        repo_impl="api_key sent as a query parameter",
        resolution=(
            "Prospective read-only client sends the Bearer header. Legacy "
            "query-param client is left as-is; both are key-redacting."
        ),
    ),
    Discrepancy(
        topic="rate_limit_headers",
        live_docs=(
            "X-RateLimit-{Limit,Remaining,Reset} (per-minute) and "
            "X-Monthly-Quota-{Limit,Remaining,Reset} (monthly); 429 with "
            "Retry-After and code RATE_LIMITED / USAGE_LIMIT_EXCEEDED"
        ),
        repo_impl="Only Retry-After is parsed on 429.",
        resolution=(
            "Collector surfaces both budgets for scheduler back-off; still "
            "honours Retry-After. Documented; not a blocker for capture."
        ),
    ),
    Discrepancy(
        topic="endpoint_naming",
        live_docs="/football/matches, /football/matches/{id}/odds, .../lineups, ...",
        repo_impl=(
            "Legacy fixture/odds providers use their own endpoint strings "
            "(e.g. /fixtures) that predate this verification."
        ),
        resolution=(
            "Prospective plane references ONLY the verified Endpoint enum. "
            "Any legacy path that differs is out of scope for this PR and is "
            "left untouched; new capture never calls unverified endpoints."
        ),
    ),
    Discrepancy(
        topic="injury_endpoints_exist",
        live_docs=(
            "/football/teams/{id}/injuries-suspensions and "
            "/football/players/{id}/injuries-suspensions exist with explicit "
            "reason/status/active fields."
        ),
        repo_impl="Not previously wired.",
        resolution=(
            "availability_reason may be set from these EXPLICIT records only. "
            "Absence from an XI is still never interpreted as an injury."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Read-only client config (fails closed, never exposes the key)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProspectiveClientConfig:
    """Configuration for the read-only prospective request helper.

    The key is read from the environment and never stored in a form that is
    logged, hashed, or serialized. :meth:`is_configured` lets callers fail
    closed before attempting any network request.
    """

    base_url: str = field(default=LIVE_BASE_URL)
    timeout_seconds: float = 30.0
    max_retries: int = 3
    rate_limit_seconds: float = 1.0

    @property
    def is_configured(self) -> bool:
        """Whether a non-empty API key is available for live requests."""
        return api_key_available()

    def resolve_base_url(self) -> str:
        """Base URL, honouring the optional override env var."""
        return os.environ.get(ENV_BASE_URL, self.base_url).rstrip("/")


def endpoint_path(endpoint: Endpoint, **params: str) -> str:
    """Render an :class:`Endpoint` template with path params.

    Args:
        endpoint: The verified endpoint.
        **params: Path params (e.g. ``match_id="mt_123"``).

    Returns:
        The path (relative to the base url), e.g. ``/football/matches/mt_123/odds``.

    Raises:
        KeyError: If a required placeholder is missing (fails visibly rather
            than emitting a malformed path).
    """
    return endpoint.value.format(**params)
