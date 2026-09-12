"""Tests for the canonical model thesis projection (derived, read-only).

Covers: paired-side projection, reverse preference, mechanical-cancellation
removal, missing/duplicate side, bookmaker/cutoff/line isolation, neutral rule,
genuine-close direction, settlement linkage (preferred side only), opposite-side
exclusion, reconstructed exclusion, consumer isolation.
"""
from __future__ import annotations

import pytest

from src.research.prospective.model_thesis import (
    CloseDirection,
    NEUTRAL_EPS,
    ThesisClassification,
    ThesisExclusionReason,
    grouping_key,
    project_group,
    project_theses,
)
from src.research.prospective import model_thesis_report as rep
from src.research.prospective.model_thesis import ModelThesis

VH = frozenset({"H"})


def _sh(selection, p_model, p_market, **over):
    r = dict(
        record_type="SHADOW_RESIDUAL",
        provenance_kind="PROSPECTIVE_SHADOW",
        classification=["RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE"],
        fixture_id="F1", competition="comp_1", market="total_goals", line=2.5,
        bookmaker="pinnacle", information_cutoff=100.0, market_observed_at=100.0,
        kickoff_ts=1000.0, forecast_commitment_hash="H", model_version="mv",
        selection=selection, p_model=p_model, p_market_devig=p_market,
        shadow_id=f"sid_{selection}",
    )
    r.update(over)
    return r


def _pair(p_over, pm_over, **over):
    return [_sh("over", p_over, pm_over, **over),
            _sh("under", 1 - p_over, 1 - pm_over, shadow_id="sid_under", **over)]


# ── paired-side projection + reverse preference ─────────────────────────────
def test_over_pair_reduces_to_one_over_thesis():
    r = project_group(_pair(0.58, 0.51), valid_commitment_hashes=VH)
    assert r.classification is ThesisClassification.MODEL_PREFERS_SIDE
    assert r.thesis.preferred_selection == "over"
    assert r.thesis.opposite_selection == "under"
    assert round(r.thesis.edge_pp, 1) == 7.0
    assert r.thesis.preferred_shadow_id == "sid_over"
    assert r.thesis.opposite_shadow_id == "sid_under"


def test_under_preference_when_model_prefers_under():
    r = project_group(_pair(0.42, 0.49), valid_commitment_hashes=VH)
    assert r.thesis.preferred_selection == "under"
    assert round(r.thesis.edge_pp, 1) == 7.0


# ── mechanical cancellation removal ─────────────────────────────────────────
def test_two_shadows_collapse_to_one_thesis():
    results, counts = project_theses(_pair(0.58, 0.51), valid_commitment_hashes=VH)
    assert len(results) == 1  # 2 shadows -> 1 thesis
    assert counts["MODEL_PREFERS_SIDE"] == 1


# ── missing / duplicate side ────────────────────────────────────────────────
def test_missing_opposite_side_fails_closed():
    r = project_group([_sh("over", 0.58, 0.51)], valid_commitment_hashes=VH)
    assert r.classification is ThesisClassification.INELIGIBLE
    assert r.reason is ThesisExclusionReason.MISSING_SIDE


def test_duplicate_side_fails_closed():
    dup = [_sh("over", 0.58, 0.51), _sh("over", 0.57, 0.50, shadow_id="sid_over2")]
    r = project_group(dup, valid_commitment_hashes=VH)
    assert r.classification is ThesisClassification.INELIGIBLE
    assert r.reason is ThesisExclusionReason.DUPLICATE_SIDE


def test_three_sided_group_fails_closed():
    r = project_group(_pair(0.58, 0.51) + [_sh("over", 0.5, 0.5, shadow_id="x")],
                      valid_commitment_hashes=VH)
    assert r.reason is ThesisExclusionReason.NOT_TWO_SIDED


# ── bookmaker / cutoff / line isolation ─────────────────────────────────────
def test_different_bookmakers_are_not_merged():
    shadows = _pair(0.58, 0.51, bookmaker="pinnacle") + \
              [_sh("over", 0.58, 0.51, bookmaker="bet365", shadow_id="o2"),
               _sh("under", 0.42, 0.49, bookmaker="bet365", shadow_id="u2")]
    results, _ = project_theses(shadows, valid_commitment_hashes=VH)
    assert len([r for r in results if r.thesis]) == 2  # one per bookmaker


def test_different_cutoffs_are_not_merged():
    shadows = _pair(0.58, 0.51, information_cutoff=100.0, market_observed_at=100.0) + \
              [_sh("over", 0.58, 0.51, information_cutoff=200.0, market_observed_at=200.0, shadow_id="o2"),
               _sh("under", 0.42, 0.49, information_cutoff=200.0, market_observed_at=200.0, shadow_id="u2")]
    results, _ = project_theses(shadows, valid_commitment_hashes=VH)
    assert len([r for r in results if r.thesis]) == 2


def test_different_lines_are_separate_theses():
    shadows = _pair(0.58, 0.51, line=2.5) + \
              [_sh("over", 0.55, 0.50, line=3.0, shadow_id="o3"),
               _sh("under", 0.45, 0.50, line=3.0, shadow_id="u3")]
    results, _ = project_theses(shadows, valid_commitment_hashes=VH)
    theses = [r.thesis for r in results if r.thesis]
    assert len(theses) == 2
    assert {t.line for t in theses} == {2.5, 3.0}


# ── neutral rule ────────────────────────────────────────────────────────────
def test_no_material_disagreement_creates_no_thesis():
    r = project_group(_pair(0.50, 0.50), valid_commitment_hashes=VH)
    assert r.classification is ThesisClassification.NO_MATERIAL_DISAGREEMENT
    assert r.thesis is None


