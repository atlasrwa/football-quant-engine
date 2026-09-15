"""Frozen, deterministic fixtures for the hypothesis-engine tests.

Everything here is synthetic and offline. No corpus read, no network, no Bedrock call --
so the whole suite is zero-spend and reproducible.

The two packets (`real_identity_packet` / `alias_identity_packet`) carry BYTE-IDENTICAL
evidence and differ only in display labels, which is what makes the identity control a
real control rather than two different questions.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import capability, context_packet as CP

CUTOFF = 1_768_000_000


def _evidence() -> list[CP.EvidenceItem]:
    """Identity-neutral evidence items. Ids contain no club or competition name."""
    spec = [
        ("HOME", "ATK", "corners", "FOR", 6.1, 24, capability.THESTATSAPI,
         "overview/corner_kicks"),
        ("HOME", "ATK", "accurate_crosses", "FOR", 9.4, 24, capability.THESTATSAPI,
         "passes/accurate_crosses"),
        ("HOME", "ATK", "total_shots", "FOR", 13.2, 24, capability.THESTATSAPI,
         "shots/total_shots"),
        ("HOME", "ATK", "shots_on_target", "FOR", 4.8, 24, capability.THESTATSAPI,
         "shots/shots_on_target"),
        ("HOME", "ATK", "touches_in_box", "FOR", 21.0, 24, capability.THESTATSAPI,
         "attack/touches_in_penalty_area"),
        ("HOME", "DIS", "fouls", "FOR", 11.3, 24, capability.THESTATSAPI, "overview/fouls"),
        ("HOME", "DIS", "yellow_cards", "FOR", 1.9, 24, capability.THESTATSAPI,
         "overview/yellow_cards"),
        ("AWAY", "DEF", "corners", "AGAINST", 6.8, 22, capability.THESTATSAPI,
         "overview/corner_kicks"),
        ("AWAY", "DEF", "shots_on_target", "AGAINST", 5.1, 22, capability.THESTATSAPI,
         "shots/shots_on_target"),
        ("AWAY", "DEF", "blocked_shots", "FOR", 3.7, 22, capability.THESTATSAPI,
         "shots/blocked_shots"),
        ("AWAY", "DEF", "clearances", "FOR", 24.5, 22, capability.THESTATSAPI,
         "defending/clearances"),
        ("AWAY", "DIS", "tackles", "FOR", 17.2, 22, capability.THESTATSAPI,
         "defending/tackles"),
        ("AWAY", "CTX", "possession", "FOR", 47.0, 22, capability.THESTATSAPI,
         "overview/ball_possession"),
    ]
    out = []
    for subj, fam, metric, side, val, n, prov, field in spec:
        scope = {"subject": subj, "side": side, "venue": "ALL", "window": "SEASON_TO_DATE"}
        out.append(CP.EvidenceItem(
            id=CP.evidence_id(subj, fam, metric, scope),
            metric=metric, value=val, sample_n=n, scope=scope,
            reliability=CP.reliability_for(n), shrinkage_level="SHRUNK",
            source_provider=prov, source_field=field,
            cutoff_unix=CUTOFF, temporal_status="PIT_SAFE",
            max_source_time_unix=CUTOFF - 86_400,
        ))
    return out


AVAILABLE_METRICS = (
    "corners", "accurate_crosses", "total_shots", "shots_on_target", "shots_off_target",
    "blocked_shots", "shots_inside_box", "touches_in_box", "possession", "tackles",
    "fouls", "yellow_cards", "total_bookings", "clearances", "goals",
)

#: 40% formation coverage -- above the manifest floor, so formation dimensions are offered
#: AND the coverage number is reported rather than assumed complete.
FORMATION_COVERAGE = {"candidate_n": 40, "usable_n": 16, "missing_n": 24,
                      "coverage_rate": 0.4}

#: 5% coverage -- below the floor, so formation dimensions are withheld for that fixture.
SPARSE_FORMATION_COVERAGE = {"candidate_n": 40, "usable_n": 2, "missing_n": 38,
                             "coverage_rate": 0.05}


def _packet(home: str, away: str, comp: str, *, formation_cov=None,
            half_level=True, fixture_id="fx_0001") -> dict:
    manifest = CP.build_capability_manifest(
        fixture_id=fixture_id,
        available_metrics=AVAILABLE_METRICS,
        formation_coverage_report=formation_cov if formation_cov is not None
        else FORMATION_COVERAGE,
        half_level_available=half_level,
        referee_available=False,
    )
    pkt = CP.FixtureContextPacket(
        fixture_id=fixture_id,
        information_cutoff_unix=CUTOFF,
        home_label=home, away_label=away, competition_label=comp,
        evidence=_evidence(),
        manifest=manifest,
        formation_distribution={
            "HOME_TEAM": {"BACK_FOUR": 11, "BACK_THREE": 5},
            "AWAY_TEAM": {"BACK_THREE": 9, "BACK_FOUR": 7},
        },
    )
    return pkt.to_dict()


def real_identity_packet() -> dict:
    return _packet("Arsenal", "Wolverhampton", "Premier League")


def alias_identity_packet() -> dict:
    """Same evidence, neutral labels. Evidence ids are identical by construction."""
    return _packet("TEAM_A", "TEAM_B", "COMPETITION_1")


def sparse_formation_packet() -> dict:
    return _packet("TEAM_A", "TEAM_B", "COMPETITION_1",
                   formation_cov=SPARSE_FORMATION_COVERAGE, fixture_id="fx_0002")


def no_half_level_packet() -> dict:
    return _packet("TEAM_A", "TEAM_B", "COMPETITION_1",
                   half_level=False, fixture_id="fx_0003")


def evidence_ids(packet: dict) -> list[str]:
    return [e["id"] for e in packet["evidence"]]


# --------------------------------------------------------------------------------------
# Mock LLM responses
# --------------------------------------------------------------------------------------
def _h(hid, family, subject, question, metrics, side, window, conditions, comparison,
       refs, confounders=("OPPONENT_STRENGTH",), caps=(), sufficiency="SUFFICIENT",
       priority="MEDIUM") -> dict:
    return {
        "hypothesis_id": hid,
        "research_family": family,
        "subject": subject,
        "question": question,
        "target_metrics": list(metrics),
        "side": side,
        "window": window,
        "conditions": [dict(c) for c in conditions],
        "comparison": comparison,
        "evidence_refs": list(refs),
        "candidate_confounders": list(confounders),
        "required_capabilities": list(caps),
        "sufficiency": sufficiency,
        "priority": priority,
    }


def valid_response(packet: dict) -> dict:
    """A well-formed, grounded, compilable hypothesis set."""
    ids = evidence_ids(packet)
    return {
        "fixture_id": packet["fixture_id"],
        "packet_hash": packet["packet_hash"],
        "hypotheses": [
            _h("H1", "SET_PIECE_GENERATION", "HOME_TEAM",
               "Does the home side's corner generation differ at home against opponents "
               "recorded with a back three, compared with its own home baseline?",
               ["corners", "accurate_crosses"], "FOR", "ALL_PRIOR",
               [{"dimension": "venue", "value": "HOME"},
                {"dimension": "opponent_formation_family", "value": "BACK_THREE"}],
               "SUBJECT_VENUE_BASELINE", ids[:2],
               caps=["historical_formation"]),
            _h("H2", "DEFENSIVE_CONCESSION", "AWAY_TEAM",
               "Does the away side concede a different rate of shots on target against "
               "opponents in the high band for accurate crosses?",
               ["shots_on_target", "blocked_shots"], "AGAINST", "ALL_PRIOR",
               [{"dimension": "opponent_profile", "value": "HIGH",
                 "axis": "accurate_crosses_for"}],
               "SUBJECT_OVERALL_BASELINE", [ids[7], ids[9]]),
            _h("H3", "MATCH_STATE_RESPONSE", "HOME_TEAM",
               "When the home side is trailing at half time, does its second-half shot "
               "volume differ from its overall second-half baseline?",
               ["total_shots", "touches_in_box"], "FOR", "ALL_PRIOR",
               [{"dimension": "half_score_state", "value": "TRAILING_AT_HT"},
                {"dimension": "period", "value": "SECOND_HALF"}],
               "SUBJECT_OVERALL_BASELINE", [ids[2], ids[4]],
               caps=["half_time_score_state"]),
            _h("H4", "DISCIPLINE", "AWAY_TEAM",
               "Does the away side's tackle and foul volume differ against opponents in "
               "the high possession band, relative to its overall baseline?",
               ["tackles", "fouls", "yellow_cards"], "FOR", "ALL_PRIOR",
               [{"dimension": "opponent_profile", "value": "HIGH",
                 "axis": "possession_for"}],
               "SUBJECT_OVERALL_BASELINE", [ids[11], ids[5]]),
        ],
    }


def abstention_response(packet: dict) -> dict:
    """An honest abstention: no refs, marked INSUFFICIENT_EVIDENCE. Must be ACCEPTED."""
    return {
        "fixture_id": packet["fixture_id"],
        "packet_hash": packet["packet_hash"],
        "hypotheses": [
            _h("H1", "FORMATION_INTERACTION", "HOME_TEAM",
               "Is there enough recorded formation history to compare this side's box "
               "entries under a back three against its own baseline?",
               ["touches_in_box"], "FOR", "ALL_PRIOR", [],
               "SUBJECT_OVERALL_BASELINE", [],
               sufficiency="INSUFFICIENT_EVIDENCE"),
        ],
    }
