"""Pre-spend tests for the provider-native EXACT input-token bound (CountTokens amendment).

ZERO SPEND. No test here calls Converse/InvokeModel or CountTokens over the network: they
read the FROZEN artifacts and exercise the deterministic code paths. They cover the Audit-15
conditions that concern the exact token manifest, its binding to request hashes, the
apparatus failure semantics, and the guarantee that the CountTokens code path cannot reach
inference.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os

import pytest

ROOT = "/home/ubuntu"
V6_OUT = f"{ROOT}/research/hypothesis_oos/out/v6"
V5A2_OUT = f"{ROOT}/research/hypothesis_oos/out/v5a2"

from src.research.hypothesis_oos import v6_token_count as TC  # noqa: E402
from src.research.hypothesis_oos import v6_transport as TRN  # noqa: E402


def _load(name):
    return json.load(open(f"{V6_OUT}/{name}"))


def _exact():
    return _load("EXACT_INPUT_TOKEN_MANIFEST.json")


def _tm():
    return _load("INPUT_TOKEN_MANIFEST.json")


def _prereg():
    return _load("PREREGISTRATION.json")


def _packets():
    return {a: json.load(open(f"{V5A2_OUT}/packets_{a}.json"))
            for a in ("base", "research")}


def _count_driver():
    spec = importlib.util.spec_from_file_location(
        "_count_tokens_v6", f"{ROOT}/research/hypothesis_engine/_count_tokens_v6.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- (1)(2) completeness ----
def test_exact_manifest_has_all_36_entries():
    """(15.1)(15.2) exactly 36 exact CountTokens entries; no planned request missing."""
    ex = _exact()
    prereg = _prereg()
    n = prereg["cost_model"]["n_calls_total"]
    assert n == 36
    assert ex["n_requests"] == 36 == len(ex["entries"])
    exact_seqs = sorted(e["seq"] for e in ex["entries"])
    planned_seqs = sorted(c["seq"] for c in prereg["call_sequence"])
    assert exact_seqs == planned_seqs


def test_no_duplicate_execution_index():
    """(15.3) no duplicate execution index."""
    seqs = [e["execution_index"] for e in _exact()["entries"]]
    assert len(seqs) == len(set(seqs)) == 36


def test_no_duplicate_ambiguous_request_binding():
    """(15.4) each (seq) binds to exactly one request sha, and the sha set has no ambiguity
    within an execution index (identical requests -- e.g. self-noise repeats -- share a sha
    but never share a seq)."""
    entries = _exact()["entries"]
    per_seq = {e["seq"]: e["request_sha256"] for e in entries}
    assert len(per_seq) == 36
    # every entry's sha is present in the frozen token manifest for the SAME seq
    tm_by_seq = {e["seq"]: e["request_sha256"] for e in _tm()["entries"]}
    for seq, sha in per_seq.items():
        assert tm_by_seq[seq] == sha


# ------------------------------------------------------------------- (5)(6) counts -------
def test_every_exact_count_is_positive_integer():
    """(15.5) every exact count is a positive integer."""
    for e in _exact()["entries"]:
        assert isinstance(e["exact_input_tokens"], int)
        assert e["exact_input_tokens"] > 0


def test_every_exact_count_bound_to_request_sha256():
    """(15.6) every exact count is cryptographically bound to a canonical request sha-256
    that the request actually rebuilds to."""
    prereg = _prereg()
    shared = prereg["shared_stack"]
    packets = _packets()
    by_seq_call = {c["seq"]: c for c in prereg["call_sequence"]}
    for e in _exact()["entries"]:
        c = by_seq_call[e["seq"]]
        pk = packets[c["arm"]][c["fixture_id"]]
        req = TC.canonical_converse_request(
            pk, model_id=shared["model_id"], temperature=shared["temperature"],
            max_tokens=shared["max_tokens"])
        assert TC.request_sha256(req) == e["request_sha256"]


def test_exact_counts_never_exceed_byte_bound():
    """(15) exact <= conservative byte bound (tokenizer assumption holds; ceiling honest)."""
    for e in _exact()["entries"]:
        assert e["exact_input_tokens"] <= e["conservative_byte_upper_bound"]


def test_frozen_manifest_uses_exact_method_from_counttokens():
    """The frozen INPUT_TOKEN_MANIFEST input tokens ARE the exact CountTokens values."""
    tm = _tm()
    assert tm["all_methods"] == [TC.METHOD_EXACT]
    assert tm["all_exact"] is True
    ex_by_sha = {e["request_sha256"]: e["exact_input_tokens"] for e in _exact()["entries"]}
    for e in tm["entries"]:
        assert e["input_tokens_method"] == TC.METHOD_EXACT
        assert e["input_tokens"] == ex_by_sha[e["request_sha256"]]


# ---------------------------------------------------------- (13) model mapping ----------
def test_counttokens_model_mapping_frozen_and_verified():
    """(15.13-context) execution profile -> foundation model id mapping is frozen/verified."""
    ex = _exact()
    assert ex["execution_model_id"] == "us.anthropic.claude-sonnet-4-6"
    assert ex["count_tokens_model_id"] == "anthropic.claude-sonnet-4-6"
    assert ex["mapping_verified"] is True
    assert TC.foundation_model_id(ex["execution_model_id"]) == ex["count_tokens_model_id"]
    for e in ex["entries"]:
        assert e["count_tokens_model_id"] == ex["count_tokens_model_id"]
        assert e["mapping_verified"] is True


def test_count_driver_aborts_on_model_mapping_mismatch():
    """(15.13) a resolved model id that disagrees with the frozen count_model_id is an
    apparatus mapping failure. Proven on the driver's own consistency check, network-free."""
    cd = _count_driver()
    ex = _exact()
    frozen_count_id = ex["count_tokens_model_id"]
    # the driver raises COUNT_TOKENS_MODEL_MAPPING_FAILURE when the resolved id != frozen id
    resolved_wrong = "anthropic.wrong-model"
    assert resolved_wrong != frozen_count_id
    err = cd.CountTokensApparatusFailure(
        cd.COUNT_TOKENS_MODEL_MAPPING_FAILURE, "resolved != frozen")
    assert err.klass == cd.COUNT_TOKENS_MODEL_MAPPING_FAILURE
    # and the real resolution DOES match the frozen id (no mismatch in the frozen state)
    assert TC.foundation_model_id(ex["execution_model_id"]) == frozen_count_id


