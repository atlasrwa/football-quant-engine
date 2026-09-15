"""V5A.1 pre-spend regression battery. ZERO SPEND: no Bedrock, no network.

Every test named in the V5A.1 mandate §32, plus the grounding battery of §19. Each one is
written so that it FAILS if a defect from the aborted V5A reappears. A failure here blocks
paid execution.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src"); sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + "/research/hypothesis_engine")

from src.research.hypothesis_engine import corpus_adapter as CA, query_plan as QP
from src.research.hypothesis_engine import validator_v3 as V3, firewall_v3
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a1_packet as PK
from src.research.hypothesis_oos import v5a1_prompt as P
from src.research.hypothesis_oos import v5a1_semantics as S
from src.research.hypothesis_oos import v5a1_admissibility as ADM

OUT = f"{ROOT}/research/hypothesis_oos/out/v5a1"
V5A_OUT = f"{ROOT}/research/hypothesis_oos/out/v5a"


# ---------------------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def base():
    return json.load(open(f"{OUT}/packets_base.json"))


@pytest.fixture(scope="module")
def research():
    return json.load(open(f"{OUT}/packets_research.json"))


@pytest.fixture(scope="module")
def prereg():
    return json.load(open(f"{OUT}/PREREGISTRATION.json"))


@pytest.fixture(scope="module")
def exposure():
    return json.load(open(f"{OUT}/exposure_audit.json"))


@pytest.fixture(scope="module")
def isolation():
    return json.load(open(f"{OUT}/ab_isolation_audit.json"))


@pytest.fixture(scope="module")
def positions():
    return json.load(open(f"{OUT}/section_position_audit.json"))


@pytest.fixture(scope="module")
def idx():
    return CA.load_index()


def _hyp(hid, *, refs, family="SET_PIECE_GENERATION", subject="HOME_TEAM",
         metrics=("corners",), side="FOR", window="ALL_PRIOR", conditions=(),
         comparison="SUBJECT_OVERALL_BASELINE", caps=(), sufficiency="SUFFICIENT"):
    return {"hypothesis_id": hid, "research_family": family, "subject": subject,
            "question": "Does HOME_TEAM's corner production differ from its own overall "
                        "prior baseline across the matches recorded in this packet?",
            "target_metrics": list(metrics), "side": side, "window": window,
            "conditions": [dict(c) for c in conditions], "comparison": comparison,
            "evidence_refs": list(refs), "candidate_confounders": ["competition"],
            "required_capabilities": list(caps), "sufficiency": sufficiency,
            "priority": "MEDIUM"}


def _validate(packet, h):
    payload = {"fixture_id": packet["fixture_id"], "packet_hash": packet["packet_hash"],
               "hypotheses": [h]}
    return V3.validate(payload, packet=packet,
                       expected_packet_hash=packet["packet_hash"],
                       expected_fixture_id=packet["fixture_id"])


def _accepted(packet, h):
    r = _validate(packet, h)
    if not r.accepted:
        return False, r.reasons
    v = r.verdicts[0]
    return v.accepted, v.reasons


#: Fields whose PURPOSE is to disclaim something. A disclaimer must be allowed to name the
#: thing it rules out ("this packet carries no odds", "not a controlled comparison"), so
#: these are checked for their content rather than scanned for banned tokens. Every OTHER
#: key and string value in the packet is scanned.
#: `note` and `cohort_definition` are NOT exempt: they interpolate per-fixture data
#: (cohort counts, tercile bands), so they are scanned like any other value. Every field
#: below is asserted fixture-invariant by `test_documentation_fields_are_static_constants`.
_DISCLAIMER_FIELDS = frozenset({
    "interpretation", "definition", "caveat", "detail",
    "meaning", "cutoff_rule", "history_note", "orientation_rule", "null_rule",
    "section_type",
    "reliability_rule", "excluded_because", "repairable_by", "rule", "section_note",
    "row_order", "cell_orientation", "baseline_definition", "basis", "estimator",
    "direction_meaning", "unsupported_context", "excluded_metrics", "window_meaning",
    "venue_scope_meaning", "subject_codes", "id_grammar", "examples", "states",
    # metric-semantics documentation fields (task §17). Their PURPOSE is to name the
    # provider field a metric comes from, e.g. goals -> "score_home / score_away". That is
    # provenance documentation, not this fixture's score.
    "source_field", "provider", "units", "direction", "null_policy", "merge_policy",
    "provider_provenance", "similarity_method", "method", "raw_row_policy",
})


def _walk_kv(obj, key=None, keys=None, values=None, skip=False):
    """Collect every key, and every string value outside a disclaimer field."""
    keys = [] if keys is None else keys
    values = [] if values is None else values
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(str(k))
            _walk_kv(v, k, keys, values, skip or str(k) in _DISCLAIMER_FIELDS)
    elif isinstance(obj, list):
        for v in obj:
            _walk_kv(v, key, keys, values, skip)
    elif isinstance(obj, str) and not skip:
        values.append(obj)
    return keys, values


def _first(ids, prefix):
    c = sorted(i for i in ids if i.startswith(prefix))
    return c[0] if c else None


# =======================================================================================
# 1. arm_b_valid_evidence_ids_nonzero  /  arm_a_...
# =======================================================================================
def test_arm_b_valid_evidence_ids_nonzero(research):
    """THE V5A HS-1 regression: the research arm's packets had zero resolvable ids."""
    for fid, p in research.items():
        assert len(E.resolve_evidence_ids(p)) > 0, f"{fid}: research arm has no valid ids"


