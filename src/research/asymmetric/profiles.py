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
Computability from the current ``ResearchMatch`` (documented decision)
---------------------------------------------------------------------------
The design's dimension source-field tables (``profile_dimensions.py``) name many
rich TheStatsAPI fields (touches_in_penalty_area, accurate_crosses, clearances,
interceptions, tackles, duels, saves, ...) that are NOT surfaced on
``ResearchMatch`` — the Rich corpus loader only maps goals, shots-on-target,
corners, cards, fouls, and xG through (see ``corpus._adapted_to_research_match``).
Following task 3.2's guidance we take the pragmatic option (b): compute every
dimension that the *available* ``ResearchMatch`` fields permit, and for any
dimension whose required fields are entirely unavailable, emit a transparent
not-populated ``ProfileDimension`` (value ``0.0``, all required fields recorded
in ``missing_fields``) rather than fabricate a value. This keeps tasks 4-13
(which depend on profiles existing) unblocked while never inventing data.

Per-dimension computability from the current ``ResearchMatch`` fields:

  Attacking
    width               PARTIAL   corners_won <- corners_{home,away}; accurate_crosses,
                                  wide_entries unavailable (recorded missing).
    central_penetration NONE      touches_in_penalty_area, final_third_entries,
                                  shots_inside_box all unavailable.
    volume_vs_quality   PARTIAL   shots_on_target present; total_shots, big_chances,
                                  npxg_per_shot unavailable (recorded missing).
    set_piece_reliance  PARTIAL   corners_won present; fouls_won_advanced unavailable.
    directness          NONE*     attacks, dangerous_attacks NOT surfaced by the Rich
                                  loader on ResearchMatch (long_balls also absent). Fully
                                  computable in the reduced/broad path where attacks +
                                  dangerous_attacks are present; NONE in the current rich
                                  ResearchMatch mapping.
  Defensive
    block_orientation   NONE      clearances, interceptions, tackles unavailable.
    aerial_vs_ground    NONE      aerial/ground duel % unavailable.
    shot_suppression    PARTIAL   conceded shots-on-target proxy from opponent
                                  shots_on_target; inside/outside-box + blocked_shots
                                  unavailable (recorded missing).
    gk_contribution     NONE      saves/high_claims unavailable (goals_prevented also
                                  absent, recorded missing per Req 17.1/17.2).
    discipline          PARTIAL   cards + fouls_conceded present; tackle_success
                                  unavailable (recorded missing).

  * ``directness`` becomes fully computable the moment ``attacks`` /
    ``dangerous_attacks`` are surfaced; the reduced (broad) profile below already
    computes it because those fields exist on FootyStats matches.

If/when the corpus path is extended to surface the rich fields, the derivation
helpers below can read them directly; the missing-field machinery already
degrades gracefully.

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

    # -- conceded (opponent) raw quantities -------------------------------- #
    @property
    def sot_against(self) -> Optional[int]:
        return (
            self._m.shots_on_target_away
            if self._is_home
            else self._m.shots_on_target_home
        )


# --------------------------------------------------------------------------- #
# Dimension derivations
# --------------------------------------------------------------------------- #
# Each derivation is a callable that, given a _TeamMatchView, returns either the
# per-match derived scalar for the dimension, or None if a required raw field is
# unavailable for that match (triggering per-feature exclusion, Req 1.17).
#
# The dimension's ``spec.required_fields`` names *all* fields the design wants;
# where a required field is not surfaced on ResearchMatch the derivation returns
# None so the field is recorded missing and the match is excluded. For a
# dimension whose fields are entirely unavailable, the derivation always returns
# None and the dimension collapses to the not-populated default.


def _d_width(v: _TeamMatchView) -> Optional[float]:
    """Width proxy from corners won (accurate_crosses/wide_entries unavailable)."""
    c = v.corners_for
    return float(c) if c is not None else None


def _d_central_penetration(v: _TeamMatchView) -> Optional[float]:
    """touches_in_penalty_area / final_third_entries / shots_inside_box: none surfaced."""
    return None


def _d_volume_vs_quality(v: _TeamMatchView) -> Optional[float]:
    """Volume-vs-quality proxy from shots on target (rich shot fields unavailable)."""
    s = v.sot_for
    return float(s) if s is not None else None


def _d_set_piece_reliance(v: _TeamMatchView) -> Optional[float]:
    """Set-piece reliance proxy from corners won (fouls_won_advanced unavailable)."""
    c = v.corners_for
    return float(c) if c is not None else None


def _d_directness(v: _TeamMatchView) -> Optional[float]:
    """Directness = dangerous_attacks / attacks (not surfaced on rich ResearchMatch)."""
    return _TeamMatchView._ratio(v.dangerous_attacks_for, v.attacks_for)


