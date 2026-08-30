"""
In-play reconstruction — fetcher + reconciliation layer (Step 2 gate).

For a selected batch of finished matches:
  1. FETCH (cache-first) /timeline and /shotmap into data/thestatsapi/inplay/.
     /stats is already cached in data/thestatsapi/championship/ (free).
  2. RECONSTRUCT full-match per-side totals from the event log + shotmap.
  3. RECONCILE against the official /stats per-side totals for every
     reconstructable variable, with EXPLICIT orientation (transposition) check.
  4. QUARANTINE on: coverage != full, per-variable mismatch, home/away
     transposition, or score-vs-eventlog contradiction.
  5. Report usable rate + failure breakdown by cause and league.

Odds are out of scope — no odds endpoint touched.
Reconstruction only — no live polling.

Cache-key conventions (existing):
  Championship /stats -> stats_<mid>
  LaLiga2      /stats -> laliga2_stats_<mid>
  Ligue2       /stats -> ligue2_stats_<mid>
New timeline/shotmap cached to inplay dir as recon_timeline_<mid>, recon_shotmap_<mid>.

Usage:
  python inplay_recon.py select        # build balanced batch -> _recon_batch.json
  python inplay_recon.py run [maxreq]   # fetch + reconcile the batch
"""
import json
import glob
import os
import re
import sys
from collections import defaultdict, Counter

sys.path.insert(0, "/home/ubuntu/scripts")
import thestatsapi_client as base

CH = "/home/ubuntu/data/thestatsapi/championship"
IP = "/home/ubuntu/data/thestatsapi/inplay"
os.makedirs(IP, exist_ok=True)

# Route NEW fetches to the inplay cache dir; usage log/budget shared there.
base.CACHE_DIR = IP
base.USAGE_LOG = f"{IP}/_usage_log.jsonl"
base.BUDGET_STATE = f"{IP}/_budget_state.json"
ALLOW = (200, 400, 404, 409, 422, 501)

BATCH = f"{IP}/_recon_batch.json"
RESULT = f"{IP}/_recon_step2_result.json"

# League -> (stats cache-key prefix, list of season_ids to sample)
LEAGUES = {
    "Championship": ("stats", ["sn_3064530", "sn_2930227"]),
    "LaLiga2": ("laliga2_stats", ["sn_8425423", "sn_8437950"]),
    "Ligue2": ("ligue2_stats", ["sn_3057202", "sn_3064056"]),
}
PER_SLICE = 17  # ~17 per (league,season) * 6 slices = ~102 matches


def stats_key(league, mid):
    prefix = LEAGUES[league][0]
    return f"{prefix}_{mid}" if prefix != "stats" else f"stats_{mid}"


def stats_path(league, mid):
    return f"{CH}/{stats_key(league, mid)}.json"


def load_fixtures():
    fx = {}
    for f in glob.glob(f"{CH}/fixtures_sn_*_p*.json") + glob.glob(f"{CH}/*_matches_sn_*_p*.json"):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        rows = d.get("data", d)
        if isinstance(rows, dict):
            rows = rows.get("data", [])
        for m in (rows or []):
            if isinstance(m, dict) and "id" in m:
                fx[m["id"]] = m
    return fx


def which_league(mid):
    for league in LEAGUES:
        if os.path.exists(stats_path(league, mid)):
            return league
    return None


# ─────────────────────────── selection ───────────────────────────

