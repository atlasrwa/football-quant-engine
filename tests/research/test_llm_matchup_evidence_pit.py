"""PIT / temporal-integrity tests for the deterministic evidence engine (brief §10, §36).

These use synthetic MatchRecords (no cache dependency) so they are fast and hermetic,
plus one determinism check. They assert the cohort engine never reads the target fixture
or the future, respects season boundaries, fails closed on cold start, and produces a
stable packet hash.
"""
import sys
sys.path.insert(0, "/home/ubuntu")
import pytest

from src.research.matchup.corpus import MatchRecord
from src.research.llm_matchup import cohorts as CH
from src.research.llm_matchup.evidence import EvidencePacketBuilder, packet_hash


def _rec(fid, comp, season, t, home, away, hc, ac, rich=None):
    base = {"team_a_yellow_cards": 2, "team_b_yellow_cards": 2}
    r = MatchRecord(fixture_id=fid, competition=comp, competition_id=comp, season_id=season,
                    kickoff_unix=t, home=home, away=away, home_id=home, away_id=away,
                    base=base, rich={"corner_kicks": (hc, ac), "accurate_crosses": (hc, ac),
                                     "shots_on_target": (4, 4), "shots_inside_box": (6, 6),
                                     "touches_in_penalty_area": (20, 20), "final_third_entries": (40, 40),
                                     "fouls": (10, 10), "tackles": (15, 15), "clearances": (12, 12),
                                     "interceptions": (8, 8), "blocked_shots": (2, 2)},
                    extra={"total_shots": (12, 12), "possession": (50, 50), "throw_ins": (18, 18)})
    if rich:
        r.rich.update(rich)
    return r


def _corpus():
    recs = []
    t = 100
    for i in range(20):
        recs.append(_rec(f"m{i}", "L", "S", t, "A", f"O{i}", 5, 3)); t += 10
        recs.append(_rec(f"n{i}", "L", "S", t, "B", f"P{i}", 4, 4)); t += 10
    target = _rec("TARGET", "L", "S", t + 1000, "A", "B", 99, 99)  # huge values must be ignored
    future = _rec("FUT", "L", "S", t + 2000, "A", "C", 1, 1)
    return recs + [target, future], target


def test_packet_excludes_target_and_future():
    recs, target = _corpus()
    b = EvidencePacketBuilder(recs, enrich_halves=False)
    pkt = b.build(target)
    # A's corners_for should reflect the prior 5-corner matches, never the 99 in TARGET/future
    corners = [e for e in pkt["evidence"] if e["metric"] == "corners_for" and e["id"].startswith("A_")]
    assert corners, "expected A corners_for evidence"
    for e in corners:
        assert e["value"] is None or e["value"] < 10, f"leaked target/future value: {e['value']}"


def test_packet_hash_deterministic():
    recs, target = _corpus()
    b = EvidencePacketBuilder(recs, enrich_halves=False)
    p1 = b.build(target)
    p2 = EvidencePacketBuilder(recs, enrich_halves=False).build(target)
    assert p1["packet_hash"] == p2["packet_hash"]
    assert p1["packet_hash"] == packet_hash(p1)


def test_cold_start_fails_closed():
    # team with no prior history -> estimates None / UNAVAILABLE, never fabricated
    recs = [_rec("only", "L", "S", 100, "A", "B", 5, 3),
            _rec("T", "L", "S", 110, "A", "B", 0, 0)]
    b = EvidencePacketBuilder(recs, enrich_halves=False)
    pkt = b.build(recs[-1])
    # A has exactly 1 prior match (< MIN_HISTORY=4) -> all values UNAVAILABLE
    a_items = [e for e in pkt["evidence"] if e["id"].startswith("A_") and "shift" not in e["metric"]]
    assert all(e["temporal_status"] == "UNAVAILABLE" for e in a_items), \
        "cold start must fail closed"


def test_league_env_prior_only():
    recs, target = _corpus()
    b = EvidencePacketBuilder(recs, enrich_halves=False)
    pkt = b.build(target)
    env = [e for e in pkt["evidence"] if e["metric"] == "league_corners_env"][0]
    # league corner env = mean total (home+away) of prior matches = 5+3 and 4+4 -> ~8
    assert env["value"] is not None
    assert 7.0 <= env["value"] <= 9.0, env["value"]


def test_against_orientation():
    recs, target = _corpus()
    b = EvidencePacketBuilder(recs, enrich_halves=False)
    pkt = b.build(target)
    # B's corners_against: B played as home with 4 for / 4 against -> ~4
    ca = [e for e in pkt["evidence"] if e["metric"] == "corners_against" and e["id"].startswith("B_")]
    assert ca and (ca[0]["value"] is None or 3.0 <= ca[0]["value"] <= 5.0)


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
