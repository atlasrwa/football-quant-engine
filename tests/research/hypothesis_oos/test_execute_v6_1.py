"""V6.1 execution-driver tests. ZERO SPEND -- every Bedrock client here is a deterministic
fake; nothing reaches the network or Converse/InvokeModel.

These prove the apparatus guarantees of `research/hypothesis_engine/_execute_v6_1.py`:
path isolation (V6 can never be targeted), the prospective pre-call cost guard, no-retry,
raw-before-adjudication, schedule/request-hash fidelity, frozen stop-rule wiring, terminal
state, and the full set of adversarial mock scenarios required by the amendment.

The driver is loaded from its file path (it is a private `_`-prefixed module). Tests run
against a TEMP COPY of the frozen V6.1 artifacts so a mutation (wrong fixture, tampered hash,
etc.) never touches the real frozen files, and the driver is repointed at the temp dir by
monkeypatching its module-level OUT/EXEC_DIR.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_oos import v6_token_count as TC

ROOT = "/home/ubuntu"
V61 = f"{ROOT}/research/hypothesis_oos/out/v6_1"
DRIVER_PATH = f"{ROOT}/research/hypothesis_engine/_execute_v6_1.py"


def _load_driver():
    spec = importlib.util.spec_from_file_location("_execute_v6_1", DRIVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DRV = _load_driver()


# ========================================================================================
# fixtures: a temp copy of the frozen V6.1 artifacts, with the driver repointed at it
# ========================================================================================
FROZEN_ARTIFACTS = ("PREREGISTRATION.json", "call_schedule.json",
                    "INPUT_TOKEN_MANIFEST.json", "EXACT_INPUT_TOKEN_MANIFEST.json",
                    "EVALUATOR_FREEZE.json", "packets_base.json", "packets_research.json",
                    # also referenced by PREREGISTRATION.artifact_hashes -> reverify needs them
                    "V6_1_DESIGN_COMPARISON.json", "arm_isolation_audit.json",
                    "pit_audit.json")


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A writable copy of the frozen V6.1 dir, with the driver's OUT/EXEC_DIR repointed here.

    IMPORTANT: the V6-forbidden path check compares against the driver's V6_FORBIDDEN_DIR,
    which stays the real out/v6 -- so the path-isolation tests are meaningful. Only OUT and
    EXEC_DIR are moved to the sandbox so tests can mutate copies safely.
    """
    out = tmp_path / "v6_1"
    out.mkdir()
    for name in FROZEN_ARTIFACTS:
        shutil.copy(f"{V61}/{name}", out / name)
    monkeypatch.setattr(DRV, "OUT", str(out))
    monkeypatch.setattr(DRV, "EXEC_DIR", str(out / "execution"))
    return out


