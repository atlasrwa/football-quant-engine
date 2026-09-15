"""V7.1 adversarial point-in-time red team (`v71_leakage_v1`). Section 19.

Two layers, because each catches what the other cannot.

  1. **Guard mutations.** Eighteen classes of future/target information are injected into the
     frozen predicates and each must be REJECTED. A guard that rejects everything would pass
     this layer trivially, so a legitimate point-in-time observation must also be ACCEPTED.

  2. **Empirical probes against the live compiler.** A guard can be correct while the engine
     never calls it. So the red team also corrupts the corpus itself and re-compiles:
       - corrupting the TARGET fixture's own statistic must not move the feature;
       - corrupting a FUTURE fixture must not move the feature;
       - corrupting a valid PRIOR fixture of the subject MUST move it.
     The third is the negative control. Without it the first two prove nothing -- a feature
     that is always constant would pass them both.

ZERO SPEND. Reads no outcome.
"""
from __future__ import annotations

from src.research.hypothesis_v7 import leakage as V7L

LEAKAGE_VERSION = "v71_leakage_v1"

LeakageRejected = V7L.LeakageRejected

#: Market, settlement and post-match fields that may never enter a feature construction.
FORBIDDEN_FEATURE_FIELDS = tuple(V7L.FORBIDDEN_FEATURE_FIELDS) + (
    "future_market_price", "provider_retrieval_time_after_kickoff",
    "future_season_aggregate", "future_formation")


def assert_no_forbidden_fields(feature_inputs) -> None:
    blob = " ".join(str(x).lower() for x in feature_inputs)
    for f in FORBIDDEN_FEATURE_FIELDS:
        if f in blob:
            raise LeakageRejected(f"feature input references forbidden field '{f}'")


def assert_retrieval_before_kickoff(retrieved_unix, kickoff_unix) -> None:
    """A provider value retrieved AFTER kickoff may embody the match itself, even when the
    value is nominally a pre-match one."""
    if retrieved_unix is None or kickoff_unix is None:
        raise LeakageRejected("missing retrieval timestamp")
    if int(retrieved_unix) >= int(kickoff_unix):
        raise LeakageRejected(
            f"provider retrieval at {retrieved_unix} is not strictly before kickoff "
            f"{kickoff_unix}")


