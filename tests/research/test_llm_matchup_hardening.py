"""Pre-Phase-C hardening invariants (patch §55).

Deterministic, offline tests (no Bedrock). They exercise the hardened contract and every
analysis primitive that must behave deterministically:

  * counter-evidence search required / SKIPPED-only-for-UNKNOWN;
  * empty counter_evidence_ids allowed only after a performed search;
  * counter-evidence held to allow-list + PIT standards (symmetric with support);
  * strong unresolved counter-evidence constrains the state;
  * team-name + competition-name neutrality is value-preserving;
  * a formation label alone cannot establish a behavioral mechanism (validator still needs
    behavioral evidence to accept a non-UNKNOWN formation mechanism);
  * repeatability field-level + severity scoring is deterministic;
  * aggregation is deterministic and PRESERVES disagreement;
  * self-noise comparison (state_distance) is deterministic;
  * mechanism eligibility classification is deterministic;
  * prompt / schema / version isolation between the frozen generation and V2.

Run: .venv/bin/python -m pytest tests/research/test_llm_matchup_hardening.py -q
"""
import sys, json
sys.path.insert(0, "/home/ubuntu")
import pytest

from src.research.llm_matchup import ontology as ONT
from src.research.llm_matchup import versions as V_FROZEN
from src.research.llm_matchup import schema as SCH_FROZEN
from src.research.llm_matchup.validator import ValidationError
from src.research.llm_matchup.hardening import schema_v3 as SCH3
from src.research.llm_matchup.hardening import validator_v3 as VV3
from src.research.llm_matchup.hardening import versions_v2 as V2
from src.research.llm_matchup.hardening import prompt_v3 as PR3
from src.research.llm_matchup.hardening import neutralize as NZ
from src.research.llm_matchup.hardening import repeatability as REP
from src.research.llm_matchup.hardening import aggregate as AG
from src.research.llm_matchup.hardening import ablation_noise as AN
from src.research.llm_matchup.hardening import counter_golden as CG
from src.research.llm_matchup.hardening import eligibility as EL

STAMP = {"ontology_version": "o", "schema_version": "football_state_schema_v3",
         "prompt_version": "sonnet_prompt_v3"}

CF = {"formation_status": "FORMATION_UNKNOWN",
      "formation_resolution_status": "RESOLVED_UNAVAILABLE",
      "prematch_formation_status": "PREMATCH_UNKNOWN",
      "injury_status": "INJURY_STATUS_UNKNOWN", "neutral_venue": "UNKNOWN",
      "score_state_conditioning": "UNAVAILABLE", "provider_agreement": "SINGLE_PROVIDER"}


def _packet():
    ev = [
        {"id": "A_cx", "metric": "crosses_for", "value": 18.0, "sample_n": 20, "scope": {},
         "reliability": "HIGH", "shrinkage_level": "DIRECT", "evidence_level": "VENUE_OVERALL",
         "source_provider": "x", "source_field": "crosses_for", "cutoff_unix": 1000,
         "temporal_status": "PIT_SAFE"},
        {"id": "B_ca", "metric": "crosses_against", "value": 21.0, "sample_n": 18, "scope": {},
         "reliability": "HIGH", "shrinkage_level": "DIRECT", "evidence_level": "VENUE_OVERALL",
         "source_provider": "x", "source_field": "crosses_against", "cutoff_unix": 1000,
         "temporal_status": "PIT_SAFE"},
    ]
    return {"fixture": {"fixture_id": "g1", "home": "A", "away": "B", "competition": "epl",
                        "season": "s", "kickoff_unix": 1000},
            "information_cutoff_unix": 1000, "evidence": ev,
            "unsupported_context": {"formation_status": "FORMATION_UNKNOWN",
                                    "injury_status": "INJURY_STATUS_UNKNOWN", "neutral_venue": "UNKNOWN"},
            "formation_context": {"resolution_status": "RESOLVED_UNAVAILABLE",
                                  "prematch_status": "PREMATCH_UNKNOWN"},
            "data_quality": {"n_evidence": 2}, "packet_hash": "ph"}


