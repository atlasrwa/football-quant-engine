"""Validated market/league scope — where the engine works, and where it does not.

The scoping is a *feature*. A calibrated prediction engine that states, per
market and per league, whether it has demonstrated skill over the naive base
rate is more trustworthy than one that implies universal coverage. This module
is the single source of truth for that status so no artifact can quietly present
an unvalidated market as if it were validated.

Market status (corners & cards under re-validation — see audit note below)
==========================================================================

* **Corners** — status PROVISIONAL (under re-validation). Corners was previously
  presented as validated skill, but an internal audit found the original figures
  were inflated by SAME-MATCH FEATURE LEAKAGE and the specific BSS/ECE numbers have
  been withdrawn (see the audit note below). No demonstrated-skill claim is made
  until a leak-free rebuild completes.
* **Cards** — status PROVISIONAL (under re-validation), for the same reason —
  **except the Championship**, where disciplinary persistence is confirmed ABSENT
  across three seasons (yellow-rate -> cards association -0.044 / +0.033 / +0.012,
  all p >= 0.37); cards there is EXCLUDED regardless.
* **Goals, BTTS** — roughly at par with the naive base rate. No demonstrated skill
  over base rate. Shown only with an explicit label; never as a prediction worth
  acting on. (Corroborated externally by a plain point-in-time Dixon-Coles, which
  is ~at par with naive on goals O/U 2.5.)

Leakage audit — why corners/cards are PROVISIONAL
=================================================
An internal forensic audit found that ``CountRegressionModel``'s DEFAULT feature
construction fed the PREDICTED match's own FINAL statistics into the model — shots,
attacks, dangerous attacks, possession (corners) and fouls (cards). The walk-forward
split did not catch it because the leak is WITHIN-ROW (feature and label from the
same match), not across-time. Zeroing the same-match features dropped corners BSS
from +8.11% -> +1.03% and cards from +6.06% -> +1.32% — i.e. roughly 85% / 78% of
the previously reported skill was leakage. The prior "validated" figures (corners
+9.6%/+6.8% BSS, cards +9.0%/+6.1%, ECE 0.018/0.027) are therefore WITHDRAWN as
inflated. The harness, corpus, metrics, and the ``_predict_lambda`` shrinkage logic
were all found sound; the negative rich-field results (EPL/La Liga/Ligue 1) were the
HONEST ones. Re-validation on strictly-prior (leak-free) features is in progress; the
counterfactual ~+1% zeroing numbers are NOT adopted as the new claim (they came from
a zeroing exercise, not a proper prior-only rebuild).

Provenance note: the earlier "25 leagues x 3 seasons (~23,000 matches)" description
conflated two data sources. The PERSISTED FootyStats corpus
(``data/discovery/corpus/manifest.json``) is 25 leagues x 2 seasons / 15,362
completed matches. The 3-season / ~23k figure traces ONLY to a live-API run captured
in ``robustness_results.json`` (``run_robustness_check.py``), not to the persisted
corpus. The two must not be conflated.

This module records market STATUS so downstream code can label every number; it does
not itself compute skill figures.

League-family transfer test (seed 20260902)
============================================
Three NEW top flights (EPL, La Liga, Ligue 1) were tested against their already-held
second-tier partners using a stricter WITHIN-LEAGUE, 2-season walk-forward (BSS vs
naive, bootstrap CIs, BH family of 6), fitting the SAME architecture with no refit.
None of the six top-flight (market x league) cells demonstrated within-league skill
(every BSS 95% CI spans 0; none passed BH). Per the standing rule, those leagues are
recorded UNVALIDATED here (see ``_FAMILY_TRANSFER_WITHIN_LEAGUE``). The built-in
cards-persistence check did NOT support a general tier law: cards persistence was
stronger in the EPL than the Championship, but stronger in La Liga 2 and Ligue 2 than
in their top flights — the tier direction flips by country. (Note: this transfer test
used the honest prior-only rolling-feature path, not the leaked default features.)
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
    * ``PROVISIONAL`` — previously presented as validated, but that claim has been
      withdrawn pending re-validation. Used for corners and cards after an internal
      audit found the original skill figures were inflated by same-match feature
      leakage (the model read the predicted match's own final statistics). The
      probability may be shown but MUST carry the "under re-validation" label and
      MUST NOT be presented as demonstrated skill until a leak-free rebuild lands.
    * ``NO_DEMONSTRATED_SKILL`` — at par with the naive base rate. The number may
      be shown, but it MUST carry the explicit "no demonstrated skill over base
      rate" label. A confident-looking probability from a model with no edge over
      the base rate is exactly the thing that misleads people.
    * ``EXCLUDED`` — not validated in this specific league (e.g. cards in the
      Championship). Do not present as a prediction; state why it is excluded.
    """

    VALIDATED = "validated"
    PROVISIONAL = "provisional"
    NO_DEMONSTRATED_SKILL = "no_demonstrated_skill"
    EXCLUDED = "excluded"


