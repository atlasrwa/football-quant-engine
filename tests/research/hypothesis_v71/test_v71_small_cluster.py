"""V7.1 execution-closure mission -- section 8: small-cluster inference for Endpoint B.

Endpoint B has ~8 multiplicity-family clusters. The frozen inference is an EXACT ENUMERATED
cluster sign-flip test. These tests are calibration/null checks on SYNTHETIC data only: no
confirmatory outcome is read, and no development or fresh effect is involved.
"""
from __future__ import annotations

import math

import pytest

from src.research.hypothesis_v71 import estimator as ES


def _rademacher_stream(k, i):
    import hashlib
    return int.from_bytes(hashlib.sha256(f"cal|{k}|{i}".encode()).digest()[:1], "big") & 1


def test_08_method_is_exact_enumerated_sign_flip():
    assert ES.SMALL_CLUSTER_METHOD == "EXACT_ENUMERATED_CLUSTER_SIGN_FLIP"
    vs = ES.version_stamp()
    assert vs["normal_approximation_p_value_is_not_the_primary"] is True
    assert vs["raw_control_pool_n_cannot_drive_precision"] is True


def test_08_cluster_means_reduce_rows_so_pool_size_cannot_drive_precision():
    """The inference operates on G cluster means, not on raw rows: replicating the rows within
    a cluster (as a large control pool would) must not change the cluster mean or the p."""
    values = [0.2, 0.2, 0.2, -0.1, -0.1, 0.3, 0.3]
    clusters = ["a", "a", "a", "b", "b", "c", "c"]
    base = ES.sign_flip_test(values, clusters)
    # inflate cluster 'a' 100x -- exactly what an oversized control pool would do to row counts
    inflated_v = values + [0.2] * 300
    inflated_c = clusters + ["a"] * 300
    infl = ES.sign_flip_test(inflated_v, inflated_c)
    assert base["n_clusters"] == infl["n_clusters"] == 3
    assert abs(base["point_estimate"] - infl["point_estimate"]) < 1e-12
    assert base["p_value"] == infl["p_value"], "row inflation changed the inference"


def test_08_is_exact_and_deterministic_for_small_g():
    values = [0.15] * 8
    clusters = list("abcdefgh")
    r1 = ES.sign_flip_test(values, clusters)
    r2 = ES.sign_flip_test(values, clusters)
    assert r1["enumerated"] and r1["n_sign_vectors"] == 2 ** 8
    assert r1 == r2, "sign-flip test is not deterministic"


def test_08_strong_consistent_signal_is_significant():
    """8 clusters all pointing the same way: the only sign vector as extreme as observed is
    the all-positive one (and its mirror), so p = 2 / 2^8."""
    values = [0.2, 0.25, 0.18, 0.22, 0.3, 0.19, 0.21, 0.24]
    clusters = list("abcdefgh")
    res = ES.sign_flip_test(values, clusters)
    assert res["point_estimate"] > 0
    assert res["p_value"] == pytest.approx(2 / 256, abs=1e-9)
    assert res["p_value"] < 0.05


def test_08_pure_null_is_not_significant():
    """A near-symmetric set of cluster effects around zero must not be called significant."""
    values = [0.10, -0.11, 0.09, -0.08, 0.12, -0.10, 0.07, -0.09]
    clusters = list("abcdefgh")
    res = ES.sign_flip_test(values, clusters)
    assert res["p_value"] > 0.20, res


def test_08_null_calibration_type1_is_controlled():
    """Monte-Carlo calibration on SYNTHETIC nulls: with truly zero-mean symmetric clusters,
    the exact test rejects at alpha ~= alpha. Uses a deterministic stream, no real data."""
    import hashlib

    def draw(trial, g):
        out = []
        for i in range(g):
            d = hashlib.sha256(f"null|{trial}|{i}".encode()).digest()
            # symmetric around zero in [-1, 1]
            out.append((int.from_bytes(d[:4], "big") / 0xFFFFFFFF) * 2 - 1)
        return out

    g, trials, alpha = 8, 400, 0.05
    rejects = 0
    for t in range(trials):
        vals = draw(t, g)
        res = ES.sign_flip_test(vals, [str(i) for i in range(g)])
        if res["p_value"] is not None and res["p_value"] <= alpha:
            rejects += 1
    rate = rejects / trials
    # exact test: the empirical type-I rate must not materially exceed alpha
    assert rate <= alpha + 0.03, f"type-I inflation: {rate}"


def test_08_insufficient_clusters_reports_limited_status_not_a_fake_p():
    res = ES.sign_flip_test([0.3, 0.4], ["a", "b"])
    assert res["p_value"] is None
    assert res["inference_status"] == "INSUFFICIENT_CLUSTERS_FOR_INFERENCE"
    assert res["point_estimate"] == pytest.approx(0.35)


def test_08_impossible_statistic_fails_closed():
    with pytest.raises(ES.InferenceRefused):
        ES.sign_flip_test([float("nan")] * 4, list("abcd"))


def test_08_wrapper_reports_signflip_p_not_normal_approx():
    values = [0.2, 0.25, 0.18, 0.22, 0.3, 0.19, 0.21, 0.24]
    clusters = list("abcdefgh")
    out = ES.small_cluster_inference(values, clusters)
    assert out["primary_method"] == ES.SMALL_CLUSTER_METHOD
    assert out["normal_approx_p_is_not_used"] is True
    assert out["n_clusters"] == 8
    # the descriptive clustered SE is present but is NOT the primary inference
    assert "clustered_se_descriptive_only" in out
    assert out["primary_p_value"] == pytest.approx(2 / 256, abs=1e-9)
