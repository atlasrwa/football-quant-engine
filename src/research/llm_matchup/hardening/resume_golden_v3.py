"""Idempotent, quota-safe resume harness for the golden_v3 smoke batch
(V3 checkpoint mandate SS4, SS6, SS7).

This module makes NO Bedrock calls on import and makes none unless `resume(dry_run=False)`
is explicitly invoked with live capacity available. It is exercised entirely by
`tests/research/test_golden_v3_resume.py` via an injected mock `call_fn` -- never the real
adapter -- so this file itself never spends tokens as a side effect of testing.

Behavior:
  * ABORT_RESUME_GENERATION_MISMATCH -- if the current code/version fingerprint does not
    match the frozen manifest's, resume refuses to run at all (SS5).
  * Per-fixture idempotency -- a fixture already marked SUCCESS in the execution ledger is
    reused with zero new calls (SS4.B/C).
  * Quota stop -- the instant a call is classified AWS_DAILY_TOKEN_QUOTA, every remaining
    not-yet-attempted fixture is recorded NOT_ATTEMPTED (never FAILED) and no further calls
    are made in that resume() invocation (SS6). Ordinary transient throttling is recorded
    but does not itself halt the batch.
  * Read-timeout handling -- recorded as its own distinct status, never silently retried
    within the same resume() call, and the ledger keeps the FULL attempt history per fixture
    (not just the latest) so an old timeout is never lost or double-counted against a later
    successful attempt (SS7).
"""
from __future__ import annotations
import os
import json
import time

from src.research.llm_matchup import phaseb_harness as H
from src.research.llm_matchup.bedrock_adapter import check_bedrock_capability, IncompatibleBotoError
from src.research.llm_matchup.hardening import atomic_io as AIO
from src.research.llm_matchup.hardening import run_lock as RL
from src.research.llm_matchup.hardening import sampling as SMP
from src.research.llm_matchup.hardening import neutralize_v3 as NZ3
from src.research.llm_matchup.hardening import golden_manifest as GM
from src.research.llm_matchup.hardening import versions_v3 as V3

OUT = GM.OUT
LEDGER_PATH = os.path.join(OUT, "golden_v3_execution_ledger.json")


def _lock_path() -> str:
    """Resolved at CALL TIME from `GM.OUT`, not at import time -- same reasoning as
    `golden_manifest.load_manifest`'s `manifest_path` default: binding this in a module-level
    constant would snapshot the production path at import and silently defeat
    `monkeypatch.setattr(GM, "OUT", ...)`, which is how the offline resume tests isolate
    themselves. Without this, every existing `dry_run=False` test would acquire a REAL lock
    file under the production `out/hardening_v3/` directory as an untracked side effect."""
    return os.path.join(GM.OUT, ".golden_v3_live_runner.lock")


def classify_bedrock_error(error: str | None) -> str:
    """Canonical, conservative classification of an UNAVAILABLE error string (SS6, SS7).
    Never conflates ordinary transient throttling with a genuine daily-quota exhaustion
    unless the message explicitly names it."""
    if not error:
        return "OTHER_UNAVAILABLE"
    e = error.lower()
    if "throttlingexception" in e and "too many tokens per day" in e:
        return "AWS_DAILY_TOKEN_QUOTA"
    if "read timeout" in e or "timed out" in e:
        return "READ_TIMEOUT"
    if "throttlingexception" in e:
        return "THROTTLING_TRANSIENT"
    return "OTHER_UNAVAILABLE"


def load_ledger() -> dict:
    if os.path.exists(LEDGER_PATH):
        return json.load(open(LEDGER_PATH))
    return {"study": "golden_v3_execution_ledger", "fixtures": {}}


def save_ledger(ledger: dict) -> None:
    AIO.atomic_write_json(LEDGER_PATH, ledger)


def resume(call_fn=None, use_cache: bool = True, dry_run: bool = False) -> dict:
    """Resume the frozen golden_v3 batch fixture-by-fixture, in manifest order.

    `call_fn(neutral_packet, use_cache=...) -> LLMResult` defaults to
    `adapter_v4.analyze_matchup_v4` and is overridable ONLY for offline testing -- production
    callers should never pass this.

    Live calls (`dry_run=False`) are guarded by TWO fail-closed gates before any Bedrock call
    is attempted: an exclusive process lock (ABORT_ALREADY_RUNNING if another live runner
    already holds it -- a duplicate `resume()` ran concurrently against this exact ledger
    once already) and a Bedrock-capability probe (ABORT_INCOMPATIBLE_BOTO3 if the active
    Python environment's boto3 cannot make a Converse call at all -- this also happened once,
    silently producing 16 misleading per-fixture UNAVAILABLE records for one environment bug).
    """
    if not dry_run:
        try:
            lock = RL.acquire(_lock_path())
            lock.__enter__()
        except RL.AlreadyRunningError as e:
            return {"status": "ABORT_ALREADY_RUNNING", "detail": str(e)}
        try:
            return _resume_locked(call_fn, use_cache, dry_run)
        finally:
            lock.__exit__(None, None, None)
    return _resume_locked(call_fn, use_cache, dry_run)