#: Human-readable label shown alongside every non-validated market number.
NO_SKILL_LABEL = "no demonstrated skill over base rate"

#: Label shown next to a market whose prior "validated" claim was withdrawn pending
#: a leak-free re-validation (corners, cards — see the audit note in the module docstring).
UNDER_REVALIDATION_LABEL = "under re-validation (prior skill figure withdrawn)"


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
        if self.status is MarketStatus.PROVISIONAL:
            return UNDER_REVALIDATION_LABEL
        if self.status is MarketStatus.NO_DEMONSTRATED_SKILL:
            return NO_SKILL_LABEL
        return "excluded (not validated in this league)"


# ─────────────────────────────────────────────────────────────────────────────
# League-family transfer test result (data-driven per-league validation status)
# ─────────────────────────────────────────────────────────────────────────────
#
# The prior blanket "corners validated / cards validated except Championship" rule
# came from the ORIGINAL 25-league x 3-season CROSS-SECTIONAL validation (pooled
# skill) — now WITHDRAWN as leakage-inflated; corners & cards are PROVISIONAL pending
# a leak-free rebuild. The league-family transfer test (seed 20260902) separately
# re-tested three NEW top flights with a stricter WITHIN-LEAGUE, 2-season walk-forward,
# BSS-vs-naive
# with bootstrap CIs, BH family of 6. Per the standing rule "a new league is
# UNVALIDATED until it passes validation in THAT league", we record the per-(market,
# canonical-league) within-league outcome here and let market_status consult it, so
# these specific leagues are not silently granted the pooled label they did not earn
# under the stricter test.
#
# Outcome (BSS-vs-naive 95% CI must exclude 0 to count as within-league skill):
#   EPL     corners -0.87% CI[-2.46,+0.67] ; cards +0.16% CI[-2.84,+3.01]  -> neither
#   La Liga corners +1.81% CI[-0.19,+3.85] ; cards -0.60% CI[-3.19,+2.11]  -> neither
#   Ligue 1 corners -0.74% CI[-2.58,+1.13] ; cards +2.08% CI[-2.52,+6.74]  -> neither
# None of the 6 primary cells passed BH (best uncorrected p = La Liga corners 0.079).
# So all six new-league (market, league) cells are WITHIN-LEAGUE UNVALIDATED.
#
# (The already-held second tiers are unchanged: La Liga 2 cards re-passed within-league
#  here, BSS +2.90% CI[+0.26,+5.83]; Championship cards remains excluded.)
#
# True == the cell demonstrated within-league calibrated skill (CI excludes 0 AND BH).
_FAMILY_TRANSFER_WITHIN_LEAGUE: dict[tuple[str, str], bool] = {
    ("corners", "EPL"): False,     ("cards", "EPL"): False,
    ("corners", "La Liga"): False, ("cards", "La Liga"): False,
    ("corners", "Ligue 1"): False, ("cards", "Ligue 1"): False,
}


