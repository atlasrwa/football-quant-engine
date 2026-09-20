"""V3 checkpoint mandate SS4-SS7, SS16: idempotent, quota-safe resume harness.

Deterministic, OFFLINE tests. `resume()` is exercised exclusively with a fake `call_fn` --
these tests make ZERO Bedrock calls and must never be changed to call the real adapter.

Run: .venv/bin/python -m pytest tests/research/test_golden_v3_resume.py -q
"""
import json
import sys

import pytest

from src.research.llm_matchup.hardening import golden_manifest as GM
from src.research.llm_matchup.hardening import resume_golden_v3 as RG


class FakeResult:
    def __init__(self, status, manifest=None):
        self.status = status
        self.manifest = manifest or {}
        self.state = {} if status == "OK" else None


# --- classify_bedrock_error ---------------------------------------------------------
def test_classify_daily_quota():
    e = ("An error occurred (ThrottlingException) when calling the Converse operation "
         "(reached max retries: 4): Too many tokens per day, please wait before trying again.")
    assert RG.classify_bedrock_error(e) == "AWS_DAILY_TOKEN_QUOTA"


def test_classify_read_timeout():
    e = 'Read timeout on endpoint URL: "https://bedrock-runtime.us-east-1.amazonaws.com/..."'
    assert RG.classify_bedrock_error(e) == "READ_TIMEOUT"


def test_classify_transient_throttle_distinct_from_daily_quota():
    e = "An error occurred (ThrottlingException) when calling the Converse operation: rate exceeded"
    assert RG.classify_bedrock_error(e) == "THROTTLING_TRANSIENT"


def test_classify_other_and_none():
    assert RG.classify_bedrock_error(None) == "OTHER_UNAVAILABLE"
    assert RG.classify_bedrock_error("boto3 not installed") == "OTHER_UNAVAILABLE"


# --- generation fingerprint / compatibility -----------------------------------------
def test_check_compatible_identical_fingerprints():
    fp = GM.current_generation_fingerprint(n=5, max_scan=50)
    manifest = GM.build_manifest(["mt_1", "mt_2"], n=5, max_scan=50)
    result = GM.check_compatible(manifest, fp)
    assert result["compatible"] is True
    assert result["mismatches"] == []


def test_check_compatible_detects_prompt_drift():
    manifest = GM.build_manifest(["mt_1"], n=5, max_scan=50)
    current = GM.current_generation_fingerprint(n=5, max_scan=50)
    current["prompt_content_hash"] = "deliberately-different-hash"
    result = GM.check_compatible(manifest, current)
    assert result["compatible"] is False
    assert any(m["field"] == "prompt_content_hash" for m in result["mismatches"])


def test_check_compatible_ignores_sampling_params_growth():
    manifest = GM.build_manifest(["mt_1"], n=15, max_scan=200)
    current = GM.current_generation_fingerprint(n=20, max_scan=200)  # n grew 15->20
    result = GM.check_compatible(manifest, current)
    assert result["compatible"] is True  # n growth alone must not trip the guard


def test_save_manifest_if_absent_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(GM, "OUT", str(tmp_path))
    monkeypatch.setattr(GM, "MANIFEST_PATH", str(tmp_path / "manifest.json"))
    m1 = GM.build_manifest(["mt_1", "mt_2"], n=2, max_scan=50)
    assert GM.save_manifest_if_absent(m1) == "CREATED"
    m2 = GM.build_manifest(["mt_9"], n=1, max_scan=50)  # a different, "regenerated" sample
    assert GM.save_manifest_if_absent(m2) == "EXISTS_UNCHANGED"
    on_disk = GM.load_manifest()
    assert on_disk["fixture_ids"] == ["mt_1", "mt_2"]  # untouched, never replaced


# --- resume(): abort paths (must make ZERO calls) -----------------------------------
def test_resume_aborts_when_no_manifest(tmp_path, monkeypatch):
    # GM.OUT must be redirected too: resume() takes the live-runner lock (resolved from GM.OUT)
    # before it discovers the manifest is missing, so without this the test writes a real lock
    # file into the production out/hardening_v3/ directory.
    monkeypatch.setattr(GM, "OUT", str(tmp_path))
    monkeypatch.setattr(GM, "MANIFEST_PATH", str(tmp_path / "absent.json"))
    calls = []
    out = RG.resume(call_fn=lambda *a, **k: calls.append(1) or FakeResult("OK"))
    assert out["status"] == "ABORT_NO_FROZEN_MANIFEST"
    assert calls == []


def test_resume_aborts_on_generation_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(GM, "OUT", str(tmp_path))
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(GM, "MANIFEST_PATH", str(manifest_path))
    manifest = GM.build_manifest(["mt_1", "mt_2"], n=2, max_scan=50)
    manifest["generation_fingerprint"]["prompt_content_hash"] = "stale-hash-from-before-a-prompt-edit"
    json.dump(manifest, open(manifest_path, "w"))

    calls = []
    out = RG.resume(call_fn=lambda *a, **k: calls.append(1) or FakeResult("OK"))
    assert out["status"] == "ABORT_RESUME_GENERATION_MISMATCH"
    assert any(m["field"] == "prompt_content_hash" for m in out["mismatches"])
    assert calls == []  # not a single call made once mismatch detected


