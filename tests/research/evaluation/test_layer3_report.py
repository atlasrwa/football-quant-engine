from dataclasses import replace
from pathlib import Path

import pytest

from src.research.data_source import ResearchMatch
from src.research.dataset.multiseason import MultiSeasonCorpusManifest
from src.research.evaluation.chronology import WARMUP_END_TS, build_chronology_manifest
from src.research.evaluation.layer3_report import (
    build_layer3_structured_evidence,
    write_layer3_structured_evidence,
)
from src.research.evaluation.model_tournament import run_layer3_development_tournament


def _match(ref: int, kickoff: int) -> ResearchMatch:
    return ResearchMatch(
        match_id=ref,
        date_unix=kickoff,
        league_id=1,
        season="sn_1",
        home_team="A",
        away_team="B",
        source_provider="THESTATSAPI",
        source_match_ref=f"mt_{ref}",
        competition_ref="comp_1",
        season_ref="sn_1",
        home_team_ref=f"tm_{1 + ref % 4}",
        away_team_ref=f"tm_{5 + ref % 4}",
        home_team_id=1 + ref % 4,
        away_team_id=5 + ref % 4,
        home_goals=2,
        away_goals=1,
        corners_home=6,
        corners_away=4,
    )


def _fixture_set():
    rows = [
        _match(i + 1, WARMUP_END_TS - (30 - i) * 86400)
        for i in range(30)
    ]
    rows.extend(
        _match(31 + i, WARMUP_END_TS + (i + 1) * 86400)
        for i in range(30)
    )
    return rows


def _manifest() -> MultiSeasonCorpusManifest:
    return MultiSeasonCorpusManifest(
        version="test",
        source_root_id="test",
        season_audit_hashes=(),
        unique_source_files=0,
        unique_source_bundle_hash="x",
        competition_refs=("comp_1",),
        season_refs=("sn_1",),
        n_matches=60,
        first_kickoff_ts=1,
        last_kickoff_ts=2,
        match_content_hash="m",
        pit_manifest_hash="p",
        decision_horizon_seconds=21600,
    )


def test_layer3_evidence_rejects_any_protected_scoring(tmp_path: Path) -> None:
    rows = _fixture_set()
    manifest = _manifest()
    chronology = build_chronology_manifest(
        matches=rows,
        corpus_manifest_hash=manifest.manifest_hash,
    )
    tournament, _ = run_layer3_development_tournament(
        matches=rows,
        corpus_manifest_hash=manifest.manifest_hash,
        chronology=chronology,
    )
    bad = replace(tournament, protected_rows_scored=1)
    with pytest.raises(ValueError, match="protected"):
        build_layer3_structured_evidence(
            repo_root=Path(__file__).resolve().parents[3],
            corpus_manifest=manifest,
            chronology=chronology,
            tournament=bad,
        )


def test_layer3_evidence_writer_is_immutable(tmp_path: Path) -> None:
    rows = _fixture_set()
    manifest = _manifest()
    chronology = build_chronology_manifest(
        matches=rows,
        corpus_manifest_hash=manifest.manifest_hash,
    )
    tournament, oof = run_layer3_development_tournament(
        matches=rows,
        corpus_manifest_hash=manifest.manifest_hash,
        chronology=chronology,
    )
    evidence = build_layer3_structured_evidence(
        repo_root=Path(__file__).resolve().parents[3],
        corpus_manifest=manifest,
        chronology=chronology,
        tournament=tournament,
    )
    json_path = tmp_path / "report.json"
    md_path = tmp_path / "report.md"
    goals_path = tmp_path / "goals.jsonl"
    corners_path = tmp_path / "corners.jsonl"
    kwargs = dict(
        json_path=json_path,
        markdown_path=md_path,
        evidence=evidence,
        goals_oof_path=goals_path,
        goals_oof=oof["goals"],
        corners_oof_path=corners_path,
        corners_oof=oof["corners"],
    )
    write_layer3_structured_evidence(**kwargs)
    write_layer3_structured_evidence(**kwargs)
    json_path.write_text("{}\n")
    with pytest.raises(FileExistsError):
        write_layer3_structured_evidence(**kwargs)
