"""V3 patch (identity-neutral LLM evidence processing) invariants — patch §59.

Deterministic, offline tests (no Bedrock). LLM_MATCHUP_V2 (hardening/) is untouched and its
own test suite (test_llm_matchup_hardening.py) is unaffected. These tests exercise the NEW
V3 modules only:

  * real team/competition names absent from the neutralized packet;
  * human-readable exact formation label / family name absent from the neutralized packet;
  * evidence ids unchanged (neutral IDs — nothing about neutralization touches ids);
  * the source packet is never mutated;
  * neutralization is deterministic and both hashes (source + neutral) are reproducible;
  * the V4 Bedrock adapter structurally REFUSES a non-neutralized packet;
  * team/competition/formation-id ALIAS controls change only the aliased token;
  * formation structural attributes actually vary across distinct formation shapes;
  * FOR/AGAINST metric orientation and A/B role labelling survive neutralization unchanged;
  * the RESOLVED-vs-PREMATCH formation status boundary is untouched by neutralization;
  * V4 reuses V3's output schema/validator unchanged (no silent divergence);
  * the global identity-control gate (added to eligibility.py) is deterministic.

Run: .venv/bin/python -m pytest tests/research/test_llm_matchup_identity_neutral.py -q
"""
import sys, json, copy
sys.path.insert(0, "/home/ubuntu")
import pytest

from src.research.llm_matchup.hardening import neutralize as NZ
from src.research.llm_matchup.hardening import neutralize_v3 as NZ3
from src.research.llm_matchup.hardening import formation_structure as FS
from src.research.llm_matchup.hardening import versions_v3 as V3
from src.research.llm_matchup.hardening import versions_v2 as V2
from src.research.llm_matchup.hardening import prompt_v3 as PR3
from src.research.llm_matchup.hardening import prompt_v4 as PR4
from src.research.llm_matchup.hardening import schema_v3 as SCH3
from src.research.llm_matchup.hardening import validator_v3 as VV3
from src.research.llm_matchup.hardening import adapter_v3 as A3
from src.research.llm_matchup.hardening import adapter_v4 as A4
from src.research.llm_matchup.hardening import eligibility as EL
from src.research.llm_matchup.hardening import audit_request as AR