def _family_transfer_status(market_key: str, canon_league: Optional[str]):
    """If this (market, league) was tested by the family-transfer test, return its
    MarketScope; else None (fall through to the default cross-sectional rule)."""
    if canon_league is None:
        return None
    passed = _FAMILY_TRANSFER_WITHIN_LEAGUE.get((market_key, canon_league))
    if passed is None:
        return None
    if passed:
        return None  # let the default VALIDATED rule stand (it earned it here)
    return MarketScope(
        market=market_key, league_label=canon_league,
        status=MarketStatus.NO_DEMONSTRATED_SKILL,
        reason=(
            f"{market_key.upper()} is UNVALIDATED in {canon_league}: the league-family "
            "transfer test (within-league, 2-season walk-forward, BSS-vs-naive with "
            "bootstrap CIs, seed 20260902, BH family of 6) did NOT demonstrate skill "
            "over the naive base rate here (95% CI on BSS spans 0; no cell passed BH). "
            "This is 'not demonstrated within-league', not 'confirmed absent' — the "
            "number may be shown with the no-skill label, never as a validated "
            "prediction. A new league is unvalidated until it passes validation there."
        ),
    )


def market_status(market: str, league_label: Optional[str] = None) -> MarketScope:
    """Resolve the validated status of ``market`` in ``league_label``.

    Rules (the single source of truth for scope labelling):

    * ``corners`` -> PROVISIONAL (under re-validation) everywhere EXCEPT the
      family-transfer leagues, which were tested leak-free and are recorded per
      their within-league result.
    * ``cards``   -> PROVISIONAL (under re-validation) everywhere EXCEPT the
      Championship (EXCLUDED — persistence absent) and the family-transfer leagues
      (per their within-league result).
    * ``goals``   -> NO_DEMONSTRATED_SKILL everywhere (at par with base rate).
    * ``btts``    -> NO_DEMONSTRATED_SKILL everywhere (at par with base rate).

    Args:
        market: one of :data:`ALL_MARKETS` (case-insensitive).
        league_label: any league identifier. The Championship (cards) and the
            three family-transfer top flights (corners+cards) are treated
            specially and data-drivenly. ``None`` means "unspecified league".

    Returns:
        A :class:`MarketScope`.

    Raises:
        ValueError: if ``market`` is not a known market.
    """
    key = market.strip().lower()
    if key not in ALL_MARKETS:
        raise ValueError(f"unknown market {market!r}; expected one of {ALL_MARKETS}")

    # Data-driven family-transfer override (new top flights not confirmed here).
    ft = _family_transfer_status(key, _canonical_league(league_label))
    if ft is not None:
        return ft

    if key == MARKET_CORNERS:
        return MarketScope(
            market=key,
            league_label=league_label,
            status=MarketStatus.PROVISIONAL,
            reason=(
                "Corners is UNDER RE-VALIDATION. Its prior 'validated skill' figures "
                "were withdrawn after an internal audit found the original result was "
                "inflated by same-match feature leakage (the model read the predicted "
                "match's own final shot/attack/possession counts). A leak-free, "
                "strictly-prior rebuild is in progress; no demonstrated-skill claim is "
                "made until it completes. The probability may be shown only with the "
                "under-re-validation label, never as validated skill."
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
            status=MarketStatus.PROVISIONAL,
            reason=(
                "Cards is UNDER RE-VALIDATION. Its prior 'validated skill' figures "
                "were withdrawn after an internal audit found the original result was "
                "inflated by same-match feature leakage (the model read the predicted "
                "match's own final foul/attack/possession counts). A leak-free, "
                "strictly-prior rebuild is in progress; no demonstrated-skill claim is "
                "made until it completes. The probability may be shown only with the "
                "under-re-validation label, never as validated skill."
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
#: ``beats_home_bh=True`` may emit a directional call. Absent cells default to
#: "no evidence" -> suppressed.
#:
#: Two provenance groups share this table:
#:  * Original directional run (pre-registered seed 20260902, BH family of 12) over
#:    the three second-tier rich leagues x {corners, cards, goals, sot}. Result:
#:    corners does NOT beat always-pick-home in any league; cards is WORSE than the
#:    baseline; goals/Championship and sot/Championship beat the bar within-league
#:    but FAIL BH; sot/Ligue 2 is the sole cell clearing both gates.
#:  * League-family transfer test (seed 20260902, directional BH family of 6) over
#:    the three NEW top flights x {corners, cards}. Result: NO cell emits a call —
#:    corners beats nothing; the cards "beats" (EPL, La Liga) clear BH only against a
#:    degenerate sub-0.5 home bar (away takes more cards) and are suppressed. See the
#:    block comment on those rows.
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

    # ── League-family transfer test (EPL / La Liga / Ligue 1 top flights) ──────
    # Added by the family-transfer test (seed 20260902). These use the LITERAL
    # always-pick-home baseline the test brief specified ("home" is the call, the
    # bar is the fraction of decisive matches where home actually produced more),
    # so `home` here is that home-advantage rate — reported so the bar cannot be
    # glossed. Directional BH family for this test = {corners, cards} x 3 = 6.
    #
    # corners: no top flight beats always-pick-home (diffs ~0, CIs span 0).
    # cards: EPL (+0.107, CI[+0.042,+0.173]) and La Liga (+0.093, CI[+0.029,+0.156])
    #   are BH-significant vs always-pick-home — BUT the home bar for cards is only
    #   ~0.40 because AWAY teams systematically take more cards, so "beats
    #   always-pick-home" here is a degenerate result (always-pick-AWAY would score
    #   ~0.60). It is NOT a genuine directional edge, and the calibration gate also
    #   fails for EPL cards (ECE 0.113 > 0.10). We therefore record beats_home_bh=
    #   False for every new-league cell: no directional call is emitted for any of
    #   them. The raw diffs/CIs are preserved in this comment so nothing is hidden.
    #   (EPL cards diff +0.107 CI[+0.042,+0.173] p=0.0018 ece 0.113;
    #    La Liga cards diff +0.093 CI[+0.029,+0.156] p=0.0054 ece 0.081 — both beat a
    #    sub-0.5 home bar only; Ligue 1 cards diff +0.053 CI[-0.027,+0.133] p=0.19.)
    DirectionalEvidence("corners", "EPL",       628, 0.572, 0.575, -0.059, 0.052, 0.083, False, 20260902, 6),
    DirectionalEvidence("corners", "La Liga",   589, 0.603, 0.606, -0.059, 0.053, 0.121, False, 20260902, 6),
    DirectionalEvidence("corners", "Ligue 1",   484, 0.568, 0.614, -0.110, 0.017, 0.117, False, 20260902, 6),
    DirectionalEvidence("cards",   "EPL",       336, 0.506, 0.399, 0.042, 0.173, 0.113, False, 20260902, 6),
    DirectionalEvidence("cards",   "La Liga",   410, 0.541, 0.449, 0.029, 0.156, 0.081, False, 20260902, 6),
    DirectionalEvidence("cards",   "Ligue 1",   300, 0.487, 0.433, -0.027, 0.133, 0.095, False, 20260902, 6),
)

_DIRECTIONAL_EVIDENCE_INDEX: dict[tuple[str, str], DirectionalEvidence] = {}


def _canonical_league(league_label: Optional[str]) -> Optional[str]:
    """Map a heterogeneous league label to the canonical evidence-table key."""
    if not league_label:
        return None
    if is_championship(league_label):
        return "Championship"
    low = str(league_label).strip().lower()
    # Second tiers first (so "la liga 2" is not swallowed by the "la liga" test).
    if "la liga 2" in low or "laliga2" in low or "segunda" in low:
        return "La Liga 2"
    if "ligue 2" in low or "ligue2" in low:
        return "Ligue 2"
    # Top flights added by the league-family transfer test. Tag/id/free-text.
    if low in {"epl", "comp_3039"} or "premier league" in low or low == "epl":
        return "EPL"
    if low in {"laliga", "la liga", "comp_8814"} or "la liga" in low or "laliga" in low:
        return "La Liga"
    if low in {"ligue1", "ligue 1", "comp_0256"} or "ligue 1" in low or "ligue1" in low:
        return "Ligue 1"
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
    "The corners and cards markets are currently UNDER RE-VALIDATION: their prior "
    "'validated skill' figures were withdrawn after an internal audit found the "
    "original result was inflated by same-match feature leakage. No demonstrated-"
    "skill claim is made for corners or cards until a leak-free rebuild completes; "
    "any probability shown for them carries the 'under re-validation' label. Cards "
    "in the Championship remains excluded. Goals and BTTS show no demonstrated skill "
    "over the base rate and are labelled as such.",
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
