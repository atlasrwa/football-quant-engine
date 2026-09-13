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
from src.research.llm_matchup.hardening import sampling as SMP
from src.research.llm_matchup.hardening import neutralize_v3 as NZ3
from src.research.llm_matchup.hardening import golden_manifest as GM

OUT = GM.OUT
LEDGER_PATH = os.path.join(OUT, "golden_v3_execution_ledger.json")


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
    os.makedirs(OUT, exist_ok=True)
    json.dump(ledger, open(LEDGER_PATH, "w"), indent=2, default=str)


def resume(call_fn=None, use_cache: bool = True, dry_run: bool = False) -> dict:
    """Resume the frozen golden_v3 batch fixture-by-fixture, in manifest order.

    `call_fn(neutral_packet, use_cache=...) -> LLMResult` defaults to
    `adapter_v4.analyze_matchup_v4` and is overridable ONLY for offline testing -- production
    callers should never pass this.
    """
    manifest = GM.load_manifest()
    if manifest is None:
        return {"status": "ABORT_NO_FROZEN_MANIFEST"}

    n = manifest["generation_fingerprint"]["sampling_params"]["n"]
    max_scan = manifest["generation_fingerprint"]["sampling_params"]["max_scan"]
    current_fp = GM.current_generation_fingerprint(n=n, max_scan=max_scan)
    compat = GM.check_compatible(manifest, current_fp)
    if not compat["compatible"]:
        return {"status": "ABORT_RESUME_GENERATION_MISMATCH", "mismatches": compat["mismatches"]}

    if call_fn is None:
        from src.research.llm_matchup.hardening import adapter_v4 as A4
        call_fn = A4.analyze_matchup_v4

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
        error_class = None if result.status == "OK" else classify_bedrock_error(
            result.manifest.get("error"))
        attempt = {"unix": int(time.time()), "status": result.status,
                  "cache_hit": result.manifest.get("cache_hit"), "error_class": error_class}
        entry["attempts"].append(attempt)

        if result.status == "OK":
            entry["status"] = "SUCCESS"
            results.append({"fixture_id": fid, "status": "SUCCESS", "source": "new_call"})
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
