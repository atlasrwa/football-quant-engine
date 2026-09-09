"""Regression tests for the live-capture adversarial review.

Locks in the phase-specific attack vectors (see
research/evaluation/prospective_live_capture_adversarial.md).
"""

from __future__ import annotations

import subprocess

import pytest

from src.research.prospective.cli import _parse_utc
from src.research.prospective.quality import SchemaDriftError, validate_odds_schema

K = 1_700_000_000.0


def test_dst_offset_equivalence():
    """Check 19: a +02:00 timestamp equals the same instant in UTC."""
    assert abs(_parse_utc("2026-07-15T17:00:00+02:00") - _parse_utc("2026-07-15T15:00:00Z")) < 1e-6


def test_wrong_type_bookmakers_is_drift():
    """Check 24: a wrong-type critical field raises rather than normalizing."""
    with pytest.raises(SchemaDriftError):
        validate_odds_schema({"data": {"bookmakers": "oops"}})


def test_live_capture_data_gitignored():
    """Check 25: prospective capture data is git-ignored."""
    r = subprocess.run(
        ["git", "check-ignore", "data/prospective/captures.jsonl.gz"],
        capture_output=True, text=True, cwd="/home/ubuntu",
    )
    assert r.stdout.strip() != ""


def test_champion_untouched_this_phase():
    """Check 27: champion model files unchanged vs main."""
    r = subprocess.run(
        ["git", "diff", "--stat", "main", "--", "src/research/models/",
         "src/research/calibration.py"],
        capture_output=True, text=True, cwd="/home/ubuntu",
    )
    assert r.stdout.strip() == "", f"champion changed:\n{r.stdout}"
