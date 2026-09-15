"""V5A.1 packet builder (`v5a1_packet_v1`) -- both arms, one evidence interface.

Arm A (base)      : shared long-run evidence only.
Arm B (research)  : EXACTLY Arm A's evidence, plus the match-level record and the
                    conditional evidence derived from it.

`build_arm_b` is literally `arm_a_records + extra_records`, so "Arm B is a superset of
Arm A" is a property of the construction, not a claim -- and the test proves it on
evidence_id sets AND values.

What this fixes from the aborted V5A:
  HS-2  both arms' ALL_PRIOR summaries are computed over the SAME full PIT-safe history
        (V5A compared Arm A's shrunk means over up to 104 matches against Arm B's plain
        means over 30). Raw-row depth is a SEPARATE, separately-declared policy.
  M-1   section order is explicit and the match rows come BEFORE the summaries.
  M-4   match slots are subject-qualified (HOME_M01 / AWAY_M01), so no cross-team collision.
  M-6   no field names an arm, a condition, or a treatment.
  §8    availability is a triple: provider / derivable / EXPOSED-in-this-packet.

ZERO SPEND. Builds data structures only; no model, no network, no artifact mutation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from src.research.hypothesis_engine import corpus_adapter as CA
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a1_semantics as S

PACKET_BUILDER_VERSION = "v5a1_packet_v1"

#: IDENTICAL in both arms. Nothing in the model-visible packet may distinguish the arms
#: except which evidence they contain (task §6).
PACKET_SCHEMA_VERSION = "research_evidence_packet_v1"

# ----------------------------------------------------------------------------------------
# Frozen policies. Both fixed before any output is produced.
# ----------------------------------------------------------------------------------------
#: The BASELINE UNIVERSE. ALL_PRIOR summaries in BOTH arms aggregate every PIT-safe prior
#: match, with no cap. This is the HS-2 fix.
BASELINE_UNIVERSE = "ALL_PIT_SAFE_PRIOR_MATCHES_UNCAPPED"

#: The RAW-ROW policy. Bounded purely for prompt cost; it does NOT bound the summaries.
MAX_RAW_ROWS_PER_TEAM = 30
MIN_PRIOR_MATCHES_PER_TEAM = 6

#: Summaries are UNSHRUNK arithmetic means in BOTH arms. V3/V5A Arm A used shrunk values;
#: mixing a shrunk scalar in one arm with a plain mean in the other was half of HS-2. A
#: shrunk value is a modelling choice, and this packet is a research-question input, so the
#: honest quantity is the plain mean with its sample_n attached.
SUMMARY_ESTIMATOR = "UNSHRUNK_ARITHMETIC_MEAN"

#: Opponent-profile response cohorts (task §14). Frozen before any output.
DEFENSIVE_SIMILARITY_AXES = ("shots_on_target_against", "goals_against")
OFFENSIVE_SIMILARITY_AXES = ("shots_on_target_for", "goals_for")
PROFILE_RESPONSE_METRICS = ("total_shots", "shots_on_target", "corners", "big_chances",
                            "touches_in_box", "accurate_crosses", "xg", "goals")
MIN_COHORT_N = 3
MIN_OPPONENT_HISTORY_FOR_BANDING = 4
PROFILE_METHOD = "RANK_BAND_TERCILE_v5a1"

VENUE_MIN_PER_SIDE = 4
FORMATION_LOW_COVERAGE_FLOOR = 0.50

_EXTRA_SOURCE = {"xg": ("base", "team_a_xg", "team_b_xg"),
                 "red_cards": ("base", "team_a_red_cards", "team_b_red_cards")}


def _team_value(rec, team, metric, side) -> Optional[float]:
    if metric in _EXTRA_SOURCE:
        _, hk, ak = _EXTRA_SOURCE[metric]
        h, a = rec.base.get(hk), rec.base.get(ak)
        if h is None or a is None:
            return None
        own, opp = (h, a) if rec.home == team else (a, h)
        v = own if side == "FOR" else opp
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return CA.team_value(rec, team, metric, side)


def _mean(vals):
    u = [v for v in vals if v is not None]
    return (round(sum(u) / len(u), 4), len(u)) if u else (None, 0)


# ----------------------------------------------------------------------------------------
# History
# ----------------------------------------------------------------------------------------
def full_prior(index, target, team) -> list:
    """Every PIT-safe prior match for the team. THE baseline universe for both arms."""
    cutoff = int(target.kickoff_unix)
    prior = [r for r in index.prior(team, cutoff) if r.fixture_id != target.fixture_id]
    prior.sort(key=lambda r: r.kickoff_unix)
    return prior


def raw_rows(prior: list) -> list:
    """The most recent N of those, serialized as match rows. A display/cost bound only."""
    return prior[-MAX_RAW_ROWS_PER_TEAM:]


def _alias_maps(index, target) -> tuple:
    """Deterministic identity-neutral aliases over BOTH teams' full prior universes."""
    opp, comp = {}, {target.competition: "COMPETITION"}
    for team in (target.home, target.away):
        for r in full_prior(index, target, team):
            o = r.away if r.home == team else r.home
            if o not in opp:
                opp[o] = f"OPP_{len(opp) + 1:03d}"
            if r.competition not in comp:
                comp[r.competition] = f"COMP_{len(comp) + 1:03d}"
    return opp, comp


