"""Team_Profiler — continuous, identity-free, point-in-time team profiles.

Responsibility:
    Build for each team exactly one :class:`AttackingProfile` and one
    :class:`DefensiveProfile` as continuous feature vectors, computed
    *point-in-time* from a rolling-10 / expanding-fallback window keyed on team
    identity across both home and away matches and across all leagues. Team
    identity is used only as an aggregation key and never appears as a feature
    value. Profiles are marked ``insufficient`` below the minimum history and
    every dimension records which required raw fields were unavailable.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.16, 1.17, 1.18, 11.1, 11.3, 11.4,
17.1, 17.2, 17.3, and (reduced variant) 4.3, 4.5.

---------------------------------------------------------------------------
Point-in-time discipline (Req 1.4, 11.1, 11.3)
---------------------------------------------------------------------------
This module reuses the exact "compute-before-update" chronological discipline
of :class:`src.features.rolling_form.RollingFormCalculator`: matches are
processed in ascending ``date_unix`` order and, for each match, every team's
profile is read from that team's accumulated history *strictly before* the
current match is folded into history. A per-team ``deque(maxlen=window)``
(``window=10``) provides the rolling window; when fewer than ``window``
completed matches are available the deque simply holds all of them, which *is*
the expanding-window fallback (Req 1.4). Because a profile for match M is a pure
function of the history recorded before M, it is invariant to whether later
matches exist (Property 2 / Req 11.1, 11.3).

---------------------------------------------------------------------------
Identity keying, not fixture slot (Req 1.5, 1.18, 11.4)
---------------------------------------------------------------------------
A team's own matches are aggregated across both its home and its away
appearances, across all leagues. For each historical match we read the team's
"produced" and "conceded" quantities from the *correct side* of that match
depending on whether the team played home or away in it — never from the slot it
occupies in the target fixture. The team string is used purely as a dictionary
key; it never enters a feature vector (Req 1.3).

---------------------------------------------------------------------------
Per-feature missing-field handling (Req 1.17)
---------------------------------------------------------------------------
Each dimension is the *window mean of a per-match derived quantity*, taken over
exactly those matches for which the dimension's required raw fields are present.
If a required field is unavailable (``None`` — NULL != ZERO) for a match, that
match is excluded from *that dimension only* and the field name is recorded in
:attr:`ProfileDimension.missing_fields`. If no match in the window has the
required fields, the dimension is emitted with a NaN-safe default value ``0.0``,
``n_matches_used=0``, and its required fields recorded in ``missing_fields`` —
transparently "not populated" rather than fabricated.

---------------------------------------------------------------------------
Computability from ``ResearchMatch`` (current state — rich fields plumbed)
---------------------------------------------------------------------------
The cached TheStatsAPI rich stats are now surfaced on ``ResearchMatch`` as
optional per-side fields (see ``corpus._adapted_to_research_match``, fed by the
broadened ``championship_adapter._rich_fields`` extraction). Every profile
dimension is therefore derived from its real design fields. Each dimension is
the *window mean of a per-match sum of the present components*; a match
contributes iff at least one required component is present (NULL != ZERO —
a genuine 0 counts as present), and any absent component (plus any design field
with no surfaced backing) is recorded in ``ProfileDimension.missing_fields``.

Per-dimension rich formula (all now populated on the Rich_Corpus):

  Attacking
    width               = accurate_crosses + corners_won + final_third_entries
                          (final_third_entries as the wide/entry proxy;
                          ``wide_entries`` has no TheStatsAPI backing -> recorded
                          as a permanent gap in missing_fields).
    central_penetration = touches_in_penalty_area + final_third_entries
                          + shots_inside_box. touches_in_penalty_area is
                          Championship-thinner, so central_penetration is flagged
                          reduced-confidence there (Req 17.3); the dimension still
                          populates from the other two components.
    volume_vs_quality   = shots_on_target + big_chances + npxg (npxg from
                          np_expected_goals; thin/absent in Ligue 2 / La Liga 2
                          per the audit -> that component is simply excluded when
                          absent, SOT + big_chances still populate the dimension.
                          ``total_shots`` is not individually surfaced ->
                          recorded as a gap).
    set_piece_reliance  = corners_won + fouled_in_final_third (advanced-area
                          fouls-won proxy).
    directness          = accurate_long_balls + dangerous_attacks/attacks ratio.
                          RICH-GAP: ``attacks`` / ``dangerous_attacks`` are NOT in
                          the TheStatsAPI stats (verified absent) and are NOT
                          surfaced on the rich ResearchMatch, so the ratio term is
                          recorded missing on rich matches and the rich directness
                          is anchored on ``accurate_long_balls`` (long balls). The
                          attacks-vs-dangerous ratio IS present in the FootyStats
                          broad corpus, where the reduced directness computes from
                          it (Req 4.3). This is the documented directness decision.
  Defensive
    block_orientation   = clearances + interceptions + tackles.
    aerial_vs_ground    = aerial_duels_percentage - ground_duels_percentage
                          (signed orientation; both percentages required).
    shot_suppression    = blocked_shots - (shots_conceded_inside_box
                          + shots_conceded_outside_box), where the conceded side
                          is the opponent's inside/outside-box shots in that match.
    gk_contribution     = saves + high_claims (Req 17.1: NOT goals_prevented;
                          goals_prevented is always recorded unavailable, and
                          high_claims is thin so recorded when absent).
    discipline          = fouls_conceded + cards + (100 - tackles_won_percentage)
                          (tackle-failure contribution, so higher == more
                          indiscipline; tackle_success recorded missing when the
                          percentage is absent).

---------------------------------------------------------------------------
Reduced-confidence surfacing mechanism (documented choice; Req 17.3)
---------------------------------------------------------------------------
``ProfileDimension`` has no dedicated confidence field. Rather than change the
frozen data model, we surface a reduced-confidence flag by recording a *sentinel
string* in the dimension's ``missing_fields`` of the form
``"reduced_confidence:<field>"`` (e.g.
``"reduced_confidence:touches_in_penalty_area"``). This is transparent, requires
no model change, and is trivially detectable by reporting. The audit case is
``central_penetration`` for the Championship (touches_in_penalty_area ~5% thin),
driven by :func:`profile_dimensions.is_reduced_confidence`.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Callable, Deque, Optional

from src.research.asymmetric import profile_dimensions as pdims
from src.research.asymmetric.models import (
    AttackingProfile,
    DefensiveProfile,
    ProfileDimension,
    TeamMatchProfiles,
)
from src.research.data_source import ResearchMatch

WINDOW = 10
MIN_HISTORY = 5

# Sentinel prefix used to surface a reduced-confidence flag inside a
# ProfileDimension's ``missing_fields`` (documented mechanism, Req 17.3).
REDUCED_CONFIDENCE_PREFIX = "reduced_confidence:"


# --------------------------------------------------------------------------- #
# Per-side view of one historical match for a single team
# --------------------------------------------------------------------------- #
class _TeamMatchView:
    """A single historical match seen from one team's perspective.

    Resolves "produced" vs "conceded" raw quantities from the correct side of
    the match depending on whether the team was home or away in it (Req 1.5,
    1.18, 11.4). All accessors return ``Optional`` so that NULL != ZERO is
    preserved and per-feature missing-field exclusion (Req 1.17) can act on a
    genuine ``None``.

    The ``league`` label is carried so reduced-confidence flags can be applied
    per league (Req 17.3).
    """

    __slots__ = ("_m", "_is_home", "league")

    def __init__(self, match: ResearchMatch, team: str, league: str) -> None:
        self._m = match
        if team == match.home_team:
            self._is_home = True
        elif team == match.away_team:
            self._is_home = False
        else:  # pragma: no cover - defensive; caller guarantees membership
            raise ValueError(f"team {team!r} not in match {match.match_id}")
        self.league = league

    # -- helpers ----------------------------------------------------------- #
    @staticmethod
    def _ratio(num: Optional[float], den: Optional[float]) -> Optional[float]:
        """Safe ratio; None if either operand is None or denominator is 0."""
        if num is None or den is None:
            return None
        if den == 0:
            return 0.0
        return num / den

    # -- produced (own) raw quantities ------------------------------------- #
    @property
    def corners_for(self) -> Optional[int]:
        return self._m.corners_home if self._is_home else self._m.corners_away

    @property
    def sot_for(self) -> Optional[int]:
        return (
            self._m.shots_on_target_home
            if self._is_home
            else self._m.shots_on_target_away
        )

    @property
    def fouls_for(self) -> Optional[int]:
        return self._m.fouls_home if self._is_home else self._m.fouls_away

    @property
    def yellow_for(self) -> Optional[int]:
        return (
            self._m.yellow_cards_home if self._is_home else self._m.yellow_cards_away
        )

    @property
    def red_for(self) -> Optional[int]:
        return self._m.red_cards_home if self._is_home else self._m.red_cards_away

    @property
    def cards_for(self) -> Optional[int]:
        y, r = self.yellow_for, self.red_for
        if y is None and r is None:
            return None
        return (y or 0) + (r or 0)

    @property
    def attacks_for(self) -> Optional[int]:
        return self._m.attacks_home if self._is_home else self._m.attacks_away

    @property
    def dangerous_attacks_for(self) -> Optional[int]:
        return (
            self._m.dangerous_attacks_home
            if self._is_home
            else self._m.dangerous_attacks_away
        )

    # -- rich produced (own) raw quantities -------------------------------- #
    @property
    def shots_inside_box_for(self) -> Optional[int]:
        return (
            self._m.shots_inside_box_home
            if self._is_home
            else self._m.shots_inside_box_away
        )

    @property
    def big_chances_for(self) -> Optional[int]:
        return self._m.big_chances_home if self._is_home else self._m.big_chances_away

    @property
    def npxg_for(self) -> Optional[float]:
        return self._m.npxg_home if self._is_home else self._m.npxg_away

    @property
    def touches_in_box_for(self) -> Optional[int]:
        return (
            self._m.touches_in_box_home
            if self._is_home
            else self._m.touches_in_box_away
        )

    @property
    def final_third_entries_for(self) -> Optional[int]:
        return (
            self._m.final_third_entries_home
            if self._is_home
            else self._m.final_third_entries_away
        )

    @property
    def fouled_in_final_third_for(self) -> Optional[int]:
        return (
            self._m.fouled_in_final_third_home
            if self._is_home
            else self._m.fouled_in_final_third_away
        )

    @property
    def accurate_crosses_for(self) -> Optional[int]:
        return (
            self._m.accurate_crosses_home
            if self._is_home
            else self._m.accurate_crosses_away
        )

    @property
    def accurate_long_balls_for(self) -> Optional[int]:
        return (
            self._m.accurate_long_balls_home
            if self._is_home
            else self._m.accurate_long_balls_away
        )

    @property
    def aerial_duel_pct_for(self) -> Optional[float]:
        return (
            self._m.aerial_duel_pct_home
            if self._is_home
            else self._m.aerial_duel_pct_away
        )

    @property
    def ground_duel_pct_for(self) -> Optional[float]:
        return (
            self._m.ground_duel_pct_home
            if self._is_home
            else self._m.ground_duel_pct_away
        )

    @property
    def tackles_for(self) -> Optional[int]:
        return self._m.tackles_home if self._is_home else self._m.tackles_away

    @property
    def tackles_won_pct_for(self) -> Optional[float]:
        return (
            self._m.tackles_won_pct_home
            if self._is_home
            else self._m.tackles_won_pct_away
        )

    @property
    def interceptions_for(self) -> Optional[int]:
        return (
            self._m.interceptions_home
            if self._is_home
            else self._m.interceptions_away
        )

    @property
    def clearances_for(self) -> Optional[int]:
        return self._m.clearances_home if self._is_home else self._m.clearances_away

    @property
    def saves_for(self) -> Optional[int]:
        return self._m.saves_home if self._is_home else self._m.saves_away

    @property
    def high_claims_for(self) -> Optional[int]:
        return self._m.high_claims_home if self._is_home else self._m.high_claims_away

    @property
    def goals_prevented_for(self) -> Optional[float]:
        return (
            self._m.goals_prevented_home
            if self._is_home
            else self._m.goals_prevented_away
        )

    # -- conceded (opponent) raw quantities -------------------------------- #
    @property
    def sot_against(self) -> Optional[int]:
        return (
            self._m.shots_on_target_away
            if self._is_home
            else self._m.shots_on_target_home
        )

    @property
    def shots_inside_box_against(self) -> Optional[int]:
        return (
            self._m.shots_inside_box_away
            if self._is_home
            else self._m.shots_inside_box_home
        )

    @property
    def shots_outside_box_against(self) -> Optional[int]:
        return (
            self._m.shots_outside_box_away
            if self._is_home
            else self._m.shots_outside_box_home
        )

    @property
    def blocked_shots_for(self) -> Optional[int]:
        """Blocked shots made by this team's defence (own blocking action)."""
        return (
            self._m.blocked_shots_home
            if self._is_home
            else self._m.blocked_shots_away
        )


