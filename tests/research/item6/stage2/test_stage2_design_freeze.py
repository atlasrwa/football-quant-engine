"""ITEM 6 STAGE 2 zero-outcome design-freeze test suite.

Covers the three mandatory batteries: DATA LEAKAGE (1-10), FEATURE FUNNEL (11-18) and MODEL
PARITY (19-25). No test reads a target label, calls an LLM, or computes an OOS metric.
"""
from __future__ import annotations

import copy
import json

import pytest

from src.research.item6.stage2 import canonical_family as CF
from src.research.item6.stage2 import evaluation as EV
from src.research.item6.stage2 import feature_generator as FG
from src.research.item6.stage2 import feature_spec as FS
from src.research.item6.stage2 import folds as FD
from src.research.item6.stage2 import funnel as FN
from src.research.item6.stage2 import model_specs as MS
from src.research.item6.stage2 import provider_measurability as PM
from src.research.item6.stage2 import similarity_policy as SP
from src.research.item6.stage2 import threshold_policy as TP

CUTOFF = 2_000.0


# ── synthetic, fully-controlled corpus ────────────────────────────────────────────────
def _match(mid, date, a_corners, b_corners, *, comp="C1", extra=None):
    m = {
        "id": mid, "date_unix": date, "competition_id": comp,
        "home_name": "H", "away_name": "A", "status": "complete",
        "team_a_corners": a_corners, "team_b_corners": b_corners,
        "team_a_fh_corners": a_corners // 2, "team_b_fh_corners": b_corners // 2,
        "team_a_2h_corners": a_corners - a_corners // 2,
        "team_b_2h_corners": b_corners - b_corners // 2,
        "homeGoalCount": 2, "awayGoalCount": 1,
        "ht_goals_team_a": 1, "ht_goals_team_b": 0,
        "team_a_shots": 10, "team_b_shots": 8,
        "team_a_shotsOnTarget": 5, "team_b_shotsOnTarget": 3,
        "team_a_possession": 55, "team_b_possession": 45,
        "team_a_fouls": 11, "team_b_fouls": 12,
        "team_a_yellow_cards": 2, "team_b_yellow_cards": 1,
        "team_a_red_cards": 0, "team_b_red_cards": 0,
        "team_a_offsides": 2, "team_b_offsides": 1,
        "team_a_2h_cards": 1, "team_b_2h_cards": 1,
    }
    if extra:
        m.update(extra)
    return m


def _season_key(m):
    return str(m.get("competition_id"))


class _SeasonFns:
    """Stands in for the champion module's season helpers, with identical semantics."""
    _season_key = staticmethod(_season_key)

    @staticmethod
    def current_season_key(hist, team, before):
        rows = [(d, m) for d, m, _ in hist.get(team, []) if d < before]
        return _season_key(max(rows, key=lambda t: t[0])[1]) if rows else None


SEASON = _SeasonFns()


def _hist(matches):
    h = {}
    for m in matches:
        h.setdefault(m["home_name"], []).append((m["date_unix"], m, "home"))
        h.setdefault(m["away_name"], []).append((m["date_unix"], m, "away"))
    for k in h:
        h[k].sort(key=lambda t: t[0])
    return h


PRIOR = [_match(i, 1000.0 + i * 100, 4 + i, 3 + i) for i in range(6)]      # before CUTOFF
FUTURE = [_match(100 + i, CUTOFF + 100 + i * 100, 40, 40) for i in range(4)]  # after CUTOFF


@pytest.fixture()
def spec():
    inst = {
        "canonical_key": "SF_THRESHOLD_NONLINEARITY::corner_kicks.FOR::FULL_MATCH",
        "structural_family": "SF_THRESHOLD_NONLINEARITY",
        "canonical_metrics": [{"metric": "corner_kicks", "perspective": "FOR"}],
        "period_signature": ["FULL_MATCH"], "required_extension": "GX_THRESHOLD_CONDITION",
    }
    return FS.build_feature_spec({"metric_instantiations": [inst]})


@pytest.fixture()
def fitted():
    return TP.fit({"corner_kicks.FOR.FULL_MATCH.STD": [float(i % 12) for i in range(600)]},
                  fold_index=0, train_end_unix=CUTOFF)


def _values(matches, spec, fitted):
    return FG.generate_features(hist=_hist(matches), home="H", away="A", before=CUTOFF,
                                spec=spec, fitted_thresholds=fitted,
                                season_key_fn=SEASON)["values"]


