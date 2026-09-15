"""V7.1 defect ledger (`v71_bugledger_v1`). Sections 24 and 25.

Every defect found while tracing the V6.1 -> measurement path, with its severity, root cause,
which experiment it affected, whether it changes V7's interpretation, the GENERIC fix, and the
regression test that now guards the CLASS rather than the instance.

Severity, per section 24:
  P0  scientific validity / leakage / wrong query / wrong outcome / corruption
  P1  evaluator / denominator / comparator / statistical-unit defect
  P2  provider semantics / provenance / measurability / coverage defect
  P3  reproducibility / lifecycle / freeze / evidence-integrity defect
  P4  maintainability / observability / cosmetic
"""
from __future__ import annotations

BUGLEDGER_VERSION = "v71_bugledger_v1"

DEFECTS = [
    {
        "id": "D1",
        "severity": "P0",
        "title": "The response schema had no token for a cross-entity comparison",
        "root_cause": (
            "V6.1's structured schema offered only subject-relative comparators. Questions of "
            "the form 'does HOME_TEAM concede more than AWAY_TEAM concedes' are CROSS-ENTITY; "
            "the model chose the nearest available token (SUBJECT_OVERALL_BASELINE) and left "
            "the real question in prose, where no deterministic stage could see it."),
        "evidence": "103 of 432 raw hypotheses; 44 of 132 canonical families",
        "affected_experiment": "V6.1 generation, V7 measurement",
        "changes_v7_interpretation": (
            "No. V7's number stands as measured. It reframes WHY: a large part of the attrition "
            "is a schema-expressiveness limit, not a football judgement by the model."),
        "generic_fix": (
            "The ontology gains SUBJECT_VS_FIXTURE_OPPONENT so a future generator can express "
            "the question. V7.1 does NOT retro-assign it to any already-generated hypothesis: "
            "re-reading 132 already-seen questions from prose would be post-hoc "
            "reinterpretation. The affected families fail closed as IDENTICAL_COHORT_BASELINE."),
        "regression_test": ("test_07_the_v7_bug_class_reconstructs_as_a_non_question, "
                            "test_07_cross_entity_comparator_is_expressible_now"),
    },
    {
        "id": "D2",
        "severity": "P1",
        "title": "The compiler implemented two of nine declared comparator semantics",
        "root_cause": (
            "`VALID_COMPARATORS` declared nine (cohort, baseline) semantics, but the executor "
            "branched on SUBJECT_VENUE_BASELINE and SUBJECT_RECENT_VS_LONG_BASELINE only and "
            "fell through to one generic subject-vs-subject contrast for the rest. The "
            "declaration was documentation the code never honoured."),
        "evidence": (
            "LEAGUE_ENVIRONMENT_BASELINE (93 raw hypotheses) would have been measured as a "
            "subject baseline question. LATENT in V7: V6.1's own qualification filter removed "
            "all 93, so no such hypothesis reached the executor."),
        "affected_experiment": "V7 (latent), any successor reusing the executor",
        "changes_v7_interpretation": "No -- the path was never taken in V7.",
        "generic_fix": (
            "A comparator is no longer a label: `ontology.COMPARATOR_BINDINGS` binds each to an "
            "explicit selector PAIR, and the compiler executes the pair. A comparator with no "
            "binding is UNKNOWN_COMPARATOR and fails closed."),
        "regression_test": ("test_08_every_declared_comparator_binds_two_selectors, "
                            "test_08_comparators_produce_distinct_structures, "
                            "test_06_every_comparator_compiles_a_real_contrast"),
    },
    {
        "id": "D3",
        "severity": "P1",
        "title": "A non-restrictive condition value was counted as a condition",
        "root_cause": (
            "`value: ANY` and unsupported dimensions were counted in `len(conditions)`, so a "
            "degenerate hypothesis carrying one bypassed the executor's degeneracy fast path "
            "(which tested `not conditions`) and instead reached `_apply_conditions`."),
        "evidence": "25 raw hypotheses beyond the 78 with literally zero conditions",
        "affected_experiment": "V7",
        "changes_v7_interpretation": (
            "Marginally: those 25 were recorded as no-support rather than as degenerate, so "
            "V7's TAUTOLOGICAL count understated the degeneracy and its UNMEASURABLE count "
            "overstated the data problem."),
        "generic_fix": (
            "`ontology.NON_RESTRICTIVE_VALUES` is frozen and the IR drops such conditions into "
            "`dropped_non_restrictive`, so a comparator's degeneracy is judged on RESTRICTIONS, "
            "never on the length of a list."),
        "regression_test": "test_08_non_restrictive_value_is_not_a_condition",
    },
    {
        "id": "D4",
        "severity": "P1",
        "title": "An unsupported condition dimension compiled to an empty cohort",
        "root_cause": (
            "`_apply_conditions` returned `[]` for any dimension it did not implement "
            "(`competition`, `opponent_formation_family`, `own_formation_family`). Downstream, "
            "an empty cohort is indistinguishable from a hypothesis with genuinely no support, "
            "so a CAPABILITY GAP was recorded as a DATA problem."),
        "evidence": "84 raw hypotheses carried at least one unimplemented dimension",
        "affected_experiment": "V7",
        "changes_v7_interpretation": (
            "It re-labels part of the attrition: some UNMEASURABLE families were really "
            "'the compiler cannot express this restriction'."),
        "generic_fix": (
            "The IR fails closed with UNSUPPORTED_FILTER_DIMENSION and names the dimension; "
            "`ontology.KNOWN_UNSUPPORTED_DIMENSIONS` records why each is unsupported. A filter "
            "that reaches the compiler is guaranteed executable, and an unknown one RAISES."),
        "regression_test": "test_08_unsupported_dimension_fails_closed_not_empty",
    },
    {
        "id": "D5",
        "severity": "P2",
        "title": "The coverage gate discarded metrics it could have measured",
        "root_cause": (
            "The gate required admissibility in all six competitions, while declaring "
            "`restricted_universes_reported: true` and never honouring it. xG is covered at "
            ">=0.99 in four of six competitions and was discarded entirely."),
        "evidence": "79 of 132 canonical families UNMEASURABLE, dominated by xg and "
                    "touches_in_penalty_area",
        "affected_experiment": "V7",
        "changes_v7_interpretation": (
            "No -- V7's gate was frozen and applied as frozen. It explains a large share of "
            "V7's low evaluability."),
        "generic_fix": (
            "`capability.COVERAGE_POLICY` admits a RESTRICTED universe at >=4 of 6 "
            "competitions, the admissible set is frozen and reported with every derived "
            "result, and `n_admissible_competitions` becomes a matching covariate so the "
            "control arm inherits the same measurability opportunity."),
        "regression_test": ("test_08_unsupported_xg_league_is_restricted_not_silently_full, "
                            "test_08_multi_metric_universe_is_the_intersection"),
    },
    {
        "id": "D6",
        "severity": "P1",
        "title": "A constant design column made the adjustment singular at execution time",
        "root_cause": (
            "The frozen confounder plan listed `venue`, but within a fixture the subject's "
            "venue is constant by construction, so the column was constant and the normal "
            "equations were singular. Families terminated CONFOUNDED_UNRESOLVED until the "
            "executor was patched mid-flight."),
        "evidence": "V7 execution log; the fix was applied on the development window",
        "affected_experiment": "V7",
        "changes_v7_interpretation": "No -- the fix preceded any confirmatory effect.",
        "generic_fix": (
            "`confounders.screen_design` screens every column before the solve and drops "
            "constant and collinear columns under NAMED reasons carried into the evidence. "
            "Unavailable and mediator variables are stripped from the plan with their own "
            "reasons rather than silently ignored."),
        "regression_test": "test_13_degenerate_design_columns_are_dropped_with_a_named_reason",
    },
    {
        "id": "D7",
        "severity": "P0",
        "title": "A structurally invalid query produced a zero-valued feature",
        "root_cause": (
            "V7 compiled a degenerate comparator to `signal == 0`, ran a full walk-forward "
            "over it, and classified it TAUTOLOGICAL afterwards. A structural zero entered an "
            "out-of-sample distribution before anything rejected it."),
        "evidence": "37 of 53 measurable V7 families terminated TAUTOLOGICAL",
        "affected_experiment": "V7",
        "changes_v7_interpretation": (
            "No -- the terminal state was correct. It was reached far too late and at the "
            "cost of the endpoint's evaluable sample."),
        "generic_fix": (
            "`invariants.assert_valid` runs before the fold loop and RAISES. In addition, a "
            "comparator that is sound in the IR but COLLAPSES at a particular fixture "
            "(cohort fixtures == baseline fixtures) causes `CompileRefused` at that fixture, "
            "so no structural zero can enter a distribution."),
        "regression_test": ("test_06_invalid_query_raises_before_the_fold_loop, "
                            "test_06_a_comparator_that_collapses_at_one_fixture_is_refused_there"),
    },
    {
        "id": "D8",
        "severity": "P2",
        "title": "A similarity profile with too many missing dimensions was imputed, not excluded",
        "root_cause": (
            "`zvector` imputes a missing dimension to the cohort mean (z = 0) and returns a "
            "missing count, but nothing consumed the count. An imputed profile sits at the "
            "average, which makes a data-poor team look artificially similar to everyone."),
        "evidence": "MAX_MISSING_DIMS was declared in the frozen spec and never enforced",
        "affected_experiment": "V7 (latent: no similarity comparator survived qualification)",
        "changes_v7_interpretation": "No -- the path was never taken in V7.",
        "generic_fix": (
            "`SimilarityEngine` enforces MAX_MISSING_DIMS on both the target and every "
            "candidate, and REFUSES the cohort when the target profile or the neighbour count "
            "is inadequate, rather than returning a k-nearest set built from imputations."),
        "regression_test": "test_11_similarity_refuses_rather_than_imputing",
    },
    {
        "id": "D9",
        "severity": "P3",
        "title": "The V7 apparatus and its evidence were never committed",
        "root_cause": (
            "The whole V7 source tree, test suite and 32 MB of immutable execution evidence "
            "existed only as untracked files in the working tree, alongside the V6.1 "
            "artifacts they depend on."),
        "evidence": "git status at the start of this mission: 0 tracked files under "
                    "src/research/hypothesis_v7, research/hypothesis_oos/out/v7 and "
                    "tests/research/hypothesis_oos",
        "affected_experiment": "V3 through V7",
        "changes_v7_interpretation": "No.",
        "generic_fix": (
            "Two preservation commits before any successor work: the V3-V6.1 lineage, then "
            "V7's apparatus, evidence and report. Successor work lives on its own branch."),
        "regression_test": "V7_1_V7_IMMUTABILITY_PROOF.json re-verifies all 26 V7 hashes and "
                           "the CHAMPION digest on every freeze",
    },
    {
        "id": "D10",
        "severity": "P4",
        "title": "A published hyperparameter was not consumed by the code that published it",
        "root_cause": (
            "V7's first similarity spec published PROFILE_SHRINKAGE_K while `team_profile` "
            "never applied it, so the frozen spec did not describe the executed code. V7 "
            "repaired the instance; the CLASS had no guard."),
        "evidence": "V7 similarity v1 -> v2 change record",
        "affected_experiment": "V7 (already repaired there)",
        "changes_v7_interpretation": "No.",
        "generic_fix": (
            "Specs are generated FROM the modules that implement them (`version_stamp()` on "
            "every module, hashed into the freeze manifest), so a published constant that no "
            "code reads cannot drift undetected."),
        "regression_test": "test_11_similarity_spec_is_the_frozen_v7_spec, "
                           "test_12_decay_family_is_frozen_and_not_searchable",
    },
]


def by_severity():
    out = {}
    for d in DEFECTS:
        out.setdefault(d["severity"], []).append(d["id"])
    return {k: sorted(v) for k, v in sorted(out.items())}


def unresolved_blocking():
    """P0-P3 defects that are not fixed. Readiness requires this to be empty."""
    return [d["id"] for d in DEFECTS
            if d["severity"] in ("P0", "P1", "P2", "P3") and not d.get("generic_fix")]


def version_stamp() -> dict:
    return {"bugledger_version": BUGLEDGER_VERSION,
            "n_defects": len(DEFECTS),
            "by_severity": by_severity(),
            "unresolved_p0_p3": unresolved_blocking(),
            "every_fix_guards_the_class_not_the_instance": True,
            "defects": DEFECTS}