def test_arm_a_valid_evidence_ids_nonzero(base):
    for fid, p in base.items():
        assert len(E.resolve_evidence_ids(p)) > 0, f"{fid}: base arm has no valid ids"


def test_both_arms_resolve_through_the_same_function(base, research):
    """No arm-specific reference mechanism exists anywhere."""
    src = open(f"{ROOT}/src/research/hypothesis_engine/validator_v3.py").read()
    assert 'packet.get("evidence")' not in src
    for fid in base:
        for p in (base[fid], research[fid]):
            assert E.resolve_evidence_ids(p) == V3.resolve_valid_ids(p)


# =======================================================================================
# 2. arm_b_grounded_reference_acceptance / arm_a_grounded_reference_acceptance  (§19)
# =======================================================================================
def test_arm_b_grounded_reference_acceptance(research):
    for fid, p in research.items():
        ids = E.resolve_evidence_ids(p)
        cases = {
            "one summary": [_first(ids, "SUMMARY:HOME:ALL_PRIOR:ANY:corners_for")],
            "one match row": [_first(ids, "MATCH:HOME:M01")],
            "several match cells": sorted(i for i in ids
                                          if i.startswith("MATCH:HOME:M01:corners"))[:2],
            "formation": [_first(ids, "FORMATION:HOME")],
        }
        for label, refs in cases.items():
            refs = [r for r in refs if r]
            assert refs, f"{fid}: no id available for {label}"
            ok, why = _accepted(p, _hyp("H1", refs=refs))
            assert ok, f"{fid}: grounded hypothesis citing {label} rejected: {why}"


def test_arm_a_grounded_reference_acceptance(base):
    for fid, p in base.items():
        ids = E.resolve_evidence_ids(p)
        for label, ref in (("summary", _first(ids, "SUMMARY:HOME:ALL_PRIOR:ANY:corners_for")),
                           ("formation", _first(ids, "FORMATION:HOME"))):
            assert ref, f"{fid}: no id available for {label}"
            ok, why = _accepted(p, _hyp("H1", refs=[ref]))
            assert ok, f"{fid}: base-arm hypothesis citing {label} rejected: {why}"


def test_conditional_evidence_accepted_only_where_exposed(base, research):
    """Venue / recent-vs-long / opponent-profile citations work in the research arm and
    are correctly refused in the base arm, which truthfully says it lacks them."""
    for fid in research:
        rp, bp = research[fid], base[fid]
        rids = E.resolve_evidence_ids(rp)
        venue = _first(rids, "SUMMARY:HOME:ALL_PRIOR:HOME_ONLY:corners_for")
        recent = _first(rids, "SUMMARY:HOME:W5:ANY:corners_for")
        profile = _first(rids, "PROFILE:HOME:")
        if venue:
            ok, why = _accepted(rp, _hyp("H2", refs=[venue], caps=["venue"],
                                         conditions=[{"dimension": "venue", "value": "HOME"}],
                                         comparison="SUBJECT_VENUE_BASELINE"))
            assert ok, f"{fid}: venue hypothesis rejected in research arm: {why}"
        if recent:
            ok, why = _accepted(rp, _hyp("H3", refs=[recent], window="W5",
                                         comparison="SUBJECT_RECENT_VS_LONG_BASELINE"))
            assert ok, f"{fid}: recent-vs-long hypothesis rejected in research arm: {why}"
        if profile:
            ok, why = _accepted(rp, _hyp("H4", refs=[profile],
                                         family="OPPONENT_PROFILE_INTERACTION",
                                         metrics=["accurate_crosses"]))
            assert ok, f"{fid}: opponent-profile hypothesis rejected in research arm: {why}"
        bids = E.resolve_evidence_ids(bp)
        bsum = _first(bids, "SUMMARY:HOME:ALL_PRIOR:ANY:corners_for")
        ok, _ = _accepted(bp, _hyp("H5", refs=[bsum], caps=["venue"],
                                   conditions=[{"dimension": "venue", "value": "HOME"}],
                                   comparison="SUBJECT_VENUE_BASELINE"))
        assert not ok, f"{fid}: base arm accepted a venue hypothesis it cannot support"
        ok, _ = _accepted(bp, _hyp("H6", refs=[bsum], window="W5"))
        assert not ok, f"{fid}: base arm accepted a W5 hypothesis it cannot support"


def test_invalid_references_fail(base, research):
    for fid in research:
        for p in (base[fid], research[fid]):
            ok, _ = _accepted(p, _hyp("H7", refs=["MATCH:HOME:M99:corners_for"]))
            assert not ok
            ok, _ = _accepted(p, _hyp("H8", refs=["SUMMARY:HOME:ALL_PRIOR:ANY:unicorns_for"]))
            assert not ok


