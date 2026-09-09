"""Regression tests locking in the data-driven-universe adversarial review.

See research/evaluation/prospective_universe_adversarial.md.
"""

from __future__ import annotations

import subprocess

import pytest

from src.research.prospective.coverage_matrix import CaptureClass, classify
from src.research.prospective.crosswalk import CrosswalkEntry, IdentityStatus, build_crosswalk
from src.research.prospective.recon import CompetitionCoverage


def _entry(status, cid=None, odds=None):
    return CrosswalkEntry(
        canonical_competition_id=("c1" if status == IdentityStatus.VERIFIED else None),
        canonical_name="X", country="C", footystats_id="1", footystats_name="X",
        thestatsapi_competition_id=cid, thestatsapi_name="X",
        identity_status=status, verification_method="t",
        odds_available=odds, xg_available=None, has_team_stats=None, has_player_stats=None)


def test_split_season_stays_ambiguous_and_unjoined():
    """Checks 1-7: split / multi-id competitions never auto-verify or auto-join."""
    cw = build_crosswalk()
    mx = next(e for e in cw if "Liga MX" in e.footystats_name)
    assert mx.identity_status == IdentityStatus.AMBIGUOUS
    assert mx.thestatsapi_competition_id is None
    assert len(mx.evidence["thestatsapi_competition_ids"]) == 2


def test_blocked_is_api_unsupported():
    cw = build_crosswalk()
    pl = next(e for e in cw if "Poland 1. Liga" in e.footystats_name)
    assert pl.identity_status == IdentityStatus.API_UNSUPPORTED


def test_no_fixtures_not_treated_as_unsupported():
    """Check 10: a VERIFIED league with 0 fixtures in scan is not disqualified."""
    e = _entry(IdentityStatus.VERIFIED, cid="comp_9", odds=True)
    cov = CompetitionCoverage(canonical_name="X", country="C",
                              thestatsapi_competition_id="comp_9",
                              scheduled_fixtures_in_scan=0, odds_endpoint_verified=None)
    row = classify(e, cov)
    assert row.capture_classification == CaptureClass.CAPTURE_PARTIAL


def test_odds_absent_on_one_fixture_not_unsupported():
    """Check 11: odds 404 on the probe fixture => PARTIAL, not insufficient."""
    e = _entry(IdentityStatus.VERIFIED, cid="comp_9", odds=True)
    cov = CompetitionCoverage(canonical_name="X", country="C",
                              thestatsapi_competition_id="comp_9",
                              scheduled_fixtures_in_scan=3, odds_endpoint_verified=False)
    assert classify(e, cov).capture_classification == CaptureClass.CAPTURE_PARTIAL


def test_unknown_odds_stays_unknown_not_false():
    """Check 25: registry odds UNKNOWN never becomes UNSUPPORTED."""
    e = _entry(IdentityStatus.VERIFIED, cid="comp_9", odds=None)
    row = classify(e, None)
    assert all(v == "UNKNOWN" for v in row.market_eligibility.values())


def test_dilution_structure_preserved_country_and_league():
    """Checks 23/24: every row retains league + country for future clustering."""
    cw = build_crosswalk()
    assert all(e.canonical_name for e in cw)
    assert all(("country" in e.to_dict()) for e in cw)


def test_no_key_material_in_artifacts():
    """Check 26: crosswalk/coverage artifacts contain no auth material."""
    for name in ("prospective_crosswalk.json", "prospective_coverage_matrix.json"):
        blob = open(f"research/evaluation/{name}").read().lower()
        assert "bearer" not in blob
        assert "authorization" not in blob


def test_champion_untouched_this_phase():
    """Check 29: champion model files unchanged vs main."""
    r = subprocess.run(
        ["git", "diff", "--stat", "main", "--", "src/research/models/",
         "src/research/calibration.py"],
        capture_output=True, text=True, cwd="/home/ubuntu")
    assert r.stdout.strip() == "", f"champion changed:\n{r.stdout}"
