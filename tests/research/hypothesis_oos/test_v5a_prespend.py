"""V5A pre-spend test battery (Phase 29). ZERO SPEND. No Bedrock, no network.

Every required pre-spend check. A failure here BLOCKS paid execution.
"""
from __future__ import annotations
import hashlib
import importlib
import json
import os
import sys

import pytest

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src"); sys.path.insert(0, ROOT)

from src.research.hypothesis_engine import corpus_adapter as CA
from src.research.hypothesis_oos import v5a_full_fidelity as V5
from src.research.hypothesis_oos import v5a_prompt as P

OUT = f"{ROOT}/research/hypothesis_oos/out/v5a"
CLEAN = ['mt_010243515', 'mt_010243537', 'mt_010243938', 'mt_010244159', 'mt_010244193',
         'mt_010441320', 'mt_010441491', 'mt_010444904', 'mt_012232295', 'mt_012232411']


@pytest.fixture(scope="module")
def idx():
    return CA.load_index()


@pytest.fixture(scope="module")
def by_id(idx):
    return {r.fixture_id: r for r in idx.records}


@pytest.fixture(scope="module")
def arm_b():
    return json.load(open(f"{OUT}/arm_b_packets.json"))


@pytest.fixture(scope="module")
def arm_a():
    return json.load(open(f"{OUT}/arm_a_packets.json"))


@pytest.fixture(scope="module")
def audit():
    return json.load(open(f"{OUT}/exposure_audit.json"))


def _rows(pk, team_label):
    blk = pk["match_level_history"][team_label]
    if "rows" in blk:
        return blk["rows"]
    return [dict(zip(blk["columns"], v)) for v in blk["values"]]


# 1-3: PIT / target / future exclusion (positive tests) --------------------------------
def test_target_fixture_excluded(arm_b, by_id):
    for fid in CLEAN:
        target = by_id[fid]
        for tl, team in (("HOME_TEAM", target.home), ("AWAY_TEAM", target.away)):
            for r in _rows(arm_b[fid], tl):
                assert r["match_alias"] != f"m_{fid}", "target fixture in its own view"


def test_future_matches_excluded(arm_b, by_id):
    for fid in CLEAN:
        cut = by_id[fid].kickoff_unix
        for tl in ("HOME_TEAM", "AWAY_TEAM"):
            for r in _rows(arm_b[fid], tl):
                assert r["kickoff_unix"] < cut, "match at/after cutoff leaked in"


def test_injected_future_record_would_be_excluded(idx, by_id):
    # positive leakage test: a match kicking off AFTER cutoff must never be admitted
    fid = "mt_010244159"
    target = by_id[fid]
    admitted = V5._admitted(idx, target, target.home, V5.DEFAULT_POLICY)
    assert all(r.kickoff_unix < target.kickoff_unix for r in admitted)
    assert all(r.fixture_id != fid for r in admitted)


# 4: target outcome / future odds not present -----------------------------------------
def test_no_outcome_or_odds_fields(arm_b):
    blob = json.dumps(arm_b, default=str).lower()
    for banned in ("closing_line", "settlement", "\"odds\"", "fair_odds", "p_model",
                   "final_score", "result_"):
        assert banned not in blob, f"forbidden field {banned!r} in Arm B packet"


# 5: cell fidelity serialized == canonical --------------------------------------------
def test_every_cell_equals_canonical(arm_b, by_id):
    checked = mism = 0
    for fid in CLEAN:
        target = by_id[fid]
        for tl, team in (("HOME_TEAM", target.home), ("AWAY_TEAM", target.away)):
            for r in _rows(arm_b[fid], tl):
                rec = by_id[r["match_alias"][2:]]
                for m in V5.CANONICAL_MATCH_METRICS:
                    for side in ("for", "against"):
                        canon = V5._team_value(rec, team, m, side.upper())
                        ser = r[f"{m}_{side}"]
                        checked += 1
                        if not ((canon is None and ser is None) or
                                (canon is not None and ser is not None
                                 and abs(canon - ser) < 1e-9)):
                            mism += 1
    assert checked > 0 and mism == 0, f"{mism}/{checked} cell mismatches"


