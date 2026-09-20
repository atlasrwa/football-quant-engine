"""Target-season semantics and simultaneous-kickoff safety for the LLM evidence path.

The LLM evidence builders filtered "current-season" team state by
`cohorts.HistoryIndex.current_season(team, before)` -- the season the team LAST PLAYED IN.
For a fixture early in a new season-instance that is the PREVIOUS season, so prior-season
history was served as current-season evidence and cold-start floors were satisfied by stale
data. They now key on `HistoryIndex.target_season(target)`.

Every season assertion is made at FOUR levels, because a repair at the index level says
nothing about what reaches a packet: HistoryIndex, the evidence/cohort builder, phaseb
candidate construction, and the built packet itself.

OFFLINE. No corpus, no credentials, no model call.
"""
from __future__ import annotations

import pytest

from src.research.matchup.corpus import MatchRecord
from src.research.llm_matchup import cohorts as CH
from src.research.llm_matchup.evidence import EvidencePacketBuilder
from src.research.llm_matchup.evidence_v2 import EvidencePacketBuilderV2

MIN = CH.MIN_HISTORY


def _rec(fid, season, t, home, away, *, ck=(5, 4), sot=(4, 3), xg=(1.2, 1.0)):
    base = {
        "homeGoalCount": 1, "awayGoalCount": 1, "overallGoalCount": 2,
        "team_a_xg": xg[0], "team_b_xg": xg[1],
        "team_a_shotsOnTarget": sot[0], "team_b_shotsOnTarget": sot[1],
        "team_a_yellow_cards": 2, "team_b_yellow_cards": 1,
        "team_a_red_cards": 0, "team_b_red_cards": 0,
        "team_a_fouls": 11, "team_b_fouls": 9,
        "team_a_possession": 55, "team_b_possession": 45,
    }
    return MatchRecord(fixture_id=fid, competition="L", competition_id="L", season_id=season,
                       kickoff_unix=t, home=home, away=away, home_id=home, away_id=away,
                       base=base, rich={"corner_kicks": ck}, extra={})


def _season_boundary_corpus(n_s2: int = 0):
    """Both teams have plenty of S1 history and `n_s2` matches in S2; target is in S2."""
    recs = []
    for i in range(MIN + 6):
        recs.append(_rec(f"a1_{i}", "S1", 1_000 + i * 10, "A", f"OA{i}"))
        recs.append(_rec(f"b1_{i}", "S1", 1_000 + i * 10, "B", f"OB{i}"))
    for i in range(n_s2):
        recs.append(_rec(f"a2_{i}", "S2", 500_000 + i * 10, "A", f"QA{i}"))
        recs.append(_rec(f"b2_{i}", "S2", 500_000 + i * 10, "B", f"QB{i}"))
    target = _rec("TGT", "S2", 900_000, "A", "B")
    recs.append(target)
    return recs, target


# ------------------------------------------------------------------ level 1: HistoryIndex

def test_history_index_target_season_is_the_fixtures_own_season():
    recs, target = _season_boundary_corpus(n_s2=0)
    idx = CH.HistoryIndex(recs)

    assert CH.HistoryIndex.target_season(target) == "L:S2"
    # The old function is deliberately unchanged and still answers "last played".
    assert idx.current_season("A", target.kickoff_unix) == "L:S1"

    stale = idx.prior_records("A", target.kickoff_unix, idx.current_season("A", target.kickoff_unix))
    assert len(stale) >= MIN, "precondition: the old semantic made prior-season history available"

    fresh = idx.prior_records("A", target.kickoff_unix, CH.HistoryIndex.target_season(target))
    assert fresh == [], "target-season history is empty, so evidence must abstain"


# --------------------------------------------------------- level 2: evidence/cohort builder

def _sample_ns(packet):
    """Sample sizes of every team-state evidence item in a packet."""
    ids = set(packet["team_a"]["evidence_ids"]) | set(packet["team_b"]["evidence_ids"])
    return [e["sample_n"] for e in packet["evidence"] if e["id"] in ids]


