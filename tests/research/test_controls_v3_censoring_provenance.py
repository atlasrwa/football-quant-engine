"""Regression tests for the SS27 infrastructure-censoring REPORTING gap.

Defect: `controls_v3_core.run_controls` recorded `infrastructure_censored` only for quota
stops and self-noise shortfalls. A per-call `LLM_STATE_UNAVAILABLE` removed one observation
from one arm -- silently reducing that arm's usable n -- with no trace in the artifact. The
completed Sonnet 4.5 battery lost two calls that way (mt_584193286 team_alias and
formation_alias), leaving `infrastructure_censored == []` next to arms of n=6 and n=7.

The fix is REPORTING-ONLY. These tests pin both halves of that claim:
  * per-call infrastructure losses now appear in provenance AND in `infrastructure_censored`;
  * every outcome category stays distinct (model rejection is NOT censoring);
  * every scientific value of the completed battery is unchanged, proven by a full offline
    replay of the frozen 4.5 controls from cache with ZERO Bedrock calls.

Run: .venv/bin/python -m pytest tests/research/test_controls_v3_censoring_provenance.py -q
"""
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")
import pytest

from src.research.llm_matchup.hardening import adapter_v4 as A4
from src.research.llm_matchup.hardening.adapter_v3 import LLMResult
from src.research.llm_matchup.hardening import controls_v3_core as CORE
from src.research.llm_matchup.hardening import controls_v3_sonnet45 as C45
from src.research.llm_matchup.hardening import resume_golden_v3 as RG


# --------------------------------------------------------------------------------------
# 1. Category separation: the five outcome classes must never collapse into each other.
# --------------------------------------------------------------------------------------

def test_per_call_unavailable_is_reported_as_infrastructure_censoring():
    log = [{"fixture_id": "f1", "arm": "team_alias", "status": "LLM_STATE_UNAVAILABLE",
            "error_class": "OTHER_UNAVAILABLE", "error": "invoke_failed: boom"}]
    per_call, prov = CORE.build_censoring_provenance(log, [], False)
    assert len(per_call) == 1
    assert per_call[0]["reason"] == CORE.CENSOR_PER_CALL_UNAVAILABLE
    assert per_call[0]["classification"] == "INFRASTRUCTURE_CENSORED"
    assert prov["n_per_call_infrastructure_censored"] == 1
    assert prov["n_model_rejected"] == 0


def test_model_rejection_is_never_reclassified_as_censoring():
    """A validator rejection is the MODEL failing the contract -- scientific data, not an
    infrastructure excuse. It must stay out of the censoring list entirely."""
    log = [{"fixture_id": "f1", "arm": "team_alias", "status": "LLM_STATE_REJECTED",
            "reject_reason": "invalid enum value 'TEAM_BASELINE'"}]
    per_call, prov = CORE.build_censoring_provenance(log, [], False)
    assert per_call == []
    assert prov["n_per_call_infrastructure_censored"] == 0
    assert prov["n_model_rejected"] == 1
    assert prov["model_outcomes"][0]["classification"] == "MODEL_OUTCOME"
    assert prov["model_outcomes"][0]["reject_reason"] == "invalid enum value 'TEAM_BASELINE'"


def test_read_timeout_stays_distinct_from_other_unavailable():
    log = [{"fixture_id": "f1", "arm": "team_alias", "status": "LLM_STATE_UNAVAILABLE",
            "error_class": "READ_TIMEOUT", "error": "Read timeout on endpoint"},
           {"fixture_id": "f2", "arm": "team_alias", "status": "LLM_STATE_UNAVAILABLE",
            "error_class": "THROTTLING_TRANSIENT", "error": "ThrottlingException"}]
    _, prov = CORE.build_censoring_provenance(log, [], False)
    assert prov["error_class_counts"] == {"READ_TIMEOUT": 1, "THROTTLING_TRANSIENT": 1}


