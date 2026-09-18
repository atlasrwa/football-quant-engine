"""V8C hypothesis grammar (`v8c_grammar_v1`). See V8C_HYPOTHESIS_GRAMMAR_SPEC.md.

Repairs P1 UNIVERSE-GRAMMAR and P1 RESEARCH-FAMILY.

V8B.1's `search._candidate_shapes` was described as the admissible universe but emitted only
`window == ALL_PRIOR` and conditions of arity 0 or 1 -- roughly a tenth of what the ontology
declares and the compiler executes. This module states the intended V8C grammar EXPLICITLY:

    (target_metric, subject, perspective, comparator, window, conditions)

    metrics      24 contract-covered (np_xg excluded upstream)
    subjects      2   HOME_TEAM / AWAY_TEAM
    perspectives  2   FOR / AGAINST
    comparators  10   every one ontology.COMPARATOR_BINDINGS declares
    windows       3   ALL_PRIOR / W5 / W10          <- restored
    conditions   76   1 unconditioned + 21 single + 54 preregistered two-condition
                      interactions (36 venue x profile, 18 competition x profile)

    = 218,880 enumerated shapes, 189,816 structurally valid.

Single-target-metric is PRESERVED: a multi-metric hypothesis has no single `observed` value,
so admitting one would change the estimand under cover of a grammar change.

ZERO SPEND. Reads no corpus row and no target outcome -- this module is pure grammar.
"""
from __future__ import annotations

import itertools

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v71 import ontology as O

GRAMMAR_VERSION = "v8c_grammar_v1"

#: Unchanged from `execution.PROFILE_AXES`.
PROFILE_AXES = ("goals_for", "goals_against", "shots_on_target_for",
                "shots_on_target_against", "possession_for", "shots_against")

#: Restored. `compiler._select` implements all three.
WINDOWS = ("ALL_PRIOR", "W5", "W10")

SUBJECTS = ("HOME_TEAM", "AWAY_TEAM")
PERSPECTIVES = ("FOR", "AGAINST")

#: The two-condition interaction families are PREREGISTERED and CLOSED (spec section 2.6).
INTERACTION_FAMILIES = ("venue_x_opponent_profile", "competition_x_opponent_profile")


def condition_shapes() -> list:
    """The 76 declared condition shapes, in a fixed deterministic order.

    Arity 0 and 1 reproduce V8B.1's set exactly. Arity 2 adds ONLY the two preregistered
    interaction families. Nothing here invents a dimension or a value the ontology does not
    declare -- `TARGET_VENUE`/`TARGET_VENUE_OPPONENT` are implemented by the compiler but NOT
    declared by `ontology.FILTER_DIMENSIONS`, so they are out of the grammar (P2-GRAMMAR-
    TARGETVENUE, logged in the spec).
    """
    venues = tuple(O.FILTER_DIMENSIONS["historical_venue_conditioning"]["values"])
    bands = tuple(O.FILTER_DIMENSIONS["opponent_profile"]["values"])
    comps = tuple(O.FILTER_DIMENSIONS["competition"]["values"])

    out = [[]]
    for v in venues:
        out.append([{"dimension": "historical_venue_conditioning", "value": v}])
    for axis in PROFILE_AXES:
        for band in bands:
            out.append([{"dimension": "opponent_profile", "value": band, "axis": axis}])
    for cv in comps:
        out.append([{"dimension": "competition", "value": cv}])

    # --- preregistered interaction 1: venue x opponent_profile (2 x 18 = 36) --------------
    for v in venues:
        for axis in PROFILE_AXES:
            for band in bands:
                out.append([{"dimension": "historical_venue_conditioning", "value": v},
                            {"dimension": "opponent_profile", "value": band, "axis": axis}])
    # --- preregistered interaction 2: competition x opponent_profile (1 x 18 = 18) --------
    for cv in comps:
        for axis in PROFILE_AXES:
            for band in bands:
                out.append([{"dimension": "competition", "value": cv},
                            {"dimension": "opponent_profile", "value": band, "axis": axis}])
    return out


CONDITION_SHAPES = condition_shapes()


# ---- research family: a deterministic STRUCTURAL map (P1 RESEARCH-FAMILY) ----------------
_SHOT_CHANCE = frozenset({"shots", "shots_on_target", "shots_off_target", "shots_inside_box",
                          "shots_outside_box", "blocked_shots", "big_chances", "xg",
                          "final_third_entries", "goals", "saves"})
_SET_PIECE = frozenset({"corner_kicks", "accurate_crosses"})
_DISCIPLINE = frozenset({"yellow_cards", "red_cards", "cards_2h", "fouls"})
_POSSESSION = frozenset({"possession", "touches_in_penalty_area", "ball_recoveries"})
_DEFENSIVE_ACTION = frozenset({"tackles", "interceptions", "clearances"})


def research_family(metric: str, perspective: str, comparator: str, window: str) -> str:
    """Total, deterministic, prose-free. Rules apply in this FIXED order, first match wins.

    No Sonnet output can influence this -- confounder/multiplicity treatment must be a
    property of the hypothesis's structure, never of how a model described it.
    """
    if comparator == "SIMILAR_OPPONENT_COHORT":
        return "MATCHUP_SIMILARITY"
    if comparator == "LEAGUE_ENVIRONMENT_BASELINE":
        return "ENVIRONMENT"
    if comparator in ("SUBJECT_VS_FIXTURE_OPPONENT", "OPPONENT_OVERALL_BASELINE",
                      "OPPONENT_VENUE_BASELINE"):
        return "CROSS_ENTITY"
    if comparator == "SUBJECT_RECENT_VS_LONG_BASELINE" or window != "ALL_PRIOR":
        return "FORM_VS_BASELINE"
    if metric in _SET_PIECE:
        return "SET_PIECE_GENERATION"
    if metric in _DISCIPLINE:
        return "DISCIPLINE"
    if metric in _POSSESSION:
        return "POSSESSION_CONTROL"
    if metric in _DEFENSIVE_ACTION:
        return "DEFENSIVE_ACTION"
    if metric in _SHOT_CHANCE:
        return "DEFENSIVE_CONCESSION" if perspective == "AGAINST" else "ATTACK_VOLUME"
    return "OTHER_STRUCTURAL"


