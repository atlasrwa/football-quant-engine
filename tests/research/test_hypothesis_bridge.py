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
from src.research.hypothesis_bridge import packet_binding as PB
from src.research.llm_matchup.evidence_v2 import EvidencePacketBuilderV2


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
    recs += [_rec(f"g{i}", season, 100 + i * 10, "B", f"P{i}", (4, 4)) for i in range(n_prior)]
    target = _rec("T", season, 900, "A", "B")
    recs.append(target)
    return recs, target


def _packet(recs, target):
    """A REAL corrected-lineage packet, built by the production builder."""
    return EvidencePacketBuilderV2(recs, enrich_halves=False).build(target)


def _ctx(recs):
    return BridgeContext(recs, producer_commit="TEST_COMMIT")


def _run(recs, raw, *, target=None, packet=None,
         source=PB.SOURCE_DETERMINISTIC_REHEARSAL):
    """Every call supplies an ACTUAL packet -- there is no NO_PACKET path to fall back to."""
    target = target or next(r for r in recs if r.fixture_id == "T")
    packet = packet if packet is not None else _packet(recs, target)
    return _ctx(recs).run_proposal(raw, packet=packet, proposal_source=source)


BASE = {"fixture_id": "T", "subject": "home_team", "target_metric": "corners",
        "perspective": "for", "comparator": "league_season_baseline",
        "research_reason": "corner production"}


# ------------------------------------------------------------------ 7/8. provider semantics

