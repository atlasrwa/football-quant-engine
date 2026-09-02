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
# Directional-call gate (data-driven, evidence-based)
# ─────────────────────────────────────────────────────────────────────────────
#
# The directional call ("home takes more corners than away") is a SEPARATE claim
# from the calibrated probability. It was tested as its own prediction: does the
# model call which side produces more BETTER than the trivial "always pick the
# side with the historical edge" (home-advantage) baseline? The answer is mostly
# NO. Directional accuracy across 12 market x league cells (out-of-sample
# walk-forward, within-league significance, BH-corrected FDR family of 12,
# pre-registered bootstrap seed) beat that baseline in exactly ONE cell.
#
# So directional output is GATED, not general. A call is emitted only where the
# EVIDENCE clears BOTH of two independent gates:
#
#   * ACCURACY gate — the directional accuracy beat the home-advantage baseline
#     with BH-corrected within-league significance. A call that does not beat
#     "always pick home" is not information, so failing this gate SUPPRESSES the
#     call entirely (it is never shown with a caveat — a caveat invites misuse).
#
#   * CALIBRATION gate — the directional PROBABILITY is acceptably calibrated
#     (ECE below :data:`DIRECTIONAL_MAX_ECE`). Accuracy and calibration can fail
#     independently: a cell may call the right side often enough yet attach
#     meaningless confidence numbers. When calibration fails but accuracy passes,
#     the direction may be STATED but the probability figure must be withheld.
#
# Adding a cell later MUST mean adding an evidence row here (updated numbers from
# a re-run), not editing a hardcoded exception elsewhere.

#: ECE ceiling for a directional probability to be considered trustworthy.
DIRECTIONAL_MAX_ECE = 0.10


@dataclass(frozen=True)
class DirectionalEvidence:
    """Recorded out-of-sample evidence for one market/league directional cell.

    Attributes:
        market / league_label: the cell.
        n_decisive: decisive (non-tie) out-of-sample matches scored.
        model_accuracy: directional accuracy (ties excluded).
        home_baseline: the home-advantage baseline accuracy (the bar).
        diff_ci_low / diff_ci_high: 95% bootstrap CI on (model - baseline).
        ece: calibration error of the directional probability.
        beats_home_bh: True iff the accuracy gate passed — beat the baseline
            with BH-corrected within-league significance.
        seed / family_size: provenance of the significance test.
    """

    market: str
    league_label: str
    n_decisive: int
    model_accuracy: float
    home_baseline: float
    diff_ci_low: float
    diff_ci_high: float
    ece: float
    beats_home_bh: bool
    seed: int
    family_size: int

    @property
    def accuracy_gate_passed(self) -> bool:
        """Directional accuracy beat the home-advantage baseline (BH-corrected)."""
        return self.beats_home_bh

    @property
    def calibration_gate_passed(self) -> bool:
        """Directional probability is acceptably calibrated (ECE within ceiling)."""
        return self.ece <= DIRECTIONAL_MAX_ECE


#: The evidence table. Keyed by ``(market, canonical-league)``. This is the
#: SINGLE SOURCE OF TRUTH for directional gating: only cells present here with
#: ``beats_home_bh=True`` may emit a directional call. Figures are the
#: out-of-sample directional-accuracy test (pre-registered seed 20260902, fresh
#: BH family of 12). Absent cells default to "no evidence" -> suppressed.
#:
#: Result summary: corners does NOT beat always-pick-home in any league; cards is
#: WORSE than the baseline in every league; goals/Championship and sot/Championship
#: beat the bar within-league but FAIL BH; sot/Ligue 2 is the sole cell clearing
#: both gates.
_DIRECTIONAL_EVIDENCE: tuple[DirectionalEvidence, ...] = (
    # market,       league,          n,   acc,   home,  ci_lo,  ci_hi,  ece,   bh,    seed,     fam
    DirectionalEvidence("corners", "Championship", 733, 0.647, 0.625, -0.003, 0.045, 0.053, False, 20260902, 12),
    DirectionalEvidence("corners", "La Liga 2",    608, 0.638, 0.628, -0.015, 0.035, 0.072, False, 20260902, 12),
    DirectionalEvidence("corners", "Ligue 2",      410, 0.617, 0.610, -0.024, 0.037, 0.061, False, 20260902, 12),
    DirectionalEvidence("cards",   "Championship", 607, 0.567, 0.644, -0.125, -0.028, 0.167, False, 20260902, 12),
    DirectionalEvidence("cards",   "La Liga 2",    555, 0.512, 0.541, -0.083, 0.023, 0.096, False, 20260902, 12),
    DirectionalEvidence("cards",   "Ligue 2",      350, 0.491, 0.534, -0.106, 0.026, 0.080, False, 20260902, 12),
    DirectionalEvidence("goals",   "Championship", 603, 0.617, 0.580, 0.005, 0.068, 0.127, False, 20260902, 12),
    DirectionalEvidence("goals",   "La Liga 2",    513, 0.628, 0.616, -0.025, 0.051, 0.169, False, 20260902, 12),
    DirectionalEvidence("goals",   "Ligue 2",      335, 0.588, 0.564, -0.024, 0.072, 0.131, False, 20260902, 12),
    DirectionalEvidence("sot",     "Championship", 724, 0.620, 0.586, 0.004, 0.066, 0.050, False, 20260902, 12),
    DirectionalEvidence("sot",     "La Liga 2",    588, 0.672, 0.667, -0.031, 0.043, 0.113, False, 20260902, 12),
    # The single directional finding: beats the home-advantage bar (+6.1pts,
    # CI [+2.3,+9.9]), BH-passed, well-calibrated (ECE 0.064), stable across 6/6
    # bootstrap seeds.
    DirectionalEvidence("sot",     "Ligue 2",      394, 0.640, 0.579, 0.023, 0.099, 0.064, True,  20260902, 12),
)

