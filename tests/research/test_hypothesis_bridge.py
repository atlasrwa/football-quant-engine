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
    r = _run(recs, BASE, packet=pkt)          # proposal says T, packet says OTHER
    assert r["validation_status"] == ST.PACKET_BINDING_FAILED
    assert "packet_fixture!=proposal_fixture" in r["rejection_reason"]


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
# Blocker 3 — provider provenance is explicit and traced, not inferred from storage shape.
# =========================================================================================

def test_yellow_cards_provenance_is_thestatsapi_not_footystats():
    """The entry the previous container-based inference got wrong.

    `team_a_yellow_cards` is a FootyStats-SCHEMA field, but `championship_adapter.adapt_match`
    reads it from the TheStatsAPI /stats payload at `overview.yellow_cards`.
    """
    from src.research.hypothesis_bridge import registry as R
    cap = R.capability_for("yellow_cards")
    assert cap.provider == R.THESTATSAPI
    assert cap.source_path == "overview.yellow_cards"
    assert cap.container == "base", "it IS stored in the FootyStats-schema container"
    assert R.CORPUS_STORAGE_SCHEMA == "footystats_schema", "schema != provider"


@pytest.mark.parametrize("metric,path,container", [
    ("corners", "overview.corner_kicks", "rich"),
    ("total_shots", "overview.total_shots", "extra"),
    ("possession", "overview.ball_possession", "extra"),
    ("tackles", "defending.tackles", "rich"),
])
def test_provenance_matches_the_traced_adapter_paths(metric, path, container):
    from src.research.hypothesis_bridge import registry as R
    cap = R.capability_for(metric)
    assert cap.provider == R.THESTATSAPI
    assert (cap.source_path, cap.container) == (path, container)


def test_every_supported_metric_has_traced_provenance():
    from src.research.hypothesis_bridge import registry as R
    for metric, cap in R.CAPABILITIES.items():
        assert cap.source_path and "." in cap.source_path, metric
        assert cap.provider in R.providers_in_use(), metric
        assert cap.null_semantics == R.NULL_SEMANTICS


def test_unsupported_metric_has_no_provider():
    from src.research.hypothesis_bridge import registry as R
    assert R.provider_for("expected_threat_v9") is None
    assert not R.is_supported("expected_threat_v9")


def test_capability_hash_moves_when_provenance_semantics_change():
    """Mutation control: the hash must actually depend on the provenance table."""
    from src.research.hypothesis_bridge import registry as R
    before = R.capability_hash()
    original = R.CAPABILITIES["yellow_cards"]
    try:
        R.CAPABILITIES["yellow_cards"] = R.MetricCapability(
            metric="yellow_cards", provider="footystats",      # the old, wrong provenance
            source_path=original.source_path, container=original.container,
            period_support=original.period_support, null_semantics=original.null_semantics)
        assert R.capability_hash() != before
    finally:
        R.CAPABILITIES["yellow_cards"] = original
    assert R.capability_hash() == before