def _resume_locked(call_fn, use_cache: bool, dry_run: bool) -> dict:
    manifest = GM.load_manifest()
    if manifest is None:
        return {"status": "ABORT_NO_FROZEN_MANIFEST"}

    # Fail-closed cross-generation guard (checkpoint SS2). This module is the SONNET 4.5 arm's
    # resume harness and owns the 4.5 ledger. It must refuse any manifest belonging to a
    # different scientific generation (e.g. LLM_MATCHUP_V3_SONNET46), so a 4.6 manifest can
    # never cause a 4.5 fixture to be marked complete, and vice versa.
    manifest_gen = manifest.get("generation_id")
    if manifest_gen is not None and manifest_gen != V3.GENERATION_ID:
        return {"status": "ABORT_GENERATION_ID_MISMATCH",
                "expected_generation_id": V3.GENERATION_ID,
                "manifest_generation_id": manifest_gen}

    n = manifest["generation_fingerprint"]["sampling_params"]["n"]
    max_scan = manifest["generation_fingerprint"]["sampling_params"]["max_scan"]
    current_fp = GM.current_generation_fingerprint(n=n, max_scan=max_scan)
    compat = GM.check_compatible(manifest, current_fp)
    if not compat["compatible"]:
        return {"status": "ABORT_RESUME_GENERATION_MISMATCH", "mismatches": compat["mismatches"]}

    if call_fn is None:
        from src.research.llm_matchup.hardening import adapter_v4 as A4
        call_fn = A4.analyze_matchup_v4

    if not dry_run:
        try:
            check_bedrock_capability(region=V3.DEFAULT_BEDROCK_REGION)
        except IncompatibleBotoError as e:
            return {"status": "ABORT_INCOMPATIBLE_BOTO3", "detail": str(e)}

    ledger = load_ledger()
    fixtures_ledger = ledger.setdefault("fixtures", {})
    ledger["fixture_manifest_hash"] = manifest["fixture_manifest_hash"]

    ctx = None
    picks_by_id = None
    stopped_for_quota = False
    results = []

    for fid in manifest["fixture_ids"]:
        entry = fixtures_ledger.setdefault(fid, {"attempts": [], "status": "NOT_ATTEMPTED"})

        if entry["status"] == "SUCCESS":
            results.append({"fixture_id": fid, "status": "SUCCESS", "source": "ledger_cache"})
            continue
        if stopped_for_quota:
            entry["status"] = "NOT_ATTEMPTED"
            results.append({"fixture_id": fid, "status": "NOT_ATTEMPTED", "source": "quota_stop"})
            continue
        if dry_run:
            results.append({"fixture_id": fid, "status": "WOULD_ATTEMPT"})
            continue

        if ctx is None:
            ctx = H.HarnessContext(enrich_halves=False)
            picks_by_id = {p.fixture_id: p for p in SMP.select_stratified(ctx, n=n, max_scan=max_scan)}
        pick = picks_by_id[fid]
        source_packet = ctx.build_packet(pick.candidate, include_formation=True, projected=True)
        neutral = NZ3.neutralize_for_llm_v2(source_packet)

        result = call_fn(neutral, use_cache=use_cache)
        # LLM_STATE_REJECTED is the validator refusing a genuine model response (e.g. a
        # hallucinated evidence-id citation) -- a SCIENTIFIC outcome, not an infrastructure
        # failure. It must never be run through classify_bedrock_error (which is only
        # meaningful for the exception/UNAVAILABLE path and would misreport it as
        # OTHER_UNAVAILABLE, hiding a real validator attrition event as a fake infra blip).
        if result.status == "LLM_STATE_REJECTED":
            error_class = "LLM_STATE_REJECTED"
        elif result.status == "OK":
            error_class = None
        else:
            error_class = classify_bedrock_error(result.manifest.get("error"))
        attempt = {"unix": int(time.time()), "status": result.status,
                  "cache_hit": result.manifest.get("cache_hit"), "error_class": error_class,
                  "reject_field": result.manifest.get("reject_field"),
                  "reject_reason": result.manifest.get("reject_reason")}
        entry["attempts"].append(attempt)

        if result.status == "OK":
            entry["status"] = "SUCCESS"
            results.append({"fixture_id": fid, "status": "SUCCESS", "source": "new_call"})
        elif result.status == "LLM_STATE_REJECTED":
            entry["status"] = "LLM_STATE_REJECTED"
            results.append({"fixture_id": fid, "status": "LLM_STATE_REJECTED",
                            "reject_reason": result.manifest.get("reject_reason")})
        elif error_class == "AWS_DAILY_TOKEN_QUOTA":
            entry["status"] = "AWS_DAILY_TOKEN_QUOTA"
            stopped_for_quota = True
            results.append({"fixture_id": fid, "status": "AWS_DAILY_TOKEN_QUOTA"})
        else:
            entry["status"] = error_class
            results.append({"fixture_id": fid, "status": error_class})

    save_ledger(ledger)
    return {"status": "RESUMED", "dry_run": dry_run,
           "stopped_for_quota": stopped_for_quota, "results": results}
