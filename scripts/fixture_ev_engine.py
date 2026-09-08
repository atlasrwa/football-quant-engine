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
  python scripts/fixture_ev_engine.py --home Flamengo --away Mirassol --date 2026-09-02 --competition brazil-serie-a
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
import re
import shutil
import sys
import time
import unicodedata
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
from src.research.footystats.client import FootyStatsResearchClient
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
FOOTYSTATS_API_CACHE = ROOT / ".cache/footystats_research"
PUBLIC_RECEIPT_ROOT = ROOT / "data/attestations/fixture_research"

CELLS = [("goals", 1.5), ("goals", 2.5), ("goals", 3.5),
         ("corners", 8.5), ("corners", 9.5), ("corners", 10.5),
         ("cards", 3.5), ("cards", 4.5), ("btts", None)]
BOOKS = ["betfair-exchange", "pinnacle", "bet365"]

# Safety / decision policy. All can be overridden, but defaults are intentionally
# conservative: most efficient-market fixtures should produce NO OPPORTUNITY.
HISTORY_SEASONS = 2
EXPECTED_EPL_SEASON_MATCHES = 380
MAX_RESOLVE_REQUESTS = int(os.environ.get("FIXTURE_EV_RESOLVE_CAP", "1"))
MAX_ODDS_ASSOCIATION_REQUESTS = int(os.environ.get("FIXTURE_EV_ODDS_ASSOCIATION_CAP", "8"))
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