# ----------------------------------------------------------------------------------------
# Section 4 -- MATCH_LEVEL_OBSERVATIONS (Arm B only)
# ----------------------------------------------------------------------------------------
def build_match_block(subject, team, rows, opp_alias, comp_alias, cutoff) -> dict:
    cols = S.cell_columns()
    out_rows = []
    for i, r in enumerate(rows, start=1):
        o = r.away if r.home == team else r.home
        cells = []
        for c in cols:
            metric, side = c.rsplit("_", 1)
            cells.append(_team_value(r, team, metric, side.upper()))
        out_rows.append({
            "evidence_id": E.match_id(subject, i),
            "subject": subject,
            "evidence_type": E.MATCH_OBSERVATION,
            "derivation_type": E.RAW_OBSERVATION,
            "kickoff_unix": int(r.kickoff_unix),
            "kickoff_date": _date(int(r.kickoff_unix)),
            "chronological_rank": i,
            "matches_before_target": len(rows) - i + 1,
            "venue": "HOME" if r.home == team else "AWAY",
            "opponent_ref": opp_alias.get(o, "OPP_UNK"),
            "competition_ref": comp_alias.get(r.competition, "COMP_OTHER"),
            "own_formation_recorded": CA.team_formation_family(r, team),
            "opponent_formation_recorded": CA.team_formation_family(r, team, opponent=True),
            "fixture_ref": E.match_id(subject, i),
            "cells": cells,
        })
    return {
        "subject": subject,
        "n_rows": len(out_rows),
        "row_order": "CHRONOLOGICAL_ASCENDING: row 1 (M01) is the OLDEST, the last row is "
                     "the most recent match before the information cutoff.",
        "cell_columns": cols,
        "cell_orientation": "from the SUBJECT team's perspective in that match; see the "
                            "metric_semantics section.",
        "cutoff": cutoff,
        "provider_provenance": S.PROVIDER,
        "rows": out_rows,
    }


def _date(unix: int) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(unix, datetime.timezone.utc).strftime("%Y-%m-%d")


# ----------------------------------------------------------------------------------------
# Section 5 -- DERIVED_SUMMARIES
# ----------------------------------------------------------------------------------------
def _summary_record(subject, metric, side, window, venue_scope, value, n, cutoff, prov):
    return E.EvidenceRecord(
        evidence_id=E.summary_id(subject, window, venue_scope, metric, side),
        evidence_type=E.DERIVED_SUMMARY, subject=subject, metric=metric, side=side.upper(),
        value=value, units=S.METRIC_SEMANTICS[metric]["units"], window=window,
        venue_scope=venue_scope, sample_n=n, reliability=E.reliability_for(n),
        provider_provenance=S.PROVIDER, cutoff=cutoff,
        derivation_type=E.UNWEIGHTED_MEAN, extra={"basis": prov})


def build_base_summaries(subject, team, prior, cutoff) -> list:
    """ALL_PRIOR / venue=ANY over the FULL PIT-safe universe. Present in BOTH arms."""
    out = []
    for metric in S.CANONICAL_METRICS:
        for side in S.SIDES:
            val, n = _mean([_team_value(r, team, metric, side.upper()) for r in prior])
            if val is None:
                continue
            out.append(_summary_record(
                subject, metric, side, "ALL_PRIOR", "ANY", val, n, cutoff,
                f"unweighted mean over all {len(prior)} PIT-safe prior matches"))
    return out