def test_tiny_disagreement_within_eps_is_neutral():
    r = project_group(_pair(0.5 + NEUTRAL_EPS / 2, 0.5), valid_commitment_hashes=VH)
    assert r.classification is ThesisClassification.NO_MATERIAL_DISAGREEMENT


# ── reconstructed / commitment exclusion ────────────────────────────────────
def test_reconstructed_parent_excluded():
    shadows = _pair(0.58, 0.51)
    shadows[0]["provenance_kind"] = "RECONSTRUCTED_SHADOW"
    r = project_group(shadows, valid_commitment_hashes=VH)
    assert r.reason is ThesisExclusionReason.NON_PROSPECTIVE_PARENT


def test_missing_commitment_link_excluded():
    r = project_group(_pair(0.58, 0.51, forecast_commitment_hash="UNKNOWN"),
                      valid_commitment_hashes=VH)
    assert r.reason is ThesisExclusionReason.MISSING_COMMITMENT_LINK


def test_malformed_probability_excluded():
    r = project_group([_sh("over", 1.5, 0.51), _sh("under", -0.5, 0.49, shadow_id="u")],
                      valid_commitment_hashes=VH)
    assert r.reason is ThesisExclusionReason.MALFORMED_PROBABILITY


# ── genuine-close direction relative to preferred side ──────────────────────
class _Store:
    def __init__(self, records):
        self._records = records

    def read_all(self):
        return iter(self._records)


class _Cap:
    """Minimal object matching what build_capture_index reads from read_all()."""
    def __init__(self, fixture, concept, value, observed_at, kickoff):
        self.canonical_entity_id = fixture
        self.concept = concept
        self.value = value
        self.observed_at = observed_at
        self.event_time = kickoff
        self.raw_status = "PROSPECTIVE_SNAPSHOT"
        self.raw_payload_hash = "h"


def _thesis(preferred="over", p_market=0.51):
    r = project_group(_pair(0.58, p_market), valid_commitment_hashes=VH)
    return r.thesis


def _close_records(over_close_odds, under_close_odds, kickoff=1000.0):
    # concept format: odds:<market>:<selection>:<line>:<bookmaker>
    return [
        _Cap("F1", "odds:total_goals:over:2.5:pinnacle", over_close_odds, 999.0, kickoff),
        _Cap("F1", "odds:total_goals:under:2.5:pinnacle", under_close_odds, 999.0, kickoff),
    ]


def test_close_toward_model_when_preferred_prob_rises():
    t = _thesis()  # preferred over, frozen p_market_preferred = 0.51
    # close over implied ~0.56 -> toward model
    store = _Store(_close_records(1.0 / 0.56, 1.0 / 0.44))
    keyed, kick = rep.build_capture_index(store)
    t2 = rep.build_close_direction(t, keyed_snapshots=keyed, key_kickoff=kick)
    assert t2.close_direction == CloseDirection.FINAL_TOWARD_MODEL.value
    assert t2.close_delta_pp > 0


def test_close_away_from_model_when_preferred_prob_falls():
    t = _thesis()
    store = _Store(_close_records(1.0 / 0.46, 1.0 / 0.54))
    keyed, kick = rep.build_capture_index(store)
    t2 = rep.build_close_direction(t, keyed_snapshots=keyed, key_kickoff=kick)
    assert t2.close_direction == CloseDirection.FINAL_AWAY_FROM_MODEL.value


def test_no_close_when_snapshots_absent():
    t = _thesis()
    keyed, kick = rep.build_capture_index(_Store([]))
    t2 = rep.build_close_direction(t, keyed_snapshots=keyed, key_kickoff=kick)
    assert t2.close_direction == CloseDirection.NO_CLOSE.value


# ── settlement linkage: preferred side only ─────────────────────────────────
def test_settlement_uses_preferred_side_only():
    t = _thesis()  # preferred sid_over
    settle_by_shadow = {
        "sid_over": {"settlement_outcome": "WIN", "result_statistic_value": 3.0},
        "sid_under": {"settlement_outcome": "LOSS", "result_statistic_value": 3.0},
    }
    t2 = rep.attach_settlement(t, settlement_by_shadow=settle_by_shadow)
    assert t2.settlement_outcome == "WIN"  # never the opposite LOSS


def test_settlement_pending_when_preferred_unsettled():
    t = _thesis()
    t2 = rep.attach_settlement(t, settlement_by_shadow={"sid_under": {"settlement_outcome": "LOSS"}})
    assert t2.settlement_outcome == "PENDING"  # opposite settled, preferred not


def test_opposite_side_settlement_never_becomes_second_thesis():
    # A pair yields exactly ONE thesis; the opposite side is not a second result.
    results, _ = project_theses(_pair(0.58, 0.51), valid_commitment_hashes=VH)
    theses = [r.thesis for r in results if r.thesis]
    assert len(theses) == 1


# ── consumer isolation ──────────────────────────────────────────────────────
def test_thesis_carries_research_classification_and_is_not_signal():
    t = _thesis()
    assert t.classification == ("RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE")
    assert t.record_type == "MODEL_THESIS"
    d = t.to_dict()
    # nothing resembling a validated/actionable signal or stake/ev/roi field
    for banned in ("stake", "ev", "roi", "signal", "recommended"):
        assert banned not in d


def test_grouping_key_stable_and_bookmaker_cutoff_sensitive():
    a = grouping_key(_sh("over", 0.5, 0.5, bookmaker="pinnacle"))
    b = grouping_key(_sh("over", 0.5, 0.5, bookmaker="bet365"))
    c = grouping_key(_sh("over", 0.5, 0.5, bookmaker="pinnacle", information_cutoff=200.0))
    assert a != b and a != c
