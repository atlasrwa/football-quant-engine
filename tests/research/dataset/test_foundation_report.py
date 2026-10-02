"""Tests for Foundation V1 frozen audit bundle generation."""

from __future__ import annotations

import json
from pathlib import Path

from src.research.dataset.foundation_report import (
    FOUNDATION_AUDIT_VERSION,
    build_foundation_audit_bundle,
    write_frozen_foundation_audit,
)
from src.research.dataset.pit import PITDatasetSpec


def _fixture(ref: str, kickoff: str, home: str, away: str) -> dict:
    return {
        "id": ref,
        "competition_id": "comp_3039",
        "season_id": "sn_1",
        "status": "finished",
        "utc_date": kickoff,
        "home_team": {"id": home, "name": home},
        "away_team": {"id": away, "name": away},
        "score": {"home": 1, "away": 0},
    }


def _stats(ref: str) -> dict:
    return {
        "data": {
            "match_id": ref,
            "overview": {
                "corner_kicks": {"all": {"home": 5, "away": 4}},
                "total_shots": {"all": {"home": 11, "away": 8}},
                "shots_on_target": {"all": {"home": 4, "away": 3}},
                "fouls": {"all": {"home": 10, "away": 9}},
                "yellow_cards": {"all": {"home": 1, "away": 2}},
                "red_cards": {"all": {"home": 0, "away": 0}},
                "ball_possession": {"all": {"home": 52, "away": 48}},
                "expected_goals": {"all": {"home": 1.1, "away": 0.8}},
            },
        }
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True))


def test_foundation_bundle_aggregates_season_audit(tmp_path: Path) -> None:
    fixtures = [
        _fixture("mt_1", "2025-01-01T15:00:00.000Z", "tm_1", "tm_2"),
        _fixture("mt_2", "2025-01-08T15:00:00.000Z", "tm_2", "tm_1"),
    ]
    _write(tmp_path / "_all_fixtures_epl_sn_1.json", {"fixtures": fixtures})
    _write(tmp_path / "epl_stats_mt_1.json", _stats("mt_1"))
    _write(tmp_path / "epl_stats_mt_2.json", _stats("mt_2"))

    repo_root = Path(__file__).resolve().parents[3]
    bundle = build_foundation_audit_bundle(
        base_dir=tmp_path,
        repo_root=repo_root,
        pit_spec=PITDatasetSpec(decision_horizon_seconds=6 * 3600),
    )

    assert bundle.foundation_audit_version == FOUNDATION_AUDIT_VERSION
    assert bundle.aggregate["discovered_seasons"] == 1
    assert bundle.aggregate["audit_usable_seasons"] == 1
    assert bundle.aggregate["normalized_finished_matches"] == 2
    assert bundle.aggregate["canonical_stats_missing"] == 0
    assert bundle.aggregate["canonical_stats_conflicts"] == 0
    assert (
        bundle.aggregate["target_status_counts"]["goals_total_regulation"]["AVAILABLE"]
        == 2
    )
    assert len(bundle.bundle_hash) == 64
    assert bundle.implementation_files


def test_frozen_bundle_writer_is_immutable(tmp_path: Path) -> None:
    fixtures = [
        _fixture("mt_1", "2025-01-01T15:00:00.000Z", "tm_1", "tm_2")
    ]
    _write(tmp_path / "_all_fixtures_epl_sn_1.json", {"fixtures": fixtures})
    _write(tmp_path / "epl_stats_mt_1.json", _stats("mt_1"))

    repo_root = Path(__file__).resolve().parents[3]
    bundle = build_foundation_audit_bundle(
        base_dir=tmp_path,
        repo_root=repo_root,
        pit_spec=PITDatasetSpec(decision_horizon_seconds=6 * 3600),
    )

    json_path = tmp_path / "frozen.json"
    md_path = tmp_path / "frozen.md"
    write_frozen_foundation_audit(
        json_path=json_path,
        markdown_path=md_path,
        bundle=bundle,
    )
    write_frozen_foundation_audit(
        json_path=json_path,
        markdown_path=md_path,
        bundle=bundle,
    )

    json_path.write_text("{}\n")
    try:
        write_frozen_foundation_audit(
            json_path=json_path,
            markdown_path=md_path,
            bundle=bundle,
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("mutated frozen audit must not be overwritten")
