"""Tests for the Experimental Picks presentation foundation (experimental_pick.py).

Proves:
- a valid PROSPECTIVE shadow record projects to an ExperimentalPick;
- a RECONSTRUCTED shadow record can NEVER become a pick;
- malformed scientific fields / missing parent provenance fail closed;
- EXPERIMENTAL_PUBLICATION_STATE defaults to OFF and OFF prevents publication;
- the state is independent of SIGNAL_PUBLICATION_STATE and cannot override
  scientific eligibility;
- the renderer contains EXPERIMENTAL / NOT VALIDATED / NOT ACTIONABLE and NONE
  of the forbidden promotional/action terms, and is deterministic.
"""

from __future__ import annotations

import copy

import pytest

from src.research.prospective.experimental_pick import (
    EXPERIMENTAL_PUBLICATION_ENV,
    ExperimentalPick,
    ExperimentalPickError,
    ExperimentalPublicationState,
    build_experimental_pick,
    can_publish_experimental_pick,
    experimental_publication_enabled,
    is_pick_eligible,
    render_experimental_pick,
    resolve_experimental_publication_state,
)


def _shadow(**over) -> dict:
    rec = {
        "record_type": "SHADOW_RESIDUAL",
        "provenance_kind": "PROSPECTIVE_SHADOW",
        "classification": ["RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE"],
        "fixture_id": "F123",
        "competition": "Premier League",
        "kickoff_ts": 1000.0 + 58 * 60,
        "information_cutoff": 1000.0,
        "provider": "prov",
        "bookmaker": "Pinnacle",
        "market": "Goals",
        "selection": "over",
        "line": 2.5,
        "p_model": 0.61,
        "p_market_devig": 0.54,
        "raw_probability_residual": 0.07,
        "raw_over_odds": 1.85,
        "raw_under_odds": 2.05,
        "forecast_commitment_hash": "fc_abc",
        "model_version": "champion/1",
        "scope_version_hash": "sc_1",
        "shadow_id": "8f3a91c2deadbeef0000000000000001",
    }
    rec.update(over)
    return rec


# --- prospective shadow -> ExperimentalPick succeeds --------------------


def test_prospective_shadow_projects_to_pick():
    pick = build_experimental_pick(_shadow())
    assert isinstance(pick, ExperimentalPick)
    assert pick.classification == "EXPERIMENTAL"
    assert pick.validation_state == "UNVALIDATED"
    assert pick.actionability == "NOT_ACTIONABLE"
    # Values preserved EXACTLY from the source (no recomputation of odds/probs).
    assert pick.engine_probability == 0.61
    assert pick.locked_market_probability == 0.54
    assert pick.locked_odds == 1.85
    assert pick.forecast_id == "fc_abc"
    assert pick.model_version == "champion/1"
    assert pick.source_shadow_id == "8f3a91c2deadbeef0000000000000001"
    assert pick.minutes_before_kickoff == 58
    # Gap is a neutral difference in pp; never called edge/EV. 61% - 54% = 7pp.
    assert round(pick.model_market_gap_pp, 6) == 7.0


def test_under_selection_uses_under_odds():
    pick = build_experimental_pick(_shadow(selection="under", p_market_devig=0.46,
                                           p_model=0.40))
    assert pick.locked_odds == 2.05


def test_pick_does_not_mutate_source_record():
    rec = _shadow()
    snapshot = copy.deepcopy(rec)
    build_experimental_pick(rec)
    assert rec == snapshot  # projection never mutates the shadow record


# --- reconstructed shadow -> fails ---------------------------------------


def test_reconstructed_shadow_cannot_become_pick():
    with pytest.raises(ExperimentalPickError):
        build_experimental_pick(_shadow(provenance_kind="RECONSTRUCTED_SHADOW"))
    assert is_pick_eligible(_shadow(provenance_kind="RECONSTRUCTED_SHADOW")) is False


# --- malformed scientific fields fail closed -----------------------------


@pytest.mark.parametrize("mutation", [
    {"p_model": 1.5},            # out-of-range probability
    {"p_model": "0.6"},          # wrong type
    {"p_market_devig": 0.0},     # degenerate probability
    {"line": None},              # missing line
    {"kickoff_ts": "soon"},      # invalid timestamp
    {"raw_over_odds": 0.0},      # fake-zero odds
    {"raw_over_odds": 1.0},      # odds must be > 1.0
    {"bookmaker": ""},           # invalid bookmaker identity
    {"market": ""},              # invalid market identity
])
def test_malformed_scientific_fields_fail_closed(mutation):
    with pytest.raises(ExperimentalPickError):
        build_experimental_pick(_shadow(**mutation))


def test_missing_parent_forecast_provenance_fails_closed():
    with pytest.raises(ExperimentalPickError):
        build_experimental_pick(_shadow(forecast_commitment_hash=""))
    with pytest.raises(ExperimentalPickError):
        build_experimental_pick(_shadow(model_version=""))


def test_information_cutoff_after_kickoff_fails_closed():
    with pytest.raises(ExperimentalPickError):
        build_experimental_pick(_shadow(information_cutoff=999_999.0))


# --- publication state (default OFF) -------------------------------------


def test_default_publication_state_is_off(monkeypatch):
    monkeypatch.delenv(EXPERIMENTAL_PUBLICATION_ENV, raising=False)
    assert resolve_experimental_publication_state() is ExperimentalPublicationState.OFF
    assert experimental_publication_enabled() is False