def _real_packet():
    """A packet shaped like evidence_v2's V2 builder output, including formation_context
    and fc_/fmx_ scope keys, real names throughout."""
    return {
        "packet_schema_version": "fixture_evidence_packet_v3",
        "cohort_policy_version": "cohort_policy_v1",
        "fixture": {"fixture_id": "mt_1", "home": "Real Madrid", "away": "Athletic Bilbao",
                    "competition": "laliga", "season": "2023", "kickoff_unix": 1000},
        "information_cutoff_unix": 1000,
        "competition_context": {"tags": []},
        "team_a": {"name": "Real Madrid", "venue": "home", "style_tags": ["HIGH_WIDTH"],
                   "evidence_ids": ["A_ATK_crosses_for_aa"],
                   "formation_evidence_ids": ["A_FC_fc_crosses_for_bb"]},
        "team_b": {"name": "Athletic Bilbao", "venue": "away", "style_tags": ["BALANCED"],
                   "evidence_ids": ["B_DEF_crosses_against_cc"]},
        "league_environment": {"evidence_ids": []},
        "evidence": [
            {"id": "A_ATK_crosses_for_aa", "metric": "crosses_for", "value": 18.0,
             "sample_n": 20, "scope": {"team": "Real Madrid", "opponent": "Athletic Bilbao",
                                       "venue": "home", "side": "for",
                                       "competition": "laliga", "season": "2023"},
             "reliability": "HIGH", "shrinkage_level": "DIRECT", "evidence_level": "VENUE_OVERALL",
             "source_provider": "thestatsapi", "source_field": "crosses_for", "cutoff_unix": 1000,
             "temporal_status": "PIT_SAFE"},
            {"id": "B_DEF_crosses_against_cc", "metric": "crosses_against", "value": 21.0,
             "sample_n": 18, "scope": {"team": "Athletic Bilbao", "opponent": "Real Madrid",
                                       "venue": "away", "side": "against",
                                       "competition": "laliga", "season": "2023"},
             "reliability": "HIGH", "shrinkage_level": "DIRECT", "evidence_level": "VENUE_OVERALL",
             "source_provider": "thestatsapi", "source_field": "crosses_for", "cutoff_unix": 1000,
             "temporal_status": "PIT_SAFE"},
            {"id": "A_FC_fc_crosses_for_bb", "metric": "fc_crosses_for", "value": 22.0,
             "sample_n": 6, "scope": {"team": "Real Madrid", "venue": "home", "side": "for",
                                      "prematch_formation": "4-3-3", "formation_family": "BACK4_1STRIKER",
                                      "prematch_source": "PROJECTED"},
             "reliability": "MEDIUM", "shrinkage_level": "SHRUNK", "evidence_level": "EXACT_FORMATION",
             "source_provider": "derived_formation", "source_field": "fc_crosses (EXACT_FORMATION)",
             "cutoff_unix": 1000, "temporal_status": "PIT_SAFE"},
            {"id": "A_FMX_fmx_corners_for_dd", "metric": "fmx_corners_for", "value": 5.0,
             "sample_n": 3, "scope": {"team": "Real Madrid", "venue": "home", "side": "for",
                                      "team_formation": "4-3-3", "team_family": "BACK4_1STRIKER",
                                      "opp_formation": "3-5-2", "opp_family": "BACK3_WINGBACK",
                                      "preferred_tier": "FAMILY",
                                      "tier_summary": [{"tier": "FAMILY", "n": 3, "value": 5.0}]},
             "reliability": "MEDIUM", "shrinkage_level": "HIERARCHICAL", "evidence_level": "FAMILY",
             "source_provider": "derived_formation", "source_field": "fmx_corners (tier FAMILY)",
             "cutoff_unix": 1000, "temporal_status": "PIT_SAFE"},
        ],
        "unsupported_context": {"formation_status": "FORMATION_UNKNOWN",
                                "formation_reason": "x", "injury_status": "INJURY_STATUS_UNKNOWN",
                                "neutral_venue": "UNKNOWN"},
        "formation_context": {
            "policy_version": "formation_policy_v1",
            "resolution_status": "RESOLVED_AVAILABLE",
            "prematch_status": "PROJECTED",
            "team_a_prematch_formation": {"formation": "4-3-3", "formation_family": "BACK4_1STRIKER",
                                          "source_type": "PROJECTED", "confidence": "LOW",
                                          "source_version": "v0",
                                          "distribution": {"4-3-3": 0.7, "4-2-3-1": 0.3},
                                          "policy_version": "formation_policy_v1",
                                          "family_version": "formation_family_v1"},
            "team_b_prematch_formation": {"formation": "3-5-2", "formation_family": "BACK3_WINGBACK",
                                          "source_type": "PROJECTED", "confidence": "LOW",
                                          "source_version": "v0", "distribution": None,
                                          "policy_version": "formation_policy_v1",
                                          "family_version": "formation_family_v1"},
            "formation_family_version": "formation_family_v1",
            "leakage_note": "x",
        },
        "data_quality": {"n_evidence": 4, "n_pit_safe": 4, "n_unavailable": 0},
        "provider_provenance": {"primary": "thestatsapi"},
    }


REAL_STRINGS = ["Real Madrid", "Athletic Bilbao", "laliga", "4-3-3", "3-5-2",
               "BACK4_1STRIKER", "BACK3_WINGBACK"]


def _all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _all_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_strings(v)


# --- identity removal -------------------------------------------------------------
def test_real_team_names_absent():
    n = NZ3.neutralize_for_llm_v2(_real_packet())
    blob = "\n".join(_all_strings(n))
    assert "Real Madrid" not in blob and "Athletic Bilbao" not in blob
    assert n["fixture"]["home"] == "TEAM_A" and n["fixture"]["away"] == "TEAM_B"


def test_real_competition_name_absent():
    n = NZ3.neutralize_for_llm_v2(_real_packet())
    blob = "\n".join(_all_strings(n))
    assert "laliga" not in blob
    assert n["fixture"]["competition"] == NZ.COMP_TOKEN


def test_exact_formation_and_family_label_absent():
    n = NZ3.neutralize_for_llm_v2(_real_packet())
    blob = "\n".join(_all_strings(n))
    for s in ("4-3-3", "3-5-2", "BACK4_1STRIKER", "BACK3_WINGBACK"):
        assert s not in blob, f"leaked identifier: {s}"


def test_find_identity_leaks_clean_on_correct_output():
    src = _real_packet()
    n = NZ3.neutralize_for_llm_v2(src)
    assert NZ3.find_identity_leaks(n, src) == []


