"""football_ontology_v1 — the finite, versioned taxonomy the LLM is confined to.

The LLM may ONLY emit mechanism ids, level enums and confidence enums drawn from this
ontology (brief §14-§16). It may not invent concepts fixture-by-fixture. Each mechanism
declares the evidence *metric families* it is allowed to cite, so the validator can
reject conclusions that cite irrelevant evidence.

This module is the single source of truth; `gen_artifacts` serialises it to ontology.json.
"""
from __future__ import annotations

LEVELS = ["VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH", "UNKNOWN"]
# Directional matchup levels (advantage framing for A-vs-B mechanisms):
ADVANTAGE_LEVELS = [
    "STRONG_B_ADVANTAGE", "B_ADVANTAGE", "NEUTRAL", "A_ADVANTAGE", "STRONG_A_ADVANTAGE",
    "UNKNOWN", "CONFLICTED",
]
CONFIDENCE = ["LOW", "MEDIUM_LOW", "MEDIUM", "MEDIUM_HIGH", "HIGH", "UNKNOWN"]
RELIABILITY = ["LOW", "MEDIUM", "HIGH"]           # evidence-strength descriptor
EVIDENCE_LEVELS = [                                 # which cohort tier was preferred
    "EXACT_OPPONENT", "EXACT_FORMATION", "FORMATION_FAMILY", "TACTICAL_CLUSTER",
    "VENUE_OVERALL", "ALL_VENUES", "COMPETITION_PRIOR", "NONE",
]

