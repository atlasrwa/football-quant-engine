"""Counter-evidence golden control cases A-E (patch §13, §14, §15).

Hand-built synthetic evidence packets where counter-evidence is KNOWN to exist by
construction. We measure whether the hardened model (prompt V3 + validator V3):
  * SURFACES the genuine counter-evidence (recall of the planted opposing item), and
  * lets it CONSTRAIN the state (downgrade / CONFLICTED), not decorate it (patch §15).

We deliberately do NOT reward counter-evidence QUANTITY (patch §13). Each case declares the
SPECIFIC evidence id(s) that constitute the genuine counter-signal; recall is measured against
that set only. A case also declares the acceptable resolved states (e.g. "CONFLICTED or a
downgraded non-extreme level"). Manufacturing extra opposition on a case with no planted
counter-signal would count against the model (false-opposition control, case F).

Packets are built with the SAME structure the frozen packet uses so validator_v3 accepts a
correct response. Team identifiers are already neutral (TEAM_A/TEAM_B) — these are synthetic.

Cases:
  A  crosses high + cross-allowance high  BUT corners low        -> support + counter (corners)
  B  box pressure high + clearances high  BUT corners-conceded low-> CONFLICTED / downgraded
  C  formation-conditioned behavior high  BUT exact N=2, family neutral -> small-N counterweight
  D  2H crosses high                       BUT score-state UNAVAILABLE -> confounding limitation
  E  provider A supports                   BUT provider B disagrees -> provider conflict
  F  clean strong support, NO planted counter-evidence            -> must NOT invent opposition
"""
from __future__ import annotations
import hashlib, json


def _ev(id, metric, value, n, status="PIT_SAFE", provider="thestatsapi", level="VENUE_OVERALL",
        reliability=None):
    rel = reliability or ("HIGH" if n >= 15 else "MEDIUM" if n >= 6 else "LOW")
    return {"id": id, "metric": metric, "value": value, "sample_n": n,
            "scope": {"venue": "home"}, "reliability": rel,
            "shrinkage_level": "DIRECT", "evidence_level": level, "source_provider": provider,
            "source_field": metric, "cutoff_unix": 1000, "temporal_status": status,
            "max_source_time_unix": (999 if status == "PIT_SAFE" else 2000)}


def _packet(fid, evidence, score_state="UNAVAILABLE", provider_agreement="SINGLE_PROVIDER"):
    p = {
        "packet_schema_version": "fixture_evidence_packet_v3",
        "cohort_policy_version": "cohort_policy_v1",
        "fixture": {"fixture_id": fid, "home": "TEAM_A", "away": "TEAM_B",
                    "competition": "COMP_NEUTRAL", "season": "SEASON_NEUTRAL", "kickoff_unix": 1000},
        "information_cutoff_unix": 1000,
        "competition_context": {"tags": []},
        "team_a": {"name": "TEAM_A", "venue": "home", "style_tags": [],
                   "evidence_ids": [e["id"] for e in evidence if e["id"].startswith("A_")],
                   "formation_evidence_ids": [e["id"] for e in evidence if e["id"].startswith("A_FC") or e["id"].startswith("A_FMX")]},
        "team_b": {"name": "TEAM_B", "venue": "away", "style_tags": [],
                   "evidence_ids": [e["id"] for e in evidence if e["id"].startswith("B_")],
                   "formation_evidence_ids": [e["id"] for e in evidence if e["id"].startswith("B_FC") or e["id"].startswith("B_FMX")]},
        "league_environment": {"evidence_ids": [e["id"] for e in evidence if e["id"].startswith("ENV")]},
        "evidence": evidence,
        "formation_context": {"policy_version": "formation_policy_v1",
                              "resolution_status": "RESOLVED_UNAVAILABLE",
                              "prematch_status": "PREMATCH_UNKNOWN"},
        "unsupported_context": {"formation_status": "FORMATION_UNKNOWN",
                                "injury_status": "INJURY_STATUS_UNKNOWN", "neutral_venue": "UNKNOWN",
                                "score_state": score_state},
        "data_quality": {"n_evidence": len(evidence),
                         "n_pit_safe": sum(1 for e in evidence if e["temporal_status"] == "PIT_SAFE"),
                         "n_formation_evidence": sum(1 for e in evidence
                                                     if e["metric"].startswith(("fc_", "fmx_", "formation_delta_")))},
        "provider_provenance": {"primary": "thestatsapi", "provider_agreement": provider_agreement},
    }
    core = {k: v for k, v in p.items() if k != "packet_hash"}
    p["packet_hash"] = hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()
    return p


