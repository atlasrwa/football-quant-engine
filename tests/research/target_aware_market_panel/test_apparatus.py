"""Target-aware market panel apparatus tests. Synthetic caches/panels for behaviour; the frozen
request files for leakage. No outcome of the cohort, no model fit, no LLM, no network."""
from __future__ import annotations

import copy
import glob
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from src.research.dual_provider_llm import packet as DP
from src.research.target_aware_market_panel import cohort_packets as CP
from src.research.target_aware_market_panel import panel as PN
from src.research.target_aware_market_panel import policy as POL
from src.research.target_aware_market_panel import registry as R
from src.research.target_aware_market_panel import templates as TM

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "research/target_aware_market_panel"
KO0 = 1_700_000_000
DAY = 86400


# ─────────────────────────── synthetic provider cache ───────────────────────────
def _iso(ts):
    import datetime as dt
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _statcell(h, a, fh=None):
    fh = fh if fh is not None else (h // 2, a // 2)
    return {"all": {"home": h, "away": a}, "first_half": {"home": fh[0], "away": fh[1]},
            "second_half": {"home": h - fh[0], "away": a - fh[1]}}


def _cache(tmp, n=1100, corners_market=True, break_halves=False):
    rng = np.random.default_rng(0)
    fx = []
    for i in range(n):
        mid = f"mt_{100000 + i}"
        k = KO0 + i * 3600
        fx.append({"id": mid, "status": "finished", "utc_date": _iso(k),
                   "competition_id": "comp_1", "season_id": "sn_1", "is_neutral": False,
                   "home_team": {"id": f"tm_{i % 10}", "name": "H"},
                   "away_team": {"id": f"tm_{(i + 3) % 10}", "name": "A"},
                   "score": {"home": int(rng.integers(0, 4)), "away": int(rng.integers(0, 3))}})
        ch, ca = int(rng.integers(1, 10)), int(rng.integers(1, 9))
        corners = _statcell(ch, ca, (ch // 2, ca // 2))
        if break_halves:                       # halves no longer sum to the full match
            corners["second_half"]["home"] += 1
        stats = {"data": {"match_id": mid, "overview": {
            "corner_kicks": corners,
            "yellow_cards": _statcell(int(rng.integers(0, 4)), int(rng.integers(0, 4))),
            "red_cards": {"all": {"home": None, "away": None}}},
            "attack": {"offsides": _statcell(1, 2)}}}
        (tmp / f"stats_mt_{100000 + i}.json").write_text(json.dumps(stats))
        if i < 20:
            mk = {"total_goals": {"2.5": {"over": {"opening": "1.9", "last_seen": "1.9"},
                                          "under": {"opening": "1.9", "last_seen": "1.9"}}},
                  "team_corners": {"home": {"4.5": {"over": {"opening": "1.8", "last_seen": "1.8"},
                                                    "under": {"opening": "2.0",
                                                              "last_seen": "2.0"}}}}}
            if corners_market:
                mk["match_corners"] = {"9.5": {"over": {"opening": "1.9", "last_seen": "1.9"},
                                               "under": {"opening": "1.9", "last_seen": "1.9"}}}
            cap = k - 3600
            import datetime as dt
            tag = dt.datetime.fromtimestamp(cap, dt.timezone.utc).strftime("%Y%m%dT%H%M%S000000Z")
            (tmp / f"research_odds_{mid}_bet365_{tag}-1.json").write_text(json.dumps(
                {"data": {"match_id": mid, "bookmakers": [{"bookmaker": "Bet365",
                                                           "markets": mk}]}}))
    (tmp / "_all_fixtures_x.json").write_text(json.dumps({"fixtures": fx}))
    return tmp


@pytest.fixture(scope="module")
def reg_pair(tmp_path_factory):
    a = R.build_registry(str(_cache(tmp_path_factory.mktemp("a"))))
    b = R.build_registry(str(_cache(tmp_path_factory.mktemp("b"), corners_market=False)))
    c = R.build_registry(str(_cache(tmp_path_factory.mktemp("c"), break_halves=True)))
    return a, b, c


def _m(reg, mid):
    return {m["market_id"]: m for m in reg["markets"]}[mid]


def test_01_registry_is_provider_derived(reg_pair):
    a, b, _ = reg_pair
    assert a["derived_from_cache_scan"] is True
    assert _m(a, "TOTAL_CORNERS")["raw_price_present"] is True
    assert _m(b, "TOTAL_CORNERS")["raw_price_present"] is False          # market removed
    assert _m(a, "TOTAL_CORNERS")["eligible_for_hypothesis_generation"] is True
    assert _m(b, "TOTAL_CORNERS")["eligible_for_hypothesis_generation"] is False


def test_02_label_and_odds_capability_are_separate(reg_pair):
    a, _, _ = reg_pair
    hc = _m(a, "HOME_CORNERS")
    assert hc["historical_label_supported"] is True and hc["eligible_for_oos_modeling"] is True
    assert hc["raw_price_present"] is True and hc["market_odds_supported"] is False
    assert "no validated adapter" in hc["odds_failure_reason"]
    tg = _m(a, "TOTAL_GOALS")
    assert tg["market_odds_supported"] and tg["genuine_last_before_kickoff_supported"]


def test_03_unsupported_half_markets_fail_closed(reg_pair):
    a, _, c = reg_pair
    assert _m(a, "FH_TOTAL_GOALS")["historical_label_supported"] is False
    assert "half-time score" in _m(a, "FH_TOTAL_GOALS")["failure_reason"]
    assert _m(a, "FH_TOTAL_CORNERS")["historical_label_supported"] is True
    assert _m(a, "FH_TOTAL_CORNERS")["eligible_for_hypothesis_generation"] is False
    assert _m(c, "FH_TOTAL_CORNERS")["historical_label_supported"] is False   # halves != all
    assert _m(a, "TOTAL_CARDS")["historical_label_supported"] is False        # red nulls


def test_04_team_totals_settle_correctly():
    fx = {"score": {"home": 2, "away": 0}}
    st = {"data": {"overview": {"corner_kicks": {"all": {"home": 6, "away": 3}},
                                "yellow_cards": {"all": {"home": 1, "away": 3}}}}}
    assert R.settle("HOME_GOALS", 1.5, fx, st) == 1.0
    assert R.settle("AWAY_GOALS", 0.5, fx, st) == 0.0
    assert R.settle("HOME_CORNERS", 5.5, fx, st) == 1.0
    assert R.settle("AWAY_CORNERS", 3.5, fx, st) == 0.0
    assert R.settle("TOTAL_YELLOW_CARDS", 3.5, fx, st) == 1.0
    assert R.settle("BTTS", None, fx, st) == 0.0
    assert R.settle("HOME_CORNERS", 5.5, fx, {"data": {}}) is None           # null stays null
    assert R.settle("TOTAL_GOALS", 2.0, fx, st) is None                      # not a half-line
    with pytest.raises(ValueError):
        R.settle("TOTAL_CARDS", 3.5, fx, st)


def test_05_thresholds_come_only_from_frozen_line_policy():
    uni = json.loads((OUT / "TARGET_UNIVERSE_V1.json").read_text())
    lp = json.loads((OUT / "MARKET_LINE_POLICY_V1.json").read_text())["lines"]
    for t in uni["targets"]:
        pol = lp[t["market_id"]]
        assert t["line"] == pol["primary_line"] or t["line"] in pol["secondary_lines"]
    fields = set(TM.output_schema()["hypothesis_required_fields"])
    assert not fields & {"line", "threshold", "market_line"}     # the LLM never sets a line


def _synthetic_history():
    fixtures, stats = {}, []
    for i in range(40):
        mid = f"mt_{200000 + i}"
        h, a = ("tm_a", "tm_x") if i % 2 == 0 else ("tm_x", "tm_a")
        fixtures[mid] = {"id": mid, "status": "finished", "utc_date": _iso(KO0 + i * DAY),
                         "competition_id": "comp_1", "season_id": "sn_1", "is_neutral": False,
                         "home_team": {"id": h, "name": h}, "away_team": {"id": a, "name": a},
                         "score": {"home": 1, "away": 1}}
        stats.append((mid, {"data": {"match_id": mid, "overview": {
            "corner_kicks": _statcell(5, 4), "yellow_cards": _statcell(2, 1),
            "total_shots": _statcell(10, 8), "shots_on_target": {"all": {"home": 4,
                                                                         "away": None}}}}}))
    ok, conf = DP.build_stats_map(stats)
    return DP.normalize_history(fixtures, ok, conf)


def _cohort_fx():
    return {"fixture_id": "thestatsapi:mt_999999", "provider_fixture_id": "mt_999999",
            "kickoff_unix": KO0 + 50 * DAY, "kickoff_utc": _iso(KO0 + 50 * DAY),
            "competition_id": "comp_1", "season_id": "sn_1",
            "home_team": {"provider_team_id": "tm_a", "name": "A"},
            "away_team": {"provider_team_id": "tm_x", "name": "X"}}


def test_06_packet_contains_no_target_outcome():
    hist = _synthetic_history()
    pk = CP.build_fixture_packet(hist, _cohort_fx(), KO0 + 45 * DAY, "v")
    assert DP.leakage_ok(pk["leakage_checks"])
    for fam in POL.FAMILY_CONTEXT:
        sl = CP.family_slice(pk, hist, fam)
        body = json.dumps(sl)
        assert "mt_999999" not in body.replace(json.dumps(sl["fixture"]), "")
        assert sl["target_outcome_included"] is False and '"score"' not in body


def _requests():
    return sorted(glob.glob(str(OUT / "out/sol_requests/*/*.json")))


PRICE_KEYS = {"over", "under", "last_seen", "opening", "bookmakers", "bookmaker",
              "available_to_back", "available_to_lay", "main_line_counts", "known_lines"}


def _keys(o):
    return TM._walk_keys(o)


def test_07_08_market_odds_and_p_model_absent_from_sol_requests():
    reqs = _requests()
    assert len(reqs) == 48
    for p in reqs:
        r = json.loads(Path(p).read_text())
        assert r["market_prices_included"] is False and r["p_model_included"] is False
        payload = {"targets": r["targets"], "evidence_packet": r["evidence_packet"],
                   "fixture": r["fixture"]}
        assert not (_keys(payload) & PRICE_KEYS)
        assert "p_model" not in _keys(payload) and "odds" not in json.dumps(payload).lower()


def test_09_every_evidence_ref_resolves():
    for p in _requests()[:8]:
        ev = json.loads(Path(p).read_text())["evidence_packet"]
        refs = [a["evidence_ref"] for a in ev["aggregate_evidence"]] + [
            h["evidence_ref"] for h in ev["half_level_evidence"]] + [
            k for rows in ev["raw_recent_matches"].values() for row in rows for k in row["values"]]
        assert sorted(refs) == ev["evidence_ref_index"] and len(refs) == len(set(refs))


def _hyp(**over):
    h = {"hypothesis_id": "H1", "target": "TOTAL_CORNERS_OVER_9_5", "market_family": "CORNERS",
         "fixture_context_observation": "x", "predictive_mechanism": "x",
         "future_target_label": "x", "evidence_refs": ["r1"], "pre_match_feature_inputs": ["x"],
         "feature_template": {"template_type": "MULTI_DIMENSION_MATCHUP",
                              "combine": "MEAN_PRODUCT", "components": [
                                  {"side": "HOME", "metric": "accurate_crosses",
                                   "perspective": "FOR", "window": "W10", "period": "FULL_MATCH"},
                                  {"side": "AWAY", "metric": "accurate_crosses",
                                   "perspective": "AGAINST", "window": "W10",
                                   "period": "FULL_MATCH"},
                                  {"side": "HOME", "metric": "touches_in_box",
                                   "perspective": "FOR", "window": "W10", "period": "FULL_MATCH"},
                                  {"side": "AWAY", "metric": "touches_in_box",
                                   "perspective": "AGAINST", "window": "W10",
                                   "period": "FULL_MATCH"}]},
         "opponent_profile_dimensions": [], "why_baseline_may_miss_it": "x",
         "panel_generalization_rule": "x", "deterministic_test_request": "x",
         "confounders": [], "provider_constraints": "x", "required_resolution": "MATCH",
         "same_match_information_required": False, "abstain_reason": None}
    h.update(over)
    return h


def _cls(h, seen=None):
    return TM.classify(h, target_ids={"TOTAL_CORNERS_OVER_9_5"}, family="CORNERS",
                       evidence_refs={"r1"}, seen_keys=seen if seen is not None else set())[0]


def test_10_feature_inputs_must_be_pre_match():
    h = _hyp()
    h["feature_template"]["components"][0]["window"] = "THIS_MATCH"
    assert _cls(h) == "F_SAME_MATCH_LEAKAGE"
    assert set(TM.WINDOWS) == {"W5", "W10", "SEASON_TO_DATE", "VENUE_SEASON_TO_DATE"}


def test_11_same_match_predictor_proposal_is_rejected():
    assert _cls(_hyp(same_match_information_required=True)) == "F_SAME_MATCH_LEAKAGE"


def test_novelty_classes_are_deterministic():
    assert _cls(_hyp()) == "C_CONTEXTUAL_TEMPLATE"
    seen = set()
    _cls(_hyp(), seen)
    assert _cls(_hyp(hypothesis_id="H2"), seen) == "G_DUPLICATE_TEMPLATE"
    one = {"template_type": "ROLLING_PROFILE", "combine": "IDENTITY", "components": [
        {"side": "HOME", "metric": "corners", "perspective": "FOR", "window": "W5",
         "period": "FULL_MATCH"}]}
    assert _cls(_hyp(feature_template=one)) == "A_BASELINE_EQUIVALENT"
    two = {"template_type": "PAIRWISE_COMBINATION", "combine": "PRODUCT",
           "components": one["components"] * 2}
    assert _cls(_hyp(feature_template=two)) == "B_SIMPLE_INTERACTION"
    bad = copy.deepcopy(_hyp())
    bad["feature_template"]["components"][0]["metric"] = "blocked_shots"
    bad["feature_template"]["components"][1]["metric"] = "blocked_shots"
    assert _cls(bad) == "E_PROVIDER_UNSUPPORTED"
    assert _cls(_hyp(evidence_refs=["nope"])) == "D_UNMEASURABLE"


# ─────────────────────────── synthetic panel ───────────────────────────
def _panel_rows(n_teams=8, rounds=40, seed=3, extra=()):
    rng = np.random.default_rng(seed)
    rows = []
    for rd in range(rounds):
        order = rng.permutation(n_teams)
        for j in range(0, n_teams, 2):
            h, a = f"tm_{order[j]}", f"tm_{order[j + 1]}"
            mid, k = f"m{rd}_{j}", KO0 + rd * 7 * DAY + j
            vals = {}
            for met in ("corners", "accurate_crosses", "touches_in_box", "shots", "goals",
                        "yellow_cards", "fouls", "possession"):
                vals[(met, "FULL_MATCH")] = (float(rng.integers(0, 12)), float(rng.integers(0, 12)))
            vals[("corners", "FIRST_HALF")] = (float(rng.integers(0, 6)), None)
            for team, opp, venue, flip in ((h, a, "HOME", False), (a, h, "AWAY", True)):
                v = tuple(sorted(((k2, (b, f) if flip else (f, b)) for k2, (f, b)
                                  in vals.items()), key=lambda t: t[0]))
                rows.append(PN.Row(mid, k, "comp_1", "sn_1", team, opp, venue, v))
    return rows + list(extra)


TEMPLATES = [
    {"template_type": "ROLLING_PROFILE", "combine": "IDENTITY", "components": [
        {"side": "HOME", "metric": "corners", "perspective": "FOR", "window": "W5",
         "period": "FULL_MATCH"}]},
    {"template_type": "PAIRWISE_COMBINATION", "combine": "PRODUCT", "components": [
        {"side": "HOME", "metric": "corners", "perspective": "FOR", "window": "W10",
         "period": "FULL_MATCH"},
        {"side": "AWAY", "metric": "corners", "perspective": "AGAINST", "window": "W10",
         "period": "FULL_MATCH"}]},
    _hyp()["feature_template"],
    {"template_type": "OPPONENT_SIMILARITY_CONDITIONAL", "combine": "SIMILARITY_CONDITIONAL",
     "components": [], "similarity": {
         "subject_side": "HOME", "subject_metric": "corners", "subject_perspective": "FOR",
         "profile_side": "AWAY", "profile_dimensions": [
             {"metric": "accurate_crosses", "perspective": "AGAINST"},
             {"metric": "touches_in_box", "perspective": "AGAINST"}]}},
    {"template_type": "STATE_DEVIATION", "combine": "RECENT_MINUS_LONG_RUN", "components": [],
     "state": {"side": "AWAY", "dimensions": [{"metric": "possession", "perspective": "FOR"},
                                              {"metric": "shots", "perspective": "FOR"}]}},
]


def _fx(k, home="tm_0", away="tm_1", mid="anything_123"):
    return {"match_id": mid, "kickoff": k, "competition_id": "comp_1", "home_team_id": home,
            "away_team_id": away}


def test_12_panel_template_instantiates_on_arbitrary_fixture_ids():
    h = PN.PanelHistory(_panel_rows(), KO0 + 400 * DAY)
    got = 0
    for tpl in TEMPLATES:
        for mid, home, away in (("x1", "tm_0", "tm_1"), ("zz_9", "tm_5", "tm_2")):
            v = PN.instantiate(tpl, h, _fx(KO0 + 250 * DAY, home, away, mid))
            assert v is None or np.isfinite(v)
            got += v is not None
    assert got >= 8


def test_13_14_only_prior_data_and_future_cannot_alter_past_features():
    t = KO0 + 200 * DAY
    base = _panel_rows()
    fut = [PN.Row("fut", t + 1, "comp_1", "sn_1", "tm_0", "tm_1", "HOME",
                  tuple(((m, "FULL_MATCH"), (1e6, 1e6)) for m in ("corners", "accurate_crosses",
                                                                   "touches_in_box", "shots",
                                                                   "possession")))]
    at = [PN.Row("at", t, "comp_1", "sn_1", "tm_0", "tm_1", "HOME",
                 tuple(((m, "FULL_MATCH"), (1e6, 1e6)) for m in ("corners", "shots")))]
    h1 = PN.PanelHistory(base, KO0 + 400 * DAY)
    h2 = PN.PanelHistory(base + fut + at, KO0 + 400 * DAY)
    for tpl in TEMPLATES:
        assert PN.instantiate(tpl, h1, _fx(t)) == PN.instantiate(tpl, h2, _fx(t))
    with pytest.raises(PN.PITViolation):
        PN.PanelHistory(base, KO0 + 100 * DAY).prior("tm_0", KO0 + 300 * DAY)


def test_15_style_similarity_is_separate_from_strength(monkeypatch):
    h = PN.PanelHistory(_panel_rows(rounds=80), KO0 + 800 * DAY)
    fx = _fx(KO0 + 500 * DAY)
    monkeypatch.setattr(PN.PanelHistory, "strength", lambda self, t, c, b: 0.0)
    d1 = PN.similarity_detail(TEMPLATES[3], h, fx)
    monkeypatch.setattr(PN.PanelHistory, "strength",
                        lambda self, t, c, b: float(int(t.split("_")[1])))
    d2 = PN.similarity_detail(TEMPLATES[3], h, fx)
    assert d1 is not None and d1["value"] == d2["value"]          # strength never in distance
    assert d1["neighbor_ids"] == d2["neighbor_ids"]
    assert d1["diagnostic"] != d2["diagnostic"]                   # but it IS reported
    monkeypatch.undo()
    bad = _hyp(feature_template=copy.deepcopy(TEMPLATES[3]))
    bad["feature_template"]["similarity"]["profile_dimensions"][0]["metric"] = "goals"
    assert _cls(bad) == "D_UNMEASURABLE"
    d = PN.style_strength_correlation(h, [_fx(KO0 + (100 + i) * DAY, f"tm_{i % 8}",
                                             f"tm_{(i + 1) % 8}") for i in range(60)],
                                      [{"metric": "corners", "perspective": "AGAINST"}], "AWAY")
    assert "corners.AGAINST" in d


def test_16_null_remains_null():
    h = PN.PanelHistory(_panel_rows(), KO0 + 400 * DAY)
    c = {"side": "HOME", "metric": "corners", "perspective": "AGAINST", "window": "W5",
         "period": "FIRST_HALF"}                                 # always None in the panel
    assert PN.rolling(h, "tm_0", "HOME", c, KO0 + 250 * DAY) is None
    fx = {"score": {"home": None, "away": 1}}
    assert R.settle("TOTAL_GOALS", 2.5, fx, None) is None


def test_17_target_family_slicing_is_deterministic():
    hist = _synthetic_history()
    pk = CP.build_fixture_packet(hist, _cohort_fx(), KO0 + 45 * DAY, "v")
    a = CP.family_slice(pk, hist, "CORNERS")
    b = CP.family_slice(copy.deepcopy(pk), hist, "CORNERS")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert {x["canonical_concept"] for x in a["aggregate_evidence"]} <= set(
        POL.FAMILY_CONTEXT["CORNERS"])


def test_18_baseline_coverage_has_no_coefficients_or_performance():
    b = POL.baseline_semantic_coverage()
    ks = _keys(b)
    for bad in ("coef", "coefficient", "coefficients", "auc", "logloss", "log_loss", "brier",
                "p_value", "performance", "oos_results"):
        assert bad not in ks
    assert b["contains_no_coefficients"] and b["contains_no_performance"]
    nums = []

    def walk(o):
        if isinstance(o, dict):
            [walk(v) for v in o.values()]
        elif isinstance(o, list):
            [walk(v) for v in o]
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            nums.append(o)
    walk(b)
    assert nums == []


def test_19_llm_output_cannot_carry_probability_edge_stake():
    for k in ("probability", "edge", "stake", "p_model", "fair_odds", "confidence"):
        assert _cls(_hyp(**{k: 0.6})) == "D_UNMEASURABLE"
    assert TM.forbidden_content({"a": {"Stake": 1}}) == ["stake"]


def test_20_prior_artifacts_untouched():
    out = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only",
                          "13f10bc1762212bf3ee35e6383019205a8005fd3", "--",
                          "research/item6", "src/research/item6", "research/dual_provider_llm",
                          "src/research/dual_provider_llm", "research/target_aware_sol"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == ""


def test_21_champion_unchanged():
    p = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")
    assert hashlib.sha256(p.read_bytes()).hexdigest() == (
        "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9")


def test_validated_adapters_exist_in_provider_code():
    import inspect
    from src.research.thestatsapi import closing_provider, odds_normalizer
    ns, cs = inspect.getsource(odds_normalizer), inspect.getsource(closing_provider)
    assert "def _extract_total_goals" in ns and "def _extract_1x2" in ns and "BTTS" in ns
    assert "def _total_goals" in cs and "def _match_odds" in cs
    assert set(R.VALIDATED_CLOSING_ADAPTERS) <= set(R.VALIDATED_PRE_MATCH_ADAPTERS)


def test_half_periods_limited_to_family_half_context():
    h = _hyp()
    for c in h["feature_template"]["components"]:
        c["metric"], c["period"] = "shots", "FIRST_HALF"           # shots halves: GOALS only
    assert _cls(h) == "E_PROVIDER_UNSUPPORTED"
    one = {"template_type": "ROLLING_PROFILE", "combine": "IDENTITY", "components": [
        {"side": "HOME", "metric": "corners", "perspective": "FOR", "window": "W10",
         "period": "FIRST_HALF"}]}
    assert _cls(_hyp(feature_template=one)) == "A_BASELINE_EQUIVALENT"   # half rolling in M0


def test_requests_carry_primary_lines_only():
    for p in _requests():
        r = json.loads(Path(p).read_text())
        assert all(t["line_role"] == "PRIMARY" for t in r["targets"])
        assert len({t["market_id"] for t in r["targets"]}) == len(r["targets"])


def test_cohort_compile_dedupes_across_fixtures_in_fixed_order():
    def req(fid):
        return {"fixture": {"fixture_id": f"thestatsapi:{fid}", "provider_fixture_id": fid},
                "family": "CORNERS", "targets": [{"target_id": "TOTAL_CORNERS_OVER_9_5",
                                                  "market_id": "TOTAL_CORNERS"}],
                "evidence_packet": {"evidence_ref_index": ["r1"]}}
    resp = {"hypotheses": [_hyp()]}
    out = TM.compile_cohort([(resp, req("mt_2")), (copy.deepcopy(resp), req("mt_1"))])
    cls = [(c["fixture_id"], h["class"]) for c in out["compiled"] for h in c["classified"]]
    assert cls == [("thestatsapi:mt_1", "C_CONTEXTUAL_TEMPLATE"),
                   ("thestatsapi:mt_2", "G_DUPLICATE_TEMPLATE")]
    assert out["n_class_c"] == 1


def test_fold_manifest_is_frozen_outcome_free_and_flags_cohort_teams():
    fm = json.loads((OUT / "TARGET_AWARE_FOLD_MANIFEST_V1.json").read_text())
    assert fm["reads_outcomes"] is False and fm["n_panel_rows"] > 5000
    keys = set().union(*(r.keys() for r in fm["rows"]))
    assert keys == {"match_id", "kickoff", "competition_id", "fold", "designation",
                    "involves_cohort_team"}
    assert fm["rows_sha256"] == hashlib.sha256(json.dumps(fm["rows"], sort_keys=True)
                                               .encode()).hexdigest()
    assert 0 < fm["n_oos_primary_excluding_cohort_teams"] < fm["n_oos_all"]
    man = json.loads((OUT / "TARGET_AWARE_PANEL_MANIFEST_V1.json").read_text())
    assert man["fold_manifest_rows_sha256"] == fm["rows_sha256"]
    assert man["half_level_evidence_rederivation_mismatches"] == 0
