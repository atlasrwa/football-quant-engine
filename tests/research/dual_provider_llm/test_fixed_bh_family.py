"""PRE_EXECUTION_IMPLEMENTATION_AMENDMENT: the BH family is the frozen five and never shrinks.
Synthetic result dicts only: no historical dataset is loaded."""
from __future__ import annotations

import copy
import itertools

import pytest

from src.research.dual_provider_llm.measurement import executor as E
from src.research.dual_provider_llm.measurement import measures as M
from src.research.dual_provider_llm.measurement import query_spec as Q
from src.research.dual_provider_llm.measurement import support as S

FAMILY = ["DP1_BOX_PRESSURE_MATCHUP", "DP2_WIDE_CENTRAL_INTERACTION",
          "DP3_ALBACETE_DIRECT_PROGRESSION", "DP4_GIRONA_CURRENT_TERRITORIAL_REGIME",
          "DP6_PRESSURE_RESOLUTION_CLEARANCE_PROFILE"]
DP5 = "DP5_ALBACETE_RECENT_TERRITORIAL_EXPANSION"
P = {"DP1_BOX_PRESSURE_MATCHUP": 0.004, "DP2_WIDE_CENTRAL_INTERACTION": 0.03,
     "DP3_ALBACETE_DIRECT_PROGRESSION": 0.2, "DP4_GIRONA_CURRENT_TERRITORIAL_REGIME": 0.01,
     "DP6_PRESSURE_RESOLUTION_CLEARANCE_PROFILE": 0.5}


def _results(non_eval=None):
    non_eval = non_eval or {}
    out = {m: ({"status": non_eval[m]} if m in non_eval else
               {"status": S.Status.OK, "primary": {"p_two_sided": P[m], "statistic": 0.1}})
           for m in FAMILY}
    out[DP5] = {"status": S.Status.OK, "primary": {"statistic": 0.2, "inferential": False}}
    return out


def test_frozen_family_matches_the_frozen_specs():
    assert list(E.FROZEN_BH_FAMILY) == FAMILY
    assert [s["mechanism_id"] for s in Q.specs()
            if s["primary_measurement"].get("in_bh_family")] == FAMILY


def test_01_05_all_five_retained_and_bh_gets_exactly_five_entries(monkeypatch):
    seen = []
    real = M.bh_adjust
    monkeypatch.setattr(M, "bh_adjust", lambda ps: seen.append(list(ps)) or real(ps))
    r = _results({"DP2_WIDE_CENTRAL_INTERACTION": S.Status.INSUFFICIENT_SUPPORT,
                  "DP3_ALBACETE_DIRECT_PROGRESSION": S.Status.INSUFFICIENT_SUPPORT})
    info = E.apply_fixed_family_bh(r)
    assert info["BH_FAMILY_FROZEN"] == FAMILY and info["N_FROZEN_BH_TESTS"] == 5
    assert info["N_BH_EVALUABLE"] == 3 and info["N_BH_NON_EVALUABLE"] == 2
    assert len(seen) == 1 and len(seen[0]) == 5
    assert all("multiplicity" in r[m] for m in FAMILY)


@pytest.mark.parametrize("status", [S.Status.INSUFFICIENT_SUPPORT, S.Status.UNSUPPORTED_METRIC,
                                    S.Status.NO_QUERY_PROFILE])
def test_02_03_04_non_evaluable_is_a_bookkeeping_placeholder(status):
    m = "DP2_WIDE_CENTRAL_INTERACTION"
    r = _results({m: status})
    E.apply_fixed_family_bh(r)
    mult = r[m]["multiplicity"]
    assert mult["primary_p_value"] is None and mult["bh_input_p"] == 1.0
    assert mult["multiplicity_placeholder"] is True and mult["evaluable"] is False
    assert "NOT EVALUABLE" in mult["interpretation"]
    assert r[m]["status"] == status and "primary" not in r[m]     # nothing fabricated


def test_06_dp5_is_never_inserted_into_bh(monkeypatch):
    seen = []
    real = M.bh_adjust
    monkeypatch.setattr(M, "bh_adjust", lambda ps: seen.append(list(ps)) or real(ps))
    r = _results()
    info = E.apply_fixed_family_bh(r)
    assert DP5 not in info["BH_FAMILY_FROZEN"] and len(seen[0]) == 5
    assert r[DP5]["multiplicity"] == {"in_bh_family": False, "descriptive_only": True}


def test_07_all_evaluable_uses_real_p_values_unchanged():
    r = _results()
    info = E.apply_fixed_family_bh(r)
    qs = M.bh_adjust([P[m] for m in FAMILY])
    for m, q in zip(FAMILY, qs):
        mult = r[m]["multiplicity"]
        assert mult["primary_p_value"] == P[m] == mult["bh_input_p"] == r[m]["primary"][
            "p_two_sided"]
        assert mult["bh_q"] == q and mult["multiplicity_placeholder"] is False
    assert info["N_BH_EVALUABLE"] == 5 and info["N_BH_NON_EVALUABLE"] == 0


def test_08_evaluability_pattern_never_changes_family_size():
    for k in range(6):
        for combo in itertools.combinations(FAMILY, k):
            r = _results({m: S.Status.INSUFFICIENT_SUPPORT for m in combo})
            info = E.apply_fixed_family_bh(r)
            assert info["N_FROZEN_BH_TESTS"] == 5 and info["BH_FAMILY_FROZEN"] == FAMILY
            assert info["N_BH_EVALUABLE"] + info["N_BH_NON_EVALUABLE"] == 5
            assert info["N_BH_NON_EVALUABLE"] == k


def test_unknown_status_or_missing_member_fails_closed():
    r = _results()
    r["DP1_BOX_PRESSURE_MATCHUP"]["status"] = "WEIRD"
    with pytest.raises(ValueError):
        E.apply_fixed_family_bh(r)
    r = _results()
    del r["DP4_GIRONA_CURRENT_TERRITORIAL_REGIME"]
    with pytest.raises(KeyError):
        E.apply_fixed_family_bh(r)


def test_09_no_historical_dataset_is_loaded(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("historical dataset loaded")
    monkeypatch.setattr(E, "load_real_history", boom)
    E.apply_fixed_family_bh(_results({"DP3_ALBACETE_DIRECT_PROGRESSION":
                                      S.Status.NO_QUERY_PROFILE}))


def test_run_all_keeps_five_on_an_unsupported_synthetic_league():
    """End-to-end on a short synthetic league where every design lacks support."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    import test_measurement_apparatus as T
    out = E.run_all(T._hist(T._league(n_rounds=12)),
                    {"home_team_id": "tm_00", "away_team_id": "tm_01", "cutoff_unix": T.CUT},
                    Q.specs())
    assert out["N_FROZEN_BH_TESTS"] == 5 and out["BH_FAMILY_FROZEN"] == FAMILY
    assert out["N_BH_EVALUABLE"] == 0 and out["N_BH_NON_EVALUABLE"] == 5
    for m in FAMILY:
        assert out["results"][m]["multiplicity"]["primary_p_value"] is None
