"""Regression tests locking in the adversarial-review findings.

Complements test_prospective_infra.py with the checks that were probed during
the independent adversarial pass (see
research/evaluation/prospective_adversarial_review.md).
"""

from __future__ import annotations

import subprocess

import pytest

from src.research.prospective.lineup_state import normalize_lineup
from src.research.prospective.player_state import PlayerMatchObservation, build_player_state

KICKOFF = 1_700_000_000.0


def test_transfer_keeps_single_identity():
    """Check 10: same player_id across different teams is one identity."""
    obs = [
        PlayerMatchObservation("pl_x", "tm_old", KICKOFF - 20 * 86400, 90, True, goals=1),
        PlayerMatchObservation("pl_x", "tm_new", KICKOFF - 10 * 86400, 90, True, goals=1),
    ]
    st = build_player_state("pl_x", obs, cutoff_ts=KICKOFF)
    assert st.appearances == 2
    assert st.goals_per_90 == pytest.approx(1.0)


def test_home_away_not_inverted():
    """Check 8: normalization preserves home/away distinction by team id."""
    payload = {"data": {"confirmed": True,
        "home": {"id": "tm_H", "starting_xi": [{"id": "pl_1"}], "substitutes": []},
        "away": {"id": "tm_A", "starting_xi": [{"id": "pl_2"}], "substitutes": []}}}
    nl = normalize_lineup(payload, fixture_id="f", observed_at=KICKOFF - 4000)
    assert nl.home.team_id == "tm_H" and "pl_1" in nl.home.starter_ids
    assert nl.away.team_id == "tm_A" and "pl_2" in nl.away.starter_ids


def test_champion_untouched_vs_main():
    """Check 18: no modification to champion model files vs main."""
    out = subprocess.run(
        ["git", "diff", "--stat", "main", "--",
         "src/research/models/hierarchical_market_model.py",
         "src/research/models/side_rows.py",
         "src/research/models/market_family.py"],
        capture_output=True, text=True, cwd="/home/ubuntu",
    )
    assert out.stdout.strip() == "", f"champion changed:\n{out.stdout}"


def test_no_api_key_in_capture_serialization():
    """Check 19: a serialized capture never contains an auth key."""
    from src.research.prospective.capture import CaptureRecord

    rec = CaptureRecord(
        provider="thestatsapi", provider_entity_id="mt_1", canonical_entity_id="mt_1",
        concept="odds:goals:over:2.5", value=1.9,
        observed_at=KICKOFF, retrieved_at=KICKOFF, raw_payload_hash="h")
    blob = str(rec.to_dict()).lower()
    assert "authorization" not in blob and "bearer" not in blob and "api_key" not in blob
