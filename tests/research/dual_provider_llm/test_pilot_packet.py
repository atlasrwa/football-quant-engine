"""Dual-provider pilot packet tests. SYNTHETIC payloads only: no cache, no network, no LLM."""
from __future__ import annotations

import copy
import json

import pytest

from src.research.dual_provider_llm import packet as P

T = 1_800_000_000          # target kickoff


def _iso(ts):
    import datetime as dt
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _fx(mid, ts, home, away, hg=1, ag=0, neutral=False):
    return {"id": mid, "status": "finished", "utc_date": _iso(ts), "competition_id": "comp_1",
            "season_id": "sn_1", "is_neutral": neutral,
            "home_team": {"id": home, "name": home.upper()},
            "away_team": {"id": away, "name": away.upper()},
            "score": {"home": hg, "away": ag}}


def _stats(mid, crosses_home, crosses_away, tackles_home=5, tackles_away=7):
    passes = {"accurate_crosses": {"all": {"home": crosses_home, "away": crosses_away}}}
    return {"data": {"match_id": mid,
                     "overview": {"total_shots": {"all": {"home": 10, "away": 4}}},
                     "passes": passes,
                     "defending": {"tackles": {"all": {"home": tackles_home,
                                                       "away": tackles_away}}}}}


def _world():
    fixtures, stats = {}, []
    for i in range(12):
        mid = f"mt_{i:03d}"
        home, away = ("tm_a", "tm_x") if i % 2 == 0 else ("tm_y", "tm_a")
        fixtures[mid] = _fx(mid, T - (12 - i) * 86400, home, away)
        stats.append((mid, _stats(mid, i, 100 + i)))
    # a match AT the target kickoff and one after it: must never be used
    fixtures["mt_900"] = _fx("mt_900", T, "tm_a", "tm_x")
    fixtures["mt_901"] = _fx("mt_901", T + 3600, "tm_a", "tm_x")
    stats += [("mt_900", _stats("mt_900", 999, 999)), ("mt_901", _stats("mt_901", 999, 999))]
    # one prior match with a NULL crosses cell for tm_a
    fixtures["mt_902"] = _fx("mt_902", T - 20 * 86400, "tm_a", "tm_x")
    stats.append(("mt_902", _stats("mt_902", None, 3)))
    ok, conf = P.build_stats_map(stats)
    return fixtures, P.normalize_history(fixtures, ok, conf)


def _packet(history, fixtures):
    target = {"id": "mt_target", "utc_date": _iso(T)}
    blocks = {"HOME_TEAM": P.build_team_block(history, "tm_a", "HOME_TEAM", T, "v"),
              "AWAY_TEAM": P.build_team_block(history, "tm_x", "AWAY_TEAM", T, "v")}
    return {"fixture": {"provider_fixture_id": target["id"],
                        "home_team": {"provider_team_id": "tm_a"},
                        "away_team": {"provider_team_id": "tm_x"}},
            "cutoff_unix": T, "selection_rule": {}, "target_outcome_included": False,
            "market_data_included": False, "p_model_included": False,
            "raw_recent_matches": {r: b["raw_recent_matches"] for r, b in blocks.items()},
            "aggregate_evidence": [x for b in blocks.values() for x in b["aggregate_evidence"]],
            "windows": {r: b["windows"] for r, b in blocks.items()}}, blocks


def test_01_history_strictly_before_target_kickoff():
    fixtures, hist = _world()
    rows = P.team_history(hist, "tm_a", T)
    assert rows and all(h.kickoff_unix < T for h in rows)
    assert "mt_900" not in {h.match_id for h in rows}


def test_02_target_and_later_matches_excluded():
    fixtures, hist = _world()
    pk, _ = _packet(hist, fixtures)
    body = json.dumps(pk)
    assert "mt_900" not in body and "mt_901" not in body
    raw_vals = [v for r in P.ROLES for row in pk["raw_recent_matches"][r]
                for v in row["values"].values()]
    assert 999 not in raw_vals and all(a["value"] < 999 for a in pk["aggregate_evidence"])
    c = P.leakage_checks(pk, hist, "mt_target")
    assert c["N_HISTORY_ROWS_AT_OR_AFTER_TARGET_KICKOFF"] == 0 and P.leakage_ok(c)


def test_03_null_stays_missing_never_zero():
    fixtures, hist = _world()
    blk = P.build_team_block(hist, "tm_a", "HOME_TEAM", T, "v")
    agg = {a["evidence_ref"]: a for a in blk["aggregate_evidence"]}
    a = agg["tsa.HOME_TEAM.accurate_crosses.FOR.ALL_PRIOR.ALL"]
    assert a["sample_n"] == 12 and a["null_match_ids"] == ["mt_902"]
    assert a["coverage"] == round(12 / 13, 4)
    # null cell contributes neither a value nor a zero
    # FOR = own side: home rows (even i) -> i ; away rows (odd i) -> 100 + i ; null excluded
    assert a["value"] == round((sum(range(0, 12, 2)) + sum(100 + i for i in range(1, 12, 2)))
                               / 12, 4) == 55.5
    for row in blk["raw_recent_matches"]:
        assert all(v is not None for v in row["values"].values())