def build_conditional_summaries(subject, team, prior, cutoff) -> list:
    """W5 / W10 and venue-split summaries. Arm B only -- the conditional evidence."""
    out = []
    windows = {"W5": prior[-5:], "W10": prior[-10:]}
    venues = {"HOME_ONLY": [r for r in prior if r.home == team],
              "AWAY_ONLY": [r for r in prior if r.away == team]}
    for metric in S.CANONICAL_METRICS:
        for side in S.SIDES:
            for wname, wrows in windows.items():
                val, n = _mean([_team_value(r, team, metric, side.upper()) for r in wrows])
                if val is not None:
                    out.append(_summary_record(
                        subject, metric, side, wname, "ANY", val, n, cutoff,
                        f"unweighted mean over the {len(wrows)} most recent PIT-safe "
                        f"matches"))
            for vname, vrows in venues.items():
                val, n = _mean([_team_value(r, team, metric, side.upper()) for r in vrows])
                if val is not None and n >= 3:
                    out.append(_summary_record(
                        subject, metric, side, "ALL_PRIOR", vname, val, n, cutoff,
                        f"unweighted mean over the {len(vrows)} PIT-safe prior matches in "
                        f"which the subject played "
                        f"{'at home' if vname == 'HOME_ONLY' else 'away'}"))
    return out


# ----------------------------------------------------------------------------------------
# Section 6 -- OPPONENT_PROFILE_SUMMARIES (Arm B only)
#
# The evidence V5A promised and never built: how the subject actually BEHAVED against past
# opponents resembling the upcoming one, next to its own overall baseline.
# ----------------------------------------------------------------------------------------
def _axis_value_before(index, team, axis, before_unix) -> Optional[tuple]:
    metric, side = (axis[:-4], "FOR") if axis.endswith("_for") else (axis[:-8], "AGAINST")
    vals = [_team_value(r, team, metric, side)
            for r in index.by_team.get(team, []) if r.kickoff_unix < before_unix]
    u = [v for v in vals if v is not None]
    return (sum(u) / len(u), len(u)) if u else None


