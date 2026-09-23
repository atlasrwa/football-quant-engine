import json
from pathlib import Path

from research.target_aware_market_panel import v1_2_fixture_discovery as D


def test_frozen_discovery_plan_is_12_seasons_and_stats_free():
    p = json.loads(Path("research/target_aware_market_panel/V1_2_BACKFILL_DISCOVERY_PLAN_V1.json").read_text())
    assert p["n_selected_seasons"] == 12
    assert p["fixture_discovery"]["hard_global_request_cap"] == 100
    assert p["fixture_discovery"]["stop_before_stats"] is True
    assert p["stats_requests_this_stage"] == 0
    assert p["odds_requests_this_stage"] == 0


def test_runner_is_match_list_only_and_no_hidden_retries():
    src = Path("research/target_aware_market_panel/v1_2_fixture_discovery.py").read_text()
    assert "client.get(Endpoint.MATCHES" in src
    assert "max_retries=1" in src
    assert "MATCH_DETAIL" not in src
    assert "MATCH_ODDS" not in src


def test_validate_fixture_fails_closed_on_wrong_scope():
    good = {
        "id": "mt_1", "status": "finished", "competition_id": "comp_1",
        "season_id": "sn_1", "utc_date": "2022-01-01T12:00:00Z",
    }
    mid, ko = D._validate_fixture(good, comp="comp_1", season="sn_1", cutoff=1700000000)
    assert mid == "mt_1" and ko < 1700000000
    bad = dict(good, status="scheduled")
    try:
        D._validate_fixture(bad, comp="comp_1", season="sn_1", cutoff=1700000000)
    except ValueError:
        pass
    else:
        raise AssertionError("scheduled fixture did not fail closed")


def test_recovery_runner_is_zero_network_and_first_pass_bound():
    src = Path("research/target_aware_market_panel/v1_2_finalize_fixture_discovery.py").read_text()
    assert "from src.research.prospective.capture import ProspectiveApiClient" not in src
    assert "client.get(" not in src
    assert 'SOURCE_FAILED_HEAD = "5a79c8aff17e4c5dc18d9b944116019a3a5ac986"' in src
    assert "EXPECTED_RAW_PAGES = 54" in src
    assert "EXPECTED_FINISHED_FIXTURES = 4994" in src
