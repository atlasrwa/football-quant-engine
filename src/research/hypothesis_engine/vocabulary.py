"""Closed vocabularies for the hypothesis layer (`hypothesis_vocabulary_v1`).

Everything the LLM may name is enumerated here. A value outside these enums does not get
approximated or coerced -- it produces a named failure state from `lifecycle`.

Why closed enums rather than free text: the hypothesis has to compile into a deterministic
query plan that reads production research data. A free-text dimension is an injection
surface and an un-auditable research record; an enum is neither.
"""
from __future__ import annotations

from . import capability

VOCABULARY_VERSION = "hypothesis_vocabulary_v1"


# --------------------------------------------------------------------------------------
# Subjects -- who the question is about. Identity-neutral by construction so the same
# vocabulary serves both the real-name and the aliased packet.
# --------------------------------------------------------------------------------------
SUBJECTS = ("HOME_TEAM", "AWAY_TEAM")

#: Legacy/neutral aliases accepted on input and normalized to the canonical subject.
SUBJECT_ALIASES = {
    "TEAM_A": "HOME_TEAM",
    "TEAM_B": "AWAY_TEAM",
    "HOME": "HOME_TEAM",
    "AWAY": "AWAY_TEAM",
}


def canonical_subject(value: str) -> str | None:
    if value in SUBJECTS:
        return value
    return SUBJECT_ALIASES.get(value)


# --------------------------------------------------------------------------------------
# Research families -- what KIND of question this is. Deliberately describes the research
# question, never a market position.
# --------------------------------------------------------------------------------------
RESEARCH_FAMILIES = (
    "ATTACK_VOLUME",
    "ATTACK_QUALITY",
    "SET_PIECE_GENERATION",
    "DEFENSIVE_SUPPRESSION",
    "DEFENSIVE_CONCESSION",
    "DISCIPLINE",
    "TEMPO_AND_TERRITORY",
    "FORMATION_INTERACTION",
    "OPPONENT_PROFILE_INTERACTION",
    "VENUE_EFFECT",
    "COMPETITION_ENVIRONMENT",
    "MATCH_STATE_RESPONSE",
    "FORM_VS_BASELINE",
)


# --------------------------------------------------------------------------------------
# Sides -- the orientation of a metric.
# --------------------------------------------------------------------------------------
SIDES = ("FOR", "AGAINST")


# --------------------------------------------------------------------------------------
# Windows -- which slice of history the cohort is drawn from.
#
# W5/W10 mirror the champion's own rolling windows (pilotC_stat_mixer.WINDOWS) so a
# candidate feature is directly comparable with what the champion already sees.
# --------------------------------------------------------------------------------------
WINDOWS = ("W5", "W10", "SEASON_TO_DATE", "ALL_PRIOR")


# --------------------------------------------------------------------------------------
# Condition dimensions -- what a cohort may be conditioned on.
#
# Each entry declares the context source it needs. The compiler resolves that against
# `capability.CONTEXT_SOURCES` and the fixture manifest, so an unsupported source produces
# UNSUPPORTED_CONTEXT_SOURCE and an unknown dimension produces UNSUPPORTED_DIMENSION --
# two different failures, never silently conflated.
# --------------------------------------------------------------------------------------
VENUE_VALUES = ("HOME", "AWAY", "ANY")

#: Structural formation families. Derived from the back-line count in the recorded
#: formation string, which is the only structurally reliable reading of it.
FORMATION_FAMILIES = ("BACK_THREE", "BACK_FOUR", "BACK_FIVE", "OTHER", "ANY")

#: Opponent-profile bands. The LLM may name a band; the DETERMINISTIC layer decides which
#: historical opponents fall in it by ranking measured pre-fixture features. The LLM never
#: supplies a similarity score -- see `similarity.py`.
PROFILE_BANDS = ("LOW", "MID", "HIGH", "ANY")

#: Which measured axis a profile band applies to. Every axis must be a supported metric.
PROFILE_AXES = (
    "shots_for", "shots_against",
    "shots_on_target_for", "shots_on_target_against",
    "corners_for", "corners_against",
    "possession_for",
    "goals_for", "goals_against",
    "tackles_for", "fouls_for",
    "yellow_cards_for", "total_bookings_for",
    "accurate_crosses_for", "accurate_crosses_against",
)

PERIOD_VALUES = ("ALL", "FIRST_HALF", "SECOND_HALF")

HALF_SCORE_STATES = ("LEADING_AT_HT", "LEVEL_AT_HT", "TRAILING_AT_HT", "ANY")

COMPETITION_VALUES = ("SAME", "ANY")


