"""Validated market/league scope — where the engine works, and where it does not.

The scoping is a *feature*. A calibrated prediction engine that states, per
market and per league, whether it has demonstrated skill over the naive base
rate is more trustworthy than one that implies universal coverage. This module
is the single source of truth for that status so no artifact can quietly present
an unvalidated market as if it were validated.

Validated status (from the project's cross-league validation)
=============================================================
Across 25 leagues x 3 seasons (~23,000 matches):

* **Corners** — validated skill. +6.8% mean BSS over naive, 91% of
  league-seasons positive (original validation +9.6% BSS, ECE 0.018).
* **Cards** — validated skill. +6.1% mean BSS over naive, 96% of league-seasons
  positive (original validation +9.0% BSS, ECE 0.027) — **except the
  Championship**, where disciplinary persistence is confirmed ABSENT across
  three seasons (yellow-rate -> cards association -0.044 / +0.033 / +0.012, all
  p >= 0.37). In the Championship, cards is NOT validated.
* **Goals, BTTS** — roughly at par with the naive base rate. No demonstrated
  skill over base rate. Shown only with an explicit label; never as a prediction
  worth acting on.

This module intentionally does NOT compute these figures — they are established
findings. It records the *status* so downstream code can label every number.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Markets and status
# ─────────────────────────────────────────────────────────────────────────────

#: Canonical market keys the engine can produce.
MARKET_CORNERS = "corners"
MARKET_CARDS = "cards"
MARKET_GOALS = "goals"
MARKET_BTTS = "btts"

ALL_MARKETS: tuple[str, ...] = (MARKET_CORNERS, MARKET_CARDS, MARKET_GOALS, MARKET_BTTS)


class MarketStatus(Enum):
    """Validated status of a market in a given league.

    * ``VALIDATED`` — demonstrated calibrated skill over the naive base rate in
      this league (safe to present as a prediction, still with its sample size).
    * ``NO_DEMONSTRATED_SKILL`` — at par with the naive base rate. The number may
      be shown, but it MUST carry the explicit "no demonstrated skill over base
      rate" label. A confident-looking probability from a model with no edge over
      the base rate is exactly the thing that misleads people.
    * ``EXCLUDED`` — not validated in this specific league (e.g. cards in the
      Championship). Do not present as a prediction; state why it is excluded.
    """

    VALIDATED = "validated"
    NO_DEMONSTRATED_SKILL = "no_demonstrated_skill"
    EXCLUDED = "excluded"


#: Human-readable label shown alongside every non-validated market number.
NO_SKILL_LABEL = "no demonstrated skill over base rate"


# ─────────────────────────────────────────────────────────────────────────────
# League identity
# ─────────────────────────────────────────────────────────────────────────────
#
# Leagues arrive with heterogeneous identifiers across the codebase (FootyStats
# comp ids like "comp_8321", TheStatsAPI tags like "champ", free-text labels like
# "England Championship"). The ONLY league-specific carve-out in the validated
# scope is the Championship cards exclusion, so we normalise just enough to
# recognise the Championship robustly and treat everything else by market status.

#: Tokens (lower-cased, substring match) that identify the England Championship.
_CHAMPIONSHIP_TOKENS: tuple[str, ...] = (
    "championship",
    "comp_8321",
    "champ",  # TheStatsAPI rich-corpus tag
)


def is_championship(league_label: Optional[str]) -> bool:
    """True iff ``league_label`` denotes the England Championship.

    Recognises FootyStats comp id (``comp_8321``), the rich-corpus tag
    (``champ``), and free-text labels (``England Championship``). Matching is
    case-insensitive and token-based. Unknown/None labels are not the
    Championship.
    """
    if not league_label:
        return False
    lower = str(league_label).strip().lower()
    # Guard the short "champ" token against false positives like "champions
    # league" by requiring it to be a standalone-ish token.
    if lower in {"champ", "championship", "england championship", "comp_8321"}:
        return True
    if "championship" in lower or "comp_8321" in lower:
        return True
    # "champ_" style tags from the rich corpus.
    if lower == "champ" or lower.startswith("champ_") or lower.startswith("champ "):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# The validated-scope resolver
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MarketScope:
    """The validated status of one market in one league, with a stated reason."""

    market: str
    league_label: Optional[str]
    status: MarketStatus
    reason: str

    @property
    def is_validated(self) -> bool:
        return self.status is MarketStatus.VALIDATED

    @property
    def label(self) -> str:
        """Short label to render next to a number for this market."""
        if self.status is MarketStatus.VALIDATED:
            return "validated skill"
        if self.status is MarketStatus.NO_DEMONSTRATED_SKILL:
            return NO_SKILL_LABEL
        return "excluded (not validated in this league)"


def market_status(market: str, league_label: Optional[str] = None) -> MarketScope:
    """Resolve the validated status of ``market`` in ``league_label``.

    Rules (the single source of truth for scope labelling):

    * ``corners`` -> VALIDATED everywhere.
    * ``cards``   -> VALIDATED everywhere EXCEPT the Championship, where it is
      EXCLUDED (disciplinary persistence confirmed absent across three seasons).
    * ``goals``   -> NO_DEMONSTRATED_SKILL everywhere (at par with base rate).
    * ``btts``    -> NO_DEMONSTRATED_SKILL everywhere (at par with base rate).

    Args:
        market: one of :data:`ALL_MARKETS` (case-insensitive).
        league_label: any league identifier; only the Championship is treated
            specially. ``None`` means "unspecified league" and applies the
            market's general status (cards resolves to VALIDATED since the
            exclusion is Championship-specific).

    Returns:
        A :class:`MarketScope`.

    Raises:
        ValueError: if ``market`` is not a known market.
    """
    key = market.strip().lower()
    if key not in ALL_MARKETS:
        raise ValueError(f"unknown market {market!r}; expected one of {ALL_MARKETS}")

    if key == MARKET_CORNERS:
        return MarketScope(
            market=key,
            league_label=league_label,
            status=MarketStatus.VALIDATED,
            reason=(
                "Corners is the best-calibrated validated market: +6.8% mean BSS "
                "over naive across 25 leagues x 3 seasons (91% of league-seasons "
                "positive; original validation +9.6% BSS, ECE 0.018)."
            ),
        )

    if key == MARKET_CARDS:
        if is_championship(league_label):
            return MarketScope(
                market=key,
                league_label=league_label,
                status=MarketStatus.EXCLUDED,
                reason=(
                    "Cards is EXCLUDED in the Championship: disciplinary "
                    "persistence is confirmed absent across three seasons "
                    "(yellow-rate -> cards association -0.044 / +0.033 / +0.012, "
                    "all p >= 0.37). No calibrated cards prediction is offered "
                    "here."
                ),
            )
        return MarketScope(
            market=key,
            league_label=league_label,
            status=MarketStatus.VALIDATED,
            reason=(
                "Cards is validated outside the Championship: +6.1% mean BSS over "
                "naive (96% of league-seasons positive; original validation "
                "+9.0% BSS, ECE 0.027)."
            ),
        )

    # goals / btts
    return MarketScope(
        market=key,
        league_label=league_label,
        status=MarketStatus.NO_DEMONSTRATED_SKILL,
        reason=(
            f"{key.upper()} is roughly at par with the naive base rate: no "
            "demonstrated skill over base rate. The probability may be shown but "
            "must be labelled as such and not presented as a prediction worth "
            "acting on."
        ),
    )


@dataclass(frozen=True)
class ValidatedScope:
    """Convenience view over the full market x league scope for a fixture."""

    league_label: Optional[str]

    def statuses(self) -> dict[str, MarketScope]:
        """The status of every market for this league."""
        return {m: market_status(m, self.league_label) for m in ALL_MARKETS}

    def validated_markets(self) -> tuple[str, ...]:
        return tuple(
            m for m, s in self.statuses().items() if s.status is MarketStatus.VALIDATED
        )

    def excluded_markets(self) -> tuple[str, ...]:
        return tuple(
            m for m, s in self.statuses().items() if s.status is MarketStatus.EXCLUDED
        )


# ─────────────────────────────────────────────────────────────────────────────
# Minimum-sample gate
# ─────────────────────────────────────────────────────────────────────────────

#: Below this many SETTLED predictions per market, no calibration figure is
#: published. An ECE on 20 predictions is noise; publishing it would undermine
#: the honesty the whole thing rests on. Displayed instead: "insufficient
#: settled predictions — N of ~200".
MIN_SETTLED_FOR_CALIBRATION = 200


def insufficient_sample_notice(n_settled: int, minimum: int = MIN_SETTLED_FOR_CALIBRATION) -> str:
    """The exact notice shown when below the minimum-sample gate."""
    return f"insufficient settled predictions — {n_settled} of ~{minimum}"


# ─────────────────────────────────────────────────────────────────────────────
# Honest framing (Section 7 of the brief)
# ─────────────────────────────────────────────────────────────────────────────

#: The mandatory honest-framing statement attached to every user-facing artifact.
HONEST_FRAMING: tuple[str, ...] = (
    "These are calibrated probability estimates, NOT betting advice.",
    "This model has NOT been shown to beat bookmaker prices. That was tested "
    "extensively and the finding is documented (edge ceiling measured directly; "
    "see the failure ledger).",
    "Validity is per-league and per-market. Corners is validated; cards is "
    "validated except in the Championship; goals and BTTS show no demonstrated "
    "skill over the base rate and are labelled as such.",
    "No profit claims, no implied profitability, and no staking guidance of any "
    "kind are provided. There is deliberately no stake sizing, Kelly fraction, or "
    "bankroll recommendation anywhere in this engine.",
)


def honest_framing_lines(prefix: str = "") -> list[str]:
    """Render the honest-framing statement as prefixed lines for any artifact.

    Args:
        prefix: optional per-line prefix (e.g. ``"# "`` for a header block).
    """
    return [f"{prefix}{line}" for line in HONEST_FRAMING]
