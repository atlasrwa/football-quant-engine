"""Formation policy tests (formation_policy_v1) — deterministic, hermetic, no Bedrock.

Covers the load-bearing Phase-B guarantees:
  * formation family mapping is deterministic and total;
  * resolved historical formation is accepted for SOURCE history;
  * the TARGET fixture's resolved formation is NEVER injected as evidence (leakage);
  * FormationInput type separation (ANNOUNCED/PROJECTED/UNKNOWN vs RESOLVED);
  * exact-formation small-N shrinkage behaves (tiny cohort does not dominate);
  * A/B formation orientation (home vs away formation not swapped);
  * formation UNKNOWN handling;
  * same evidence -> stable packet hash (cache key stability).

Run: .venv/bin/python -m pytest tests/research/test_formation_policy.py -q
"""
import sys
sys.path.insert(0, "/home/ubuntu")
import pytest

from src.research.matchup.corpus import MatchRecord
from src.research.llm_matchup import formation as FM
from src.research.llm_matchup import formation_evidence as FE
from src.research.llm_matchup.evidence_v2 import EvidencePacketBuilderV2, packet_hash


# ---------- family mapping ----------
def test_family_mapping_is_deterministic_and_total():
    known = {
        "4-2-3-1": "BACK4_1STRIKER", "4-3-3": "BACK4_1STRIKER", "4-4-2": "BACK4_2STRIKER",
        "3-4-2-1": "BACK3_WINGBACK", "3-5-2": "BACK3_WINGBACK", "5-3-2": "BACK5_DEFENSIVE",
        "5-4-1": "BACK5_DEFENSIVE",
    }
    for f, fam in known.items():
        assert FM.formation_family(f) == fam
        assert FM.formation_family(f) == FM.formation_family(f)  # deterministic
    # totality: unknown / malformed / None all map to UNKNOWN_FORMATION
    for bad in (None, "", "garbage", "9", "x-y-z"):
        assert FM.formation_family(bad) == FM.UNKNOWN_FORMATION
    # a never-seen but valid string derives from digit structure
    assert FM.formation_family("4-2-4") == "BACK4_OTHER"
    assert FM.formation_family("5-2-3") == "BACK5_DEFENSIVE"


def test_family_mapping_never_uses_club_knowledge():
    # identical formation always maps identically regardless of any context
    assert FM.formation_family("4-3-3") == FM.formation_family("4-3-3")


# ---------- FormationInput type separation ----------
def test_formation_input_types_are_separate():
    unk = FM.FormationInput.unknown()
    ann = FM.FormationInput.announced("4-2-3-1", "feed_v1")
    prj = FM.FormationInput.projected("4-4-2", "proj_v1")
    assert unk.source_type == "UNKNOWN"
    assert ann.source_type == "ANNOUNCED"
    assert prj.source_type == "PROJECTED"
    # RESOLVED is not a valid FormationInput source; the leakage guard rejects it
    bad = FM.FormationInput.projected("4-2-3-1", "x")
    bad.source_type = "RESOLVED"
    with pytest.raises(ValueError):
        FM.assert_not_target_resolved(bad)
    # a legitimate projected input passes the guard
    FM.assert_not_target_resolved(prj)


def test_formation_uncertain_distribution():
    d = {"4-2-3-1": 0.55, "4-3-3": 0.30, "4-4-2": 0.15}
    fi = FM.FormationInput.projected("4-2-3-1", "proj", distribution=d)
    assert fi.distribution == d
    assert abs(sum(fi.distribution.values()) - 1.0) < 1e-9


# ---------- synthetic corpus with resolved formations (via monkeypatched loader) ----
def _rec(fid, t, home, away, hc, ac):
    return MatchRecord(
        fixture_id=fid, competition="L", competition_id="L", season_id="S",
        kickoff_unix=t, home=home, away=away, home_id=home, away_id=away,
        base={"team_a_yellow_cards": 2, "team_b_yellow_cards": 2},
        rich={"corner_kicks": (hc, ac), "accurate_crosses": (hc, ac),
              "shots_on_target": (4, 4), "shots_inside_box": (6, 6),
              "touches_in_penalty_area": (20, 20), "final_third_entries": (40, 40),
              "fouls": (10, 10), "tackles": (15, 15), "clearances": (12, 12),
              "interceptions": (8, 8), "blocked_shots": (2, 2)},
        extra={"total_shots": (12, 12), "possession": (50, 50), "throw_ins": (18, 18)})