# ══════════════════════════ 1-10  DATA LEAKAGE ══════════════════════════
def test_01_future_target_outcome_mutation_does_not_change_features(spec, fitted):
    base = _values(PRIOR + FUTURE, spec, fitted)
    mutated = copy.deepcopy(FUTURE)
    for m in mutated:
        m["homeGoalCount"], m["awayGoalCount"], m["totalGoalCount"] = 99, 99, 198
    assert _values(PRIOR + mutated, spec, fitted) == base


def test_02_closing_line_mutation_does_not_change_features(spec, fitted):
    base = _values(PRIOR + FUTURE, spec, fitted)
    mutated = copy.deepcopy(PRIOR)
    for m in mutated:
        m.update({"odds_ft_over25": 9.99, "odds_corners_1": 1.01, "closing_line": 0.5})
    assert _values(mutated + FUTURE, spec, fitted) == base


def test_03_post_match_stat_mutation_of_the_target_fixture_does_not_change_features(spec, fitted):
    """The fixture being predicted contributes NOTHING to its own features."""
    target = _match(999, CUTOFF, 50, 50)
    base = _values(PRIOR + [target], spec, fitted)
    t2 = copy.deepcopy(target)
    t2.update({"team_a_corners": 0, "team_b_corners": 0, "team_a_shots": 0})
    assert _values(PRIOR + [t2], spec, fitted) == base


def test_04_future_fixture_mutation_does_not_change_a_prior_prediction(spec, fitted):
    base = _values(PRIOR, spec, fitted)
    assert _values(PRIOR + FUTURE, spec, fitted) == base     # adding future matches is inert


def test_05_future_lineup_or_injury_mutation_does_not_change_features(spec, fitted):
    base = _values(PRIOR + FUTURE, spec, fitted)
    mutated = copy.deepcopy(FUTURE)
    for m in mutated:
        m.update({"lineups": {"home": ["x"]}, "injuries": ["y"], "expected_lineup": "z"})
    assert _values(PRIOR + mutated, spec, fitted) == base


def test_06_fold_boundaries_prevent_future_data_in_training():
    ms = [_match(i, 1000.0 + i * 10, 5, 5) for i in range(500)]
    man = FD.build_fold_manifest(ms, sufficiency_fn=lambda train, m: True)
    FD.assert_chronological(man)          # raises on any ordering/overlap violation
    for r in man["rows"]:
        assert r["kickoff_unix"] >= r["train_cutoff_unix"]
    usable = [f for f in man["folds"] if not f["skipped"]]
    for a, b in zip(usable, usable[1:]):
        assert a["test_end_unix"] <= b["test_start_unix"]


def test_07_threshold_fit_uses_training_fold_only(fitted):
    """Edges depend only on the values handed to fit(); test-fold values cannot reach them."""
    train_only = TP.fit({"s": [float(i) for i in range(600)]}, fold_index=0, train_end_unix=CUTOFF)
    with_test = TP.fit({"s": [float(i) for i in range(600)] + [1e6] * 600},
                       fold_index=0, train_end_unix=CUTOFF)
    assert train_only.edges["s"] != with_test.edges["s"]      # contamination WOULD move them
    assert fitted.fold_index == 0 and fitted.train_end_unix == CUTOFF
    assert TP.version_stamp()["fit_scope"] == "training_fold_only"


def test_08_similarity_fit_uses_training_fold_only():
    rows = [[("ax", "low"), ("bx", "high")]] * 60
    pb = SP.fit(rows, fold_index=0)
    assert pb.cell_support["ax=low|bx=high"] == 60
    assert pb.resolve([("ax", "low"), ("bx", "high")]) == "ax=low|bx=high"
    assert pb.resolve([("ax", None), ("bx", "high")]) is None      # abstain, never impute
    assert SP.version_stamp()["fit_scope"] == "training_fold_only"


def test_09_normalization_fit_uses_training_fold_only():
    ft = TP.fit({"s": [float(i) for i in range(600)]}, fold_index=0, train_end_unix=CUTOFF)
    mean, sd = ft.center_scale["s"]
    assert abs(mean - 299.5) < 1e-6 and sd > 0
    assert ft.standardize("s", 299.5) == pytest.approx(0.0, abs=1e-9)
    assert ft.standardize("unknown_stat", 1.0) is None
    for arm in (MS.m0_spec(["f"]), MS.m1_spec(["f"], ["i6_x"])):
        assert arm["scaling"] == "standardize_fit_inside_tuning_fold"


