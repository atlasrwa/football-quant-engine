"""Named profile dimensions and the reduced-profile map (declarative spec).

Responsibility:
    Define, *as data*, the specification of every named profile dimension of the
    Team_Profiler: its name, the raw source fields it is derived from (split into
    required vs optional/unavailable fields), which corpus it is available in
    (``rich`` full-profile vs ``broad`` reduced-profile), and the audit-grounded
    reduced-confidence annotations.

    This module contains **no computation**. It is a declarative catalogue that
    task 3.2 (``TeamProfiler`` in ``profiles.py``) consumes to know which raw
    fields to read for each dimension, which fields are optional (so a dimension
    stays buildable when they are absent), and which (league, dimension) pairs
    must be flagged as reduced-confidence.

Named attacking dimensions (Req 1.6-1.10):
    width, central_penetration, volume_vs_quality, set_piece_reliance, directness.
Named defensive dimensions (Req 1.11-1.15):
    block_orientation, aerial_vs_ground, shot_suppression, gk_contribution,
    discipline.

Audit-grounded constraints (Req 17):
    - ``gk_contribution`` is built from ``saves`` (and ``high_claims`` where
      present) and MUST NOT require ``goals_prevented``, which the coverage audit
      (docs/coverage_matrix.md) found zero-populated across the Rich_Corpus
      leagues. ``goals_prevented`` is therefore declared *optional/unavailable*
      so the dimension is buildable from ``saves`` alone (Req 17.1, 17.2).
    - ``central_penetration`` is flagged reduced-confidence for the Championship
      because ``touches_in_penalty_area`` is thin (~5%) there (Req 17.3).

Reduced-profile map for the Broad_Corpus (Req 4.3):
    width from corners, directness from the attacks-vs-dangerous-attacks ratio,
    and discipline from fouls and cards. Dimensions requiring rich-only fields
    are marked absent from the reduced profile.

Requirements: 1.6-1.15, 4.3, 17.1, 17.2, 17.3.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Corpus identifiers -----------------------------------------------------

RICH_CORPUS = "rich"
BROAD_CORPUS = "broad"

# The one league whose touches-in-penalty-area coverage is thin (~5%), per the
# coverage audit (docs/coverage_matrix.md, Req 17.3).
CHAMPIONSHIP = "Championship"


@dataclass(frozen=True)
class DimensionSpec:
    """Declarative specification of a single named profile dimension.

    This is data, not computation. It tells the ``TeamProfiler`` which raw
    fields to read for the dimension and how to treat them.

    Attributes:
        name:
            The dimension's stable identifier (e.g. ``"width"``), matching the
            field name on ``AttackingProfile`` / ``DefensiveProfile``.
        side:
            ``"attacking"`` or ``"defensive"``.
        requirement:
            The acceptance-criterion id this dimension satisfies (e.g. ``"1.6"``).
        required_fields:
            Raw source fields the dimension needs. The dimension is buildable as
            long as at least the required fields are available for a match; a
            match missing any required field is excluded from *this* feature only
            (Req 1.17), handled downstream in task 3.2.
        optional_fields:
            Raw source fields that enrich the dimension when present but are NOT
            required to build it. ``goals_prevented`` is optional for
            ``gk_contribution`` precisely because the audit found it
            zero-populated (Req 17.1, 17.2).
        unavailable_fields:
            The subset of ``optional_fields`` that the coverage audit found to be
            effectively unpopulated across the Rich_Corpus leagues. Declared
            explicitly so the profiler records them as unavailable rather than
            silently treating a null as zero.
        available_in:
            The corpora in which this dimension can be built. Rich-only
            dimensions omit ``BROAD_CORPUS``; dimensions present in the reduced
            profile include both ``RICH_CORPUS`` and ``BROAD_CORPUS``.
        thin_in_leagues:
            Leagues for which a required field is thin, so the dimension must be
            flagged reduced-confidence there (Req 17.3). Consulted by task 3.2.
        reduced_fields:
            When the dimension is present in the reduced Broad_Corpus profile,
            the raw fields it is derived from there (a subset / substitute of the
            rich fields, Req 4.3). Empty when the dimension is rich-only.
    """

    name: str
    side: str
    requirement: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    unavailable_fields: tuple[str, ...] = ()
    available_in: tuple[str, ...] = (RICH_CORPUS,)
    thin_in_leagues: tuple[str, ...] = ()
    reduced_fields: tuple[str, ...] = ()

    @property
    def in_reduced_profile(self) -> bool:
        """True if this dimension is buildable in the Broad_Corpus reduced profile."""
        return BROAD_CORPUS in self.available_in

    def source_fields(self, *, corpus: str = RICH_CORPUS) -> tuple[str, ...]:
        """All source fields (required + optional) for the given corpus.

        For the reduced (broad) profile this returns ``reduced_fields``; for the
        rich profile it returns required + optional fields in declared order.
        """
        if corpus == BROAD_CORPUS:
            return self.reduced_fields
        return tuple(self.required_fields) + tuple(self.optional_fields)

    def requires(self, raw_field: str) -> bool:
        """True if ``raw_field`` is a *required* source field for this dimension."""
        return raw_field in self.required_fields

    def is_reduced_confidence_in(self, league: str) -> bool:
        """True if this dimension must be flagged reduced-confidence for ``league`` (Req 17.3)."""
        return league in self.thin_in_leagues


# --- Five named attacking dimensions (Req 1.6-1.10) ------------------------

ATTACKING_DIMENSIONS: dict[str, DimensionSpec] = {
    "width": DimensionSpec(
        name="width",
        side="attacking",
        requirement="1.6",
        # accurate crosses, wide entries, corners won (Req 1.6)
        required_fields=("accurate_crosses", "wide_entries", "corners_won"),
        # Reduced profile derives width from corners alone (Req 4.3).
        available_in=(RICH_CORPUS, BROAD_CORPUS),
        reduced_fields=("corners_won",),
    ),
    "central_penetration": DimensionSpec(
        name="central_penetration",
        side="attacking",
        requirement="1.7",
        # touches in penalty area, final-third entries, shots inside box (Req 1.7)
        required_fields=(
            "touches_in_penalty_area",
            "final_third_entries",
            "shots_inside_box",
        ),
        # touches_in_penalty_area is Championship-thin (~5%) -> reduced-confidence
        # for that league (Req 17.3). Rich-only (needs rich fields).
        available_in=(RICH_CORPUS,),
        thin_in_leagues=(CHAMPIONSHIP,),
    ),
    "volume_vs_quality": DimensionSpec(
        name="volume_vs_quality",
        side="attacking",
        requirement="1.8",
        # total shots, shots on target, big chances, npxG per shot (Req 1.8)
        required_fields=(
            "total_shots",
            "shots_on_target",
            "big_chances",
            "npxg_per_shot",
        ),
        available_in=(RICH_CORPUS,),
    ),
    "set_piece_reliance": DimensionSpec(
        name="set_piece_reliance",
        side="attacking",
        requirement="1.9",
        # corners won, fouls won in advanced areas (Req 1.9)
        required_fields=("corners_won", "fouls_won_advanced"),
        available_in=(RICH_CORPUS,),
    ),
    "directness": DimensionSpec(
        name="directness",
        side="attacking",
        requirement="1.10",
        # attacks vs dangerous-attacks ratio, long balls (Req 1.10)
        required_fields=("attacks", "dangerous_attacks", "long_balls"),
        # Reduced profile derives directness from the attacks-vs-dangerous-attacks
        # ratio (Req 4.3); long balls are a rich-only enrichment.
        available_in=(RICH_CORPUS, BROAD_CORPUS),
        reduced_fields=("attacks", "dangerous_attacks"),
    ),
}


# --- Five named defensive dimensions (Req 1.11-1.15) -----------------------

DEFENSIVE_DIMENSIONS: dict[str, DimensionSpec] = {
    "block_orientation": DimensionSpec(
        name="block_orientation",
        side="defensive",
        requirement="1.11",
        # clearances, interceptions, tackles (Req 1.11)
        required_fields=("clearances", "interceptions", "tackles"),
        available_in=(RICH_CORPUS,),
    ),
    "aerial_vs_ground": DimensionSpec(
        name="aerial_vs_ground",
        side="defensive",
        requirement="1.12",
        # aerial duel %, ground duel % (Req 1.12)
        required_fields=("aerial_duel_pct", "ground_duel_pct"),
        available_in=(RICH_CORPUS,),
    ),
    "shot_suppression": DimensionSpec(
        name="shot_suppression",
        side="defensive",
        requirement="1.13",
        # shots conceded inside box, outside box, blocked shots (Req 1.13)
        required_fields=(
            "shots_conceded_inside_box",
            "shots_conceded_outside_box",
            "blocked_shots",
        ),
        available_in=(RICH_CORPUS,),
    ),
    "gk_contribution": DimensionSpec(
        name="gk_contribution",
        side="defensive",
        requirement="1.14",
        # Built from saves (required). high_claims enriches where present.
        # goals_prevented is declared optional AND unavailable: the coverage
        # audit found it zero-populated across the Rich_Corpus leagues, so the
        # dimension MUST be buildable from saves alone (Req 17.1, 17.2).
        required_fields=("saves",),
        optional_fields=("high_claims", "goals_prevented"),
        unavailable_fields=("goals_prevented",),
        available_in=(RICH_CORPUS,),
    ),
    "discipline": DimensionSpec(
        name="discipline",
        side="defensive",
        requirement="1.15",
        # fouls conceded, tackle success, cards (Req 1.15)
        required_fields=("fouls_conceded", "tackle_success", "cards"),
        # Reduced profile derives discipline from fouls and cards (Req 4.3);
        # tackle_success is a rich-only enrichment.
        available_in=(RICH_CORPUS, BROAD_CORPUS),
        reduced_fields=("fouls_conceded", "cards"),
    ),
}


# --- Combined view ----------------------------------------------------------

ALL_DIMENSIONS: dict[str, DimensionSpec] = {
    **ATTACKING_DIMENSIONS,
    **DEFENSIVE_DIMENSIONS,
}


# --- Reduced-profile map for the Broad_Corpus (Req 4.3) ---------------------
#
# Only the dimensions buildable from FootyStats core fields survive into the
# reduced profile: width (from corners), directness (from the
# attacks-vs-dangerous-attacks ratio), and discipline (from fouls and cards).
# Every other named dimension requires rich-only fields and is therefore ABSENT
# from the reduced profile.

REDUCED_PROFILE_DIMENSIONS: dict[str, DimensionSpec] = {
    name: spec for name, spec in ALL_DIMENSIONS.items() if spec.in_reduced_profile
}

# Names of dimensions deliberately absent from the reduced profile because they
# require rich-only fields (Req 4.3). Useful for reporting the rich-vs-broad gap.
RICH_ONLY_DIMENSIONS: tuple[str, ...] = tuple(
    name for name, spec in ALL_DIMENSIONS.items() if not spec.in_reduced_profile
)


# --- Reduced-confidence annotations (Req 17.3) ------------------------------
#
# The set of (league, dimension) pairs that task 3.2 must flag as
# reduced-confidence. Derived from each spec's ``thin_in_leagues`` so there is a
# single source of truth. Currently only (Championship, central_penetration)
# because touches_in_penalty_area is thin (~5%) in the Championship.

REDUCED_CONFIDENCE_FLAGS: frozenset[tuple[str, str]] = frozenset(
    (league, spec.name)
    for spec in ALL_DIMENSIONS.values()
    for league in spec.thin_in_leagues
)


# --- Helpers (declarative lookups consumed by task 3.2) ---------------------


def get_dimension(name: str) -> DimensionSpec:
    """Return the :class:`DimensionSpec` for ``name`` (attacking or defensive)."""
    return ALL_DIMENSIONS[name]


def required_source_fields(name: str) -> tuple[str, ...]:
    """Required raw source fields for a dimension (must be present to build it)."""
    return ALL_DIMENSIONS[name].required_fields


def optional_source_fields(name: str) -> tuple[str, ...]:
    """Optional raw source fields for a dimension (enrich but are not required)."""
    return ALL_DIMENSIONS[name].optional_fields


def source_fields(name: str, *, corpus: str = RICH_CORPUS) -> tuple[str, ...]:
    """All source fields for a dimension in the given corpus (Req 4.3)."""
    return ALL_DIMENSIONS[name].source_fields(corpus=corpus)


def is_reduced_confidence(league: str, dimension: str) -> bool:
    """True if ``(league, dimension)`` must be flagged reduced-confidence (Req 17.3)."""
    return (league, dimension) in REDUCED_CONFIDENCE_FLAGS


def requires_goals_prevented() -> bool:
    """Audit invariant: gk_contribution MUST NOT require goals_prevented (Req 17.1).

    Provided as an explicit, testable statement of the audit-grounded
    constraint. Returns ``False`` because ``goals_prevented`` is declared
    optional (and unavailable), never required.
    """
    return "goals_prevented" in DEFENSIVE_DIMENSIONS["gk_contribution"].required_fields