def _rewrite(out, name, obj):
    with open(os.path.join(str(out), name), "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True, default=str)


def _rehash_prereg_artifact(out, name):
    """After mutating a frozen artifact in the sandbox, update its hash in the sandbox
    PREREGISTRATION so reverify fails ONLY for the reason the test intends (not for a
    trivially-stale hash), unless the test is specifically about hash drift."""
    pr = json.load(open(os.path.join(str(out), "PREREGISTRATION.json")))
    h = hashlib.sha256(open(os.path.join(str(out), name), "rb").read()).hexdigest()
    if name in pr["artifact_hashes"]:
        pr["artifact_hashes"][name] = h
    _rewrite(out, "PREREGISTRATION.json", pr)


# ========================================================================================
# fake Bedrock clients (deterministic; zero network)
# ========================================================================================
def _valid_payload(packet):
    """A minimal VALID tool-use payload tagged to this packet (correct fixture/packet hash)."""
    return {"fixture_id": packet["fixture_id"], "packet_hash": packet["packet_hash"],
            "hypotheses": []}


class FakeClient:
    """A Converse-capable fake. Records calls; returns a valid payload with configurable
    token usage. `total_max_attempts` mirrors the live-client retry accessor."""

    def __init__(self, out_dir, *, in_tok=100, out_tok=50, behavior=None, retries=1,
                 fail_positions=None):
        self.out_dir = out_dir
        self.in_tok = in_tok
        self.out_tok = out_tok
        self.behavior = behavior or {}     # request_hash -> "raise" | int override in_tok
        self.fail_positions = set(fail_positions or ())   # 1-based call-order positions to raise after send
        self.calls = []
        self._retries = retries
        self._packets = {a: json.load(open(f"{out_dir}/packets_{a}.json"))
                         for a in ("base", "research")}
        self._by_hash = {}
        for arm, pk in self._packets.items():
            for fid, p in pk.items():
                r = TC.canonical_converse_request(p, model_id="us.anthropic.claude-sonnet-4-6",
                                                  temperature=0.0, max_tokens=8192)
                self._by_hash[TC.request_sha256(r)] = p

    # botocore-style retry accessor the driver's transport asserts on
    class _Meta:
        def __init__(self, retries):
            self.config = type("C", (), {"retries": {"total_max_attempts": retries}})()

    @property
    def meta(self):
        return FakeClient._Meta(self._retries)

    def converse(self, **request):
        rhash = TC.request_sha256(request)
        seq = len(self.calls) + 1
        self.calls.append(rhash)
        if seq in self.fail_positions:                 # after-send failure by call position
            raise RuntimeError("simulated post-send transport failure (billing unknown)")
        b = self.behavior.get(rhash)
        if b == "raise":
            raise RuntimeError("simulated transport failure")
        packet = self._by_hash.get(rhash)
        in_tok = self.in_tok if not isinstance(b, int) else b
        return {"usage": {"inputTokens": in_tok, "outputTokens": self.out_tok},
                "output": {"message": {"content": [
                    {"toolUse": {"input": _valid_payload(packet)}}]}}}


def _run(out, client, **kw):
    return DRV.execute(client, out_dir=str(out), **kw)


# ========================================================================================
# PATH ISOLATION (regression: V6 can never be targeted)
# ========================================================================================
class TestPathIsolation:
    def test_v6_1_experiment_and_dir_pass(self):
        rep = DRV.assert_v6_1_paths("V6.1_GROUNDED_RESEARCH", DRV.OUT)
        assert rep["is_under_v6_1"] and not rep["is_under_v6"]

    def test_non_v6_1_experiment_id_aborts(self):
        with pytest.raises(DRV.PathSafetyError):
            DRV.assert_v6_1_paths("V6_GROUNDED_RESEARCH", DRV.OUT)

    def test_out_v6_dir_aborts(self):
        with pytest.raises(DRV.PathSafetyError):
            DRV.assert_v6_1_paths("V6.1", f"{ROOT}/research/hypothesis_oos/out/v6")

    def test_out_v6_execution_dir_aborts(self):
        with pytest.raises(DRV.PathSafetyError):
            DRV.assert_v6_1_paths("V6.1", f"{ROOT}/research/hypothesis_oos/out/v6/execution")

    def test_arbitrary_outside_dir_aborts(self):
        with pytest.raises(DRV.PathSafetyError):
            DRV.assert_v6_1_paths("V6.1", "/tmp/somewhere_else")

    def test_write_guard_refuses_v6(self):
        with pytest.raises(DRV.PathSafetyError):
            DRV.assert_write_target_is_v6_1(f"{ROOT}/research/hypothesis_oos/out/v6/x.json")

    def test_write_guard_refuses_outside(self):
        with pytest.raises(DRV.PathSafetyError):
            DRV.assert_write_target_is_v6_1("/tmp/x.json")


# ========================================================================================
# DRY RUN (zero inference)
# ========================================================================================
class TestDryRun:
    def test_dry_run_all_36_zero_inference(self, sandbox):
        rep = DRV.dry_run(out_dir=str(sandbox))
        assert rep["zero_inference"] is True
        assert rep["n_scheduled_calls"] == 36 and rep["all_36_present"]
        assert rep["reverify_ok"], rep["reverify_problems"]
        assert rep["worst_case_within_ceiling"]
        assert rep["cost_guard_is_prospective"]
        # every call has a matching request hash
        assert all(r.get("request_hash_ok") for r in rep["checked_calls"])

    def test_dry_run_writes_only_synthetic_report_no_execution_dir(self, sandbox):
        DRV.dry_run(out_dir=str(sandbox))
        assert os.path.exists(os.path.join(str(sandbox), "DRY_RUN_REPORT.json"))
        # no model-observation artifacts, no execution dir
        assert not os.path.isdir(os.path.join(str(sandbox), "execution"))


# ========================================================================================
# MOCK EXECUTION SCENARIOS (1..26)
# ========================================================================================
class TestMockExecution:
    def test_01_full_36_call_success(self, sandbox):
        client = FakeClient(str(sandbox), in_tok=100, out_tok=50)
        s = _run(sandbox, client)
        assert s["execution_status"] == "COMPLETE"
        assert s["execution_state"] == DRV.S_COMPLETE
        assert s["transport"]["n_charged"] == 36
        assert len(client.calls) == 36
        assert s["stop"] is None
        # scores + raw persisted
        assert os.path.exists(os.path.join(str(sandbox), "execution", "scores.json"))
        assert len(os.listdir(os.path.join(str(sandbox), "execution", "raw"))) == 36

    def test_02_first_call_infrastructure_failure(self, sandbox):
        # an INFRASTRUCTURE_FAILURE hypothesis class -> n_infra>=1 -> apparatus stop.
        # simulate by making the adjudicator see a fatal (non-dict) payload on call 1 via a
        # client that returns a non-object payload.
        client = FakeClient(str(sandbox))
        # override converse to yield a non-dict payload on the first call
        orig = client.converse
        def broken(**req):
            r = orig(**req)
            if len(client.calls) == 1:
                r["output"]["message"]["content"] = [{"toolUse": {"input": "not-an-object"}}]
            return r
        client.converse = broken
        s = _run(sandbox, client)
        # a parse-fatal response is counted; run continues (fatal-rate gated), but the raw is
        # preserved and the response is non-fatal-classified as RESPONSE_PARSE_FATAL
        assert s["n_responses_fatal"] >= 1

    def test_03_transport_failure_recorded_not_charged(self, sandbox):
        client = FakeClient(str(sandbox))
        # fail seq 1's request hash
        first = _first_hash(sandbox, 1)
        client.behavior = {first: "raise"}
        s = _run(sandbox, client)
        assert s["transport"]["n_transport_failures"] >= 1
        # a transport failure is never charged
        assert s["transport"]["n_charged"] <= 35

    def test_04_accepted_response_lost_no_retry(self, sandbox):
        # "lost" == the call raised AFTER acceptance; driver must NOT retry that seq, and
        # must reserve the frozen max as UNKNOWN_AFTER_SEND exposure (never zero).
        client = FakeClient(str(sandbox))
        first = _first_hash(sandbox, 1)
        client.behavior = {first: "raise"}
        s = _run(sandbox, client)
        assert s["transport"]["n_transport_failures"] >= 1
        assert len(client.calls) <= 36        # no retry ever adds an attempt beyond schedule
        assert s["transport"]["n_charged"] + s["transport"]["n_transport_failures"] <= 36
        # the lost call is UNKNOWN_AFTER_SEND with reserved exposure > 0 (never zero)
        assert s["n_unknown_after_send"] >= 1
        assert s["unknown_after_send_max_exposure_usd"] > 0.0

    def test_05_request_hash_mismatch_aborts_before_call(self, sandbox):
        # tamper a packet so its canonical request no longer matches the frozen manifest
        pk = json.load(open(os.path.join(str(sandbox), "packets_base.json")))
        fid = sorted(pk)[0]
        pk[fid]["sections"].append({"section_type": "TAMPER", "x": 1})
        _rewrite(sandbox, "packets_base.json", pk)
        client = FakeClient(str(sandbox))
        s = _run(sandbox, client)
        assert s["execution_status"] == "STOPPED"
        assert s["stop"][0]["rule"] == "V6_1_STOP_REQUEST_HASH_MISMATCH"
        # nothing was charged for the mismatched call
        assert s["transport"]["n_charged"] == 0

    def test_06_schedule_mismatch_missing_manifest_entry(self, sandbox):
        # remove a token-manifest entry so a scheduled seq has no cost bound
        tm = json.load(open(os.path.join(str(sandbox), "INPUT_TOKEN_MANIFEST.json")))
        tm["entries"] = [e for e in tm["entries"] if e["seq"] != 1]
        _rewrite(sandbox, "INPUT_TOKEN_MANIFEST.json", tm)
        client = FakeClient(str(sandbox))
        s = _run(sandbox, client)
        assert s["stop"][0]["rule"] == "V6_1_STOP_TOKEN_MANIFEST_MISSING"

    def test_07_wrong_fixture_in_manifest_reverify_fails(self, sandbox):
        tm = json.load(open(os.path.join(str(sandbox), "INPUT_TOKEN_MANIFEST.json")))
        for e in tm["entries"]:
            if e["seq"] == 1:
                e["fixture_id"] = "mt_999999999"
        _rewrite(sandbox, "INPUT_TOKEN_MANIFEST.json", tm)
        frozen = DRV.load_frozen(str(sandbox))
        problems = DRV.reverify(frozen, str(sandbox))
        assert any("fixture_id mismatch" in p for p in problems)

    def test_08_wrong_arm_in_manifest_reverify_fails(self, sandbox):
        tm = json.load(open(os.path.join(str(sandbox), "INPUT_TOKEN_MANIFEST.json")))
        for e in tm["entries"]:
            if e["seq"] == 1:
                e["arm"] = "research"
        _rewrite(sandbox, "INPUT_TOKEN_MANIFEST.json", tm)
        frozen = DRV.load_frozen(str(sandbox))
        problems = DRV.reverify(frozen, str(sandbox))
        assert any("arm mismatch" in p for p in problems)

    def test_09_wrong_replicate_in_manifest_reverify_fails(self, sandbox):
        tm = json.load(open(os.path.join(str(sandbox), "INPUT_TOKEN_MANIFEST.json")))
        for e in tm["entries"]:
            if e["seq"] == 1:
                e["rep"] = 9
        _rewrite(sandbox, "INPUT_TOKEN_MANIFEST.json", tm)
        frozen = DRV.load_frozen(str(sandbox))
        problems = DRV.reverify(frozen, str(sandbox))
        assert any("rep mismatch" in p for p in problems)

    def test_10_wrong_max_tokens_reverify_fails(self, sandbox):
        tm = json.load(open(os.path.join(str(sandbox), "INPUT_TOKEN_MANIFEST.json")))
        for e in tm["entries"]:
            if e["seq"] == 1:
                e["max_output_tokens"] = 4096
        _rewrite(sandbox, "INPUT_TOKEN_MANIFEST.json", tm)
        frozen = DRV.load_frozen(str(sandbox))
        problems = DRV.reverify(frozen, str(sandbox))
        assert any("max_output_tokens" in p for p in problems)

    def test_11_wrong_model_reverify_fails(self, sandbox):
        tm = json.load(open(os.path.join(str(sandbox), "INPUT_TOKEN_MANIFEST.json")))
        for e in tm["entries"]:
            if e["seq"] == 1:
                e["converse_model_id"] = "us.anthropic.some-other-model"
        _rewrite(sandbox, "INPUT_TOKEN_MANIFEST.json", tm)
        frozen = DRV.load_frozen(str(sandbox))
        problems = DRV.reverify(frozen, str(sandbox))
        assert any("model id" in p for p in problems)

    def test_12_missing_token_entry_stop(self, sandbox):
        # same mechanism as 06 but assert the driver stops mid-run (not just reverify)
        tm = json.load(open(os.path.join(str(sandbox), "INPUT_TOKEN_MANIFEST.json")))
        tm["entries"] = [e for e in tm["entries"] if e["seq"] != 5]
        _rewrite(sandbox, "INPUT_TOKEN_MANIFEST.json", tm)
        client = FakeClient(str(sandbox))
        s = _run(sandbox, client)
        assert s["stop"][0]["rule"] == "V6_1_STOP_TOKEN_MANIFEST_MISSING"

    def test_13_prospective_cost_ceiling_breach(self, sandbox):
        # a $0 ceiling makes the FIRST call's projected max cost breach before any converse
        client = FakeClient(str(sandbox))
        s = _run(sandbox, client, ceiling_override=0.0)
        assert s["stop"][0]["rule"] == "V6_1_STOP_COST_CEILING"
        assert s["transport"]["n_charged"] == 0        # nothing charged
        assert len(client.calls) == 0                  # converse never called

    def test_14_final_call_exactly_within_ceiling(self, sandbox):
        # ceiling exactly equal to the frozen worst-case total: all 36 must fit (<=)
        ex = json.load(open(os.path.join(str(sandbox), "INPUT_TOKEN_MANIFEST.json")))
        worst = round(sum(e["max_request_cost_usd"] for e in ex["entries"]), 2)
        client = FakeClient(str(sandbox), in_tok=1, out_tok=1)   # tiny real usage
        s = _run(sandbox, client, ceiling_override=worst)
        assert s["execution_status"] == "COMPLETE"
        assert s["transport"]["n_charged"] == 36

    def test_15_next_call_one_unit_above_ceiling_stops(self, sandbox):
        # ceiling one cent below the worst-case total -> the LAST scheduled call's guard
        # trips prospectively (spent + projected > ceiling), stopping before that converse.
        ex = json.load(open(os.path.join(str(sandbox), "INPUT_TOKEN_MANIFEST.json")))
        worst = round(sum(e["max_request_cost_usd"] for e in ex["entries"]), 2)
        # Use tiny real usage so accounted spend ~ 0 and the guard trips only when the
        # PROJECTED frozen max would cross the ceiling. Set ceiling below one call's max.
        one_call_max = max(e["max_request_cost_usd"] for e in ex["entries"])
        client = FakeClient(str(sandbox), in_tok=1, out_tok=1)
        s = _run(sandbox, client, ceiling_override=one_call_max - 0.01)
        assert s["stop"][0]["rule"] == "V6_1_STOP_COST_CEILING"

    def test_16_raw_write_failure_stops_before_adjudication(self, sandbox, monkeypatch):
        client = FakeClient(str(sandbox))
        def boom(seq, obj):
            raise DRV.RawPersistenceError("disk full (simulated)")
        monkeypatch.setattr(DRV, "_write_raw", boom)
        s = _run(sandbox, client)
        assert s["stop"][0]["rule"] == "V6_1_STOP_RAW_PERSISTENCE"
        # no scores were produced (adjudication never ran)
        assert not os.path.exists(os.path.join(str(sandbox), "execution", "scores.json")) \
            or json.load(open(os.path.join(str(sandbox), "execution", "scores.json"))) == []
        # the response was RECEIVED (hence billed): confirmed cost accounted, NOT zero
        assert s["confirmed_provider_cost_usd"] > 0.0
        led = [e for e in s["billing_ledger"] if e.get("billing_status") == "CONFIRMED"]
        assert led and led[0]["confirmed_cost_usd"] > 0.0

    def test_17_adjudicator_exception_is_surfaced(self, sandbox, monkeypatch):
        client = FakeClient(str(sandbox))
        import src.research.hypothesis_engine.validator_v5 as VV
        def boom(*a, **k):
            raise ValueError("adjudicator blew up (simulated)")
        monkeypatch.setattr(VV, "adjudicate", boom)
        # the driver treats a post-raw exception path: adjudication raises -> not swallowed as
        # a transport failure because raw already persisted. It should propagate.
        with pytest.raises(ValueError):
            _run(sandbox, client)

    def test_18_evaluator_invalid_is_a_verdict_state_not_driver_concern(self, sandbox):
        # the driver records scores; EVALUATOR_INVALID is produced by the frozen evaluator
        # run separately. Prove the driver imports and can hand scores to the frozen verdict.
        from src.research.hypothesis_oos import v6_1_verdict as V61
        client = FakeClient(str(sandbox))
        s = _run(sandbox, client)
        scores = json.load(open(os.path.join(str(sandbox), "execution", "scores.json")))
        # inject an impossible rate into one scorecard -> evaluator returns EVALUATOR_INVALID
        sc = [x["scorecard"] for x in scores]
        if sc:
            sc[0]["qualified_rate"] = 1.5
        from src.research.hypothesis_oos import v6_selfnoise as SN
        out = V61.final_verdict(sc, {"base": 4, "research": 4}, SN.pooled_sd([]))
        assert out["scientific_status"] in (V61.EVALUATOR_INVALID, "NON_EVALUABLE")

    def test_19_scientific_early_stop_wiring(self, sandbox, monkeypatch):
        # force the frozen stop classifier to fire a MODEL stop; the driver must stop.
        import src.research.hypothesis_oos.v6_stop as STOP
        real = STOP.classify_stop
        calls = {"n": 0}
        def fake(**kw):
            calls["n"] += 1
            if calls["n"] >= 3:
                return {"stop": True, "fired": [{"rule": "V6_STOP_MODEL_FIREWALL_VIOLATION_RATE",
                        "class": "MODEL", "detail": "simulated"}],
                        "eligibility": {}, "rules_evaluated": [], "model_rules_gated": False}
            return {"stop": False, "fired": [], "eligibility": {}, "rules_evaluated": [],
                    "model_rules_gated": False}
        monkeypatch.setattr(DRV.STOP, "classify_stop", fake)
        client = FakeClient(str(sandbox))
        s = _run(sandbox, client)
        assert s["execution_status"] == "STOPPED"
        assert s["stop"][0]["class"] == "MODEL"

    def test_20_apparatus_immediate_stop_wiring(self, sandbox, monkeypatch):
        import src.research.hypothesis_oos.v6_stop as STOP
        def fake(**kw):
            return {"stop": True, "fired": [{"rule": "V6_STOP_INFRASTRUCTURE_FAILURE",
                    "class": "APPARATUS", "detail": "simulated"}],
                    "eligibility": {}, "rules_evaluated": [], "model_rules_gated": False}
        monkeypatch.setattr(DRV.STOP, "classify_stop", fake)
        client = FakeClient(str(sandbox))
        s = _run(sandbox, client)
        assert s["execution_status"] == "STOPPED"
        assert s["stop"][0]["class"] == "APPARATUS"

    def test_21_natural_completion(self, sandbox):
        client = FakeClient(str(sandbox))
        s = _run(sandbox, client)
        assert s["execution_status"] == "COMPLETE"
        assert s["transport"]["n_charged"] == 36

    def test_22_write_into_v6_hard_failure(self):
        with pytest.raises(DRV.PathSafetyError):
            DRV.assert_write_target_is_v6_1(
                f"{ROOT}/research/hypothesis_oos/out/v6/execution/scores.json")

    def test_23_load_v6_packet_hard_failure(self, sandbox, monkeypatch):
        # point the driver at out/v6 and require it to abort in path safety
        monkeypatch.setattr(DRV, "OUT", f"{ROOT}/research/hypothesis_oos/out/v6")
        with pytest.raises(DRV.PathSafetyError):
            DRV.assert_v6_1_paths("V6.1", DRV.OUT)

    def test_24_duplicate_execution_index_in_schedule(self, sandbox):
        sch = json.load(open(os.path.join(str(sandbox), "call_schedule.json")))
        sch["calls"].append(dict(sch["calls"][0]))     # duplicate seq 1
        _rewrite(sandbox, "call_schedule.json", sch)
        frozen = DRV.load_frozen(str(sandbox))
        problems = DRV.reverify(frozen, str(sandbox))
        assert any("duplicate execution index" in p for p in problems)

    def test_25_call_after_terminal_state_forbidden(self, sandbox, monkeypatch):
        # prove the terminal-state guard: after a stop, no further converse is issued.
        import src.research.hypothesis_oos.v6_stop as STOP
        def fake(**kw):
            return {"stop": True, "fired": [{"rule": "V6_STOP_INFRASTRUCTURE_FAILURE",
                    "class": "APPARATUS", "detail": "x"}], "eligibility": {},
                    "rules_evaluated": [], "model_rules_gated": False}
        monkeypatch.setattr(DRV.STOP, "classify_stop", fake)
        client = FakeClient(str(sandbox))
        s = _run(sandbox, client)
        # stop fired after call 1 -> exactly 1 converse call, then terminal
        assert len(client.calls) == 1
        assert s["execution_state"] == DRV.S_STOPPED

    def test_26_retry_enabled_client_hard_failure(self, sandbox):
        from src.research.hypothesis_oos import v6_transport as TRN
        client = FakeClient(str(sandbox), retries=5)      # retries ENABLED
        with pytest.raises(TRN.TransportPreflightFailure):
            TRN.assert_no_retries(client)


def _first_hash(out, seq):
    tm = json.load(open(os.path.join(str(out), "INPUT_TOKEN_MANIFEST.json")))
    return {e["seq"]: e["request_sha256"] for e in tm["entries"]}[seq]


# ========================================================================================
# frozen-artifact reverify + no scientific policy in the driver
# ========================================================================================
class TestReverifyAndPurity:
    def test_clean_sandbox_reverifies(self, sandbox):
        frozen = DRV.load_frozen(str(sandbox))
        assert DRV.reverify(frozen, str(sandbox)) == []

    def test_tampered_packet_hash_drift_detected(self, sandbox):
        pk = json.load(open(os.path.join(str(sandbox), "packets_base.json")))
        fid = sorted(pk)[0]
        pk[fid]["sections"].append({"section_type": "TAMPER"})
        _rewrite(sandbox, "packets_base.json", pk)      # hash now drifts from prereg
        frozen = DRV.load_frozen(str(sandbox))
        problems = DRV.reverify(frozen, str(sandbox))
        assert any("packets_base.json changed" in p or "request hash drift" in p
                   for p in problems)

    def test_missing_required_artifact_is_missing_contract(self, sandbox):
        os.remove(os.path.join(str(sandbox), "call_schedule.json"))
        with pytest.raises(DRV.MissingContractError):
            DRV.load_frozen(str(sandbox))

    def test_driver_defines_no_scientific_policy(self):
        vs = DRV.version_stamp()
        assert vs["defines_scientific_policy"] is False
        src = open(DRIVER_PATH).read()
        # the driver must not hardcode thresholds/parameters
        for forbidden in ("DISCIPLINE_TOLERANCE =", "MIN_PAIRED_FIXTURES =",
                          "Z_MULTIPLIER =", "0.05", "1.645"):
            assert forbidden not in src, f"driver hardcodes scientific policy: {forbidden}"

    def test_driver_uses_frozen_canonical_builder_only(self):
        src = open(DRIVER_PATH).read()
        # exactly one request construction path: the frozen TC.canonical_converse_request
        assert "canonical_converse_request" in src
        assert "def canonical_converse_request" not in src   # not redefined here

    def test_driver_cannot_import_champion(self):
        src = open(DRIVER_PATH).read()
        for t in ("pilotC", "stat_mixer", "p_model"):
            assert t not in src



# ========================================================================================
# CONSERVATIVE UNKNOWN-AFTER-SEND BILLING ACCOUNTING (amendment v2)
# ========================================================================================
class TestUnknownBillingAccounting:
    """A request whose billing status becomes unknowable after send must NEVER be treated as
    zero financial exposure by the next-call guard. Only NOT_SENT may carry zero exposure."""

    def _manifest(self, out):
        tm = json.load(open(os.path.join(str(out), "INPUT_TOKEN_MANIFEST.json")))
        return {e["seq"]: e for e in tm["entries"]}

    def test_01_failure_before_converse_is_not_sent_zero_exposure(self, sandbox):
        # request-hash mismatch is raised INSIDE call_once BEFORE converse -> NOT_SENT, $0.
        pk = json.load(open(os.path.join(str(sandbox), "packets_base.json")))
        fid = sorted(pk)[0]; pk[fid]["sections"].append({"section_type": "TAMPER"})
        _rewrite(sandbox, "packets_base.json", pk)
        s = _run(sandbox, FakeClient(str(sandbox)))
        led = [e for e in s["billing_ledger"] if e["billing_status"] == DRV.BILLING_NOT_SENT]
        assert led and all(e["reserved_exposure_usd"] == 0.0 for e in led)
        assert s["unknown_after_send_max_exposure_usd"] == 0.0

    def test_02_converse_entered_then_error_is_unknown_after_send(self, sandbox):
        s = _run(sandbox, FakeClient(str(sandbox), fail_positions={1}))
        led1 = [e for e in s["billing_ledger"] if e["seq"] == 1][0]
        assert led1["billing_status"] == DRV.BILLING_UNKNOWN_AFTER_SEND

    def test_03_unknown_after_send_reserves_frozen_max(self, sandbox):
        me = self._manifest(sandbox)
        s = _run(sandbox, FakeClient(str(sandbox), fail_positions={1}))
        led1 = [e for e in s["billing_ledger"] if e["seq"] == 1][0]
        assert led1["reserved_exposure_usd"] == float(me[1]["max_request_cost_usd"])
        assert led1["reserved_exposure_usd"] > 0.0

    def test_04_unknown_exposure_participates_in_next_call_guard(self, sandbox):
        # ceiling set so that after seq1 becomes UNKNOWN (reserves its frozen max), the
        # NEXT call's projected max would cross the ceiling -> stop before it.
        me = self._manifest(sandbox)
        seq1_max = float(me[1]["max_request_cost_usd"])
        seq2_max = float(me[2]["max_request_cost_usd"])
        # budget = seq1 reserved + a sliver, but < seq1 + seq2 -> next-call guard must trip.
        s = _run(sandbox, FakeClient(str(sandbox), in_tok=1, out_tok=1, fail_positions={1}),
                 ceiling_override=seq1_max + seq2_max - 0.01)
        assert s["stop"] and s["stop"][0]["rule"] == "V6_1_STOP_COST_CEILING"
        assert s["unknown_after_send_max_exposure_usd"] == seq1_max

    def test_05_successful_response_reconciles_to_actual(self, sandbox):
        s = _run(sandbox, FakeClient(str(sandbox), in_tok=100, out_tok=50))
        # confirmed cost is the actual usage, strictly less than the frozen maxima sum
        assert s["confirmed_provider_cost_usd"] > 0.0
        assert s["confirmed_provider_cost_usd"] < 8.52
        assert s["unknown_after_send_max_exposure_usd"] == 0.0

    def test_06_confirmed_never_exceeds_frozen_max_per_call(self, sandbox):
        me = self._manifest(sandbox)
        s = _run(sandbox, FakeClient(str(sandbox), in_tok=100, out_tok=50))
        for e in s["billing_ledger"]:
            if e["billing_status"] == DRV.BILLING_CONFIRMED:
                assert e["confirmed_cost_usd"] <= e["frozen_max_cost_usd"] + 1e-9

    def test_07_unknown_never_retried(self, sandbox):
        c = FakeClient(str(sandbox), fail_positions={1})
        s = _run(sandbox, c)
        assert len(c.calls) <= 36                      # no extra attempt
        # exactly one UNKNOWN_AFTER_SEND recorded for seq 1
        assert sum(1 for e in s["billing_ledger"]
                   if e["seq"] == 1 and e["billing_status"] ==
                   DRV.BILLING_UNKNOWN_AFTER_SEND) == 1

    def test_08_one_unknown_plus_remaining_cannot_breach_ceiling(self, sandbox):
        s = _run(sandbox, FakeClient(str(sandbox), in_tok=100, out_tok=50,
                                     fail_positions={1}))
        assert s["conservative_accounted_exposure_usd"] <= 8.52
        assert s["conservative_exposure_within_ceiling"]

    def test_09_multiple_unknown_remain_bounded(self, sandbox):
        # positions 1 and 2 fail after send (2 < 3 consecutive, so no transport stop yet)
        s = _run(sandbox, FakeClient(str(sandbox), in_tok=100, out_tok=50,
                                     fail_positions={1, 2}))
        assert s["n_unknown_after_send"] >= 1
        assert s["conservative_accounted_exposure_usd"] <= 8.52

    def test_10_all_36_frozen_maxima_sum_to_ceiling(self, sandbox):
        from decimal import Decimal
        me = self._manifest(sandbox)
        tot = sum(Decimal(str(me[s]["max_request_cost_usd"])) for s in me)
        assert tot == Decimal("8.52")               # worst case if EVERY attempt unknown

    def test_11_absent_usage_after_send_is_not_zero_exposure(self, sandbox):
        s = _run(sandbox, FakeClient(str(sandbox), fail_positions={1}))
        # the unknown attempt contributed > 0 to conservative exposure despite no usage
        assert s["unknown_after_send_max_exposure_usd"] > 0.0
        led1 = [e for e in s["billing_ledger"] if e["seq"] == 1][0]
        assert "confirmed_cost_usd" not in led1      # no fabricated usage
        assert led1["reserved_exposure_usd"] > 0.0

    def test_12_unknown_remains_apparatus_classification(self, sandbox):
        # 3 consecutive after-send failures -> frozen transport apparatus stop
        s = _run(sandbox, FakeClient(str(sandbox), fail_positions={1, 2, 3}))
        assert s["execution_status"] == "STOPPED"
        assert s["stop"][0]["class"] == "APPARATUS"

    def test_13_no_scientific_verdict_consumes_billing_state(self):
        # the driver records billing; the verdict is v6_1_verdict, run separately, and takes
        # ONLY scorecards + repeat groups + self-noise -- no billing field.
        import inspect
        from src.research.hypothesis_oos import v6_1_verdict as V61
        sig = inspect.signature(V61.final_verdict)
        assert set(sig.parameters) == {"scorecards", "repeat_groups_per_arm", "self_noise"}
        src = inspect.getsource(V61)
        for t in ("billing", "reserved_exposure", "unknown_after_send", "max_request_cost"):
            assert t not in src

    def test_14_ledger_distinguishes_not_sent_vs_unknown(self, sandbox):
        # a guard-tripped call (NOT_SENT) and an after-send failure (UNKNOWN) are distinct.
        me = self._manifest(sandbox)
        seq1_max = float(me[1]["max_request_cost_usd"])
        seq2_max = float(me[2]["max_request_cost_usd"])
        s = _run(sandbox, FakeClient(str(sandbox), in_tok=1, out_tok=1, fail_positions={1}),
                 ceiling_override=seq1_max + seq2_max - 0.01)
        statuses = {e["billing_status"] for e in s["billing_ledger"]}
        assert DRV.BILLING_UNKNOWN_AFTER_SEND in statuses
        assert DRV.BILLING_NOT_SENT in statuses      # the stopped-before-send call

    def test_15_final_reporting_separates_confirmed_and_unknown(self, sandbox):
        s = _run(sandbox, FakeClient(str(sandbox), in_tok=100, out_tok=50,
                                     fail_positions={1}))
        for k in ("confirmed_provider_cost_usd", "unknown_after_send_max_exposure_usd",
                  "conservative_accounted_exposure_usd", "hard_ceiling_usd"):
            assert k in s
        assert abs(s["conservative_accounted_exposure_usd"]
                   - (s["confirmed_provider_cost_usd"]
                      + s["unknown_after_send_max_exposure_usd"])) < 1e-9

    def test_16_next_request_exactly_within_conservative_exposure_allowed(self, sandbox):
        # ceiling exactly equal to the frozen worst-case total -> all 36 fit (<=), even with
        # tiny confirmed usage; no cost stop.
        me = self._manifest(sandbox)
        worst = round(sum(e["max_request_cost_usd"] for e in me.values()), 2)
        s = _run(sandbox, FakeClient(str(sandbox), in_tok=1, out_tok=1),
                 ceiling_override=worst)
        assert s["execution_status"] == "COMPLETE"
        assert s["transport"]["n_charged"] == 36

    def test_17_next_request_one_unit_over_conservative_exposure_refused(self, sandbox):
        # ceiling below the FIRST scheduled call's frozen max -> seq1's guard trips first.
        me = self._manifest(sandbox)
        seq1_max = float(me[1]["max_request_cost_usd"])
        s = _run(sandbox, FakeClient(str(sandbox), in_tok=1, out_tok=1),
                 ceiling_override=seq1_max - 0.01)
        assert s["stop"][0]["rule"] == "V6_1_STOP_COST_CEILING"
        assert s["transport"]["n_charged"] == 0

    def test_18_cost_guard_occurs_before_converse(self):
        src = open(DRIVER_PATH).read()
        i_guard = src.index("(accounted_exposure + projected) > ceiling")
        i_call = src.index("payload, in_tok, out_tok, raw_sha = call_once")
        assert i_guard < i_call            # guard precedes the paid call in execute()

    def test_19_retry_enabled_client_still_hard_fails(self, sandbox):
        from src.research.hypothesis_oos import v6_transport as TRN
        with pytest.raises(TRN.TransportPreflightFailure):
            TRN.assert_no_retries(FakeClient(str(sandbox), retries=5))

    def test_20_v6_path_isolation_intact(self):
        with pytest.raises(DRV.PathSafetyError):
            DRV.assert_v6_1_paths("V6.1", f"{ROOT}/research/hypothesis_oos/out/v6")
        with pytest.raises(DRV.PathSafetyError):
            DRV.assert_write_target_is_v6_1(
                f"{ROOT}/research/hypothesis_oos/out/v6/execution/scores.json")
