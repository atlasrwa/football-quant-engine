"""The research bridge: proposal -> canonical IR -> validation -> measurement -> shadow.

Every test demonstrates a failure MODE, not an implementation detail. OFFLINE: no corpus, no
credentials, no model call -- the bridge makes none by construction and one test proves it by
blocking outbound sockets rather than by asserting that a mock was not called.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap

import pytest

from src.research.matchup.corpus import MatchRecord
from src.research.hypothesis_bridge import firewall, status as ST
from src.research.hypothesis_bridge.bridge import BridgeContext
from src.research.hypothesis_bridge.canonical import canonicalize, CanonicalizationRefused
from src.research.hypothesis_bridge.measurement import MIN_SUPPORT
from src.research.hypothesis_bridge.proposal import parse_proposal, HypothesisProposal


def _rec(fid, season, t, h, a, ck=(5, 4), yellow=(2, 1)):
    base = {"homeGoalCount": 1, "awayGoalCount": 1, "overallGoalCount": 2,
            "team_a_xg": 1.0, "team_b_xg": 1.0,
            "team_a_shotsOnTarget": 4, "team_b_shotsOnTarget": 3,
            "team_a_yellow_cards": yellow[0], "team_b_yellow_cards": yellow[1],
            "team_a_red_cards": 0, "team_b_red_cards": 0,
            "team_a_fouls": 10, "team_b_fouls": 9}
    return MatchRecord(fixture_id=fid, competition="L", competition_id="L", season_id=season,
                       kickoff_unix=t, home=h, away=a, home_id=h, away_id=a,
                       base=base, rich={"corner_kicks": ck}, extra={})


def _corpus(n_prior: int = 8, season: str = "S"):
    recs = [_rec(f"h{i}", season, 100 + i * 10, "A", f"O{i}", (5 + i, 4)) for i in range(n_prior)]
    target = _rec("T", season, 900, "A", "B")
    recs.append(target)
    return recs, target


def _ctx(recs):
    return BridgeContext(recs, packet_version="fixture_evidence_packet_v4",
                         producer_commit="TEST_COMMIT")


BASE = {"fixture_id": "T", "subject": "home_team", "target_metric": "corners",
        "perspective": "for", "comparator": "league_season_baseline",
        "research_reason": "corner production"}


# ------------------------------------------------------------------ 7/8. provider semantics

def test_unsupported_metric_rejects():
    recs, _ = _corpus()
    r = _ctx(recs).run_proposal({**BASE, "target_metric": "expected_threat_v9"})
    assert r["validation_status"] == ST.UNSUPPORTED_METRIC
    assert r["measurement"] is None, "an unsupported metric must never be measured"


def test_unsupported_provider_semantics_rejects():
    """`big_chances` is a supported metric with NO half-split mapping in the corpus.

    A first-half request is therefore not measurable and is refused, rather than
    approximated from the full-match value — provider equivalence is never assumed.
    (`possession` deliberately is NOT used here: it does have a half mapping, so it would
    make this test pass for the wrong reason.)
    """
    from src.research.llm_matchup import cohorts as CH
    assert "big_chances" in CH.ALL_METRICS and "big_chances" not in CH.HALF_METRICS

    recs, _ = _corpus()
    r = _ctx(recs).run_proposal({**BASE, "target_metric": "big_chances",
                                 "conditions": {"period": "first_half"}})
    assert r["validation_status"] == ST.UNSUPPORTED_PROVIDER_SEMANTICS
    assert r["measurement"] is None


# ------------------------------------------------------------------- 9. ambiguous proposal

@pytest.mark.parametrize("mutation,expected", [
    ({"subject": "the home side"}, ST.COMPILER_REFUSED),
    ({"comparator": "whatever_feels_right"}, ST.COMPILER_REFUSED),
    ({"conditions": {"vibe": "attacking"}}, ST.COMPILER_REFUSED),
    ({"window": {"mode": "last_n", "n": 0}}, ST.COMPILER_REFUSED),
    ({"similar_opponent_intent": {"like": "top6"}}, ST.COMPILER_REFUSED),
])
def test_ambiguous_or_unmappable_proposal_refuses(mutation, expected):
    recs, _ = _corpus()
    r = _ctx(recs).run_proposal({**BASE, **mutation})
    assert r["validation_status"] == expected, r["rejection_reason"]
    assert r["measurement"] is None
    assert r["rejection_reason"], "a refusal must name its cause"


def test_unknown_top_level_field_is_not_silently_ignored():
    recs, _ = _corpus()
    r = _ctx(recs).run_proposal({**BASE, "freeform_instruction": "just trust me"})
    assert r["validation_status"] == ST.AMBIGUOUS_PROPOSAL
    assert "field_not_allowed" in r["rejection_reason"]


# ----------------------------------------------------------------------- 10. below support

def test_below_support_cohort_rejects():
    recs, _ = _corpus(n_prior=MIN_SUPPORT - 1)
    r = _ctx(recs).run_proposal(BASE)
    assert r["validation_status"] == ST.INSUFFICIENT_SUPPORT
    assert r["effective_n"] == MIN_SUPPORT - 1
    assert r["measurement"] is None, "measurement must not run below the support floor"


def test_metric_null_everywhere_is_missing_data_not_insufficient_support():
    """NULL means NOT RECORDED. It is a different failure from too few matches."""
    recs = [_rec(f"h{i}", "S", 100 + i * 10, "A", f"O{i}", ck=(None, None)) for i in range(8)]
    recs.append(_rec("T", "S", 900, "A", "B"))
    r = _ctx(recs).run_proposal(BASE)
    assert r["validation_status"] == ST.MISSING_DATA
    assert r["raw_n"] == 8 and r["effective_n"] == 0


# ------------------------------------------------------------ 11/12. deterministic identity

def test_valid_proposal_canonicalizes_and_measures():
    recs, _ = _corpus()
    r = _ctx(recs).run_proposal(BASE)
    assert r["validation_status"] == ST.VALID_MEASURABLE
    assert r["canonical_hypothesis_id"].startswith("hyp_")
    assert r["measurement"]["cohort"]["effective_n"] == 8


def test_identical_proposals_give_identical_hypothesis_ids():
    a = canonicalize(parse_proposal(dict(BASE)))
    b = canonicalize(parse_proposal(dict(BASE)))
    assert a.canonical_hypothesis_id == b.canonical_hypothesis_id

    # ...and a materially different proposal must not collide with it.
    c = canonicalize(parse_proposal({**BASE, "perspective": "against"}))
    assert c.canonical_hypothesis_id != a.canonical_hypothesis_id

    # Field ORDER is not material; the id is over content.
    reordered = {k: BASE[k] for k in reversed(list(BASE))}
    assert canonicalize(parse_proposal(reordered)).canonical_hypothesis_id == a.canonical_hypothesis_id


# ----------------------------------------------------------------- 13/15. numerical firewall

@pytest.mark.parametrize("bad", [
    {"probability": 0.62}, {"p_model": 0.62}, {"edge": 0.04}, {"ev": 1.2},
    {"odds": 2.1}, {"stake": 5.0}, {"expected_value": 0.3}, {"effect_size": 0.8},
    {"conditions": {"venue": "home", "pModel": 0.6}},
    {"window": {"mode": "all", "confidence": 0.9}},
])
def test_prediction_shaped_fields_are_refused(bad):
    recs, _ = _corpus()
    r = _ctx(recs).run_proposal({**BASE, **bad})
    assert r["validation_status"] == ST.FORBIDDEN_PREDICTION_FIELD, r["rejection_reason"]
    assert r["measurement"] is None


def test_forbidden_field_is_distinct_from_ambiguous():
    """Collapsing these would hide the only signal that the LLM is being used as a predictor."""
    recs, _ = _corpus()
    forbidden = _ctx(recs).run_proposal({**BASE, "edge": 0.04})
    ambiguous = _ctx(recs).run_proposal({**BASE, "freeform_instruction": "x"})
    assert forbidden["validation_status"] != ambiguous["validation_status"]


def test_shadow_record_carries_no_predictive_quantity():
    recs, _ = _corpus()
    r = _ctx(recs).run_proposal(BASE)
    assert r["validation_status"] == ST.VALID_MEASURABLE
    assert firewall.prohibited_fields(r) == [], "record carries a prediction-shaped field"
    flat = json.dumps(r).lower()
    for banned in ('"p_model"', '"probability"', '"edge"', '"ev"', '"odds"', '"stake"'):
        assert banned not in flat


def test_outbound_firewall_raises_on_a_planted_field():
    """Mutation control: the deny-list must actually fire, not merely be present."""
    recs, _ = _corpus()
    r = _ctx(recs).run_proposal(BASE)
    r["measurement"]["p_model"] = 0.61
    with pytest.raises(firewall.FirewallViolation):
        firewall.assert_outbound_clean(r)


# ------------------------------------------------------------------ 14. no model call at all

def test_bridge_makes_no_network_or_model_call():
    """Proved by BLOCKING outbound sockets, not by asserting a mock went uncalled."""
    script = textwrap.dedent("""
        import json, socket, sys

        class Blocked(RuntimeError): pass
        def _deny(*a, **k):
            raise Blocked("the bridge attempted a network connection")
        socket.socket.connect = _deny
        socket.create_connection = _deny

        from src.research.matchup.corpus import MatchRecord
        from src.research.hypothesis_bridge.bridge import BridgeContext

        def rec(fid, t, ck):
            b = {"homeGoalCount":1,"awayGoalCount":1,"overallGoalCount":2,"team_a_xg":1.0,
                 "team_b_xg":1.0,"team_a_shotsOnTarget":4,"team_b_shotsOnTarget":3,
                 "team_a_yellow_cards":2,"team_b_yellow_cards":1,"team_a_red_cards":0,
                 "team_b_red_cards":0,"team_a_fouls":10,"team_b_fouls":9}
            return MatchRecord(fixture_id=fid, competition="L", competition_id="L",
                               season_id="S", kickoff_unix=t, home="A", away="B",
                               home_id="A", away_id="B", base=b,
                               rich={"corner_kicks": ck}, extra={})
        recs = [rec(f"h{i}", 100+i*10, (5+i,4)) for i in range(8)] + [rec("T", 900, (5,4))]
        ctx = BridgeContext(recs, packet_version="v4", producer_commit="T")
        r = ctx.run_proposal({"fixture_id":"T","subject":"home_team","target_metric":"corners",
                              "perspective":"for","comparator":"league_season_baseline"})
        print(json.dumps({"status": r["validation_status"],
                          "bedrock_imported": "botocore.client" in sys.modules}))
    """)
    env = dict(os.environ); env.pop("PYTHONPATH", None); env["PYTHONNOUSERSITE"] = "1"
    proc = subprocess.run([sys.executable, "-c", script], cwd=os.path.realpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)),
        env=env, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["status"] == ST.VALID_MEASURABLE
    assert out["bedrock_imported"] is False, "the bridge pulled in a Bedrock client"


# ------------------------------------------------------------- 5/6 at the measurement layer

def test_target_outcome_cannot_change_the_measurement():
    recs, target = _corpus()
    before = _ctx(recs).run_proposal(BASE)["measurement"]["cohort_identity_hash"]
    mutated = [(_rec("T", "S", 900, "A", "B", ck=(99, 99)) if r.fixture_id == "T" else r)
               for r in recs]
    after = _ctx(mutated).run_proposal(BASE)["measurement"]["cohort_identity_hash"]
    assert before == after, "the target's own result entered its cohort"


def test_future_match_cannot_change_the_measurement():
    recs, _ = _corpus()
    before = _ctx(recs).run_proposal(BASE)["measurement"]
    with_future = recs + [_rec("FUT", "S", 99_999, "A", "Z", ck=(99, 99))]
    after = _ctx(with_future).run_proposal(BASE)["measurement"]
    assert before["cohort"] == after["cohort"], "a future match entered the cohort"


def test_simultaneous_match_cannot_change_the_measurement():
    recs, _ = _corpus()
    before = _ctx(recs).run_proposal(BASE)["measurement"]
    with_sim = recs + [_rec("SIM", "S", 900, "A", "Z", ck=(99, 99))]   # exactly the target's T
    after = _ctx(with_sim).run_proposal(BASE)["measurement"]
    assert before["cohort"] == after["cohort"], "a simultaneous match entered the cohort"


# ------------------------------------------------------------------------ 18. CHAMPION safe

CHAMPION_PATH = "/home/ubuntu/data/discovery/pilotC_stat_mixer.json"
CHAMPION_SHA = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def test_champion_artifact_unchanged():
    if not os.path.isfile(CHAMPION_PATH):
        pytest.skip("CHAMPION artifact not present in this environment")
    got = hashlib.sha256(open(CHAMPION_PATH, "rb").read()).hexdigest()
    assert got == CHAMPION_SHA, "CHAMPION artifact changed"


def test_champion_path_does_not_import_the_research_bridge():
    """A research-layer failure must never be able to stop CHAMPION."""
    root = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         os.pardir, os.pardir))
    hits = []
    for sub in ("src/research/prediction_engine", "src/research/hypothesis_v8c", "scripts"):
        d = os.path.join(root, sub)
        for dirpath, _dirs, files in os.walk(d):
            for f in files:
                if not f.endswith(".py"):
                    continue
                p = os.path.join(dirpath, f)
                if "hypothesis_bridge" in open(p, encoding="utf-8", errors="ignore").read():
                    hits.append(os.path.relpath(p, root))
    assert hits == [], f"production path imports the research bridge: {hits}"