def test_off_prevents_publication_even_for_eligible_record(monkeypatch):
    monkeypatch.delenv(EXPERIMENTAL_PUBLICATION_ENV, raising=False)
    rec = _shadow()
    assert is_pick_eligible(rec) is True          # scientifically eligible
    assert can_publish_experimental_pick(rec) is False  # but OFF blocks it


def test_state_cannot_override_scientific_eligibility(monkeypatch):
    # Even PUBLIC cannot publish a reconstructed (ineligible) record.
    monkeypatch.setenv(EXPERIMENTAL_PUBLICATION_ENV, "PUBLIC")
    assert experimental_publication_enabled() is True
    assert can_publish_experimental_pick(_shadow(provenance_kind="RECONSTRUCTED_SHADOW")) is False
    # A genuinely eligible record with PUBLIC set may publish (state + eligibility).
    assert can_publish_experimental_pick(_shadow()) is True


def test_beta_and_public_recognized(monkeypatch):
    monkeypatch.setenv(EXPERIMENTAL_PUBLICATION_ENV, "beta")
    assert resolve_experimental_publication_state() is ExperimentalPublicationState.BETA
    monkeypatch.setenv(EXPERIMENTAL_PUBLICATION_ENV, "  PUBLIC ")
    assert resolve_experimental_publication_state() is ExperimentalPublicationState.PUBLIC
    monkeypatch.setenv(EXPERIMENTAL_PUBLICATION_ENV, "garbage")
    assert resolve_experimental_publication_state() is ExperimentalPublicationState.OFF


def test_experimental_state_independent_of_signal_state(monkeypatch):
    # SIGNAL_PUBLICATION_STATE (validated signals) must NOT enable experimental.
    monkeypatch.delenv(EXPERIMENTAL_PUBLICATION_ENV, raising=False)
    monkeypatch.setenv("SIGNAL_PUBLICATION_STATE", "PROMOTED")
    assert experimental_publication_enabled() is False


# --- renderer content + safety -------------------------------------------


def test_renderer_matches_target_copy():
    pick = build_experimental_pick(_shadow())
    text = render_experimental_pick(pick, sequence_number=1, fixture_name="Arsenal vs Chelsea")
    assert "\U0001f9ea EXPERIMENTAL PICK #001" in text
    assert "Arsenal vs Chelsea" in text
    assert "Over 2.5 @ 1.85" in text
    assert "Engine: 61%" in text
    assert "Market: 54%" in text
    assert "Gap: +7pp" in text
    assert "Locked 58m before kickoff" in text
    assert "TESTING \u2014 NOT VALIDATED" in text
    assert "Not actionable" in text


def test_renderer_contains_required_labels():
    pick = build_experimental_pick(_shadow())
    text = render_experimental_pick(pick, sequence_number=7).upper()
    assert "EXPERIMENTAL" in text
    assert "NOT VALIDATED" in text
    assert "NOT ACTIONABLE" in text.replace("NOT ACTIONABLE.", "NOT ACTIONABLE")


def test_renderer_has_no_forbidden_terms():
    pick = build_experimental_pick(_shadow())
    text = render_experimental_pick(pick, sequence_number=1, fixture_name="Arsenal vs Chelsea")
    low = text.lower()
    for term in ("bet", "wager", "stake", "buy", "sell", "take", "play",
                 "edge", " ev ", "roi", "profit", "value", "tip"):
        assert term not in f" {low} ", f"forbidden term leaked: {term!r}"


def test_renderer_no_internal_labels():
    pick = build_experimental_pick(_shadow())
    text = render_experimental_pick(pick, sequence_number=1)
    for internal in ("SHADOW_RESIDUAL", "SHADOW_RESIDUAL".lower(), "shadow_residual",
                     "residual", "provenance", "devig", "PROSPECTIVE_SHADOW"):
        assert internal not in text


def test_renderer_is_deterministic():
    pick = build_experimental_pick(_shadow())
    a = render_experimental_pick(pick, sequence_number=3, fixture_name="A vs B")
    b = render_experimental_pick(pick, sequence_number=3, fixture_name="A vs B")
    assert a == b


def test_renderer_fixture_name_fallback_is_presentation_only():
    pick = build_experimental_pick(_shadow())
    text = render_experimental_pick(pick, sequence_number=1)  # no fixture name
    assert "Fixture F123" in text  # degrades to id (display-only), not an error


# --- champion / model outputs unchanged ----------------------------------


def test_pick_preserves_model_output_verbatim():
    # The projection must never recompute or alter the champion probability; it
    # copies p_model verbatim as engine_probability. This is the projection-
    # boundary guarantee that champion outputs are unchanged by this PR.
    for p in (0.501, 0.61, 0.739, 0.9):
        pick = build_experimental_pick(_shadow(p_model=p))
        assert pick.engine_probability == p


def test_pick_gap_is_pure_difference_no_ev():
    # model_market_gap_pp is EXACTLY (p_model - p_market_devig)*100 — a neutral
    # difference, never an odds-derived EV/edge computation.
    pick = build_experimental_pick(_shadow(p_model=0.60, p_market_devig=0.50))
    assert round(pick.model_market_gap_pp, 6) == 10.0