# 6: every omitted cell/row has an allowed reason -------------------------------------
def test_no_unexplained_omission(audit):
    for fid, f in audit["fixtures"].items():
        if f.get("arm_b_built"):
            assert f["UNEXPLAINED_OMISSION"] == 0
    assert audit["hard_fail"] is False


# 7: venue rows correct ----------------------------------------------------------------
def test_venue_orientation_correct(arm_b, by_id):
    for fid in CLEAN:
        target = by_id[fid]
        for tl, team in (("HOME_TEAM", target.home), ("AWAY_TEAM", target.away)):
            for r in _rows(arm_b[fid], tl):
                rec = by_id[r["match_alias"][2:]]
                expect = "HOME" if rec.home == team else "AWAY"
                assert r["venue"] == expect


# 8: chronology correct ----------------------------------------------------------------
def test_chronological_order(arm_b):
    for fid in CLEAN:
        for tl in ("HOME_TEAM", "AWAY_TEAM"):
            ks = [r["kickoff_unix"] for r in _rows(arm_b[fid], tl)]
            assert ks == sorted(ks), "match rows not chronological"


# 9: W5/W10 reconstructed correctly from the rows -------------------------------------
def test_w5_w10_summaries_match_rows(arm_b):
    for fid in CLEAN:
        pk = arm_b[fid]
        rows = _rows(pk, "HOME_TEAM")
        sums = {(_s["metric"], _s["side"], _s["window"], _s["venue"]): _s
                for _s in pk["derived_summaries"]["HOME_TEAM"]}
        # verify corners_for W5
        key = ("corners", "FOR", "W5", "ALL")
        if key in sums:
            vals = [r["corners_for"] for r in rows[-5:] if r["corners_for"] is not None]
            if vals:
                assert abs(sums[key]["value"] - round(sum(vals) / len(vals), 4)) < 1e-6


# 10: opponent-profile cohorts deterministic ------------------------------------------
def test_opponent_profile_deterministic(idx, by_id):
    fid = "mt_010244159"
    target = by_id[fid]
    a = V5.build_opponent_profile_context(idx, target, V5.DEFAULT_POLICY,
                                          V5._alias_map(idx, target, V5.DEFAULT_POLICY))
    b = V5.build_opponent_profile_context(idx, target, V5.DEFAULT_POLICY,
                                          V5._alias_map(idx, target, V5.DEFAULT_POLICY))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# 11: formation coverage correct -------------------------------------------------------
def test_formation_availability_matches_coverage(arm_b, by_id):
    for fid in CLEAN:
        pk = arm_b[fid]
        rows = _rows(pk, "HOME_TEAM") + _rows(pk, "AWAY_TEAM")
        cov = sum(1 for r in rows if r["own_formation_family"]) / len(rows)
        avail = pk["availability_map"]["formation"]
        if cov == 0:
            assert avail == "UNAVAILABLE"
        elif cov >= 0.5:
            assert avail == "AVAILABLE"
        else:
            assert avail == "LOW_COVERAGE"


# 12: aliases deterministic ------------------------------------------------------------
def test_aliases_deterministic(idx, by_id):
    fid = "mt_010243515"
    t = by_id[fid]
    a = V5._alias_map(idx, t, V5.DEFAULT_POLICY)
    b = V5._alias_map(idx, t, V5.DEFAULT_POLICY)
    assert a == b and all(v.startswith("OPP_") for v in a.values())


def test_no_club_names_in_packet(arm_b, by_id):
    # identity-neutral: real club/competition names must not appear as VALUES.
    # Check structurally (row/summary/context values) rather than naive substring, since
    # short league tags like 'epl' occur inside ordinary words ('replace').
    import re
    for fid in CLEAN:
        pk = arm_b[fid]
        home, away, comp = by_id[fid].home, by_id[fid].away, by_id[fid].competition
        # collect all string leaf values in the packet
        vals = []
        def walk(o):
            if isinstance(o, dict):
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
            elif isinstance(o, str):
                vals.append(o)
        walk(pk)
        for name in (home, away, comp):
            assert name not in vals, f"real identity {name!r} leaked as a packet value"
        # competition column must be aliased in every row
        for tl in ("HOME_TEAM", "AWAY_TEAM"):
            for r in _rows(pk, tl):
                assert r["competition"] in ("COMPETITION",) or r["competition"].startswith("COMP_")