RESEARCH_FAMILIES = ("MATCHUP_SIMILARITY", "ENVIRONMENT", "CROSS_ENTITY", "FORM_VS_BASELINE",
                     "SET_PIECE_GENERATION", "DISCIPLINE", "POSSESSION_CONTROL",
                     "DEFENSIVE_ACTION", "DEFENSIVE_CONCESSION", "ATTACK_VOLUME",
                     "OTHER_STRUCTURAL")


def covered_metrics(capability) -> list:
    """Metrics the capability contract covers anywhere in the corpus, sorted. The per-fixture
    COMPADM gate (target competition must be admissible) is applied later, by `pre_t`."""
    return sorted(m for m in CAP.METRIC_SEMANTICS
                  if capability.classify_metric(m)[0] in (CAP.SUPPORTED, CAP.RESTRICTED))


def candidate_specs(capability, *, metrics=None, windows=WINDOWS,
                    condition_set=None):
    """Yield every grammar spec, deterministically. Iteration is over SORTED inputs only.

    Keyword arguments exist for tests and for the synthetic golden environment; the default
    call is the full declared grammar.
    """
    metrics = list(metrics) if metrics is not None else covered_metrics(capability)
    conds = condition_set if condition_set is not None else CONDITION_SHAPES
    comparators = sorted(O.COMPARATOR_BINDINGS)
    for metric, subj, side, comp, window, cond in itertools.product(
            metrics, SUBJECTS, PERSPECTIVES, comparators, windows, conds):
        binding = O.COMPARATOR_BINDINGS[comp]
        caps = ()
        if any(c.get("dimension") == "opponent_profile" for c in cond) or \
                binding.get("requires_similarity"):
            caps = ("opponent_profile",)
        yield {"target_metrics": [metric], "subject": subj, "side": side,
               "comparison": comp, "window": window, "conditions": cond,
               "research_family": research_family(metric, side, comp, window),
               "required_capabilities": caps}


def build_valid_irs(capability, **kw):
    """(spec, ir) for every spec whose IR builds OK. Invariant checking happens downstream in
    the pre-T classifier, which reports the violation codes as PRE_T_COMPILER_INVALID."""
    for spec in candidate_specs(capability, **kw):
        ir = IRM.build_ir(spec)
        if ir.status == IRM.OK:
            yield spec, ir


def resolve(hypothesis_id: str, capability, **kw):
    """Canonical id -> IR, by re-walking the SAME grammar. Used to validate that a submitted
    id corresponds to a real candidate rather than a free-floating string."""
    for _spec, ir in build_valid_irs(capability, **kw):
        if ir.ir_id() == hypothesis_id:
            return ir
    return None


def grammar_size(capability, **kw) -> dict:
    """Declared sizes, computed rather than stated."""
    metrics = kw.get("metrics") or covered_metrics(capability)
    windows = kw.get("windows", WINDOWS)
    conds = kw.get("condition_set") or CONDITION_SHAPES
    return {"n_metrics": len(metrics), "n_subjects": len(SUBJECTS),
            "n_perspectives": len(PERSPECTIVES),
            "n_comparators": len(O.COMPARATOR_BINDINGS), "n_windows": len(windows),
            "n_condition_shapes": len(conds),
            "n_condition_shapes_by_arity": {
                "0": sum(1 for c in conds if len(c) == 0),
                "1": sum(1 for c in conds if len(c) == 1),
                "2": sum(1 for c in conds if len(c) == 2)},
            "n_enumerated_shapes": (len(metrics) * len(SUBJECTS) * len(PERSPECTIVES)
                                    * len(O.COMPARATOR_BINDINGS) * len(windows) * len(conds))}


def version_stamp() -> dict:
    return {"grammar_version": GRAMMAR_VERSION,
            "repairs": ["P1-UNIVERSE-GRAMMAR", "P1-RESEARCH-FAMILY"],
            "successor_to": "v8b1_search_v1 (_candidate_shapes, NOT modified)",
            "windows": list(WINDOWS),
            "windows_restored_vs_v8b1": ["W5", "W10"],
            "n_condition_shapes": len(CONDITION_SHAPES),
            "condition_arities": sorted({len(c) for c in CONDITION_SHAPES}),
            "interaction_families": list(INTERACTION_FAMILIES),
            "interaction_set_is_preregistered_and_closed": True,
            "single_target_metric": True,
            "multi_target_rejected_reason": ("a multi-metric hypothesis has no single observed "
                                             "value; admitting one would change the estimand"),
            "research_families": list(RESEARCH_FAMILIES),
            "research_family_source": "structural map over (metric, perspective, comparator, "
                                      "window); never LLM prose",
            "target_venue_values_excluded": True,
            "target_venue_exclusion_reason": ("compiler implements TARGET_VENUE/"
                                              "TARGET_VENUE_OPPONENT but ontology."
                                              "FILTER_DIMENSIONS does not declare them "
                                              "(P2-GRAMMAR-TARGETVENUE)"),
            "reads_corpus": False, "reads_target_outcome": False}
