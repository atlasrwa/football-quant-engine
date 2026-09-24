from pathlib import Path

from research.target_aware_market_panel import v1_2_make_support_plan as P


def test_support_plan_pins_original_v1_inputs():
    assert P.EXPECTED_PANEL_ROWS == 5620
    assert P.EXPECTED_TEMPLATES == 124
    assert P.EXPECTED_SIMILARITY == 116
    assert P.COVERAGE_THRESHOLD == 0.60
    assert P.FOLD_SHA256 == "f353068ec40864d56ac2c514a22e1199a9e237f58b1399e9739c71ae4488d3a1"
    assert P.REGISTRY_SHA256 == "2367b9ea5b3bad10b66c2958599069d574d5bc8c829d6066dc04b75aa069bf1b"
    assert P.RESPONSES_SHA256 == "79edc665876aca82ba9425eb741d74fa5252722b9b017dd10bf8f37744b46c6a"


def test_support_plan_generator_contains_no_execution_path():
    src = Path("research/target_aware_market_panel/v1_2_make_support_plan.py").read_text()
    assert "fit(" not in src
    assert "predict(" not in src
    assert "settle_" not in src
    assert "httpx" not in src and "requests." not in src
    assert '"target_outcomes_read": False' in src
    assert '"model_fit": False' in src
    assert '"oos_executed": False' in src