def cases() -> dict:
    """Return {case_id: {packet, target_mechanism, counter_evidence_ids (planted), expect}}.

    `expect` fields:
      * counter_expected: True if the case plants genuine counter-evidence for the mechanism.
      * acceptable_states: set of assessments that correctly reflect the constraint.
      * forbidden_states: assessments that would ignore the counter-evidence (patch §15).
      * planted_counter_ids: the specific ids that ARE the genuine counter-signal (recall base).
    """
    out = {}

    # A: A crosses high + B cross allowance high (supports wide pressure) BUT A corners low.
    # The low corner production is genuine counter-evidence to a strong corner-pressure story.
    A = _packet("cg_A", [
        _ev("A_crosses", "crosses_for", 22.0, 20),
        _ev("B_cross_allow", "crosses_against", 24.0, 20),
        _ev("A_corners", "corners_for", 3.1, 20),         # <-- counter: low corners despite width
    ])
    out["A"] = {"packet": A, "target_mechanism": "WIDE_PRESSURE_MATCHUP",
                "planted_counter_ids": {"A_corners"},
                "expect": {"counter_expected": True,
                           "acceptable_states": {"A_ADVANTAGE", "NEUTRAL", "CONFLICTED"},
                           "forbidden_states": {"STRONG_A_ADVANTAGE"}}}

    # B: A box pressure high BUT B box protection strong (low box shots allowed) -> the strong
    # protective response is genuine counter-evidence to a strong A box advantage; must CONFLICT
    # or downgrade. Uses only BOX_PRESSURE_MATCHUP allow-listed metrics.
    B = _packet("cg_B", [
        _ev("A_box", "touches_in_box_for", 34.0, 20),
        _ev("B_box_prot", "touches_in_box_against", 9.0, 20),   # <-- counter: B allows few box touches
        _ev("B_sib_allow", "shots_inside_box_against", 2.5, 20),  # <-- counter: few box shots allowed
    ])
    out["B"] = {"packet": B, "target_mechanism": "BOX_PRESSURE_MATCHUP",
                "planted_counter_ids": {"B_box_prot", "B_sib_allow"},
                "expect": {"counter_expected": True,
                           "acceptable_states": {"CONFLICTED", "NEUTRAL", "A_ADVANTAGE"},
                           "forbidden_states": {"STRONG_A_ADVANTAGE"}}}

    # C: formation-conditioned A behavior high BUT exact formation N=2 and family evidence neutral.
    # small-N counterweight: must lower confidence / add EXACT_FORMATION_SPARSE, not emit HIGH conf.
    C = _packet("cg_C", [
        _ev("A_FC_crosses", "fc_crosses_for", 20.0, 2, level="EXACT_FORMATION", reliability="LOW"),
        _ev("A_FMX_family", "fmx_crosses_for", 9.0, 18, level="FORMATION_FAMILY"),  # family ~ neutral
    ])
    out["C"] = {"packet": C, "target_mechanism": "FORMATION_WIDTH_INTERACTION",
                "planted_counter_ids": {"A_FMX_family"},
                "expect": {"counter_expected": True,
                           "acceptable_states": {"NEUTRAL", "A_ADVANTAGE", "CONFLICTED", "UNKNOWN"},
                           "forbidden_states": {"STRONG_A_ADVANTAGE"},
                           "require_uncertainty_any": {"EXACT_FORMATION_SPARSE", "SMALL_SAMPLE",
                                                       "FORMATION_FAMILY_ONLY", "SHRUNK_TO_PRIOR"}}}

    # D: 2H crosses high BUT score-state control unavailable -> confounding limitation.
    D = _packet("cg_D", [
        _ev("A_2h_cross", "crosses_2h_shift", 8.0, 20),
    ], score_state="UNAVAILABLE")
    out["D"] = {"packet": D, "target_mechanism": "SECOND_HALF_PRESSURE_SHIFT",
                "planted_counter_ids": set(),
                "expect": {"counter_expected": False,     # not opposing evidence — a CONFOUND
                           "acceptable_states": {"A_ADVANTAGE", "NEUTRAL", "UNKNOWN", "CONFLICTED"},
                           "forbidden_states": {"STRONG_A_ADVANTAGE"},
                           "require_uncertainty_any": {"SCORE_STATE_CONFOUND"}}}

    # E: provider A supports mechanism, provider B materially disagrees -> provider conflict.
    E = _packet("cg_E", [
        _ev("A_cross_ts", "crosses_for", 21.0, 18, provider="thestatsapi"),
        _ev("A_cross_fs", "crosses_for", 7.0, 18, provider="footystats"),   # <-- counter: disagrees
    ], provider_agreement="DISAGREE")
    out["E"] = {"packet": E, "target_mechanism": "WIDTH_PRESSURE",
                "planted_counter_ids": {"A_cross_fs"},
                "expect": {"counter_expected": True,
                           "acceptable_states": {"MEDIUM", "LOW", "UNKNOWN", "CONFLICTED"},
                           "forbidden_states": {"VERY_HIGH"},
                           "require_uncertainty_any": {"PROVIDER_DISAGREEMENT"}}}

    # F: clean strong support, NO planted counter-evidence -> must NOT invent opposition (patch §13).
    F = _packet("cg_F", [
        _ev("A_crosses", "crosses_for", 24.0, 22),
        _ev("A_corners", "corners_for", 8.5, 22),
        _ev("B_cross_allow", "crosses_against", 25.0, 22),
        _ev("B_corners_conc", "corners_against", 9.0, 22),
    ])
    out["F"] = {"packet": F, "target_mechanism": "WIDE_PRESSURE_MATCHUP",
                "planted_counter_ids": set(),
                "expect": {"counter_expected": False,
                           "acceptable_states": {"A_ADVANTAGE", "STRONG_A_ADVANTAGE", "NEUTRAL"},
                           "forbidden_states": set(),
                           "no_false_opposition": True}}
    return out


