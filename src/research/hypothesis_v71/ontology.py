"""V7.1 frozen football ontology (`v71_ontology_v1`). The vocabulary the IR is built from.

Every token here denotes a FOOTBALL role, perspective or restriction. The ontology is frozen
and outcome-blind: no token encodes an expected direction, an effect size, or anything learned
from data. It exists so that `ir.py` can bind a structured hypothesis to an unambiguous
measurement without ever consulting prose, an LLM, or an outcome.

Design rule that V7 violated: a comparator is NOT a label. It is a pair of fully specified
observation selectors. If the pair cannot be constructed from structural fields alone, the
hypothesis is SEMANTICALLY_AMBIGUOUS and is never measured.
"""
from __future__ import annotations

ONTOLOGY_VERSION = "v71_ontology_v1"

# --- entity roles -----------------------------------------------------------------------
#: Whose observations a selector reads. `SUBJECT` and `FIXTURE_OPPONENT` are the two teams of
#: the target fixture; `COMPETITION_ENVIRONMENT` is the league-season environment mean.
ENTITY_ROLES = ("SUBJECT", "FIXTURE_OPPONENT", "COMPETITION_ENVIRONMENT")

#: Which side of a match statistic a selector reads. `FOR` is the entity's own production,
#: `AGAINST` is what it concedes. Inverting this inverts the football question.
PERSPECTIVES = ("FOR", "AGAINST")

#: How prior observations are weighted inside a selector's window.
WEIGHTINGS = ("UNIFORM", "TIME_DECAY")

#: Temporal extent of the prior observations a selector reads.
WINDOWS = ("ALL_PRIOR", "W5", "W10")

#: The temporal resolution a hypothesis needs from the provider. A hypothesis that needs
#: half-level or event-level resolution may not be answered with match-level aggregates.
TEMPORAL_RESOLUTIONS = ("MATCH", "HALF", "EVENT")

# --- observation filters ----------------------------------------------------------------
#: Restriction dimensions the compiler can honour, with the structural fields each needs.
#: A dimension NOT listed here is unsupported: the hypothesis fails closed rather than
#: silently compiling to an unrestricted or empty cohort (the V7 `_apply_conditions` defect).
FILTER_DIMENSIONS = {
    "historical_venue_conditioning": {
        "values": ("HOME", "AWAY"),
        "means": "restrict the entity's prior matches to those played at that venue",
        "needs": (),
    },
    "opponent_profile": {
        "values": ("HIGH", "MID", "LOW"),
        "means": ("restrict to prior matches whose OPPONENT sat in that PIT tercile of the "
                  "named profile axis, within the opponent's own competition"),
        "needs": ("axis",),
    },
    "competition": {
        "values": ("SAME",),
        "means": ("restrict to prior matches played in the same competition as the target "
                  "fixture"),
        "needs": (),
    },
}

#: Values that express "no restriction". A condition carrying one of these is NOT a condition:
#: it must never make a degenerate comparator look conditioned. V7 counted them as conditions,
#: which let 25 raw hypotheses bypass the degeneracy fast path and vanish as no-support.
NON_RESTRICTIVE_VALUES = (None, "ANY", "ALL")

#: Dimensions the V6.1 schema can emit that this corpus/provider cannot honour. Listed
#: explicitly so the failure is a NAMED capability gap, not an unknown-key fallthrough.
KNOWN_UNSUPPORTED_DIMENSIONS = {
    "opponent_formation_family": "formation is not resolvable per prior match in this corpus",
    "own_formation_family": "formation is not resolvable per prior match in this corpus",
}

