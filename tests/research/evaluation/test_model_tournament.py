"""Tests for the Layer 3 development-only model tournament."""

from __future__ import annotations

from src.research.data_source import ResearchMatch
from src.research.evaluation.chronology import (
    CALIBRATION_END_TS,
    DEVELOPMENT_END_TS,
    WARMUP_END_TS,
    build_chronology_manifest,
)
from src.research.evaluation import model_tournament
from src.research.evaluation.model_tournament import (
    ANCHOR_CANDIDATE_ID,
    predefined_intensity_grid,
    run_distribution_tournament,
    run_layer3_development_tournament,
)
from src.research.models.dynamic_count_strength import (
    GOALS_TARGET,
    DynamicCountConfig,
    DynamicHierarchicalCountBaseline,
)


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

def test_distribution_tournament_never_uses_immediate_process_batch(monkeypatch) -> None:
    rows = _rows()

    def forbidden_process_batch(self, matches):
        raise AssertionError("scientific tournament must use horizon-gated walk_forward")

    monkeypatch.setattr(
        DynamicHierarchicalCountBaseline,
        "process_batch",
        forbidden_process_batch,
    )
    report, oof = run_distribution_tournament(
        matches=rows,
        target=GOALS_TARGET,
        selected_config=DynamicCountConfig(),
    )
    assert report.n_scored == len(oof) == 40


def test_distribution_selector_obeys_t6h_availability_boundary(monkeypatch) -> None:
    selection_observations = []

    class SpySelector:
        def __init__(self, grid, min_observations=20):
            self.grid = tuple(grid)
            self.observations = 0

        @property
        def selected(self):
            selection_observations.append(self.observations)
            return self.grid[0]

        def update(self, loss_by_parameter):
            # Exercise every registered parameter so this spy preserves the
            # selector's loss-evaluation side effects.
            for value in self.grid:
                float(loss_by_parameter(value))
            self.observations += 1

    monkeypatch.setattr(model_tournament, "OnlineGridSelector", SpySelector)

    t0 = WARMUP_END_TS - 2 * 86400
    t1 = WARMUP_END_TS - 1 * 86400
    t2 = WARMUP_END_TS + 1 * 3600
    t3 = t2 + 6 * 3600
    t4 = t2 + 12 * 3600

    rows = [
        _match(1001, t0, 1, 5, goals=(1, 0)),
        _match(1002, t1, 1, 5, goals=(2, 0)),
        _match(1003, t2, 1, 5, goals=(3, 0)),
        _match(1004, t3, 1, 5, goals=(4, 0)),
        _match(1005, t4, 1, 5, goals=(5, 0)),
    ]

    _, oof = run_distribution_tournament(
        matches=rows,
        target=GOALS_TARGET,
        selected_config=DynamicCountConfig(),
    )

    # t0 is available for t1 (24h gap); t1 for t2 (25h gap).
    # t2 is NOT available for t3 (6h gap), because source+6h > target-6h.
    # At t4 the equality source(t2)+6h == target(t4)-6h is admissible.
    assert selection_observations == [0, 1, 2, 2, 3]
    assert [row.kickoff_ts for row in oof] == [t2, t3, t4]