def score_case(case_id: str, case: dict, state: dict) -> dict:
    """Score one hardened response against a golden case (patch §13-§15). Deterministic."""
    mech = case["target_mechanism"]
    planted = case["planted_counter_ids"]
    expect = case["expect"]

    # locate the target mechanism state (any side)
    found = None
    for side in ("team_a_states", "team_b_states", "matchup_states"):
        for st in (state or {}).get(side, []):
            if st["mechanism"] == mech:
                found = st
                break
        if found:
            break

    if found is None:
        return {"case": case_id, "mechanism": mech, "mechanism_present": False,
                "counter_recall": None, "counter_search_performed": None,
                "state_constrained": None, "false_opposition": None,
                "uncertainty_ok": None, "pass": False,
                "note": "target mechanism absent"}

    status = found.get("level") or found.get("assessment")
    counter_ids = set(found.get("counter_evidence_ids", []) or [])
    search = found.get("counter_evidence_search")
    unc = set(found.get("uncertainty_factors", []) or [])

    # recall of PLANTED counter-evidence (only meaningful when counter_expected)
    if expect["counter_expected"] and planted:
        recall = round(len(counter_ids & planted) / len(planted), 4)
    else:
        recall = None

    # state constrained: not in forbidden set, and if counter expected+found, must be a
    # downgraded/conflicted acceptable state.
    state_constrained = status not in expect.get("forbidden_states", set()) \
        and status in expect.get("acceptable_states", set())

    # false opposition: on a NO-counter case, citing counter-evidence that isn't planted is bad.
    false_opposition = False
    if not expect["counter_expected"]:
        false_opposition = len(counter_ids) > 0

    # uncertainty requirement (confound / provider / small-N limitation must be flagged)
    req = expect.get("require_uncertainty_any")
    uncertainty_ok = True if not req else bool(unc & req)

    # pass criteria (patch §15 — what actually matters for measurement integrity):
    #   * counter_evidence_search performed;
    #   * state constrained appropriately (not extreme/one-sided when opposition exists);
    #   * uncertainty requirement satisfied (confound / provider / small-N flagged);
    #   * if NOT expected: no false opposition.
    # EXPLICIT RECALL (did the opposing item land in counter_evidence_ids) is reported
    # SEPARATELY as a secondary signal — the model may legitimately encode opposition via
    # state constraint + uncertainty_factors rather than the id list. We do NOT fail a case
    # solely for weak explicit recall, and we NEVER reward recall quantity (patch §13).
    constraint_pass = (search == "PERFORMED") and state_constrained and uncertainty_ok
    if not expect["counter_expected"]:
        constraint_pass = constraint_pass and (not false_opposition)
    explicit_recall = recall  # may be None when not expected

    return {"case": case_id, "mechanism": mech, "mechanism_present": True,
            "status": status, "counter_search_performed": search == "PERFORMED",
            "counter_recall": recall, "explicit_recall": explicit_recall,
            "n_counter_cited": len(counter_ids),
            "state_constrained": state_constrained, "false_opposition": false_opposition,
            "uncertainty_ok": uncertainty_ok, "uncertainty_factors": "|".join(sorted(unc)),
            "pass": bool(constraint_pass)}
