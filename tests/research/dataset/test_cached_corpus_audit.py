"""Adversarial tests for the QFE V2 cached-corpus audit layer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.research.dataset.audit import (
    CachedCorpusSpec,
    audit_cached_corpus,
    discover_cached_seasons,
    inspect_global_stats_aliases,
    write_audit_report,
)
from src.research.dataset.pit import PITDatasetSpec


def _fixture(
    *,
    ref: str = "mt_1",
    kickoff: str = "2025-01-01T15:00:00.000Z",
    comp: str = "comp_3039",
    season: str = "sn_1",
    home: str = "tm_1",
    away: str = "tm_2",
    status: str = "finished",
    score: tuple[int, int] = (1, 0),
) -> dict:
    return {
        "id": ref,
        "competition_id": comp,
        "season_id": season,
        "status": status,
        "utc_date": kickoff,
        "home_team": {"id": home, "name": f"Home-{home}"},
        "away_team": {"id": away, "name": f"Away-{away}"},
        "score": {"home": score[0], "away": score[1]},
    }


def _stats(
    *,
    ref: str = "mt_1",
    corners: tuple[int, int] = (5, 3),
    shots: tuple[int, int] = (10, 7),
) -> dict:
    return {
        "data": {
            "match_id": ref,
            "overview": {
                "corner_kicks": {"all": {"home": corners[0], "away": corners[1]}},
                "total_shots": {"all": {"home": shots[0], "away": shots[1]}},
                "shots_on_target": {"all": {"home": 4, "away": 2}},
                "fouls": {"all": {"home": 11, "away": 9}},
                "yellow_cards": {"all": {"home": 1, "away": 2}},
                "red_cards": {"all": {"home": 0, "away": 0}},
                "ball_possession": {"all": {"home": 55, "away": 45}},
                "expected_goals": {"all": {"home": 1.3, "away": 0.7}},
            },
        }
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True))


def _write_fixture_file(
    base: Path,
    name: str,
    fixtures: list[dict],
) -> None:
    _write(base / name, {"fixtures": fixtures})


def _spec() -> PITDatasetSpec:
    return PITDatasetSpec(
        decision_horizon_seconds=6 * 3600,
        reconstructed_post_match_embargo_seconds=6 * 3600,
    )


def test_discovery_maps_canonical_fixture_family_to_stats_family(
    tmp_path: Path,
) -> None:
    _write_fixture_file(
        tmp_path,
        "_all_fixtures_epl_sn_1.json",
        [_fixture()],
    )
    _write_fixture_file(
        tmp_path,
        "_all_fixtures_sn_2.json",
        [_fixture(comp="comp_8321", season="sn_2")],
    )
    found = {
        row.fixture_file: row
        for row in discover_cached_seasons(tmp_path)
    }
    assert found["_all_fixtures_epl_sn_1.json"].stats_glob == "epl_stats_mt_*.json"
    assert found["_all_fixtures_sn_2.json"].stats_glob == "stats_mt_*.json"
    assert all(row.usable_for_audit for row in found.values())


def test_discovery_blocks_empty_or_multi_season_fixture_file(
    tmp_path: Path,
) -> None:
    _write_fixture_file(tmp_path, "_all_fixtures_epl_sn_1.json", [])
    _write_fixture_file(
        tmp_path,
        "_all_fixtures_laliga_sn_mixed.json",
        [
            _fixture(ref="mt_1", season="sn_1"),
            _fixture(ref="mt_2", season="sn_2"),
        ],
    )
    found = {
        row.fixture_file: row
        for row in discover_cached_seasons(tmp_path)
    }
    assert found["_all_fixtures_epl_sn_1.json"].usable_for_audit is False
    assert "fixture_file_empty" in found["_all_fixtures_epl_sn_1.json"].blocking_anomalies
    assert found["_all_fixtures_laliga_sn_mixed.json"].usable_for_audit is False
    assert (
        "fixture_file_not_single_season"
        in found["_all_fixtures_laliga_sn_mixed.json"].blocking_anomalies
    )


def test_unrelated_stats_file_cannot_change_frozen_season_report(
    tmp_path: Path,
) -> None:
    fixture_name = "_all_fixtures_epl_sn_1.json"
    _write_fixture_file(tmp_path, fixture_name, [_fixture()])
    _write(tmp_path / "epl_stats_mt_1.json", _stats())

    spec = CachedCorpusSpec(
        label="comp_3039:sn_1",
        fixture_files=(fixture_name,),
        stats_globs=("epl_stats_mt_*.json",),
    )
    first = audit_cached_corpus(
        base_dir=tmp_path,
        corpus_spec=spec,
        pit_spec=_spec(),
    )

    # Same prefix, different season/match. It must not enter source_files or
    # change the season report.
    _write(
        tmp_path / "epl_stats_mt_999.json",
        _stats(ref="mt_999", corners=(99, 99)),
    )
    second = audit_cached_corpus(
        base_dir=tmp_path,
        corpus_spec=spec,
        pit_spec=_spec(),
    )

    assert first.report_hash == second.report_hash
    assert {row.relative_path for row in first.source_files} == {
        fixture_name,
        "epl_stats_mt_1.json",
    }
    assert first.source_root_id == "cache://thestatsapi/championship"


def test_identical_stats_duplicates_are_reported_and_deterministic(
    tmp_path: Path,
) -> None:
    fixture_name = "_all_fixtures_epl_sn_1.json"
    _write_fixture_file(tmp_path, fixture_name, [_fixture()])
    payload = _stats()
    _write(tmp_path / "epl_stats_mt_1_a.json", payload)
    _write(tmp_path / "epl_stats_mt_1_b.json", payload)

    report = audit_cached_corpus(
        base_dir=tmp_path,
        corpus_spec=CachedCorpusSpec(
            label="comp_3039:sn_1",
            fixture_files=(fixture_name,),
            stats_globs=("epl_stats_mt_*.json",),
        ),
        pit_spec=_spec(),
    )

    assert report.audit_usable is True
    assert report.stats_identical_duplicate_refs == ("mt_1",)
    assert report.stats_conflicting_match_refs == ()
    assert report.stats_payloads_selected == 1
    assert "epl_stats_mt_1_a.json" in {
        row.relative_path for row in report.source_files
    }
    assert "epl_stats_mt_1_b.json" not in {
        row.relative_path for row in report.source_files
    }


def test_conflicting_stats_duplicates_block_audit_and_fail_closed(
    tmp_path: Path,
) -> None:
    fixture_name = "_all_fixtures_epl_sn_1.json"
    _write_fixture_file(tmp_path, fixture_name, [_fixture()])
    _write(tmp_path / "epl_stats_mt_1_a.json", _stats(corners=(5, 3)))
    _write(tmp_path / "epl_stats_mt_1_b.json", _stats(corners=(8, 1)))

    report = audit_cached_corpus(
        base_dir=tmp_path,
        corpus_spec=CachedCorpusSpec(
            label="comp_3039:sn_1",
            fixture_files=(fixture_name,),
            stats_globs=("epl_stats_mt_*.json",),
        ),
        pit_spec=_spec(),
    )

    assert report.audit_usable is False
    assert report.stats_conflicting_match_refs == ("mt_1",)
    assert "conflicting_stats_payloads" in report.blocking_anomalies
    assert report.stats_payloads_selected == 0
    assert (
        report.target_status_counts["corners_total_regulation"]["SOURCE_MISSING"]
        == 1
    )


def test_missing_stats_is_coverage_loss_not_identity_failure(
    tmp_path: Path,
) -> None:
    fixture_name = "_all_fixtures_epl_sn_1.json"
    _write_fixture_file(
        tmp_path,
        fixture_name,
        [
            _fixture(ref="mt_1"),
            _fixture(
                ref="mt_2",
                kickoff="2025-01-08T15:00:00.000Z",
                home="tm_2",
                away="tm_1",
            ),
        ],
    )
    _write(tmp_path / "epl_stats_mt_1.json", _stats(ref="mt_1"))

    report = audit_cached_corpus(
        base_dir=tmp_path,
        corpus_spec=CachedCorpusSpec(
            label="comp_3039:sn_1",
            fixture_files=(fixture_name,),
            stats_globs=("epl_stats_mt_*.json",),
        ),
        pit_spec=_spec(),
    )
    assert report.audit_usable is True
    assert report.stats_missing_match_refs == ("mt_2",)
    assert report.stats_join_rate == pytest.approx(0.5)
    assert report.normalized_match_count == 2
    assert (
        report.target_status_counts["corners_total_regulation"]["SOURCE_MISSING"]
        == 1
    )


def test_duplicate_fixture_ref_blocks_audit(tmp_path: Path) -> None:
    fixture_name = "_all_fixtures_epl_sn_1.json"
    _write_fixture_file(
        tmp_path,
        fixture_name,
        [_fixture(), _fixture()],
    )
    _write(tmp_path / "epl_stats_mt_1.json", _stats())
    with pytest.raises(Exception):
        # PIT builder itself refuses duplicate stable fixture identity. This is
        # stronger than merely reporting it.
        audit_cached_corpus(
            base_dir=tmp_path,
            corpus_spec=CachedCorpusSpec(
                label="comp_3039:sn_1",
                fixture_files=(fixture_name,),
                stats_globs=("epl_stats_mt_*.json",),
            ),
            pit_spec=_spec(),
        )


def test_global_alias_audit_distinguishes_identical_and_conflicting(
    tmp_path: Path,
) -> None:
    same = _stats(ref="mt_1")
    _write(tmp_path / "a_stats_mt_1.json", same)
    _write(tmp_path / "b_stats_mt_1.json", same)
    _write(tmp_path / "a_stats_mt_2.json", _stats(ref="mt_2", corners=(1, 2)))
    _write(tmp_path / "b_stats_mt_2.json", _stats(ref="mt_2", corners=(9, 9)))

    result = inspect_global_stats_aliases(tmp_path)
    assert result.identical_duplicate_refs == ("mt_1",)
    assert result.conflicting_duplicate_refs == ("mt_2",)


def test_write_audit_report_is_immutable(tmp_path: Path) -> None:
    fixture_name = "_all_fixtures_epl_sn_1.json"
    _write_fixture_file(tmp_path, fixture_name, [_fixture()])
    _write(tmp_path / "epl_stats_mt_1.json", _stats())
    report = audit_cached_corpus(
        base_dir=tmp_path,
        corpus_spec=CachedCorpusSpec(
            label="comp_3039:sn_1",
            fixture_files=(fixture_name,),
            stats_globs=("epl_stats_mt_*.json",),
        ),
        pit_spec=_spec(),
    )
    path = tmp_path / "audit.json"
    write_audit_report(path, report)
    write_audit_report(path, report)

    path.write_text("{}\n")
    with pytest.raises(FileExistsError):
        write_audit_report(path, report)


def test_history_support_is_reported(tmp_path: Path) -> None:
    fixture_name = "_all_fixtures_epl_sn_1.json"
    fixtures = [
        _fixture(ref="mt_1"),
        _fixture(
            ref="mt_2",
            kickoff="2025-01-08T15:00:00.000Z",
            home="tm_2",
            away="tm_1",
        ),
        _fixture(
            ref="mt_3",
            kickoff="2025-01-15T15:00:00.000Z",
            home="tm_1",
            away="tm_2",
        ),
    ]
    _write_fixture_file(tmp_path, fixture_name, fixtures)
    for ref in ("mt_1", "mt_2", "mt_3"):
        _write(tmp_path / f"epl_stats_{ref}.json", _stats(ref=ref))

    report = audit_cached_corpus(
        base_dir=tmp_path,
        corpus_spec=CachedCorpusSpec(
            label="comp_3039:sn_1",
            fixture_files=(fixture_name,),
            stats_globs=("epl_stats_mt_*.json",),
        ),
        pit_spec=_spec(),
    )
    assert report.history_support.thresholds["0"] == 3
    assert report.history_support.thresholds["1"] == 2
    assert report.history_support.median_support == 1.0
