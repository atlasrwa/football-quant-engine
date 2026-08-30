"""
Heatmap spatial validation-batch fetcher (Step 5) — GATED, costs quota.

Discipline (mirrors scripts/inplay_recon.py):
  - Cache-first via thestatsapi_client.get_json (idempotent re-runs cost zero).
  - Dedicated cache/log/budget dir so this batch is isolated and auditable.
  - PROBE a single match first to confirm the /heatmap endpoint exists and
    returns usable spatial data BEFORE any batch pull.
  - Hard local cap; prints monthly_remaining each call.
  - Every reconstructed per-side aggregate must later pass the home/away
    transposition check before use (the corner-transposition defect class).

Usage:
  python3 scripts/heatmap_fetch.py probe        # 1 call, endpoint discovery
  python3 scripts/heatmap_fetch.py batch N       # up to N matches across >=2 leagues
"""
from __future__ import annotations
import sys, os, glob, json, time

sys.path.insert(0, '/home/ubuntu/scripts')
sys.path.insert(0, '/home/ubuntu')
import thestatsapi_client as base

HEATMAP_DIR = '/home/ubuntu/data/thestatsapi/heatmap'
os.makedirs(HEATMAP_DIR, exist_ok=True)
# isolate this batch's budget/log/cache
base.CACHE_DIR = HEATMAP_DIR
base.USAGE_LOG = os.path.join(HEATMAP_DIR, '_usage_log.jsonl')
base.BUDGET_STATE = os.path.join(HEATMAP_DIR, '_budget_state.json')

# candidate endpoint paths to probe (we do NOT know a priori that /heatmap exists)
CANDIDATE_PATHS = [
    "/football/matches/{mid}/heatmap",
    "/football/matches/{mid}/heatmaps",
    "/football/matches/{mid}/positions",
    "/football/matches/{mid}/touchmap",
]


def strip_id(fn):
    b = os.path.basename(fn)
    for p in ('laliga2_', 'ligue2_'):
        b = b.replace(p, '')
    return b.replace('stats_', '').replace('.json', '')  # -> mt_...


def target_matches(n):
    """Pick matches across >=2 leagues that already have cached stats (so we can
    reconcile spatial vs known outcomes without extra stats calls)."""
    champ = sorted(glob.glob('/home/ubuntu/data/thestatsapi/championship/stats_mt_*.json'))
    ll2 = sorted(glob.glob('/home/ubuntu/data/thestatsapi/championship/laliga2_stats_mt_*.json'))
    lig2 = sorted(glob.glob('/home/ubuntu/data/thestatsapi/championship/ligue2_stats_mt_*.json'))
    out = []
    per = max(1, n // 3)
    for grp in (champ, ll2, lig2):
        for f in grp[:per]:
            out.append(strip_id(f))
    return out[:n]


def probe():
    mid = target_matches(1)[0]
    print(f"Probing heatmap endpoints on {mid} (monthly_remaining before: "
          f"{base.budget_snapshot().get('last_monthly_remaining')})")
    found = None
    for tmpl in CANDIDATE_PATHS:
        path = tmpl.format(mid=mid)
        try:
            data, meta = base.get_json(path, cache_key=f"probe_{tmpl.split('/')[-1]}_{mid}",
                                       allow_status=(200, 400, 404))
        except SystemExit as e:
            print(f"  {path}: aborted ({e})")
            continue
        status = meta.get('http_status') if isinstance(meta, dict) else '?'
        has = bool(data) and status == 200
        print(f"  {path}: status={status} usable={has}")
        if has:
            found = (path, data)
            break
    print(f"monthly_remaining after: {base.budget_snapshot().get('last_monthly_remaining')}; "
          f"live_requests_this_batch: {base.live_requests_made()}")
    if found:
        path, data = found
        print(f"\nFOUND heatmap-like endpoint: {path}")
        print("Top-level keys:", list(data.keys())[:20] if isinstance(data, dict) else type(data))
        with open(os.path.join(HEATMAP_DIR, '_probe_result.json'), 'w') as f:
            json.dump({'path': path, 'sample_keys': list(data.keys()) if isinstance(data, dict) else None,
                       'sample': data}, f, indent=2, default=str)
    else:
        print("\nNO heatmap endpoint found among candidates. Do NOT batch.")
        with open(os.path.join(HEATMAP_DIR, '_probe_result.json'), 'w') as f:
            json.dump({'path': None, 'note': 'no heatmap endpoint; candidates all non-200/empty'}, f, indent=2)
    return found


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'probe'
    if cmd == 'probe':
        probe()
    elif cmd == 'batch':
        print("Batch is gated on a successful probe + directional validation. "
              "Run probe first; batch logic is enabled only if probe finds a usable endpoint.")
