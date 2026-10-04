import json
from pathlib import Path

from src.research.evaluation.v21_local_state_space_stage1 import (
    PROFILE_ORDER,
    _profile_config,
)


def _protocol():
    return json.loads(
        Path("research/qfe_v21_state_space/PROTOCOL_V2.json").read_text()
    )


def test_v2_profile_order_matches_frozen_tie_break():
    assert PROFILE_ORDER == ("EB_COMP_STRONG", "EB_LOCAL", "EB_LOCAL_SLOW")


def test_v2_configs_disable_team_global_transfer_and_use_median_intensity():
    protocol = _protocol()
    for target in ("goals", "corners"):
        for profile in PROFILE_ORDER:
            config = _profile_config(protocol, target, profile)
            assert config.use_team_global_transfer is False
            assert config.intensity_point == "posterior_median"
            assert config.team_influence == 1.0


def test_v2_stationary_uncertainty_is_target_scaled():
    protocol = _protocol()
    goals = _profile_config(protocol, "goals", "EB_LOCAL")
    corners = _profile_config(protocol, "corners", "EB_LOCAL")
    assert corners.global_state.stationary_sd < goals.global_state.stationary_sd
    assert corners.competition_state.stationary_sd < goals.competition_state.stationary_sd
    assert corners.team_comp_state.stationary_sd < goals.team_comp_state.stationary_sd