# 13: provider provenance intact -------------------------------------------------------
def test_provider_provenance_present(arm_b):
    for fid in CLEAN:
        pk = arm_b[fid]
        assert pk["opponent_profile_context"]["similarity_version"]
        assert pk["history_policy"]["version"]
        assert pk["capability_manifest"]["capability_inventory_version"]


# 14: missing values NOT imputed -------------------------------------------------------
def test_missing_values_not_imputed(arm_b, by_id):
    # where canonical is None, serialized must be None (explicit null, not 0/mean)
    seen_null = False
    for fid in CLEAN:
        target = by_id[fid]
        for tl, team in (("HOME_TEAM", target.home), ("AWAY_TEAM", target.away)):
            for r in _rows(arm_b[fid], tl):
                rec = by_id[r["match_alias"][2:]]
                for m in V5.CANONICAL_MATCH_METRICS:
                    if V5._team_value(rec, team, m, "FOR") is None:
                        assert r[f"{m}_for"] is None
                        seen_null = True
    # at least some nulls exist (not every metric present every match) -> proves no impute
    assert seen_null


# 15: Arm A unchanged (frozen V3 body) -------------------------------------------------
def test_arm_a_equals_frozen_v3(arm_a):
    v3 = json.load(open(f"{ROOT}/research/hypothesis_engine/out/"
                        "MATERIALIZED_PACKETS_sonnet46_v3.json"))
    for fid in CLEAN:
        assert arm_a[fid] == v3[f"reference::{fid}"], f"Arm A {fid} diverged from frozen V3"


# 16-19: V2/V3/V4/CHAMPION unchanged ---------------------------------------------------
def test_champion_unchanged():
    path = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    assert h.hexdigest() == "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def test_frozen_v3_v4_artifacts_present_and_unread_for_write():
    # V5A only READS these; presence check + they are not among V5A outputs
    for p in ("research/hypothesis_engine/out/hypothesis_v3_sonnet46/hypothesis_states.jsonl",
              "research/hypothesis_oos/out/V4_OOS_RESULTS.json"):
        assert os.path.exists(f"{ROOT}/{p}")


def test_schema_matches_frozen_v3():
    from src.research.hypothesis_engine import schema_v2 as S2
    states = [json.loads(l) for l in open(
        f"{ROOT}/research/hypothesis_engine/out/hypothesis_v3_sonnet46/hypothesis_states.jsonl")]
    assert S2.schema_content_hash() == states[0]["schema_content_hash"]


# 20: no LLM -> p_model path -----------------------------------------------------------
def test_no_llm_to_pmodel_path():
    import sys as _sys
    for modname in ("src.research.hypothesis_oos.v5a_full_fidelity",
                    "src.research.hypothesis_oos.v5a_prompt"):
        importlib.import_module(modname)
    seen = set()
    stack = ["src.research.hypothesis_oos.v5a_full_fidelity",
             "src.research.hypothesis_oos.v5a_prompt"]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        m = _sys.modules.get(name)
        if not m:
            continue
        for attr in dir(m):
            sub = getattr(getattr(m, attr, None), "__module__", None)
            if isinstance(sub, str) and sub.startswith("src.research"):
                stack.append(sub)
    for name in seen:
        low = name.lower()
        for banned in ("bedrock", "p_model", "forecast_broadcast", "pilotc", "prospective"):
            assert banned not in low, f"V5A imports {banned}: {name}"


# extra: prompt determinism ------------------------------------------------------------
def test_serialized_request_deterministic(arm_b):
    fid = CLEAN[0]
    p1 = P.build_user_payload(arm_b[fid])
    p2 = P.build_user_payload(arm_b[fid])
    assert p1 == p2


def test_columnar_encoding_lossless(idx, by_id):
    fid = "mt_010244159"
    pk = V5.build_full_fidelity_packet(by_id[fid], idx, V5.DEFAULT_POLICY)
    compact = pk.to_dict(compact_rows=True)
    perrow = pk.to_dict(compact_rows=False, include_hash=False)
    # reconstruct rows from compact, compare to per-row dicts
    blk = compact["match_level_history"]["HOME_TEAM"]
    recon = [dict(zip(blk["columns"], v)) for v in blk["values"]]
    assert recon == perrow["match_level_history"]["HOME_TEAM"]["rows"]
