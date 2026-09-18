"""P1 INFERENCE. The 4/14/15 regression cases the mission names explicitly, plus the
qualifying-block rule and the pair-level S-v-R estimand."""
from __future__ import annotations

from src.research.hypothesis_v8c import aggregate as AG


def _rec(fid, arm, hid, score, status=AG.SC.SCORE_OK):
    return {"fixture_id": fid, "arm": arm, "hypothesis_id": hid, "status": status,
            "score": score, "reason": ""}


# ---- the three named regression cases ------------------------------------------------------
def test_four_paired_across_four_blocks_is_insufficient():
    """THE case the mission names: must be INSUFFICIENT_CLUSTERS_FOR_INFERENCE, never EXACT."""
    per_block = {f"block_{i:03d}": 1 for i in range(4)}
    r = AG.inference_reachability(per_block)
    assert r["n_paired_total"] == 4
    assert r["n_qualifying_blocks"] == 0
    assert r["expected_inference_status"] == AG.INSUFFICIENT_CLUSTERS
    assert r["exact_enumeration_available"] is False
    assert r["n_sign_vectors"] == 0


def test_fourteen_cohort_fixtures_cannot_support_exact_inference():
    b = AG.chronological_blocks([str(i) for i in range(14)])
    assert b["target_n_blocks"] == 0
    assert b["below_exact_inference_size"] is True
    r = AG.inference_reachability({"block_000": 14})
    assert r["n_qualifying_blocks"] == 1
    assert r["expected_inference_status"] == AG.INSUFFICIENT_CLUSTERS


def test_fifteen_cohort_fixtures_reach_exact_inference():
    b = AG.chronological_blocks([str(i) for i in range(15)])
    assert b["target_n_blocks"] == 3
    assert b["block_size"] == 5
    assert b["n_blocks_actual"] == 3
    r = AG.inference_reachability({"block_000": 5, "block_001": 5, "block_002": 5})
    assert r["n_qualifying_blocks"] == 3
    assert r["expected_inference_status"] == "EXACT"
    assert r["n_sign_vectors"] == 8


# ---- the qualifying rule itself -------------------------------------------------------------
def test_block_with_four_paired_differences_does_not_qualify():
    r = AG.inference_reachability({"block_000": 4, "block_001": 5, "block_002": 5})
    assert r["n_qualifying_blocks"] == 2
    assert r["expected_inference_status"] == AG.INSUFFICIENT_CLUSTERS


def test_no_paired_fixtures_is_its_own_state():
    r = AG.inference_reachability({})
    assert r["expected_inference_status"] == AG.NO_PAIRED_EVALUABLE_FIXTURES


def test_no_p_value_is_invented_when_underpowered():
    per_fixture = [{"fixture_id": str(i), "D_R": 0.5} for i in range(4)]
    f2b = {str(i): f"block_{i:03d}" for i in range(4)}
    ep = AG.endpoint(per_fixture, "D_R", f2b, label="t")
    assert ep["inference"]["inference_status"] == AG.INSUFFICIENT_CLUSTERS
    assert ep["inference"]["primary_p_value"] is None
    assert ep["paired_n_all"] == 4
    # the descriptive mean is still reported, explicitly labelled as not the inferential set
    assert ep["descriptive_all_fixtures"]["mean_diff"] == 0.5


def test_exact_inference_returns_a_real_p_value():
    per_fixture, f2b = [], {}
    for b in range(3):
        for j in range(5):
            fid = f"f{b}_{j}"
            per_fixture.append({"fixture_id": fid, "D_R": 1.0 + 0.1 * j})
            f2b[fid] = f"block_{b:03d}"
    ep = AG.endpoint(per_fixture, "D_R", f2b, label="t")
    assert ep["inference"]["inference_status"] == "EXACT"
    assert ep["inference"]["primary_p_value"] is not None
    assert 0.0 <= ep["inference"]["primary_p_value"] <= 1.0
    assert ep["paired_n_in_inference"] == 15


