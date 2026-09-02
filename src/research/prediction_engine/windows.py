"""Feature windows (w5 and w10) with explicit per-field computability.

The engine uses TWO rolling windows — **w5** and **w10** — and lets the model
select which window matters *per market and per league* rather than forcing one
across all targets. Reporting which window carries weight where is itself a
finding worth publishing (e.g. "cards respond to short-term form, corners to a
longer-term team profile").

Two stat sources, availability handled explicitly
=================================================
* **Broad (FootyStats, ~15,362 matches, 25 leagues)** — the backbone. Core
  observables (goals, corners, cards, shots, fouls, possession, attacks,
  dangerous attacks, xG) support both windows widely.
* **Rich (TheStatsAPI, ~3,189 matches)** — tackles, interceptions, clearances,
  ball recoveries, blocked shots, shots inside/outside box, big chances, touches
  in the box, crosses, long balls, duels, saves, npxG — available only in a few
  leagues (Championship / La Liga 2 / Ligue 2 / a slice of the EPL).

The rich fields exist for far fewer matches, so w10 on a rich field may be
uncomputable for teams with thin rich-data history. This module reports
**per-league, per-window, per-field computability** and **excludes what cannot
be built rather than silently defaulting to zero** (NULL != ZERO).

Known gaps respected (from the coverage audit)
==============================================
* ``goals_prevented`` — 0% populated everywhere; never usable (use saves alone).
* ``touches_in_penalty_area`` (``touches_in_box``) — ~5% in the Championship;
  computability is measured, not assumed.
* Referee assignment — not available pre-match in either source; never a feature.

Point-in-time discipline
=========================
Rolling means are computed compute-before-update, keyed on team identity across
home and away appearances, look-ahead-free — the same discipline as
:func:`src.research.asymmetric.evaluation.build_marginal_features`. The current
match never enters its own feature.

NO STAKE SIZING anywhere here.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Optional

from src.research.data_source import ResearchMatch

# ─────────────────────────────────────────────────────────────────────────────
# Windows
# ─────────────────────────────────────────────────────────────────────────────

#: The two supported rolling windows.
WINDOWS: tuple[int, ...] = (5, 10)


# ─────────────────────────────────────────────────────────────────────────────
# Field taxonomy: which side-resolved fields come from which source
# ─────────────────────────────────────────────────────────────────────────────
#
# Each entry maps a logical per-side field name to the ResearchMatch attribute
# pair (home_attr, away_attr). "Broad" fields come from FootyStats and are widely
# available; "rich" fields come from TheStatsAPI and are league-restricted.

#: Broad (FootyStats) per-side count/rate fields — the backbone.
BROAD_FIELDS: dict[str, tuple[str, str]] = {
    "goals": ("home_goals", "away_goals"),
    "corners": ("corners_home", "corners_away"),
    "shots": ("shots_home", "shots_away"),
    "shots_on_target": ("shots_on_target_home", "shots_on_target_away"),
    "fouls": ("fouls_home", "fouls_away"),
    "possession": ("possession_home", "possession_away"),
    "attacks": ("attacks_home", "attacks_away"),
    "dangerous_attacks": ("dangerous_attacks_home", "dangerous_attacks_away"),
    "xg": ("home_xg", "away_xg"),
    "yellow_cards": ("yellow_cards_home", "yellow_cards_away"),
    "red_cards": ("red_cards_home", "red_cards_away"),
    "offsides": ("offsides_home", "offsides_away"),
}

#: Rich (TheStatsAPI) per-side fields — league-restricted, may be uncomputable.
RICH_FIELDS: dict[str, tuple[str, str]] = {
    "shots_inside_box": ("shots_inside_box_home", "shots_inside_box_away"),
    "shots_outside_box": ("shots_outside_box_home", "shots_outside_box_away"),
    "blocked_shots": ("blocked_shots_home", "blocked_shots_away"),
    "big_chances": ("big_chances_home", "big_chances_away"),
    "npxg": ("npxg_home", "npxg_away"),
    "touches_in_box": ("touches_in_box_home", "touches_in_box_away"),
    "final_third_entries": ("final_third_entries_home", "final_third_entries_away"),
    "fouled_in_final_third": ("fouled_in_final_third_home", "fouled_in_final_third_away"),
    "accurate_crosses": ("accurate_crosses_home", "accurate_crosses_away"),
    "accurate_long_balls": ("accurate_long_balls_home", "accurate_long_balls_away"),
    "aerial_duel_pct": ("aerial_duel_pct_home", "aerial_duel_pct_away"),
    "ground_duel_pct": ("ground_duel_pct_home", "ground_duel_pct_away"),
    "tackles": ("tackles_home", "tackles_away"),
    "tackles_won_pct": ("tackles_won_pct_home", "tackles_won_pct_away"),
    "interceptions": ("interceptions_home", "interceptions_away"),
    "clearances": ("clearances_home", "clearances_away"),
    "saves": ("saves_home", "saves_away"),
    "high_claims": ("high_claims_home", "high_claims_away"),
    # goals_prevented deliberately EXCLUDED: 0% populated everywhere (use saves).
}

#: Fields that are known to be unusable regardless of what a corpus appears to
#: hold (respected from the coverage audit). goals_prevented is 0% populated.
KNOWN_ZERO_POPULATION_FIELDS: frozenset[str] = frozenset({"goals_prevented"})

#: Referee is not available pre-match in either source and is never a feature.
NEVER_PREMATCH_FIELDS: frozenset[str] = frozenset({"referee"})

#: The per-side source fields each market's rolling features draw on. Cards uses
#: the sum of yellow+red as its own family already models; here we expose the
#: component drivers plus the correlated broad observables the validated engine
#: found useful. Goals/BTTS share the goals-family observables.
MARKET_SOURCE_FIELDS: dict[str, tuple[str, ...]] = {
    "corners": ("corners", "shots", "shots_on_target", "attacks", "dangerous_attacks"),
    "cards": ("yellow_cards", "red_cards", "fouls"),
    "goals": ("goals", "shots_on_target", "xg", "dangerous_attacks"),
    "btts": ("goals", "shots_on_target", "xg"),
}


def all_fields() -> dict[str, tuple[str, str]]:
    """Merged broad+rich field map."""
    return {**BROAD_FIELDS, **RICH_FIELDS}


def is_rich_field(field_name: str) -> bool:
    return field_name in RICH_FIELDS


# ─────────────────────────────────────────────────────────────────────────────
# Per-side observed value extraction (NULL != ZERO)
# ─────────────────────────────────────────────────────────────────────────────
def _side_value(m: ResearchMatch, attr: str) -> Optional[float]:
    """Read a per-side field value, preserving None (absent) vs 0 (genuine zero)."""
    v = getattr(m, attr, None)
    return None if v is None else float(v)


# ─────────────────────────────────────────────────────────────────────────────
# Computability report
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FieldWindowComputability:
    """Computability of one field at one window, in one league.

    Attributes:
        field_name: logical field name.
        source: "broad" or "rich".
        window: 5 or 10.
        league_id: the league this row describes.
        population_rate: fraction of side-observations where the raw field is
            present (NULL != ZERO; a present 0 counts as populated).
        computable_sides: number of (match, side) points where a full rolling
            window of that size could be filled from strictly-prior history.
        total_sides: total (match, side) points considered.
        computable: True iff the field is usable at this window in this league —
            it is present often enough AND enough teams have the window's depth
            of history. Uncomputable fields are EXCLUDED, never zero-filled.
        reason: why it is/ isn't computable (esp. for excluded fields).
    """

    field_name: str
    source: str
    window: int
    league_id: Optional[int]
    population_rate: float
    computable_sides: int
    total_sides: int
    computable: bool
    reason: str

    @property
    def computable_rate(self) -> float:
        return self.computable_sides / self.total_sides if self.total_sides else 0.0


#: Minimum share of side-observations that must carry the raw field for it to be
#: considered available at all (below this, the field is excluded).
DEFAULT_MIN_POPULATION_RATE = 0.5

#: Minimum share of side-observations for which a full window of prior history
#: exists, for the field+window to be considered computable in a league.
DEFAULT_MIN_COMPUTABLE_RATE = 0.5


def field_window_computability(
    matches: list[ResearchMatch],
    *,
    league_id: Optional[int] = None,
    fields: Optional[dict[str, tuple[str, str]]] = None,
    windows: tuple[int, ...] = WINDOWS,
    min_population_rate: float = DEFAULT_MIN_POPULATION_RATE,
    min_computable_rate: float = DEFAULT_MIN_COMPUTABLE_RATE,
) -> list[FieldWindowComputability]:
    """Report per-field, per-window computability for a set of matches.

    For each field and each window, this measures (a) how often the raw field is
    populated (NULL != ZERO), and (b) for how many (match, side) points a full
    rolling window of prior observations of that field exists — i.e. whether w10
    can actually be built given each team's rich-data history depth. A field is
    marked ``computable`` only when both rates clear their thresholds; otherwise
    it is EXCLUDED with a reason (never silently zero-filled).

    Args:
        matches: the corpus slice (typically one league). Processed in ascending
            ``date_unix`` order for the history-depth check.
        league_id: label for the rows (does not filter — pass a pre-filtered
            slice).
        fields: field map to assess (defaults to broad+rich merged).
        windows: windows to assess (defaults to w5 and w10).
        min_population_rate / min_computable_rate: thresholds described above.

    Returns:
        One :class:`FieldWindowComputability` per (field, window).
    """
    field_map = fields if fields is not None else all_fields()
    ordered = sorted(matches, key=lambda m: m.date_unix)

    # Count population and, per team, the depth of prior history available at
    # each side-observation (compute-before-update).
    reports: list[FieldWindowComputability] = []

    for field_name, (home_attr, away_attr) in field_map.items():
        source = "rich" if is_rich_field(field_name) else "broad"

        # Known-zero-population override (audit): goals_prevented etc.
        if field_name in KNOWN_ZERO_POPULATION_FIELDS:
            for w in windows:
                reports.append(
                    FieldWindowComputability(
                        field_name=field_name, source=source, window=w,
                        league_id=league_id, population_rate=0.0,
                        computable_sides=0, total_sides=0, computable=False,
                        reason="field is 0% populated everywhere per the coverage "
                        "audit; excluded (never zero-filled)",
                    )
                )
            continue

        # Walk chronologically, tracking each team's count of PRIOR present
        # observations of this field, and how many side-points had >= w prior.
        history_len: dict[str, int] = defaultdict(int)
        total_sides = 0
        present_sides = 0
        # depth_at_point[w] counts side-points with >= w prior present obs.
        depth_at_point: dict[int, int] = {w: 0 for w in windows}

        for m in ordered:
            for team, attr in ((m.home_team, home_attr), (m.away_team, away_attr)):
                total_sides += 1
                prior = history_len[team]
                for w in windows:
                    if prior >= w:
                        depth_at_point[w] += 1
                val = _side_value(m, attr)
                if val is not None:
                    present_sides += 1
            # update AFTER reading (compute-before-update)
            for team, attr in ((m.home_team, home_attr), (m.away_team, away_attr)):
                if _side_value(m, attr) is not None:
                    history_len[team] += 1

        population_rate = present_sides / total_sides if total_sides else 0.0

        for w in windows:
            computable_sides = depth_at_point[w]
            computable_rate = computable_sides / total_sides if total_sides else 0.0
            # A field+window is computable only if the raw field is populated
            # often enough AND enough side-points have the window's depth.
            enough_population = population_rate >= min_population_rate
            enough_depth = computable_rate >= min_computable_rate
            computable = enough_population and enough_depth
            if computable:
                reason = (
                    f"populated {population_rate:.0%} of side-obs; {computable_rate:.0%} "
                    f"of side-obs have >= {w} prior observations"
                )
            elif not enough_population:
                reason = (
                    f"EXCLUDED: field populated only {population_rate:.0%} of side-obs "
                    f"(< {min_population_rate:.0%}); not zero-filled"
                )
            else:
                reason = (
                    f"EXCLUDED at w{w}: only {computable_rate:.0%} of side-obs have "
                    f">= {w} prior observations (thin history for this window); "
                    "not zero-filled"
                )
            reports.append(
                FieldWindowComputability(
                    field_name=field_name, source=source, window=w,
                    league_id=league_id, population_rate=population_rate,
                    computable_sides=computable_sides, total_sides=total_sides,
                    computable=computable, reason=reason,
                )
            )

    return reports


# ─────────────────────────────────────────────────────────────────────────────
# Rolling window features (w5 + w10), look-ahead-free, per team
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class WindowFeatureRow:
    """The w5/w10 rolling features for one side of one match.

    Attributes:
        match_id / league_id / team / side: identity.
        features: ``{f"{field}_w{window}" -> rolling mean}`` computed ONLY from
            the team's strictly-prior matches where the field was present. Fields
            with no prior present observation are OMITTED (never zero-filled), so
            a missing key means "uncomputable for this team at this point", which
            the model treats as an absent feature.
        n_prior: the team's completed-match count prior to this fixture (for the
            family's ``n/(n+k)`` shrinkage bookkeeping).
    """

    match_id: int
    league_id: int
    team: str
    side: str
    features: dict[str, float]
    n_prior: int


def build_window_features(
    matches: list[ResearchMatch],
    *,
    fields: Optional[dict[str, tuple[str, str]]] = None,
    windows: tuple[int, ...] = WINDOWS,
) -> list[WindowFeatureRow]:
    """Build look-ahead-free w5/w10 rolling-mean features per side, per match.

    For each match (ascending ``date_unix``) and each side, emits a
    :class:`WindowFeatureRow` whose features are that team's rolling mean of each
    requested field over its last ``w`` PRESENT observations strictly before this
    fixture. NULL != ZERO: absent raw values never enter the mean, and a field
    with zero prior present observations is OMITTED from the row (not zero-filled).

    This shares the compute-before-update discipline of the validated engine, so
    the current match cannot leak into its own feature.
    """
    field_map = fields if fields is not None else all_fields()
    ordered = sorted(matches, key=lambda m: m.date_unix)

    # Per (team, field) rolling deque of PRESENT values; per-team match count.
    history: dict[tuple[str, str], Deque[float]] = defaultdict(
        lambda: deque(maxlen=max(windows))
    )
    match_count: dict[str, int] = defaultdict(int)

    rows: list[WindowFeatureRow] = []
    for m in ordered:
        for side, team in (("home", m.home_team), ("away", m.away_team)):
            feats: dict[str, float] = {}
            for field_name, (home_attr, away_attr) in field_map.items():
                if field_name in KNOWN_ZERO_POPULATION_FIELDS:
                    continue
                prior = history[(team, field_name)]
                if not prior:
                    continue  # uncomputable: no prior present obs (omit, not zero)
                prior_list = list(prior)
                for w in windows:
                    if len(prior_list) >= w:
                        window_vals = prior_list[-w:]
                        feats[f"{field_name}_w{w}"] = sum(window_vals) / len(window_vals)
                    # else: window not fillable yet -> omit that window's feature
            rows.append(
                WindowFeatureRow(
                    match_id=m.match_id,
                    league_id=m.league_id,
                    team=team,
                    side=side,
                    features=feats,
                    n_prior=match_count[team],
                )
            )
        # Update AFTER reading (compute-before-update). Only present values enter.
        for side, team in (("home", m.home_team), ("away", m.away_team)):
            match_count[team] += 1
            for field_name, (home_attr, away_attr) in field_map.items():
                if field_name in KNOWN_ZERO_POPULATION_FIELDS:
                    continue
                attr = home_attr if side == "home" else away_attr
                val = _side_value(m, attr)
                if val is not None:
                    history[(team, field_name)].append(val)

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Window selection: which window carries weight, per market and per league
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class WindowSelection:
    """Which window (5 or 10) the model weights more for a market in a league.

    A publishable finding in its own right (Section 3b of the brief). ``weights``
    holds the total absolute model weight attributed to each window's features;
    ``selected_window`` is the argmax. When windows are effectively tied (within
    ``tie_tolerance``) ``selected_window`` is None and ``tied`` is True.
    """

    market: str
    league_label: Optional[str]
    weights: dict[int, float]
    selected_window: Optional[int]
    tied: bool
    detail: str


DEFAULT_TIE_TOLERANCE = 0.05


def select_window(
    market: str,
    feature_weights: dict[str, float],
    *,
    league_label: Optional[str] = None,
    windows: tuple[int, ...] = WINDOWS,
    tie_tolerance: float = DEFAULT_TIE_TOLERANCE,
) -> WindowSelection:
    """Determine which window carries weight for a market in a league.

    Sums the absolute fitted model weights over features whose name ends in
    ``_w{window}`` (as produced by :func:`build_window_features`) and reports the
    dominant window. This lets the engine state, per market and per league, that
    e.g. cards respond to short-term (w5) form while corners respond to a
    longer-term (w10) team profile — a finding worth publishing.

    Args:
        market: market key (labelling only).
        feature_weights: the fitted model's ``{feature_name -> weight}``.
        league_label: league (labelling only).
        windows: windows to score.
        tie_tolerance: relative gap below which the top two windows are "tied".
    """
    weights = {w: 0.0 for w in windows}
    for name, w_val in feature_weights.items():
        for w in windows:
            if name.endswith(f"_w{w}"):
                weights[w] += abs(float(w_val))
                break

    total = sum(weights.values())
    if total <= 0.0:
        return WindowSelection(
            market=market, league_label=league_label, weights=weights,
            selected_window=None, tied=False,
            detail="no window features carried weight (no windowed features fitted)",
        )

    ranked = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    top_w, top_v = ranked[0]
    second_v = ranked[1][1] if len(ranked) > 1 else 0.0
    # Relative gap between top two windows.
    gap = (top_v - second_v) / total
    if gap < tie_tolerance:
        return WindowSelection(
            market=market, league_label=league_label, weights=weights,
            selected_window=None, tied=True,
            detail=(
                f"windows are effectively tied (relative gap {gap:.1%} < "
                f"{tie_tolerance:.0%}); no single window dominates for {market}"
            ),
        )
    share = top_v / total
    return WindowSelection(
        market=market, league_label=league_label, weights=weights,
        selected_window=top_w, tied=False,
        detail=(
            f"w{top_w} carries the most weight for {market}"
            + (f" in {league_label}" if league_label else "")
            + f" ({share:.0%} of windowed weight)"
        ),
    )