def _state(a_states, m_states=None):
    return {"fixture_id": "g1", "information_cutoff_unix": 1000, "context_flags": CF,
            "team_a_states": a_states, "team_b_states": [], "matchup_states": m_states or []}


def _st(**over):
    s = {"mechanism": "WIDTH_PRESSURE", "level": "HIGH", "confidence": "MEDIUM",
         "evidence_ids": ["A_cx"], "counter_evidence_ids": [], "counter_evidence_search": "PERFORMED",
         "uncertainty_factors": [], "preferred_evidence_level": "VENUE_OVERALL"}
    s.update(over)
    return s


# --- schema / validator hardening -----------------------------------------------
def test_schema_v3_requires_counter_evidence_search():
    s = SCH3.build_schema()
    item = s["properties"]["team_a_states"]["items"]
    assert "counter_evidence_search" in item["required"]
    assert item["properties"]["counter_evidence_search"]["enum"] == ["PERFORMED", "SKIPPED"]


def test_valid_v3_state_accepted():
    VV3.validate_v3(_state([_st()]), _packet(), STAMP)


def test_counter_search_required_skipped_only_for_unknown():
    # SKIPPED on a HIGH state -> reject
    with pytest.raises(ValidationError):
        VV3.validate_v3(_state([_st(counter_evidence_search="SKIPPED")]), _packet(), STAMP)
    # SKIPPED on UNKNOWN -> allowed
    VV3.validate_v3(_state([_st(level="UNKNOWN", counter_evidence_search="SKIPPED", evidence_ids=[])]),
                    _packet(), STAMP)


def test_empty_counter_ids_only_valid_after_search():
    # SKIPPED must not carry counter ids
    with pytest.raises(ValidationError):
        VV3.validate_v3(_state([_st(level="UNKNOWN", counter_evidence_search="SKIPPED",
                                    counter_evidence_ids=["B_ca"], evidence_ids=[])]), _packet(), STAMP)


def test_counter_evidence_must_be_pit_safe_and_allowed():
    pk = _packet()
    pk["evidence"].append({"id": "B_un", "metric": "crosses_against", "value": 5.0, "sample_n": 10,
                           "scope": {}, "reliability": "HIGH", "shrinkage_level": "DIRECT",
                           "evidence_level": "VENUE_OVERALL", "source_provider": "x",
                           "source_field": "f", "cutoff_unix": 1000, "temporal_status": "UNAVAILABLE"})
    with pytest.raises(ValidationError):
        VV3.validate_v3(_state([_st(counter_evidence_ids=["B_un"])]), pk, STAMP)


def test_strong_counter_constrains_state():
    # VERY_HIGH with a strong (HIGH reliability, n18) counter -> must reject
    with pytest.raises(ValidationError):
        VV3.validate_v3(_state([_st(level="VERY_HIGH", counter_evidence_ids=["B_ca"])]), _packet(), STAMP)


def test_conflicted_with_strong_counter_allowed():
    m = [{"mechanism": "WIDE_PRESSURE_MATCHUP", "assessment": "CONFLICTED", "confidence": "MEDIUM",
          "supporting_evidence_ids": ["A_cx"], "counter_evidence_ids": ["B_ca"],
          "counter_evidence_search": "PERFORMED", "uncertainty_factors": []}]
    VV3.validate_v3(_state([_st()], m), _packet(), STAMP)


def test_reasoning_trace_field_forbidden():
    bad = _state([_st()])
    bad["reasoning_trace"] = "I thought about it"
    with pytest.raises(ValidationError):
        VV3.validate_v3(bad, _packet(), STAMP)


def test_formation_label_alone_cannot_establish_behavior():
    # A formation mechanism asserted with ZERO PIT-safe allowed evidence must be UNKNOWN.
    bad = _state([{"mechanism": "FORMATION_WIDTH_INTERACTION", "level": "HIGH", "confidence": "HIGH",
                   "evidence_ids": [], "counter_evidence_ids": [], "counter_evidence_search": "SKIPPED",
                   "uncertainty_factors": [], "preferred_evidence_level": "EXACT_FORMATION"}])
    with pytest.raises(ValidationError):
        VV3.validate_v3(bad, _packet(), STAMP)


