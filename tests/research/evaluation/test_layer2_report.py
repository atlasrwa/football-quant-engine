"""Tests for deterministic Layer 2 development evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.research.dataset.pit import PITDatasetSpec
from src.research.evaluation.layer2_report import (
    build_layer2_evidence,
    write_layer2_evidence,
)


def _fixture(ref: str, kickoff: str, home: str, away: str) -> dict:
    return {
        "id": ref,
        "competition_id": "comp_1",
        "season_id": "sn_1",
        "status": "finished",
        "utc_date": kickoff,
        "home_team": {"id": home, "name": home},
        "away_team": {"id": away, "name": away},
        "score": {"home": 2, "away": 1},
    }


def _stats(ref: str) -> dict:
    return {
        "data": {
            "match_id": ref,
            "overview": {
                "corner_kicks": {"all": {"home": 5, "away": 4}},
                "total_shots": {"all": {"home": 11, "away": 8}},
                "shots_on_target": {"all": {"home": 5, "away": 3}},
                "fouls": {"all": {"home": 10, "away": 9}},
                "yellow_cards": {"all": {"home": 1, "away": 1}},
                "red_cards": {"all": {"home": 0, "away": 0}},
                "ball_possession": {"all": {"home": 54, "away": 46}},
                "expected_goals": {"all": {"home": 1.5, "away": 0.8}},
            },
        }
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True))


def _corpus(tmp_path: Path) -> None:
    fixtures = [
        _fixture("mt_1", "2025-01-01T15:00:00.000Z", "tm_1", "tm_2"),
        _fixture("mt_2", "2025-01-08T15:00:00.000Z", "tm_2", "tm_1"),
    ]
    _write(tmp_path / "_all_fixtures_epl_sn_1.json", {"fixtures": fixtures})
    _write(tmp_path / "epl_stats_mt_1.json", _stats("mt_1"))
    _write(tmp_path / "epl_stats_mt_2.json", _stats("mt_2"))


def test_layer2_bundle_is_deterministic(tmp_path: Path) -> None:
    _corpus(tmp_path)
    repo_root = Path(__file__).resolve().parents[3]
    kwargs = dict(
        base_dir=tmp_path,
        repo_root=repo_root,
        pit_spec=PITDatasetSpec(decision_horizon_seconds=6 * 3600),
    )
    a = build_layer2_evidence(**kwargs)
    b = build_layer2_evidence(**kwargs)
    assert a.bundle_hash == b.bundle_hash
    assert a.version == "qfe-layer2-development-smoke-v2-pit-horizon"
    assert a.corpus_manifest.n_matches == 2
    assert {r.target for r in a.target_reports} == {"goals", "corners"}
    assert all(r.predictions == 2 for r in a.target_reports)
    assert all(r.usable_outcomes == 2 for r in a.target_reports)


def test_layer2_writer_refuses_mutation(tmp_path: Path) -> None:
    _corpus(tmp_path)
    repo_root = Path(__file__).resolve().parents[3]
    bundle = build_layer2_evidence(
        base_dir=tmp_path,
        repo_root=repo_root,
        pit_spec=PITDatasetSpec(decision_horizon_seconds=6 * 3600),
    )
    json_path = tmp_path / "layer2.json"
    md_path = tmp_path / "layer2.md"
    write_layer2_evidence(
        json_path=json_path,
        markdown_path=md_path,
        bundle=bundle,
    )
    write_layer2_evidence(
        json_path=json_path,
        markdown_path=md_path,
        bundle=bundle,
    )
    json_path.write_text("{}\n")
    with pytest.raises(FileExistsError):
        write_layer2_evidence(
            json_path=json_path,
            markdown_path=md_path,
            bundle=bundle,
        )


def test_scientific_status_is_explicitly_nonpromotional(tmp_path: Path) -> None:
    _corpus(tmp_path)
    repo_root = Path(__file__).resolve().parents[3]
    bundle = build_layer2_evidence(
        base_dir=tmp_path,
        repo_root=repo_root,
        pit_spec=PITDatasetSpec(decision_horizon_seconds=6 * 3600),
    )
    assert "NOT_PROMOTED" in bundle.scientific_status
    assert "NO_MARKET_COMPARISON" in bundle.scientific_status