def test_10_calibration_fit_uses_training_or_validation_only():
    m0, m1 = MS.m0_spec(["f"]), MS.m1_spec(["f"], ["i6_x"])
    assert m0["calibration"] == m1["calibration"] == (
        "isotonic_fit_on_inner_timeseries_oof_predictions_of_training_block")
    assert "in_sample" not in m0["calibration"] and "test" not in m0["calibration"]
    assert FD.CALIBRATION_WINDOW == "INNER_TRAINING_FOLDS_ONLY"


# ══════════════════════════ 11-18  FEATURE FUNNEL ══════════════════════════
def _f(**kw):
    base = {
        "f_class": FN.F4, "grounded": True, "provider_safe": True, "future_leakage": False,
        "counts_as_novel_measurable": True, "distinct_metrics": ["corner_kicks", "possession"],
        "novelty_signals": ["US_THRESHOLD_NONLINEARITY"],
        "required_extension": "GX_THRESHOLD_CONDITION",
        "valid_evidence_refs": ["E:TEAM_A:corner_kicks:FOR:FULL_MATCH:ALL:ALL_PRIOR"],
        "mechanism_id_local": "M1",
    }
    base.update(kw)
    return base


def test_11_unresolved_or_unavailable_provider_metric_is_rejected():
    assert FN.classify_mechanism(
        _f(distinct_metrics=["accurate_crosses", "corner_kicks"]))["status"] == FN.S2F1
    assert FN.classify_mechanism(_f(distinct_metrics=["blocks"]))["status"] == FN.S2F1
    assert FN.classify_mechanism(
        _f(distinct_metrics=["totally_made_up_metric"]))["status"] == FN.S2F4
    assert not PM.is_measurable("accurate_crosses")


def test_12_unsupported_temporal_resolution_is_rejected():
    # asserts half/sequence novelty but cites no half-period evidence
    assert FN.classify_mechanism(_f(
        novelty_signals=["US_SEQUENCING_REGIME"],
        required_extension="GX_SEQUENCE_REGIME"))["status"] == FN.S2F6
    # cites half resolution for a metric with no half split in the corpus
    assert FN.classify_mechanism(_f(
        distinct_metrics=["possession"],
        valid_evidence_refs=["E:TEAM_A:possession:FOR:SECOND_HALF:ALL:ALL_PRIOR"],
    ))["status"] == FN.S2F6


def test_13_stage1_numeric_thresholds_are_never_used(spec, fitted):
    """Every cut point comes from the training-fold quantile policy, not from LLM prose."""
    assert TP.version_stamp()["llm_numeric_thresholds_used"] is False
    assert FS.version_stamp()["reads_outcomes"] is False
    assert list(TP.QUANTILE_GRID) == [1 / 3, 2 / 3]
    # the ONLY numbers that band a feature are the fitted edges
    edges = fitted.edges["corner_kicks.FOR.FULL_MATCH.STD"]
    assert fitted.bin_of("corner_kicks.FOR.FULL_MATCH.STD", edges[0] - 1e-9) == "low"
    assert fitted.bin_of("corner_kicks.FOR.FULL_MATCH.STD", edges[1] + 1e-9) == "high"
    src = open("src/research/item6/stage2/feature_generator.py").read()
    assert "provider_requirements" not in src          # LLM-authored field never consulted


def test_14_duplicate_canonical_family_is_collapsed_deterministically():
    a, b = _f(mechanism_id_local="M1"), _f(mechanism_id_local="M2")
    a["_fixture_id"] = b["_fixture_id"] = "fx1"
    res = FN.run_funnel([a, b])
    statuses = sorted(r["status"] for r in res["rows"])
    assert statuses == [FN.S2F5, FN.S2F8]
    assert res["n_distinct_feasible_canonical_keys"] == 1
    assert CF.canonical_key(a) == CF.canonical_key(b)
    # collapse order is stable across runs
    assert FN.run_funnel([a, b])["rows"][0]["status"] == res["rows"][0]["status"]


def test_15_stage1_registry_cannot_be_mutated_by_stage2_code():
    reg = json.load(open("research/item6/out/execution/stage1_live_v6/"
                         "ITEM6_STAGE1_NOVEL_FAMILY_REGISTRY_V1.json"))
    before = json.dumps(reg, sort_keys=True)
    rows = _f(); rows["_fixture_id"] = "fx"
    FN.run_funnel([rows])
    CF.build_canonical_registry([], {})
    after = json.dumps(json.load(open("research/item6/out/execution/stage1_live_v6/"
                                      "ITEM6_STAGE1_NOVEL_FAMILY_REGISTRY_V1.json")),
                       sort_keys=True)
    assert before == after