def test_cross_fixture_references_fail(base):
    fids = sorted(base)
    a, b = base[fids[0]], base[fids[1]]
    ids = E.resolve_evidence_ids(b)
    payload = {"fixture_id": b["fixture_id"], "packet_hash": b["packet_hash"],
               "hypotheses": [_hyp("H1", refs=[_first(ids, "SUMMARY:HOME")])]}
    r = V3.validate(payload, packet=a, expected_packet_hash=a["packet_hash"],
                    expected_fixture_id=a["fixture_id"])
    assert not r.accepted, "a payload bound to another fixture was accepted"


def test_empty_refs_fail_only_when_schema_requires_refs(research):
    p = research[sorted(research)[0]]
    ok, _ = _accepted(p, _hyp("H1", refs=[], sufficiency="SUFFICIENT"))
    assert not ok, "a SUFFICIENT hypothesis with no evidence was accepted"
    ok, why = _accepted(p, _hyp("H2", refs=[], sufficiency="INSUFFICIENT_EVIDENCE"))
    assert ok, f"an honest abstention was rejected: {why}"


def test_compiler_accepts_grounded_hypotheses(research):
    p = research[sorted(research)[0]]
    ids = E.resolve_evidence_ids(p)
    h = _hyp("H1", refs=[_first(ids, "MATCH:HOME:M01")])
    r = _validate(p, h)
    assert r.accepted and r.accepted_hypotheses
    plans = QP.compile_hypothesis(r.accepted_hypotheses[0], fixture_id=p["fixture_id"],
                                  cutoff_unix=p["information_cutoff_unix"])
    assert plans and all(getattr(pl, "plan", None) is not None for pl in plans), \
        f"compiler rejected a validated hypothesis: {[getattr(pl,'reasons',None) for pl in plans]}"


# =======================================================================================
# 3. duplicate ids / aliases
# =======================================================================================
def test_duplicate_evidence_ids_zero(base, research):
    audit = json.load(open(f"{OUT}/evidence_id_audit.json"))
    for fid, a in audit.items():
        assert a["DUPLICATE_EVIDENCE_IDS"]["base"] == []
        assert a["DUPLICATE_EVIDENCE_IDS"]["research"] == []


def test_duplicate_match_aliases_zero(research):
    """V5A defect M-4: bare provider match ids collided across the two teams 9 times."""
    for fid, p in research.items():
        seen = []
        for sec in p["sections"]:
            if sec.get("section_type") != "MATCH_LEVEL_OBSERVATIONS":
                continue
            for blk in sec["blocks"]:
                seen += [r["evidence_id"] for r in blk["rows"]]
        assert len(seen) == len(set(seen)), f"{fid}: duplicate match alias"


def test_duplicate_ids_fail_construction():
    r = E.EvidenceRecord(evidence_id="X:1", evidence_type=E.DERIVED_SUMMARY)
    with pytest.raises(E.DuplicateEvidenceId):
        E.assert_unique([r, r])


# =======================================================================================
# 4. same_base_history_universe / arm_b_superset_of_arm_a_base_evidence
# =======================================================================================
def test_same_base_history_universe(base, research, idx, exposure):
    """HS-2: V5A compared Arm A's means over up to 104 matches with Arm B's over 30."""
    by = {r.fixture_id: r for r in idx.records}
    for fid in base:
        t = by[fid]
        expect = {"HOME": len(PK.full_prior(idx, t, t.home)),
                  "AWAY": len(PK.full_prior(idx, t, t.away))}
        for arm_packets in (base, research):
            p = arm_packets[fid]
            for sec in p["sections"]:
                if sec.get("section_type") != "DERIVED_SUMMARIES":
                    continue
                cols = sec["columns"]
                iw, iv, isb, isn = (cols.index("window"), cols.index("venue_scope"),
                                    cols.index("subject"), cols.index("sample_n"))
                for row in sec["rows"]:
                    if row[iw] == "ALL_PRIOR" and row[iv] == "ANY":
                        assert row[isn] <= expect[row[isb]]
                        assert row[isn] >= expect[row[isb]] - 60, (
                            f"{fid}: ALL_PRIOR sample_n {row[isn]} far below the "
                            f"{expect[row[isb]]}-match universe")
        # and the two arms must agree exactly
        na = _allprior_ns(base[fid])
        nb = _allprior_ns(research[fid])
        assert na == nb, f"{fid}: ALL_PRIOR sample sizes differ across arms"


def _allprior_ns(p):
    out = {}
    for sec in p["sections"]:
        if sec.get("section_type") != "DERIVED_SUMMARIES":
            continue
        cols = sec["columns"]
        iw, iv, ii, isn = (cols.index("window"), cols.index("venue_scope"),
                           cols.index("evidence_id"), cols.index("sample_n"))
        for row in sec["rows"]:
            if row[iw] == "ALL_PRIOR" and row[iv] == "ANY":
                out[row[ii]] = row[isn]
    return out


def test_arm_b_superset_of_arm_a_base_evidence(isolation):
    for fid, a in isolation.items():
        assert a["RESEARCH_SUPERSET_OF_BASE"], f"{fid}: research arm is not a superset"
        assert a["BASE_IDS_NOT_IN_RESEARCH"] == []
        assert a["N_UNEXPECTED_SHARED_VALUE_MISMATCHES"] == 0, (
            f"{fid}: shared evidence differs in value across arms: "
            f"{a['UNEXPECTED_SHARED_VALUE_MISMATCHES']}")
        assert a["RESEARCH_ONLY_IDS"] > 0