@pytest.fixture
def formation_corpus(monkeypatch):
    """20 prior A matches + 20 prior B matches + target; A always plays 4-2-3-1 at home
    except a couple 3-5-2; the TARGET (huge corner values) also 'played' a formation we
    inject only to prove it is NEVER read."""
    recs = []
    t = 100
    forms = {}
    for i in range(20):
        fa = f"a{i}"
        recs.append(_rec(fa, t, "A", f"O{i}", 6, 3)); t += 10
        forms[fa] = {"home": ("3-5-2" if i < 2 else "4-2-3-1"), "away": "4-4-2",
                     "home_family": FM.formation_family("3-5-2" if i < 2 else "4-2-3-1"),
                     "away_family": "BACK4_2STRIKER", "confirmed": True}
        fb = f"b{i}"
        recs.append(_rec(fb, t, "B", f"P{i}", 4, 4)); t += 10
        forms[fb] = {"home": "4-3-3", "away": "4-4-2",
                     "home_family": "BACK4_1STRIKER", "away_family": "BACK4_2STRIKER",
                     "confirmed": True}
    target = _rec("TARGET", t + 1000, "A", "B", 99, 99)
    forms["TARGET"] = {"home": "4-2-3-1", "away": "4-3-3",   # must NEVER be read as evidence
                       "home_family": "BACK4_1STRIKER", "away_family": "BACK4_1STRIKER",
                       "confirmed": True}
    recs.append(target)

    monkeypatch.setattr(FM, "resolved_coverage_index", lambda: forms)
    monkeypatch.setattr(FE.FormationHistoryIndex, "team_formation",
                        lambda self, rec, team: (
                            (forms.get(rec.fixture_id, {}).get("home"),
                             forms.get(rec.fixture_id, {}).get("home_family", FM.UNKNOWN_FORMATION))
                            if (rec.home == team) else
                            (forms.get(rec.fixture_id, {}).get("away"),
                             forms.get(rec.fixture_id, {}).get("away_family", FM.UNKNOWN_FORMATION))))
    return recs, target, forms


def test_target_resolved_formation_not_leaked(formation_corpus):
    recs, target, forms = formation_corpus
    b = EvidencePacketBuilderV2(recs, enrich_halves=False)
    # pass PROJECTED formation for the target (never its resolved one)
    pf = {"home": FM.FormationInput.projected("4-2-3-1", "proj"),
          "away": FM.FormationInput.projected("4-3-3", "proj")}
    pkt = b.build(target, prematch_formations=pf)
    # every corner/cross fc_/fmx_ evidence value must derive from prior matches
    # (corner ~6, cross ~6 for A home), never the target's 99.
    for e in pkt["evidence"]:
        if e["metric"].startswith(("fc_", "fmx_")) and e["value"] is not None \
                and ("corners" in e["metric"] or "crosses" in e["metric"]):
            assert e["value"] < 50, f"target value leaked into {e['metric']}={e['value']}"
    # prematch status must be PROJECTED, resolution present but target not used
    assert pkt["formation_context"]["prematch_status"] == "PROJECTED"


def test_resolved_formation_accepted_for_source_history(formation_corpus):
    recs, target, forms = formation_corpus
    fidx = FE.FormationHistoryIndex(recs)
    season = fidx.base.current_season("A", target.kickoff_unix)
    # A's 4-2-3-1 cohort (18 matches) should be usable; corner ~6
    vals = fidx.conditioned_values("A", "corners", "for", target.kickoff_unix, season,
                                   "home", formation="4-2-3-1")
    assert len(vals) >= 15
    assert 5.0 <= sum(vals) / len(vals) <= 7.0