def test_find_identity_leaks_catches_a_deliberate_leak():
    src = _real_packet()
    n = NZ3.neutralize_for_llm_v2(src)
    n["evidence"][0]["scope"]["debug_note"] = "was Real Madrid at home"
    leaks = NZ3.find_identity_leaks(n, src)
    assert any("Real Madrid" in l for l in leaks)


# --- evidence id / value preservation ----------------------------------------------
def test_evidence_ids_unchanged():
    src = _real_packet()
    n = NZ3.neutralize_for_llm_v2(src)
    assert [e["id"] for e in src["evidence"]] == [e["id"] for e in n["evidence"]]


def test_metric_orientation_and_values_preserved():
    src = _real_packet()
    n = NZ3.neutralize_for_llm_v2(src)
    for se, ne in zip(src["evidence"], n["evidence"]):
        assert se["metric"] == ne["metric"]          # FOR/AGAINST orientation untouched
        assert se["value"] == ne["value"]
        assert se["sample_n"] == ne["sample_n"]
        assert se["reliability"] == ne["reliability"]
        assert se["temporal_status"] == ne["temporal_status"]
        assert se["cutoff_unix"] == ne["cutoff_unix"]


def test_source_packet_not_mutated():
    src = _real_packet()
    before = copy.deepcopy(src)
    NZ3.neutralize_for_llm_v2(src)
    assert src == before


def test_ab_role_labelling_preserved():
    n = NZ3.neutralize_for_llm_v2(_real_packet())
    assert n["team_a"]["name"] == "TEAM_A"
    assert n["team_b"]["name"] == "TEAM_B"


def test_resolved_vs_prematch_status_untouched_by_neutralization():
    src = _real_packet()
    n = NZ3.neutralize_for_llm_v2(src)
    assert n["formation_context"]["resolution_status"] == src["formation_context"]["resolution_status"]
    assert n["formation_context"]["prematch_status"] == src["formation_context"]["prematch_status"]


# --- determinism + hashing ----------------------------------------------------------
def test_neutralization_deterministic():
    src = _real_packet()
    n1 = NZ3.neutralize_for_llm_v2(src)
    n2 = NZ3.neutralize_for_llm_v2(src)
    assert n1 == n2
    assert n1["neutral_llm_packet_hash"] == n2["neutral_llm_packet_hash"]


def test_source_hash_recorded_and_correct():
    from src.research.llm_matchup.evidence import packet_hash
    src = _real_packet()
    n = NZ3.neutralize_for_llm_v2(src)
    assert n["source_evidence_packet_hash"] == packet_hash(src)


def test_neutral_packet_hash_reproducible():
    n = NZ3.neutralize_for_llm_v2(_real_packet())
    recomputed = json.loads(json.dumps(n, default=str))  # round-trip like a real Bedrock payload
    assert recomputed["neutral_llm_packet_hash"] == n["neutral_llm_packet_hash"]


def test_is_neutralized_predicate():
    n = NZ3.neutralize_for_llm_v2(_real_packet())
    assert NZ3.is_neutralized(n)
    assert not NZ3.is_neutralized(_real_packet())
    assert not NZ3.is_neutralized({})


# --- hard interface guard (adapter_v4) -----------------------------------------------
def test_adapter_v4_rejects_non_neutralized_packet():
    with pytest.raises(A4.NonNeutralPacketError):
        A4.analyze_matchup_v4(_real_packet())


def test_adapter_v4_accepts_neutralized_packet_shape_before_network(monkeypatch):
    """Offline: force the Bedrock-client step to fail so we never touch the network, while
    proving the interface guard did NOT fire for a correctly-neutralized packet (a
    NonNeutralPacketError would have raised before this point)."""
    from src.research.llm_matchup.bedrock_adapter import BedrockUnavailable, LLMResult

    def _no_network(region):
        raise BedrockUnavailable("network disabled in offline test")

    monkeypatch.setattr(A4, "_bedrock_client", _no_network)
    n = NZ3.neutralize_for_llm_v2(_real_packet())
    result = A4.analyze_matchup_v4(n, use_cache=False)
    assert isinstance(result, LLMResult)
    assert result.status == "LLM_STATE_UNAVAILABLE"