def test_arm_b_does_not_omit_anything_arm_a_receives(base, research):
    for fid in base:
        ra = {r["evidence_id"]: r for r in E.evidence_records_of(base[fid])
              if r.get("evidence_id")}
        rb = {r["evidence_id"]: r for r in E.evidence_records_of(research[fid])
              if r.get("evidence_id")}
        missing = sorted(set(ra) - set(rb))
        assert not missing, f"{fid}: research arm omits base evidence {missing[:5]}"


# =======================================================================================
# 5. no_visible_treatment_label
# =======================================================================================
def test_documentation_fields_are_static_constants(base, research):
    """The disclaimer exemption must be an invariant, not a list that grew until the
    scanners passed.

    A field may be exempt from token scanning only if it carries no per-fixture data --
    i.e. its value set is identical across all 10 fixtures within an arm. `note` and
    `cohort_definition` interpolate per-fixture counts and bands, so they are deliberately
    NOT exempt and are scanned like any other value.
    """
    def values_by_field(packet):
        acc = {}

        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in _DISCLAIMER_FIELDS:
                        acc.setdefault(k, set()).add(json.dumps(v, sort_keys=True))
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(packet)
        return acc

    for arm_packets in (base, research):
        fids = sorted(arm_packets)
        ref = values_by_field(arm_packets[fids[0]])
        for fid in fids[1:]:
            got = values_by_field(arm_packets[fid])
            assert got == ref, (
                "an exempted documentation field varies per fixture and therefore may "
                "carry data: "
                f"{sorted(k for k in set(got) | set(ref) if got.get(k) != ref.get(k))}")
    assert "note" not in _DISCLAIMER_FIELDS
    assert "cohort_definition" not in _DISCLAIMER_FIELDS


def test_no_visible_treatment_label(base, research):
    """V5A defect M-6: `"arm": "B_full_fidelity"` was the first key of every Arm B payload.

    Checked structurally: no KEY and no non-disclaimer string VALUE may name the condition.
    A disclaimer is allowed to say "this is not a controlled comparison"; a field called
    `arm` or a value of `full_fidelity` is not allowed anywhere.
    """
    hard = ("arm_a", "arm_b", "full_fidelity", "b_full_fidelity", "condition_a",
            "condition_b", "experiment_arm", "baseline_arm", "treatment_arm")
    generic = ("control", "treatment", "compressed", "arm")
    for fid in base:
        for p in (base[fid], research[fid]):
            payload = P.build_user_payload(p).lower()
            for label in hard:
                assert label not in payload, f"{fid}: treatment label {label!r} serialized"
            keys, values = _walk_kv(p)
            for k in keys:
                assert k.lower() not in generic, f"{fid}: field named {k!r}"
                for label in hard:
                    assert label not in k.lower(), f"{fid}: field {k!r}"
            for v in values:
                assert v.strip().lower() not in generic, f"{fid}: value {v!r}"
            assert re.search(r'"arm[_a-z]*"\s*:', payload) is None


def test_packet_schema_version_identical_across_arms(base, research):
    for fid in base:
        assert (base[fid]["packet_schema_version"]
                == research[fid]["packet_schema_version"] == PK.PACKET_SCHEMA_VERSION)
        assert (base[fid]["evidence_interface_version"]
                == research[fid]["evidence_interface_version"])


def test_system_prompt_identical_across_arms(prereg):
    assert prereg["request_manifest"]["system_prompt_identical_across_arms"] is True
    assert (hashlib.sha256(P.SYSTEM_PROMPT.encode()).hexdigest()
            == prereg["request_manifest"]["system_prompt_sha256"])


# =======================================================================================
# 6. truthful_availability_map / no_prompt_invited_unsupported_dimension
# =======================================================================================
def test_truthful_availability_map(base, research):
    """V5A HS-3: Arm A's `data_quality.n_unavailable: 0` asserted nothing was missing while
    four whole evidence classes were withheld."""
    for fid in base:
        for p, has_rows, has_cond in ((base[fid], False, False),
                                      (research[fid], True, True)):
            states = ADM.exposure_states(p)
            sect = {s["section_type"] for s in p["sections"]}
            assert (states["match_level_observations"] == E.EXPOSED) == has_rows
            assert ("MATCH_LEVEL_OBSERVATIONS" in sect) == has_rows
            for dim in ("venue_splits", "recent_vs_long", "opponent_profile_response"):
                exposed = states[dim] in (E.EXPOSED, E.EXPOSED_LOW_COVERAGE)
                assert exposed == has_cond, f"{fid}/{dim}: availability map is untruthful"
            # every declaration carries the full triple
            for sec in p["sections"]:
                if sec.get("section_type") != "AVAILABILITY_MAP":
                    continue
                for rec in sec["records"]:
                    for k in ("PROVIDER_AVAILABLE", "DERIVABLE_PIT_SAFE", "EXPOSED_TO_LLM"):
                        assert k in rec
                    assert rec["EXPOSED_TO_LLM"] in E.EXPOSURE_STATES


