from pathlib import Path

from research.target_aware_market_panel import v1_2_1_make_support_plan as P


def test_v1_2_1_support_plan_pins_original_v1_inputs():
    assert P.EXPECTED_PANEL_ROWS == 5620
    assert P.EXPECTED_TEMPLATES == 124
    assert P.EXPECTED_SIMILARITY == 116
    assert P.COVERAGE_THRESHOLD == 0.60
    assert P.FOLD_SHA256 == "f353068ec40864d56ac2c514a22e1199a9e237f58b1399e9739c71ae4488d3a1"
    assert P.REGISTRY_SHA256 == "2367b9ea5b3bad10b66c2958599069d574d5bc8c829d6066dc04b75aa069bf1b"
    assert P.RESPONSES_SHA256 == "79edc665876aca82ba9425eb741d74fa5252722b9b017dd10bf8f37744b46c6a"


def test_v1_2_1_support_plan_generator_contains_no_execution_path():
    src = Path("research/target_aware_market_panel/v1_2_1_make_support_plan.py").read_text()
    assert "fit(" not in src
    assert "predict(" not in src
    assert "settle_" not in src
    assert "httpx" not in src and "requests." not in src
    assert '"target_outcomes_read": False' in src
    assert '"model_fit": False' in src
    assert '"oos_executed": False' in src


def test_v1_2_1_support_plan_binds_all_support_semantic_modules_and_runner_template():
    rel = {str(p.relative_to(P.ROOT)) for p in P.SEMANTIC_MODULES}
    assert rel == {
        "src/research/target_aware_market_panel/panel.py",
        "src/research/target_aware_market_panel/support.py",
        "src/research/target_aware_market_panel/support_v12.py",
        "src/research/target_aware_market_panel/cohort_packets.py",
        "src/research/dual_provider_llm/packet.py",
        "src/research/thestatsapi/normalizer.py",
        "research/target_aware_market_panel/run_support_diagnostics.py",
        "research/target_aware_market_panel/v1_2_freeze_prehistory.py",
    }
    from research.target_aware_market_panel import run_support_diagnostics_v1_2_1 as R
    assert R.normalized_self_template_sha256() == P.runner_template_sha256()


def test_v1_2_1_support_plan_script_is_directly_invocable():
    import subprocess
    import sys
    proc = subprocess.run(
        [sys.executable, "research/target_aware_market_panel/v1_2_1_make_support_plan.py", "--help"],
        cwd=P.ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--authorized-head" in proc.stdout


def test_v1_2_1_repair_is_scalar_normalization_only():
    from src.research.target_aware_market_panel import support_v12 as S
    import numpy as np
    assert S._finite(1.0) is True
    assert S._finite(None) is False
    assert isinstance(S._finite(np.float64(1.0)), bool)
    assert P.V12_ABORT_SHA256 == "ea97968682054f1b507efe8335e065bf7390881c66e51047351e09d123e2c90f"
    assert P.V12_PLAN_SHA256 == "39d7a0fa46bda14e742b86de1f703f74b711017158f6164b1fcc83849eccdc0d"