# --- Mechanism taxonomy ---------------------------------------------------------
# Each entry: family, direction ('A'|'B'|'MATCH'), level_kind ('level'|'advantage'),
# allowed_metric_prefixes (evidence a conclusion may legitimately cite), markets.
MECHANISMS: dict[str, dict] = {
    # ATTACK (team-state, one per team; direction filled per side at emit time) ----
    "WIDTH_PRESSURE": dict(family="attack", level_kind="level", markets=["corners"],
        allow=["crosses", "throw_ins", "final_third_entries", "possession"],
        desc="Volume/intent of wide territorial pressure (crossing, wide entries)."),
    "TERRITORIAL_PRESSURE": dict(family="attack", level_kind="level", markets=["corners", "goals"],
        allow=["possession", "final_third_entries", "touches_in_box", "attacks", "dangerous_attacks"],
        desc="Sustained territorial dominance / field tilt."),
    "BOX_PRESSURE": dict(family="attack", level_kind="level", markets=["corners", "goals"],
        allow=["touches_in_box", "shots_inside_box", "big_chances", "final_third_entries"],
        desc="Penetration into and activity within the penalty area."),
    "SHOT_VOLUME": dict(family="attack", level_kind="level", markets=["goals", "corners"],
        allow=["total_shots", "shots_on_target", "shots_off_target", "shots_outside_box",
               "shots_inside_box"],
        desc="Raw shot generation (all shot locations)."),
    "SHOT_QUALITY": dict(family="attack", level_kind="level", markets=["goals"],
        allow=["xg", "npxg", "big_chances", "shots_inside_box", "shots_on_target"],
        desc="Quality per shot / chance value (xG, big chances, box shots)."),
    "SET_PIECE_GENERATION": dict(family="attack", level_kind="level", markets=["corners"],
        allow=["corners", "blocked_shots", "crosses", "throw_ins"],
        desc="Tendency to win corners / set-piece territory."),
    "SECOND_HALF_ESCALATION": dict(family="attack", level_kind="level", markets=["corners", "goals"],
        allow=["crosses_2h_shift", "shots_2h_shift", "corners_2h_shift", "possession_2h_shift"],
        desc="Escalation of attacking pressure from 1H to 2H (score-state caveated)."),

    # DEFENSE (team-state) -------------------------------------------------------
    # allow-lists include both the canonical "_allowed" vocabulary and the packet's
    # actual "_against" metric names so Sonnet can cite the real evidence items.
    "SHOT_SUPPRESSION": dict(family="defense", level_kind="level", markets=["goals"],
        allow=["shots_allowed", "sot_allowed", "shots_inside_box_allowed", "xg_allowed", "npxg_allowed",
               "total_shots_against", "shots_on_target_against", "shots_inside_box_against"],
        desc="Ability to limit opponent shot volume/quality."),
    "BOX_PROTECTION": dict(family="defense", level_kind="level", markets=["goals", "corners"],
        allow=["touches_in_box_allowed", "shots_inside_box_allowed", "big_chances_allowed",
               "touches_in_box_against", "shots_inside_box_against"],
        desc="Protection of the penalty area."),
    "CROSS_ALLOWANCE": dict(family="defense", level_kind="level", markets=["corners"],
        allow=["crosses_allowed", "final_third_entries_allowed", "crosses_against",
               "final_third_entries_against"],
        desc="Vulnerability to wide/crossing pressure."),
    "CLEARANCE_DEPENDENCE": dict(family="defense", level_kind="level", markets=["corners"],
        allow=["clearances", "blocked_shots", "interceptions"],
        desc="Reliance on clearances/blocks (a corner-conceding profile)."),
    "CORNER_CONCESSION": dict(family="defense", level_kind="level", markets=["corners"],
        allow=["corners_against", "blocked_shots", "clearances"],
        desc="Rate of conceding corners."),
    "SAVE_ENVIRONMENT": dict(family="defense", level_kind="level", markets=["goals"],
        allow=["saves", "sot_allowed"],
        desc="Goalkeeping shot-stopping load/quality behind goals conceded."),

    # DISCIPLINE -----------------------------------------------------------------
    "CONTACT_INTENSITY": dict(family="discipline", level_kind="level", markets=["cards"],
        allow=["tackles", "fouls", "duels", "interceptions"],
        desc="Physical/contact volume (tackles, fouls, duels)."),
    "FOUL_TENDENCY": dict(family="discipline", level_kind="level", markets=["cards"],
        allow=["fouls", "tackles"],
        desc="Propensity to commit fouls."),
    "BOOKING_CONVERSION": dict(family="discipline", level_kind="level", markets=["cards"],
        allow=["yellow_cards", "red_cards", "fouls", "cards_per_foul"],
        desc="Cards produced per unit of contact (referee-influenced)."),
    "FOUL_DRAWING": dict(family="discipline", level_kind="level", markets=["cards"],
        allow=["fouled_in_final_third", "fouls_drawn"],
        desc="Propensity to draw fouls from the opponent."),

    # MATCH CONTEXT / INTERACTION (direction MATCH) ------------------------------
    "WIDE_PRESSURE_MATCHUP": dict(family="matchup", level_kind="advantage", markets=["corners"],
        allow=["crosses", "crosses_allowed", "clearances", "corners", "corners_against", "throw_ins"],
        desc="A's wide pressure vs B's cross allowance/clearance response (and reverse)."),
    "BOX_PRESSURE_MATCHUP": dict(family="matchup", level_kind="advantage", markets=["goals", "corners"],
        allow=["touches_in_box", "touches_in_box_allowed", "shots_inside_box", "shots_inside_box_allowed",
               "big_chances", "big_chances_allowed"],
        desc="A's box penetration vs B's box protection (and reverse)."),
    "SHOT_CREATION_MATCHUP": dict(family="matchup", level_kind="advantage", markets=["goals"],
        allow=["total_shots", "shots_allowed", "xg", "xg_allowed", "npxg", "npxg_allowed",
               "shots_on_target", "sot_allowed", "saves", "shots_inside_box",
               "shots_inside_box_against"],
        desc="A's chance creation vs B's shot suppression / save environment (and reverse)."),
    "CORNER_MECHANISM_MATCHUP": dict(family="matchup", level_kind="advantage", markets=["corners"],
        allow=["corners", "corners_against", "crosses", "crosses_allowed", "blocked_shots",
               "clearances", "touches_in_box", "possession"],
        desc="Net expected corner-pressure interaction between the two sides."),
    "CONTACT_MATCHUP": dict(family="matchup", level_kind="advantage", markets=["cards"],
        allow=["tackles", "fouls", "duels", "fouled_in_final_third", "fouls_drawn",
               "yellow_cards", "referee_cards_per_match", "league_cards_env"],
        desc="A contact/foul production vs B foul-drawing, modulated by referee/league (and reverse)."),
    "SECOND_HALF_PRESSURE_SHIFT": dict(family="matchup", level_kind="advantage", markets=["corners", "goals"],
        allow=["crosses_2h_shift", "shots_2h_shift", "corners_2h_shift", "possession_2h_shift"],
        desc="Which side is expected to escalate pressure in 2H (score-state caveated)."),
    "TEMPO_EXPECTATION": dict(family="matchup", level_kind="level", markets=["goals", "corners"],
        allow=["possession", "attacks", "dangerous_attacks", "total_shots", "league_goals_env",
               "league_corners_env"],
        desc="Expected match tempo/openness relative to competition baseline."),

    # FORMATION-CONDITIONED MECHANISMS (football_ontology_v2, brief §27, §28) --------
    # These cite formation-conditioned evidence (formation_value / formation_delta /
    # opponent-formation-conditioned behavior). A formation LABEL is never sufficient on
    # its own; the allowed evidence is always measured behavior under that formation.
    "FORMATION_BEHAVIOR_FIT": dict(family="formation", level_kind="level", markets=["corners", "goals"],
        allow=["fc_crosses", "fc_touches_in_box", "fc_possession", "fc_total_shots",
               "fc_corners", "formation_delta"],
        desc="How the team's measured behavior under its resolved/projected formation "
             "differs from its own baseline (measured, not stereotyped)."),
    "FORMATION_WIDTH_INTERACTION": dict(family="formation", level_kind="advantage", markets=["corners"],
        allow=["fc_crosses", "fmx_crosses", "fmx_crosses_against", "fc_corners",
               "fmx_corners", "fmx_clearances", "formation_delta"],
        desc="A's measured width/crossing under its formation vs B's measured cross "
             "allowance under B's formation / equivalent behavioral profile."),
    "FORMATION_BOX_INTERACTION": dict(family="formation", level_kind="advantage", markets=["corners", "goals"],
        allow=["fc_touches_in_box", "fmx_touches_in_box", "fmx_shots_inside_box_against",
               "fmx_touches_in_box_against", "formation_delta"],
        desc="A's box penetration under its formation vs B's box protection under B's formation."),
    "FORMATION_VS_OPP_DEFENSIVE_PROFILE": dict(family="formation", level_kind="advantage", markets=["corners"],
        allow=["fmx_crosses_against", "fmx_clearances", "fmx_blocked_shots",
               "fmx_corners_against", "fmx_shots_inside_box_against"],
        desc="A's formation-conditioned attack vs B's formation-conditioned defensive/"
             "clearance response (measured cross-formation interaction)."),
    "FORMATION_TRANSITION_STATE": dict(family="formation", level_kind="level", markets=["corners", "goals"],
        allow=["formation_delta", "fc_crosses", "fc_possession", "fc_total_shots",
               "fc_touches_in_box"],
        desc="How current/projected formation differs from the team's baseline formation "
             "family and how measured behavior shifts under that state."),
}