# Reviewed fixture-research competition profiles. These profiles affect only this
# on-demand engine; they do not expand Pilot C's preregistered league coverage.
COMPETITION_PROFILES = {
    "comp_3039": {
        "name": "England Premier League",
        "country": "England",
        "footystats_seasons": KNOWN_EPL_SEASONS,
        "expected_matches": 380,
        "crosswalk_section": "England Premier League",
        "pilotc_covered": True,
    },
    "comp_4795": {
        "name": "Brasileirão Série A",
        "country": "Brazil",
        "footystats_seasons": {
            "11321": {"label": "2024"},
            "14231": {"label": "2025"},
        },
        "expected_matches": 380,
        "crosswalk_section": None,
        "pilotc_covered": False,
    },
    # The fixture universe identifies these Pilot C leagues by TheStatsAPI
    # competition IDs. Their FootyStats names let resolve_fixture_request verify
    # the exact eligible fixture before history or odds are evaluated.
    "comp_8321": {
        "name": "England Championship",
        "country": "England",
        "footystats_seasons": {},
        "expected_matches": 0,
        "crosswalk_section": None,
        "pilotc_covered": True,
    },
    "comp_9777": {
        "name": "France Ligue 2",
        "country": "France",
        "footystats_seasons": {},
        "expected_matches": 0,
        "crosswalk_section": None,
        "pilotc_covered": True,
    },
}
# Legacy provider IDs remain compatibility hints only. Runtime eligibility is
# determined from FootyStats /league-list and /league-matches, never this map.
COMPETITION_ALIASES = {
    "epl": "England Premier League",
    "england-premier-league": "England Premier League",
    "brazil-serie-a": "Brasileirão Série A",
    "brasileirao": "Brasileirão Série A",
    "brasileirão": "Brasileirão Série A",
    "comp_3039": "England Premier League",
    "comp_4795": "Brasileirão Série A",
}
PILOTC_FOOTYSTATS_COMPETITIONS = {
    "England Championship", "England Premier League", "France Ligue 2", "Spain La Liga 2",
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


def _slug(value: str) -> str:
    """Normalize provider/user league labels without inventing provider IDs."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _footystats_client(cached: bool = True) -> FootyStatsResearchClient:
    return FootyStatsResearchClient(cache_dir=FOOTYSTATS_API_CACHE if cached else None)


def _matching_footystats_leagues(value: str, leagues: list[dict]) -> list[dict]:
    key = _slug(value)
    compatibility_name = COMPETITION_ALIASES.get(str(value or "").strip().casefold())
    if compatibility_name:
        key = _slug(compatibility_name)
    matches = []
    for league in leagues:
        name = str(league.get("name") or "").strip()
        country = str(league.get("country") or "").strip()
        if not name or not isinstance(league.get("season"), list):
            continue
        full = _slug(name)
        aliases = {full}
        country_slug = _slug(country)
        if country_slug and full.startswith(country_slug + "-"):
            aliases.add(full[len(country_slug) + 1:])
        if key in aliases:
            matches.append(league)
    unique = {}
    for league in matches:
        unique[(str(league.get("country")), str(league.get("name")))] = league
    return list(unique.values())


def resolve_footystats_competition(value: str) -> dict:
    """Resolve a league against FootyStats' subscribed /league-list endpoint."""
    if not str(value or "").strip():
        raise ValueError("competition is required")
    try:
        leagues = _footystats_client(cached=True).fetch_league_list()
    except Exception as exc:
        raise ValueError(f"FootyStats league-list endpoint failed: {exc}") from exc
    matches = _matching_footystats_leagues(value, leagues)
    source = "footystats_league_list_cache"
    if not matches and os.environ.get("FOOTYSTATS_API_KEY") not in (None, "", "example"):
        try:
            leagues = _footystats_client(cached=False).fetch_league_list()
            matches = _matching_footystats_leagues(value, leagues)
            source = "footystats_league_list_live"
        except Exception as exc:
            raise ValueError(f"FootyStats could not verify competition {value!r}: {exc}") from exc
    if not matches:
        raise ValueError(f"FootyStats does not support or expose competition {value!r} on /league-list")
    if len(matches) > 1:
        candidates = ", ".join(sorted(f"{m.get('country')} {m.get('name')}" for m in matches))
        raise ValueError(f"ambiguous FootyStats competition {value!r}; use a country-qualified name: {candidates}")
    league = matches[0]
    seasons = [dict(s) for s in league.get("season", []) if s.get("id") is not None]
    if not seasons:
        raise ValueError(f"FootyStats exposes {league.get('name')!r} but returned no seasons")
    return {"name": str(league["name"]), "country": str(league.get("country") or ""),
            "seasons": seasons, "resolution_source": source}


def _season_sort_key(season: dict) -> tuple[int, int]:
    raw = re.sub(r"\D", "", str(season.get("year") or ""))
    try:
        year_key = int(raw)
    except ValueError:
        year_key = 0
    return year_key, int(season.get("id") or 0)


def _candidate_fixture_seasons(seasons: list[dict], day) -> list[dict]:
    year = str(day.year)
    matching = [s for s in seasons if year in re.sub(r"\D", "", str(s.get("year") or ""))]
    return sorted(matching or seasons, key=_season_sort_key, reverse=True)


def _footystats_match_to_fixture(row: dict, league: dict, season: dict,
                                  source: str, *, require_history: bool = True) -> dict:
    required = ("id", "date_unix", "competition_id", "homeID", "awayID",
                "home_name", "away_name")
    missing = [field for field in required if row.get(field) in (None, "")]
    if missing:
        raise ValueError(f"FootyStats fixture payload lacks: {', '.join(missing)}")
    kickoff = float(row["date_unix"])
    target_key = _season_sort_key(season)
    prior = sorted((dict(s) for s in league["seasons"]
                    if _season_sort_key(s) < target_key), key=_season_sort_key, reverse=True)
    history_eligible = len(prior) >= HISTORY_SEASONS
    if require_history and not history_eligible:
        raise ValueError(f"FootyStats has fewer than {HISTORY_SEASONS} prior seasons for {league['name']}")
    fs_id = str(row["id"])
    return {
        "fixture_id": f"fs_{fs_id}", "footystats_fixture_id": fs_id,
        "ts": kickoff, "kickoff_unix": kickoff,
        "kickoff_iso": datetime.fromtimestamp(kickoff, timezone.utc).isoformat(),
        "comp": f"footystats:{season['id']}",
        "competition_id": f"footystats:{season['id']}",
        "competition_name": league["name"], "season_id": season["id"],
        "status": row.get("status"), "home": str(row["home_name"]),
        "away": str(row["away_name"]), "home_team_id": row["homeID"],
        "away_team_id": row["awayID"], "resolution_source": source,
        "history_eligible": history_eligible,
        "footystats_competition": {
            "name": league["name"], "country": league["country"],
            "fixture_season": dict(season), "history_seasons": prior[:HISTORY_SEASONS],
            "league_resolution_source": league["resolution_source"],
        },
    }


def discover_footystats_fixtures_for_day(day, *, fresh: bool = True,
                                         request_cap: int = 300) -> dict:
    """Discover every account-accessible FootyStats fixture for a UTC date.

    ``fixtures`` is the complete normalized FootyStats day slate, including
    fixtures that cannot be modeled or priced. ``analysis_fixtures`` is the
    fail-closed subset with two prior FootyStats seasons and one independently
    verified, odds-capable TheStatsAPI identity. Endpoint and fixture failures
    are recorded so partial discovery is never presented as full coverage.
    """
    client = _footystats_client(cached=not fresh)
    manifest = {"day": day.isoformat(), "fresh": fresh, "complete": True,
                "league_count": 0, "season_count": 0, "live_requests": 0,
                "fixtures": [], "analysis_fixtures": [], "skipped": [],
                "failures": []}
    try:
        rows = client.fetch_league_list()
    except Exception as exc:
        manifest.update({"complete": False,
                         "failures": [{"scope": "league-list",
                                       "reason": f"{type(exc).__name__}: {exc}"}]})
        manifest["live_requests"] = client.request_count
        return manifest

    for raw_league in rows:
        if client.request_count >= request_cap:
            manifest["complete"] = False
            manifest["failures"].append({"scope": "discovery",
                                         "reason": f"FootyStats live-request cap {request_cap} reached"})
            break
        league_name = str(raw_league.get("name") or "").strip()
        seasons = [dict(s) for s in raw_league.get("season", []) if s.get("id") is not None]
        if not league_name or not seasons:
            manifest["skipped"].append({"scope": "league", "league": league_name or "n/a",
                                        "reason": "missing league name or seasons"})
            continue
        manifest["league_count"] += 1
        league = {"name": league_name, "country": str(raw_league.get("country") or ""),
                  "seasons": seasons, "resolution_source": "footystats_account_league_list"}
        date_seasons = [season for season in seasons
                        if str(day.year) in re.sub(r"\D", "", str(season.get("year") or ""))]
        if not date_seasons:
            manifest["skipped"].append({"scope": "league", "league": league_name,
                                        "reason": f"no FootyStats season includes {day.year}"})
            continue
        for season in sorted(date_seasons, key=_season_sort_key, reverse=True):
            if client.request_count >= request_cap:
                manifest["complete"] = False
                manifest["failures"].append({"scope": "discovery",
                                             "reason": f"FootyStats live-request cap {request_cap} reached"})
                break
            manifest["season_count"] += 1
            try:
                matches = client.fetch_season_matches(int(season["id"]))
            except Exception as exc:
                manifest["complete"] = False
                manifest["failures"].append({"scope": "season", "league": league_name,
                                             "season_id": season["id"],
                                             "reason": f"{type(exc).__name__}: {exc}"})
                continue
            for row in matches:
                kickoff = numeric(row.get("date_unix"))
                if kickoff is None or datetime.fromtimestamp(kickoff, timezone.utc).date() != day:
                    continue
                try:
                    fixture = _footystats_match_to_fixture(
                        row, league, season, "footystats_account_date_discovery",
                        require_history=False)
                    manifest["fixtures"].append(fixture)
                    if not fixture["history_eligible"]:
                        manifest["skipped"].append({
                            "scope": "analysis", "fixture_id": fixture["fixture_id"],
                            "league": league_name,
                            "reason": f"fewer than {HISTORY_SEASONS} prior FootyStats seasons",
                        })
                        continue
                    odds_resolution = resolve_thestats_odds_fixture(fixture)
                    fixture["odds_resolution"] = odds_resolution
                    if not odds_resolution.get("matched"):
                        manifest["skipped"].append({
                            "scope": "analysis", "fixture_id": fixture["fixture_id"],
                            "league": league_name,
                            "reason": f"no verified executable odds: {odds_resolution.get('reason', 'unmatched')}",
                        })
                        continue
                    for key in ("thestats_fixture_id", "thestats_competition_id",
                                "thestats_season_id", "thestats_home_team_id",
                                "thestats_away_team_id"):
                        fixture[key] = odds_resolution[key]
                    manifest["analysis_fixtures"].append(fixture)
                except Exception as exc:
                    manifest["skipped"].append({"scope": "fixture", "league": league_name,
                                                "fixture_id": row.get("id"),
                                                "reason": f"{type(exc).__name__}: {exc}"})
        if not manifest["complete"]:
            break
    manifest["fixtures"].sort(key=lambda fixture: fixture["kickoff_unix"])
    manifest["analysis_fixtures"].sort(key=lambda fixture: fixture["kickoff_unix"])
    manifest["live_requests"] = client.request_count
    manifest["fixture_count"] = len(manifest["fixtures"])
    manifest["analysis_fixture_count"] = len(manifest["analysis_fixtures"])
    return manifest


def _competition_id(value: str) -> str:
    """Compatibility helper returning the FootyStats canonical league name."""
    return resolve_footystats_competition(value)["name"]


def _api_match_to_fixture(row: dict, source: str) -> dict:
    """Normalize a TheStatsAPI match object to the engine's fixture contract."""
    if not isinstance(row, dict) or not row.get("id") or not row.get("utc_date"):
        raise ValueError("provider match payload lacks id or utc_date")
    dt = datetime.fromisoformat(str(row["utc_date"]).replace("Z", "+00:00"))
    home = row.get("home_team") or {}; away = row.get("away_team") or {}
    if not home.get("name") or not away.get("name"):
        raise ValueError("provider match payload lacks home/away team names")
    comp = str(row.get("competition_id") or "")
    legacy_profile = COMPETITION_PROFILES.get(comp, {})
    return {
        "fixture_id": str(row["id"]),
        "thestats_fixture_id": str(row["id"]),
        "ts": dt.timestamp(),
        "kickoff_unix": dt.timestamp(),
        "kickoff_iso": dt.astimezone(timezone.utc).isoformat(),
        "comp": comp,
        "competition_id": comp,
        "competition_name": row.get("competition_name") or legacy_profile.get("name") or comp,
        "season_id": row.get("season_id"),
        "status": row.get("status"),
        "home": str(home["name"]),
        "away": str(away["name"]),
        "home_team_id": home.get("id"),
        "away_team_id": away.get("id"),
        "resolution_source": source,
    }


def _set_stage_request_cap(api, allowance: int) -> int:
    """Set a stage ceiling without ever raising the process/run budget."""
    before = api.live_requests_made()
    configured = int(getattr(api, "CONFIGURED_MAX_LIVE_REQUESTS", api.MAX_LIVE_REQUESTS))
    run_cap = int(getattr(api, "RUN_MAX_LIVE_REQUESTS", configured))
    api.MAX_LIVE_REQUESTS = min(configured, run_cap, before + max(0, int(allowance)))
    return before


def _resolver_api():
    import thestatsapi_client as api
    # The resolver receives at most its explicit one-call allowance; cache hits
    # consume zero, and the immutable process ceiling is never raised.
    _set_stage_request_cap(api, MAX_RESOLVE_REQUESTS)
    return api


def _provider_rows(payload) -> list[dict]:
    if isinstance(payload, dict):
        rows = payload.get("data", [])
    else:
        rows = payload or []
    return rows if isinstance(rows, list) else []


def _provider_total_pages(payload, current: int) -> int:
    if not isinstance(payload, dict):
        return current
    meta = payload.get("meta") or payload.get("metadata") or {}
    try:
        return max(current, int(meta.get("total_pages") or meta.get("last_page") or current))
    except (TypeError, ValueError):
        return current


def resolve_thestats_odds_fixture(fixture: dict) -> dict:
    """Associate a FootyStats fixture with one odds-capable TheStatsAPI match.

    The association is fail-closed: country/competition, season years, ordered teams,
    provider team IDs, kickoff minute, and the match-level odds flag must all agree.
    Failure leaves probability analysis available but never guesses an odds identity.
    """
    import thestatsapi_client as api
    before = _set_stage_request_cap(api, MAX_ODDS_ASSOCIATION_REQUESTS)
    context = fixture.get("footystats_competition") or {}
    country = str(context.get("country") or "").strip()
    fs_name = str(context.get("name") or "").strip()
    short_name = fs_name
    if country and _slug(fs_name).startswith(_slug(country) + "-"):
        short_name = fs_name[len(country):].strip()
    try:
        competitions = []
        page = 1
        total_pages = 1
        while page <= total_pages:
            payload, _ = api.get_json(
                "/football/competitions", params={"per_page": 100, "page": page},
                cache_key=f"competitions_list_p{page}", allow_status=(200,))
            competitions.extend(_provider_rows(payload))
            total_pages = _provider_total_pages(payload, page)
            page += 1
        comp_matches = [c for c in competitions
                        if _slug(c.get("name")) == _slug(short_name)
                        and _slug(c.get("country") or c.get("country_name")) == _slug(country)
                        and c.get("odds_available") is True]
        if len(comp_matches) != 1:
            return {"matched": False, "reason": "no unique odds-capable TheStatsAPI competition",
                    "live_requests": api.live_requests_made() - before}
        comp = comp_matches[0]

        seasons_payload, _ = api.get_json(
            f"/football/competitions/{comp['id']}/seasons",
            cache_key=f"seasons_{comp['id']}", allow_status=(200,))
        seasons = _provider_rows(seasons_payload)
        fs_season = context.get("fixture_season") or {}
        year_digits = re.sub(r"\D", "", str(fs_season.get("year") or ""))
        start_year = int(year_digits[:4]) if len(year_digits) >= 4 else None
        end_year = int(year_digits[4:8]) if len(year_digits) >= 8 else start_year
        season_matches = [s for s in seasons
                          if (start_year is None or int(s.get("start_year") or 0) == start_year)
                          and (end_year is None or int(s.get("end_year") or 0) == end_year)]
        if len(season_matches) != 1:
            return {"matched": False, "reason": "no unique TheStatsAPI season matching FootyStats years",
                    "thestats_competition_id": comp["id"],
                    "live_requests": api.live_requests_made() - before}
        season = season_matches[0]

        all_matches = []
        page = 1
        total_pages = 1
        asof = datetime.now(timezone.utc).strftime("%Y%m%d")
        while page <= total_pages:
            payload, _ = api.get_json(
                "/football/matches",
                params={"competition_id": comp["id"], "season_id": season["id"],
                        "per_page": 100, "page": page},
                cache_key=(f"fixture_odds_matches_{comp['id']}_{season['id']}"
                           f"_p{page}_asof_{asof}"), allow_status=(200,))
            all_matches.extend(_provider_rows(payload))
            total_pages = _provider_total_pages(payload, page)
            page += 1

        candidates = []
        for row in all_matches:
            if row.get("competition_id") != comp["id"] or row.get("season_id") != season["id"]:
                continue
            home = row.get("home_team") or {}; away = row.get("away_team") or {}
            if not home.get("id") or not away.get("id"):
                continue
            if (canonical_team_name(home.get("name")) != canonical_team_name(fixture["home"]) or
                    canonical_team_name(away.get("name")) != canonical_team_name(fixture["away"])):
                continue
            try:
                kickoff = datetime.fromisoformat(str(row.get("utc_date") or "").replace("Z", "+00:00")).timestamp()
            except (TypeError, ValueError):
                continue
            if abs(kickoff - float(fixture["kickoff_unix"])) > 60:
                continue
            if row.get("odds_available") is not True:
                continue
            if str(row.get("status") or "").casefold() in {"cancelled", "canceled", "postponed"}:
                continue
            candidates.append(row)
        if len(candidates) != 1:
            return {"matched": False,
                    "reason": f"expected one verified odds fixture, found {len(candidates)}",
                    "thestats_competition_id": comp["id"],
                    "thestats_season_id": season["id"],
                    "live_requests": api.live_requests_made() - before}
        row = candidates[0]
        return {"matched": True, "thestats_fixture_id": str(row["id"]),
                "thestats_competition_id": comp["id"], "thestats_season_id": season["id"],
                "thestats_home_team_id": row["home_team"]["id"],
                "thestats_away_team_id": row["away_team"]["id"],
                "kickoff_delta_seconds": 0,
                "source": "thestats_competition_season_match_endpoints",
                "live_requests": api.live_requests_made() - before}
    except SystemExit as exc:
        return {"matched": False, "reason": f"TheStatsAPI resolver aborted ({exc.code})",
                "live_requests": api.live_requests_made() - before}
    except Exception as exc:
        return {"matched": False, "reason": f"TheStatsAPI resolver failed: {exc}",
                "live_requests": api.live_requests_made() - before}


def resolve_fixture(fixture_id: str, allow_live: bool = True) -> dict:
    """Resolve a provider fixture ID cache-first, then with one bounded API call."""
    row = None
    if FIXTURE_LIST.exists():
        row = json.loads(FIXTURE_LIST.read_text()).get("meta", {}).get(fixture_id)
    if row:
        out = dict(row)
        out["fixture_id"] = fixture_id
        out["competition_id"] = out.get("comp")
        out["kickoff_unix"] = float(out.get("ts") or 0)
        out["kickoff_iso"] = datetime.fromtimestamp(out["kickoff_unix"], timezone.utc).isoformat()
        out["resolution_source"] = "pilotC_fixture_cache"
        return out
    if not allow_live:
        raise ValueError(f"fixture {fixture_id} is not in the local fixture universe")
    api = _resolver_api()
    payload, meta = api.get_json(
        f"/football/matches/{fixture_id}",
        cache_key=f"fixture_request_match_{fixture_id}", allow_status=(200,))
    data = (payload or {}).get("data")
    return _api_match_to_fixture(data, "provider_cache" if meta.get("from_cache") else "provider_live")


def resolve_fixture_request(home: str, away: str, date: str, competition: str) -> dict:
    """Resolve an exact fixture through FootyStats-supported league endpoints."""
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("fixture date must use YYYY-MM-DD") from exc
    wanted_home = canonical_team_name(home); wanted_away = canonical_team_name(away)
    if not wanted_home or not wanted_away:
        raise ValueError("home and away team names are required")

    league = resolve_footystats_competition(competition)
    candidate_seasons = _candidate_fixture_seasons(league["seasons"], day)

    def find_matches(client: FootyStatsResearchClient) -> list[tuple[dict, dict]]:
        found = []
        for season in candidate_seasons:
            rows = client.fetch_season_matches(int(season["id"]))
            for row in rows:
                ts = numeric(row.get("date_unix"))
                if ts is None or datetime.fromtimestamp(ts, timezone.utc).date() != day:
                    continue
                if str(row.get("competition_id")) != str(season["id"]):
                    continue
                if (canonical_team_name(row.get("home_name")) == wanted_home and
                        canonical_team_name(row.get("away_name")) == wanted_away):
                    found.append((row, season))
        return found

    cached_client = _footystats_client(cached=True)
    try:
        matches = find_matches(cached_client)
    except Exception as exc:
        raise ValueError(f"FootyStats league-matches endpoint failed for {league['name']}: {exc}") from exc
    source = "footystats_league_matches_cache" if cached_client.request_count == 0 else "footystats_league_matches_live_cached"

    # Active schedules can change after a cache entry was created. One uncached retry
    # makes the endpoint, rather than stale local metadata, the final support boundary.
    if not matches and os.environ.get("FOOTYSTATS_API_KEY") not in (None, "", "example"):
        try:
            matches = find_matches(_footystats_client(cached=False))
            source = "footystats_league_matches_live_refresh"
        except Exception as exc:
            raise ValueError(f"FootyStats could not refresh {league['name']} fixtures: {exc}") from exc
    if not matches:
        raise ValueError(f"FootyStats returned no exact {home} vs {away} fixture in {league['name']} on {day.isoformat()}")
    if len(matches) > 1:
        raise ValueError(f"FootyStats returned multiple exact fixtures in {league['name']} on {day.isoformat()}")

    row, season = matches[0]
    fixture = _footystats_match_to_fixture(row, league, season, source)

    # FootyStats remains authoritative for eligibility and history. TheStatsAPI is
    # discovered independently and attached only after strict cross-provider checks.
    odds_resolution = resolve_thestats_odds_fixture(fixture)
    fixture["odds_resolution"] = odds_resolution
    if odds_resolution.get("matched"):
        for key in ("thestats_fixture_id", "thestats_competition_id", "thestats_season_id",
                    "thestats_home_team_id", "thestats_away_team_id"):
            fixture[key] = odds_resolution[key]
    return fixture


def validated_crosswalk(home: str, away: str, fixture: dict | None = None) -> dict:
    """Validate provider-to-corpus team identity for the fixture competition."""
    fs_context = (fixture or {}).get("footystats_competition")
    if fs_context:
        ids = {home: (fixture or {}).get("home_team_id"),
               away: (fixture or {}).get("away_team_id")}
        out = {}
        for team in (home, away):
            if ids[team] in (None, ""):
                raise ValueError(f"FootyStats fixture lacks a team ID for {team!r}")
            out[team] = {"footystats_name": team, "footystats_id": ids[team],
                         "confidence": 1.0, "status": "exact_footystats_fixture_identity"}
        return out

    comp = str((fixture or {}).get("competition_id") or (fixture or {}).get("comp") or "comp_3039")
    profile = COMPETITION_PROFILES.get(comp)
    if not profile:
        raise ValueError(f"fixture competition {comp!r} is not configured")
    section = profile.get("crosswalk_section")
    if section:
        data = json.loads(CROSSWALK.read_text())
        rows = data.get("leagues", {}).get(section, [])
        by_name = {r["footystats_name"]: r for r in rows}
        out = {}
        for team in (home, away):
            row = by_name.get(team)
            if not row or float(row.get("confidence", 0)) < 0.95:
                raise ValueError(f"no validated high-confidence crosswalk for {team!r}")
            out[team] = row
        return out

    # Brazil uses exact provider names confirmed against the two reviewed complete
    # FootyStats seasons. No fuzzy alias or guessed provider ID is admitted.
    corpus_names = {}
    for sid in profile["footystats_seasons"]:
        for row in _load_season_pages(sid):
            for name in (row.get("home_name"), row.get("away_name")):
                if name:
                    corpus_names[str(name).strip().casefold()] = str(name).strip()
    ids = {home: (fixture or {}).get("home_team_id"),
           away: (fixture or {}).get("away_team_id")}
    out = {}
    for team in (home, away):
        canonical = corpus_names.get(team.strip().casefold())
        if not canonical or not ids.get(team):
            raise ValueError(f"no validated exact provider/corpus mapping for {team!r}")
        out[team] = {"footystats_name": canonical, "thestats_id": ids[team],
                     "thestats_name": team, "confidence": 1.0,
                     "status": "exact_provider_corpus_match"}
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


def load_two_season_history(home: str, away: str, cutoff: float,
                            competition_id: str = "comp_3039",
                            fixture: dict | None = None) -> tuple[list[dict], dict]:
    """Load two complete provider seasons strictly before the fixture cutoff."""
    fs_context = (fixture or {}).get("footystats_competition")
    if fs_context:
        seasons = fs_context.get("history_seasons", [])
        if len(seasons) < HISTORY_SEASONS:
            raise ValueError(f"FootyStats returned fewer than {HISTORY_SEASONS} prior seasons")
        all_rows = []
        season_counts = {}
        season_sources = {}
        for season in seasons[:HISTORY_SEASONS]:
            sid = str(season["id"])
            rows = _load_season_pages(sid)
            source = "canonical_corpus_cache"
            if not rows:
                try:
                    client = _footystats_client(cached=True)
                    rows = client.fetch_season_matches(int(sid))
                    source = ("footystats_api_cache" if client.request_count == 0
                              else "footystats_api_live_cached")
                except Exception as exc:
                    raise ValueError(f"FootyStats could not supply history season {sid}: {exc}") from exc
            complete = [m for m in rows if str(m.get("status") or "").casefold() == "complete"]
            if not complete:
                raise ValueError(f"FootyStats history season {sid} returned no completed matches")
            all_rows.extend(complete)
            season_counts[sid] = len(complete)
            season_sources[sid] = source

        target_ids = {str((fixture or {}).get("home_team_id")),
                      str((fixture or {}).get("away_team_id"))}
        seen = set(); selected = []
        for m in all_rows:
            d = numeric(m.get("date_unix"))
            if d is None or not d < cutoff:
                continue
            row_ids = {str(m.get("homeID")), str(m.get("awayID"))}
            names_match = (canonical_team_name(home) in
                           {canonical_team_name(m.get("home_name")), canonical_team_name(m.get("away_name"))} or
                           canonical_team_name(away) in
                           {canonical_team_name(m.get("home_name")), canonical_team_name(m.get("away_name"))})
            if target_ids.isdisjoint(row_ids) and not names_match:
                continue
            key = fixture_identity(m)
            if key in seen:
                continue
            seen.add(key); selected.append(m)
        selected.sort(key=lambda x: x["date_unix"])
        return selected, {
            "competition_id": competition_id,
            "footystats_competition": fs_context["name"],
            "history_seasons": [dict(s) for s in seasons[:HISTORY_SEASONS]],
            "season_page_counts": season_counts, "season_sources": season_sources,
            "fallback": {"used": False, "live_requests": 0, "missing_seasons": [],
                         "note": "FootyStats is authoritative for dynamic league history"},
            "strict_cutoff_unix": cutoff,
            "latest_history_unix": max((m["date_unix"] for m in selected), default=None),
        }

    # Legacy path retained for direct TheStatsAPI fixtures while they are attached to
    # a FootyStats context by build_report.
    profile = COMPETITION_PROFILES.get(competition_id)
    if not profile:
        raise ValueError(f"fixture competition {competition_id!r} is not configured")
    seasons = profile["footystats_seasons"]
    expected_matches = int(profile["expected_matches"])
    all_rows = []
    season_counts = {}
    missing_seasons = []
    for sid, meta in seasons.items():
        rows = _load_season_pages(sid)
        season_counts[sid] = len(rows)
        if len(rows) < expected_matches:
            missing_seasons.append((sid, {**meta, "cached_match_count": len(rows),
                                          "expected_match_count": expected_matches}))
        all_rows.extend(rows)

    fallback = {"used": False, "live_requests": 0, "missing_seasons": [s for s, _ in missing_seasons],
                "note": None}
    if missing_seasons and all(meta.get("thestats_id") for _, meta in missing_seasons):
        hydrated, info = hydrate_history_from_thestats(home, away, cutoff, missing_seasons)
        all_rows.extend(hydrated)
        fallback.update(info)
    elif missing_seasons:
        fallback["note"] = ("reviewed local season is incomplete and no verified provider "
                            "season mapping exists; no history was fabricated")

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
    return selected, {"competition_id": competition_id,
                      "season_page_counts": season_counts, "fallback": fallback,
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
    # Per-stage ceiling: earlier fixture/history calls cannot consume the odds budget,
    # and this stage cannot spend more than MAX_HISTORY_REQUESTS from its own start or
    # exceed the immutable process-level request ceiling.
    before = _set_stage_request_cap(api, MAX_HISTORY_REQUESTS)
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
    now = time.time()
    # Independent per-stage allowance that cannot exceed the process-level ceiling.
    live_before = _set_stage_request_cap(api, MAX_ODDS_REQUESTS)
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
                 commit: bool = False, resolved_fixture: dict | None = None) -> dict:
    fixture = dict(resolved_fixture) if resolved_fixture is not None else resolve_fixture(fixture_id)
    fixture_id = fixture["fixture_id"]
    if time.time() >= fixture["kickoff_unix"]:
        raise ValueError("fixture already kicked off; this engine refuses retrospective candidate generation because current prices cannot prove a pre-kickoff information set")

    # Direct TheStatsAPI IDs are accepted only after the corresponding FootyStats
    # fixture is verified. This makes FootyStats endpoint coverage the eligibility gate.
    if not fixture.get("footystats_competition"):
        original = dict(fixture)
        legacy = COMPETITION_PROFILES.get(str(original.get("competition_id") or original.get("comp") or ""), {})
        competition_hint = legacy.get("name") or original.get("competition_name")
        day = datetime.fromtimestamp(float(original["kickoff_unix"]), timezone.utc).date().isoformat()
        fixture = resolve_fixture_request(original["home"], original["away"], day, competition_hint)
        fixture["fixture_id"] = str(original["fixture_id"])
        fixture["thestats_fixture_id"] = str(original["fixture_id"])
        fixture["thestats_competition_id"] = original.get("competition_id") or original.get("comp")
        fixture["resolution_source"] += "+thestats_fixture_verified"
        fixture_id = fixture["fixture_id"]

    fs_context = fixture["footystats_competition"]
    comp = str(fixture.get("competition_id") or fixture.get("comp") or "")
    profile = {"name": fs_context["name"], "country": fs_context.get("country"),
               "pilotc_covered": fs_context["name"] in PILOTC_FOOTYSTATS_COMPETITIONS}
    cross = validated_crosswalk(fixture["home"], fixture["away"], fixture)
    history, history_meta = load_two_season_history(fixture["home"], fixture["away"],
                                                     fixture["kickoff_unix"], comp,
                                                     fixture=fixture)
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
    odds_fixture_id = fixture.get("thestats_fixture_id")
    if odds_fixture_id:
        raw_odds, quota = capture_odds(str(odds_fixture_id), source_dir,
                                        refresh=refresh_odds,
                                        kickoff_unix=fixture["kickoff_unix"])
    else:
        raw_odds = {}
        quota = {"live_requests": 0, "monthly_remaining": None,
                 "monthly_limit": None, "monthly_reset": None, "sources": [],
                 "note": "No independently verified TheStatsAPI fixture ID; league analysis continues without executable odds."}
    books = parse_books(raw_odds)
    full_ms = mix.load_corpus(); full_hist = mix.build_histories(full_ms)
    local_diagnostics = local_walk_forward_diagnostics(full_ms, full_hist,
                                                        fixture["home"], fixture["away"])
    markets, diagnostic = analyze_markets(fixture, history, books, local_diagnostics)
    source_hashes = {s["book"]: s["sha256"] for s in quota["sources"]}
    report = {
        "request_id": request_id, "generated_at": now_iso(), "requested_by": requested_by,
        "fixture": fixture, "crosswalk": cross,
        "inference_domain": {
            "competition_profile": profile["name"],
            "pilotc_preregistered_coverage": bool(profile["pilotc_covered"]),
            "classification": ("pilotc-covered" if profile["pilotc_covered"]
                               else "fixture-research-out-of-pilotc-domain"),
            "note": ("This result remains outside the Pilot C preregistered sample and "
                     "can only use the structurally separate fixture-research path."
                     if not profile["pilotc_covered"] else
                     "Fixture is within a Pilot C covered competition."),
        },
        "information_cutoff": {"rule": "strict date_unix < fixture kickoff",
                               "cutoff_unix": fixture["kickoff_unix"],
                               "target_match_stats_consumed": False},
        "request_plan": {"history_source": "FootyStats endpoint-backed two-season history",
                         "footystats_competition": fs_context,
                         "history_fallback": history_meta["fallback"],
                         "heatmaps": {"available": False,
                                      "reason": "TheStatsAPI heatmap/positions/touchmap probes returned no usable endpoint; not imputed."},
                         "odds_live_request_cap": MAX_ODDS_REQUESTS,
                         "odds_association_live_request_cap": MAX_ODDS_ASSOCIATION_REQUESTS,
                         "odds_resolution": fixture.get("odds_resolution"),
                         "history_live_request_cap": MAX_HISTORY_REQUESTS,
                         "resolver_live_request_cap": MAX_RESOLVE_REQUESTS},
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
    odds_note = "TheStatsAPI odds" if f.get("thestats_fixture_id") else "no verified odds fixture"
    lines.append(f"Sources: FootyStats endpoint-backed history + {odds_note} | live odds requests={q['live_requests']} | monthly={q['monthly_remaining']}/{q['monthly_limit']}")
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
    selector = ap.add_mutually_exclusive_group(required=True)
    selector.add_argument("--fixture-id", help="TheStatsAPI fixture ID; league support is verified through FootyStats")
    selector.add_argument("--home", help="exact FootyStats home-team name; requires --away, --date and --competition")
    ap.add_argument("--away", help="exact FootyStats away-team name")
    ap.add_argument("--date", help="fixture UTC date, YYYY-MM-DD")
    ap.add_argument("--competition", help="FootyStats league name or unambiguous slug")
    ap.add_argument("--requested-by", default="unspecified")
    ap.add_argument("--refresh-odds", action="store_true", help="force new versioned odds snapshots (max 3 calls)")
    ap.add_argument("--commit", action="store_true", help="attest the report in the separate fixture-research ledger")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.home:
        missing = [name for name in ("away", "date", "competition") if not getattr(args, name)]
        if missing:
            ap.error("--home requires " + ", ".join(f"--{name}" for name in missing))
        fixture = resolve_fixture_request(args.home, args.away, args.date, args.competition)
    else:
        if any((args.away, args.date, args.competition)):
            ap.error("--away, --date and --competition are only valid with --home")
        fixture = resolve_fixture(args.fixture_id)
    report = build_report(fixture["fixture_id"], args.requested_by, args.refresh_odds,
                          args.commit, resolved_fixture=fixture)
    print(json.dumps(report, indent=2, default=str) if args.json else render(report))


if __name__ == "__main__":
    main()