def select():
    """Balanced batch: per (league, season) take PER_SLICE matches that already
    have /stats cached, spread across the season calendar, balancing team
    appearances as much as possible."""
    fx = load_fixtures()
    batch = []
    for league, (prefix, seasons) in LEAGUES.items():
        # matches with stats cached, indexed by season
        cached_ids = set()
        for f in glob.glob(stats_path(league, "mt_*")):
            m = re.search(r"(mt_\d+)", f)
            if m:
                cached_ids.add(m.group(1))
        for season in seasons:
            cand = [mid for mid in cached_ids
                    if (fx.get(mid) or {}).get("season_id") == season and fx.get(mid, {}).get("utc_date")]
            cand.sort(key=lambda mid: fx[mid]["utc_date"])  # chronological
            if not cand:
                continue
            # even spread across the calendar + team-balance greedy
            picks, team_count = [], Counter()
            # stride sampling for calendar spread
            stride = max(1, len(cand) // (PER_SLICE * 2))
            pool = cand[::stride] or cand
            for mid in pool:
                if len(picks) >= PER_SLICE:
                    break
                m = fx[mid]
                h = (m.get("home_team") or {}).get("id"); a = (m.get("away_team") or {}).get("id")
                # prefer matches that keep team counts balanced
                picks.append(mid); team_count[h] += 1; team_count[a] += 1
            for mid in picks:
                m = fx[mid]
                batch.append({
                    "mid": mid, "league": league, "season": season,
                    "home_id": (m.get("home_team") or {}).get("id"),
                    "away_id": (m.get("away_team") or {}).get("id"),
                    "home": (m.get("home_team") or {}).get("name"),
                    "away": (m.get("away_team") or {}).get("name"),
                    "utc_date": m.get("utc_date"),
                    "score": m.get("score", {}),
                })
    json.dump(batch, open(BATCH, "w"), indent=2)
    # balance report
    tc = Counter()
    for b in batch:
        tc[b["home_id"]] += 1; tc[b["away_id"]] += 1
    counts = sorted(tc.values())
    import statistics
    print(f"selected {len(batch)} matches across {len(LEAGUES)} leagues x 2 seasons")
    by = Counter((b['league'], b['season']) for b in batch)
    for k, v in sorted(by.items()):
        print(f"   {k}: {v}")
    print(f"team appearances: min={counts[0]} max={counts[-1]} median={int(statistics.median(counts))} "
          f"(n_teams={len(tc)})")
    print(f"wrote {BATCH}")


# ─────────────────────────── reconstruction ───────────────────────────

# taxonomy normalization
GOAL_TYPES = {"goal", "penalty_scored", "own_goal"}
YELLOW_TYPES = {"yellow_card"}
SECOND_YELLOW_TYPES = {"second_yellow", "second_yellow_card", "yellow_red_card"}
RED_TYPES = {"red_card"}
CORNER_TYPES = {"corner_kick", "corner"}
FOUL_TYPES = {"foul"}
SHOT_ON_TYPES = {"shot_on_target"}
SHOT_OFF_TYPES = {"shot_off_target"}
SHOT_BLOCKED_TYPES = {"shot_blocked"}
# total_shots = all shot subtypes + goals (a goal is a shot that scored)
SHOT_ANY = SHOT_ON_TYPES | SHOT_OFF_TYPES | SHOT_BLOCKED_TYPES | GOAL_TYPES


def official_side(stats, group, side):
    try:
        return stats["overview"][group]["all"][side]
    except Exception:
        return None


def reconcile_match(mid, meta, timeline, shotmap, stats):
    """Return a reconciliation record for one match."""
    rec = {"mid": mid, "league": meta["league"], "season": meta["season"],
           "quarantined": False, "reasons": [], "types_seen": []}

    events = timeline.get("events") if isinstance(timeline, dict) else timeline
    coverage = timeline.get("coverage") if isinstance(timeline, dict) else None
    rec["coverage"] = coverage
    if coverage != "full":
        rec["quarantined"] = True
        rec["reasons"].append(f"coverage={coverage}")
        return rec
    if not events:
        rec["quarantined"] = True
        rec["reasons"].append("no_events")
        return rec

    # team side map from stats-side (home/away) via the fixture score/home ids in meta
    # timeline events carry team.id; map to home/away using fixture team ids
    side_of = {meta.get("home_id"): "home", meta.get("away_id"): "away"}

    types_seen = Counter(e.get("type") for e in events)
    rec["types_seen"] = dict(types_seen)

    # accumulate per-side
    acc = defaultdict(lambda: defaultdict(int))
    for e in events:
        t = e.get("type")
        side = side_of.get((e.get("team") or {}).get("id"))
        if side is None:
            continue
        if t in GOAL_TYPES:
            acc[side]["goals"] += 1
        if t in YELLOW_TYPES:
            acc[side]["yellow_cards"] += 1
        if t in SECOND_YELLOW_TYPES:
            acc[side]["yellow_cards"] += 1  # second yellow counts as a yellow in stats
            acc[side]["red_cards"] += 1     # and a red
        if t in RED_TYPES:
            acc[side]["red_cards"] += 1
        if t in CORNER_TYPES:
            acc[side]["corners"] += 1
        if t in FOUL_TYPES:
            acc[side]["fouls"] += 1
        if t in SHOT_ON_TYPES:
            acc[side]["shots_on_target"] += 1
        if t in SHOT_ANY:
            acc[side]["total_shots"] += 1

    # xG + SOT via shotmap (per team_id)
    shots = shotmap if isinstance(shotmap, list) else (shotmap or {}).get("shots") or (shotmap or {}).get("shotmap") or []
    xg = defaultdict(float); sog_sm = defaultdict(int)
    for s in shots:
        side = side_of.get(s.get("team_id"))
        if side is None:
            continue
        xg[side] += float(s.get("expected_goals") or 0.0)
        if s.get("is_on_target"):
            sog_sm[side] += 1

    recon = {
        "goals": {s: acc[s]["goals"] for s in ("home", "away")},
        "corners": {s: acc[s]["corners"] for s in ("home", "away")},
        "yellow_cards": {s: acc[s]["yellow_cards"] for s in ("home", "away")},
        "red_cards": {s: acc[s]["red_cards"] for s in ("home", "away")},
        "fouls": {s: acc[s]["fouls"] for s in ("home", "away")},
        "total_shots": {s: acc[s]["total_shots"] for s in ("home", "away")},
        "shots_on_target": {s: sog_sm[s] for s in ("home", "away")},
        "xg": {s: round(xg[s], 2) for s in ("home", "away")},
    }
    rec["recon"] = recon

    # official per-side
    GRP = {"corners": "corner_kicks", "yellow_cards": "yellow_cards", "red_cards": "red_cards",
           "fouls": "fouls", "total_shots": "total_shots", "shots_on_target": "shots_on_target",
           "xg": "expected_goals"}
    off = {}
    for var, grp in GRP.items():
        off[var] = {s: official_side(stats, grp, s) for s in ("home", "away")}
    rec["official"] = off

    # ── reconciliation: exact for counts, tolerance for xG ──
    XG_TOL = 0.30
    per_var = {}
    transposed_vars = []
    for var in GRP:
        r = recon[var]; o = off[var]
        if o["home"] is None or o["away"] is None:
            per_var[var] = "no_official"
            continue
        if var == "xg":
            match_direct = abs(r["home"] - o["home"]) <= XG_TOL and abs(r["away"] - o["away"]) <= XG_TOL
            match_swap = abs(r["home"] - o["away"]) <= XG_TOL and abs(r["away"] - o["home"]) <= XG_TOL
        else:
            match_direct = r["home"] == o["home"] and r["away"] == o["away"]
            match_swap = r["home"] == o["away"] and r["away"] == o["home"]
        if match_direct:
            per_var[var] = "ok"
        elif match_swap and o["home"] != o["away"]:
            per_var[var] = "transposed"
            transposed_vars.append(var)
        else:
            per_var[var] = "mismatch"
    rec["per_var"] = per_var

    # score-vs-eventlog contradiction: fixture final score vs reconstructed goals
    sc = meta.get("score", {}) or {}
    fin_h, fin_a = sc.get("home"), sc.get("away")
    tl_h, tl_a = recon["goals"]["home"], recon["goals"]["away"]
    score_ok = (fin_h is None or (fin_h == tl_h and fin_a == tl_a))
    rec["score_check"] = {"fixture": [fin_h, fin_a], "timeline": [tl_h, tl_a], "ok": score_ok}

    # quarantine decision
    if transposed_vars:
        rec["quarantined"] = True
        rec["reasons"].append("transposition:" + ",".join(transposed_vars))
    mism = [v for v, s in per_var.items() if s == "mismatch"]
    if mism:
        rec["quarantined"] = True
        rec["reasons"].append("mismatch:" + ",".join(mism))
    if not score_ok:
        rec["quarantined"] = True
        rec["reasons"].append("score_vs_eventlog")

    return rec


def run(maxreq=250):
    base.MAX_LIVE_REQUESTS = int(maxreq)
    os.environ["THESTATS_MAX_REQUESTS"] = str(maxreq)
    batch = json.load(open(BATCH))
    print(f"reconciling {len(batch)} matches (cap {maxreq} live requests)")

    results = []
    fetch_fail = 0
    for i, b in enumerate(batch):
        mid = b["mid"]; league = b["league"]
        # stats (already cached, read directly from championship dir)
        sp = stats_path(league, mid)
        if not os.path.exists(sp):
            fetch_fail += 1
            results.append({"mid": mid, "league": league, "season": b["season"],
                            "quarantined": True, "reasons": ["no_stats_cached"]})
            continue
        stats = json.load(open(sp)).get("data", {})

        # fetch timeline + shotmap (cache-first into inplay dir)
        dtl, mtl = base.get_json(f"/football/matches/{mid}/timeline",
                                 cache_key=f"recon_timeline_{mid}", allow_status=ALLOW)
        dsm, msm = base.get_json(f"/football/matches/{mid}/shotmap",
                                 cache_key=f"recon_shotmap_{mid}", allow_status=ALLOW)
        if mtl.get("http_status") not in (200,) or dtl is None:
            results.append({"mid": mid, "league": league, "season": b["season"],
                            "quarantined": True, "reasons": [f"timeline_http_{mtl.get('http_status')}"]})
            continue
        timeline = dtl.get("data", dtl)
        shotmap = (dsm or {}).get("data", dsm) if dsm else []
        rec = reconcile_match(mid, b, timeline, shotmap, stats)
        results.append(rec)
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(batch)} done  budget_remaining={base.budget_snapshot().get('last_monthly_remaining')}")

    # ── aggregate ──
    n = len(results)
    usable = [r for r in results if not r.get("quarantined")]
    quar = [r for r in results if r.get("quarantined")]
    cause = Counter()
    for r in quar:
        for reason in r.get("reasons", []):
            cause[reason.split(":")[0]] += 1
    by_league = defaultdict(lambda: {"n": 0, "usable": 0})
    for r in results:
        by_league[r["league"]]["n"] += 1
        if not r.get("quarantined"):
            by_league[r["league"]]["usable"] += 1
    # all event types seen across corpus (taxonomy documentation)
    all_types = Counter()
    for r in results:
        for t, c in (r.get("types_seen") or {}).items():
            all_types[t] += c

    summary = {
        "n_matches": n,
        "usable": len(usable),
        "usable_rate": round(len(usable) / n, 4) if n else 0,
        "quarantined": len(quar),
        "quarantine_causes": dict(cause),
        "by_league": {k: {**v, "usable_rate": round(v["usable"] / v["n"], 3) if v["n"] else 0}
                      for k, v in by_league.items()},
        "event_types_seen": dict(all_types.most_common()),
        "live_requests_this_run": base.live_requests_made(),
        "budget": base.budget_snapshot(),
    }
    json.dump({"summary": summary, "results": results}, open(RESULT, "w"), indent=2, default=str)

    print("\n" + "=" * 70)
    print("STEP 2 — RECONCILIATION RESULT")
    print("=" * 70)
    print(f"matches: {n}   usable: {len(usable)}   usable_rate: {summary['usable_rate']*100:.1f}%")
    print(f"quarantine causes: {dict(cause)}")
    print("by league:")
    for k, v in summary["by_league"].items():
        print(f"   {k}: {v['usable']}/{v['n']} usable ({v['usable_rate']*100:.0f}%)")
    print(f"event types seen: {dict(all_types.most_common())}")
    print(f"\nlive requests this run: {base.live_requests_made()}  "
          f"budget remaining: {base.budget_snapshot().get('last_monthly_remaining')}")
    print(f"wrote {RESULT}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "select"
    if cmd == "select":
        select()
    elif cmd == "run":
        run(int(sys.argv[2]) if len(sys.argv) > 2 else 250)
