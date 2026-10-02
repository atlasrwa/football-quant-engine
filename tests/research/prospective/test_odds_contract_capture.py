"""Contract tests binding target registry to prospective odds capture."""

from src.research.contracts.target import TARGET_REGISTRY_V1
from src.research.prospective.odds_capture import extract_prices


def _payload():
    return {
        "data": {
            "match_id": "mt_1",
            "bookmakers": [
                {
                    "bookmaker": "Pinnacle",
                    "markets": {
                        "total_goals": {
                            "2.5": {
                                "over": {"last_seen": "1.91"},
                                "under": {"last_seen": "1.97"},
                            }
                        },
                        "match_corners": {
                            "9.5": {
                                "over": {"last_seen": "1.95"},
                                "under": {"last_seen": "1.95"},
                            }
                        },
                        "team_total_goals": {
                            "home": {
                                "1.5": {
                                    "over": {"last_seen": "2.05"},
                                    "under": {"last_seen": "1.80"},
                                }
                            },
                            "away": {
                                "0.5": {
                                    "over": {"last_seen": "1.72"},
                                    "under": {"last_seen": "2.15"},
                                }
                            },
                        },
                        "team_corners": {
                            "home": {
                                "5.5": {
                                    "over": {"last_seen": "1.88"},
                                    "under": {"last_seen": "2.02"},
                                }
                            },
                            "away": {
                                "4.5": {
                                    "over": {"last_seen": "2.10"},
                                    "under": {"last_seen": "1.75"},
                                }
                            },
                        },
                    },
                }
            ],
        }
    }


def test_nested_team_markets_are_captured_with_exact_side_key() -> None:
    prices = extract_prices(_payload(), payload_hash="abc")
    keys = {(p.market, p.selection, p.line) for p in prices}
    assert ("team_total_goals:home", "over", 1.5) in keys
    assert ("team_total_goals:away", "under", 0.5) in keys
    assert ("team_corners:home", "over", 5.5) in keys
    assert ("team_corners:away", "under", 4.5) in keys


def test_target_contract_keys_match_capture_keys() -> None:
    prices = extract_prices(_payload(), payload_hash="abc")
    captured = {p.market for p in prices}

    for target_id in (
        "goals_home_regulation",
        "goals_away_regulation",
        "goals_total_regulation",
        "corners_home_regulation",
        "corners_away_regulation",
        "corners_total_regulation",
    ):
        contract = TARGET_REGISTRY_V1.contract(target_id)
        assert contract.captured_market_key in captured
