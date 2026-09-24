from pathlib import Path

from research.target_aware_market_panel import run_support_diagnostics_v1_2 as R


def test_runner_is_bound_to_frozen_plan_hash():
    assert not R.PLAN_SHA256.startswith("__")
    assert R.PLAN_SHA256 == R.fsha(R.SUPPORT_PLAN)
    src = Path(
        "research/target_aware_market_panel/run_support_diagnostics_v1_2.py"
    ).read_text()
    assert 'raise SystemExit("SUPPORT_PLAN_SHA_NOT_PINNED")' in src


def test_runner_keeps_v1_scoring_population_and_threshold():
    assert R.EXPECTED_PANEL_ROWS == 5620
    assert R.EXPECTED_FOLD_ROWS_SHA256 == (
        "9fca0ec2860ed13cda0368502978445b9444419eece690cba685449c26bf3270"
    )
    assert R.S12.COVERAGE_THRESHOLD == 0.60
    src = Path(
        "research/target_aware_market_panel/run_support_diagnostics_v1_2.py"
    ).read_text()
    assert "hm = base_history.get(fr[\"match_id\"])" in src
    assert "PN.PanelHistory(PN.rows_from_history(history), panel_end)" in src


def test_runner_has_no_predictive_or_market_execution_surface():
    src = Path(
        "research/target_aware_market_panel/run_support_diagnostics_v1_2.py"
    ).read_text()
    for forbidden in (
        "/odds", "/lineups", "/injuries", "LogLoss", "brier_score_loss",
        "CalibratedClassifier", ".fit(", ".predict(", "settle_target",
    ):
        assert forbidden not in src
    assert '"target_outcomes_read": False' in src
    assert '"market_results_read": False' in src
    assert '"model_fit": False' in src
    assert '"oos_executed": False' in src


def test_runner_outputs_explicit_gate_before_any_next_stage():
    assert R.OUTPUTS == (
        "SOL_PANEL_SUPPORT_DIAGNOSTICS_V1_2.json",
        "SOL_PANEL_SUPPORT_AUDIT_V1_2.md",
        "V1_2_EVALUABILITY_GATE_DECISION_V1.json",
        "SOL_PANEL_SUPPORT_FREEZE_MANIFEST_V1_2.json",
    )


def test_runner_verifies_frozen_semantic_module_hashes_and_template_hash():
    src = Path(
        "research/target_aware_market_panel/run_support_diagnostics_v1_2.py"
    ).read_text()
    assert "SUPPORT_RUNNER_TEMPLATE_HASH_MISMATCH" in src
    assert "SEMANTIC_MODULE_HASH_MISMATCH" in src
    import json
    assert 'plan["semantic_module_sha256"]' in src
    plan = json.loads(R.SUPPORT_PLAN.read_text())
    assert R.normalized_self_template_sha256() == plan["support_runner_template_sha256"]