def test_availability_matches_what_the_packet_actually_contains(base, research):
    for fid in base:
        for p in (base[fid], research[fid]):
            states = ADM.exposure_states(p)
            wins = ADM.exposed_windows(p)
            recent = states["recent_vs_long"] in (E.EXPOSED, E.EXPOSED_LOW_COVERAGE)
            assert recent == bool({"W5", "W10"} & wins)
            venue_rows = any(
                r[sec["columns"].index("venue_scope")] in ("HOME_ONLY", "AWAY_ONLY")
                for sec in p["sections"]
                if sec.get("section_type") == "DERIVED_SUMMARIES"
                for r in sec["rows"])
            venue_state = states["venue_splits"] in (E.EXPOSED, E.EXPOSED_LOW_COVERAGE)
            assert venue_state == venue_rows


def test_no_prompt_invited_unsupported_dimension(base, research):
    """The prompt must promise no section, and the admissible surface must be exactly what
    the packet exposes -- not schema_v2's wider frozen enums."""
    txt = P.SYSTEM_PROMPT
    for promised in ("You will receive", "match_level_history", "derived_summaries",
                     "opponent_profile_context", "availability_map:"):
        assert promised not in txt, f"prompt promises packet structure: {promised!r}"
    for fid in base:
        for p in (base[fid], research[fid]):
            surf = ADM.packet_capability_summary(p)
            assert set(surf["metrics"]) == set(S.CANONICAL_METRICS)
            for m in S.EXCLUDED_METRICS:
                assert m not in surf["metrics"]
                ok, _ = _accepted(p, _hyp("H1", metrics=[m],
                                          refs=[_first(E.resolve_evidence_ids(p),
                                                       "SUMMARY:HOME")]))
                assert not ok, f"{fid}: excluded metric {m} was accepted"
            for c in ("LEAGUE_ENVIRONMENT_BASELINE", "SUBJECT_COMPETITION_BASELINE"):
                ok, _ = _accepted(p, _hyp("H2", comparison=c,
                                          refs=[_first(E.resolve_evidence_ids(p),
                                                       "SUMMARY:HOME")]))
                assert not ok, f"{fid}: unsupported comparison {c} was accepted"


def test_formation_restraint(base, research):
    """Formation can be CONDITIONED on only where the packet carries it per observation.

    Both arms carry a formation COVERAGE record, so without the per-observation rule a
    formation-conditioned hypothesis would be admitted against a packet with no per-match
    formation at all. Coverage is low in every fixture, and the packet says so three ways;
    the research arm is allowed to ask, and restraint is then a measured outcome.
    """
    for fid in base:
        bids = E.resolve_evidence_ids(base[fid])
        h = _hyp("H1", family="FORMATION_INTERACTION",
                 refs=[_first(bids, "FORMATION:HOME")],
                 conditions=[{"dimension": "own_formation_family", "value": "BACK_THREE"}],
                 caps=["historical_formation"])
        ok, why = _accepted(base[fid], h)
        assert not ok, f"{fid}: base arm accepted a formation-conditioned hypothesis"
        assert any("each observation" in r for r in why), why
        rids = E.resolve_evidence_ids(research[fid])
        h2 = dict(h, evidence_refs=[_first(rids, "FORMATION:HOME")])
        ok, why = _accepted(research[fid], h2)
        assert ok, f"{fid}: research arm rejected a formation-conditioned hypothesis: {why}"
        # and low coverage must be visible three ways
        states = ADM.exposure_states(research[fid])
        assert states["formation_recorded_history"] in (E.EXPOSED, E.EXPOSED_LOW_COVERAGE)
        rec = [r for sec in research[fid]["sections"]
               if sec["section_type"] == "FORMATION_CONTEXT"
               for r in sec["records"]]
        assert rec and all(x["coverage"] is not None for x in rec)
        assert all(x["matches_without_recorded_formation"] >= 0 for x in rec)
        blocks = [s for s in research[fid]["sections"]
                  if s["section_type"] == "MATCH_LEVEL_OBSERVATIONS"][0]["blocks"]
        assert any(r["own_formation_recorded"] is None for b in blocks for r in b["rows"])


def test_excluded_metrics_are_declared_in_the_packet(base, research):
    for fid in base:
        for p in (base[fid], research[fid]):
            sem = [s for s in p["sections"] if s["section_type"] == "METRIC_SEMANTICS"][0]
            assert set(sem["content"]["excluded_metrics"]) == set(S.EXCLUDED_METRICS)
            assert "npxg" in sem["content"]["excluded_metrics"]


# =======================================================================================
# 7. raw_rows_before_summary_majority / no_hidden_truncation / cell fidelity
# =======================================================================================
def test_raw_rows_before_summary_majority(positions):
    """V5A defect M-1: the rows sat at 81.5-95.9% behind ~80% of summary bytes."""
    for fid, arms in positions.items():
        secs = arms["research"]
        rows = [s for s in secs if s["section_type"] == "MATCH_LEVEL_OBSERVATIONS"]
        sums = [s for s in secs if s["section_type"] in
                ("DERIVED_SUMMARIES", "OPPONENT_PROFILE_SUMMARIES")]
        assert rows, f"{fid}: research arm has no match rows"
        assert rows[0]["byte_end"] <= min(s["byte_start"] for s in sums), (
            f"{fid}: summary content precedes the match record")