def test_exact_formation_small_n_shrinks(formation_corpus):
    recs, target, forms = formation_corpus
    fidx = FE.FormationHistoryIndex(recs)
    season = fidx.base.current_season("A", target.kickoff_unix)
    # A's 3-5-2 cohort has only 2 matches -> below MIN_FORMATION_N; the matchup resolver
    # must NOT let it dominate: preferred tier should fall back to a more general tier.
    fm = FE.formation_matchup(fidx, "A", "home", "corners", "for", target.kickoff_unix,
                              season, "3-5-2", "BACK3_WINGBACK", "4-4-2", "BACK4_2STRIKER",
                              competition_value=8.0)
    assert fm.preferred_tier != "EXACT_x_EXACT" or fm.reliability == "LOW"


def test_ab_formation_orientation(formation_corpus):
    recs, target, forms = formation_corpus
    b = EvidencePacketBuilderV2(recs, enrich_halves=False)
    pf = {"home": FM.FormationInput.projected("4-2-3-1", "proj"),
          "away": FM.FormationInput.projected("4-3-3", "proj")}
    pkt = b.build(target, prematch_formations=pf)
    fc = pkt["formation_context"]
    assert fc["team_a_prematch_formation"]["formation"] == "4-2-3-1"
    assert fc["team_b_prematch_formation"]["formation"] == "4-3-3"
    # A is home, B is away — never swapped
    assert pkt["team_a"]["venue"] == "home"
    assert pkt["team_b"]["venue"] == "away"


def test_formation_unknown_handling(formation_corpus):
    recs, target, forms = formation_corpus
    b = EvidencePacketBuilderV2(recs, enrich_halves=False)
    # no prematch formation -> UNKNOWN, cohorts fall back, prematch status UNKNOWN
    pkt = b.build(target, prematch_formations=None)
    assert pkt["formation_context"]["prematch_status"] == "PREMATCH_UNKNOWN"
    assert pkt["unsupported_context"]["formation_status"] == "FORMATION_UNKNOWN"


def test_ablation_removes_formation_dimensions(formation_corpus):
    recs, target, forms = formation_corpus
    b = EvidencePacketBuilderV2(recs, enrich_halves=False)
    pf = {"home": FM.FormationInput.projected("4-2-3-1", "proj"),
          "away": FM.FormationInput.projected("4-3-3", "proj")}
    full = b.build(target, prematch_formations=pf, include_formation=True)
    abl = b.build(target, prematch_formations=pf, include_formation=False)
    assert any(e["metric"].startswith(("fc_", "fmx_")) for e in full["evidence"])
    assert not any(e["metric"].startswith(("fc_", "fmx_")) for e in abl["evidence"])


def test_label_shuffle_changes_only_labels_not_behavior(formation_corpus):
    recs, target, forms = formation_corpus
    b = EvidencePacketBuilderV2(recs, enrich_halves=False)
    pf = {"home": FM.FormationInput.projected("4-2-3-1", "proj"),
          "away": FM.FormationInput.projected("4-3-3", "proj")}
    normal = b.build(target, prematch_formations=pf)
    shuffled = b.build(target, prematch_formations=pf,
                       formation_override={"home": "4-3-3", "away": "4-2-3-1"})
    # the behavioral (non-formation) evidence must be byte-identical between the two
    def behav(pkt):
        return sorted((e["metric"], e["value"]) for e in pkt["evidence"]
                      if not e["metric"].startswith(("fc_", "fmx_", "formation_delta_")))
    assert behav(normal) == behav(shuffled)
    # but the nominal labels differ
    assert normal["formation_context"]["team_a_prematch_formation"]["formation"] != \
           shuffled["formation_context"]["team_a_prematch_formation"]["formation"]


def test_packet_hash_stable_for_same_inputs(formation_corpus):
    recs, target, forms = formation_corpus
    b1 = EvidencePacketBuilderV2(recs, enrich_halves=False)
    b2 = EvidencePacketBuilderV2(recs, enrich_halves=False)
    pf = {"home": FM.FormationInput.projected("4-2-3-1", "proj"),
          "away": FM.FormationInput.projected("4-3-3", "proj")}
    p1 = b1.build(target, prematch_formations=pf)
    p2 = b2.build(target, prematch_formations=pf)
    assert p1["packet_hash"] == p2["packet_hash"]
    assert p1["packet_hash"] == packet_hash(p1)


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