# --- neutralization / controls --------------------------------------------------
def test_team_name_neutrality_value_preserving():
    pk = _packet()
    pk["team_a"] = {"name": "A"}
    pk["team_b"] = {"name": "B"}
    neutral = NZ.neutralize_packet(pk)
    NZ.assert_value_preserving(pk, neutral)  # must not raise
    s = json.dumps(neutral)
    assert "TEAM_A" in s and "TEAM_B" in s


def test_competition_neutrality_value_preserving():
    pk = _packet()
    real, ncomp = NZ.competition_control_pair(pk)
    NZ.assert_value_preserving(pk, ncomp)
    assert ncomp["fixture"]["competition"] == NZ.COMP_TOKEN
    assert real["fixture"]["competition"] == "epl"  # untouched


# --- repeatability + severity ---------------------------------------------------
def test_severity_ladder_deterministic():
    assert REP.severity("HIGH", "MEDIUM", "HIGH", "MEDIUM") == 0
    assert REP.severity("HIGH", "MEDIUM", "MEDIUM", "MEDIUM") == 1
    assert REP.severity("LOW", "MEDIUM", "HIGH", "MEDIUM") == 2
    assert REP.severity("A_ADVANTAGE", "MEDIUM", "B_ADVANTAGE", "MEDIUM") == 3
    assert REP.severity("HIGH", "MEDIUM", "CONFLICTED", "MEDIUM") == 4
    assert REP.severity("UNKNOWN", "LOW", "CONFLICTED", "LOW") == 4


def _mk(mech, lvl, conf="MEDIUM", ev=None):
    return {"mechanism": mech, "assessment": lvl, "confidence": conf,
            "supporting_evidence_ids": ev or [], "counter_evidence_ids": [],
            "counter_evidence_search": "PERFORMED", "uncertainty_factors": []}


def _ms(items):
    return {"team_a_states": [], "team_b_states": [], "matchup_states": items}


def test_field_level_agreement_deterministic():
    c1 = _ms([_mk("WIDE_PRESSURE_MATCHUP", "A_ADVANTAGE", ev=["e1"])])
    c2 = _ms([_mk("WIDE_PRESSURE_MATCHUP", "A_ADVANTAGE", ev=["e1"])])
    c3 = _ms([_mk("WIDE_PRESSURE_MATCHUP", "B_ADVANTAGE", ev=["e2"])])
    rows = REP.field_level_agreement([c1, c2, c3])
    r = rows[0]
    assert r["presence_stable"] and not r["status_agree"] and r["worst_severity"] == 3
    # deterministic: recompute identical
    assert REP.field_level_agreement([c1, c2, c3])[0] == r


# --- aggregation preserves disagreement -----------------------------------------
def test_aggregation_deterministic_and_preserves_disagreement():
    severe = [_ms([_mk("X", "A_ADVANTAGE")]), _ms([_mk("X", "B_ADVANTAGE")]), _ms([_mk("X", "CONFLICTED")])]
    agg = AG.aggregate_fixture(severe)
    item = agg["aggregate_states"]["matchup_states"][0]
    assert item["aggregate_status"] == "UNSTABLE"
    assert item["llm_interpretation_stability"] == "UNSTABLE"
    # determinism
    assert AG.aggregate_fixture(severe)["aggregate_states"] == agg["aggregate_states"]


def test_aggregation_stable_keeps_status():
    same = [_ms([_mk("X", "A_ADVANTAGE", ev=["e1"])])] * 3
    agg = AG.aggregate_fixture(same)
    item = agg["aggregate_states"]["matchup_states"][0]
    assert item["aggregate_status"] == "A_ADVANTAGE"
    assert item["llm_interpretation_stability"] == "STABLE"