def test_quota_and_not_attempted_stay_distinct_and_are_preserved():
    """Fixture-level quota codes are produced by run_controls, not by the provenance builder;
    they must survive untouched alongside the new per-call entries."""
    fixture_level = [{"fixture_id": "f7", "reason": "AWS_DAILY_TOKEN_QUOTA", "error": "..."},
                     {"fixture_id": "f8", "reason": "NOT_ATTEMPTED_AFTER_QUOTA_STOP"}]
    log = [{"fixture_id": "f1", "arm": "team_alias", "status": "LLM_STATE_UNAVAILABLE",
            "error_class": "OTHER_UNAVAILABLE"}]
    per_call, prov = CORE.build_censoring_provenance(log, fixture_level, True)
    assert prov["fixture_level_censored"] == fixture_level
    assert prov["quota_stopped"] is True
    reasons = {e["reason"] for e in per_call}
    assert "AWS_DAILY_TOKEN_QUOTA" not in reasons
    assert "NOT_ATTEMPTED_AFTER_QUOTA_STOP" not in reasons


def test_unrecorded_error_class_is_labelled_not_guessed():
    """A log written before the error fields existed must say so, not emit a bare null that
    reads like 'no error class' rather than 'never recorded'."""
    log = [{"fixture_id": "f1", "arm": "team_alias", "status": "LLM_STATE_UNAVAILABLE"}]
    per_call, _ = CORE.build_censoring_provenance(log, [], False)
    assert per_call[0]["error_class"] == "UNKNOWN_NOT_PERSISTED"


def test_per_arm_accounting_reconciles_usable_n():
    log = ([{"fixture_id": f"f{i}", "arm": "team_alias", "status": "OK"} for i in range(6)]
           + [{"fixture_id": "f7", "arm": "team_alias", "status": "LLM_STATE_REJECTED"},
              {"fixture_id": "f8", "arm": "team_alias", "status": "LLM_STATE_UNAVAILABLE"}])
    _, prov = CORE.build_censoring_provenance(log, [], False)
    acc = prov["per_arm_accounting"]["team_alias"]
    assert acc == {"attempted": 8, "ok": 6, "model_rejected": 1, "infra_unavailable": 1}


def test_usage_records_error_class_for_unavailable_only():
    """_usage must classify UNAVAILABLE errors (so a future READ_TIMEOUT is recoverable) and
    must not invent an error_class for an OK or REJECTED call."""
    unavail = LLMResult("LLM_STATE_UNAVAILABLE", None,
                        {"error": "Read timeout on endpoint URL"})
    assert CORE._usage(unavail)["error_class"] == "READ_TIMEOUT"
    rejected = LLMResult("LLM_STATE_REJECTED", None, {"reject_reason": "bad enum"})
    assert CORE._usage(rejected)["error_class"] is None
    ok = LLMResult("OK", {}, {"cache_hit": True})
    assert CORE._usage(ok)["error_class"] is None


# --------------------------------------------------------------------------------------
# 2. Scientific invariance of the COMPLETED Sonnet 4.5 battery (offline, zero spend).
# --------------------------------------------------------------------------------------

#: The frozen completed Sonnet 4.5 control metrics. Any drift here is a hard stop.
FROZEN_45 = {
    "D_self": 0.0793,
    "D_football": 0.1335,
    "team": (0.0770, 0.3333, 6, "FAIL"),
    "competition": (0.1500, 0.6250, 8, "FAIL"),
    "formation": (0.1519, 0.7143, 7, "FAIL"),
    "behavior_sensitivity": 0.625,
    "identity_gate_passed": False,
    "degenerate_near_constant": False,
}


@pytest.fixture(scope="module")
def replayed():
    """Replay the completed 4.5 battery from the response cache. Any cache miss is returned as
    LLM_STATE_UNAVAILABLE -- exactly the historical outcome for the two lost mt_584193286
    calls. Asserts ZERO Bedrock calls by construction: the adapter is replaced outright."""
    if not os.path.exists(C45.CONTROLS_PATH):
        pytest.skip("completed 4.5 controls artifact not present")
    cfg = C45._cfg()
    model = cfg.gen.DEFAULT_BEDROCK_MODEL_ID
    counts = {"cache": 0, "miss": 0}

    def fake_analyze(packet, use_cache=True, call_index=0, gen=None, cache_dir=None,
                     capture_rejected_raw=False, model_id=None, region=None):
        key = A4._cache_key(model, packet["packet_hash"], call_index, gen=cfg.gen)
        payload = A4._load_cache(key, cfg.cache_dir, expect_model_id=model)
        if payload is None:
            counts["miss"] += 1
            return LLMResult("LLM_STATE_UNAVAILABLE", None,
                             {"fixture_id": packet["fixture"]["fixture_id"],
                              "error": "replayed: no cache entry (historical infra loss)"})
        counts["cache"] += 1
        m = dict(payload.get("manifest", {}))
        m["cache_hit"] = True
        return LLMResult(payload["status"], payload.get("state"), m)

    real = A4.analyze_matchup_v4
    A4.analyze_matchup_v4 = fake_analyze
    CORE.A4.analyze_matchup_v4 = fake_analyze
    try:
        res = CORE.run_controls(cfg, n_fixtures=8, k=3, persist=False)
    finally:
        A4.analyze_matchup_v4 = real
        CORE.A4.analyze_matchup_v4 = real
    return res["controls"], counts, json.load(open(C45.CONTROLS_PATH))


