"""Tests for the provider comparison experiment infrastructure.

Covers: fair-comparison guard, PIT exclusion, provider isolation, NULL
semantics, no-max reconciliation in the bridge, odds validity, paired
identical-key comparison, and determinism. Uses the cached EPL corpus; skips
cleanly if absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_CORPUS = Path("data/mapping/team_crosswalk.json")
pytestmark = pytest.mark.skipif(
    not _CORPUS.exists(), reason="provider comparison corpus not present"
)

from src.research.experiments.provider_comparison.bridge import (  # noqa: E402
    build_provider_matches,
    make_reconciler,
    _reconcile_value,
)
from src.research.experiments.provider_comparison.bootstrap import (  # noqa: E402
    _aligned_fixture_losses,
    paired_block_bootstrap,
)
from src.research.experiments.provider_comparison.dataset import (  # noqa: E402
    _num,
    build_epl_paired_dataset,
)
from src.research.experiments.provider_comparison.identity_setup import (  # noqa: E402
    load_high_confidence_team_registry,
)
from src.research.experiments.provider_comparison.market import _valid_odds  # noqa: E402
from src.research.experiments.provider_comparison.pit import is_prior_fixture  # noqa: E402
from src.research.experiments.provider_comparison.walkforward import (  # noqa: E402
    Prediction,
    run_walk_forward,
)


@pytest.fixture(scope="module")
def paired():
    _, _, n2t = load_high_confidence_team_registry(
        min_confidence=0.9, leagues=["England Premier League"]
    )
    fixtures, _ = build_epl_paired_dataset(n2t["England Premier League"])
    return fixtures


class TestIdentity:
    def test_only_high_confidence_admitted(self):
        _, rep, n2t = load_high_confidence_team_registry(
            min_confidence=0.9, leagues=["England Premier League"]
        )
        # Known-wrong fuzzy maps must be excluded.
        admitted = set(n2t["England Premier League"])
        assert "Leicester City" not in admitted
        assert "West Ham United" not in admitted
        assert rep.excluded_low_confidence >= 2


class TestDataset:
    def test_join_score_agreement(self, paired):
        assert len(paired) > 300
        assert all(f.score_agreement for f in paired)  # 100% score agreement

    def test_null_not_zero(self):
        assert _num(None) is None
        assert _num(0) == 0.0        # genuine zero preserved
        assert _num(True) is None    # bool rejected
        assert _num("x") is None


class TestPIT:
    def test_only_strictly_prior_fixtures(self):
        assert is_prior_fixture(100, 200) is True
        assert is_prior_fixture(200, 200) is False   # same kickoff excluded
        assert is_prior_fixture(300, 200) is False   # future excluded


class TestProviderIsolation:
    def test_identical_fixtures_outcomes_only_features_differ(self, paired):
        fs = build_provider_matches(paired, "footystats_only")
        tsa = build_provider_matches(paired, "thestatsapi_only")
        assert len(fs) == len(tsa)
        # identical identity/date/outcome across arms
        for a, b in zip(fs, tsa):
            assert (a["homeID"], a["awayID"], a["date_unix"]) == (b["homeID"], b["awayID"], b["date_unix"])
            assert a["totalCornerCount"] == b["totalCornerCount"]
        # but SOME feature values differ (providers disagree on shots)
        assert any(a["team_a_shots"] != b["team_a_shots"] for a, b in zip(fs, tsa))

    def test_fs_only_features_gated(self, paired):
        base = build_provider_matches(paired, "footystats_only", include_fs_only_features=False)
        ext = build_provider_matches(paired, "footystats_only", include_fs_only_features=True)
        assert "team_a_dangerous_attacks" not in base[0]
        assert "team_a_dangerous_attacks" in ext[0]


class TestNoMaxReconciliation:
    def test_bridge_never_selects_max(self):
        # THESTATSAPI_ONLY must return the TSA value even when it is SMALLER.
        r = make_reconciler("thestatsapi_only")
        assert _reconcile_value(r, fs_val=9.9, tsa_val=1.1) == 1.1
        # FOOTYSTATS_ONLY returns FS value even when smaller.
        r2 = make_reconciler("footystats_only")
        assert _reconcile_value(r2, fs_val=1.1, tsa_val=9.9) == 1.1

    def test_none_not_coerced_to_zero(self):
        r = make_reconciler("footystats_only")
        # FS absent under FS-only policy -> None, never 0.
        assert _reconcile_value(r, fs_val=None, tsa_val=5.0) is None


class TestOddsValidity:
    def test_valid_odds_rejects_non_positive_book(self):
        assert _valid_odds(0) is None      # 0 = market not available
        assert _valid_odds(1.0) is None    # <=1.0 invalid
        assert _valid_odds(0.5) is None
        assert _valid_odds("x") is None
        assert _valid_odds(1.8) == 1.8


class TestPairedIdenticalKey:
    def test_bootstrap_aligns_on_pair_key(self):
        # Two arms sharing keys A,B; arm_b also has extra key C (must be ignored).
        a = [
            Prediction(1, 100, "M", 9.5, 0.6, True, "L", "S"),
            Prediction(2, 200, "M", 9.5, 0.4, False, "L", "S"),
        ]
        b = [
            Prediction(1, 100, "M", 9.5, 0.7, True, "L", "S"),
            Prediction(2, 200, "M", 9.5, 0.3, False, "L", "S"),
            Prediction(3, 300, "M", 9.5, 0.9, True, "L", "S"),  # unmatched
        ]
        keys, diffs = _aligned_fixture_losses(a, b, "brier", collapse_lines=True)
        assert keys == [1, 2]  # only common fixtures, chronological


class TestDeterminism:
    def test_walk_forward_deterministic(self, paired):
        r1 = run_walk_forward(paired, policy="footystats_only", market="CORNERS_TOTAL", arm="pooled")
        r2 = run_walk_forward(paired, policy="footystats_only", market="CORNERS_TOTAL", arm="pooled")
        assert [(p.pair_key, round(p.prob_over, 10)) for p in r1.predictions] == \
               [(p.pair_key, round(p.prob_over, 10)) for p in r2.predictions]

    def test_bootstrap_deterministic(self, paired):
        r = run_walk_forward(paired, policy="footystats_only", market="CORNERS_TOTAL", arm="pooled")
        r2 = run_walk_forward(paired, policy="thestatsapi_only", market="CORNERS_TOTAL", arm="pooled")
        b1 = paired_block_bootstrap(r.predictions, r2.predictions, arm_a="a", arm_b="b", seed=7)
        b2 = paired_block_bootstrap(r.predictions, r2.predictions, arm_a="a", arm_b="b", seed=7)
        assert b1.observed_diff == b2.observed_diff
        assert (b1.ci_low, b1.ci_high, b1.prob_a_better) == (b2.ci_low, b2.ci_high, b2.prob_a_better)