def test_unsupported_metric_rejects():
    recs, _ = _corpus()
    r = _run(recs, {**BASE, "target_metric": "expected_threat_v9"})
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
    r = _run(recs, {**BASE, "target_metric": "big_chances",
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
    r = _run(recs, {**BASE, **mutation})
    assert r["validation_status"] == expected, r["rejection_reason"]
    assert r["measurement"] is None
    assert r["rejection_reason"], "a refusal must name its cause"


def test_unknown_top_level_field_is_not_silently_ignored():
    recs, _ = _corpus()
    r = _run(recs, {**BASE, "freeform_instruction": "just trust me"})
    assert r["validation_status"] == ST.AMBIGUOUS_PROPOSAL
    assert "field_not_allowed" in r["rejection_reason"]


# ----------------------------------------------------------------------- 10. below support

def test_below_support_cohort_rejects():
    recs, _ = _corpus(n_prior=MIN_SUPPORT - 1)
    r = _run(recs, BASE)
    assert r["validation_status"] == ST.INSUFFICIENT_SUPPORT
    assert r["effective_n"] == MIN_SUPPORT - 1
    assert r["measurement"] is None, "measurement must not run below the support floor"


def test_metric_null_everywhere_is_missing_data_not_insufficient_support():
    """NULL means NOT RECORDED. It is a different failure from too few matches."""
    recs = [_rec(f"h{i}", "S", 100 + i * 10, "A", f"O{i}", ck=(None, None)) for i in range(8)]
    recs.append(_rec("T", "S", 900, "A", "B"))
    r = _run(recs, BASE)
    assert r["validation_status"] == ST.MISSING_DATA
    assert r["raw_n"] == 8 and r["effective_n"] == 0


# ------------------------------------------------------------ 11/12. deterministic identity

def test_valid_proposal_canonicalizes_and_measures():
    recs, _ = _corpus()
    r = _run(recs, BASE)
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
    r = _run(recs, {**BASE, **bad})
    assert r["validation_status"] == ST.FORBIDDEN_PREDICTION_FIELD, r["rejection_reason"]
    assert r["measurement"] is None


def test_forbidden_field_is_distinct_from_ambiguous():
    """Collapsing these would hide the only signal that the LLM is being used as a predictor."""
    recs, _ = _corpus()
    forbidden = _run(recs, {**BASE, "edge": 0.04})
    ambiguous = _run(recs, {**BASE, "freeform_instruction": "x"})
    assert forbidden["validation_status"] != ambiguous["validation_status"]


def test_shadow_record_carries_no_predictive_quantity():
    recs, _ = _corpus()
    r = _run(recs, BASE)
    assert r["validation_status"] == ST.VALID_MEASURABLE
    assert firewall.prohibited_fields(r) == [], "record carries a prediction-shaped field"
    flat = json.dumps(r).lower()
    for banned in ('"p_model"', '"probability"', '"edge"', '"ev"', '"odds"', '"stake"'):
        assert banned not in flat


def test_outbound_firewall_raises_on_a_planted_field():
    """Mutation control: the deny-list must actually fire, not merely be present."""
    recs, _ = _corpus()
    r = _run(recs, BASE)
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
        from src.research.llm_matchup.evidence_v2 import EvidencePacketBuilderV2
        from src.research.hypothesis_bridge import packet_binding as PB
        target = recs[-1]
        pkt = EvidencePacketBuilderV2(recs, enrich_halves=False).build(target)
        ctx = BridgeContext(recs, producer_commit="T")
        r = ctx.run_proposal({"fixture_id":"T","subject":"home_team","target_metric":"corners",
                              "perspective":"for","comparator":"league_season_baseline"},
                             packet=pkt, proposal_source=PB.SOURCE_DETERMINISTIC_REHEARSAL)
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
    before = _run(recs, BASE)["measurement"]["cohort_identity_hash"]
    mutated = [(_rec("T", "S", 900, "A", "B", ck=(99, 99)) if r.fixture_id == "T" else r)
               for r in recs]
    after = _run(mutated, BASE)["measurement"]["cohort_identity_hash"]
    assert before == after, "the target's own result entered its cohort"


def test_future_match_cannot_change_the_measurement():
    recs, _ = _corpus()
    before = _run(recs, BASE)["measurement"]
    with_future = recs + [_rec("FUT", "S", 99_999, "A", "Z", ck=(99, 99))]
    after = _run(with_future, BASE)["measurement"]
    assert before["cohort"] == after["cohort"], "a future match entered the cohort"


def test_simultaneous_match_cannot_change_the_measurement():
    recs, _ = _corpus()
    before = _run(recs, BASE)["measurement"]
    with_sim = recs + [_rec("SIM", "S", 900, "A", "Z", ck=(99, 99))]   # exactly the target's T
    after = _run(with_sim, BASE)["measurement"]
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


# =========================================================================================
# Blocker 1 — the bridge must be handed the ACTUAL packet, and must verify it.
# =========================================================================================

def test_missing_packet_refuses():
    recs, target = _corpus()
    for bad in (None, {}, "NO_PACKET", 42):
        r = _ctx(recs).run_proposal(BASE, packet=bad,
                                    proposal_source=PB.SOURCE_DETERMINISTIC_REHEARSAL)
        assert r["validation_status"] == ST.PACKET_BINDING_FAILED, bad
        assert r["packet_binding_verified"] is False
        assert r["measurement"] is None


def test_tampered_packet_with_stale_hash_refuses():
    """The declared hash is RECOMPUTED, never trusted."""
    recs, target = _corpus()
    pkt = _packet(recs, target)
    stale = dict(pkt)
    stale["data_quality"] = {**pkt.get("data_quality", {}), "n_evidence": 9999}  # content moved
    # packet_hash deliberately left at its old value
    r = _run(recs, BASE, packet=stale)
    assert r["validation_status"] == ST.PACKET_BINDING_FAILED
    assert "packet_hash_mismatch" in r["rejection_reason"]


def test_proposal_fixture_not_matching_packet_refuses():
    recs, target = _corpus()
    other = _rec("OTHER", "S", 950, "A", "B")
    pkt = _packet(recs + [other], other)
    r = _run(recs + [other], BASE, packet=pkt)   # proposal says T, packet says OTHER
    assert r["validation_status"] == ST.PACKET_BINDING_FAILED
    # Caught in STAGE A, off the RAW payload -- before the proposal was ever parsed.
    assert "raw_fixture!=packet_fixture" in r["rejection_reason"]


def test_old_lineage_packet_refuses():
    """A packet minted under the pre-correction lineage must not be measured as corrected."""
    recs, target = _corpus()
    pkt = dict(_packet(recs, target))
    pkt["cohort_policy_version"] = "cohort_policy_v1"
    from src.research.llm_matchup.evidence import packet_hash as ph
    pkt["packet_hash"] = ph(pkt)              # internally consistent, but WRONG lineage
    r = _run(recs, BASE, packet=pkt)
    assert r["validation_status"] == ST.PACKET_BINDING_FAILED
    assert "cohort_policy_version" in r["rejection_reason"]


def test_fabricated_and_foreign_evidence_refs_refuse():
    recs, target = _corpus()
    pkt = _packet(recs, target)

    fabricated = _run(recs, {**BASE, "evidence_refs": ["A_totally_made_up"]}, packet=pkt)
    assert fabricated["validation_status"] == ST.PACKET_BINDING_FAILED
    assert "evidence_refs_not_in_packet" in fabricated["rejection_reason"]

    # A ref that is valid in ANOTHER packet but absent from this one.
    other = _rec("OTHER", "S", 950, "A", "B")
    other_pkt = _packet(recs + [other], other)
    foreign = sorted(set(valid_ids(other_pkt)) - set(valid_ids(pkt)))
    if foreign:
        r = _run(recs, {**BASE, "evidence_refs": [foreign[0]]}, packet=pkt)
        assert r["validation_status"] == ST.PACKET_BINDING_FAILED


def valid_ids(packet):
    from src.research.llm_matchup.evidence import valid_evidence_ids
    return valid_evidence_ids(packet)


def test_exact_packet_and_real_refs_proceed():
    recs, target = _corpus()
    pkt = _packet(recs, target)
    ref = sorted(valid_ids(pkt))[0]
    r = _ctx(recs).run_proposal({**BASE, "evidence_refs": [ref]}, packet=pkt,
                                proposal_source=PB.SOURCE_LLM_PROPOSAL)
    assert r["validation_status"] == ST.VALID_MEASURABLE
    assert r["packet_binding_verified"] is True
    assert r["packet_hash"] == pkt["packet_hash"]
    assert r["evidence_refs_bound"] == [ref]


def test_llm_proposal_without_evidence_refs_refuses_but_rehearsal_may_omit():
    """The two modes are explicit and never conflated."""
    recs, target = _corpus()
    pkt = _packet(recs, target)
    llm = _ctx(recs).run_proposal(BASE, packet=pkt, proposal_source=PB.SOURCE_LLM_PROPOSAL)
    assert llm["validation_status"] == ST.PACKET_BINDING_FAILED
    assert "requires_at_least_one_evidence_ref" in llm["rejection_reason"]

    stub = _run(recs, BASE, packet=pkt)     # DETERMINISTIC_REHEARSAL
    assert stub["validation_status"] == ST.VALID_MEASURABLE
    assert stub["proposal_source"] == PB.SOURCE_DETERMINISTIC_REHEARSAL


# =========================================================================================
# Blocker 2 — provenance must bind the measured VALUES, not just membership.
# =========================================================================================

def _measure(recs):
    return _run(recs, BASE)["measurement"]


def test_mutating_a_prior_measured_value_changes_the_cohort_source_hash():
    """Same ids, same kickoffs, same membership — only a historical stat changes."""
    recs, _ = _corpus()
    before = _measure(recs)
    mutated = [(_rec("h3", "S", 130, "A", "O3", (99, 4)) if r.fixture_id == "h3" else r)
               for r in recs]
    after = _measure(mutated)

    assert after["cohort_identity_hash"] == before["cohort_identity_hash"], (
        "membership is unchanged, so the membership identity must not move")
    assert after["cohort_source_hash"] != before["cohort_source_hash"], (
        "a changed historical value did not change the value identity")
    assert after["measurement_input_hash"] != before["measurement_input_hash"]
    assert after["cohort"]["mean"] != before["cohort"]["mean"]


def test_mutating_a_baseline_only_value_changes_the_baseline_source_hash():
    recs, _ = _corpus()
    before = _measure(recs)
    # `g3` belongs to team B: it is in the league baseline but not in A's cohort.
    mutated = [(_rec("g3", "S", 130, "B", "P3", (99, 99)) if r.fixture_id == "g3" else r)
               for r in recs]
    after = _measure(mutated)

    assert after["cohort_source_hash"] == before["cohort_source_hash"], "cohort must be untouched"
    assert after["baseline_source_hash"] != before["baseline_source_hash"]


def test_future_row_does_not_change_target_bounded_identities():
    recs, _ = _corpus()
    before = _run(recs, BASE)
    with_future = recs + [_rec("FUT", "S", 99_999, "A", "Z", (99, 99))]
    after = _run(with_future, BASE)

    for key in ("cohort_source_hash", "baseline_source_hash", "measurement_input_hash",
                "data_vintage_target_bounded", "cohort_identity_hash"):
        assert after[key] == before[key], f"a future row moved {key}"


def test_target_outcome_mutation_does_not_change_identities():
    recs, _ = _corpus()
    before = _run(recs, BASE)
    mutated = [(_rec("T", "S", 900, "A", "B", (99, 99)) if r.fixture_id == "T" else r)
               for r in recs]
    after = _run(mutated, BASE)

    for key in ("cohort_source_hash", "baseline_source_hash", "measurement_input_hash",
                "data_vintage_target_bounded"):
        assert after[key] == before[key], f"the target's own outcome moved {key}"


def test_source_hashes_are_stable_under_input_reordering():
    recs, _ = _corpus()
    before = _measure(recs)
    after = _measure(list(reversed(recs)))
    for key in ("cohort_source_hash", "baseline_source_hash", "measurement_input_hash",
                "cohort_identity_hash"):
        assert after[key] == before[key], f"{key} depends on input list order"


# =========================================================================================
# Amendment 1 — PACKET PROVENANCE IS ESTABLISHED BEFORE THE PROPOSAL IS PARSED.
#
# Invalid model output is still a TREATMENT RESULT. If a forbidden or malformed response
# loses the identity of the packet it was shown, the rejection-reason distribution cannot be
# attributed to any instrument. Every test here asserts the packet identity SURVIVED, not
# merely that the status was right.
# =========================================================================================

def _assert_packet_identity_survived(rec, pkt):
    """The record kept the REAL, recomputed identity of the packet the model saw."""
    assert rec["packet_binding_verified"] is True
    assert rec["packet_hash"] == pkt["packet_hash"]
    assert rec["packet_schema_version"] == pkt["packet_schema_version"]
    assert rec["packet_cohort_policy_version"] == pkt["cohort_policy_version"]
    assert rec["packet_fixture_id"] == pkt["fixture"]["fixture_id"]
    assert rec["packet_kickoff_unix"] == pkt["fixture"]["kickoff_unix"]
    assert rec["packet_information_cutoff_unix"] == pkt["information_cutoff_unix"]


def test_forbidden_prediction_field_keeps_verified_packet_identity():
    """valid packet + probability=0.7 -> FORBIDDEN_PREDICTION_FIELD, packet identity intact."""
    recs, target = _corpus()
    pkt = _packet(recs, target)
    r = _run(recs, {**BASE, "probability": 0.7}, packet=pkt)
    assert r["validation_status"] == ST.FORBIDDEN_PREDICTION_FIELD
    _assert_packet_identity_survived(r, pkt)


def test_unknown_field_keeps_verified_packet_identity():
    recs, target = _corpus()
    pkt = _packet(recs, target)
    r = _run(recs, {**BASE, "some_unknown_field": 1}, packet=pkt)
    assert r["validation_status"] == ST.AMBIGUOUS_PROPOSAL
    _assert_packet_identity_survived(r, pkt)


def test_missing_required_field_keeps_verified_packet_identity():
    recs, target = _corpus()
    pkt = _packet(recs, target)
    raw = {k: v for k, v in BASE.items() if k != "target_metric"}
    r = _run(recs, raw, packet=pkt)
    assert r["validation_status"] == ST.AMBIGUOUS_PROPOSAL
    assert "missing_required:target_metric" in r["rejection_reason"]
    _assert_packet_identity_survived(r, pkt)


def test_non_mapping_proposal_still_keeps_packet_identity():
    """A payload with no readable fixture_id must not be a BINDING failure -- it is a PARSE
    failure, and Stage A has already proven the packet."""
    recs, target = _corpus()
    pkt = _packet(recs, target)
    r = _run(recs, ["not", "a", "mapping"], packet=pkt)
    assert r["validation_status"] == ST.AMBIGUOUS_PROPOSAL
    _assert_packet_identity_survived(r, pkt)


def test_tampered_packet_beats_malformed_proposal():
    """INVALID packet + malformed proposal -> PACKET_BINDING_FAILED takes precedence."""
    recs, target = _corpus()
    pkt = _packet(recs, target)
    pkt["fixture"]["kickoff_unix"] = target.kickoff_unix + 5      # stale hash now
    r = _run(recs, {**BASE, "some_unknown_field": 1}, packet=pkt)
    assert r["validation_status"] == ST.PACKET_BINDING_FAILED
    assert r["packet_binding_verified"] is False
    assert r["packet_hash"] is None


def test_forbidden_field_plus_wrong_fixture_is_binding_failure_but_names_both():
    """The one precedence collision the taxonomy does not resolve, DECIDED and pinned.

    The packet outranks the proposal because it is the instrument -- but the
    "the LLM tried to predict" signal must not vanish, so the reason names both.
    """
    recs, target = _corpus()
    other = _rec("OTHER", "S", 950, "A", "B")
    pkt = _packet(recs + [other], other)
    r = _run(recs + [other], {**BASE, "probability": 0.7}, packet=pkt)
    assert r["validation_status"] == ST.PACKET_BINDING_FAILED
    assert "raw_fixture!=packet_fixture" in r["rejection_reason"]
    assert "prediction_field:probability" in r["rejection_reason"]


def test_fabricated_evidence_ref_on_a_valid_proposal_is_binding_failure():
    recs, target = _corpus()
    pkt = _packet(recs, target)
    r = _run(recs, {**BASE, "evidence_refs": ["ev_fabricated_999"]}, packet=pkt)
    assert r["validation_status"] == ST.PACKET_BINDING_FAILED
    assert "evidence_refs_not_in_packet" in r["rejection_reason"]


def test_packet_verified_before_parse_is_observable_in_ordering():
    """Behavioural proof of the ORDER, not just of the outcome.

    A packet for a fixture the corpus does not hold fails in Stage A. If parsing still ran
    first, a forbidden field would be reported instead -- so the status distinguishes the
    two orderings.
    """
    recs, target = _corpus()
    orphan = _rec("ORPHAN", "S", 960, "A", "B")
    pkt = _packet(recs + [orphan], orphan)
    r = _run(recs, {**BASE, "fixture_id": "ORPHAN", "probability": 0.9}, packet=pkt)
    assert r["validation_status"] == ST.PACKET_BINDING_FAILED
    assert "packet_fixture_not_in_corpus" in r["rejection_reason"]


# =========================================================================================
# Amendment 2 — the packet cutoff must EQUAL the target kickoff.
# =========================================================================================

def test_earlier_cutoff_correctly_rehashed_still_refuses():
    """The trap this test exists to avoid: if the repack is wrong the packet fails on HASH
    MISMATCH and the test passes for the wrong reason. So the reason must name the CUTOFF."""
    recs, target = _corpus()
    pkt = _packet(recs, target)
    pkt["information_cutoff_unix"] = target.kickoff_unix - 3600
    pkt["packet_hash"] = PB.recompute_packet_hash(pkt)            # correctly re-hashed
    assert PB.recompute_packet_hash(pkt) == pkt["packet_hash"]
    r = _run(recs, BASE, packet=pkt)
    assert r["validation_status"] == ST.PACKET_BINDING_FAILED
    assert "information_cutoff_must_equal_target_kickoff" in r["rejection_reason"]
    assert "hash_mismatch" not in r["rejection_reason"]


def test_the_real_builder_already_cuts_exactly_at_kickoff():
    """Equality must be a property of the production builder, not just a rule we assert."""
    recs, target = _corpus()
    pkt = _packet(recs, target)
    assert pkt["information_cutoff_unix"] == target.kickoff_unix
    assert _run(recs, BASE, packet=pkt)["validation_status"] == ST.VALID_MEASURABLE


# =========================================================================================
# Amendment 3 — DUAL-PROVIDER capability model. FootyStats and TheStatsAPI stay separate.
# =========================================================================================

def _R():
    from src.research.hypothesis_bridge import registry as R
    return R


def test_thestatsapi_corners_capability_has_the_exact_traced_source():
    R = _R()
    cap = R.capability_for(R.THESTATSAPI, "corners")
    assert cap.provider == "thestatsapi"
    assert cap.provider_source_field == "overview.corner_kicks"
    assert cap.is_measurable


def test_footystats_corners_capability_is_traced_to_the_real_normalizer():
    R = _R()
    cap = R.capability_for(R.FOOTYSTATS, "corners")
    assert cap.provider == "footystats"
    assert cap.provider_source_field == "team_a_corners/team_b_corners"
    assert "footystats/normalizer.py" in cap.traced_from


def test_same_canonical_metric_from_two_providers_is_two_distinct_capabilities():
    """capability(footystats, corners) != capability(thestatsapi, corners)."""
    R = _R()
    fs = R.capability_for(R.FOOTYSTATS, "corners")
    tsa = R.capability_for(R.THESTATSAPI, "corners")
    assert fs.canonical_metric == tsa.canonical_metric == "corners"
    assert fs != tsa
    assert fs.capability_id != tsa.capability_id
    assert fs.provider_source_field != tsa.provider_source_field
    assert fs.semantic_equivalence_validated is False
    assert tsa.semantic_equivalence_validated is False


def test_yellow_cards_is_the_provider_collision_and_both_sides_are_kept():
    """The sharpest case in the whole registry.

    FootyStats genuinely exposes `team_a_yellow_cards`. TheStatsAPI exposes
    `overview.yellow_cards`, which `championship_adapter` then PARKS in a storage field ALSO
    called `team_a_yellow_cards`. Same spelling, two providers. Provenance must survive it.
    """
    R = _R()
    tsa = R.capability_for(R.THESTATSAPI, "yellow_cards")
    fs = R.capability_for(R.FOOTYSTATS, "yellow_cards")
    assert tsa.provider_source_field == "overview.yellow_cards"
    assert fs.provider_source_field == "team_a_yellow_cards/team_b_yellow_cards"
    assert tsa.storage_container == "base", "stored in the FootyStats-SCHEMA container"
    assert R.CORPUS_STORAGE_SCHEMA == "footystats_schema", "schema is NOT the provider"
    assert tsa.capability_id != fs.capability_id


def test_same_value_different_provider_gives_a_different_source_hash():
    """3H: provider identity is bound into measurement provenance."""
    from src.research.hypothesis_bridge.measurement import source_hash, cohort_sample
    from src.research.hypothesis_bridge.canonical import canonicalize
    from src.research.hypothesis_bridge.proposal import parse_proposal
    R = _R()
    recs, target = _corpus()
    from src.research.llm_matchup.cohorts import HistoryIndex
    idx = HistoryIndex(recs)
    ir = canonicalize(parse_proposal(BASE))
    sample = cohort_sample(idx, target, ir)
    team = target.home_id
    tsa_h = source_hash(target, ir, sample, team, "cohort", R.capability_for(R.THESTATSAPI, "corners"))
    fs_h = source_hash(target, ir, sample, team, "cohort", R.capability_for(R.FOOTYSTATS, "corners"))
    assert tsa_h != fs_h, "identical rows and values must not share provenance across providers"


def test_measurement_without_a_resolved_capability_fails_closed():
    from src.research.hypothesis_bridge import measurement as M
    with pytest.raises(M.MeasurementFailed):
        M.capability_identity(None)


def test_thestatsapi_npxg_is_not_measurable_under_the_existing_semantics_audit():
    """V5A.1 measured npxG > xG in 15.8% of raw pairs and classified it
    PROVIDER_SOURCE_INCONSISTENCY. That evidence governs until superseded."""
    R = _R()
    cap = R.capability_for(R.THESTATSAPI, "npxg")
    assert cap is not None, "excluded is not the same as absent -- audit needs the entry"
    assert cap.is_measurable is False
    assert cap.status == R.EXCLUDED_PROVIDER_SEMANTICS
    assert cap.exclusion_reason == "PROVIDER_SOURCE_INCONSISTENCY"
    assert "V5A1_PROVIDER_SEMANTICS_AUDIT" in cap.exclusion_evidence
    # and the real raw node, not the fictitious np_expected_goals.np_expected_goals
    assert cap.provider_source_field == "np_expected_goals.all.{home|away}"


def test_a_proposal_targeting_npxg_is_refused_end_to_end():
    recs, target = _corpus()
    r = _run(recs, {**BASE, "target_metric": "npxg"})
    assert r["validation_status"] == ST.UNSUPPORTED_PROVIDER_SEMANTICS
    assert "PROVIDER_SOURCE_INCONSISTENCY" in r["rejection_reason"]


def test_footystats_npxg_is_absent_not_assumed_from_footystats_xg():
    R = _R()
    assert R.capability_for(R.FOOTYSTATS, "npxg") is None
    # ...and its xG is NOT quietly promoted into one.
    xg = R.capability_for(R.FOOTYSTATS, "xg")
    assert xg.canonical_metric == "xg" and not xg.is_measurable


def test_provider_specific_xg_is_never_assumed_equal():
    """3G: both xGs are declared, with distinct sources and no equivalence claim."""
    R = _R()
    fs, tsa = R.capability_for(R.FOOTYSTATS, "xg"), R.capability_for(R.THESTATSAPI, "xg")
    assert fs.provider_source_field == "team_a_xg/team_b_xg"
    assert tsa.provider_source_field == "overview.expected_goals"
    assert fs.capability_id != tsa.capability_id
    assert not fs.semantic_equivalence_validated
    assert not tsa.semantic_equivalence_validated


def test_unknown_provider_fails_closed():
    R = _R()
    with pytest.raises(R.UnknownProvider):
        R.capability_for("opta", "corners")
    with pytest.raises(R.UnknownProvider):
        R.is_measurable("", "corners")


def test_unknown_provider_metric_pair_fails_closed():
    R = _R()
    assert R.capability_for(R.THESTATSAPI, "expected_threat_v9") is None
    assert not R.is_measurable(R.THESTATSAPI, "expected_threat_v9")
    # A metric one provider has and the other does not must NOT resolve for the other.
    assert R.capability_for(R.FOOTYSTATS, "big_chances") is None
    assert R.capability_for(R.THESTATSAPI, "big_chances") is not None


def test_no_implicit_provider_fallback_in_validation():
    """`big_chances` exists for TheStatsAPI only. Under FOOTYSTATS_ONLY it must NOT silently
    resolve to the TheStatsAPI capability."""
    from src.research.hypothesis_bridge.validation import validate_provider
    from src.research.hypothesis_bridge.canonical import canonicalize
    from src.research.hypothesis_bridge.proposal import parse_proposal
    R = _R()
    ir = canonicalize(parse_proposal({**BASE, "target_metric": "big_chances"}))
    assert validate_provider(ir, R.THESTATSAPI) is None
    refusal = validate_provider(ir, R.FOOTYSTATS)
    assert refusal is not None and refusal.status == ST.UNSUPPORTED_METRIC
    assert "does not fall back" in refusal.rejection_reason


def test_blend_and_fallback_policies_are_refused_not_implemented():
    """IMPLICIT_PROVIDER_BLEND=false is earned by the code path not existing."""
    from src.research.reconciliation.policy import ReconciliationPolicy as RP
    R = _R()
    assert R.resolve_measurement_provider(RP.THESTATSAPI_ONLY) == "thestatsapi"
    assert R.resolve_measurement_provider(RP.FOOTYSTATS_ONLY) == "footystats"
    for policy in (RP.PREFERRED_PROVIDER_WITH_FALLBACK, RP.VALIDATED_BLEND):
        with pytest.raises(R.ProviderPolicyUnsupported):
            R.resolve_measurement_provider(policy)
    with pytest.raises(R.ProviderPolicyUnsupported):
        R.resolve_measurement_provider("THESTATSAPI_ONLY")       # a string is not a policy


def test_a_context_cannot_claim_a_provider_the_corpus_did_not_come_from():
    """No fabricated FootyStats provenance over TheStatsAPI-derived rows."""
    from src.research.reconciliation.policy import ReconciliationPolicy as RP
    R = _R()
    recs, _ = _corpus()
    with pytest.raises(R.UnknownProvider):
        BridgeContext(recs, producer_commit="T", provider_policy=RP.FOOTYSTATS_ONLY)


def test_the_rehearsal_provider_policy_is_frozen_to_thestatsapi_only():
    R = _R()
    assert R.FROZEN_REHEARSAL_POLICY.value == "THESTATSAPI_ONLY"
    assert R.CORPUS_PROVIDER_LINEAGE == "thestatsapi"
    recs, _ = _corpus()
    assert _ctx(recs).measurement_provider == "thestatsapi"


def test_shadow_record_names_the_provider_actually_used():
    recs, target = _corpus()
    r = _run(recs, BASE)
    assert r["validation_status"] == ST.VALID_MEASURABLE
    assert r["measurement_provider"] == "thestatsapi"
    assert r["provider_policy"] == "THESTATSAPI_ONLY"
    assert r["provider_source_field"] == "overview.corner_kicks"
    assert r["provider_capability_id"].startswith("cap_thestatsapi_corners_")
    assert r["measurement"]["measurement_provider"] == "thestatsapi"
    assert r["corpus_storage_schema"] == "footystats_schema"


def test_every_declared_capability_is_traced_and_provider_scoped():
    R = _R()
    for (provider, metric), cap in R.PROVIDER_CAPABILITIES.items():
        assert provider in R.PROVIDERS, (provider, metric)
        assert cap.provider == provider and cap.canonical_metric == metric
        assert cap.provider_source_field, (provider, metric)
        assert cap.traced_from, (provider, metric)
        assert cap.null_semantics == R.NULL_IS_NOT_RECORDED
        if not cap.is_measurable:
            assert cap.status in {R.EXCLUDED_PROVIDER_SEMANTICS,
                                  R.DECLARED_NOT_IN_BRIDGE_VOCABULARY,
                                  R.UNVALIDATED_EQUIVALENCE}


def test_registry_hash_moves_when_a_provider_identity_changes():
    """Mutation control: the hash must actually depend on provider identity."""
    R = _R()
    before = R.registry_hash()
    key = (R.THESTATSAPI, "yellow_cards")
    original = R.PROVIDER_CAPABILITIES[key]
    try:
        import dataclasses
        R.PROVIDER_CAPABILITIES[key] = dataclasses.replace(original, provider="footystats")
        assert R.registry_hash() != before
    finally:
        R.PROVIDER_CAPABILITIES[key] = original
    assert R.registry_hash() == before