def test_replay_makes_no_bedrock_calls(replayed):
    _, counts, _ = replayed
    assert counts["cache"] + counts["miss"] == 56
    assert counts["miss"] == 2          # the two historical infrastructure losses


def test_scientific_metrics_unchanged_after_reporting_fix(replayed):
    c, _, _ = replayed
    ctl, gate, interp = c["controls"], c["identity_gate"], c["interpretation"]
    got = {
        "D_self": interp["mean_self_noise"],
        "D_football": ctl["D_behavior_sensitivity_formation_ablation"]["mean_distance"],
        "team": (ctl["A_team_token_invariance"]["mean_distance"],
                 ctl["A_team_token_invariance"]["trip_rate"],
                 ctl["A_team_token_invariance"]["n"],
                 gate["verdicts"]["team_token_control"]["status"]),
        "competition": (ctl["B_competition_token_invariance"]["mean_distance"],
                        ctl["B_competition_token_invariance"]["trip_rate"],
                        ctl["B_competition_token_invariance"]["n"],
                        gate["verdicts"]["competition_token_control"]["status"]),
        "formation": (ctl["C_formation_token_invariance"]["mean_distance"],
                      ctl["C_formation_token_invariance"]["trip_rate"],
                      ctl["C_formation_token_invariance"]["n"],
                      gate["verdicts"]["formation_token_control"]["status"]),
        "behavior_sensitivity": interp["behavior_sensitivity_exceeds_noise_rate"],
        "identity_gate_passed": gate["identity_gate_passed"],
        "degenerate_near_constant": interp["degenerate_near_constant"],
    }
    assert got == FROZEN_45


def test_every_control_row_identical_to_persisted_artifact(replayed):
    c, _, disk = replayed
    for arm in c["controls"]:
        assert c["controls"][arm]["rows"] == disk["controls"][arm]["rows"], arm
        for f in ("n", "n_tripped", "trip_rate", "mean_distance", "median_distance",
                  "max_distance"):
            assert c["controls"][arm][f] == disk["controls"][arm][f], f"{arm}.{f}"


def test_fix_surfaces_the_two_real_losses_the_artifact_hid(replayed):
    """The whole point: the persisted artifact reported zero censoring beside arms of n=6/n=7."""
    c, _, disk = replayed
    assert disk["infrastructure_censored"] == []        # the defect, as shipped
    prov = c["censoring_provenance"]
    assert prov["n_per_call_infrastructure_censored"] == 2
    lost = {(e["fixture_id"], e["arm"]) for e in prov["per_call_infrastructure_censored"]}
    assert lost == {("mt_584193286", "team_alias"), ("mt_584193286", "formation_alias")}
    assert prov["n_model_rejected"] == 1
    assert prov["model_outcomes"][0]["fixture_id"] == "mt_012249215"


def test_derived_provenance_artifact_matches_usable_n():
    path = os.path.join(C45.OUT, "golden_v3_censoring_provenance.json")
    if not os.path.exists(path):
        pytest.skip("derived provenance artifact not present")
    d = json.load(open(path))
    disk = json.load(open(C45.CONTROLS_PATH))
    for arm, n in d["usable_n_by_arm"].items():
        assert disk["controls"][arm]["n"] == n
    acc = d["per_arm_accounting"]
    assert acc["team_alias"]["attempted"] - acc["team_alias"]["model_rejected"] \
        - acc["team_alias"]["infra_unavailable"] == disk["controls"]["A_team_token_invariance"]["n"]