_DIRECTIONAL_EVIDENCE_INDEX: dict[tuple[str, str], DirectionalEvidence] = {}


def _canonical_league(league_label: Optional[str]) -> Optional[str]:
    """Map a heterogeneous league label to the canonical evidence-table key."""
    if not league_label:
        return None
    if is_championship(league_label):
        return "Championship"
    low = str(league_label).strip().lower()
    if "la liga 2" in low or "laliga2" in low or "segunda" in low:
        return "La Liga 2"
    if "ligue 2" in low or "ligue2" in low:
        return "Ligue 2"
    return str(league_label).strip()


for _ev in _DIRECTIONAL_EVIDENCE:
    _DIRECTIONAL_EVIDENCE_INDEX[(_ev.market, _ev.league_label)] = _ev


@dataclass(frozen=True)
class DirectionalStatus:
    """The resolved directional-output status for one market in one league.

    Attributes:
        market / league_label: the cell.
        evidence: the recorded :class:`DirectionalEvidence`, or None if untested.
        emit_call: True iff a directional CALL may be shown (accuracy gate).
        show_probability: True iff the directional PROBABILITY may be shown
            (accuracy gate AND calibration gate — a call with meaningless
            confidence shows the direction only).
        reason: plain-language suppression/emission reason for the artifact.
    """

    market: str
    league_label: Optional[str]
    evidence: Optional[DirectionalEvidence]
    emit_call: bool
    show_probability: bool
    reason: str


def directional_status(market: str, league_label: Optional[str] = None) -> DirectionalStatus:
    """Resolve whether a directional call may be emitted for ``market`` in ``league``.

    Data-driven: consults :data:`_DIRECTIONAL_EVIDENCE`. A call is emitted only
    when the ACCURACY gate passed (beat the home-advantage baseline with
    BH-corrected within-league significance). The probability figure is shown
    only when the CALIBRATION gate ALSO passed. The two gates are independent.

    Absent evidence (an untested cell) defaults to suppression — the honest
    default is "not shown to beat the baseline".
    """
    key = market.strip().lower()
    canon = _canonical_league(league_label)
    ev = _DIRECTIONAL_EVIDENCE_INDEX.get((key, canon)) if canon else None

    if ev is None:
        return DirectionalStatus(
            market=key, league_label=league_label, evidence=None,
            emit_call=False, show_probability=False,
            reason=(
                "no directional call: not evaluated against the home-advantage "
                "baseline in this market/league"
            ),
        )

    if not ev.accuracy_gate_passed:
        return DirectionalStatus(
            market=key, league_label=league_label, evidence=ev,
            emit_call=False, show_probability=False,
            reason=(
                "no directional call: does not beat the home-advantage baseline "
                f"in this market/league (directional accuracy {ev.model_accuracy:.1%} "
                f"vs baseline {ev.home_baseline:.1%}; 95% CI on the difference "
                f"[{ev.diff_ci_low:+.1%}, {ev.diff_ci_high:+.1%}])"
            ),
        )

    # Accuracy gate passed. Calibration gate decides whether the probability shows.
    if not ev.calibration_gate_passed:
        return DirectionalStatus(
            market=key, league_label=league_label, evidence=ev,
            emit_call=True, show_probability=False,
            reason=(
                "directional call shown WITHOUT a probability: it beats the "
                f"home-advantage baseline (accuracy {ev.model_accuracy:.1%} vs "
                f"{ev.home_baseline:.1%}) but its confidence is not calibrated "
                f"(ECE {ev.ece:.3f} > {DIRECTIONAL_MAX_ECE:.2f})"
            ),
        )

    return DirectionalStatus(
        market=key, league_label=league_label, evidence=ev,
        emit_call=True, show_probability=True,
        reason=(
            "directional call validated: beats the home-advantage baseline "
            f"(accuracy {ev.model_accuracy:.1%} vs {ev.home_baseline:.1%}; 95% CI "
            f"[{ev.diff_ci_low:+.1%}, {ev.diff_ci_high:+.1%}]; ECE {ev.ece:.3f}; "
            f"BH-corrected within-league significance, family size {ev.family_size}, "
            f"seed {ev.seed})"
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Honest framing (Section 7 of the brief)
# ─────────────────────────────────────────────────────────────────────────────

#: The mandatory honest-framing statement attached to every user-facing artifact.
HONEST_FRAMING: tuple[str, ...] = (
    "These are calibrated probability estimates, NOT betting advice.",
    "This model has NOT been shown to beat bookmaker prices. That was tested "
    "extensively and the finding is documented (edge ceiling measured directly; "
    "see the failure ledger).",
    "The primary claim is CALIBRATED PROBABILITIES for corners and cards, scoped "
    "per league (corners validated everywhere; cards validated except in the "
    "Championship). Goals and BTTS show no demonstrated skill over the base rate "
    "and are labelled as such.",
    "Directional calls (which side produces more) are a SEPARATE, mostly "
    "UNVALIDATED claim: tested out-of-sample against an always-pick-the-favoured-"
    "side baseline, they beat it in only one market/league (shots on target in "
    "Ligue 2). They are suppressed everywhere else and are NOT a general "
    "capability of this engine.",
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