def test_evidence_builder_abstains_across_a_season_boundary():
    recs, target = _season_boundary_corpus(n_s2=0)
    packet = EvidencePacketBuilder(recs, enrich_halves=False).build(target)

    ns = _sample_ns(packet)
    assert ns, "the packet must still carry team-state items, as abstentions"
    assert max(ns) == 0, (
        f"prior-season matches were counted as current-season evidence: sample_n={sorted(set(ns))}")


def test_evidence_builder_uses_target_season_once_it_exists():
    """Positive control: genuine S2 history restores evidence, and only S2 is used."""
    recs, target = _season_boundary_corpus(n_s2=MIN + 2)
    packet = EvidencePacketBuilder(recs, enrich_halves=False).build(target)

    ns = _sample_ns(packet)
    assert max(ns) > 0, "genuine target-season history must produce evidence"
    assert max(ns) <= MIN + 2, (
        f"sample_n exceeds the available S2 history, so S1 leaked in: max={max(ns)}")


# --------------------------------------------------- level 3: phaseb candidate construction

def test_phaseb_candidates_do_not_qualify_on_prior_season_history():
    from src.research.llm_matchup import phaseb_harness as PH

    recs, target = _season_boundary_corpus(n_s2=0)

    # `HarnessContext.__init__` loads the real corpus and the real formation coverage index,
    # so it is bypassed and the attributes are supplied directly. The logic under test --
    # `candidates()` and the season key it uses -- is the genuine production code; nothing
    # about eligibility is mocked. (Constructor-does-I/O is logged as P3, not a blocker.)
    ctx = object.__new__(PH.HarnessContext)
    ctx.recs = recs
    ctx.coverage = {r.fixture_id: {"home": True, "away": True} for r in recs}
    ctx.builder = EvidencePacketBuilderV2(recs, enrich_halves=False)
    ctx._hidx = CH.HistoryIndex(recs)

    cands = ctx.candidates(min_prior=MIN, min_form_cov=0, require_target_lineup=False)
    assert target.fixture_id not in {c.target.fixture_id for c in cands}, (
        "a fixture whose teams have no target-season history qualified on prior-season matches")

    # Positive control: with genuine S2 history the same fixture becomes eligible.
    recs2, target2 = _season_boundary_corpus(n_s2=MIN + 2)
    ctx2 = object.__new__(PH.HarnessContext)
    ctx2.recs = recs2
    ctx2.coverage = {r.fixture_id: {"home": True, "away": True} for r in recs2}
    ctx2.builder = EvidencePacketBuilderV2(recs2, enrich_halves=False)
    ctx2._hidx = CH.HistoryIndex(recs2)
    cands2 = ctx2.candidates(min_prior=MIN, min_form_cov=0, require_target_lineup=False)
    assert target2.fixture_id in {c.target.fixture_id for c in cands2}, (
        "genuine target-season history must restore eligibility")


# ------------------------------------------------------------------- level 4: built packet

def test_packet_v2_abstains_across_a_season_boundary():
    recs, target = _season_boundary_corpus(n_s2=0)
    packet = EvidencePacketBuilderV2(recs, enrich_halves=False).build(target)

    assert packet["cohort_policy_version"] == "cohort_policy_v2"
    assert packet["packet_schema_version"] == "fixture_evidence_packet_v4"
    ns = _sample_ns(packet)
    assert ns and max(ns) == 0, f"prior-season evidence reached the packet: {sorted(set(ns))}"


# ==========================================================================================
# Part B — simultaneous-kickoff safety in the LLM evidence path.
# Verified, not assumed: the comparison audit found strict `<` everywhere, and this proves it
# at the packet level, where a field reaching the packet by an unaudited route would show up.
# ==========================================================================================