# ---- the pair-level estimand ------------------------------------------------------------------
def test_sr_is_matched_pair_not_arm_mean():
    """The defect: mean(3 surviving S) vs mean(1 surviving R). Pair-level must drop the PAIR."""
    records = [
        _rec("T", "S", "s1", 10.0), _rec("T", "S", "s2", 20.0), _rec("T", "S", "s3", 30.0),
        _rec("T", "R", "r1", 1.0),
        _rec("T", "R", "r2", None, AG.SC.SCORE_INSUFFICIENT_SUPPORT),
        _rec("T", "R", "r3", None, AG.SC.SCORE_INSUFFICIENT_SUPPORT),
    ]
    triples = {"T": [{"s_id": "s1", "r_id": "r1", "tier": "EXACT", "status": "MATCHED"},
                     {"s_id": "s2", "r_id": "r2", "tier": "EXACT", "status": "MATCHED"},
                     {"s_id": "s3", "r_id": "r3", "tier": "EXACT", "status": "MATCHED"}]}
    pf = AG.per_fixture_endpoints(records, ["T"], triples)[0]
    # only pair 1 survives -> 10.0 - 1.0, NOT mean(10,20,30) - mean(1)
    assert pf["n_pairs_frozen"] == 3
    assert pf["n_pairs_surviving"] == 1
    assert pf["D_R"] == 9.0
    assert pf["D_R"] != (60.0 / 3) - 1.0


def test_a_dropped_pair_does_not_drop_the_fixture():
    records = [
        _rec("T", "S", "s1", 10.0), _rec("T", "S", "s2", 20.0),
        _rec("T", "R", "r1", 4.0),
        _rec("T", "R", "r2", None, AG.SC.SCORE_UNDEFINED),
    ]
    triples = {"T": [{"s_id": "s1", "r_id": "r1", "tier": "EXACT", "status": "MATCHED"},
                     {"s_id": "s2", "r_id": "r2", "tier": "EXACT", "status": "MATCHED"}]}
    pf = AG.per_fixture_endpoints(records, ["T"], triples)[0]
    assert pf["D_R"] == 6.0
    assert len(pf["dropped_pairs"]) == 1
    assert pf["dropped_pairs"][0]["reason"] == "R_NOT_OK"


def test_unmatched_pair_is_recorded_not_silently_dropped():
    records = [_rec("T", "S", "s1", 10.0)]
    triples = {"T": [{"s_id": "s1", "r_id": None, "tier": "UNMATCHED",
                      "status": "UNMATCHED_DISTINCT_CONTROL"}]}
    pf = AG.per_fixture_endpoints(records, ["T"], triples)[0]
    assert pf["D_R"] is None
    assert pf["dropped_pairs"][0]["reason"] == "UNMATCHED_DISTINCT_CONTROL"


def test_sh_stays_arm_mean_and_is_named_differently():
    records = [_rec("T", "S", "s1", 10.0), _rec("T", "S", "s2", 20.0),
               _rec("T", "H", "h1", 5.0)]
    pf = AG.per_fixture_endpoints(records, ["T"], {"T": []})[0]
    assert pf["D_H"] == 15.0 - 5.0
    st = AG.version_stamp()
    assert "MATCHED-PAIR" in st["estimands"]["S_vs_R"]
    assert "ARM-MEAN" in st["estimands"]["S_vs_H"]
    assert st["estimands_are_not_comparable"] is True


def test_null_is_never_zero():
    """An arm with zero SCORE_OK yields None, never 0.0, and the fixture drops listwise."""
    records = [_rec("T", "S", "s1", None, AG.SC.SCORE_INSUFFICIENT_SUPPORT),
               _rec("T", "H", "h1", 5.0)]
    pf = AG.per_fixture_endpoints(records, ["T"], {"T": []})[0]
    assert pf["S_arm_mean"] is None
    assert pf["D_H"] is None
    assert pf["D_R"] is None


def test_one_value_per_fixture_per_endpoint():
    records, triples = [], {"T": []}
    for i in range(5):
        records += [_rec("T", "S", f"s{i}", float(i)), _rec("T", "R", f"r{i}", 0.0)]
        triples["T"].append({"s_id": f"s{i}", "r_id": f"r{i}", "tier": "EXACT",
                             "status": "MATCHED"})
    pf = AG.per_fixture_endpoints(records, ["T"], triples)
    assert len(pf) == 1
    ep = AG.endpoint(pf, "D_R", {"T": "block_000"}, label="t")
    assert ep["paired_n_all"] == 1, "a fixture contributed more than one endpoint value"
