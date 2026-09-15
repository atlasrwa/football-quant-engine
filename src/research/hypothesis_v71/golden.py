"""V7.1 golden semantic corpus (`v71_golden_v1`). Section 7.

A representative corpus of the football hypothesis grammar. Each entry states the intended
human-readable meaning, the structured hypothesis that expresses it, and what the pipeline
MUST do with it. The round-trip suite asserts

    intended meaning -> structured spec -> canonical IR -> compiled selectors
                     -> reconstructed meaning  ==  intended meaning

Every entry is hand-written from the football question, never from what the code happens to
produce. Entries whose `expect_codes` is non-empty are NEGATIVE controls: they prove the
suite can fail, and they include the exact bug class that invalidated most of V7.

No entry contains an effect, a direction, or an outcome.
"""
from __future__ import annotations

GOLDEN_VERSION = "v71_golden_v1"


def _h(**kw):
    base = {"target_metrics": [], "subject": "HOME_TEAM", "side": "FOR",
            "comparison": "SUBJECT_OVERALL_BASELINE", "conditions": [],
            "window": "ALL_PRIOR", "research_family": "ATTACK_VOLUME",
            "required_capabilities": []}
    base.update(kw)
    return base


#: Each case: name, meaning, spec, expect_status, expect_codes, must_say, must_not_say.
#: `must_say` are substrings the RECONSTRUCTED meaning must contain; `must_not_say` are
#: substrings that would indicate the reconstruction lost the football question.
GOLDEN_CASES = [
    # ---- the V7 bug class, as an explicit negative control ---------------------------
    dict(name="degenerate_subject_vs_itself",
         meaning=("A question with no restriction and no window: the subject's all-prior "
                  "mean compared with the subject's all-prior mean. There is no contrast."),
         spec=_h(target_metrics=["total_shots"]),
         expect_status="OK",
         expect_codes=["IDENTICAL_COHORT_BASELINE", "SELF_COMPARISON"],
         must_say=[], must_not_say=[]),
    dict(name="degenerate_masked_by_ANY_condition",
         meaning=("The same non-question, but carrying a `competition: ANY` condition. ANY is "
                  "not a restriction, so this must be caught by the SAME invariant and must "
                  "not be mistaken for a conditioned hypothesis."),
         spec=_h(target_metrics=["total_shots"],
                 conditions=[{"dimension": "competition", "value": "ANY"}]),
         expect_status="OK",
         expect_codes=["IDENTICAL_COHORT_BASELINE", "SELF_COMPARISON"],
         must_say=[], must_not_say=[]),
    dict(name="venue_baseline_absorbs_venue_condition",
         meaning=("The subject's home matches compared against the subject's home baseline. "
                  "The baseline already contains the restriction, so the contrast collapses."),
         spec=_h(target_metrics=["corners"], comparison="SUBJECT_VENUE_BASELINE",
                 conditions=[{"dimension": "historical_venue_conditioning",
                              "value": "HOME"}],
                 research_family="SET_PIECE_GENERATION"),
         expect_status="OK", expect_codes=["BASELINE_ABSORPTION"],
         must_say=[], must_not_say=[]),

    # ---- core contrastful grammar ----------------------------------------------------
    dict(name="shots_vs_high_possession_opponents",
         meaning=("Does the subject concede more shots when the opponent is a high-possession "
                  "side, compared with the subject's overall concession baseline?"),
         spec=_h(target_metrics=["total_shots"], side="AGAINST",
                 comparison="SUBJECT_OVERALL_BASELINE",
                 conditions=[{"dimension": "opponent_profile", "axis": "possession_for",
                              "value": "HIGH"}],
                 research_family="DEFENSIVE_CONCESSION",
                 required_capabilities=["opponent_profile"]),
         expect_status="OK", expect_codes=[],
         must_say=["the subject's concession",
                   "the opponent was in the HIGH tercile of possession_for",
                   "differ from the subject's concession, over all prior matches"],
         must_not_say=["the fixture opponent's"]),
    dict(name="shots_on_target_recent_form",
         meaning=("Is the subject's recent shots-on-target production different from its "
                  "long-run production over the same prior matches?"),
         spec=_h(target_metrics=["shots_on_target"],
                 comparison="SUBJECT_RECENT_VS_LONG_BASELINE",
                 research_family="FORM_VS_BASELINE"),
         expect_status="OK", expect_codes=[],
         must_say=["weighted toward recent matches"], must_not_say=[]),
    dict(name="blocked_shots_last_five",
         meaning=("Does the subject's blocked-shots rate over its last five matches differ "
                  "from its all-prior rate?"),
         spec=_h(target_metrics=["blocked_shots"], window="W5",
                 research_family="DEFENSIVE_SUPPRESSION"),
         expect_status="OK", expect_codes=[],
         must_say=["over its last 5 prior matches", "over all prior matches"],
         must_not_say=[]),
    dict(name="corners_away_only",
         meaning="Does the subject win more corners away than at its target venue baseline?",
         spec=_h(target_metrics=["corners"], comparison="SUBJECT_VENUE_BASELINE",
                 conditions=[{"dimension": "opponent_profile", "axis": "goals_against",
                              "value": "HIGH"}],
                 research_family="SET_PIECE_GENERATION",
                 required_capabilities=["opponent_profile"]),
         expect_status="OK", expect_codes=[],
         must_say=["the opponent was in the HIGH tercile of goals_against"],
         must_not_say=[]),
    dict(name="accurate_crosses_same_competition",
         meaning=("Does the subject complete more crosses inside the target competition than "
                  "across all competitions?"),
         spec=_h(target_metrics=["accurate_crosses"],
                 comparison="SUBJECT_COMPETITION_BASELINE",
                 conditions=[{"dimension": "competition", "value": "SAME"}],
                 research_family="TEMPO_AND_TERRITORY"),
         expect_status="OK", expect_codes=[],
         must_say=["the match was in the same competition as the target fixture"],
         must_not_say=[]),
    dict(name="possession_vs_league_environment",
         meaning=("Does the subject hold more possession than the competition-season "
                  "environment mean?"),
         spec=_h(target_metrics=["possession"],
                 comparison="LEAGUE_ENVIRONMENT_BASELINE",
                 research_family="TEMPO_AND_TERRITORY"),
         expect_status="OK", expect_codes=[],
         must_say=["the competition environment's production"], must_not_say=[]),
    dict(name="cards_conditional_vs_complement",
         meaning=("Does the subject collect more yellow cards against high-fouling opponents "
                  "than when that condition does NOT hold?"),
         spec=_h(target_metrics=["yellow_cards"],
                 comparison="SUBJECT_CONDITIONAL_VS_BASELINE",
                 conditions=[{"dimension": "opponent_profile", "axis": "goals_for",
                              "value": "HIGH"}],
                 research_family="DISCIPLINE",
                 required_capabilities=["opponent_profile"]),
         expect_status="OK", expect_codes=[],
         must_say=["excluding matches where"], must_not_say=[]),
    dict(name="tackles_vs_similar_opponents",
         meaning=("Does the subject make more tackles against opponents deterministically "
                  "similar to the fixture opponent than against the rest?"),
         spec=_h(target_metrics=["tackles"], comparison="SIMILAR_OPPONENT_COHORT",
                 research_family="OPPONENT_PROFILE_INTERACTION",
                 required_capabilities=["opponent_profile", "similar_opponents"]),
         expect_status="OK", expect_codes=[],
         must_say=["against opponents similar to the fixture opponent",
                   "against opponents NOT similar to the fixture opponent"],
         must_not_say=[]),
    dict(name="fouls_opponent_baseline",
         meaning=("Does the fixture opponent commit more fouls under a condition than in its "
                  "own overall baseline?"),
         spec=_h(target_metrics=["fouls"], comparison="OPPONENT_OVERALL_BASELINE",
                 conditions=[{"dimension": "historical_venue_conditioning", "value": "AWAY"}],
                 research_family="DISCIPLINE"),
         expect_status="OK", expect_codes=[],
         must_say=["the fixture opponent's production"], must_not_say=["the subject's"]),

    # ---- the comparator V6.1's schema could not express ------------------------------
    dict(name="cross_entity_subject_vs_opponent",
         meaning=("Does the subject concede more shots than the team it actually faces "
                  "concedes? This is a CROSS-ENTITY question; V6.1's schema had no token for "
                  "it, so such questions arrived labelled SUBJECT_OVERALL_BASELINE with the "
                  "real meaning left in prose."),
         spec=_h(target_metrics=["total_shots"], side="AGAINST",
                 comparison="SUBJECT_VS_FIXTURE_OPPONENT",
                 research_family="DEFENSIVE_CONCESSION"),
         expect_status="OK", expect_codes=[],
         must_say=["the subject's concession", "the fixture opponent's concession"],
         must_not_say=[]),

    # ---- perspective / role sensitivity ----------------------------------------------
    dict(name="attacking_profile_interaction",
         meaning=("Does the subject's shot production change against opponents with a weak "
                  "defensive profile?"),
         spec=_h(target_metrics=["shots_on_target"], side="FOR",
                 conditions=[{"dimension": "opponent_profile",
                              "axis": "shots_on_target_against", "value": "HIGH"}],
                 research_family="OPPONENT_PROFILE_INTERACTION",
                 required_capabilities=["opponent_profile"]),
         expect_status="OK", expect_codes=[],
         must_say=["the subject's production",
                   "the opponent was in the HIGH tercile of shots_on_target_against"],
         must_not_say=["concession"]),
    dict(name="defensive_profile_interaction",
         meaning=("Does the subject's concession change against opponents with a strong "
                  "attacking profile? Same axis family as the previous case but the "
                  "PERSPECTIVE is inverted, so it must be a different question."),
         spec=_h(target_metrics=["shots_on_target"], side="AGAINST",
                 conditions=[{"dimension": "opponent_profile",
                              "axis": "shots_on_target_for", "value": "HIGH"}],
                 research_family="DEFENSIVE_CONCESSION",
                 required_capabilities=["opponent_profile"]),
         expect_status="OK", expect_codes=[],
         must_say=["the subject's concession"], must_not_say=["the subject's production"]),

    # ---- provider-safety / resolution negative controls -------------------------------
    dict(name="xg_is_provider_safe_but_restricted",
         meaning=("An xG question. xG is contracted and audited, but is not covered in every "
                  "competition, so it must compile to a RESTRICTED universe, never be "
                  "silently measured on all six."),
         spec=_h(target_metrics=["xg"], comparison="SUBJECT_RECENT_VS_LONG_BASELINE",
                 research_family="ATTACK_QUALITY", required_capabilities=["xg"]),
         expect_status="OK", expect_codes=[],
         expect_capability="RESTRICTED",
         must_say=[], must_not_say=[]),
    dict(name="formation_condition_is_unsupported",
         meaning=("A formation-conditioned question. Formation is not resolvable per prior "
                  "match in this corpus, so the hypothesis must fail CLOSED with a named "
                  "capability gap -- never compile to an empty cohort."),
         spec=_h(target_metrics=["total_shots"],
                 conditions=[{"dimension": "opponent_formation_family",
                              "value": "BACK_FOUR"}],
                 required_capabilities=["formation_recorded_history"]),
         expect_status="UNSUPPORTED_FILTER_DIMENSION",
         expect_codes=["UNSUPPORTED_FILTER_DIMENSION"], must_say=[], must_not_say=[]),
    dict(name="half_level_state_requires_half_resolution",
         meaning=("A trailing-at-half-time style question. The corpus resolves only 2nd-half "
                  "cards at half level, so a half-resolution request for a match-level metric "
                  "must be refused rather than answered with match aggregates."),
         spec=_h(target_metrics=["total_shots"], research_family="ATTACK_VOLUME"),
         temporal_resolution="HALF",
         expect_status="OK",
         expect_codes=["IDENTICAL_COHORT_BASELINE", "SELF_COMPARISON",
                       "TEMPORAL_RESOLUTION_UNSUPPORTED"],
         expect_half_resolution_refused=True, must_say=[], must_not_say=[]),
    dict(name="half_level_metric_answers_half_question",
         meaning=("The positive control for the previous case: 2nd-half cards ARE held at "
                  "half resolution, so a half-level question about them must be allowed. "
                  "Without this case the resolution check could pass by refusing everything."),
         spec=_h(target_metrics=["cards_2h"],
                 comparison="SUBJECT_RECENT_VS_LONG_BASELINE",
                 research_family="DISCIPLINE"),
         temporal_resolution="HALF",
         expect_status="OK", expect_codes=[], must_say=[], must_not_say=[]),
    dict(name="unknown_metric_is_not_unsupported",
         meaning=("A metric this corpus has never characterised. It must be reported as "
                  "UNKNOWN -- a named gap -- not silently treated as unsupported or zero."),
         spec=_h(target_metrics=["progressive_carries"],
                 comparison="SUBJECT_RECENT_VS_LONG_BASELINE"),
         expect_status="OK", expect_codes=["UNKNOWN_PROVIDER_SEMANTICS"],
         expect_capability="UNKNOWN", must_say=[], must_not_say=[]),
    dict(name="ambiguous_cards_metric_must_resolve",
         meaning=("The bare token `cards` is ambiguous between yellow and total. It must be "
                  "refused until it resolves explicitly."),
         spec=_h(target_metrics=["cards"], comparison="SUBJECT_RECENT_VS_LONG_BASELINE",
                 research_family="DISCIPLINE"),
         expect_status="OK", expect_codes=["UNSUPPORTED_METRIC"],
         expect_capability="UNSUPPORTED", must_say=[], must_not_say=[]),
]


def case_names():
    return tuple(c["name"] for c in GOLDEN_CASES)


def version_stamp() -> dict:
    return {"golden_version": GOLDEN_VERSION, "n_cases": len(GOLDEN_CASES),
            "n_negative_controls": sum(1 for c in GOLDEN_CASES if c["expect_codes"]),
            "case_names": list(case_names()),
            "contains_effects": False, "contains_outcomes": False}