def _simultaneity_corpus(partner_kickoff: int):
    """Target F1 at T, plus a partner F2 with extreme values at `partner_kickoff`."""
    recs = []
    for i in range(MIN + 4):
        recs.append(_rec(f"h{i}", "S", 1_000 + i * 10, "A", f"OA{i}"))
        recs.append(_rec(f"g{i}", "S", 1_000 + i * 10, "B", f"OB{i}"))
    target = _rec("F1", "S", 500_000, "A", "B")
    partner = _rec("F2", "S", partner_kickoff, "C", "D",
                   ck=(99, 99), sot=(50, 50), xg=(9.9, 9.9))
    recs += [target, partner]
    return recs, target


def test_simultaneous_match_cannot_enter_the_packet():
    """A match kicking off at the same instant must not affect the target's packet.

    Asserted on `packet_hash` over the whole packet rather than field-by-field, so a leak
    through any field is caught, including one that arrives by a path the audit missed.
    """
    same_recs, target = _simultaneity_corpus(partner_kickoff=500_000)   # exactly T
    later_recs, _ = _simultaneity_corpus(partner_kickoff=500_001)       # strictly after T

    p_same = EvidencePacketBuilderV2(same_recs, enrich_halves=False).build(target)
    p_later = EvidencePacketBuilderV2(later_recs, enrich_halves=False).build(target)

    assert p_same["packet_hash"] == p_later["packet_hash"], (
        "a simultaneous match changed the target's packet")


def test_future_match_insertion_cannot_change_the_packet():
    recs, target = _simultaneity_corpus(partner_kickoff=900_000)        # far future
    baseline = EvidencePacketBuilderV2(
        [r for r in recs if r.fixture_id != "F2"], enrich_halves=False).build(target)
    with_future = EvidencePacketBuilderV2(recs, enrich_halves=False).build(target)

    assert baseline["packet_hash"] == with_future["packet_hash"], (
        "a future match changed a pre-match packet")


def test_target_outcome_mutation_cannot_change_the_packet():
    """Rewriting the target's OWN result must not move its pre-match packet."""
    recs, target = _simultaneity_corpus(partner_kickoff=900_000)
    before = EvidencePacketBuilderV2(recs, enrich_halves=False).build(target)

    mutated = []
    for r in recs:
        if r.fixture_id == "F1":
            b = dict(r.base); b.update({"overallGoalCount": 99, "team_a_xg": 9.9,
                                        "team_a_shotsOnTarget": 50})
            r = MatchRecord(fixture_id=r.fixture_id, competition=r.competition,
                            competition_id=r.competition_id, season_id=r.season_id,
                            kickoff_unix=r.kickoff_unix, home=r.home, away=r.away,
                            home_id=r.home_id, away_id=r.away_id, base=b,
                            rich={"corner_kicks": (99, 99)}, extra={})
        mutated.append(r)
    tgt2 = next(r for r in mutated if r.fixture_id == "F1")
    after = EvidencePacketBuilderV2(mutated, enrich_halves=False).build(tgt2)

    assert before["packet_hash"] == after["packet_hash"], (
        "the target's own outcome leaked into its pre-match packet")


# ---------------------------------------------------------------- Part C — cache lineage

def test_corrected_lineage_cannot_reuse_an_old_cache_entry():
    """Same fixture + same packet hash must not resolve to the old lineage's cache key."""
    from src.research.llm_matchup.hardening import adapter_v4 as A4
    from src.research.llm_matchup.hardening import versions_v3 as V45

    class OldLineage:
        DEFAULT_BEDROCK_MODEL_ID = V45.DEFAULT_BEDROCK_MODEL_ID
        @staticmethod
        def version_stamp():
            st = dict(V45.version_stamp())
            st["cohort_policy_version"] = "cohort_policy_v1"   # the frozen lineage
            return st

    new_key = A4._cache_key(V45.DEFAULT_BEDROCK_MODEL_ID, "SAME_PACKET_HASH", 0, gen=V45)
    old_key = A4._cache_key(V45.DEFAULT_BEDROCK_MODEL_ID, "SAME_PACKET_HASH", 0, gen=OldLineage)

    assert V45.version_stamp()["cohort_policy_version"] == "cohort_policy_v2"
    assert new_key != old_key, "corrected packets could read cache written under old semantics"