def run_guard_suite(reference_unix: int, target_fixture_id: str) -> dict:
    """Eighteen injected leakage classes, plus a legitimate observation that must pass."""
    results = {}

    def expect_reject(name, fn):
        try:
            fn()
            results[name] = "LEAKED"
        except LeakageRejected:
            results[name] = "rejected"

    day = 86400
    expect_reject("01_target_outcome", lambda: V7L.assert_target_not_in_baseline(
        target_fixture_id, [target_fixture_id, "mt_other"]))
    expect_reject("02_target_post_match_stat", lambda: V7L.assert_target_stat_absent(
        [f"stat:{target_fixture_id}:corners"], target_fixture_id))
    expect_reject("03_future_fixture", lambda: V7L.assert_obs_before_reference(
        reference_unix + 1, reference_unix, "obs"))
    expect_reject("04_future_same_team_fixture", lambda: V7L.assert_no_future_in_profile(
        [reference_unix + 7 * day], reference_unix))
    expect_reject("05_future_opponent_fixture", lambda: V7L.assert_no_future_in_profile(
        [reference_unix + 3 * day], reference_unix))
    expect_reject("06_future_season_aggregate", lambda: assert_no_forbidden_fields(
        ["team_form", "future_season_aggregate"]))
    expect_reject("07_settlement", lambda: assert_no_forbidden_fields(
        ["team_form", "settlement"]))
    expect_reject("08_closing_line", lambda: assert_no_forbidden_fields(
        ["team_form", "closing_line"]))
    expect_reject("09_future_market_price", lambda: assert_no_forbidden_fields(
        ["team_form", "future_market_price"]))
    expect_reject("10_future_lineup", lambda: assert_no_forbidden_fields(
        ["team_form", "future_lineup"]))
    expect_reject("11_future_injury", lambda: assert_no_forbidden_fields(
        ["team_form", "future_injury"]))
    expect_reject("12_future_formation", lambda: assert_no_forbidden_fields(
        ["team_form", "future_formation"]))
    expect_reject("13_target_own_stat", lambda: assert_no_forbidden_fields(
        ["team_form", "target_fixture_stat"]))
    expect_reject("14_timestamp_at_cutoff", lambda: V7L.assert_obs_before_reference(
        reference_unix, reference_unix, "obs"))
    expect_reject("15_provider_retrieval_after_kickoff",
                  lambda: assert_retrieval_before_kickoff(reference_unix + 60,
                                                          reference_unix))
    expect_reject("16_similarity_profile_from_future",
                  lambda: V7L.assert_similarity_past_only([reference_unix + day],
                                                          reference_unix))
    expect_reject("17_scaler_fitted_on_future",
                  lambda: V7L.assert_scaler_fit_past_only([reference_unix + 30 * day],
                                                          reference_unix))
    expect_reject("18_shrinkage_fitted_on_future",
                  lambda: V7L.assert_hyperparams_fit_past_only([reference_unix + 90 * day],
                                                               reference_unix))

    try:
        V7L.assert_obs_before_reference(reference_unix - day, reference_unix, "obs")
        V7L.assert_target_not_in_baseline(target_fixture_id, ["mt_a", "mt_b"])
        V7L.assert_similarity_past_only([reference_unix - day], reference_unix)
        V7L.assert_hyperparams_fit_past_only([reference_unix - day], reference_unix)
        V7L.assert_target_stat_absent(["stat:mt_a:corners"], target_fixture_id)
        assert_retrieval_before_kickoff(reference_unix - 3600, reference_unix)
        assert_no_forbidden_fields(["team_form", "opponent_profile"])
        results["00_legitimate_pit_observation"] = "accepted"
    except LeakageRejected as exc:
        results["00_legitimate_pit_observation"] = f"WRONGLY_REJECTED: {exc}"

    mutations = {k: v for k, v in results.items() if k != "00_legitimate_pit_observation"}
    return {"leakage_version": LEAKAGE_VERSION,
            "n_mutation_classes": len(mutations),
            "results": results,
            "all_mutations_rejected": all(v == "rejected" for v in mutations.values()),
            "legitimate_observation_accepted":
                results["00_legitimate_pit_observation"] == "accepted",
            "all_pass": (all(v == "rejected" for v in mutations.values())
                         and results["00_legitimate_pit_observation"] == "accepted")}


def empirical_probe(compile_fn, *, corrupt_target, corrupt_future, corrupt_prior):
    """Three-way probe against the LIVE compiler. `compile_fn()` returns a feature value.

    Each `corrupt_*` is a context manager that perturbs one class of observation. The prior
    corruption is the NEGATIVE CONTROL: if it does not move the feature, the other two
    results are vacuous and the probe reports failure.
    """
    baseline = compile_fn()
    with corrupt_target:
        target_moved = compile_fn() != baseline
    with corrupt_future:
        future_moved = compile_fn() != baseline
    with corrupt_prior:
        prior_moved = compile_fn() != baseline
    return {"baseline": baseline,
            "target_corruption_moved_feature": target_moved,
            "future_corruption_moved_feature": future_moved,
            "prior_corruption_moved_feature": prior_moved,
            "negative_control_live": prior_moved,
            "pass": (not target_moved) and (not future_moved) and prior_moved}


def version_stamp() -> dict:
    return {"leakage_version": LEAKAGE_VERSION,
            "source": V7L.LEAKAGE_VERSION,
            "n_mutation_classes": 18,
            "has_empirical_probe_against_live_compiler": True,
            "has_negative_control": True,
            "forbidden_feature_fields": list(FORBIDDEN_FEATURE_FIELDS)}
