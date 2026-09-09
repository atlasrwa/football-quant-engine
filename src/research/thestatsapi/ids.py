"""TheStatsAPI identifier parsing and formatting.

TheStatsAPI uses string-prefixed identifiers:
    match        -> "mt_010243001"
    team         -> "tm_5290"
    competition  -> "comp_3039"
    season       -> "sn_3057848"

The canonical ``ResearchMatch`` schema stores ``match_id`` and ``league_id`` as
``int``. This module provides *deterministic*, side-effect-free conversion
between the two representations so identity is never lost and never guessed.

Rules:
- Parsing strips the known prefix and returns the integer suffix.
- The ORIGINAL prefixed string is always preserved separately (on provenance
  and on the canonical identity map) so we never conflate a FootyStats integer
  id with a TheStatsAPI integer id: they only ever meet through an explicit
  canonical mapping, never by numeric coincidence.
- Malformed ids raise ``ValueError`` rather than silently coercing to 0, so a
  bad id fails visibly.
"""

from __future__ import annotations

from typing import Final

MATCH_PREFIX: Final = "mt_"
TEAM_PREFIX: Final = "tm_"
COMPETITION_PREFIX: Final = "comp_"
SEASON_PREFIX: Final = "sn_"


class ProviderIdError(ValueError):
    """Raised when a TheStatsAPI id cannot be parsed."""


def _parse_prefixed(value: str, prefix: str) -> int:
    """Parse a ``{prefix}{digits}`` id into its integer suffix.

    Args:
        value: The prefixed id string (e.g. "mt_010243001").
        prefix: Expected prefix (e.g. "mt_").

    Returns:
        Integer value of the digit suffix (leading zeros dropped:
        "mt_010243001" -> 10243001).

    Raises:
        ProviderIdError: If value is not a string, lacks the prefix, or the
            suffix is not purely numeric.
    """
    if not isinstance(value, str):
        raise ProviderIdError(f"Expected str id, got {type(value).__name__}: {value!r}")
    if not value.startswith(prefix):
        raise ProviderIdError(f"Id {value!r} does not start with expected prefix {prefix!r}")
    suffix = value[len(prefix):]
    if not suffix.isdigit():
        raise ProviderIdError(f"Id {value!r} has non-numeric suffix {suffix!r}")
    return int(suffix)


def parse_match_id(value: str) -> int:
    """Parse "mt_XXXX" -> int."""
    return _parse_prefixed(value, MATCH_PREFIX)


def parse_team_id(value: str) -> int:
    """Parse "tm_XXXX" -> int."""
    return _parse_prefixed(value, TEAM_PREFIX)


def parse_competition_id(value: str) -> int:
    """Parse "comp_XXXX" -> int."""
    return _parse_prefixed(value, COMPETITION_PREFIX)


def parse_season_id(value: str) -> int:
    """Parse "sn_XXXX" -> int."""
    return _parse_prefixed(value, SEASON_PREFIX)


def format_match_id(value: int) -> str:
    """Format int -> "mt_XXXX" (no zero-padding; provider tolerates both)."""
    return f"{MATCH_PREFIX}{int(value)}"


def format_team_id(value: int) -> str:
    return f"{TEAM_PREFIX}{int(value)}"


def format_competition_id(value: int) -> str:
    return f"{COMPETITION_PREFIX}{int(value)}"


def format_season_id(value: int) -> str:
    return f"{SEASON_PREFIX}{int(value)}"


def is_prefixed_id(value: object) -> bool:
    """Whether ``value`` looks like any known TheStatsAPI prefixed id."""
    if not isinstance(value, str):
        return False
    return any(
        value.startswith(p)
        for p in (MATCH_PREFIX, TEAM_PREFIX, COMPETITION_PREFIX, SEASON_PREFIX)
    )