def test_both_teams_rows_present_and_before_summaries(research, positions):
    for fid, p in research.items():
        blk = [s for s in p["sections"]
               if s["section_type"] == "MATCH_LEVEL_OBSERVATIONS"][0]["blocks"]
        subjects = [b["subject"] for b in blk]
        assert subjects == ["HOME", "AWAY"], f"{fid}: {subjects}"
        for b in blk:
            assert b["n_rows"] == len(b["rows"]) > 0


def test_no_hidden_truncation(base, research, exposure, idx):
    by = {r.fixture_id: r for r in idx.records}
    for fid, p in research.items():
        payload = P.build_user_payload(p)
        assert '"..."' not in payload and "…" not in payload
        assert not re.search(r"truncat|elided|clipped", payload, re.I)
        t = by[fid]
        for blk in [s for s in p["sections"]
                    if s["section_type"] == "MATCH_LEVEL_OBSERVATIONS"][0]["blocks"]:
            team = t.home if blk["subject"] == "HOME" else t.away
            expect = len(PK.raw_rows(PK.full_prior(idx, t, team)))
            assert blk["n_rows"] == expect == len(blk["rows"])
            for row in blk["rows"]:
                assert len(row["cells"]) == len(blk["cell_columns"]) == len(S.cell_columns())
        e = exposure["fixtures"][fid]
        assert e["UNEXPLAINED_OMISSION"] == 0
        assert e["ROWS_OMITTED_BY_RAW_ROW_POLICY"] is not None


def test_serialized_cells_equal_canonical(exposure):
    assert exposure["cell_fidelity"]["clean"] is True
    assert exposure["cell_fidelity"]["mismatches"] == 0
    assert exposure["cell_fidelity"]["checked"] > 10000
    assert exposure["hard_fail"] is False
    for fid, e in exposure["fixtures"].items():
        assert e["CELL_FIDELITY_MISMATCHES"] == 0


def test_chronology_and_row_order(research):
    for fid, p in research.items():
        for blk in [s for s in p["sections"]
                    if s["section_type"] == "MATCH_LEVEL_OBSERVATIONS"][0]["blocks"]:
            ks = [r["kickoff_unix"] for r in blk["rows"]]
            assert ks == sorted(ks), f"{fid}: rows not chronological"
            assert [r["chronological_rank"] for r in blk["rows"]] == list(
                range(1, len(ks) + 1))
            assert "CHRONOLOGICAL_ASCENDING" in blk["row_order"]
            assert all(r["kickoff_date"] for r in blk["rows"])


# =======================================================================================
# 8. leakage
# =======================================================================================
def test_target_fixture_excluded_and_future_observations_excluded(research, idx):
    by = {r.fixture_id: r for r in idx.records}
    for fid, p in research.items():
        cutoff = p["information_cutoff_unix"]
        assert cutoff == int(by[fid].kickoff_unix)
        for blk in [s for s in p["sections"]
                    if s["section_type"] == "MATCH_LEVEL_OBSERVATIONS"][0]["blocks"]:
            for row in blk["rows"]:
                assert row["kickoff_unix"] < cutoff


def test_no_target_outcome_and_no_future_market(base, research, idx):
    by = {r.fixture_id: r for r in idx.records}
    for fid in base:
        t = by[fid]
        for p in (base[fid], research[fid]):
            payload = P.build_user_payload(p).lower()
            for tok in re.split(r"[^A-Za-z]+", f"{t.home} {t.away} {t.competition}"):
                if len(tok) >= 4:
                    assert tok.lower() not in payload, f"{fid}: identity leak {tok!r}"
            keys, values = _walk_kv(p)
            # `market_prices` is the availability dimension that DECLARES market data is
            # absent, so the name is expected. Assert it declares absence rather than
            # banning the word that makes the declaration readable.
            states = ADM.exposure_states(p)
            assert states["market_prices"] == E.NOT_PROVIDED_BY_SOURCE
            # A value that IS one of the declared unsupported-context constants is a
            # declaration of absence ("this packet carries no odds"), not data. These are
            # static module strings, identical in every packet, so exempting them by exact
            # match cannot hide a per-fixture value.
            declared = set(S.UNSUPPORTED_CONTEXT.values())
            keys = [k for k in keys if k != "market_prices"]
            values = [v for v in values
                      if v not in declared
                      and v not in ("market_prices", E.availability_id("market_prices"))]
            for banned in ("odds", "price", "market", "probability", "implied",
                           "score_home", "score_away", "fulltime", "fixture_result"):
                for k in keys:
                    assert banned not in k.lower(), f"{fid}: field {k!r} ({banned})"
                for v in values:
                    assert banned not in v.lower(), f"{fid}: value {v!r} ({banned})"


