#!/usr/bin/env python3
"""On-demand fixture research and uncertainty-aware EV engine.

This is the richer request-time layer discussed for individual fixtures. It does NOT
fit or select a new model for the requested match. It:

1. resolves the fixture and validated provider crosswalk;
2. builds a strict point-in-time, two-complete-season evidence snapshot for both teams;
3. uses immutable local FootyStats history, falling back to the quota-capped
   TheStatsAPI client only when required history is genuinely absent;
4. applies the frozen Pilot C market models (saved hyperparameters; no retune);
5. compares both OVER/YES and UNDER/NO probabilities with versioned multi-book prices;
6. subtracts a conservative calibration/history uncertainty buffer and returns either
   CANDIDATE or NO OPPORTUNITY;
7. optionally commits the pre-kickoff research prediction to its own manual-research
   ledger, structurally separate from Pilot C.

Heatmaps are explicitly reported unavailable: the repository probed TheStatsAPI
/heatmap, /heatmaps, /positions and /touchmap routes and found no usable payload.
Unavailable spatial evidence is never imputed or described as observed.

Pilot C is untouched. This script writes only under data/fixture_research/ and to
fixture_research_{commitments,reveals}.jsonl when --commit is requested.

Usage:
  python scripts/fixture_ev_engine.py --fixture-id mt_466259566
  python scripts/fixture_ev_engine.py --fixture-id mt_466259566 --commit
  python scripts/fixture_ev_engine.py --fixture-id mt_466259566 --json
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import shutil
import sys
import time
from collections import defaultdict
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

# Environment for TheStatsAPI fallback.
ENV_PATH = Path("/home/ubuntu/.env")
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import numpy as np
from sklearn.linear_model import LogisticRegression

import pilotC_forward_predict as fp
import pilotC_stat_mixer as mix
import manual_predict as manual
from src.research.forward.attestation_ledger import AttestationLedger, LedgerTamperError

ROOT = Path("/home/ubuntu")
CORPUS = ROOT / "data/discovery/corpus"
CH = ROOT / "data/thestatsapi/championship"
TS_CACHE = ROOT / "data/thestatsapi/cache"
FIXTURE_LIST = CH / "_pilotC_fixture_list.json"
CROSSWALK = ROOT / "data/mapping/team_crosswalk.json"
MODEL_REPORT = ROOT / "data/discovery/pilotC_stat_mixer.json"
RESEARCH_ROOT = ROOT / "data/fixture_research"
RESEARCH_COMMIT_LEDGER = ROOT / "data/forward/fixture_research_commitments.jsonl"
RESEARCH_REVEAL_LEDGER = ROOT / "data/forward/fixture_research_reveals.jsonl"
RESEARCH_MODEL_CACHE = RESEARCH_ROOT / "model_cache"
PUBLIC_RECEIPT_ROOT = ROOT / "data/attestations/fixture_research"

CELLS = [("goals", 1.5), ("goals", 2.5), ("goals", 3.5),
         ("corners", 8.5), ("corners", 9.5), ("corners", 10.5),
         ("cards", 3.5), ("cards", 4.5), ("btts", None)]
BOOKS = ["betfair-exchange", "pinnacle", "bet365"]

# Safety / decision policy. All can be overridden, but defaults are intentionally
# conservative: most efficient-market fixtures should produce NO OPPORTUNITY.
HISTORY_SEASONS = 2
EXPECTED_EPL_SEASON_MATCHES = 380
MAX_HISTORY_REQUESTS = int(os.environ.get("FIXTURE_EV_HISTORY_CAP", "80"))
MAX_ODDS_REQUESTS = int(os.environ.get("FIXTURE_EV_ODDS_CAP", "3"))
ODDS_FRESH_MINUTES = int(os.environ.get("FIXTURE_EV_ODDS_FRESH_MINUTES", "30"))
MIN_HISTORY_MATCHES = int(os.environ.get("FIXTURE_EV_MIN_HISTORY", "30"))
MIN_FEATURE_SUPPORT = float(os.environ.get("FIXTURE_EV_MIN_FEATURE_SUPPORT", "0.80"))
MIN_RAW_EDGE_PP = float(os.environ.get("FIXTURE_EV_MIN_EDGE_PP", "3.0"))
MIN_EV_PCT = float(os.environ.get("FIXTURE_EV_MIN_EV_PCT", "2.0"))
COMMISSION_BUFFER_PP = float(os.environ.get("FIXTURE_EV_COMMISSION_BUFFER_PP", "0.5"))
MAX_REFERENCE_OVERROUND = float(os.environ.get("FIXTURE_EV_MAX_OVERROUND", "0.04"))
UNCERTAINTY_Z = float(os.environ.get("FIXTURE_EV_UNCERTAINTY_Z", "1.2816"))  # 80%
LOCAL_DIAG_MIN_N = int(os.environ.get("FIXTURE_EV_LOCAL_DIAG_MIN_N", "20"))
LOCAL_DIAG_MIN_BSS = float(os.environ.get("FIXTURE_EV_LOCAL_DIAG_MIN_BSS", "-10.0"))

CAVEAT = ("A single fixture demonstrates nothing about edge. A CANDIDATE means the "
          "predeclared uncertainty and price gates passed; it is not proof the model "
          "or market is right. Only a complete, prospectively settled sample can test that.")

# Two complete EPL seasons immediately preceding the target 2026/27 fixture. The
# manifest is authoritative; aliases here avoid relying on filename ordering.
KNOWN_EPL_SEASONS = {
    "12325": {"label": "2024/25", "thestats_id": "sn_3057848"},
    "15050": {"label": "2025/26", "thestats_id": "sn_6125938"},
}

# Evidence summaries. These are descriptive inputs, not adaptively selected model
# features. The frozen model uses mix.POOLS/mix.match_features exactly as before.
SUMMARY_STATS = {
    "goals": ("homeGoalCount", "awayGoalCount"),
    "xg": ("team_a_xg", "team_b_xg"),
    "shots": ("team_a_shots", "team_b_shots"),
    "shots_on_target": ("team_a_shotsOnTarget", "team_b_shotsOnTarget"),
    "possession": ("team_a_possession", "team_b_possession"),
    "corners": ("team_a_corners", "team_b_corners"),
    "yellow_cards": ("team_a_yellow_cards", "team_b_yellow_cards"),
    "fouls": ("team_a_fouls", "team_b_fouls"),
    "attacks": ("team_a_attacks", "team_b_attacks"),
    "dangerous_attacks": ("team_a_dangerous_attacks", "team_b_dangerous_attacks"),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def numeric(v):
    try:
        x = float(v)
        return x if x >= 0 else None
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _team_aliases() -> dict[str, str]:
    """High-confidence provider aliases -> canonical FootyStats team name."""
    aliases = {}
    try:
        data = json.loads(CROSSWALK.read_text())
        for rows in data.get("leagues", {}).values():
            for row in rows:
                if float(row.get("confidence", 0)) < 0.95:
                    continue
                canonical = str(row.get("footystats_name", "")).strip()
                for name in (row.get("footystats_name"), row.get("thestats_name")):
                    if name:
                        aliases[str(name).strip().casefold()] = canonical.casefold()
    except Exception:
        pass
    return aliases


def canonical_team_name(name) -> str:
    raw = str(name or "").strip().casefold()
    return _team_aliases().get(raw, raw)


def fixture_identity(m: dict):
    """Cross-provider identity: canonical teams + kickoff minute + final score.

    FootyStats integer IDs and TheStatsAPI mt_* IDs are not comparable. High-confidence
    crosswalk aliases (for example AFC Bournemouth/Bournemouth) are canonicalized before
    identity construction; minute precision tolerates timestamp formatting differences.
    """
    d = numeric(m.get("date_unix")) or 0
    return (canonical_team_name(m.get("home_name")), canonical_team_name(m.get("away_name")),
            int(d // 60), m.get("homeGoalCount"), m.get("awayGoalCount"))


def ensure_pre_kickoff(kickoff_unix: float, phase: str) -> None:
    if time.time() >= float(kickoff_unix):
        raise ValueError(f"fixture crossed kickoff during {phase}; refusing to use/publish prices that cannot be proven pre-kickoff")


def resolve_fixture(fixture_id: str) -> dict:
    if not FIXTURE_LIST.exists():
        raise RuntimeError(f"fixture universe missing: {FIXTURE_LIST}")
    row = json.loads(FIXTURE_LIST.read_text()).get("meta", {}).get(fixture_id)
    if not row:
        raise ValueError(f"fixture {fixture_id} is not in {FIXTURE_LIST}")
    out = dict(row)
    out["fixture_id"] = fixture_id
    out["kickoff_unix"] = float(out.get("ts") or 0)
    out["kickoff_iso"] = datetime.fromtimestamp(out["kickoff_unix"], timezone.utc).isoformat()
    return out


def validated_crosswalk(home: str, away: str) -> dict:
    data = json.loads(CROSSWALK.read_text())
    rows = data.get("leagues", {}).get("England Premier League", [])
    by_name = {r["footystats_name"]: r for r in rows}
    out = {}
    for team in (home, away):
        row = by_name.get(team)
        if not row or float(row.get("confidence", 0)) < 0.95:
            raise ValueError(f"no validated high-confidence crosswalk for {team!r}")
        out[team] = row
    return out


def _load_season_pages(season_id: str) -> list[dict]:
    rows = []
    pattern = str(CORPUS / f"league-matches_*season_id:_ {season_id}*.json")
    # Existing filenames do not have a space; explicit glob is less fragile.
    files = glob.glob(str(CORPUS / f"league-matches_*season_id:_{season_id}*.json"))
    for path in sorted(files):
        try:
            rows.extend(json.loads(Path(path).read_text()).get("data", []))
        except Exception:
            continue
    return rows


def load_two_season_history(home: str, away: str, cutoff: float) -> tuple[list[dict], dict]:
    """Load complete local FootyStats history strictly before cutoff.

    If either team's required two-season history is absent, hydrate missing history via
    TheStatsAPI (bounded, cache-first), adapt supported fields, and merge it. The
    current target match is never requested or consumed.
    """
    all_rows = []
    season_counts = {}
    missing_seasons = []
    for sid, meta in KNOWN_EPL_SEASONS.items():
        rows = _load_season_pages(sid)
        season_counts[sid] = len(rows)
        # A single non-empty page is not a complete season. EPL has 380 fixtures;
        # anything below that triggers the cache-first TheStatsAPI completion path.
        if len(rows) < EXPECTED_EPL_SEASON_MATCHES:
            missing_seasons.append((sid, {**meta, "cached_match_count": len(rows),
                                          "expected_match_count": EXPECTED_EPL_SEASON_MATCHES}))
        all_rows.extend(rows)

    fallback = {"used": False, "live_requests": 0, "missing_seasons": [s for s, _ in missing_seasons],
                "note": None}
    if missing_seasons:
        hydrated, info = hydrate_history_from_thestats(home, away, cutoff, missing_seasons)
        all_rows.extend(hydrated)
        fallback.update(info)

    # Strict information cutoff and target-team filter. Deduplicate provider overlap by
    # stable provider id when possible, otherwise identity/date/score tuple.
    seen = set(); selected = []
    for m in all_rows:
        d = numeric(m.get("date_unix"))
        if d is None or not d < cutoff:
            continue
        if home not in (m.get("home_name"), m.get("away_name")) and \
           away not in (m.get("home_name"), m.get("away_name")):
            continue
        key = fixture_identity(m)
        if key in seen:
            continue
        seen.add(key); selected.append(m)
    selected.sort(key=lambda x: x["date_unix"])
    return selected, {"season_page_counts": season_counts, "fallback": fallback,
                      "strict_cutoff_unix": cutoff, "latest_history_unix":
                      max((m["date_unix"] for m in selected), default=None)}


def _find_cached_stats(mid: str) -> Path | None:
    patterns = [TS_CACHE / f"stats_{mid}.json", TS_CACHE / f"stats_mt_{mid}.json",
                CH / f"stats_{mid}.json", CH / f"stats_mt_{mid}.json",
                CH / f"*_stats_{mid}.json", CH / f"*_stats_mt_{mid}.json"]
    for p in patterns:
        matches = glob.glob(str(p))
        if matches:
            return Path(matches[0])
    return None


def _stats_cell(stats: dict, section: str, field: str):
    node = (stats.get(section) or {}).get(field) if isinstance(stats.get(section), dict) else None
    allv = node.get("all") if isinstance(node, dict) else None
    if not isinstance(allv, dict):
        return None, None
    return allv.get("home"), allv.get("away")


def adapt_thestats_fixture(fx: dict, stats_payload: dict) -> dict:
    """Adapt supported TheStatsAPI history to the FootyStats-shaped model schema.

    Unsupported fields remain -1; they are never proxied. The frozen model's existing
    median-imputation handles isolated misses, and feature support is reported/gated.
    """
    dt = datetime.fromisoformat(str(fx["utc_date"]).replace("Z", "+00:00"))
    h = fx.get("home_team") or {}; a = fx.get("away_team") or {}; score = fx.get("score") or {}
    stats = (stats_payload or {}).get("data", stats_payload or {})
    rec = {"id": fx.get("id"), "date_unix": dt.timestamp(),
           "home_name": h.get("name"), "away_name": a.get("name"),
           "homeGoalCount": score.get("home"), "awayGoalCount": score.get("away")}
    if rec["homeGoalCount"] is not None and rec["awayGoalCount"] is not None:
        rec["totalGoalCount"] = rec["homeGoalCount"] + rec["awayGoalCount"]
    mapping = {
        "xg": ("overview", "expected_goals"), "shots": ("overview", "total_shots"),
        "shotsOnTarget": ("overview", "shots_on_target"),
        "possession": ("overview", "ball_possession"), "corners": ("overview", "corner_kicks"),
        "yellow_cards": ("overview", "yellow_cards"), "red_cards": ("overview", "red_cards"),
        "fouls": ("overview", "fouls"), "shotsOffTarget": ("shots", "shots_off_target"),
    }
    for name, (sec, fld) in mapping.items():
        hv, av = _stats_cell(stats, sec, fld)
        rec[f"team_a_{name}"] = hv if hv is not None else -1
        rec[f"team_b_{name}"] = av if av is not None else -1
    for name in ("attacks", "dangerous_attacks", "freekicks", "throwins"):
        rec[f"team_a_{name}"] = rec[f"team_b_{name}"] = -1
    ya, yb = numeric(rec.get("team_a_yellow_cards")), numeric(rec.get("team_b_yellow_cards"))
    ra, rb = numeric(rec.get("team_a_red_cards")), numeric(rec.get("team_b_red_cards"))
    rec["team_a_cards_num"] = (ya + (ra or 0)) if ya is not None else -1
    rec["team_b_cards_num"] = (yb + (rb or 0)) if yb is not None else -1
    rec["_source"] = "thestatsapi_fallback"
    return rec


def hydrate_history_from_thestats(home: str, away: str, cutoff: float,
                                   missing_seasons: list[tuple[str, dict]]) -> tuple[list[dict], dict]:
    """Cache-first fallback for genuinely absent FootyStats history.

    Fetches only finished fixtures and only /stats rows strictly before cutoff, with a
    hard MAX_HISTORY_REQUESTS live cap. Existing caches under BOTH TheStats roots are
    checked before spending quota. This function is normally zero-call for EPL targets.
    """
    import thestatsapi_client as api
    before = api.live_requests_made()
    # Per-stage ceiling: earlier fixture/history calls cannot consume the odds budget,
    # and this stage cannot spend more than MAX_HISTORY_REQUESTS from its own start.
    api.MAX_LIVE_REQUESTS = before + MAX_HISTORY_REQUESTS
    errors = []; all_fixtures = {}
    cross = validated_crosswalk(home, away)
    home_id, away_id = cross[home]["thestats_id"], cross[away]["thestats_id"]
    ids = {home_id, away_id}

    for _, smeta in missing_seasons:
        sid = smeta["thestats_id"]
        fixtures = []
        # Prefer already-local fixture pages in either root.
        candidates = list(TS_CACHE.glob(f"matches_comp_3039_{sid}_p*.json"))
        candidates += list(CH.glob(f"research_matches_comp_3039_{sid}_p*.json"))
        for p in sorted(candidates):
            try: fixtures.extend(json.loads(p.read_text()).get("data", []))
            except Exception: pass
        if len({x.get('id') for x in fixtures if x.get('id')}) < EXPECTED_EPL_SEASON_MATCHES:
            # Complete all pages rather than treating one non-empty page as a season.
            for page in range(1, 5):
                try:
                    data, _ = api.get_json("/football/matches",
                        params={"competition_id": "comp_3039", "season_id": sid,
                                "stage": "regular", "status": "finished",
                                "per_page": 100, "page": page},
                        cache_key=f"research_matches_comp_3039_{sid}_p{page}",
                        allow_status=(200, 404, 422))
                    batch = (data or {}).get("data", [])
                    fixtures.extend(batch)
                    if len(batch) < 100: break
                except SystemExit:
                    errors.append("request cap reached fetching fixture pages"); break
        for fx in fixtures:
            if fx.get("id"):
                all_fixtures[fx["id"]] = fx

    # Fetch only the newest minimum sample required for each team, not every historical
    # match in two seasons. With four fixture pages/season this is at most 8 + 60 live
    # calls for two unrelated teams, below the default 80-call cold-cache cap.
    eligible = []
    for fx in all_fixtures.values():
        try:
            d = datetime.fromisoformat(str(fx.get("utc_date", "")).replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        h = (fx.get("home_team") or {}).get("id"); a = (fx.get("away_team") or {}).get("id")
        if d < cutoff and ({h, a} & ids):
            eligible.append((d, fx))
    eligible.sort(key=lambda x: x[0], reverse=True)
    selected = []; needed = {home_id: 0, away_id: 0}
    for _, fx in eligible:
        involved = ids & {(fx.get("home_team") or {}).get("id"),
                          (fx.get("away_team") or {}).get("id")}
        if any(needed[i] < MIN_HISTORY_MATCHES for i in involved):
            selected.append(fx)
            for i in involved: needed[i] += 1
        if all(n >= MIN_HISTORY_MATCHES for n in needed.values()):
            break

    adapted = []
    for fx in sorted(selected, key=lambda x: x.get("utc_date", "")):
        mid = fx.get("id"); cached = _find_cached_stats(mid)
        try:
            if cached:
                payload = json.loads(cached.read_text())
            else:
                payload, _ = api.get_json(f"/football/matches/{mid}/stats",
                                           cache_key=f"research_stats_{mid}",
                                           allow_status=(200, 404, 422))
            adapted.append(adapt_thestats_fixture(fx, payload or {}))
        except SystemExit:
            errors.append("request cap reached fetching stats"); break
        except Exception as e:
            errors.append(f"{mid}: {type(e).__name__}: {str(e)[:80]}")
    return adapted, {"used": True, "live_requests": api.live_requests_made() - before,
                     "missing_seasons": [s for s, _ in missing_seasons], "errors": errors,
                     "planned_team_fixture_counts": needed,
                     "selected_stats_fixtures": len(selected),
                     "note": "TheStatsAPI supplied only real cache misses; unsupported raw fields remain missing."}


def _team_rows(history: list[dict], team: str) -> list[tuple[dict, bool]]:
    return [(m, m.get("home_name") == team) for m in history
            if team in (m.get("home_name"), m.get("away_name"))]


def _own_opp(m: dict, is_home: bool, pair: tuple[str, str]):
    own = numeric(m.get(pair[0] if is_home else pair[1]))
    opp = numeric(m.get(pair[1] if is_home else pair[0]))
    return own, opp


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def summarize_team(history: list[dict], team: str) -> dict:
    rows = _team_rows(history, team)
    out = {"matches": len(rows), "windows": {}, "home_matches": sum(h for _, h in rows),
           "away_matches": sum(not h for _, h in rows)}
    for label, size in (("last5", 5), ("last10", 10), ("two_seasons", None)):
        part = rows[-size:] if size else rows
        stats = {}
        for name, pair in SUMMARY_STATS.items():
            own, opp = [], []
            for m, is_home in part:
                a, b = _own_opp(m, is_home, pair); own.append(a); opp.append(b)
            stats[name] = {"for": _mean(own), "against": _mean(opp),
                           "coverage": round(sum(v is not None for v in own) / len(part), 3) if part else 0}
        out["windows"][label] = {"matches": len(part), "stats": stats}
    return out


def supported_context_counts(history: list[dict], teams: tuple[str, str]) -> dict:
    """Count rows with real statistical support, excluding score-only/empty fallbacks."""
    out = {}
    for team in teams:
        n = 0
        for m, is_home in _team_rows(history, team):
            present = 0
            for pair in SUMMARY_STATS.values():
                own, opp = _own_opp(m, is_home, pair)
                present += own is not None and opp is not None
            if present / len(SUMMARY_STATS) >= 0.70:
                n += 1
        out[team] = n
    return out


def merge_inference_history(canonical: list[dict], request_history: list[dict]) -> list[dict]:
    """Merge API-hydrated cache misses into inference features without refitting.

    Models are fitted on canonical history only. This merged list is used solely by
    match_features/predict_one, ensuring a genuine cache miss actually feeds the engine
    while keeping coefficients and hyperparameters frozen.
    """
    merged = list(canonical); seen = {fixture_identity(m) for m in canonical}
    for m in request_history:
        key = fixture_identity(m)
        if key not in seen:
            merged.append(m); seen.add(key)
    merged.sort(key=lambda m: m.get("date_unix", 0))
    return merged


def historical_market_rates(history: list[dict], home: str, away: str) -> dict:
    """Descriptive two-team rates only; never used to fit/select the model."""
    relevant = [m for m in history if home in (m.get("home_name"), m.get("away_name")) or
                away in (m.get("home_name"), m.get("away_name"))]
    out = {}
    for market, line in CELLS:
        ys = [mix.outcome(m, market, line) for m in relevant]
        ys = [y for y in ys if y is not None]
        out[f"{market}@{line}"] = {"n": len(ys), "empirical_rate": round(sum(ys)/len(ys), 4) if ys else None}
    return out


def capture_odds(fixture_id: str, request_dir: Path, refresh: bool = False,
                 kickoff_unix: float | None = None) -> tuple[dict, dict]:
    """Get current multi-book odds, preserving immutable timestamped snapshots.

    Uses a recent cached response at zero cost; otherwise TheStatsAPI is called with a
    time-bucketed cache key so an old price is never overwritten. Raw source bodies are
    copied into this request's source directory and hashed.
    """
    import thestatsapi_client as api
    request_dir.mkdir(parents=True, exist_ok=True)
    if kickoff_unix is not None:
        ensure_pre_kickoff(kickoff_unix, "odds capture start")
    now = time.time(); live_before = api.live_requests_made()
    # Independent per-stage ceiling; history hydration cannot consume this allowance.
    api.MAX_LIVE_REQUESTS = live_before + MAX_ODDS_REQUESTS
    raw = {}; sources = []
    bucket = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + f"-{time.time_ns()}"
    for book in BOOKS:
        if kickoff_unix is not None:
            ensure_pre_kickoff(kickoff_unix, f"{book} odds capture")
        static = CH / f"pilotC_odds_{fixture_id}_{book}.json"
        # Reuse the newest immutable snapshot (research or static) while fresh. This
        # prevents repeated requests during report regeneration without ever
        # overwriting an older price.
        candidates = ([static] if static.exists() else []) + \
                     list(CH.glob(f"research_odds_{fixture_id}_{book}_*.json"))
        newest = max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None
        recent = bool(newest and (now - newest.stat().st_mtime) <= ODDS_FRESH_MINUTES * 60)
        chosen = newest if recent and not refresh else None
        if chosen is None:
            key = f"research_odds_{fixture_id}_{book}_{bucket}"
            try:
                data, meta = api.get_json(f"/football/matches/{fixture_id}/odds",
                    params={"bookmaker": book}, cache_key=key, allow_status=(200, 404, 422))
                chosen = Path(api.cache_path(key))
            except SystemExit:
                data = None; meta = {"error": "request cap/API abort"}
        else:
            data = json.loads(chosen.read_text()); meta = {"from_cache": True, "cache_key": chosen.stem}
        if kickoff_unix is not None:
            ensure_pre_kickoff(kickoff_unix, f"{book} odds acceptance")
        if chosen and chosen.exists():
            dest = request_dir / f"odds_{book}_{bucket}.json"
            shutil.copy2(chosen, dest)
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            sources.append({"book": book, "path": str(dest), "sha256": digest,
                            "source_path": str(chosen), "from_recent_cache": bool(recent and not refresh),
                            "age_minutes": round((now - chosen.stat().st_mtime)/60, 1)})
            raw[book] = json.loads(chosen.read_text())
    if kickoff_unix is not None:
        ensure_pre_kickoff(kickoff_unix, "odds capture completion")
    after = api.budget_snapshot()
    return raw, {"live_requests": api.live_requests_made() - live_before,
                 "monthly_remaining": after.get("last_monthly_remaining"),
                 "monthly_limit": after.get("last_monthly_limit"),
                 "monthly_reset": after.get("last_monthly_reset"), "sources": sources}


def parse_books(raw: dict) -> dict:
    out = {}
    for book, payload in raw.items():
        bks = (payload or {}).get("data", {}).get("bookmakers", [])
        if bks and isinstance(bks[0], dict) and bks[0].get("markets"):
            out[book] = bks[0]["markets"]
    return out


def _market_prices(markets: dict, market: str, line):
    if market == "btts":
        node = markets.get("btts", {})
        return (node.get("yes", {}) or {}).get("last_seen"), (node.get("no", {}) or {}).get("last_seen")
    key = fp.MKT_ODDSKEY[market]
    node = (markets.get(key, {}) or {}).get(str(line), {})
    return (node.get("over", {}) or {}).get("last_seen"), (node.get("under", {}) or {}).get("last_seen")


def feature_support(model: dict, hist: dict, fixture: dict, market: str) -> dict:
    m = {"home_name": fixture["home"], "away_name": fixture["away"],
         "date_unix": fixture["kickoff_unix"]}
    raw = mix.match_features(hist, m, market)
    kept = [raw[i] for i in model["keep"]]
    present = sum(v is not None for v in kept)
    return {"selected_features": len(kept), "present": present,
            "fraction": round(present / len(kept), 4) if kept else 0}


def uncertainty_pp(p: float, n_context: int, ece: float) -> float:
    """Conservative request-time probability uncertainty buffer.

    The frozen model has no parameter-covariance artifact. We therefore do not invent a
    narrow model CI. We combine its held-out ECE with an 80% finite-history binomial
    scale based on the smaller team's two-season sample. This is deliberately
    conservative and is used only to ABSTAIN, never to manufacture edge.
    """
    n = max(n_context, 1)
    return 100.0 * (float(ece) + UNCERTAINTY_Z * math.sqrt(max(p * (1-p), 1e-9) / n))


def _oos_cache_key(ms: list[dict]) -> str:
    hp = MODEL_REPORT.read_bytes()
    identity = {"n": len(ms), "last": max((m.get("date_unix", 0) for m in ms), default=0),
                "hp_sha": hashlib.sha256(hp).hexdigest(), "split": 0.7, "version": 1}
    return canonical_hash(identity)[:16]


def _fit_fixed_oos_model(ms: list[dict], hist: dict, market: str, line,
                         C: float, l1r: float) -> tuple[dict, list[dict], np.ndarray]:
    """Fit fixed saved hyperparameters on the first 70% and return the untouched 30%.

    This recreates the honest time-ordered diagnostic boundary without CV, retuning or
    fixture-specific model choice. Features for each test row remain point-in-time
    because mix.match_features only reads history strictly before that row's kickoff.
    """
    names = mix.feat_names(market); rows = []; y = []
    for m in ms:
        o = mix.outcome(m, market, line)
        if o is None:
            continue
        rows.append((m, mix.match_features(hist, m, market))); y.append(o)
    split = int(len(rows) * 0.7)
    train, test = rows[:split], rows[split:]
    ytr = np.asarray(y[:split], dtype=float); yte = np.asarray(y[split:], dtype=float)
    cov = np.mean([[v is not None for v in r] for _, r in train], axis=0)
    keep = [i for i in range(len(names)) if cov[i] >= 0.6]
    def mat(chunk):
        return np.asarray([[(np.nan if r[i] is None else r[i]) for i in keep]
                           for _, r in chunk], dtype=float)
    Xtr = mat(train); Xte = mat(test)
    med = np.nanmedian(Xtr, axis=0); med = np.where(np.isnan(med), 0, med)
    for A in (Xtr, Xte):
        idx = np.where(np.isnan(A)); A[idx] = np.take(med, idx[1])
    mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd == 0] = 1
    clf = LogisticRegression(penalty="elasticnet", solver="saga", C=C, l1_ratio=l1r,
                             max_iter=4000, random_state=0)
    clf.fit((Xtr-mu)/sd, ytr)
    model = {"clf": clf, "keep": keep, "med": med, "mu": mu, "sd": sd,
             "train_base_rate": float(ytr.mean())}
    probs = np.clip(clf.predict_proba((Xte-mu)/sd)[:, 1], 0.01, 0.99)
    return model, [m for m, _ in test], np.column_stack([probs, yte])


def local_walk_forward_diagnostics(ms: list[dict], hist: dict, home: str, away: str) -> dict:
    """Team-specific diagnostics on the untouched final 30% time split.

    The model specification and hyperparameters are frozen globally. No local feature,
    window, market or threshold is selected from these results. Diagnostics can reduce
    confidence or explain abstention; they never increase model probability.
    """
    import pickle
    saved = json.loads(MODEL_REPORT.read_text())["models"]
    hp = {(x["market"], x["line"]): (x["C"], x["l1_ratio"]) for x in saved}
    key = _oos_cache_key(ms); cache = RESEARCH_MODEL_CACHE / f"oos_{key}.pkl"
    bundle = None
    if cache.exists():
        try:
            with open(cache, "rb") as f: bundle = pickle.load(f)
        except Exception: bundle = None
    if bundle is None:
        bundle = {}
        for market, line in CELLS:
            bundle[(market, line)] = _fit_fixed_oos_model(ms, hist, market, line, *hp[(market, line)])
        cache.parent.mkdir(parents=True, exist_ok=True)
        with open(cache, "wb") as f: pickle.dump(bundle, f)
    out = {}
    for market, line in CELLS:
        model, test_matches, py = bundle[(market, line)]
        mask = np.asarray([home in (m.get("home_name"), m.get("away_name")) or
                           away in (m.get("home_name"), m.get("away_name"))
                           for m in test_matches], dtype=bool)
        local = py[mask]
        if len(local):
            p, y = local[:, 0], local[:, 1]
            brier = float(np.mean((p-y)**2)); base = model["train_base_rate"]
            naive = float(np.mean((base-y)**2))
            bss = (1-brier/naive)*100 if naive > 0 else None
            out[f"{market}@{line}"] = {"n": int(len(local)), "brier": round(brier, 4),
                "brier_skill_vs_training_base_pct": round(bss, 2) if bss is not None else None,
                "mean_predicted": round(float(p.mean()), 4), "observed_rate": round(float(y.mean()), 4),
                "calibration_gap": round(float(p.mean()-y.mean()), 4),
                "use": "diagnostic/abstention only; never refits or raises model probability"}
        else:
            out[f"{market}@{line}"] = {"n": 0, "use": "insufficient local OOS rows"}
    return out


def analyze_markets(fixture: dict, history: list[dict], books: dict,
                    local_diagnostics: dict | None = None) -> tuple[list[dict], dict]:
    # Frozen model path: same corpus + saved HP as Pilot C; model cache only avoids
    # recomputing identical coefficients.
    full_ms = mix.load_corpus(); full_hist = mix.build_histories(full_ms)
    inference_ms = merge_inference_history(full_ms, history)
    inference_hist = mix.build_histories(inference_ms)
    models, _ = manual._fit_models(full_ms, full_hist)
    metrics = {(m["market"], m["line"]): m for m in json.loads(MODEL_REPORT.read_text())["models"]}
    supported_counts = supported_context_counts(history, (fixture["home"], fixture["away"]))
    context_n = min(supported_counts.values())
    fm = {"home_name": fixture["home"], "away_name": fixture["away"],
          "date_unix": fixture["kickoff_unix"]}
    results = []
    for market, line in CELLS:
        model = models[(market, line)]
        p_over = fp.predict_one(model, inference_hist, fm, market)
        support = feature_support(model, inference_hist, fixture, market)
        met = metrics[(market, line)]
        local_diag = (local_diagnostics or {}).get(f"{market}@{line}", {})
        unc = uncertainty_pp(p_over, context_n, met["ece"])
        row = {"market": market, "line": line, "model_p_over_or_yes": round(p_over, 4),
               "model_p_under_or_no": round(1-p_over, 4), "feature_support": support,
               "model_validation": {"n_test": met["n_test"], "bss_pct": met["bss_pct"],
                                    "ece": met["ece"], "local_walk_forward": local_diag},
               "uncertainty_buffer_pp": round(unc, 2), "books": {}, "decision": "NO OPPORTUNITY",
               "decision_reasons": []}
        candidates = []
        for book, markets in books.items():
            over_o, under_o = _market_prices(markets, market, line)
            dv = fp.devig(over_o, under_o)
            if not dv:
                continue
            fair_over, ovr = dv
            fair_under = 1 - fair_over
            for side, p, fair, odds in (("over/yes", p_over, fair_over, float(over_o)),
                                         ("under/no", 1-p_over, fair_under, float(under_o))):
                edge = (p - fair) * 100
                ev = (p * odds - 1) * 100
                effective = edge - unc - COMMISSION_BUFFER_PP
                item = {"side": side, "model_p": round(p, 4), "fair_p": round(fair, 4),
                        "decimal_odds": odds, "edge_pp": round(edge, 2),
                        "ev_pct": round(ev, 2), "overround": round(ovr, 4),
                        "uncertainty_adjusted_edge_pp": round(effective, 2)}
                row["books"].setdefault(book, []).append(item)
                reasons = []
                if support["fraction"] < MIN_FEATURE_SUPPORT: reasons.append("feature support below threshold")
                if met["bss_pct"] <= 0: reasons.append("model has no held-out skill")
                if (local_diag.get("n", 0) >= LOCAL_DIAG_MIN_N and
                    local_diag.get("brier_skill_vs_training_base_pct") is not None and
                    local_diag["brier_skill_vs_training_base_pct"] < LOCAL_DIAG_MIN_BSS):
                    reasons.append("team-specific walk-forward diagnostic is materially poor")
                if ovr > MAX_REFERENCE_OVERROUND: reasons.append("reference overround too high")
                if edge < MIN_RAW_EDGE_PP: reasons.append("raw edge below threshold")
                if ev < MIN_EV_PCT: reasons.append("EV below threshold")
                if effective <= 0: reasons.append("edge does not survive uncertainty buffer")
                item["gate_reasons"] = reasons
                if not reasons:
                    candidates.append({"book": book, **item})
        if candidates:
            candidates.sort(key=lambda x: x["uncertainty_adjusted_edge_pp"], reverse=True)
            row["decision"] = "CANDIDATE"
            row["best_candidate"] = candidates[0]
        else:
            if not row["books"]: row["decision_reasons"].append("no executable two-sided odds for this line")
            else: row["decision_reasons"].append("no book/side passes every predeclared gate")
        results.append(row)
    return results, {"context_matches_per_team_min": context_n,
                     "supported_context_counts": supported_counts,
                     "inference_rows_added_from_request_cache": len(inference_ms) - len(full_ms),
                     "policy": {"min_feature_support": MIN_FEATURE_SUPPORT,
                                "min_raw_edge_pp": MIN_RAW_EDGE_PP, "min_ev_pct": MIN_EV_PCT,
                                "commission_buffer_pp": COMMISSION_BUFFER_PP,
                                "max_reference_overround": MAX_REFERENCE_OVERROUND,
                                "uncertainty_z": UNCERTAINTY_Z,
                                "local_diag_min_n": LOCAL_DIAG_MIN_N,
                                "local_diag_min_bss_pct": LOCAL_DIAG_MIN_BSS}}


def commit_report(report: dict) -> dict:
    """Attest each priced market in a separate research ledger before kickoff."""
    ledger = AttestationLedger(RESEARCH_COMMIT_LEDGER, RESEARCH_REVEAL_LEDGER)
    ok, problems = ledger.verify_chain(RESEARCH_COMMIT_LEDGER)
    if not ok:
        raise LedgerTamperError(f"fixture-research commit chain failed: {problems[:3]}")
    report_hash = canonical_hash({k: v for k, v in report.items() if k != "attestation"})
    already = ledger.commitments_by_prediction(); rows = []
    snapshot_id = report["request_id"]
    for market in report["markets"]:
        # Bind the lowest-overround available book as reference.
        refs = []
        for book, sides in market["books"].items():
            over = next((x for x in sides if x["side"] == "over/yes"), None)
            under = next((x for x in sides if x["side"] == "under/no"), None)
            if over and under:
                refs.append((over["overround"], book, over, under))
        if not refs:
            rows.append({"market": market["market"], "line": market["line"],
                         "attested": False, "reason": "no two-sided reference price"}); continue
        _, book, over, under = min(refs, key=lambda x: x[0])
        pid = f"fixture-research:{snapshot_id}:{market['market']}:{market['line']}"
        reference = {"book": book, "over_odds": over["decimal_odds"],
                     "under_odds": under["decimal_odds"], "fair_p": over["fair_p"],
                     "overround": over["overround"], "odds_source_hashes": report["source_hashes"]}
        p = market["model_p_over_or_yes"]; p_under = round(1-p, 4)
        if pid in already:
            existing = already[pid]
            conflicts = []
            for key, expected in (("p_over", p), ("p_under", p_under),
                                  ("reference_price", reference), ("report_hash", report_hash)):
                if existing.get(key) != expected:
                    conflicts.append(key)
            if conflicts:
                raise LedgerTamperError(f"existing {pid} conflicts on {conflicts}; refusing to label it attested")
            rows.append({"prediction_id": pid, "attested": True,
                         "commitment_hash": existing["commitment_hash"], "existing": True}); continue
        res = ledger.commit(prediction_id=pid, fixture_id=report["fixture"]["fixture_id"],
            model=f"fixture_ev_v1_{market['market']}_{market['line']}",
            kickoff_unix=report["fixture"]["kickoff_unix"], p_over=p, p_under=p_under,
            reference_price=reference,
            extra={"source": "fixture_research", "requested_by": report["requested_by"],
                   "request_id": snapshot_id, "report_hash": report_hash,
                   "p_over": p, "p_under": p_under,
                   "decision": market["decision"], "caveat": CAVEAT})
        rows.append({"prediction_id": pid, "attested": res.committed,
                     "commitment_hash": res.record["commitment_hash"] if res.committed else None,
                     "reason": res.reason})
    commits = ledger.load_commitments()
    return {"report_hash": report_hash, "ledger": str(RESEARCH_COMMIT_LEDGER), "rows": rows,
            "chain_head": commits[-1]["link_hash"] if commits else None,
            "anchor_note": "Hash chain is locally tamper-evident. The public receipt must be pushed to Git to externally timestamp this chain head."}


def write_public_receipt(report: dict) -> Path:
    """Write a small provider-data-free receipt suitable for Git publication."""
    att = report["attestation"]
    receipt = {"version": 1, "fixture_id": report["fixture"]["fixture_id"],
               "fixture": f"{report['fixture']['home']} v {report['fixture']['away']}",
               "kickoff_iso": report["fixture"]["kickoff_iso"],
               "request_id": report["request_id"], "generated_at": report["generated_at"],
               "report_hash": att["report_hash"], "source_hashes": report["source_hashes"],
               "commitment_hashes": [r.get("commitment_hash") for r in att["rows"] if r.get("commitment_hash")],
               "chain_head": att["chain_head"], "result_summary": report["summary"],
               "caveat": CAVEAT,
               "verification": "Recompute SHA-256 hashes from the retained local report/source snapshots; verify the fixture-research JSONL chain. Git publication timestamps this receipt, not the proprietary raw source bodies."}
    PUBLIC_RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)
    path = PUBLIC_RECEIPT_ROOT / f"{report['request_id']}.json"
    path.write_text(json.dumps(receipt, indent=2, default=str) + "\n")
    return path


def build_report(fixture_id: str, requested_by: str, refresh_odds: bool = False,
                 commit: bool = False) -> dict:
    fixture = resolve_fixture(fixture_id)
    if time.time() >= fixture["kickoff_unix"]:
        raise ValueError("fixture already kicked off; this engine refuses retrospective candidate generation because current prices cannot prove a pre-kickoff information set")
    cross = validated_crosswalk(fixture["home"], fixture["away"])
    history, history_meta = load_two_season_history(fixture["home"], fixture["away"],
                                                     fixture["kickoff_unix"])
    counts = {t: len(_team_rows(history, t)) for t in (fixture["home"], fixture["away"])}
    supported_counts = supported_context_counts(history, (fixture["home"], fixture["away"]))
    if any(n < MIN_HISTORY_MATCHES for n in counts.values()):
        raise ValueError(f"insufficient strictly pre-cutoff history: {counts}")
    if any(n < MIN_HISTORY_MATCHES for n in supported_counts.values()):
        raise ValueError(f"insufficient statistically supported history after cache hydration: {supported_counts}")

    request_id = (f"{fixture_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
                  f"-{time.time_ns()}")
    request_dir = RESEARCH_ROOT / fixture_id / request_id
    source_dir = request_dir / "sources"
    raw_odds, quota = capture_odds(fixture_id, source_dir, refresh=refresh_odds,
                                    kickoff_unix=fixture["kickoff_unix"])
    books = parse_books(raw_odds)
    full_ms = mix.load_corpus(); full_hist = mix.build_histories(full_ms)
    local_diagnostics = local_walk_forward_diagnostics(full_ms, full_hist,
                                                        fixture["home"], fixture["away"])
    markets, diagnostic = analyze_markets(fixture, history, books, local_diagnostics)
    source_hashes = {s["book"]: s["sha256"] for s in quota["sources"]}
    report = {
        "request_id": request_id, "generated_at": now_iso(), "requested_by": requested_by,
        "fixture": fixture, "crosswalk": cross,
        "information_cutoff": {"rule": "strict date_unix < fixture kickoff",
                               "cutoff_unix": fixture["kickoff_unix"],
                               "target_match_stats_consumed": False},
        "request_plan": {"history_source": "FootyStats immutable two-season cache",
                         "history_fallback": history_meta["fallback"],
                         "heatmaps": {"available": False,
                                      "reason": "TheStatsAPI heatmap/positions/touchmap probes returned no usable endpoint; not imputed."},
                         "odds_live_request_cap": MAX_ODDS_REQUESTS,
                         "history_live_request_cap": MAX_HISTORY_REQUESTS},
        "evidence": {"history_counts": counts, "supported_history_counts": supported_counts,
                     "history_meta": history_meta,
                     "teams": {t: summarize_team(history, t) for t in counts},
                     "descriptive_market_rates": historical_market_rates(history, fixture["home"], fixture["away"]),
                     "local_walk_forward_diagnostics": local_diagnostics},
        "model": {"name": "Pilot C elastic-net stat mixer (frozen saved HP, no retune)",
                  "note": "Two-season evidence and local rates are diagnostics; they do not select or refit the model."},
        "decision_policy": diagnostic, "markets": markets, "quota": quota,
        "source_hashes": source_hashes, "caveat": CAVEAT,
    }
    report["summary"] = {"candidate_markets": sum(m["decision"] == "CANDIDATE" for m in markets),
                         "no_opportunity_markets": sum(m["decision"] != "CANDIDATE" for m in markets)}
    try:
        ensure_pre_kickoff(fixture["kickoff_unix"], "pre-publication validation")
        if commit:
            report["attestation"] = commit_report(report)
            ensure_pre_kickoff(fixture["kickoff_unix"], "post-attestation publication")
            receipt = write_public_receipt(report)
            report["attestation"]["public_receipt"] = str(receipt)
        else:
            ensure_pre_kickoff(fixture["kickoff_unix"], "report publication")
    except Exception:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise
    request_dir.mkdir(parents=True, exist_ok=True)
    (request_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))
    latest = RESEARCH_ROOT / fixture_id / "latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(request_dir / "report.json", latest)
    report["report_path"] = str(request_dir / "report.json")
    return report


def render(report: dict) -> str:
    f = report["fixture"]; lines = ["="*96,
        f"FIXTURE EV RESEARCH — {f['home']} v {f['away']} [{f['fixture_id']}]",
        f"Kickoff: {f['kickoff_iso']}  Request: {report['request_id']}",
        "="*96]
    counts = report["evidence"]["history_counts"]
    lines.append(f"Evidence: {counts[f['home']]} {f['home']} matches; {counts[f['away']]} {f['away']} matches; strict pre-kickoff cutoff")
    q = report["quota"]
    lines.append(f"Sources: FootyStats 2-season cache + TheStatsAPI odds | live requests={q['live_requests']} | monthly={q['monthly_remaining']}/{q['monthly_limit']}")
    lines.append("Heatmaps: UNAVAILABLE (provider routes returned no usable payload; not imputed)")
    lines.append("")
    lines.append(f"{'market':8s} {'line':>5s} {'p_over':>7s} {'unc_pp':>7s} {'support':>7s} {'book':17s} {'side':9s} {'fair_p':>7s} {'odds':>6s} {'edge':>7s} {'EV%':>7s} {'adj_edge':>9s}  decision")
    lines.append("-"*150)
    for m in report["markets"]:
        first = True
        if not m["books"]:
            lines.append(f"{m['market']:8s} {str(m['line']):>5s} {m['model_p_over_or_yes']:7.4f} {m['uncertainty_buffer_pp']:7.2f} {m['feature_support']['fraction']:7.2f} {'(no odds)':17s} {'':9s} {'':7s} {'':6s} {'':7s} {'':7s} {'':9s}  {m['decision']}")
            continue
        for book, sides in m["books"].items():
            for s in sides:
                lines.append(f"{(m['market'] if first else ''):8s} {(str(m['line']) if first else ''):>5s} {(f'{m['model_p_over_or_yes']:.4f}' if first else ''):>7s} {(f'{m['uncertainty_buffer_pp']:.2f}' if first else ''):>7s} {(f'{m['feature_support']['fraction']:.2f}' if first else ''):>7s} {book:17s} {s['side']:9s} {s['fair_p']:7.4f} {s['decimal_odds']:6.2f} {s['edge_pp']:+7.2f} {s['ev_pct']:+7.2f} {s['uncertainty_adjusted_edge_pp']:+9.2f}  {(m['decision'] if first else '')}")
                first = False
    lines += ["", f"RESULT: {report['summary']['candidate_markets']} candidate market(s); {report['summary']['no_opportunity_markets']} no-opportunity market(s)."]
    if report.get("attestation"):
        ok = sum(r.get("attested", False) for r in report["attestation"]["rows"])
        lines.append(f"Attestation: {ok} market(s) committed to {report['attestation']['ledger']}")
        lines.append(f"Report hash: {report['attestation']['report_hash']}")
    lines += ["", CAVEAT, "="*96, f"Saved: {report.get('report_path', RESEARCH_ROOT)}"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="On-demand two-season fixture research + conservative EV engine")
    ap.add_argument("--fixture-id", required=True)
    ap.add_argument("--requested-by", default="unspecified")
    ap.add_argument("--refresh-odds", action="store_true", help="force new versioned odds snapshots (max 3 calls)")
    ap.add_argument("--commit", action="store_true", help="attest the report in the separate fixture-research ledger")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    report = build_report(args.fixture_id, args.requested_by, args.refresh_odds, args.commit)
    print(json.dumps(report, indent=2, default=str) if args.json else render(report))


if __name__ == "__main__":
    main()