# --------------------------------------------------------------------------- #
# Dimension derivations
# --------------------------------------------------------------------------- #
# Each dimension is now derived from one or more *component accessors* on a
# _TeamMatchView, using the rich per-side fields surfaced on ResearchMatch. A
# component is a (design_field_name, accessor, kind) triple where ``kind`` is:
#   "add"   -> the component's per-match value is added into the dimension score
#   "sub"   -> subtracted (used only for conceded-vs-suppression contrast)
# A match contributes to a dimension iff at least one of the dimension's
# components is present (non-None) for that match (Req 1.17 per-feature
# inclusion); every component that is None for an included match, and every
# design-required field that has no surfaced backing at all, is recorded in the
# dimension's ``missing_fields``. When no match has ANY component present the
# dimension collapses to the transparent not-populated default (value 0.0,
# n_matches_used 0, all required fields recorded missing).
#
# NULL != ZERO is preserved throughout: a genuine 0 counts as present and
# contributes 0; only ``None`` triggers exclusion/recording.
#
# Documented per-dimension formulas (rich corpus), each a window mean of the
# per-match sum of present components:
#   width               = accurate_crosses + corners_won + final_third_entries
#                         (final_third_entries as the wide/entry proxy; the
#                          design's ``wide_entries`` field is not surfaced by
#                          TheStatsAPI and is recorded as a permanent gap).
#   central_penetration = touches_in_penalty_area + final_third_entries
#                         + shots_inside_box.
#   volume_vs_quality   = shots_on_target + big_chances + npxg (npxg via
#                         np_expected_goals; "per shot" is captured by summing
#                         npxg alongside shot counts — npxg is thin/absent in
#                         Ligue 2 / La Liga 2 per the audit, handled by exclusion).
#   set_piece_reliance  = corners_won + fouled_in_final_third (advanced-area
#                         fouls-won proxy).
#   directness          = dangerous_attacks / attacks (rich ResearchMatch does
#                         NOT surface attacks/dangerous_attacks -> documented
#                         rich-gap; see module docstring. accurate_long_balls IS
#                         surfaced and is added as the long-balls directness
#                         component so the dimension is derivable in the rich
#                         corpus). Final rich formula: accurate_long_balls
#                         (+ dangerous_attacks/attacks ratio where present).
#   block_orientation   = clearances + interceptions + tackles.
#   aerial_vs_ground    = aerial_duels_percentage - ground_duels_percentage
#                         (signed orientation; both are percentages).
#   shot_suppression    = blocked_shots - (shots_conceded_inside_box
#                         + shots_conceded_outside_box) [conceded side = the
#                         opponent's inside/outside-box shots in that match].
#   gk_contribution     = saves + high_claims (NOT goals_prevented, Req 17.1);
#                         goals_prevented always recorded unavailable.
#   discipline          = fouls_conceded + cards + (100 - tackles_won_percentage)
#                         (tackle success -> tackle-failure contribution, so
#                         higher == more indiscipline; tackle_success recorded
#                         missing when the percentage is absent).


