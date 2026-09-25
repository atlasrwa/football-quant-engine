from types import SimpleNamespace
from src.research.target_aware_market_panel import predictive_v122 as V

def test_m0_feature_counts_are_frozen_by_family():
    comps=["c1","c2","c3","c4","c5","c6"]
    assert len(V.m0_feature_specs("GOALS",comps)) == 200
    assert len(V.m0_feature_specs("CORNERS",comps)) == 168
    assert len(V.m0_feature_specs("TEAM_TOTALS",comps)) == 216
    assert len(V.m0_feature_specs("BOOKINGS",comps)) == 184

def test_class_c_registry_count_and_family_partition():
    d=V.class_c_by_family()
    assert sum(len(v) for v in d.values()) == 124
    assert set(d) == {"GOALS","CORNERS","TEAM_TOTALS","BOOKINGS"}

def test_primary_target_count_is_fixed():
    ts=V.primary_targets()
    assert len(ts) == 8
    assert {t["family"] for t in ts} == {"GOALS","CORNERS","TEAM_TOTALS","BOOKINGS"}

def test_labeler_semantics_on_synthetic_history_match():
    hm=SimpleNamespace(values={
        "goals":{"home":2,"away":1},
        "corners":{"home":5,"away":4},
        "yellow_cards":{"home":2,"away":2},
    })
    def t(mid,line=None): return {"market_id":mid,"line":line}
    assert V.label_for_target(hm,t("BTTS")) == 1
    assert V.label_for_target(hm,t("TOTAL_GOALS",2.5)) == 1
    assert V.label_for_target(hm,t("HOME_GOALS",1.5)) == 1
    assert V.label_for_target(hm,t("AWAY_GOALS",1.5)) == 0
    assert V.label_for_target(hm,t("TOTAL_CORNERS",9.5)) == 0
    assert V.label_for_target(hm,t("HOME_CORNERS",4.5)) == 1
    assert V.label_for_target(hm,t("TOTAL_YELLOW_CARDS",3.5)) == 1