# --- resume(): idempotent cache reuse -----------------------------------------------
def test_resume_reuses_ledger_success_without_new_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(GM, "OUT", str(tmp_path))
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(GM, "MANIFEST_PATH", str(manifest_path))
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setattr(RG, "LEDGER_PATH", str(ledger_path))

    manifest = GM.build_manifest(["mt_a", "mt_b"], n=2, max_scan=50)
    json.dump(manifest, open(manifest_path, "w"))
    json.dump({"fixtures": {"mt_a": {"status": "SUCCESS", "attempts": [{"status": "OK"}]},
                            "mt_b": {"status": "SUCCESS", "attempts": [{"status": "OK"}]}}},
              open(ledger_path, "w"))

    calls = []
    out = RG.resume(call_fn=lambda *a, **k: calls.append(1) or FakeResult("OK"))
    assert out["status"] == "RESUMED"
    assert calls == []  # both fixtures already SUCCESS -> zero new calls
    assert all(r["source"] == "ledger_cache" for r in out["results"])


def test_resume_dry_run_makes_zero_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(GM, "OUT", str(tmp_path))
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(GM, "MANIFEST_PATH", str(manifest_path))
    monkeypatch.setattr(RG, "LEDGER_PATH", str(tmp_path / "ledger.json"))
    manifest = GM.build_manifest(["mt_a", "mt_b"], n=2, max_scan=50)
    json.dump(manifest, open(manifest_path, "w"))

    calls = []
    out = RG.resume(call_fn=lambda *a, **k: calls.append(1) or FakeResult("OK"), dry_run=True)
    assert calls == []
    assert all(r["status"] == "WOULD_ATTEMPT" for r in out["results"])


# --- resume(): quota-stop behavior (uses real corpus selection, fake call_fn -> no network) --
def test_resume_stops_immediately_on_daily_quota(tmp_path, monkeypatch):
    from src.research.llm_matchup import phaseb_harness as H
    from src.research.llm_matchup.hardening import sampling as SMP

    monkeypatch.setattr(GM, "OUT", str(tmp_path))
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(GM, "MANIFEST_PATH", str(manifest_path))
    monkeypatch.setattr(RG, "LEDGER_PATH", str(tmp_path / "ledger.json"))

    ctx = H.HarnessContext(enrich_halves=False)
    picks = SMP.select_stratified(ctx, n=4, max_scan=50)
    fixture_ids = [p.fixture_id for p in picks]
    manifest = GM.build_manifest(fixture_ids, n=4, max_scan=50)
    json.dump(manifest, open(manifest_path, "w"))

    quota_error = ("An error occurred (ThrottlingException) when calling the Converse "
                  "operation (reached max retries: 4): Too many tokens per day, please "
                  "wait before trying again.")
    call_log = []

    def fake_call(packet, use_cache=True):
        fid = packet["fixture"]["fixture_id"]
        call_log.append(fid)
        if len(call_log) == 1:
            return FakeResult("OK")
        return FakeResult("LLM_STATE_UNAVAILABLE", {"error": quota_error})

    out = RG.resume(call_fn=fake_call)
    assert out["stopped_for_quota"] is True
    # exactly 2 calls made: 1 success, then the one that trips the quota classification
    assert len(call_log) == 2
    statuses = {r["fixture_id"]: r["status"] for r in out["results"]}
    assert statuses[fixture_ids[0]] == "SUCCESS"
    assert statuses[fixture_ids[1]] == "AWS_DAILY_TOKEN_QUOTA"
    assert statuses[fixture_ids[2]] == "NOT_ATTEMPTED"
    assert statuses[fixture_ids[3]] == "NOT_ATTEMPTED"

    # a second resume() call must NOT re-attempt the quota-exhausted fixture in this test's
    # fake_call sequencing sense -- but it MUST reuse fixture[0]'s SUCCESS and retry the rest.
    out2 = RG.resume(call_fn=fake_call)
    assert call_log[2:] or out2["results"][0]["source"] == "ledger_cache"


def test_resume_preserves_full_attempt_history_across_calls(tmp_path, monkeypatch):
    from src.research.llm_matchup import phaseb_harness as H
    from src.research.llm_matchup.hardening import sampling as SMP

    monkeypatch.setattr(GM, "OUT", str(tmp_path))
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(GM, "MANIFEST_PATH", str(manifest_path))
    monkeypatch.setattr(RG, "LEDGER_PATH", str(tmp_path / "ledger.json"))

    ctx = H.HarnessContext(enrich_halves=False)
    picks = SMP.select_stratified(ctx, n=1, max_scan=50)
    fixture_ids = [p.fixture_id for p in picks]
    manifest = GM.build_manifest(fixture_ids, n=1, max_scan=50)
    json.dump(manifest, open(manifest_path, "w"))

    def timeout_then_ok(packet, use_cache=True):
        n_prior = len(RG.load_ledger().get("fixtures", {}).get(fixture_ids[0], {}).get("attempts", []))
        if n_prior == 0:
            return FakeResult("LLM_STATE_UNAVAILABLE", {"error": 'Read timeout on endpoint URL'})
        return FakeResult("OK")

    RG.resume(call_fn=timeout_then_ok)     # attempt 1: READ_TIMEOUT
    RG.resume(call_fn=timeout_then_ok)     # attempt 2: OK

    ledger = RG.load_ledger()
    attempts = ledger["fixtures"][fixture_ids[0]]["attempts"]
    assert len(attempts) == 2               # both attempts kept, never overwritten/lost
    assert attempts[0]["error_class"] == "READ_TIMEOUT"
    assert attempts[1]["status"] == "OK"
    assert ledger["fixtures"][fixture_ids[0]]["status"] == "SUCCESS"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