# --- comparator -> selector pair --------------------------------------------------------
#: THE central table. Each comparator binds to an explicit (cohort, baseline) selector pair.
#: `cohort_role`/`baseline_role` are entity roles; `*_perspective` is FOR/AGAINST or "SPEC"
#: (inherit the hypothesis' own side); `*_scope` says which filters/window apply.
#:
#: `SPEC_CONDITIONS`  - the hypothesis' own restrictive conditions apply to this selector.
#: `NONE`             - the selector is unrestricted (the entity's full prior history).
#: `VENUE_OF_TARGET`  - restricted to the venue the subject occupies in the target fixture.
#: `SPEC_WINDOW`      - the hypothesis' own window applies; `ALL_PRIOR` pins it open.
COMPARATOR_BINDINGS = {
    "SUBJECT_OVERALL_BASELINE": {
        "cohort": {"role": "SUBJECT", "perspective": "SPEC",
                   "filters": "SPEC_CONDITIONS", "window": "SPEC_WINDOW",
                   "weighting": "UNIFORM"},
        "baseline": {"role": "SUBJECT", "perspective": "SPEC",
                     "filters": "NONE", "window": "ALL_PRIOR", "weighting": "UNIFORM"},
        "reads": ("the subject under its own stated conditions, against the subject's "
                  "unrestricted all-prior mean"),
    },
    "SUBJECT_VENUE_BASELINE": {
        "cohort": {"role": "SUBJECT", "perspective": "SPEC",
                   "filters": "SPEC_CONDITIONS", "window": "SPEC_WINDOW",
                   "weighting": "UNIFORM"},
        "baseline": {"role": "SUBJECT", "perspective": "SPEC",
                     "filters": "VENUE_OF_TARGET", "window": "ALL_PRIOR",
                     "weighting": "UNIFORM"},
        "reads": ("the subject under its own stated conditions, against the subject's mean "
                  "at the venue it occupies in the target fixture"),
    },
    "SUBJECT_COMPETITION_BASELINE": {
        "cohort": {"role": "SUBJECT", "perspective": "SPEC",
                   "filters": "SPEC_CONDITIONS", "window": "SPEC_WINDOW",
                   "weighting": "UNIFORM"},
        "baseline": {"role": "SUBJECT", "perspective": "SPEC",
                     "filters": "NONE", "window": "ALL_PRIOR", "weighting": "UNIFORM"},
        "reads": ("the subject inside the target competition, against its cross-competition "
                  "all-prior mean"),
        "requires_filter": {"dimension": "competition", "value": "SAME"},
    },
    "SUBJECT_RECENT_VS_LONG_BASELINE": {
        "cohort": {"role": "SUBJECT", "perspective": "SPEC",
                   "filters": "SPEC_CONDITIONS", "window": "SPEC_WINDOW",
                   "weighting": "TIME_DECAY"},
        "baseline": {"role": "SUBJECT", "perspective": "SPEC",
                     "filters": "SPEC_CONDITIONS", "window": "SPEC_WINDOW",
                     "weighting": "UNIFORM"},
        "reads": ("the subject's time-decayed recent weighting of a set of prior matches, "
                  "against the un-decayed mean of the SAME matches"),
    },
    "OPPONENT_OVERALL_BASELINE": {
        "cohort": {"role": "FIXTURE_OPPONENT", "perspective": "SPEC",
                   "filters": "SPEC_CONDITIONS", "window": "SPEC_WINDOW",
                   "weighting": "UNIFORM"},
        "baseline": {"role": "FIXTURE_OPPONENT", "perspective": "SPEC",
                     "filters": "NONE", "window": "ALL_PRIOR", "weighting": "UNIFORM"},
        "reads": ("the fixture opponent under the stated conditions, against the opponent's "
                  "unrestricted all-prior mean"),
    },
    "OPPONENT_VENUE_BASELINE": {
        "cohort": {"role": "FIXTURE_OPPONENT", "perspective": "SPEC",
                   "filters": "SPEC_CONDITIONS", "window": "SPEC_WINDOW",
                   "weighting": "UNIFORM"},
        "baseline": {"role": "FIXTURE_OPPONENT", "perspective": "SPEC",
                     "filters": "VENUE_OF_TARGET_OPPONENT", "window": "ALL_PRIOR",
                     "weighting": "UNIFORM"},
        "reads": ("the fixture opponent under the stated conditions, against its mean at the "
                  "venue it occupies in the target fixture"),
    },
    "LEAGUE_ENVIRONMENT_BASELINE": {
        "cohort": {"role": "SUBJECT", "perspective": "SPEC",
                   "filters": "SPEC_CONDITIONS", "window": "SPEC_WINDOW",
                   "weighting": "UNIFORM"},
        "baseline": {"role": "COMPETITION_ENVIRONMENT", "perspective": "SPEC",
                     "filters": "NONE", "window": "ALL_PRIOR", "weighting": "UNIFORM"},
        "reads": ("the subject under the stated conditions, against the competition-season "
                  "environment mean of the same metric"),
    },
    "SIMILAR_OPPONENT_COHORT": {
        "cohort": {"role": "SUBJECT", "perspective": "SPEC",
                   "filters": "SIMILAR_TO_FIXTURE_OPPONENT", "window": "SPEC_WINDOW",
                   "weighting": "UNIFORM"},
        "baseline": {"role": "SUBJECT", "perspective": "SPEC",
                     "filters": "DISSIMILAR_TO_FIXTURE_OPPONENT", "window": "ALL_PRIOR",
                     "weighting": "UNIFORM"},
        "reads": ("the subject against opponents deterministically similar to the fixture "
                  "opponent, versus the subject against the remaining opponents"),
        "requires_similarity": True,
    },
    "SUBJECT_CONDITIONAL_VS_BASELINE": {
        "cohort": {"role": "SUBJECT", "perspective": "SPEC",
                   "filters": "SPEC_CONDITIONS", "window": "SPEC_WINDOW",
                   "weighting": "UNIFORM"},
        "baseline": {"role": "SUBJECT", "perspective": "SPEC",
                     "filters": "COMPLEMENT_OF_SPEC_CONDITIONS", "window": "ALL_PRIOR",
                     "weighting": "UNIFORM"},
        "reads": ("the subject under the stated conditions, against the subject when those "
                  "conditions do NOT hold"),
        "requires_conditions": True,
    },
    # ---- Added in V7.1. V6.1's response schema had NO token for a cross-entity contrast,
    # so questions of the form "does HOME_TEAM generate more shots than AWAY_TEAM?" were
    # emitted as SUBJECT_OVERALL_BASELINE with the real meaning left in prose. The token now
    # exists so a FUTURE generator can express the question; V7.1 does NOT retro-assign it to
    # any already-generated hypothesis (that would be post-hoc reinterpretation).
    "SUBJECT_VS_FIXTURE_OPPONENT": {
        "cohort": {"role": "SUBJECT", "perspective": "SPEC",
                   "filters": "SPEC_CONDITIONS", "window": "SPEC_WINDOW",
                   "weighting": "UNIFORM"},
        "baseline": {"role": "FIXTURE_OPPONENT", "perspective": "SPEC",
                     "filters": "SPEC_CONDITIONS", "window": "SPEC_WINDOW",
                     "weighting": "UNIFORM"},
        "reads": ("the subject's own rate against the corresponding rate of the team it "
                  "actually faces in the target fixture"),
        "added_in": "v7_1",
    },
}

