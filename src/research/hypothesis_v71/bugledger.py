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
        "id": "D11",
        "severity": "P1",
        "title": "The recency comparator's 'long' baseline was bound to the hypothesis' window",
        "root_cause": (
            "V7.1's first ontology bound BOTH selectors of SUBJECT_RECENT_VS_LONG_BASELINE to "
            "the hypothesis' own window, so a W5 hypothesis compared a decayed five-match "
            "cohort against an UN-DECAYED FIVE-MATCH baseline. Over five matches, decay and "
            "uniform weighting barely differ, so the contrast collapses toward zero by "
            "construction. The comparator's own name, and V7's frozen definition ('subject "
            "long-run un-decayed PIT baseline'), both say the baseline is long-run."),
        "evidence": (
            "On the development window the same canonical families V7 scored at |r| 0.09-0.18 "
            "scored 0.000-0.044 under the mis-bound baseline"),
        "affected_experiment": "V7.1 only (introduced and fixed during this mission)",
        "changes_v7_interpretation": "No -- V7 never had this binding.",
        "generic_fix": (
            "The baseline selector is pinned to ALL_PRIOR. A golden round-trip case asserts "
            "the reconstructed meaning contrasts a windowed cohort against the whole prior "
            "history, so the binding cannot silently regress."),
        "regression_test": "test_12_recency_baseline_is_long_run_not_the_spec_window",
    },
    {
        "id": "D12",
        "severity": "P1",
        "title": "BASELINE_ABSORPTION fired on reweighting comparators",
        "root_cause": (
            "The absorption check compared the two selectors' venue filters without noticing "
            "that a REWEIGHTING comparator's selectors legitimately share their filters -- the "
            "contrast is carried by the weighting. Every venue-conditioned recency hypothesis "
            "was rejected as absorbed."),
        "evidence": "one of V7's seven survivors was classified STRUCTURALLY_INVALID",
        "affected_experiment": "V7.1 only (introduced and fixed during this mission)",
        "changes_v7_interpretation": "No.",
        "generic_fix": (
            "Absorption is only considered when the two selectors share a weighting. A "
            "reweighting pair is judged on its weighting difference alone."),
        "regression_test": "test_12_conditioned_recency_is_not_baseline_absorption",
    },
    {
        "id": "D13",
        "severity": "P2",
        "title": "V7's executor ignored the declared window for reweighting comparators",
        "root_cause": (
            "In V7's `compile_signal`, the W5/W10 truncation lived in the non-recency branch "
            "only, so every SUBJECT_RECENT_VS_LONG_BASELINE hypothesis decayed over the "
            "team's whole prior history regardless of the window it declared. W5 and W10 "
            "recency hypotheses were therefore the same query."),
        "evidence": "V7 `_execute_v7_oos.compile_signal`; W5 and W10 recency families differ "
                    "only in a field the compiler never read",
        "affected_experiment": "V7",
        "changes_v7_interpretation": (
            "Mildly: V7's recency survivors are all-prior decay contrasts, not the W5/W10 "
            "contrasts their specs declared. The measured effect is real; the label is wrong."),
        "generic_fix": (
            "The window is part of the Selector, so it applies wherever the binding says it "
            "does. A W5 and a W10 recency hypothesis now compile to different queries and "
            "therefore to different IR identities."),
        "regression_test": "test_12_recency_window_changes_the_compiled_cohort",
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
    {
        "id": "D14",
        "severity": "P3",
        "title": "A blast-radius declaration was hand-maintained and drifted from disk",
        "root_cause": (
            "V7's blast-radius artifact listed its changed modules by hand. A module added "
            "after the list was written (`hypothesis_v7/measurement.py`) was silently excluded "
            "from the analysis, so the published conclusion -- no pre-existing test module "
            "reaches changed code -- was never actually checked for that module. V7.1's own "
            "first blast-radius driver repeated the same pattern and had already drifted by "
            "two modules (`matching.py`, `bugledger.py`). The defect is the hand-maintained "
            "declaration, not either instance."),
        "evidence": ("tests/research/hypothesis_oos/test_v7_control_b.py::"
                     "test_blast_radius_proof_is_current_and_complete fails on the unchanged "
                     "pre-V7.1 baseline commit 4c663a737"),
        "affected_experiment": "V7 evidence integrity; V7.1 test discipline",
        "changes_v7_interpretation": (
            "No. V7 is immutable and is NOT patched. The uncovered claim was re-verified "
            "read-only in V7_1_BLAST_RADIUS.json: the only test module that reaches "
            "hypothesis_v7/measurement.py is one of V7.1's own new tests, so no PRE-EXISTING "
            "test module reached it and V7's conclusion was correct although under-verified."),
        "generic_fix": (
            "V7.1's blast-radius driver DERIVES the changed set from the package directory on "
            "disk instead of declaring it, and the artifact carries an explicit re-verification "
            "of the module V7's artifact omitted."),
        "regression_test": ("test_15_blast_radius_declares_every_v71_module_on_disk, "
                            "test_15_v7_undeclared_module_claim_is_reverified_without_"
                            "patching_v7"),
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