# --- alias controls (SS24-SS26) structural checks -------------------------------------
def test_team_alias_changes_only_team_tokens():
    n = NZ3.neutralize_for_llm_v2(_real_packet())
    aliased = NZ3.alias_team_tokens(n, "ENTITY_X", "ENTITY_Y")
    assert aliased["fixture"]["home"] == "ENTITY_X"
    assert aliased["fixture"]["competition"] == n["fixture"]["competition"]  # untouched
    for e_orig, e_new in zip(n["evidence"], aliased["evidence"]):
        assert e_orig["value"] == e_new["value"]
        assert e_orig["metric"] == e_new["metric"]
    assert aliased["neutral_llm_packet_hash"] != n["neutral_llm_packet_hash"]


def test_competition_alias_changes_only_competition_token():
    n = NZ3.neutralize_for_llm_v2(_real_packet())
    aliased = NZ3.alias_competition_token(n, "COMP_X")
    assert aliased["fixture"]["competition"] == "COMP_X"
    assert aliased["fixture"]["home"] == n["fixture"]["home"]  # untouched


def test_formation_id_alias_leaves_structure_untouched():
    n = NZ3.neutralize_for_llm_v2(_real_packet())
    old_id = n["formation_context"]["team_a_prematch_formation"]["formation_id"]
    new_id = "F_99"
    aliased = NZ3.alias_formation_id(n, old_id, new_id)
    a_form = aliased["formation_context"]["team_a_prematch_formation"]
    assert a_form["formation_id"] == new_id
    assert a_form["back_line_count"] == n["formation_context"]["team_a_prematch_formation"]["back_line_count"]
    assert a_form["forward_line_count"] == n["formation_context"]["team_a_prematch_formation"]["forward_line_count"]


# --- formation structure -----------------------------------------------------------
def test_formation_structure_varies_across_shapes():
    back4 = FS.formation_structure("4-3-3")
    back3 = FS.formation_structure("3-5-2")
    back5 = FS.formation_structure("5-3-2")
    assert back4["back_line_count"] == 4
    assert back3["back_line_count"] == 3
    assert back5["back_line_count"] == 5
    assert back4["formation_id"] != back3["formation_id"] != back5["formation_id"]


def test_formation_structure_single_middle_band_does_not_invent_split():
    st = FS.formation_structure("4-3-3")   # one middle band (3)
    assert st["midfield_count"] == 3
    assert st["holding_midfield_count"] is None
    assert st["advanced_midfield_count"] is None


def test_formation_structure_two_middle_bands_split():
    st = FS.formation_structure("4-2-3-1")
    assert st["holding_midfield_count"] == 2
    assert st["advanced_midfield_count"] == 3


def test_formation_structure_unknown_fails_safe():
    st = FS.formation_structure(None)
    assert st["formation_id"] == FS.UNKNOWN_FORMATION_ID
    assert st["structure_known"] is False
    assert all(st[k] is None for k in ("back_line_count", "holding_midfield_count",
                                       "advanced_midfield_count", "midfield_count",
                                       "forward_line_count"))
    st2 = FS.formation_structure("not-a-formation")
    assert st2["formation_id"] == FS.UNKNOWN_FORMATION_ID


def test_formation_structure_unreviewed_but_parseable_gets_unk_id():
    # a syntactically valid formation NOT in the reviewed table still gets F_UNK for the id
    # (SS10: the neutral-id namespace is closed to reviewed shapes) even though its counts
    # are still safely derivable.
    st = FS.formation_structure("4-4-1")  # not in the reviewed table; single middle band
    assert st["formation_id"] == FS.UNKNOWN_FORMATION_ID
    assert st["structure_known"] is True
    assert st["back_line_count"] == 4
    assert st["forward_line_count"] == 1
    assert st["midfield_count"] == 4


# --- reuse / no silent divergence from V2's output contract -------------------------
def test_v4_reuses_v3_output_schema_and_validator_unchanged():
    assert A4.SCH3 is A3.SCH3 or A4.SCH3.build_schema() == A3.SCH3.build_schema()
    assert A4.VV3.validate_v3 is A3.VV3.validate_v3
    assert V3.SCHEMA_VERSION == V2.SCHEMA_VERSION == "football_state_schema_v3"


def test_v3_v4_generation_identity_distinct_from_v2():
    assert V3.GENERATION_ID == "LLM_MATCHUP_V3"
    assert V2.GENERATION_ID == "LLM_MATCHUP_V2"
    assert V3.PROMPT_VERSION == "sonnet_prompt_v4" != V2.PROMPT_VERSION
    assert V3.PACKET_SCHEMA_VERSION != V2.PACKET_SCHEMA_VERSION
    assert PR4.SYSTEM_PROMPT_V4 != PR3.SYSTEM_PROMPT_V3
    assert PR4.prompt_content_hash() != PR3.prompt_content_hash()