#: Comparators whose cohort and baseline draw on the SAME observation set and differ only in
#: weighting. They are legitimate but must be reported across the whole frozen decay family.
REWEIGHTING_COMPARATORS = ("SUBJECT_RECENT_VS_LONG_BASELINE",)


def version_stamp() -> dict:
    return {"ontology_version": ONTOLOGY_VERSION,
            "entity_roles": list(ENTITY_ROLES),
            "perspectives": list(PERSPECTIVES),
            "windows": list(WINDOWS),
            "weightings": list(WEIGHTINGS),
            "temporal_resolutions": list(TEMPORAL_RESOLUTIONS),
            "filter_dimensions": {k: {"values": list(v["values"]),
                                      "needs": list(v["needs"]),
                                      "means": v["means"]}
                                  for k, v in FILTER_DIMENSIONS.items()},
            "non_restrictive_values": [v for v in NON_RESTRICTIVE_VALUES],
            "known_unsupported_dimensions": dict(KNOWN_UNSUPPORTED_DIMENSIONS),
            "comparators": {k: {"cohort": v["cohort"], "baseline": v["baseline"],
                                "reads": v["reads"]}
                            for k, v in COMPARATOR_BINDINGS.items()},
            "reweighting_comparators": list(REWEIGHTING_COMPARATORS),
            "uses_llm": False, "reads_outcomes": False, "reads_prose": False}
