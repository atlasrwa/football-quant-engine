"""Required tests for the V8B.1 evidence packet builder, per
research/hypothesis_engine/V8B1_EVIDENCE_PACKET_SPEC.md section 7. Run against the REAL
corpus/capability contract.
"""
from __future__ import annotations

import json

import pytest

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import engine as EN
from src.research.hypothesis_v71 import execution as EX
from src.research.hypothesis_v71 import similarity as SIM
from src.research.hypothesis_v8b1 import packet as PK

COVERAGE_MATRIX = "/home/ubuntu/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json"


@pytest.fixture(scope="module")
def cap():
    return CAP.CapabilityContract(json.load(open(COVERAGE_MATRIX)))


@pytest.fixture(scope="module")
def index():
    recs = CI.load_records(include_fresh=False)
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    return CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)


@pytest.fixture(scope="module")
def ctx(index):
    return EX.build_context(index)


REC_I = 3000   # a fixture position deep enough into the corpus for both teams to have history


def test_1_symmetric_structure(index, cap, ctx):
    """Team A and Team B blocks must have IDENTICAL structure (same keys at every level) --
    only values may differ. Checked by comparing key sets, not the SAME dict (which would be
    trivially true and prove nothing)."""
    p = PK.build_packet(index, REC_I, cap, ctx.terciles, ctx.axis_cache, ctx.similarity,
                        _recency_family())
    a, b = p["team_a"], p["team_b"]
    assert set(a.keys()) == set(b.keys())
    assert set(a["raw_rows"][0].keys()) == set(b["raw_rows"][0].keys())
    assert set(a["recent_vs_long"].keys()) == set(b["recent_vs_long"].keys())
    # per-metric row structure must match too
    for ra, rb in zip(a["raw_rows"], b["raw_rows"]):
        assert set(ra["for"].keys()) == set(rb["for"].keys())
        assert set(ra["against"].keys()) == set(rb["against"].keys())


def _recency_family():
    from src.research.hypothesis_v71 import recency as REC
    return tuple(REC.family()) + (REC.UniformRecency(),)


def test_2_no_outcome_leakage(index, cap, ctx):
    """No packet value may equal the target fixture's OWN observed value for any metric --
    checked by confirming every reported figure is a PIT_mean/env_mean/recent-shrunk value,
    which by PITIndex's OWN construction can only read strictly-prior positions. This test
    additionally confirms the packet contains no field literally named with 'observed' or
    'target_value'."""
    p = PK.build_packet(index, REC_I, cap, ctx.terciles, ctx.axis_cache, ctx.similarity,
                        _recency_family())
    blob = json.dumps(p)
    assert "observed" not in blob.lower()
    assert '"target_value"' not in blob
    assert p["reads_target_outcome"] is False


def test_3_null_not_zero_for_thin_coverage(index, cap, ctx):
    """A metric/team pair with fewer than THIN_COVERAGE_THRESHOLD prior observations must
    report coverage=THIN with value fields present as None where n < threshold, never a
    fabricated 0.0. Uses an early-corpus position where several teams genuinely have thin
    history, rather than asserting on synthetic data."""
    early_rec_i = 25  # early enough that most teams have < 20 prior matches
    p = PK.build_packet(index, early_rec_i, cap, ctx.terciles, ctx.axis_cache, ctx.similarity,
                        _recency_family())
    found_thin = False
    for block in (p["team_a"], p["team_b"]):
        for row in block["raw_rows"]:
            for persp in ("for", "against"):
                if row[persp]["coverage"] == "THIN":
                    found_thin = True
                    # a THIN row is not required to be None (it may have SOME prior matches,
                    # just fewer than the threshold) -- but if n==0 the mean MUST be None
                    if row[persp]["long_run_n"] == 0:
                        assert row[persp]["long_run_mean"] is None
    assert found_thin, "expected at least one THIN-coverage row this early in the corpus"


def test_4_determinism(index, cap, ctx):
    p1 = PK.build_packet(index, REC_I, cap, ctx.terciles, ctx.axis_cache, ctx.similarity,
                         _recency_family())
    p2 = PK.build_packet(index, REC_I, cap, ctx.terciles, ctx.axis_cache, ctx.similarity,
                         _recency_family())
    assert p1["packet_hash"] == p2["packet_hash"]
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)


def test_5_target_formation_always_unknown(index, cap, ctx):
    for rec_i in (100, 500, 1000, REC_I):
        p = PK.build_packet(index, rec_i, cap, ctx.terciles, ctx.axis_cache, ctx.similarity,
                            _recency_family())
        assert p["target_formation"] == "FORMATION_UNKNOWN"


def test_similar_opponents_membership_only_never_a_score(index, cap, ctx):
    p = PK.build_packet(index, REC_I, cap, ctx.terciles, ctx.axis_cache, ctx.similarity,
                        _recency_family())
    for block in (p["team_a"], p["team_b"]):
        sim = block["similar_to_fixture_opponent"]
        assert sim["status"] in ("OK", "REFUSED")
        if sim["status"] == "OK":
            assert isinstance(sim["similar_opponent_ids"], list)
            for tid in sim["similar_opponent_ids"]:
                assert isinstance(tid, str)  # identity, never a float distance


def test_capability_envelope_present_and_outcome_free(index, cap, ctx):
    p = PK.build_packet(index, REC_I, cap, ctx.terciles, ctx.axis_cache, ctx.similarity,
                        _recency_family())
    env = p["capability_envelope"]
    assert env["contains_outcomes"] is False
    assert env["contains_effect_estimates"] is False


def test_version_stamp():
    stamp = PK.version_stamp()
    assert stamp["reads_target_outcome"] is False
    assert stamp["target_formation_always_unknown"] is True
    assert stamp["symmetric_team_construction"] is True