def test_16_infeasible_family_never_enters_m1():
    bad = _f(distinct_metrics=["accurate_crosses"]); bad["_fixture_id"] = "fx"
    good = _f(); good["_fixture_id"] = "fx"
    res = FN.run_funnel([bad, good])
    feas = [r for r in res["rows"] if r["status"] in FN.FEASIBLE_STATUSES]
    byseq = {0: bad, 1: good}
    reg = CF.build_canonical_registry(feas, byseq)
    spec_ = FS.build_feature_spec(reg)
    names = " ".join(c["name"] for c in spec_["columns"])
    assert "accurate_crosses" not in names
    m1 = MS.m1_spec(["m0f"], [c["name"] for c in spec_["columns"]])
    assert not any("accurate_crosses" in n for n in m1["feature_universe"])


def test_17_feasible_family_instantiates_deterministically():
    good = _f(); good["_fixture_id"] = "fx"
    r1 = FN.run_funnel([good]); r2 = FN.run_funnel([copy.deepcopy(good)])
    reg1 = CF.build_canonical_registry(
        [x for x in r1["rows"] if x["status"] in FN.FEASIBLE_STATUSES], {0: good})
    reg2 = CF.build_canonical_registry(
        [x for x in r2["rows"] if x["status"] in FN.FEASIBLE_STATUSES], {0: good})
    s1, s2 = FS.build_feature_spec(reg1), FS.build_feature_spec(reg2)
    assert json.dumps(s1, sort_keys=True) == json.dumps(s2, sort_keys=True)
    assert s1["n_columns"] > 0


def test_18_same_historical_state_gives_byte_identical_feature_vector(spec, fitted):
    a = _values(PRIOR + FUTURE, spec, fitted)
    b = _values(copy.deepcopy(PRIOR) + copy.deepcopy(FUTURE), spec, fitted)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ══════════════════════════ 19-25  MODEL PARITY ══════════════════════════
@pytest.fixture()
def arms():
    m0 = MS.m0_spec([f"m0_{i}" for i in range(72)])
    m1 = MS.m1_spec([f"m0_{i}" for i in range(72)], [f"i6_{i}" for i in range(108)])
    return m0, m1


def test_19_both_arms_receive_identical_fixture_folds():
    ms = [_match(i, 1000.0 + i * 10, 5, 5) for i in range(400)]
    a = FD.build_fold_manifest(ms, sufficiency_fn=lambda t, m: True)
    b = FD.build_fold_manifest(ms, sufficiency_fn=lambda t, m: True)
    assert a["fold_manifest_sha256"] == b["fold_manifest_sha256"]
    assert a["identical_for_both_arms"] is True


def test_20_identical_target_labels(arms):
    """Neither arm defines or transforms the label; a single shared target spec governs both."""
    m0, m1 = arms
    assert "target" not in m0 and "target" not in m1
    dr = EV.decision_rule()
    assert dr["primary_target_only"] is True
    assert EV.PRIMARY_METRIC == "OOS_MEAN_LOGLOSS_DELTA_M0_MINUS_M1"


def test_21_identical_preprocessing_policy(arms):
    m0, m1 = arms
    for k in ("imputation", "scaling", "coverage_screen_min_nonmissing_rate",
              "coverage_screen_scope"):
        assert m0[k] == m1[k]


def test_22_identical_regularization_selection_machinery(arms):
    m0, m1 = arms
    for k in ("model_class", "penalty_structure", "estimator", "selection_rule", "c_grid",
              "l1_ratio_grid", "inner_cv_splits", "inner_cv_kind",
              "uses_frozen_champion_hyperparameters"):
        assert m0[k] == m1[k]
    assert m0["uses_frozen_champion_hyperparameters"] is False
    assert "grouped_shrinkage_groups" not in m0 and "grouped_shrinkage_groups" not in m1


def test_23_identical_calibration_machinery(arms):
    m0, m1 = arms
    assert m0["calibration"] == m1["calibration"]
    assert m0["probability_clip"] == m1["probability_clip"] == [0.01, 0.99]