DIMENSIONS: dict[str, dict] = {
    "venue": {
        "values": VENUE_VALUES,
        "context_source": "venue",
        "desc": "Whether the subject played at home or away in the cohort fixtures.",
    },
    "competition": {
        "values": COMPETITION_VALUES,
        "context_source": "competition",
        "desc": "Restrict the cohort to the upcoming fixture's competition, or any.",
    },
    "own_formation_family": {
        "values": FORMATION_FAMILIES,
        "context_source": "historical_formation",
        "desc": "Structural family of the subject's RECORDED formation in each cohort "
                "fixture. Historical fixture context; needs no announcement timestamp.",
    },
    "opponent_formation_family": {
        "values": FORMATION_FAMILIES,
        "context_source": "historical_formation",
        "desc": "Structural family of the OPPONENT's recorded formation in each cohort "
                "fixture.",
    },
    "opponent_profile": {
        "values": PROFILE_BANDS,
        "axes": PROFILE_AXES,
        "context_source": "competition",
        "desc": "Band of the opponent's measured pre-fixture profile on a named axis. "
                "Bands are computed deterministically from history strictly before each "
                "cohort fixture's kickoff.",
    },
    "period": {
        "values": PERIOD_VALUES,
        "context_source": "competition",
        "desc": "Full match, or a half split where the metric supports one.",
    },
    "half_score_state": {
        "values": HALF_SCORE_STATES,
        "context_source": "half_time_score_state",
        "desc": "The subject's score state at half time in each cohort fixture. Derived "
                "from half-time goals; requires no minute-level event feed.",
    },
    "referee": {
        "values": ("SAME", "ANY"),
        "context_source": "referee",
        "desc": "Restrict to fixtures with the same referee. FootyStats-only.",
    },
}


def dimension(name: str) -> dict | None:
    return DIMENSIONS.get(name)


def is_supported_dimension(name: str) -> bool:
    return name in DIMENSIONS


def dimension_names() -> list[str]:
    return sorted(DIMENSIONS)


# --------------------------------------------------------------------------------------
# Comparisons -- what the conditional cohort is measured AGAINST.
#
# A conditional mean with no baseline is not a research result, so a comparison is
# mandatory. The engine computes both sides; the LLM only names which baseline is the
# meaningful one for its question.
# --------------------------------------------------------------------------------------
COMPARISONS = (
    "SUBJECT_OVERALL_BASELINE",       # subject's own unconditional rate
    "SUBJECT_VENUE_BASELINE",         # subject's own rate at the same venue
    "SUBJECT_COMPETITION_BASELINE",   # subject's own rate in the same competition
    "LEAGUE_ENVIRONMENT_BASELINE",    # competition-wide mean for the metric
    "SUBJECT_RECENT_VS_LONG_BASELINE",  # W5/W10 against ALL_PRIOR: form vs baseline
)


# --------------------------------------------------------------------------------------
# Sufficiency -- the LLM's own declaration about whether the packet supported the question.
# Abstention is a first-class, VALID outcome: §16, "good output is not necessarily more
# hypotheses".
# --------------------------------------------------------------------------------------
SUFFICIENCY = ("SUFFICIENT", "INSUFFICIENT_EVIDENCE")


# --------------------------------------------------------------------------------------
# Priority -- a research-budget scheduling hint ONLY.
#
# This is an ordered label with no arithmetic meaning. It is NOT a confidence, NOT a
# strength, NOT a weight, and it may never be read as a probability or an effect size.
# The firewall enforces that it is one of these three tokens and never a number.
# --------------------------------------------------------------------------------------
PRIORITY = ("LOW", "MEDIUM", "HIGH")


# --------------------------------------------------------------------------------------
# BANNED grading vocabularies (mandate §14).
#
# These are the latent-state labels from the legacy LLM_LATENT_STATE_EXPERIMENT. Their
# presence anywhere in a hypothesis-layer response means the model is grading football
# strength instead of asking a question, which is the exact architectural error this
# package exists to remove. Matching is on VALUES, not just keys, because the grade can
# appear as any field's value.
# --------------------------------------------------------------------------------------
BANNED_LEVEL_GRADES = frozenset({
    "VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH",
    "MEDIUM_LOW", "MEDIUM_HIGH",
})

BANNED_ADVANTAGE_GRADES = frozenset({
    "STRONG_A_ADVANTAGE", "A_ADVANTAGE", "NEUTRAL", "B_ADVANTAGE", "STRONG_B_ADVANTAGE",
    "STRONG_HOME_ADVANTAGE", "HOME_ADVANTAGE", "AWAY_ADVANTAGE", "STRONG_AWAY_ADVANTAGE",
    "SLIGHT_A_ADVANTAGE", "SLIGHT_B_ADVANTAGE",
})

#: Fields where an ordered LOW/MEDIUM/HIGH token is legitimate and carries no football
#: judgement, so the level-grade ban does not apply to them.
GRADE_EXEMPT_FIELDS = frozenset({"priority"})

#: Fields where a PROFILE_BAND token is legitimate (naming a cohort band to measure, not
#: grading a team's strength).
BAND_EXEMPT_PATH_SUFFIXES = ("conditions.value",)


def snapshot() -> dict:
    """Machine-readable vocabulary snapshot, embedded in the prompt and in provenance so a
    stored hypothesis can always be replayed against the vocabulary that produced it."""
    return {
        "vocabulary_version": VOCABULARY_VERSION,
        "capability_inventory_version": capability.CAPABILITY_INVENTORY_VERSION,
        "subjects": list(SUBJECTS),
        "research_families": list(RESEARCH_FAMILIES),
        "sides": list(SIDES),
        "windows": list(WINDOWS),
        "dimensions": {k: {kk: (list(vv) if isinstance(vv, tuple) else vv)
                           for kk, vv in v.items()}
                       for k, v in DIMENSIONS.items()},
        "comparisons": list(COMPARISONS),
        "sufficiency": list(SUFFICIENCY),
        "priority": list(PRIORITY),
        "metrics": capability.metric_names(),
    }