def _d_block_orientation(v: _TeamMatchView) -> Optional[float]:
    """clearances / interceptions / tackles: none surfaced."""
    return None


def _d_aerial_vs_ground(v: _TeamMatchView) -> Optional[float]:
    """aerial/ground duel %: not surfaced."""
    return None


def _d_shot_suppression(v: _TeamMatchView) -> Optional[float]:
    """Shot-suppression proxy: opponent shots on target conceded (lower is better).

    Inside/outside-box splits and blocked_shots are unavailable; we use conceded
    shots-on-target as the derivable conceded-side proxy.
    """
    s = v.sot_against
    return float(s) if s is not None else None


def _d_gk_contribution(v: _TeamMatchView) -> Optional[float]:
    """saves / high_claims unavailable (goals_prevented also absent — Req 17.1/2)."""
    return None


def _d_discipline(v: _TeamMatchView) -> Optional[float]:
    """Discipline from fouls conceded and cards (tackle_success unavailable).

    Higher value == more indiscipline. Combines fouls and cards additively; if
    both are None the match is excluded from this feature.
    """
    f, c = v.fouls_for, v.cards_for
    if f is None and c is None:
        return None
    return float((f or 0) + (c or 0))


# Reduced (broad) derivations (Req 4.3): width from corners, directness from
# attacks-vs-dangerous ratio, discipline from fouls and cards.
_DERIVATIONS: dict[str, Callable[[_TeamMatchView], Optional[float]]] = {
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

# Which raw ResearchMatch field each dimension actually reads, so we can record
# a precise missing-field entry when it is None for a match. Maps dimension ->
# the accessor name(s) on _TeamMatchView used, paired with the design field name
# recorded in missing_fields. For dimensions with no surfaced field, the whole
# ``required_fields`` set is recorded missing.
_PRIMARY_FIELD: dict[str, str] = {
    "width": "corners_won",
    "volume_vs_quality": "shots_on_target",
    "set_piece_reliance": "corners_won",
    "directness": "attacks",  # ratio needs attacks + dangerous_attacks
    "shot_suppression": "shots_conceded",
    "discipline": "cards",
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
        """Compute one dimension as the window mean over present-field matches.

        Missing-field handling (Req 1.17): matches whose required field is
        unavailable (derivation returns ``None``) are excluded from THIS
        dimension only; the primary field is recorded in ``missing_fields``. When
        the dimension is present in the reduced profile, its reduced source
        fields are used for reporting.
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

        derive = _DERIVATIONS[name]
        present: list[float] = []
        excluded = 0
        for v in views:
            val = derive(v)
            if val is None:
                excluded += 1
                continue
            present.append(val)

        source = spec.source_fields(corpus=corpus)
        missing: list[str] = []

        if present:
            value = sum(present) / len(present)
        else:
            # Entirely not populated from available fields -> transparent default.
            value = 0.0

        # Record missing fields: the design's required fields that are not
        # surfaced on ResearchMatch, plus any per-match exclusions.
        if not present:
            # Nothing derivable at all -> record every required field.
            missing.extend(spec.required_fields)
        else:
            # We derived from a proxy; record the design-required fields that are
            # not backed by a surfaced ResearchMatch field, or that were None on
            # some matches. The primary field is the one we actually read.
            primary = _PRIMARY_FIELD.get(name)
            for f in spec.required_fields:
                # A required field is "missing" if it is not the primary surfaced
                # field we computed from (proxies for the unavailable rich fields).
                if primary is None or f != primary:
                    # directness needs both attacks and dangerous_attacks; both are
                    # surfaced together, so neither should be flagged when present.
                    if name == "directness" and f in ("attacks", "dangerous_attacks"):
                        continue
                    missing.append(f)
            if excluded:
                # Some matches lacked the primary field; record it too.
                if primary is not None and primary not in missing:
                    missing.append(primary)

        # goals_prevented is optional+unavailable for gk_contribution: always
        # record it as unavailable (Req 17.1, 17.2).
        if name == "gk_contribution" and "goals_prevented" not in missing:
            missing.append("goals_prevented")

        # Reduced-confidence sentinel (Req 17.3): surfaced via missing_fields.
        # The audit case is central_penetration in the Championship, where
        # touches_in_penalty_area is thin (~5%).
        if (
            league is not None
            and name == "central_penetration"
            and pdims.is_reduced_confidence(league, name)
        ):
            missing.append(f"{REDUCED_CONFIDENCE_PREFIX}touches_in_penalty_area")

        # De-duplicate while preserving order.
        seen: set[str] = set()
        deduped: list[str] = []
        for f in missing:
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
