"""Tests for the Layer 3 development-only model tournament."""

from __future__ import annotations

from src.research.data_source import ResearchMatch
from src.research.evaluation.chronology import (
    CALIBRATION_END_TS,
    DEVELOPMENT_END_TS,
    WARMUP_END_TS,
    build_chronology_manifest,
)
from src.research.evaluation.model_tournament import (
    ANCHOR_CANDIDATE_ID,
    predefined_intensity_grid,
    run_layer3_development_tournament,
)
from src.research.models.dynamic_count_strength import GOALS_TARGET


def _match(
    ref: int,
    kickoff: int,
    home: int,
    away: int,
    goals=(1, 0),
    corners=(5, 4),
) -> ResearchMatch:
    return ResearchMatch(
        match_id=ref,
        date_unix=kickoff,
        league_id=1,
        season="sn_1",
        home_team=f"T{home}",
        away_team=f"T{away}",
        source_provider="THESTATSAPI",
        source_match_ref=f"mt_{ref}",
        competition_ref="comp_1",
        season_ref="sn_1",
        home_team_ref=f"tm_{home}",
        away_team_ref=f"tm_{away}",
        home_team_id=home,
        away_team_id=away,
        home_goals=goals[0],
        away_goals=goals[1],
        total_goals=sum(goals),
        corners_home=corners[0],
        corners_away=corners[1],
        total_corners=sum(corners),
    )


def _rows():
    rows = []
    ref = 1
    # Warmup history.
    for i in range(30):
        rows.append(
            _match(
                ref,
                WARMUP_END_TS - (30 - i) * 86400,
                1 + (i % 4),
                5 + (i % 4),
                goals=(2 if i % 2 == 0 else 1, 0 if i % 3 == 0 else 1),
                corners=(6, 3),
            )
        )
        ref += 1
    # Development.
    for i in range(40):
        rows.append(
            _match(
                ref,
                WARMUP_END_TS + (i + 1) * 86400,
                1 + (i % 4),
                5 + (i % 4),
                goals=(2, 1),
                corners=(7, 3),
            )
        )
        ref += 1
    # Calibration and protected counterexamples should never be scored.
    rows.append(
        _match(
            ref,
            DEVELOPMENT_END_TS + 10,
            1,
            5,
            goals=(99, 99),
            corners=(99, 99),
        )
    )
    ref += 1
    rows.append(
        _match(
            ref,
            CALIBRATION_END_TS + 10,
            1,
            5,
            goals=(99, 99),
            corners=(99, 99),
        )
    )
    return rows


def test_intensity_grid_is_bounded_and_contains_anchor() -> None:
    grid = predefined_intensity_grid()
    assert len(grid) == 27
    assert len({candidate_id for candidate_id, _ in grid}) == 27
    assert ANCHOR_CANDIDATE_ID in {candidate_id for candidate_id, _ in grid}


def test_tournament_never_scores_calibration_or_protected() -> None:
    rows = _rows()
    chronology = build_chronology_manifest(
        matches=rows,
        corpus_manifest_hash="corpus",
    )
    tournament, oof = run_layer3_development_tournament(
        matches=rows,
        corpus_manifest_hash="corpus",
        chronology=chronology,
    )
    assert tournament.calibration_rows_scored == 0
    assert tournament.protected_rows_scored == 0
    assert len(oof["goals"]) == 40
    assert len(oof["corners"]) == 40
    assert all(row.observed_home < 99 for row in oof["goals"])
    assert all(row.observed_home < 99 for row in oof["corners"])


def test_oof_rows_are_strictly_development_only() -> None:
    rows = _rows()
    chronology = build_chronology_manifest(
        matches=rows,
        corpus_manifest_hash="corpus",
    )
    _, oof = run_layer3_development_tournament(
        matches=rows,
        corpus_manifest_hash="corpus",
        chronology=chronology,
    )
    for target_rows in oof.values():
        assert target_rows
        assert all(
            WARMUP_END_TS <= row.kickoff_ts < DEVELOPMENT_END_TS
            for row in target_rows
        )


def test_tournament_is_deterministic() -> None:
    rows = _rows()
    chronology = build_chronology_manifest(
        matches=rows,
        corpus_manifest_hash="corpus",
    )
    a, aoof = run_layer3_development_tournament(
        matches=rows,
        corpus_manifest_hash="corpus",
        chronology=chronology,
    )
    b, boof = run_layer3_development_tournament(
        matches=list(reversed(rows)),
        corpus_manifest_hash="corpus",
        chronology=chronology,
    )
    assert a.tournament_hash == b.tournament_hash
    assert {
        key: [row.to_dict() for row in value]
        for key, value in aoof.items()
    } == {
        key: [row.to_dict() for row in value]
        for key, value in boof.items()
    }
