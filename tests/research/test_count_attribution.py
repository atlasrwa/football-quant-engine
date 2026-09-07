"""Tests for per-fixture attribution.

Three properties matter and each is asserted: the explanation comes from the
fitted weights, it passes the content gate, and it says "no strong signal either
way" when the model is neutral instead of manufacturing a story.
"""

from __future__ import annotations

import math

import pytest

from src.research.models.count_attribution import (
    DEFAULT_SIGNAL_THRESHOLD,
    FEATURE_LEXICON,
    LEAN_NEUTRAL,
    LEAN_OVER,
    LEAN_UNDER,
    NO_SIGNAL_STATEMENT,
    _STRUCTURAL_FEATURES,
    explain_market,
    render_explanations,
)
from src.research.models.market_family import ALL_FAMILY_NAMES, family_by_name
from src.research.prediction_engine.broadcast.payload import find_forbidden_content

from tests.research.test_hierarchical_market_model import _fit, _row


def _fixture_rows(model, *, league="league-0"):
    teams = sorted(key[1] for key in model.attack_effects if key[0] == league)
    home, away = teams[0], teams[1]
    return (
        _row(model, league, home, away, is_home=True),
        _row(model, league, away, home, is_home=False),
    )


def _explanations(family_name: str, *, count: int = 12):
    family = family_by_name(family_name)
    model = _fit(family)
    league = "league-0"
    teams = sorted(key[1] for key in model.attack_effects if key[0] == league)
    results = []
    for index in range(min(count, len(teams) - 1)):
        home, away = teams[index], teams[index + 1]
        results.append(
            explain_market(
                model,
                _row(model, league, home, away, is_home=True),
                _row(model, league, away, home, is_home=False),
            )
        )
    return model, results


# ─────────────────────────────────────────────────────────────────────────────
# The content gate applies to explanation text too
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("family_name", ALL_FAMILY_NAMES)
def test_explanations_pass_the_content_gate(family_name: str) -> None:
    """No skill, edge, expected-value or recommendation language, ever."""
    _, explanations = _explanations(family_name)
    assert explanations
    for explanation in explanations:
        text = explanation.text()
        forbidden = find_forbidden_content(text)
        assert not forbidden, f"{family_name}: {forbidden} in {text!r}"


def test_the_lexicon_itself_is_gate_clean() -> None:
    """Every phrase that can reach a reader is checked, not just sampled output."""
    for feature, phrase in FEATURE_LEXICON.items():
        forbidden = find_forbidden_content(phrase)
        assert not forbidden, f"lexicon entry {feature!r} -> {phrase!r}: {forbidden}"


def test_rendered_block_is_gate_clean() -> None:
    _, explanations = _explanations("corners")
    forbidden = find_forbidden_content(render_explanations(explanations))
    assert not forbidden


# ─────────────────────────────────────────────────────────────────────────────
# Attribution comes from the fitted model
# ─────────────────────────────────────────────────────────────────────────────
def test_every_driver_contribution_is_weight_times_standardised_value() -> None:
    """The arithmetic is the model's, verified term by term."""
    family = family_by_name("corners")
    model = _fit(family)
    home_row, away_row = _fixture_rows(model)
    explanation = explain_market(model, home_row, away_row)
    layer = model.global_layer
    feature_drivers = [d for d in explanation.drivers if d.kind == "feature"]
    assert feature_drivers
    for driver in feature_drivers:
        assert driver.weight is not None
        assert driver.standardised_value is not None
        assert driver.contribution == pytest.approx(
            driver.weight * driver.standardised_value, abs=1e-12
        )
        # The weight is the global slope plus any shrunk league deviation.
        base = layer.weights[driver.feature]
        slope = model.league_slopes.get((home_row.league, driver.feature))
        expected = base + (slope.posterior if slope else 0.0)
        assert driver.weight == pytest.approx(expected, abs=1e-12)


def test_feature_contributions_reconstruct_log_mu() -> None:
    """Nothing is added to or hidden from the explanation."""
    family = family_by_name("corners")
    model = _fit(family)
    home_row, _ = _fixture_rows(model)
    terms = model._side_terms(home_row)
    rebuilt = model.global_layer.intercept + sum(
        terms["feature_contributions"].values()
    )
    league = terms["league_effect"]
    rebuilt += league.posterior if league else 0.0
    rebuilt += terms["attack_effect"].posterior if terms["attack_effect"] else 0.0
    rebuilt += terms["concede_effect"].posterior if terms["concede_effect"] else 0.0
    clipped = min(3.5, max(-4.0, rebuilt))
    assert float(terms["log_mu"]) == pytest.approx(clipped, abs=1e-9)


def test_team_state_drivers_carry_their_own_shrinkage() -> None:
    model = _fit(family_by_name("corners"))
    home_row, away_row = _fixture_rows(model)
    explanation = explain_market(model, home_row, away_row)
    state_drivers = [
        d for d in explanation.drivers if d.kind in ("team_attack", "team_concede")
    ]
    assert state_drivers
    for driver in state_drivers:
        assert driver.n_observations is not None and driver.n_observations > 0
        assert driver.shrinkage_weight is not None
        assert 0.0 <= driver.shrinkage_weight <= 1.0