def _add(val: Optional[float], acc: list[float]) -> bool:
    """Append ``val`` to ``acc`` if present; return True iff it was present."""
    if val is None:
        return False
    acc.append(float(val))
    return True


def _d_width(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    parts: list[float] = []
    missing: list[str] = []
    if not _add(v.accurate_crosses_for, parts):
        missing.append("accurate_crosses")
    if not _add(v.corners_for, parts):
        missing.append("corners_won")
    if not _add(v.final_third_entries_for, parts):
        missing.append("final_third_entries")
    if not parts:
        return None, missing
    return sum(parts), missing


def _d_central_penetration(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    parts: list[float] = []
    missing: list[str] = []
    if not _add(v.touches_in_box_for, parts):
        missing.append("touches_in_penalty_area")
    if not _add(v.final_third_entries_for, parts):
        missing.append("final_third_entries")
    if not _add(v.shots_inside_box_for, parts):
        missing.append("shots_inside_box")
    if not parts:
        return None, missing
    return sum(parts), missing


def _d_volume_vs_quality(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    parts: list[float] = []
    missing: list[str] = []
    if not _add(v.sot_for, parts):
        missing.append("shots_on_target")
    if not _add(v.big_chances_for, parts):
        missing.append("big_chances")
    if not _add(v.npxg_for, parts):
        missing.append("npxg_per_shot")
    # total_shots is not individually surfaced (only SOT); record it as a gap.
    missing.append("total_shots")
    if not parts:
        return None, missing
    return sum(parts), missing


def _d_set_piece_reliance(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    parts: list[float] = []
    missing: list[str] = []
    if not _add(v.corners_for, parts):
        missing.append("corners_won")
    if not _add(v.fouled_in_final_third_for, parts):
        missing.append("fouls_won_advanced")
    if not parts:
        return None, missing
    return sum(parts), missing


def _d_directness(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    """Rich directness: accurate_long_balls, plus dangerous/attacks ratio if present.

    The rich ResearchMatch mapping does not surface ``attacks`` /
    ``dangerous_attacks`` (documented rich-gap); when a broad-corpus match DOES
    carry them (reduced path / hand-built), the ratio is added. ``long_balls`` is
    surfaced via ``accurate_long_balls`` and anchors the rich derivation.
    """
    parts: list[float] = []
    missing: list[str] = []
    ratio = _TeamMatchView._ratio(v.dangerous_attacks_for, v.attacks_for)
    if ratio is not None:
        parts.append(ratio)
    else:
        missing.append("attacks")
        missing.append("dangerous_attacks")
    if not _add(v.accurate_long_balls_for, parts):
        missing.append("long_balls")
    if not parts:
        return None, missing
    return sum(parts), missing


def _d_block_orientation(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    parts: list[float] = []
    missing: list[str] = []
    if not _add(v.clearances_for, parts):
        missing.append("clearances")
    if not _add(v.interceptions_for, parts):
        missing.append("interceptions")
    if not _add(v.tackles_for, parts):
        missing.append("tackles")
    if not parts:
        return None, missing
    return sum(parts), missing


def _d_aerial_vs_ground(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    """Signed aerial-vs-ground orientation = aerial% - ground%.

    Both percentages are required for the contrast to be meaningful; if either
    is absent the match is excluded and the absent field recorded.
    """
    missing: list[str] = []
    a = v.aerial_duel_pct_for
    g = v.ground_duel_pct_for
    if a is None:
        missing.append("aerial_duel_pct")
    if g is None:
        missing.append("ground_duel_pct")
    if a is None or g is None:
        return None, missing
    return float(a) - float(g), missing


def _d_shot_suppression(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    """Shot suppression = blocked_shots - shots conceded inside/outside box.

    Conceded side = the opponent's inside/outside-box shots in that match. A
    match contributes iff at least one component is present; absent components
    are recorded.
    """
    parts: list[float] = []
    missing: list[str] = []
    if not _add(v.blocked_shots_for, parts):
        missing.append("blocked_shots")
    ci = v.shots_inside_box_against
    if ci is None:
        missing.append("shots_conceded_inside_box")
    else:
        parts.append(-float(ci))
    co = v.shots_outside_box_against
    if co is None:
        missing.append("shots_conceded_outside_box")
    else:
        parts.append(-float(co))
    if not parts:
        return None, missing
    return sum(parts), missing


def _d_gk_contribution(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    """GK contribution = saves + high_claims (never goals_prevented, Req 17.1)."""
    parts: list[float] = []
    missing: list[str] = []
    if not _add(v.saves_for, parts):
        missing.append("saves")
    if not _add(v.high_claims_for, parts):
        missing.append("high_claims")
    if not parts:
        return None, missing
    return sum(parts), missing


def _d_discipline(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    """Discipline (higher == more indiscipline) = fouls + cards + tackle-failure%.

    tackle-failure% = (100 - tackles_won_percentage) so that low tackle success
    raises the indiscipline score. A match contributes iff at least one of fouls
    or cards is present; tackle success is an enrichment recorded when absent.
    """
    parts: list[float] = []
    missing: list[str] = []
    f = v.fouls_for
    c = v.cards_for
    anchor_present = False
    if f is not None:
        parts.append(float(f))
        anchor_present = True
    else:
        missing.append("fouls_conceded")
    if c is not None:
        parts.append(float(c))
        anchor_present = True
    else:
        missing.append("cards")
    twp = v.tackles_won_pct_for
    if twp is not None:
        parts.append(100.0 - float(twp))
    else:
        missing.append("tackle_success")
    if not anchor_present:
        return None, missing
    return sum(parts), missing


# Rich derivations return (per_match_value_or_None, per_match_missing_fields).
_DERIVATIONS: dict[str, Callable[[_TeamMatchView], "tuple[Optional[float], list[str]]"]] = {
    "width": _d_width,
    "central_penetration": _d_central_penetration,
    "volume_vs_quality": _d_volume_vs_quality,
    "set_piece_reliance": _d_set_piece_reliance,
    "directness": _d_directness,
    "block_orientation": _d_block_orientation,
    "aerial_vs_ground": _d_aerial_vs_ground,
    "shot_suppression": _d_shot_suppression,
    "gk_contribution": _d_gk_contribution,
    "discipline": _d_discipline,
}


# Reduced (broad) derivations (Req 4.3): width from corners, directness from the
# attacks-vs-dangerous ratio, discipline from fouls and cards. Same
# (value, missing) contract; only these three are built in the reduced profile.
def _rd_width(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    c = v.corners_for
    if c is None:
        return None, ["corners_won"]
    return float(c), []


def _rd_directness(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    ratio = _TeamMatchView._ratio(v.dangerous_attacks_for, v.attacks_for)
    if ratio is None:
        return None, ["attacks", "dangerous_attacks"]
    return ratio, []


def _rd_discipline(v: _TeamMatchView) -> tuple[Optional[float], list[str]]:
    f, c = v.fouls_for, v.cards_for
    if f is None and c is None:
        return None, ["fouls_conceded", "cards"]
    missing: list[str] = []
    if f is None:
        missing.append("fouls_conceded")
    if c is None:
        missing.append("cards")
    return float((f or 0) + (c or 0)), missing


_REDUCED_DERIVATIONS: dict[str, Callable[[_TeamMatchView], "tuple[Optional[float], list[str]]"]] = {
    "width": _rd_width,
    "directness": _rd_directness,
    "discipline": _rd_discipline,
}


class TeamProfiler:
    """Builds point-in-time attacking/defensive profiles keyed on team identity.

    Args:
        window: rolling window size (Req 1.4). Default 10.
        min_history: below this many completed matches a profile is marked
            ``insufficient`` (Req 1.16). Default 5.
        reduced: when True, build only the Broad_Corpus reduced dimensions
            (Req 4.3) and carry ``reduced=True`` on the emitted profiles (Req 4.5).
    """

    def __init__(
        self,
        window: int = WINDOW,
        min_history: int = MIN_HISTORY,
        reduced: bool = False,
    ) -> None:
        if window < 1:
            raise ValueError(f"window must be >= 1, got {window}")
        if min_history < 1:
            raise ValueError(f"min_history must be >= 1, got {min_history}")
        self._window = window
        self._min_history = min_history
        self._reduced = reduced

    @property
    def window(self) -> int:
        return self._window

    @property
    def min_history(self) -> int:
        return self._min_history

    @property
    def reduced(self) -> bool:
        return self._reduced

    # ---------------------------------------------------------------- API #
    def compute_profiles_map(
        self, matches: list[ResearchMatch], leagues: Optional[dict[int, str]] = None
    ) -> dict[int, TeamMatchProfiles]:
        """Point-in-time profiles for BOTH teams of every match (Req 1.4, 11.1).

        For each match (processed in ascending ``date_unix`` order), returns a
        mapping ``match_id -> {team -> TeamMatchProfiles}`` collapsed into a
        single dict per match by returning both teams. Concretely the returned
        dict maps ``match_id`` to the HOME team's ``TeamMatchProfiles`` and
        ``-match_id`` (negated) to the AWAY team's, so both point-in-time
        profiles for a fixture are addressable while remaining a flat
        ``dict[int, TeamMatchProfiles]`` per the design signature.

        Every profile is computed from the team's history STRICTLY BEFORE the
        current match, then the current match is folded into both teams'
        histories (compute-before-update, Req 11.3).

        Args:
            matches: matches to profile (any order; sorted internally).
            leagues: optional ``league_id -> label`` map so reduced-confidence
                flags can be applied per league (Req 17.3). When absent the
                numeric ``league_id`` is used as the label.
        """
        leagues = leagues or {}
        ordered = sorted(matches, key=lambda m: m.date_unix)

        history: dict[str, Deque[_TeamMatchView]] = defaultdict(
            lambda: deque(maxlen=self._window)
        )

        out: dict[int, TeamMatchProfiles] = {}
        for m in ordered:
            for team, key in ((m.home_team, m.match_id), (m.away_team, -m.match_id)):
                league = leagues.get(m.league_id, str(m.league_id))
                out[key] = self._profile_from_history(
                    team, int(m.date_unix), list(history[team]), league
                )

            # Fold this match into both teams' histories AFTER reading (Req 11.3).
            self._fold(history, m, leagues)

        return out

    def profile_for_team_at(
        self,
        team: str,
        as_of_unix: int,
        history: list[ResearchMatch],
    ) -> TeamMatchProfiles:
        """Point-in-time profile for one team as of a timestamp (CLI path).

        Only matches strictly before ``as_of_unix`` that the team actually played
        contribute (identity keying across home and away, all leagues — Req 1.5,
        1.18). The most recent ``window`` such matches are used (expanding
        fallback under ``window``).
        """
        views: list[_TeamMatchView] = []
        for m in sorted(history, key=lambda x: x.date_unix):
            if m.date_unix >= as_of_unix:
                continue
            if team not in (m.home_team, m.away_team):
                continue
            views.append(_TeamMatchView(m, team, str(m.league_id)))
        window_views = views[-self._window :]
        return self._profile_from_history(team, as_of_unix, window_views, None)

    # ------------------------------------------------------------- internal #
    def _fold(
        self,
        history: dict[str, Deque[_TeamMatchView]],
        match: ResearchMatch,
        leagues: dict[int, str],
    ) -> None:
        """Append this completed match to each team's rolling history."""
        if not _is_completed(match):
            return
        league = leagues.get(match.league_id, str(match.league_id))
        history[match.home_team].append(_TeamMatchView(match, match.home_team, league))
        history[match.away_team].append(_TeamMatchView(match, match.away_team, league))

    def _profile_from_history(
        self,
        team: str,
        as_of_unix: int,
        views: list[_TeamMatchView],
        league: Optional[str],
    ) -> TeamMatchProfiles:
        """Build both profiles for ``team`` from its prior-match ``views``."""
        n = len(views)
        insufficient = n < self._min_history

        # The profile object always carries all five attacking and five
        # defensive dimensions so the vector shape is stable. In the reduced
        # profile, rich-only dimensions are emitted as not-populated (handled in
        # _dimension), which is how "rich-only dimensions marked absent" (Req 4.3)
        # is surfaced without changing the frozen model's shape.
        att_names = ["width", "central_penetration", "volume_vs_quality",
                     "set_piece_reliance", "directness"]
        def_names = ["block_orientation", "aerial_vs_ground",
                     "shot_suppression", "gk_contribution", "discipline"]

        att = {name: self._dimension(name, views, league) for name in att_names}
        deff = {name: self._dimension(name, views, league) for name in def_names}

        attacking = AttackingProfile(
            team=team,
            as_of_unix=as_of_unix,
            width=att["width"],
            central_penetration=att["central_penetration"],
            volume_vs_quality=att["volume_vs_quality"],
            set_piece_reliance=att["set_piece_reliance"],
            directness=att["directness"],
            reduced=self._reduced,
        )
        defensive = DefensiveProfile(
            team=team,
            as_of_unix=as_of_unix,
            block_orientation=deff["block_orientation"],
            aerial_vs_ground=deff["aerial_vs_ground"],
            shot_suppression=deff["shot_suppression"],
            gk_contribution=deff["gk_contribution"],
            discipline=deff["discipline"],
            reduced=self._reduced,
        )
        return TeamMatchProfiles(
            team=team,
            n_history=n,
            insufficient=insufficient,
            attacking=attacking,
            defensive=defensive,
        )

    def _dimension(
        self,
        name: str,
        views: list[_TeamMatchView],
        league: Optional[str],
    ) -> ProfileDimension:
        """Compute one dimension as the window mean over present-component matches.

        Missing-field handling (Req 1.17): a match contributes to the dimension
        iff the derivation yields a non-None value (at least one required
        component present); matches whose components are entirely absent are
        excluded from THIS dimension only. Every component field that was absent
        on an included match, plus every design-required field with no surfaced
        backing, is recorded in ``missing_fields``. NULL != ZERO is preserved: a
        genuine 0 counts as present.
        """
        spec = pdims.get_dimension(name)
        corpus = pdims.BROAD_CORPUS if self._reduced else pdims.RICH_CORPUS

        # In a reduced profile, dimensions requiring rich-only fields are absent:
        # emit a not-populated dimension with all required fields recorded.
        if self._reduced and not spec.in_reduced_profile:
            return ProfileDimension(
                name=name,
                value=0.0,
                source_fields=spec.required_fields,
                n_matches_used=0,
                missing_fields=spec.required_fields,
            )

        derive = (
            _REDUCED_DERIVATIONS[name]
            if self._reduced
            else _DERIVATIONS[name]
        )

        present: list[float] = []
        missing_accum: list[str] = []
        for v in views:
            val, per_match_missing = derive(v)
            if val is None:
                # Match excluded from this dimension; still surface which of its
                # components were absent (Req 1.17 field recording).
                missing_accum.extend(per_match_missing)
                continue
            present.append(val)
            missing_accum.extend(per_match_missing)

        source = spec.source_fields(corpus=corpus)

        if present:
            value = sum(present) / len(present)
        else:
            # Entirely not populated from available fields -> transparent default.
            value = 0.0
            # Record every required field when nothing was derivable at all.
            missing_accum.extend(spec.required_fields)

        # goals_prevented is optional+unavailable for gk_contribution: always
        # record it as unavailable (Req 17.1, 17.2), regardless of population.
        if name == "gk_contribution":
            missing_accum.append("goals_prevented")

        # Reduced-confidence sentinel (Req 17.3): surfaced via missing_fields.
        # The audit case is central_penetration in the Championship, where
        # touches_in_penalty_area is thin (~5%).
        if (
            league is not None
            and name == "central_penetration"
            and pdims.is_reduced_confidence(league, name)
        ):
            missing_accum.append(
                f"{REDUCED_CONFIDENCE_PREFIX}touches_in_penalty_area"
            )

        # De-duplicate while preserving first-seen order.
        seen: set[str] = set()
        deduped: list[str] = []
        for f in missing_accum:
            if f not in seen:
                seen.add(f)
                deduped.append(f)

        return ProfileDimension(
            name=name,
            value=float(value),
            source_fields=tuple(source),
            n_matches_used=len(present),
            missing_fields=tuple(deduped),
        )


# --------------------------------------------------------------------------- #
# Completed-match predicate
# --------------------------------------------------------------------------- #
def _is_completed(match: ResearchMatch) -> bool:
    """A match counts toward history only if it has a played result (Req 1.4).

    We treat a match as completed when both goal counts are present (post-match
    fields populated). This mirrors the corpus loaders, which only admit played
    matches, but is defensive for hand-built histories in tests.
    """
    return match.home_goals is not None and match.away_goals is not None