def _tercile_thresholds(index, target, axis) -> Optional[tuple]:
    """Tercile cut points for the axis across the target competition, measured strictly
    before the target cutoff. A fixed reference scale; PIT-safe by construction."""
    cutoff = int(target.kickoff_unix)
    teams = sorted({t for r in index.records
                    if r.competition == target.competition and r.kickoff_unix < cutoff
                    for t in (r.home, r.away)})
    vals = []
    for t in teams:
        got = _axis_value_before(index, t, axis, cutoff)
        if got and got[1] >= MIN_OPPONENT_HISTORY_FOR_BANDING:
            vals.append(got[0])
    if len(vals) < 6:
        return None
    vals.sort()
    lo = vals[len(vals) // 3]
    hi = vals[(2 * len(vals)) // 3]
    return (lo, hi, len(vals))


def _band(value, thresholds) -> str:
    lo, hi, _ = thresholds
    return "LOW" if value < lo else ("HIGH" if value >= hi else "MID")


def build_profile_summaries(index, target, subject, team, opponent, prior, cutoff,
                            opp_alias) -> list:
    """For each direction and axis: band the upcoming opponent, gather the subject's prior
    matches against similarly-banded opponents, and report the subject's response next to
    its own overall baseline. Descriptive history only -- never an expected effect."""
    out = []
    directions = (
        (E.ATTACK_VS_DEF_SIMILAR, DEFENSIVE_SIMILARITY_AXES, "for"),
        (E.DEFENCE_VS_ATK_SIMILAR, OFFENSIVE_SIMILARITY_AXES, "against"),
    )
    for direction, axes, resp_side in directions:
        for axis in axes:
            th = _tercile_thresholds(index, target, axis)
            if th is None:
                continue
            got = _axis_value_before(index, opponent, axis, cutoff)
            if not got or got[1] < MIN_OPPONENT_HISTORY_FOR_BANDING:
                continue
            target_band = _band(got[0], th)
            # cohort: subject's prior matches whose opponent was in the same band, each
            # opponent measured strictly before THAT match.
            cohort = []
            for r in prior:
                o = r.away if r.home == team else r.home
                ov = _axis_value_before(index, o, axis, int(r.kickoff_unix))
                if not ov or ov[1] < MIN_OPPONENT_HISTORY_FOR_BANDING:
                    continue
                if _band(ov[0], th) == target_band:
                    cohort.append(r)
            if len(cohort) < MIN_COHORT_N:
                continue
            for metric in PROFILE_RESPONSE_METRICS:
                side = resp_side.upper()
                cval, cn = _mean([_team_value(r, team, metric, side) for r in cohort])
                bval, bn = _mean([_team_value(r, team, metric, side) for r in prior])
                if cval is None or bval is None:
                    continue
                out.append(E.EvidenceRecord(
                    evidence_id=E.profile_id(subject, direction, axis, metric, resp_side),
                    evidence_type=E.OPPONENT_PROFILE_SUMMARY,
                    subject=subject, metric=metric, side=side, value=cval,
                    units=S.METRIC_SEMANTICS[metric]["units"],
                    window="ALL_PRIOR", venue_scope="ANY",
                    sample_n=cn, reliability=E.reliability_for(cn),
                    provider_provenance=S.PROVIDER, cutoff=cutoff,
                    derivation_type=E.COHORT_UNWEIGHTED_MEAN,
                    extra={
                        "semantic_label": E.profile_semantic_label(subject, direction),
                        "response_direction": direction,
                        "response_metric": f"{metric}_{resp_side}",
                        "similarity_axis": axis,
                        "similarity_method": PROFILE_METHOD,
                        "upcoming_opponent_band_on_axis": target_band,
                        "cohort_definition":
                            f"the subject's prior matches against opponents whose {axis} "
                            f"was in the {target_band} tercile of this competition, each "
                            f"opponent measured using only matches before that cohort "
                            f"match",
                        "cohort_n": cn,
                        "baseline_value": bval,
                        "baseline_n": bn,
                        "baseline_definition":
                            "the subject's unweighted mean of the same metric over ALL its "
                            "PIT-safe prior matches",
                        "coverage": round(len(cohort) / len(prior), 4) if prior else 0.0,
                        "interpretation":
                            "This is a description of what already happened. It is not an "
                            "expected effect, an advantage, or a prediction for the "
                            "upcoming fixture, and the cohort is not a controlled "
                            "comparison.",
                    }))
    return out


# ----------------------------------------------------------------------------------------
# Section 7 -- FORMATION_CONTEXT (both arms; coverage summary is base evidence)
# ----------------------------------------------------------------------------------------
def build_formation_context(subject, team, prior, cutoff) -> E.EvidenceRecord:
    fams = [CA.team_formation_family(r, team) for r in prior]
    usable = [f for f in fams if f]
    cov = round(len(usable) / len(fams), 4) if fams else 0.0
    hist = {}
    for f in usable:
        hist[f] = hist.get(f, 0) + 1
    return E.EvidenceRecord(
        evidence_id=E.formation_id(subject), evidence_type=E.FORMATION_CONTEXT,
        subject=subject, value=cov, units="coverage_rate", window="ALL_PRIOR",
        sample_n=len(fams), coverage=cov, reliability=E.reliability_for(len(usable)),
        provider_provenance=S.PROVIDER, cutoff=cutoff, derivation_type=E.COUNT,
        extra={"recorded_formation_histogram": dict(sorted(hist.items())),
               "candidate_matches": len(fams), "matches_with_recorded_formation": len(usable),
               "matches_without_recorded_formation": len(fams) - len(usable),
               "meaning": "Coverage of the subject's RECORDED historical formation. The "
                          "UPCOMING fixture's formation is not known and is not in this "
                          "packet."})


# ----------------------------------------------------------------------------------------
# Section 2 -- the availability triple (task §8)
# ----------------------------------------------------------------------------------------
def build_exposure(arm_has_rows, arm_has_conditional, arm_has_profiles,
                   venue_ok, recent_ok, formation_cov, profile_n, xg_cov) -> list:
    def rows_state(ok_state):
        return ok_state if arm_has_rows else E.NOT_EXPOSED_IN_PACKET
    t = []
    t.append(E.ExposureTriple(
        "match_level_observations", True, True,
        E.EXPOSED if arm_has_rows else E.NOT_EXPOSED_IN_PACKET,
        "Individual historical match rows." if arm_has_rows else
        "Individual historical match rows are derivable and PIT-safe but are NOT included "
        "in this packet. Use the summaries that are included."))
    t.append(E.ExposureTriple(
        "venue_splits", True, True,
        (E.EXPOSED if venue_ok else E.EXPOSED_LOW_COVERAGE) if arm_has_conditional
        else E.NOT_EXPOSED_IN_PACKET,
        "Home/away conditioned summaries." if arm_has_conditional else
        "Venue-conditioned evidence is derivable and PIT-safe but is NOT included in this "
        "packet. Do not ask a venue-conditioned question against this packet.",
        coverage=None))
    t.append(E.ExposureTriple(
        "recent_vs_long", True, True,
        (E.EXPOSED if recent_ok else E.EXPOSED_LOW_COVERAGE) if arm_has_conditional
        else E.NOT_EXPOSED_IN_PACKET,
        "W5 and W10 summaries alongside ALL_PRIOR." if arm_has_conditional else
        "Short-window evidence is derivable and PIT-safe but is NOT included in this "
        "packet: only the full-history (ALL_PRIOR) summaries are present."))
    t.append(E.ExposureTriple(
        "opponent_profile_response", True, True,
        (E.EXPOSED if profile_n else E.EXPOSED_LOW_COVERAGE) if arm_has_profiles
        else E.NOT_EXPOSED_IN_PACKET,
        f"{profile_n} response-cohort summaries." if arm_has_profiles else
        "Opponent-profile response evidence is derivable and PIT-safe but is NOT included "
        "in this packet."))
    t.append(E.ExposureTriple(
        "formation_recorded_history", True, True,
        E.EXPOSED_LOW_COVERAGE if formation_cov < FORMATION_LOW_COVERAGE_FLOOR else E.EXPOSED,
        f"Recorded historical formation, coverage {formation_cov:.3f}. Below "
        f"{FORMATION_LOW_COVERAGE_FLOOR} this is too sparse to condition on.",
        coverage=formation_cov))
    t.append(E.ExposureTriple(
        "xg", True, True,
        E.EXPOSED if xg_cov >= 0.5 else E.EXPOSED_LOW_COVERAGE,
        f"Total expected goals, coverage {xg_cov:.3f} on this fixture's history.",
        coverage=round(xg_cov, 4)))
    t.append(E.ExposureTriple("expected_formation", False, False, E.NOT_PROVIDED_BY_SOURCE,
                              S.UNSUPPORTED_CONTEXT["expected_formation"]))
    t.append(E.ExposureTriple("lineup", True, False, E.NOT_DERIVABLE_PIT_SAFE,
                              S.UNSUPPORTED_CONTEXT["lineup"]))
    t.append(E.ExposureTriple("injuries", False, False, E.NOT_PROVIDED_BY_SOURCE,
                              S.UNSUPPORTED_CONTEXT["injuries"]))
    t.append(E.ExposureTriple("weather", False, False, E.NOT_PROVIDED_BY_SOURCE,
                              S.UNSUPPORTED_CONTEXT["weather"]))
    t.append(E.ExposureTriple("referee", False, False, E.NOT_PROVIDED_BY_SOURCE,
                              S.UNSUPPORTED_CONTEXT["referee"]))
    t.append(E.ExposureTriple("half_time_state", False, False, E.NOT_PROVIDED_BY_SOURCE,
                              S.UNSUPPORTED_CONTEXT["half_time_state"]))
    t.append(E.ExposureTriple("minute_level_events", False, False, E.NOT_PROVIDED_BY_SOURCE,
                              S.UNSUPPORTED_CONTEXT["minute_level_events"]))
    t.append(E.ExposureTriple("player_ratings", False, False, E.NOT_PROVIDED_BY_SOURCE,
                              S.UNSUPPORTED_CONTEXT["player_ratings"]))
    t.append(E.ExposureTriple("market_prices", False, False, E.NOT_PROVIDED_BY_SOURCE,
                              S.UNSUPPORTED_CONTEXT["market_prices"]))
    return t


# ----------------------------------------------------------------------------------------
# Assembly
# ----------------------------------------------------------------------------------------
@dataclass
class ArmEvidence:
    """One arm's evidence, kept as records + optional row blocks until serialization."""
    base_summaries: list
    formation: list
    exposure: list
    match_blocks: list
    conditional_summaries: list
    profile_summaries: list

    def all_records(self) -> list:
        return (list(self.base_summaries) + list(self.conditional_summaries)
                + list(self.profile_summaries) + list(self.formation)
                + [t.as_record() for t in self.exposure])


def _fixture_context(target, cutoff, n_prior_home, n_prior_away, n_rows_home, n_rows_away,
                     has_rows) -> dict:
    d = {
        "section_note": "The fixture these observations precede. Team identities are "
                        "aliased; HOME_TEAM plays at home.",
        "home": "HOME_TEAM",
        "away": "AWAY_TEAM",
        "competition": "COMPETITION",
        "information_cutoff_unix": cutoff,
        "information_cutoff_date": _date(cutoff),
        "cutoff_rule": "Every observation and every summary in this packet comes from "
                       "matches that kicked off strictly before the information cutoff. "
                       "The upcoming fixture itself, its result, and any market price are "
                       "not present.",
        "subject_codes": {"HOME": "HOME_TEAM, the home side of the upcoming fixture",
                          "AWAY": "AWAY_TEAM, the away side of the upcoming fixture"},
        "baseline_universe": BASELINE_UNIVERSE,
        "summary_estimator": SUMMARY_ESTIMATOR,
        "history_counts": {
            "HOME": {"pit_safe_prior_matches": n_prior_home,
                     "matches_serialized_as_rows": n_rows_home,
                     "rows_not_serialized": n_prior_home - n_rows_home},
            "AWAY": {"pit_safe_prior_matches": n_prior_away,
                     "matches_serialized_as_rows": n_rows_away,
                     "rows_not_serialized": n_prior_away - n_rows_away},
        },
        "history_note":
            ("Every ALL_PRIOR summary in this packet aggregates ALL the PIT-safe prior "
             "matches counted above. The individual match rows, where present, are the most "
             "recent {} of them and are bounded for prompt size only -- they are NOT the "
             "team's entire record.".format(MAX_RAW_ROWS_PER_TEAM) if has_rows else
             "Every ALL_PRIOR summary in this packet aggregates ALL the PIT-safe prior "
             "matches counted above. Individual match rows are not included in this "
             "packet."),
    }
    return d


def _sections(target, cutoff, ctx, exposure, match_blocks, summaries, profiles, formation):
    """§11 order: fixture, availability, semantics, HOME rows, AWAY rows, summaries,
    profiles, formation, output instructions. Raw football record before the aggregates."""
    sem = S.metric_semantics_block()
    sem["reliability_rule"] = E.RELIABILITY_RULE
    secs = [
        {"section": 1, "section_type": "TARGET_FIXTURE_CONTEXT", "content": ctx},
        {"section": 2, "section_type": "AVAILABILITY_MAP",
         "content": {
             "note": "Three different things, kept separate. Act ONLY on EXPOSED_TO_LLM: it "
                     "says whether the evidence is in THIS packet. PROVIDER_AVAILABLE and "
                     "DERIVABLE_PIT_SAFE describe the upstream corpus and are given for "
                     "transparency only -- a dimension can be derivable and still absent "
                     "here.",
             "states": list(E.EXPOSURE_STATES)},
         "records": [t.as_record().to_dict() for t in exposure]},
        {"section": 3, "section_type": "METRIC_SEMANTICS", "content": sem},
    ]
    n = 4
    if match_blocks:
        secs.append({"section": n, "section_type": "MATCH_LEVEL_OBSERVATIONS",
                     "content": {"note": "The actual historical record. Each row is one "
                                         "real prior match, with every canonical metric "
                                         "aligned on that row so relationships between "
                                         "metrics within a single match are inspectable."},
                     "blocks": match_blocks})
        n += 1
    secs.append({"section": n, "section_type": "DERIVED_SUMMARIES",
                 "content": {"note": "Deterministic aggregates computed from the same "
                                     "canonical observations. They supplement the record; "
                                     "they are not observations themselves.",
                             "window_meaning": {
                                 "ALL_PRIOR": "every PIT-safe prior match of the subject",
                                 "W5": "the 5 most recent of those",
                                 "W10": "the 10 most recent of those"},
                             "venue_scope_meaning": {
                                 "ANY": "not venue-conditioned",
                                 "HOME_ONLY": "only matches the SUBJECT played at home",
                                 "AWAY_ONLY": "only matches the SUBJECT played away"}},
                 "shared": {"evidence_type": E.DERIVED_SUMMARY,
                            "derivation_type": E.UNWEIGHTED_MEAN,
                            "estimator": SUMMARY_ESTIMATOR,
                            "provider_provenance": S.PROVIDER,
                            "cutoff": cutoff,
                            "reliability_rule": E.RELIABILITY_RULE},
                 "columns": SUMMARY_COLUMNS,
                 "rows": [_summary_row(r) for r in summaries]})
    n += 1
    if profiles:
        secs.append({"section": n, "section_type": "OPPONENT_PROFILE_SUMMARIES",
                     "content": {
                         "note": "How the subject behaved against past opponents "
                                 "resembling the upcoming one, next to its own overall "
                                 "baseline over ALL prior matches.",
                         "method": PROFILE_METHOD,
                         "interpretation":
                             "These describe what already happened against a loosely "
                             "matched cohort. They are not expected effects, advantages, "
                             "favourable matchups or predictions, and the cohort is not a "
                             "controlled comparison: cohort and baseline differ in "
                             "opponent quality, venue mix and period.",
                         "direction_meaning": E.DIRECTION_MEANING,
                         "cohorts": _cohort_lookup(profiles)},
                     "shared": {"evidence_type": E.OPPONENT_PROFILE_SUMMARY,
                                "derivation_type": E.COHORT_UNWEIGHTED_MEAN,
                                "provider_provenance": S.PROVIDER,
                                "cutoff": cutoff,
                                "window": "ALL_PRIOR", "venue_scope": "ANY",
                                "baseline_definition":
                                    "the subject's unweighted mean of the same metric over "
                                    "ALL its PIT-safe prior matches"},
                     "columns": PROFILE_COLUMNS,
                     "rows": [_profile_row(r) for r in profiles]})
        n += 1
    secs.append({"section": n, "section_type": "FORMATION_CONTEXT",
                 "content": {"note": "Coverage of RECORDED historical formation. The "
                                     "upcoming fixture's formation is unknown."},
                 "records": [r.to_dict() for r in formation]})
    n += 1
    secs.append({"section": n, "section_type": "EVIDENCE_CITATION_INSTRUCTIONS",
                 "content": {
                     "note": "Cite the evidence that motivated each hypothesis by its "
                             "evidence_id, exactly as written in this packet.",
                     "id_grammar": E.ID_GRAMMAR_DOC,
                     "examples": ["MATCH:HOME:M01:corners_for",
                                  "SUMMARY:HOME:ALL_PRIOR:ANY:corners_for",
                                  "SUMMARY:AWAY:W5:ANY:shots_on_target_against",
                                  "FORMATION:HOME"],
                     "rule": "A reference that does not appear in this packet is not "
                             "evidence. If the packet does not support a question, mark it "
                             "INSUFFICIENT_EVIDENCE rather than citing something absent."}})
    return secs


#:  is deliberately NOT a column: it is a property of the metric, declared once in
#: the metric_semantics section rather than repeated on 460 rows (task §12).
SUMMARY_COLUMNS = ["evidence_id", "subject", "metric", "side", "window", "venue_scope",
                   "value", "sample_n", "reliability"]

PROFILE_COLUMNS = ["evidence_id", "subject", "cohort_key", "response_metric", "side",
                   "cohort_value", "cohort_n", "baseline_value", "baseline_n",
                   "reliability"]


def _summary_row(r) -> list:
    return [r.evidence_id, r.subject, r.metric, r.side, r.window, r.venue_scope,
            r.value, r.sample_n, r.reliability]


def _cohort_key(r) -> str:
    x = r.extra
    return f"{r.subject}|{x['response_direction']}|{x['similarity_axis']}"


def _cohort_lookup(profiles) -> dict:
    """Cohort definitions declared ONCE per (subject, direction, axis) instead of repeated
    on every response row (task §12)."""
    out = {}
    for r in profiles:
        k = _cohort_key(r)
        if k in out:
            continue
        x = r.extra
        out[k] = {
            "subject": r.subject,
            "semantic_label": x["semantic_label"],
            "response_direction": x["response_direction"],
            "similarity_axis": x["similarity_axis"],
            "similarity_method": x["similarity_method"],
            "upcoming_opponent_band_on_axis": x["upcoming_opponent_band_on_axis"],
            "cohort_definition": x["cohort_definition"],
            "cohort_n": x["cohort_n"],
            "cohort_share_of_prior_matches": x["coverage"],
        }
    return out


def _profile_row(r) -> list:
    x = r.extra
    return [r.evidence_id, r.subject, _cohort_key(r), x["response_metric"], r.side,
            r.value, x["cohort_n"], x["baseline_value"], x["baseline_n"], r.reliability]


def build_packet(index, target, *, arm: str) -> Optional[dict]:
    """Build one arm's packet. `arm` selects the evidence set; it is NOT serialized."""
    if arm not in ("base", "research"):
        raise ValueError(f"arm {arm!r} must be 'base' or 'research'")
    cutoff = int(target.kickoff_unix)
    opp_alias, comp_alias = _alias_maps(index, target)
    prior = {"HOME": full_prior(index, target, target.home),
             "AWAY": full_prior(index, target, target.away)}
    if min(len(prior["HOME"]), len(prior["AWAY"])) < MIN_PRIOR_MATCHES_PER_TEAM:
        return None
    teams = {"HOME": target.home, "AWAY": target.away}
    opps = {"HOME": target.away, "AWAY": target.home}
    rows = {s: raw_rows(prior[s]) for s in ("HOME", "AWAY")}

    base_sum, formation = [], []
    for s in ("HOME", "AWAY"):
        base_sum += build_base_summaries(s, teams[s], prior[s], cutoff)
        formation.append(build_formation_context(s, teams[s], prior[s], cutoff))

    cond_sum, profiles, blocks = [], [], []
    if arm == "research":
        for s in ("HOME", "AWAY"):
            cond_sum += build_conditional_summaries(s, teams[s], prior[s], cutoff)
            profiles += build_profile_summaries(index, target, s, teams[s], opps[s],
                                                prior[s], cutoff, opp_alias)
            blocks.append(build_match_block(s, teams[s], rows[s], opp_alias, comp_alias,
                                            cutoff))

    # coverage inputs for the availability triple
    fc = max(_form_cov(teams[s], prior[s]) for s in ("HOME", "AWAY"))
    xgc = _xg_cov(teams, prior)
    venue_ok = all(_venue_ok(teams[s], prior[s]) for s in ("HOME", "AWAY"))
    recent_ok = all(len(prior[s]) >= 10 for s in ("HOME", "AWAY"))
    exposure = build_exposure(bool(blocks), arm == "research", arm == "research",
                              venue_ok, recent_ok, fc, len(profiles), xgc)

    ev = ArmEvidence(base_sum, formation, exposure, blocks, cond_sum, profiles)
    E.assert_unique(ev.all_records())            # raises on any duplicate id

    ctx = _fixture_context(target, cutoff, len(prior["HOME"]), len(prior["AWAY"]),
                           len(rows["HOME"]) if blocks else 0,
                           len(rows["AWAY"]) if blocks else 0, bool(blocks))
    body = {
        "packet_schema_version": PACKET_SCHEMA_VERSION,
        "evidence_interface_version": E.EVIDENCE_INTERFACE_VERSION,
        "fixture_id": target.fixture_id,
        "information_cutoff_unix": cutoff,
        "sections": _sections(target, cutoff, ctx, exposure, blocks,
                              base_sum + cond_sum, profiles, formation),
    }
    body["packet_hash"] = E.packet_hash(body)
    return body


def _form_cov(team, prior):
    fams = [CA.team_formation_family(r, team) for r in prior]
    return (sum(1 for f in fams if f) / len(fams)) if fams else 0.0


def _xg_cov(teams, prior):
    tot = ok = 0
    for s in ("HOME", "AWAY"):
        for r in prior[s]:
            tot += 1
            if _team_value(r, teams[s], "xg", "FOR") is not None:
                ok += 1
    return (ok / tot) if tot else 0.0


def _venue_ok(team, prior):
    h = sum(1 for r in prior if r.home == team)
    a = len(prior) - h
    return h >= VENUE_MIN_PER_SIDE and a >= VENUE_MIN_PER_SIDE
