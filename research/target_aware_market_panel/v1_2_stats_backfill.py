"""Resumable, stats-only acquisition for Target-Aware Market Panel V1.2.

Scientific scope is frozen by V1_2_STATS_BACKFILL_PLAN_V1.json. This runner:
- reads exactly the 4,994 fixture ids from the frozen discovery artifact;
- calls only /football/matches/{match_id}/stats;
- writes one immutable terminal wrapper per fixture (HTTP 200 or 404);
- never re-requests a fixture with a valid terminal wrapper;
- records every attempted provider call in an append-only ledger;
- performs no target settlement, market access, model fitting or OOS scoring.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.discovery.corpus import _load_env_for_thestats  # noqa: E402
from src.research.prospective.api_contract import ProspectiveClientConfig, resolve_api_key  # noqa: E402

OUT = ROOT / "research/target_aware_market_panel"
PLAN = OUT / "V1_2_STATS_BACKFILL_PLAN_V1.json"
DISCOVERY = OUT / "V1_2_BACKFILL_FIXTURE_DISCOVERY_V1.json"
CHAMPION = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")

PLAN_SHA256 = "751fde682b03ad568cd77925e2a87021ad0639f0a56b89a3f0e0b49202f0d03a"
DISCOVERY_SHA256 = "219d95d9a4c14a2bef4aaa8fa5b25ff9b2b52698343fd469b2967b8e0a94a4ac"
CHAMPION_SHA256 = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

RAW_ROOT = Path("/home/ubuntu/data/thestatsapi/v1_2_prehistory/stats_v1")
LEDGER = Path("/home/ubuntu/data/thestatsapi/v1_2_prehistory/stats_v1_attempts.jsonl")
PROGRESS = Path("/home/ubuntu/data/thestatsapi/v1_2_prehistory/stats_v1_progress.json")
BASE_URL = "https://api.thestatsapi.com/api"
TERMINAL_STATUSES = {200, 404}
def fsha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True, capture_output=True, text=True
    ).stdout.strip()


def utc_now(ts: float | None = None) -> str:
    if ts is None:
        ts = time.time()
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def append_ledger(record: dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    with open(LEDGER, "a") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def raw_path(match_id: str) -> Path:
    return RAW_ROOT / f"{match_id}.json"


def terminal_wrapper(match_id: str) -> dict[str, Any] | None:
    p = raw_path(match_id)
    if not p.exists():
        return None
    try:
        x = json.loads(p.read_text())
    except Exception:
        raise RuntimeError(f"CORRUPT_TERMINAL_WRAPPER:{match_id}")
    if x.get("match_id") != match_id or int(x.get("http_status", -1)) not in TERMINAL_STATUSES:
        raise RuntimeError(f"INVALID_TERMINAL_WRAPPER:{match_id}")
    if x.get("endpoint") != f"/football/matches/{match_id}/stats":
        raise RuntimeError(f"ENDPOINT_MISMATCH_TERMINAL_WRAPPER:{match_id}")
    return x


def attempt_counts() -> dict[str, int]:
    out: dict[str, int] = {}
    if not LEDGER.exists():
        return out
    for line in LEDGER.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("event") == "REQUEST_START":
            mid = str(rec["match_id"])
            out[mid] = out.get(mid, 0) + 1
    return out
def load_exact_ids() -> list[str]:
    d = json.loads(DISCOVERY.read_text())
    ids = sorted({mid for s in d["seasons"] for mid in s["fixture_ids"]})
    if len(ids) != 4994 or len(ids) != int(d["n_finished_fixtures"]):
        raise RuntimeError(f"EXACT_FIXTURE_SET_MISMATCH:{len(ids)}")
    return ids


def progress_doc(ids: list[str], *, new_calls: int, stop_reason: str | None,
                 last_rate: dict[str, Any] | None) -> dict[str, Any]:
    done_200 = done_404 = 0
    raw_hashes = {}
    for mid in ids:
        x = terminal_wrapper(mid)
        if x is None:
            continue
        status = int(x["http_status"])
        done_200 += status == 200
        done_404 += status == 404
        raw_hashes[mid] = fsha(raw_path(mid))
    return {
        "artifact_version": "target_aware_v1_2_stats_backfill_progress_v1",
        "source_plan_sha256": PLAN_SHA256,
        "source_fixture_discovery_sha256": DISCOVERY_SHA256,
        "n_exact_fixture_ids": len(ids),
        "n_terminal": done_200 + done_404,
        "n_http_200": done_200,
        "n_http_404": done_404,
        "n_unresolved": len(ids) - done_200 - done_404,
        "new_provider_calls_this_process": new_calls,
        "stop_reason": stop_reason,
        "last_rate_limit": last_rate,
        "raw_hashes_sha256": hashlib.sha256(
            json.dumps(raw_hashes, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "target_outcomes_read": False,
        "market_results_read": False,
        "model_fit": False,
        "oos_executed": False,
        "champion_sha256": fsha(CHAMPION),
        "updated_at_utc": utc_now(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authorized-head", required=True)
    ap.add_argument("--max-new-calls", type=int, default=None,
                    help="Operational process bound only; never changes frozen fixture universe")
    args = ap.parse_args()

    head = git("rev-parse", "HEAD")
    if head != args.authorized_head:
        raise SystemExit(f"HEAD_MISMATCH expected={args.authorized_head} actual={head}")
    if git("status", "--porcelain"):
        raise SystemExit("WORKTREE_NOT_CLEAN")
    if fsha(PLAN) != PLAN_SHA256 or fsha(DISCOVERY) != DISCOVERY_SHA256:
        raise SystemExit("FROZEN_INPUT_HASH_MISMATCH")
    if fsha(CHAMPION) != CHAMPION_SHA256:
        raise SystemExit("CHAMPION_HASH_MISMATCH")

    plan = json.loads(PLAN.read_text())
    ids = load_exact_ids()
    if int(plan["n_exact_fixture_ids"]) != len(ids):
        raise SystemExit("PLAN_FIXTURE_COUNT_MISMATCH")
    if int(plan["request_policy"]["hidden_client_retries"]) != 0:
        raise SystemExit("PLAN_RETRY_POLICY_MISMATCH")
    if int(plan["request_policy"]["max_process_attempts_per_unresolved_id"]) != 2:
        raise SystemExit("PLAN_ATTEMPT_POLICY_MISMATCH")
    interval = float(plan["request_policy"]["minimum_interval_seconds"])
    if interval != 1.0:
        raise SystemExit("PLAN_PACING_MISMATCH")
    _load_env_for_thestats()
    key = resolve_api_key()
    if not key:
        raise SystemExit("THESTATSAPI_KEY_UNAVAILABLE")
    try:
        import httpx
    except Exception as exc:
        raise SystemExit("HTTPX_UNAVAILABLE") from exc

    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    counts = attempt_counts()
    max_calls = len(ids) if args.max_new_calls is None else max(0, int(args.max_new_calls))
    new_calls = 0
    last_request_mono = 0.0
    last_rate = None
    stop_reason = None

    with httpx.Client(timeout=float(plan["request_policy"]["http_timeout_seconds"])) as client:
        for mid in ids:
            if terminal_wrapper(mid) is not None:
                continue
            if counts.get(mid, 0) >= int(plan["request_policy"]["max_process_attempts_per_unresolved_id"]):
                stop_reason = f"MAX_PROCESS_ATTEMPTS_EXHAUSTED:{mid}"
                break
            if new_calls >= max_calls:
                stop_reason = "PROCESS_CALL_BOUND_REACHED"
                break

            elapsed = time.monotonic() - last_request_mono
            if last_request_mono and elapsed < interval:
                time.sleep(interval - elapsed)

            attempt_no = counts.get(mid, 0) + 1
            start_ts = time.time()
            append_ledger({
                "event": "REQUEST_START",
                "match_id": mid,
                "attempt_no": attempt_no,
                "endpoint": f"/football/matches/{mid}/stats",
                "started_at_unix": start_ts,
                "started_at_utc": utc_now(start_ts),
                "runner_head": head,
            })
            last_request_mono = time.monotonic()
            new_calls += 1
            counts[mid] = attempt_no
            try:
                resp = client.get(
                    f"{BASE_URL}/football/matches/{mid}/stats",
                    headers={"Authorization": f"Bearer {key}"},
                )
            except Exception as exc:
                append_ledger({
                    "event": "REQUEST_ERROR",
                    "match_id": mid,
                    "attempt_no": attempt_no,
                    "error_type": type(exc).__name__,
                    "ended_at_utc": utc_now(),
                })
                stop_reason = f"TRANSPORT_ERROR:{mid}:{type(exc).__name__}"
                break

            rate = {
                "rate_limit": resp.headers.get("X-RateLimit-Limit"),
                "rate_remaining": resp.headers.get("X-RateLimit-Remaining"),
                "rate_reset": resp.headers.get("X-RateLimit-Reset"),
                "monthly_limit": resp.headers.get("X-Monthly-Quota-Limit"),
                "monthly_remaining": resp.headers.get("X-Monthly-Quota-Remaining"),
                "monthly_reset": resp.headers.get("X-Monthly-Quota-Reset"),
            }
            last_rate = rate
            status = int(resp.status_code)
            if status not in TERMINAL_STATUSES:
                append_ledger({
                    "event": "REQUEST_ERROR",
                    "match_id": mid,
                    "attempt_no": attempt_no,
                    "http_status": status,
                    "rate_limit": rate,
                    "ended_at_utc": utc_now(),
                })
                stop_reason = f"NONTERMINAL_HTTP_STATUS:{mid}:{status}"
                break
            payload = None
            if status == 200:
                try:
                    payload = resp.json()
                except Exception:
                    append_ledger({
                        "event": "REQUEST_ERROR",
                        "match_id": mid,
                        "attempt_no": attempt_no,
                        "http_status": status,
                        "error_type": "INVALID_JSON",
                        "ended_at_utc": utc_now(),
                    })
                    stop_reason = f"INVALID_JSON:{mid}"
                    break
                if not isinstance(payload, dict):
                    stop_reason = f"NONOBJECT_PAYLOAD:{mid}"
                    append_ledger({
                        "event": "REQUEST_ERROR", "match_id": mid, "attempt_no": attempt_no,
                        "http_status": status, "error_type": "NONOBJECT_PAYLOAD",
                        "ended_at_utc": utc_now(),
                    })
                    break

            end_ts = time.time()
            wrapper = {
                "provider": "thestatsapi",
                "match_id": mid,
                "endpoint": f"/football/matches/{mid}/stats",
                "retrieved_at_unix": end_ts,
                "retrieved_at_utc": utc_now(end_ts),
                "http_status": status,
                "payload": payload,
            }
            atomic_json(raw_path(mid), wrapper)
            raw_sha = fsha(raw_path(mid))
            append_ledger({
                "event": "REQUEST_TERMINAL",
                "match_id": mid,
                "attempt_no": attempt_no,
                "http_status": status,
                "raw_path": str(raw_path(mid)),
                "raw_sha256": raw_sha,
                "rate_limit": rate,
                "ended_at_unix": end_ts,
                "ended_at_utc": utc_now(end_ts),
            })

    doc = progress_doc(ids, new_calls=new_calls, stop_reason=stop_reason, last_rate=last_rate)
    atomic_json(PROGRESS, doc)
    print(json.dumps({
        "status": "V1_2_STATS_BACKFILL_PROGRESS",
        "authorized_head": head,
        "n_exact_fixture_ids": doc["n_exact_fixture_ids"],
        "n_terminal": doc["n_terminal"],
        "n_http_200": doc["n_http_200"],
        "n_http_404": doc["n_http_404"],
        "n_unresolved": doc["n_unresolved"],
        "new_provider_calls_this_process": new_calls,
        "stop_reason": stop_reason,
        "last_rate_limit": last_rate,
        "target_outcomes_read": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
