"""Hard leakage-boundary tests for the two-concept formation model (formation_policy_v1).

These are the most safety-critical Phase-B tests: they assert the TARGET fixture's resolved
formation can never enter the evidence used to describe that fixture, and that the validator
enforces two-concept honesty so the LLM cannot silently upgrade an UNKNOWN pre-match
formation into a known one.

Run: .venv/bin/python -m pytest tests/research/test_formation_leakage.py -q
"""
import sys, copy
sys.path.insert(0, "/home/ubuntu")
import pytest

from src.research.llm_matchup import formation as FM
from src.research.llm_matchup import ontology as ONT
from src.research.llm_matchup.validator import validate, ValidationError
from src.research.llm_matchup.versions import version_stamp

STAMP = version_stamp()


def _v2_packet(prematch_status, resolution_status="RESOLVED_AVAILABLE"):
    """Minimal v2-shaped packet carrying formation_context for validator honesty checks."""
    ev = [{
        "id": "A_FC_fc_crosses_for_x", "metric": "fc_crosses_for", "value": 6.0, "sample_n": 12,
        "scope": {"venue": "home"}, "reliability": "MEDIUM", "shrinkage_level": "DIRECT",
        "evidence_level": "EXACT_FORMATION", "source_provider": "derived_formation",
        "source_field": "fc crosses", "cutoff_unix": 1000, "temporal_status": "PIT_SAFE",
        "max_source_time_unix": 999,
    }]
    return {
        "packet_schema_version": "fixture_evidence_packet_v2",
        "cohort_policy_version": "cohort_policy_v1",
        "fixture": {"fixture_id": "F1", "home": "A", "away": "B", "competition": "L",
                    "season": "S", "kickoff_unix": 1000},
        "information_cutoff_unix": 1000,
        "competition_context": {"tags": []},
        "team_a": {"name": "A", "venue": "home", "style_tags": [], "evidence_ids": ["A_FC_fc_crosses_for_x"]},
        "team_b": {"name": "B", "venue": "away", "style_tags": [], "evidence_ids": []},
        "league_environment": {"evidence_ids": []},
        "evidence": ev,
        "unsupported_context": {"formation_status": "FORMATION_UNKNOWN",
                                "injury_status": "INJURY_STATUS_UNKNOWN", "neutral_venue": "UNKNOWN"},
        "formation_context": {"policy_version": "formation_policy_v1",
                              "resolution_status": resolution_status,
                              "prematch_status": prematch_status},
        "data_quality": {"n_evidence": 1}, "provider_provenance": {"primary": "x"},
        "packet_hash": "deadbeef",
    }


def _state(cf_overrides=None):
    cf = {"formation_status": "FORMATION_UNKNOWN",
          "formation_resolution_status": "RESOLVED_AVAILABLE",
          "prematch_formation_status": "PROJECTED",
          "injury_status": "INJURY_STATUS_UNKNOWN", "neutral_venue": "UNKNOWN",
          "score_state_conditioning": "UNAVAILABLE", "provider_agreement": "SINGLE_PROVIDER"}
    if cf_overrides:
        cf.update(cf_overrides)
    return {
        "fixture_id": "F1", "information_cutoff_unix": 1000, "context_flags": cf,
        "team_a_states": [{"mechanism": "FORMATION_BEHAVIOR_FIT", "level": "MEDIUM",
                           "confidence": "MEDIUM", "evidence_ids": ["A_FC_fc_crosses_for_x"],
                           "counter_evidence_ids": [], "uncertainty_factors": ["EXACT_FORMATION_SPARSE"],
                           "preferred_evidence_level": "EXACT_FORMATION"}],
        "team_b_states": [], "matchup_states": [],
    }


def test_prematch_projected_must_be_mirrored():
    pkt = _v2_packet(prematch_status="PROJECTED")
    good = _state({"prematch_formation_status": "PROJECTED"})
    validate(good, pkt, STAMP)  # ok
    # claiming ANNOUNCED when packet says PROJECTED is dishonest -> reject
    bad = _state({"prematch_formation_status": "ANNOUNCED"})
    with pytest.raises(ValidationError):
        validate(bad, pkt, STAMP)


def test_prematch_unknown_cannot_be_upgraded():
    pkt = _v2_packet(prematch_status="PREMATCH_UNKNOWN")
    # the LLM tries to claim a known/announced/projected pre-match formation -> reject
    for lie in ("ANNOUNCED", "PROJECTED"):
        bad = _state({"prematch_formation_status": lie})
        with pytest.raises(ValidationError):
            validate(bad, pkt, STAMP)
    good = _state({"prematch_formation_status": "PREMATCH_UNKNOWN"})
    validate(good, pkt, STAMP)


def test_resolution_status_must_be_mirrored():
    pkt = _v2_packet(prematch_status="PROJECTED", resolution_status="RESOLVED_PARTIAL")
    bad = _state({"formation_resolution_status": "RESOLVED_AVAILABLE"})
    with pytest.raises(ValidationError):
        validate(bad, pkt, STAMP)
    good = _state({"formation_resolution_status": "RESOLVED_PARTIAL"})
    validate(good, pkt, STAMP)


def test_resolved_source_type_rejected_as_target_input():
    # A FormationInput must never carry the RESOLVED source type for a target fixture.
    fi = FM.FormationInput.projected("4-2-3-1", "proj")
    fi.source_type = "RESOLVED"
    with pytest.raises(ValueError):
        FM.assert_not_target_resolved(fi)


def test_formation_mechanism_requires_formation_evidence():
    # FORMATION_BEHAVIOR_FIT citing a plain behavioral (non-formation) metric that is not in
    # its allow-list must reject (the mechanism is about formation-conditioned behavior).
    pkt = _v2_packet(prematch_status="PROJECTED")
    pkt["evidence"].append({
        "id": "A_DIS_fouls_for_y", "metric": "fouls_for", "value": 10.0, "sample_n": 12,
        "scope": {}, "reliability": "MEDIUM", "shrinkage_level": "DIRECT",
        "evidence_level": "VENUE_OVERALL", "source_provider": "thestatsapi",
        "source_field": "fouls", "cutoff_unix": 1000, "temporal_status": "PIT_SAFE",
        "max_source_time_unix": 999})
    bad = _state()
    bad["team_a_states"][0]["evidence_ids"] = ["A_DIS_fouls_for_y"]
    with pytest.raises(ValidationError):
        validate(bad, pkt, STAMP)


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