def test_no_llm_to_p_model_path():
    """Import-graph isolation: nothing in the V5A.1 stack may reach prediction code."""
    banned = ("p_model", "pilotC_stat_mixer", "bedrock", "boto3", "prospective",
              "broadcast", "forward", "dixon_coles", "market_family")
    for mod in ("v5a1_evidence", "v5a1_semantics", "v5a1_packet", "v5a1_prompt",
                "v5a1_admissibility", "v5a1_ontology"):
        src = open(f"{ROOT}/src/research/hypothesis_oos/{mod}.py").read().lower()
        for b in banned:
            assert b not in src, f"{mod}.py references {b!r}"
    for mod in ("validator_v3", "firewall_v3"):
        src = open(f"{ROOT}/src/research/hypothesis_engine/{mod}.py").read().lower()
        for b in banned:
            assert b not in src, f"{mod}.py references {b!r}"


# =======================================================================================
# 9. opponent_profile_direction_unambiguous
# =======================================================================================
def test_opponent_profile_direction_unambiguous(research):
    """V5A defect M-2: `axes.<axis>.HOME` was a SUBJECT label in a packet where HOME meant
    venue everywhere else, and carried no cohort, response or baseline."""
    for fid, p in research.items():
        secs = [s for s in p["sections"]
                if s["section_type"] == "OPPONENT_PROFILE_SUMMARIES"]
        if not secs:
            continue
        sec = secs[0]
        cohorts = sec["content"]["cohorts"]
        assert cohorts
        for key, c in cohorts.items():
            for k in ("semantic_label", "response_direction", "similarity_axis",
                      "similarity_method", "upcoming_opponent_band_on_axis",
                      "cohort_definition", "cohort_n"):
                assert c.get(k) is not None, f"{fid}: cohort {key} missing {k}"
            assert c["subject"] in ("HOME", "AWAY")
            assert "SIMILAR_TO" in c["semantic_label"]
        cols = sec["columns"]
        for need in ("cohort_value", "cohort_n", "baseline_value", "baseline_n",
                     "response_metric", "cohort_key"):
            assert need in cols, f"{fid}: profile table missing {need}"
        for row in sec["rows"]:
            assert row[cols.index("cohort_key")] in cohorts


def test_opponent_profile_is_descriptive_not_predictive(research):
    banned = ("advantage", "edge", "favourable", "favorable", "expected effect",
              "positive matchup", "will ", "predict")
    for fid, p in research.items():
        secs = [s for s in p["sections"]
                if s["section_type"] == "OPPONENT_PROFILE_SUMMARIES"]
        if not secs:
            continue
        keys, values = _walk_kv(secs[0])
        for b in banned:
            for k in keys:
                assert b not in k.lower(), f"{fid}: profile field {k!r} ({b!r})"
            for v in values:
                assert b not in v.lower(), (
                    f"{fid}: profile section uses predictive language {b!r} in {v!r}")
        disc = secs[0]["content"]["interpretation"].lower()
        assert "not expected effects" in disc and "not a controlled comparison" in disc


# =======================================================================================
# 10. semantics / priming
# =======================================================================================
def test_xg_npxg_semantics_resolved_or_npxg_excluded(base, research):
    assert "npxg" in S.EXCLUDED_METRICS
    assert "npxg" not in S.CANONICAL_METRICS
    assert S.EXCLUDED_METRICS["npxg"]["excluded_because"] == "PROVIDER_SOURCE_INCONSISTENCY"
    for fid in base:
        for p in (base[fid], research[fid]):
            assert "npxg_for" not in P.build_user_payload(p)


def test_every_exposed_metric_has_documented_semantics(base, research):
    for m in S.CANONICAL_METRICS:
        d = S.METRIC_SEMANTICS[m]
        for k in ("source_field", "provider", "units", "definition", "direction",
                  "null_policy", "merge_policy"):
            assert d.get(k), f"{m} missing {k}"
    for fid in base:
        for p in (base[fid], research[fid]):
            sem = [s for s in p["sections"] if s["section_type"] == "METRIC_SEMANTICS"][0]
            assert set(sem["content"]["metrics"]) == set(S.CANONICAL_METRICS)
            assert sem["content"]["orientation_rule"]
            assert sem["content"]["null_rule"]
            assert sem["content"]["reliability_rule"]


def test_no_priming_language_in_packets(base, research):
    for fid in base:
        for p in (base[fid], research[fid]):
            low = P.build_user_payload(p).lower()
            for w in P.PRIMING_PHRASES:
                if w.lower() in P.PROHIBITION_ONLY_TERMS:
                    continue
                assert w.lower() not in low, f"{fid}: priming phrase {w!r} in packet"


def test_prompt_does_not_prime_or_quota_dimensions():
    """The prompt is wrapped prose, so collapse whitespace before matching."""
    low = re.sub(r"\s+", " ", P.SYSTEM_PROMPT.lower())
    for w in P.PRIMING_PHRASES:
        if w.lower() in P.PROHIBITION_ONLY_TERMS:
            continue
        assert w.lower() not in low, f"prompt contains priming phrase {w!r}"
    # the prohibition-only terms must appear ONLY inside the HARD RULES prohibition
    rules = low.split("hard rules")[-1]
    for w in P.PROHIBITION_ONLY_TERMS:
        assert low.count(w) == rules.count(w), (
            f"{w!r} appears outside the prohibition list")
    assert "boundary, not a checklist" in low
    assert "insufficient_evidence is a correct and valued answer" in low
    # and it must not tell the model which dimensions to produce
    for quota in ("generate venue", "use opponent profiles", "use recent form",
                  "generate interactions", "use formation"):
        assert quota not in low