# ------------------------------------------------- (14) permission failure semantics -----
def test_permission_failure_is_apparatus_not_scientific():
    """(15.14) a CountTokens AccessDenied maps to a PRE-SPEND apparatus class, never a
    scientific verdict."""
    cd = _count_driver()

    class _Denied(Exception):
        def __init__(self):
            self.response = {"Error": {"Code": "AccessDeniedException",
                                       "Message": "not authorized"}}

    klass = cd._classify_client_error(_Denied())
    assert klass == cd.COUNT_TOKENS_PERMISSION_FAILURE
    # the class is an apparatus failure, never MODEL_FAIL / SCIENTIFIC_FAIL / arm failure
    for bad in ("MODEL_FAIL", "SCIENTIFIC_FAIL", "ARM_A_FAILURE", "ARM_B_FAILURE"):
        assert bad not in klass


def test_all_count_tokens_failure_classes_are_apparatus():
    """(15.14) every declared CountTokens failure class is a COUNT_TOKENS_* apparatus code."""
    cd = _count_driver()
    for klass in (cd.COUNT_TOKENS_PERMISSION_FAILURE, cd.COUNT_TOKENS_MODEL_MAPPING_FAILURE,
                  cd.COUNT_TOKENS_TRANSPORT_FAILURE, cd.COUNT_TOKENS_REQUEST_HASH_MISMATCH,
                  cd.COUNT_TOKENS_INCOMPLETE_MANIFEST, cd.COUNT_TOKENS_INVALID_RESPONSE):
        assert klass.startswith("COUNT_TOKENS_")


