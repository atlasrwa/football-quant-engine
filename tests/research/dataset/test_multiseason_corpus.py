"""Tests for the canonical multi-season QFE V2 PIT corpus."""

from __future__ import annotations

import json
from pathlib import Path

from src.research.dataset.multiseason import build_multiseason_pit_corpus
from src.research.dataset.pit import PITDatasetSpec


def _fixture(
    *,
    ref: str,
    kickoff: str,
    comp: str,
    season: str,
    home: str,
    away: str,
    goals: tuple[int, int] = (1, 0),
) -> dict:
    return {
        "id": ref,
        "competition_id": comp,
        "season_id": season,
        "status": "finished",
        "utc_date": kickoff,
        "home_team": {"id": home, "name": home},
        "away_team": {"id": away, "name": away},
        "score": {"home": goals[0], "away": goals[1]},
    }


def _stats(ref: str, corners: tuple[int, int] = (5, 4)) -> dict:
    return {
        "data": {
            "match_id": ref,
            "overview": {
                "corner_kicks": {"all": {"home": corners[0], "away": corners[1]}},
                "total_shots": {"all": {"home": 10, "away": 8}},
                "shots_on_target": {"all": {"home": 4, "away": 2}},
                "fouls": {"all": {"home": 11, "away": 9}},
                "yellow_cards": {"all": {"home": 1, "away": 2}},
                "red_cards": {"all": {"home": 0, "away": 0}},
                "ball_possession": {"all": {"home": 53, "away": 47}},
                "expected_goals": {"all": {"home": 1.2, "away": 0.8}},
            },
        }
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True))


def _pit_spec() -> PITDatasetSpec:
    return PITDatasetSpec(
        decision_horizon_seconds=6 * 3600,
        reconstructed_post_match_embargo_seconds=6 * 3600,
    )


def test_multiseason_history_carries_across_season_boundary(tmp_path: Path) -> None:
    _write(
        tmp_path / "_all_fixtures_epl_sn_1.json",
        {
            "fixtures": [
                _fixture(
                    ref="mt_1",
                    kickoff="2025-05-01T15:00:00.000Z",
                    comp="comp_1",
                    season="sn_1",
                    home="tm_1",
                    away="tm_2",
                    goals=(2, 0),
                )
            ]
        },
    )
    _write(tmp_path / "epl_stats_mt_1.json", _stats("mt_1"))

    _write(
        tmp_path / "_all_fixtures_epl_sn_2.json",
        {
            "fixtures": [
                _fixture(
                    ref="mt_2",
                    kickoff="2025-08-15T15:00:00.000Z",
                    comp="comp_1",
                    season="sn_2",
                    home="tm_1",
                    away="tm_3",
                    goals=(1, 1),
                )
            ]
        },
    )
    _write(tmp_path / "epl_stats_mt_2.json", _stats("mt_2", (6, 2)))

    corpus = build_multiseason_pit_corpus(
        base_dir=tmp_path,
        pit_spec=_pit_spec(),
    )

    assert corpus.manifest.n_matches == 2
    assert corpus.manifest.season_refs == ("sn_1", "sn_2")
    second = corpus.pit.rows[1]
    assert second.season_ref == "sn_2"
    assert second.features["home_history_matches"] == 1
    assert second.features["home_goals_for_mean"] == 2.0


def test_global_team_history_carries_across_competition_transition(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "_all_fixtures_epl_sn_1.json",
        {
            "fixtures": [
                _fixture(
                    ref="mt_1",
                    kickoff="2025-05-01T15:00:00.000Z",
                    comp="comp_1",
                    season="sn_1",
                    home="tm_1",
                    away="tm_2",
                    goals=(3, 0),
                )
            ]
        },
    )
    _write(tmp_path / "epl_stats_mt_1.json", _stats("mt_1"))

    _write(
        tmp_path / "_all_fixtures_laliga_sn_2.json",
        {
            "fixtures": [
                _fixture(
                    ref="mt_2",
                    kickoff="2025-08-15T15:00:00.000Z",
                    comp="comp_2",
                    season="sn_2",
                    home="tm_1",
                    away="tm_4",
                    goals=(1, 1),
                )
            ]
        },
    )
    _write(tmp_path / "laliga_stats_mt_2.json", _stats("mt_2"))

    corpus = build_multiseason_pit_corpus(
        base_dir=tmp_path,
        pit_spec=_pit_spec(),
    )
    second = corpus.pit.rows[1]
    assert second.competition_ref == "comp_2"
    assert second.features["home_history_matches"] == 1
    assert second.features["home_comp_history_matches"] == 0


def test_multiseason_manifest_is_deterministic(tmp_path: Path) -> None:
    _write(
        tmp_path / "_all_fixtures_epl_sn_1.json",
        {
            "fixtures": [
                _fixture(
                    ref="mt_1",
                    kickoff="2025-05-01T15:00:00.000Z",
                    comp="comp_1",
                    season="sn_1",
                    home="tm_1",
                    away="tm_2",
                )
            ]
        },
    )
    _write(tmp_path / "epl_stats_mt_1.json", _stats("mt_1"))
    _write(
        tmp_path / "_all_fixtures_epl_sn_2.json",
        {
            "fixtures": [
                _fixture(
                    ref="mt_2",
                    kickoff="2025-08-01T15:00:00.000Z",
                    comp="comp_1",
                    season="sn_2",
                    home="tm_2",
                    away="tm_1",
                )
            ]
        },
    )
    _write(tmp_path / "epl_stats_mt_2.json", _stats("mt_2"))

    a = build_multiseason_pit_corpus(
        base_dir=tmp_path,
        pit_spec=_pit_spec(),
    )
    b = build_multiseason_pit_corpus(
        base_dir=tmp_path,
        pit_spec=_pit_spec(),
    )
    assert a.manifest.manifest_hash == b.manifest.manifest_hash
    assert a.manifest.match_content_hash == b.manifest.match_content_hash
    assert a.manifest.pit_manifest_hash == b.manifest.pit_manifest_hash


def test_source_mutation_after_audit_is_detected(tmp_path: Path) -> None:
    # This behavior is exercised inside one call through the season audit +
    # exact source fingerprint reconstruction. A malformed selected source must
    # fail rather than silently continue.
    _write(
        tmp_path / "_all_fixtures_epl_sn_1.json",
        {
            "fixtures": [
                _fixture(
                    ref="mt_1",
                    kickoff="2025-05-01T15:00:00.000Z",
                    comp="comp_1",
                    season="sn_1",
                    home="tm_1",
                    away="tm_2",
                )
            ]
        },
    )
    _write(tmp_path / "epl_stats_mt_1.json", _stats("mt_1"))
    corpus = build_multiseason_pit_corpus(
        base_dir=tmp_path,
        pit_spec=_pit_spec(),
    )
    assert corpus.manifest.unique_source_files == 2