def test_driver_direction_follows_the_sign_of_the_fitted_contribution() -> None:
    """A statement's direction is never independent of the model's arithmetic."""
    model = _fit(family_by_name("corners"))
    home_row, away_row = _fixture_rows(model)
    explanation = explain_market(model, home_row, away_row)
    if explanation.lean == LEAN_NEUTRAL:
        pytest.skip("neutral fixture carries no directional statements")
    expected_up = explanation.lean == LEAN_OVER
    ranked = [
        d
        for d in explanation.drivers
        if d.feature not in _STRUCTURAL_FEATURES and d.magnitude > 1e-9
    ]
    contributing = [d for d in ranked if d.pushes_up == expected_up]
    assert contributing, "a lean must be supported by same-signed contributions"


def test_attribution_source_is_declared_as_the_fitted_model() -> None:
    model = _fit(family_by_name("cards"))
    home_row, away_row = _fixture_rows(model)
    payload = explain_market(model, home_row, away_row).to_dict()
    assert payload["attribution_source"] == "fitted_model_coefficients"


def test_structural_features_never_appear_as_drivers() -> None:
    """Terms identical in every fixture explain nothing about this one."""
    for family_name in ("corners", "goals", "cards"):
        _, explanations = _explanations(family_name)
        for explanation in explanations:
            for statement in explanation.statements:
                assert "home advantage" not in statement
                assert "how many recent matches" not in statement


def test_no_rule_mining_vocabulary_is_produced() -> None:
    """No thresholds, no percentiles, no discretised conditions in the output."""
    for family_name in ("corners", "goals", "cards"):
        _, explanations = _explanations(family_name)
        for explanation in explanations:
            text = explanation.text().lower()
            for banned in ("p70", "percentile", " threshold", "% of matches", " and "):
                if banned == " and ":
                    continue
                assert banned not in text, f"{banned!r} appeared in {text!r}"


# ─────────────────────────────────────────────────────────────────────────────
# Neutral is a real answer
# ─────────────────────────────────────────────────────────────────────────────
def test_a_league_typical_fixture_reports_no_strong_signal() -> None:
    """Feed the model its own training means and it must decline to editorialise."""
    family = family_by_name("corners")
    model = _fit(family)
    layer = model.global_layer
    league = "league-0"
    neutral_home = _row(model, league, "unseen-home", "unseen-away", is_home=True)
    neutral_away = _row(model, league, "unseen-away", "unseen-home", is_home=False)
    explanation = explain_market(model, neutral_home, neutral_away)
    assert explanation.lean == LEAN_NEUTRAL
    assert explanation.has_signal is False
    assert NO_SIGNAL_STATEMENT in explanation.text()
    assert explanation.signal_strength < DEFAULT_SIGNAL_THRESHOLD


def test_neutral_text_makes_no_directional_claim() -> None:
    family = family_by_name("goals")
    model = _fit(family, overdispersed=False)
    explanation = explain_market(
        model,
        _row(model, "league-0", "unseen-a", "unseen-b", is_home=True),
        _row(model, "league-0", "unseen-b", "unseen-a", is_home=False),
    )
    text = explanation.text().lower()
    assert "leans higher" not in text
    assert "leans lower" not in text


def test_a_strong_fixture_does_produce_a_lean() -> None:
    """Neutrality must not be the only outcome the layer can reach."""
    model = _fit(family_by_name("corners"))
    league = "league-0"
    teams = sorted(key[1] for key in model.attack_effects if key[0] == league)
    leans = set()
    for index in range(len(teams) - 1):
        explanation = explain_market(
            model,
            _row(model, league, teams[index], teams[index + 1], is_home=True),
            _row(model, league, teams[index + 1], teams[index], is_home=False),
        )
        leans.add(explanation.lean)
    assert leans & {LEAN_OVER, LEAN_UNDER}, "no fixture produced a directional read"


def test_a_lean_always_comes_with_at_least_one_statement() -> None:
    for family_name in ALL_FAMILY_NAMES:
        _, explanations = _explanations(family_name)
        for explanation in explanations:
            if explanation.has_signal:
                assert explanation.statements


def test_thin_evidence_is_stated_plainly() -> None:
    """A team with no fitted state must be flagged, not silently averaged."""
    model = _fit(family_by_name("corners"))
    explanation = explain_market(
        model,
        _row(model, "league-0", "brand-new-team", "also-new", is_home=True),
        _row(model, "league-0", "also-new", "brand-new-team", is_home=False),
    )
    assert explanation.thin_evidence_note is not None
    assert "no fitted team state" in explanation.thin_evidence_note
    assert not find_forbidden_content(explanation.text())


def test_line_and_reference_probabilities_are_both_reported() -> None:
    family = family_by_name("corners")
    model = _fit(family)
    home_row, away_row = _fixture_rows(model)
    explanation = explain_market(model, home_row, away_row)
    assert set(explanation.line_probabilities) == set(family.lines)
    assert set(explanation.reference_probabilities) == set(family.lines)
    for value in explanation.line_probabilities.values():
        assert 0.0 <= value <= 1.0
    ordered = [explanation.line_probabilities[line] for line in family.lines]
    assert all(b <= a + 1e-12 for a, b in zip(ordered, ordered[1:]))


def test_explanation_dict_is_json_ready() -> None:
    import json

    model = _fit(family_by_name("corners"))
    home_row, away_row = _fixture_rows(model)
    payload = explain_market(model, home_row, away_row).to_dict()
    encoded = json.dumps(payload)
    assert "fitted_model_coefficients" in encoded
    assert math.isfinite(payload["expected_total"])