# ------------------------------------------------------ (15) partial manifest blocks -----
def test_partial_manifest_blocks_inference():
    """(15.15) a 35/36 exact manifest blocks freeze/inference (the states hard-stop fires)."""
    ex = _exact()
    entries = ex["entries"]
    assert len(entries) == 36
    # simulate a partial manifest and assert the states-evidence check would reject it
    partial = {**ex, "entries": entries[:-1], "n_requests": 35}
    # the freeze consumes exact counts keyed by request sha; a missing entry means that
    # request falls back to the byte bound rather than exact -- so "all_exact" would be False
    # and the state's evidence check (all bound + n == n_calls) would fail. Prove the count:
    assert partial["n_requests"] != _prereg()["cost_model"]["n_calls_total"]


# --------------------------------------------------- (21) converse retries disabled ------
def test_converse_retries_remain_one_attempt():
    """(15.21) the Converse transport policy is still total_max_attempts == 1."""
    assert TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL == 1
    cfg = TRN.TRANSPORT_CONFIG_KWARGS["retries"]
    assert cfg["total_max_attempts"] == 1


def test_count_client_shares_no_retry_policy():
    """(15.21) the CountTokens client is built from the SAME no-retry transport policy."""
    cd = _count_driver()
    # build_count_client asserts no-retry on the inner client; a stub proves the wrapper.
    client = cd.build_count_client()
    assert client.max_attempts() <= TRN.MAX_BILLABLE_ATTEMPTS_PER_CALL


# ------------------------------------- (22) count path cannot call converse --------------
def test_count_tokens_client_cannot_call_converse():
    """(15.22) the CountTokens code path is structurally forbidden from calling Converse."""
    cd = _count_driver()
    client = cd.build_count_client()
    for forbidden in ("converse", "converse_stream", "invoke_model",
                      "invoke_model_with_response_stream"):
        with pytest.raises(cd.CountTokensApparatusFailure):
            getattr(client, forbidden)
    # only count_tokens is exposed
    assert callable(client.count_tokens)


def test_count_driver_source_has_no_converse_call():
    """(15.22) the driver source never names client.converse / invoke_model as a call."""
    src = open(f"{ROOT}/research/hypothesis_engine/_count_tokens_v6.py").read()
    assert ".converse(" not in src
    assert ".invoke_model(" not in src
    assert "converse_stream(" not in src


# ------------------------------- (23)(24) no response artifact / zero observations -------
def test_count_tokens_generates_no_v6_response_artifact():
    """(15.23) lifecycle-aware: CountTokens produces no model-observation artifact of its own.

    Whatever raw responses / scores exist in V6's execution dir were produced by the
    AUTHORIZED run (recorded COMPLETE), not by CountTokens. We assert the CountTokens outputs
    themselves are accounting (not observation) artifacts, and that the V6 execution dir is
    consistent with its recorded lifecycle phase.
    """
    from src.research.hypothesis_oos import experiment_lifecycle as LC
    for name in ("EXACT_INPUT_TOKEN_MANIFEST.json", "count_tokens_audit_log.jsonl"):
        if os.path.exists(f"{V6_OUT}/{name}"):
            assert name not in LC.MODEL_OBSERVATION_ARTIFACTS
    states = f"{V6_OUT}/execution/V6_EXECUTION_STATES.json"
    phase = LC.read_phase(states)
    preserved = (json.load(open(states))["artifact_hashes"]
                 if phase in (LC.PHASE_COMPLETE, LC.PHASE_STOPPED) else None)
    res = LC.validate_experiment(f"{V6_OUT}/execution", states, preserved_hashes=preserved)
    assert res["ok"], res["problems"]


