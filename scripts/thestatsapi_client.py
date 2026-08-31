"""
Cached TheStatsAPI client — Championship slice.

Design rules (per task brief):
  * Bearer auth from THESTATS_API_KEY env (never printed).
  * Every raw response saved UNMODIFIED to data/thestatsapi/championship/ before use.
  * Cache-first: if a cache file exists it is returned and NO request is made
    (idempotent re-runs cost zero budget; never overwrites an existing cache file).
  * Quota tracking: reads X-RateLimit-* and X-Monthly-Quota-* from every response
    and records them to a running usage log so budget is always visible.
  * Abort on any non-200 (except documented 404/empty which callers handle) rather
    than silently retrying and burning budget. Respects Retry-After on 429.
  * A hard local request cap (default 425) so a bug cannot blow the trial budget.

This module makes NO calls on import. Callers invoke get_json(path, params, cache_key).
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone

BASE_URL = "https://api.thestatsapi.com/api"
CACHE_DIR = "/home/ubuntu/data/thestatsapi/championship"
USAGE_LOG = f"{CACHE_DIR}/_usage_log.jsonl"
BUDGET_STATE = f"{CACHE_DIR}/_budget_state.json"

# Hard local safety cap on the number of *live* requests this process will make.
# Overridable via env THESTATS_MAX_REQUESTS. The trial is ~425; keep a margin.
MAX_LIVE_REQUESTS = int(os.environ.get("THESTATS_MAX_REQUESTS", "425"))

_API_KEY = os.environ.get("THESTATS_API_KEY")

# in-process counter of live requests actually sent
_live_requests_made = 0

# Proactive pacing: the trial burst limit is 12 requests/minute. Space live requests
# at least MIN_INTERVAL seconds apart to avoid 429 churn. Overridable via env.
MIN_INTERVAL_SEC = float(os.environ.get("THESTATS_MIN_INTERVAL", "5.2"))
_last_request_ts = [0.0]


def _pace():
    now = time.time()
    wait = MIN_INTERVAL_SEC - (now - _last_request_ts[0])
    if wait > 0:
        time.sleep(wait)
    _last_request_ts[0] = time.time()


def _load_budget_state():
    if os.path.exists(BUDGET_STATE):
        with open(BUDGET_STATE) as f:
            return json.load(f)
    return {"total_live_requests": 0, "last_monthly_remaining": None,
            "last_ratelimit_remaining": None,
            # API-authoritative monthly quota fields (from x-monthly-quota-* headers).
            # These, not total_live_requests (a lifetime local counter), are the source
            # of truth for the low-quota alert.
            "last_monthly_limit": None, "last_monthly_reset": None,
            "monthly_quota_updated_at": None, "updated_at": None}


def _save_budget_state(state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(BUDGET_STATE, "w") as f:
        json.dump(state, f, indent=2)


def _log_usage(entry):
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    with open(USAGE_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def cache_path(cache_key):
    return f"{CACHE_DIR}/{cache_key}.json"


def is_cached(cache_key):
    return os.path.exists(cache_path(cache_key))


def get_json(path, params=None, cache_key=None, allow_status=(200,)):
    """Fetch BASE_URL+path with query params. Cache-first by cache_key.

    Returns (data_dict, meta) where meta carries http_status, from_cache, and
    the quota headers seen. Aborts (SystemExit) on unexpected status or when the
    local request cap would be exceeded. 404 is returned to the caller (data=None)
    only if 404 in allow_status.
    """
    global _live_requests_made
    if cache_key is None:
        raise ValueError("cache_key is required (all responses are cached)")

    cpath = cache_path(cache_key)
    if os.path.exists(cpath):
        with open(cpath) as f:
            data = json.load(f)
        return data, {"from_cache": True, "http_status": 200, "cache_key": cache_key}

    if _API_KEY is None:
        print("ABORT: THESTATS_API_KEY not set in environment.", file=sys.stderr)
        sys.exit(2)

    if _live_requests_made >= MAX_LIVE_REQUESTS:
        print(f"ABORT: local live-request cap {MAX_LIVE_REQUESTS} reached "
              f"(made {_live_requests_made}). Not spending more budget.",
              file=sys.stderr)
        sys.exit(3)

    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {_API_KEY}",
        "Accept": "application/json",
        "User-Agent": "fqe-championship-slice/1.0",
    })

    _pace()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8", errors="replace")
        headers = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
    except Exception as e:
        print(f"ABORT: network error on {path}: {e}", file=sys.stderr)
        sys.exit(4)

    _live_requests_made += 1

    # Record quota/rate-limit headers
    quota = {
        "ratelimit_limit": headers.get("x-ratelimit-limit"),
        "ratelimit_remaining": headers.get("x-ratelimit-remaining"),
        "ratelimit_reset": headers.get("x-ratelimit-reset"),
        "monthly_limit": headers.get("x-monthly-quota-limit"),
        "monthly_remaining": headers.get("x-monthly-quota-remaining"),
        "monthly_reset": headers.get("x-monthly-quota-reset"),
    }
    state = _load_budget_state()
    state["total_live_requests"] += 1
    if quota["monthly_remaining"] is not None:
        state["last_monthly_remaining"] = quota["monthly_remaining"]
    if quota["ratelimit_remaining"] is not None:
        state["last_ratelimit_remaining"] = quota["ratelimit_remaining"]
    # Record the API-authoritative monthly quota window (limit + reset) so the
    # heartbeat's low-quota alert reads the server's own accounting, not the local
    # lifetime request counter (which drifts from the API's monthly reset cycle).
    if quota["monthly_limit"] is not None:
        state["last_monthly_limit"] = quota["monthly_limit"]
    if quota["monthly_reset"] is not None:
        state["last_monthly_reset"] = quota["monthly_reset"]
    if quota["monthly_remaining"] is not None or quota["monthly_reset"] is not None:
        state["monthly_quota_updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_budget_state(state)
    _log_usage({"path": path, "params": params or {}, "cache_key": cache_key,
                "http_status": status, "quota": quota})

    # 429 handling: respect Retry-After once, then abort if still limited.
    if status == 429:
        retry_after = headers.get("retry-after")
        print(f"429 rate/quota limited on {path}. Retry-After={retry_after}. "
              f"quota={quota}", file=sys.stderr)
        if retry_after and retry_after.isdigit() and int(retry_after) <= 90:
            time.sleep(int(retry_after) + 1)
            # one retry
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    status = resp.status
                    body = resp.read().decode("utf-8")
                    headers = {k.lower(): v for k, v in resp.headers.items()}
                _live_requests_made += 1
            except urllib.error.HTTPError as e:
                status = e.code
                body = e.read().decode("utf-8", errors="replace")
        if status == 429:
            print("ABORT: still 429 after retry. Stopping to preserve budget.",
                  file=sys.stderr)
            sys.exit(5)

    if status not in allow_status:
        if status == 404 and 404 in allow_status:
            pass
        else:
            print(f"ABORT: unexpected HTTP {status} on {path}: {body[:400]}",
                  file=sys.stderr)
            sys.exit(6)

    if status == 404:
        return None, {"from_cache": False, "http_status": 404, "quota": quota,
                      "cache_key": cache_key}

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(f"ABORT: non-JSON response on {path}: {body[:300]}", file=sys.stderr)
        sys.exit(7)

    # Save raw response unmodified
    with open(cpath, "w") as f:
        f.write(body)

    return data, {"from_cache": False, "http_status": status, "quota": quota,
                  "cache_key": cache_key}


def live_requests_made():
    return _live_requests_made


def budget_snapshot():
    return _load_budget_state()