# --- self-noise / state distance ------------------------------------------------
def test_state_distance_deterministic():
    a = _ms([_mk("X", "A_ADVANTAGE"), _mk("Y", "HIGH")])
    b = _ms([_mk("X", "A_ADVANTAGE"), _mk("Y", "HIGH")])
    d, pk = AN.state_distance(a, b)
    assert d == 0.0
    b2 = _ms([_mk("X", "A_ADVANTAGE")])  # Y removed -> presence change
    d2, _ = AN.state_distance(a, b2)
    assert d2 > 0.0
    assert AN.state_distance(a, b2)[0] == d2  # deterministic


# --- eligibility deterministic --------------------------------------------------
def test_eligibility_classification_deterministic():
    sig = {"WIDTH_PRESSURE": {"coverage": 10, "n_severe": 0, "n_total": 10, "n_stable": 10,
                              "sensitivity_flag": "OK", "sensitivity_margin": 0.3,
                              "surrogate_verdict": "MULTIDIMENSIONAL", "surrogate_s1": 0.6}}
    rows = EL.classify(sig)
    wp = next(r for r in rows if r["mechanism"] == "WIDTH_PRESSURE")
    assert wp["eligibility"] == "PHASE_C_ELIGIBLE"
    # trivially reducible -> REDUNDANT
    sig["WIDTH_PRESSURE"]["surrogate_verdict"] = "TRIVIALLY_REDUCIBLE"
    sig["WIDTH_PRESSURE"]["surrogate_s1"] = 0.95
    rows2 = EL.classify(sig)
    wp2 = next(r for r in rows2 if r["mechanism"] == "WIDTH_PRESSURE")
    assert wp2["eligibility"] == "REDUNDANT_WITH_DETERMINISTIC"
    # unstable sensitivity -> RESEARCH_ONLY_UNSTABLE
    sig["WIDTH_PRESSURE"]["surrogate_verdict"] = "MULTIDIMENSIONAL"
    sig["WIDTH_PRESSURE"]["sensitivity_flag"] = "UNSTABLE_SENSITIVITY"
    rows3 = EL.classify(sig)
    wp3 = next(r for r in rows3 if r["mechanism"] == "WIDTH_PRESSURE")
    assert wp3["eligibility"] == "RESEARCH_ONLY_UNSTABLE"


# --- prompt / schema / version isolation ----------------------------------------
def test_generation_isolation_frozen_vs_v2():
    # frozen and V2 must have DISTINCT prompt + schema versions and generation identity.
    assert V_FROZEN.PROMPT_VERSION == "sonnet_prompt_v2"
    assert V2.PROMPT_VERSION == "sonnet_prompt_v3"
    assert V_FROZEN.SCHEMA_VERSION == "football_state_schema_v2"
    assert V2.SCHEMA_VERSION == "football_state_schema_v3"
    assert V2.GENERATION_ID == "LLM_MATCHUP_V2"
    # frozen schema has NO counter_evidence_search; V3 does.
    frozen_item = SCH_FROZEN.build_schema()["properties"]["team_a_states"]["items"]
    assert "counter_evidence_search" not in frozen_item["required"]
    v3_item = SCH3.build_schema()["properties"]["team_a_states"]["items"]
    assert "counter_evidence_search" in v3_item["required"]


def test_generation_hash_changes_with_prompt():
    h1 = V2.generation_hash(extra={"prompt_content": "hashA"})
    h2 = V2.generation_hash(extra={"prompt_content": "hashB"})
    assert h1 != h2


# --- counter-golden scoring deterministic ---------------------------------------
def test_counter_golden_scoring_deterministic():
    cases = CG.cases()
    # a synthetic "perfect" response for case F (no counter expected) should pass constraint
    case = cases["F"]
    state = _state([], [{"mechanism": "WIDE_PRESSURE_MATCHUP", "assessment": "A_ADVANTAGE",
                         "confidence": "MEDIUM", "supporting_evidence_ids": ["A_crosses"],
                         "counter_evidence_ids": [], "counter_evidence_search": "PERFORMED",
                         "uncertainty_factors": []}])
    s1 = CG.score_case("F", case, state)
    s2 = CG.score_case("F", case, state)
    assert s1 == s2
    assert s1["pass"] is True and s1["false_opposition"] is False


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