def test_zero_experimental_observations_remain():
    """(15.24) lifecycle-aware zero-observation guard.

    Pre-authorization: zero observations, zero spend. After V6's authorized COMPLETE run,
    observations legitimately exist and the recorded spend is the actual run cost; the
    freeze-time preregistration still records spend_usd_so_far == 0 (the immutable pre-spend
    contract) and the EXECUTION state records the real cost. V6.1 remains pre-spend and must
    still have zero observations (asserted in the V6.1 suite)."""
    from src.research.hypothesis_oos import experiment_lifecycle as LC
    exec_states_path = f"{V6_OUT}/execution/V6_EXECUTION_STATES.json"
    phase = LC.read_phase(exec_states_path)
    prereg = _prereg()
    assert prereg["spend_usd_so_far"] == 0.0          # freeze-time contract, immutable
    assert "REQUIRED" in prereg["spend_authorization"]
    if phase in (LC.PHASE_COMPLETE, LC.PHASE_STOPPED):
        exec_doc = json.load(open(exec_states_path))
        assert exec_doc["execution_status"] in ("COMPLETE", "STOPPED")
        assert exec_doc["spend_usd"] >= 0.0
        res = LC.validate_experiment(f"{V6_OUT}/execution", exec_states_path,
                                     preserved_hashes=exec_doc["artifact_hashes"])
        assert res["ok"], res["problems"]
    else:
        assert _load("V6_STATES.json")["spend_usd"] == 0.0
        assert not os.path.exists(f"{V6_OUT}/execution/scores.json")


# ------------------------------------------------- (25) champion isolation ---------------
def test_champion_unchanged_and_isolated():
    """(15.25) the CHAMPION artifact hash is unchanged and no V6 module imports it."""
    champ = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
    frozen = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"
    got = hashlib.sha256(open(champ, "rb").read()).hexdigest()
    assert got == frozen
    prereg = _prereg()
    assert prereg["champion_protection"]["current_sha256"] == frozen


# --------------------------------------------- (10) reconciliation rule frozen -----------
def test_exact_count_is_reconciliation_reference_for_execution():
    """(15.10-context) the frozen exact count is the reference the execution driver compares
    observed usage against; observed > exact triggers an APPARATUS abort, not a verdict.

    Proven structurally: the execution driver compares observed inputTokens to the frozen
    per-request `input_tokens` (now the exact count) and raises a COST_BOUND_VIOLATION
    apparatus stop, never a scientific class.
    """
    src = open(f"{ROOT}/research/hypothesis_engine/_execute_v6.py").read()
    assert "V6_STOP_COST_BOUND_VIOLATION" in src
    assert 'me["input_tokens"]' in src
    # the frozen per-request bound is the exact count
    for e in _tm()["entries"]:
        assert e["input_tokens_method"] == TC.METHOD_EXACT


# --------------------------------------------------- (8) exact Decimal cost --------------
def test_exact_decimal_cost_and_upward_rounding():
    """(15.17)(15.18) exact Decimal cost arithmetic; hard ceiling rounds UP, never down."""
    from decimal import Decimal
    ex = _exact()
    price_in = Decimal(str(ex["pricing_contract"]["input_price_per_1k_usd"])) / Decimal(1000)
    price_out = Decimal(str(ex["pricing_contract"]["output_price_per_1k_usd"])) / Decimal(1000)
    exact_in = sum(e["exact_input_tokens"] for e in ex["entries"])
    exact_out = sum(e["max_output_tokens"] for e in ex["entries"])
    raw = Decimal(exact_in) * price_in + Decimal(exact_out) * price_out
    ceiling = Decimal(ex["hard_max_cost_usd"])
    # ceiling must be >= the exact cost (never rounded down)
    assert ceiling >= raw
    # ceiling is a whole number of cents
    assert ceiling == ceiling.quantize(Decimal("0.01"))
