import numpy as np
from src.research.target_aware_market_panel import support as S


def _fold(mid, fold=None, cohort=False):
    return {"match_id": mid, "fold": fold, "involves_cohort_team": cohort}


def test_support_summary_is_outcome_blind_and_diagnostic_only():
    ids = [f"m{i}" for i in range(10)]
    fx = [{"competition_id": "c1" if i < 5 else "c2"} for i in range(10)]
    vals = [float(i) if i < 7 else None for i in range(10)]
    fr = {m: _fold(m, None if i < 2 else 0, i == 9) for i, m in enumerate(ids)}
    d = S.summarize_column(ids, fx, vals, fr)
    assert d["n_nonnull"] == 7 and d["coverage_all"] == 0.7
    assert d["support_status"] == "GLOBAL_COVERAGE_GE_60_DIAGNOSTIC"
    assert d["selection_effect"].startswith("NONE")
    assert set(d["by_competition"]) == {"c1", "c2"}


def test_zero_support_is_reported_not_imputed():
    ids = ["a", "b"]
    fx = [{"competition_id": "c"}, {"competition_id": "c"}]
    fr = {m: _fold(m) for m in ids}
    d = S.summarize_column(ids, fx, [None, None], fr)
    assert d["support_status"] == "ZERO_SUPPORT" and d["n_nonnull"] == 0
    assert d["distribution"]["mean"] is None


def test_near_duplicates_are_report_only_and_family_scoped():
    n = 250
    x = [float(i) for i in range(n)]
    y = [2.0 * i for i in range(n)]
    z = [float((-1) ** i) for i in range(n)]
    cols = {"a": x, "b": y, "c": y, "d": z}
    meta = {"a": {"family": "GOALS"}, "b": {"family": "GOALS"},
            "c": {"family": "CORNERS"}, "d": {"family": "GOALS"}}
    got = S.pairwise_near_duplicates(cols, meta)
    assert len(got) == 1 and got[0]["a"] == "a" and got[0]["b"] == "b"
    assert got[0]["abs_r_ge_0_99"] and got[0]["selection_effect"].startswith("NONE")


def test_similarity_summary_keeps_strength_gap_secondary():
    ds = [{"n_history": 18, "n_neighbors": 6,
           "diagnostic": {"neighbor_opponent_strength_mean": -0.2,
                          "all_opponent_strength_mean": 0.1}}, None,
          {"n_history": 30, "n_neighbors": 10,
           "diagnostic": {"neighbor_opponent_strength_mean": 0.4,
                          "all_opponent_strength_mean": 0.2}}]
    s = S.summarize_similarity_details(ds)
    assert s["n_supported_rows"] == 2 and s["n_rows_with_strength_gap"] == 2
    assert np.isfinite(s["neighbor_minus_all_opponent_strength"]["mean"])
