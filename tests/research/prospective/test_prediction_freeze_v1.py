from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.research.data_source import ResearchMatch
from src.research.dataset.manifest import sha256_json
from src.research.prospective.prediction_freeze import (
    BASE_CORPUS_MANIFEST_HASH,
    COMPETITION_UNIVERSE,
    _validate_inputs,
    blank_target_from_match,
    write_prospective_prediction_bundle,
)


def _target(*, kickoff=2_000_000, goals=None):
    return ResearchMatch(
        match_id=123,
        date_unix=kickoff,
        league_id=256,
        season="sn_test",
        home_team="Home",
        away_team="Away",
        source_provider="THESTATSAPI",
        source_match_ref="mt_123",
        competition_ref="comp_0256",
        season_ref="sn_test",
        home_team_ref="tm_home",
        away_team_ref="tm_away",
        home_goals=goals,
    )


def _cohort(target, *, frozen_at=None):
    cutoff=target.date_unix-21600
    frozen_at=frozen_at or datetime.fromtimestamp(cutoff-1,timezone.utc).isoformat()
    base={
        "version":"qfe-prospective-cohort-v1",
        "status":"FROZEN_OUTCOME_BLIND",
        "frozen_at":frozen_at,
        "fixtures":[{"fixture_id":target.source_match_ref,"event_time":float(target.date_unix)}],
    }
    return {**base,"cohort_hash":sha256_json(base)}


def test_blank_target_strips_post_match_evidence():
    full=_target(goals=2)
    blank=blank_target_from_match(full)
    assert blank.home_goals is None
    assert blank.away_goals is None
    assert blank.corners_home is None
    assert blank.source_match_ref==full.source_match_ref
    assert blank.home_team_ref==full.home_team_ref


def test_target_with_outcome_field_fails_closed():
    target=_target(goals=1)
    with pytest.raises(ValueError,match="non-identity evidence"):
        _validate_inputs(
            target=target,
            history=(),
            cohort_manifest=_cohort(target),
            history_snapshot_hash="incremental",
            history_snapshot_captured_at=target.date_unix-21600,
            history_snapshot_competitions=COMPETITION_UNIVERSE,
        )


def test_target_not_in_frozen_cohort_fails_closed():
    target=_target()
    other=ResearchMatch(
        match_id=999,date_unix=target.date_unix,league_id=256,season="sn_test",
        home_team="X",away_team="Y",source_provider="THESTATSAPI",
        source_match_ref="mt_999",competition_ref="comp_0256",season_ref="sn_test",
        home_team_ref="tm_x",away_team_ref="tm_y",
    )
    with pytest.raises(ValueError,match="not present"):
        _validate_inputs(
            target=target,
            history=(),
            cohort_manifest=_cohort(other),
            history_snapshot_hash="incremental",
            history_snapshot_captured_at=target.date_unix-21600,
            history_snapshot_competitions=COMPETITION_UNIVERSE,
        )


def test_stale_canonical_history_fails_for_post_base_target():
    target=_target(kickoff=1_800_000_000)
    with pytest.raises(ValueError,match="stale canonical history"):
        _validate_inputs(
            target=target,
            history=(),
            cohort_manifest=_cohort(target),
            history_snapshot_hash=BASE_CORPUS_MANIFEST_HASH,
            history_snapshot_captured_at=target.date_unix-21600,
            history_snapshot_competitions=COMPETITION_UNIVERSE,
        )


def test_history_snapshot_must_cover_full_frozen_universe():
    target=_target()
    with pytest.raises(ValueError,match="complete frozen competition universe"):
        _validate_inputs(
            target=target,
            history=(),
            cohort_manifest=_cohort(target),
            history_snapshot_hash="incremental",
            history_snapshot_captured_at=target.date_unix-21600,
            history_snapshot_competitions=("comp_0256",),
        )


def test_history_snapshot_cannot_be_captured_after_cutoff():
    target=_target()
    cutoff=target.date_unix-21600
    with pytest.raises(ValueError,match="after target T-6h"):
        _validate_inputs(
            target=target,
            history=(),
            cohort_manifest=_cohort(target),
            history_snapshot_hash="incremental",
            history_snapshot_captured_at=cutoff+1,
            history_snapshot_competitions=COMPETITION_UNIVERSE,
        )


def test_writer_is_immutable(tmp_path: Path):
    bundle={"version":"x","bundle_hash":"h","rows":[]}
    path=tmp_path/"prediction.json"
    write_prospective_prediction_bundle(path,bundle)
    before=path.read_bytes()
    write_prospective_prediction_bundle(path,bundle)
    assert path.read_bytes()==before
    path.write_text("{}\n")
    with pytest.raises(FileExistsError):
        write_prospective_prediction_bundle(path,bundle)


def test_writer_signature_has_no_market_or_outcome_inputs():
    import inspect
    from src.research.prospective.prediction_freeze import build_prospective_prediction_bundle
    names=set(inspect.signature(build_prospective_prediction_bundle).parameters)
    assert not any("market" in x.lower() or "odds" in x.lower() or "outcome" in x.lower() or "score" in x.lower() for x in names)