def test_24_only_difference_is_llm_derived_feature_availability(arms):
    m0, m1 = arms
    p = MS.parity_assertions(m0, m1)
    assert p["shared_knobs_identical"] and p["m0_universe_is_subset_of_m1"]
    assert p["only_difference_is_llm_feature_availability"] is True
    assert p["n_added_features"] == 108
    assert m0["llm_derived_features_available"] is False
    assert m1["llm_derived_features_available"] is True


def test_25_m1_cannot_see_oos_labels_during_feature_construction():
    src = open("src/research/item6/stage2/feature_generator.py").read()
    for banned in ("outcome(", "homeGoalCount'] -", "y_true", "label", "closing"):
        assert banned not in src, f"generator references {banned!r}"
    assert FG.version_stamp()["reads_outcomes"] is False
    assert FG.version_stamp()["made_llm_call"] is False


# ══════════════════════════ design-freeze invariants ══════════════════════════
def test_multiplicity_policy_controls_search_space():
    mp = MS.multiplicity_policy()
    assert mp["primary_claim"] == "M1_universe_vs_M0_universe"
    assert mp["feature_selected_using_oos_information"] is False
    assert mp["hyperparameters_tuned_on_test_folds"] is False
    assert "elastic_net_uniform_per_coefficient_penalty_both_arms" in mp["controls"]
    assert mp["grouped_shrinkage_used"] is False
    assert mp["structural_groups_role"] == "secondary_ablation_definition_only"


def test_parity_check_catches_any_non_feature_knob_difference(arms):
    m0, m1 = arms
    for key, val in (("calibration", "platt"), ("probability_clip", [0.0, 1.0]),
                     ("estimator", {**m1["estimator"], "max_iter": 100}),
                     ("some_future_knob", "x")):
        bad = dict(m1); bad[key] = val
        p = MS.parity_assertions(m0, bad)
        assert p["only_difference_is_llm_feature_availability"] is False, key
        assert key in p["differing_shared_knobs"], key


def test_evaluation_execution_pins_leave_no_executor_choice():
    vs = EV.version_stamp()
    pins = vs["execution_pins"]
    for k in ("scored_set", "pooling", "probability_scored", "bootstrap", "ci_type", "ece",
              "brier_delta", "residual_deviance_delta", "selected_feature_stability",
              "ablation_construction", "family_level_test", "secondary_target_test",
              "fold_training_failure"):
        assert pins.get(k), k
    assert vs["ece_n_bins"] == 10 and vs["bootstrap_ci_type"] == "percentile"
    assert "intersection" in pins["scored_set"]
    assert not any("grouped shrinkage" in f for f in EV.failure_modes())


def test_power_sensitivity_brackets_both_dependence_bounds():
    from src.research.item6.stage2 import power as PW
    ps = PW.build_power_sensitivity(n_oos_predictions=13012, n_blocks=95, n_folds=5,
                                    median_feature_coverage=0.8,
                                    n_columns_below_coverage_screen=0)
    b = ps["max_paired_sd_with_ci_half_width_at_or_below_mpi"]
    assert b["conservative_bound"] < b["independent_bound"]
    for row in ps["sensitivity_table"]:
        c, i = row["conservative_bound_n_blocks"], row["independent_bound_n_fixtures"]
        assert c["standard_error"] >= i["standard_error"]
        # The conjunctive rule caps power at a true effect equal to MPI at one half.
        assert c["power_at_true_delta_equal_mpi"] <= 0.5 + 1e-9
        assert i["power_at_true_delta_equal_mpi"] <= 0.5 + 1e-9
        assert c["true_delta_for_80pct_power"] > EV.MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT
    assert ps["reads_outcomes"] is False


def test_stage2_can_fail_cleanly():
    dr = EV.decision_rule()
    assert dr["combination"] == "CONJUNCTIVE_ALL_CLAUSES_REQUIRED"
    assert dr["subjective_override_permitted"] is False
    assert dr["fail_is_a_valid_scientific_result"] is True
    assert len(EV.failure_modes()) >= 4


def test_no_paid_llm_anywhere_in_stage2_package():
    import pathlib
    for p in pathlib.Path("src/research/item6/stage2").glob("*.py"):
        src = p.read_text()
        for banned in ("boto3", "bedrock", "converse", "Converse", "anthropic"):
            assert banned not in src, f"{p.name} references {banned!r}"


def test_market_edge_excluded_from_primary_endpoint():
    assert EV.version_stamp()["market_edge_in_primary_endpoint"] is False
    assert EV.version_stamp()["hit_rate_used_as_primary"] is False