def test_04_05_evidence_refs_unique_and_deterministic():
    fixtures, hist = _world()
    p1, _ = _packet(hist, fixtures)
    p2, _ = _packet(copy.deepcopy(hist), fixtures)
    refs = [a["evidence_ref"] for a in p1["aggregate_evidence"]] + [
        k for r in P.ROLES for row in p1["raw_recent_matches"][r] for k in row["values"]]
    assert len(refs) == len(set(refs))
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)


def test_06_07_no_market_pmodel_or_npxg():
    fixtures, hist = _world()
    pk, _ = _packet(hist, fixtures)
    c = P.leakage_checks(pk, hist, "mt_target")
    assert not c["MARKET_DATA_INCLUDED"] and not c["P_MODEL_INCLUDED"] and c["N_NPXG_ITEMS"] == 0
    assert "npxg" not in {x[0] for x in P.CONCEPTS} and "xg" not in {x[0] for x in P.CONCEPTS}
    bad = copy.deepcopy(pk)
    bad["aggregate_evidence"][0]["odds_note"] = "x"
    assert P.leakage_checks(bad, hist, "mt_target")["MARKET_DATA_INCLUDED"] is True
    bad = copy.deepcopy(pk)
    bad["p_model_included"] = True
    with pytest.raises(ValueError):
        P.leakage_checks(bad, hist, "mt_target")


def test_08_09_team_perspective_and_for_against_inversion():
    fixtures, hist = _world()
    blk = P.build_team_block(hist, "tm_a", "HOME_TEAM", T, "v")
    by_id = {r["provider_match_id"]: r for r in blk["raw_recent_matches"]}
    home_row, away_row = by_id["mt_010"], by_id["mt_011"]      # tm_a home / away
    assert home_row["venue"] == "HOME" and away_row["venue"] == "AWAY"
    v = home_row["values"]
    assert v["tsa.HOME_TEAM.raw.mt_010.accurate_crosses.FOR"] == 10
    assert v["tsa.HOME_TEAM.raw.mt_010.accurate_crosses.AGAINST"] == 110
    v = away_row["values"]                                    # tm_a is provider "away"
    assert v["tsa.HOME_TEAM.raw.mt_011.accurate_crosses.FOR"] == 111
    assert v["tsa.HOME_TEAM.raw.mt_011.accurate_crosses.AGAINST"] == 11
    assert v["tsa.HOME_TEAM.raw.mt_011.tackles.FOR"] == 7
    assert v["tsa.HOME_TEAM.raw.mt_011.goals.FOR"] == 0      # a genuine 0 stays 0


def test_10_raw_recent_rows_chronologically_valid():
    fixtures, hist = _world()
    blk = P.build_team_block(hist, "tm_a", "HOME_TEAM", T, "v")
    ks = [r["kickoff_unix"] for r in blk["raw_recent_matches"]]
    assert len(ks) == P.RAW_RECENT_ROWS and ks == sorted(ks, reverse=True) and max(ks) < T
    assert blk["windows"]["RECENT_10|ALL"]["match_ids"] == [
        r["provider_match_id"] for r in blk["raw_recent_matches"]][::-1]


def test_conflicting_stats_payloads_are_never_resolved():
    ok, conf = P.build_stats_map([("a.json", _stats("mt_1", 1, 2)),
                                  ("b.json", _stats("mt_1", 9, 2))])
    assert "mt_1" not in ok and conf["mt_1"] == ["a.json", "b.json"]


def test_neutral_venue_excluded_from_home_away_aggregates():
    fixtures = {"mt_950": _fx("mt_950", T - 100, "tm_a", "tm_x", neutral=True)}
    ok, conf = P.build_stats_map([("n", _stats("mt_950", 1, 2))])
    hist = P.normalize_history(fixtures, ok, conf)
    blk = P.build_team_block(hist, "tm_a", "HOME_TEAM", T, "v")
    assert blk["raw_recent_matches"][0]["venue"] == "NEUTRAL"
    assert not any(a["venue_scope"] in ("HOME", "AWAY") for a in blk["aggregate_evidence"])


def test_tampered_value_is_detected_as_untraceable():
    fixtures, hist = _world()
    pk, _ = _packet(hist, fixtures)
    pk["aggregate_evidence"][0]["value"] += 1
    assert P.leakage_checks(pk, hist, "mt_target")["N_UNTRACEABLE_NUMERIC_EVIDENCE_ITEMS"] >= 1


def test_selection_is_mechanical():
    fixtures, hist = _world()
    sched = [{"id": "mt_z", "status": "scheduled", "utc_date": _iso(T),
              "home_team": {"id": "tm_a"}, "away_team": {"id": "tm_x"}},
             {"id": "mt_b", "status": "scheduled", "utc_date": _iso(T),
              "home_team": {"id": "tm_a"}, "away_team": {"id": "tm_x"}},
             {"id": "mt_past", "status": "scheduled", "utc_date": _iso(T - 10 ** 6),
              "home_team": {"id": "tm_a"}, "away_team": {"id": "tm_x"}}]
    fx, audit = P.select_fixture(sched, hist, as_of_unix=T - 10)
    # tm_x only has 7 prior matches in this world -> nobody eligible
    assert fx is None and [a["provider_fixture_id"] for a in audit] == ["mt_b", "mt_z"]