def test_prompt_v4_has_no_real_world_examples():
    # SS46: the prompt itself must not name a real club/competition/formation.
    banned = ["Manchester City", "Liverpool", "Premier League", "Champions League",
              "4-2-3-1", "4-3-3", "3-5-2"]
    for b in banned:
        assert b not in PR4.SYSTEM_PROMPT_V4, f"prompt leaks example identifier: {b}"


# --- global identity gate (eligibility.py) -------------------------------------------
def test_identity_gate_fails_closed_on_high_trip_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(EL, "OUT", str(tmp_path))
    controls = {
        "formation_label_shuffle": {"n": 12, "trip_rate": 0.75},
        "team_name_control": {"n": 13, "trip_rate": 0.10},
        "competition_name_control": {"n": 13, "trip_rate": 0.05},
    }
    (tmp_path / "controls_summary.json").write_text(json.dumps(controls))
    gate = EL.identity_gate()
    assert gate["phase_c_eligible_generation"] is False
    assert "formation_label_shuffle" in gate["failed_controls"]
    assert "team_name_control" not in gate["failed_controls"]


def test_identity_gate_passes_when_all_controls_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(EL, "OUT", str(tmp_path))
    controls = {
        "formation_label_shuffle": {"n": 12, "trip_rate": 0.05},
        "team_name_control": {"n": 13, "trip_rate": 0.02},
        "competition_name_control": {"n": 13, "trip_rate": 0.0},
    }
    (tmp_path / "controls_summary.json").write_text(json.dumps(controls))
    gate = EL.identity_gate()
    assert gate["phase_c_eligible_generation"] is True
    assert gate["failed_controls"] == []


def test_identity_gate_inconclusive_counts_as_not_passed(tmp_path, monkeypatch):
    monkeypatch.setattr(EL, "OUT", str(tmp_path))
    controls = {
        "formation_label_shuffle": {"n": 1, "trip_rate": 0.0},   # too few samples
        "team_name_control": {"n": 13, "trip_rate": 0.02},
        "competition_name_control": {"n": 13, "trip_rate": 0.0},
    }
    (tmp_path / "controls_summary.json").write_text(json.dumps(controls))
    gate = EL.identity_gate()
    assert gate["phase_c_eligible_generation"] is False
    assert gate["verdicts"]["formation_label_shuffle"]["status"] == "INCONCLUSIVE"


def test_apply_identity_gate_preserves_pre_gate_class_for_audit():
    rows = [{"mechanism": "X", "eligibility": "PHASE_C_ELIGIBLE"},
            {"mechanism": "Y", "eligibility": "INSUFFICIENT_COVERAGE"}]
    gate = {"phase_c_eligible_generation": False, "reason": "NOT_PHASE_C_ELIGIBLE: test"}
    out = EL.apply_identity_gate(rows, gate)
    x = next(r for r in out if r["mechanism"] == "X")
    y = next(r for r in out if r["mechanism"] == "Y")
    assert x["eligibility"] == "REJECTED" and x["pre_gate_eligibility"] == "PHASE_C_ELIGIBLE"
    assert y["eligibility"] == "INSUFFICIENT_COVERAGE" and "pre_gate_eligibility" not in y


def test_apply_identity_gate_noop_when_gate_passes():
    rows = [{"mechanism": "X", "eligibility": "PHASE_C_ELIGIBLE"}]
    gate = {"phase_c_eligible_generation": True}
    assert EL.apply_identity_gate(rows, gate) == rows


# --- serialized-request audit (SS60: object tests are not sufficient) ---------------
def test_serialized_request_text_has_no_leaks():
    src = _real_packet()
    report = AR.render_and_check(src)
    assert report["clean"] is True
    assert report["leaks"] == []


def test_serialized_request_audit_catches_leak_if_present():
    src = _real_packet()
    neutral = NZ3.neutralize_for_llm_v2(src)
    # simulate a bug: an evidence source_field accidentally carries the real team name
    neutral["evidence"][0]["source_field"] = "crosses_for (Real Madrid)"
    leaks = AR.audit_serialized_request(neutral, src)
    assert any("Real Madrid" in l for l in leaks)


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
