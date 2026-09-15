"""V7 leakage guards + mutation tests (`v7_leakage_v2`). Phase 24.

Mechanical PIT/leakage guards used by the measurement engine, plus injectable mutation checks
that PROVE future information is rejected. Each guard is a pure predicate over (observation,
reference_time / target_fixture); the mutation tests flip a fact and assert the guard fires.

ZERO SPEND. No effects. No OOS outcomes.
"""
from __future__ import annotations

LEAKAGE_VERSION = "v7_leakage_v2"


class LeakageRejected(Exception):
    """A construction attempted to use information not available at the prediction time."""


def assert_obs_before_reference(obs_unix: int, reference_unix: int, what: str) -> None:
    """An observation feeding a PIT construction must strictly precede the reference time."""
    if obs_unix is None or reference_unix is None:
        raise LeakageRejected(f"{what}: missing timestamp")
    if int(obs_unix) >= int(reference_unix):
        raise LeakageRejected(
            f"{what}: observation {obs_unix} >= reference {reference_unix} (future leak)")


def assert_target_not_in_baseline(target_fixture_id: str, cohort_fixture_ids) -> None:
    """A fixture's own outcome may never appear in its baseline/cohort."""
    if target_fixture_id in set(cohort_fixture_ids):
        raise LeakageRejected(
            f"target fixture {target_fixture_id} present in its own baseline/cohort")


def assert_no_future_in_profile(profile_fixture_unixes, reference_unix: int) -> None:
    """A team/opponent profile may use only strictly-prior fixtures (no full-season future)."""
    for u in profile_fixture_unixes:
        if int(u) >= int(reference_unix):
            raise LeakageRejected(
                f"profile uses fixture at {u} >= reference {reference_unix} (future season "
                f"aggregate leak)")


def assert_scaler_fit_past_only(fit_fixture_unixes, train_end_unix: int) -> None:
    """A scaler/standardizer must be fitted only on the fold's training past."""
    for u in fit_fixture_unixes:
        if int(u) >= int(train_end_unix):
            raise LeakageRejected(
                f"scaler fitted on fixture at {u} >= train_end {train_end_unix}")


def assert_similarity_past_only(similarity_fixture_unixes, reference_unix: int) -> None:
    """Similarity must be computed from strictly-prior fixtures only."""
    for u in similarity_fixture_unixes:
        if int(u) >= int(reference_unix):
            raise LeakageRejected(
                f"similarity uses fixture at {u} >= reference {reference_unix}")


# fields that must NEVER appear in a candidate feature construction (market/settlement/future)
FORBIDDEN_FEATURE_FIELDS = (
    "closing_line", "closing_odds", "over_odds", "under_odds", "settlement",
    "settled_result", "future_match", "future_lineup", "future_injury",
    "final_season_table", "post_match_only", "target_fixture_stat")


def assert_hyperparams_fit_past_only(fit_fixture_unixes, train_end_unix: int) -> None:
    """Shrinkage/decay hyperparameters must be fitted on the fold's training past only.

    Distinct from `assert_scaler_fit_past_only`: a scaler can be fitted per-fold while a
    hyperparameter (shrinkage k, decay half-life) is silently chosen ONCE over the whole
    timeline, which leaks the confirmatory window into every fold at once.
    """
    for u in fit_fixture_unixes:
        if int(u) >= int(train_end_unix):
            raise LeakageRejected(
                f"shrinkage/decay hyperparameter fitted on fixture at {u} >= train_end "
                f"{train_end_unix}")


def assert_target_stat_absent(feature_input_keys, target_fixture_id: str) -> None:
    """The target fixture's OWN observed statistics may never be a feature input."""
    for k in feature_input_keys:
        if target_fixture_id in str(k):
            raise LeakageRejected(
                f"feature input '{k}' reads the target fixture {target_fixture_id}'s own "
                f"observed statistic")


def assert_no_forbidden_fields(feature_inputs) -> None:
    blob = " ".join(str(x).lower() for x in feature_inputs)
    for f in FORBIDDEN_FEATURE_FIELDS:
        if f in blob:
            raise LeakageRejected(f"feature input references forbidden field '{f}'")


def run_mutation_suite(reference_unix: int, target_fixture_id: str) -> dict:
    """Inject each leakage class and confirm rejection. Returns per-mutation results."""
    results = {}

    def _expect_reject(name, fn):
        try:
            fn(); results[name] = "LEAKED"
        except LeakageRejected:
            results[name] = "rejected"

    _expect_reject("future_match_in_profile",
                   lambda: assert_no_future_in_profile([reference_unix + 86400],
                                                       reference_unix))
    _expect_reject("post_cutoff_obs",
                   lambda: assert_obs_before_reference(reference_unix + 1, reference_unix,
                                                       "obs"))
    _expect_reject("at_cutoff_obs",
                   lambda: assert_obs_before_reference(reference_unix, reference_unix, "obs"))
    _expect_reject("target_in_baseline",
                   lambda: assert_target_not_in_baseline(target_fixture_id,
                                                         [target_fixture_id, "mt_other"]))
    _expect_reject("future_season_similarity",
                   lambda: assert_similarity_past_only([reference_unix + 7 * 86400],
                                                       reference_unix))
    _expect_reject("scaler_on_future_fold",
                   lambda: assert_scaler_fit_past_only([reference_unix + 30 * 86400],
                                                       reference_unix))
    _expect_reject("forbidden_market_field",
                   lambda: assert_no_forbidden_fields(["team_form", "closing_odds"]))
    _expect_reject("settlement_field",
                   lambda: assert_no_forbidden_fields(["team_form", "settlement"]))
    _expect_reject("future_lineup_injury_field",
                   lambda: assert_no_forbidden_fields(["future_lineup", "future_injury"]))
    _expect_reject("shrinkage_hyperparam_on_future",
                   lambda: assert_hyperparams_fit_past_only(
                       [reference_unix + 90 * 86400], reference_unix))
    _expect_reject("target_fixture_own_stat",
                   lambda: assert_target_stat_absent(
                       [f"stat:{target_fixture_id}:corners"], target_fixture_id))
    # a legitimate PIT observation must PASS (not be rejected)
    try:
        assert_obs_before_reference(reference_unix - 86400, reference_unix, "obs")
        assert_target_not_in_baseline(target_fixture_id, ["mt_a", "mt_b"])
        assert_hyperparams_fit_past_only([reference_unix - 86400], reference_unix)
        assert_target_stat_absent(["stat:mt_a:corners"], target_fixture_id)
        results["legitimate_pit_obs"] = "accepted"
    except LeakageRejected:
        results["legitimate_pit_obs"] = "WRONGLY_REJECTED"

    all_ok = (all(v == "rejected" for k, v in results.items() if k != "legitimate_pit_obs")
              and results["legitimate_pit_obs"] == "accepted")
    return {"leakage_version": LEAKAGE_VERSION, "results": results, "all_pass": all_ok}


def version_stamp() -> dict:
    return {"leakage_version": LEAKAGE_VERSION,
            "guards": ["assert_obs_before_reference", "assert_target_not_in_baseline",
                       "assert_no_future_in_profile", "assert_scaler_fit_past_only",
                       "assert_similarity_past_only", "assert_no_forbidden_fields",
                       "assert_hyperparams_fit_past_only", "assert_target_stat_absent"],
            "forbidden_feature_fields": list(FORBIDDEN_FEATURE_FIELDS)}