# =======================================================================================
# 11. frozen artifacts untouched
# =======================================================================================
def test_champion_unchanged(prereg):
    cp = prereg["champion_protection"]
    assert cp["current_sha256"] == cp["frozen_sha256"]
    assert _sha(cp["artifact"]) == cp["frozen_sha256"]


def test_v2_v3_v4_unchanged(prereg):
    """Every module hashed into the frozen V3 / aborted-V5A preregistrations is byte-identical."""
    assert all(prereg["frozen_v5a_modules_unchanged"].values()), \
        prereg["frozen_v5a_modules_unchanged"]
    v5a = json.load(open(f"{V5A_OUT}/PREREGISTRATION.json"))
    for mod, h in v5a["module_hashes"].items():
        if not os.path.exists(f"{ROOT}/{mod}"):
            continue
        if mod.endswith(("_build_v5a.py", "_freeze_v5a.py")) or "v5a_" in mod:
            continue
        assert _sha(f"{ROOT}/{mod}") == h, f"{mod} changed since the V5A freeze"


def test_v5a_artifacts_preserved(prereg):
    assert prereg["V5A_PREVIOUS_VERSION"] == "ABORTED_PRE_SPEND"
    for f in ("PREREGISTRATION.json", "arm_a_packets.json", "arm_b_packets.json",
              "exposure_audit.json"):
        assert os.path.exists(f"{V5A_OUT}/{f}"), f"aborted V5A artifact {f} missing"


def test_no_network_or_bedrock_in_the_build_path():
    """Checked on the IMPORT GRAPH, not on prose: the docstrings legitimately say
    'no Bedrock, no network'."""
    import ast
    banned = {"boto3", "botocore", "requests", "httpx", "urllib", "socket", "http"}
    for path in ("research/hypothesis_engine/_build_v5a1.py",
                 "research/hypothesis_engine/_freeze_v5a1.py",
                 "src/research/hypothesis_oos/v5a1_evidence.py",
                 "src/research/hypothesis_oos/v5a1_packet.py",
                 "src/research/hypothesis_oos/v5a1_prompt.py",
                 "src/research/hypothesis_oos/v5a1_semantics.py",
                 "src/research/hypothesis_oos/v5a1_admissibility.py",
                 "src/research/hypothesis_oos/v5a1_ontology.py",
                 "src/research/hypothesis_engine/validator_v3.py",
                 "src/research/hypothesis_engine/firewall_v3.py"):
        tree = ast.parse(open(f"{ROOT}/{path}").read())
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module.split(".")[0])
        bad = mods & banned
        assert not bad, f"{path} imports {bad}"


# =======================================================================================
# 12. manifest integrity
# =======================================================================================
def test_request_manifest_hashes_reproduce(prereg, base, research):
    packets = {"base": base, "research": research}
    for call in prereg["request_manifest"]["calls"]:
        p = packets[call["arm_internal"]][call["fixture_id"]]
        req = P.serialized_request(p)
        assert len(req) == call["request_bytes"]
        assert hashlib.sha256(req.encode()).hexdigest() == call["serialized_request_sha256"]
        assert p["packet_hash"] == call["packet_hash"]
        assert call["valid_evidence_ids"] > 0


def test_packet_hash_reproduces(base, research):
    for packets in (base, research):
        for fid, p in packets.items():
            assert E.packet_hash(p) == p["packet_hash"], f"{fid}: packet hash mismatch"


def test_frozen_artifacts_are_byte_reproducible():
    """A frozen artifact that cannot be reproduced cannot be verified.

    The build is re-run under a different PYTHONHASHSEED and every output must be
    byte-identical. This caught a real defect: `id_prefix_counts` was built with
    `Counter` over a SET, so its key order followed set-iteration order and the audit
    file differed run to run while its content stayed the same.
    """
    import tempfile
    before = {}
    for name in os.listdir(OUT):
        if name.endswith(".json"):
            before[name] = _sha(f"{OUT}/{name}")
    env = dict(os.environ, PYTHONHASHSEED="12345")
    for script in ("_build_v5a1.py", "_freeze_v5a1.py"):
        r = subprocess.run([sys.executable, f"{ROOT}/research/hypothesis_engine/{script}"],
                           capture_output=True, env=env, cwd=ROOT)
        assert r.returncode == 0, r.stderr.decode()[-600:]
    after = {name: _sha(f"{OUT}/{name}") for name in before}
    differing = sorted(n for n in before if before[n] != after[n])
    assert not differing, f"not byte-reproducible under a different hash seed: {differing}"


def test_cost_model_within_ceiling(prereg):
    c = prereg["cost_model"]
    assert c["expected_cost_usd"] <= c["p90_cost_usd"] <= c["hard_ceiling_usd"]
    assert c["n_calls_total"] == 38
    assert c["hard_ceiling_usd"] < 10.0


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()
