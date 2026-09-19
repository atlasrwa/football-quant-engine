"""AUDIT FINDING 4: ONE authoritative submission contract.

`select_cohort` used to re-implement validation: it split a submission into valid/invalid and
kept the valid ids, which is PARTIAL ACCEPTANCE -- directly contradicting
`runner.PARTIAL_ACCEPTANCE = False`. It also never checked the selection cap, uniqueness,
session-registry membership or canonical round-trip.

These tests pin the repaired behaviour and would FAIL against the pre-repair code.
"""
from __future__ import annotations

import pytest

from src.research.hypothesis_v8c import runner as R
from src.research.hypothesis_v8c import select_freeze as SF

GKW = {"metrics": ["goals", "yellow_cards"]}


def _select(env, selector, **kw):
    return SF.select_cohort(
        env.index, [env.target_pos], capability=env.capability,
        fixture_ids=[env.target_fixture_id], grammar_kwargs=GKW,
        classification="SYNTHETIC_ONLY", enforce_seal=False, s_selector=selector, **kw)


def _first_page(session, n):
    return [c["hypothesis_id"] for c in session.search({"max_results": 50})["results"][:n]]


# ------------------------------------------------------------------ partial acceptance
def test_mixed_valid_and_fabricated_accepts_nothing(golden_env):
    """THE defect: a good id must NOT survive beside a fabricated one."""
    def selector(session):
        return _first_page(session, 1) + ["hyp_TOTALLY_INVENTED"]

    row = _select(golden_env, selector)["selections"][0]
    assert row["arm_status"] == R.INVALID_SUBMISSION
    assert row["S"] == [], "partial acceptance leaked a valid id into the freeze"
    assert row["k_valid"] == 0


def test_invalid_submission_is_not_relabelled_abstention(golden_env):
    """An explicit empty submission and a rejected submission are DIFFERENT events."""
    def bad(session):
        return _first_page(session, 1) + ["hyp_NOPE"]

    def empty(session):
        session.search({"max_results": 50})
        return []

    bad_row = _select(golden_env, bad)["selections"][0]
    empty_row = _select(golden_env, empty)["selections"][0]
    assert bad_row["arm_status"] == R.INVALID_SUBMISSION
    assert empty_row["arm_status"] == R.OK_ABSTAIN
    assert bad_row["arm_status"] != empty_row["arm_status"]


def test_failure_status_propagates_to_controls_and_freeze(golden_env):
    """A rejected submission must yield NO controls -- not controls for the surviving ids."""
    def bad(session):
        return _first_page(session, 3) + ["hyp_NOPE"]

    row = _select(golden_env, bad)["selections"][0]
    assert row["arm_status"] == R.INVALID_SUBMISSION
    assert row["S"] == [] and row["R"] == [] and row["H"] == []
    assert row["R_pairs"] == []


# ------------------------------------------------------------------ the other five terms
def test_over_cap_submission_rejected(golden_env):
    def selector(session):
        return _first_page(session, R.MAX_SELECTIONS + 1)

    row = _select(golden_env, selector)["selections"][0]
    assert row["arm_status"] == R.INVALID_SUBMISSION
    assert any(p["reason"] == R.REASON_OVER_CAP for p in row["S_invalid"])


def test_duplicate_ids_rejected(golden_env):
    def selector(session):
        one = _first_page(session, 1)
        return one + one

    row = _select(golden_env, selector)["selections"][0]
    assert row["arm_status"] == R.INVALID_SUBMISSION
    assert any(p["reason"] == R.REASON_DUPLICATE for p in row["S_invalid"])


def test_id_not_returned_this_session_rejected(golden_env, golden_universe):
    """A REAL evaluable id that this session's search never surfaced is still rejected."""
    real = golden_universe.evaluable[0]["hypothesis_id"]

    def selector(session):
        return [real]          # no search issued at all

    row = _select(golden_env, selector)["selections"][0]
    assert row["arm_status"] == R.INVALID_SUBMISSION
    assert any(p["reason"] == R.REASON_NOT_RETURNED for p in row["S_invalid"])


def test_clean_submission_is_accepted_and_bound(golden_env):
    def selector(session):
        return _first_page(session, 3)

    row = _select(golden_env, selector)["selections"][0]
    assert row["arm_status"] == R.OK
    assert row["k_valid"] == 3
    assert len(row["R_pairs"]) == 3


# ------------------------------------------------------------------ provenance + bypass
def test_freeze_carries_complete_treatment_provenance(golden_env):
    def selector(session):
        return _first_page(session, 2)

    row = _select(golden_env, selector)["selections"][0]
    tp = row["treatment_provenance"]
    required = ["fixture_id", "kickoff_unix", "corpus_vintage", "capability_hash",
                "pit_context_hash", "universe_hash", "packet_hash",
                "requested_model_id", "resolved_model_id", "prompt_version",
                "prompt_sha256", "tool_schema_version", "tool_schema_sha256",
                "runner_version", "orchestration_version", "model_config_hash",
                "cache_key", "cache_hit", "converse_calls", "search_calls_attempted",
                "search_calls_executed", "search_budget_exhausted", "termination_reason",
                "search_queries", "ids_returned_to_model", "submitted_ids", "accepted_ids",
                "validation_status", "research_reason", "evidence_references",
                "raw_model_response_hashes"]
    missing = [k for k in required if k not in tp]
    assert not missing, f"treatment provenance missing {missing}"
    assert tp["search_calls_executed"] == 1
    assert tp["ids_returned_to_model"], "session registry was not bound"
    assert row["packet_hash"] and row["packet_hash"] != "REHEARSAL_PACKET"


def test_resolved_model_id_is_not_fabricated(golden_env):
    """When the transport did not report a resolved model, the record says None."""
    def selector(session):
        return _first_page(session, 1)

    tp = _select(golden_env, selector)["selections"][0]["treatment_provenance"]
    assert tp["resolved_model_id"] is None
    assert tp["requested_model_id"] == "DETERMINISTIC_STANDIN"


def test_seal_bypass_is_refused_for_non_synthetic_classification(golden_env):
    """The test-only relaxation must not be reachable for real evidence."""
    with pytest.raises(AssertionError, match="test-only"):
        SF.select_cohort(
            golden_env.index, [golden_env.target_pos], capability=golden_env.capability,
            fixture_ids=[golden_env.target_fixture_id], grammar_kwargs=GKW,
            classification="DEVELOPMENT_REAL_CORPUS", enforce_seal=False)
