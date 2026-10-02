"""Tests for the frozen Layer 3 chronology protocol."""

from __future__ import annotations

from src.research.data_source import ResearchMatch
from src.research.evaluation.chronology import (
    CALIBRATION_END_TS,
    DEVELOPMENT_END_TS,
    WARMUP_END_TS,
    EvaluationPartition,
    assert_calibration_partition_allowed,
    assert_selection_partition_allowed,
    build_chronology_manifest,
    partition_for_kickoff,
    write_chronology_manifest,
)


def _match(ref: int, kickoff: int, comp: int = 1) -> ResearchMatch:
    return ResearchMatch(
        match_id=ref,
        date_unix=kickoff,
        league_id=comp,
        season="sn_1",
        home_team="A",
        away_team="B",
        source_provider="THESTATSAPI",
        source_match_ref=f"mt_{ref}",
        competition_ref=f"comp_{comp}",
        season_ref="sn_1",
        home_team_ref=f"tm_{ref * 2}",
        away_team_ref=f"tm_{ref * 2 + 1}",
        home_team_id=ref * 2,
        away_team_id=ref * 2 + 1,
        home_goals=1,
        away_goals=0,
    )


def test_boundary_membership_is_exact() -> None:
    assert partition_for_kickoff(WARMUP_END_TS - 1) == EvaluationPartition.WARMUP
    assert partition_for_kickoff(WARMUP_END_TS) == EvaluationPartition.DEVELOPMENT
    assert partition_for_kickoff(DEVELOPMENT_END_TS - 1) == EvaluationPartition.DEVELOPMENT
    assert partition_for_kickoff(DEVELOPMENT_END_TS) == EvaluationPartition.CALIBRATION
    assert partition_for_kickoff(CALIBRATION_END_TS - 1) == EvaluationPartition.CALIBRATION
    assert partition_for_kickoff(CALIBRATION_END_TS) == EvaluationPartition.PROTECTED


def test_manifest_is_order_invariant_and_freezes_fixture_membership() -> None:
    rows = [
        _match(1, WARMUP_END_TS - 10),
        _match(2, WARMUP_END_TS + 10),
        _match(3, DEVELOPMENT_END_TS + 10),
        _match(4, CALIBRATION_END_TS + 10),
    ]
    a = build_chronology_manifest(matches=rows, corpus_manifest_hash="abc")
    b = build_chronology_manifest(matches=list(reversed(rows)), corpus_manifest_hash="abc")
    assert a.manifest_hash == b.manifest_hash
    assert a.partition(EvaluationPartition.WARMUP).n_fixtures == 1
    assert a.partition(EvaluationPartition.DEVELOPMENT).n_fixtures == 1
    assert a.partition(EvaluationPartition.CALIBRATION).n_fixtures == 1
    assert a.partition(EvaluationPartition.PROTECTED).n_fixtures == 1


def test_selection_guard_rejects_calibration_and_protected() -> None:
    assert_selection_partition_allowed(EvaluationPartition.DEVELOPMENT)
    for bad in (
        EvaluationPartition.WARMUP,
        EvaluationPartition.CALIBRATION,
        EvaluationPartition.PROTECTED,
    ):
        try:
            assert_selection_partition_allowed(bad)
        except PermissionError:
            pass
        else:
            raise AssertionError(f"{bad} must not be available to candidate selection")


def test_calibration_guard_is_calibration_only() -> None:
    assert_calibration_partition_allowed(EvaluationPartition.CALIBRATION)
    for bad in (
        EvaluationPartition.WARMUP,
        EvaluationPartition.DEVELOPMENT,
        EvaluationPartition.PROTECTED,
    ):
        try:
            assert_calibration_partition_allowed(bad)
        except PermissionError:
            pass
        else:
            raise AssertionError(f"{bad} must not be available to calibration fitting")


def test_chronology_writer_is_immutable(tmp_path) -> None:
    rows = [
        _match(1, WARMUP_END_TS - 10),
        _match(2, WARMUP_END_TS + 10),
        _match(3, DEVELOPMENT_END_TS + 10),
        _match(4, CALIBRATION_END_TS + 10),
    ]
    manifest = build_chronology_manifest(matches=rows, corpus_manifest_hash="abc")
    path = tmp_path / "chronology.json"
    write_chronology_manifest(path, manifest)
    write_chronology_manifest(path, manifest)
    path.write_text("{}\n")
    try:
        write_chronology_manifest(path, manifest)
    except FileExistsError:
        pass
    else:
        raise AssertionError("mutated chronology must not be overwritten")
