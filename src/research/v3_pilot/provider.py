"""TheStatsAPI-only repository for the frozen V3 pilot."""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path
from typing import Any

from src.research.prospective.api_contract import Endpoint, ProspectiveClientConfig
from src.research.prospective.capture import ProspectiveApiClient, payload_hash

from .config import (
    HISTORY_REFRESH_SECONDS,
    HISTORY_ROOT,
    MONTHLY_RESERVE,
    PER_RUN_REQUEST_CAP,
    PROVIDER_CACHE,
    MIN_REQUEST_INTERVAL_SECONDS,
)

class ProviderBudgetStop(RuntimeError):
    pass

def _ts(value: str) -> float:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()

def _atomic_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)

class V3Provider:
    def __init__(self, *, request_cap: int = PER_RUN_REQUEST_CAP) -> None:
        cfg = ProspectiveClientConfig(
            rate_limit_seconds=MIN_REQUEST_INTERVAL_SECONDS,
            max_retries=2,
            timeout_seconds=30.0,
        )
        self.client = ProspectiveApiClient(config=cfg)
        self.request_cap = int(request_cap)
        self.requests = 0

    def _guard(self) -> None:
        if self.requests >= self.request_cap:
            raise ProviderBudgetStop(f"per-run request cap {self.request_cap} reached")
        rl = self.client.last_rate_limit
        if rl is not None:
            remaining = getattr(rl, "monthly_remaining", None)
            if remaining not in (None, -1) and int(remaining) <= MONTHLY_RESERVE:
                raise ProviderBudgetStop(
                    f"monthly reserve reached: remaining={remaining}, reserve={MONTHLY_RESERVE}"
                )

    def _raw_path(self, kind: str, entity: str, observed_at: float, ph: str) -> Path:
        safe = entity.replace("/", "_").replace(":", "_")
        return PROVIDER_CACHE / kind / safe / f"{int(observed_at)}_{ph}.json"

    def _get(self, endpoint: Endpoint, *, kind: str, entity: str,
             params: dict | None = None, **path: str) -> tuple[Any, float, str]:
        self._guard()
        observed = time.time()
        payload = self.client.get(endpoint, params=params, **path)
        self.requests += 1
        if payload is None:
            return None, observed, ""
        ph = payload_hash(payload)
        raw_path = self._raw_path(kind, entity, observed, ph)
        if not raw_path.exists():
            _atomic_json(raw_path, payload)
        return payload, observed, ph

    def seasons(self, competition_id: str) -> list[dict]:
        payload, _, _ = self._get(
            Endpoint.COMPETITION_SEASONS,
            kind="seasons", entity=competition_id,
            competition_id=competition_id,
        )
        return list((payload or {}).get("data", []))

    def finished_matches(self, competition_id: str, season_id: str) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            params = {
                "competition_id": competition_id, "season_id": season_id,
                "status": "finished", "per_page": 100, "page": page,
            }
            payload, _, _ = self._get(
                Endpoint.MATCHES, kind="matches",
                entity=f"{competition_id}_{season_id}_p{page}", params=params,
            )
            rows = list((payload or {}).get("data", []))
            out.extend(rows)
            meta = (payload or {}).get("meta", {}) if isinstance(payload, dict) else {}
            total_pages = int(meta.get("total_pages") or 1)
            if page >= total_pages or not rows:
                break
            page += 1
            if page > 20:
                raise RuntimeError("unexpected matches pagination >20 pages")
        return out

    @staticmethod
    def _normalize_match(m: dict) -> dict | None:
        try:
            score = m.get("score") or {}
            home_score, away_score = score.get("home"), score.get("away")
            if home_score is None or away_score is None:
                return None
            return {
                "match_id": str(m["id"]),
                "competition_id": str(m["competition_id"]),
                "season_id": str(m["season_id"]),
                "ts": float(_ts(str(m["utc_date"]))),
                "utc_date": str(m["utc_date"]),
                "home_id": str(m["home_team"]["id"]),
                "home_name": str(m["home_team"].get("name") or ""),
                "away_id": str(m["away_team"]["id"]),
                "away_name": str(m["away_team"].get("name") or ""),
                "score": {"home": int(home_score), "away": int(away_score)},
                "is_neutral": bool(m.get("is_neutral", False)),
            }
        except (KeyError, TypeError, ValueError):
            return None

    def _latest_history_pointer(self, competition_id: str) -> Path:
        return HISTORY_ROOT / competition_id / "latest.json"

    def load_history(self, competition_id: str) -> dict | None:
        p = self._latest_history_pointer(competition_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def history_fresh(self, competition_id: str, *, now: float | None = None) -> bool:
        obj = self.load_history(competition_id)
        if not obj:
            return False
        now = time.time() if now is None else now
        return now - float(obj.get("observed_at", 0)) <= HISTORY_REFRESH_SECONDS

    def refresh_history(self, competition_id: str, *, seasons_back: int = 4,
                        force: bool = False) -> dict:
        if not force and self.history_fresh(competition_id):
            current = self.load_history(competition_id)
            if current is not None:
                return current
        seasons = self.seasons(competition_id)
        if not seasons:
            raise RuntimeError(f"no seasons returned for {competition_id}")
        def skey(s: dict) -> tuple:
            # Provider display years may be strings such as "26/27". Bind
            # chronology to explicit numeric start/end fields instead of IDs.
            def iv(v):
                try:
                    return int(v)
                except (TypeError, ValueError):
                    return -1
            return (iv(s.get("start_year")), iv(s.get("end_year")),
                    str(s.get("id", "")))
        selected = sorted(seasons, key=skey, reverse=True)[:seasons_back]
        norm: list[dict] = []
        for s in selected:
            sid = str(s.get("id") or "")
            if not sid:
                continue
            season_cache = HISTORY_ROOT / competition_id / "completed_seasons" / f"{sid}.json"
            is_current = bool(s.get("is_current"))
            if not is_current and season_cache.exists():
                cached = json.loads(season_cache.read_text(encoding="utf-8"))
                norm.extend(cached.get("matches", []))
                continue
            raw_matches = self.finished_matches(competition_id, sid)
            season_rows = [
                r for r in (self._normalize_match(m) for m in raw_matches)
                if r is not None
            ]
            norm.extend(season_rows)
            if not is_current:
                _atomic_json(season_cache, {
                    "competition_id": competition_id, "season_id": sid,
                    "provider": "THESTATSAPI_ONLY",
                    "matches": season_rows, "season_hash": payload_hash(season_rows),
                })
        dedup = {r["match_id"]: r for r in norm}
        rows = sorted(dedup.values(), key=lambda r: (r["ts"], r["match_id"]))
        observed = time.time()
        obj = {
            "competition_id": competition_id,
            "observed_at": observed,
            "season_ids": [str(s.get("id")) for s in selected if s.get("id")],
            "matches": rows,
            "history_hash": payload_hash(rows),
        }
        snap = HISTORY_ROOT / competition_id / f"history_{int(observed)}_{obj['history_hash']}.json"
        _atomic_json(snap, obj)
        _atomic_json(self._latest_history_pointer(competition_id), obj)
        return obj

    def upcoming(self, competition_id: str, *, hours: int = 48) -> list[dict]:
        now = time.time()
        horizon = now + hours * 3600
        date_from = dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat()
        date_to = dt.datetime.fromtimestamp(horizon, dt.timezone.utc).date().isoformat()
        payload, observed, ph = self._get(
            Endpoint.MATCHES, kind="upcoming", entity=competition_id,
            params={"status": "scheduled", "competition_id": competition_id,
                    "date_from": date_from, "date_to": date_to, "per_page": 100},
        )
        out = []
        for m in list((payload or {}).get("data", [])):
            try:
                ts = _ts(str(m["utc_date"]))
                if not (now <= ts <= horizon):
                    continue
                out.append({
                    "match_id": str(m["id"]), "competition_id": str(m["competition_id"]),
                    "season_id": str(m["season_id"]), "ts": ts, "utc_date": str(m["utc_date"]),
                    "home_id": str(m["home_team"]["id"]), "home_name": str(m["home_team"].get("name") or ""),
                    "away_id": str(m["away_team"]["id"]), "away_name": str(m["away_team"].get("name") or ""),
                    "provider_observed_at": observed, "provider_payload_hash": ph,
                })
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(out, key=lambda r: (r["ts"], r["match_id"]))

    def odds(self, match_id: str) -> tuple[dict | None, float, str]:
        return self._get(
            Endpoint.MATCH_ODDS, kind="odds", entity=match_id, match_id=match_id
        )

    def match_detail(self, match_id: str) -> tuple[dict | None, float, str]:
        return self._get(
            Endpoint.MATCH_DETAIL, kind="match_detail", entity=match_id, match_id=match_id
        )

    def _stats_cache(self, match_id: str) -> Path:
        return PROVIDER_CACHE / "finished_stats" / f"{match_id}.json"

    def stats(self, match_id: str) -> tuple[dict | None, float, str]:
        p = self._stats_cache(match_id)
        if p.exists():
            obj = json.loads(p.read_text(encoding="utf-8"))
            return obj["payload"], float(obj["observed_at"]), str(obj["payload_hash"])
        payload, observed, ph = self._get(
            Endpoint.MATCH_STATS, kind="stats_raw", entity=match_id, match_id=match_id
        )
        if payload is not None:
            _atomic_json(p, {"observed_at": observed, "payload_hash": ph, "payload": payload})
        return payload, observed, ph

    @staticmethod
    def _corner_row(match: dict, stats_payload: dict) -> dict | None:
        try:
            allv = stats_payload["data"]["overview"]["corner_kicks"]["all"]
            if not isinstance(allv, dict):
                return None
            h, a = allv.get("home"), allv.get("away")
            if h is None or a is None:
                return None
            return {
                "match_id": match["match_id"], "competition_id": match["competition_id"],
                "season_id": match["season_id"], "ts": match["ts"],
                "home_id": match["home_id"], "away_id": match["away_id"],
                "corners_home": float(h), "corners_away": float(a),
            }
        except (KeyError, TypeError, ValueError):
            return None

    def corner_history(self, history: dict, target: dict) -> list[dict]:
        rows = [m for m in history.get("matches", []) if float(m["ts"]) < float(target["ts"])]
        home_id, away_id = str(target["home_id"]), str(target["away_id"])
        team_rows = [
            m for m in rows
            if home_id in (str(m["home_id"]), str(m["away_id"]))
            or away_id in (str(m["home_id"]), str(m["away_id"]))
        ][-24:]
        baseline_rows = rows[-30:]
        needed = {m["match_id"]: m for m in baseline_rows + team_rows}
        out = []
        for m in sorted(needed.values(), key=lambda r: (r["ts"], r["match_id"])):
            payload, _, _ = self.stats(m["match_id"])
            if payload is None:
                continue
            cr = self._corner_row(m, payload)
            if cr is not None:
                out.append(cr)
        return out
