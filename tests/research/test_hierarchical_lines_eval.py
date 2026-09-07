"""Tests for the walk-forward line evaluation.

What is being checked here is mostly discipline rather than arithmetic: that the
primary endpoint really is calibration, that every preregistered cell survives into
the report with a reason when it is insufficient, that the BH family is fresh and
covers exactly the valid cells, and that no arrangement of the output constitutes a
skill claim.
"""

from __future__ import annotations

import json

import pytest

from src.research.evaluation.hierarchical_lines import (
    SCHEMA_VERSION,
    VERDICT_CALIBRATED,
    VERDICT_INSUFFICIENT,
    VERDICT_MISCALIBRATED,
    HierarchicalEvalConfig,
    HierarchicalLineEvaluator,
    expected_calibration_error,
    reliability_curve,
)
from src.research.models.hierarchical_market_model import HierarchicalConfig
from src.research.models.market_family import family_by_name
from src.research.models.side_rows import build_fixture_rows

from tests.research.test_form_window import _match

CURRENT_SEASON = "9002"
PRIOR_SEASON = "9001"


def _corpus(n_rounds: int = 34, n_teams: int = 10) -> list[dict]:
    """A two-season synthetic league with enough rows to refit several times."""
    matches: list[dict] = []
    teams = [f"T{index}" for index in range(n_teams)]
    kickoff = 1_600_000_000
    for season in (PRIOR_SEASON, CURRENT_SEASON):
        for round_index in range(n_rounds):
            kickoff += 7 * 86_400
            for offset in range(n_teams // 2):
                home = teams[(round_index + offset) % n_teams]
                away = teams[(round_index + offset + n_teams // 2) % n_teams]
                if home == away:
                    continue
                # Goals must vary, or "both teams scored" is a constant and the
                # direct comparator correctly refuses to fit a degenerate label.
                seed = round_index * 7 + offset * 3
                match = _match(
                    season=season,
                    kickoff=kickoff + offset,
                    home=home,
                    away=away,
                    home_corners=float(4 + (round_index + offset) % 6),
                    away_corners=float(3 + (round_index * 2 + offset) % 5),
                )
                home_goals = seed % 4
                away_goals = (seed // 2) % 3
                match["homeGoalCount"] = home_goals
                match["awayGoalCount"] = away_goals
                match["ht_goals_team_a"] = home_goals // 2
                match["ht_goals_team_b"] = away_goals // 2
                match["team_a_shotsOnTarget"] = 3 + seed % 5
                match["team_b_shotsOnTarget"] = 2 + (seed // 3) % 5
                match["team_a_xg"] = 0.6 + (seed % 5) * 0.3
                match["team_b_xg"] = 0.5 + ((seed // 2) % 4) * 0.3
                matches.append(match)
    return matches


@pytest.fixture(scope="module")
def report():
    families = [family_by_name("corners"), family_by_name("goals")]
    fixtures = build_fixture_rows(_corpus(), families)
    config = HierarchicalEvalConfig(
        min_global_train=200,
        refit_every_kickoff_batches=20,
        min_league_train=40,
        min_cell_predictions=60,
        min_bootstrap_blocks=3,
        bootstrap_draws=120,
    )
    evaluator = HierarchicalLineEvaluator(
        config, model_config=HierarchicalConfig(min_global_observations=40)
    )
    return evaluator.evaluate(fixtures, families)


# ─────────────────────────────────────────────────────────────────────────────
# Monotonicity, checked on every scored fixture
# ─────────────────────────────────────────────────────────────────────────────
def test_no_monotonicity_violations_across_the_walk_forward(report) -> None:
    monotonicity = report["monotonicity"]
    assert monotonicity["fixtures_checked"] > 0
    assert monotonicity["violations"] == 0
    assert monotonicity["holds"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Calibration is the primary endpoint
# ─────────────────────────────────────────────────────────────────────────────
def test_primary_endpoint_is_calibration_not_a_skill_contrast(report) -> None:
    config = report["config"]
    assert config["primary_endpoint"] == "expected_calibration_error"
    assert "calibrated" in config["primary_hypothesis"]
    assert config["supporting_metrics"] == ["brier", "log_loss"]
    assert "unresolved" in config["skill_status"]


def test_every_tested_cell_reports_ece_and_a_reliability_curve(report) -> None:
    tested = [cell for cell in report["cells"] if cell["status"] == "tested"]
    assert tested, "expected at least one tested cell"
    for cell in tested:
        calibration = cell["calibration"]
        assert calibration is not None
        assert 0.0 <= calibration["ece"] <= 1.0
        assert calibration["bins"] == 10
        assert len(cell["reliability_curve"]) == 10
        assert sum(bin_["n"] for bin_ in cell["reliability_curve"]) == cell[
            "n_predictions"
        ]
        assert cell["supporting"]["brier"] is not None
        assert cell["supporting"]["log_loss"] is not None


def test_skill_is_reported_but_explicitly_unresolved(report) -> None:
    for cell in report["cells"]:
        assert cell["skill_claim_blocked"] is True
        if cell["status"] == "tested":
            skill = cell["skill_secondary"]
            assert skill["status"] == "reported_but_unresolved"
            assert "no skill claim" in skill["note"]
    assert report["governance"]["skill_claims"] == "blocked"


def test_ece_helper_is_zero_for_perfectly_calibrated_input() -> None:
    import numpy as np

    probabilities = np.array([0.25] * 400 + [0.75] * 400)
    outcomes = np.array([0.0] * 300 + [1.0] * 100 + [0.0] * 100 + [1.0] * 300)
    assert expected_calibration_error(probabilities, outcomes, 10) == pytest.approx(
        0.0, abs=1e-9
    )


def test_ece_helper_detects_gross_miscalibration() -> None:
    import numpy as np

    probabilities = np.array([0.9] * 200)
    outcomes = np.array([0.0] * 200)
    assert expected_calibration_error(probabilities, outcomes, 10) == pytest.approx(
        0.9, abs=1e-9
    )


def test_reliability_curve_bins_partition_the_sample() -> None:
    import numpy as np

    rng = np.random.default_rng(3)
    probabilities = rng.random(500)
    outcomes = (rng.random(500) < probabilities).astype(float)
    curve = reliability_curve(probabilities, outcomes, 10)
    assert sum(bin_["n"] for bin_ in curve) == 500


# ─────────────────────────────────────────────────────────────────────────────
# The FDR family
# ─────────────────────────────────────────────────────────────────────────────
def test_fdr_family_is_fresh_and_covers_exactly_the_valid_cells(report) -> None:
    governance = report["governance"]
    tested = [cell for cell in report["cells"] if cell["status"] == "tested"]
    assert governance["valid_family_size"] == len(tested)
    assert governance["fdr_method"] == "Benjamini-Hochberg step-up"
    assert governance["fdr_family_scope"].startswith("every league x market x line")
    assert governance["invalid_cells_retained"] is True
    for cell in report["cells"]:
        assert cell["fdr"]["family_size"] == governance["valid_family_size"]


def test_q_values_are_monotone_in_the_p_value_ranking(report) -> None:
    tested = [cell for cell in report["cells"] if cell["status"] == "tested"]
    ordered = sorted(tested, key=lambda cell: cell["fdr"]["rank"])
    q_values = [cell["fdr"]["q_value"] for cell in ordered]
    assert all(later >= earlier - 1e-12 for earlier, later in zip(q_values, q_values[1:]))
    for cell in ordered:
        assert 0.0 <= cell["fdr"]["raw_p"] <= 1.0
        assert 0.0 <= cell["fdr"]["q_value"] <= 1.0


def test_a_finding_means_miscalibration_detected(report) -> None:
    assert report["governance"]["finding_means"] == "miscalibration detected"
    for cell in report["cells"]:
        if cell["status"] != "tested":
            continue
        expected = (
            VERDICT_MISCALIBRATED if cell["fdr"]["reject"] else VERDICT_CALIBRATED
        )
        assert cell["verdict"] == expected


def test_insufficient_cells_are_retained_with_machine_readable_reasons(report) -> None:
    insufficient = [cell for cell in report["cells"] if cell["status"] == "insufficient"]
    for cell in insufficient:
        assert cell["verdict"] == VERDICT_INSUFFICIENT
        assert cell["insufficient_reasons"]
        for reason in cell["insufficient_reasons"]:
            assert reason.startswith(("no_walk_forward_predictions", "n_predictions<", "n_blocks<"))
        assert cell["calibration"] is None
        assert cell["fdr"]["reject"] is False


def test_every_preregistered_cell_appears_exactly_once(report) -> None:
    families = [family_by_name("corners"), family_by_name("goals")]
    leagues = {cell["league"] for cell in report["cells"]}
    expected = len(leagues) * sum(len(family.lines) for family in families)
    assert len(report["cells"]) == expected
    keys = [(cell["league"], cell["family"], cell["line"]) for cell in report["cells"]]
    assert len(set(keys)) == len(keys)


# ─────────────────────────────────────────────────────────────────────────────
# Per-league, never pooled-only
# ─────────────────────────────────────────────────────────────────────────────
def test_pooled_rows_are_flagged_as_never_substituting_for_per_league(report) -> None:
    pooled = report["pooled_rows"]
    assert pooled
    for row in pooled:
        assert row["league"] == "POOLED"
        if row["status"] == "tested":
            assert row["skill_claim_blocked"] is True
            assert "artifact" in row["note"]
    assert "artifact" in report["governance"]["pooled_only_positives"]


def test_cells_are_reported_per_league(report) -> None:
    assert all(cell["league"] != "POOLED" for cell in report["cells"])


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward discipline
# ─────────────────────────────────────────────────────────────────────────────
def test_walk_forward_is_expanding_and_batched(report) -> None:
    walk_forward = report["walk_forward"]
    assert walk_forward["fold_type"] == "expanding chronological"
    assert walk_forward["equal_kickoff_batches"] is True
    assert walk_forward["strict_train_before_score"] is True
    for diagnostics in walk_forward["family_diagnostics"]:
        assert diagnostics["n_folds"] >= 1
        assert diagnostics["prediction_failures"] == 0
        assert diagnostics["monotonicity_violations"] == 0


def test_preprocessing_is_declared_as_inside_the_training_fold(report) -> None:
    assert "inside the training fold" in report["config"]["preprocessing"]
    assert "training snapshot only" in report["config"]["climatology"]


def test_more_than_one_fold_is_produced(report) -> None:
    """A single-fold run would not be a walk-forward at all."""
    folds = [
        diagnostics["n_folds"]
        for diagnostics in report["walk_forward"]["family_diagnostics"]
    ]
    assert max(folds) > 1


def test_fit_reports_expose_the_selected_distribution_per_fold(report) -> None:
    assert report["fit_reports"]
    for fit in report["fit_reports"]:
        assert fit["fold_id"] >= 1
        assert fit["global"]["distribution"] in ("poisson", "negative_binomial")
        assert "residual_variance_mean_ratio" in fit["global"]
        assert fit["league_slope_shrinkage_cap"] <= 1.0


def test_window_support_is_recorded_per_cell(report) -> None:
    """A cell built mostly on shrunken windows must be identifiable as such."""
    for cell in report["cells"]:
        if cell["status"] != "tested":
            continue
        support = cell["window_support"]
        assert support["median_window_matches_used"] >= 1
        assert 0.0 <= support["share_shrunk_window"] <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# BTTS contrast
# ─────────────────────────────────────────────────────────────────────────────
def test_btts_derived_is_compared_against_a_direct_model(report) -> None:
    contrast = report["btts_contrast"]
    assert contrast["status"] == "tested"
    for arm in ("derived", "direct"):
        assert set(contrast[arm]) == {"ece", "brier", "log_loss"}
    assert "logistic regression" in contrast["direct_model"]
    assert isinstance(contrast["derived_kept"], bool)
    assert "underperforms" in contrast["decision_rule"]
    assert contrast["per_league"]


# ─────────────────────────────────────────────────────────────────────────────
# Report shape
# ─────────────────────────────────────────────────────────────────────────────
def test_report_is_json_serialisable_and_declares_its_schema(report) -> None:
    assert report["schema_version"] == SCHEMA_VERSION
    encoded = json.dumps(report)
    assert len(encoded) > 1000


def test_families_section_states_line_rationale_and_gaps(report) -> None:
    for family in report["families"]:
        assert family["line_rationale"]
        assert isinstance(family["unavailable_mechanisms"], list)
        assert isinstance(family["league_varying_slopes"], list)
        assert len(family["league_varying_slopes"]) <= 2


def test_config_rejects_an_unknown_bootstrap_block() -> None:
    with pytest.raises(ValueError, match="bootstrap_block"):
        HierarchicalEvalConfig(bootstrap_block="fixture")
