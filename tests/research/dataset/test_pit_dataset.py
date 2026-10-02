"""Adversarial tests for the point-in-time QFE V2 dataset builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.research.data_source import ResearchMatch
from src.research.dataset.manifest import (
    verify_immutable_dataset,
    write_immutable_dataset,
)
from src.research.dataset.pit import (
    DatasetIntegrityError,
    PITDatasetBuilder,
    PITDatasetSpec,
)


DAY = 86400
BASE = 1_700_000_000


def _match(
    *,
    ref: str,
    kickoff: int,
    home_ref: str,
    away_ref: str,
    home_name: str,
    away_name: str,
    goals: tuple[int, int] = (0, 0),
    corners: tuple[int, int] = (0, 0),
    shots: tuple[int, int] = (10, 10),
    sot: tuple[int, int] = (4, 4),
    fouls: tuple[int, int] = (10, 10),
    yellows: tuple[int, int] = (1, 1),
    possession: tuple[float, float] = (50.0, 50.0),
    xg: tuple[float, float] = (1.0, 1.0),
    competition_ref: str = "comp_3039",
    league_id: int = 3039,
    season_ref: str = "sn_1",
    **overrides,
) -> ResearchMatch:
    match_id = int(ref.split("_")[-1])
    values = dict(
        match_id=match_id,
        date_unix=kickoff,
        league_id=league_id,
        season=season_ref,
        home_team=home_name,
        away_team=away_name,
        source_provider="THESTATSAPI",
        source_match_ref=ref,
        competition_ref=competition_ref,
        season_ref=season_ref,
        home_team_ref=home_ref,
        away_team_ref=away_ref,
        home_team_id=int(home_ref.split("_")[-1]),
        away_team_id=int(away_ref.split("_")[-1]),
        home_goals=goals[0],
        away_goals=goals[1],
        total_goals=sum(goals),
        corners_home=corners[0],
        corners_away=corners[1],
        total_corners=sum(corners),
        shots_home=shots[0],
        shots_away=shots[1],
        shots_on_target_home=sot[0],
        shots_on_target_away=sot[1],
        fouls_home=fouls[0],
        fouls_away=fouls[1],
        yellow_cards_home=yellows[0],
        yellow_cards_away=yellows[1],
        total_cards=sum(yellows),
        possession_home=possession[0],
        possession_away=possession[1],
        home_xg=xg[0],
        away_xg=xg[1],
    )
    values.update(overrides)
    return ResearchMatch(**values)


def _three_matches():
    m1 = _match(
        ref="mt_1",
        kickoff=BASE,
        home_ref="tm_1",
        away_ref="tm_2",
        home_name="A",
        away_name="B",
        goals=(2, 1),
        corners=(6, 4),
        shots=(14, 8),
        sot=(6, 3),
        xg=(1.8, 0.9),
    )
    m2 = _match(
        ref="mt_2",
        kickoff=BASE + DAY,
        home_ref="tm_3",
        away_ref="tm_1",
        home_name="C",
        away_name="A",
        goals=(0, 1),
        corners=(3, 5),
        shots=(7, 12),
        sot=(2, 5),
        xg=(0.6, 1.4),
    )
    m3 = _match(
        ref="mt_3",
        kickoff=BASE + 2 * DAY,
        home_ref="tm_1",
        away_ref="tm_3",
        home_name="A",
        away_name="C",
        goals=(3, 0),
        corners=(7, 2),
        shots=(16, 5),
        sot=(8, 1),
        xg=(2.2, 0.4),
    )
    return m1, m2, m3


def _builder(horizon: int = 6 * 3600, embargo: int = 6 * 3600):
    return PITDatasetBuilder(
        spec=PITDatasetSpec(
            decision_horizon_seconds=horizon,
            reconstructed_post_match_embargo_seconds=embargo,
        )
    )


def test_current_fixture_never_predicts_itself() -> None:
    m1, _, _ = _three_matches()
    artifact = _builder().build([m1])
    row = artifact.rows[0]
    assert row.features["home_history_matches"] == 0
    assert row.features["away_history_matches"] == 0
    assert row.features["home_goals_for_mean"] is None
    assert row.targets["goals_total_regulation"] == 3


def test_prior_fixture_enters_only_after_registered_availability() -> None:
    m1, m2, _ = _three_matches()
    artifact = _builder().build([m1, m2])
    row2 = artifact.rows[1]

    # A is away in match 2. Its only eligible history is match 1.
    assert row2.features["away_history_matches"] == 1
    assert row2.features["away_goals_for_mean"] == pytest.approx(2.0)
    assert row2.features["away_goals_against_mean"] == pytest.approx(1.0)
    assert row2.features["away_corners_for_mean"] == pytest.approx(6.0)
    assert row2.features["competition_goals_total_mean"] == pytest.approx(3.0)

    # C had no earlier match.
    assert row2.features["home_history_matches"] == 0
    assert row2.lineage.eligible_history_matches == 1
    assert row2.lineage.max_source_available_at <= row2.cutoff_ts


def test_same_day_match_is_withheld_by_embargo() -> None:
    m1 = _match(
        ref="mt_1",
        kickoff=BASE,
        home_ref="tm_1",
        away_ref="tm_2",
        home_name="A",
        away_name="B",
        goals=(2, 1),
    )
    m2 = _match(
        ref="mt_2",
        kickoff=BASE + 5 * 3600,
        home_ref="tm_3",
        away_ref="tm_1",
        home_name="C",
        away_name="A",
        goals=(0, 0),
    )
    artifact = _builder(horizon=3600, embargo=6 * 3600).build([m1, m2])
    row2 = artifact.rows[1]
    assert row2.features["away_history_matches"] == 0
    assert row2.lineage.eligible_history_matches == 0


def test_input_order_does_not_change_artifact() -> None:
    m1, m2, m3 = _three_matches()
    a = _builder().build([m1, m2, m3])
    b = _builder().build([m3, m1, m2])
    assert a.manifest.manifest_hash == b.manifest.manifest_hash
    assert [row.content_hash for row in a.rows] == [
        row.content_hash for row in b.rows
    ]


def test_extra_time_match_is_not_used_as_regulation_history() -> None:
    m1, m2, _ = _three_matches()
    m1 = _match(
        ref="mt_1",
        kickoff=m1.date_unix,
        home_ref="tm_1",
        away_ref="tm_2",
        home_name="A",
        away_name="B",
        goals=(3, 2),
        extra_time_home_goals=1,
        extra_time_away_goals=0,
    )
    artifact = _builder().build([m1, m2])
    row1, row2 = artifact.rows

    assert row1.target_status["goals_total_regulation"] == "EXTRA_TIME_UNSAFE"
    assert row1.targets["goals_total_regulation"] is None
    assert row2.features["away_history_matches"] == 0
    assert artifact.manifest.excluded_history_counts[
        "extra_time_or_shootout"
    ] == 1


def test_stable_identity_is_mandatory() -> None:
    m1, _, _ = _three_matches()
    broken = ResearchMatch(
        **{
            **m1.to_dict(),
            "home_team_ref": None,
        }
    )
    with pytest.raises(DatasetIntegrityError):
        _builder().build([broken])


def test_duplicate_fixture_fails_visibly() -> None:
    m1, _, _ = _three_matches()
    with pytest.raises(DatasetIntegrityError):
        _builder().build([m1, m1])


def test_feature_names_are_odds_blind() -> None:
    artifact = _builder().build(_three_matches())
    for row in artifact.rows:
        names = " ".join(row.features).lower()
        assert "odds" not in names
        assert "price" not in names
        assert "p_market" not in names


def test_manifest_records_reconstructed_availability_not_fake_timestamp() -> None:
    artifact = _builder().build(_three_matches())
    manifest = artifact.manifest
    assert manifest.historical_availability_policy.startswith("RECONSTRUCTED_")
    assert manifest.reconstructed_post_match_embargo_seconds == 6 * 3600
    assert manifest.provider_registry_version == "thestatsapi-capabilities-v1"
    assert manifest.target_registry_version == "qfe-target-contracts-v1"


def test_immutable_artifact_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    artifact = _builder().build(_three_matches())
    first = write_immutable_dataset(
        root=tmp_path,
        manifest=artifact.manifest,
        rows=artifact.row_dicts(),
    )
    second = write_immutable_dataset(
        root=tmp_path,
        manifest=artifact.manifest,
        rows=artifact.row_dicts(),
    )
    assert first.path.name == artifact.manifest.manifest_hash
    assert second.already_existed is True
    verified = verify_immutable_dataset(first.path)
    assert verified.manifest_hash == artifact.manifest.manifest_hash


def test_immutable_artifact_detects_row_tampering(tmp_path: Path) -> None:
    artifact = _builder().build(_three_matches())
    result = write_immutable_dataset(
        root=tmp_path,
        manifest=artifact.manifest,
        rows=artifact.row_dicts(),
    )
    rows_path = result.path / "rows.jsonl"
    lines = rows_path.read_text().splitlines()
    row0 = json.loads(lines[0])
    row0["features"]["home_history_matches"] = 999
    lines[0] = json.dumps(row0, sort_keys=True)
    rows_path.write_text("\n".join(lines) + "\n")

    with pytest.raises(ValueError, match="rows byte hash"):
        verify_immutable_dataset(result.path)


def test_venue_and_competition_histories_are_separate() -> None:
    m1 = _match(
        ref="mt_10", kickoff=BASE, home_ref="tm_1", away_ref="tm_2",
        home_name="A", away_name="B", goals=(2, 0),
        competition_ref="comp_1", league_id=1,
    )
    m2 = _match(
        ref="mt_11", kickoff=BASE + DAY, home_ref="tm_3", away_ref="tm_1",
        home_name="C", away_name="A", goals=(1, 1),
        competition_ref="comp_2", league_id=2,
    )
    m3 = _match(
        ref="mt_12", kickoff=BASE + 2 * DAY, home_ref="tm_1", away_ref="tm_3",
        home_name="A", away_name="C", goals=(3, 1),
        competition_ref="comp_1", league_id=1,
    )
    row = _builder().build([m1, m2, m3]).rows[2]
    assert row.features["home_history_matches"] == 2
    assert row.features["home_comp_history_matches"] == 1
    assert row.features["home_venue_history_matches"] == 1
    assert row.features["home_goals_for_mean"] == pytest.approx(1.5)
    assert row.features["home_comp_goals_for_mean"] == pytest.approx(2.0)
    assert row.features["home_venue_goals_for_mean"] == pytest.approx(2.0)


def test_decision_horizon_is_part_of_dataset_identity() -> None:
    rows = _three_matches()
    a = _builder(horizon=6 * 3600).build(rows)
    b = _builder(horizon=12 * 3600).build(rows)
    assert a.manifest.manifest_hash != b.manifest.manifest_hash


def test_provider_contract_provenance_is_frozen_into_manifest() -> None:
    manifest = _builder().build(_three_matches()).manifest
    assert manifest.provider_contract_source_url.endswith("/llms.txt")
    assert len(manifest.provider_contract_source_sha256) == 64
    assert manifest.provider_contract_verified_on == "2026-10-01"


def test_artifact_rejects_noncanonical_byte_mutation(tmp_path: Path) -> None:
    artifact = _builder().build(_three_matches())
    result = write_immutable_dataset(
        root=tmp_path, manifest=artifact.manifest, rows=artifact.row_dicts()
    )
    rows_path = result.path / "rows.jsonl"
    # Semantic JSON is unchanged, but whitespace mutation must still be caught.
    rows_path.write_bytes(rows_path.read_bytes().replace(b'":', b'": ', 1))
    with pytest.raises(ValueError, match="rows byte hash"):
        verify_immutable_dataset(result.path)


def test_artifact_rejects_unexpected_extra_file(tmp_path: Path) -> None:
    artifact = _builder().build(_three_matches())
    result = write_immutable_dataset(
        root=tmp_path, manifest=artifact.manifest, rows=artifact.row_dicts()
    )
    (result.path / "unexpected.txt").write_text("mutation")
    with pytest.raises(ValueError, match="file set mismatch"):
        verify_immutable_dataset(result.path)


def test_failed_publish_does_not_use_partial_final_directory(tmp_path: Path) -> None:
    artifact = _builder().build(_three_matches())
    final = tmp_path / artifact.manifest.manifest_hash
    final.mkdir(parents=True)
    # A partial final artifact is treated as corruption, never overwritten.
    with pytest.raises((ValueError, FileNotFoundError, FileExistsError)):
        write_immutable_dataset(
            root=tmp_path, manifest=artifact.manifest, rows=artifact.row_dicts()
        )
    assert not (final / "rows.jsonl").exists()