# Context flags the LLM must set honestly (closed-world; UNKNOWN when unsupported) ---
# Phase B two-concept formation model (formation_policy_v1):
#   formation_resolution_status  — is historical RESOLVED formation present in the packet?
#   prematch_formation_status    — is a legitimate PRE-MATCH formation known for the target?
# These are DISTINCT. Historical resolution being available does NOT imply the target
# formation is known before kickoff (brief §2, §43). The legacy `formation_status` flag is
# retained for backward compatibility and mirrors prematch availability.
CONTEXT_FLAGS = {
    "formation_status": ["KNOWN_PIT_SAFE", "FORMATION_UNKNOWN"],
    "formation_resolution_status": ["RESOLVED_AVAILABLE", "RESOLVED_PARTIAL", "RESOLVED_UNAVAILABLE"],
    "prematch_formation_status": ["ANNOUNCED", "PROJECTED", "PREMATCH_UNKNOWN"],
    "injury_status": ["KNOWN_PIT_SAFE", "INJURY_STATUS_UNKNOWN"],
    "neutral_venue": ["TRUE", "FALSE", "UNKNOWN"],
    "score_state_conditioning": ["APPLIED", "UNAVAILABLE"],
    "provider_agreement": ["AGREE", "DISAGREE", "SINGLE_PROVIDER", "UNKNOWN"],
}

UNCERTAINTY_FACTORS = [
    "SMALL_SAMPLE", "SHRUNK_TO_PRIOR", "PROVIDER_DISAGREEMENT", "FORMATION_UNKNOWN",
    "SCORE_STATE_CONFOUND", "COLD_START", "SINGLE_PROVIDER", "WIDE_COHORT_ONLY",
    # Phase B formation-specific factors:
    "EXACT_FORMATION_SPARSE", "FORMATION_FAMILY_ONLY", "OPP_FORMATION_UNKNOWN",
    "PREMATCH_FORMATION_UNKNOWN", "FORMATION_LABEL_UNRELIABLE",
]


def mechanism_ids() -> list[str]:
    return sorted(MECHANISMS.keys())


def allowed_metric_prefixes(mech_id: str) -> list[str]:
    return MECHANISMS[mech_id]["allow"]


def to_dict() -> dict:
    """Serialisable ontology (written to ontology.json, hashed for versioning)."""
    return {
        "version": "football_ontology_v2",
        "levels": LEVELS,
        "advantage_levels": ADVANTAGE_LEVELS,
        "confidence": CONFIDENCE,
        "reliability": RELIABILITY,
        "evidence_levels": EVIDENCE_LEVELS,
        "mechanisms": MECHANISMS,
        "context_flags": CONTEXT_FLAGS,
        "uncertainty_factors": UNCERTAINTY_FACTORS,
    }
