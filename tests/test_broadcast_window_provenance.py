"""The broadcast message must render the per-team windows map.

This closes a specific observability gap. The windows map was recorded in the
ledger and folded into the commitment hash, but never printed, so a reader saw
"Nantes 4, Nancy 4 (min 3)" with no way to tell that both rolling windows had
abstained and the forecast was carried by a season-to-date mean alone. That is the
case where a reader most needs the information, and it was the one case the message
withheld.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.research.prediction_engine.broadcast.payload import (
    build_forecast_payload,
    find_forbidden_content,
    render_checked_message,
    render_message,
)
from src.research.prediction_engine.broadcast.scope_config import load_scope_config

SCOPE_PATH = Path("config/forecast_broadcast_scope.json")


@pytest.fixture(scope="module")
def config():
    return load_scope_config(SCOPE_PATH)


def _payload(config, history_provenance):
    probabilities = {
        ("goals", 2.5): 0.5397,
        ("corners", 9.5): 0.5447,
        ("cards", 4.5): 0.4126,
        ("btts", None): 0.5661,
    }
    return build_forecast_payload(
        config=config,
        fixture_id="fixture-1",
        comp_id="comp_3039",
        home_team="Nantes",
        away_team="Nancy",
        kickoff_unix=1_789_200_000,
        probabilities=probabilities,
        model_version="hierarchical-count/v1",
        data_cutoff_utc="2026-09-07T00:00:00+00:00",
        generated_at_utc="2026-09-07T12:00:00+00:00",
        corpus_provenance={
            "corpus_content_hash": "abc123",
            "corpus_match_count": 15362,
            "corpus_seasons": ["2026/2027"],
        },
        history_provenance=history_provenance,
    )


#: The live shape today: each declared window is populated or abstains.
FIXED_WINDOW_PROVENANCE = {
    "min_current_season_matches": 3,
    "windows_declared": ["w5", "w10", "std"],
    "sufficient": True,
    "home": {
        "current_season": "12345",
        "current_season_matches": 4,
        "meets_min_history": True,
        "windows": {"w5": "abstain", "w10": "abstain", "std": "populated"},
    },
    "away": {
        "current_season": "12345",
        "current_season_matches": 4,
        "meets_min_history": True,
        "windows": {"w5": "abstain", "w10": "abstain", "std": "populated"},
    },
}

#: The shrinking-window shape: matches actually used against the window requested.
SHRINKING_WINDOW_PROVENANCE = {
    "min_current_season_matches": 3,
    "window_declared": "last5",
    "window_requested": 5,
    "window_policy": (
        "current season only; shrinks below the declared window rather than "
        "backfilling from the prior season"
    ),
    "gate_keys_on": "window_availability_and_min_current_season_matches",
    "sufficient": True,
    "home": {
        "label": "last5",
        "requested": 5,
        "used": 4,
        "deficit": 1,
        "status": "shrunk",
        "available": True,
        "shrunk": True,
        "season": "12345",
        "current_season_matches": 4,
    },
    "away": {
        "label": "last5",
        "requested": 5,
        "used": 3,
        "deficit": 2,
        "status": "shrunk",
        "available": True,
        "shrunk": True,
        "season": "12345",
        "current_season_matches": 3,
    },
    "shrinkage_weights": {
        "league": 0.8893,
        "home_attack": 0.3118,
        "away_attack": 0.2402,
    },
    "prior_season_contribution": {"home_attack": -0.0412, "away_attack": 0.0183},
}


# ─────────────────────────────────────────────────────────────────────────────
# The gap that is being closed
# ─────────────────────────────────────────────────────────────────────────────
def test_fixed_window_map_is_rendered_per_team(config) -> None:
    text = render_message(_payload(config, FIXED_WINDOW_PROVENANCE))
    assert "windows[Nantes]: std=populated, w10=abstain, w5=abstain" in text
    assert "windows[Nancy]: std=populated, w10=abstain, w5=abstain" in text
    assert "windows_declared: w5, w10, std" in text


def test_abstaining_windows_are_visible_not_merely_implied(config) -> None:
    """The Nantes/Nancy case: four matches each, every rolling window abstains."""
    text = render_message(_payload(config, FIXED_WINDOW_PROVENANCE))
    assert "current_season_matches: Nantes 4, Nancy 4 (min 3)" in text
    assert text.count("abstain") == 4, "both teams' abstaining windows must show"


def test_shrinking_window_reports_matches_actually_used(config) -> None:
    text = render_message(_payload(config, SHRINKING_WINDOW_PROVENANCE))
    assert "windows[Nantes]: last5=4/5 matches used, shrunk, season 12345" in text
    assert "windows[Nancy]: last5=3/5 matches used, shrunk, season 12345" in text


def test_window_policy_and_gate_basis_are_stated(config) -> None:
    text = render_message(_payload(config, SHRINKING_WINDOW_PROVENANCE))
    assert "window_policy:" in text
    assert "backfilling from the prior season" in text
    assert (
        "history_gate_keys_on: window_availability_and_min_current_season_matches"
        in text
    )


def test_shrinkage_weights_are_rendered(config) -> None:
    """A forecast leaning on the league average must be distinguishable."""
    text = render_message(_payload(config, SHRINKING_WINDOW_PROVENANCE))
    assert "shrinkage_weights:" in text
    assert "league=0.89" in text
    assert "home_attack=0.31" in text


def test_prior_season_contribution_is_rendered(config) -> None:
    text = render_message(_payload(config, SHRINKING_WINDOW_PROVENANCE))
    assert "prior_season_contribution:" in text
    assert "home_attack=-0.04" in text


def test_a_forecast_on_four_matches_reads_differently_from_one_on_thirty(
    config,
) -> None:
    thin = dict(SHRINKING_WINDOW_PROVENANCE)
    rich = {
        **SHRINKING_WINDOW_PROVENANCE,
        "home": {
            **SHRINKING_WINDOW_PROVENANCE["home"],
            "used": 5,
            "deficit": 0,
            "status": "full",
            "shrunk": False,
            "current_season_matches": 30,
        },
        "away": {
            **SHRINKING_WINDOW_PROVENANCE["away"],
            "used": 5,
            "deficit": 0,
            "status": "full",
            "shrunk": False,
            "current_season_matches": 28,
        },
    }
    thin_text = render_message(_payload(config, thin))
    rich_text = render_message(_payload(config, rich))
    assert thin_text != rich_text
    assert "shrunk" in thin_text
    assert "5/5 matches used, full" in rich_text
    assert "current_season_matches: Nantes 30, Nancy 28" in rich_text


# ─────────────────────────────────────────────────────────────────────────────
# Nothing else may regress
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "provenance", [FIXED_WINDOW_PROVENANCE, SHRINKING_WINDOW_PROVENANCE]
)
def test_the_content_gate_still_passes(config, provenance) -> None:
    payload = _payload(config, provenance)
    text = render_checked_message(payload, config)
    assert not find_forbidden_content(text)


@pytest.mark.parametrize(
    "provenance", [FIXED_WINDOW_PROVENANCE, SHRINKING_WINDOW_PROVENANCE]
)
def test_required_provenance_lines_are_all_still_present(config, provenance) -> None:
    payload = _payload(config, provenance)
    text = render_message(payload)
    for line in (
        "model_version: hierarchical-count/v1",
        "data_cutoff_utc: 2026-09-07T00:00:00+00:00",
        "generated_at_utc: 2026-09-07T12:00:00+00:00",
        f"commitment: {payload.commitment_hash()}",
        "corpus_content_hash: abc123",
        "corpus_matches: 15362",
    ):
        assert line in text


def test_both_sides_of_every_market_are_still_stated(config) -> None:
    payload = _payload(config, FIXED_WINDOW_PROVENANCE)
    text = render_message(payload)
    for market in payload.priced_markets:
        assert market.over_label in text
        assert market.under_label in text


def test_a_payload_without_history_provenance_still_renders(config) -> None:
    text = render_message(_payload(config, None))
    assert "FORECAST" in text
    assert "windows[" not in text


def test_partial_history_provenance_does_not_break_rendering(config) -> None:
    """A side dict with neither shape present must degrade, not raise."""
    provenance = {
        "min_current_season_matches": 3,
        "home": {"current_season_matches": 6},
        "away": {"current_season_matches": 5},
    }
    text = render_message(_payload(config, provenance))
    assert "current_season_matches: Nantes 6, Nancy 5 (min 3)" in text
    assert "windows[" not in text
